#!/usr/bin/env python3
"""Phase 1 (#398) — pure-core unit tests for the calibration-ledger pipeline.

The ledger is "the epistemic backbone" (CLAUDE.md): every Tier-A verdict and
every calibration-weighted dispatch reads it. A silent regression in
append/dedup/truncation/reduce/reconcile corrupts the corpus all gating
decisions trust. Before this file the write/reduce/reconcile core had ZERO
coverage; `test_brier_advise.py` covers the READ side only.

Covers the deterministic, IO-light core only (the seam `reconcile_ledger.py:8-13`
documents as "architected for unit-testability"):
  - ledger_append: caller_dedup (L-2), _truncate_payload (L-8), append against a
    tmp store (success / kill-switch no-op / oversize rejection / truncation +
    sidecar). The lock state machine + crash recovery are Phase 2 (test_locks.py).
  - ledger_reduce.reduce: L-9 latest-wins, tolerant read, and the documented
    trailing-partial-line drop (a CHARACTERIZATION test, not a bug — the drop is
    the intended torn-write tolerance per the module docstring).
  - reconcile_ledger pure core: ledger_entry_hash, load_jsonl,
    read_manual_attribution, reconcile (walkback), compute_brier, parse_predicate.

Pure stdlib `unittest`. Machine-local central store is NEVER touched — every
case writes to a tmp dir (the pure functions take explicit paths; append() is
pointed at a tmp ledger_path). No git, no subprocess.
"""
import hashlib
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts import ledger_append as la  # noqa: E402
from scripts import ledger_reduce as lr  # noqa: E402
from scripts import reconcile_ledger as rl  # noqa: E402


def _entry_hash(run_id, skill):
    return hashlib.sha256((run_id + ":" + skill).encode()).hexdigest()


# --------------------------------------------------------------------------- #
# ledger_append — caller_dedup (L-2)                                          #
# --------------------------------------------------------------------------- #

