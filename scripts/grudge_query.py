#!/usr/bin/env python3
"""Grudge query — the pre-flight read of the Book of Grudges (#271).

Given the files a skill is about to touch, surface the grudges held against them
as a "DO NOT REPEAT" block. Read-only (except --cull). Spec:
docs/plans/2026-06-01-regression-oracle-design.md.

Pure stdlib. No third-party deps.

Design fixes baked in (from the design adversarial gate):
- #1 normalize both sides to repo-relative POSIX before comparing; glob only when
     the stored path actually contains glob metachars, else exact equality.
- #3 filter loaded grudges to the current repo_root (isolation, not just dir name).
- #4 stderr counts + --stats so write-starvation is visible.
- #5 per-path staleness: match against surviving files only; cull iff none survive.
- #7 signature compiled defensively (re.error -> literal substring); file read size-capped.
"""
import fnmatch
import glob as _glob
import json
import os
import re as _re
import sys
from typing import Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from grudge_append import (  # noqa: E402
    default_base_dir, grudges_dir, normalize_path, resolve_repo,
)

SIG_READ_CAP_BYTES = 256 * 1024  # fix #7: bound signature-match file reads
SIG_MATCH_TIMEOUT_S = 2.0  # wall-clock guard so a pathological signature regex can never hang a pre-flight
DEFAULT_LIMIT = 5
_GLOB_CHARS = set("*?[")


def _qwarn(msg: str) -> None:
    print(f"[grudge_query WARN] {msg}", file=sys.stderr)


class _SigTimeout(Exception):
    """Raised by the SIGALRM handler when a signature match overruns its budget."""


def _glob_match(path: str, pattern: str) -> bool:
    """Path-aware glob: `*` matches within ONE segment, never crosses `/`
    (reused discipline from reconcile_ledger._glob_match, PR #340). fnmatchcase
    keeps it case-sensitive + cross-host deterministic. Glob-free patterns fall
    out as segment-wise equality."""
    p_seg = path.split("/")
    pat_seg = pattern.split("/")
    if len(p_seg) != len(pat_seg):
        return False
    return all(fnmatch.fnmatchcase(a, b) for a, b in zip(p_seg, pat_seg))


def _path_match(scope_norm: str, stored: str) -> bool:
    """Exact normalized equality, unless the stored path carries glob metachars
    (then path-aware glob). Fix #1: stored files_touched are concrete paths, so
    exact equality is the correct default — not _glob_match's depth-pinned glob.

    Exact equality is tried FIRST, before the metachar check: a real filename can
    legally contain `[ ] ? *` (e.g. Next.js dynamic routes `pages/[id].js`), and
    such a literal path must match itself rather than being misread as a glob."""
    if scope_norm == stored:
        return True
    if any(c in stored for c in _GLOB_CHARS):
        return _glob_match(scope_norm, stored)
    return False


