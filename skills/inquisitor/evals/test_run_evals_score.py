#!/usr/bin/env python3
"""score() tests for the inquisitor fan-out eval harness (#424).

stdlib unittest (D1). Builds synthetic manifests + judge-verdict files so the math
is pinned precisely. The ground-truth file is written into the PATCHED _EVALS_DIR
(F1) — score must resolve it at call time, else test_off_axis would silently read
the real committed file and go green-but-vacuous.
"""
import json
import math
import os
import pathlib
import statistics
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from skills.inquisitor.evals import run_evals  # noqa: E402


class ScoreTestBase(unittest.TestCase):
    def setUp(self):
        self._dispatch_tmp = tempfile.TemporaryDirectory()
        self._evals_tmp = tempfile.TemporaryDirectory()
        self.evals_dir = pathlib.Path(self._evals_tmp.name)
        self._env = mock.patch.dict(
            os.environ,
            {"XDG_RUNTIME_DIR": self._dispatch_tmp.name, "USER": "tester"})
        self._env.start()
        self._evd = mock.patch.object(run_evals, "_EVALS_DIR", self.evals_dir)
        self._evd.start()

    def tearDown(self):
        self._evd.stop()
        self._env.stop()
        self._dispatch_tmp.cleanup()
        self._evals_tmp.cleanup()

    def make_run(self, run_id, trials, cells, ground_truth, *, collect=True):
        """cells: list of (fixture_id, trial, arm, [records]). A record is a dict
        {id,tag,verdict} (→ JSON line) or a raw str (→ malformed line)."""
        dd = run_evals.resolve_dispatch_dir(run_id)
        dd.mkdir(parents=True, exist_ok=True)
        manifest_cells = []
        for (fid, trial, arm, records) in cells:
            rf = f"f{fid}-t{trial}-{arm}.jsonl"
            lines = [r if isinstance(r, str) else json.dumps(r) for r in records]
            (dd / rf).write_text(("\n".join(lines) + "\n") if lines else "",
                                 encoding="utf-8")
            manifest_cells.append({"fixture_id": fid, "trial": trial,
                                   "arm": arm, "result_file": rf})
        (dd / "stage-manifest.json").write_text(json.dumps(
            {"run_id": run_id, "trials": trials, "cells": manifest_cells}))
        if collect:
            (dd / ".collect-status").write_text("complete")
        (self.evals_dir / "ground-truth-bugs.json").write_text(
            json.dumps(ground_truth))
        return dd

    def last_run(self):
        return json.loads((self.evals_dir / "last_run.json").read_text())

    @staticmethod
    def prim(bug, verdict):
        return {"id": bug, "tag": "primary", "verdict": verdict}

    @staticmethod
    def sec(sid, verdict):
        return {"id": sid, "tag": "secondary", "verdict": verdict}


class TestPairedDeltaMath(ScoreTestBase):
    def test_paired_is_mean_of_per_trial_not_rate_diff(self):
        """Test 3 (S1): WITH=[1,1,0], WITHOUT=[1,0,0] over 3 trials, 1 bug →
        paired == 0.333 (mean of per-trial deltas), NOT 1.0 (majority-rate diff).
        Also pins the mde_heuristic formula (F2)."""
        gt = {"fixtures": [{"id": 1, "bugs": [
            {"bug_id": "f1-b1", "off_axis": False}]}]}
        with_v = ["PASS", "PASS", "FAIL"]
        without_v = ["PASS", "FAIL", "FAIL"]
        cells = []
        for t in (1, 2, 3):
            cells.append((1, t, "with", [self.prim("f1-b1", with_v[t - 1])]))
            cells.append((1, t, "without", [self.prim("f1-b1", without_v[t - 1])]))
            cells.append((1, t, "mid", [self.prim("f1-b1", "FAIL")]))
        rc = run_evals.score(self.make_run("run3", 3, cells, gt) and "run3")
        self.assertEqual(rc, 0)
        lr = self.last_run()
        d = lr["deltas"]["with_without"]
        self.assertAlmostEqual(d["paired"], 1 / 3, places=9)
        self.assertNotAlmostEqual(d["paired"], 1.0, places=6)
        self.assertEqual(d["trial_spread"], [0.0, 1.0])
        # the majority-collapsed rate diff IS 1.0 (and differs from paired)
        self.assertEqual(lr["with"]["rate"], 1.0)
        self.assertEqual(lr["without"]["rate"], 0.0)
        # mde formula
        expected_mde = 1.96 * statistics.stdev([0.0, 1.0, 0.0]) / math.sqrt(3)
        self.assertAlmostEqual(d["mde_heuristic"], expected_mde, places=9)
        # per-fixture majority rates
        pf = {row["id"]: row for row in lr["per_fixture"]}
        self.assertEqual(pf[1]["with"], 1.0)
        self.assertEqual(pf[1]["without"], 0.0)
        # the rate-vs-paired note is present (non-optional, S-3)
        self.assertIn("_note", lr["deltas"])


