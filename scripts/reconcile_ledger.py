#!/usr/bin/env python3
"""`/calibration-reconcile` reconciler (#270, Epistemics Phase 4).

Walks fix branches to falsify originating gating-verdicts, computes per-skill
Brier calibration scores, and writes a falsification log.

Architecture (binding):
  - PURE core (no subprocess/git, deterministic, drives off injected data):
      ledger_entry_hash, reconcile, compute_brier, load_jsonl,
      read_manual_attribution
  - GIT layer (subprocess; NOT exercised by unit tests):
      discover_candidates, fix_branch_sizes, cross_cut_threshold_from, main

Scope: design §3 steps 1-6 ONLY. The predicted-falsifier predicate parser /
"second pass" is Phase 7 and explicitly OUT OF SCOPE here.

The Brier formula `brier = mean((confidence - actual)^2)` (contract L-10).

Pure stdlib. No third-party deps.
"""
import argparse
import datetime as _dt
import hashlib
import json
import math
import os
import re
import sys
from typing import Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# L-9 canonical reduction over falsification.jsonl.
# <!-- CANONICAL: shared/ledger-reduce.md -->
from scripts.ledger_reduce import reduce as _falsification_reduce  # noqa: E402
from scripts.ledger_append import (  # noqa: E402
    append as _ledger_append,
    default_ledger_dir,
    default_ledger_path,
)

# 30-day grace period: a verdict must be older than this before it can be
# falsified by a fix (so it has had a chance to be falsified) and before it is
# admitted into the Brier sample.
GRACE_DAYS = 30
# Confidence-window cutoffs (design §3.4).
HIGH_WINDOW_DAYS = 14
MEDIUM_WINDOW_DAYS = 30
# Bootstrap cross-cut threshold until >= 30 fix-branch samples exist (§3.2).
BOOTSTRAP_CROSS_CUT = 20
MIN_CROSS_CUT_SAMPLES = 30
# Multi-file fix heuristic (§3.4 'low'): >5 touched files but <= cross-cut.
MULTI_FILE_LOW = 5
# Brier sample requires a calibrated verdict.
MIN_CONFIDENCE = 0.5
# Verdict-type classifier (T-11): only these count for Brier.
BRIER_VERDICTS = {"PASS", "FAIL"}


# --------------------------------------------------------------------------- #
# Time helpers                                                                #
# --------------------------------------------------------------------------- #

def _parse_iso(ts: str) -> Optional[_dt.datetime]:
    """Parse an ISO8601 timestamp (tolerant of a trailing 'Z'). Returns an
    aware UTC datetime, or None when unparseable."""
    if not ts or not isinstance(ts, str):
        return None
    s = ts.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = _dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.timezone.utc)
    return dt.astimezone(_dt.timezone.utc)


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# PURE core                                                                   #
# --------------------------------------------------------------------------- #

def ledger_entry_hash(run_id: str, skill: str) -> str:
    """Stable hash over only the immutable identity fields (run_id + skill)."""
    return hashlib.sha256((run_id + ":" + skill).encode()).hexdigest()


def load_jsonl(path: str) -> List[dict]:
    """Tolerant per-line JSONL read.

    Skips blank/malformed lines and a trailing partial line (no terminating
    newline). Missing file -> []. (Same tolerance as ledger_reduce.reduce.)
    """
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return []
    if not raw:
        return []
    parts = raw.split(b"\n")
    if not raw.endswith(b"\n"):
        parts = parts[:-1]  # drop the partial trailing line
    out: List[dict] = []
    for chunk in parts:
        if not chunk:
            continue
        try:
            out.append(json.loads(chunk))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
    return out


def read_manual_attribution(path: str) -> Dict[str, dict]:
    """Read manual-attribution.jsonl into a dict keyed by ledger_entry_hash.

    Latest file-position wins per hash (L-9 semantics). Missing file -> {}
    (no overrides, no error).
    """
    out: Dict[str, dict] = {}
    for obj in load_jsonl(path):
        key = obj.get("ledger_entry_hash")
        if key is None:
            continue
        out[key] = obj
    return out


