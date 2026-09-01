#!/usr/bin/env python3
"""Grudge query — the pre-flight read of the Book of Grudges (#271).

Given the files a skill is about to touch, surface the grudges held against them
as a "DO NOT REPEAT" block. Read-only (except --cull).

Pure stdlib. No third-party deps.

Design fixes baked in (from the design adversarial gate):
- #1 normalize both sides to repo-relative POSIX before comparing; glob only when
     the stored path actually contains glob metachars, else exact equality.
- #3 filter loaded grudges to the current repo_root (isolation, not just dir name).
- #4 stderr counts + --stats so write-starvation is visible.
- #5 per-path staleness: match against surviving files only; cull iff none survive.
- #7 signature compiled defensively (re.error -> literal substring); file read size-capped.
"""
import glob as _glob
import json
import os
import re as _re
import sys
from typing import Dict, List, Optional, Tuple

# #401: root the package at the repo (`scripts.X`), matching reconcile_ledger /
# render_ledger / brier_advisory / backfill-ledger — was the lone sibling using
# `sys.path.insert(0, HERE)` + bare `from grudge_append import …`, which forced
# every caller to keep BOTH roots on sys.path for the grudge path to resolve.
HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
from scripts.grudge_append import (  # noqa: E402
    default_base_dir, grudges_dir, normalize_path, resolve_repo,
)
from scripts.pathmatch import glob_match as _glob_match  # noqa: E402

SIG_READ_CAP_BYTES = 256 * 1024  # fix #7: bound signature-match file reads
SIG_MATCH_TIMEOUT_S = 2.0  # wall-clock guard so a pathological signature regex can never hang a pre-flight
DEFAULT_LIMIT = 5
_GLOB_CHARS = set("*?[")


def _qwarn(msg: str) -> None:
    print(f"[grudge_query WARN] {msg}", file=sys.stderr)


class _SigTimeout(Exception):
    """Raised by the SIGALRM handler when a signature match overruns its budget."""


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
                # #408 F4: a malformed files_touched silently empties the
                # grudge's match scope (it then matches NO path and is a silent
                # miss, not a loud parse error). Surface it.
                _qwarn(f"malformed files_touched in {path}; grudge will match "
                       f"no files")
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


# --------------------------------------------------------------------------- #
# #559: resolution lookups for the grudge-resolution Stop hook.               #
#                                                                             #
# store_repo_root locates/filters the grudge store; session_root is the        #
# checkout every git call runs against (`git -C <session_root>`). The two are  #
# distinct: a linked worktree shares the store of its checkout root but has    #
# its own HEAD and its own on-disk files.                                     #
# --------------------------------------------------------------------------- #
# `git -C <dir>` only chdirs — it does NOT clear the inherited environment, and
# two families of variables there outrank everything on the command line:
#   * repository LOCATION — GIT_DIR, GIT_WORK_TREE, GIT_INDEX_FILE, … — which
#     take precedence over discovery-from-cwd, so an inherited GIT_DIR (a Stop
#     hook firing while a git hook is on the stack, or any shell that exported
#     it) silently sends every call below at a DIFFERENT repository;
#   * git CONFIG — GIT_CONFIG_COUNT/GIT_CONFIG_KEY_n/GIT_CONFIG_VALUE_n,
#     GIT_CONFIG_GLOBAL and GIT_CONFIG_PARAMETERS (`git -c`'s own transport).
#     A single bad key in any of them turns EVERY call here into
#     `fatal: unable to parse command-line config` (rc=128), which this module
#     reads as an ordinary miss — measured: with `GIT_CONFIG_COUNT=1` inherited,
#     a --by-commit lookup that answers `matched=1` answers `matched=0` instead,
#     so the Stop hook's step-13 clearance flips from cleared to blocked with
#     nothing in its output to say why.
# Either way the wrong answer is indistinguishable from a right one.
#
# This is therefore an ALLOWLIST, not a denylist, mirroring the Stop hook's own
# `env -i PATH HOME git` (hooks/grudge-resolution-guard.sh). A denylist CANNOT
# be complete here even in principle: GIT_CONFIG_KEY_n is INDEXED, so the set of
# names to drop is unbounded and no literal tuple can name them all. git is
# handed only what it genuinely needs — PATH (git must be findable at all) and
# HOME (git's per-user config, where a legitimate `safe.directory` lives).
# Everything git needs about the repository it is being asked about arrives as
# an argument, which covers the repository-location family for free.
_GIT_ENV_KEEP = ("PATH", "HOME")


def _git_env() -> Dict[str, str]:
    return {k: os.environ[k] for k in _GIT_ENV_KEEP if k in os.environ}