class TestTaggedUnionPartition(ScoreTestBase):
    def test_single_judge_partition_populates_both(self):
        """Test 3b (S-1): one verdict file carrying primary + secondary items
        populates BOTH graded_bugs/deltas AND secondary_diagnostic, with
        graded_expectations == 26."""
        gt = {"fixtures": [{"id": 1, "bugs": [
            {"bug_id": "f1-b1", "off_axis": False}]}]}
        sec_records = [self.sec(f"expectation-{i}",
                                "PASS" if i % 2 else "FAIL") for i in range(1, 27)]
        cell_records = [self.prim("f1-b1", "PASS")] + sec_records
        cells = [(1, 1, "with", cell_records),
                 (1, 1, "mid", cell_records),
                 (1, 1, "without", cell_records)]
        run_evals.score(self.make_run("runb", 1, cells, gt) and "runb")
        lr = self.last_run()
        self.assertEqual(lr["graded_bugs"], 1)
        self.assertEqual(lr["with"]["pass"], 1)              # primary partition
        self.assertEqual(lr["secondary_diagnostic"]["graded_expectations"], 26)
        self.assertIn("with", lr["secondary_diagnostic"])    # secondary partition


class TestOffAxisDiagnostic(ScoreTestBase):
    def test_off_axis_partition_over_subset(self):
        """Test 3c (S-FIND-1 + F1): off_axis_diagnostic totals only the
        off_axis:true primary bugs, read from the synthetic ground-truth in the
        PATCHED _EVALS_DIR (not the real committed file)."""
        gt = {"fixtures": [{"id": 1, "bugs": [
            {"bug_id": "f1-b1", "off_axis": True},
            {"bug_id": "f1-b2", "off_axis": False},
            {"bug_id": "f1-b3", "off_axis": True}]}]}
        with_rec = [self.prim("f1-b1", "PASS"), self.prim("f1-b2", "PASS"),
                    self.prim("f1-b3", "FAIL")]
        none_rec = [self.prim(b, "FAIL") for b in ("f1-b1", "f1-b2", "f1-b3")]
        cells = [(1, 1, "with", with_rec),
                 (1, 1, "mid", none_rec),
                 (1, 1, "without", none_rec)]
        run_evals.score(self.make_run("runc", 1, cells, gt) and "runc")
        oa = self.last_run()["off_axis_diagnostic"]
        self.assertEqual(oa["with"]["total"], 2)   # only off_axis bugs, NOT 3
        self.assertEqual(oa["with"]["pass"], 1)    # f1-b1 PASS, f1-b3 FAIL
        self.assertEqual(oa["with"]["rate"], 0.5)
        self.assertEqual(oa["without"]["total"], 2)


class TestTieRule(ScoreTestBase):
    def test_even_n_tie_resolves_to_fail(self):
        """Test 4 (M1): a 1-1 per-bug majority tie over 2 trials → FAIL."""
        gt = {"fixtures": [{"id": 1, "bugs": [
            {"bug_id": "f1-b1", "off_axis": False}]}]}
        cells = [(1, 1, "with", [self.prim("f1-b1", "PASS")]),
                 (1, 2, "with", [self.prim("f1-b1", "FAIL")]),
                 (1, 1, "mid", [self.prim("f1-b1", "FAIL")]),
                 (1, 2, "mid", [self.prim("f1-b1", "FAIL")]),
                 (1, 1, "without", [self.prim("f1-b1", "FAIL")]),
                 (1, 2, "without", [self.prim("f1-b1", "FAIL")])]
        run_evals.score(self.make_run("runt", 2, cells, gt) and "runt")
        self.assertEqual(self.last_run()["with"]["rate"], 0.0)  # tie → FAIL


