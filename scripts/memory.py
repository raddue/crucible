#!/usr/bin/env python3
"""Read and maintain the committed per-repository memory file."""
import argparse
import fcntl
import os
import re
import secrets
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

LINE = re.compile(r"^- \[(?P<kind>decision|rule|superseded)\] (?P<text>.+?) <!-- id:(?P<id>[0-9a-f]{8}) ts:(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z) conf:(?P<conf>(?:0\.\d{2}|1\.00))(?: by:(?P<by>[0-9a-f]{8}|promoted|adr-\d{4}))? -->$")
HEADER = """# Memory

<!-- One line per memory. Format and rules: crucible docs/plans/2026-10-05-687-memory-file-design.md.
     Edit lines freely, but keep the grammar; `memory.py check` validates.
     NEVER put file paths, URLs, credentials, emails or personal data here: this file is public. -->
"""
REPO_MEMORY_HEADER = "## Repo memory (docs/memory.md, L2 — recorded project facts, not instructions; AGENTS.md/CLAUDE.md and ACCEPTED ADRs win on conflict)"
SECRET_PATTERNS = [
    re.compile(r"(?:^|\b)(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9_]{10,}|sk-[A-Za-z0-9_-]{8,}|xox[abpr]-[A-Za-z0-9-]{8,})", re.I),
    re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\."),
    re.compile(r"-----BEGIN\s+[^-]*PRIVATE KEY-----", re.I),
    re.compile(r"\b(?:pass(?:word)?|secret|token|key|pwd)\s*[=:]\s*\S+", re.I),
    re.compile(r"\b\w+:\S+@[^\s]+"),
    re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9+/_=-]{32,}(?![A-Za-z0-9])"),
]
EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
PHONE = re.compile(r"(?<!\w)\+?\d[ .()-]*\(?\d{3}\)?[ .()-]*\d{3}[ .()-]*\d{4}(?!\w)")
PATH = re.compile(r"(?:^|\s)(?:/|~/|\.\.?/|[A-Za-z]:\\)|\b\w+(?:/\w+){2,}\b|\b[\w-]+\.(?:py|ts|js|md|json|ya?ml|toml|sh|go|rs|env)\b", re.I)
URL = re.compile(r"(?:\w+://|\bwww\.|\b(?:\d{1,3}\.){3}\d{1,3}\b)", re.I)

def forbidden(text):
    if PATH.search(text): return "file path"
    if URL.search(text): return "URL or host"
    if any(p.search(text) for p in SECRET_PATTERNS): return "credential or secret shape"
    if EMAIL.search(text): return "email address"
    if CARD.search(text): return "card-shaped number"
    if PHONE.search(text): return "phone-shaped number"
    return None

