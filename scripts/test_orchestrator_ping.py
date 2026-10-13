#!/usr/bin/env python3
"""Tests orchestrator_ping.py — safe, bounded worker status pings."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts import orchestrator_ping as ping  # noqa: E402


class PingTest(unittest.TestCase):
    def test_only_settled_agents_are_promptable(self):
        self.assertTrue(ping.promptable("idle"))
        self.assertTrue(ping.promptable("done"))
        for status in ("working", "blocked", "unknown", None):
            with self.subTest(status=status):
                self.assertFalse(ping.promptable(status))

    def test_prompt_requests_one_short_status_line(self):
        self.assertLessEqual(len(ping.PROMPT.split()), 14)
        self.assertIn("STATUS=", ping.PROMPT)
        self.assertIn("NEXT=", ping.PROMPT)

    def test_default_selects_nonterminal_workers_only(self):
        workers = [
            {"name": "active", "status": "working"},
            {"name": "idle", "status": "idle"},
            {"name": "blocked", "status": "blocked"},
            {"name": "done", "status": "done"},
        ]
        self.assertEqual([w["name"] for w in ping.select_workers(workers)], ["active", "idle", "blocked", "done"])

    def test_explicit_selection_rejects_unknown_name(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            ping.select_workers([{"name": "known"}], ["missing"])

    def test_extracts_only_status_line(self):
        self.assertEqual(ping.status_line("thinking\nSTATUS=done NEXT=tests pass\n"),
                         "STATUS=done NEXT=tests pass")


if __name__ == "__main__":
    unittest.main()
