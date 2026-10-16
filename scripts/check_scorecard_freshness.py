#!/usr/bin/env python3
"""Compare regenerated skill-practices scorecard with committed snapshot."""
import difflib
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent.parent
MESSAGE = "run scripts/check_skill_best_practices.py --write-report and commit"


def diff_report(committed: Path, generated: str) -> str:
    return "".join(difflib.unified_diff(
        committed.read_text(encoding="utf-8").splitlines(keepends=True),
        generated.splitlines(keepends=True),
        fromfile=str(committed), tofile="regenerated scorecard"))


def main() -> int:
    with TemporaryDirectory() as tmp:
        target = Path(tmp) / "skill-practices-audit.md"
        subprocess.run(["python3", str(ROOT / "scripts/check_skill_best_practices.py"),
                        "--write-report", "--report-path", str(target)], cwd=ROOT, check=True,
                       stdout=subprocess.DEVNULL)
        diff = diff_report(ROOT / "docs/skill-practices-audit.md", target.read_text(encoding="utf-8"))
    if diff:
        print(diff)
        print(MESSAGE)
        return 1
    print("OK — skill practices scorecard fresh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
