#!/usr/bin/env python3
"""Tests for scripts/dispatch.py — manifest.jsonl bookkeeping for disk-mediated dispatch.

Pure stdlib unittest. Run: python3 scripts/test_dispatch.py (registered in run_tests.sh).
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, REPO_ROOT)

from scripts import dispatch  # noqa: E402


def read_manifest(d):
    p = os.path.join(d, "manifest.jsonl")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


class DispatchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ddir = os.path.join(self.tmp, "crucible-dispatch-123")
        os.makedirs(self.ddir)
        self.dfile = os.path.join(self.ddir, "1-plan-writer.md")
        with open(self.dfile, "w", encoding="utf-8") as f:
            f.write("# Dispatch: plan-writer\n" + ("x" * 100))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_seq_empty(self):
        self.assertEqual(dispatch.cmd_seq(self.ddir), 0)
        # capture stdout: cmd_seq prints the number
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            dispatch.cmd_seq(self.ddir)
        self.assertEqual(buf.getvalue().strip(), "1")

    def test_before_and_after(self):
        self.assertEqual(dispatch.cmd_before(_Args(self.ddir, 1, self.dfile, "plan-writer", None, None, "opus")), 0)
        rows = read_manifest(self.ddir)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "dispatched")
        self.assertEqual(rows[0]["file"], "1-plan-writer.md")
        with open(self.dfile, encoding="utf-8") as f:
            self.assertEqual(rows[0]["input_chars"], len(f.read()))
        self.assertEqual(rows[0]["output_chars"], None)

        self.assertEqual(dispatch.cmd_after(_Args(self.ddir, status="completed", seq=1)), 0)
        rows = read_manifest(self.ddir)
        self.assertEqual(len(rows), 2)
        last = rows[-1]
        self.assertEqual(last["status"], "completed")
        self.assertEqual(last["file"], "1-plan-writer.md")  # copied from dispatched
        self.assertEqual(last["input_chars"], rows[0]["input_chars"])  # copied, not re-measured
        self.assertEqual(last["role"], "plan-writer")

    def test_seq_recovery_after_entries(self):
        dispatch.cmd_before(_Args(self.ddir, 1, self.dfile, "plan-writer", None, None, "opus"))
        dispatch.cmd_after(_Args(self.ddir, status="completed", seq=1))
        # next seq = max(1) + 1
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            dispatch.cmd_seq(self.ddir)
        self.assertEqual(buf.getvalue().strip(), "2")

    def test_after_invalid_status(self):
        self.assertEqual(dispatch.cmd_after(_Args(status="dispatched", seq=1)), 2)

    def test_before_missing_file(self):
        self.assertEqual(dispatch.cmd_before(_Args(self.ddir, 1, "/nonexistent", "r", None, None, "opus")), 1)

    def test_before_invalid_tier(self):
        self.assertEqual(dispatch.cmd_before(_Args(self.ddir, 1, self.dfile, "r", None, None, "fable")), 2)

    def test_summary_pipebuf_truncation(self):
        huge = "s" * 8000
        dispatch.cmd_before(_Args(self.ddir, 1, self.dfile, "plan-writer", None, None, "opus"))
        self.assertEqual(dispatch.cmd_after(_Args(self.ddir, status="completed", seq=1, summary=huge)), 0)
        # measure the actual byte length of the last written line
        with open(os.path.join(self.ddir, "manifest.jsonl"), encoding="utf-8") as f:
            lines = f.read().splitlines()
        self.assertLessEqual(len(lines[-1]) + 1, dispatch.PIPE_BUF)

    def test_cleanup_success_copies_and_deletes(self):
        dispatch.cmd_before(_Args(self.ddir, 1, self.dfile, "plan-writer", None, None, "opus"))
        dispatch.cmd_after(_Args(self.ddir, status="completed", seq=1))
        with open(os.path.join(self.ddir, "receipt-ledger.jsonl"), "w") as f:
            f.write("{}\n")
        scratch = os.path.join(self.tmp, "scratch")
        self.assertEqual(dispatch.cmd_cleanup(_Args(self.ddir, scratch=scratch)), 0)
        dest = os.path.join(scratch, "crucible-dispatch-123")
        self.assertTrue(os.path.exists(os.path.join(dest, "manifest.jsonl")))
        self.assertTrue(os.path.exists(os.path.join(dest, "receipt-ledger.jsonl")))
        self.assertFalse(os.path.exists(self.ddir))

    def test_cleanup_failed_copies_dir(self):
        with open(os.path.join(self.ddir, "manifest.jsonl"), "w") as f:
            f.write("{}\n")
        scratch = os.path.join(self.tmp, "scratch")
        self.assertEqual(dispatch.cmd_cleanup(_Args(self.ddir, scratch=scratch, failed=True)), 0)
        self.assertTrue(os.path.isdir(os.path.join(scratch, "crucible-dispatch-123")))
        self.assertTrue(os.path.exists(self.ddir))  # /tmp copy left in place


class _Args:
    """Tiny namespace standing in for argparse.Namespace."""

    def __init__(self, d=None, seq=None, file=None, role=None, phase=None, task=None,
                 tier=None, status=None, summary=None, output_chars=None, tool_calls=None,
                 duration=None, failed=False, scratch=None):
        self.dir = d
        self.seq = seq
        self.file = file
        self.role = role
        self.phase = phase
        self.task = task
        self.model_tier = tier
        self.status = status
        self.summary = summary
        self.output_chars = output_chars
        self.tool_calls = tool_calls
        self.duration = duration
        self.failed = failed
        self.scratch = scratch


if __name__ == "__main__":
    unittest.main(verbosity=2)