class TestCollectStatusGating(ScoreTestBase):
    def _trivial(self, collect):
        gt = {"fixtures": [{"id": 1, "bugs": [
            {"bug_id": "f1-b1", "off_axis": False}]}]}
        cells = [(1, 1, a, [self.prim("f1-b1", "FAIL")])
                 for a in ("with", "mid", "without")]
        return self.make_run("rung", 1, cells, gt, collect=collect)

    def test_refuses_without_status(self):
        """Test 5: score returns non-zero without .collect-status and no flag."""
        self._trivial(collect=False)
        self.assertEqual(run_evals.score("rung", allow_incomplete=False), 1)

    def test_allow_incomplete_stamps_false(self):
        self._trivial(collect=False)
        self.assertEqual(run_evals.score("rung", allow_incomplete=True), 0)
        self.assertFalse(self.last_run()["complete"])

    def test_complete_run_stamps_true(self):
        self._trivial(collect=True)
        self.assertEqual(run_evals.score("rung", allow_incomplete=False), 0)
        self.assertTrue(self.last_run()["complete"])


class TestBeyondSpread(ScoreTestBase):
    def test_beyond_spread_logic_helper(self):
        """Test 6: beyond_spread iff band excludes zero AND |mean| >= 0.05."""
        self.assertTrue(run_evals._beyond_spread([1.0, 1.0, 1.0], 1.0))
        self.assertFalse(run_evals._beyond_spread([1.0, -1.0, 1.0], 1 / 3))  # straddle
        self.assertFalse(run_evals._beyond_spread([0.04, 0.04, 0.04], 0.04))  # |mean|<eps
        self.assertFalse(run_evals._beyond_spread([0.0, 0.1, 0.2], 0.1))      # band touches 0

    def test_beyond_spread_end_to_end_positive(self):
        gt = {"fixtures": [{"id": 1, "bugs": [
            {"bug_id": "f1-b1", "off_axis": False}]}]}
        cells = []
        for t in (1, 2, 3):
            cells.append((1, t, "with", [self.prim("f1-b1", "PASS")]))
            cells.append((1, t, "without", [self.prim("f1-b1", "FAIL")]))
            cells.append((1, t, "mid", [self.prim("f1-b1", "FAIL")]))
        run_evals.score(self.make_run("runbs", 3, cells, gt) and "runbs")
        self.assertTrue(self.last_run()["deltas"]["with_without"]["beyond_spread"])

    def test_trial_count_floor(self):
        """Test 6b (S2): a 1-trial run forces beyond_spread False even when the
        single delta >= eps and the degenerate point 'excludes zero', and even
        though the run is complete:true."""
        self.assertFalse(run_evals._beyond_spread([1.0], 1.0))
        self.assertFalse(run_evals._beyond_spread([1.0, 1.0], 1.0))
        gt = {"fixtures": [{"id": 1, "bugs": [
            {"bug_id": "f1-b1", "off_axis": False}]}]}
        cells = [(1, 1, "with", [self.prim("f1-b1", "PASS")]),
                 (1, 1, "without", [self.prim("f1-b1", "FAIL")]),
                 (1, 1, "mid", [self.prim("f1-b1", "FAIL")])]
        run_evals.score(self.make_run("run1", 1, cells, gt) and "run1")
        lr = self.last_run()
        self.assertTrue(lr["complete"])
        self.assertFalse(lr["deltas"]["with_without"]["beyond_spread"])
        self.assertIsNone(lr["deltas"]["with_without"]["mde_heuristic"])  # trials<2


