#!/usr/bin/env python3
"""T-5: /ledger honest "caught N" headline + supporting renderer tests.

The Phase-5 renderer core lives at `scripts/render_ledger.py`. Its filename is
underscore-named, so it imports normally as `scripts.render_ledger` (unlike the
hyphenated `backfill-ledger.py`, which requires importlib).

T-5 (required, design §4 + §4a "Honest count" + L-3/L-5):
  The "caught N silent bugs" headline counts entries with
  `would_have_shipped_without_gate == True` EXCLUDING `backfilled == True`.
  Backfilled entries carry `severity_histogram: null` -> WHS null -> excluded.
  The fixture mixes, in ONE ISO week:
    - a backfilled WHS-null entry      (excluded: backfilled + WHS null)
    - a forward WHS:true entry         (counted)
    - a forward WHS:false entry        (excluded: WHS false)
  Assert caught_count == exactly the forward-WHS-true count (== 1).

Supporting tests: iso_week grouping, tolerant load (malformed line skipped),
missing runs.jsonl -> load_runs == [] and main prints "no ledger data yet",
falsified_count == 0 when falsification.jsonl absent, raw rates computed from
forward entries only (backfilled excluded from rate denominator).

Run: python3 -m pytest eval/calibration-ledger/test-ledger-headline-t5.py -v
"""
import io
import json
import os
import sys
from contextlib import redirect_stdout

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts import render_ledger as rl  # noqa: E402


# --------------------------------------------------------------------------- #
# Entry builders                                                              #
# --------------------------------------------------------------------------- #

def _forward_entry(run_id, *, whs, fatal=0, significant=0, minor=0, nit=0,
                   skill="quality-gate", verdict="PASS",
                   timestamp="2026-05-18T12:00:00Z"):
    """A forward-captured entry: backfilled=False, real severity_histogram."""
    return {
        "schema_version": 1,
        "run_id": run_id,
        "skill": skill,
        "tier": "A",
        "artifact_type": "code",
        "verdict": verdict,
        "confidence": 0.8,
        "artifact_hash": "a" * 64,
        "chunk_hash": None,
        "gated_files": ["x.py"],
        "findings_count": fatal + significant + minor + nit,
        "severity_histogram": {
            "fatal": fatal, "significant": significant,
            "minor": minor, "nit": nit,
        },
        "highest_finding": "some finding" if (fatal or significant) else None,
        "would_have_shipped_without_gate": whs,
        "rounds": 1,
        "timestamp": timestamp,
        "backfilled": False,
        "falsified": None,
        "falsified_by": None,
        "gated_files_truncated": 0,
        "comment": None,
        "predicted_falsifier": None,
    }


def _backfilled_entry(run_id, *, timestamp="2026-05-18T12:00:00Z",
                      skill="quality-gate"):
    """A backfilled entry: backfilled=True, severity_histogram null, WHS null."""
    return {
        "schema_version": 1,
        "run_id": run_id,
        "skill": skill,
        "tier": "A",
        "artifact_type": "code",
        "verdict": "PASS",
        "confidence": None,
        "artifact_hash": None,
        "chunk_hash": None,
        "gated_files": ["y.py"],
        "findings_count": None,
        "severity_histogram": None,
        "highest_finding": None,
        "would_have_shipped_without_gate": None,
        "rounds": None,
        "timestamp": timestamp,
        "backfilled": True,
        "falsified": None,
        "falsified_by": None,
        "gated_files_truncated": 0,
        "comment": "inferred-from-fix",
        "predicted_falsifier": None,
    }


def _write_jsonl(path, entries):
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, separators=(",", ":")) + "\n")


# --------------------------------------------------------------------------- #
# T-5: THE headline                                                           #
# --------------------------------------------------------------------------- #

def test_t5_caught_count_excludes_backfilled_and_whs_false():
    """T-5: caught_count == forward-WHS-true count, in a mixed single ISO week."""
    entries = [
        _backfilled_entry("backfill-100-quality-gate"),          # WHS null -> excluded
        _forward_entry("fwd-true", whs=True, significant=1),     # counted
        _forward_entry("fwd-false", whs=False, minor=2),         # WHS false -> excluded
    ]
    # All three land in the SAME ISO week (2026-05-18 is in 2026-W21).
    weeks = {rl.iso_week(e) for e in entries}
    assert len(weeks) == 1, f"fixture entries must share one ISO week: {weeks}"

    assert rl.caught_count(entries) == 1

    # Make the discrimination explicit: a backfilled entry with WHS forced True
    # must STILL be excluded (the exclusion is on `backfilled`, not just WHS null).
    sneaky = _backfilled_entry("backfill-evil-quality-gate")
    sneaky["would_have_shipped_without_gate"] = True  # pathological
    assert rl.caught_count(entries + [sneaky]) == 1


# --------------------------------------------------------------------------- #
# iso_week                                                                     #
# --------------------------------------------------------------------------- #