def parse_grudge(path: str) -> Optional[Dict]:
    """Parse one grudge .md (frontmatter + body). Returns a dict or None if the
    file is unparseable (skipped silently — a malformed file never crashes a read)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    # Split only on a '---' that is alone on its own line. A naive
    # text.split("---", 2) breaks on the first '---' ANYWHERE — including inside
    # a frontmatter value (`symptom: regression --- see PR`) or a body fence
    # (markdown rules / diffs in a repro), both common — truncating the
    # frontmatter and silently dropping files_touched so the grudge never matches.
    parts = _re.split(r"(?m)^---[ \t]*$", text, maxsplit=2)
    if len(parts) < 3:
        return None
    fm_block, body = parts[1], parts[2]
    rec: Dict = {"_path": path, "repro": "", "why": ""}
    for line in fm_block.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        if key in ("files_touched",):
            try:
                rec[key] = json.loads(val)
            except (ValueError, TypeError):
                rec[key] = []
        elif key == "anti_pattern_signature":
            try:
                rec[key] = json.loads(val) if val else ""
            except (ValueError, TypeError):
                rec[key] = val
        else:
            rec[key] = val
    rec.setdefault("files_touched", [])
    rec.setdefault("anti_pattern_signature", "")
    return rec


def load_grudges(repo: str, repo_root: str, base_dir: Optional[str] = None) -> List[Dict]:
    """Load all grudges for this repo, filtered to the current repo_root
    (fix #3 — same-basename repos cannot bleed)."""
    d = grudges_dir(repo, base_dir)
    out: List[Dict] = []
    if not os.path.isdir(d):
        return out
    unparseable = 0  # #400: surface corrupt grudge files instead of silent skip
    for name in sorted(os.listdir(d)):
        if not name.endswith(".md"):
            continue
        g = parse_grudge(os.path.join(d, name))
        if g is None:
            unparseable += 1
            continue
        if os.path.realpath(g.get("repo_root", "")) != os.path.realpath(repo_root):
            continue
        out.append(g)
    if unparseable:
        _qwarn(f"skipped {unparseable} unparseable grudge file(s) in {d}")
    return out


def survivors(grudge: Dict, repo_root: str) -> List[str]:
    """files_touched that still exist on disk (fix #5 — per-path staleness).

    A glob entry (e.g. `src/auth/*`) can't be existence-checked literally — it
    "survives" iff the pattern still matches at least one real file. Concrete
    paths survive iff they exist.

    Literal existence is checked FIRST: a real file whose name contains glob
    metachars (e.g. `pages/[id].js`) exists on disk but `glob.glob` would read
    `[id]` as a character class and find nothing — so a literal-exists hit must
    win before the glob fallback, else the grudge is wrongly judged stale (and
    `--cull` would delete it)."""
    out = []
    for f in grudge.get("files_touched", []):
        full = os.path.join(repo_root, f)
        if os.path.exists(full):
            out.append(f)
        elif any(c in f for c in _GLOB_CHARS) and _glob.glob(full):
            out.append(f)
    return out


def _signature_hit(signature: str, scope_files: List[str], repo_root: str) -> bool:
    """Defensive signature match (fix #7): compile as regex, fall back to literal
    substring on re.error; cap file read size.

    A stored signature is free text and may be a catastrophic-backtracking regex
    (`(a+)+$`); run unguarded it can hang the host for minutes, violating the
    pre-flight's NEVER-block contract (and quality-gate wires --with-signatures).
    Each per-file match therefore runs under a SIGALRM wall-clock budget; on
    timeout the whole signature scan is abandoned (treated as no-hit) with a
    stderr warning. When no usable timer exists (e.g. imported on a worker
    thread — SIGALRM is main-thread-only), degrade to literal substring matching,
    which cannot backtrack, rather than risk a hang."""
    sig = (signature or "").strip()
    if not sig:
        return False
    try:
        rx = _re.compile(sig)
        regex_ok = True
    except _re.error:
        rx = None
        regex_ok = False

    import signal as _signal
    import threading
    can_arm = (
        hasattr(_signal, "SIGALRM")
        and threading.current_thread() is threading.main_thread()
    )
    if regex_ok and can_arm:
        matcher = lambda s: rx.search(s) is not None  # noqa: E731
        armed = True
    else:
        matcher = lambda s: sig in s  # noqa: E731 — literal, ReDoS-proof
        armed = False

    def _on_alarm(signum, frame):  # noqa: ANN001
        raise _SigTimeout()

    old_handler = _signal.signal(_signal.SIGALRM, _on_alarm) if armed else None
    try:
        for f in scope_files:
            p = os.path.join(repo_root, f)
            try:
                with open(p, "r", encoding="utf-8", errors="replace") as fh:
                    content = fh.read(SIG_READ_CAP_BYTES)
            except OSError:
                continue
            if armed:
                _signal.setitimer(_signal.ITIMER_REAL, SIG_MATCH_TIMEOUT_S)
            try:
                if matcher(content):
                    return True
            except _SigTimeout:
                _qwarn(
                    f"signature match exceeded {SIG_MATCH_TIMEOUT_S}s on {f}; "
                    f"abandoning signature scan (a pre-flight must never block)"
                )
                return False
            finally:
                if armed:
                    _signal.setitimer(_signal.ITIMER_REAL, 0)
    except _SigTimeout:
        # The alarm can fire in the sub-microsecond gap between a match returning
        # and the inner finally disarming the timer, escaping the inner except.
        # Catch it here too so a timeout can never propagate out uncaught.
        _qwarn("signature match timed out at the deadline boundary; treating as no-hit")
        return False
    finally:
        if armed and old_handler is not None:
            _signal.signal(_signal.SIGALRM, old_handler)
    return False


def query(
    scope_files: List[str],
    repo: str,
    repo_root: str,
    *,
    with_signatures: bool = False,
    base_dir: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
) -> Tuple[List[Dict], Dict]:
    """Return (matched_grudges, stats). Matched grudges are sorted most-recent
    first and capped at `limit`."""
    scope_norm = [normalize_path(f, repo_root) for f in scope_files if f and f.strip()]
    grudges = load_grudges(repo, repo_root, base_dir)
    matched: List[Dict] = []
    skipped_stale = 0
    for g in grudges:
        surv = survivors(g, repo_root)
        if not surv:
            skipped_stale += 1
            continue
        hit = any(_path_match(s, stored) for s in scope_norm for stored in surv)
        if not hit and with_signatures:
            hit = _signature_hit(g.get("anti_pattern_signature", ""), scope_norm, repo_root)
        if hit:
            matched.append(g)
    matched.sort(key=lambda g: g.get("date_fixed", ""), reverse=True)
    truncated = max(0, len(matched) - limit)
    stats = {
        "scanned": len(grudges),
        "matched": len(matched),
        "skipped_stale": skipped_stale,
        "truncated": truncated,
        "repo_root": repo_root,
    }
    return matched[:limit], stats


def render_block(matched: List[Dict], stats: Dict) -> str:
    if not matched:
        return ""
    lines = [f"⚠️  {len(matched)} grudge(s) held against the files you're about to touch — DO NOT REPEAT:"]
    for g in matched:
        sym = g.get("symptom", "(no symptom)")
        commit = g.get("fixed_in_commit", "")
        when = g.get("date_fixed", "")
        files = ", ".join(g.get("files_touched", []))
        tag = f" (fixed {commit[:9]}{', ' + when if when else ''})" if commit or when else ""
        lines.append(f"  ☠ {sym}{tag}")
        rc = g.get("root_cause", "")
        if rc:
            lines.append(f"      root cause: {rc}")
        if files:
            lines.append(f"      files: {files}")
    if stats.get("truncated"):
        lines.append(f"  … and {stats['truncated']} more (showing {len(matched)} most recent).")
    return "\n".join(lines)


def cull(repo: str, repo_root: str, base_dir: Optional[str] = None) -> List[str]:
    """Remove grudges whose every files_touched path is gone (fix #5: same
    predicate as read-time skip). Returns removed file paths."""
    removed = []
    for g in load_grudges(repo, repo_root, base_dir):
        if not survivors(g, repo_root):
            try:
                os.remove(g["_path"])
                removed.append(g["_path"])
            except OSError:
                pass
    return removed


def _main(argv: List[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Query the Book of Grudges for files about to be touched.")
    ap.add_argument("files", nargs="*", help="in-scope files (absolute, ./-prefixed, or repo-relative)")
    ap.add_argument("--with-signatures", action="store_true", help="also match anti_pattern_signature against file contents")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ap.add_argument("--stats", action="store_true", help="report grudge counts for this repo and exit")
    ap.add_argument("--cull", action="store_true", help="remove grudges whose files_touched are all gone")
    ap.add_argument("--repo-root", default=None, help="override git toplevel realpath (tests)")
    ap.add_argument("--repo", default=None, help="override repo basename (tests)")
    args = ap.parse_args(argv)

    if args.repo_root:
        repo_root = os.path.realpath(args.repo_root)
        repo = args.repo or os.path.basename(repo_root) or "unknown"
    else:
        repo, repo_root = resolve_repo()
        if args.repo:
            repo = args.repo

    if args.cull:
        removed = cull(repo, repo_root)
        print(f"grudge: culled {len(removed)} settled grudge(s) for {repo}", file=sys.stderr)
        for r in removed:
            print(r)
        return 0

    if args.stats:
        grudges = load_grudges(repo, repo_root)
        import datetime as _dt
        today = _dt.datetime.now(_dt.timezone.utc).date()
        def _within(days):
            n = 0
            for g in grudges:
                try:
                    d = _dt.date.fromisoformat(g.get("date_fixed", ""))
                    if (today - d).days <= days:
                        n += 1
                except ValueError:
                    pass
            return n
        print(f"grudge: {len(grudges)} held for {repo}; {_within(7)} in last 7d, {_within(30)} in last 30d")
        return 0

    matched, stats = query(
        args.files, repo, repo_root,
        with_signatures=args.with_signatures, limit=args.limit,
    )
    print(
        f"grudge: scanned={stats['scanned']} matched={stats['matched']} "
        f"skipped_stale={stats['skipped_stale']} repo={repo_root}",
        file=sys.stderr,
    )
    block = render_block(matched, stats)
    if block:
        print(block)
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
