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
# TOTAL is computed dynamically at end (T3.5 M2 / plan line 425).

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

# ========================================================================
# T3.5 — EXTENDED AC COVERAGE (plan lines 374–433)
# Each case below MUST be self-isolated: setup_case() wipes $FAKE_HOME and
# recreates the memory dir from scratch before every case (plan line 424).
# ========================================================================

# Per-case setUp/tearDown — rebuilds FAKE_HOME from empty so no case leaks
# state files, sentinels, markers, or env vars into the next.
setup_case() {
  rm -rf "$FAKE_HOME"
  mkdir -p "$MEMORY_DIR"
  unset CRUCIBLE_DISABLE_BUILD_ROUTING_ADVISOR
}

# Build a Task/Agent payload with explicit tool_name (newer fixtures use
# tool_name; helper mirrors that while remaining compatible with legacy).
# args: prompt, [subagent_type=general-purpose], [tool_name=Agent]
make_agent_json() {
  local prompt="$1"
  # Use ${2-default} (no colon) so an explicit empty string is preserved —
  # ${2:-default} would also default on empty, masking the "" allowlist case.
  local subagent="${2-general-purpose}"
  local tool_name="${3-Agent}"
  jq -nc --arg p "$prompt" --arg s "$subagent" --arg t "$tool_name" \
    '{"tool_name":$t,"tool_input":{"prompt":$p,"subagent_type":$s}}'
}

# Invoke hook with an explicit env-var prefix (e.g. CRUCIBLE_DISABLE_...=1).
# args: env_prefix_string, json
run_hook_env() {
  local env_prefix="$1"
  local json="$2"
  local stderr_file="$TMPDIR_BASE/stderr_env.$$"
  set +e
  ( cd "$FAKE_PROJECT" && eval "HOME=\"$FAKE_HOME\" $env_prefix bash \"$HOOK\"" <<< "$json" ) \
    2> "$stderr_file"
  RC=$?
  set -e
  STDERR="$(cat "$stderr_file" 2>/dev/null || true)"
  rm -f "$stderr_file"
}

# Stderr-to-named-file runner (needed for precise line-count assertions).
# args: json, stderr_file
run_hook_to_file() {
  local json="$1"
  local stderr_file="$2"
  set +e
  ( cd "$FAKE_PROJECT" && HOME="$FAKE_HOME" bash "$HOOK" <<< "$json" ) \
    2> "$stderr_file"
  RC=$?
  set -e
}

pass() { echo "Test $1: $2... PASS"; PASSED=$((PASSED + 1)); }
fail() { echo "Test $1: $2... FAIL ($3)"; FAILED=$((FAILED + 1)); }

# ------------------------------------------------------------------------
# Test E1 — Dedup across (near-)parallel scouts (plan case 1; Min-9/Min-4-R7)
# Two invocations with same prompt → advisory-count ∈ {1,2}, fires-total ∈ {1,2}
# ------------------------------------------------------------------------
setup_case
JSON="$(make_agent_json "spec + implement + PR")"
SE1="$TMPDIR_BASE/e1a.$$"; SE2="$TMPDIR_BASE/e1b.$$"
( cd "$FAKE_PROJECT" && HOME="$FAKE_HOME" bash "$HOOK" <<< "$JSON" ) 2> "$SE1" &
P1=$!
( cd "$FAKE_PROJECT" && HOME="$FAKE_HOME" bash "$HOOK" <<< "$JSON" ) 2> "$SE2" &
P2=$!
wait "$P1"; wait "$P2"
ADV_COUNT=0
grep -q 'ADVISORY' "$SE1" && ADV_COUNT=$((ADV_COUNT + 1))
grep -q 'ADVISORY' "$SE2" && ADV_COUNT=$((ADV_COUNT + 1))
FIRES_TOTAL="$(grep '^fires-total:' "$STATE_PATH" 2>/dev/null | cut -d' ' -f2)"
FP_STATE="$(grep '^last-advisory-fingerprint:' "$STATE_PATH" 2>/dev/null | cut -d' ' -f2)"
FP_EXPECT="$(echo "spec + implement + PR" | sha256sum | cut -c1-16)"
rm -f "$SE1" "$SE2"
if { [ "$ADV_COUNT" = "1" ] || [ "$ADV_COUNT" = "2" ]; } \
   && { [ "$FIRES_TOTAL" = "1" ] || [ "$FIRES_TOTAL" = "2" ]; } \
   && [ "$FP_STATE" = "$FP_EXPECT" ]; then
  pass E1 "Dedup across parallel scouts: count∈{1,2}, fires-total∈{1,2}, FP matches"
