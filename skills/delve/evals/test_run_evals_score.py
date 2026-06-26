#!/usr/bin/env python3
"""`score` mechanics for the delve eval harness (#373) — fully synthetic, no live
agents. Stages the committed `sample` fixture, writes a hand-authored recorded
findings JSON + .collect-status, and asserts last_run.json carries the expected
matcher metrics.
"""
import json
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from skills.delve.evals import run_evals  # noqa: E402

_EVALS_DIR = pathlib.Path(__file__).resolve().parent

# A hand-authored recorded findings set over the `sample` fixture (6 planted bugs):
# hits sm-b1, sm-b3, sm-b5 (one of which, sm-b5, is off_axis), plus one positional
# false-positive (a non-bug finding). → recall 3/6, FP 1/4, off-axis recall 1/1.
SAMPLE_FINDINGS = [
    {"file": "inventory.py", "line": 11,
     "summary": "off-by-one in last_n drops the final element",
     "failure_scenario": "the most recent item is silently omitted",
     "severity": "Important", "verdict": "CONFIRMED"},
    {"file": "inventory.py", "line": 24,
     "summary": "is_in_stock uses the wrong operator and returns true at zero",
     "failure_scenario": "a sold-out SKU is reported available",
     "severity": "Important", "verdict": "CONFIRMED"},
    {"file": "report.py", "line": 10,
     "summary": "write_report leaks a resource — the file handle is not closed",
     "failure_scenario": "fd exhaustion under repeated calls",
     "severity": "Minor", "verdict": "PLAUSIBLE"},
    # A false positive: real line, but about a wholly different (non-planted) concern
    # with no signature overlap → must NOT match any bug.
    {"file": "inventory.py", "line": 5,
     "summary": "the module could use a docstring for clarity",
     "failure_scenario": "none — readability only",
     "severity": "Suggestion", "verdict": "PLAUSIBLE"},
]


