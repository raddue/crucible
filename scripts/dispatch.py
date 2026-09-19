#!/usr/bin/env python3
"""dispatch.py — deterministic manifest.jsonl bookkeeping for disk-mediated dispatch.

Executable transcription of the mechanical pieces of
skills/shared/dispatch-convention.md: seq recovery (## File Naming),
record-before/record-after (## Dispatch Manifest), and cleanup (## Cleanup).

Invocation (from repo root; cwd-independent):

    dispatch.py seq        --dir <dispatch-dir>
    dispatch.py before     --dir <D> --seq N --file <dispatch-file> --role <r> \
                           [--phase P] [--task K] --model-tier <opus|sonnet|haiku>
    dispatch.py after      --dir <D> --seq N --status <completed|failed|error|skipped> \
                           [--summary ".."] [--output-chars C] [--tool-calls K] [--duration S]
    dispatch.py cleanup    --dir <D> --scratch <s> [--failed]

`before` measures the dispatch file's character count and appends the
`status:"dispatched"` entry. `after` appends the authoritative completion
entry for the same seq, copying the dispatched entry's context fields
(file/role/phase/task/model_tier/input_chars) so the last entry per seq is
self-sufficient — matching the convention's completed-entry example. Entries
are kept under POSIX PIPE_BUF (4096 bytes) by truncating `summary`, so a
single `write()` append stays atomic under concurrent access.

Deliberately NOT here: token/rework aggregation (`summary`) — forge owns that
aggregation (its ## Step 8.5 already hand-computes totals); a third
implementation would be a drift surface, not a win. Pure stdlib.
"""

import argparse
import json
import os
import shutil
import sys

PIPE_BUF = 4096
MANIFEST = "manifest.jsonl"
RECEIPT_LEDGER = "receipt-ledger.jsonl"

STATUSES = {"completed", "failed", "error", "skipped", "dispatched"}
TIERS = {"opus", "sonnet", "haiku"}


def _manifest_path(d):
    return os.path.join(d, MANIFEST)


def _read_manifest(dirpath):
    """Return list of parsed entries; tolerant of ragged final lines."""
    p = _manifest_path(dirpath)
    if not os.path.exists(p):
        return []
    rows = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _append(dirpath, entry):
    line = json.dumps(entry, separators=(",", ":"), ensure_ascii=False)
    if len(line) + 1 > PIPE_BUF:
        # shrink summary until the whole line fits PIPE_BUF
        fixed = dict(entry)
        fixed["summary"] = None
        overhead = len(json.dumps(fixed, separators=(",", ":"), ensure_ascii=False))
        budget = PIPE_BUF - 1 - overhead
        if entry.get("summary") is not None and budget > 0:
            s = entry["summary"]
            if len(s) > budget:
                # reserve 1 for the ellipsis
                s = s[: max(budget - 1, 0)] + "\u2026"
            entry["summary"] = s
            line = json.dumps(entry, separators=(",", ":"), ensure_ascii=False)
        if len(line) + 1 > PIPE_BUF:
            print(f"[dispatch WARN] entry for seq {entry.get('seq')} still exceeds "
                  f"PIPE_BUF after summary truncation; writing anyway", file=sys.stderr)
    with open(_manifest_path(dirpath), "a", encoding="utf-8") as f:
        f.write(line + "\n")


def cmd_seq(dirpath):
    rows = _read_manifest(dirpath)
    seqs = [int(r["seq"]) for r in rows if isinstance(r.get("seq"), int)]
    print(max(seqs) + 1 if seqs else 1)
    return 0


