#!/usr/bin/env python3
"""Tests for compass.py PARSER / PATCH / RENDER core (#408 F16a).

Before this file only the lock state machine (test_locks.py) exercised compass;
the parse → validate → patch → render pipeline that actually maintains
docs/compass.md was entirely untested. These are pure-stdlib unittest cases
(run as `python3 scripts/test_compass.py`, registered in run_tests.sh)."""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts import compass as cm  # noqa: E402


class ParseRenderRoundTripTest(unittest.TestCase):
    def _state(self, **over):
        s = {
            "current_arc": "#42: do the thing",
            "last_meaningful_commit": "abc123: base commit",
            "updated": "2026-06-29T10:00",
            "open_loops": ["loop one", "loop two"],
            "next_move": "ship it",
            "dont_forget": ["remember this"],
        }
        s.update(over)
        return s

    def test_render_parse_is_identity(self):
        s = self._state()
        parsed = cm._parse(cm._render(s))
        self.assertEqual(parsed, s)

    def test_render_parse_identity_empty_lists(self):
        s = self._state(open_loops=[], dont_forget=[], next_move="")
        self.assertEqual(cm._parse(cm._render(s)), s)

    def test_multiline_next_move_round_trips(self):
        s = self._state(next_move="line a\nline b\nline c")
        self.assertEqual(cm._parse(cm._render(s))["next_move"],
                         "line a\nline b\nline c")


class ParseStrictnessTest(unittest.TestCase):
    BASE = ("# Compass\n\n**Current arc:** #1: x\n"
            "**Last meaningful commit:** s: c\n**Updated:** 2026-06-29T10:00\n\n"
            "## Open loops\n\n## Next move\n\n## Don't forget\n")

    def test_missing_compass_header_raises(self):
        with self.assertRaises(ValueError):
            cm._parse("not a compass\n")

    def test_missing_required_header_raises(self):
        bad = self.BASE.replace("**Updated:** 2026-06-29T10:00\n", "")
        with self.assertRaises(ValueError):
            cm._parse(bad)

    def test_wrong_bullet_char_in_open_loops_raises(self):
        bad = self.BASE.replace("## Open loops\n\n", "## Open loops\n* nope\n")
        with self.assertRaises(ValueError):
            cm._parse(bad)

    def test_stray_content_in_header_block_raises(self):
        bad = self.BASE.replace(
            "**Current arc:** #1: x\n",
            "**Current arc:** #1: x\nstray line here\n")
        with self.assertRaises(ValueError):
            cm._parse(bad)

    def test_duplicate_section_raises(self):
        bad = self.BASE + "## Open loops\n"
        with self.assertRaises(ValueError):
            cm._parse(bad)


class ValidateCapTest(unittest.TestCase):
    def _render_state(self, **over):
        s = {
            "current_arc": "#1: x", "last_meaningful_commit": "s: c",
            "updated": "2026-06-29T10:00", "open_loops": [],
            "next_move": "", "dont_forget": [],
        }
        s.update(over)
        return cm._render(s)

    def test_over_line_cap_raises_compass_full(self):
        # A long multi-line next_move (paragraph field) pushes past MAX_LINES
        # without tripping the open_loops cap first.
        nm = "\n".join(f"para line {i}" for i in range(cm.MAX_LINES + 5))
        with self.assertRaises(cm.CompassFullError):
            cm._validate(self._render_state(next_move=nm))

    def test_open_loops_hard_cap_raises(self):
        loops = [f"loop {i}" for i in range(cm.MAX_OPEN_LOOPS_HARD + 1)]
        with self.assertRaises(cm.OpenLoopsCapError):
            cm._validate(self._render_state(open_loops=loops))

    def test_dont_forget_cap_raises_valueerror(self):
        df = [f"df {i}" for i in range(cm.MAX_DONT_FORGET + 1)]
        with self.assertRaises(ValueError):
            cm._validate(self._render_state(dont_forget=df))


class ValidateValueTest(unittest.TestCase):
    def test_current_arc_grammar_enforced(self):
        with self.assertRaises(ValueError):
            cm._validate_value("current_arc", "no ticket prefix")
        cm._validate_value("current_arc", "#7: ok")          # no raise
        cm._validate_value("current_arc", "")                # closure, allowed

    def test_control_chars_rejected(self):
        with self.assertRaises(ValueError):
            cm._validate_value("open_loops", "has\ttab")
        with self.assertRaises(ValueError):
            cm._validate_value("dont_forget", "has\nnewline")
        # next_move legitimately allows newline
        cm._validate_value("next_move", "para\nline")        # no raise

    def test_last_meaningful_commit_grammar(self):
        with self.assertRaises(ValueError):
            cm._validate_value("last_meaningful_commit", "no-colon-here")
        cm._validate_value("last_meaningful_commit", "sha: subject")  # ok