class TestCoverageGuard(ScoreTestBase):
    """S1: score must refuse a misconfigured/partial-coverage run instead of
    false-greening it as a clean 'no methodology effect' null with complete:true."""

    def test_uncovered_fixture_returns_nonzero_no_complete(self):
        """Manifest stages fixture 1; ground-truth lists only fixture 99 → K=0 via
        zero coverage. score must return non-zero and NOT write a complete:true
        last_run.json (the original false-green: exit 0, complete:true, all deltas
        0.0)."""
        gt = {"fixtures": [{"id": 99, "bugs": [
            {"bug_id": "f99-b1", "off_axis": False}]}]}
        cells = [(1, 1, a, [self.prim("f1-b1", "FAIL")])
                 for a in ("with", "mid", "without")]
        rc = run_evals.score(self.make_run("runcov", 1, cells, gt) and "runcov")
        self.assertNotEqual(rc, 0)
        # no complete:true last_run.json written
        lr_path = self.evals_dir / "last_run.json"
        if lr_path.exists():
            self.assertNotEqual(
                json.loads(lr_path.read_text()).get("complete"), True)

    def test_partial_coverage_returns_nonzero(self):
        """Run stages fixtures {1,2}; ground-truth covers only {1} → fixture 2 is
        uncovered. score must return non-zero (not silently drop fixture 2 from K)."""
        gt = {"fixtures": [{"id": 1, "bugs": [
            {"bug_id": "f1-b1", "off_axis": False}]}]}
        cells = []
        for fid in (1, 2):
            for a in ("with", "mid", "without"):
                cells.append((fid, 1, a, [self.prim(f"f{fid}-b1", "FAIL")]))
        rc = run_evals.score(self.make_run("runpart", 1, cells, gt) and "runpart")
        self.assertNotEqual(rc, 0)


class TestMalformedVerdicts(ScoreTestBase):
    def test_malformed_counted_per_arm_and_graded_fail(self):
        """A malformed line is counted per arm and the missing item grades FAIL."""
        gt = {"fixtures": [{"id": 1, "bugs": [
            {"bug_id": "f1-b1", "off_axis": False}]}]}
        cells = [(1, 1, "with", ["{not json"]),
                 (1, 1, "mid", [self.prim("f1-b1", "FAIL")]),
                 (1, 1, "without", [self.prim("f1-b1", "FAIL")])]
        run_evals.score(self.make_run("runm", 1, cells, gt) and "runm")
        lr = self.last_run()
        self.assertEqual(lr["malformed_verdicts"]["with"], 1)
        self.assertEqual(lr["with"]["pass"], 0)  # missing record → FAIL


class TestCollectionPresenceGuard(ScoreTestBase):
    """S-1: score must refuse a `complete` run whose every result_file is
    missing/empty/dispatch-failed instead of false-greening it as a tidy
    complete:true zero-delta null (mirror TestCoverageGuard)."""

    def test_all_empty_complete_run_returns_nonzero_no_complete(self):
        """.collect-status present, but every cell result_file is empty → zero
        verdicts parsed. score must return non-zero and leave no complete:true
        last_run.json (the original false-green: exit 0, complete:true, all 0.0)."""
        gt = {"fixtures": [{"id": 1, "bugs": [
            {"bug_id": "f1-b1", "off_axis": False}]}]}
        # empty record lists → make_run writes empty result files; collect=True
        # stamps .collect-status.
        cells = [(1, 1, a, []) for a in ("with", "mid", "without")]
        rc = run_evals.score(self.make_run("runempty", 1, cells, gt) and "runempty")
        self.assertNotEqual(rc, 0)
        lr_path = self.evals_dir / "last_run.json"
        if lr_path.exists():
            self.assertNotEqual(
                json.loads(lr_path.read_text()).get("complete"), True)

    def test_partial_collection_returns_nonzero(self):
        """One cell collected, the rest empty → partial collection. A complete run
        must refuse rather than grade the absent cells FAIL-by-absence."""
        gt = {"fixtures": [{"id": 1, "bugs": [
            {"bug_id": "f1-b1", "off_axis": False}]}]}
        cells = [(1, 1, "with", [self.prim("f1-b1", "PASS")]),
                 (1, 1, "mid", []),
                 (1, 1, "without", [])]
        rc = run_evals.score(self.make_run("runpartcol", 1, cells, gt) and "runpartcol")
        self.assertNotEqual(rc, 0)

    def test_dispatch_error_cell_returns_nonzero(self):
        """A cell whose result_file is a DISPATCH_STATUS: ERROR sentinel (S-2) is a
        dispatch failure — score must refuse the complete run (S-1 ∩ S-2)."""
        gt = {"fixtures": [{"id": 1, "bugs": [
            {"bug_id": "f1-b1", "off_axis": False}]}]}
        cells = [(1, 1, "with", [self.prim("f1-b1", "PASS")]),
                 (1, 1, "mid", [self.prim("f1-b1", "PASS")]),
                 (1, 1, "without",
                  ["DISPATCH_STATUS: ERROR: subagent timed out"])]
        rc = run_evals.score(self.make_run("runerr", 1, cells, gt) and "runerr")
        self.assertNotEqual(rc, 0)

    def test_allow_incomplete_does_not_trigger_guard(self):
        """The presence guard is a `complete`-run assertion; --allow-incomplete
        (a smoke/debug score) must still run on an all-empty set."""
        gt = {"fixtures": [{"id": 1, "bugs": [
            {"bug_id": "f1-b1", "off_axis": False}]}]}
        cells = [(1, 1, a, []) for a in ("with", "mid", "without")]
        self.make_run("runsmoke", 1, cells, gt, collect=False)
        self.assertEqual(
            run_evals.score("runsmoke", allow_incomplete=True), 0)
        self.assertFalse(self.last_run()["complete"])


