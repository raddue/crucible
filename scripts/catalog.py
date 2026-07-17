#!/usr/bin/env python3
"""Generated skill-catalog contract for `docs/skills.md` (#364).

Invocation (from repo root):
    python3 scripts/catalog.py check     # read-only CI gate (exit 1 on drift)
    python3 scripts/catalog.py render    # rewrite docs/skills.md + count tokens

`check` validates that the catalog rows between the
`<!-- CATALOG:START -->` / `<!-- CATALOG:END -->` markers in `docs/skills.md`
are in bijection with the `name:` frontmatter of every `skills/*/SKILL.md`
(no omission, no bogus row, no naming mismatch), that every on-disk skill is in
`CATEGORIES` (and every `CATEGORIES` entry has a SKILL.md), and that every
registered count token (README, workshop, plugin.json) equals the runtime skill
count `n = len(parse_skill_names(root))`. The expected count is ALWAYS derived
at runtime — never a literal — so the tool cannot reintroduce the stale-count
bug it exists to retire.

`render` rewrites only between the CATALOG markers (regenerated headings +
tables in `CATEGORIES` order, preserving curated descriptions and intra-section
intro prose) plus the registered count-token sites.

Style mirrors `scripts/check_canonical_drift.py`: ROOT-from-`__file__`, error
accumulation, `sys.exit(main())`, stdlib only (no yaml, no argparse, no pytest).
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Ordered category -> ordered skill names. Every name MUST map to a real
# skills/<name>/SKILL.md, and every on-disk skill MUST appear here (bijection
# enforced by check()'s uncategorized + dangling-category guards).
CATEGORIES: dict[str, list[str]] = {
    "Core Pipeline": [
        "build", "spec", "design", "planning", "recon", "replay", "assay",
    ],
    "Implementation": [
        "test-driven-development", "source-driven-development", "checkpoint",
        "worktree", "parallel", "adversarial-tester", "inquisitor", "migrate",
    ],
    "Quality & Audit": [
        "delve", "audit", "siege", "consensus", "prospector", "quality-gate",
        "red-team", "test-coverage", "temper", "review-feedback", "verify",
        "finish", "innovate", "dependency-audit",
    ],
    "Debugging": [
        "debugging",
    ],
    "Knowledge & Learning": [
        "forge", "project-init", "grudge", "compass",
    ],
    "Utilities": [
        "distill", "recall",
    ],
    "Maintenance & Meta": [
        "stocktake", "merge-pr", "skill-creator", "getting-started", "handoff",
        "ledger", "calibration-reconcile", "workshop",
    ],
    "Unity UI (Domain-Specific)": [
        "mockup-builder", "mock-to-unity", "ui-verify",
    ],
    "Eval & Maintenance (internal)": [
        "cartographer-skill", "temper-eval-collect", "temper-eval-calibrate",
        "skill-selection-evals",
    ],
}

START = "<!-- CATALOG:START -->"
END = "<!-- CATALOG:END -->"

# Count-token surfaces. Expected value is ALWAYS runtime n — no literal stored.
# Generic grammar requires a non-`skills` separator-or-nothing so an eval-claim
# phrase ("N core skills") with an interposed word is NOT captured.
#
# DISCIPLINE (deliberate, gate-accepted; NOT a sentinel scheme): the grammar
# matches ANY "N skills" / "N agent skills" phrase in a registered count-target
# file, not a fenced sentinel — because plugin.json's published JSON description
# string cannot carry a sentinel comment. So each registered count-target file
# below must contain ONLY the catalog-total "N skills" / "N agent skills" token;
# any OTHER count phrase added to these files MUST keep an interposed non-`skills`
# word (e.g. "13 core skills") so the grammar does not capture it as the total.
_GENERIC = re.compile(r"(~?)(\d+)([ -])(skills?)\b")
_PLUGIN = re.compile(r"(\d+)( agent skills?)\b")
COUNT_TARGETS: list[tuple[str, re.Pattern[str]]] = [
    ("README.md", _GENERIC),
    ("skills/workshop/SKILL.md", _GENERIC),
    (".claude-plugin/plugin.json", _PLUGIN),
]


# --------------------------------------------------------------------------
# Frontmatter parsing
# --------------------------------------------------------------------------
def _frontmatter(text: str) -> list[str]:
    """Return the lines of the first `---`-fenced YAML block (exclusive)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    out: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            return out
        out.append(line)
    return []


