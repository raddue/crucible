#!/usr/bin/env python3
"""Tests for scripts/pipeline_status.py — the ambient status writer.

Pure stdlib unittest. Run: python3 scripts/test_pipeline_status.py
"""

import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, REPO_ROOT)

from scripts import pipeline_status as ps  # noqa: E402


class Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)
        self.__dict__.setdefault("event", [])
        self.__dict__.setdefault("suggested_action", None)
        self.__dict__.setdefault("body_file", None)
        self.__dict__.setdefault("path", None)


def read_field(path, name):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = re.search(rf"^\*\*{name}:\*\*\s*(.+?)\s*$", text, re.M)
    return m.group(1) if m else None


def read_events(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return re.findall(r"^- \[(\d{2}:\d{2})\] (.*)$", text, re.M)


class PipelineStatusTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "pipeline-status.md")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_write_fresh_green_omits_suggested(self):
        self.assertEqual(ps.cmd_write(Args(path=self.path, skill="build", phase="1 — Design", health="GREEN")), 0)
        with open(self.path, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("# Pipeline Status", text)
        self.assertIn("**Health:** GREEN", text)
        self.assertNotIn("**Suggested Action:**", text)
        self.assertEqual(read_field(self.path, "Skill"), "build")

    def test_suggested_present_on_red(self):
        self.assertEqual(ps.cmd_write(Args(path=self.path, skill="build", phase="3", health="RED", suggested_action="escalate to user")), 0)
        self.assertIsNotNone(read_field(self.path, "Suggested Action"))

    def test_started_persists(self):
        ps.cmd_write(Args(path=self.path, skill="build", phase="1", health="GREEN"))
        s1 = read_field(self.path, "Started")
        ps.cmd_write(Args(path=self.path, skill="build", phase="2", health="GREEN"))
        s2 = read_field(self.path, "Started")
        self.assertEqual(s1, s2)

    def test_events_keep_last_5_newest_first(self):
        ps.cmd_write(Args(path=self.path, skill="build", phase="1", health="GREEN", event=["a", "b", "c"]))
        ps.cmd_write(Args(path=self.path, skill="build", phase="1", health="GREEN", event=["d", "e", "f"]))
        evs = read_events(self.path)
        texts = [t for _, t in evs]
        self.assertEqual(len(evs), 5)
        # newest first: f, e, d, then only 2 of a/b/c survive
        self.assertEqual(texts[0], "f")
        self.assertEqual(texts[1], "e")
        self.assertEqual(texts[2], "d")

    def test_health_backward_within_phase_refused(self):
        ps.cmd_write(Args(path=self.path, skill="build", phase="3", health="YELLOW"))
        self.assertEqual(ps.cmd_write(Args(path=self.path, skill="build", phase="3", health="GREEN")), 1)

    def test_health_forward_within_phase_ok(self):
        ps.cmd_write(Args(path=self.path, skill="build", phase="3", health="YELLOW"))
        self.assertEqual(ps.cmd_write(Args(path=self.path, skill="build", phase="3", health="RED")), 0)

    def test_phase_change_resets_health(self):
        ps.cmd_write(Args(path=self.path, skill="build", phase="3", health="RED"))
        self.assertEqual(ps.cmd_write(Args(path=self.path, skill="build", phase="4", health="GREEN")), 0)

    def test_phase_change_immediate_escalation_allowed(self):
        # reset sets the baseline to GREEN in the new phase, so YELLOW/RED on the
        # first write is a forward move, not a backward one
        ps.cmd_write(Args(path=self.path, skill="build", phase="3", health="RED"))
        self.assertEqual(ps.cmd_write(Args(path=self.path, skill="build", phase="4", health="RED")), 0)

    def test_body_file_included(self):
        body = os.path.join(self.tmp, "body.md")
        with open(body, "w", encoding="utf-8") as f:
            f.write("## Task Progress\n| 1 | x |\n")
        ps.cmd_write(Args(path=self.path, skill="build", phase="3", health="GREEN", body_file=body))
        with open(self.path, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("## Task Progress", text)

    def test_skill_body_bullets_not_swept_into_events(self):
        body = os.path.join(self.tmp, "body.md")
        with open(body, "w", encoding="utf-8") as f:
            f.write("## Compression State\nGoal: x\n- [12:00] not an event\n")
        ps.cmd_write(Args(path=self.path, skill="build", phase="3", health="GREEN", body_file=body))
        st = ps.read_status(self.path)
        self.assertEqual(len(st["events"]), 0)  # body bullet must NOT become history
        self.assertIn("## Compression State", st["skill_body"])

    def test_compact_no_file(self):
        self.assertEqual(ps.cmd_compact(Args(path=self.path)), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)