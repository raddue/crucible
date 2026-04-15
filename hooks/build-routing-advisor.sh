#!/usr/bin/env bash
# hooks/build-routing-advisor.sh
# PreToolUse hook for Task/Agent dispatches — warn-only advisor that flags
# build-shaped general-purpose subagent dispatches that bypass an active
# pipeline (#174). Exits 0 on all paths; emits ADVISORY on stderr when a
# dispatch looks build-shaped and no active marker matches.
#
# Mirrors gate-ledger-guard.sh style: set +e; INPUT="$(cat)"; jq // empty;
# all utility failures → exit 0 silently.
#
# Configured in ~/.claude/settings.json:
#   "hooks": { "PreToolUse": [{ "matcher": "Agent",
#     "command": "bash hooks/build-routing-advisor.sh", "timeout": 500 }] }

# Disable errexit — this hook must never fail fatally
set +e

# ── 1. Read stdin ──────────────────────────────────────────────────────
INPUT="$(cat)"
if [ -z "$INPUT" ]; then
  exit 0
fi

# ── 2. Env-var kill-switch (plan lines 181–195, step 2 — before jq etc.)
# Scoped PROJECT_ROOT / PROJECT_MEMORY derivation internal to this branch.
# FIX 3: This now runs BEFORE jq dep check and tool/prompt extraction so
# that non-Task/non-Agent calls still honor the kill-switch, and the honor
# path pays no jq/extraction cost needlessly.
if [ "${CRUCIBLE_DISABLE_BUILD_ROUTING_ADVISOR:-}" = "1" ]; then
  _PROJECT_ROOT="$(git -C "$(pwd)" rev-parse --show-toplevel 2>/dev/null || pwd)"
  _PROJECT_DIR_SAFE="$(echo "$_PROJECT_ROOT" | tr '/' '-')"
  _PROJECT_MEMORY="$HOME/.claude/projects/$_PROJECT_DIR_SAFE/memory"
  _STATE_FILE="$_PROJECT_MEMORY/build-routing-advisor-state.md"

  # Short-circuit: if state file already records today's date as last-honored,
  # exit 0 without rewriting (kill-switch fires ~50-90× per /build run).
  grep -q "^last-honored: $(date +%Y-%m-%d)$" "$_STATE_FILE" 2>/dev/null && exit 0

  # Explicit RMW preserves dedup fields + counters across kill-switch toggles.
  # FIX 1: tr -d '\r' on every state-file read to tolerate CRLF line endings.
  _FIRES_TODAY="$(grep '^fires-today:' "$_STATE_FILE" 2>/dev/null | cut -d' ' -f2 | tr -d '\r')"
  [ -z "$_FIRES_TODAY" ] && _FIRES_TODAY=0
  _FIRES_TOTAL="$(grep '^fires-total:' "$_STATE_FILE" 2>/dev/null | cut -d' ' -f2 | tr -d '\r')"
  [ -z "$_FIRES_TOTAL" ] && _FIRES_TOTAL=0
  _LAST_ADV_AT="$(grep '^last-advisory-at:' "$_STATE_FILE" 2>/dev/null | cut -d' ' -f2- | tr -d '\r')"
  _LAST_ADV_FP="$(grep '^last-advisory-fingerprint:' "$_STATE_FILE" 2>/dev/null | cut -d' ' -f2 | tr -d '\r')"

  mkdir -p "$_PROJECT_MEMORY"
  cat > "$_STATE_FILE.tmp" <<EOF
last-honored: $(date +%Y-%m-%d)
fires-today: $_FIRES_TODAY
fires-total: $_FIRES_TOTAL
last-advisory-at: $_LAST_ADV_AT
last-advisory-fingerprint: $_LAST_ADV_FP
EOF
  mv "$_STATE_FILE.tmp" "$_STATE_FILE"

  # Self-check (S2-R4): assert column-0 anchoring — if the heredoc body was
  # accidentally indented (common footgun), the first line will not match.
  # 2P-3-R5: preserve state file for forensics on regression; warn-only hook.
  grep -q '^last-honored: ' "$_STATE_FILE" || {
    echo "advisor: state-file column-0 invariant broken; preserving for forensics" >&2
    exit 0
  }
  exit 0
