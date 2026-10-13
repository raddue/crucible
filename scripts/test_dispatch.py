#!/usr/bin/env python3
"""Tests for scripts/dispatch.py — manifest.jsonl bookkeeping for disk-mediated dispatch.

Pure stdlib unittest. Run: python3 scripts/test_dispatch.py (registered in run_tests.sh).
"""

import hashlib
import json
import os
import shutil
import subprocess
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

    def test_after_records_pi_dispatch_provenance(self):
        dispatch.cmd_before(_Args(self.ddir, 1, self.dfile, "crucible-red-team", None, None, "high"))
        self.assertEqual(dispatch.main([
            "after", "--dir", self.ddir, "--seq", "1", "--status", "completed",
            "--actual-model", "provider/model", "--dispatch-ref", "run-123", "--harness", "pi",
        ]), 0)
        row = read_manifest(self.ddir)[-1]
        self.assertEqual(row["dispatch_ref"], "run-123")
        self.assertEqual(row["harness"], "pi")

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


class GateProvenanceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ddir = self.tmp.name
        self.marker = os.path.join(self.ddir, "gate-verdict.md")
        with open(self.marker, "w", encoding="utf-8") as f:
            f.write("Harness: pi\nVerdict: PASS\nRequired-Legs: crucible-red-team\n"
                    "Mapped-Model: crucible-red-team=provider/model\n")
        self.row = {"seq": 1, "file": "1-crucible-red-team.md", "role": "crucible-red-team",
                    "status": "completed", "dispatch_ref": "run-1", "actual_model": "provider/model",
                    "harness": "pi"}

    def run_checker(self):
        return subprocess.run([sys.executable, os.path.join(HERE, "check_gate_provenance.py"),
                               self.ddir, "--marker", self.marker],
                              capture_output=True, text=True)

    def write_manifest(self):
        with open(os.path.join(self.ddir, "manifest.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps(self.row) + "\n")

    def write_ledger(self, raw=None):
        with open(os.path.join(self.ddir, "receipt-ledger.jsonl"), "w", encoding="utf-8") as f:
            f.write(raw if raw is not None else json.dumps({
                "dispatch_id": "1-crucible-red-team", "phase": "quality-gate:round/1",
                "rcpt_sha256": "0" * 64, "verdict": "PASS"}) + "\n")

    def write_receipt(self, text=None):
        text = text if text is not None else (
            "RCPT v1.1 quality-gate/1-crucible-red-team\nVERDICT  PASS  conf=0.90\n"
            "ARTIFACTS\n  (none)\nTRACE\n  1  SKIPPED  no-artifacts\nCLAIMS\n  (none)\n"
            "WITNESS    lint:trace-consistent  expect-fail=/inconsistent/  ran=TRACE#1\n"
            "SUSPICION  0.00\nNEXT       (none)\nTRIPWIRE: none\nSUPERSEDES: none\n"
            "TRIPWIRE-CHILD: none\n"
        )
        with open(os.path.join(self.ddir, "1-crucible-red-team-receipt.md"), "w", encoding="utf-8") as f:
            f.write(text)
        self.write_ledger(json.dumps({"dispatch_id": "1-crucible-red-team",
                                      "phase": "quality-gate:round/1",
                                      "rcpt_sha256": hashlib.sha256(text.encode()).hexdigest(),
                                      "verdict": "PASS"}) + "\n")

    def test_empty_dispatch_reports_unavailable(self):
        result = self.run_checker()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertTrue(result.stdout.startswith("BLOCKED: DISPATCH-UNAVAILABLE\n"), result.stdout)

    def test_no_required_legs_cannot_pass(self):
        self.write_manifest()
        with open(self.marker, "w", encoding="utf-8") as f:
            f.write("Harness: pi\nVerdict: PASS\nRequired-Legs: ,\n")
        result = self.run_checker()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("BLOCKED: DISPATCH-UNAVAILABLE", result.stdout)

    def test_fabricated_ledger_cannot_pass_without_receipt(self):
        self.write_manifest()
        self.write_ledger()
        result = self.run_checker()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("receipt", result.stdout.lower())

    def test_malformed_receipt_fails_even_when_ledger_hash_matches(self):
        self.write_manifest()
        self.write_receipt("not an RCPT v1.1 receipt\n")
        result = self.run_checker()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("receipt verification failed", result.stdout)

    def test_verified_receipt_passes(self):
        self.write_manifest()
        self.write_receipt()
        result = self.run_checker()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_malformed_ledger_cannot_pass(self):
        self.write_manifest()
        self.write_receipt()
        self.write_ledger('{"dispatch_id":"1-crucible-red-team"}\n{broken\n')
        result = self.run_checker()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("receipt-ledger", result.stdout)

    def test_unrelated_receipt_with_correct_hash_cannot_cover_dispatch(self):
        self.write_manifest()
        text = ("RCPT v1.1 quality-gate/2-other\nVERDICT  PASS  conf=0.90\n"
                "ARTIFACTS\n  (none)\nTRACE\n  1  SKIPPED  no-artifacts\nCLAIMS\n  (none)\n"
                "WITNESS    lint:trace-consistent  expect-fail=/inconsistent/  ran=TRACE#1\n"
                "SUSPICION  0.00\nNEXT       (none)\nTRIPWIRE: none\nSUPERSEDES: none\n"
                "TRIPWIRE-CHILD: none\n")
        self.write_receipt(text)
        result = self.run_checker()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("receipt dispatch ID mismatch", result.stdout)

    def test_ledger_hash_must_match_receipt(self):
        self.write_manifest()
        self.write_receipt()
        self.write_ledger()
        result = self.run_checker()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("receipt not bound", result.stdout)

    def test_ledger_must_cover_dispatch(self):
        self.write_manifest()
        self.write_ledger(json.dumps({"dispatch_id": "other", "phase": "quality-gate:round/1",
                                      "rcpt_sha256": "0" * 64, "verdict": "PASS"}) + "\n")
        result = self.run_checker()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("receipt", result.stdout.lower())


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