def _scalar_value(fm: list[str], key: str) -> str:
    """Read a YAML scalar `key:` from frontmatter lines, handling the three
    live forms: plain (rest of line), double-quoted (strip quotes), and folded
    block (`>` then indented continuation lines joined with single spaces)."""
    prefix = f"{key}:"
    for i, line in enumerate(fm):
        if not line.startswith(prefix):
            continue
        rest = line[len(prefix):].strip()
        if rest in (">", "|", ">-", "|-", ">+", "|+"):
            # Folded/literal block: gather indented continuation lines until the
            # next top-level key (non-indented, non-blank) or end of block.
            cont: list[str] = []
            for nxt in fm[i + 1:]:
                if nxt.strip() == "":
                    if cont:
                        break
                    continue
                if not nxt.startswith((" ", "\t")):
                    break
                cont.append(nxt.strip())
            return " ".join(cont)
        if len(rest) >= 2 and rest[0] == '"' and rest[-1] == '"':
            return rest[1:-1]
        if len(rest) >= 2 and rest[0] == "'" and rest[-1] == "'":
            return rest[1:-1]
        return rest
    return ""


def parse_skill_names(root: pathlib.Path = ROOT) -> set[str]:
    """Read each skills/*/SKILL.md, extract the `name:` frontmatter scalar."""
    names: set[str] = set()
    for skill_md in sorted((root / "skills").glob("*/SKILL.md")):
        fm = _frontmatter(skill_md.read_text(encoding="utf-8"))
        name = _scalar_value(fm, "name")
        if name:
            names.add(name)
    return names


def _frontmatter_descriptions(root: pathlib.Path) -> dict[str, str]:
    """name -> frontmatter description scalar, for all on-disk skills."""
    out: dict[str, str] = {}
    for skill_md in sorted((root / "skills").glob("*/SKILL.md")):
        fm = _frontmatter(skill_md.read_text(encoding="utf-8"))
        name = _scalar_value(fm, "name")
        if name:
            out[name] = _scalar_value(fm, "description")
    return out


# --------------------------------------------------------------------------
# Catalog row parsing (between the markers)
# --------------------------------------------------------------------------
_ROW_NAME = re.compile(r"^\|\s*\*\*([^*]+)\*\*\s*\|")


def _catalog_region(text: str) -> str | None:
    """Return the substring strictly between START and END, or None."""
    si = text.find(START)
    ei = text.find(END)
    if si == -1 or ei == -1 or ei < si:
        return None
    return text[si + len(START):ei]


def _parse_row(line: str) -> tuple[str, str] | None:
    """A catalog row: first non-pipe cell is `**name**`. Returns (name, desc)
    using the first `|` after the name cell as the delimiter and the last ` |`
    as the terminator (so an embedded `` `a | b` `` stays one cell). Skips
    separator and header rows."""
    m = _ROW_NAME.match(line)
    if not m:
        return None
    name = m.group(1).strip()
    # Description is between the delimiter pipe (right after the name cell) and
    # the last ` |` terminator on the line.
    delim = line.index("|", m.end() - 1)
    last = line.rstrip().rfind(" |")
    if last <= delim:
        return None
    desc = line[delim + 1:last].strip()
    return name, desc


def _parse_rows(region: str) -> "dict[str, str]":
    """name -> existing description, for every catalog row in the region."""
    rows: dict[str, str] = {}
    for line in region.splitlines():
        parsed = _parse_row(line)
        if parsed:
            rows[parsed[0]] = parsed[1]
    return rows


