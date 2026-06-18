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
    args = parser.parse_args(argv)

    grudge_dir = args.grudge_dir if args.grudge_dir is not None \
        else _default_grudge_dir()
    return doctor(args.ledger_dir, grudge_dir)


if __name__ == "__main__":
    sys.exit(main())