else
  fail E1 "Dedup across parallel scouts" "adv=$ADV_COUNT fires=$FIRES_TOTAL fp=$FP_STATE want=$FP_EXPECT"
fi

# ------------------------------------------------------------------------
# Test E2 — Kill-switch auto-expiry (plan case 2)
# sentinel with disabled-until: yesterday → advisor proceeds, trigger fires
# ------------------------------------------------------------------------
setup_case
YESTERDAY="$(date -u -d 'yesterday' +%Y-%m-%d 2>/dev/null \
  || date -u -v-1d +%Y-%m-%d 2>/dev/null || echo "2020-01-01")"
printf "disabled-until: %s\n" "$YESTERDAY" > "$SENTINEL_PATH"
JSON="$(make_agent_json "spec + implement + PR")"
run_hook "$JSON"
if [ "$RC" -eq 0 ] && echo "$STDERR" | grep -q 'ADVISORY'; then
  pass E2 "Kill-switch auto-expiry: expired sentinel allows advisory"
else
  fail E2 "Kill-switch auto-expiry" "rc=$RC stderr=$STDERR"
fi

# ------------------------------------------------------------------------
# Test E3 — Malformed disabled-until (plan case 3): PERMANENTLY DISABLED,
# stderr empty, state records disabled-until-parse-error
# ------------------------------------------------------------------------
setup_case
printf "disabled-until: not-a-date\n" > "$SENTINEL_PATH"
JSON="$(make_agent_json "spec + implement + PR")"
run_hook "$JSON"
if [ "$RC" -eq 0 ] && [ -z "$STDERR" ] \
   && grep -q '^disabled-until-parse-error:' "$STATE_PATH" 2>/dev/null; then
  pass E3 "Malformed disabled-until fail-safe: PERMANENTLY DISABLED + parse-error recorded"
else
  fail E3 "Malformed disabled-until fail-safe" "rc=$RC stderr='$STDERR' state=$(cat "$STATE_PATH" 2>/dev/null)"
fi

# ------------------------------------------------------------------------
# Test E4 — Multiple disabled-until lines (plan case 4): FIRST wins (future
# → honored). Hook uses `grep -m1` so first match governs.
# ------------------------------------------------------------------------
setup_case
TOMORROW="$(date -u -d 'tomorrow' +%Y-%m-%d 2>/dev/null \
  || date -u -v+1d +%Y-%m-%d 2>/dev/null || echo "2099-01-01")"
{ printf "disabled-until: %s\n" "$TOMORROW"
  printf "disabled-until: 2020-01-01\n"; } > "$SENTINEL_PATH"
JSON="$(make_agent_json "spec + implement + PR")"
run_hook "$JSON"
if [ "$RC" -eq 0 ] && ! echo "$STDERR" | grep -q 'ADVISORY'; then
  pass E4 "Multiple disabled-until lines: first (future) wins → honored"
else
  fail E4 "Multiple disabled-until lines" "rc=$RC stderr=$STDERR"
fi

# ------------------------------------------------------------------------
# Test E5 — Asymmetric detached-HEAD (plan case 5): marker .branch empty,
# current branch = "test-branch" → NOT active; advisory fires.
# ------------------------------------------------------------------------
setup_case
write_marker "build" "$NOW_ISO" ""  # empty marker branch
JSON="$(make_agent_json "spec + implement + PR")"
run_hook "$JSON"
if [ "$RC" -eq 0 ] && echo "$STDERR" | grep -q 'ADVISORY'; then
  pass E5 "Asymmetric detached-HEAD: empty marker .branch vs real current → advisory fires"
else
  fail E5 "Asymmetric detached-HEAD" "rc=$RC stderr=$STDERR"
fi

