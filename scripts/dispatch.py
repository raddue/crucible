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

`before` measures the dispatch file's size and appends the `status:"dispatched"`
entry. `after` appends the authoritative completion entry for the same seq,
copying the dispatched entry's context fields (file/role/phase/task/model_tier/
input_chars) so the last entry per seq is self-sufficient — matching the
convention's completed-entry example — and refuses to run if that dispatched
entry is absent (no fabricated history). Entries are kept under POSIX PIPE_BUF
(4096 bytes, measured on the UTF-8 encoded line) by shrinking `summary`, so a
single `write()` append stays atomic under concurrent access.

Deliberately NOT here: token/rework aggregation (`summary`) — forge owns that
aggregation; a third implementation would be a drift surface, not a win.
Pure stdlib.
"""

import argparse
import json
import os
import shutil
import sys

PIPE_BUF = 4096
MANIFEST = "manifest.jsonl"
RECEIPT_LEDGER = "receipt-ledger.jsonl"

STATUSES = {"completed", "failed", "error", "skipped"}
TIERS = {"opus", "sonnet", "haiku"}


def _manifest_path(d):
    return os.path.join(d, MANIFEST)


def _read_manifest(dirpath):
    """Return (rows, interior_corrupt_count).

    Interior corrupt lines (anything but a torn final line) are counted —
    seq recovery is unsafe across them. A ragged trailing line (mid-write
    crash) is tolerated silently, matching the convention's crash safety.
    """
    p = _manifest_path(dirpath)
    lines = []
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            lines = [ln for ln in f.read().split("\n") if ln.strip()]
    rows = []
    corrupt = 0
    for i, ln in enumerate(lines):
        try:
            rows.append(json.loads(ln))
        except json.JSONDecodeError:
            if i != len(lines) - 1:  # only the final line may be torn
                corrupt += 1
    return rows, corrupt


def _serialize(entry):
    return json.dumps(entry, separators=(",", ":"), ensure_ascii=False)


def _append(dirpath, entry):
    line = _serialize(entry)
    if len(line.encode("utf-8")) + 1 > PIPE_BUF:
        summary = entry.get("summary")
        if summary is not None:
            # binary-search the largest summary prefix (bytes) that fits
            fixed = dict(entry)
            fixed["summary"] = None
            overhead = len(_serialize(fixed).encode("utf-8"))
            budget = PIPE_BUF - 1 - overhead
            ell = "..."
            lo, hi, best = 0, len(summary), 0
            while lo <= hi:
                mid = (lo + hi) // 2
                entry["summary"] = summary[:mid] + (ell if mid < len(summary) else "")
                if len(_serialize(entry).encode("utf-8")) + 1 <= PIPE_BUF:
                    best = mid
                    lo = mid + 1
                else:
                    hi = mid - 1
            entry["summary"] = summary[:best] + (ell if best < len(summary) else "")
            line = _serialize(entry)
        if len(line.encode("utf-8")) + 1 > PIPE_BUF:
            print(f"[dispatch WARN] entry for seq {entry.get('seq')} still exceeds "
                  f"PIPE_BUF after summary truncation (fixed fields too large); "
                  f"writing anyway", file=sys.stderr)
    with open(_manifest_path(dirpath), "a", encoding="utf-8") as f:
        f.write(line + "\n")


def cmd_seq(dirpath):
    rows, corrupt = _read_manifest(dirpath)
    if corrupt:
        print(f"dispatch seq: {corrupt} interior corrupt line(s) in manifest.jsonl "
              f"— seq recovery unsafe, refusing to allocate", file=sys.stderr)
        return 1
    seqs = [int(r["seq"]) for r in rows if isinstance(r.get("seq"), int)]
    print(seqs[-1] + 1 if seqs else 1)
    return 0


def cmd_before(args):
    fp = args.file
    input_chars = None
    try:
        with open(fp, encoding="utf-8") as f:
            input_chars = len(f.read())
    except (OSError, UnicodeDecodeError) as e:
        # measurement failure must never block dispatch — proceed with null
        print(f"[dispatch WARN] cannot read dispatch file {fp}: {e}; "
              f"input_chars set to null", file=sys.stderr)
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
    if args.status not in STATUSES:
        print(f"dispatch after: status must be one of {sorted(STATUSES)}", file=sys.stderr)
        return 2
    prev = None
    rows, _ = _read_manifest(args.dir)
    for r in rows:
        if r.get("seq") == args.seq and r.get("status") == "dispatched":
            prev = r
    if prev is None:
        print(f"dispatch after: no dispatched entry for seq {args.seq} — "
              f"refusing to fabricate a completion record", file=sys.stderr)
        return 1
    entry = {
        "seq": args.seq,
        "file": prev.get("file"),
        "role": prev.get("role"),
        "phase": prev.get("phase"),
        "task": prev.get("task"),
        "status": args.status,
        "duration_s": args.duration,
        "summary": args.summary,
        "input_chars": prev.get("input_chars"),
        "output_chars": args.output_chars,
        "model_tier": prev.get("model_tier"),
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
        dst = os.path.join(scratch, os.path.basename(os.path.normpath(dirpath)))
        shutil.copytree(dirpath, dst, dirs_exist_ok=True)
        print(f"copied dispatch dir to {dst} (left /tmp in place)")
        return 0
    src_m = os.path.join(dirpath, MANIFEST)
    src_r = os.path.join(dirpath, RECEIPT_LEDGER)
    if not (os.path.exists(src_m) and os.path.exists(src_r)):
        print(f"dispatch cleanup: both {MANIFEST} and {RECEIPT_LEDGER} must exist "
              f"before deleting the dispatch dir (refusing)", file=sys.stderr)
        return 1
    dest = os.path.join(scratch, os.path.basename(os.path.normpath(dirpath)))
    os.makedirs(dest, exist_ok=True)
    shutil.copy2(src_m, os.path.join(dest, MANIFEST))
    shutil.copy2(src_r, os.path.join(dest, RECEIPT_LEDGER))
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