#!/usr/bin/env python3
"""Assertion fixtures for CI guards; marker strings are assembled, never literal."""
import subprocess
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import check_conflict_markers
import check_machine_paths
import check_scorecard_freshness


def main() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        machine = root / "machine.md"
        machine.write_text("safe\n" + "/home/" + "rickr/private\n" + "/Users" + "/person/work\n" + "C:" + "\\" + "person\\work\n")
        assert check_machine_paths.offenders(root, ["machine.md"]) == [
            "machine.md:2: machine-specific absolute path",
            "machine.md:3: machine-specific absolute path",
            "machine.md:4: machine-specific absolute path"]
        machine.write_text("/home/user/work\n")
        assert not check_machine_paths.offenders(root, ["machine.md"])
        example = root / "skills" / "worktree" / "SKILL.md"
        example.parent.mkdir(parents=True)
        example.write_text("filler\n" * 188 + "Worktree ready at /Users" + "/jesse/myproject/.worktrees/auth\n")
        assert not check_machine_paths.offenders(root, ["skills/worktree/SKILL.md"])
        example.write_text("filler\n" * 188 + "Worktree ready at /Users" + "/actual/private\n")
        assert check_machine_paths.offenders(root, ["skills/worktree/SKILL.md"])
        (root / "notes.md").write_text("clean\n" + "<" * 7 + " HEAD\n" + "=" * 7 + "\n" + ">" * 7 + " branch\n")
        (root / "binary.png").write_text("<" * 7 + " HEAD\n")
        assert check_conflict_markers.offenders(root, ["notes.md", "binary.png"]) == [
            "notes.md:2", "notes.md:3", "notes.md:4"]
        assert not check_conflict_markers.offenders(root, ["binary.png"])
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "add", "notes.md"], cwd=root, check=True)
        output = StringIO()
        with patch.object(check_conflict_markers, "ROOT", root), redirect_stdout(output):
            assert check_conflict_markers.main() == 1
        assert output.getvalue().splitlines() == [f"- notes.md:{n}: unresolved conflict marker" for n in (2, 3, 4)]

        docs = root / "docs"
        docs.mkdir()
        report = docs / "skill-practices-audit.md"
        report.write_text("current\n")
        assert check_scorecard_freshness.diff_report(report, "current\n") == ""
        assert check_scorecard_freshness.diff_report(report, "stale\n")
    print("CI gap self-test OK")


if __name__ == "__main__":
    main()
