#!/usr/bin/env python3
"""run-id validation re-assertion for the delve eval harness (#373).

stdlib unittest. The validator is the copied _runid.validate_run_id; this re-asserts
its I-9 behavior in delve's own gating suite (the drift check pins the body; this pins
the behavior).
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from skills.delve.evals import run_evals  # noqa: E402
from skills.delve.evals._runid import validate_run_id  # noqa: E402


class TestRunIdValidation(unittest.TestCase):
    def test_accepts_well_formed_ids(self):
        for ok in ("run1", "2026-06-26T20-45-00", "abc_DEF-123", "_x"):
            validate_run_id(ok)  # must not raise

    def test_rejects_flag_like_and_traversal_unsafe(self):
        for bad in ("-rf", "--force", "../escape", "a/b", "has space",
                    "x" * 40, "", "a.b"):
            with self.assertRaises(ValueError):
                validate_run_id(bad)

    def test_stage_rejects_bad_run_id(self):
        with self.assertRaises(ValueError):
            run_evals.stage("../escape")


if __name__ == "__main__":
    unittest.main()
