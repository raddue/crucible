#!/usr/bin/env bash
# hooks/session-index.sh
# PostToolUse hook for session activity indexing.
# Receives JSON on stdin: {"tool":"Edit","input":{...},"output":{...}}
# Must ALWAYS exit 0 — never block tool execution.
#
# Configured in .claude/settings.json:
#   "hooks": { "PostToolUse": [{ "command": "bash hooks/session-index.sh", "timeout": 500 }] }

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

# ── Noise filter: skip read-only tools ──────────────────────────────────
case "$TOOL" in
  Read|Glob|Grep|TodoRead|ToolSearch)
    exit 0
    ;;
esac

# ── Compute session index path ──────────────────────────────────────────
PROJECT_DIR="$(pwd)"
PROJECT_HASH="$(echo -n "$PROJECT_DIR" | sha256sum | cut -c1-16)"
CLAUDE_PROJECTS_DIR="$HOME/.claude/projects/$PROJECT_HASH"
SESSION_INDEX_BASE="$CLAUDE_PROJECTS_DIR/memory/session-index"

# Session ID: prefer env var, then most-recent dir, then create new
if [ -n "$CLAUDE_SESSION_ID" ]; then
  SESSION_ID="$CLAUDE_SESSION_ID"
else
  # Find most recently modified session dir
  if [ -d "$SESSION_INDEX_BASE" ]; then
    SESSION_ID="$(ls -t "$SESSION_INDEX_BASE" 2>/dev/null | head -1)"
  fi
  if [ -z "$SESSION_ID" ]; then
    SESSION_ID="$(date +%s)"
  fi
fi

SESSION_DIR="$SESSION_INDEX_BASE/$SESSION_ID"
EVENTS_FILE="$SESSION_DIR/events.jsonl"
OUTBOX_FILE="$SESSION_DIR/outbox.jsonl"

# ── Create session directory on first event ─────────────────────────────
if [ ! -d "$SESSION_DIR" ]; then
  mkdir -p "$SESSION_DIR"

  # Stale cleanup: remove session-index directories older than 7 days
  if [ -d "$SESSION_INDEX_BASE" ]; then
    find "$SESSION_INDEX_BASE" -mindepth 1 -maxdepth 1 -type d -mtime +7 -exec rm -rf {} + 2>/dev/null
  fi
fi

# ── Drain outbox (semantic events from skills) ──────────────────────────
if [ -f "$OUTBOX_FILE" ] && [ -s "$OUTBOX_FILE" ]; then
  # Assign proper seq numbers to outbox entries (they arrive with seq:0)
  DRAIN_SEQ=0
  if [ -f "$EVENTS_FILE" ]; then
    DRAIN_SEQ="$(wc -l < "$EVENTS_FILE")"
  fi
  while IFS= read -r outbox_line; do
    if [ -n "$outbox_line" ]; then
      DRAIN_SEQ=$((DRAIN_SEQ + 1))
      echo "$outbox_line" | jq -c --argjson s "$DRAIN_SEQ" '.seq = $s' >> "$EVENTS_FILE" 2>/dev/null
    fi
  done < "$OUTBOX_FILE"
  rm -f "$OUTBOX_FILE"
fi

# ── Classify event ──────────────────────────────────────────────────────
EVENT_TYPE=""
EVENT_SUMMARY=""
EVENT_DETAIL=""

