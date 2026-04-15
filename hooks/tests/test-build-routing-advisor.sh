#!/usr/bin/env bash
# hooks/tests/test-build-routing-advisor.sh
# Acceptance test suite for the build-routing-advisor.sh PreToolUse hook (#174).
#
# RED phase: hook does not yet exist. Tests MUST FAIL initially.
# Each test maps to an acceptance criterion (AC) from
# docs/plans/2026-04-14-build-routing-enforcement-design.md.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK="$SCRIPT_DIR/../build-routing-advisor.sh"

PASSED=0
FAILED=0
TOTAL=10

# ── Setup temp dirs / fake project memory ──────────────────────────────
TMPDIR_BASE="$(mktemp -d)"
FAKE_HOME="$TMPDIR_BASE/fakehome"
FAKE_PROJECT="$TMPDIR_BASE/project"
mkdir -p "$FAKE_PROJECT"
# Initialize a git repo so `git branch --show-current` returns a value
( cd "$FAKE_PROJECT" && git init -q -b test-branch >/dev/null 2>&1 \
  && git -c user.email=t@t -c user.name=t commit -q --allow-empty -m init >/dev/null 2>&1 ) || true

# Match Claude Code's native marker-writer convention: tr '/' '-' on the
# absolute path. (Previous sha256 derivation was incorrect — see S3-R1.)
# The echo-n-vs-echo concern (historical F4) is moot under the tr derivation.
# Note: variable name stays PROJECT_HASH for readability, but the VALUE is now
# a dash-sanitized path segment, not a hash.
PROJECT_HASH="$(echo "$FAKE_PROJECT" | tr '/' '-')"
MEMORY_DIR="$FAKE_HOME/.claude/projects/$PROJECT_HASH/memory"
MARKER_PATH="$MEMORY_DIR/.pipeline-active"
SENTINEL_PATH="$MEMORY_DIR/.build-routing-advisor-disabled"
STATE_PATH="$MEMORY_DIR/build-routing-advisor-state.md"

mkdir -p "$MEMORY_DIR"

cleanup() {
  rm -rf "$TMPDIR_BASE"
}
trap cleanup EXIT

# ── Helpers ────────────────────────────────────────────────────────────
reset_state() {
  rm -f "$MARKER_PATH" "$SENTINEL_PATH" "$STATE_PATH"
  unset CRUCIBLE_DISABLE_BUILD_ROUTING_ADVISOR
}

# Build a Task PreToolUse JSON payload.
# args: prompt, [subagent_type=general-purpose]
make_task_json() {
  local prompt="$1"
  local subagent="${2:-general-purpose}"
  jq -nc --arg p "$prompt" --arg s "$subagent" \
    '{"tool":"Task","tool_input":{"prompt":$p,"subagent_type":$s}}'
}

# Write a pipeline-active marker.
# args: skill, start_time(ISO), branch, [pipeline_id]
write_marker() {
  local skill="$1"
  local start_time="$2"
  local branch="$3"
  local pid="${4:-build-test-pipeline-id}"
  jq -nc \
    --arg sk "$skill" --arg st "$start_time" --arg br "$branch" --arg pid "$pid" \
    '{skill:$sk, start_time:$st, branch:$br, pipeline_id:$pid}' > "$MARKER_PATH"
}

# Run the hook from inside the fake project dir (so $(pwd) hashing matches),
# capturing stderr. Returns exit code in $RC, stderr in $STDERR.
run_hook() {
  local json="$1"
  local stderr_file="$TMPDIR_BASE/stderr.$$"
  set +e
  ( cd "$FAKE_PROJECT" && HOME="$FAKE_HOME" bash "$HOOK" <<< "$json" ) \
    2> "$stderr_file"
  RC=$?
  set -e
  STDERR="$(cat "$stderr_file" 2>/dev/null || true)"
  rm -f "$stderr_file"
}

# Assert the advisory string appears (or does not) in stderr.
# args: test_num, name, expect_advisory(yes|no)
check_advisory() {
  local n="$1" name="$2" expect="$3"
  local has="no"
  if echo "$STDERR" | grep -qiE 'ADVISORY|build-shaped'; then
    has="yes"
  fi
  if [ "$RC" -ne 0 ]; then
    echo "Test $n: $name... FAIL (hook exited $RC, expected 0; stderr: $STDERR)"
    FAILED=$((FAILED + 1))
    return
  fi
  if [ "$has" = "$expect" ]; then
    echo "Test $n: $name... PASS"
    PASSED=$((PASSED + 1))
  else
    echo "Test $n: $name... FAIL (expected advisory=$expect, got=$has; stderr: $STDERR)"
    FAILED=$((FAILED + 1))
  fi
}

