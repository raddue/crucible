#!/usr/bin/env bash
# hooks/tests/test-gate-ledger-guard.sh
# Test suite for the gate-ledger-guard.sh PreToolUse hook.
# Runs 17 test cases validating allow/block behavior.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK="$SCRIPT_DIR/../gate-ledger-guard.sh"

PASSED=0
FAILED=0
TOTAL=18

# ── Setup temp directory ────────────────────────────────────────────────
TMPDIR_BASE="$(mktemp -d)"
FAKE_HOME="$TMPDIR_BASE/fakehome"
PROJECT_HASH="abc123test"
MEMORY_DIR="$FAKE_HOME/.claude/projects/$PROJECT_HASH/memory"
VERDICT_DIR="$MEMORY_DIR/quality-gate"
LEDGER_PATH="$MEMORY_DIR/build-gate-ledger.md"

cleanup() {
  rm -rf "$TMPDIR_BASE"
}
trap cleanup EXIT

mkdir -p "$MEMORY_DIR"

# ── Helper: run hook with given JSON, return exit code ──────────────────
run_hook() {
  local json="$1"
  # HOME is set per-subprocess via prefix assignment, so no save/restore needed
  HOME="$FAKE_HOME" bash "$HOOK" <<< "$json"
  return $?
}

# ── Helper: report result ──────────────────────────────────────────────
check() {
  local test_num="$1"
  local test_name="$2"
  local expected_rc="$3"
  local actual_rc="$4"

  if [ "$actual_rc" -eq "$expected_rc" ]; then
    echo "Test $test_num: $test_name... PASS"
    PASSED=$((PASSED + 1))
  else
    echo "Test $test_num: $test_name... FAIL (expected exit $expected_rc, got $actual_rc)"
    FAILED=$((FAILED + 1))
  fi
}

# ── Helper: build ledger content ───────────────────────────────────────
make_ledger() {
  local pipeline_id="$1"
  local p1_status="$2"
  local p2_status="$3"
  local p3_status="$4"
  local p4_status="$5"
  cat <<EOF
# Build Gate Ledger
Run: 2026-04-13T14:00:00
PipelineID: $pipeline_id
Goal: Test goal
Mode: feature

## Phase 1: Design
Status: $p1_status

## Phase 2: Plan
Status: $p2_status

## Phase 3: Execute
Status: $p3_status

## Phase 4: Completion
Status: $p4_status
EOF
}

# ── Helper: build Write JSON ────────────────────────────────────────────
make_json() {
  local file_path="$1"
  local content="$2"
  jq -nc --arg fp "$file_path" --arg c "$content" '{"tool":"Write","input":{"file_path":$fp,"content":$c}}'
}

# ── Helper: build Edit JSON ────────────────────────────────────────────
make_edit_json() {
  local file_path="$1"
  local old_string="$2"
  local new_string="$3"
  jq -nc --arg fp "$file_path" --arg os "$old_string" --arg ns "$new_string" \
    '{"tool":"Edit","input":{"file_path":$fp,"old_string":$os,"new_string":$ns}}'
}

# ── Helper: create verdict marker ──────────────────────────────────────
create_marker() {
  local run_id="$1"
  local pipeline_id="$2"
  local verdict="$3"
  local phase="$4"
  mkdir -p "$VERDICT_DIR"
  cat > "$VERDICT_DIR/gate-verdict-${run_id}.md" <<EOF
Verdict: $verdict
Phase: $phase
PipelineID: $pipeline_id
Rounds: 3
FinalScore: 95
Timestamp: 2026-04-13T14:30:00
RunID: $run_id
EOF
}

# ── Clean state between tests ──────────────────────────────────────────
reset_state() {
  rm -rf "$VERDICT_DIR"
  rm -f "$LEDGER_PATH"
}

# ========================================================================
# Test 1: Non-ledger write (exit 0)
# ========================================================================
reset_state
JSON="$(make_json "/some/other/file.md" "hello world")"
set +e; run_hook "$JSON" 2>/dev/null; RC=$?; set -e
check 1 "Non-ledger write" 0 "$RC"

# ========================================================================
# Test 2: Non-PASS write to ledger (exit 0)
# ========================================================================
reset_state
CONTENT="$(make_ledger "build-test-001" "IN_PROGRESS" "NOT_STARTED" "NOT_STARTED" "NOT_STARTED")"
JSON="$(make_json "$LEDGER_PATH" "$CONTENT")"
set +e; run_hook "$JSON" 2>/dev/null; RC=$?; set -e
check 2 "Non-PASS write" 0 "$RC"