class TestUnderEmissionGuard(ScoreTestBase):
    """F-1: score must refuse a `complete` run whose cells emit FEWER primary
    records than the fixture's ground-truth primary budget — every omitted bug
    grades FAIL-by-absence in all arms equally, collapsing the deltas to a
    false-green 0.0 null with complete:true (mirror TestCollectionPresenceGuard)."""

    def test_under_emitting_complete_run_returns_nonzero_no_complete(self):
        """K=3 GT, but each cell carries a single valid primary record → 1 < 3
        under-emission. score must return non-zero and leave no complete:true
        last_run.json (the original false-green: rc 0, complete:true, deltas 0.0)."""
        gt = {"fixtures": [{"id": 1, "bugs": [
            {"bug_id": "f1-b1", "off_axis": False},
            {"bug_id": "f1-b2", "off_axis": False},
            {"bug_id": "f1-b3", "off_axis": False}]}]}
        cells = [(1, 1, a, [self.prim("f1-b1", "FAIL")])
                 for a in ("with", "mid", "without")]
        rc = run_evals.score(self.make_run("rununder", 1, cells, gt) and "rununder")
        self.assertNotEqual(rc, 0)
        lr_path = self.evals_dir / "last_run.json"
        if lr_path.exists():
            self.assertNotEqual(
                json.loads(lr_path.read_text()).get("complete"), True)

    def test_malformed_present_round5_case_still_scores(self):
        """Round-5 contract preserved: a K=1 cell with one malformed line (0 parsed
        primary, mal=1) is NOT under-emission (0 + 1 >= 1) — it still scores with
        malformed=1, pass=0. Distinct from didn't-collect."""
        gt = {"fixtures": [{"id": 1, "bugs": [
            {"bug_id": "f1-b1", "off_axis": False}]}]}
        cells = [(1, 1, "with", ["{not json"]),
                 (1, 1, "mid", [self.prim("f1-b1", "FAIL")]),
                 (1, 1, "without", [self.prim("f1-b1", "FAIL")])]
        rc = run_evals.score(self.make_run("runmal5", 1, cells, gt) and "runmal5")
        self.assertEqual(rc, 0)
        lr = self.last_run()
        self.assertEqual(lr["malformed_verdicts"]["with"], 1)
        self.assertEqual(lr["with"]["pass"], 0)