# ------------------------------------------------------------------------
# Test E6 — Branch-switch-mid-pipeline (plan case 6): marker on A, current B.
# ------------------------------------------------------------------------
setup_case
write_marker "build" "$NOW_ISO" "branch-A"
JSON="$(make_agent_json "spec + implement + PR")"
run_hook "$JSON"
if [ "$RC" -eq 0 ] && echo "$STDERR" | grep -q 'ADVISORY'; then
  pass E6 "Branch-switch-mid-pipeline: marker=branch-A, current=test-branch → advisory fires"
else
  fail E6 "Branch-switch-mid-pipeline" "rc=$RC stderr=$STDERR"
fi

# ------------------------------------------------------------------------
# Test E7 — Substring decoys (plan case 7, combined): planning/commitment/
# shipping/codebase as substrings → classification does NOT fire.
# Combined single-case form to keep harness lean.
# ------------------------------------------------------------------------
setup_case
DECOY_OK=1
for DECOY in "planning meeting notes" "commitment to quality" "shipping container" "codebase audit"; do
  JSON="$(make_agent_json "$DECOY")"
  run_hook "$JSON"
  if [ "$RC" -ne 0 ] || echo "$STDERR" | grep -q 'ADVISORY'; then
    DECOY_OK=0
    DECOY_FAIL="$DECOY (rc=$RC stderr=$STDERR)"
    break
  fi
done
if [ "$DECOY_OK" = "1" ]; then
  pass E7 "Substring decoys (planning/commitment/shipping/codebase): no advisory"
else
  fail E7 "Substring decoys" "$DECOY_FAIL"
fi

# ------------------------------------------------------------------------
# Test E8 — subagent_type non-allowlist cases (plan case 8): code-reviewer,
# researcher, custom-agent, "" — all exit 0 with no emission. Combined.
# ------------------------------------------------------------------------
setup_case
NON_OK=1
for ST in "code-reviewer" "researcher" "custom-agent" ""; do
  JSON="$(make_agent_json "spec + implement + PR" "$ST")"
  run_hook "$JSON"
  if [ "$RC" -ne 0 ] || echo "$STDERR" | grep -q 'ADVISORY'; then
    NON_OK=0
    NON_FAIL="subagent='$ST' rc=$RC stderr=$STDERR"
    break
  fi
done
if [ "$NON_OK" = "1" ]; then
  pass E8 "subagent_type non-allowlist (code-reviewer/researcher/custom-agent/\"\"): all skip"
else
  fail E8 "subagent_type non-allowlist" "$NON_FAIL"
fi

# ------------------------------------------------------------------------
# Test E9 — DROPPED per plan line 397-398 drop criterion. Missing-hook-script
# graceful path requires modifying Claude Code's hook dispatcher to test
# meaningfully; documented as T7 manual-verification item instead.
# No test-case block — skipped deliberately.
# ------------------------------------------------------------------------

# ------------------------------------------------------------------------
# Test E10 — Perf P95 informational (plan case 10): 20 back-to-back
# invocations measured externally; assert P95 < 250ms. Single-gate per
# plan line 398 (dual-gate collapsed).
# ------------------------------------------------------------------------
setup_case
JSON="$(make_agent_json "spec + implement + PR")"
TIMES_FILE="$TMPDIR_BASE/times.$$"
: > "$TIMES_FILE"
i=0
while [ "$i" -lt 20 ]; do
  # setup_case each iteration would invalidate perf realism; we keep state
  # across iterations (dedup after first will be cheaper — representative of
  # real steady-state dispatch cadence).
  T_START="$(date +%s%N)"
  ( cd "$FAKE_PROJECT" && HOME="$FAKE_HOME" bash "$HOOK" <<< "$JSON" ) >/dev/null 2>&1
  T_END="$(date +%s%N)"
  echo "$(( (T_END - T_START) / 1000000 ))" >> "$TIMES_FILE"
  i=$((i + 1))
done
# Sort numerically, pick 19th sample (P95 = 19/20 index, 1-indexed).
P95_MS="$(sort -n "$TIMES_FILE" | sed -n '19p')"
rm -f "$TIMES_FILE"
if [ -n "$P95_MS" ] && [ "$P95_MS" -lt 250 ]; then
  pass E10 "Perf P95 informational: P95=${P95_MS}ms < 250ms"
