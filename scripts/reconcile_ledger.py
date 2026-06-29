#!/usr/bin/env python3
"""`/calibration-reconcile` reconciler (#270, Epistemics Phase 4).

Walks fix branches to falsify originating gating-verdicts, computes per-skill
Brier calibration scores, and writes a falsification log.

Architecture (binding):
  - PURE core (no subprocess/git, deterministic, drives off injected data):
      ledger_entry_hash, reconcile, compute_brier, load_jsonl,
      read_manual_attribution, parse_predicate, reconcile_predicates
  - GIT layer (subprocess; NOT exercised by unit tests):
      discover_candidates, fix_branch_sizes, cross_cut_threshold_from, main

Scope: design §3 steps 1-6 (file-intersection walkback + Brier) PLUS the Phase 7
second pass (design §3a): the predicted-falsifier predicate parser and walk.
`main()` runs the walkback first, then the predicate pass; the predicate pass
appends after the walkback so L-9 (latest-wins) gives a fired predicate
precedence over a walkback match on the same verdict (design §3a step 2).

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
    valid_ledger_identity,
)
from scripts.atomic_write import atomic_write_text  # noqa: E402
# #401: path-aware glob is the single source of truth (scripts/pathmatch.py);
# was verbatim-duplicated here and in grudge_query.py. Alias to the prior
# private name so the calibration call sites are untouched.
from scripts.pathmatch import glob_match as _glob_match  # noqa: E402

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
# Phase 1->Phase 7 bridge sentinel. Entries bearing it are bootstrap-window
# emits with no real predicate; excluded from BOTH predicate rate denominators
# (design §3a bootstrap-window paragraph / contract R4-S2). Parsers MUST
# early-return on it before any regex matching.
PREDICATE_SENTINEL = "<DEFERRED:pre-phase-7>"


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


def _warn(msg: str) -> None:
    print(f"[reconcile_ledger WARN] {msg}", file=sys.stderr)


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
    skipped = 0
    for chunk in parts:
        if not chunk:
            continue
        try:
            obj = json.loads(chunk)
        except (json.JSONDecodeError, UnicodeDecodeError):
            skipped += 1  # #400: corruption is counted, not silently dropped
            continue
        if not isinstance(obj, dict):
            # #400: a valid-JSON-but-non-object line (e.g. `[1,2,3]`, `42`) has
            # no `.get` — downstream e.get(...) would AttributeError. Count it
            # as corruption, same as render_ledger.load_runs.
            skipped += 1
            continue
        out.append(obj)
    if skipped:
        _warn(f"load_jsonl: skipped {skipped} unparseable line(s) in {path}")
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


def _valid_repo_path(p) -> bool:
    """A `touched_files` entry must be a non-empty repo-relative posix path.

    Git `--name-only` only ever emits repo-relative paths; an absolute path or
    a `..` traversal segment signals corrupted git-layer output (or a `\\x1f`/
    `\\x1e`-injected commit body that mangled the field split, F1) and must not
    enter the pure matchers.
    """
    if not isinstance(p, str) or not p:
        return False
    if p.startswith("/") or os.path.isabs(p):
        return False
    return ".." not in p.split("/")


def _valid_candidate(cand, *, require_message: bool = False) -> bool:
    """Schema gate for git-layer candidate dicts at the pure-core boundary (F1).

    The git layer (`discover_*`) is the SOLE producer of the falsification input
    that flips a Brier `actual`; before this gate its output entered the pure
    core unvalidated. We reject the LOAD-BEARING corruption modes:

      - `merge_time` that does not parse → dropped (fail-CLOSED, F2). This is
        the single posture for an unplaceable candidate timestamp across the
        matchers that consume one — the walkback and the three predicate matchers
        now agree: a fix we cannot place in time falsifies nothing, rather than
        the old walkback fail-OPEN that let a garbage `merge_time` falsify an
        arbitrarily-old verdict it never post-dated. (`compute_brier` never
        parses a candidate `merge_time`; its own S-1 fail-CLOSED is about an
        unparseable `now`, an unrelated mechanism.)
      - `touched_files` present but not a list of repo-relative paths.
      - `message` missing/non-str when the consumer needs it (`referencing`).

    `commit` is deliberately NOT format-checked: it is decorative provenance
    (#412), used only in the human-readable `reason`/`falsified_by.commit`
    string, never in the calibration math — a `\\x1f`-mangled commit field
    manifests as an unparseable `merge_time` and is dropped on that basis.
    """
    if not isinstance(cand, dict):
        return False
    if _parse_iso(cand.get("merge_time")) is None:
        return False
    tf = cand.get("touched_files")
    # Whole-dict rejection is intentional: if ANY path element is invalid, the
    # candidate is partially-corrupt and therefore suspect, so we drop it rather
    # than salvage the good paths.
    if tf is not None and (
        not isinstance(tf, list) or not all(_valid_repo_path(p) for p in tf)
    ):
        return False
    if require_message and not isinstance(cand.get("message"), str):
        return False
    return True


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
    # first qualifying entry we encounter per candidate. #402 read-side: drop
    # rows lacking a valid (run_id, skill) join key HERE (once per entry, not
    # once per candidate) so the walkback never hashes one into the shared
    # "unknown:unknown" bucket and mis-attributes a fix to it.
    indexed = []
    skipped_identityless = 0
    for e in entries:
        ts = _parse_iso(e.get("timestamp"))
        if ts is None:
            continue
        if not valid_ledger_identity(e):
            skipped_identityless += 1
            continue
        indexed.append((ts, e))
    indexed.sort(key=lambda pair: pair[0])
    if skipped_identityless:
        _warn(f"reconcile: skipped {skipped_identityless} ledger row(s) lacking "
              f"a valid (run_id, skill) identity (#402)")

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
        # #342: signal_type distinguishes a plain manual override from a
        # `bad_implementation` signal ("a verdict accepted as PASS led to a bad
        # implementation"). Default `manual_override` (back-compat). Inject it
        # into falsified_by on BOTH construction paths — the default-built dict
        # AND a user-supplied falsified_by (which would otherwise miss it).
        signal_type = mo.get("signal_type", "manual_override")
        falsified_by = mo.get("falsified_by")
        if falsified_by is None:
            falsified_by = {
                "commit": mo.get("commit"),
                "reason": mo.get("reasoning", "manual attribution"),
                "confidence": mo.get("confidence", "low"),
                "cross_cut": mo.get("cross_cut", False),
                "manual_override": True,
            }
        falsified_by = {**falsified_by, "signal_type": signal_type}
        entry = {
            "ledger_entry_hash": h,
            "falsified": mo.get("falsified", True),
            "falsified_by": falsified_by,
            "confidence": mo.get("confidence", "low"),
            "reasoning": mo.get("reasoning", "manual attribution"),
            "cross_cut": mo.get("cross_cut", False),
            "signal_type": signal_type,
        }
        seen_hashes.add(h)
        _ledger_append(falsification_path, entry)
        appended.append(entry)

    # --- §3.3/§3.4 algorithm pass ----------------------------------------- #
    # F1: gate git-layer candidates at the boundary; a candidate failing the
    # schema (unparseable merge_time / non-repo-relative touched_files) is
    # dropped + counted, not silently fed into the matcher.
    valid_candidates = [c for c in candidates if _valid_candidate(c)]
    dropped = len(candidates) - len(valid_candidates)
    if dropped:
        _warn(f"reconcile: dropped {dropped} candidate(s) failing schema "
              f"validation (bad merge_time / touched_files)")
    for cand in valid_candidates:
        touched = set(cand.get("touched_files") or [])
        if not touched:
            continue
        # merge_time is validated-parseable for every valid candidate.
        merge_dt = _parse_iso(cand["merge_time"])
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
            # (b) entry timestamp < candidate merge_time (fail-CLOSED: merge_dt
            # is validated non-None, so an unplaceable fix matches nothing — the
            # posture now shared with the three predicate matchers).
            if not (ts < merge_dt):
                continue
            # run_id/skill are guaranteed valid: identity-less rows were dropped
            # when `indexed` was built (#402).
            h = ledger_entry_hash(e["run_id"], e["skill"])
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

        # §3.4 confidence (merge_dt validated non-None above).
        days_delta = (merge_dt - ts).total_seconds() / 86400.0
        confidence = _confidence_label(days_delta, len(touched), cross_cut)
        # Phase 7 (design §3a step 3 / plan combination rule): a file-intersection
        # walkback is the COARSER heuristic — it caps at "medium". Only a
        # self-declared predicted_falsifier that fires earns "high" (set in
        # reconcile_predicates). This demotes the heuristic relative to sharp,
        # pre-registered predictions.
        if confidence == "high":
            confidence = "medium"

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
                "via": "walkback",
            },
            "confidence": confidence,
            "reasoning": reason,
            "cross_cut": cross_cut,
            "via": "walkback",
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

    actual = 1 iff CORRECT: a PASS NOT marked falsified, OR a FAIL whose
      predicted_falsifier did NOT fire.
    actual = 0 iff WRONG: a PASS that WAS marked falsified: true, OR a FAIL
      whose predicted_falsifier fired (L-10 FAIL-side flip, Phase 7) — detected
      via a falsification entry carrying via == "predicate". A walkback-only
      falsification does NOT flip a FAIL.

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
    skipped_identityless = 0

    for e in ledger_entries:
        # #402 read-side: a row lacking a valid (run_id, skill) join key would
        # otherwise hash to the shared "unknown:unknown" bucket and pollute an
        # "unknown" skill's Brier with unrelated runs. Skip + count it instead.
        run_id = e.get("run_id")
        skill = e.get("skill")
        if not valid_ledger_identity(e):
            skipped_identityless += 1
            continue
        # Hoist the falsification lookup ABOVE the artifact_type gate so the
        # #342 non-code admission can consult it.
        h = ledger_entry_hash(run_id, skill)
        fals = falsification_map.get(h)

        # #342 scoped relaxation: a NON-code verdict is admitted into the Brier
        # sample ONLY when a human has supplied a definitive `bad_implementation`
        # outcome (⇒ actual=0). Absent that, a non-code verdict's outcome is
        # unknown (auto-falsification can never reach it) and it stays excluded —
        # we never assume a non-code PASS was correct just because nothing
        # falsified it. Code verdicts are unaffected.
        if e.get("artifact_type") != "code":
            # `bad_implementation` is a PASS-side marker ("a verdict accepted as
            # PASS led to a bad implementation"). On a non-code FAIL it is
            # out-of-contract — NOT admitted (its outcome is undefined and
            # auto-falsification can never reach it), so we require verdict==PASS
            # here. Absent a PASS-side bad_implementation attribution, a non-code
            # verdict's outcome is unknown and stays excluded.
            sig = (fals or {}).get("signal_type") \
                or ((fals or {}).get("falsified_by") or {}).get("signal_type")
            if not (fals and bool(fals.get("falsified"))
                    and sig == "bad_implementation" and e.get("verdict") == "PASS"):
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

        # Cross-cut falsifications are excluded from the denominator.
        if fals is not None and fals.get("cross_cut"):
            continue

        # Determine actual (contract L-10; Phase 7 completes the FAIL-side flip).
        if verdict == "FAIL":
            # A FAIL is WRONG (actual=0) ONLY if its predicted_falsifier fired —
            # signalled by a falsification entry with via == "predicate". A
            # walkback-only match (a later fix touching the gated files) is the
            # gate working as intended, NOT the FAIL being wrong, so it does not
            # flip the FAIL. With no fired predicate, a FAIL defaults to actual=1.
            via = None
            if fals is not None:
                via = fals.get("via") or (fals.get("falsified_by") or {}).get("via")
            predicate_fired = (
                fals is not None and bool(fals.get("falsified"))
                and via == "predicate"
            )
            actual = 0 if predicate_fired else 1
        else:  # PASS
            falsified = bool(fals.get("falsified")) if fals is not None else False
            actual = 0 if falsified else 1

        sq_err = (float(confidence) - actual) ** 2
        acc.setdefault(skill, []).append(sq_err)

    if skipped_identityless:
        _warn(f"compute_brier: skipped {skipped_identityless} ledger row(s) "
              f"lacking a valid (run_id, skill) identity (#402)")

    out: Dict[str, dict] = {}
    last = _now_iso() if now_dt is None else now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    for skill, errs in acc.items():
        n = len(errs)
        brier = sum(errs) / n if n else 0.0
        out[skill] = {"n": n, "brier": brier, "last_updated": last}
    return out


# --------------------------------------------------------------------------- #
# Predicted-falsifier second pass (design §3a, Phase 7) — PURE                #
# --------------------------------------------------------------------------- #

# Canonical grammar (design §3a, v1). Three forms; verbs are case-insensitive.
_PRED_VERB = r"(fix|hotfix|revert|merge|cve|postmortem)"
_PRED_TOUCHING = re.compile(
    rf"^{_PRED_VERB}\s+touching\s+(.+?)\s+within\s+(\d+)\s*d$", re.I)
_PRED_HASH = re.compile(
    rf"^{_PRED_VERB}\s+of\s+artifact_hash=([0-9a-f]+)"
    rf"(?:\s+without\s+touching\s+(.+?))?\s+within\s+(\d+)\s*d$", re.I)
_PRED_REF = re.compile(
    rf"^{_PRED_VERB}\s+referencing\s+(\S+)\s+within\s+(\d+)\s*d$", re.I)


def _split_file_list(s: str) -> List[str]:
    return [p.strip() for p in s.split(",") if p.strip()]


def _valid_days(n: int) -> bool:
    return 1 <= n <= 365


def parse_predicate(text) -> Optional[dict]:
    """Parse a `predicted_falsifier` string against the canonical grammar (§3a).

    Returns a dict describing the predicate on success, or None on PARSE FAILURE
    (an unparseable / free-form prose predicate). The caller is responsible for
    early-returning on the bootstrap sentinel BEFORE calling this — the sentinel
    is neither parseable nor unparseable (it is excluded from both buckets).

    Forms:
      touching    -> {"form": "touching", "verb", "files": [...], "within_days"}
      hash        -> {"form": "hash", "verb", "artifact_hash",
                      "without_files": [...], "within_days"}
      referencing -> {"form": "referencing", "verb", "token", "within_days"}
    """
    if not text or not isinstance(text, str):
        return None
    s = text.strip()

    m = _PRED_TOUCHING.match(s)
    if m:
        n = int(m.group(3))
        if not _valid_days(n):
            return None
        files = _split_file_list(m.group(2))
        if not files:
            return None
        return {"form": "touching", "verb": m.group(1).lower(),
                "files": files, "within_days": n}

    m = _PRED_HASH.match(s)
    if m:
        n = int(m.group(4))
        if not _valid_days(n):
            return None
        return {"form": "hash", "verb": m.group(1).lower(),
                "artifact_hash": m.group(2).lower(),
                "without_files": _split_file_list(m.group(3)) if m.group(3) else [],
                "within_days": n}

    m = _PRED_REF.match(s)
    if m:
        n = int(m.group(3))
        if not _valid_days(n):
            return None
        return {"form": "referencing", "verb": m.group(1).lower(),
                "token": m.group(2), "within_days": n}

    return None


def _predicate_fired(parsed: dict, entry_dt, candidates: List[dict]):
    """Return the candidate that FIRED `parsed` within its window, else None.

    v1 auto-checks the `touching` form ONLY (design §3a: "For the <verb> touching
    <file-list> within <N>d form: scan ..."). The `hash` and `referencing` forms
    parse successfully but have no candidate-side signal to match at v1, so they
    never fire — they sit in the parseable denominator (a confirmed-or-not
    prediction the reconciler cannot yet auto-check), never the numerator. This
    is the documented v1 limitation; a v1.1 may wire artifact_hash / token walks.

    A candidate fires when its merge lands strictly AFTER the verdict and within
    `within_days`, AND any touched file matches any file-list pattern (exact or
    fnmatch glob).
    """
    if not parsed or entry_dt is None or parsed.get("form") != "touching":
        return None
    window_end = entry_dt + _dt.timedelta(days=parsed["within_days"])
    patterns = parsed["files"]
    for cand in candidates:
        merge_dt = _parse_iso(cand.get("merge_time"))
        if merge_dt is None:
            continue
        if not (entry_dt < merge_dt <= window_end):
            continue
        for tf in (cand.get("touched_files") or []):
            if any(_glob_match(tf, pat) for pat in patterns):
                return cand
    return None


def predicate_checkable(parsed: Optional[dict]) -> bool:
    """Single source of truth (used by BOTH the reconciler and render_ledger):
    is this parsed predicate auto-checkable at v1.1?

      touching    -> True  (file-intersection walk)
      referencing -> True  (commit-message token scan)
      hash        -> True ONLY when verb == "revert" (verb-gated revert-only;
                     a `fix of artifact_hash=…` stays uncheckable — there is no
                     candidate population for it without exact-hash matching)
      else / None -> False
    """
    if not parsed:
        return False
    form = parsed.get("form")
    if form in ("touching", "referencing"):
        return True
    if form == "hash":
        return parsed.get("verb") == "revert"
    return False


def _hash_fired(parsed: dict, entry_dt, revert_candidates: List[dict],
                gated_files: List[str], entry_artifact_hash):
    """`hash` form — verb-gated revert-only matcher (design #343).

    A `revert of artifact_hash=<hex> [without touching <files>] within Nd`
    predicate FIRES when an actual revert commit lands strictly after the verdict
    and within the window, touches at least one of the verdict's `gated_files`,
    and touches NONE of the `without_files` exclusion patterns.

    Hash bind: the parsed `artifact_hash` must be a case-insensitive prefix of
    (or equal to) the LEDGER ENTRY's own `artifact_hash` — hashes may be
    abbreviated. A predicate naming a different artifact than the verdict it is
    attached to is malformed and does NOT fire; a null/empty entry hash also
    fails the bind (older rows) → no fire (safe). This makes the parsed hash
    load-bearing, not decorative.
    """
    if not parsed or entry_dt is None or parsed.get("form") != "hash":
        return None
    if parsed.get("verb") != "revert":
        return None
    # Hash bind — the predicate must name THIS verdict's artifact.
    pred_hash = (parsed.get("artifact_hash") or "").lower()
    entry_hash = (entry_artifact_hash or "").lower()
    if not pred_hash or not entry_hash or not entry_hash.startswith(pred_hash):
        return None
    gated = set(gated_files or [])
    without = parsed.get("without_files") or []
    window_end = entry_dt + _dt.timedelta(days=parsed["within_days"])
    for cand in revert_candidates or []:
        merge_dt = _parse_iso(cand.get("merge_time"))
        if merge_dt is None or not (entry_dt < merge_dt <= window_end):
            continue
        touched = cand.get("touched_files") or []
        # Disqualify if the revert touches any excluded path (path-aware glob).
        if any(_glob_match(tf, pat) for tf in touched for pat in without):
            continue
        # Must touch at least one gated file.
        if any(tf in gated for tf in touched):
            return cand
    return None


def _referencing_fired(parsed: dict, entry_dt, reference_candidates: List[dict]):
    """`referencing` form — commit-message token scan matcher (design #343).

    A `<verb> referencing <token> within Nd` predicate FIRES when a candidate
    commit lands strictly after the verdict and within the window AND mentions
    the token as a DELIMITED unit. The non-word lookarounds `(?<!\\w)…(?!\\w)`
    (NOT raw substring, NOT `\\b…\\b`) correctly match `closes #341` / `ping
    @handle` while rejecting `#3419` and `authentication` — `\\b` would silently
    fail on tokens that begin/end with a non-word char (`#341`, `@handle`).
    """
    if not parsed or entry_dt is None or parsed.get("form") != "referencing":
        return None
    token = parsed.get("token") or ""
    if not token:
        return None
    pat = re.compile(rf"(?<!\w){re.escape(token)}(?!\w)", re.I)
    window_end = entry_dt + _dt.timedelta(days=parsed["within_days"])
    for cand in reference_candidates or []:
        merge_dt = _parse_iso(cand.get("merge_time"))
        if merge_dt is None or not (entry_dt < merge_dt <= window_end):
            continue
        if pat.search(cand.get("message") or ""):
            return cand
    return None


def reconcile_predicates(
    ledger_entries: List[dict],
    candidates: List[dict],
    falsification_path: str,
    *,
    now: str,
    revert_candidates: Optional[List[dict]] = None,
    reference_candidates: Optional[List[dict]] = None,
) -> "tuple[List[dict], List[dict]]":
    """Phase 7 second pass (design §3a). Runs AFTER the file-intersection walkback.

    For each ledger entry carrying a non-null `predicted_falsifier`:
      - sentinel  -> excluded from both rate buckets; append nothing.
      - non-code  -> skipped (predicates are defined for code artifacts only).
      - parseable + fired in-window -> append a falsification entry with
        confidence:"high", via:"predicate". Because this runs after the walkback
        and L-9 is latest-wins, a fired predicate takes precedence over a
        walkback match on the same hash (design §3a step 2).
      - parseable + not fired  -> append nothing (counts toward the hit-rate
        denominator only; surfaced by /ledger).
      - unparseable            -> append nothing; do NOT auto-falsify; the
        walkback outcome (if any) stands (design §3a step 1, parse-failure path).

    Returns (classifications, appended). `classifications` has one record per
    non-null predicate — {ledger_entry_hash, skill, sentinel, parseable, fired,
    unparseable, uncheckable} — for tests; /ledger derives its own rates from
    runs.jsonl. Dispatch by form: touching→`_predicate_fired`, hash→`_hash_fired`
    (verb-gated revert-only), referencing→`_referencing_fired`. A parseable but
    not-`predicate_checkable` predicate is classified `uncheckable` and appends
    nothing.
    """
    # F1/F3: gate every git-layer candidate population at the boundary BEFORE
    # the second pass runs over it (this pass escalates a fired predicate to
    # confidence:"high" and flips a FAIL's Brier actual, so corrupt input here
    # is maximally costly). Reference candidates additionally require a string
    # `message` (their matcher scans it); all require a parseable merge_time
    # (fail-CLOSED — a fix we cannot place in time fires no predicate, F2).
    raw_total = len(candidates) + len(revert_candidates or []) \
        + len(reference_candidates or [])
    candidates = [c for c in candidates if _valid_candidate(c)]
    revert_candidates = [c for c in (revert_candidates or [])
                         if _valid_candidate(c)]
    reference_candidates = [c for c in (reference_candidates or [])
                            if _valid_candidate(c, require_message=True)]
    dropped = raw_total - (len(candidates) + len(revert_candidates)
                           + len(reference_candidates))
    if dropped:
        _warn(f"reconcile_predicates: dropped {dropped} candidate(s) failing "
              f"schema validation (bad merge_time / touched_files / message)")
    classifications: List[dict] = []
    appended: List[dict] = []
    skipped_identityless = 0
    for e in ledger_entries:
        pf = e.get("predicted_falsifier")
        if pf is None:
            continue
        # #402 read-side: an identity-less predicate row has no stable join key
        # to attribute a fired falsifier to — skip + count rather than hash it
        # into the shared "unknown:unknown" bucket.
        run_id = e.get("run_id")
        skill = e.get("skill")
        if not valid_ledger_identity(e):
            skipped_identityless += 1
            continue
        h = ledger_entry_hash(run_id, skill)

        if pf == PREDICATE_SENTINEL:
            classifications.append({
                "ledger_entry_hash": h, "skill": skill, "sentinel": True,
                "parseable": False, "fired": False, "unparseable": False,
                "uncheckable": False})
            continue

        # Predicates are only defined for code artifacts (emit rule). A stray
        # predicate on a non-code entry is out of scope — skip without counting.
        if e.get("artifact_type") != "code":
            continue

        parsed = parse_predicate(pf)
        if parsed is None:
            classifications.append({
                "ledger_entry_hash": h, "skill": skill, "sentinel": False,
                "parseable": False, "fired": False, "unparseable": True,
                "uncheckable": False})
            continue

        # Parseable but not auto-checkable (e.g. a non-revert `hash` predicate):
        # classified `uncheckable`, excluded from the hit-rate denominator.
        if not predicate_checkable(parsed):
            classifications.append({
                "ledger_entry_hash": h, "skill": skill, "sentinel": False,
                "parseable": False, "fired": False, "unparseable": False,
                "uncheckable": True})
            continue

        entry_dt = _parse_iso(e.get("timestamp"))
        form = parsed.get("form")
        if form == "touching":
            cand = _predicate_fired(parsed, entry_dt, candidates)
        elif form == "hash":
            cand = _hash_fired(parsed, entry_dt, revert_candidates,
                               e.get("gated_files") or [], e.get("artifact_hash"))
        else:  # referencing
            cand = _referencing_fired(parsed, entry_dt, reference_candidates)
        fired = cand is not None
        classifications.append({
            "ledger_entry_hash": h, "skill": skill, "sentinel": False,
            "parseable": True, "fired": fired, "unparseable": False,
            "uncheckable": False})

        if fired:
            _how = {
                "touching": "touched a predicted file",
                "hash": "reverted the predicted artifact",
                "referencing": "referenced the predicted token",
            }.get(form, "matched the predicate")
            reason = (
                f"predicted_falsifier {pf!r} fired: {parsed['verb']} "
                f"{cand.get('commit', '?')} {_how} within the "
                f"{parsed['within_days']}d window"
            )
            entry = {
                "ledger_entry_hash": h,
                "falsified": True,
                "falsified_by": {
                    "commit": cand.get("commit"),
                    "reason": reason,
                    "confidence": "high",
                    "cross_cut": False,
                    "via": "predicate",
                },
                "confidence": "high",
                "reasoning": reason,
                "cross_cut": False,
                "via": "predicate",
            }
            _ledger_append(falsification_path, entry)
            appended.append(entry)

    if skipped_identityless:
        _warn(f"reconcile_predicates: skipped {skipped_identityless} predicate "
              f"row(s) lacking a valid (run_id, skill) identity (#402)")

    return classifications, appended


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
# Conventional-commit subject of a SQUASH-merged fix landing: `fix:`,
# `fix(scope):`, `fix(scope)!:`, `hotfix:`. Anchored at start so `prefix:`,
# `fixture:`, `affix:` do NOT match (#439 — squash workflow has no fix/* merge).
_FIX_COMMIT_RE = re.compile(r"^(?:hot)?fix(?:\([^)]*\))?!?:", re.I)


def _is_fix_merge_subject(subject: str) -> bool:
    """True iff a merge-commit subject references a fix/* or hotfix/* branch.

    Anchored on a branch boundary (start-of-string / whitespace / slash /
    quote) so it matches `fix/` and `hotfix/` but NOT `prefix/`, `affix/`,
    `suffix/` where the token is mid-word (S-4)."""
    if not subject:
        return False
    return _FIX_MERGE_RE.search(subject) is not None


def _is_fix_commit_subject(subject: str) -> bool:
    """True iff a non-merge commit subject is a conventional-commit fix landing
    (`fix:` / `fix(scope):` / `fix(scope)!:` / `hotfix:`). This is the squash-
    merge analog of `_is_fix_merge_subject`: repos that squash-merge (the
    default here) land a fix as a single non-merge commit, never a fix/* merge,
    so the merge-only discovery missed every one of them (#439)."""
    if not subject:
        return False
    return _FIX_COMMIT_RE.match(subject) is not None


def discover_candidates(lookback_days: int = 30) -> List[dict]:
    """Discover fix/* hotfix/* merges within lookback_days, plus regression
    issues with a referenced commit (best-effort).

    Each candidate: {"commit", "touched_files": [...], "merge_time": iso}.
    """
    candidates: List[dict] = []
    since = (
        _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=lookback_days)
    ).strftime("%Y-%m-%d")

    # A fix lands one of two ways, depending on the repo's merge policy. We
    # discover both on the mainline first-parent chain (so feature-branch internal
    # commits are never double-counted against their own merge):
    #   (1) MERGE workflow — a merge commit whose subject names a fix/* branch.
    #   (2) SQUASH workflow (the default here) — a single non-merge commit with a
    #       conventional-commit `fix(...)` subject. Missing this class was the #439
    #       Fatal: merge-only discovery found zero squash-merged fixes.
    for fp_args, is_fix in (
        (["--merges"], _is_fix_merge_subject),
        (["--no-merges"], _is_fix_commit_subject),
    ):
        log = _git([
            "log", "--first-parent", *fp_args, f"--since={since}",
            "--pretty=format:%H%x1f%cI%x1f%s",
        ])
        if not log:
            continue
        for line in log.splitlines():
            parts = line.split("\x1f")
            if len(parts) < 3:
                continue
            sha, when, subject = parts[0], parts[1], parts[2]
            if not is_fix(subject):
                continue
            candidates.append({
                "commit": sha,
                "touched_files": _touched_files(sha),
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
    # `--first-parent` is load-bearing (#439): plain `git show` emits NO diff for
    # a merge commit, so every fix/* merge candidate got empty touched_files and
    # walkback falsification silently never fired. `--first-parent` shows the
    # merge's net change vs mainline; on a non-merge (squash) commit it is a no-op.
    out = _git(["show", "--first-parent", "--name-only", "--pretty=format:", sha])
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


_REVERT_BRANCH_RE = re.compile(r"(?:^|[\s/'\"])revert/", re.I)


def discover_revert_candidates(lookback_days: int = 30) -> List[dict]:
    """Discover revert commits within lookback_days (#343 `hash` form).

    `git revert` writes subject `Revert "<orig>"`, so `^Revert` anchors the
    canonical form deterministically; we ALSO include merge commits of a
    `revert/*` branch. Each: {"commit", "touched_files", "merge_time",
    "message"}. Deterministic over a local clone (same class as the existing
    `touching` discovery). NOT exercised by unit tests.
    """
    since = (
        _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=lookback_days)
    ).strftime("%Y-%m-%d")
    out: List[dict] = []
    seen: set = set()

    # (a) canonical `git revert` commits: subject begins with `Revert`.
    log = _git([
        "log", f"--since={since}", "--grep=^Revert",
        "--pretty=format:%H%x1f%cI%x1f%s",
    ])
    if log:
        for line in log.splitlines():
            parts = line.split("\x1f")
            if len(parts) < 3:
                continue
            sha, when, subject = parts[0], parts[1], parts[2]
            if sha in seen:
                continue
            seen.add(sha)
            out.append({"commit": sha, "touched_files": _touched_files(sha),
                        "merge_time": when, "message": subject})

    # (b) merges of a revert/* branch.
    mlog = _git([
        "log", "--merges", f"--since={since}",
        "--pretty=format:%H%x1f%cI%x1f%s",
    ])
    if mlog:
        for line in mlog.splitlines():
            parts = line.split("\x1f")
            if len(parts) < 3:
                continue
            sha, when, subject = parts[0], parts[1], parts[2]
            if sha in seen or not _REVERT_BRANCH_RE.search(subject or ""):
                continue
            seen.add(sha)
            out.append({"commit": sha, "touched_files": _touched_files(sha),
                        "merge_time": when, "message": subject})
    return out


def discover_reference_commits(tokens: List[str], lookback_days: int = 30) -> List[dict]:
    """Discover commits whose message mentions any of `tokens` (#343 `referencing`).

    A coarse `git log -i --grep=<token>` pre-filter over ALL commits in the
    window (referencing is about any mention, not just fix-merges); the pure
    `_referencing_fired` matcher then applies the exact word-boundary check.
    Each: {"commit", "merge_time", "message"} (full subject+body). NO `gh` PR
    scan — PR search is non-deterministic/mutable and would make a shared-ledger
    Brier depend on which machine/when reconcile ran (determinism invariant).
    NOT exercised by unit tests.
    """
    since = (
        _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=lookback_days)
    ).strftime("%Y-%m-%d")
    out: List[dict] = []
    seen: set = set()
    for token in {t for t in tokens if t}:
        log = _git([
            "log", "-i", f"--grep={token}", f"--since={since}",
            "--pretty=format:%H%x1f%cI%x1f%B%x1e",
        ])
        if not log:
            continue
        for rec in log.split("\x1e"):
            rec = rec.strip("\n")
            if not rec.strip():
                continue
            parts = rec.split("\x1f")
            if len(parts) < 3:
                continue
            sha, when, message = parts[0].strip(), parts[1].strip(), parts[2]
            if sha in seen:
                continue
            seen.add(sha)
            out.append({"commit": sha, "merge_time": when, "message": message})
    return out


def fix_branch_sizes(days: int = 90) -> List[int]:
    """Touched-file counts of fix/hotfix landings over the prior `days` (a
    DISTINCT 90-day window from the 30-day candidate lookback). Counts BOTH
    fix/* merges and squash-merged `fix(...)` commits (#439) — counting only
    merges left every size at 0 on a squash-merge repo, collapsing the p90
    cross-cut threshold."""
    since = (
        _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)
    ).strftime("%Y-%m-%d")
    sizes: List[int] = []
    for fp_args, is_fix in (
        (["--merges"], _is_fix_merge_subject),
        (["--no-merges"], _is_fix_commit_subject),
    ):
        log = _git([
            "log", "--first-parent", *fp_args, f"--since={since}",
            "--pretty=format:%H%x1f%s",
        ])
        if not log:
            continue
        for line in log.splitlines():
            parts = line.split("\x1f")
            if len(parts) < 2:
                continue
            sha, subject = parts[0], parts[1]
            if not is_fix(subject):
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
    # F5 (#408): every git call collapses a timeout / corrupt-repo / git-absent
    # failure to None, so candidates=0 is indistinguishable from "no fixes
    # merged" — a falsely-clean reconciliation. Probe git liveness once up front
    # and warn loudly, so the operator can tell "git couldn't look" from
    # "git looked and found nothing".
    if _git(["rev-parse", "--is-inside-work-tree"]) is None:
        _warn("git is unavailable or this is not a work tree; candidate "
              "discovery will return 0 with no signal — a reported "
              "candidates=0 / falsified+=0 is NOT evidence that no fixes merged")
    candidates = discover_candidates(lookback_days=args.lookback_days)
    threshold = cross_cut_threshold_from(fix_branch_sizes(days=90))

    appended = reconcile(
        args.ledger, args.falsification, args.manual_attribution, candidates,
        cross_cut_threshold=threshold, lookback_days=args.lookback_days, now=now,
    )

    # §3a Phase 7 second pass: pre-registered predicate walk. Runs AFTER the
    # walkback so a fired predicate wins precedence under L-9 (latest-wins).
    entries = load_jsonl(args.ledger)
    # #343: per-form candidate populations (SEPARATE lists, not added to
    # `candidates`, so walkback/touching is unregressed). Reference tokens are
    # extracted once from the referencing predicates present in the ledger.
    revert_candidates = discover_revert_candidates(lookback_days=args.lookback_days)
    ref_tokens: List[str] = []
    for e in entries:
        pf = e.get("predicted_falsifier")
        if not pf or pf == PREDICATE_SENTINEL:
            continue
        parsed = parse_predicate(pf)
        if parsed and parsed.get("form") == "referencing":
            ref_tokens.append(parsed["token"])
    reference_candidates = (
        discover_reference_commits(ref_tokens, lookback_days=args.lookback_days)
        if ref_tokens else []
    )
    classifications, predicate_appended = reconcile_predicates(
        entries, candidates, args.falsification, now=now,
        revert_candidates=revert_candidates,
        reference_candidates=reference_candidates,
    )
    parseable = sum(1 for c in classifications if c.get("parseable"))
    unparseable = sum(1 for c in classifications if c.get("unparseable"))

    # Recompute Brier over the full ledger + reduced falsification map (which now
    # includes any predicate-sourced entries, predicate winning per L-9).
    fmap = _falsification_reduce(args.falsification)
    brier = compute_brier(entries, fmap, now=now)

    # Write brier-rolling.json (gitignored) — torn-write-safe (#400): every
    # reader (brier_advisory) degrades a corrupt rolling file silently to {},
    # so a half-written file would make the advisory vanish without a trace.
    try:
        rolling = json.dumps(brier, indent=2, sort_keys=True) + "\n"
        atomic_write_text(args.brier_out, rolling)
    except OSError as e:
        print(f"[calibration-reconcile] could not write brier-rolling.json: {e}",
              file=sys.stderr)

    print(f"[calibration-reconcile] candidates={len(candidates)} "
          f"cross_cut_threshold={threshold} falsified+={len(appended)} "
          f"predicate_falsified+={len(predicate_appended)} "
          f"predicates(parseable={parseable} unparseable={unparseable}) "
          f"skills_scored={len(brier)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