# ISO timestamps
NOW_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
STALE_ISO="$(date -u -d '48 hours ago' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
  || date -u -v-48H +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
  || echo "2020-01-01T00:00:00Z")"

# ========================================================================
# Test 1 — MOTIVATING-EXAMPLE CANARY (AC: S3-R6 motivating example)
# Verbatim "spec + implement + PR" with no marker → advisory MUST emit.
# ========================================================================
reset_state
JSON="$(make_task_json "spec + implement + PR")"
run_hook "$JSON"
check_advisory 1 "MOTIVATING CANARY: 'spec + implement + PR' emits advisory" "yes"

# ========================================================================
# Test 2 — Single-category prompt (AC: trigger classification — single category)
# "audit the codebase" matches no category words → no advisory.
# ========================================================================
reset_state
JSON="$(make_task_json "audit the codebase for unused imports")"
run_hook "$JSON"
check_advisory 2 "Single-category audit prompt: no advisory" "no"

# ========================================================================
# Test 3 — Marker suppression (AC: marker fresh + same branch + skill=build)
# 2-of-3 prompt with active fresh same-branch build marker → suppressed.
# ========================================================================
reset_state
write_marker "build" "$NOW_ISO" "test-branch"
JSON="$(make_task_json "implement the new feature and open a PR")"
run_hook "$JSON"
check_advisory 3 "Active fresh same-branch build marker suppresses advisory" "no"

# ========================================================================
# Test 4 — 2-of-3 with no marker (AC: trigger fires when marker absent)
# ========================================================================
reset_state
JSON="$(make_task_json "implement the new feature and open a PR")"
run_hook "$JSON"
check_advisory 4 "Implement+Ship with no marker emits advisory" "yes"

# ========================================================================
# Test 5 — Stale marker (AC: M3-R2/M4-R4 stale marker does not suppress)
# Marker > 24h old → advisory STILL emits.
# ========================================================================
reset_state
write_marker "build" "$STALE_ISO" "test-branch"
JSON="$(make_task_json "implement the new feature and open a PR")"
run_hook "$JSON"
check_advisory 5 "Stale (>24h) marker does NOT suppress advisory" "yes"

# ========================================================================
# Test 6 — Marker on different branch (AC: F1-R3/F2-R3 branch mismatch)
# Fresh, valid skill, but .branch != current branch → advisory STILL emits.
# ========================================================================
reset_state
write_marker "build" "$NOW_ISO" "some-other-branch"
JSON="$(make_task_json "implement the new feature and open a PR")"
run_hook "$JSON"
check_advisory 6 "Different-branch marker does NOT suppress advisory" "yes"

# ========================================================================
# Test 7 — Single-phase disclaimer (AC: S2 disclaimer skip)
# "design only" disclaimer → no advisory even if trigger would fire.
# ========================================================================
reset_state
JSON="$(make_task_json "design only — spec out the implementation approach for the new PR workflow")"
run_hook "$JSON"
check_advisory 7 "Single-phase disclaimer 'design only' skips advisory" "no"

# ========================================================================
# Test 8 — Non-general-purpose subagent_type (AC: SP2 allowlist)
# subagent_type other than general-purpose → no advisory.
# ========================================================================
reset_state
JSON="$(make_task_json "spec + implement + PR" "specialty-mcp-agent")"
run_hook "$JSON"
check_advisory 8 "Non-general-purpose subagent_type skipped" "no"

# ========================================================================
# Test 9 — Kill switch env var (AC: M5-R2)
# CRUCIBLE_DISABLE_BUILD_ROUTING_ADVISOR=1 → no advisory, exit 0 silently.
# ========================================================================
reset_state
JSON="$(make_task_json "spec + implement + PR")"
STDERR_FILE="$TMPDIR_BASE/ks_stderr.$$"
set +e
( cd "$FAKE_PROJECT" \
  && HOME="$FAKE_HOME" CRUCIBLE_DISABLE_BUILD_ROUTING_ADVISOR=1 \
     bash "$HOOK" <<< "$JSON" ) 2> "$STDERR_FILE"
RC=$?
set -e
STDERR="$(cat "$STDERR_FILE" 2>/dev/null || true)"
rm -f "$STDERR_FILE"
check_advisory 9 "Kill switch env var suppresses advisory silently" "no"

# ========================================================================
# Test 10 — Malformed JSON (AC: M5 graceful degradation)
# Garbage stdin → exit 0, no advisory.
# ========================================================================
reset_state
run_hook "this is not json {{{"
check_advisory 10 "Malformed JSON exits 0 with no advisory" "no"

# ── Summary ─────────────────────────────────────────────────────────────
echo ""
echo "Results: $PASSED/$TOTAL passed"

if [ "$FAILED" -gt 0 ]; then
  exit 1
fi
exit 0