# ========================================================================
# Test 3: PASS write with valid verdict marker (exit 0)
# ========================================================================
reset_state
# Write existing ledger with Phase 1 as IN_PROGRESS
EXISTING="$(make_ledger "build-test-002" "IN_PROGRESS" "NOT_STARTED" "NOT_STARTED" "NOT_STARTED")"
echo "$EXISTING" > "$LEDGER_PATH"
# Create matching verdict marker
create_marker "run-001" "build-test-002" "PASS" "design"
# Write new content with Phase 1 as PASS
CONTENT="$(make_ledger "build-test-002" "PASS" "NOT_STARTED" "NOT_STARTED" "NOT_STARTED")"
JSON="$(make_json "$LEDGER_PATH" "$CONTENT")"
set +e; run_hook "$JSON" 2>/dev/null; RC=$?; set -e
check 3 "PASS write with valid verdict marker" 0 "$RC"

# ========================================================================
# Test 4: PASS write with no verdict marker (exit 2)
# ========================================================================
reset_state
EXISTING="$(make_ledger "build-test-003" "IN_PROGRESS" "NOT_STARTED" "NOT_STARTED" "NOT_STARTED")"
echo "$EXISTING" > "$LEDGER_PATH"
# Create the verdict directory but leave it empty (no markers)
mkdir -p "$VERDICT_DIR"
CONTENT="$(make_ledger "build-test-003" "PASS" "NOT_STARTED" "NOT_STARTED" "NOT_STARTED")"
JSON="$(make_json "$LEDGER_PATH" "$CONTENT")"
set +e; run_hook "$JSON" 2>/dev/null; RC=$?; set -e
check 4 "PASS write with no verdict marker" 2 "$RC"

# ========================================================================
# Test 5: PASS write with mismatched PipelineID (exit 2)
# ========================================================================
reset_state
EXISTING="$(make_ledger "build-test-004" "IN_PROGRESS" "NOT_STARTED" "NOT_STARTED" "NOT_STARTED")"
echo "$EXISTING" > "$LEDGER_PATH"
# Marker has wrong PipelineID
create_marker "run-002" "build-WRONG-id" "PASS" "design"
CONTENT="$(make_ledger "build-test-004" "PASS" "NOT_STARTED" "NOT_STARTED" "NOT_STARTED")"
JSON="$(make_json "$LEDGER_PATH" "$CONTENT")"
set +e; run_hook "$JSON" 2>/dev/null; RC=$?; set -e
check 5 "PASS write with mismatched PipelineID" 2 "$RC"

# ========================================================================
# Test 6: Missing jq (exit 0)
# ========================================================================
reset_state
CONTENT="$(make_ledger "build-test-005" "PASS" "NOT_STARTED" "NOT_STARTED" "NOT_STARTED")"
JSON="$(make_json "$LEDGER_PATH" "$CONTENT")"
# Create a temp bin dir with only coreutils but no jq
NO_JQ_BIN="$TMPDIR_BASE/nojqbin"
mkdir -p "$NO_JQ_BIN"
# Symlink common utilities the hook needs (bash, grep, sed, awk, cat, etc.) but NOT jq
for cmd in bash cat grep sed awk cut date head command mkdir rm; do
  CMD_PATH="$(command -v "$cmd" 2>/dev/null)" || true
  [ -n "$CMD_PATH" ] && ln -sf "$CMD_PATH" "$NO_JQ_BIN/$cmd" 2>/dev/null || true
done
set +e
HOME="$FAKE_HOME" PATH="$NO_JQ_BIN" bash "$HOOK" <<< "$JSON" 2>/dev/null
RC=$?
set -e
rm -rf "$NO_JQ_BIN"
check 6 "Missing jq" 0 "$RC"

# ========================================================================
# Test 7: Missing verdict directory with PASS write (exit 2)
# ========================================================================
# The quality-gate verdict directory does not exist — should block (QG never ran)
reset_state
# reset_state removes VERDICT_DIR, so it won't exist
EXISTING="$(make_ledger "build-test-006" "IN_PROGRESS" "NOT_STARTED" "NOT_STARTED" "NOT_STARTED")"
echo "$EXISTING" > "$LEDGER_PATH"
CONTENT="$(make_ledger "build-test-006" "PASS" "NOT_STARTED" "NOT_STARTED" "NOT_STARTED")"
JSON="$(make_json "$LEDGER_PATH" "$CONTENT")"
set +e; run_hook "$JSON" 2>/dev/null; RC=$?; set -e
check 7 "Missing verdict directory blocks PASS write" 2 "$RC"

# ========================================================================
# Test 8: Malformed JSON stdin (exit 0)
# ========================================================================
reset_state
set +e; run_hook "this is not json at all {{{" 2>/dev/null; RC=$?; set -e
check 8 "Malformed JSON stdin" 0 "$RC"

