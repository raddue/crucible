#!/usr/bin/env python3
"""pipeline_status.py — deterministic ambient pipeline status file writer.

Executable transcription of the shared `## Pipeline Status` protocol (file
path, header fields, one-directional health state machine, last-5 Recent Events
buffer, Started persistence, atomic overwrite) currently duplicated in prose
across 6 orchestrator skills (build, debugging, audit, siege, migrate, spec)
and hand-composed on ~375-1000 writes/wk fleet-wide.

Invocation (from repo root; cwd determines the project hash):

    pipeline_status.py write --skill <s> --phase <text> --health GREEN|YELLOW|RED \
        [--suggested-action ".."] [--event ".."] ... [--body-file <f>]
    pipeline_status.py compact              # print the recoverable subset

Path (default): ~/.claude/projects/<sha256(cwd)[:16]>/memory/pipeline-status.md
    override with --path.

Rules enforced (transcribed from the protocol):
- Started persists across rewrites (first write stamps it).
- Health is one-directional GREEN(0) -> YELLOW(1) -> RED(2) within a phase;
  a phase change resets the machine. A backward transition within the same
  phase is refused (exit 1) — fail-closed against the drift this file guards.
- Suggested Action is omitted on GREEN, required on YELLOW/RED (stderr warning
  if absent, not a hard failure).
- Recent Events keeps the last 5, newest first, prefixed [HH:MM].
- Single write() of the whole file body (overwrite, never append).

Pure stdlib.
"""

import argparse
import hashlib
import os
import re
import sys
from datetime import datetime

HEALTH_ORDER = {"GREEN": 0, "YELLOW": 1, "RED": 2}
MAX_EVENTS = 5
MEMORY_ROOT = os.path.expanduser("~/.claude/projects")


def project_hash():
    return hashlib.sha256(os.getcwd().encode("utf-8")).hexdigest()[:16]


def default_path():
    return os.path.join(MEMORY_ROOT, project_hash(), "memory", "pipeline-status.md")


def _now():
    return datetime.now()


def _parse_time(s):
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _fmt_ts(dt):
    return dt.isoformat(timespec="seconds")


def _fmt_elapsed(seconds):
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    return f"{seconds // 3600}h {seconds % 3600 // 60}m"


def read_status(path):
    """Return {phase, health, started_iso, events: [(hhmm, text)], body_exists}."""
    out = {"phase": None, "health": None, "started_iso": None,
           "events": [], "skill_body": None}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        text = f.read()

    m = re.search(r"^\*\*Phase:\*\*\s*(.+?)\s*$", text, re.M)
    if m:
        out["phase"] = m.group(1).strip()
    m = re.search(r"^\*\*Health:\*\*\s*(GREEN|YELLOW|RED)\s*$", text, re.M)
    if m:
        out["health"] = m.group(1)
    m = re.search(r"^\*\*Started:\*\*\s*(\S+)\s*$", text, re.M)
    if m:
        out["started_iso"] = m.group(1)

    # Recent events: lines "- [HH:MM] text" inside the file, newest-first
    m = re.search(r"## Recent Events\n((?:.*\n)*)", text)
    if m:
        for line in m.group(1).splitlines():
            em = re.match(r"^- \[(\d{2}:\d{2})\] (.*)$", line)
            if em:
                out["events"].append((em.group(1), em.group(2)))

    # skill body = everything after the (last) "## Recent Events" section
    idx = text.find("## Recent Events")
    if idx != -1:
        rest = text[idx:]
        rest = re.sub(r"^## Recent Events\n(?:.*\n)*?", "", rest, count=1)
        # keep remaining skill-specific sections (Task Progress, etc.)
        kept = [ln for ln in rest.splitlines() if ln.strip()]
        out["skill_body"] = "\n".join(kept) + ("\n" if kept else "")
    return out


def validate_health(path, phase, new_health):
    st = read_status(path)
    # phase change resets; same phase is one-directional
    if st["phase"] is not None and st["phase"] == phase and st["health"] is not None:
        if HEALTH_ORDER[new_health] < HEALTH_ORDER[st["health"]]:
            return f"health would move backward within phase {phase!r}: {st['health']} -> {new_health}"
    return None


def render(path, skill, phase, health, suggested, events, skill_body, started_override=None):
    st = read_status(path)
    now = _now()

    started_iso = started_override if started_override is not None else st["started_iso"]
    if started_iso is None:
        started_iso = _fmt_ts(now)
    started_dt = _parse_time(started_iso)
    elapsed = _fmt_elapsed((now - started_dt).total_seconds()) if started_dt else "?"

    # merge events: new events (chronological as given by caller) go first
    merged = st["events"][:]
    for e in events:
        merged.insert(0, (_now().strftime("%H:%M"), e))
    merged = merged[:MAX_EVENTS]

    lines = ["# Pipeline Status",
             f"**Updated:** {_fmt_ts(now)}",
             f"**Started:** {started_iso}",
             f"**Skill:** {skill}",
             f"**Phase:** {phase}",
             f"**Health:** {health}"]
    if health != "GREEN":
        lines.append(f"**Suggested Action:** {suggested or ''}")
    lines.append(f"**Elapsed:** {elapsed}")
    lines.append("")
    lines.append("## Recent Events")
    for hhmm, text in merged:
        lines.append(f"- [{hhmm}] {text}")
    lines.append("")
    body = ""
    if skill_body is not None:
        body = skill_body
    if body and not body.startswith("\n"):
        body = "\n" + body
    return "\n".join(lines) + body


def cmd_write(args):
    if args.health not in HEALTH_ORDER:
        print(f"health must be one of {sorted(HEALTH_ORDER)}", file=sys.stderr)
        return 2
    path = args.path or default_path()
    err = validate_health(path, args.phase, args.health)
    if err:
        print(f"pipeline_status: {err}", file=sys.stderr)
        return 1
    if args.health != "GREEN" and not args.suggested_action:
        print(f"pipeline_status WARN: {args.health} without --suggested-action", file=sys.stderr)
    skill_body = None
    if args.body_file:
        with open(args.body_file, encoding="utf-8") as f:
            skill_body = f.read()
    content = render(path, args.skill, args.phase, args.health,
                     args.suggested_action, args.event, skill_body)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"wrote {path} ({args.phase} | {args.health})")
    return 0


def cmd_compact(args):
    path = args.path or default_path()
    st = read_status(path)
    if not os.path.exists(path):
        print("[no pipeline-status.md — no recovered state]")
        return 0
    print(f"Phase: {st['phase']}")
    print(f"Started: {st['started_iso']}")
    print("Recent Events (newest first):")
    for hhmm, text in st["events"]:
        print(f"  - [{hhmm}] {text}")
    if st["skill_body"]:
        print("--- skill-specific body ---")
        sys.stdout.write(st["skill_body"])
    return 0


def main(argv):
    p = argparse.ArgumentParser(prog="pipeline_status.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("write")
    w.add_argument("--skill", required=True)
    w.add_argument("--phase", required=True)
    w.add_argument("--health", required=True)
    w.add_argument("--suggested-action", default=None)
    w.add_argument("--event", action="append", default=[])
    w.add_argument("--body-file", default=None)
    w.add_argument("--path", default=None)

    c = sub.add_parser("compact")
    c.add_argument("--path", default=None)

    a = p.parse_args(argv)
    if a.cmd == "write":
        return cmd_write(a)
    if a.cmd == "compact":
        return cmd_compact(a)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))