def _confidence_label(days_delta: float, n_touched: int, cross_cut: bool) -> str:
    """Confidence scoring (design §3.4).

    high   : intersection >=1 AND merge within 14d AND cross_cut == False
    medium : 14-30 days AND cross_cut == False
    low    : >30 days OR cross_cut == True OR multi-file (>5 files but <= xcut)
    """
    if cross_cut:
        return "low"
    if days_delta > MEDIUM_WINDOW_DAYS:
        return "low"
    # Multi-file fixes (>5 files, but not cross-cut) downgrade to low.
    if n_touched > MULTI_FILE_LOW:
        return "low"
    if days_delta <= HIGH_WINDOW_DAYS:
        return "high"
    return "medium"


def reconcile(
    ledger_path: str,
    falsification_path: str,
    manual_attribution_path: str,
    candidates: List[dict],
    *,
    cross_cut_threshold: int,
    lookback_days: int = 30,
    now: str,
) -> List[dict]:
    """Run design §3 steps 2-5 over an INJECTED candidate list.

    For each candidate, walk back to the EARLIEST forward code-verdict whose
    gated_files intersect the candidate's touched_files and whose timestamp
    precedes the merge. Records a falsification entry per matched ledger entry,
    honoring manual overrides. Appends each entry (append-only, L-1/L-9) to
    falsification_path and also returns the list of appended entries.

    Returns the list of falsification entries appended (in append order).
    """
    now_dt = _parse_iso(now)
    entries = load_jsonl(ledger_path)
    manual = read_manual_attribution(manual_attribution_path)

    # Pre-sort ledger entries by timestamp ascending so "earliest match" is the
    # first qualifying entry we encounter per candidate.
    indexed = []
    for e in entries:
        ts = _parse_iso(e.get("timestamp"))
        if ts is None:
            continue
        indexed.append((ts, e))
    indexed.sort(key=lambda pair: pair[0])

    appended: List[dict] = []
    # Track hashes already attributed in THIS run so one verdict isn't
    # double-counted. Manual entries claim their hash first (S-3), and the
    # algorithm pass skips a verdict once attributed, falling through to the
    # next-earliest UNSEEN overlapping verdict (S-2).
    seen_hashes = set()

    # --- §3.5 manual pass FIRST (authoritative) ---------------------------- #
    # Manual attribution is read first and overrides the algorithm. A human
    # asserting a missed falsification (or suppressing a wrong one) is a
    # first-class entry: we emit one falsification entry for EVERY manual
    # attribution, regardless of whether the algorithm would have matched its
    # hash, and reserve that hash so the algorithm pass skips it (S-3).
    for h, mo in manual.items():
        entry = {
            "ledger_entry_hash": h,
            "falsified": mo.get("falsified", True),
            "falsified_by": mo.get("falsified_by", {
                "commit": mo.get("commit"),
                "reason": mo.get("reasoning", "manual attribution"),
                "confidence": mo.get("confidence", "low"),
                "cross_cut": mo.get("cross_cut", False),
                "manual_override": True,
            }),
            "confidence": mo.get("confidence", "low"),
            "reasoning": mo.get("reasoning", "manual attribution"),
            "cross_cut": mo.get("cross_cut", False),
        }
        seen_hashes.add(h)
        _ledger_append(falsification_path, entry)
        appended.append(entry)

    # --- §3.3/§3.4 algorithm pass ----------------------------------------- #
    for cand in candidates:
        touched = set(cand.get("touched_files") or [])
        if not touched:
            continue
        merge_dt = _parse_iso(cand.get("merge_time"))
        cross_cut = len(touched) > cross_cut_threshold

        # Walkback: earliest UNSEEN ledger entry meeting ALL §3.3 conditions.
        # The seen-check is INSIDE the loop so a candidate whose earliest match
        # is already attributed falls through to the next-earliest unseen
        # overlapping verdict rather than being dropped entirely (S-2).
        match = None
        for ts, e in indexed:
            # (c) artifact_type == "code"
            if e.get("artifact_type") != "code":
                continue
            # (d) backfilled == false
            if e.get("backfilled"):
                continue
            # (a) gated_files ∩ touched_files non-empty
            gated = set(e.get("gated_files") or [])
            if not (gated & touched):
                continue
            # (b) entry timestamp < candidate merge_time
            if merge_dt is not None and not (ts < merge_dt):
                continue
            run_id = e.get("run_id", "unknown")
            skill = e.get("skill", "unknown")
            h = ledger_entry_hash(run_id, skill)
            # Skip already-attributed verdicts (manual pass or a prior
            # candidate this run); keep scanning for the next-earliest unseen.
            if h in seen_hashes:
                continue
            match = (ts, e, gated, h)
            break

        if match is None:
            continue

        ts, e, gated, h = match
        seen_hashes.add(h)

        # §3.4 confidence
        if merge_dt is not None:
            days_delta = (merge_dt - ts).total_seconds() / 86400.0
        else:
            days_delta = float("inf")
        confidence = _confidence_label(days_delta, len(touched), cross_cut)

        reason = (
            f"fix {cand.get('commit', '?')} touched "
            f"{sorted(gated & touched)} gated by this verdict; merged "
            f"{days_delta:.1f}d after the verdict"
        )

        entry = {
            "ledger_entry_hash": h,
            "falsified": True,
            "falsified_by": {
                "commit": cand.get("commit"),
                "reason": reason,
                "confidence": confidence,
                "cross_cut": cross_cut,
            },
            "confidence": confidence,
            "reasoning": reason,
            "cross_cut": cross_cut,
        }

        # Append-only write (L-1). The append helper honors the kill-switch and
        # the 16 KiB cap; a no-op return does not stop us from reporting the
        # in-memory entry to the caller.
        _ledger_append(falsification_path, entry)
        appended.append(entry)

    return appended


