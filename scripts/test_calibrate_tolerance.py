#!/usr/bin/env python3
"""Unit tests for scripts/calibrate_tolerance.py (#442 G5, #441 calibrate() body)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.calibrate_tolerance import _per_fixture_pass_rate, calibrate


class TestPerFixturePassRate(unittest.TestCase):
    def test_missing_per_trial_verdicts_key_does_not_crash(self):
        # G5: an expectation lacking 'per_trial_verdicts' must not KeyError.
        fr = {"expectations": [{"id": "e1"}]}  # no per_trial_verdicts
        self.assertEqual(_per_fixture_pass_rate(fr), 0.0)

    def test_ragged_per_trial_lists_do_not_crash(self):
        # G5: n_trials was read from [0]; a shorter later list must not IndexError.
        fr = {"expectations": [
            {"per_trial_verdicts": ["PASS", "PASS", "PASS"]},
            {"per_trial_verdicts": ["PASS"]},  # ragged (shorter)
        ]}
        # common prefix = 1 trial; both PASS at t=0 -> rate 1.0
        self.assertEqual(_per_fixture_pass_rate(fr), 1.0)

    def test_ragged_with_fail_in_common_prefix(self):
        fr = {"expectations": [
            {"per_trial_verdicts": ["PASS", "FAIL"]},
            {"per_trial_verdicts": ["FAIL"]},  # common prefix = 1; t=0 -> not all PASS
        ]}
        self.assertEqual(_per_fixture_pass_rate(fr), 0.0)

    def test_no_expectations_returns_zero(self):
        self.assertEqual(_per_fixture_pass_rate({"expectations": []}), 0.0)
        self.assertEqual(_per_fixture_pass_rate({}), 0.0)

    def test_happy_path_unchanged(self):
        fr = {"expectations": [
            {"per_trial_verdicts": ["PASS", "FAIL", "PASS"]},
            {"per_trial_verdicts": ["PASS", "PASS", "PASS"]},
        ]}
        # t0 all PASS, t1 not (FAIL), t2 all PASS -> 2/3
        self.assertAlmostEqual(_per_fixture_pass_rate(fr), 2 / 3)


def _fixture(fid, per_trial):
    """A scored-fixture dict: one expectation carrying per_trial verdicts. The
    per-fixture rate = k PASS-trials / N trials (via _per_fixture_pass_rate), so
    ["PASS"]->1.0, ["FAIL"]->0.0, ["PASS","FAIL"]->0.5 — rates are DERIVED, never
    a settable field."""
    return {"id": fid, "expectations": [{"per_trial_verdicts": per_trial}]}


class TestCalibrate(unittest.TestCase):
    """#441 gap-2: calibrate() body — clamp, floor/ceiling-binding flags, pstdev
    degenerate fallback, str-vs-list lens_column routing, empty input, output shape.
    Builds temp last_run.json + evals.json (rates derive from per_trial_verdicts)."""

    def _run(self, runs, lens_map):
        """runs: list of run-fixture-lists, each [(fid, per_trial), ...].
        lens_map: {fid: lens_column}. Returns calibrate() output."""
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            evals_path = tdp / "evals.json"
            evals_path.write_text(json.dumps(
                {"evals": [{"id": fid, "lens_column": lc} for fid, lc in lens_map.items()]}
            ), encoding="utf-8")
            input_paths = []
            for i, run in enumerate(runs):
                p = tdp / f"run-{i}.json"
                p.write_text(json.dumps(
                    {"fixtures": [_fixture(fid, pt) for fid, pt in run]}
                ), encoding="utf-8")
                input_paths.append(p)
            return calibrate(input_paths, evals_path)

    def test_empty_input_raises_valueerror(self):
        with tempfile.TemporaryDirectory() as td:
            # calibrate() raises on `if not input_paths` BEFORE reading evals,
            # so the evals file is never opened — pass an unwritten path.
            evals_path = Path(td) / "evals.json"
            with self.assertRaises(ValueError):
                calibrate([], evals_path)

    def test_floor_binding_identical_rates(self):
        # 2 runs, fixture f1 rate 1.0 both -> sigma 0 -> t_emp 0 < 0.447 -> floor.
        out = self._run(
            [[("f1", ["PASS"])], [("f1", ["PASS"])]],
            {"f1": "Surgical"},
        )
        self.assertEqual(out["tolerance"], 0.45)  # round(0.447, 2)
        self.assertTrue(out["floor_binding"])
        self.assertFalse(out["ceiling_binding"])

    def test_ceiling_binding_wide_spread(self):
        # column rates [0.0, 1.0] -> pstdev 0.5 -> t_emp 1.0 -> clamps to 0.7.
        out = self._run(
            [[("f1", ["FAIL"])], [("f1", ["PASS"])]],
            {"f1": "Surgical"},
        )
        self.assertEqual(out["t_emp"], 1.0)
        self.assertEqual(out["tolerance"], 0.7)
        self.assertTrue(out["ceiling_binding"])
        self.assertFalse(out["floor_binding"])

    def test_mid_range_neither_binding(self):
        # column rates [1.0, 1.0, 0.5] -> pstdev ~0.2357 -> t_emp ~0.4714 -> 0.47.
        out = self._run(
            [[("f1", ["PASS"])], [("f1", ["PASS"])], [("f1", ["PASS", "FAIL"])]],
            {"f1": "Surgical"},
        )
        self.assertAlmostEqual(out["t_emp"], 0.4714, places=3)
        self.assertEqual(out["tolerance"], 0.47)
        self.assertFalse(out["floor_binding"])
        self.assertFalse(out["ceiling_binding"])

    def test_single_rate_degenerate_no_statisticserror(self):
        # one run, one rate -> len(rates) < 2 -> sigma 0.0 fallback, no StatisticsError.
        out = self._run([[("f1", ["PASS"])]], {"f1": "Surgical"})
        self.assertEqual(out["per_lens_sigma_empirical"]["Surgical"], 0.0)
        self.assertEqual(out["sigma_worst"], 0.0)
        self.assertEqual(out["tolerance"], 0.45)

    def test_lens_column_list_routes_into_both(self):
        # f1 lens=list ["Surgical","DRY"] feeds rate into BOTH columns; "SRP" (str)
        # feeds one; "Nonsense" (unknown) feeds none.
        out = self._run(
            [
                [("f1", ["FAIL"]), ("f2", ["FAIL"]), ("f3", ["FAIL"])],
                [("f1", ["PASS"]), ("f2", ["PASS"]), ("f3", ["PASS"])],
            ],
            {"f1": ["Surgical", "DRY"], "f2": "SRP", "f3": "Nonsense"},
        )
        sig = out["per_lens_sigma_empirical"]
        # Routing signal: Surgical & DRY both == 0.5 proves the list fed BOTH columns;
        # SRP == 0.5 proves the str fed exactly one. OCP == 0.0 only confirms no fixture
        # reached OCP (degenerate <2 rates) — it is NOT the unknown-"Nonsense" proof.
        self.assertEqual(sig["Surgical"], 0.5)  # list routed here
        self.assertEqual(sig["DRY"], 0.5)        # ...and here
        self.assertEqual(sig["SRP"], 0.5)        # str routed here
        self.assertEqual(sig["OCP"], 0.0)        # no fixture reached OCP

    def test_output_shape_invariants(self):
        out = self._run([[("f1", ["PASS"])], [("f1", ["FAIL"])]], {"f1": "Surgical"})
        for k in ("tolerance", "sigma_worst", "t_emp", "per_lens_sigma_empirical",
                  "floor_binding", "ceiling_binding", "analytic_floor", "design_ceiling"):
            self.assertIn(k, out)
        self.assertEqual(set(out["per_lens_sigma_empirical"]),
                         {"Surgical", "DRY", "SRP", "OCP"})
        self.assertEqual(out["analytic_floor"], 0.447)
        self.assertEqual(out["design_ceiling"], 0.7)
        self.assertGreaterEqual(out["tolerance"], 0.45)
        self.assertLessEqual(out["tolerance"], 0.7)


if __name__ == "__main__":
    unittest.main()
