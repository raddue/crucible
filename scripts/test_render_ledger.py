#!/usr/bin/env python3
"""Tests for render_ledger.py — the /ledger weekly render core (#408 F16b).

render_ledger is the source of truth for the honest "caught N silent bugs"
headline, the §4a inflation detector, the falsification cross-link, and the
Phase-7 predicate calibration table. None of that pipeline had direct tests
(only the in-repo fixture round-trip exercised `main`). These are pure-stdlib
unittest cases — `python3 scripts/test_render_ledger.py`, registered in
run_tests.sh."""
import contextlib
import datetime as _dt
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts import render_ledger as rl  # noqa: E402
from scripts.reconcile_ledger import ledger_entry_hash  # noqa: E402


def _entry(**over):
    """A forward-captured Tier-A-ish row with a valid (run_id, skill) identity."""
    e = {
        "run_id": "0190aaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "skill": "quality-gate",
        "timestamp": "2026-06-10T10:00:00Z",
        "verdict": "PASS",
        "would_have_shipped_without_gate": False,
        "backfilled": False,
        "severity_histogram": {"fatal": 0, "significant": 0, "minor": 0, "nit": 0},
    }
    e.update(over)
    return e


# --------------------------------------------------------------------------- #
# load_runs                                                                   #
# --------------------------------------------------------------------------- #

class LoadRunsTest(unittest.TestCase):
    def _write(self, d, text, *, mode="w"):
        path = os.path.join(d, "runs.jsonl")
        with open(path, mode) as f:
            f.write(text)
        return path

    def test_missing_file_returns_empty(self):
        self.assertEqual(rl.load_runs("/no/such/runs.jsonl"), [])

    def test_empty_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(rl.load_runs(self._write(d, "")), [])

    def test_skips_blank_and_malformed_lines(self):
        with tempfile.TemporaryDirectory() as d:
            text = (json.dumps(_entry(run_id="r1")) + "\n\n"
                    + "{not json\n"
                    + "[1,2,3]\n"  # valid JSON, non-dict -> skipped
                    + json.dumps(_entry(run_id="r2")) + "\n")
            path = self._write(d, text)
            # #400 contract: corruption is COUNTED and surfaced via _warn to
            # stderr, not silently dropped — capture and assert the warn fires.
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                out = rl.load_runs(path)
            self.assertEqual([o["run_id"] for o in out], ["r1", "r2"])
            self.assertIn("skipped 2 unparseable", err.getvalue())

    def test_dedup_latest_wins_preserves_first_seen_order(self):
        with tempfile.TemporaryDirectory() as d:
            text = (json.dumps(_entry(run_id="r1", verdict="PASS")) + "\n"
                    + json.dumps(_entry(run_id="r2")) + "\n"
                    + json.dumps(_entry(run_id="r1", verdict="FAIL")) + "\n")
            out = rl.load_runs(self._write(d, text))
            # r1 kept its first-seen slot but took the later verdict.
            self.assertEqual([o["run_id"] for o in out], ["r1", "r2"])
            self.assertEqual(out[0]["verdict"], "FAIL")

    def test_partial_trailing_line_dropped(self):
        with tempfile.TemporaryDirectory() as d:
            text = (json.dumps(_entry(run_id="r1")) + "\n"
                    + json.dumps(_entry(run_id="r2")))  # no terminating newline
            out = rl.load_runs(self._write(d, text))
            self.assertEqual([o["run_id"] for o in out], ["r1"])


# --------------------------------------------------------------------------- #
# iso_week                                                                     #
# --------------------------------------------------------------------------- #

class IsoWeekTest(unittest.TestCase):
    def test_basic_and_trailing_z(self):
        self.assertEqual(rl.iso_week({"timestamp": "2026-06-10T10:00:00Z"}),
                         "2026-W24")
        self.assertEqual(rl.iso_week({"timestamp": "2026-06-10T10:00:00+00:00"}),
                         "2026-W24")

    def test_iso_week_year_can_differ_from_calendar_year(self):
        # 2027-01-01 is a Friday in ISO week 53 of week-year 2026.
        self.assertEqual(rl.iso_week({"timestamp": "2027-01-01T00:00:00Z"}),
                         "2026-W53")

    def test_bad_timestamp_raises(self):
        with self.assertRaises(ValueError):
            rl.iso_week({"timestamp": "not-a-date"})