class TestIdDriftGuard(ScoreTestBase):
    """S-1: score must refuse a `complete` run whose cells emit well-formed primary
    records (mal=0) under ids that are NOT members of ground-truth — every
    ground-truth bug is looked up by id, found absent, and grades FAIL-by-absence in
    all arms equally, collapsing the deltas to a false-green 0.0 null with
    complete:true. The under-emission budget counts only gt-id-matched primary
    records, so id-drift falls short of K and is refused (mirror
    TestUnderEmissionGuard)."""

    def test_full_id_drift_complete_run_returns_nonzero_no_complete(self):
        """K=2 GT (f1-b1/f1-b2); WITH judges both PASS, WITHOUT both FAIL (maximal
        real effect); but the judge echoes bug-1/bug-2. mal=0, records parse cleanly.
        Pre-fix: paired 0.0, complete:true, rc 0. score must now return non-zero and
        leave no complete:true last_run.json."""
        gt = {"fixtures": [{"id": 1, "bugs": [
            {"bug_id": "f1-b1", "off_axis": False},
            {"bug_id": "f1-b2", "off_axis": False}]}]}
        cells = [
            (1, 1, "with", [self.prim("bug-1", "PASS"), self.prim("bug-2", "PASS")]),
            (1, 1, "mid", [self.prim("bug-1", "FAIL"), self.prim("bug-2", "FAIL")]),
            (1, 1, "without",
             [self.prim("bug-1", "FAIL"), self.prim("bug-2", "FAIL")])]
        rc = run_evals.score(self.make_run("rundrift", 1, cells, gt) and "rundrift")
        self.assertNotEqual(rc, 0)
        lr_path = self.evals_dir / "last_run.json"
        if lr_path.exists():
            self.assertNotEqual(
                json.loads(lr_path.read_text()).get("complete"), True)

    def test_partial_id_drift_complete_run_returns_nonzero_no_complete(self):
        """K=2 GT; one correct id (f1-b1) + one drifted (bug-2), mal=0 → gt-matched
        primary = 1 < 2 → refused (more robust than a bare empty-intersection
        assert)."""
        gt = {"fixtures": [{"id": 1, "bugs": [
            {"bug_id": "f1-b1", "off_axis": False},
            {"bug_id": "f1-b2", "off_axis": False}]}]}
        cells = [
            (1, 1, a, [self.prim("f1-b1", "FAIL"), self.prim("bug-2", "FAIL")])
            for a in ("with", "mid", "without")]
        rc = run_evals.score(
            self.make_run("rundriftp", 1, cells, gt) and "rundriftp")
        self.assertNotEqual(rc, 0)
        lr_path = self.evals_dir / "last_run.json"
        if lr_path.exists():
            self.assertNotEqual(
                json.loads(lr_path.read_text()).get("complete"), True)

    def test_extra_hallucinated_id_does_not_refuse(self):
        """K=2 GT, both correct (f1-b1/f1-b2) + one extra hallucinated id (bug-99),
        mal=0 → gt-matched primary = 2 >= 2 → NOT refused. Extra ids are harmless:
        the blind-anchored K ignores them. score returns 0 and stamps complete."""
        gt = {"fixtures": [{"id": 1, "bugs": [
            {"bug_id": "f1-b1", "off_axis": False},
            {"bug_id": "f1-b2", "off_axis": False}]}]}
        cells = [(1, 1, a, [self.prim("f1-b1", "PASS"), self.prim("f1-b2", "PASS"),
                            self.prim("bug-99", "PASS")])
                 for a in ("with", "mid", "without")]
        rc = run_evals.score(self.make_run("runextra", 1, cells, gt) and "runextra")
        self.assertEqual(rc, 0)
        self.assertTrue(self.last_run()["complete"])


