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
        self.assertEqual(rows[0]["model_tier"], "opus")
        self.assertEqual(rows[0]["model_profile"], "high")

        self.assertEqual(dispatch.cmd_after(_Args(self.ddir, status="completed", seq=1, actual_model="observed-model")), 0)
        rows = read_manifest(self.ddir)
        self.assertEqual(len(rows), 2)
        last = rows[-1]
        self.assertEqual(last["status"], "completed")
        self.assertEqual(last["file"], "1-plan-writer.md")  # copied from dispatched
        self.assertEqual(last["input_chars"], rows[0]["input_chars"])  # copied, not re-measured
        self.assertEqual(last["role"], "plan-writer")
        self.assertEqual(last["model_tier"], "opus")
        self.assertEqual(last["model_profile"], "high")
        self.assertEqual(last["actual_model"], "observed-model")

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

    def test_before_missing_file_writes_null_input_chars(self):
        # measurement failure must not block dispatch — input_chars null
        self.assertEqual(dispatch.cmd_before(_Args(self.ddir, 1, "/nonexistent", "r", None, None, "opus")), 0)
        rows = read_manifest(self.ddir)
        self.assertEqual(rows[0]["status"], "dispatched")
        self.assertIsNone(rows[0]["input_chars"])
        self.assertEqual(rows[0]["file"], "nonexistent")

    def test_before_accepts_unknown_model_label_without_blocking(self):
        self.assertEqual(dispatch.cmd_before(_Args(self.ddir, 1, self.dfile, "r", None, None, "provider/custom-model")), 0)
        rows = read_manifest(self.ddir)
        self.assertEqual(rows[0]["model_tier"], "provider/custom-model")
        self.assertIsNone(rows[0]["model_profile"])

    def test_before_accepts_neutral_profile(self):
        self.assertEqual(dispatch.cmd_before(_Args(self.ddir, 1, self.dfile, "r", None, None, "standard")), 0)
        rows = read_manifest(self.ddir)
        self.assertEqual(rows[0]["model_tier"], "standard")
        self.assertEqual(rows[0]["model_profile"], "standard")

    def test_oversized_model_tier_keeps_manifest_line_within_pipebuf(self):
        self.assertEqual(dispatch.main([
            "before", "--dir", self.ddir, "--seq", "1", "--file", self.dfile,
            "--role", "r", "--model-tier", "x" * 4100,
        ]), 0)
        with open(os.path.join(self.ddir, "manifest.jsonl"), "rb") as f:
            line = f.readline()
        self.assertLessEqual(len(line), dispatch.PIPE_BUF)
        self.assertIsNone(json.loads(line)["model_tier"])

    def test_oversized_model_tier_preserves_short_summary(self):
        dispatch._append(self.ddir, {
            "seq": 1,
            "model_tier": "x" * 4100,
            "summary": "useful summary",
        })
        with open(os.path.join(self.ddir, "manifest.jsonl"), "rb") as f:
            line = f.readline()
        entry = json.loads(line)
        self.assertLessEqual(len(line), dispatch.PIPE_BUF)
        self.assertIsNone(entry["model_tier"])
        self.assertEqual(entry["summary"], "useful summary")

    def test_oversized_actual_model_keeps_manifest_line_within_pipebuf(self):
        dispatch.cmd_before(_Args(self.ddir, 1, self.dfile, "r", None, None, "standard"))
        self.assertEqual(dispatch.main([
            "after", "--dir", self.ddir, "--seq", "1", "--status", "completed",
            "--actual-model", "x" * 4100,
        ]), 0)
        with open(os.path.join(self.ddir, "manifest.jsonl"), "rb") as f:
            lines = f.readlines()
        self.assertLessEqual(len(lines[-1]), dispatch.PIPE_BUF)
        self.assertIsNone(json.loads(lines[-1])["actual_model"])

    def test_before_omitted_model_tier_records_null(self):
        self.assertEqual(dispatch.cmd_before(_Args(self.ddir, 1, self.dfile, "r", None, None, None)), 0)
        rows = read_manifest(self.ddir)
        self.assertIsNone(rows[0]["model_tier"])
        self.assertIsNone(rows[0]["model_profile"])

    def test_summary_pipebuf_truncation(self):
        huge = "s" * 8000
        dispatch.cmd_before(_Args(self.ddir, 1, self.dfile, "plan-writer", None, None, "opus"))
        self.assertEqual(dispatch.cmd_after(_Args(self.ddir, status="completed", seq=1, summary=huge)), 0)
        with open(os.path.join(self.ddir, "manifest.jsonl"), encoding="utf-8") as f:
            lines = f.read().splitlines()
        self.assertLessEqual(len(lines[-1].encode("utf-8")) + 1, dispatch.PIPE_BUF)

    def test_summary_pipebuf_unicode_bytes(self):
        # multibyte chars: PIPE_BUF is BYTES not characters
        huge = "\u00e9" * 8000
        dispatch.cmd_before(_Args(self.ddir, 1, self.dfile, "plan-writer", None, None, "opus"))
        self.assertEqual(dispatch.cmd_after(_Args(self.ddir, status="completed", seq=1, summary=huge)), 0)
        with open(os.path.join(self.ddir, "manifest.jsonl"), encoding="utf-8") as f:
            lines = f.read().splitlines()
        self.assertLessEqual(len(lines[-1].encode("utf-8")) + 1, dispatch.PIPE_BUF)

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

    def test_seq_refuses_on_interior_corruption(self):
        with open(os.path.join(self.ddir, "manifest.jsonl"), "w") as f:
            f.write('{"seq":1,"x":0}\n')
            f.write('{corrupt interior line}\n')
            f.write('{"seq":2,"x":0}\n')
        self.assertEqual(dispatch.cmd_seq(self.ddir), 1)

    def test_after_refuses_without_dispatched_entry(self):
        self.assertEqual(dispatch.cmd_after(_Args(self.ddir, status="completed", seq=1)), 1)
        rows = read_manifest(self.ddir)
        self.assertEqual(len(rows), 0)

    def test_cleanup_refuses_missing_ledger(self):
        dispatch.cmd_before(_Args(self.ddir, 1, self.dfile, "plan-writer", None, None, "opus"))
        dispatch.cmd_after(_Args(self.ddir, status="completed", seq=1))
        # receipt-ledger.jsonl missing -> refuse, leave dir intact
        scratch = os.path.join(self.tmp, "scratch")
        self.assertEqual(dispatch.cmd_cleanup(_Args(self.ddir, scratch=scratch)), 1)
        self.assertTrue(os.path.exists(self.ddir))

    def test_cleanup_failed_copies_dir(self):
        with open(os.path.join(self.ddir, "manifest.jsonl"), "w") as f:
            f.write("{}\n")
        scratch = os.path.join(self.tmp, "scratch")
        self.assertEqual(dispatch.cmd_cleanup(_Args(self.ddir, scratch=scratch, failed=True)), 0)
        self.assertTrue(os.path.isdir(os.path.join(scratch, "crucible-dispatch-123")))
        self.assertTrue(os.path.exists(self.ddir))


class _Args:
    """Tiny namespace standing in for argparse.Namespace."""

    def __init__(self, d=None, seq=None, file=None, role=None, phase=None, task=None,
                 tier=None, status=None, summary=None, output_chars=None, tool_calls=None,
                 duration=None, failed=False, scratch=None, actual_model=None):
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
        self.actual_model = actual_model


if __name__ == "__main__":
    unittest.main(verbosity=2)