def compute_brier(
    ledger_entries: List[dict],
    falsification_map: Dict[str, dict],
    *,
    now: str,
) -> Dict[str, dict]:
    """Per-skill Brier score over the falsifiable sample.

    brier = mean((confidence - actual)^2)  (contract L-10).

    Falsifiable sample filters (ALL must hold):
      - artifact_type == "code"
      - backfilled == false
      - verdict in {PASS, FAIL} with confidence >= 0.5  (T-11 classifier)
      - entry older than the 30-day grace period
      - if a matching falsification entry exists, its cross_cut must be False
        (cross-cut excluded from the denominator)

    actual = 1 iff CORRECT: a PASS NOT marked falsified, OR any FAIL (at v1
      every FAIL => actual=1, since predicates are Phase 7).
    actual = 0 iff WRONG: a PASS that WAS marked falsified: true.

    Returns {"<skill>": {"n": int, "brier": float, "last_updated": iso}}.
    """
    now_dt = _parse_iso(now)
    # Fail-CLOSED: a calibration metric must not admit verdicts whose age it
    # cannot evaluate. If `now` is unparseable, the 30-day grace filter cannot
    # be applied, so exclude EVERYTHING rather than fail open (S-1).
    if now_dt is None:
        return {}
    grace_cutoff = now_dt - _dt.timedelta(days=GRACE_DAYS)

    # accumulate squared errors per skill
    acc: Dict[str, List[float]] = {}

    for e in ledger_entries:
        if e.get("artifact_type") != "code":
            continue
        if e.get("backfilled"):
            continue
        verdict = e.get("verdict")
        if verdict not in BRIER_VERDICTS:
            continue
        confidence = e.get("confidence")
        if not isinstance(confidence, (int, float)):
            continue
        if confidence < MIN_CONFIDENCE:
            continue
        ts = _parse_iso(e.get("timestamp"))
        if ts is None:
            continue
        # Must be older than the grace period.
        if grace_cutoff is not None and not (ts < grace_cutoff):
            continue

        run_id = e.get("run_id", "unknown")
        skill = e.get("skill", "unknown")
        h = ledger_entry_hash(run_id, skill)
        fals = falsification_map.get(h)

        # Cross-cut falsifications are excluded from the denominator.
        if fals is not None and fals.get("cross_cut"):
            continue

        # Determine actual.
        if verdict == "FAIL":
            actual = 1  # v1: every FAIL is correct (predicates are Phase 7)
        else:  # PASS
            falsified = bool(fals.get("falsified")) if fals is not None else False
            actual = 0 if falsified else 1

        sq_err = (float(confidence) - actual) ** 2
        acc.setdefault(skill, []).append(sq_err)

    out: Dict[str, dict] = {}
    last = _now_iso() if now_dt is None else now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    for skill, errs in acc.items():
        n = len(errs)
        brier = sum(errs) / n if n else 0.0
        out[skill] = {"n": n, "brier": brier, "last_updated": last}
    return out


