#!/usr/bin/env bash
# hooks/gate-ledger-guard.sh
# PreToolUse hook for Write/Edit — blocks unauthorized PASS writes to build-gate-ledger.md.
# Receives JSON on stdin: {"tool":"Write","input":{"file_path":"/path","content":"..."}}
#   or for Edit: {"tool":"Edit","input":{"file_path":"/path","old_string":"...","new_string":"..."}}
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
  echo "WARNING: jq not found — gate-ledger-guard is disabled" >&2
  exit 0
fi

# ── Extract tool name ───────────────────────────────────────────────────
TOOL="$(echo "$INPUT" | jq -r '.tool // empty' 2>/dev/null)"
if [ -z "$TOOL" ]; then
  exit 0
fi

# Gate Write and Edit operations
IS_EDIT=false
if [ "$TOOL" = "Edit" ]; then
  IS_EDIT=true
elif [ "$TOOL" != "Write" ]; then
  exit 0
fi

# ── Extract file_path and content ───────────────────────────────────────
FILE_PATH="$(echo "$INPUT" | jq -r '.input.file_path // empty' 2>/dev/null)"

if [ -z "$FILE_PATH" ]; then
  exit 0
fi

if [ "$IS_EDIT" = "true" ]; then
  # Edit tool: check if new_string introduces "Status: PASS" where old_string didn't have it
  EDIT_OLD="$(echo "$INPUT" | jq -r '.input.old_string // empty' 2>/dev/null)"
  EDIT_NEW="$(echo "$INPUT" | jq -r '.input.new_string // empty' 2>/dev/null)"
  if [ -z "$EDIT_NEW" ]; then
    exit 0
  fi
  # If the edit isn't introducing a new PASS, allow it
  if ! echo "$EDIT_NEW" | grep -q 'Status:[[:space:]]*PASS'; then
    exit 0
  fi
  # If old_string already had PASS for the same line, this isn't a new PASS
  if echo "$EDIT_OLD" | grep -q 'Status:[[:space:]]*PASS'; then
    exit 0
  fi
  # A PASS is being introduced via Edit — read the existing file for full context
  RESOLVED_EDIT_PATH="${FILE_PATH/#\~/$HOME}"
  if [ -f "$RESOLVED_EDIT_PATH" ]; then
    CONTENT="$(cat "$RESOLVED_EDIT_PATH" 2>/dev/null)" || true
    # Simulate the edit result: replace old_string with new_string
    # Use awk for literal string replacement (no regex interpretation)
    CONTENT="$(awk -v old="$EDIT_OLD" -v new="$EDIT_NEW" '
      BEGIN { found=0; split(old, old_lines, "\n"); n=length(old_lines) }
      {
        lines[NR] = $0
      }
      END {
        for (i=1; i<=NR; i++) {
          if (found == 0 && lines[i] == old_lines[1]) {
            match_all = 1
            for (j=2; j<=n; j++) {
              if (i+j-1 > NR || lines[i+j-1] != old_lines[j]) {
                match_all = 0
                break
              }
            }
            if (match_all) {
              printf "%s", new
              if (i+n-1 < NR) printf "\n"
              i = i + n - 1
              found = 1
              continue
            }
          }
          print lines[i]
        }
      }
    ' "$RESOLVED_EDIT_PATH")"
  else
    # File doesn't exist yet — use new_string as content
    CONTENT="$EDIT_NEW"
  fi
