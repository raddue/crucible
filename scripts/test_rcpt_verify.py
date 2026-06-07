#!/usr/bin/env python3
"""Stdlib unittest suite for scripts/rcpt_verify.py.

Run from repo root:  python3 scripts/test_rcpt_verify.py
                  or  python3 -m unittest scripts.test_rcpt_verify -v

No pytest — matches the stdlib-only discipline of rcpt_verify.py itself, and the
flat-in-scripts/ layout of scripts/test_catalog.py (a `scripts/tests/` subdir is
caught by the repo-wide `tests/` .gitignore rule).
"""
import importlib.util
import json
import pathlib
import subprocess
import sys
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent / "rcpt_verify.py"
REPO = pathlib.Path(__file__).resolve().parent.parent
CORPUS = REPO / "eval/ledger-return-protocol"


def run(*args, stdin=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin, capture_output=True, text=True,
    )


def _import_rv():
    spec = importlib.util.spec_from_file_location("rcpt_verify", SCRIPT)
    rv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rv)
    return rv


def _load(name):
    return [json.loads(l) for l in (CORPUS / name).read_text().splitlines() if l.strip()]


class TestSkeleton(unittest.TestCase):
    def test_no_args_usage_nonzero(self):
        r = run()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("usage", (r.stderr + r.stdout).lower())

    def test_exposes_main(self):
        rv = _import_rv()
        self.assertTrue(hasattr(rv, "main"))


class TestV1CorpusEquivalence(unittest.TestCase):
    """Tier-1 port must classify the corpus identically to lint.py: the 5 sample
    receipts lint-pass; the 5 Tier-1 injections raise from lint_receipt; the 2
    Tier-2-only rows (102-inject/105-inject — the ONLY artifact_bodies carriers)
    return cleanly from lint_receipt (their catch fires via the Tier-2 path)."""

    def test_samples_lint_pass(self):
        rv = _import_rv()
        for rec in _load("sample-corpus/receipts.jsonl"):
            self.assertIn(rv.lint_receipt(rec["receipt"]), {"PASS", "FAIL", "BLOCKED"})

    def test_injections_partition_by_artifact_bodies(self):
        rv = _import_rv()
        inject_dir = CORPUS / "inject"
        # M5: glob so a future inject shape is auto-covered (don't hard-code names).
        shapes = sorted(inject_dir.glob("shape-*.jsonl"))
        self.assertTrue(shapes, "no inject/shape-*.jsonl found")
        for shape_path in shapes:
            for rec in _load(f"inject/{shape_path.name}"):
                try:
                    rv.lint_receipt(rec["receipt"])
                    raised = False
                except rv.LintError:
                    raised = True
                if rec.get("artifact_bodies"):
                    # Tier-2-only rows (102/105) — lint_receipt must NOT raise; their
                    # catch is asserted via the --eval / verify_witness path (Task 6/8).
                    self.assertFalse(
                        raised,
                        f"{rec.get('dispatch-id','?')} carries artifact_bodies "
                        f"(Tier-2-only) — lint_receipt must NOT raise",
                    )
                else:
                    self.assertTrue(
                        raised,
                        f"{shape_path.name}/{rec.get('dispatch-id','?')} should Tier-1 LINT-FAIL",
                    )


if __name__ == "__main__":
    unittest.main()
