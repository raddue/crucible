#!/usr/bin/env bash
# hooks/tests/tools/build-routing-reconcile.sh
# Post-merge reconciler for the #174 build-routing advisor — READ-ONLY telemetry tool.
#
# Purpose
# -------
# For each merged PR in a window, answer the binary question:
#   "Did this PR's branch write `Status: PASS` to build-gate-ledger.md?"
# If NO → the #174 failure mode occurred (branch merged without /build running).
#
# Usage
# -----
#   bash hooks/tests/tools/build-routing-reconcile.sh [--since <date>] [--repo <path>]
#                                                     [--output <file>] [--json] [--forge]
#
# Arguments
#   --since <date>   Window start (default: "14 days ago"). Accepted by `date -d`
#                    (GNU) or ISO-8601 YYYY-MM-DD.
#   --repo  <path>   Repo root (default: $PWD).
#   --output <file>  Write report to file (default: stdout).
#   --json           Emit JSON instead of markdown.
#   --forge          Append markdown to $PROJECT_MEMORY/forge-scratchpad.md.
#
# Exit codes
#   0   success (irrespective of flagged PR count — this is telemetry, not a gate)
#   2   usage error
#
# DEGRADATION NOTICE (M10-R4 / plan T9 step 0)
# --------------------------------------------
# `hooks/session-index.sh` does NOT index `Task` tool invocations
# (verified: `grep -nE 'Task|subagent_type' hooks/session-index.sh` → no matches).
# Therefore this reconciler runs in **gate-ledger-audit-only mode**: it produces
# the `(merged PR) ∧ (no gate-ledger PASS)` signal ONLY, WITHOUT the
# advisor-fire-count / general-purpose-dispatch-count correlation from plan
# step 7. In this degraded form, T9's output is an INPUT to manual maintainer
# review — NOT an actionable automated signal for the "remove Part 2 if cost >
# value" decision promised by the design's Honest-about-limits clause. That
# decision requires BOTH signals (flagged-PR count AND per-PR advisor fire
# count) to compute a precision estimate; archived advisor state and
# session-index Task coverage are prerequisites.
#
# Similarly, state-file historical enrichment (plan step 6) is NOT available:
# `build-routing-advisor-state.md` is overwritten between runs with no archive
# mechanism, so per-PR advisor-fire counts cannot be reconstructed historically.
#
# Data-source split (plan step 7 note)
# ------------------------------------
# Two directories live under `~/.claude/projects/` under different conventions:
#   - marker-writer:   $HOME/.claude/projects/$(pwd | tr '/' '-')/memory/
#   - session-index:   $HOME/.claude/projects/$(sha256sum(pwd) | cut -c1-16)/memory/session-index/
# The gate-ledger lives under the marker-writer path. This reconciler consults
# ONLY the marker-writer path (session-index is unused in degraded mode).
#
# PR discovery (plan step 3, M4-R4)
# ---------------------------------
# Primary: `gh pr list --state merged --search "base:main merged:>=$SINCE"`.
# Squash-merged PRs have no second parent and are invisible to `git log --merges`,
# so the GitHub API is the canonical source. If `gh` is unavailable, this script
# falls back to `git log --merges --since="$SINCE"` and skips squash-merged PRs
# (with a coverage warning in the report).

set +e

# ── Argument parsing ───────────────────────────────────────────────────
SINCE="14 days ago"
REPO_PATH="$PWD"
OUTPUT_FILE=""
OUTPUT_JSON=false
OUTPUT_FORGE=false

usage() {
  sed -n '3,45p' "$0" >&2
  exit 2
}

while [ $# -gt 0 ]; do
  case "$1" in
    --since)   SINCE="${2:?--since requires a value}"; shift 2 ;;
    --repo)    REPO_PATH="${2:?--repo requires a value}"; shift 2 ;;
    --output)  OUTPUT_FILE="${2:?--output requires a value}"; shift 2 ;;
    --json)    OUTPUT_JSON=true; shift ;;
    --forge)   OUTPUT_FORGE=true; shift ;;
    -h|--help) usage ;;
    *)         echo "ERROR: unknown argument: $1" >&2; usage ;;
  esac
done

if [ ! -d "$REPO_PATH/.git" ]; then
  echo "ERROR: --repo $REPO_PATH is not a git repo" >&2
  exit 2
fi

