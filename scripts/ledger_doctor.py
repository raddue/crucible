#!/usr/bin/env python3
"""`ledger doctor` — on-demand consistency check for the calibration + grudge
stores (#400).

The calibration ledger is "the epistemic backbone": every reader degrades
SILENTLY on a torn / unparseable line, so a single corrupt write permanently and
invisibly degrades calibration accuracy and the grudge preflight — "the only
symptom is the advisory stopped showing up." `compass.py` already ships a
`doctor`; this is its analogue for the ledger and grudge stores, reporting
unparseable-line counts and #402 identity-less rows.

On-demand only — it gates NOTHING. Pure stdlib; reads the central machine-local
store by default (override via CRUCIBLE_LEDGER_DIR / --ledger-dir / --grudge-dir).

Exit codes (mirrors compass doctor): 0 = healthy, 1 = corruption found.
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts.ledger_append import default_ledger_dir, _valid_identity  # noqa: E402


# --------------------------------------------------------------------------- #
# PURE scanners (deterministic; unit-tested)                                  #
# --------------------------------------------------------------------------- #

def scan_jsonl(path: str, *, identity: bool = False) -> dict:
    """Scan a JSONL store. Returns counts WITHOUT mutating anything.

    Reads exactly as every production reader does (render_ledger.load_runs /
    ledger_reduce.reduce / reconcile_ledger.load_jsonl): BYTE mode, split on
    b"\\n", drop a partial trailing line (no terminating newline — crash-mid-
    append), skip only a TRULY empty chunk, and feed each remaining RAW chunk to
    json.loads. A whitespace-only chunk and an invalid-UTF-8 chunk therefore
    count as unparseable, exactly as the readers count them — the doctor's whole
    job is to surface the corruption the readers degrade silently on.

    Keys: exists, total (non-empty chunks scanned == parseable + unparseable),
    parseable, unparseable, and — when `identity` is set — identityless
    (parseable object rows lacking a valid (run_id, skill) join key, the #402
    collision risk). A non-object parseable chunk counts as unparseable (a store
    row must be a JSON object). A present-but-unreadable store (OSError on open/
    read — e.g. a directory or permission-denied) is reported as one unparseable
    line, NOT healthy: the doctor must be more honest than the readers, which
    swallow OSError.
    """
    rep = {"exists": False, "total": 0, "parseable": 0, "unparseable": 0,
           "identityless": 0}
    if not path or not os.path.exists(path):
        return rep
    rep["exists"] = True
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        # File exists but cannot be read (directory, permission-denied). The
        # readers return [] silently; the doctor surfaces it as corruption.
        rep["total"] += 1
        rep["unparseable"] += 1
        return rep
    if not raw:
        return rep
    parts = raw.split(b"\n")
    if not raw.endswith(b"\n"):
        # Last element is a partial trailing line (crash-mid-append) — drop it,
        # matching the readers.
        parts = parts[:-1]
    for chunk in parts:
        if not chunk:  # only a TRULY empty chunk is skipped (matches readers)
            continue
        rep["total"] += 1
        try:
            obj = json.loads(chunk)
        except (json.JSONDecodeError, UnicodeDecodeError):
            rep["unparseable"] += 1
            continue
        if not isinstance(obj, dict):
            rep["unparseable"] += 1
            continue
        rep["parseable"] += 1
        if identity and not (
            _valid_identity(obj.get("run_id"))
            and _valid_identity(obj.get("skill"))
        ):
            rep["identityless"] += 1
    return rep


def scan_brier(path: str) -> dict:
    """Scan brier-rolling.json. Keys: exists, ok (parses to a JSON object)."""
    rep = {"exists": False, "ok": False}
    if not path or not os.path.exists(path):
        return rep
    rep["exists"] = True
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        rep["ok"] = isinstance(data, dict)
    except (OSError, ValueError):
        rep["ok"] = False
    return rep


def scan_grudges(grudge_dir: str) -> dict:
    """Scan a grudge store directory of `*.md` files. Keys: exists, total,
    unparseable (files `grudge_query.parse_grudge` rejects)."""
    rep = {"exists": False, "total": 0, "unparseable": 0}
    if not grudge_dir or not os.path.isdir(grudge_dir):
        return rep
    rep["exists"] = True
    # Imported lazily: grudge_query pulls in grudge_append; keep doctor importable
    # even if the grudge subsystem is absent.
    try:
        from scripts.grudge_query import parse_grudge
    except Exception:  # noqa: BLE001 — grudge subsystem unavailable
        return rep
    for name in sorted(os.listdir(grudge_dir)):
        if not name.endswith(".md"):
            continue
        rep["total"] += 1
        if parse_grudge(os.path.join(grudge_dir, name)) is None:
            rep["unparseable"] += 1
    return rep


# --------------------------------------------------------------------------- #
# Report                                                                      #
# --------------------------------------------------------------------------- #

def _default_grudge_dir() -> "str | None":
    """Best-effort grudge store for the cwd's repo, or None if undeterminable
    (not in a git repo, grudge subsystem absent). Never raises."""
    try:
        from scripts.grudge_append import grudges_dir, resolve_repo
        repo, _repo_root = resolve_repo()
        return grudges_dir(repo)
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
    """Store identity basename for the cwd's repo (design §4.2/§8), or the
    worktree basename fallback. Never raises."""
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
    unreadable/absent file, mirroring scan_grudges; never raises."""
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
        # foreign-repo-only view still reads 0 line for repo "r".
        # STALE fixture -> the stuck session's LAST BLOCK flagged exactly once.
        s = scan_witness(stale_p, "r")
        assert [x[1] for x in s["flagged"]] == ["s-stuck"], f"STALE fixture: {s['flagged']}"
        # no-repo view counts all rows
        s_all = scan_witness(stale_p, None)
        assert [x[1] for x in s_all["flagged"]] == ["s-stuck"]
        print("selftest OK — witness reader flags a stale un-terminated BLOCK, "
              "ignores recent/superseded/terminal/foreign-repo rows")
        return 0


