#!/usr/bin/env python3
"""Phase 3 — 90-day fix-branch ledger backfill.

Walks merged `fix/*` and `hotfix/*` PRs in a lookback window and appends
synthetic schema-v1 calibration entries to the machine-local central ledger
store (`default_ledger_dir()` → ~/.claude/crucible/ledger/runs.jsonl, override
via CRUCIBLE_LEDGER_DIR) — the same store every reducer/render/reconcile reads.

These entries seed the corpus to honor #272's "≥10 entries" intent WITHOUT
polluting accuracy claims:
  - `backfilled: true`  -> excluded from Brier (the reconciler's falsifiable
    sample filters `backfilled == false`; see design L-5 + "Backfill semantics").
  - `severity_histogram: null` -> `would_have_shipped_without_gate` is null per
    the mechanical WHS rule (L-3), so the entry is also excluded from the
    `/ledger` "caught N" headline.

Structure: a testable PURE CORE (`pr_to_entry`, `build_entries`) plus a thin
`fetch_prs()` gh shell. The smoke test exercises the pure core with synthetic
PR dicts and never touches real `gh`/network.

Schema is the canonical 22-field v1 from `skills/shared/ledger-append.md`.
Append + dedup go through `scripts.ledger_append` (the importable single source
of truth) — same module T-1 and the Tier A emit call-sites use.

Pure stdlib. No third-party deps.
"""
import argparse
import datetime as _dt
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts.ledger_append import (  # noqa: E402
    append,
    caller_dedup,
    default_ledger_dir,
)

# Write to the machine-local central store every reader actually consumes
# (#270): render_ledger / reconcile_ledger / brier_advisory all route through
# default_ledger_dir() → ~/.claude/crucible/ledger (override via
# CRUCIBLE_LEDGER_DIR). Pinning this to the in-repo .crucible/ tree — as an
# earlier version did — both made the backfill a dead store (no reader reads it)
# and leaked finding data into the PUBLIC repo tree. Do NOT reintroduce an
# in-repo .crucible/ write path here. scripts/check_ledger_write_path.py is an
# AST guard that flags any `.crucible` path-shaped STRING LITERAL in scripts/ —
# it catches every realistic spelling (os.path.join, pathlib, concat, f-string,
# variable segment, multi-line). The only uncaught case is a path assembled with
# no `.crucible` literal at all (e.g. runtime string concat) — don't do that.
LEDGER_PATH = os.path.join(default_ledger_dir(), "runs.jsonl")
DEFAULT_LOOKBACK_DAYS = 90


def _file_path(file_obj: dict) -> str:
    """Map one `files` entry to its path string.

    `gh pr list --json files` returns objects keyed `path` (verified against
    this repo's live API). Older/other gh shapes use `filename`; accept both so
    a gh version bump can't silently empty out `gated_files`.
    """
    return file_obj.get("path") or file_obj.get("filename") or ""


def filter_ignored(paths: list, repo_root: str) -> list:
    """Return only paths NOT currently gitignored in `repo_root`.

    Drops ambient noise (e.g. `.claude/`, `.envrc`) that a historical PR's
    `files` payload may carry from before those paths were gitignored — see the
    `git add -A` incident that polluted PR #320's payload. Such paths are not
    real gated artifacts and shipping them as `gated_files` corrupts /ledger.

    Uses a SINGLE batched `git check-ignore --stdin` call (one path per line on
    stdin) rather than one subprocess per path. check-ignore exit codes:
    0 = some paths matched (ignored), 1 = none matched, 128 = error. Both 0 and
    1 are success; only 128 (or unexpected) is a real failure. The paths it
    prints are the IGNORED ones, so we keep the complement (input order
    preserved).
    """
    if not paths:
        return []
    proc = subprocess.run(
        ["git", "-C", repo_root, "check-ignore", "--stdin"],
        input="\n".join(paths) + "\n",
        capture_output=True,
        text=True,
    )
    if proc.returncode not in (0, 1):
        # 128 (or anything unexpected) -> can't determine ignore status; fail
        # open and keep all paths rather than silently emptying gated_files.
        print(
            f"[backfill WARN] git check-ignore failed (rc={proc.returncode}); "
            f"keeping all paths: {proc.stderr.strip()}",
            file=sys.stderr,
        )
        return list(paths)
    ignored = {line for line in proc.stdout.splitlines() if line}
    return [p for p in paths if p not in ignored]