# Normalize --since to ISO-8601 (YYYY-MM-DD) for gh search and git log
SINCE_ISO="$(date -d "$SINCE" +%Y-%m-%d 2>/dev/null)"
if [ -z "$SINCE_ISO" ]; then
  echo "ERROR: --since value '$SINCE' is not parseable by date -d" >&2
  exit 2
fi

# ── Resolve gate-ledger path (marker-writer convention) ────────────────
REPO_ABS="$(cd "$REPO_PATH" && pwd)"
PROJECT_HASH="$(echo "$REPO_ABS" | tr '/' '-')"
LEDGER_PATH="$HOME/.claude/projects/$PROJECT_HASH/memory/build-gate-ledger.md"

# ── PR enumeration (primary: gh; fallback: git log --merges) ───────────
DISCOVERY_PATH="unknown"
PRS_JSON=""

if command -v gh &>/dev/null; then
  GH_OUT="$(gh pr list \
    --repo "$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || echo "")" \
    --state merged \
    --search "base:main merged:>=$SINCE_ISO" \
    --json number,headRefName,mergeCommit,mergedAt \
    --limit 200 2>/dev/null)"
  if [ -n "$GH_OUT" ] && [ "$GH_OUT" != "[]" ]; then
    PRS_JSON="$GH_OUT"
    DISCOVERY_PATH="gh-api"
  fi
fi

if [ -z "$PRS_JSON" ]; then
  DISCOVERY_PATH="git-log-fallback"
  # Build a minimal JSON array from `git log --merges`. Squash-merged PRs are
  # NOT visible here — report coverage limitation upstream.
  TMP_JSON="$(mktemp)"
  echo "[" > "$TMP_JSON"
  FIRST=true
  while IFS='|' read -r SHA SUBJ DATE; do
    [ -z "$SHA" ] && continue
    # Extract PR number and branch name from merge subject if it matches
    # "Merge pull request #N from user/branch".
    PR_NUM="$(echo "$SUBJ" | grep -oE '#[0-9]+' | head -1 | tr -d '#')"
    BRANCH="$(echo "$SUBJ" | sed -n 's|.*from [^/]*/\(.*\)$|\1|p')"
    [ -z "$PR_NUM" ] && continue
    [ -z "$BRANCH" ] && BRANCH="(unknown)"
    if [ "$FIRST" = "true" ]; then FIRST=false; else echo "," >> "$TMP_JSON"; fi
    printf '  {"number":%s,"headRefName":"%s","mergeCommit":{"oid":"%s"},"mergedAt":"%s"}' \
      "$PR_NUM" "$BRANCH" "$SHA" "$DATE" >> "$TMP_JSON"
  done < <(git -C "$REPO_PATH" log --merges --since="$SINCE_ISO" --pretty=tformat:'%H|%s|%cI')
  echo "" >> "$TMP_JSON"
  echo "]" >> "$TMP_JSON"
  PRS_JSON="$(cat "$TMP_JSON")"
  rm -f "$TMP_JSON"
fi

# ── Gate-ledger signal per PR branch ───────────────────────────────────
# For each PR, check whether the ledger file (in the project-memory path)
# ever gained a `Status: PASS` line reachable from the PR's merge commit OR
# ever, from any commit, on the PR branch.
#
# Note: the ledger is stored in $HOME/.claude/projects/, NOT in the repo
# working tree, so `git log -- build-gate-ledger.md` on the branch tip cannot
# see it. The only ground-truth check available is "does the CURRENT ledger
# contain a PASS line tagged with this branch/PR context?" — which is weaker
# than the plan's per-commit check. We document this and do the best-available
# grep: look for the PR's merge-commit SHA OR branch name inside the ledger.

has_gate_pass() {
  local branch="$1" sha="$2"
  [ ! -f "$LEDGER_PATH" ] && return 1
  # Accept any of: PR/branch mention within ~20 lines of a "Status: PASS" line.
  # This heuristic is the best we can do without per-commit ledger history.
  awk -v b="$branch" -v s="$sha" '
    /Status: PASS/ { pass=1; for (i=NR-20; i<=NR+20; i++) win[i]=1 }
    { lines[NR]=$0 }
    END {
      for (n in win) {
        if (lines[n] ~ b || (s != "" && lines[n] ~ substr(s,1,7))) { print "hit"; exit 0 }
      }
      exit 1
    }
  ' "$LEDGER_PATH" | grep -q hit
}