class _DispatchEnv(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._prev = os.environ.get("XDG_RUNTIME_DIR")
        os.environ["XDG_RUNTIME_DIR"] = self._tmp.name
        # Preserve any pre-existing committed/ignored eval outputs.
        self._lr = _EVALS_DIR / "last_run.json"
        self._md = _EVALS_DIR / "results.md"
        self._saved = {p: (p.read_bytes() if p.exists() else None)
                       for p in (self._lr, self._md)}

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("XDG_RUNTIME_DIR", None)
        else:
            os.environ["XDG_RUNTIME_DIR"] = self._prev
        self._tmp.cleanup()
        for p, data in self._saved.items():
            if data is None:
                if p.exists():
                    p.unlink()
            else:
                p.write_bytes(data)

    def _stage_and_record(self, run_id, findings, *, sentinel="DISPATCH_STATUS: OK",
                          collect=True):
        dispatch_dir = run_evals.stage(run_id, fixture="sample")
        m = json.loads((dispatch_dir / "stage-manifest.json").read_text("utf-8"))
        cell = m["cells"][0]
        body = json.dumps(findings)
        text = f"{sentinel}\n\n{body}" if sentinel else body
        (dispatch_dir / cell["result_file"]).write_text(text, encoding="utf-8")
        if collect:
            (dispatch_dir / ".collect-status").write_text("", encoding="utf-8")
        return dispatch_dir


class TestScore(_DispatchEnv):
    def test_score_computes_expected_metrics(self):
        self._stage_and_record("test-score-1", SAMPLE_FINDINGS)
        rc = run_evals.score("test-score-1")
        self.assertEqual(rc, 0)

        lr = json.loads((_EVALS_DIR / "last_run.json").read_text("utf-8"))
        self.assertTrue(lr["complete"])
        agg = lr["aggregate"]
        self.assertEqual(agg["bugs"], 6)
        self.assertEqual(agg["matched"], 3)
        self.assertEqual(agg["recall"], 3 / 6)
        self.assertEqual(agg["findings"], 4)
        self.assertEqual(agg["false_positives"], 1)
        self.assertEqual(agg["false_positive_rate"], 1 / 4)
        # Only sm-b5 is off_axis in the fixture, and it was hit.
        self.assertEqual(agg["off_axis_recall"], 1.0)

        pf = lr["per_fixture"][0]
        self.assertEqual(pf["fixture_id"], "sample")
        self.assertEqual(sorted(pf["unmatched_bugs"]),
                         ["sm-b2", "sm-b4", "sm-b6"])
        self.assertFalse(pf["dispatch_failed"])
        self.assertTrue((_EVALS_DIR / "results.md").exists())

    def test_score_refuses_without_collect_status(self):
        self._stage_and_record("test-score-2", SAMPLE_FINDINGS, collect=False)
        self.assertEqual(run_evals.score("test-score-2"), 1)
        # --allow-incomplete scores anyway, stamping complete:false.
        self.assertEqual(
            run_evals.score("test-score-2", allow_incomplete=True), 0)
        lr = json.loads((_EVALS_DIR / "last_run.json").read_text("utf-8"))
        self.assertFalse(lr["complete"])

    def test_score_error_sentinel_scores_zero(self):
        self._stage_and_record("test-score-3", SAMPLE_FINDINGS,
                               sentinel="DISPATCH_STATUS: ERROR")
        self.assertEqual(run_evals.score("test-score-3"), 0)
        lr = json.loads((_EVALS_DIR / "last_run.json").read_text("utf-8"))
        agg = lr["aggregate"]
        self.assertEqual(agg["matched"], 0)
        self.assertEqual(agg["findings"], 0)
        self.assertEqual(agg["recall"], 0.0)
        self.assertEqual(agg["false_positive_rate"], 0.0)
        self.assertTrue(lr["per_fixture"][0]["dispatch_failed"])

    def test_score_no_sentinel_parses_bare_array(self):
        # Backward-compat: a file with no DISPATCH_STATUS sentinel parses as a bare
        # JSON array (as a minimal operator might write).
        self._stage_and_record("test-score-4", SAMPLE_FINDINGS, sentinel=None)
        self.assertEqual(run_evals.score("test-score-4"), 0)
        lr = json.loads((_EVALS_DIR / "last_run.json").read_text("utf-8"))
        self.assertEqual(lr["aggregate"]["matched"], 3)

    def test_score_no_manifest_fails(self):
        self.assertEqual(run_evals.score("test-score-missing"), 1)

    def test_score_malformed_line_counts_as_fp_without_crash(self):
        # R2-S1 regression: a recorded finding with an unparseable `line` (here None)
        # must NOT abort the whole score with a raw ValueError. The run completes
        # (rc 0), the valid findings still match (recall 3/6), and the malformed one is
        # counted as a kept-unmatched false positive (findings 5, FP 2) and reflected in
        # the new per-cell `malformed_findings` count.
        malformed = {"file": "inventory.py", "line": None,
                     "summary": "the line is unparseable here",
                     "failure_scenario": "n/a", "severity": "Minor",
                     "verdict": "PLAUSIBLE"}
        findings = SAMPLE_FINDINGS + [malformed]
        self._stage_and_record("test-score-malformed", findings)
        rc = run_evals.score("test-score-malformed")
        self.assertEqual(rc, 0)

        lr = json.loads((_EVALS_DIR / "last_run.json").read_text("utf-8"))
        agg = lr["aggregate"]
        self.assertEqual(agg["matched"], 3)          # valid findings still match
        self.assertEqual(agg["recall"], 3 / 6)
        self.assertEqual(agg["findings"], 5)         # malformed finding still counted
        self.assertEqual(agg["false_positives"], 2)  # original FP + the malformed one
        pf = lr["per_fixture"][0]
        self.assertEqual(pf["malformed_findings"], 1)

    def test_score_reconciles_scope_prefixed_paths(self):
        # S2 regression: the live engine may emit scope-relative paths
        # (`<scope>/inventory.py`) rather than bare GT filenames. The harness
        # reconciles the fixture's known `scope` prefix so verbatim-recorded findings
        # still join — scoring identically to the bare-path case (recall 3/6 etc.),
        # NOT silently 0.0.
        scope = "skills/delve/evals/fixtures/sample"
        prefixed = [{**f, "file": f"{scope}/{f['file']}"} for f in SAMPLE_FINDINGS]
        self._stage_and_record("test-score-scope", prefixed)
        self.assertEqual(run_evals.score("test-score-scope"), 0)

        lr = json.loads((_EVALS_DIR / "last_run.json").read_text("utf-8"))
        agg = lr["aggregate"]
        self.assertEqual(agg["bugs"], 6)
        self.assertEqual(agg["matched"], 3)
        self.assertEqual(agg["recall"], 3 / 6)
        self.assertEqual(agg["findings"], 4)
        self.assertEqual(agg["false_positives"], 1)
        self.assertEqual(agg["false_positive_rate"], 1 / 4)
        self.assertEqual(agg["off_axis_recall"], 1.0)


if __name__ == "__main__":
    unittest.main()
