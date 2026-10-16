#!/usr/bin/env python3
"""Reject machine-specific absolute paths in tracked text files."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Historical, fictional examples; each exemption is one exact path and line.
EXAMPLES = {
    ("skills/worktree/SKILL.md", 189),
    ("skills/debugging/root-cause-tracing.md", 36),
    ("skills/getting-started/handoff.md", 112),
    ("skills/getting-started/forge.md", 167),
    ("eval/memory/test_memory.py", 67),
}
PATH = re.compile(r"/home/" + "rickr|/Users" + r"/[A-Za-z0-9_]|C:\\[A-Za-z0-9_]{2,}")


def offenders(root: Path, files: list[str]) -> list[str]:
    errors = []
    for name in files:
        path = root / name
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeError:
            continue
        for number, line in enumerate(lines, 1):
            if (name, number) not in EXAMPLES and PATH.search(line):
                errors.append(f"{name}:{number}: machine-specific absolute path")
    return errors


def main() -> int:
    files = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().strip("\0").split("\0")
    errors = offenders(ROOT, files)
    if errors:
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("OK — no machine-specific paths")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
