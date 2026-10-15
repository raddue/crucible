#!/usr/bin/env python3
"""Tests orchestrator_scan.py — passive fleet liveness detector. Pure-stdlib
unittest; run `python3 scripts/test_orchestrator_scan.py`. Registered in
run_tests.sh."""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts import orchestrator_scan as scan  # noqa: E402


class ScanTest(unittest.TestCase):
    def test_inflight_worker_gone_fails_closed(self):
        doc = {"workers": [{"name": "w1", "worktree": "/tmp/gone", "status": "working"}]}
        verdicts, rc = scan.scan(doc, [])
        self.assertEqual(rc, 1)
        self.assertEqual(verdicts[0]["verdict"], "GONE")

    def test_idle_worker_gone_is_not_fatal(self):
        doc = {"workers": [{"name": "w1", "worktree": "/tmp/gone", "status": "idle"}]}
        _, rc = scan.scan(doc, [])
        self.assertEqual(rc, 0)

    def test_live_worker_matches_by_worktree(self):
        doc = {"workers": [{"name": "w1", "worktree": "/tmp/wt", "status": "working"}]}
        agents = [{"name": "", "cwd": "/tmp/wt", "pane_id": "w9:p1", "agent_status": "working"}]
        verdicts, rc = scan.scan(doc, agents)
        self.assertEqual(rc, 0)
        self.assertEqual(verdicts[0]["verdict"], "LIVE")

    def test_transcript_quota_verdict(self):
        with tempfile.TemporaryDirectory() as d:
            doc = {"workers": [{"name": "w1", "worktree": "/tmp/wt", "status": "working"}]}
            agents = [{"name": "", "cwd": "/tmp/wt", "pane_id": "p", "agent_status": "working"}]
            # write a transcript whose tail contains a 429 marker
            lines = ["{\"type\": \"message\", \"message\": {\"role\": \"user\"}}"] * 3
            lines.append("{\"type\":\"message\",\"message\":{\"role\":\"assistant\",\"content\":\"429 rate limit\"}}")
            p = os.path.join(d, "sess.jsonl")
            with open(p, "w") as f:
                f.write("\n".join(lines) + "\n")
            verdicts, rc = scan.scan(doc, agents, transcript_dir=d)
            self.assertEqual(verdicts[0]["verdict"], "QUOTA")
            self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()