else
  fail E10 "Perf P95 informational" "P95=${P95_MS}ms not < 250ms"
fi
E10_P95="$P95_MS"  # retain for final report

# ------------------------------------------------------------------------
# Test E11 — Stderr capture assertion (plan case 11, programmatic grep).
# ------------------------------------------------------------------------
setup_case
JSON="$(make_agent_json "spec + implement + PR")"
CAPTURED="$TMPDIR_BASE/e11.$$"
run_hook_to_file "$JSON" "$CAPTURED"
if [ "$RC" -eq 0 ] && grep -Fq "ADVISORY:" "$CAPTURED"; then
  pass E11 "Stderr capture: grep -Fq 'ADVISORY:' matches redirected stderr"
else
  fail E11 "Stderr capture" "rc=$RC file=$(cat "$CAPTURED")"
fi
rm -f "$CAPTURED"

# ------------------------------------------------------------------------
# Test E12 — Matcher neither Task nor Agent (plan case 12): exit 0, empty
# stderr, no state mutation.
# ------------------------------------------------------------------------
setup_case
JSON='{"tool_name":"Edit","tool_input":{"file_path":"/tmp/x"}}'
run_hook "$JSON"
STATE_EXISTS_AFTER="no"
[ -f "$STATE_PATH" ] && STATE_EXISTS_AFTER="yes"
if [ "$RC" -eq 0 ] && [ -z "$STDERR" ] && [ "$STATE_EXISTS_AFTER" = "no" ]; then
  pass E12 "Non-Task/non-Agent tool: exit 0, empty stderr, no state write"
else
  fail E12 "Non-Task/non-Agent tool" "rc=$RC stderr='$STDERR' state=$STATE_EXISTS_AFTER"
fi

# ------------------------------------------------------------------------
# Test E13 — Kill-switch toggle preserves dedup fields (plan case 13).
# (a) emit → (b) env-var kill-switch honor → (c) unset → (d) same prompt
# within 5 min → deduped (fingerprint preserved).
# ------------------------------------------------------------------------
setup_case
JSON="$(make_agent_json "spec + implement + PR")"
run_hook "$JSON"                               # (a) emit
FP_A="$(grep '^last-advisory-fingerprint:' "$STATE_PATH" | cut -d' ' -f2)"
FIRES_A="$(grep '^fires-total:' "$STATE_PATH" | cut -d' ' -f2)"
run_hook_env "CRUCIBLE_DISABLE_BUILD_ROUTING_ADVISOR=1" "$JSON"   # (b) honor
FP_B="$(grep '^last-advisory-fingerprint:' "$STATE_PATH" | cut -d' ' -f2)"
# (c) env var naturally unset in next run_hook invocation (setup doesn't run)
run_hook "$JSON"                               # (d) same prompt → deduped
FP_D="$(grep '^last-advisory-fingerprint:' "$STATE_PATH" | cut -d' ' -f2)"
FIRES_D="$(grep '^fires-total:' "$STATE_PATH" | cut -d' ' -f2)"
# Invariants: FP preserved A→B→D; second visible advisory (run 3) is deduped,
# but fires-total increments in suppress branch too → fires_D > fires_A.
if [ -n "$FP_A" ] && [ "$FP_A" = "$FP_B" ] && [ "$FP_B" = "$FP_D" ] \
   && [ "$FIRES_D" -gt "$FIRES_A" ]; then
  pass E13 "Kill-switch toggle preserves dedup FP across honor→release→re-trigger"
else
  fail E13 "Kill-switch toggle" "FP_A=$FP_A FP_B=$FP_B FP_D=$FP_D fires A=$FIRES_A D=$FIRES_D"
fi

# ------------------------------------------------------------------------
# Test E14 — Literal "build-shaped" + exactly-2-line advisory (plan case 14)
# ------------------------------------------------------------------------
setup_case
JSON="$(make_agent_json "spec + implement + PR")"
CAPTURED="$TMPDIR_BASE/e14.$$"
run_hook_to_file "$JSON" "$CAPTURED"
LINE_COUNT="$(grep -c '^' "$CAPTURED")"
if [ "$RC" -eq 0 ] && grep -Fq "build-shaped" "$CAPTURED" && [ "$LINE_COUNT" -eq 2 ]; then
  pass E14 "Advisory contains literal 'build-shaped' AND is exactly 2 lines"