def test_iso_week_format_and_grouping():
    e1 = _forward_entry("a", whs=True, significant=1, timestamp="2026-05-18T00:00:00Z")
    e2 = _forward_entry("b", whs=True, significant=1, timestamp="2026-05-25T00:00:00Z")
    assert rl.iso_week(e1) == "2026-W21"
    assert rl.iso_week(e2) == "2026-W22"


def test_iso_week_handles_trailing_z_and_offset():
    z = _forward_entry("z", whs=False, timestamp="2026-05-18T23:59:59Z")
    off = _forward_entry("o", whs=False, timestamp="2026-05-18T23:59:59+00:00")
    assert rl.iso_week(z) == rl.iso_week(off) == "2026-W21"


# --------------------------------------------------------------------------- #
# tolerant load                                                               #
# --------------------------------------------------------------------------- #

def test_load_runs_skips_malformed_and_blank_lines(tmp_path):
    p = tmp_path / "runs.jsonl"
    good1 = json.dumps(_forward_entry("g1", whs=True, significant=1))
    good2 = json.dumps(_forward_entry("g2", whs=False))
    with open(p, "w", encoding="utf-8") as f:
        f.write(good1 + "\n")
        f.write("\n")                       # blank line
        f.write("{not valid json\n")        # malformed line
        f.write(good2 + "\n")
    rows = rl.load_runs(str(p))
    assert len(rows) == 2
    assert {r["run_id"] for r in rows} == {"g1", "g2"}


def test_load_runs_drops_partial_trailing_line(tmp_path):
    p = tmp_path / "runs.jsonl"
    good = json.dumps(_forward_entry("ok", whs=True, significant=1))
    with open(p, "w", encoding="utf-8") as f:
        f.write(good + "\n")
        f.write('{"run_id":"partial"')      # no terminating newline
    rows = rl.load_runs(str(p))
    assert [r["run_id"] for r in rows] == ["ok"]


def test_load_runs_dedup_latest_position_wins(tmp_path):
    p = tmp_path / "runs.jsonl"
    first = _forward_entry("dup", whs=False, significant=0)
    second = _forward_entry("dup", whs=True, significant=1)  # same (run_id, skill)
    _write_jsonl(p, [first, second])
    rows = rl.load_runs(str(p))
    assert len(rows) == 1
    assert rows[0]["would_have_shipped_without_gate"] is True  # latest wins


def test_load_runs_missing_file_returns_empty():
    assert rl.load_runs("/nonexistent/path/to/runs.jsonl") == []


# --------------------------------------------------------------------------- #
# missing runs.jsonl -> main prints notice, exits 0                           #
# --------------------------------------------------------------------------- #

