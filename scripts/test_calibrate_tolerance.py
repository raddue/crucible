#!/usr/bin/env python3
"""Unit tests for scripts/calibrate_tolerance.py (#442 G5)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.calibrate_tolerance import _per_fixture_pass_rate


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


if __name__ == "__main__":
    unittest.main()