def _git(session_root: str, *args: str) -> Tuple[int, str]:
    """Run `git -C <session_root> <args>`; return (returncode, stripped stdout).
    A missing/failing git is a non-zero returncode, never a raised error."""
    import subprocess
    try:
        proc = subprocess.run(
            ["git", "-C", session_root, *args],
            capture_output=True, text=True, timeout=30, env=_git_env(),
        )
    except (OSError, ValueError):
        return (1, "")
    return (proc.returncode, proc.stdout.strip())


def _fs_root(session_root: str) -> str:
    """The checkout root `session_root` names, for the FILESYSTEM half of the
    lookup. git resolves a repository from any subdirectory, but files_touched
    are stored repo-relative, so joining them onto a session_root that is a
    subdirectory makes every stored path "not exist" and every grudge look
    0-survivor. --session-root defaults to cwd and a Stop hook's cwd is routinely
    a subdirectory, so this is the default path, not an exotic argument.
    A session_root that is not inside a repository at all falls back to itself —
    an ordinary miss, never an internal error."""
    rc, top = _git(session_root, "rev-parse", "--show-toplevel")
    if rc != 0 or not top:
        return session_root
    return os.path.realpath(top)


_HEX_TOKEN = _re.compile(r"^[0-9a-fA-F]{4,40}$")


def _resolve_commit(session_root: str, sha: str) -> Optional[str]:
    """Full 40-char commit id for `sha`, or None when it is empty, unresolvable
    or ambiguous. "Cannot resolve" is a miss, never an internal error.

    A hex-shaped token — exactly what fixed_in_commit stores — is disambiguated
    into the OBJECT namespace first. `rev-parse --verify <s>^{commit}` prefers a
    REF named <s> over the object whose abbreviation is <s> (announcing it only
    as "refname is ambiguous" on stderr, which _git discards), so a repository
    holding a tag or branch named like a short SHA would otherwise resolve a
    stored abbreviation to a completely unrelated commit. Each candidate object
    is still peeled through the contract's pinned
    `rev-parse --verify <sha>^{commit}` form; a prefix that peels to more than
    one commit is genuinely ambiguous and stays a miss."""
    s = (sha or "").strip()
    if not s:
        return None
    if _HEX_TOKEN.match(s):
        rc, out = _git(session_root, "rev-parse", f"--disambiguate={s}")
        if rc != 0:
            return None
        commits = set()
        for oid in out.split():
            crc, cout = _git(session_root, "rev-parse", "--verify", f"{oid}^{{commit}}")
            if crc == 0 and len(cout) == 40:
                commits.add(cout)
        return commits.pop() if len(commits) == 1 else None
    rc, out = _git(session_root, "rev-parse", "--verify", f"{s}^{{commit}}")
    if rc != 0 or len(out) != 40:
        return None
    return out


def find_by_commit(sha: str, repo: str, store_repo_root: str, session_root: str) -> Optional[Dict]:
    """The grudge whose fixed_in_commit is the same commit as `sha`, or None.

    BOTH sides go through `git rev-parse --verify <x>^{commit}` first, so a full
    40-char candidate matches a stored 7-char abbreviation. A non-zero rev-parse
    on either side means "no match"."""
    target = _resolve_commit(session_root, sha)
    if target is None:
        return None
    for g in load_grudges(repo, store_repo_root):
        stored = _resolve_commit(session_root, g.get("fixed_in_commit", ""))
        if stored is not None and stored == target:
            return g
    return None


def _patch_id(session_root: str, sha: str, path: str) -> str:
    """Field 1 (the patch-id) of `diff-tree -p <sha> -- <path> | patch-id
    --stable`, or "" when either side produces nothing. Field 2 is the commit id,
    which differs by construction between a rewrite and its original."""
    import subprocess
    try:
        # --root: without it `diff-tree -p` prints NOTHING for a parentless root
        # commit, so _patch_id returns "" and _structural_match's bool() guard
        # can never match one. Root commits are a real case here (orphan
        # branches, fresh repos, squash-to-orphan); the flag is a no-op for a
        # commit that has a parent.
        diff = subprocess.run(
            ["git", "-C", session_root, "diff-tree", "--root", "-p", sha, "--", path],
            capture_output=True, text=True, timeout=30, env=_git_env(),
        )
        if diff.returncode != 0 or not diff.stdout.strip():
            return ""
        pid = subprocess.run(
            ["git", "-C", session_root, "patch-id", "--stable"],
            input=diff.stdout, capture_output=True, text=True, timeout=30,
            env=_git_env(),
        )
    except (OSError, ValueError):
        return ""
    if pid.returncode != 0:
        return ""
    fields = pid.stdout.split()
    return fields[0] if fields else ""


def _structural_match(grudge: Dict, survivor: str, session_root: str, candidate_sha: str) -> bool:
    """==1-survivor branch: the stored fix resolves, is NOT already reachable
    from the session's HEAD (the exact-SHA path covers reachable ones), and
    carries the same patch as the candidate for that one file."""
    stored = _resolve_commit(session_root, grudge.get("fixed_in_commit", ""))
    if stored is None:
        return False
    rc, _ = _git(session_root, "merge-base", "--is-ancestor", stored, "HEAD")
    if rc == 0:
        return False
    stored_pid = _patch_id(session_root, stored, survivor)
    cand_pid = _patch_id(session_root, candidate_sha, survivor)
    return bool(stored_pid) and bool(cand_pid) and stored_pid == cand_pid


