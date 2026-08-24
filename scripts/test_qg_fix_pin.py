#!/usr/bin/env python3
"""Regression pin for `agents/crucible-qg-fix.md`'s model tier (#537).

Nothing in the tracked suite previously asserted the fix agent's `model:`
frontmatter value — a silent revert to `model: inherit` (the pre-#537 state)
passed the full suite. This test reads the agent def and line-scans for the
`model:` key between the YAML frontmatter fences, matching this repo's own
lightweight-parsing convention (see `check_model_pins.py`'s frontmatter
scanner) rather than adding a YAML dependency."""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
AGENT_DEF = os.path.join(REPO_ROOT, "agents", "crucible-qg-fix.md")

MODEL_RE = re.compile(r"^model:\s*(\S+)\s*$")


def _frontmatter_model(path: str) -> str | None:
    """Line-scan for `model:` strictly between the first two `---` fences."""
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    fence_indices = [i for i, line in enumerate(lines) if line.strip() == "---"]
    if len(fence_indices) < 2:
        return None
    start, end = fence_indices[0], fence_indices[1]
    for line in lines[start + 1:end]:
        m = MODEL_RE.match(line)
        if m:
            return m.group(1)
    return None


class QgFixModelPinTest(unittest.TestCase):
    def test_model_pin_is_sonnet(self):
        model = _frontmatter_model(AGENT_DEF)
        self.assertEqual(
            model, "sonnet",
            "agents/crucible-qg-fix.md's `model:` frontmatter must stay "
            "pinned to sonnet (#537) — a revert to `inherit` (or omitting "
            "the key) silently re-degrades the fix agent to the "
            "orchestrator's session model.")


if __name__ == "__main__":
    unittest.main()