# --------------------------------------------------------------------------- #
# caught_count / _is_forward                                                   #
# --------------------------------------------------------------------------- #

class CaughtCountTest(unittest.TestCase):
    def test_counts_whs_true_excludes_backfilled(self):
        entries = [
            _entry(run_id="a", would_have_shipped_without_gate=True),
            _entry(run_id="b", would_have_shipped_without_gate=False),
            _entry(run_id="c", would_have_shipped_without_gate=None),
            # backfilled + WHS forced True is STILL excluded (keys on backfilled).
            _entry(run_id="d", backfilled=True,
                   would_have_shipped_without_gate=True, severity_histogram=None),
        ]
        self.assertEqual(rl.caught_count(entries), 1)

    def test_is_forward(self):
        self.assertTrue(rl._is_forward(_entry()))
        self.assertFalse(rl._is_forward(_entry(backfilled=True)))
        self.assertFalse(rl._is_forward(_entry(severity_histogram=None)))


# --------------------------------------------------------------------------- #
# week_summary                                                                 #
# --------------------------------------------------------------------------- #

class WeekSummaryTest(unittest.TestCase):
    def test_per_skill_rates_from_forward_only(self):
        entries = [
            _entry(run_id="a", skill="audit",
                   severity_histogram={"fatal": 1, "significant": 1,
                                       "minor": 2, "nit": 0}),
            # backfilled row for the same skill must NOT dilute the rate.
            _entry(run_id="b", skill="audit", backfilled=True,
                   severity_histogram=None),
        ]
        s = rl.week_summary(entries)
        audit = s["per_skill"]["audit"]
        self.assertEqual(audit["forward_entries"], 1)
        self.assertEqual(audit["findings"], 4)
        self.assertAlmostEqual(audit["fatal_rate"], 0.25)
        self.assertAlmostEqual(audit["significant_rate"], 0.25)
        self.assertEqual(s["backfilled"], 1)

    def test_zero_findings_rate_is_zero_not_division_error(self):
        s = rl.week_summary([_entry(skill="recon")])
        self.assertEqual(s["per_skill"]["recon"]["significant_rate"], 0.0)
        self.assertEqual(s["per_skill"]["recon"]["fatal_rate"], 0.0)

    def test_identityless_row_skipped_from_per_skill(self):
        # Missing skill -> no valid (run_id, skill) identity -> skipped, not
        # bucketed under an "unknown" skill key.
        entries = [_entry(run_id="a"), {"run_id": "x", "timestamp": "t"}]
        s = rl.week_summary(entries)
        self.assertIn("quality-gate", s["per_skill"])
        self.assertEqual(len(s["per_skill"]), 1)
        # total_runs counts the raw list (identity filter is per-skill only).
        self.assertEqual(s["total_runs"], 2)
        # Asymmetry by design: per_repo keys on `repo`, NOT the (run_id, skill)
        # join, so it does NOT apply the identity guard — the identityless row
        # still leaks into per_repo as 'unknown' (no `repo` key). Intentional.
        self.assertEqual(s["per_repo"]["unknown"]["runs"], 2)

    def test_per_repo_breakdown_and_caught_subset(self):
        entries = [
            _entry(run_id="a", repo="riftlock",
                   would_have_shipped_without_gate=True),
            _entry(run_id="b", repo="riftlock"),
            _entry(run_id="c"),  # no repo key -> 'unknown'
            _entry(run_id="d", repo="driftmap", backfilled=True,
                   severity_histogram=None),  # backfilled excluded from per_repo
        ]
        s = rl.week_summary(entries)
        self.assertEqual(s["per_repo"]["riftlock"], {"runs": 2, "caught": 1})
        self.assertEqual(s["per_repo"]["unknown"], {"runs": 1, "caught": 0})
        self.assertNotIn("driftmap", s["per_repo"])


# --------------------------------------------------------------------------- #
# inflation_alert (§4a)                                                        #
# --------------------------------------------------------------------------- #