# --------------------------------------------------------------------------
# check
# --------------------------------------------------------------------------
def check(root: pathlib.Path = ROOT) -> list[str]:
    errs: list[str] = []
    disk = parse_skill_names(root)
    n = len(disk)

    categorized: set[str] = set()
    for skills in CATEGORIES.values():
        categorized.update(skills)

    # (6) dangling category: a CATEGORIES entry with no SKILL.md on disk.
    for cat, skills in CATEGORIES.items():
        for name in skills:
            if name not in disk:
                errs.append(
                    f"- category entry `{name}` (in `{cat}`) has no SKILL.md on disk")

    # (4) uncategorized: an on-disk skill absent from CATEGORIES.
    for name in sorted(disk):
        if name not in categorized:
            errs.append(
                f"- skill `{name}` is uncategorized — add it to CATEGORIES")

    # (8) no-name guard + duplicate-name guard: in one pass over the on-disk
    # SKILL.md files, flag any whose `name:` does not parse (silently dropped
    # from disk/n by parse_skill_names — surfacing only as mysterious count
    # drift) AND accumulate name -> [reldir, ...] so two dirs declaring the SAME
    # name (which dedupe in the parse_skill_names set, undercounting n and making
    # the second dir invisible to every other guard) can be flagged explicitly.
    by_name: dict[str, list[str]] = {}
    for skill_md in sorted((root / "skills").glob("*/SKILL.md")):
        fm = _frontmatter(skill_md.read_text(encoding="utf-8"))
        rel = skill_md.relative_to(root).as_posix()
        name = _scalar_value(fm, "name")
        if not name:
            errs.append(f"- {rel} has no parseable name: frontmatter")
            continue
        by_name.setdefault(name, []).append(rel)
    for name, rels in sorted(by_name.items()):
        if len(rels) > 1:
            errs.append(
                f"- duplicate skill name `{name}` declared by "
                + " and ".join(rels))

    # (7) count-target path existence + (5) count drift (every match == n, and
    # ≥1 match per target). These are doc-INDEPENDENT (they read README /
    # workshop / plugin.json against runtime n, never the catalog region), so
    # they run BEFORE the missing-doc early return — a missing docs/skills.md
    # must not mask a co-occurring count drift.
    for relpath, regex in COUNT_TARGETS:
        path = root / relpath
        if not path.is_file():
            errs.append(f"- registered count target `{relpath}` not found")
            continue
        content = path.read_text(encoding="utf-8")
        matches = list(regex.finditer(content))
        if not matches:
            errs.append(
                f"- registered count target `{relpath}` matched no count token "
                "— grammar drift?")
            continue
        for mt in matches:
            digits = mt.group(2) if regex is _GENERIC else mt.group(1)
            if int(digits) != n:
                errs.append(
                    f"- count drift in `{relpath}`: token `{mt.group(0)}` "
                    f"!= runtime skill count {n}")

    # (9) missing doc: only the catalog-region-dependent checks (the bijection:
    # omission/bogus/naming) need docs/skills.md, so a missing doc short-circuits
    # ONLY those — the doc-independent bullets above have already accrued. Get a
    # graceful bullet (symmetry with the count-target path-existence handling),
    # not an uncaught FileNotFoundError.
    doc = root / "docs" / "skills.md"
    if not doc.is_file():
        errs.append("- docs/skills.md not found")
        return errs

    # Catalog rows between the markers.
    text = doc.read_text(encoding="utf-8")
    region = _catalog_region(text)
    if region is None:
        errs.append("- CATALOG markers not found in docs/skills.md")
        return errs
    rows = _parse_rows(region)

    # (2) bogus + (3) naming: a row whose name has no matching SKILL.md.
    for name in sorted(rows):
        if name not in disk:
            errs.append(
                f"- catalog row `{name}` is bogus — no skills/{name}/SKILL.md "
                "(naming mismatch or stale entry)")

    # (1) omission: an on-disk skill with no catalog row.
    for name in sorted(disk):
        if name not in rows:
            errs.append(
                f"- skill `{name}` is omitted — no catalog row between the markers")

    return errs


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------
def _rewrite_counts(root: pathlib.Path, n: int) -> None:
    """Rewrite every COUNT_TARGETS token's digits to n (in-place substring edit;
    preserves `~`/separator; no JSON re-serialization)."""
    for relpath, regex in COUNT_TARGETS:
        path = root / relpath
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        if regex is _GENERIC:
            new = regex.sub(lambda m: f"{m.group(1)}{n}{m.group(3)}{m.group(4)}", content)
        else:
            new = regex.sub(lambda m: f"{n}{m.group(2)}", content)
        if new != content:
            path.write_text(new, encoding="utf-8")