class CallerDedupTest(unittest.TestCase):
    def _write(self, path, rows):
        with open(path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    def test_missing_file_is_not_dup(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(la.caller_dedup(os.path.join(d, "nope.jsonl"),
                                             "r1", "siege"))

    def test_match_on_run_id_and_skill(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            self._write(p, [{"run_id": "r1", "skill": "siege"}])
            self.assertTrue(la.caller_dedup(p, "r1", "siege"))

    def test_same_run_id_different_skill_is_not_dup(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            self._write(p, [{"run_id": "r1", "skill": "siege"}])
            # (run_id, skill) is the composite identity — skill must match too.
            self.assertFalse(la.caller_dedup(p, "r1", "delve"))

    def test_malformed_and_blank_lines_skipped_not_fatal(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            with open(p, "w", encoding="utf-8") as f:
                f.write("\n")
                f.write("{ not json\n")
                f.write(json.dumps({"run_id": "r1", "skill": "siege"}) + "\n")
            self.assertTrue(la.caller_dedup(p, "r1", "siege"))
            self.assertFalse(la.caller_dedup(p, "rX", "siege"))


# --------------------------------------------------------------------------- #
# ledger_append — _truncate_payload (L-8)                                     #
# --------------------------------------------------------------------------- #

class TruncatePayloadTest(unittest.TestCase):
    def test_gated_files_truncated_with_overflow_returned(self):
        entry = {"gated_files": [f"f{i}.py" for i in range(10)]}
        out, overflow = la._truncate_payload(entry, max_gated_files=3,
                                              max_highest_finding_chars=256)
        self.assertEqual(out["gated_files"], ["f0.py", "f1.py", "f2.py"])
        self.assertEqual(out["gated_files_truncated"], 7)
        self.assertEqual(len(overflow), 10)   # full original list for the sidecar

    def test_under_cap_sets_truncated_zero_no_overflow(self):
        entry = {"gated_files": ["a.py", "b.py"]}
        out, overflow = la._truncate_payload(entry, max_gated_files=500,
                                              max_highest_finding_chars=256)
        self.assertEqual(out["gated_files_truncated"], 0)
        self.assertIsNone(overflow)

    def test_highest_finding_clamped(self):
        entry = {"highest_finding": "x" * 1000}
        out, _ = la._truncate_payload(entry, max_gated_files=500,
                                      max_highest_finding_chars=256)
        self.assertEqual(len(out["highest_finding"]), 256)

    def test_does_not_mutate_input(self):
        entry = {"gated_files": [f"f{i}.py" for i in range(10)]}
        la._truncate_payload(entry, max_gated_files=3, max_highest_finding_chars=256)
        self.assertEqual(len(entry["gated_files"]), 10)   # original untouched


# --------------------------------------------------------------------------- #
# ledger_append — append() against a tmp ledger (no lock contention here)     #
# --------------------------------------------------------------------------- #

def _save_kill_switch():
    """Pop CRUCIBLE_CALIBRATION_DISABLED and return its prior value (or None)."""
    return os.environ.pop("CRUCIBLE_CALIBRATION_DISABLED", None)


def _restore_kill_switch(saved):
    """UNCONDITIONAL restore: always clear the var first, then re-set it only if
    it was present at setUp. The non-leak guarantee holds ONLY for the classes
    that call these helpers in setUp/tearDown (AppendTest, ReconcileTest,
    ReconcilePredicatesTest) — it is not a whole-file property. For those classes,
    on a clean checkout `saved` is None, so a test that set the var to "1" can NOT
    leak it to a sibling test or out of the process.
    """
    os.environ.pop("CRUCIBLE_CALIBRATION_DISABLED", None)
    if saved is not None:
        os.environ["CRUCIBLE_CALIBRATION_DISABLED"] = saved


# NOTE (kill-switch guard scope): classes that never reach _ledger_append do NOT
# need the setUp/tearDown above and intentionally omit it (ComputeBrierTest,
# HashAndLoadTest are pure read/compute). If a future case in ANY such class
# starts appending to a ledger (directly or via reconcile/reconcile_predicates),
# it MUST adopt the _save_kill_switch/_restore_kill_switch guard, or it will go
# RED under an ambient CRUCIBLE_CALIBRATION_DISABLED=1.


class AppendTest(unittest.TestCase):
    def setUp(self):
        # Kill-switch must be OFF for the happy-path cases.
        self._saved = _save_kill_switch()

    def tearDown(self):
        _restore_kill_switch(self._saved)

    def _last_line(self, path):
        with open(path, "rb") as f:
            return json.loads(f.read().splitlines()[-1])

    def test_append_writes_one_jsonl_line(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            self.assertTrue(la.append(p, {"run_id": "r1", "skill": "siege"}))
            obj = self._last_line(p)
            self.assertEqual(obj["run_id"], "r1")
            self.assertEqual(obj["skill"], "siege")

    def test_append_is_append_only(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            la.append(p, {"run_id": "r1", "skill": "siege"})
            # Snapshot the FIRST line's exact bytes after the first append.
            with open(p, "rb") as f:
                first_after_one = f.read().splitlines()[0]
            la.append(p, {"run_id": "r2", "skill": "delve"})
            with open(p, "rb") as f:
                lines = [ln for ln in f.read().splitlines() if ln.strip()]
            self.assertEqual(len(lines), 2)   # L-1: never rewrites a prior line
            # L-1 (the real guarantee): the prior line is byte-for-byte untouched.
            self.assertEqual(lines[0], first_after_one)

    def test_kill_switch_is_noop_returns_false(self):
        os.environ["CRUCIBLE_CALIBRATION_DISABLED"] = "1"
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            self.assertFalse(la.append(p, {"run_id": "r1", "skill": "siege"}))
            # L-6: no file created, no lock acquired.
            self.assertFalse(os.path.exists(p))

    def test_lock_released_after_append(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            la.append(p, {"run_id": "r1", "skill": "siege"})
            self.assertFalse(os.path.exists(os.path.join(d, la.LOCK_DIRNAME)))

    def test_oversize_after_truncation_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            # A single highest_finding under the char-cap but a payload that
            # blows the byte-cap: force rejection via a tiny max_line_bytes.
            ok = la.append(p, {"run_id": "r1", "skill": "siege",
                               "blob": "x" * 1000}, max_line_bytes=50)
            self.assertFalse(ok)
            # Oversize rejection returns BEFORE _acquire_lock, so no lock is ever
            # created (asserting "release" here would be vacuous — nothing was
            # acquired). The intent-precise invariant: no ledger file was created
            # and no lock dir exists. (We assert exactly that, not whole-dir
            # emptiness, which would couple to append's internal validation
            # ordering. Real lock-release-after-contention coverage is Phase 2 /
            # test_locks.py.)
            self.assertFalse(os.path.exists(p))
            self.assertFalse(os.path.exists(os.path.join(d, la.LOCK_DIRNAME)))

    def test_truncation_writes_overflow_sidecar(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            ok = la.append(p, {"run_id": "r1", "skill": "siege",
                               "gated_files": [f"f{i}.py" for i in range(600)]},
                           max_gated_files=500)
            self.assertTrue(ok)
            obj = self._last_line(p)
            self.assertEqual(len(obj["gated_files"]), 500)
            self.assertEqual(obj["gated_files_truncated"], 100)
            sidecar = os.path.join(d, "overflow", "r1.siege.txt")
            self.assertTrue(os.path.exists(sidecar))
            with open(sidecar) as f:
                self.assertEqual(len(f.read().splitlines()), 600)

    def test_oversize_rejection_writes_no_sidecar(self):
        # S-3: sidecar I/O is deferred until AFTER the size check, so a rejected
        # oversize append must not leak an orphan sidecar.
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            ok = la.append(p, {"run_id": "r1", "skill": "siege",
                               "gated_files": [f"f{i}.py" for i in range(600)]},
                           max_gated_files=500, max_line_bytes=50)
            self.assertFalse(ok)
            self.assertFalse(os.path.exists(os.path.join(d, "overflow",
                                                         "r1.siege.txt")))


# --------------------------------------------------------------------------- #
# ledger_reduce.reduce — L-9 latest-wins + tolerant read                      #
# --------------------------------------------------------------------------- #

class ReduceTest(unittest.TestCase):
    def _write(self, path, lines, *, trailing_newline=True):
        body = "\n".join(lines)
        if trailing_newline and lines:
            body += "\n"
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)

    def test_missing_file_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(lr.reduce(os.path.join(d, "nope.jsonl")), {})

    def test_empty_file_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "f.jsonl")
            open(p, "w").close()
            self.assertEqual(lr.reduce(p), {})

    def test_latest_position_wins_not_timestamp(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "f.jsonl")
            # Earlier file position carries a LATER timestamp — file order wins.
            self._write(p, [
                json.dumps({"ledger_entry_hash": "h", "v": 1,
                            "timestamp": "2026-12-01T00:00:00Z"}),
                json.dumps({"ledger_entry_hash": "h", "v": 2,
                            "timestamp": "2026-01-01T00:00:00Z"}),
            ])
            self.assertEqual(lr.reduce(p)["h"]["v"], 2)   # last line wins

    def test_distinct_hashes_kept(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "f.jsonl")
            self._write(p, [
                json.dumps({"ledger_entry_hash": "a"}),
                json.dumps({"ledger_entry_hash": "b"}),
            ])
            self.assertEqual(set(lr.reduce(p)), {"a", "b"})

    def test_malformed_line_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "f.jsonl")
            self._write(p, ["{ not json",
                            json.dumps({"ledger_entry_hash": "a"})])
            self.assertEqual(set(lr.reduce(p)), {"a"})

    def test_missing_hash_key_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "f.jsonl")
            self._write(p, [json.dumps({"no_hash": True})])
            self.assertEqual(lr.reduce(p), {})

    def test_non_utf8_line_skipped_not_fatal(self):
        # reduce() catches UnicodeDecodeError alongside JSONDecodeError
        # (ledger_reduce.py:45): a raw non-UTF8 byte line is skipped without
        # raising, and a valid line in the same file still survives.
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "f.jsonl")
            with open(p, "wb") as f:
                f.write(b"\xff\xfe not utf8\n")
                f.write(json.dumps({"ledger_entry_hash": "ok"}).encode() + b"\n")
            result = lr.reduce(p)
            self.assertEqual(set(result), {"ok"})   # bad line skipped, valid kept

    def test_trailing_partial_line_dropped_characterization(self):
        # CHARACTERIZATION (not a bug): the module docstring declares the
        # trailing partial line (no terminating newline) is silently skipped —
        # the intended tolerance for a torn concurrent write. A complete line
        # before it survives; the partial one is dropped.
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "f.jsonl")
            self._write(p, [json.dumps({"ledger_entry_hash": "complete"}),
                            json.dumps({"ledger_entry_hash": "partial"})],
                        trailing_newline=False)
            result = lr.reduce(p)
            self.assertIn("complete", result)
            self.assertNotIn("partial", result)


# --------------------------------------------------------------------------- #
# reconcile_ledger — ledger_entry_hash / load_jsonl / read_manual_attribution #
# --------------------------------------------------------------------------- #

class HashAndLoadTest(unittest.TestCase):
    # Pure read/compute — never reaches _ledger_append, so no kill-switch guard
    # needed. Any future appending case here must adopt the guard (see helper note).
    def test_entry_hash_stable_and_skill_scoped(self):
        self.assertEqual(rl.ledger_entry_hash("r1", "siege"),
                         _entry_hash("r1", "siege"))
        # skill is part of the identity → a different skill is a different hash.
        self.assertNotEqual(rl.ledger_entry_hash("r1", "siege"),
                            rl.ledger_entry_hash("r1", "delve"))

    def test_load_jsonl_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(rl.load_jsonl(os.path.join(d, "nope.jsonl")), [])

    def test_load_jsonl_tolerant_and_drops_partial_tail(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "f.jsonl")
            with open(p, "w", encoding="utf-8") as f:
                f.write(json.dumps({"a": 1}) + "\n")
                f.write("{ bad\n")                       # malformed → skipped
                f.write(json.dumps({"a": 2}))            # no newline → partial drop
            self.assertEqual(rl.load_jsonl(p), [{"a": 1}])

    def test_read_manual_attribution_latest_wins_per_hash(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "m.jsonl")
            with open(p, "w", encoding="utf-8") as f:
                f.write(json.dumps({"ledger_entry_hash": "h", "v": 1}) + "\n")
                f.write(json.dumps({"ledger_entry_hash": "h", "v": 2}) + "\n")
                f.write(json.dumps({"no_key": True}) + "\n")   # skipped
            out = rl.read_manual_attribution(p)
            self.assertEqual(set(out), {"h"})
            self.assertEqual(out["h"]["v"], 2)


# --------------------------------------------------------------------------- #
# reconcile_ledger — reconcile() walkback (design §3.3/§3.4)                   #
# --------------------------------------------------------------------------- #

class ReconcileTest(unittest.TestCase):
    def setUp(self):
        self._saved = _save_kill_switch()

    def tearDown(self):
        _restore_kill_switch(self._saved)

    def _ledger(self, d, rows):
        p = os.path.join(d, "runs.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        return p

    def _row(self, run_id, skill, gated, ts, *, artifact_type="code",
             backfilled=False):
        return {"run_id": run_id, "skill": skill, "gated_files": gated,
                "timestamp": ts, "artifact_type": artifact_type,
                "backfilled": backfilled}

    def test_walkback_matches_intersecting_pre_merge_code_verdict(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = self._ledger(d, [
                self._row("r1", "siege", ["auth.py"], "2026-01-01T00:00:00Z"),
            ])
            fals = os.path.join(d, "fals.jsonl")
            out = rl.reconcile(
                ledger, fals, os.path.join(d, "manual.jsonl"),
                [{"commit": "abc", "touched_files": ["auth.py"],
                  "merge_time": "2026-01-10T00:00:00Z"}],
                cross_cut_threshold=20, now="2026-02-01T00:00:00Z")
            self.assertEqual(len(out), 1)
            self.assertEqual(out[0]["ledger_entry_hash"],
                             _entry_hash("r1", "siege"))
            self.assertEqual(out[0]["falsified_by"]["via"], "walkback")

    def test_non_code_verdict_not_matched(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = self._ledger(d, [
                self._row("r1", "siege", ["auth.py"], "2026-01-01T00:00:00Z",
                          artifact_type="design"),
            ])
            out = rl.reconcile(
                ledger, os.path.join(d, "f.jsonl"), os.path.join(d, "m.jsonl"),
                [{"commit": "abc", "touched_files": ["auth.py"],
                  "merge_time": "2026-01-10T00:00:00Z"}],
                cross_cut_threshold=20, now="2026-02-01T00:00:00Z")
            self.assertEqual(out, [])

    def test_backfilled_verdict_not_matched(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = self._ledger(d, [
                self._row("r1", "siege", ["auth.py"], "2026-01-01T00:00:00Z",
                          backfilled=True),
            ])
            out = rl.reconcile(
                ledger, os.path.join(d, "f.jsonl"), os.path.join(d, "m.jsonl"),
                [{"commit": "abc", "touched_files": ["auth.py"],
                  "merge_time": "2026-01-10T00:00:00Z"}],
                cross_cut_threshold=20, now="2026-02-01T00:00:00Z")
            self.assertEqual(out, [])

    def test_verdict_after_merge_not_matched(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = self._ledger(d, [
                self._row("r1", "siege", ["auth.py"], "2026-02-01T00:00:00Z"),
            ])
            out = rl.reconcile(
                ledger, os.path.join(d, "f.jsonl"), os.path.join(d, "m.jsonl"),
                [{"commit": "abc", "touched_files": ["auth.py"],
                  "merge_time": "2026-01-10T00:00:00Z"}],
                cross_cut_threshold=20, now="2026-03-01T00:00:00Z")
            self.assertEqual(out, [])   # (b): entry ts must precede merge

    def test_unparseable_merge_time_short_circuits_b_and_still_matches(self):
        # reconcile_ledger.py:270 guards (b) as
        #   `merge_dt is not None and not (ts < merge_dt)`.
        # When merge_time fails to parse (_parse_iso → None), merge_dt is None,
        # so the timestamp-precedence check is SKIPPED — the candidate can still
        # match on file-intersection alone. Verified against production: it emits
        # a walkback falsification at "low" confidence (days_delta → inf → >30d).
        with tempfile.TemporaryDirectory() as d:
            ledger = self._ledger(d, [
                self._row("r1", "siege", ["auth.py"], "2026-01-01T00:00:00Z"),
            ])
            out = rl.reconcile(
                ledger, os.path.join(d, "f.jsonl"), os.path.join(d, "m.jsonl"),
                [{"commit": "abc", "touched_files": ["auth.py"],
                  "merge_time": "not-a-real-date"}],
                cross_cut_threshold=20, now="2026-02-01T00:00:00Z")
            self.assertEqual(len(out), 1)   # (b) short-circuits → admit
            self.assertEqual(out[0]["ledger_entry_hash"],
                             _entry_hash("r1", "siege"))
            self.assertEqual(out[0]["falsified_by"]["via"], "walkback")
            self.assertEqual(out[0]["confidence"], "low")

    def test_walkback_confidence_capped_at_medium(self):
        # design §3a: a file-intersection walkback caps at "medium" even when
        # the merge is well within the 14d high window.
        with tempfile.TemporaryDirectory() as d:
            ledger = self._ledger(d, [
                self._row("r1", "siege", ["auth.py"], "2026-01-01T00:00:00Z"),
            ])
            out = rl.reconcile(
                ledger, os.path.join(d, "f.jsonl"), os.path.join(d, "m.jsonl"),
                [{"commit": "abc", "touched_files": ["auth.py"],
                  "merge_time": "2026-01-02T00:00:00Z"}],   # 1 day → would be high
                cross_cut_threshold=20, now="2026-02-01T00:00:00Z")
            self.assertEqual(out[0]["confidence"], "medium")

    def test_earliest_unseen_match_then_fallthrough(self):
        # Two intersecting verdicts; a single candidate attributes the EARLIEST.
        # The seen-hash set means a second candidate touching the same file
        # falls through to the next-earliest UNSEEN verdict (S-2), not a re-hit.
        with tempfile.TemporaryDirectory() as d:
            ledger = self._ledger(d, [
                self._row("r-late", "siege", ["auth.py"], "2026-01-05T00:00:00Z"),
                self._row("r-early", "siege", ["auth.py"], "2026-01-01T00:00:00Z"),
            ])
            out = rl.reconcile(
                ledger, os.path.join(d, "f.jsonl"), os.path.join(d, "m.jsonl"),
                [{"commit": "c1", "touched_files": ["auth.py"],
                  "merge_time": "2026-01-10T00:00:00Z"},
                 {"commit": "c2", "touched_files": ["auth.py"],
                  "merge_time": "2026-01-11T00:00:00Z"}],
                cross_cut_threshold=20, now="2026-02-01T00:00:00Z")
            hashes = [o["ledger_entry_hash"] for o in out]
            self.assertEqual(hashes, [_entry_hash("r-early", "siege"),
                                      _entry_hash("r-late", "siege")])

    def test_manual_user_supplied_falsified_by_preserved_with_signal_type(self):
        # reconcile_ledger.py:222-231: when a manual attribution row carries its
        # OWN falsified_by dict, the default-build else-branch is skipped and the
        # user dict is used verbatim, with signal_type merged in (L231). The
        # user's fields survive; signal_type defaults to "manual_override".
        with tempfile.TemporaryDirectory() as d:
            ledger = self._ledger(d, [
                self._row("r1", "siege", ["auth.py"], "2026-01-01T00:00:00Z"),
            ])
            manual = os.path.join(d, "manual.jsonl")
            with open(manual, "w", encoding="utf-8") as f:
                f.write(json.dumps({
                    "ledger_entry_hash": _entry_hash("r1", "siege"),
                    "falsified_by": {"commit": "deadbeef", "reason": "human note",
                                     "custom_field": "kept"},
                }) + "\n")
            out = rl.reconcile(
                ledger, os.path.join(d, "f.jsonl"), manual, [],
                cross_cut_threshold=20, now="2026-02-01T00:00:00Z")
            self.assertEqual(len(out), 1)
            fb = out[0]["falsified_by"]
            # user-supplied fields preserved verbatim
            self.assertEqual(fb["commit"], "deadbeef")
            self.assertEqual(fb["reason"], "human note")
            self.assertEqual(fb["custom_field"], "kept")
            # signal_type merged in (default, since the row supplied none)
            self.assertEqual(fb["signal_type"], "manual_override")

    def test_manual_pass_emits_and_reserves_hash(self):
        # §3.5: manual attribution is authoritative and runs first. It emits an
        # entry for its hash AND reserves it so the walkback skips that verdict.
        with tempfile.TemporaryDirectory() as d:
            ledger = self._ledger(d, [
                self._row("r1", "siege", ["auth.py"], "2026-01-01T00:00:00Z"),
            ])
            manual = os.path.join(d, "manual.jsonl")
            with open(manual, "w", encoding="utf-8") as f:
                f.write(json.dumps({
                    "ledger_entry_hash": _entry_hash("r1", "siege"),
                    "reasoning": "human says this PASS was wrong",
                }) + "\n")
            out = rl.reconcile(
                ledger, os.path.join(d, "f.jsonl"), manual,
                [{"commit": "abc", "touched_files": ["auth.py"],
                  "merge_time": "2026-01-10T00:00:00Z"}],
                cross_cut_threshold=20, now="2026-02-01T00:00:00Z")
            # exactly one entry — the manual one; walkback skipped the reserved hash
            self.assertEqual(len(out), 1)
            self.assertEqual(out[0]["falsified_by"]["manual_override"], True)


# --------------------------------------------------------------------------- #
# reconcile_ledger — compute_brier (contract L-10)                            #
# --------------------------------------------------------------------------- #

class ComputeBrierTest(unittest.TestCase):
    # Pure compute — never reaches _ledger_append, so no kill-switch guard needed.
    # Any future appending case here must adopt the guard (see helper note).
    NOW = "2026-06-01T00:00:00Z"
    OLD = "2026-01-01T00:00:00Z"     # > 30d before NOW
    RECENT = "2026-05-25T00:00:00Z"  # < 30d before NOW (inside grace)

    def _e(self, run_id, skill, verdict, conf, ts, **extra):
        e = {"run_id": run_id, "skill": skill, "verdict": verdict,
             "confidence": conf, "timestamp": ts, "artifact_type": "code",
             "backfilled": False}
        e.update(extra)
        return e

    def test_pass_not_falsified_is_correct(self):
        out = rl.compute_brier(
            [self._e("r1", "siege", "PASS", 0.9, self.OLD)], {}, now=self.NOW)
        # actual=1, conf=0.9 → (0.9-1)^2 = 0.01
        self.assertAlmostEqual(out["siege"]["brier"], 0.01)
        self.assertEqual(out["siege"]["n"], 1)

    def test_pass_falsified_is_wrong(self):
        h = _entry_hash("r1", "siege")
        out = rl.compute_brier(
            [self._e("r1", "siege", "PASS", 0.9, self.OLD)],
            {h: {"falsified": True}}, now=self.NOW)
        # actual=0, conf=0.9 → 0.81
        self.assertAlmostEqual(out["siege"]["brier"], 0.81)

    def test_fail_defaults_correct_walkback_does_not_flip(self):
        h = _entry_hash("r1", "siege")
        # A walkback-only falsification must NOT flip a FAIL (actual stays 1).
        out = rl.compute_brier(
            [self._e("r1", "siege", "FAIL", 0.8, self.OLD)],
            {h: {"falsified": True, "via": "walkback"}}, now=self.NOW)
        self.assertAlmostEqual(out["siege"]["brier"], (0.8 - 1) ** 2)

    def test_fail_predicate_fired_flips_to_wrong(self):
        h = _entry_hash("r1", "siege")
        out = rl.compute_brier(
            [self._e("r1", "siege", "FAIL", 0.8, self.OLD)],
            {h: {"falsified": True, "via": "predicate"}}, now=self.NOW)
        # FAIL-side flip (Phase 7): actual=0, conf=0.8 → 0.64
        self.assertAlmostEqual(out["siege"]["brier"], 0.64)

    def test_fail_predicate_via_nested_only_flips(self):
        # Minor 1: exercise the NESTED fallback in compute_brier:427 —
        # `via` lives ONLY under falsified_by, not at top level. It must still
        # flip the FAIL (this is what reconcile_predicates' emit-shape relies on
        # if the top-level `via` were ever absent).
        h = _entry_hash("r1", "siege")
        out = rl.compute_brier(
            [self._e("r1", "siege", "FAIL", 0.8, self.OLD)],
            {h: {"falsified": True, "falsified_by": {"via": "predicate"}}},
            now=self.NOW)
        self.assertAlmostEqual(out["siege"]["brier"], 0.64)

    def test_exact_grace_boundary_excluded(self):
        # Minor 3: the 30-day grace uses a STRICT `<` (reconcile_ledger.py:411),
        # so an entry timestamped EXACTLY now-30d is NOT yet scorable.
        exactly_30d = "2026-05-02T00:00:00Z"   # NOW (2026-06-01) minus 30 days
        out = rl.compute_brier(
            [self._e("r1", "siege", "PASS", 0.9, exactly_30d)], {}, now=self.NOW)
        self.assertEqual(out, {})   # boundary excluded (ts < cutoff is False)

    def test_inside_grace_period_excluded(self):
        out = rl.compute_brier(
            [self._e("r1", "siege", "PASS", 0.9, self.RECENT)], {}, now=self.NOW)
        self.assertEqual(out, {})   # younger than 30d grace → not yet scorable

    def test_low_confidence_excluded(self):
        out = rl.compute_brier(
            [self._e("r1", "siege", "PASS", 0.4, self.OLD)], {}, now=self.NOW)
        self.assertEqual(out, {})   # confidence < 0.5 → not calibrated

    def test_non_brier_verdict_excluded(self):
        out = rl.compute_brier(
            [self._e("r1", "siege", "ABSTAIN", 0.9, self.OLD)], {}, now=self.NOW)
        self.assertEqual(out, {})

    def test_cross_cut_falsification_excluded_from_denominator(self):
        h = _entry_hash("r1", "siege")
        out = rl.compute_brier(
            [self._e("r1", "siege", "PASS", 0.9, self.OLD)],
            {h: {"falsified": True, "cross_cut": True}}, now=self.NOW)
        self.assertEqual(out, {})

    def test_unparseable_now_fails_closed(self):
        # S-1: if `now` can't be parsed, the grace filter can't run → exclude
        # EVERYTHING rather than admit unscorable verdicts.
        out = rl.compute_brier(
            [self._e("r1", "siege", "PASS", 0.9, self.OLD)], {}, now="not-a-date")
        self.assertEqual(out, {})

    def test_noncode_bad_implementation_pass_admitted_as_wrong(self):
        # #342: a non-code PASS is admitted ONLY with a human bad_implementation
        # signal, scored actual=0.
        h = _entry_hash("r1", "design-reviewer")
        e = self._e("r1", "design-reviewer", "PASS", 0.9, self.OLD)
        e["artifact_type"] = "design"
        out = rl.compute_brier(
            [e], {h: {"falsified": True, "signal_type": "bad_implementation"}},
            now=self.NOW)
        self.assertAlmostEqual(out["design-reviewer"]["brier"], 0.81)

    def test_noncode_without_signal_excluded(self):
        e = self._e("r1", "design-reviewer", "PASS", 0.9, self.OLD)
        e["artifact_type"] = "design"
        out = rl.compute_brier([e], {}, now=self.NOW)
        self.assertEqual(out, {})

    def test_mean_over_multiple_entries_per_skill(self):
        h2 = _entry_hash("r2", "siege")
        out = rl.compute_brier(
            [self._e("r1", "siege", "PASS", 1.0, self.OLD),      # correct → 0.0
             # 0.6 is deliberately above MIN_CONFIDENCE=0.5 so the entry is admitted.
             self._e("r2", "siege", "PASS", 0.6, self.OLD)],  # falsified → wrong
            {h2: {"falsified": True}}, now=self.NOW)
        # err1 = (1.0-1)^2 = 0 ; err2 = (0.6-0)^2 = 0.36 ; mean = 0.18
        self.assertEqual(out["siege"]["n"], 2)
        self.assertAlmostEqual(out["siege"]["brier"], 0.18)


# --------------------------------------------------------------------------- #
# reconcile_ledger — _confidence_label (design §3.4)                          #
# --------------------------------------------------------------------------- #

class ConfidenceLabelTest(unittest.TestCase):
    # Minor 2: the cross_cut→low and the multi-file (>5)→low downgrade branches
    # were previously only exercised indirectly. Pin every branch directly.
    def test_cross_cut_is_low_even_when_recent_and_single_file(self):
        # cross_cut wins over an otherwise-"high" 1-day/1-file match.
        self.assertEqual(rl._confidence_label(1, 1, True), "low")

    def test_over_30d_is_low(self):
        self.assertEqual(rl._confidence_label(31, 1, False), "low")

    def test_multi_file_over_five_is_low(self):
        # >5 touched files (not cross-cut, well within 14d) downgrades to low.
        self.assertEqual(rl._confidence_label(2, 6, False), "low")

    def test_recent_small_is_high(self):
        self.assertEqual(rl._confidence_label(14, 1, False), "high")

    def test_mid_window_is_medium(self):
        # 14 < days <= 30, single file, not cross-cut → medium.
        self.assertEqual(rl._confidence_label(20, 1, False), "medium")


# --------------------------------------------------------------------------- #
# reconcile_ledger — _glob_match (path-aware glob, design §3a)                #
# --------------------------------------------------------------------------- #

class GlobMatchTest(unittest.TestCase):
    def test_single_segment_glob_matches_one_segment(self):
        self.assertTrue(rl._glob_match("src/auth/token.ts", "src/auth/*"))

    def test_glob_does_not_cross_slash(self):
        # segment-count guard: `*` is one segment, must NOT match a deeper path.
        self.assertFalse(rl._glob_match("src/auth/sub/x.ts", "src/auth/*"))

    def test_exact_path_matches_itself(self):
        self.assertTrue(rl._glob_match("a/b/c.py", "a/b/c.py"))

    def test_non_matching_segment_fails(self):
        self.assertFalse(rl._glob_match("src/db/token.ts", "src/auth/*"))

    def test_case_sensitive(self):
        # fnmatchcase → `Auth` != `auth` regardless of host OS.
        self.assertFalse(rl._glob_match("src/Auth/token.ts", "src/auth/*"))


# --------------------------------------------------------------------------- #
# reconcile_ledger — reconcile_predicates (Phase 7 second pass, design §3a)   #
# --------------------------------------------------------------------------- #

class ReconcilePredicatesTest(unittest.TestCase):
    NOW = "2026-06-01T00:00:00Z"

    def setUp(self):
        # reconcile_predicates appends via _ledger_append, which no-ops when
        # CRUCIBLE_CALIBRATION_DISABLED == "1". Neutralize the ambient var so the
        # append-bearing cases are hermetic (same guard AppendTest/ReconcileTest use).
        self._saved = _save_kill_switch()

    def tearDown(self):
        _restore_kill_switch(self._saved)

    def _code_entry(self, run_id, skill, pf, ts="2026-01-01T00:00:00Z",
                    **extra):
        e = {"run_id": run_id, "skill": skill, "predicted_falsifier": pf,
             "artifact_type": "code", "timestamp": ts, "verdict": "FAIL",
             "confidence": 0.8, "backfilled": False}
        e.update(extra)
        return e

    def test_fires_in_window_classifies_and_appends_with_via_predicate(self):
        with tempfile.TemporaryDirectory() as d:
            fals = os.path.join(d, "fals.jsonl")
            entry = self._code_entry(
                "r1", "siege", "fix touching src/auth/*.ts within 14d")
            cand = {"commit": "abc", "touched_files": ["src/auth/token.ts"],
                    "merge_time": "2026-01-05T00:00:00Z"}   # 4d after, in-window
            classifications, appended = rl.reconcile_predicates(
                [entry], [cand], fals, now=self.NOW)
            self.assertEqual(len(classifications), 1)
            cl = classifications[0]
            self.assertTrue(cl["parseable"])
            self.assertTrue(cl["fired"])
            self.assertEqual(cl["ledger_entry_hash"], _entry_hash("r1", "siege"))
            # exactly one falsification appended, carrying via:"predicate" BOTH
            # at the top level AND inside falsified_by (reconcile_predicates:761).
            self.assertEqual(len(appended), 1)
            self.assertEqual(appended[0]["via"], "predicate")
            self.assertEqual(appended[0]["falsified_by"]["via"], "predicate")
            self.assertEqual(appended[0]["confidence"], "high")
            # and it really landed on disk.
            self.assertEqual(len(lr.reduce(fals)), 1)

    def test_not_fired_out_of_window_classifies_no_append(self):
        with tempfile.TemporaryDirectory() as d:
            fals = os.path.join(d, "fals.jsonl")
            entry = self._code_entry(
                "r1", "siege", "fix touching src/auth/*.ts within 14d")
            # merge 100d after the verdict → outside the 14d window.
            cand = {"commit": "abc", "touched_files": ["src/auth/token.ts"],
                    "merge_time": "2026-04-15T00:00:00Z"}
            classifications, appended = rl.reconcile_predicates(
                [entry], [cand], fals, now=self.NOW)
            self.assertEqual(len(classifications), 1)
            self.assertTrue(classifications[0]["parseable"])
            self.assertFalse(classifications[0]["fired"])
            self.assertEqual(appended, [])
            self.assertFalse(os.path.exists(fals))   # nothing written

    def test_not_fired_no_file_match_classifies_no_append(self):
        with tempfile.TemporaryDirectory() as d:
            fals = os.path.join(d, "fals.jsonl")
            entry = self._code_entry(
                "r1", "siege", "fix touching src/auth/*.ts within 14d")
            # in-window merge but the touched file is in a different subtree.
            cand = {"commit": "abc", "touched_files": ["src/db/conn.ts"],
                    "merge_time": "2026-01-05T00:00:00Z"}
            classifications, appended = rl.reconcile_predicates(
                [entry], [cand], fals, now=self.NOW)
            self.assertFalse(classifications[0]["fired"])
            self.assertEqual(appended, [])

    def test_merge_at_exact_verdict_instant_does_not_fire(self):
        # _predicate_fired window is `entry_dt < merge_dt <= window_end`
        # (reconcile_ledger.py:566). The lower bound is STRICT: a merge at the
        # EXACT verdict instant is NOT after it, so the predicate must NOT fire.
        # (Most prone to silent regression if simplified to `<=`.)
        with tempfile.TemporaryDirectory() as d:
            fals = os.path.join(d, "fals.jsonl")
            entry = self._code_entry(
                "r1", "siege", "fix touching src/auth/*.ts within 14d",
                ts="2026-01-01T00:00:00Z")
            cand = {"commit": "abc", "touched_files": ["src/auth/token.ts"],
                    "merge_time": "2026-01-01T00:00:00Z"}   # == verdict instant
            classifications, appended = rl.reconcile_predicates(
                [entry], [cand], fals, now=self.NOW)
            self.assertFalse(classifications[0]["fired"])
            self.assertEqual(appended, [])
            self.assertFalse(os.path.exists(fals))

    def test_merge_exactly_at_window_end_fires(self):
        # Inclusive UPPER bound: a merge landing EXACTLY at window_end
        # (entry_dt + within_days) satisfies `merge_dt <= window_end` and fires.
        # Verdict 2026-01-01 + 14d → window_end 2026-01-15T00:00:00Z.
        with tempfile.TemporaryDirectory() as d:
            fals = os.path.join(d, "fals.jsonl")
            entry = self._code_entry(
                "r1", "siege", "fix touching src/auth/*.ts within 14d",
                ts="2026-01-01T00:00:00Z")
            cand = {"commit": "abc", "touched_files": ["src/auth/token.ts"],
                    "merge_time": "2026-01-15T00:00:00Z"}   # == window_end
            classifications, appended = rl.reconcile_predicates(
                [entry], [cand], fals, now=self.NOW)
            self.assertTrue(classifications[0]["fired"])
            self.assertEqual(len(appended), 1)

    def test_sentinel_classifies_sentinel_no_append(self):
        with tempfile.TemporaryDirectory() as d:
            fals = os.path.join(d, "fals.jsonl")
            entry = self._code_entry("r1", "siege", rl.PREDICATE_SENTINEL)
            classifications, appended = rl.reconcile_predicates(
                [entry], [], fals, now=self.NOW)
            self.assertEqual(len(classifications), 1)
            self.assertTrue(classifications[0]["sentinel"])
            self.assertFalse(classifications[0]["parseable"])
            self.assertEqual(appended, [])

    def test_unparseable_prose_classifies_unparseable_no_append(self):
        with tempfile.TemporaryDirectory() as d:
            fals = os.path.join(d, "fals.jsonl")
            entry = self._code_entry(
                "r1", "siege", "this just looks bad, fix it sometime")
            classifications, appended = rl.reconcile_predicates(
                [entry], [], fals, now=self.NOW)
            self.assertEqual(len(classifications), 1)
            self.assertTrue(classifications[0]["unparseable"])
            self.assertFalse(classifications[0]["parseable"])
            self.assertEqual(appended, [])

    def test_non_code_entry_skipped_no_classification(self):
        with tempfile.TemporaryDirectory() as d:
            fals = os.path.join(d, "fals.jsonl")
            entry = self._code_entry(
                "r1", "siege", "fix touching src/auth/*.ts within 14d",
                artifact_type="design")
            classifications, appended = rl.reconcile_predicates(
                [entry], [], fals, now=self.NOW)
            self.assertEqual(classifications, [])   # skipped entirely
            self.assertEqual(appended, [])

    def test_emit_to_brier_flip_end_to_end(self):
        # The real payoff: prove the emit→flip contract through the PRODUCTION
        # read path. reconcile_predicates appends to a tmp falsification file;
        # we reduce it exactly as main() does (ledger_reduce.reduce, keyed by
        # ledger_entry_hash, latest-wins) and feed that map to compute_brier.
        # A FAIL whose predicate fired must flip to actual=0.
        with tempfile.TemporaryDirectory() as d:
            fals = os.path.join(d, "fals.jsonl")
            old_ts = "2026-01-01T00:00:00Z"   # > 30d before NOW → scorable
            entry = self._code_entry(
                "r1", "siege", "fix touching src/auth/*.ts within 14d",
                ts=old_ts, verdict="FAIL", confidence=0.8)
            cand = {"commit": "abc", "touched_files": ["src/auth/token.ts"],
                    "merge_time": "2026-01-05T00:00:00Z"}
            _, appended = rl.reconcile_predicates(
                [entry], [cand], fals, now=self.NOW)
            self.assertEqual(len(appended), 1)
            # Production read path: reduce the falsification log into the map.
            fmap = lr.reduce(fals)
            self.assertIn(_entry_hash("r1", "siege"), fmap)
            brier = rl.compute_brier([entry], fmap, now=self.NOW)
            # FAIL flipped to WRONG (actual=0): (0.8 - 0)^2 = 0.64.
            self.assertAlmostEqual(brier["siege"]["brier"], 0.64)

    # ----------------------------------------------------------------------- #
    # predicate_checkable — single source of truth for v1.1 auto-checkability #
    # (Significant: the dispatch gate had ZERO direct coverage.)               #
    # ----------------------------------------------------------------------- #

    def test_predicate_checkable_touching_true(self):
        self.assertTrue(rl.predicate_checkable(
            rl.parse_predicate("fix touching a.py within 14d")))

    def test_predicate_checkable_referencing_true(self):
        self.assertTrue(rl.predicate_checkable(
            rl.parse_predicate("cve referencing #341 within 90d")))

    def test_predicate_checkable_revert_hash_true(self):
        # hash form is checkable ONLY when verb == "revert".
        self.assertTrue(rl.predicate_checkable(
            rl.parse_predicate("revert of artifact_hash=deadbeef within 30d")))

    def test_predicate_checkable_non_revert_hash_false(self):
        # a `fix of artifact_hash=…` parses but stays uncheckable (no candidate
        # population without exact-hash matching).
        self.assertFalse(rl.predicate_checkable(
            rl.parse_predicate("fix of artifact_hash=abc within 5d")))

    def test_predicate_checkable_none_false(self):
        # an unparseable predicate (parse_predicate → None) is not checkable.
        self.assertFalse(rl.predicate_checkable(None))

    # ----------------------------------------------------------------------- #
    # _hash_fired — verb-gated revert-only matcher (production-live, was       #
    # only exercised through the `touching` form before). End-to-end via       #
    # reconcile_predicates' revert_candidates= kwarg (kept in the guarded      #
    # class because the firing path reaches _ledger_append).                   #
    # ----------------------------------------------------------------------- #

    def test_hash_predicate_fires_appends_via_predicate(self):
        with tempfile.TemporaryDirectory() as d:
            fals = os.path.join(d, "fals.jsonl")
            # entry artifact_hash "deadbeef" — predicate hash "dead" is a prefix.
            entry = self._code_entry(
                "r1", "siege", "revert of artifact_hash=dead within 30d",
                gated_files=["src/auth/token.ts"], artifact_hash="deadbeef")
            revert_cand = {"commit": "rv1",
                           "touched_files": ["src/auth/token.ts"],
                           "merge_time": "2026-01-10T00:00:00Z"}  # in-window
            classifications, appended = rl.reconcile_predicates(
                [entry], [], fals, now=self.NOW,
                revert_candidates=[revert_cand])
            cl = classifications[0]
            self.assertTrue(cl["parseable"])
            self.assertTrue(cl["fired"])
            self.assertEqual(len(appended), 1)
            self.assertEqual(appended[0]["via"], "predicate")
            self.assertEqual(appended[0]["falsified_by"]["via"], "predicate")
            self.assertEqual(appended[0]["confidence"], "high")
            self.assertEqual(len(lr.reduce(fals)), 1)

    def test_hash_predicate_bind_failure_no_fire(self):
        # The parsed hash is NOT a prefix of the entry's artifact_hash → the
        # predicate names a different artifact → must NOT fire (hash is
        # load-bearing, not decorative).
        with tempfile.TemporaryDirectory() as d:
            fals = os.path.join(d, "fals.jsonl")
            entry = self._code_entry(
                "r1", "siege", "revert of artifact_hash=dead within 30d",
                gated_files=["src/auth/token.ts"], artifact_hash="cafef00d")
            revert_cand = {"commit": "rv1",
                           "touched_files": ["src/auth/token.ts"],
                           "merge_time": "2026-01-10T00:00:00Z"}
            classifications, appended = rl.reconcile_predicates(
                [entry], [], fals, now=self.NOW,
                revert_candidates=[revert_cand])
            self.assertTrue(classifications[0]["parseable"])
            self.assertFalse(classifications[0]["fired"])
            self.assertEqual(appended, [])
            self.assertFalse(os.path.exists(fals))

    def test_hash_predicate_without_files_exclusion_no_fire(self):
        # The revert touches an excluded (`without touching`) path → disqualified.
        with tempfile.TemporaryDirectory() as d:
            fals = os.path.join(d, "fals.jsonl")
            entry = self._code_entry(
                "r1", "siege",
                "revert of artifact_hash=dead without touching src/auth/* "
                "within 30d",
                gated_files=["src/auth/token.ts"], artifact_hash="deadbeef")
            # touches the gated file but it is also under the excluded glob.
            revert_cand = {"commit": "rv1",
                           "touched_files": ["src/auth/token.ts"],
                           "merge_time": "2026-01-10T00:00:00Z"}
            classifications, appended = rl.reconcile_predicates(
                [entry], [], fals, now=self.NOW,
                revert_candidates=[revert_cand])
            self.assertFalse(classifications[0]["fired"])
            self.assertEqual(appended, [])

    # ----------------------------------------------------------------------- #
    # _referencing_fired — delimited commit-message token scan.                #
    # ----------------------------------------------------------------------- #

    def test_referencing_predicate_fires_on_delimited_token(self):
        with tempfile.TemporaryDirectory() as d:
            fals = os.path.join(d, "fals.jsonl")
            entry = self._code_entry(
                "r1", "siege", "cve referencing #341 within 90d")
            ref_cand = {"commit": "rc1", "message": "closes #341 — done",
                        "merge_time": "2026-01-10T00:00:00Z"}  # in-window
            classifications, appended = rl.reconcile_predicates(
                [entry], [], fals, now=self.NOW,
                reference_candidates=[ref_cand])
            self.assertTrue(classifications[0]["fired"])
            self.assertEqual(len(appended), 1)
            self.assertEqual(appended[0]["via"], "predicate")
            self.assertEqual(appended[0]["falsified_by"]["via"], "predicate")
            self.assertEqual(len(lr.reduce(fals)), 1)

    def test_referencing_predicate_delimited_boundary_negative(self):
        # token `#341` must NOT match a message mentioning `#3419` — the
        # non-word lookarounds reject the longer token.
        with tempfile.TemporaryDirectory() as d:
            fals = os.path.join(d, "fals.jsonl")
            entry = self._code_entry(
                "r1", "siege", "cve referencing #341 within 90d")
            ref_cand = {"commit": "rc1", "message": "closes #3419 unrelated",
                        "merge_time": "2026-01-10T00:00:00Z"}
            classifications, appended = rl.reconcile_predicates(
                [entry], [], fals, now=self.NOW,
                reference_candidates=[ref_cand])
            self.assertFalse(classifications[0]["fired"])
            self.assertEqual(appended, [])
            self.assertFalse(os.path.exists(fals))

    # ----------------------------------------------------------------------- #
    # uncheckable classification — parseable-but-not-checkable predicate.      #
    # ----------------------------------------------------------------------- #

    def test_uncheckable_predicate_classifies_no_append(self):
        # A `fix of artifact_hash=…` (non-revert hash) parses but is NOT
        # predicate_checkable → classified uncheckable, appends nothing
        # (reconcile_ledger.py:728-733).
        with tempfile.TemporaryDirectory() as d:
            fals = os.path.join(d, "fals.jsonl")
            entry = self._code_entry(
                "r1", "siege", "fix of artifact_hash=abc within 5d")
            classifications, appended = rl.reconcile_predicates(
                [entry], [], fals, now=self.NOW)
            self.assertEqual(len(classifications), 1)
            cl = classifications[0]
            self.assertTrue(cl["uncheckable"])
            self.assertFalse(cl["parseable"])
            self.assertFalse(cl["fired"])
            self.assertEqual(appended, [])
            self.assertFalse(os.path.exists(fals))


# --------------------------------------------------------------------------- #
# reconcile_ledger — parse_predicate (design §3a grammar)                     #
# --------------------------------------------------------------------------- #

class ParsePredicateTest(unittest.TestCase):
    def test_touching_form(self):
        p = rl.parse_predicate("fix touching a.py, b.py within 14d")
        self.assertEqual(p, {"form": "touching", "verb": "fix",
                             "files": ["a.py", "b.py"], "within_days": 14})

    def test_touching_verb_case_insensitive(self):
        p = rl.parse_predicate("HOTFIX touching a.py within 7d")
        self.assertEqual(p["verb"], "hotfix")

    def test_hash_form_with_without_clause(self):
        p = rl.parse_predicate(
            "revert of artifact_hash=DEADBEEF without touching x.py within 30d")
        self.assertEqual(p["form"], "hash")
        self.assertEqual(p["artifact_hash"], "deadbeef")   # lowercased
        self.assertEqual(p["without_files"], ["x.py"])
        self.assertEqual(p["within_days"], 30)

    def test_hash_form_without_clause_optional(self):
        p = rl.parse_predicate("merge of artifact_hash=abc within 5d")
        self.assertEqual(p["without_files"], [])

    def test_referencing_form(self):
        p = rl.parse_predicate("cve referencing CVE-2026-1 within 90d")
        self.assertEqual(p, {"form": "referencing", "verb": "cve",
                             "token": "CVE-2026-1", "within_days": 90})

    def test_freeform_prose_is_unparseable(self):
        self.assertIsNone(rl.parse_predicate("this looks bad, fix it sometime"))

    def test_out_of_range_days_rejected(self):
        self.assertIsNone(rl.parse_predicate("fix touching a.py within 0d"))
        self.assertIsNone(rl.parse_predicate("fix touching a.py within 999d"))

    def test_empty_file_list_rejected(self):
        # "touching" with only commas → no real files → parse failure.
        self.assertIsNone(rl.parse_predicate("fix touching , within 14d"))

    def test_non_string_and_empty_return_none(self):
        self.assertIsNone(rl.parse_predicate(None))
        self.assertIsNone(rl.parse_predicate(""))
        self.assertIsNone(rl.parse_predicate(123))


if __name__ == "__main__":
    unittest.main()