else
  CONTENT="$(echo "$INPUT" | jq -r '.input.content // empty' 2>/dev/null)"
  if [ -z "$CONTENT" ]; then
    exit 0
  fi
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
    /^## Phase [0-9]+/ {
      # Extract just the phase number — robust against malformed headers
      # like "## Phase 4:Completion" (no space after colon).
      # Uses sub() to isolate the number (portable across awk versions).
      line = $0
      sub(/^## Phase /, "", line)
      sub(/[^0-9].*/, "", line)
      phase = line
    }
    /^Status:/ && phase != "" {
      gsub(/^Status:[[:space:]]*/, "")
      gsub(/[[:space:]]+$/, "")
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

# ── Detect PipelineID change ────────────────────────────────────────────
# If the PipelineID changed between existing and incoming, ALL PASS values are "new"
PIPELINE_CHANGED=false
if [ -f "$RESOLVED_PATH" ] && [ -n "$EXISTING_CONTENT" ]; then
  EXISTING_PID="$(echo "$EXISTING_CONTENT" | grep -m1 '^PipelineID:' | sed 's/^PipelineID:[[:space:]]*//;s/[[:space:]]*$//')"
  INCOMING_PID="$(echo "$CONTENT" | grep -m1 '^PipelineID:' | sed 's/^PipelineID:[[:space:]]*//;s/[[:space:]]*$//')"
  if [ -n "$EXISTING_PID" ] && [ -n "$INCOMING_PID" ] && [ "$EXISTING_PID" != "$INCOMING_PID" ]; then
    PIPELINE_CHANGED=true
  fi
fi

# ── Compare: find phases gaining a new PASS ─────────────────────────────
NEW_PASS_PHASES=""
while IFS=: read -r phase status; do
  [ -z "$phase" ] && continue
  if [ "$status" = "PASS" ]; then
    if [ "$PIPELINE_CHANGED" = "true" ]; then
      # PipelineID changed — treat ALL PASS values as new
      NEW_PASS_PHASES="${NEW_PASS_PHASES} ${phase}"
    else
      # Check if existing file had this phase as PASS already
      OLD_STATUS=""
      if [ -n "$EXISTING_PHASES" ]; then
        OLD_STATUS="$(echo "$EXISTING_PHASES" | grep "^${phase}:" | head -1 | cut -d: -f2)"
      fi
      if [ "$OLD_STATUS" != "PASS" ]; then
        NEW_PASS_PHASES="${NEW_PASS_PHASES} ${phase}"
      fi
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
PIPELINE_ID="$(echo "$CONTENT" | grep -m1 '^PipelineID:' | sed 's/^PipelineID:[[:space:]]*//;s/[[:space:]]*$//')"
if [ -z "$PIPELINE_ID" ]; then
  echo "BLOCKED: PipelineID missing from ledger content — cannot verify quality gate." >&2
  exit 2
fi

# Extract project hash from the file path
# Path format: .../.claude/projects/<hash>/memory/build-gate-ledger.md
PROJECT_HASH="$(echo "$RESOLVED_PATH" | sed -n 's|.*\.claude/projects/\([^/]*\)/memory/.*|\1|p')"
if [ -z "$PROJECT_HASH" ]; then
  echo "BLOCKED: Cannot determine project from ledger path — ensure the ledger is at the canonical path under .claude/projects/." >&2
  exit 2
fi

VERDICT_DIR="$HOME/.claude/projects/$PROJECT_HASH/memory/quality-gate"

# If the verdict directory doesn't exist, block — QG was never run
if [ ! -d "$VERDICT_DIR" ]; then
  echo "BLOCKED: quality-gate verdict directory does not exist — run the quality gate before marking this phase as passed." >&2
  exit 2
fi

# ── Check each phase that gained PASS ───────────────────────────────────
# Phase name mapping: 1=design, 2=plan, 4=code
# Note: "code" is the QG artifact type for Phase 4 (displayed as "Completion" in the
# ledger). This value must match the Phase field written in verdict markers by the
# quality-gate skill, NOT the human-facing phase display name.
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
    MARKER_PID="$(grep -m1 '^PipelineID:' "$MARKER" 2>/dev/null | sed 's/^PipelineID:[[:space:]]*//;s/[[:space:]]*$//')"
    MARKER_VERDICT="$(grep -m1 '^Verdict:' "$MARKER" 2>/dev/null | sed 's/^Verdict:[[:space:]]*//;s/[[:space:]]*$//')"
    MARKER_PHASE="$(grep -m1 '^Phase:' "$MARKER" 2>/dev/null | sed 's/^Phase:[[:space:]]*//;s/[[:space:]]*$//')"

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
