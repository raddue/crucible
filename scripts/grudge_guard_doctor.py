#!/usr/bin/env python3
"""grudge-guard doctor — consistency + identity checks for the grudge subsystem.

Two on-demand readers, both pure-stdlib, both gating NOTHING:

1. **--grudge-guard** (R5, design §5b): the read side of the Stop hook's
   write-ONLY outcome witness at <witness-dir>/outcomes.tsv. The hook never
   reads that file (C-h); this is its only consumer. It flags a possibly-STUCK
   stop hook: a session whose last recorded outcome is a `BLOCK` older than the
   age threshold with no terminal `CLEARED`/`GIVEUP` and no later `BLOCK` for
   the same session.

2. **--grudge-keys / --migrate-store-keys** (R3, design §4.3, criterion 9):
   reports STORE-keyed vs WORKTREE-keyed grudges (non-zero exit when
   worktree-keyed records exist), and migrates worktree-keyed records into the
   store identity (directory AND the `repo_root` frontmatter field). The hook's
   dual-key `_worktree_fallback` stays active until this reports zero on the
   machines that run it.

History: this subsystem lived in `scripts/ledger_doctor.py` until origin/dev
moved the calibration-ledger reporting cluster to raddue/crucible-eval
(#460/#569). The grudge-guard responsibilities (which the #558/#559 plan places
here) were re-homed into this file so the PR adds code instead of resurrecting a
deleted host.

Exit codes: 0 = healthy, 1 = issue found. `--selftest` runs the witness reader's
synthetic-fixture self-test (design §9 T-o vs a fixture, never live $HOME state).
"""
import argparse
import os
import sys
import time

# Root at the repo (scripts.X package), matching the grudge subsystem files.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# --------------------------------------------------------------------------- #
# R3 store-identity detector + migration (design §4.3, criterion 9).          #
# --------------------------------------------------------------------------- #
# DEFS: a grudge is STORE-keyed iff its recorded frontmatter `repo_root`
# equals the cwd repo's STORE identity (git-common-dir parent, shared across
# worktrees); it is WORKTREE-keyed iff that field records a filesystem root
# that differs — a record captured before DEC-4, whose isolation key would
# change when the recording worktree is removed / re-cloned, and which a
# store-identity reader cannot find. Criterion 9: `_worktree_fallback` in the
# hook is kept — and the dual-key read may only be DELETED later, gated on
# this detector reporting ZERO worktree-keyed records on the machines that
# run it. `--migrate-store-keys` performs the non-destructive move (directory
# AND the `repo_root` frontmatter field — moving the dir alone is not a
# migration, load_grudges filters on that field) and prints what it moved.