def find_by_files(
    files: List[str],
    repo: str,
    store_repo_root: str,
    session_root: str,
    candidate_sha: str,
    candidate_at: int,
) -> Optional[Dict]:
    """The grudge already resolving the candidate commit's file set, or None.

    survivors(g, session_root) is BOTH the branch selector and the match test, so
    a grudge with >=1 survivor is checked by exactly one branch: >=2 survivors ->
    subset of the candidate's files AND date_fixed not after the candidate's UTC
    author date; ==1 -> structural patch-id identity."""
    import datetime as _dt
    # git resolves the repo from any subdirectory, but files_touched are stored
    # repo-relative — so the FILESYSTEM half of this lookup must run against the
    # checkout root, not against a session_root that may be below it.
    fs_root = _fs_root(session_root)
    cand = {normalize_path(f, fs_root) for f in (files or []) if f and f.strip()}
    cand_date = _dt.datetime.fromtimestamp(int(candidate_at), _dt.timezone.utc).date()
    for g in load_grudges(repo, store_repo_root):
        # parse_grudge's #408 F4 guard catches only a JSON decode error, so a
        # hand-written files_touched that decodes to a non-list (`5`, `null`) or
        # a list holding a non-string reaches survivors() and raises. A malformed
        # record is a silent miss, never the CLI's exit 3.
        try:
            surv = survivors(g, fs_root)
        except (TypeError, AttributeError):
            _qwarn(f"unusable files_touched in {g.get('_path')}; grudge cannot match")
            continue
        if not surv:
            continue
        if len(surv) >= 2:
            if not set(surv) <= cand:
                continue
            try:
                fixed_on = _dt.date.fromisoformat(g.get("date_fixed", ""))
            except (ValueError, TypeError):
                _qwarn(f"unusable date_fixed in {g.get('_path')}; grudge cannot match")
                continue
            if fixed_on <= cand_date:
                return g
        elif _structural_match(g, surv[0], session_root, candidate_sha):
            return g
    return None


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
    ap.add_argument("--by-commit", default=None, metavar="SHA",
                    help="#559: print the stem of the grudge fixed by this commit")
    ap.add_argument("--by-files", default=None, metavar="CSV",
                    help="#559: comma-separated files the candidate commit touched")
    ap.add_argument("--candidate-sha", default=None, help="#559: candidate commit for --by-files")
    ap.add_argument("--candidate-at", type=int, default=None,
                    help="#559: candidate commit author date, epoch seconds")
    ap.add_argument("--session-root", default=None, metavar="PATH",
                    help="#559: checkout every git call runs against (default: cwd)")
    args = ap.parse_args(argv)

    if args.repo_root:
        repo_root = os.path.realpath(args.repo_root)
        repo = args.repo or os.path.basename(repo_root) or "unknown"
    else:
        repo, repo_root = resolve_repo()
        if args.repo:
            repo = args.repo

    # #559 resolution lookups. Exit-code contract (distinct from argparse's own
    # exit 2 for a bad argument, AMB-7): match -> 0 + the record's filename stem
    # on stdout; ordinary miss (including unresolvable/ambiguous/empty SHAs) ->
    # 0 + empty stdout; internal error -> 3 + stderr diagnostic + empty stdout.
    # A malformed grudge record is NOT an internal error — load_grudges and
    # parse_grudge deliberately never raise on those.
    if args.by_commit is not None or args.by_files is not None:
        session_root = os.path.realpath(args.session_root) if args.session_root else os.getcwd()
        try:
            scanned = len(load_grudges(repo, repo_root))
            if args.by_commit is not None:
                hit = find_by_commit(args.by_commit, repo, repo_root, session_root)
            else:
                # KNOWN LIMITATION: --by-files is pinned by the contract as a
                # comma-separated list, so a path that itself contains a comma
                # (legal on POSIX) is split into two names — inventing candidate
                # entries and destroying the real one. Changing the encoding
                # would change the frozen CLI surface; carried deliberately.
                hit = find_by_files(
                    [f for f in args.by_files.split(",") if f.strip()],
                    repo, repo_root, session_root,
                    args.candidate_sha or "", args.candidate_at or 0,
                )
            print(f"grudge: scanned={scanned} matched={1 if hit else 0}", file=sys.stderr)
            if hit:
                print(os.path.splitext(os.path.basename(hit["_path"]))[0])
            return 0
        except Exception as exc:  # noqa: BLE001 — any failure is exit 3, never a match
            print(f"grudge: lookup failed: {exc!r}", file=sys.stderr)
            return 3

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
