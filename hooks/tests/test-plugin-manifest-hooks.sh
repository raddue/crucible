#!/usr/bin/env bash
# hooks/tests/test-plugin-manifest-hooks.sh
# Structural check (#591 item 3): .claude-plugin/plugin.json actually declares
# a PreToolUse registration for gate-ledger-guard.sh, so the plugin install
# path is real rather than just documented. This is a WIRING check — it does
# NOT assert the hook fires at runtime (that's #591 item 4 / #585's scope).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MANIFEST="$REPO_ROOT/.claude-plugin/plugin.json"

PASSED=0
FAILED=0
TOTAL=5

check() {
  local test_num="$1" test_name="$2" expected="$3" actual="$4"
  if [ "$actual" = "$expected" ]; then
    echo "Test $test_num: $test_name... PASS"
    PASSED=$((PASSED + 1))
  else
    echo "Test $test_num: $test_name... FAIL (expected '$expected', got '$actual')"
    FAILED=$((FAILED + 1))
  fi
}

# Test 1: manifest is valid JSON with a hooks.PreToolUse array
VALID_JSON="$(jq -re '.hooks.PreToolUse | type' "$MANIFEST" 2>/dev/null || echo "invalid")"
check 1 "plugin.json has hooks.PreToolUse array" "array" "$VALID_JSON"

# Test 2: some PreToolUse entry's command references gate-ledger-guard.sh
HAS_GUARD_ENTRY="$(jq -e '[.hooks.PreToolUse[].hooks[]?.command // empty | select(contains("gate-ledger-guard.sh"))] | length > 0' "$MANIFEST" 2>/dev/null || echo "false")"
check 2 "a PreToolUse entry references gate-ledger-guard.sh" "true" "$HAS_GUARD_ENTRY"

# Test 3: that entry's command uses CLAUDE_PLUGIN_ROOT (absolute, not repo-relative)
USES_PLUGIN_ROOT="$(jq -e '[.hooks.PreToolUse[].hooks[]?.command // empty | select(contains("gate-ledger-guard.sh"))] | all(contains("CLAUDE_PLUGIN_ROOT"))' "$MANIFEST" 2>/dev/null || echo "false")"
check 3 "gate-ledger-guard.sh command uses \${CLAUDE_PLUGIN_ROOT}" "true" "$USES_PLUGIN_ROOT"

# Test 4: the entry's type is "command" (a bare {command:...} silently no-ops per hooks/README.md)
GUARD_TYPE="$(jq -r '[.hooks.PreToolUse[] | select(.hooks[]?.command // "" | contains("gate-ledger-guard.sh"))][0].hooks[0].type // "missing"' "$MANIFEST" 2>/dev/null || echo "missing")"
check 4 "gate-ledger-guard.sh hook entry has type=command" "command" "$GUARD_TYPE"

# Test 5: matcher covers both Write and Edit (either "*" or a pattern naming both)
GUARD_MATCHER="$(jq -r '[.hooks.PreToolUse[] | select(.hooks[]?.command // "" | contains("gate-ledger-guard.sh"))][0].matcher // ""' "$MANIFEST" 2>/dev/null || echo "")"
MATCHER_OK="false"
if [ "$GUARD_MATCHER" = "*" ] || { echo "$GUARD_MATCHER" | grep -q "Write" && echo "$GUARD_MATCHER" | grep -q "Edit"; }; then
  MATCHER_OK="true"
fi
check 5 "matcher covers Write and Edit" "true" "$MATCHER_OK"

echo ""
echo "Results: $PASSED/$TOTAL passed"

if [ "$FAILED" -gt 0 ] || [ "$((PASSED + FAILED))" -ne "$TOTAL" ]; then
  exit 1
fi
exit 0