def _frontmatter_value(path: str, key: str) -> "str | None":
    """Value of one `key: value` frontmatter line, or None."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for ln in fh:
                line = ln.rstrip("\n")
                if line == "---":
                    continue
                if line.startswith("## "):
                    return None
                if line.startswith(key + ":"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        return None
    return None


def scan_grudge_store_keys(grudge_base: "str | None", store_repo: "str | None",
                           store_root: "str | None") -> dict:
    """Classify every grudge under grudge_base by identity key. Returns
    {store_keyed: [path...], worktree_keyed: [(path, recorded_root)...]}."""
    rep = {"store_keyed": [], "worktree_keyed": []}
    if store_root is None or not grudge_base or not os.path.isdir(grudge_base):
        return rep
    sroot = os.path.realpath(store_root)
    for key in sorted(os.listdir(grudge_base)):
        grudges = os.path.join(grudge_base, key, "grudges")
        if not os.path.isdir(grudges):
            continue
        for name in sorted(os.listdir(grudges)):
            if not name.endswith(".md"):
                continue
            p = os.path.join(grudges, name)
            recorded = _frontmatter_value(p, "repo_root")
            if recorded is not None and os.path.realpath(recorded) == sroot:
                rep["store_keyed"].append(p)
            else:
                rep["worktree_keyed"].append((p, recorded))
    return rep


def _rewrite_repo_root(text: str, new_root: str) -> str:
    """Replace the frontmatter `repo_root:` value; leave every other byte and
    the body untouched."""
    out = []
    in_fm = False
    for ln in text.splitlines(keepends=True):
        if ln.rstrip("\n") == "---":
            in_fm = not in_fm
            out.append(ln)
        elif in_fm and ln.startswith("repo_root:"):
            out.append(f"repo_root: {new_root}\n")
        else:
            out.append(ln)
    return "".join(out)


def migrate_grudge_store_keys(grudge_base: "str | None", store_repo: "str | None",
                              store_root: "str | None") -> list:
    """Move worktree-keyed grudges into the store identity (directory + the
    `repo_root` frontmatter), returning a list of (src, dst, new_root) moves.
    Non-destructive: a rewrite failure aborts THAT file (left in place)."""
    moved: list = []
    if store_repo is None or store_root is None or not grudge_base:
        return moved
    base = grudge_base
    scan = scan_grudge_store_keys(base, store_repo, store_root)
    store_dir = os.path.join(base, store_repo, "grudges")
    sroot = os.path.realpath(store_root)
    for p, recorded in scan["worktree_keyed"]:
        try:
            with open(p, "r", encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        rewritten = _rewrite_repo_root(text, sroot)
        if rewritten == text and p.startswith(os.path.join(base, store_repo)):
            continue  # already store-identity; nothing to migrate
        os.makedirs(store_dir, exist_ok=True)
        name = os.path.basename(p)
        dst = os.path.join(store_dir, name)
        if os.path.abspath(dst) == os.path.abspath(p):
            if rewritten == text:
                continue
            try:
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(rewritten)
            except OSError:
                continue
            moved.append((p, p, sroot))
            continue
        tmp = dst + ".migrating"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(rewritten)
            os.replace(tmp, dst)
            os.remove(p)
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass
            continue
        moved.append((p, dst, sroot))
    return moved


def report_grudge_store_keys(grudge_base: "str | None", store_repo: "str | None",
                             store_root: "str | None") -> int:
    """Print the detector report; 0 = zero worktree-keyed records (the
    criterion-9 precondition), 1 = worktree-keyed records found."""
    scan = scan_grudge_store_keys(grudge_base, store_repo, store_root)
    print("=== grudge store identity ===")
    print(f"  store-keyed:   {len(scan['store_keyed'])}")
    print(f"  worktree-keyed: {len(scan['worktree_keyed'])}")
    for p, recorded in scan["worktree_keyed"]:
        print(f"  [FAIL] {p}  (repo_root={recorded!r})")
    if scan["worktree_keyed"]:
        print("  --- worktree-keyed records found — run --migrate-store-keys to "
              "move them into the store identity; the hook's dual-key "
              "_worktree_fallback stays active until this reports zero "
              "(criterion 9) ---")
        return 1
    print("  [ok] zero worktree-keyed records — a clean store identity")
    return 0


def _store_identity():
    """(repo_basename, store_root) from resolve_store_repo (C-l allowlisted),
    or (None, None) when the subsystem is absent / not a repo."""
    try:
        from scripts.grudge_append import resolve_store_repo
        repo, root = resolve_store_repo()
        return repo, root
    except Exception:  # noqa: BLE001 — best-effort
        return None, None


def _grudge_base():
    try:
        from scripts.grudge_append import default_base_dir
        return default_base_dir()
    except Exception:  # noqa: BLE001 — best-effort
        return None


# --------------------------------------------------------------------------- #
# R5 outcome-witness reader (design §5b): the grudge-guard detector.          #
# --------------------------------------------------------------------------- #
# The Stop hook writes a write-ONLY outcome witness at
# <witness-dir>/outcomes.tsv, one TSV row per decision:
#   <epoch>\t<session-id>\t<repo-basename>\t<outcome>\t<nonce-or-->
#   outcome ∈ BLOCK | GIVEUP | CLEARED | DEGRADE:<reason-code>
# This reader is the ONLY consumer; the hook never reads the file (C-h). It
# detects a possibly-STUCK stop hook: a session whose LAST record is a `BLOCK`
# older than the age threshold with no later terminal line (`GIVEUP`/`CLEARED`)
# and no later `BLOCK` for the same session. A session that just ends after a
# nag (closed terminal, Ctrl-C, /clear, or answered in a later session) is the
# guard's ordinary outcome — a recent or superseded BLOCK is not flagged (§5b.2).
DEFAULT_WITNESS_DIR = os.path.join(
    os.path.expanduser("~"), ".claude", "crucible", "grudge-guard")
WITNESS_AGE_HOURS = 24
_BLOCK = "BLOCK"


def default_witness_dir() -> str:
    env = os.environ.get("CRUCIBLE_GRUDGE_GUARD_WITNESS_DIR")
    return env if env else DEFAULT_WITNESS_DIR


def _repo_basename():
    """Store identity basename for the cwd's repo (design §4.2/§8), or None.
    Never raises."""
    try:
        from scripts.grudge_append import resolve_store_repo
        repo, _root = resolve_store_repo()
        return repo
    except Exception:  # noqa: BLE001 — best-effort
        return None


def scan_witness(witness_path: str, repo: "str | None", *,
                 age_hours: int = WITNESS_AGE_HOURS) -> dict:
    """Scan the outcome witness for the given repo. Returns counts + flagged
    (epoch_s, session_id) pairs for possibly-stuck sessions. {} shapes on an
    unreadable/absent file; never raises."""
    rep = {"exists": False, "total": 0, "parseable": 0, "unparseable": 0,
           "flagged": []}
    if not witness_path or not os.path.isfile(witness_path):
        return rep
    rep["exists"] = True
    try:
        with open(witness_path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        rep["total"] += 1
        rep["unparseable"] += 1
        return rep
    now = time.time()
    cutoff = now - age_hours * 3600
    by_session = {}
    for ln in lines:
        rep["total"] += 1
        parts = ln.split("\t")
        if len(parts) != 5:
            rep["unparseable"] += 1
            continue
        epoch_s, session, repo_b, outcome, _nonce = parts
        try:
            epoch = float(epoch_s)
        except ValueError:
            rep["unparseable"] += 1
            continue
        if repo is not None and repo_b != repo:
            continue
        rep["parseable"] += 1
        by_session.setdefault(session, []).append((epoch, outcome))
    for session, recs in by_session.items():
        epoch, outcome = max(recs, key=lambda r: r[0])
        if outcome == _BLOCK and epoch < cutoff:
            rep["flagged"].append((int(epoch), session))
    rep["flagged"].sort(reverse=True)
    return rep


def grudge_guard(witness_dir: str, repo: "str | None",
                 age_hours: int = WITNESS_AGE_HOURS) -> int:
    """Report the outcome witness for `repo`. Return 0 healthy / 1 issues
    found (a possible stuck stop hook)."""
    w = scan_witness(os.path.join(witness_dir, "outcomes.tsv"), repo,
                     age_hours=age_hours)
    print("=== grudge-guard witness ===")
    print(f"  witness-dir: {witness_dir}")
    if repo:
        print(f"  repo: {repo}")
    if not w["exists"]:
        print("  [info] no outcome witness recorded yet for this repo — the "
              "stop hook has not blocked / retired a fix(*) group here")
        return 0
    print(f"  outcomes.tsv — {w['parseable']}/{w['total']} parseable "
          f"line(s) for {repo or 'any repo'}")
    if w["unparseable"]:
        print(f"  [FAIL] {w['unparseable']} unparseable line(s)")
    if w["flagged"]:
        import datetime as _dt
        for epoch_s, session in w["flagged"]:
            when = _dt.datetime.fromtimestamp(epoch_s, _dt.timezone.utc).strftime(
                "%Y-%m-%d %H:%M UTC")
            print(f"  [FAIL] session {session!r}: last outcome is a BLOCK at "
                  f"{when} (>{age_hours}h ago) with no terminal CLEARED/GIVEUP "
                  f"and no later BLOCK — the grudge guard may be stuck mid-nag "
                  f"for this session (stop hook stopped enforcing)")
    else:
        print("  [ok] no stale un-terminated session")
    if w["flagged"] or w["unparseable"]:
        print(f"  --- {len(w['flagged'])} stale session(s), "
              f"{w['unparseable']} unparseable line(s) found ---")
        return 1
    print("  --- healthy ---")
    return 0


def _go_selftest() -> int:
    """T-o behaviour over synthetic fixtures: a stale un-terminated BLOCK is
    flagged; a recent BLOCK, a superseded (later-BLOCK) BLOCK, a terminal-line
    session, and a foreign-repo line are not. Pure stdlib, no real state."""
    now = int(time.time())
    hour = 3600
    row = "{e}\t{ses}\t{repo}\t{out}\t{n}"
    def mk(lines):
        return "\n".join(lines) + "\n"

    good = [
        row.format(e=now - 48 * hour, ses="s-normal", repo="r", out="BLOCK", n="ab" * 8),
        row.format(e=now - 47 * hour, ses="s-normal", repo="r", out="CLEARED", n="-"),
        row.format(e=now - 2 * hour, ses="s-recent", repo="r", out="BLOCK", n="cd" * 8),
        row.format(e=now - 60 * hour, ses="s-superseded", repo="r", out="BLOCK", n="ef" * 8),
        row.format(e=now - 2 * hour, ses="s-superseded", repo="r", out="BLOCK", n="ff" * 8),
        row.format(e=now - 100 * hour, ses="s-other", repo="other", out="BLOCK", n="11" * 8),
    ]
    stale = [
        row.format(e=now - 100 * hour, ses="s-stuck", repo="r", out="BLOCK", n="12" * 8),
        row.format(e=now - 99 * hour + 1, ses="s-stuck", repo="r", out="BLOCK", n="13" * 8),
    ]
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        good_p = os.path.join(tmp, "good.tsv")
        stale_p = os.path.join(tmp, "stale.tsv")
        with open(good_p, "w", encoding="utf-8") as fh:
            fh.write(mk(good))
        with open(stale_p, "w", encoding="utf-8") as fh:
            fh.write(mk(stale))
        # GOOD fixture (repo "r", recent/terminal/superseded/foreign only) ->
        # nothing flagged; foreign-repo line excluded.
        g = scan_witness(good_p, "r")
        assert g["flagged"] == [], f"GOOD fixture flagged: {g['flagged']}"
        assert g["parseable"] == 5, f"GOOD parseable got {g['parseable']} (foreign repo excluded)"
        # STALE fixture -> the stuck session's LAST BLOCK flagged exactly once.
        s = scan_witness(stale_p, "r")
        assert [x[1] for x in s["flagged"]] == ["s-stuck"], f"STALE fixture: {s['flagged']}"
        # no-repo view counts all rows
        s_all = scan_witness(stale_p, None)
        assert [x[1] for x in s_all["flagged"]] == ["s-stuck"]
        print("selftest OK — witness reader flags a stale un-terminated BLOCK, "
              "ignores recent/superseded/terminal/foreign-repo rows")
        return 0


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Consistency + identity checks for the grudge subsystem.")
    parser.add_argument(
        "--grudge-guard", action="store_true",
        help="#558/§5b: report the cwd repo's grudge-guard outcome witness "
             "(a possibly-STUCK stop hook is a blocking finding)")
    parser.add_argument(
        "--witness-dir", default=None,
        help="grudge-guard outcome-witness dir (default: CRUCIBLE_GRUDGE_GUARD_"
             "WITNESS_DIR or ~/.claude/crucible/grudge-guard)")
    parser.add_argument(
        "--witness-age-hours", type=int, default=WITNESS_AGE_HOURS,
        help="stale threshold for an un-terminated BLOCK (default: 24)")
    parser.add_argument(
        "--repo", default=None,
        help="#558/§5b: repo-basename the --grudge-guard filter uses "
             "(default: cwd's store identity)")
    parser.add_argument(
        "--grudge-keys", action="store_true",
        help="#580/§4.3: report STORE-keyed vs WORKTREE-keyed grudges; non-zero "
             "exit when worktree-keyed records exist (criterion 9 pre-gate)")
    parser.add_argument(
        "--migrate-store-keys", action="store_true",
        help="#580/§4.3: move worktree-keyed grudges into the store identity "
             "(directory + repo_root frontmatter), printing what was moved")
    parser.add_argument(
        "--selftest", action="store_true",
        help="#558/§5b: run the witness reader's synthetic-fixture self-test")
    args = parser.parse_args(argv)

    if args.grudge_guard:
        if args.selftest:
            return _go_selftest()
        repo = args.repo
        if repo is None:
            repo = _repo_basename()
        return grudge_guard(
            args.witness_dir if args.witness_dir is not None
            else default_witness_dir(),
            repo, age_hours=args.witness_age_hours)

    if args.grudge_keys or args.migrate_store_keys:
        store_repo, store_root = _store_identity()
        base = _grudge_base()
        if args.migrate_store_keys:
            moved = migrate_grudge_store_keys(base, store_repo, store_root)
            print("=== grudge store migration ===")
            if not moved:
                print("  [ok] nothing to migrate — zero worktree-keyed records")
            for src, dst, new_root in moved:
                where = "rewrote repo_root in-place" if src == dst else \
                    f"moved to {dst}"
                print(f"  {src} -> {where}  (repo_root -> {new_root})")
            return report_grudge_store_keys(base, store_repo, store_root)
        return report_grudge_store_keys(base, store_repo, store_root)

    parser.error("one of --grudge-guard / --grudge-keys / --migrate-store-keys "
                 "is required")
    return 2  # unreachable


if __name__ == "__main__":
    sys.exit(main())