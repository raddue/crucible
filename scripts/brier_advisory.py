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


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_adv = sub.add_parser("advisory", help="per-skill Brier advisory line")
    p_adv.add_argument("skill", help="ledger skill key, e.g. quality-gate or siege")
    sub.add_parser("stale-check", help="reconciliation-staleness nudge")

    args = parser.parse_args(argv)

    # Derive existence from the single mtime probe: getmtime succeeds iff the
    # file exists, so `staleness is not None` IS the existence signal. Using one
    # stat (rather than os.path.exists + getmtime) removes a TOCTOU window where
    # the file could vanish between two separate calls.
    staleness = _staleness_days(_falsification_path())
    exists = staleness is not None
    disabled = _disabled()

    if args.cmd == "advisory":
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
