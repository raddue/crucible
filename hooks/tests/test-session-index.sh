#!/usr/bin/env bash
# hooks/tests/test-session-index.sh
# Acceptance test for hooks/session-index.sh PostToolUse indexer (#623).
# Regression: the indexer read legacy .tool/.input fields and silently
# no-opped on the live .tool_name/.tool_input payload. Tests 1-2 build the
# CANONICAL PostToolUse shape and prove an event is indexed; tests 3-4 prove
# the legacy .tool/.input fallback is still parsed (not a blanket no-op).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK="$SCRIPT_DIR/../session-index.sh"

PASSED=0
FAILED=0
TOTAL=4

# ── Setup temp dirs + fake project home ────────────────────────────────
TMPDIR_BASE="$(mktemp -d)"
FAKE_HOME="$TMPDIR_BASE/fakehome"
FAKE_PROJECT="$TMPDIR_BASE/project"
SESSION_ID="test-session-0001"
mkdir -p "$FAKE_HOME" "$FAKE_PROJECT"

cleanup() { rm -rf "$TMPDIR_BASE"; }
trap cleanup EXIT

# Match the hook's own PROJECT_HASH derivation (sha256 of pwd, first 16 hex).
if command -v sha256sum >/dev/null 2>&1; then
  PROJECT_HASH="$(echo -n "$FAKE_PROJECT" | sha256sum | cut -c1-16)"
else
  PROJECT_HASH="$(echo -n "$FAKE_PROJECT" | shasum -a 256 | cut -c1-16)"
fi
EVENTS_FILE="$FAKE_HOME/.claude/projects/$PROJECT_HASH/memory/session-index/$SESSION_ID/events.jsonl"

# ── Helpers: build CANONICAL (.tool_name/.tool_input) payloads ─────────
make_edit_json() {
  local fp="$1"
  jq -nc --arg sid "$SESSION_ID" --arg fp "$fp" \
    '{session_id:$sid, hook_event_name:"PostToolUse", tool_name:"Edit",
      tool_input:{file_path:$fp, old_string:"old", new_string:"new"}}'
}
make_bash_json() {
  local cmd="$1"
  jq -nc --arg sid "$SESSION_ID" --arg cmd "$cmd" \
    '{session_id:$sid, hook_event_name:"PostToolUse", tool_name:"Bash",
      tool_input:{command:$cmd}}'
}
# ── Helpers: build LEGACY (.tool/.input) payloads ──────────────────────
make_legacy_edit_json() {
  local fp="$1"
  jq -nc --arg fp "$fp" '{tool:"Edit", input:{file_path:$fp}}'
}
make_legacy_bash_json() {
  local cmd="$1"
  jq -nc --arg cmd "$cmd" '{tool:"Bash", input:{command:$cmd}}'
}

# ── Helper: run indexer against the fake project/home ──────────────────
run_indexer() {
  local json="$1"
  (cd "$FAKE_PROJECT" && HOME="$FAKE_HOME" CLAUDE_SESSION_ID="$SESSION_ID" bash "$HOOK" <<< "$json")
}

reset_state() { rm -f "$EVENTS_FILE"; }

# ── Helper: assert the last indexed event's type and a content needle ──
assert_last_event() {
  local num="$1" name="$2" expected_type="$3" expected_needle="$4"
  local line actual_type
  line="$(tail -n 1 "$EVENTS_FILE" 2>/dev/null)"
  actual_type="$(echo "$line" | jq -r '.type // empty' 2>/dev/null)"
  if [ "$actual_type" = "$expected_type" ] && echo "$line" | grep -qF "$expected_needle"; then
    echo "Test $num: $name... PASS"
    PASSED=$((PASSED + 1))
  else
    echo "Test $num: $name... FAIL (type='$actual_type' want '$expected_type', needle '$expected_needle'; line: $line)"
    FAILED=$((FAILED + 1))
  fi
}

# ========================================================================
# Test 1: canonical Edit payload indexes a file_edit event (was silent no-op
# when the hook read legacy `.tool`, resolving TOOL empty and exiting early).
# ========================================================================
reset_state
run_indexer "$(make_edit_json "/work/src/main.go")"
assert_last_event 1 "Canonical .tool_name/.tool_input Edit indexed" "file_edit" "main.go"

# ========================================================================
# Test 2: canonical Bash payload indexes a git_commit event (the
# `.input.command` read resolved empty, so classification never fired).
# ========================================================================
reset_state
run_indexer "$(make_bash_json 'git commit -m "Test commit"')"
assert_last_event 2 "Canonical .tool_name/.tool_input Bash indexed" "git_commit" "Test commit"

# ========================================================================
# Test 3: legacy .tool/.input Edit still indexed — the fallback genuinely
# parses, not a blanket no-op (fallback-preservation guard).
# ========================================================================
reset_state
run_indexer "$(make_legacy_edit_json "/legacy/old.md")"
assert_last_event 3 "Legacy .tool/.input Edit fallback indexed" "file_edit" "old.md"

# ========================================================================
# Test 4: legacy .tool/.input Bash still indexed — exercises the command-path
# fallback specifically (test 3 covers the file_path fallback only).
# ========================================================================
reset_state
run_indexer "$(make_legacy_bash_json 'git commit -m "Legacy commit"')"
assert_last_event 4 "Legacy .tool/.input Bash fallback indexed" "git_commit" "Legacy commit"

# ── Summary ─────────────────────────────────────────────────────────────
echo ""
echo "Results: $PASSED/$TOTAL passed"

if [ "$((PASSED + FAILED))" -ne "$TOTAL" ]; then
  echo "FATAL: $((PASSED + FAILED)) tests recorded a result (PASSED=$PASSED, FAILED=$FAILED) but TOTAL=$TOTAL — a test silently did not run." >&2
  exit 1
fi
if [ "$FAILED" -gt 0 ]; then
  exit 1
fi
exit 0