#!/usr/bin/env python3
"""Reject unresolved merge markers in tracked text files."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXTENSIONS = {".md", ".py", ".sh", ".json", ".yaml", ".yml"}
MARKER = re.compile(r"^(?:<{7} |={7}$|>{7} )")


def offenders(root: Path, files: list[str]) -> list[str]:
    found = []
    for name in files:
        path = root / name
        if path.suffix not in EXTENSIONS or not path.is_file():
            continue
        try:
            for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if MARKER.match(line):
                    found.append(f"{name}:{line_no}")
        except UnicodeError:
            continue  # A tracked binary blob with a text extension is not text.
    return found


def main() -> int:
    files = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().strip("\0").split("\0")
    found = offenders(ROOT, files)
    if found:
        print("\n".join(f"- {entry}: unresolved conflict marker" for entry in found))
        return 1
    print("OK — no tracked conflict markers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