class ApplyPatchTest(unittest.TestCase):
    def _state(self):
        return cm._bootstrap_state()

    def test_unknown_field_raises(self):
        with self.assertRaises(ValueError):
            cm._apply_patch(self._state(), "bogus", "x", False, [])

    def test_append_on_scalar_raises(self):
        with self.assertRaises(ValueError):
            cm._apply_patch(self._state(), "next_move", "x", True, [])

    def test_scalar_set_and_noop(self):
        s = self._state()
        self.assertTrue(cm._apply_patch(s, "next_move", "go", False, []))
        self.assertEqual(s["next_move"], "go")
        # idempotent re-set returns False (no change)
        self.assertFalse(cm._apply_patch(s, "next_move", "go", False, []))

    def test_list_append_dedups(self):
        s = self._state()
        self.assertTrue(cm._apply_patch(s, "open_loops", "L1", True, []))
        self.assertFalse(cm._apply_patch(s, "open_loops", "L1", True, []))  # dup
        self.assertEqual(s["open_loops"], ["L1"])

    def test_list_replacement(self):
        s = self._state()
        s["open_loops"] = ["old"]
        self.assertTrue(cm._apply_patch(s, "open_loops", ["a", "b"], False, []))
        self.assertEqual(s["open_loops"], ["a", "b"])

    def test_current_arc_set(self):
        s = self._state()
        self.assertTrue(cm._apply_patch(s, "current_arc", "#9: new arc", False, []))
        self.assertEqual(s["current_arc"], "#9: new arc")


class ApplyCurrentArcTest(unittest.TestCase):
    """_apply_current_arc branch coverage (M1/M2): arc closure (Step 3),
    collision push (Step 6), and resume removal (Step 1). Only the <pending>
    bootstrap (Step 4) was previously exercised."""

    def _state(self, **over):
        s = cm._bootstrap_state()
        s.update(over)
        return s

    def test_closure_clears_arc(self):
        # Step 3: empty new_value clears the live arc.
        s = self._state(current_arc="#1: a")
        adv = []
        self.assertTrue(cm._apply_current_arc(s, "", adv))
        self.assertEqual(s["current_arc"], "")

    def test_collision_push_pauses_prior_arc(self):
        # Step 6: setting a new arc over a live arc pushes the prior arc onto
        # open_loops as a [paused] entry and emits an [OPEN] advisory.
        s = self._state(current_arc="#1: old", open_loops=[])
        adv = []
        self.assertTrue(cm._apply_current_arc(s, "#2: new", adv))
        self.assertEqual(s["current_arc"], "#2: new")
        self.assertEqual(len(s["open_loops"]), 1)
        # timestamp is non-deterministic -> startswith, not exact.
        self.assertTrue(s["open_loops"][0].startswith("[paused] #1: old @ "),
                        s["open_loops"][0])
        self.assertTrue(
            any(e.startswith("[OPEN]") and "moved to open_loops" in e
                for e in adv), adv)

    def test_resume_removes_paused_entry(self):
        # Step 1: setting an arc whose ticket id matches a [paused] #<id>: entry
        # removes that entry and emits a [RESUME] advisory. The paused entry must
        # match PAUSED_LINE_RE (the @ <ISO-timestamp> suffix is required).
        s = self._state(
            current_arc="<pending>",
            open_loops=["[paused] #7: prior @ 2026-06-01T10:00:00"])
        adv = []
        self.assertTrue(cm._apply_current_arc(s, "#7: resumed", adv))  # changed
        self.assertEqual(s["open_loops"], [])
        self.assertTrue(any(e.startswith("[RESUME]") for e in adv), adv)


class PublicRoundTripTest(unittest.TestCase):
    """read / update_many against a real temp compass.md."""

    def test_update_many_then_read(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "compass.md")
            # current_arc + open_loops are a mutex pair in one atomic update,
            # so split across two calls.
            cm.update_many([
                ("current_arc", "#5: arc", False),
                ("next_move", "do x", False),
            ], path=path)
            cm.update_many([("open_loops", "loop a", True)], path=path)
            # read() returns file text; _parse gives the state (also proves the
            # on-disk file re-parses cleanly — render/parse identity held).
            state = cm._parse(cm.read(path=path))
            self.assertEqual(state["current_arc"], "#5: arc")
            self.assertEqual(state["next_move"], "do x")
            self.assertIn("loop a", state["open_loops"])
            # compact form renders the live arc + next move (not the parse-error
            # fallback, and not a wrong-but-non-empty string)
            compact = cm.read(path=path, compact=True)
            self.assertIn("[ARC] #5: arc", compact)
            self.assertIn("[NEXT] do x", compact)


if __name__ == "__main__":
    unittest.main()