# ========================================================================
# Test 9: COMPLETE write to ledger (exit 0)
# ========================================================================
reset_state
# Phase 3 going from IN_PROGRESS to COMPLETE — no marker needed
EXISTING="$(make_ledger "build-test-007" "PASS" "PASS" "IN_PROGRESS" "NOT_STARTED")"
echo "$EXISTING" > "$LEDGER_PATH"
CONTENT="$(make_ledger "build-test-007" "PASS" "PASS" "COMPLETE" "NOT_STARTED")"
JSON="$(make_json "$LEDGER_PATH" "$CONTENT")"
set +e; run_hook "$JSON" 2>/dev/null; RC=$?; set -e
check 9 "COMPLETE write to ledger" 0 "$RC"

# ========================================================================
# Test 10: PASS write with wrong-phase marker (exit 2)
# ========================================================================
reset_state
EXISTING="$(make_ledger "build-test-008" "PASS" "IN_PROGRESS" "NOT_STARTED" "NOT_STARTED")"
echo "$EXISTING" > "$LEDGER_PATH"
# Marker has correct PipelineID but Phase: design (Phase 1) instead of plan (Phase 2)
create_marker "run-003" "build-test-008" "PASS" "design"
CONTENT="$(make_ledger "build-test-008" "PASS" "PASS" "NOT_STARTED" "NOT_STARTED")"
JSON="$(make_json "$LEDGER_PATH" "$CONTENT")"
set +e; run_hook "$JSON" 2>/dev/null; RC=$?; set -e
check 10 "PASS write with wrong-phase marker" 2 "$RC"

# ========================================================================
# Test 11: Phase 3 PASS write blocked (exit 2)
# ========================================================================
reset_state
EXISTING="$(make_ledger "build-test-009" "PASS" "PASS" "IN_PROGRESS" "NOT_STARTED")"
echo "$EXISTING" > "$LEDGER_PATH"
# Even with a marker, Phase 3 PASS should be blocked
create_marker "run-004" "build-test-009" "PASS" "execute"
CONTENT="$(make_ledger "build-test-009" "PASS" "PASS" "PASS" "NOT_STARTED")"
JSON="$(make_json "$LEDGER_PATH" "$CONTENT")"
set +e; run_hook "$JSON" 2>/dev/null; RC=$?; set -e
check 11 "Phase 3 PASS write blocked" 2 "$RC"

# ========================================================================
# Test 12: First-run bypass — no ledger, no verdict dir, PASS write (exit 2)
# ========================================================================
# Exercises Finding 1 fix: when no existing ledger and no verdict directory
# exist, a write that introduces PASS should be blocked (QG was never run).
reset_state
# Do NOT create ledger or verdict dir — simulates first-ever run
CONTENT="$(make_ledger "build-test-010" "PASS" "NOT_STARTED" "NOT_STARTED" "NOT_STARTED")"
JSON="$(make_json "$LEDGER_PATH" "$CONTENT")"
set +e; run_hook "$JSON" 2>/dev/null; RC=$?; set -e
check 12 "First-run bypass: no ledger, no verdict dir, PASS blocked" 2 "$RC"

# ========================================================================
# Test 13: INFERRED to PASS without verdict marker (exit 2)
# ========================================================================
# Existing ledger has INFERRED for Phase 1, incoming has PASS for Phase 1,
# but no verdict marker exists — should block the promotion.
reset_state
EXISTING="$(make_ledger "build-test-011" "INFERRED" "NOT_STARTED" "NOT_STARTED" "NOT_STARTED")"
echo "$EXISTING" > "$LEDGER_PATH"
# Create verdict dir but leave it empty (no markers)
mkdir -p "$VERDICT_DIR"
CONTENT="$(make_ledger "build-test-011" "PASS" "NOT_STARTED" "NOT_STARTED" "NOT_STARTED")"
JSON="$(make_json "$LEDGER_PATH" "$CONTENT")"
set +e; run_hook "$JSON" 2>/dev/null; RC=$?; set -e
check 13 "INFERRED to PASS without verdict marker blocked" 2 "$RC"

# ========================================================================
# Test 14: Edit tool introducing PASS → blocked (exit 2)
# ========================================================================
reset_state
# Set up existing ledger with IN_PROGRESS
EXISTING="$(make_ledger "build-test-012" "IN_PROGRESS" "NOT_STARTED" "NOT_STARTED" "NOT_STARTED")"
echo "$EXISTING" > "$LEDGER_PATH"
# Create verdict dir but no matching marker
mkdir -p "$VERDICT_DIR"
# Edit: change "Status: IN_PROGRESS" to "Status: PASS" for Phase 1
JSON="$(make_edit_json "$LEDGER_PATH" "Status: IN_PROGRESS" "Status: PASS")"
set +e; run_hook "$JSON" 2>/dev/null; RC=$?; set -e
check 14 "Edit tool introducing PASS blocked" 2 "$RC"

