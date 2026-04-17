#!/usr/bin/env python3
"""
Reconcile `### Noticed But Not Touching` sections from multiple implementer
reports into a single docs/plans/<date>-<slug>-noticed.md artifact.

Implements the 7-step reconciliation process from
docs/plans/2026-04-16-noticed-but-not-touching-implementation-plan.md §T2.

Contract tag: contract:integration:inv-4
"""
from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import re
import sys
from typing import List, Tuple


NONE_MARKER = "*(none)*"
SECTION_HEADER_RE = re.compile(r"^###\s+Noticed But Not Touching\s*$", re.MULTILINE)
ENTRY_RE = re.compile(
    r"-\s+\*\*file:\*\*\s+`(?P<path>.+?):(?P<range>L\d+-L\d+)`\s*\n"
    r"\s+\*\*noticed:\*\*\s+(?P<noticed>[^\n]+)\n"
    r"\s+\*\*why it matters:\*\*\s+(?P<why>[^\n]+)"
    r"(?:\n\s+\*\*suggested follow-up:\*\*\s+(?P<follow>[^\n]+))?"
    r"(?=\n\s*-\s+\*\*file:\*\*|\n\s*###|\n\s*\n|\Z)",
)


def extract_section(report_text: str) -> str | None:
    """Return the body of the ### Noticed But Not Touching section, or None."""
    m = SECTION_HEADER_RE.search(report_text)
    if not m:
        return None
    start = m.end()
    # body ends at next ### heading OR end of string
    rest = report_text[start:]
    next_h = re.search(r"\n###\s+\S", rest)
    body = rest[: next_h.start()] if next_h else rest
    return body.strip()


def parse_entries(body: str) -> List[dict]:
    """Parse entries from a section body. Returns [] if body is *(none)* or empty."""
    if not body or body.strip() == NONE_MARKER:
        return []
    entries = []
    for m in ENTRY_RE.finditer(body):
        entries.append(
            {
                "file_path": m.group("path").strip(),
                "line_range": m.group("range").strip(),
                "noticed": m.group("noticed").strip(),
                "why": m.group("why").strip(),
                "follow": (m.group("follow") or "").strip(),
            }
        )
    return entries


def dedupe_key(entry: dict) -> str:
    """Canonical Constants dedupe key: sha256(normalize(path) + | + range + | + noticed[:40])."""
    norm_path = entry["file_path"].replace("\\", "/").lower()
    raw = f"{norm_path}|{entry['line_range']}|{entry['noticed'][:40]}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def line_range_sort_key(entry: dict) -> Tuple[str, int, int]:
    m = re.match(r"L(\d+)-L(\d+)", entry["line_range"])
    if not m:
        return (entry["file_path"], 0, 0)
    return (entry["file_path"], int(m.group(1)), int(m.group(2)))


def render_file(
    entries: List[dict], pipeline_id: str, date: str, ticket: str, slug: str
) -> str:
    lines = [
        "---",
        f'pipeline_id: "{pipeline_id}"',
        f'date: "{date}"',
        f'ticket: "{ticket}"',
        "---",
        "",
        f"# Noticed But Not Touching — {slug}",
        "",
    ]
    for e in entries:
        lines.append(f"- **file:** `{e['file_path']}:{e['line_range']}`")
        lines.append(f"  **noticed:** {e['noticed']}")
        lines.append(f"  **why it matters:** {e['why']}")
        if e["follow"]:
            lines.append(f"  **suggested follow-up:** {e['follow']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_existing(path: pathlib.Path) -> List[dict]:
    """Read an existing -noticed.md and extract entries for idempotent merge."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    # Strip frontmatter
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4 :]
    return parse_entries(text)


def reconcile(
    reports: List[str],
    out_path: pathlib.Path,
    pipeline_id: str,
    date: str,
    ticket: str,
    slug: str,
) -> int:
    all_entries: List[dict] = []
    for r in reports:
        body = extract_section(r)
        if body is None:
            continue
        all_entries.extend(parse_entries(body))
    # Step 6: idempotent overwrite — merge with on-disk
    all_entries.extend(parse_existing(out_path))

    seen = {}
    for e in all_entries:
        k = dedupe_key(e)
        if k not in seen:
            seen[k] = e
    entries = sorted(seen.values(), key=line_range_sort_key)

    if not entries:
        return 0

    content = render_file(entries, pipeline_id, date, ticket, slug)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    return len(entries)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True, help="output -noticed.md path")
    p.add_argument("--pipeline-id", required=True)
    p.add_argument("--date", required=True)
    p.add_argument("--ticket", required=True)
    p.add_argument("--slug", required=True)
    p.add_argument("reports", nargs="*", help="implementer report files; stdin if empty")
    args = p.parse_args()

    if args.reports:
        reports = [pathlib.Path(r).read_text(encoding="utf-8") for r in args.reports]
    else:
        reports = [sys.stdin.read()]

    n = reconcile(
        reports,
        pathlib.Path(args.out),
        args.pipeline_id,
        args.date,
        args.ticket,
        args.slug,
    )
    print(f"reconciled {n} entries -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