def pr_to_entry(pr: dict, path_filter=None) -> dict:
    """Map ONE merged-PR dict to ONE schema-v1 (22-field) backfill ledger entry.

    Input keys used: `number`, `mergedAt`, `files` (list of {path|filename}).

    PURE by default: `path_filter` is identity unless a callable is injected
    (the gh-shell path injects a gitignore filter). This function never calls
    git itself, so the pure-core tests stay independent of any repo state.
    """
    if path_filter is None:
        path_filter = lambda ps: ps  # noqa: E731 — identity keeps the core pure
    number = pr["number"]
    # Filter may empty gated_files (all paths gitignored); keep the entry with an
    # empty list anyway — the PR still merged, so [] is the honest record.
    gated_files = path_filter(
        [p for p in (_file_path(f) for f in pr.get("files") or []) if p]
    )
    return {
        "schema_version": 1,
        "run_id": f"backfill-{number}-quality-gate",
        # quality-gate is the canonical attribution for ALL backfilled entries:
        # QG is the broadest gate, so this avoids inventing per-skill Brier
        # baselines for skills that may never have run on the historical artifact.
        "skill": "quality-gate",
        "tier": "A",
        # fix/hotfix branches change code -> artifact_type is always "code".
        "artifact_type": "code",
        # Synthetic PASS: the historical artifact shipped to main; the later fix
        # is the latent regression this entry represents. Inert for Brier
        # (backfilled excluded) and for caught-N (severity_histogram null ->
        # WHS null per L-3).
        "verdict": "PASS",
        "confidence": None,
        # No real gated artifact existed. L-4 falsification keys on
        # sha256(run_id + ":" + skill), NOT artifact_hash, so null is safe here.
        "artifact_hash": None,
        "chunk_hash": None,
        # Files THE FIX touched, not files a verdict actually gated — hence the
        # "inferred-from-fix" comment below.
        "gated_files": gated_files,
        "findings_count": None,
        "severity_histogram": None,
        "highest_finding": None,
        # Follows from severity_histogram == null per the mechanical WHS rule (L-3).
        "would_have_shipped_without_gate": None,
        "rounds": None,
        # REAL historical merge time (verbatim) so /ledger groups the entry into
        # the correct ISO week.
        "timestamp": pr["mergedAt"],
        "backfilled": True,
        "falsified": None,
        "falsified_by": None,
        "gated_files_truncated": 0,
        "comment": "inferred-from-fix",
        # Backfilled entries cannot be retroactively pre-registered -> always
        # null (per L-2 note + design Component 3a).
        "predicted_falsifier": None,
    }


def _parse_iso(ts: str) -> _dt.datetime:
    """Parse an ISO-8601 timestamp (handles trailing 'Z') to aware UTC."""
    return _dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def build_entries(prs: list, lookback_days: int, now_iso: str,
                  path_filter=None) -> list:
    """Filter PRs to those merged within the lookback window, map each to an entry.

    `now_iso` is the window anchor (injected for deterministic tests). PRs with
    a missing/unparseable `mergedAt`, or merged before the cutoff, are dropped.

    `path_filter` is forwarded verbatim to `pr_to_entry`; it defaults to None
    (identity), so synthetic-path tests need no git. The gh-shell path injects a
    gitignore filter to strip ambient non-artifact paths.
    """
    now = _parse_iso(now_iso)
    cutoff = now - _dt.timedelta(days=lookback_days)
    entries = []
    seen_run_ids = set()
    for pr in prs:
        # Guard missing `number` like mergedAt — don't let pr_to_entry KeyError
        # abort the whole run over one malformed PR dict.
        if pr.get("number") is None:
            continue
        merged_at = pr.get("mergedAt")
        if not merged_at:
            continue
        try:
            merged_dt = _parse_iso(merged_at)
            # Comparison sits INSIDE the try: a timezone-naive but parseable
            # mergedAt raises TypeError on `<` against the aware cutoff; treat
            # it as unparseable (skip) rather than aborting the run.
            if merged_dt < cutoff:
                continue
        except (ValueError, AttributeError, TypeError):
            continue
        entry = pr_to_entry(pr, path_filter=path_filter)
        # In-batch dedup: the fix/hotfix unions can in principle overlap, and a
        # PR appearing twice must not yield two entries.
        if entry["run_id"] in seen_run_ids:
            continue
        seen_run_ids.add(entry["run_id"])
        entries.append(entry)
    return entries


def _gh_query(search: str) -> list:
    """Run one `gh pr list` query and return parsed JSON (a list of PR dicts)."""
    out = subprocess.check_output(
        [
            "gh", "pr", "list",
            "--state", "merged",
            "--search", search,
            "--limit", "200",
            "--json", "mergedAt,number,title,files",
        ],
        text=True,
    )
    return json.loads(out)


def fetch_prs() -> list:
    """Fetch merged fix/* and hotfix/* PRs via gh. NOT covered by the smoke test.

    CRITICAL: `gh --search` treats multiple space-separated terms as AND, not
    OR — so a single `head:fix/ head:hotfix/` query returns ZERO matches. We run
    TWO separate queries and union the results. Do NOT collapse these into one
    query or the backfill silently produces nothing.
    """
    fix_prs = _gh_query("head:fix/")
    hotfix_prs = _gh_query("head:hotfix/")
    return fix_prs + hotfix_prs


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill the calibration ledger from merged fix/hotfix PRs."
    )
    parser.add_argument(
        "--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS,
        help="lookback window in days (default: 90)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="print entries as JSON to stdout; do NOT append to the ledger",
    )
    args = parser.parse_args(argv)

    now_iso = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    prs = fetch_prs()
    # Strip ambient non-artifact paths (gitignored now) from each PR's payload —
    # historical PRs (e.g. #320) carry `.claude/` noise from the git-add-A era.
    path_filter = lambda ps: filter_ignored(ps, REPO_ROOT)  # noqa: E731
    entries = build_entries(
        prs, lookback_days=args.lookback_days, now_iso=now_iso,
        path_filter=path_filter,
    )

    if args.dry_run:
        for entry in entries:
            print(json.dumps(entry, separators=(",", ":"), ensure_ascii=False))
        print(
            f"[dry-run] {len(entries)} entries (no append)", file=sys.stderr,
        )
        return 0

    appended = 0
    skipped = 0
    for entry in entries:
        if caller_dedup(LEDGER_PATH, entry["run_id"], entry["skill"]):
            skipped += 1
            continue
        if append(LEDGER_PATH, entry):
            appended += 1
        else:
            print(
                f"[backfill WARN] append failed for {entry['run_id']}",
                file=sys.stderr,
            )
    print(
        f"[backfill] appended={appended} skipped(dup)={skipped} "
        f"total_in_window={len(entries)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
