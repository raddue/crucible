#!/usr/bin/env python3
"""Grudge append — record one bug into the cross-session Book of Grudges (#271).

A "grudge" is a structured record of a fixed bug. Every grudge is one markdown
file with YAML-ish frontmatter at
    <base>/<repo>/grudges/<hash>.md
where <base> = $CRUCIBLE_GRUDGE_DIR or ~/.claude/crucible/grudge — NEVER inside a
git working tree (grudges carry private file paths + repro detail and crucible is
a PUBLIC repo). This mirrors the calibration-ledger central-store decision (PR
#326).

Pure stdlib. No third-party deps.

Design fixes baked in (from the design adversarial gate):
- #2 dedupe key = sha256(repo_root | sorted-normalized(files_touched) | discriminator);
     discriminator = anti_pattern_signature if non-empty else symptom; commit NOT in key.
- #3 repo_root (git toplevel realpath) is the isolation key, also a hash input.
- #6 privacy guard: refuse to write into the current repo's tree.
"""
import datetime as _dt
import hashlib
import json
import os
import sys
from typing import List, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.atomic_write import atomic_write_text  # noqa: E402

SCHEMA_VERSION = 1


# --------------------------------------------------------------------------- #
# Path + repo resolution (shared with grudge_query via import).               #
# --------------------------------------------------------------------------- #
def default_base_dir() -> str:
    """Root of the grudgebook. A non-empty CRUCIBLE_GRUDGE_DIR wins (tests,
    fixtures); else ~/.claude/crucible/grudge — a ~-rooted path never inside a
    git working tree."""
    env = os.environ.get("CRUCIBLE_GRUDGE_DIR")
    if env:
        return env
    return os.path.join(os.path.expanduser("~"), ".claude", "crucible", "grudge")


def grudges_dir(repo: str, base_dir: Optional[str] = None) -> str:
    """Per-repo grudges directory: <base>/<repo>/grudges. <repo> is the cosmetic
    basename; isolation is enforced by repo_root filtering at read time."""
    base = base_dir if base_dir is not None else default_base_dir()
    return os.path.join(base, repo, "grudges")


# #605 / C-l: every git shell-out in the grudge subsystem runs git through this
# PATH+HOME-only allowlist, never the inherited process environment — git
# obeys repository-LOCATION variables (GIT_DIR, GIT_WORK_TREE, …) and
# config-transport variables (GIT_CONFIG_COUNT/KEY_n/VALUE_n,
# GIT_CONFIG_PARAMETERS, …) that outrank any `-C` argument, so a single
# inherited variable can silently retarget or misreport a query. A denylist
# cannot be complete (GIT_CONFIG_KEY_n is indexed); an allowlist only has to
# name what git genuinely needs: PATH (findable at all) and HOME (per-user
# config, where a legitimate `safe.directory` lives). Mirrors the hook's
# `env -i PATH HOME git` and grudge_query.py's `_git_env()`.
_GIT_ENV_KEEP = ("PATH", "HOME")


def _git_env() -> dict:
    import os as _os
    return {k: _os.environ[k] for k in _GIT_ENV_KEEP if k in _os.environ}