# --------------------------------------------------------------------------- #
# GIT layer (subprocess; NOT exercised by unit tests)                         #
# --------------------------------------------------------------------------- #

def _git(args: List[str], cwd: Optional[str] = None) -> Optional[str]:
    """Run a git command; return stdout (stripped) or None on any failure."""
    import subprocess
    try:
        proc = subprocess.run(
            ["git"] + args, capture_output=True, text=True, timeout=30, cwd=cwd,
        )
    except Exception:  # noqa: BLE001 — git is best-effort
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


_FIX_MERGE_RE = re.compile(r"(?:^|[\s/'\"])(?:hot)?fix/", re.I)


def _is_fix_merge_subject(subject: str) -> bool:
    """True iff a merge-commit subject references a fix/* or hotfix/* branch.

    Anchored on a branch boundary (start-of-string / whitespace / slash /
    quote) so it matches `fix/` and `hotfix/` but NOT `prefix/`, `affix/`,
    `suffix/` where the token is mid-word (S-4)."""
    if not subject:
        return False
    return _FIX_MERGE_RE.search(subject) is not None


def discover_candidates(lookback_days: int = 30) -> List[dict]:
    """Discover fix/* hotfix/* merges within lookback_days, plus regression
    issues with a referenced commit (best-effort).

    Each candidate: {"commit", "touched_files": [...], "merge_time": iso}.
    """
    candidates: List[dict] = []
    since = (
        _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=lookback_days)
    ).strftime("%Y-%m-%d")

    # Merge commits whose merged branch matches fix/* or hotfix/*. We look at
    # merge commits in the lookback window and inspect the merge subject for a
    # fix/hotfix branch name.
    log = _git([
        "log", "--merges", f"--since={since}",
        "--pretty=format:%H%x1f%cI%x1f%s",
    ])
    if log:
        for line in log.splitlines():
            parts = line.split("\x1f")
            if len(parts) < 3:
                continue
            sha, when, subject = parts[0], parts[1], parts[2]
            if not _is_fix_merge_subject(subject):
                continue
            touched = _touched_files(sha)
            candidates.append({
                "commit": sha,
                "touched_files": touched,
                "merge_time": when,
            })

    # regression-labelled closed issues with a referenced commit (best-effort).
    gh = _git_gh_regression_commits()
    for sha in gh:
        touched = _touched_files(sha)
        when = _git(["show", "-s", "--format=%cI", sha])
        candidates.append({
            "commit": sha,
            "touched_files": touched,
            "merge_time": (when or "").strip(),
        })

    return candidates