else
  fail E14 "build-shaped / 2-line assertion" "rc=$RC lines=$LINE_COUNT file=$(cat "$CAPTURED")"
fi
rm -f "$CAPTURED"

# ------------------------------------------------------------------------
# Test E15 — State-file bounded growth ≤6 lines (plan case 15).
# DECISION: ≤6 default. Parse-error transitions are NOT included in this
# sequence (they are tested separately in E3). This keeps the assertion clean.
# Sequence: (i) advisory emit → (ii) set sentinel future → honor (iii) advisor
# is re-eligible after sentinel removal → re-fire. Assert wc -l ≤ 6.
# ------------------------------------------------------------------------
setup_case
JSON="$(make_agent_json "spec + implement + PR")"
run_hook "$JSON"                               # (i) emit
printf "disabled-until: %s\n" "$TOMORROW" > "$SENTINEL_PATH"
run_hook "$JSON"                               # (ii) honor
rm -f "$SENTINEL_PATH"
JSON2="$(make_agent_json "spec + implement + PR now")"   # different FP → re-fire
run_hook "$JSON2"                              # (iii) re-fire
LINES="$(wc -l < "$STATE_PATH")"
if [ "$LINES" -le 6 ] 2>/dev/null; then
  pass E15 "State-file bounded growth: $LINES line(s) ≤ 6"
else
  fail E15 "State-file bounded growth" "lines=$LINES file=$(cat "$STATE_PATH")"
fi

# ------------------------------------------------------------------------
# Test E16 — PROJECT_HASH derivation canary (plan case 16; S3-R1).
# Marker at ~/.claude/projects/$(tr '/' '-' on fake project)/memory/
# → build-shaped prompt → hook finds marker and suppresses.
# ------------------------------------------------------------------------
setup_case
write_marker "build" "$NOW_ISO" "test-branch"
JSON="$(make_agent_json "spec + implement + PR")"
run_hook "$JSON"
if [ "$RC" -eq 0 ] && ! echo "$STDERR" | grep -q 'ADVISORY'; then
  pass E16 "PROJECT_HASH derivation canary: tr '/' '-' marker suppresses"
else
  fail E16 "PROJECT_HASH derivation mismatch: hook must look at ~/.claude/projects/\$(echo \$PROJECT_ROOT | tr '/' '-')/memory/.pipeline-active" \
    "rc=$RC stderr=$STDERR"
fi

# ------------------------------------------------------------------------
# Test E17a — Real-fixture pass-through PRIMARY (plan case 17a).
# Non-build-shaped general-purpose fixture: exit 0, empty stderr, state
# mtime unchanged (absent → absent counts as unchanged).
# ------------------------------------------------------------------------
setup_case
FIXTURE_PRIMARY="$SCRIPT_DIR/fixtures/agent-pretooluse-sample.json"
# State file path when hook runs under real crucible cwd (git toplevel =
# /mnt/e/Coding/crucible) — path is different from our FAKE_PROJECT path.
REAL_PROJECT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REAL_HASH="$(echo "$REAL_PROJECT" | tr '/' '-')"
REAL_STATE="$FAKE_HOME/.claude/projects/$REAL_HASH/memory/build-routing-advisor-state.md"
MTIME_BEFORE="absent"
[ -f "$REAL_STATE" ] && MTIME_BEFORE="$(stat -c%Y "$REAL_STATE" 2>/dev/null)"
STDERR_FILE="$TMPDIR_BASE/e17a.$$"
set +e
( cd "$REAL_PROJECT" && HOME="$FAKE_HOME" bash "$HOOK" < "$FIXTURE_PRIMARY" ) 2> "$STDERR_FILE"
RC17A=$?
set -e
MTIME_AFTER="absent"
[ -f "$REAL_STATE" ] && MTIME_AFTER="$(stat -c%Y "$REAL_STATE" 2>/dev/null)"
STDERR_17A="$(cat "$STDERR_FILE")"
rm -f "$STDERR_FILE"
if [ "$RC17A" -eq 0 ] && [ -z "$STDERR_17A" ] && [ "$MTIME_BEFORE" = "$MTIME_AFTER" ]; then
  pass E17a "Real primary fixture: exit 0, empty stderr, state mtime unchanged ($MTIME_BEFORE)"
