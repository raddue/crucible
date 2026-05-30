#!/usr/bin/env bash
# hooks/session-summary.sh
# Produces a rolling summary.md from events.jsonl.
# Called by session-index.sh; can also be invoked standalone.
#
# Usage: session-summary.sh <events.jsonl path> <summary.md path> <session-id>
#
# Token budget: ~2000 tokens (~8000 chars). If exceeded, oldest Activity
# Timeline entries are truncated while Files Modified and Key Decisions
# are preserved.

set +e

EVENTS_FILE="${1:?Usage: session-summary.sh <events.jsonl> <summary.md> <session-id>}"
SUMMARY_FILE="${2:?}"
SESSION_ID="${3:?}"

if [ ! -f "$EVENTS_FILE" ] || [ ! -s "$EVENTS_FILE" ]; then
  exit 0
fi

if ! command -v jq &>/dev/null; then
  exit 0
fi

# ── Gather metadata ─────────────────────────────────────────────────────
TOTAL_EVENTS="$(wc -l < "$EVENTS_FILE")"
FIRST_TS="$(head -1 "$EVENTS_FILE" | jq -r '.ts // "unknown"')"
LAST_TS="$(tail -1 "$EVENTS_FILE" | jq -r '.ts // "unknown"')"

# ── Activity Timeline (last 30 events, one line each) ──────────────────
TIMELINE=""
TIMELINE_LINES=0
while IFS= read -r line; do
  ts="$(echo "$line" | jq -r '.ts // ""' 2>/dev/null)"
  type="$(echo "$line" | jq -r '.type // ""' 2>/dev/null)"
  summary="$(echo "$line" | jq -r '.summary // ""' 2>/dev/null)"
  # Extract HH:MM from ISO timestamp
  time_short="$(echo "$ts" | sed 's/.*T\([0-9][0-9]:[0-9][0-9]\).*/\1/')"
  TIMELINE="$TIMELINE
- [$time_short] ($type) $summary"
  TIMELINE_LINES=$((TIMELINE_LINES + 1))
done < <(tail -30 "$EVENTS_FILE")

# ── Files Modified (deduplicated) ───────────────────────────────────────
FILES_MODIFIED=""
while IFS= read -r fpath; do
  if [ -n "$fpath" ] && [ "$fpath" != "null" ]; then
    FILES_MODIFIED="$FILES_MODIFIED
- $fpath"
  fi
done < <(jq -r 'select(.type == "file_edit" or .type == "file_create") | .detail.file // empty' "$EVENTS_FILE" 2>/dev/null | sort -u)

# ── Key Decisions (from decision-type events) ───────────────────────────
DECISIONS=""
while IFS= read -r line; do
  if [ -n "$line" ]; then
    summary="$(echo "$line" | jq -r '.summary // ""' 2>/dev/null)"
    DECISIONS="$DECISIONS
- $summary"
  fi
done < <(jq -c 'select(.type == "decision")' "$EVENTS_FILE" 2>/dev/null)

# ── Errors Encountered ──────────────────────────────────────────────────
ERRORS=""
while IFS= read -r line; do
  if [ -n "$line" ]; then
    ts="$(echo "$line" | jq -r '.ts // ""' 2>/dev/null)"
    summary="$(echo "$line" | jq -r '.summary // ""' 2>/dev/null)"
    time_short="$(echo "$ts" | sed 's/.*T\([0-9][0-9]:[0-9][0-9]\).*/\1/')"
    ERRORS="$ERRORS
- [$time_short] $summary"
  fi
done < <(jq -c 'select(.type == "error")' "$EVENTS_FILE" 2>/dev/null)

# ── Compose summary ─────────────────────────────────────────────────────
SUMMARY="# Session Summary
**Session:** $SESSION_ID
**Started:** $FIRST_TS
**Last Updated:** $LAST_TS
**Events:** $TOTAL_EVENTS

## Activity Timeline
$TIMELINE

## Files Modified
${FILES_MODIFIED:-
- (none)}

## Key Decisions
${DECISIONS:-
- (none)}

## Errors Encountered
${ERRORS:-
- (none)}"

# ── Token budget enforcement (~8000 chars) ──────────────────────────────
CHAR_COUNT="${#SUMMARY}"
if [ "$CHAR_COUNT" -gt 8000 ]; then
  # Truncate Activity Timeline from the oldest end
  # Rebuild with fewer timeline entries until under budget
  KEEP_LINES=$((TIMELINE_LINES - 1))
  while [ "$CHAR_COUNT" -gt 8000 ] && [ "$KEEP_LINES" -gt 5 ]; do
    TIMELINE=""
    while IFS= read -r line; do
      ts="$(echo "$line" | jq -r '.ts // ""' 2>/dev/null)"
      type="$(echo "$line" | jq -r '.type // ""' 2>/dev/null)"
      summary="$(echo "$line" | jq -r '.summary // ""' 2>/dev/null)"
      time_short="$(echo "$ts" | sed 's/.*T\([0-9][0-9]:[0-9][0-9]\).*/\1/')"
      TIMELINE="$TIMELINE
- [$time_short] ($type) $summary"
    done < <(tail -"$KEEP_LINES" "$EVENTS_FILE")

    SUMMARY="# Session Summary
**Session:** $SESSION_ID
**Started:** $FIRST_TS
**Last Updated:** $LAST_TS
**Events:** $TOTAL_EVENTS

## Activity Timeline
*(showing last $KEEP_LINES of $TOTAL_EVENTS events)*
$TIMELINE

## Files Modified
${FILES_MODIFIED:-
- (none)}

## Key Decisions
${DECISIONS:-
- (none)}

## Errors Encountered
${ERRORS:-
- (none)}"

    CHAR_COUNT="${#SUMMARY}"
    KEEP_LINES=$((KEEP_LINES - 5))
  done
fi

# ── Write summary ───────────────────────────────────────────────────────
echo "$SUMMARY" > "$SUMMARY_FILE"

exit 0