def doctor(ledger_dir: str, grudge_dir: "str | None") -> int:
    """Print the consistency report; return 0 healthy / 1 corruption found."""
    runs = scan_jsonl(os.path.join(ledger_dir, "runs.jsonl"), identity=True)
    fals = scan_jsonl(os.path.join(ledger_dir, "falsification.jsonl"))
    brier = scan_brier(os.path.join(ledger_dir, "brier-rolling.json"))
    grudges = scan_grudges(grudge_dir) if grudge_dir else {"exists": False}

    info, warnings, issues = [], [], []

    info.append(f"ledger-dir: {ledger_dir}")

    if not runs["exists"]:
        info.append("runs.jsonl — not present (no gating runs captured yet)")
    else:
        line = (f"runs.jsonl — {runs['parseable']}/{runs['total']} parseable")
        if runs["unparseable"]:
            issues.append(f"runs.jsonl: {runs['unparseable']} unparseable line(s)")
        else:
            info.append(line)
        if runs["identityless"]:
            warnings.append(
                f"runs.jsonl: {runs['identityless']} row(s) lack a valid "
                f"(run_id, skill) identity — skipped by consumers (#402)")

    if not fals["exists"]:
        info.append("falsification.jsonl — not present (reconciler not run yet)")
    elif fals["unparseable"]:
        issues.append(
            f"falsification.jsonl: {fals['unparseable']} unparseable line(s)")
    else:
        info.append(
            f"falsification.jsonl — {fals['parseable']}/{fals['total']} parseable")

    if not brier["exists"]:
        info.append("brier-rolling.json — not present (reconciler not run yet)")
    elif not brier["ok"]:
        issues.append("brier-rolling.json: corrupt or not a JSON object")
    else:
        info.append("brier-rolling.json — OK")

    if not grudges["exists"]:
        info.append("grudge store — not present / not resolvable")
    elif grudges["unparseable"]:
        issues.append(
            f"grudge store: {grudges['unparseable']}/{grudges['total']} "
            f"unparseable file(s)")
    else:
        info.append(f"grudge store — {grudges['total']} grudge(s), all parseable")

    print("=== ledger doctor ===")
    for line in info:
        print(f"  [ok] {line}")
    for line in warnings:
        print(f"  [warn] {line}")
    for line in issues:
        print(f"  [FAIL] {line}")
    if issues:
        print(f"  --- {len(issues)} issue(s) found ---")
    else:
        print("  --- healthy ---")
    return 1 if issues else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Consistency check for the calibration + grudge stores (#400).")
    parser.add_argument(
        "--ledger-dir", default=default_ledger_dir(),
        help="ledger store dir (default: central ~/.claude/crucible/ledger)")
    parser.add_argument(
        "--grudge-dir", default=None,
        help="grudge store dir of *.md files (default: derive from cwd repo)")
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

    grudge_dir = args.grudge_dir if args.grudge_dir is not None \
        else _default_grudge_dir()
    return doctor(args.ledger_dir, grudge_dir)


if __name__ == "__main__":
    sys.exit(main())