class InflationAlertTest(unittest.TestCase):
    RATES = {"audit": {"significant_rate": 0.6, "fatal_rate": 0.0}}

    def test_silent_during_bootstrap(self):
        base = {"audit": {"significant_median": 0.1, "fatal_median": 0.0,
                          "weeks": 3}}  # < MIN_BASELINE_WEEKS
        self.assertEqual(rl.inflation_alert(self.RATES, base), [])

    def test_missing_baseline_silent(self):
        self.assertEqual(rl.inflation_alert(self.RATES, {}), [])

    def test_fires_above_3x_median(self):
        base = {"audit": {"significant_median": 0.1, "fatal_median": 0.0,
                          "weeks": 4}}  # 0.6 > 3 * 0.1
        alerts = rl.inflation_alert(self.RATES, base)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["skill"], "audit")

    def test_no_fire_within_threshold(self):
        base = {"audit": {"significant_median": 0.3, "fatal_median": 0.0,
                          "weeks": 4}}  # 0.6 < 3 * 0.3 = 0.9
        self.assertEqual(rl.inflation_alert(self.RATES, base), [])

    def test_zero_median_never_fires(self):
        # A zero baseline median can't define "3x" — must stay silent.
        base = {"audit": {"significant_median": 0.0, "fatal_median": 0.0,
                          "weeks": 4}}
        self.assertEqual(rl.inflation_alert(self.RATES, base), [])


# --------------------------------------------------------------------------- #
# falsified_count / falsified_breakdown / _breakdown_from_reduced             #
# --------------------------------------------------------------------------- #

class FalsifiedTest(unittest.TestCase):
    def test_missing_file_counts_zero(self):
        self.assertEqual(rl.falsified_count("/no/such/falsification.jsonl"), 0)

    def test_count_and_breakdown_from_file(self):
        rows = [
            {"ledger_entry_hash": "h1", "falsified": True, "via": "walkback"},
            {"ledger_entry_hash": "h2", "falsified": True, "via": "predicate"},
            {"ledger_entry_hash": "h3", "falsified": False, "via": "walkback"},
            {"ledger_entry_hash": "h4", "falsified": True,
             "falsified_by": {"manual_override": True}},
            {"ledger_entry_hash": "h5", "falsified": True,
             "signal_type": "bad_implementation"},
        ]
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "falsification.jsonl")
            with open(path, "w") as f:
                for r in rows:
                    f.write(json.dumps(r) + "\n")
            self.assertEqual(rl.falsified_count(path), 4)
            bd = rl.falsified_breakdown(path)
            self.assertEqual(bd, {"walkback": 1, "predicate": 1,
                                  "manual_override": 1, "bad_implementation": 1})

    def test_breakdown_precedence_via_beats_signal(self):
        # via=="walkback" wins even when a bad_implementation signal co-exists.
        reduced = {
            "h1": {"falsified": True, "via": "walkback",
                   "signal_type": "bad_implementation"},
            "h2": {"falsified": True, "via": None,
                   "falsified_by": {"signal_type": "bad_implementation"}},
            "h3": {"falsified": False, "via": "predicate"},  # not falsified
        }
        bd = rl._breakdown_from_reduced(reduced)
        self.assertEqual(bd["walkback"], 1)
        self.assertEqual(bd["bad_implementation"], 1)
        self.assertEqual(bd["predicate"], 0)


# --------------------------------------------------------------------------- #
# predicate_rates (Phase 7, §3a)                                              #
# --------------------------------------------------------------------------- #