fi

# ── 3. Dependency check (jq required) ─────────────────────────────────
if ! command -v jq &>/dev/null; then
  exit 0
fi

# ── 4. Tool-name extraction (accept both .tool_name and legacy .tool) ──
# T1 finding: canonical field is .tool_name, canonical value is "Agent".
# Legacy alias "Task" is honored for back-compat / test payloads.
TOOL="$(echo "$INPUT" | jq -r '.tool_name // .tool // empty' 2>/dev/null)"
case "$TOOL" in
  Task|Agent) ;;
  *) exit 0 ;;
esac

# ── 5. Prompt + subagent extraction ────────────────────────────────────
PROMPT="$(echo "$INPUT" | jq -r '.tool_input.prompt // .input.prompt // empty' 2>/dev/null)"
SUBAGENT="$(echo "$INPUT" | jq -r '.tool_input.subagent_type // .input.subagent_type // empty' 2>/dev/null)"
if [ -z "$PROMPT" ] && [ -z "$SUBAGENT" ]; then
  exit 0
fi

# Session id (payload, not env var — $CLAUDE_SESSION_ID is NOT exported per T1).
SESSION_ID="$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)"

# ── 6. Allowlist gate — only general-purpose dispatches are advised ────
# Empty subagent_type treated as SPECIALTY (indistinguishable from MCP types).
if [ -n "$SUBAGENT" ] && [ "$SUBAGENT" != "general-purpose" ]; then
  exit 0
fi
if [ -z "$SUBAGENT" ]; then
  exit 0
fi

# ── 7. Disclaimer skip ────────────────────────────────────────────────
# FIX 5: Anchored regex — disclaimer must appear at start-of-prompt or after
# a sentence-boundary punctuator (newline / colon / semicolon / dash). This
# preserves plan line 262's single-phase intent while preventing mid-prompt
# false-negatives like "Build feature: ... audit only if time permits."
if echo "$PROMPT" | grep -qiE '(^|[[:space:]]*[:;[:cntrl:]-][[:space:]]*)(just the design|design only|no implementation|review only|audit only|spec only|recon only)\b'; then
  exit 0
fi

# ── 8. Classification (grep-only; NO git subprocess yet — Min-7) ───────
# "spec + implement + PR" → DESIGN=1, IMPLEMENT=1, SHIP=1, TOTAL_DISTINCT=3 → fires.
# TOTAL_DISTINCT uses 'tr [:upper:] [:lower:] | sort -u | wc -l' to count DISTINCT
# lowercased hits across all three categories. sort -u is sound (dedup is per-line
# and category words are single-token, no subword overlap risk). Do NOT replace
# with per-category wc -l addition — would double-count words in multiple
# categories (none currently, but sort -u form is future-proof).
DESIGN_HITS=$(echo "$PROMPT" | grep -ioE '\b(design|spec|plan)\b' | wc -l)
IMPLEMENT_HITS=$(echo "$PROMPT" | grep -ioE '\b(implement|code|create|refactor)\b' | wc -l)
SHIP_HITS=$(echo "$PROMPT" | grep -ioE '\b(PR|commit|merge|push|land|ship)\b' | wc -l)
TOTAL_DISTINCT=$(echo "$PROMPT" | grep -ioE '\b(design|spec|plan|implement|code|create|refactor|PR|commit|merge|push|land|ship)\b' | tr '[:upper:]' '[:lower:]' | sort -u | wc -l)

# Trigger: IMPLEMENT >= 1 AND (DESIGN >= 1 OR SHIP >= 1) AND TOTAL_DISTINCT >= 2.
TRIGGER=0
if [ "$IMPLEMENT_HITS" -ge 1 ] 2>/dev/null; then
  if [ "$DESIGN_HITS" -ge 1 ] 2>/dev/null || [ "$SHIP_HITS" -ge 1 ] 2>/dev/null; then
    if [ "$TOTAL_DISTINCT" -ge 2 ] 2>/dev/null; then
      TRIGGER=1
    fi
  fi
