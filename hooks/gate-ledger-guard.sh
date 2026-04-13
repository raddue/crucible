#!/usr/bin/env bash
# hooks/gate-ledger-guard.sh
# PreToolUse hook for Write — blocks unauthorized PASS writes to build-gate-ledger.md.
# Receives JSON on stdin: {"tool":"Write","input":{"file_path":"/path","content":"..."}}
# Exit 0 = allow, non-zero = block (reason on stderr).
#
# Configured in .claude/settings.json:
#   "hooks": { "PreToolUse": [{ "command": "bash hooks/gate-ledger-guard.sh", "timeout": 500 }] }

# Disable errexit — this hook must never fail fatally
set +e

# ── Read stdin ──────────────────────────────────────────────────────────
INPUT="$(cat)"
if [ -z "$INPUT" ]; then
  exit 0
fi

# ── Dependency check (jq required) ─────────────────────────────────────
if ! command -v jq &>/dev/null; then
  exit 0
fi

# ── Extract tool name ───────────────────────────────────────────────────
TOOL="$(echo "$INPUT" | jq -r '.tool // empty' 2>/dev/null)"
if [ -z "$TOOL" ]; then
  exit 0
fi

# Only gate Write operations
if [ "$TOOL" != "Write" ]; then
  exit 0
fi

# ── Extract file_path and content ───────────────────────────────────────
FILE_PATH="$(echo "$INPUT" | jq -r '.input.file_path // empty' 2>/dev/null)"
CONTENT="$(echo "$INPUT" | jq -r '.input.content // empty' 2>/dev/null)"

if [ -z "$FILE_PATH" ] || [ -z "$CONTENT" ]; then
  exit 0
fi

# Only gate writes to build-gate-ledger.md
case "$FILE_PATH" in
  *build-gate-ledger.md) ;;
  *) exit 0 ;;
esac

# ── Parse incoming content: extract phase→status map ────────────────────
# Returns lines like "1:PASS", "2:IN_PROGRESS", etc.
parse_phase_statuses() {
  local text="$1"
  echo "$text" | awk '
    /^## Phase [0-9]+:/ {
      split($0, a, " ")
      # a[3] is "N:" — strip the colon
      gsub(/:/, "", a[3])
      phase = a[3]
    }
    /^Status:/ && phase != "" {
      gsub(/^Status:[[:space:]]*/, "")
      print phase ":" $0
      phase = ""
    }
  '
}

INCOMING_PHASES="$(parse_phase_statuses "$CONTENT")"

# ── Parse existing file (if it exists) ──────────────────────────────────
# Resolve ~ to $HOME for non-interactive shell safety
RESOLVED_PATH="${FILE_PATH/#\~/$HOME}"
EXISTING_PHASES=""
if [ -f "$RESOLVED_PATH" ]; then
  EXISTING_CONTENT="$(cat "$RESOLVED_PATH" 2>/dev/null)" || true
  if [ -n "$EXISTING_CONTENT" ]; then
    EXISTING_PHASES="$(parse_phase_statuses "$EXISTING_CONTENT")"
  fi
fi

# ── Compare: find phases gaining a new PASS ─────────────────────────────
NEW_PASS_PHASES=""
while IFS=: read -r phase status; do
  [ -z "$phase" ] && continue
  if [ "$status" = "PASS" ]; then
    # Check if existing file had this phase as PASS already
    OLD_STATUS=""
    if [ -n "$EXISTING_PHASES" ]; then
      OLD_STATUS="$(echo "$EXISTING_PHASES" | grep "^${phase}:" | head -1 | cut -d: -f2)"
    fi
    if [ "$OLD_STATUS" != "PASS" ]; then
      NEW_PASS_PHASES="${NEW_PASS_PHASES} ${phase}"
    fi
  fi
done <<< "$INCOMING_PHASES"

# Trim leading space
NEW_PASS_PHASES="${NEW_PASS_PHASES# }"

# If no phase gained a new PASS, allow the write
if [ -z "$NEW_PASS_PHASES" ]; then
  exit 0
fi

# ── New PASS detected — verify verdict markers ─────────────────────────

# Extract PipelineID from incoming content
PIPELINE_ID="$(echo "$CONTENT" | grep -m1 '^PipelineID:' | sed 's/^PipelineID:[[:space:]]*//')"
if [ -z "$PIPELINE_ID" ]; then
  # Can't verify without a PipelineID — graceful degradation
  exit 0
fi

# Extract project hash from the file path
# Path format: .../.claude/projects/<hash>/memory/build-gate-ledger.md
PROJECT_HASH="$(echo "$RESOLVED_PATH" | sed -n 's|.*\.claude/projects/\([^/]*\)/memory/.*|\1|p')"
if [ -z "$PROJECT_HASH" ]; then
  # Can't determine project hash — graceful degradation
  exit 0
fi

VERDICT_DIR="$HOME/.claude/projects/$PROJECT_HASH/memory/quality-gate"

# If the verdict directory doesn't exist at all, graceful degradation
if [ ! -d "$VERDICT_DIR" ]; then
  exit 0
fi

# ── Check each phase that gained PASS ───────────────────────────────────
# Phase name mapping: 1=design, 2=plan, 4=code
phase_name() {
  case "$1" in
    1) echo "design" ;;
    2) echo "plan" ;;
    4) echo "code" ;;
    *) echo "" ;;
  esac
}

for PHASE_NUM in $NEW_PASS_PHASES; do
  # Phase 3 should NEVER receive PASS — it uses COMPLETE
  if [ "$PHASE_NUM" = "3" ]; then
    echo "BLOCKED: Phase 3 uses COMPLETE, not PASS." >&2
    exit 2
  fi

  EXPECTED_PHASE="$(phase_name "$PHASE_NUM")"
  if [ -z "$EXPECTED_PHASE" ]; then
    # Unknown phase number — graceful degradation
    continue
  fi

  # Scan verdict markers
  FOUND_MATCH=false
  for MARKER in "$VERDICT_DIR"/gate-verdict-*.md; do
    [ -f "$MARKER" ] || continue
    MARKER_PID="$(grep -m1 '^PipelineID:' "$MARKER" 2>/dev/null | sed 's/^PipelineID:[[:space:]]*//')"
    MARKER_VERDICT="$(grep -m1 '^Verdict:' "$MARKER" 2>/dev/null | sed 's/^Verdict:[[:space:]]*//')"
    MARKER_PHASE="$(grep -m1 '^Phase:' "$MARKER" 2>/dev/null | sed 's/^Phase:[[:space:]]*//')"

    if [ "$MARKER_PID" = "$PIPELINE_ID" ] && [ "$MARKER_VERDICT" = "PASS" ] && [ "$MARKER_PHASE" = "$EXPECTED_PHASE" ]; then
      FOUND_MATCH=true
      break
    fi
  done

  if [ "$FOUND_MATCH" != "true" ]; then
    echo "BLOCKED: Cannot write PASS to gate ledger — no matching verdict marker found for Phase ${PHASE_NUM}. Run the quality gate before marking this phase as passed." >&2
    exit 2
  fi
done

# All new PASS phases verified
exit 0
