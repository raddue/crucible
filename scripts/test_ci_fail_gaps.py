#!/usr/bin/env python3
"""Assertion fixtures for CI guards; marker strings are assembled, never literal."""
import json
import subprocess
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import check_conflict_markers
import check_evals_consistency
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
        for listing in (b"", b"\xff"):
            output = StringIO()
            with (patch.object(check_machine_paths, "ROOT", root),
                  patch.object(check_machine_paths.subprocess, "check_output", return_value=listing),
                  redirect_stdout(output)):
                assert check_machine_paths.main() == 1
            assert output.getvalue().startswith("- git ls-files")
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
        output = StringIO()
        with patch.object(check_evals_consistency, "ROOT", root), redirect_stdout(output):
            assert check_evals_consistency.main() == 1
        assert output.getvalue().splitlines() == [f"- {error}" for error in errors]
        file.write_text(json.dumps({"evals": [{"expected_skill": ["good"], "common_mistakes": []}]}))
        assert not check_evals_consistency.check(root)

        docs = root / "docs"
        docs.mkdir()
        report = docs / "skill-practices-audit.md"
        report.write_text("current\n")
        assert check_scorecard_freshness.diff_report(report, "current\n") == ""
        assert check_scorecard_freshness.diff_report(report, "stale\n")
        output = StringIO()
        with (patch.object(check_scorecard_freshness, "ROOT", root),
              patch.object(check_scorecard_freshness.subprocess, "run", side_effect=subprocess.CalledProcessError(1, ["checker"])),
              redirect_stdout(output)):
            assert check_scorecard_freshness.main() == 1
        assert output.getvalue().splitlines() == ["- scorecard generation failed: checker exited with status 1"]
    print("CI gap self-test OK")


if __name__ == "__main__":
    main()
