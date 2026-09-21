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

def _walk_up_git_root(base: str) -> Optional[str]:
    """Env-free repo-root detector: walk up from `base` looking for a `.git`
    entry (a dir in a normal clone, a file in a worktree/submodule). Returns the
    realpath of the containing dir, or None when no `.git` is found."""
    cur = os.path.realpath(os.path.abspath(base))
    while True:
        if os.path.exists(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def resolve_repo(start_dir: Optional[str] = None) -> Tuple[str, str]:
    """(repo_basename, repo_root_realpath) for the repo the cwd is in. Shells to
    git; if that fails, walks up for a `.git` entry; falls back to the realpath
    of start_dir/cwd only when neither finds a repo.
    Never raises. CLI-only (git side effect)."""
    base = start_dir or os.getcwd()
    try:
        import subprocess
        # #605 (siege S-3): run git under an ALLOWLIST env, never the inherited
        # one. Hooks export GIT_DIR/GIT_WORK_TREE; with no env= those leak in
        # and steer which repo git reports — the store dir, the repo_root
        # isolation key, and the privacy-guard check all follow the WRONG repo.
        # A denylist can't work (GIT_CONFIG_KEY_n is indexed, no finite set), so
        # keep only what git needs: PATH (find git) + HOME (read ~/.gitconfig).
        keep = ("PATH", "HOME")
        env = {k: os.environ[k] for k in keep if k in os.environ}
        proc = subprocess.run(
            ["git", "-C", base, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5, env=env,
        )
        top = proc.stdout.strip()
        if proc.returncode == 0 and top:
            root = os.path.realpath(top)
            return (os.path.basename(root.rstrip("/")) or root, root)
    except Exception:  # noqa: BLE001 — best-effort, never fatal
        pass
    # #605 (follow-up): the allowlist above makes the git call newly FAILABLE in
    # legitimate setups (config reachable only via GIT_CONFIG_GLOBAL/XDG_CONFIG_HOME,
    # a Windows box needing SystemRoot/PATHEXT, git off PATH). Falling straight
    # through to cwd would report a SUBDIR as the repo root — and then the
    # privacy guard in append() compares the store dir against that too-narrow
    # root and happily writes the private store INTO the repo tree, which is the
    # exact leak #605 closed, reached via a silent git failure instead. So try an
    # env-free walk-up first; bare cwd is only for a genuine non-repo dir.
    walked = _walk_up_git_root(base)
    if walked is not None:
        _warn(
            f"git rev-parse failed under the allowlist env (PATH+HOME) but {base} is "
            f"inside a git repo; using the walked-up root {walked}. Grudge dedupe keys "
            f"and the privacy guard depend on this root being the real toplevel."
        )
        return (os.path.basename(walked.rstrip("/")) or walked, walked)
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
    # #607 (siege S-8): only Windows treats backslash as a path separator. On
    # POSIX it is a legal filename byte — git stores it verbatim (diff-tree -z),
    # so rewriting it to '/' stores a DIFFERENT non-existent path, voiding the
    # grudge; --cull then permanently deletes it. Rewrite only on Windows.
    _windows = os.name == "nt"
    p = p.replace("\\", "/") if _windows else p
    p = p.strip()
    if os.path.isabs(p) or p.startswith(repo_root):
        try:
            p = os.path.relpath(p, repo_root)
            if _windows:
                p = p.replace("\\", "/")
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
    """Render a grudge to markdown. Every frontmatter value is JSON-encoded on
    one line (#602 S-0): fields are written through the writer alone, never
    copied, so a value cannot smuggle a bare `---` terminator or forged
    `key: value` lines past the fence — the reader's `key: value` parsing can
    then never see attacker-injected keys. This is why the writer-side escape
    closes the class the reader's key-set validation cannot: forged keys are
    all *known* keys, so allowlisting the reader is not enough alone."""
    fm = [
        "---",
        f"schema: {SCHEMA_VERSION}",
        f"hash: {record['hash']}",
        f"repo: {json.dumps(record['repo'])}",
        f"repo_root: {json.dumps(record['repo_root'])}",
        f"fixed_in_commit: {json.dumps(record.get('fixed_in_commit', '') or '')}",
        f"symptom: {json.dumps(record.get('symptom', '') or '')}",
        f"root_cause: {json.dumps(record.get('root_cause', '') or '')}",
        f"files_touched: {json.dumps(record.get('files_touched', []))}",
        f"anti_pattern_signature: {json.dumps(record.get('anti_pattern_signature', '') or '')}",
        f"date_fixed: {json.dumps(record.get('date_fixed', '') or '')}",
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
    store_root: str,
    worktree_root: Optional[str] = None,
    base_dir: Optional[str] = None,
    date_fixed: Optional[str] = None,
) -> Optional[str]:
    """Record (write/overwrite) one grudge. Returns the file path, or None if the
    write was refused/skipped. Overwrite-on-same-key (last write wins) — NOT the
    ledger's append-only-skip model (stated honestly per fix #2).

    DEC-4 / §4.2: store identity and filesystem identity are DIFFERENT concepts
    (S5 / siege S-2 — one root cannot serve both once they diverge in a linked
    worktree). `store_root` (git-common-dir parent) feeds compute_hash() and the
    recorded `repo_root` frontmatter field; `worktree_root` (--show-toplevel),
    defaulting to `store_root` for the ordinary-clone case, feeds normalize_path()
    and the fix-#6 privacy guard. The guard refuses when the target is inside
    EITHER root (SIEGE-R2-H7): a store placed inside the main clone is caught
    even when recording from a linked worktree whose own worktree_root is not a
    parent of it."""
    worktree_root = worktree_root or store_root
    files_norm = sorted({normalize_path(f, worktree_root) for f in (files_touched or []) if f and f.strip()})
    if not files_norm:
        _warn("no files_touched — grudge needs at least one file to hold a grudge against; skipped")
        return None

    disc = _discriminator(symptom, anti_pattern_signature)
    if not disc:
        _warn("empty discriminator (no anti_pattern_signature and no symptom) — nothing to key on; skipped")
        return None

    target_dir = grudges_dir(repo, base_dir)

    # Privacy guard (fix #6, SIEGE-R2-H7): never write the live store into ANY
    # git working tree the write could reach — the worktree the recording runs
    # from, OR the store identity's main clone (public, tracked). With a single
    # root, a store under the main clone escaped the guard when recording from a
    # linked worktree (its worktree_root is not a parent of the main clone).
    if _is_inside(target_dir, worktree_root) or _is_inside(target_dir, store_root):
        _warn(
            f"refusing to write grudges into the repo tree ({target_dir} is inside "
            f"{worktree_root} or {store_root}); grudges carry private paths and must "
            f"live outside any repo. Unset/relocate CRUCIBLE_GRUDGE_DIR."
        )
        return None

    h = compute_hash(store_root, files_norm, disc)
    record = {
        "hash": h,
        "repo": repo,
        "repo_root": store_root,
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
    ap.add_argument("--repo-root", default=None,
                    help="override STORE identity realpath (git-common-dir "
                    "parent; tests / explicit store identity)")
    ap.add_argument("--worktree-root", default=None,
                    help="override FILESYSTEM identity realpath "
                    "(--show-toplevel; defaults to resolve_repo())")
    ap.add_argument("--repo", default=None, help="override repo basename (tests)")
    args = ap.parse_args(argv)

    if args.repo_root:
        store_root = os.path.realpath(args.repo_root)
        repo = args.repo or os.path.basename(store_root) or "unknown"
    else:
        repo, store_root = resolve_store_repo()
        if args.repo:
            repo = args.repo
    worktree_root = None
    if args.worktree_root:
        worktree_root = os.path.realpath(args.worktree_root)
    else:
        # --worktree-root defaults to the filesystem root the recording runs
        # from (resolve_repo), NOT store_root — the two diverge in a linked
        # worktree and normalize_path must see the worktree (T-w, DEC-4).
        _basename, worktree_root = resolve_repo()
        # resolve_repo() silently falls back to the realpath of cwd when cwd is
        # NOT in a git work tree. A non-git cwd carries no filesystem identity:
        # trusting that path makes the two-root guard refuse a store that merely
        # sits under an unrelated parent (an explicit --repo-root caller like
        # test_558_559_acceptance, cwd = a tmp dir). Steady default: the store
        # identity itself, the old single-root semantics.
        import subprocess as _core_sp
        _in_tree = _core_sp.run(
            ["git", "-C", os.getcwd(), "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, timeout=5, env=_git_env(),
        ).returncode == 0
        if not _in_tree:
            worktree_root = store_root
    if args.files_from:
        files = _read_files_from(args.files_from)
    else:
        files = list(args.files or [])
    files = [f for f in files if f and f.strip()]
    path = append(
        symptom=args.symptom, root_cause=args.root_cause, files_touched=files,
        anti_pattern_signature=args.signature, fixed_in_commit=args.fixed_in_commit,
        repro=args.repro, why=args.why, repo=repo, store_root=store_root,
        worktree_root=worktree_root,
    )
    if path:
        print(path)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
