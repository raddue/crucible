#!/usr/bin/env python3
"""I2 invariant check: engine-dispatch marker allowlist (Review-Trio Reshape, #336).

Invocation (from repo root):
    python3 scripts/check_i2_marker.py

The canonical engine-dispatch marker is a column-0 body line in the two DIRECT
dispatchers of the shared engine -- the `/delve` skill and `temper`. (The marker
phrase is written split/reworded throughout this script so the script can never
itself become a stray match; it only ever scans `*.md` files, never `*.py`.)
`audit` reaches the engine only transitively via the `/delve` skill, so it carries
the shorter SKILL marker (no `-engine` suffix) and is deliberately out of scope.

The check is ANCHORED (column-0 only, mirroring `grep -rn '^dispatch: delve-engine'`)
and a SET EQUALITY: the set of `*.md` files containing such a line must EQUAL
exactly {skills/delve/SKILL.md, skills/temper/SKILL.md}. A stray third dispatcher
(extra file) OR a missing expected file both FAIL -- presence of the two expected
matches alone is not sufficient. Prose mentions elsewhere (changelog, workshop,
this milestone's own docs) stay safe by writing the marker inline /
backtick-wrapped / reworded, never as the first characters of a line.

Why the longer `-engine` anchor: the shorter `^dispatch: delve` prefix also matches
audit's skill-marker line, so that prefix set is {audit, delve, temper}. Only the
`-engine` anchor isolates the engine set {delve, temper}.

Exits 0 if the set matches exactly, 1 with a delta summary otherwise. Stdlib only.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKIP_DIRS = {"node_modules", ".git"}

# Anchored at line start. Built from fragments so this source file is not itself
# a column-0 occurrence of the phrase.
MARKER = re.compile(r"^dispatch: " + "delve-engine")

EXPECTED = {
    "skills/delve/SKILL.md",
    "skills/temper/SKILL.md",
}


def iter_markdown(root: pathlib.Path):
    for path in root.rglob("*.md"):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        yield path


def files_with_engine_marker(root: pathlib.Path) -> set[str]:
    found: set[str] = set()
    for path in iter_markdown(root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            if MARKER.match(line):
                found.add(path.relative_to(root).as_posix())
                break
    return found


def main() -> int:
    found = files_with_engine_marker(ROOT)
    extra = sorted(found - EXPECTED)
    missing = sorted(EXPECTED - found)

    if extra or missing:
        print("I2 MARKER ALLOWLIST VIOLATION:")
        if extra:
            print(
                "  - Unexpected column-0 engine-dispatch marker in: "
                + ", ".join(extra)
            )
            print(
                "    Only the two DIRECT engine dispatchers (delve, temper) may carry it."
            )
            print(
                "    Reference the marker only inline / backtick-wrapped / reworded,"
                " never as a column-0 line."
            )
        if missing:
            print(
                "  - Expected engine dispatcher(s) MISSING the column-0 marker: "
                + ", ".join(missing)
            )
        return 1

    print("OK -- column-0 engine-dispatch marker set equals exactly {delve, temper}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