# ========================================================================
# Test 15: Trailing space on PASS status → blocked (exit 2)
# ========================================================================
reset_state
EXISTING="$(make_ledger "build-test-013" "IN_PROGRESS" "NOT_STARTED" "NOT_STARTED" "NOT_STARTED")"
echo "$EXISTING" > "$LEDGER_PATH"
mkdir -p "$VERDICT_DIR"
# Build content with trailing space after PASS
CONTENT="$(cat <<EOF
# Build Gate Ledger
Run: 2026-04-13T14:00:00
PipelineID: build-test-013
Goal: Test goal
Mode: feature

## Phase 1: Design
Status: PASS

## Phase 2: Plan
Status: NOT_STARTED

## Phase 3: Execute
Status: NOT_STARTED

## Phase 4: Completion
Status: NOT_STARTED
EOF
)"
JSON="$(make_json "$LEDGER_PATH" "$CONTENT")"
set +e; run_hook "$JSON" 2>/dev/null; RC=$?; set -e
check 15 "Trailing space on PASS status blocked" 2 "$RC"

# ========================================================================
# Test 16: PASS write with no PipelineID → blocked (exit 2)
# ========================================================================
reset_state
mkdir -p "$VERDICT_DIR"
# Build content with PASS but no PipelineID line
CONTENT="$(cat <<EOF
# Build Gate Ledger
Run: 2026-04-13T14:00:00
Goal: Test goal
Mode: feature

## Phase 1: Design
Status: PASS

## Phase 2: Plan
Status: NOT_STARTED

## Phase 3: Execute
Status: NOT_STARTED

## Phase 4: Completion
Status: NOT_STARTED
EOF
)"
JSON="$(make_json "$LEDGER_PATH" "$CONTENT")"
set +e; run_hook "$JSON" 2>/dev/null; RC=$?; set -e
check 16 "PASS write with no PipelineID blocked" 2 "$RC"

# ========================================================================
# Test 17: PipelineID changed, existing Phase 1 PASS → requires marker (exit 2)
# ========================================================================
reset_state
# Existing ledger has Phase 1 PASS under old PipelineID
EXISTING="$(make_ledger "build-OLD-pipeline" "PASS" "NOT_STARTED" "NOT_STARTED" "NOT_STARTED")"
echo "$EXISTING" > "$LEDGER_PATH"
# Create marker for OLD pipeline — should NOT satisfy new pipeline
create_marker "run-005" "build-OLD-pipeline" "PASS" "design"
# Incoming content changes PipelineID but keeps Phase 1 PASS
CONTENT="$(make_ledger "build-NEW-pipeline" "PASS" "NOT_STARTED" "NOT_STARTED" "NOT_STARTED")"
JSON="$(make_json "$LEDGER_PATH" "$CONTENT")"
set +e; run_hook "$JSON" 2>/dev/null; RC=$?; set -e
check 17 "PipelineID changed, existing PASS requires new marker" 2 "$RC"

# ========================================================================
# Test 18: Malformed phase header bypass blocked (exit 2)
# ========================================================================
reset_state
mkdir -p "$VERDICT_DIR"
EXISTING="$(make_ledger "build-test-018" "IN_PROGRESS" "NOT_STARTED" "NOT_STARTED" "NOT_STARTED")"
echo "$EXISTING" > "$LEDGER_PATH"
# Malformed content: "## Phase 4:Completion" (no space after colon)
MALFORMED_CONTENT="# Build Gate Ledger
Run: 2026-04-13T14:00:00
PipelineID: build-test-018
Goal: Test goal
Mode: feature

## Phase 1: Design
Status: IN_PROGRESS

## Phase 2: Plan
Status: NOT_STARTED

## Phase 3: Execute
Status: NOT_STARTED

## Phase 4:Completion
Status: PASS"
JSON="$(make_json "$LEDGER_PATH" "$MALFORMED_CONTENT")"
set +e; run_hook "$JSON" 2>/dev/null; RC=$?; set -e
check 18 "Malformed phase header bypass blocked" 2 "$RC"

# ── Summary ─────────────────────────────────────────────────────────────
echo ""
echo "Results: $PASSED/$TOTAL passed"

if [ "$FAILED" -gt 0 ]; then
  exit 1
fi
exit 0
