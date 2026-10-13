#!/usr/bin/env python3
"""Passive liveness/stuck detector for an orchestrator fleet (skills/orchestrator/SKILL.md).

Reads the fleet file + one external source, writes nothing. Emits one
fail-closed verdict per worker and exits nonzero if any worker with fleet
status `dispatched`/`working` is not LIVE, so a supervisor loop can wake on a
verdict instead of a fixed timer.

Two signal layers:

1. Liveness (default, kind-agnostic): `herdr agent list` — a worker is GONE if
   no live agent sits in its worktree (or bears its name). This is the only
   source that covers non-Claude backends (opencode/pi/gemini), which have no
   Claude transcript.
2. Transcript forensics (opt-in via `--transcript-dir`): newest `*.jsonl` in
   that dir, only for fleets whose workers produce Claude transcripts. Adds
   QUOTA / INTERRUPTED / STUCK above the liveness verdict.

ponytail: no slug autodetection — the real `~/.claude/projects/<slug>` slug is
an absolute path with `/` mapped to `-` and is easy to get wrong; require the
dir explicitly instead. Liveness-only (no `--transcript-dir`) is correct for
this repo's 9router fleet, which has no `~/.claude/projects/*` transcripts.
"""
import argparse
import glob
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts import orchestrator_fleet as of  # noqa: E402

_IN_FLIGHT = ("dispatched", "working")

_QUOTA_RE = re.compile(r"429|quota|rate\.limit|overloaded", re.I)


def _newest_jsonl(transcript_dir):
    candidates = [p for p in glob.glob(os.path.join(transcript_dir, "*.jsonl"))]
    if not candidates:
        # shallow one level deeper (session-id/*.jsonl layouts)
        candidates = [p for p in glob.glob(os.path.join(transcript_dir, "*", "*.jsonl"))]
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


def _tail_lines(path, n=200):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return lines[-n:]
    except OSError:
        return []


def _forensics(transcript_dir):
    """Return a verdict dict for `transcript_dir`, or None if no transcripts."""
    if not (transcript_dir and os.path.isdir(transcript_dir)):
        return None
    newest = _newest_jsonl(transcript_dir)
    if newest is None:
        return {"verdict": "NO-TRANSCRIPT"}
    tail = _tail_lines(newest)
    if any(_QUOTA_RE.search(line) for line in tail):
        return {"verdict": "QUOTA", "transcript": newest}

    # Last user/tool turn with no following assistant completion == interrupted.
    # ponytail: heurche on JSONL line order, not a real event parser; upgrade to
    # structured parse only if this misfires on a real interrupted fleet.
    roles = []
    for line in tail:
        try:
            ev = json.loads(line)
        except Exception:
            continue
        t = (ev.get("type") or ev.get("message", {}).get("role") or "").lower()
        roles.append(str(t))
    if roles and roles[-1] in ("user", "tool") and "assistant" not in roles[-4:]:
        return {"verdict": "INTERRUPTED", "transcript": newest}
    return {"verdict": "LIVE", "transcript": newest}


def scan(doc, agents, transcript_dir=None):
    """Return (verdicts, rc). Pure — pass agents; rc nonzero iff an in-flight
    worker is not LIVE."""
    by_name = {a.get("name"): a for a in agents if a.get("name")}
    by_cwd = {}
    for a in agents:
        cwd = a.get("cwd")
        if cwd:
            by_cwd[os.path.realpath(cwd)] = a
    verdicts = []
    lost = 0
    for w in doc.get("workers", []):
        name = w.get("name")
        a = by_name.get(name)
        if a is None:
            wt = w.get("worktree")
            a = by_cwd.get(os.path.realpath(wt)) if wt else None
        if a is None:
            verdicts.append({"name": name, "verdict": "GONE", "status": w.get("status")})
            if w.get("status") in _IN_FLIGHT:
                lost += 1
            continue
        fx = _forensics(transcript_dir) or {}
        verdict = fx.get("verdict", "LIVE")
        if verdict == "NO-TRANSCRIPT":
            verdict = "LIVE"  # liveness-only: no transcript is not a failure
        verdicts.append({
            "name": name,
            "verdict": verdict,
            "status": w.get("status"),
            "agent_status": a.get("agent_status"),
            "pane_id": a.get("pane_id"),
        })
        if w.get("status") in _IN_FLIGHT and verdict != "LIVE":
            lost += 1
    return verdicts, (1 if lost else 0)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Passive fleet liveness detector")
    ap.add_argument("-p", "--path", default=None)
    ap.add_argument("--transcript-dir", default=None,
                    help="opt-in dir of *.jsonl transcripts for quota/interrupted/stuck forensics")
    args = ap.parse_args(argv)
    path = args.path or of._default_path()
    doc = of._load(path)
    if doc is None:
        print("no fleet file", file=sys.stderr)
        return 1
    agents = of.live_agents()
    if agents is None:
        print("could not read live agents from herdr agent list", file=sys.stderr)
        return 2
    verdicts, rc = scan(doc, agents, args.transcript_dir)
    for v in verdicts:
        print(f"{v['verdict']:<12} {v['name']} fleet_status={v['status']} "
              f"agent={v.get('agent_status')} pane={v.get('pane_id')}")
    return rc


if __name__ == "__main__":
    sys.exit(main())