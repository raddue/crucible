#!/usr/bin/env python3
"""Deterministic comment-position verification (#628).

Review skills (delve-engine, temper) emit `{file, line, summary}` findings whose
`file:line` refs come straight from the LLM — with no check that the cited line
actually matches the claimed code. A drifted position silently degrades trust and
wastes triage. This gate runs BEFORE a finding reaches the user and re-derives
the position deterministically against the tree:

  - every `{file, line}` ref must resolve to a real file and an existing
    line number (or `lo-hi` range) inside the working tree;
  - the finding's `summary` is parsed for quoted/code symbols; symbols that
    occur anywhere in the cited file are the "referenced symbols", and at
    least one of them must occur on the cited line (within an optional
    `--window` of lines) — otherwise the position is drifted and the finding is
    REJECTED;
  - if NO parsed symbol occurs in the file at all (a pure-prose comment, or a
    removed-code reference whose symbol is gone), the ref degrades to
    provenance-only: VERIFIED if the line exists, never a hard REJECT — a
    removed-behavior finding legitimately names code that no longer exists.

Exit code: 0 if every ref is VERIFIED, 1 if any ref is REJECTED, 2 on usage
error. Pure stdlib, no third-party deps; deterministic on a fixed tree.

Invocation:
    python3 scripts/verify_comment_positions.py [--root DIR] [--window N] refs.json
    python3 scripts/verify_comment_positions.py --selftest

`refs.json` is a JSON list of records, each with at least `file` and `line`;
`summary` (optional) supplies the referenced symbols. Any other fields are
ignored, so the engine's eight-field records pass straight through.
"""
import argparse
import json
import os
import re
import sys

_QUOTED_RE = re.compile(r"([`\"'])(.{1,200}?)\1")
_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_.]*"
                            r"|[A-Za-z_][A-Za-z0-9_]*")


def _code_like(tok: str) -> bool:
    """A token looks code-bearable if it carries a nontrivial code shape:
    an uppercase letter (camelCase/SCREAMING), a dot (dotted ident), an
    underscore, or a digit. Lowercase single prose words (`reader`, `check`,
    `token`) are excluded — they flood summaries and would trigger false
    drift rejects when one casually appears elsewhere in the file (#628)."""
    return any(c.isupper() or c in "._" or c.isdigit() for c in tok)


def extract_symbols(summary: str) -> list:
    """Code symbols a summary references, in priority order. Quoted/backticked
    spans first — the author's explicit code claims (`claims.expiresAt`, `<`,
    `<=`) — then bare code-like identifiers (`token.exp`). Lowercase prose
    words are never authoritative symbols. Returns [] for prose-only summaries,
    which is the provenance-only degrade signal the gate relies on."""
    symbols = []
    seen = set()

    def _add(s):
        if s and s not in seen:
            seen.add(s)
            symbols.append(s)

    if summary:
        for m in _QUOTED_RE.finditer(summary):
            quoted = m.group(2).strip()
            if quoted:
                _add(quoted)
                for ident in _IDENTIFIER_RE.findall(quoted):
                    if _code_like(ident):
                        _add(ident)
        for ident in _IDENTIFIER_RE.findall(summary):
            if _code_like(ident):
                _add(ident)
    return symbols


def _parse_line_ref(line):
    """Normalize a line ref: int, 'N', or 'lo-hi' → (lo, hi). None if malformed."""
    if isinstance(line, int):
        lo = hi = line
        return (lo, hi) if lo >= 1 else None
    if isinstance(line, str):
        line = line.strip()
    else:
        return None
    m = re.fullmatch(r"(\d+)(?:-(\d+))?", line)
    if not m:
        return None
    lo = int(m.group(1))
    hi = int(m.group(2)) if m.group(2) else lo
    if lo < 1 or hi < lo:
        return None
    return (lo, hi)


def resolve_path(root, file):
    """Repo-relative `file` resolved inside `root`; None if missing or escaping."""
    joined = os.path.abspath(os.path.join(root, file.lstrip("/")))
    root_abs = os.path.abspath(root)
    if os.path.commonpath([joined, root_abs]) != root_abs:
        return None
    return joined if os.path.isfile(joined) else None


