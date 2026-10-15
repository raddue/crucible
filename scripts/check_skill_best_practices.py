#!/usr/bin/env python3
"""Warn-only, per-skill practices audit (#719). No enforcement or baseline yet."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from catalog import _scalar_value

ROOT = Path(__file__).resolve().parent.parent
EXCLUDED = {"shared", "skill-selection-evals"}
COLUMNS = ("Body", "Contents", "Nesting", "Frontmatter", "Scripts")
# Canonical markers declare references; inline-code path mentions do not.
LINK = re.compile(r"<!--\s*CANONICAL:\s*([^\s>]+\.md)(?:\s+[^>]*?)?\s*-->|\]\(([^)\s]+\.md)(?:#[^)]*)?\)")
SCRIPT_STEP = re.compile(r"\b(?:python3?|bash|sh)\s+(?:\S+/)?(?:scripts|hooks)/\S+|\./(?:scripts|hooks)/\S+")
SETUP = re.compile(r"\b(?:requires?|dependencies|prerequisites?|setup|install|stdlib|built-in|no install|python 3)\b", re.I)
WHEN = re.compile(r"\b(?:when|whenever|use for|used for|triggers? on|for tasks? (?:that|involving))\b", re.I)
PERSONAL = re.compile(r"\b(?:you|your|we|our|i|my)\b", re.I)


def references(text: str, source: Path, root: Path) -> set[Path]:
    """Resolve existing local .md links, including repo-root skills/ paths."""
    found = set()
    for match in LINK.finditer(text):
        raw = next(group for group in match.groups() if group is not None)
        if raw.startswith(("http:", "https:")) or any(c in raw for c in " <>*{}$"):
            continue
        raw = raw.split("#", 1)[0]
        if raw.startswith("skills/"):
            target = root / raw
        elif raw.startswith("shared/"):
            target = root / "skills" / raw
        else:
            target = source.parent / raw
        target = target.resolve()
        if target.is_relative_to(root.resolve()) and target.is_file() and target.name != "SKILL.md":
            found.add(target)
    return found


def has_contents(text: str) -> bool:
    lines = text.splitlines()
    top = lines[:20]
    start = next((i for i, line in enumerate(top) if re.match(
        r"^(?:#{1,6}\s+|\*\*)(?:table of )?contents\b", line, re.I)), None)
    if start is None:
        return False
    section = []
    for line in top[start + 1:]:
        if re.match(r"^#{1,6}\s+", line):
            break
        section.append(line)
    anchors = {re.sub(r"[^\w -]", "", match.group(1).lower()).replace(" ", "-")
               for line in lines for match in [re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)] if match}
    entries = [match.group(1) for line in section
               for match in [re.match(r"^\s*[-*+]\s+\[[^]]+\]\(#([^)]+)\)", line)] if match]
    plain = [match.group(1) for line in section
             for match in [re.match(r"^\s*(?:[-*+]|\d+[.)])\s+(.+?)\s*$", line)] if match]
    plain = [re.sub(r"^\[([^]]+)\]\(#[^)]+\)$", r"\1", item) for item in plain]
    prose = [line.strip() for line in section if line.strip() and not re.match(
        r"^\s*(?:[-*+]|\d+[.)])\s+", line)]
    return (bool(entries) and all(anchor in anchors for anchor in entries)
            or bool(plain) and all(re.sub(r"[^\w -]", "", item.lower()).replace(" ", "-") in anchors
                                   for item in plain)
            or any(any(word in line.lower() for word in anchor.split("-"))
                   for line in prose for anchor in anchors - {"contents", "table-of-contents"}))


def read_markdown(path: Path, problems: list[str]) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except (UnicodeError, OSError) as exc:
        problems.append(f"{path.name}: cannot read UTF-8 Markdown ({type(exc).__name__})")
        return ""


def audit(root: Path = ROOT) -> dict[str, dict[str, list[str]]]:
    result = {}
    for skill in sorted((root / "skills").glob("*/SKILL.md")):
        name = skill.parent.name
        if name in EXCLUDED or name.startswith("temper-eval-"):
            continue
        problems = {column: [] for column in COLUMNS}
        lines = read_markdown(skill, problems["Frontmatter"]).splitlines()
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None) if lines and lines[0].strip() == "---" else None
        if end is None:
            problems["Frontmatter"].append("missing or unclosed frontmatter")
            body, fm = lines, []
        else:
            fm, body = lines[1:end], lines[end + 1:]
        if len(body) > 500:
            problems["Body"].append(f"{len(body)} body lines (max 500)")
        declared = _scalar_value(fm, "name")
        description = _scalar_value(fm, "description").strip()
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", declared) or len(declared) > 64:
            problems["Frontmatter"].append("name must be <=64 lowercase letters/digits/hyphens")
        if not description or len(description) > 1024:
            problems["Frontmatter"].append("description must be non-empty and <=1024 characters")
        if description and PERSONAL.search(description):
            problems["Frontmatter"].append("description should use third-person, not first/second-person voice")
        if description and not WHEN.search(description):
            problems["Frontmatter"].append("description lacks when-to-use signal")

        direct = references("\n".join(body), skill, root)
        nested = set()
        read_refs = {}
        for ref in sorted(direct):
            text = read_markdown(ref, problems["Contents"])
            read_refs[ref] = text
            for child in sorted(references(text, ref, root) - direct - {ref}):
                nested.add(child)
                problems["Nesting"].append(f"{ref.relative_to(root)} -> {child.relative_to(root)} not linked directly")
        for ref in sorted(direct | nested):
            text = read_refs.get(ref)
            if text is None:
                text = read_markdown(ref, problems["Contents"])
            if len(text.splitlines()) > 100 and not has_contents(text):
                problems["Contents"].append(f"{ref.relative_to(root)}: >100 lines, no contents list in first 20")
        for index, line in enumerate(body):
            if SCRIPT_STEP.search(line) and not SETUP.search("\n".join(body[max(0, index - 5):index + 1])):
                problems["Scripts"].append(f"SKILL.md:{end + index + 2 if end is not None else index + 1}: script step lacks nearby dependency/setup note (heuristic)")
        result[name] = problems
    return result


def render(results: dict[str, dict[str, list[str]]]) -> str:
    header = "# Skill practices audit\n\nWarn-only snapshot for #719; violations do not fail CI. Refresh with `python3 scripts/check_skill_best_practices.py --write-report`; the default check-only run never updates this file. Scripts column is a best-effort dependency-note heuristic. Later `--enforce` can compare per-skill failures against a ratchet baseline; no baseline or enforcement exists yet.\n\n"
    rows = ["| Skill | Body | Contents | Nesting | Frontmatter | Scripts | Overall |",
            "| --- | --- | --- | --- | --- | --- | --- |"]
    for name, checks in results.items():
        cells = ["FAIL" if checks[column] else "PASS" for column in COLUMNS]
        rows.append(f"| {name} | " + " | ".join(cells + ["PASS" if all(c == "PASS" for c in cells) else "FAIL"]) + " |")
    totals = [sum(not checks[column] for checks in results.values()) for column in COLUMNS]
    clean = sum(all(not issues for issues in checks.values()) for checks in results.values())
    rows.append(f"| TOTAL | " + " | ".join(f"{count}/{len(results)}" for count in totals) + f" | {clean}/{len(results)} |")
    details = [f"\n## Violations ({sum(len(items) for checks in results.values() for items in checks.values())})\n"]
    for name, checks in results.items():
        for column in COLUMNS:
            if checks[column]:
                examples = "; ".join(checks[column][:3]).replace("|", "\\|")
                suffix = f"; … and {len(checks[column]) - 3} more" if len(checks[column]) > 3 else ""
                details.append(f"- `{name}` {column} ({len(checks[column])}): {examples}{suffix}")
    return header + "\n".join(rows + details) + "\n"


def main(root: Path = ROOT, write_report: bool = False) -> int:
    results = audit(root)
    report = root / "docs" / "skill-practices-audit.md"
    if write_report:
        report.parent.mkdir(parents=True, exist_ok=True)
        content = render(results)
        if not report.exists() or report.read_text(encoding="utf-8") != content:
            report.write_text(content, encoding="utf-8")
    print(f"Skill practices audit: {len(results)} skills; {sum(all(not x for x in checks.values()) for checks in results.values())} clean; warn-only")
    for name, checks in results.items():
        for column in COLUMNS:
            for item in checks[column]:
                print(f"WARN {name} {column}: {item}")
    if write_report:
        print(f"Scorecard: {report.relative_to(root)}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-report", action="store_true", help="update docs/skill-practices-audit.md")
    raise SystemExit(main(write_report=parser.parse_args().write_report))