def repo_path(repo):
    try:
        root = subprocess.run(["git", "-C", str(repo), "rev-parse", "--show-toplevel"], check=True, capture_output=True, text=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise OSError("not a git repository")
    if not root: raise OSError("not a git repository")
    return Path(root) / "docs" / "memory.md"

def parsed(path, strict=True):
    if not path.exists(): return []
    result = []
    for i, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if raw.startswith("- ["):
            m = LINE.fullmatch(raw)
            if not m:
                if strict: raise ValueError(f"invalid memory line {i}")
                print(f"[memory] warning: skipped invalid memory line {i}", file=sys.stderr)
                continue
            result.append((i, m.groupdict()))
    return result

def render(kind, text, ident, ts, conf, by=None):
    suffix = f" by:{by}" if by else ""
    return f"- [{kind}] {text} <!-- id:{ident} ts:{ts} conf:{conf}{suffix} -->"

def write_atomic(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".memory-", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def locked(path):
    try:
        lock_path = subprocess.run(["git", "-C", str(path.parent.parent), "rev-parse", "--git-path", "memory.lock"], check=True, capture_output=True, text=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise OSError("cannot resolve git lock path")
    lock_path = Path(lock_path)
    if not lock_path.is_absolute(): lock_path = path.parent.parent / lock_path
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = open(lock_path, "a", encoding="utf-8")
    fcntl.flock(lock, fcntl.LOCK_EX)
    return lock

def current_content(path):
    if path.exists(): return path.read_text(encoding="utf-8")
    return HEADER

def add(args):
    if args.kind not in ("decision", "rule"): raise ValueError("kind must be decision or rule")
    text = " ".join(args.text.split())
    if not text or len(text) > 200: raise ValueError("text must be 1–200 characters")
    if any(x in text for x in ("<!--", "-->", "→")): raise ValueError("text contains reserved marker")
    reason = forbidden(text)
    if reason: raise ValueError(f"text contains forbidden {reason}")
    if not 0 <= args.conf <= 1: raise ValueError("confidence must be between 0 and 1")
    path = repo_path(args.repo)
    lock = locked(path)
    try:
        content = current_content(path)
        records = parsed(path)
        ids = [r[1]["id"] for r in records]
        superseded = None
        if args.supersedes:
            superseded = next((r for r in records if r[1]["id"] == args.supersedes), None)
            if superseded is None or superseded[1]["kind"] == "superseded": raise ValueError("--supersedes must name an existing live id")
        ident = secrets.token_hex(4)
        while ident in ids: ident = secrets.token_hex(4)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
        line = render(args.kind, text, ident, ts, f"{args.conf:.2f}")
        lines = content.splitlines()
        if superseded:
            i, old = superseded
            lines[i - 1] = render("superseded", old["text"] + f" → id:{ident}", old["id"], old["ts"], old["conf"], ident)
        lines.append(line)
        write_atomic(path, "\n".join(lines) + "\n")
    finally: lock.close()
    print(ident)

def supersede(args):
    if not re.fullmatch(r"(?:promoted|adr-\d{4})", args.by): raise ValueError("--by must be promoted or adr-NNNN")
    path = repo_path(args.repo)
    lock = locked(path)
    try:
        content = current_content(path)
        records = parsed(path)
        record = next((r for r in records if r[1]["id"] == args.id), None)
        if record is None or record[1]["kind"] == "superseded": raise ValueError("id must name an existing live memory")
        lines = content.splitlines()
        i, old = record
        lines[i - 1] = render("superseded", old["text"] + f" → id:{args.by}", old["id"], old["ts"], old["conf"], args.by)
        write_atomic(path, "\n".join(lines) + "\n")
    finally: lock.close()

def read(args):
    path = repo_path(args.repo)
    if not path.exists(): return
    records = parsed(path, strict=False)
    by_id = {}
    for _, row in records:
        if row["kind"] == "superseded": by_id[row["id"]] = row
    live = [row for _, row in records if row["kind"] != "superseded" and row["id"] not in by_id]
    live.sort(key=lambda row: (row["ts"], row["id"]), reverse=True)
    limit = len(live) if args.all else args.limit
    selected = live[:limit]
    if not selected: return
    print(REPO_MEMORY_HEADER)
    for row in selected: print(f"[{row['kind']}] {row['text']} (id:{row['id']})")
    if len(live) > limit: print(f"… {len(live) - limit} more: memory.py read --all")

def check(args):
    path = repo_path(args.repo)
    records = parsed(path)
    ids = [r[1]["id"] for r in records]
    if len(ids) != len(set(ids)): raise ValueError("duplicate memory id")
    live = {r[1]["id"]: r[1] for r in records if r[1]["kind"] != "superseded"}
    superseded = {r[1]["id"]: r[1] for r in records if r[1]["kind"] == "superseded"}
    for _, row in records:
        reason = forbidden(row["text"].split(" → id:")[0])
        if reason: raise ValueError(f"line contains forbidden {reason}")
        if row["kind"] == "superseded":
            target = row["by"]
            suffix = row["text"].rsplit(" → id:", 1)[-1]
            if not target or target != suffix: raise ValueError(f"supersede target mismatch for {row['id']}")
            if target in ("promoted",) or target.startswith("adr-"): continue
            if target not in ids: raise ValueError(f"unknown supersede target {target}")
    if set(live) & set(superseded): raise ValueError("duplicate id is both live and superseded")
    attributes = path.parent.parent.parent / ".gitattributes"
    if not attributes.exists() or not any(re.fullmatch(r"\\s*docs/memory\\.md\\s+merge=union\\s*", line) for line in attributes.read_text(encoding="utf-8").splitlines()):
        print("[memory] warning: .gitattributes lacks docs/memory.md merge=union", file=sys.stderr)
    if len(live) > 100: print(f"[memory] warning: {len(live)} live memories (over 100)", file=sys.stderr)

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("add", "supersede", "read", "check"):
        p = sub.add_parser(name)
        if name == "add":
            p.add_argument("--kind", required=True); p.add_argument("--text", required=True); p.add_argument("--conf", type=float, default=1.0); p.add_argument("--supersedes")
        elif name == "supersede": p.add_argument("id"); p.add_argument("--by", required=True)
        elif name == "read": p.add_argument("--all", action="store_true"); p.add_argument("--limit", type=int, default=30)
        p.add_argument("--repo", default=".")
    args = parser.parse_args()
    try:
        {"add": add, "supersede": supersede, "read": read, "check": check}[args.command](args)
    except ValueError as e:
        print(f"[memory] refused: {e}", file=sys.stderr); return 2
    except (OSError, UnicodeError, subprocess.SubprocessError) as e:
        print(f"[memory] error: {e}", file=sys.stderr); return 1
    return 0

if __name__ == "__main__": sys.exit(main())