def _line_window_text(lines, lo, hi, window):
    """The text of lines [lo, hi], widened by `window` lines on both sides."""
    start = max(lo - window - 1, 0)
    end = min(hi - 1 + window, len(lines) - 1)
    return "\n".join(lines[start:end + 1])


def verify_record(record, root, window=0):
    """Verify a single finding ref. Returns (status, reason).

    status is one of:
      VERIFIED  — line exists and (a referenced symbol is on it, or the summary
                  carries no symbol present in the file → provenance-only);
      REJECTED  — file/line unresolvable, or a referenced symbol is present in
                  the file but not on the cited line (position drift).
    """
    file = record.get("file", "")
    if not file:
        return ("REJECTED", "record has no file")
    path = resolve_path(root, file)
    if not path:
        return ("REJECTED", f"{file!r} does not resolve inside root")
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError as exc:
        return ("REJECTED", f"{file!r} unreadable: {exc}")
    line_ref = _parse_line_ref(record.get("line"))
    if not line_ref:
        return ("REJECTED", f"{file!r} line ref malformed: {record.get('line')!r}")
    lo, hi = line_ref
    if hi > len(lines):
        return ("REJECTED", f"{file}:{lo}-{hi} past EOF ({len(lines)} lines)")
    cited = _line_window_text(lines, lo, hi, window)
    symbols = extract_symbols(record.get("summary", ""))
    referenced = [s for s in symbols if s in "\n".join(lines)]
    if not referenced:
        return ("VERIFIED", f"{file}:{lo}-{hi} provenance-only "
                            f"(no cited symbol present in file)")
    if any(s in cited for s in referenced):
        return ("VERIFIED", f"{file}:{lo}-{hi} symbol on line")
    return ("REJECTED", f"{file}:{lo}-{hi} drift: referenced symbol(s) "
                        f"{sorted(set(referenced))} not on that line")


def verify_records(records, root, window=0):
    outcomes = []
    for rec in records:
        status, reason = verify_record(rec, root, window=window)
        outcomes.append((rec, status, reason))
    return outcomes


def _selftest() -> int:
    import tempfile
    root = tempfile.mkdtemp(prefix="verify_cp_st_")
    with open(os.path.join(root, "a.py"), "w", encoding="utf-8") as f:
        f.write("# place\nL1\nL2 L3\n")
    cases = [
        ({"file": "a.py", "line": 3, "summary": "`L2` `L3`"}, "VERIFIED"),
        ({"file": "a.py", "line": 1, "summary": "`L2`"}, "REJECTED"),
        ({"file": "missing.py", "line": 1, "summary": "x"}, "REJECTED"),
        ({"file": "a.py", "line": "1-99", "summary": "x"}, "REJECTED"),
        ({"file": "a.py", "line": 2, "summary": "remove the whole check"},
         "VERIFIED"),
    ]
    failures = []
    for rec, want in cases:
        status, _ = verify_record(rec, root)
        if status != want:
            failures.append(f"{rec} → {status}, want {want}")
    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print(f"  {f}")
        return 1
    print("SELFTEST OK")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic comment-position verification (#628).")
    parser.add_argument("refs", nargs="?", help="JSON list of {file, line, ...} "
                                               "record(s); '-' reads stdin")
    parser.add_argument("--root", default=os.getcwd(),
                        help="repo root the file refs resolve against")
    parser.add_argument("--window", type=int, default=0,
                        help="lines of tolerance around the cited line")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()
    if not args.refs:
        parser.error("refs JSON path (or '-') is required")

    try:
        if args.refs == "-":
            records = json.loads(sys.stdin.read())
        else:
            with open(args.refs, encoding="utf-8") as f:
                records = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error reading refs: {exc}", file=sys.stderr)
        return 2
    if not isinstance(records, list):
        records = [records]

    results = verify_records(records, args.root, window=args.window)
    rejected = 0
    for rec, status, reason in results:
        print(f"{status}  {rec.get('file', '?')}:{rec.get('line', '?')}  {reason}")
        if status == "REJECTED":
            rejected += 1
    return 1 if rejected else 0


if __name__ == "__main__":
    sys.exit(main())