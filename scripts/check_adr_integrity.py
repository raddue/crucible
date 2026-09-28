#!/usr/bin/env python3
"""ADR corpus integrity checker for `docs/decisions/` (#552).

Invocation (from repo root):
    python3 scripts/check_adr_integrity.py             # check the tracked corpus
    python3 scripts/check_adr_integrity.py --selftest  # built-in logic tests

Enforces design invariants I1-I10 over every `docs/decisions/*.md`, plus the
cross-file `<!-- CONTRACT:adr-falsification-home -->` anchor in
`skills/recon/SKILL.md` (the falsification-home pin, per
`scripts/CHECKER_CONVENTIONS.md` §1's cross-file-doctrine rule). Stdlib only.

Graceful absence: when `docs/decisions/` is absent, exits 0 (printing
`no docs/decisions/ — 0 ADRs checked`) only when I9 holds — no ADR-shaped file
exists under any of D2's other known locations. A corpus living *elsewhere*
without `docs/decisions/` is a second scheme, and fails.

Exit 0 clean / 1 with a `path: message` list, matching house style.
"""
from __future__ import annotations

import datetime
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DECISIONS = ROOT / "docs" / "decisions"
OTHER_LOCS = [
    ROOT / "docs" / "adr",
    ROOT / "doc" / "adr",
    ROOT / "docs" / "architecture" / "decisions",
    ROOT / "adr",
]