class TestGridCompletenessGuard(ScoreTestBase):
    """S1: score must assert the realized (arm × fixture × trial) cell grid is
    complete for a `complete` run. A manifest that under-enumerates cells (missing
    arm/trial), over-states `trials`, or sets `trials:0` false-greens a wrong delta
    with complete:true — refuse before writing last_run.json. --allow-incomplete is
    exempt (mirror TestCollectionPresenceGuard)."""

    def test_missing_arm_returns_nonzero_no_false_green(self):
        """Manifest lists ONLY the WITH cell for f1-t1 (no mid/without). Pre-fix:
        rc 0, complete:true, WITH−WITHOUT paired=+1.0 maximal false-green. score
        must now return non-zero and NOT write a complete:true last_run.json."""
        gt = {"fixtures": [{"id": 1, "bugs": [
            {"bug_id": "f1-b1", "off_axis": False}]}]}
        cells = [(1, 1, "with", [self.prim("f1-b1", "PASS")])]
        rc = run_evals.score(self.make_run("rungrid1", 1, cells, gt) and "rungrid1")
        self.assertNotEqual(rc, 0)
        lr_path = self.evals_dir / "last_run.json"
        if lr_path.exists():
            lr = json.loads(lr_path.read_text())
            self.assertNotEqual(lr.get("complete"), True)
            # the +1.0 false headline delta must NOT have been produced
            self.assertNotIn("deltas", lr)

    def test_over_stated_trials_returns_nonzero(self):
        """trials=3 but only trial-1 cells present → trials 2,3 are missing for
        every arm. score must refuse (phantom all-FAIL trials would dilute the
        delta)."""
        gt = {"fixtures": [{"id": 1, "bugs": [
            {"bug_id": "f1-b1", "off_axis": False}]}]}
        cells = [(1, 1, a, [self.prim("f1-b1", "PASS")])
                 for a in ("with", "mid", "without")]
        rc = run_evals.score(self.make_run("rungrid2", 3, cells, gt) and "rungrid2")
        self.assertNotEqual(rc, 0)

    def test_trials_zero_returns_nonzero(self):
        """trials=0 → range(1,1) empty, _majority_pass([]) False → all-zero
        false-green. score must refuse the degenerate trial count."""
        gt = {"fixtures": [{"id": 1, "bugs": [
            {"bug_id": "f1-b1", "off_axis": False}]}]}
        cells = [(1, 1, a, [self.prim("f1-b1", "PASS")])
                 for a in ("with", "mid", "without")]
        rc = run_evals.score(self.make_run("rungrid0", 0, cells, gt) and "rungrid0")
        self.assertNotEqual(rc, 0)

    def test_valid_full_grid_still_scores(self):
        """Regression guard: a complete full 3-arm × all-trials grid still returns
        0 with complete:true (the guard must not reject a correctly-staged run)."""
        gt = {"fixtures": [{"id": 1, "bugs": [
            {"bug_id": "f1-b1", "off_axis": False}]}]}
        cells = []
        for t in (1, 2):
            for a in ("with", "mid", "without"):
                cells.append((1, t, a, [self.prim("f1-b1", "PASS")]))
        rc = run_evals.score(self.make_run("rungridok", 2, cells, gt) and "rungridok")
        self.assertEqual(rc, 0)
        self.assertTrue(self.last_run()["complete"])

    def test_duplicate_cell_returns_nonzero(self):
        """The same (arm, fid, trial) listed twice is a manifest-shape error → the
        grid-completeness assertion refuses it."""
        gt = {"fixtures": [{"id": 1, "bugs": [
            {"bug_id": "f1-b1", "off_axis": False}]}]}
        cells = [(1, 1, a, [self.prim("f1-b1", "PASS")])
                 for a in ("with", "mid", "without")]
        cells.append((1, 1, "with", [self.prim("f1-b1", "PASS")]))  # dup WITH cell
        rc = run_evals.score(self.make_run("rungriddup", 1, cells, gt) and "rungriddup")
        self.assertNotEqual(rc, 0)

    def test_allow_incomplete_partial_grid_still_scores(self):
        """The grid guard is a `complete`-run assertion; --allow-incomplete (a
        smoke/debug score) may legitimately score a partial grid — here only the
        WITH cell for f1-t1, which would be refused under complete."""
        gt = {"fixtures": [{"id": 1, "bugs": [
            {"bug_id": "f1-b1", "off_axis": False}]}]}
        cells = [(1, 1, "with", [self.prim("f1-b1", "PASS")])]
        self.make_run("rungridsmoke", 1, cells, gt, collect=False)
        self.assertEqual(
            run_evals.score("rungridsmoke", allow_incomplete=True), 0)
        self.assertFalse(self.last_run()["complete"])


