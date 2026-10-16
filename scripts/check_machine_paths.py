#!/usr/bin/env python3
"""Reject machine-specific absolute paths in tracked text files."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Historical, fictional examples; exemption requires exact path, line, and text.
EXAMPLES = {
    ("skills/worktree/SKILL.md", 189): "Worktree ready at /Users" + "/jesse/myproject/.worktrees/auth",
    ("skills/debugging/root-cause-tracing.md", 36): "Error: git init failed in /Users" + "/jesse/project/packages/core",
    ("skills/getting-started/handoff.md", 112): None,  # /home/user generic template, outside narrow matcher.
    ("skills/getting-started/forge.md", 167): "   Example: `/home/alice/projects/myapp/src/auth.py` becomes `~/projects/myapp/src/auth.py`",
    ("eval/memory/test_memory.py", 67): '        samples = ["/home/alice/file", "https://example.com", "AKIA1234567890123456", "abc@example.com", "4111111111111111", "+1 (555) 123-4567"]',
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
            if line != EXAMPLES.get((name, number)) and PATH.search(line):
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