fi

# FIX 3: No env-var check here — already handled at step 2 above. If trigger
# did not fire AND env-var is unset (reached here), exit cheapest path.
if [ "$TRIGGER" -ne 1 ]; then
  exit 0
fi

# ── 9. Lazy PROJECT_ROOT / PROJECT_MEMORY derivation (MIN-3) ──────────
# Walks upward via git-toplevel so cwd drift between dispatches doesn't break
# derivation. If not inside a git repo, falls back to pwd.
PROJECT_ROOT="$(git -C "$(pwd)" rev-parse --show-toplevel 2>/dev/null || pwd)"
PROJECT_DIR_SAFE="$(echo "$PROJECT_ROOT" | tr '/' '-')"
PROJECT_MEMORY="$HOME/.claude/projects/$PROJECT_DIR_SAFE/memory"
STATE_FILE="$PROJECT_MEMORY/build-routing-advisor-state.md"

# ── 10. Sentinel-file kill switch ──────────────────────────────────────
SENTINEL="$PROJECT_MEMORY/.build-routing-advisor-disabled"
if [ -f "$SENTINEL" ]; then
  # MIN-3-R7: matching line starts with "disabled-until: " at column 0.
  DISABLED_UNTIL_LINE="$(grep -m1 '^disabled-until: ' "$SENTINEL" 2>/dev/null)"
  if [ -n "$DISABLED_UNTIL_LINE" ]; then
    DISABLED_UNTIL_RAW="${DISABLED_UNTIL_LINE#disabled-until: }"
    DISABLED_EPOCH="$(date -d "$DISABLED_UNTIL_RAW" +%s 2>/dev/null)"
    TODAY_EPOCH="$(date +%s)"
    if [ -n "$DISABLED_EPOCH" ]; then
      if [ "$TODAY_EPOCH" -lt "$DISABLED_EPOCH" ] 2>/dev/null; then
        # Honored — update last-honored and exit (preserve counters + dedup).
        # FIX 1: tr -d '\r' on each read to tolerate CRLF state files.
        FIRES_TODAY="$(grep '^fires-today:' "$STATE_FILE" 2>/dev/null | cut -d' ' -f2 | tr -d '\r')"
        [ -z "$FIRES_TODAY" ] && FIRES_TODAY=0
        FIRES_TOTAL="$(grep '^fires-total:' "$STATE_FILE" 2>/dev/null | cut -d' ' -f2 | tr -d '\r')"
        [ -z "$FIRES_TOTAL" ] && FIRES_TOTAL=0
        LAST_ADV_AT="$(grep '^last-advisory-at:' "$STATE_FILE" 2>/dev/null | cut -d' ' -f2- | tr -d '\r')"
        LAST_ADV_FP="$(grep '^last-advisory-fingerprint:' "$STATE_FILE" 2>/dev/null | cut -d' ' -f2 | tr -d '\r')"
        mkdir -p "$PROJECT_MEMORY"
        cat > "$STATE_FILE.tmp" <<EOF