else
  fail E17a "Real primary fixture pass-through" "rc=$RC17A stderr='$STDERR_17A' mtime before=$MTIME_BEFORE after=$MTIME_AFTER"
fi

# ------------------------------------------------------------------------
# Test E17b — Real-fixture pass-through SECONDARY (plan case 17b).
# subagent_type=Explore (specialty) → allowlist gate suppresses.
# ------------------------------------------------------------------------
setup_case
FIXTURE_SECONDARY="$SCRIPT_DIR/fixtures/agent-pretooluse-build-internal-sample.json"
MTIME_BEFORE="absent"
[ -f "$REAL_STATE" ] && MTIME_BEFORE="$(stat -c%Y "$REAL_STATE" 2>/dev/null)"
STDERR_FILE="$TMPDIR_BASE/e17b.$$"
set +e
( cd "$REAL_PROJECT" && HOME="$FAKE_HOME" bash "$HOOK" < "$FIXTURE_SECONDARY" ) 2> "$STDERR_FILE"
RC17B=$?
set -e
MTIME_AFTER="absent"
[ -f "$REAL_STATE" ] && MTIME_AFTER="$(stat -c%Y "$REAL_STATE" 2>/dev/null)"
STDERR_17B="$(cat "$STDERR_FILE")"
rm -f "$STDERR_FILE"
if [ "$RC17B" -eq 0 ] && [ -z "$STDERR_17B" ] && [ "$MTIME_BEFORE" = "$MTIME_AFTER" ]; then
  pass E17b "Real secondary fixture (Explore specialty): exit 0, empty stderr, no state write"
else
  fail E17b "Real secondary fixture pass-through" "rc=$RC17B stderr='$STDERR_17B' mtime before=$MTIME_BEFORE after=$MTIME_AFTER"
fi

# ------------------------------------------------------------------------
# Test E18 — Trigger (a) Implement+Design, density=2 (plan case 18).
# "implement refactor of design": Implement={implement,refactor}=2 distinct,
# Design={design}=1, Ship=0, TOTAL_DISTINCT≥2 → advisory.
# Trigger rule: Implement≥1 AND (Design≥1 OR Ship≥1) AND total-distinct≥2.
# ------------------------------------------------------------------------
setup_case
JSON="$(make_agent_json "implement refactor of design")"
run_hook "$JSON"
if [ "$RC" -eq 0 ] && echo "$STDERR" | grep -q 'ADVISORY'; then
  pass E18 "Trigger (a) Implement+Design density=2: advisory fires"
else
  fail E18 "Trigger (a)" "rc=$RC stderr=$STDERR"
fi

# ------------------------------------------------------------------------
# Test E19 — Trigger (b) all three (plan case 19): "design, implement, and commit"
# ------------------------------------------------------------------------
setup_case
JSON="$(make_agent_json "design, implement, and commit")"
run_hook "$JSON"
if [ "$RC" -eq 0 ] && echo "$STDERR" | grep -q 'ADVISORY'; then
  pass E19 "Trigger (b) all three categories: advisory fires"
else
  fail E19 "Trigger (b)" "rc=$RC stderr=$STDERR"
fi

# ------------------------------------------------------------------------
# Test E20 — Trigger (c) Design+Ship, no Implement (plan case 20):
# "design doc + merge PR" → Design=1, Ship=2 ({merge,PR}), Implement=0 → NO advisory.
# ------------------------------------------------------------------------
setup_case
JSON="$(make_agent_json "design doc + merge PR")"
run_hook "$JSON"
if [ "$RC" -eq 0 ] && ! echo "$STDERR" | grep -q 'ADVISORY'; then
  pass E20 "Trigger (c) Design+Ship without Implement: no advisory"
else
  fail E20 "Trigger (c)" "rc=$RC stderr=$STDERR"
fi