def _touched_files(sha: str) -> List[str]:
    out = _git(["show", "--name-only", "--pretty=format:", sha])
    if not out:
        return []
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def _git_gh_regression_commits() -> List[str]:
    """Best-effort: closed issues labelled `regression` with a referenced
    commit, via the `gh` CLI. If gh is unavailable, skip silently."""
    import subprocess
    try:
        proc = subprocess.run(
            ["gh", "issue", "list", "--state", "closed", "--label",
             "regression", "--json", "body,title", "--limit", "100"],
            capture_output=True, text=True, timeout=30,
        )
    except Exception:  # noqa: BLE001 — gh optional
        return []
    if proc.returncode != 0 or not proc.stdout.strip():
        return []
    try:
        issues = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        return []
    shas: List[str] = []
    sha_re = re.compile(r"\b([0-9a-f]{7,40})\b")
    for iss in issues:
        text = (iss.get("body") or "") + " " + (iss.get("title") or "")
        for m in sha_re.findall(text):
            shas.append(m)
    return shas


def fix_branch_sizes(days: int = 90) -> List[int]:
    """Touched-file counts of fix/hotfix merges over the prior `days` (a
    DISTINCT 90-day window from the 30-day candidate lookback)."""
    since = (
        _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)
    ).strftime("%Y-%m-%d")
    log = _git([
        "log", "--merges", f"--since={since}",
        "--pretty=format:%H%x1f%s",
    ])
    sizes: List[int] = []
    if not log:
        return sizes
    for line in log.splitlines():
        parts = line.split("\x1f")
        if len(parts) < 2:
            continue
        sha, subject = parts[0], parts[1]
        if not _is_fix_merge_subject(subject):
            continue
        sizes.append(len(_touched_files(sha)))
    return sizes


def cross_cut_threshold_from(sizes: List[int]) -> int:
    """p90 of `sizes` when len(sizes) >= 30, else the bootstrap fixed 20 (§3.2)."""
    if len(sizes) < MIN_CROSS_CUT_SAMPLES:
        return BOOTSTRAP_CROSS_CUT
    ordered = sorted(sizes)
    # Nearest-rank percentile: rank = ceil(0.9 * N), 1-indexed.
    rank = max(1, math.ceil(0.9 * len(ordered)))
    return int(ordered[rank - 1])


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    # L-6 kill-switch: graceful no-op exit BEFORE any work.
    if os.environ.get("CRUCIBLE_CALIBRATION_DISABLED") == "1":
        print("[calibration-reconcile] calibration disabled; reconcile skipped",
              file=sys.stderr)
        return 0

    ledger_dir = default_ledger_dir()
    parser = argparse.ArgumentParser(description="calibration reconciler (#270)")
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--ledger", default=default_ledger_path())
    parser.add_argument("--falsification",
                        default=os.path.join(ledger_dir, "falsification.jsonl"))
    parser.add_argument("--manual-attribution",
                        default=os.path.join(ledger_dir, "manual-attribution.jsonl"))
    parser.add_argument("--brier-out",
                        default=os.path.join(ledger_dir, "brier-rolling.json"))
    args = parser.parse_args(argv)

    now = _now_iso()

    # §3.1 candidate discovery + §3.2 cross-cut threshold (distinct 90d window).
    candidates = discover_candidates(lookback_days=args.lookback_days)
    threshold = cross_cut_threshold_from(fix_branch_sizes(days=90))

    appended = reconcile(
        args.ledger, args.falsification, args.manual_attribution, candidates,
        cross_cut_threshold=threshold, lookback_days=args.lookback_days, now=now,
    )

    # Recompute Brier over the full ledger + reduced falsification map.
    fmap = _falsification_reduce(args.falsification)
    entries = load_jsonl(args.ledger)
    brier = compute_brier(entries, fmap, now=now)

    # Write brier-rolling.json (gitignored).
    try:
        os.makedirs(os.path.dirname(args.brier_out) or ".", exist_ok=True)
        with open(args.brier_out, "w", encoding="utf-8") as f:
            json.dump(brier, f, indent=2, sort_keys=True)
            f.write("\n")
    except OSError as e:
        print(f"[calibration-reconcile] could not write brier-rolling.json: {e}",
              file=sys.stderr)

    print(f"[calibration-reconcile] candidates={len(candidates)} "
          f"cross_cut_threshold={threshold} falsified+={len(appended)} "
          f"skills_scored={len(brier)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