class PredicateRatesTest(unittest.TestCase):
    NOW = "2026-07-01T00:00:00Z"  # well past the 30d grace for June 1 entries

    def test_sentinel_excluded_no_slot(self):
        e = _entry(predicted_falsifier=rl.PREDICATE_SENTINEL)
        out = rl.predicate_rates([e], {}, now=self.NOW)
        self.assertEqual(out, {})

    def test_null_predicate_ignored(self):
        out = rl.predicate_rates([_entry(predicted_falsifier=None)], {},
                                 now=self.NOW)
        self.assertEqual(out, {})

    def test_unparseable_counts_in_denominator(self):
        e = _entry(skill="audit", predicted_falsifier="it will break somehow")
        out = rl.predicate_rates([e], {}, now=self.NOW)["audit"]
        self.assertEqual(out["total_non_null"], 1)
        self.assertEqual(out["unparseable"], 1)
        self.assertEqual(out["parseable"], 0)
        self.assertAlmostEqual(out["unparseable_rate"], 1.0)

    def test_non_revert_hash_is_uncheckable_not_parseable(self):
        # A `fix of artifact_hash=…` parses but has no candidate population ->
        # uncheckable, excluded from the hit-rate denominator. The `timestamp`
        # is irrelevant here: the uncheckable branch short-circuits before the
        # grace check ever reads it.
        e = _entry(skill="audit",
                   timestamp="2026-06-01T00:00:00Z",
                   predicted_falsifier="fix of artifact_hash=abc123 within 30d")
        out = rl.predicate_rates([e], {}, now=self.NOW)["audit"]
        self.assertEqual(out["uncheckable"], 1)
        self.assertEqual(out["parseable"], 0)
        self.assertEqual(out["unparseable"], 0)

    def test_grace_cutoff_boundary_is_inside_grace(self):
        # The exact cutoff (NOW - 30d = 2026-06-01T00:00:00Z) is treated as
        # INSIDE grace under the strict `<` in predicate_rates -> not parseable.
        # Pins the boundary direction so a `<`->`<=` refactor would fail here.
        e = _entry(skill="audit",
                   timestamp="2026-06-01T00:00:00Z",
                   predicted_falsifier="fix touching scripts/foo.py within 30d")
        out = rl.predicate_rates([e], {}, now=self.NOW)["audit"]
        self.assertEqual(out["parseable"], 0)
        self.assertEqual(out["total_non_null"], 1)

    def test_inside_grace_not_counted_in_parseable(self):
        # Timestamp 5 days before NOW is inside the 30d grace -> a checkable
        # predicate that has NOT yet had a full chance to fire.
        e = _entry(skill="audit",
                   timestamp="2026-06-26T00:00:00Z",
                   predicted_falsifier="fix touching scripts/foo.py within 30d")
        out = rl.predicate_rates([e], {}, now=self.NOW)["audit"]
        self.assertEqual(out["parseable"], 0)
        self.assertEqual(out["total_non_null"], 1)

    def test_outside_grace_hit_counted(self):
        run_id = "0190aaaa-bbbb-cccc-dddd-000000000001"
        # 2026-05-15 is strictly before the grace cutoff (NOW - 30d = 2026-06-01).
        e = _entry(run_id=run_id, skill="audit",
                   timestamp="2026-05-15T00:00:00Z",
                   predicted_falsifier="fix touching scripts/foo.py within 30d")
        h = ledger_entry_hash(run_id, "audit")
        reduced = {h: {"falsified": True, "via": "predicate"}}
        out = rl.predicate_rates([e], reduced, now=self.NOW)["audit"]
        self.assertEqual(out["parseable"], 1)
        self.assertEqual(out["hit_count"], 1)
        self.assertAlmostEqual(out["hit_rate"], 1.0)

    def test_outside_grace_non_predicate_falsification_no_hit(self):
        # A falsification record that is NOT via=="predicate" doesn't count as a
        # predicate hit even though the entry is in the parseable denominator.
        run_id = "0190aaaa-bbbb-cccc-dddd-000000000002"
        e = _entry(run_id=run_id, skill="audit",
                   timestamp="2026-05-15T00:00:00Z",
                   predicted_falsifier="fix touching scripts/foo.py within 30d")
        h = ledger_entry_hash(run_id, "audit")
        reduced = {h: {"falsified": True, "via": "walkback"}}
        out = rl.predicate_rates([e], reduced, now=self.NOW)["audit"]
        self.assertEqual(out["parseable"], 1)
        self.assertEqual(out["hit_count"], 0)
        self.assertAlmostEqual(out["hit_rate"], 0.0)

    def test_identityless_predicate_row_skipped(self):
        e = {"timestamp": "2026-06-01T00:00:00Z",
             "predicted_falsifier": "fix touching scripts/foo.py within 30d"}
        self.assertEqual(rl.predicate_rates([e], {}, now=self.NOW), {})


# --------------------------------------------------------------------------- #
# _commit_citation                                                            #
# --------------------------------------------------------------------------- #