def _section_intros(region: str) -> dict[str, str]:
    """category -> VERBATIM intra-section intro prose between a `## Category`
    heading and its table, or absent when there is none.

    Captures the exact text from after the heading up to (but not including) the
    first table line (lstrip starts with `|`) or the next `## ` heading, then
    strips leading/trailing blank lines while PRESERVING interior blank lines —
    so a two-paragraph intro survives render byte-for-byte (a previous
    non-blank-only join silently fused multi-paragraph intros into one block)."""
    intros: dict[str, str] = {}
    lines = region.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("## "):
            cat = line[3:].strip()
            j = i + 1
            block: list[str] = []
            while j < len(lines):
                cur = lines[j]
                if cur.startswith("## "):
                    break
                if cur.lstrip().startswith("|"):
                    break
                block.append(cur)
                j += 1
            # Strip leading/trailing blank lines; keep interior blanks verbatim.
            while block and not block[0].strip():
                block.pop(0)
            while block and not block[-1].strip():
                block.pop()
            if block:
                intros[cat] = "\n".join(block)
            i = j
            continue
        i += 1
    return intros


def render(root: pathlib.Path = ROOT) -> None:
    doc = root / "docs" / "skills.md"
    if not doc.is_file():
        raise SystemExit("docs/skills.md not found")
    text = doc.read_text(encoding="utf-8")
    si = text.find(START)
    ei = text.find(END)
    if si == -1 or ei == -1 or ei < si:
        raise SystemExit("CATALOG markers not found in docs/skills.md")

    region = text[si + len(START):ei]
    existing = _parse_rows(region)
    intros = _section_intros(region)
    seeds = _frontmatter_descriptions(root)
    disk = parse_skill_names(root)
    n = len(disk)

    out: list[str] = [""]  # blank line after START marker
    for cat, skills in CATEGORIES.items():
        out.append(f"## {cat}")
        out.append("")
        if cat in intros:
            out.append(intros[cat])
            out.append("")
        out.append("| Skill | Description |")
        out.append("|---|---|")
        for name in skills:
            if name not in disk:
                continue
            desc = existing.get(name) or seeds.get(name, "")
            out.append(f"| **{name}** | {desc} |")
        out.append("")

    new_region = "\n".join(out) + "\n"
    new_text = text[:si + len(START)] + new_region + text[ei:]
    if new_text != text:
        doc.write_text(new_text, encoding="utf-8")

    _rewrite_counts(root, n)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main() -> int:
    if len(sys.argv) < 2:
        print("usage: catalog.py {check|render}", file=sys.stderr)
        return 2
    cmd = sys.argv[1]
    if cmd == "check":
        errs = check()
        if errs:
            print("CATALOG DRIFT DETECTED:")
            for e in errs:
                print(e)
            return 1
        print("OK — skill catalog is in bijection with frontmatter; counts match.")
        return 0
    if cmd == "render":
        render()
        print("Rendered docs/skills.md + count tokens.")
        return 0
    print(f"usage: catalog.py {{check|render}} (unknown command: {cmd!r})",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