classify_bash() {
  local command
  command="$(echo "$INPUT" | jq -r '.input.command // empty' 2>/dev/null)"
  local exit_code
  exit_code="$(echo "$INPUT" | jq -r '.output.exit_code // .output.exitCode // "0"' 2>/dev/null)"

  # Check for non-zero exit code -> error
  if [ "$exit_code" != "0" ] && [ "$exit_code" != "null" ] && [ -n "$exit_code" ]; then
    local stderr
    stderr="$(echo "$INPUT" | jq -r '.output.stderr // .output.error // empty' 2>/dev/null | head -1 | cut -c1-120)"
    EVENT_TYPE="error"
    EVENT_SUMMARY="Command failed (exit $exit_code): $(echo "$command" | cut -c1-80)"
    EVENT_DETAIL="$(jq -nc --arg cmd "$command" --arg err "$stderr" --arg code "$exit_code" \
      '{command: $cmd, exit_code: ($code | tonumber), error: $err}')"
    return
  fi

  # Skip read-only bash commands
  local cmd_base
  cmd_base="$(echo "$command" | sed 's/^[[:space:]]*//' | cut -d' ' -f1)"
  case "$cmd_base" in
    cat|ls|find|echo|head|tail|less|more|wc|du|df|pwd|which|file|stat|type|test)
      return
      ;;
  esac

  # git commit
  if echo "$command" | grep -qE 'git\s+commit'; then
    local stdout
    stdout="$(echo "$INPUT" | jq -r '.output.stdout // empty' 2>/dev/null)"
    local sha
    sha="$(echo "$stdout" | grep -oE '[0-9a-f]{7,40}' | head -1)"
    local msg
    msg="$(echo "$command" | sed -n 's/.*-m[[:space:]]*["'"'"']\([^"'"'"']*\)["'"'"'].*/\1/p' | cut -c1-80)"
    if [ -z "$msg" ]; then
      msg="$(echo "$stdout" | head -1 | cut -c1-80)"
    fi
    EVENT_TYPE="git_commit"
    EVENT_SUMMARY="Committed${sha:+: $sha} ${msg}"
    EVENT_DETAIL="$(jq -nc --arg sha "${sha:-unknown}" --arg msg "$msg" '{sha: $sha, message: $msg}')"
    return
  fi

  # git checkout / git switch
  if echo "$command" | grep -qE 'git\s+(checkout|switch)'; then
    local branch
    branch="$(echo "$command" | grep -oE '(checkout|switch)\s+(-b\s+)?[^ ]+' | awk '{print $NF}')"
    EVENT_TYPE="git_checkout"
    EVENT_SUMMARY="Branch: $branch"
    EVENT_DETAIL="$(jq -nc --arg branch "$branch" '{branch: $branch}')"
    return
  fi

  # Test runners
  if echo "$command" | grep -qE '(npm\s+test|npx\s+vitest|npx\s+jest|pytest|cargo\s+test|go\s+test|make\s+test|yarn\s+test|pnpm\s+test|bun\s+test)'; then
    local stdout
    stdout="$(echo "$INPUT" | jq -r '.output.stdout // empty' 2>/dev/null | tail -5)"
    EVENT_TYPE="test_run"
    EVENT_SUMMARY="Test run: $(echo "$command" | cut -c1-60) — $(echo "$stdout" | tail -1 | cut -c1-50)"
    EVENT_DETAIL="$(jq -nc --arg cmd "$command" --arg result "$(echo "$stdout" | tail -1 | cut -c1-120)" \
      '{command: $cmd, result: $result}')"
    return
  fi

  # Other non-trivial bash commands — skip (too noisy without specific classification)
}

case "$TOOL" in
  Edit)
    local_file="$(echo "$INPUT" | jq -r '.input.file_path // empty' 2>/dev/null)"
    EVENT_TYPE="file_edit"
    EVENT_SUMMARY="Edited ${local_file##*/}"
    EVENT_DETAIL="$(jq -nc --arg file "$local_file" --arg tool "Edit" '{file: $file, tool: $tool}')"
    ;;
  Write)
    local_file="$(echo "$INPUT" | jq -r '.input.file_path // empty' 2>/dev/null)"
    # Skip outbox writes — these are semantic event emissions, not user file edits
    case "$local_file" in */session-index/*/outbox.jsonl) exit 0 ;; esac
    # Note: file always exists by PostToolUse time, so file_create is not reliably distinguishable
    EVENT_TYPE="file_edit"
    EVENT_SUMMARY="Wrote ${local_file##*/}"
    EVENT_DETAIL="$(jq -nc --arg file "$local_file" --arg tool "Write" '{file: $file, tool: $tool}')"
    ;;
  Bash)
    classify_bash
    ;;
  *)
    # Unknown tool — skip
    exit 0
    ;;
esac

# ── Skip if no event classified ─────────────────────────────────────────
if [ -z "$EVENT_TYPE" ]; then
  exit 0
fi

# ── Compute sequence number ─────────────────────────────────────────────
if [ -f "$EVENTS_FILE" ]; then
  SEQ="$(wc -l < "$EVENTS_FILE")"
  SEQ=$((SEQ + 1))
else
  SEQ=1
fi

# ── Truncate summary to 120 chars ──────────────────────────────────────
EVENT_SUMMARY="$(echo "$EVENT_SUMMARY" | cut -c1-120)"

# ── Build and append JSONL entry ────────────────────────────────────────
TIMESTAMP="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

ENTRY="$(jq -nc \
  --arg ts "$TIMESTAMP" \
  --argjson seq "$SEQ" \
  --arg type "$EVENT_TYPE" \
  --arg summary "$EVENT_SUMMARY" \
  --argjson detail "${EVENT_DETAIL:-null}" \
  '{ts: $ts, seq: $seq, type: $type, summary: $summary, detail: $detail}')"

echo "$ENTRY" >> "$EVENTS_FILE"

# ── Trigger summary writer every 20 events or on semantic events ────────
SHOULD_SUMMARIZE=false
if [ "$EVENT_TYPE" = "phase_change" ] || [ "$EVENT_TYPE" = "skill_end" ] || [ "$EVENT_TYPE" = "error" ] || [ "$EVENT_TYPE" = "decision" ]; then
  SHOULD_SUMMARIZE=true
elif [ $((SEQ % 20)) -eq 0 ]; then
  SHOULD_SUMMARIZE=true
fi

if [ "$SHOULD_SUMMARIZE" = true ]; then
  SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
  if [ -f "$SCRIPT_DIR/session-summary.sh" ]; then
    bash "$SCRIPT_DIR/session-summary.sh" "$EVENTS_FILE" "$SESSION_DIR/summary.md" "$SESSION_ID" &
  fi
fi

exit 0