last-honored: $(date +%Y-%m-%d)
fires-today: $FIRES_TODAY
fires-total: $FIRES_TOTAL
last-advisory-at: $LAST_ADV_AT
last-advisory-fingerprint: $LAST_ADV_FP
EOF
        mv "$STATE_FILE.tmp" "$STATE_FILE"
        exit 0
      fi
      # Else: switch expired (auto-expiry) — fall through to advisor flow.
    else
      # Parse error → PERMANENTLY DISABLED fail-safe, record raw value.
      # FIX 4: preserve existing counters + dedup + schema-version instead of
      # wiping them (Min-1-R6 / 2P-3-R5). Schema now has up to 7 lines.
      FIRES_TODAY="$(grep '^fires-today:' "$STATE_FILE" 2>/dev/null | cut -d' ' -f2 | tr -d '\r')"
      [ -z "$FIRES_TODAY" ] && FIRES_TODAY=0
      FIRES_TOTAL="$(grep '^fires-total:' "$STATE_FILE" 2>/dev/null | cut -d' ' -f2 | tr -d '\r')"
      [ -z "$FIRES_TOTAL" ] && FIRES_TOTAL=0
      LAST_ADV_AT="$(grep '^last-advisory-at:' "$STATE_FILE" 2>/dev/null | cut -d' ' -f2- | tr -d '\r')"
      LAST_ADV_FP="$(grep '^last-advisory-fingerprint:' "$STATE_FILE" 2>/dev/null | cut -d' ' -f2 | tr -d '\r')"
      SCHEMA_VERSION_LINE="$(grep '^schema-version:' "$STATE_FILE" 2>/dev/null | tr -d '\r')"
      mkdir -p "$PROJECT_MEMORY"
      {
        [ -n "$SCHEMA_VERSION_LINE" ] && echo "$SCHEMA_VERSION_LINE"
        echo "last-honored: $(date +%Y-%m-%d)"
        echo "fires-today: $FIRES_TODAY"
        echo "fires-total: $FIRES_TOTAL"
        echo "last-advisory-at: $LAST_ADV_AT"
        echo "last-advisory-fingerprint: $LAST_ADV_FP"
        echo "disabled-until-parse-error: $DISABLED_UNTIL_RAW"
      } > "$STATE_FILE.tmp"
      mv "$STATE_FILE.tmp" "$STATE_FILE"
      exit 0
    fi
  else
    # Sentinel exists but no disabled-until: line → honor indefinitely.
    # FIX 1: tr -d '\r' applied to all reads.
    mkdir -p "$PROJECT_MEMORY"
    FIRES_TODAY="$(grep '^fires-today:' "$STATE_FILE" 2>/dev/null | cut -d' ' -f2 | tr -d '\r')"
    [ -z "$FIRES_TODAY" ] && FIRES_TODAY=0
    FIRES_TOTAL="$(grep '^fires-total:' "$STATE_FILE" 2>/dev/null | cut -d' ' -f2 | tr -d '\r')"
    [ -z "$FIRES_TOTAL" ] && FIRES_TOTAL=0
    LAST_ADV_AT="$(grep '^last-advisory-at:' "$STATE_FILE" 2>/dev/null | cut -d' ' -f2- | tr -d '\r')"
    LAST_ADV_FP="$(grep '^last-advisory-fingerprint:' "$STATE_FILE" 2>/dev/null | cut -d' ' -f2 | tr -d '\r')"
    cat > "$STATE_FILE.tmp" <<EOF
last-honored: $(date +%Y-%m-%d)
fires-today: $FIRES_TODAY
fires-total: $FIRES_TOTAL
last-advisory-at: $LAST_ADV_AT
last-advisory-fingerprint: $LAST_ADV_FP
EOF
    mv "$STATE_FILE.tmp" "$STATE_FILE"
    exit 0
  fi
fi

