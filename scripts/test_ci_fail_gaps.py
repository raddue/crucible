#!/usr/bin/env python3
"""Assertion fixtures for CI guards; marker strings are assembled, never literal."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import check_conflict_markers
import check_evals_consistency
import check_scorecard_freshness


def main() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "notes.md").write_text("clean\n" + "<" * 7 + " HEAD\n" + "=" * 7 + "\n" + ">" * 7 + " branch\n")
        (root / "binary.png").write_text("<" * 7 + " HEAD\n")
        assert check_conflict_markers.offenders(root, ["notes.md", "binary.png"]) == [
            "notes.md:2", "notes.md:3", "notes.md:4"]
        assert not check_conflict_markers.offenders(root, ["binary.png"])

        skill = root / "skills" / "good"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("# Good\n")
        (root / "skills" / "shared").mkdir()
        cases = root / "skills" / "selection" / "evals"
        cases.mkdir(parents=True)
        file = cases / "evals.json"
        file.write_text(json.dumps({"evals": [
            {"id": "ok", "expected_skill": ["good"], "common_mistakes": ["other"]},
            {"id": "contradiction", "expected_skill": "good", "common_mistakes": ["good"]},
            {"id": "unknown", "expected_skill": "absent", "common_mistakes": []},
            {"id": "directory-only", "expected_skill": "shared", "common_mistakes": []},
        ]}))
        errors = check_evals_consistency.check(root)
        assert len(errors) == 3 and any("contradiction" in e for e in errors) and any("unknown" in e for e in errors)
        assert any("directory-only" in e for e in errors)
        file.write_text(json.dumps({"evals": [{"expected_skill": ["good"], "common_mistakes": []}]}))
        assert not check_evals_consistency.check(root)

        docs = root / "docs"
        docs.mkdir()
        report = docs / "skill-practices-audit.md"
        report.write_text("current\n")
        assert check_scorecard_freshness.diff_report(report, "current\n") == ""
        assert check_scorecard_freshness.diff_report(report, "stale\n")
    print("CI gap self-test OK")


if __name__ == "__main__":
    main()