# ── Classify PRs ───────────────────────────────────────────────────────
if ! command -v jq &>/dev/null; then
  echo "ERROR: jq is required" >&2
  exit 2
fi

FLAGGED_REPORT=""
TOTAL_PRS=0
FLAGGED_COUNT=0

# Iterate with jq -c for robust field extraction
while IFS= read -r PR_LINE; do
  [ -z "$PR_LINE" ] && continue
  TOTAL_PRS=$((TOTAL_PRS + 1))
  PR_NUM="$(echo "$PR_LINE" | jq -r '.number')"
  BRANCH="$(echo "$PR_LINE" | jq -r '.headRefName')"
  SHA="$(echo "$PR_LINE" | jq -r '.mergeCommit.oid // ""')"
  MERGED_AT="$(echo "$PR_LINE" | jq -r '.mergedAt // ""' | cut -c1-10)"

  if ! has_gate_pass "$BRANCH" "$SHA"; then
    FLAGGED_COUNT=$((FLAGGED_COUNT + 1))
    # Count commits on branch (best-effort; may fail for deleted branches)
    COMMITS="$(git -C "$REPO_PATH" rev-list --count "$SHA" 2>/dev/null || echo "?")"
    FLAGGED_REPORT="${FLAGGED_REPORT}- PR #${PR_NUM} (branch: ${BRANCH}, merged ${MERGED_AT}): no gate-ledger PASS found, ${COMMITS} commits"$'\n'
  fi
done < <(echo "$PRS_JSON" | jq -c '.[]' 2>/dev/null)

# ── Emit report ────────────────────────────────────────────────────────
NOW_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

emit_markdown() {
  cat <<EOF
# Build-Routing Reconciler Report

- Generated: $NOW_ISO
- Window: since $SINCE_ISO
- Repo: $REPO_ABS
- PR discovery path: $DISCOVERY_PATH
- Gate-ledger: $LEDGER_PATH $([ -f "$LEDGER_PATH" ] && echo "(found)" || echo "(MISSING)")
- Mode: DEGRADED — gate-ledger-audit-only (session-index lacks Task coverage; see header)

## Summary

- Total merged PRs in window: $TOTAL_PRS
- Flagged (no gate-ledger PASS): $FLAGGED_COUNT

## Flagged PRs

$([ -z "$FLAGGED_REPORT" ] && echo "_(none)_" || echo "$FLAGGED_REPORT")

## Honest-limits notice

In degraded mode, this output is an INPUT to manual maintainer review — NOT an
actionable automated signal for the "remove Part 2 if cost > value" decision.
That decision requires archived advisor state + session-index Task coverage,
which do not yet exist. See header comment and hooks/README.md §T9.
EOF
}

emit_json() {
  # Build flagged array
  jq -n \
    --arg generated "$NOW_ISO" \
    --arg since "$SINCE_ISO" \
    --arg repo "$REPO_ABS" \
    --arg discovery "$DISCOVERY_PATH" \
    --arg ledger "$LEDGER_PATH" \
    --argjson total "$TOTAL_PRS" \
    --argjson flagged_count "$FLAGGED_COUNT" \
    --arg flagged_md "$FLAGGED_REPORT" \
    '{
      generated: $generated,
      since: $since,
      repo: $repo,
      pr_discovery_path: $discovery,
      gate_ledger_path: $ledger,
      mode: "degraded-gate-ledger-audit-only",
      total_merged_prs: $total,
      flagged_count: $flagged_count,
      flagged_markdown: $flagged_md
    }'
}

if [ "$OUTPUT_JSON" = "true" ]; then
  REPORT="$(emit_json)"
else
  REPORT="$(emit_markdown)"
fi

if [ -n "$OUTPUT_FILE" ]; then
  printf '%s\n' "$REPORT" > "$OUTPUT_FILE"
elif [ "$OUTPUT_FORGE" = "true" ]; then
  FORGE_PATH="$HOME/.claude/projects/$PROJECT_HASH/memory/forge-scratchpad.md"
  mkdir -p "$(dirname "$FORGE_PATH")"
  {
    echo ""
    echo "---"
    printf '%s\n' "$REPORT"
  } >> "$FORGE_PATH"
  echo "Appended to $FORGE_PATH" >&2
else
  printf '%s\n' "$REPORT"
fi

exit 0
