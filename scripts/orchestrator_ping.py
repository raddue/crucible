#!/usr/bin/env python3
"""One-shot, low-token status checks for settled Herdr fleet workers."""
import argparse
import json
import os
import re
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts import orchestrator_fleet as of  # noqa: E402

PROMPT = "Status only. Reply exactly: STATUS=<working|blocked|done> NEXT=<short phrase>. No tools."
_IN_FLIGHT = ("dispatched", "working")


def promptable(status):
    return status in ("idle", "done")


def select_workers(workers, names=None):
    if not names:
        return list(workers)
    selected = [w for w in workers if w.get("name") in names]
    missing = set(names) - {w.get("name") for w in selected}
    if missing:
        raise ValueError("unknown worker(s): " + ", ".join(sorted(missing)))
    return selected


def status_line(text):
    return next((line.strip() for line in text.splitlines() if re.search(r"\bSTATUS=", line)), None)


def get_agent(target):
    try:
        out = subprocess.run(["herdr", "agent", "get", target], capture_output=True, text=True, timeout=10)
        if out.returncode:
            return None
        result = json.loads(out.stdout).get("result", {})
        return result.get("agent")
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Ping settled fleet workers for a one-line status")
    ap.add_argument("-p", "--path", default=None)
    ap.add_argument("--name", action="append", help="worker name; repeat to select several (default: all fleet workers)")
    ap.add_argument("--timeout", type=int, default=60000, help="prompt wait timeout in milliseconds")
    args = ap.parse_args(argv)
    if args.timeout < 1:
        ap.error("--timeout must be positive")

    path = args.path or of._default_path()
    doc = of._load(path)
    if doc is None:
        print("no fleet file", file=sys.stderr)
        return 1
    try:
        selected = select_workers(doc.get("workers", []), args.name)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1

    live = of.live_agents()
    if live is None:
        print("could not read live agents from herdr agent list", file=sys.stderr)
        return 2
    matched, stale = of.reconcile({"workers": selected}, live)
    rc = 0
    for worker in stale:
        print(f"GONE {worker.get('name')}")
        if worker.get("status") in _IN_FLIGHT:
            rc = 1

    agents_by_pane = {a.get("pane_id"): a for a in live}
    for name, pane, listed_status, _cwd in matched:
        agent = agents_by_pane.get(pane, {})
        target = agent.get("name") or pane
        if not target:
            print(f"SKIP {name} agent=unknown")
            continue
        # Re-read immediately before prompting; a stale list must never interrupt a working turn.
        current = get_agent(target)
        status = current.get("agent_status") if current else None
        if not promptable(status):
            print(f"SKIP {name} agent={status or 'unknown'}")
            continue
        try:
            sent = subprocess.run(
                ["herdr", "agent", "prompt", target, PROMPT, "--wait", "--timeout", str(args.timeout)],
                capture_output=True, text=True, timeout=args.timeout / 1000 + 10,
            )
        except (OSError, subprocess.SubprocessError) as e:
            print(f"FAILED {name}: {e}")
            rc = 1
            continue
        if sent.returncode:
            detail = (sent.stderr or sent.stdout).strip().replace("\n", " ")[:180]
            print(f"FAILED {name}: {detail or 'prompt failed'}")
            rc = 1
            continue
        try:
            read = subprocess.run(
                ["herdr", "agent", "read", target, "--source", "recent-unwrapped", "--lines", "12"],
                capture_output=True, text=True, timeout=10,
            )
            reply = status_line(read.stdout) if read.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            reply = None
        print(f"PING {name}: {reply or 'reply has no STATUS= line'}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