def cmd_before(args):
    fp = args.file
    try:
        with open(fp, encoding="utf-8") as f:
            input_chars = len(f.read())
    except OSError as e:
        print(f"dispatch before: cannot read dispatch file {fp}: {e}", file=sys.stderr)
        return 1
    if args.model_tier not in TIERS:
        print(f"dispatch before: model-tier must be one of {sorted(TIERS)}", file=sys.stderr)
        return 2
    entry = {
        "seq": args.seq,
        "file": os.path.basename(fp),
        "role": args.role,
        "phase": args.phase,
        "task": args.task,
        "status": "dispatched",
        "duration_s": None,
        "summary": None,
        "input_chars": input_chars,
        "output_chars": None,
        "model_tier": args.model_tier,
        "tool_calls": None,
    }
    _append(args.dir, entry)
    print(f"dispatched seq {args.seq} ({entry['file']}, {input_chars} chars)")
    return 0


def cmd_after(args):
    if args.status not in STATUSES - {"dispatched"}:
        print(f"dispatch after: status must be one of "
              f"{sorted(STATUSES - {'dispatched'})}", file=sys.stderr)
        return 2
    # copy context fields from the dispatched entry for this seq (last one wins)
    prev = None
    for r in _read_manifest(args.dir):
        if r.get("seq") == args.seq and r.get("status") == "dispatched":
            prev = r
    entry = {
        "seq": args.seq,
        "file": prev.get("file") if prev else f"{args.seq}-unknown.md",
        "role": prev.get("role") if prev else None,
        "phase": prev.get("phase") if prev else None,
        "task": prev.get("task") if prev else None,
        "status": args.status,
        "duration_s": args.duration,
        "summary": args.summary,
        "input_chars": prev.get("input_chars") if prev else None,
        "output_chars": args.output_chars,
        "model_tier": prev.get("model_tier") if prev else None,
        "tool_calls": args.tool_calls,
    }
    _append(args.dir, entry)
    print(f"{args.status} seq {args.seq} ({entry['file']})")
    return 0


def cmd_cleanup(args):
    dirpath = args.dir
    scratch = args.scratch
    if not os.path.isdir(dirpath):
        print(f"dispatch cleanup: dispatch dir missing: {dirpath}", file=sys.stderr)
        return 1
    if args.failed:
        # directory-into-directory, basename preserved -> lands at <scratch>/crucible-dispatch-<sid>/
        dst = os.path.join(scratch, os.path.basename(os.path.normpath(dirpath)))
        shutil.copytree(dirpath, dst, dirs_exist_ok=True)
        print(f"copied dispatch dir to {dst} (left /tmp in place)")
        return 0
    dest = os.path.join(scratch, os.path.basename(os.path.normpath(dirpath)))
    os.makedirs(dest, exist_ok=True)
    for name in (MANIFEST, RECEIPT_LEDGER):
        src = os.path.join(dirpath, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(dest, name))
    shutil.rmtree(dirpath)
    print(f"copied {MANIFEST} + {RECEIPT_LEDGER} to {dest}; deleted {dirpath}")
    return 0


def main(argv):
    p = argparse.ArgumentParser(prog="dispatch.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("seq")
    s.add_argument("--dir", required=True)

    b = sub.add_parser("before")
    b.add_argument("--dir", required=True)
    b.add_argument("--seq", type=int, required=True)
    b.add_argument("--file", required=True)
    b.add_argument("--role", required=True)
    b.add_argument("--phase", default=None)
    b.add_argument("--task", type=int, default=None)
    b.add_argument("--model-tier", required=True)

    a = sub.add_parser("after")
    a.add_argument("--dir", required=True)
    a.add_argument("--seq", type=int, required=True)
    a.add_argument("--status", required=True)
    a.add_argument("--summary", default=None)
    a.add_argument("--output-chars", type=int, default=None)
    a.add_argument("--tool-calls", type=int, default=None)
    a.add_argument("--duration", type=int, default=None)

    c = sub.add_parser("cleanup")
    c.add_argument("--dir", required=True)
    c.add_argument("--scratch", required=True)
    c.add_argument("--failed", action="store_true")

    a2 = p.parse_args(argv)

    if a2.cmd == "seq":
        return cmd_seq(a2.dir)
    if a2.cmd == "before":
        return cmd_before(a2)
    if a2.cmd == "after":
        return cmd_after(a2)
    if a2.cmd == "cleanup":
        return cmd_cleanup(a2)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))