# ── 11. Pipeline-active marker check ───────────────────────────────────
MARKER="$PROJECT_MEMORY/.pipeline-active"
MARKER_ACTIVE=0
if [ -f "$MARKER" ]; then
  MARKER_SKILL="$(jq -r '.skill // empty' "$MARKER" 2>/dev/null)"
  MARKER_START="$(jq -r '.start_time // empty' "$MARKER" 2>/dev/null)"
  MARKER_BRANCH="$(jq -r '.branch // empty' "$MARKER" 2>/dev/null)"
  MARKER_PID="$(jq -r '.pipeline_id // empty' "$MARKER" 2>/dev/null)"

  # Skill must be in allowed set
  case "$MARKER_SKILL" in
    build|spec|debugging|migrate) SKILL_OK=1 ;;
    *) SKILL_OK=0 ;;
  esac

  if [ "$SKILL_OK" = "1" ] && [ -n "$MARKER_START" ]; then
    # FIX 2: Validate start_time is ISO-8601-like before date -d. Plan line 275
    # mandates unparseable timestamps are treated as STALE, not silently honored.
    # A numeric-literal start_time (e.g. "0") parses via GNU date -d but means
    # "today local midnight" → would spuriously suppress advisory.
    if echo "$MARKER_START" | grep -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}'; then
      START_EPOCH="$(date -d "$MARKER_START" +%s 2>/dev/null)"
      NOW_EPOCH="$(date -u +%s 2>/dev/null)"
      if [ -n "$START_EPOCH" ] && [ -n "$NOW_EPOCH" ]; then
        AGE=$((NOW_EPOCH - START_EPOCH))
        # Within 24h window
        if [ "$AGE" -ge 0 ] 2>/dev/null && [ "$AGE" -le 86400 ] 2>/dev/null; then
          CUR_BRANCH="$(git -C "$PROJECT_ROOT" branch --show-current 2>/dev/null)"
          # Branch comparison:
          #   both non-empty and equal → active
          #   both empty AND session_id == pipeline_id → active (detached-HEAD
          #     symmetric fallback, using payload .session_id per T1)
          #   else → not active
          if [ -n "$MARKER_BRANCH" ] && [ -n "$CUR_BRANCH" ] && [ "$MARKER_BRANCH" = "$CUR_BRANCH" ]; then
            MARKER_ACTIVE=1
          elif [ -z "$MARKER_BRANCH" ] && [ -z "$CUR_BRANCH" ]; then
            # Detached-HEAD symmetric fallback. Per T1 finding, $CLAUDE_SESSION_ID
            # is NOT exported — use payload .session_id. Per plan line 317, when
            # session-id match is unavailable, fall back to 5-minute .start_time
            # session-proxy window (M9-R4).
            if [ -n "$SESSION_ID" ] && [ -n "$MARKER_PID" ] && [ "$SESSION_ID" = "$MARKER_PID" ]; then
              MARKER_ACTIVE=1
            elif [ "$AGE" -le 300 ] 2>/dev/null; then
              MARKER_ACTIVE=1
            fi
          fi
          # Explicit branch mismatch OR asymmetric empty → NOT active (plan S3).
        fi
        # Else: stale marker (>24h) → MARKER_ACTIVE stays 0 → advisory fires.
      fi
    fi
    # Else: unparseable (or non-ISO-8601) timestamp → treat as stale → advisory fires.
  fi
fi

if [ "$MARKER_ACTIVE" = "1" ]; then
  exit 0
fi

# ── 12. Dedup check (Min-9) ───────────────────────────────────────────
# Fingerprint: SHA256 of FULL prompt text, truncated to 16 hex chars.
FINGERPRINT=""
if command -v sha256sum &>/dev/null; then
  FINGERPRINT="$(echo "$PROMPT" | sha256sum 2>/dev/null | cut -c1-16)"
fi

# FIX 1: tr -d '\r' on all state-file reads.
LAST_ADV_AT_EXISTING="$(grep '^last-advisory-at:' "$STATE_FILE" 2>/dev/null | cut -d' ' -f2- | tr -d '\r')"
LAST_ADV_FP_EXISTING="$(grep '^last-advisory-fingerprint:' "$STATE_FILE" 2>/dev/null | cut -d' ' -f2 | tr -d '\r')"
FIRES_TODAY="$(grep '^fires-today:' "$STATE_FILE" 2>/dev/null | cut -d' ' -f2 | tr -d '\r')"
[ -z "$FIRES_TODAY" ] && FIRES_TODAY=0
FIRES_TOTAL="$(grep '^fires-total:' "$STATE_FILE" 2>/dev/null | cut -d' ' -f2 | tr -d '\r')"
[ -z "$FIRES_TOTAL" ] && FIRES_TOTAL=0
LAST_HONORED_EXISTING="$(grep '^last-honored:' "$STATE_FILE" 2>/dev/null | cut -d' ' -f2 | tr -d '\r')"

