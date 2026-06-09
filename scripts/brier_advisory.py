#!/usr/bin/env python3
"""Brier calibration advisory (#270, Epistemics Phase 6).

Consumer-side reader of the calibration signal the Phase 4 reconciler writes
(`brier-rolling.json` + `falsification.jsonl` in the central store). Two thin
CLI entry points the gating skills invoke:

  advisory <skill>   -> per-skill Brier advisory line (QG / siege gate entry)
  stale-check        -> reconciliation-staleness line (getting-started session init)

Architecture (binding, mirrors reconcile_ledger.py / render_ledger.py):
  - PURE core (deterministic, injected-data, unit-tested by T-4 / T-8):
      advisory_line, stale_advisory_line
  - IO/CLI layer (central-store resolution + mtime; NOT unit-tested):
      _staleness_days, _load_brier, main

The advisory is print-only: no behavior change, never blocks a gate. It is
kill-switched by CRUCIBLE_CALIBRATION_DISABLED=1 (consumer-side L-6; emit-side
already enforced in Phase 1's ledger-append.md).

Thresholds (design §5): advisory fires at n >= 5 AND brier > 0.25; data older
than 30 days is too stale to trust (silent); a 7-30 day window prints a
staleness suffix.

Pure stdlib. No third-party deps.
"""
import argparse
import json
import math
import os
import sys
import time
from typing import Optional

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Central-store resolution (honors CRUCIBLE_LEDGER_DIR; falls back to
# ~/.claude/crucible/ledger). The advisory MUST read the path the reconciler
# actually writes to, NOT the cwd-relative .crucible/ledger/ the design text
# predated.
from scripts.ledger_append import default_ledger_dir  # noqa: E402

# Advisory thresholds (design §5).
MIN_N = 5
BRIER_THRESHOLD = 0.25
# Staleness windows, in days.
STALE_TRUST_CUTOFF = 30  # older than this: advisory is silent (untrustworthy)
STALE_SUFFIX_CUTOFF = 7  # older than this (but <= 30): print a staleness note
RECONCILE_STALE_CUTOFF = 7  # getting-started nudges to reconcile past this

# Calibration-weighted dispatch (#372): bounds for the `advise` DispatchAdvice.
ADVICE_FILE_TOPK = 5       # per-signal rendered-file cap (hit-count desc, path asc)
GRUDGE_QUERY_LIMIT = 10_000  # large constant -> nothing recency-dropped by query()


# --------------------------------------------------------------------------- #
# PURE core (deterministic; exercised by T-4 / T-8)                           #
# --------------------------------------------------------------------------- #

def advisory_line(
    brier: dict,
    skill: str,
    *,
    falsification_exists: bool,
    staleness_days: Optional[float],
    disabled: bool,
) -> Optional[str]:
    """The per-skill Brier advisory line, or None when silent.

    Silent when: kill-switched; no falsification data yet (pre-bootstrap);
    data older than 30 days; the skill has < 5 falsifiable verdicts; or the
    skill's Brier is at/below 0.25. Otherwise prints a scrutiny advisory with
    an optional staleness suffix when the data is 7-30 days old.
    """
    if disabled:
        return None
    # No calibration data yet (pre-bootstrap) -> mtime would be undefined.
    if not falsification_exists:
        return None
    # Too stale to be trustworthy.
    if staleness_days is not None and staleness_days > STALE_TRUST_CUTOFF:
        return None
    entry = brier.get(skill)
    if not isinstance(entry, dict):
        return None
    n = entry.get("n")
    score = entry.get("brier")
    # bool is a subclass of int/float — reject it so a malformed
    # `"brier": true` degrades to silent rather than printing "Brier of 1.00".
    if isinstance(n, bool) or isinstance(score, bool):
        return None
    if not isinstance(n, int) or not isinstance(score, (int, float)):
        return None
    # Reject NaN/Infinity (json.load parses bare NaN/Infinity by default) so a
    # corrupt artifact degrades to silent rather than printing "Brier of inf".
    if not math.isfinite(score):
        return None
    if n < MIN_N or score <= BRIER_THRESHOLD:
        return None
    suffix = ""
    if staleness_days is not None and staleness_days > STALE_SUFFIX_CUTOFF:
        suffix = f" [based on {round(staleness_days)}-day-stale reconciliation]"
    return (
        f"[calibration] My last {n} verdicts had a Brier of {float(score):.2f}. "
        f"Treat my outputs with extra scrutiny this run.{suffix}"
    )


def stale_advisory_line(
    *,
    falsification_exists: bool,
    staleness_days: Optional[float],
    disabled: bool,
) -> Optional[str]:
    """The reconciliation-staleness nudge for getting-started, or None.

    Silent when kill-switched, pre-bootstrap (no falsification data), or the
    data is fresh (<= 7 days). Never auto-invokes the reconciler.
    """
    if disabled:
        return None
    if not falsification_exists:
        return None
    if staleness_days is None or staleness_days <= RECONCILE_STALE_CUTOFF:
        return None
    return (
        f"[calibration] Reconciliation data is {round(staleness_days)} days stale. "
        f"Run /calibration-reconcile when convenient "
        f"(takes ~30s-2min depending on history)."
    )


# --------------------------------------------------------------------------- #
# Calibration-weighted dispatch (#372): pure merge core                       #
# --------------------------------------------------------------------------- #

# ledger_entry_hash is the SINGLE source for the falsification<->run join key
# (design discipline: import, never re-derive). Guarded so a broken import
# degrades the falsification signal to empty rather than breaking the whole
# command (preserving the never-raise contract of the existing advisory paths).
try:
    from scripts.reconcile_ledger import ledger_entry_hash as _ledger_entry_hash
except Exception:  # noqa: BLE001 — best-effort; falsification degrades to silent
    _ledger_entry_hash = None


def _falsification_hits(runs, falsified_hashes, skill, norm_inputs):
    """Per-input-file count of distinct NON-backfilled falsified runs (for
    `skill`) whose gated_files include that file. Pure.

    `runs` is an iterable of runs.jsonl entry dicts; `falsified_hashes` is the
    set of `ledger_entry_hash` values reduce() reports as falsified;
    `norm_inputs` is the set of repo-relative input paths. A row lacking
    `gated_files` contributes nothing (skip-the-row via `or []`) rather than
    silencing the signal. The join key embeds the skill, so a falsified run of a
    different skill never hits — the signal is suite-wide on the FILE only.

    "Distinct runs" is enforced on `run_id`: should a malformed ledger carry two
    rows with the same `(run_id, skill)`, the file is counted once, so the count
    matches the docstring (run_id is a UUIDv7, unique per run by construction —
    this guard only hardens against a duplicated row).
    """
    counts = {}
    if _ledger_entry_hash is None or not falsified_hashes:
        return counts
    seen_runs = set()
    for e in runs:
        if not isinstance(e, dict) or e.get("backfilled"):
            continue
        if e.get("skill") != skill:
            continue
        rid = e.get("run_id")
        if not rid or rid in seen_runs:
            continue
        if _ledger_entry_hash(rid, skill) not in falsified_hashes:
            continue
        seen_runs.add(rid)
        for f in (set(e.get("gated_files") or []) & norm_inputs):
            counts[f] = counts.get(f, 0) + 1
    return counts


def _topk(hits):
    """Top ADVICE_FILE_TOPK (file, count) pairs, hit-count desc then path asc,
    plus the overflow count. Pure."""
    ordered = sorted(hits.items(), key=lambda kv: (-kv[1], kv[0]))
    head = ordered[:ADVICE_FILE_TOPK]
    return head, max(0, len(ordered) - ADVICE_FILE_TOPK)


def _fmt_files(hits):
    head, overflow = _topk(hits)
    parts = [f"{f} ({c})" for f, c in head]
    if overflow:
        parts.append(f"(+{overflow} more)")
    return ", ".join(parts)


def _render_advice(skill, brier_line, fals_hits, grudge_hits):
    """Render the bounded DispatchAdvice block, or "" when every signal is
    silent. Pure. File lists are top-K capped; no absolute paths are emitted
    (inputs are repo-relative by the time they reach here)."""
    lines = []
    if brier_line:
        lines.append(f"- scrutiny: {brier_line}")
    if fals_hits:
        lines.append(f"- past wrong verdicts touched: {_fmt_files(fals_hits)}")
    if grudge_hits:
        lines.append(f"- past regressions on file: {_fmt_files(grudge_hits)}")
    if not lines:
        return ""
    header = ("[calibration-weighted dispatch] advisory only — does not change "
              "any verdict or score.")
    footer = ("- suggested weighting: give the named files extra reviewer "
              "attention this run.")
    return "\n".join([header, *lines, footer])


# --------------------------------------------------------------------------- #
# IO / CLI layer (central-store resolution + mtime; NOT unit-tested)          #
# --------------------------------------------------------------------------- #

def _disabled() -> bool:
    return os.environ.get("CRUCIBLE_CALIBRATION_DISABLED") == "1"


def _falsification_path() -> str:
    return os.path.join(default_ledger_dir(), "falsification.jsonl")


def _brier_path() -> str:
    return os.path.join(default_ledger_dir(), "brier-rolling.json")


def _staleness_days(path: str, *, now: Optional[float] = None) -> Optional[float]:
    """Days since `path` was last modified, or None if it does not exist."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    ref = time.time() if now is None else now
    return max(0.0, (ref - mtime) / 86400.0)


def _load_brier(path: str) -> dict:
    """Load brier-rolling.json; {} on any missing/unreadable/malformed file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _runs_path() -> str:
    return os.path.join(default_ledger_dir(), "runs.jsonl")


def _load_runs(path: str) -> list:
    """Tolerant runs.jsonl read -> list of dicts. [] on any missing/unreadable
    file; blank/malformed lines are skipped (mirrors ledger_reduce tolerance).
    Never raises."""
    out = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    out.append(obj)
    except OSError:
        return []
    return out


def _grudge_hits(files) -> dict:
    """Per-input-file count of distinct surviving grudges held against it, for
    the repo the cwd is in. {} on any error (never raises).

    IO: shells `git` via resolve_repo() and reads the grudge store (honoring
    CRUCIBLE_GRUDGE_DIR). Re-derives the per-file hit by intersecting each
    matched grudge's survivors() against the normalized inputs with the SAME
    `_path_match` query() uses internally — so the count is "distinct surviving
    grudges touching this file", consistent with query()'s match predicate."""
    try:
        from scripts.grudge_query import (
            query as _grudge_query,
            survivors as _survivors,
            _path_match as _grudge_path_match,
        )
        from scripts.grudge_append import normalize_path as _norm, resolve_repo
    except Exception:  # noqa: BLE001 — grudge module unavailable -> signal empty
        return {}
    try:
        repo, repo_root = resolve_repo()
        norm_inputs = {_norm(f, repo_root) for f in files if f and f.strip()}
        if not norm_inputs:
            return {}
        matched, _stats = _grudge_query(
            files, repo, repo_root,
            with_signatures=False, limit=GRUDGE_QUERY_LIMIT,
        )
        counts = {}
        for g in matched:
            surv = _survivors(g, repo_root)
            hit_files = {
                inp for inp in norm_inputs
                for s in surv if _grudge_path_match(inp, s)
            }
            for f in hit_files:
                counts[f] = counts.get(f, 0) + 1
        return counts
    except Exception:  # noqa: BLE001 — best-effort; degrade to empty
        return {}


def dispatch_advice(skill: str, files) -> str:
    """Assemble the bounded calibration-weighted DispatchAdvice for `skill`
    about `files`, or "" when every signal is silent.

    Advisory-only contract: kill-switch silences the whole block; each of the
    three components (Brier / falsification / grudge) is wrapped so an internal
    error degrades THAT signal to empty rather than raising — the caller always
    gets a string and the CLI always exits 0. Not pure (reads the central store
    + shells git); tested via the subprocess fixture."""
    if _disabled():
        return ""

    # --- Brier: reuse advisory_line() via main()'s exact plumbing (no new
    #     Brier logic), gating already done above so disabled=False here. ---
    brier_line = None
    try:
        staleness = _staleness_days(_falsification_path())
        brier_line = advisory_line(
            _load_brier(_brier_path()),
            skill,
            falsification_exists=staleness is not None,
            staleness_days=staleness,
            disabled=False,
        )
    except Exception:  # noqa: BLE001
        brier_line = None

    # --- Falsification: suite-wide on the FILE (skill-agnostic join is scoped
    #     by the hash, which embeds skill); non-backfilled falsified runs only. ---
    fals_hits = {}
    try:
        from scripts.ledger_reduce import reduce as _reduce
        from scripts.grudge_append import normalize_path as _norm, resolve_repo
        _repo, repo_root = resolve_repo()
        norm_inputs = {_norm(f, repo_root) for f in files if f and f.strip()}
        reduced = _reduce(_falsification_path())
        falsified = {
            h for h, e in reduced.items()
            if isinstance(e, dict) and e.get("falsified")
        }
        runs = _load_runs(_runs_path())
        fals_hits = _falsification_hits(runs, falsified, skill, norm_inputs)
    except Exception:  # noqa: BLE001
        fals_hits = {}

    # --- Grudge ---
    try:
        grudge_hits = _grudge_hits(files)
    except Exception:  # noqa: BLE001
        grudge_hits = {}

    return _render_advice(skill, brier_line, fals_hits, grudge_hits)


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_adv = sub.add_parser("advisory", help="per-skill Brier advisory line")
    p_adv.add_argument("skill", help="ledger skill key, e.g. quality-gate or siege")
    sub.add_parser("stale-check", help="reconciliation-staleness nudge")
    p_advise = sub.add_parser(
        "advise", help="calibration-weighted DispatchAdvice (#372)")
    p_advise.add_argument("skill", help="ledger skill key, e.g. quality-gate or siege")
    p_advise.add_argument("files", nargs="*", help="in-scope files for this dispatch")

    args = parser.parse_args(argv)

    # Derive existence from the single mtime probe: getmtime succeeds iff the
    # file exists, so `staleness is not None` IS the existence signal. Using one
    # stat (rather than os.path.exists + getmtime) removes a TOCTOU window where
    # the file could vanish between two separate calls.
    staleness = _staleness_days(_falsification_path())
    exists = staleness is not None
    disabled = _disabled()

    if args.cmd == "advise":
        line = dispatch_advice(args.skill, args.files)
    elif args.cmd == "advisory":
        line = advisory_line(
            _load_brier(_brier_path()),
            args.skill,
            falsification_exists=exists,
            staleness_days=staleness,
            disabled=disabled,
        )
    else:  # stale-check
        line = stale_advisory_line(
            falsification_exists=exists,
            staleness_days=staleness,
            disabled=disabled,
        )

    if line:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