def test_main_missing_runs_prints_notice(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no .crucible/ledger/runs.jsonl here
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = rl.main(["--weeks", "1"])
    assert rc == 0
    assert "no ledger data yet" in buf.getvalue().lower()
    # MUST NOT write an empty report.
    assert not (tmp_path / "docs" / "ledger").exists() or \
        not list((tmp_path / "docs" / "ledger").glob("weekly-*.md"))


# --------------------------------------------------------------------------- #
# falsified_count graceful degradation                                        #
# --------------------------------------------------------------------------- #

def test_falsified_count_absent_file_returns_zero(tmp_path):
    absent = tmp_path / "falsification.jsonl"
    assert not absent.exists()
    assert rl.falsified_count(str(absent)) == 0


def test_falsified_count_reads_reduction(tmp_path):
    p = tmp_path / "falsification.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps({"ledger_entry_hash": "h1", "falsified": True}) + "\n")
        f.write(json.dumps({"ledger_entry_hash": "h2", "falsified": True}) + "\n")
        f.write(json.dumps({"ledger_entry_hash": "h1", "falsified": True}) + "\n")  # L-9 dup
    assert rl.falsified_count(str(p)) == 2  # h1 deduped by hash


# --------------------------------------------------------------------------- #
# raw rates from forward entries only                                         #
# --------------------------------------------------------------------------- #

def test_week_summary_rates_exclude_backfilled():
    """significant_rate / fatal_rate denominators use forward entries only."""
    entries = [
        # forward QG: 2 findings, 1 significant, 1 nit -> sig_rate 0.5, fatal_rate 0
        _forward_entry("f1", whs=True, significant=1, nit=1),
        # backfilled QG: must NOT enter the rate denominator at all
        _backfilled_entry("backfill-9-quality-gate"),
    ]
    summary = rl.week_summary(entries)
    qg = summary["per_skill"]["quality-gate"]
    assert qg["findings"] == 2          # only the forward entry's findings
    assert qg["significant_rate"] == pytest.approx(0.5)
    assert qg["fatal_rate"] == pytest.approx(0.0)
    assert summary["backfilled"] == 1   # reported separately
    assert summary["caught_count"] == 1


def test_week_summary_all_backfilled_zero_caught_and_no_rate():
    """The real corpus shape: all backfilled -> caught 0, rates 0 (no forward)."""
    entries = [_backfilled_entry(f"backfill-{i}-quality-gate") for i in range(5)]
    summary = rl.week_summary(entries)
    assert summary["caught_count"] == 0
    assert summary["backfilled"] == 5
    qg = summary["per_skill"]["quality-gate"]
    assert qg["findings"] == 0
    assert qg["significant_rate"] == 0.0
    assert qg["fatal_rate"] == 0.0


# --------------------------------------------------------------------------- #
# inflation alert: silent under 4 weeks of forward data                       #
# --------------------------------------------------------------------------- #

def test_inflation_alert_silent_without_4wk_baseline():
    per_skill = {"quality-gate": {"significant_rate": 0.9, "fatal_rate": 0.5}}
    baselines = {}  # no rolling history -> silent
    assert rl.inflation_alert(per_skill, baselines) == []


def test_inflation_alert_fires_above_3x_with_baseline():
    per_skill = {"quality-gate": {"significant_rate": 0.9, "fatal_rate": 0.0}}
    # 4 weeks of forward median present, low -> 0.9 > 3*0.1 -> alert
    baselines = {"quality-gate": {
        "significant_median": 0.1, "fatal_median": 0.0, "weeks": 4,
    }}
    alerts = rl.inflation_alert(per_skill, baselines)
    assert len(alerts) == 1
    assert alerts[0]["skill"] == "quality-gate"


# --------------------------------------------------------------------------- #
# Monthly spot-check: deterministic, idempotent across re-renders (§4a)        #
# --------------------------------------------------------------------------- #

def _write_corpus(out_dir):
    """3 backfilled entries each in 2026-W22 (May) and 2026-W16 (April)."""
    ledger = out_dir / "runs.jsonl"
    entries = []
    for run, ts in [("backfill-320-quality-gate", "2026-05-31T01:00:00Z"),
                    ("backfill-318-quality-gate", "2026-05-30T01:00:00Z"),
                    ("backfill-314-quality-gate", "2026-05-29T01:00:00Z"),
                    ("backfill-193-quality-gate", "2026-04-17T01:00:00Z"),
                    ("backfill-192-quality-gate", "2026-04-16T01:00:00Z"),
                    ("backfill-191-quality-gate", "2026-04-15T01:00:00Z")]:
        entries.append(_backfilled_entry(run, timestamp=ts))
    _write_jsonl(ledger, entries)
    return ledger


def _spotcheck_count(path):
    return path.read_text(encoding="utf-8").count("## Monthly spot-check")


def test_first_of_month_weeks_deterministic_one_per_month():
    """Pure helper: exactly the earliest selected week per calendar month."""
    selected = ["2026-W22", "2026-W21", "2026-W20", "2026-W16", "2026-W15"]
    fom = rl.first_of_month_weeks(selected)
    # May weeks W20-W22 -> earliest is W20; April weeks W15-W16 -> earliest W15.
    assert fom == {"2026-W20", "2026-W15"}


def test_monthly_spotcheck_idempotent_across_rerenders(tmp_path):
    """Re-rendering the same corpus must NOT drop the spot-check checklist."""
    ledger = _write_corpus(tmp_path)
    out_dir = tmp_path / "out"
    falsif = tmp_path / "falsification.jsonl"  # absent -> count 0

    argv = ["--weeks", "12", "--ledger", str(ledger),
            "--falsification", str(falsif), "--out-dir", str(out_dir)]

    # First render.
    assert rl.main(argv) == 0
    w22 = out_dir / "weekly-2026-W22.md"
    w16 = out_dir / "weekly-2026-W16.md"
    w20 = out_dir / "weekly-2026-W20.md"
    w15 = out_dir / "weekly-2026-W15.md"
    # NOTE: the corpus only has W22 (May) and W16 (April). Earliest-per-month
    # among the SELECTED weeks => W22 is the only May week, W16 the only April
    # week, so both carry the checklist on render 1.
    assert _spotcheck_count(w22) == 1
    assert _spotcheck_count(w16) == 1

    # Second render of the SAME corpus into the SAME out-dir.
    assert rl.main(argv) == 0
    # The checklist must SURVIVE — this is the regression the QG flagged.
    assert _spotcheck_count(w22) == 1
    assert _spotcheck_count(w16) == 1

    # At-most-once-per-month still holds: no other May/April week gets it.
    assert not w20.exists()  # corpus has no W20
    assert not w15.exists()  # corpus has no W15


def test_monthly_spotcheck_at_most_once_per_month(tmp_path):
    """Two weeks in the same month -> only the earliest gets the checklist."""
    ledger = tmp_path / "runs.jsonl"
    _write_jsonl(ledger, [
        _backfilled_entry("backfill-1-quality-gate", timestamp="2026-05-31T01:00:00Z"),  # W22
        _backfilled_entry("backfill-2-quality-gate", timestamp="2026-05-11T01:00:00Z"),  # W20
    ])
    out_dir = tmp_path / "out"
    argv = ["--weeks", "12", "--ledger", str(ledger),
            "--out-dir", str(out_dir)]
    assert rl.main(argv) == 0
    # W20 (earlier May week) gets the checklist; W22 does not.
    assert _spotcheck_count(out_dir / "weekly-2026-W20.md") == 1
    assert _spotcheck_count(out_dir / "weekly-2026-W22.md") == 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