def resolve_repo(start_dir: Optional[str] = None) -> Tuple[str, str]:
    """(repo_basename, repo_root_realpath) for the repo the cwd is in. Shells to
    git via the PATH/HOME allowlist (#605/C-l); falls back to the realpath of
    start_dir/cwd when not in a git repo. Never raises. CLI-only (git side
    effect). FILESYSTEM identity — the worktree."""
    base = start_dir or os.getcwd()
    try:
        import subprocess
        proc = subprocess.run(
            ["git", "-C", base, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5, env=_git_env(),
        )
        top = proc.stdout.strip()
        if proc.returncode == 0 and top:
            root = os.path.realpath(top)
            return (os.path.basename(root.rstrip("/")) or root, root)
    except Exception:  # noqa: BLE001 — best-effort, never fatal
        pass
    root = os.path.realpath(os.path.abspath(base))
    return (os.path.basename(root) or "unknown", root)


def resolve_store_repo(start_dir: Optional[str] = None) -> Tuple[str, str]:
    """(repo_basename, store_root) — the STORE identity for the repo at
    start_dir: the git-common-dir parent, RESOLVED AGAINST start_dir (never
    the process cwd — SIEGE-R2-M8: git returns `--git-common-dir` relative to
    its `-C` directory for an ordinary clone), when that resolved path's final
    component is '.git' AND its own parent is not itself literally named
    'modules' (SIEGE-R2-M7 — a submodule's common-dir is
    `<super>/.git/modules/<name>`, whose parent `modules` is excluded so a
    submodule an attacker names `.git` cannot defeat the discriminator, and
    sibling submodules do not collide); otherwise falls back to
    `resolve_repo()` — the worktree root — and records that the fallback fired
    (submodule, bare repo, or an unresolvable common-dir) via a WARN.

    Distinct from `resolve_repo()` (FILESYSTEM identity = `--show-toplevel`,
    the worktree). Never used for filesystem existence checks. Invokes git via
    the same PATH/HOME allowlist (#605/C-l)."""
    base = start_dir or os.getcwd()
    try:
        import subprocess
        proc = subprocess.run(
            ["git", "-C", base, "rev-parse", "--git-common-dir"],
            capture_output=True, text=True, timeout=5, env=_git_env(),
        )
        common = proc.stdout.strip()
        if proc.returncode == 0 and common:
            # Resolve the R E L A T I V E common-dir against start_dir, not the
            # process cwd (SIEGE-R2-M8): `ledger_doctor`/`brier_advisory` call
            # in with a start_dir that differs from cwd.
            resolved = common if os.path.isabs(common) \
                else os.path.realpath(os.path.join(base, common))
            if os.path.basename(resolved) == ".git" \
                    and os.path.basename(os.path.dirname(resolved)) != "modules":
                parent = os.path.dirname(resolved)
                return (os.path.basename(parent) or parent, parent)
    except Exception:  # noqa: BLE001 — best-effort, never fatal
        pass
    _warn("resolve_store_repo: store-identity discriminator failed — fell back "
          "to resolve_repo()'s worktree root (submodule, bare repo, or an "
          "unresolvable git-common-dir)")
    return resolve_repo(base)


def normalize_path(p: str, repo_root: str) -> str:
    """Normalize a path to repo-relative POSIX form (fix #1): forward-slashes,
    made relative to repo_root when absolute, no leading './', no trailing '/'."""
    p = p.replace("\\", "/").strip()
    if os.path.isabs(p) or p.startswith(repo_root):
        try:
            p = os.path.relpath(p, repo_root).replace("\\", "/")
        except ValueError:  # different drive on Windows — leave as-is
            pass
    while p.startswith("./"):
        p = p[2:]
    return p.rstrip("/")


def _discriminator(symptom: str, signature: Optional[str]) -> str:
    sig = (signature or "").strip()
    if sig:
        return sig
    sym = (symptom or "").strip()
    return sym


def compute_hash(repo_root: str, files_norm: List[str], discriminator: str) -> str:
    key = repo_root + "|" + "\n".join(sorted(files_norm)) + "|" + (discriminator or "")
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def _warn(msg: str) -> None:
    print(f"[grudge_append WARN] {msg}", file=sys.stderr)


def _is_inside(child: str, parent: str) -> bool:
    """True if realpath(child) is at or under realpath(parent)."""
    c = os.path.realpath(child)
    p = os.path.realpath(parent)
    try:
        return os.path.commonpath([c, p]) == p
    except ValueError:  # different drives
        return False


# --------------------------------------------------------------------------- #
# Serialization                                                               #
# --------------------------------------------------------------------------- #
def _render(record: dict) -> str:
    """Render a grudge to markdown. Frontmatter is simple `key: value` lines;
    files_touched is a JSON array on one line so the reader can json.loads it
    without a YAML dependency."""
    fm = [
        "---",
        f"schema: {SCHEMA_VERSION}",
        f"hash: {record['hash']}",
        f"repo: {record['repo']}",
        f"repo_root: {record['repo_root']}",
        f"fixed_in_commit: {record.get('fixed_in_commit', '') or ''}",
        f"symptom: {record.get('symptom', '') or ''}",
        f"root_cause: {record.get('root_cause', '') or ''}",
        f"files_touched: {json.dumps(record.get('files_touched', []))}",
        f"anti_pattern_signature: {json.dumps(record.get('anti_pattern_signature', '') or '')}",
        f"date_fixed: {record.get('date_fixed', '') or ''}",
        "---",
        "## Repro",
        (record.get("repro") or "").rstrip(),
        "",
        "## Why this kept happening",
        (record.get("why") or "").rstrip(),
        "",
    ]
    return "\n".join(fm)


def append(
    *,
    symptom: str,
    root_cause: str = "",
    files_touched: List[str],
    anti_pattern_signature: str = "",
    fixed_in_commit: str = "",
    repro: str = "",
    why: str = "",
    repo: str,
    repo_root: str,
    base_dir: Optional[str] = None,
    date_fixed: Optional[str] = None,
) -> Optional[str]:
    """Record (write/overwrite) one grudge. Returns the file path, or None if the
    write was refused/skipped. Overwrite-on-same-key (last write wins) — NOT the
    ledger's append-only-skip model (stated honestly per fix #2)."""
    files_norm = sorted({normalize_path(f, repo_root) for f in (files_touched or []) if f and f.strip()})
    if not files_norm:
        _warn("no files_touched — grudge needs at least one file to hold a grudge against; skipped")
        return None

    disc = _discriminator(symptom, anti_pattern_signature)
    if not disc:
        _warn("empty discriminator (no anti_pattern_signature and no symptom) — nothing to key on; skipped")
        return None

    target_dir = grudges_dir(repo, base_dir)

    # Privacy guard (fix #6): never write the live store into the repo we're in.
    if _is_inside(target_dir, repo_root):
        _warn(
            f"refusing to write grudges into the repo tree ({target_dir} is inside "
            f"{repo_root}); grudges carry private paths and must live outside any repo. "
            f"Unset/relocate CRUCIBLE_GRUDGE_DIR."
        )
        return None

    h = compute_hash(repo_root, files_norm, disc)
    record = {
        "hash": h,
        "repo": repo,
        "repo_root": repo_root,
        "fixed_in_commit": fixed_in_commit or "",
        "symptom": (symptom or "").strip(),
        "root_cause": (root_cause or "").strip(),
        "files_touched": files_norm,
        "anti_pattern_signature": (anti_pattern_signature or "").strip(),
        "date_fixed": date_fixed or _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d"),
        "repro": repro,
        "why": why,
    }
    os.makedirs(target_dir, exist_ok=True)
    path = os.path.join(target_dir, f"{h}.md")
    # #400: overwrite-on-key is idempotent (content is deterministic by hash),
    # so parallel same-key writers race on this path. Atomic replace makes that
    # safe — last full file wins, no reader ever sees a truncated grudge.
    atomic_write_text(path, _render(record))
    return path


def _read_files_from(path: str) -> List[str]:
    """Read a NUL-delimited path list (the `$STATE_DIR/<sha>.files` artifact,
    DEC-5). Python reads the file itself — the shell never re-tokenizes its
    contents — so every byte a path can hold (TAB, LF, comma, backtick) comes
    through unchanged. Invalid UTF-8 round-trips via surrogateescape."""
    with open(path, "rb") as fh:
        data = fh.read()
    return [p.decode("utf-8", "surrogateescape") for p in data.split(b"\0") if p]


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
def _main(argv: List[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Record a grudge (fixed bug) into the Book of Grudges.")
    ap.add_argument("--symptom", required=True)
    ap.add_argument("--root-cause", default="")
    # Repeatable, EQUALS-form: --files=PATH one per touched path. A value is a
    # single argv element, so a comma in a filename is data, not a delimiter,
    # and a value beginning with `-` stays inert (C-m, DEC-5/#568).
    ap.add_argument("--files", action="append", metavar="PATH",
                    help="a touched file (repeatable: one --files= per path)")
    ap.add_argument("--files-from", dest="files_from", default=None, metavar="PATH",
                    help="NUL-delimited file of touched paths (the hook's paste-me remedy)")
    ap.add_argument("--signature", default="", help="anti_pattern_signature (regex or literal snippet)")
    ap.add_argument("--commit", dest="fixed_in_commit", default="",
                    help="fixed_in_commit SHA")
    ap.add_argument("--candidate-sha", dest="fixed_in_commit", default="",
                    help="alias for --commit (hook paste-me form)")
    ap.add_argument("--repro", default="")
    ap.add_argument("--why", default="")
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

    if args.files_from:
        files = _read_files_from(args.files_from)
    else:
        files = list(args.files or [])
    files = [f for f in files if f and f.strip()]
    path = append(
        symptom=args.symptom, root_cause=args.root_cause, files_touched=files,
        anti_pattern_signature=args.signature, fixed_in_commit=args.fixed_in_commit,
        repro=args.repro, why=args.why, repo=repo, repo_root=repo_root,
    )
    if path:
        print(path)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