SUPPRESS=0
if [ -n "$FINGERPRINT" ] && [ -n "$LAST_ADV_FP_EXISTING" ] && [ "$FINGERPRINT" = "$LAST_ADV_FP_EXISTING" ] && [ -n "$LAST_ADV_AT_EXISTING" ]; then
  LAST_EPOCH="$(date -d "$LAST_ADV_AT_EXISTING" +%s 2>/dev/null)"
  NOW_EPOCH="$(date -u +%s 2>/dev/null)"
  if [ -n "$LAST_EPOCH" ] && [ -n "$NOW_EPOCH" ]; then
    DIFF=$((NOW_EPOCH - LAST_EPOCH))
    if [ "$DIFF" -ge 0 ] 2>/dev/null && [ "$DIFF" -le 300 ] 2>/dev/null; then
      SUPPRESS=1
    fi
  fi
fi

TODAY_DATE="$(date +%Y-%m-%d)"

if [ "$SUPPRESS" = "1" ]; then
  # Suppressed: increment fires-total only, do not emit.
  FIRES_TOTAL=$((FIRES_TOTAL + 1))
  mkdir -p "$PROJECT_MEMORY"
  cat > "$STATE_FILE.tmp" <<EOF
last-honored: $LAST_HONORED_EXISTING
fires-today: $FIRES_TODAY
fires-total: $FIRES_TOTAL
last-advisory-at: $LAST_ADV_AT_EXISTING
last-advisory-fingerprint: $LAST_ADV_FP_EXISTING
EOF
  mv "$STATE_FILE.tmp" "$STATE_FILE"
  exit 0
fi

# ── 13. Lazy fires-today reset (Min-3-R6) ─────────────────────────────
# Reset is LAZY — only here, on advisory-eligible invocation. Compare today's
# local date against the MOST RECENT of (last-honored date, last-advisory-at
# date). If neither exists OR most recent is older than today → reset to 0.
LAST_ADV_DATE=""
if [ -n "$LAST_ADV_AT_EXISTING" ]; then
  LAST_ADV_DATE="$(date -d "$LAST_ADV_AT_EXISTING" +%Y-%m-%d 2>/dev/null)"
fi
MOST_RECENT=""
if [ -n "$LAST_HONORED_EXISTING" ] && [ -n "$LAST_ADV_DATE" ]; then
  if [ "$LAST_HONORED_EXISTING" \> "$LAST_ADV_DATE" ]; then
    MOST_RECENT="$LAST_HONORED_EXISTING"
  else
    MOST_RECENT="$LAST_ADV_DATE"
  fi
elif [ -n "$LAST_HONORED_EXISTING" ]; then
  MOST_RECENT="$LAST_HONORED_EXISTING"
elif [ -n "$LAST_ADV_DATE" ]; then
  MOST_RECENT="$LAST_ADV_DATE"
fi

if [ -z "$MOST_RECENT" ] || [ "$MOST_RECENT" \< "$TODAY_DATE" ]; then
  FIRES_TODAY=0
fi

# ── 14. Emit advisory (exactly 2 lines; literal "build-shaped") ───────
echo "ADVISORY: Dispatch looks build-shaped. If single-phase, ignore." >&2
echo "Else prefer /build (or /spec then /build) for gate coverage." >&2

# ── 15. Atomic state-file update ──────────────────────────────────────
mkdir -p "$PROJECT_MEMORY"
FIRES_TODAY=$((FIRES_TODAY + 1))
FIRES_TOTAL=$((FIRES_TOTAL + 1))
NOW_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

cat > "$STATE_FILE.tmp" <<EOF
last-honored: $LAST_HONORED_EXISTING
fires-today: $FIRES_TODAY
fires-total: $FIRES_TOTAL
last-advisory-at: $NOW_ISO
last-advisory-fingerprint: $FINGERPRINT
EOF
mv "$STATE_FILE.tmp" "$STATE_FILE"

exit 0