FILENAME_RE = re.compile(r"^\d{4}-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
H1_RE = re.compile(r"^# ADR-(\d{4}): .+$")
REJECTED_RE = re.compile(r"^\s*[-*]?\s*Rejected:")
FALSIFY_RE = re.compile(
    r"^Recon claim falsified: L-\d+ from brief \S+ — .+$")
FALSIFY_LOOSE = re.compile(r"Recon claim falsified:")
SUPERSEDED_RE = re.compile(r"^SUPERSEDED by ADR-\d{4}$")
SUPERSEDES_RE = re.compile(r"^Supersedes ADR-\d{4}$")
RENUMBERED_RE = re.compile(r"^Renumbered-from ADR-\d{4}$")

SECTIONS = ["## Status", "## Date", "## Context", "## Decision",
            "## Alternatives Considered", "## Consequences"]

CONTRACT_ANCHOR = "CONTRACT:adr-falsification-home"


def _status_lines(text: str) -> list[str]:
    """Non-blank body lines of the `## Status` section (until next `## `)."""
    started = False
    out: list[str] = []
    for line in text.splitlines():
        if line.startswith("## ") and not started:
            started = (line.strip() == "## Status")
            continue
        if started:
            if line.startswith("## "):
                break
            if line.strip():
                out.append(line.strip())
    return out


def _section_text(text: str, heading: str) -> str:
    """Raw body text between `heading` and the next `## ` heading, or ""."""
    started = False
    out: list[str] = []
    for line in text.splitlines():
        if line.startswith("## ") and not started:
            started = (line.strip() == heading)
            continue
        if started:
            if line.startswith("## "):
                break
            out.append(line)
    return "\n".join(out)


def _h1_num(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("## "):
            break
        m = H1_RE.match(line.strip())
        if m:
            return m.group(1)
    return None


def check_one(rel: pathlib.Path, text: str, errs: list[str]) -> None:
    name = rel.name
    num = name[:4] if len(name) >= 4 and name[:4].isdigit() else ""

    # I1 filename
    if not FILENAME_RE.match(name):
        errs.append(f"- {rel}: filename does not match "
                    f"`\\d{{4}}-[a-z0-9-].md`")

    # I3 H1 number matches filename
    h1 = _h1_num(text)
    if h1 != num:
        errs.append(f"- {rel}: H1 `# ADR-{h1 or '?'}: …` does not match "
                    f"filename number {num or '?'}")

    # I4 sections present (subset)
    missing = [s for s in SECTIONS if s not in text]
    if missing:
        errs.append(f"- {rel}: missing section(s) {', '.join(missing)}")

    # I5 status token grammar
    status = _status_lines(text)
    if not status:
        errs.append(f"- {rel}: `## Status` has no state token")
    else:
        first = status[0]
        if not (first in ("PROPOSED", "ACCEPTED")
                or SUPERSEDED_RE.match(first)):
            errs.append(f"- {rel}: state token `{first}` is not PROPOSED / "
                        f"ACCEPTED / SUPERSEDED by ADR-NNNN")
        for extra in status[1:]:
            if not (SUPERSEDES_RE.match(extra) or RENUMBERED_RE.match(extra)):
                errs.append(f"- {rel}: illegal `## Status` line `{extra}`")

    # I7 date parses
    try:
        date_body = _section_text(text, "## Date").strip()
        datetime.date.fromisoformat(date_body.splitlines()[0].strip())
    except (ValueError, IndexError):
        errs.append(f"- {rel}: `## Date` does not parse as YYYY-MM-DD")

    # I8 falsification home + grammar: every `Recon claim falsified:` line must
    # sit under the trailing `## Falsifications` section and match grammar.
    in_falsify = False
    for i, line in enumerate(text.splitlines(), start=1):
        if line.startswith("## "):
            in_falsify = (line.strip() == "## Falsifications")
            continue
        if FALSIFY_LOOSE.search(line):
            if not in_falsify:
                errs.append(f"- {rel}:{i} `Recon claim falsified:` line outside "
                            f"`## Falsifications`")
            if not FALSIFY_RE.match(line.strip()):
                errs.append(f"- {rel}:{i} `Recon claim falsified:` line does "
                            f"not match canonical grammar")

    # I10 alternatives non-empty + Rejected:
    alt = _section_text(text, "## Alternatives Considered").strip()
    if not alt:
        errs.append(f"- {rel}: `## Alternatives Considered` is empty (I10)")
    elif not any(REJECTED_RE.match(l) for l in alt.splitlines()):
        errs.append(f"- {rel}: `## Alternatives Considered` has no `Rejected:` "
                    f"line (I10)")


def check(paths: list[pathlib.Path], errs: list[str]) -> None:
    # I2 duplicate numbers
    by_num: dict[str, list[str]] = {}
    for p in paths:
        num = p.name[:4]
        by_num.setdefault(num, []).append(p.relative_to(DECISIONS).as_posix())
    for num, rels in sorted(by_num.items()):
        if len(rels) > 1:
            errs.append(f"- I2: two files share number {num}: "
                        f"{', '.join(rels)}")

    # I6 supersede pointers resolve + mirror
    corpus = {p.name[:4]: p.name for p in paths}
    for p in paths:
        text = p.read_text(encoding="utf-8")
        for line in text.splitlines():
            m = SUPERSEDED_RE.match(line.strip())
            if m:
                target = m.group(1)
                if target not in corpus:
                    errs.append(f"- {p.name}: SUPERSEDED by ADR-{target} "
                                f"points at missing ADR")
                else:
                    other = DECISIONS / corpus[target]
                    otxt = other.read_text(encoding="utf-8")
                    need = f"Supersedes ADR-{p.name[:4]}"
                    if need not in otxt:
                        errs.append(f"- {p.name}: SUPERSEDED by ADR-{target} "
                                    f"has no mirroring `{need}` in "
                                    f"{corpus[target]}")


def main() -> int:
    errs: list[str] = []

    # I9 + graceful absence
    if not DECISIONS.is_dir():
        stray = [p for loc in OTHER_LOCS if loc.is_dir()
                 for p in sorted(loc.glob("*.md"))]
        if stray:
            errs.append("- I9: ADR-shaped files found outside `docs/decisions/`"
                        f": {', '.join(str(s) for s in stray)}")
            print("\n".join(errs))
            return 1
        print("no docs/decisions/ — 0 ADRs checked")
        return 0

    for loc in OTHER_LOCS:
        if loc.is_dir():
            for p in sorted(loc.glob("*.md")):
                errs.append(f"- I9: ADR-shaped file outside `docs/decisions/`: "
                            f"{p}")

    adr_files = sorted(DECISIONS.glob("*.md"))
    for p in adr_files:
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            errs.append(f"- {p.name}: unreadable")
            continue
        check_one(p.relative_to(ROOT), text, errs)
    check(adr_files, errs)

    # CONTRACT anchor (S4/M5 cross-file pin)
    recon = ROOT / "skills" / "recon" / "SKILL.md"
    if recon.is_file() and CONTRACT_ANCHOR not in recon.read_text(encoding="utf-8"):
        errs.append(f"- {recon.relative_to(ROOT)}: missing "
                    f"`<!-- {CONTRACT_ANCHOR} -->` anchor")

    if errs:
        print("\n".join(errs))
        return 1
    print(f"OK — {len(adr_files)} ADR(s) satisfy I1–I10; falsification home "
          f"pinned.")
    return 0


def selftest() -> int:
    failures: list[str] = []

    def ok(label: str, cond: bool) -> None:
        if not cond:
            failures.append(f"  {label}")

    ok("FILENAME_RE rejects non-kebab",
       not FILENAME_RE.match("0001-Foo.md"))
    ok("FILENAME_RE accepts kebab",
       bool(FILENAME_RE.match("0001-foo-bar.md")))
    _h1m = H1_RE.match("# ADR-0007: Do the thing")
    ok("H1_RE captures number", _h1m is not None and _h1m.group(1) == "0007")
    ok("REJECTED_RE matches bullet",
       bool(REJECTED_RE.match("- Rejected: x")))
    ok("REJECTED_RE matches plain", bool(REJECTED_RE.match("Rejected: x")))
    ok("SUPERSEDED_RE", bool(SUPERSEDED_RE.match("SUPERSEDED by ADR-0009")))
    ok("RENUMBERED_RE", bool(RENUMBERED_RE.match("Renumbered-from ADR-0001")))

    if failures:
        print("SELFTEST FAILED:")
        print("\n".join(failures))
        return 1
    print("SELFTEST OK — core regexes behave as specified.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    sys.exit(main())