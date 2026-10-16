#!/usr/bin/env python3
"""#720/#719: build absorbs migrate as migration mode; build body split into flat references."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from catalog import _frontmatter, _scalar_value  # noqa: E402
from check_skill_best_practices import has_contents  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "skills/build"
REFS = BUILD / "references"
MIGRATION = REFS / "migration.md"

# Migrate mechanics that must survive verbatim (phased plan, compat verification, kill criteria).
VERBATIM = (
    "**safe stopping point invariant**",
    "| 1 | Introduce new version | Feature | Add new dependency alongside old |",
    "| 3a-3N | Migrate consumer waves | Refactor | Update consumers wave-by-wave |",
    "| 5 | Remove old version | Refactor | Delete old dependency |",
    "### Legacy Migration Patterns",
    "5. **Kill the old system explicitly**",
    "**Kill Criteria:** [from evaluator — when to abort this migration approach]",
    "a. Both old and new API paths respond correctly (if coexistence phase)",
    "b. Compatibility layer tests pass (if shim exists)",
    "**Between-phase gate:** Full test suite must pass before proceeding to the next phase.",
    "**Removal criteria** -- when each shim can be safely deleted",
    "explicit `mode: standard` (or caller-requested `full`)",
)


def body(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    end = lines.index("---", 1)
    return lines[end + 1:]


class BuildSplit(unittest.TestCase):
    def test_body_at_most_500_lines(self):
        self.assertLessEqual(len(body(BUILD / "SKILL.md")), 500)

    def test_references_flat_listed_and_contented(self):
        text = (BUILD / "SKILL.md").read_text(encoding="utf-8")
        refs = sorted(REFS.glob("*.md"))
        self.assertTrue(refs)
        self.assertFalse([p for p in REFS.rglob("*") if p.is_dir()], "references/ must be flat")
        for ref in refs:
            self.assertIn(f"](references/{ref.name})", text, f"{ref.name} not linked from SKILL.md")
            if len(ref.read_text(encoding="utf-8").splitlines()) > 100:
                self.assertTrue(has_contents(ref.read_text(encoding="utf-8")), f"{ref.name} lacks contents list")

    def test_migration_mechanics_verbatim(self):
        text = MIGRATION.read_text(encoding="utf-8")
        for needle in VERBATIM:
            self.assertIn(needle, text)
        for prompt in ("migration-analyzer", "blast-radius-mapper", "phase-planner",
                       "compatibility-designer", "wave-grouper"):
            self.assertTrue((BUILD / f"{prompt}-prompt.md").is_file(), prompt)

    def test_description_routes_migration_triggers(self):
        fm = _frontmatter((BUILD / "SKILL.md").read_text(encoding="utf-8"))
        desc = _scalar_value(fm, "description")
        for trigger in ("migration plan", "upgrade X from Y to Z", "remove deprecated", "major version bump"):
            self.assertIn(trigger, desc)
        self.assertLessEqual(len(desc), 1024)

    def test_migrate_skill_gone_and_unreferenced(self):
        self.assertFalse((ROOT / "skills/migrate").exists())
        tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                                 check=True).stdout.split()
        stale = re.compile(r"crucible:migrate|skills/migrate/|`/migrate`|\(/migrate\b")
        skip = ("docs/plans/", "docs/research/", "CHANGELOG.md", "scripts/test_build_split.py")
        hits = [f for f in tracked if not f.startswith(skip) and (ROOT / f).is_file()
                and stale.search((ROOT / f).read_text(encoding="utf-8", errors="ignore"))]
        self.assertEqual(hits, [])

    def test_selection_evals_route_migration_to_build(self):
        evals = json.loads((ROOT / "skills/skill-selection-evals/evals/evals.json").read_text())["evals"]
        migration = [e for e in evals if e["id"].startswith("build-migration-")]
        self.assertGreaterEqual(len(migration), 4)
        for case in evals:
            if case["expected_skill"] == "build":
                self.assertNotIn("build", case["common_mistakes"], case["id"])


if __name__ == "__main__":
    unittest.main()