# ------------------------------------------------------------------------
# Test E21 — Trigger (d) Only-Implement multi-distinct (plan case 21):
# "implement and code and refactor" → Implement=3, Design=0, Ship=0 → NO advisory.
# ------------------------------------------------------------------------
setup_case
JSON="$(make_agent_json "implement and code and refactor")"
run_hook "$JSON"
if [ "$RC" -eq 0 ] && ! echo "$STDERR" | grep -q 'ADVISORY'; then
  pass E21 "Trigger (d) Implement-only multi-distinct: no advisory"
else
  fail E21 "Trigger (d)" "rc=$RC stderr=$STDERR"
fi

# ------------------------------------------------------------------------
# Test E22 — Trigger (e) Implement+Ship (plan case 22): "implement X and commit, push"
# ------------------------------------------------------------------------
setup_case
JSON="$(make_agent_json "implement X and commit, push")"
run_hook "$JSON"
if [ "$RC" -eq 0 ] && echo "$STDERR" | grep -q 'ADVISORY'; then
  pass E22 "Trigger (e) Implement+Ship: advisory fires"
else
  fail E22 "Trigger (e)" "rc=$RC stderr=$STDERR"
fi

# ------------------------------------------------------------------------
# Test E23 — Kill-switch same-day skip-write (plan case 23; S4-R2).
# (a) first invocation → state written, capture MTIME1.
# (b) sleep 1.
# (c) second invocation same day → mtime unchanged (short-circuit on today-match).
# ------------------------------------------------------------------------
setup_case
JSON="$(make_agent_json "spec + implement + PR")"
run_hook_env "CRUCIBLE_DISABLE_BUILD_ROUTING_ADVISOR=1" "$JSON"
RC_A=$RC; STDERR_A="$STDERR"
MTIME1="$(stat -c%Y "$STATE_PATH" 2>/dev/null)"
sleep 1
run_hook_env "CRUCIBLE_DISABLE_BUILD_ROUTING_ADVISOR=1" "$JSON"
RC_B=$RC; STDERR_B="$STDERR"
MTIME2="$(stat -c%Y "$STATE_PATH" 2>/dev/null)"
if [ "$RC_A" -eq 0 ] && [ "$RC_B" -eq 0 ] \
   && [ -z "$STDERR_A" ] && [ -z "$STDERR_B" ] \
   && [ -n "$MTIME1" ] && [ "$MTIME1" = "$MTIME2" ]; then
  pass E23 "Kill-switch same-day skip-write: mtime unchanged ($MTIME1)"
else
  fail E23 "write-elision short-circuit on same-day kill-switch — expected no state-file write, got mtime change" \
    "rc_a=$RC_A rc_b=$RC_B stderr_a='$STDERR_A' stderr_b='$STDERR_B' mtime1=$MTIME1 mtime2=$MTIME2"
fi

# ------------------------------------------------------------------------
# Test E24 — State-file column-0 invariant (plan case 24; S2-R4).
# Emit advisory → assert first line matches ^last-honored: AND each required
# key appears at column 0.
# ------------------------------------------------------------------------
setup_case
JSON="$(make_agent_json "spec + implement + PR")"
run_hook "$JSON"
COL_OK=1
COL_MSG=""
head -1 "$STATE_PATH" | grep -q '^last-honored: ' || { COL_OK=0; COL_MSG="first-line"; }
for KEY in "fires-today" "fires-total" "last-advisory-at" "last-advisory-fingerprint"; do
  grep -q "^$KEY: " "$STATE_PATH" || { COL_OK=0; COL_MSG="$COL_MSG $KEY"; }
done
if [ "$COL_OK" = "1" ]; then
  pass E24 "State-file column-0 invariant: all required keys anchored"
else
  fail E24 "state file lines not column-0 anchored — heredoc indentation regression; see S2-R4 in plan" \
    "missing/mis-anchored:$COL_MSG file=$(cat "$STATE_PATH")"
fi

# ── Summary ─────────────────────────────────────────────────────────────
TOTAL=$((PASSED + FAILED))
echo ""
echo "Results: $PASSED/$TOTAL passed"
[ -n "${E10_P95:-}" ] && echo "Perf E10 P95: ${E10_P95}ms (informational)"

if [ "$FAILED" -gt 0 ]; then
  exit 1
fi
exit 0