class CommitCitationTest(unittest.TestCase):
    def test_backfilled_pr_citation(self):
        e = {"backfilled": True, "run_id": "backfill-410-quality-gate"}
        self.assertEqual(rl._commit_citation(e), "PR #410")

    def test_forward_uuid_has_no_citation(self):
        self.assertIsNone(rl._commit_citation(_entry(run_id="0190-uuid-here")))

    def test_backfill_non_numeric_pr_is_none(self):
        e = {"backfilled": True, "run_id": "backfill-foo-quality-gate"}
        self.assertIsNone(rl._commit_citation(e))


# --------------------------------------------------------------------------- #
# _group_by_week / _week_month / first_of_month_weeks                          #
# --------------------------------------------------------------------------- #

class GroupingTest(unittest.TestCase):
    def test_group_by_week_skips_bad_timestamp(self):
        entries = [
            _entry(run_id="a", timestamp="2026-06-10T10:00:00Z"),
            _entry(run_id="b", timestamp="garbage"),
            _entry(run_id="c", timestamp="2026-06-10T11:00:00Z"),
        ]
        groups = rl._group_by_week(entries)
        self.assertEqual(set(groups), {"2026-W24"})
        self.assertEqual(len(groups["2026-W24"]), 2)

    def test_week_month(self):
        self.assertEqual(rl._week_month("2026-W24"), "2026-06")
        self.assertIsNone(rl._week_month("not-a-week"))

    def test_first_of_month_picks_earliest_per_month(self):
        # Earliest-wins per calendar month, pinned with a HARDCODED expected set
        # (not derived via _week_month, the same helper the code uses — a co-bug
        # in the earliest-wins direction must fail here). Week->month of each
        # Monday: W22->2026-05, W23/W24/W27->2026-06, W30->2026-07; so the
        # earliest per month is W22, W23, W30. Month-correctness itself is
        # independently anchored by test_week_month.
        weeks = ["2026-W24", "2026-W23", "2026-W22", "2026-W27", "2026-W30"]
        fom = rl.first_of_month_weeks(weeks)
        self.assertEqual(fom, {"2026-W22", "2026-W23", "2026-W30"})


# --------------------------------------------------------------------------- #
# render_week (smoke / contract)                                              #
# --------------------------------------------------------------------------- #

class RenderWeekTest(unittest.TestCase):
    def test_headline_singular_plural_and_sections(self):
        one = rl.render_week("2026-W24",
                             [_entry(would_have_shipped_without_gate=True)],
                             now=PredicateRatesTest.NOW)
        self.assertIn("## Crucible caught 1 silent bug\n", one)
        self.assertIn("## Verdict breakdown", one)
        self.assertIn("## Falsified verdicts (cross-link)", one)

        none = rl.render_week("2026-W24", [_entry()], now=PredicateRatesTest.NOW)
        self.assertIn("caught 0 silent bugs", none)

    def test_falsified_by_source_line_rendered(self):
        # The `if falsified > 0:` by-source branch is otherwise never exercised
        # (default falsified=0). Smoke-assert the `_By source: …_` line renders.
        md = rl.render_week(
            "2026-W24", [_entry()], falsified=1,
            falsification_reduced={"h": {"falsified": True, "via": "walkback"}},
            now=PredicateRatesTest.NOW)
        self.assertIn("_By source: walkback 1._", md)

    def test_inflation_block_rendered_when_armed(self):
        entries = [_entry(skill="audit",
                          severity_histogram={"fatal": 0, "significant": 3,
                                              "minor": 0, "nit": 0})]
        base = {"audit": {"significant_median": 0.1, "fatal_median": 0.0,
                          "weeks": 4}}
        md = rl.render_week("2026-W24", entries, baseline_medians=base,
                            now=PredicateRatesTest.NOW)
        self.assertIn("## ⚠ Inflation alert", md)
        self.assertIn("**audit**", md)

    def test_first_of_month_adds_spotcheck(self):
        md = rl.render_week("2026-W24", [_entry()], is_first_of_month=True,
                            now=PredicateRatesTest.NOW)
        self.assertIn("## Monthly spot-check", md)
        plain = rl.render_week("2026-W24", [_entry()], is_first_of_month=False,
                               now=PredicateRatesTest.NOW)
        self.assertNotIn("## Monthly spot-check", plain)


if __name__ == "__main__":
    unittest.main()