class TestSecondaryReconciliation(ScoreTestBase):
    """S-1: a full-fixture complete run whose observed secondary count differs from
    the documented 26-pool stamps a visible reconciliation (contracted/reconciled)
    in last_run.json — diagnostic only, rc stays 0 (score does NOT gate on it)."""

    def test_under_26_secondary_stamps_mismatch_but_returns_zero(self):
        """A full-fixture (single-fixture GT, fully covered) complete run grading
        fewer than 26 secondary records stamps contracted=26 + reconciled=False and
        STILL returns 0 — the secondary count is a diagnostic, not a gate."""
        gt = {"fixtures": [{"id": 1, "bugs": [
            {"bug_id": "f1-b1", "off_axis": False}]}]}
        sec_records = [self.sec(f"expectation-{i}", "PASS") for i in range(1, 4)]
        cell_records = [self.prim("f1-b1", "PASS")] + sec_records  # 3 secondary < 26
        cells = [(1, 1, a, cell_records) for a in ("with", "mid", "without")]
        rc = run_evals.score(self.make_run("runrec", 1, cells, gt) and "runrec")
        self.assertEqual(rc, 0)                                   # diagnostic, not a gate
        sd = self.last_run()["secondary_diagnostic"]
        self.assertEqual(sd["graded_expectations"], 3)
        self.assertEqual(sd["contracted"], run_evals._CONTRACTED_SECONDARY_POOL)
        self.assertFalse(sd["reconciled"])


class TestDispatchStatusSentinel(ScoreTestBase):
    """S-2: the README collect contract writes each result_file using the
    `DISPATCH_STATUS: OK\\n\\n<body>` sentinel. _parse_verdict_file must consume the
    sentinel without counting it malformed (the documented file shape the unit
    tests bypass)."""

    def test_ok_sentinel_parses_with_zero_malformed(self):
        """A result file in the documented DISPATCH_STATUS: OK\\n\\n<JSONL> shape
        parses its verdicts with malformed == 0 (the sentinel line is consumed,
        NOT counted malformed — the per-cell inflation the README contract caused)."""
        gt = {"fixtures": [{"id": 1, "bugs": [
            {"bug_id": "f1-b1", "off_axis": False}]}]}
        # Build cells normally, then overwrite each result_file with the documented
        # DISPATCH_STATUS: OK sentinel prefix in front of the JSONL body.
        cells = [(1, 1, a, [self.prim("f1-b1", "PASS")])
                 for a in ("with", "mid", "without")]
        dd = self.make_run("runok", 1, cells, gt)
        manifest = json.loads((dd / "stage-manifest.json").read_text())
        for c in manifest["cells"]:
            rf = dd / c["result_file"]
            body = rf.read_text()
            rf.write_text("DISPATCH_STATUS: OK\n\n" + body, encoding="utf-8")
        rc = run_evals.score("runok")
        self.assertEqual(rc, 0)
        lr = self.last_run()
        # sentinel consumed, not counted malformed
        self.assertEqual(lr["malformed_verdicts"],
                         {"with": 0, "mid": 0, "without": 0})
        # the real verdict still parsed (PASS)
        self.assertEqual(lr["with"]["pass"], 1)

    def test_plain_jsonl_still_parses_unchanged(self):
        """Backward-compat: a file with NO DISPATCH_STATUS sentinel (pure JSONL, as
        make_run writes) still parses exactly as before — the sentinel handling is
        consume-if-present, never require."""
        p = pathlib.Path(self._dispatch_tmp.name) / "plain.jsonl"
        p.write_text('{"id":"f1-b1","tag":"primary","verdict":"PASS"}\n',
                     encoding="utf-8")
        parsed, mal, failed = run_evals._parse_verdict_file(p)
        self.assertEqual(mal, 0)
        self.assertFalse(failed)
        self.assertEqual(parsed[("primary", "f1-b1")], True)

    def test_error_sentinel_is_dispatch_failure(self):
        """A DISPATCH_STATUS: ERROR first line → dispatch failure (no records, the
        flag S-1's guard refuses on), with no malformed inflation."""
        p = pathlib.Path(self._dispatch_tmp.name) / "err.jsonl"
        p.write_text("DISPATCH_STATUS: ERROR: timed out\n", encoding="utf-8")
        parsed, mal, failed = run_evals._parse_verdict_file(p)
        self.assertTrue(failed)
        self.assertEqual(parsed, {})
        self.assertEqual(mal, 0)


if __name__ == "__main__":
    unittest.main()
