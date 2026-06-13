#!/usr/bin/env bash
# hooks/rcpt-verify-hook.sh
# SubagentStop hook (Tier-1 advisory) for the Ledger Return Protocol (#369).
#
# PURE OBSERVER, NEVER FATAL: reads the SubagentStop JSON on stdin, extracts the
# last text-bearing assistant message from the transcript, and — if it carries an
# `RCPT v1` receipt block — runs `scripts/rcpt_verify.py --tier1 -` on it. A failing
# structural lint emits a 2-line ADVISORY on stderr. The hook ALWAYS exits 0 and
# performs NO writes (find-and-report; it does not block, edit, or record anything).
#
# OPT-IN — not auto-enabled. Configure in .claude/settings.json:
#   "hooks": { "SubagentStop": [{ "matcher": "*", "hooks": [
#     { "type": "command", "command": "bash hooks/rcpt-verify-hook.sh", "timeout": 500 }
#   ]}]}
#
# Mirrors gate-ledger-guard.sh's never-fatal skeleton + build-routing-advisor.sh's
# warn-only contract. Every dependency-absent / parse-error / shape-mismatch path
# exits 0 silently.

# Disable errexit — this hook must never fail fatally.
set +e

# ── 1. Read stdin ──────────────────────────────────────────────────────
INPUT="$(cat)"
[ -z "$INPUT" ] && exit 0

# ── 2. Dependency checks (jq + python3) — absent → exit 0 silently ─────
command -v jq >/dev/null 2>&1 || exit 0
command -v python3 >/dev/null 2>&1 || exit 0

# ── 3. Transcript path ─────────────────────────────────────────────────
TRANSCRIPT="$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)"
[ -z "$TRANSCRIPT" ] && exit 0
[ -r "$TRANSCRIPT" ] || exit 0

# ── 4. Extract the last text-bearing assistant message ────────────────
# content may be a verbatim string OR an array of blocks (concat the type=="text"
# block .text values). Any parse error / unrecognized shape / no text → exit 0.
TEXT="$(jq -rs '
  [ .[]
    | select((.message | type) == "object")
    | select(.message.role == "assistant")
    | ( if (.message.content | type) == "string" then .message.content
        elif (.message.content | type) == "array" then
          ([.message.content[] | select((. | type) == "object" and .type == "text") | .text] | join("\n"))
        else "" end )
    | select(. != null and . != "")
  ] | last // empty
' "$TRANSCRIPT" 2>/dev/null)"
[ -z "$TEXT" ] && exit 0

# ── 5. Gate: only proceed when the message carries an RCPT v1 receipt ──
case "$TEXT" in
  *"RCPT v1"*) ;;
  *) exit 0 ;;
esac

# Extract from the first column-0 `RCPT v1 ` line to end-of-message (trailing prose
# lands harmlessly in the NEXT body; leading prose is excluded).
# NOTE: the `RCPT v1 ` trailing-space anchor matches v1 receipts ONLY — `RCPT v1.1`
# receipts are not extracted by this hook (v1.1 is out of scope for #369). This is
# advisory-only, so a dropped v1.1 receipt simply yields no advisory.
RCPT_BLOCK="$(printf '%s\n' "$TEXT" | awk '/^RCPT v1 /{p=1} p')"
[ -z "$RCPT_BLOCK" ] && exit 0

# ── 6. Resolve repo root + the existence gate (M2) ────────────────────
# Without this gate a SubagentStop in a non-crucible repo (these gating skills run
# in other repos too) would `python3 <nonexistent>` → exit 2 → a
# misleading "structural lint failed" advisory on every receipt. Never-fatal holds
# regardless; the gate prevents the spurious advisory.
REPO="$(git rev-parse --show-toplevel 2>/dev/null)"
[ -z "$REPO" ] && exit 0
[ -f "$REPO/scripts/rcpt_verify.py" ] || exit 0

# ── 7. Run the Tier-1 structural lint (advisory only) ─────────────────
ERR="$(printf '%s\n' "$RCPT_BLOCK" | python3 "$REPO/scripts/rcpt_verify.py" --tier1 - 2>&1 1>/dev/null)"
RC=$?
if [ "$RC" -ne 0 ]; then
  FIRST_BULLET="$(printf '%s\n' "$ERR" | head -n 1)"
  echo "[rcpt-verify] structural lint failed: $FIRST_BULLET" >&2
  echo "[rcpt-verify] advisory only — receipt not blocked (run scripts/rcpt_verify.py --tier1 to inspect)" >&2
fi

# Pure observer: no writes, always exit 0.
exit 0
