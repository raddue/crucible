#!/usr/bin/env bash
# hooks/tests/test-rcpt-verify-hook.sh
# Test suite for the rcpt-verify-hook.sh SubagentStop hook (#369).
# Proves the never-fatal + pure-observer contract: exit 0 in EVERY branch, advisory
# only on a genuinely-malformed receipt, the M2 script-absent gate suppresses the
# false advisory, and the hook makes no writes.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK="$SCRIPT_DIR/../rcpt-verify-hook.sh"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

PASSED=0
FAILED=0

TMPDIR_BASE="$(mktemp -d)"
cleanup() { rm -rf "$TMPDIR_BASE"; }
trap cleanup EXIT

# ── First sample receipt (valid) and a malformed one ──────────────────
GOOD_RCPT="$(python3 -c "import json;print(json.loads(open('$REPO_ROOT/eval/ledger-return-protocol/sample-corpus/receipts.jsonl').readline())['receipt'])")"
BAD_RCPT="$(printf 'RCPT v1 build/x\nVERDICT  PASS  conf=0.90\nARTIFACTS\n  (none)\nTRACE\n  1  READ  a\n')"

# write_transcript <file> <content-mode> ...
# Builds a JSONL transcript whose last assistant message carries the given text.
mk_transcript() {  # $1=path  $2=text
  python3 - "$1" "$2" <<'PY'
import json, sys, pathlib
path, text = sys.argv[1], sys.argv[2]
recs = [
    {"message": {"role": "user", "content": "go"}},
    {"message": {"role": "assistant", "content": text}},
]
pathlib.Path(path).write_text("\n".join(json.dumps(r) for r in recs) + "\n")
PY
}

# Runs hook from a given cwd with a given stdin JSON; captures exit + stderr.
# Sets globals: RC, ADVISORY (1 if "[rcpt-verify]" seen on stderr, else 0)
run_hook() {  # $1=cwd  $2=stdin-json  [$3=PATH override]
  local cwd="$1" json="$2" pathenv="${3:-$PATH}"
  local err
  set +e
  err="$(cd "$cwd" && PATH="$pathenv" bash "$HOOK" <<<"$json" 2>&1 1>/dev/null)"
  RC=$?
  set -e
  if printf '%s' "$err" | grep -q '\[rcpt-verify\]'; then ADVISORY=1; else ADVISORY=0; fi
  LAST_ERR="$err"
}

check() {  # $1=name  $2=expected_rc  $3=expected_advisory(0/1)
  local name="$1" exp_rc="$2" exp_adv="$3"
  if [ "$RC" -eq "$exp_rc" ] && [ "$ADVISORY" -eq "$exp_adv" ]; then
    echo "PASS: $name (exit=$RC advisory=$ADVISORY)"
    PASSED=$((PASSED + 1))
  else
    echo "FAIL: $name — expected exit=$exp_rc advisory=$exp_adv, got exit=$RC advisory=$ADVISORY"
    [ -n "${LAST_ERR:-}" ] && echo "      stderr: $LAST_ERR"
    FAILED=$((FAILED + 1))
  fi
}

# ════════════════════════════════════════════════════════════════════
# (b) valid receipt → silent + exit 0   (cwd inside crucible repo)
mk_transcript "$TMPDIR_BASE/good.jsonl" "$GOOD_RCPT"
run_hook "$REPO_ROOT" "$(printf '{"transcript_path":"%s/good.jsonl"}' "$TMPDIR_BASE")"
check "valid receipt → silent" 0 0

# (a) malformed receipt → advisory + exit 0
mk_transcript "$TMPDIR_BASE/bad.jsonl" "$BAD_RCPT"
run_hook "$REPO_ROOT" "$(printf '{"transcript_path":"%s/bad.jsonl"}' "$TMPDIR_BASE")"
check "malformed receipt → advisory" 0 1

# (8) true-positive: prose-wrapped malformed receipt + a trailing tool_use turn
python3 - "$TMPDIR_BASE/wrapped.jsonl" "$BAD_RCPT" <<'PY'
import json, sys, pathlib
path, bad = sys.argv[1], sys.argv[2]
recs = [
    {"message": {"role": "user", "content": "implement + return a receipt"}},
    {"message": {"role": "assistant", "content": [
        {"type": "text", "text": "Done. Receipt:\n\n" + bad + "\n\nProceeding."}]}},
    {"message": {"role": "assistant", "content": [
        {"type": "tool_use", "name": "Bash", "input": {"command": "echo hi"}}]}},
]
pathlib.Path(path).write_text("\n".join(json.dumps(r) for r in recs) + "\n")
PY
run_hook "$REPO_ROOT" "$(printf '{"transcript_path":"%s/wrapped.jsonl"}' "$TMPDIR_BASE")"
check "prose-wrapped malformed + trailing tool_use turn → advisory" 0 1

# (c) non-receipt last message → silent
mk_transcript "$TMPDIR_BASE/none.jsonl" "just prose, no receipt here"
run_hook "$REPO_ROOT" "$(printf '{"transcript_path":"%s/none.jsonl"}' "$TMPDIR_BASE")"
check "no receipt → silent" 0 0

# (c) empty stdin → silent
run_hook "$REPO_ROOT" ""
check "empty stdin → silent" 0 0

# (c) no transcript_path key → silent
run_hook "$REPO_ROOT" '{"foo":"bar"}'
check "missing transcript_path → silent" 0 0

# (c) unreadable / nonexistent transcript → silent
run_hook "$REPO_ROOT" '{"transcript_path":"/nonexistent/path.jsonl"}'
check "nonexistent transcript → silent" 0 0

# (c) unrecognized transcript shape (not JSONL records) → silent
printf 'this is not json\n{also not\n' > "$TMPDIR_BASE/garbage.jsonl"
run_hook "$REPO_ROOT" "$(printf '{"transcript_path":"%s/garbage.jsonl"}' "$TMPDIR_BASE")"
check "garbage transcript → silent" 0 0

# (c) missing jq → silent (PATH with only a minimal toolset, no jq)
FAKEBIN="$TMPDIR_BASE/fakebin"
mkdir -p "$FAKEBIN"
for t in cat bash; do ln -sf "$(command -v $t)" "$FAKEBIN/"; done
run_hook "$REPO_ROOT" "$(printf '{"transcript_path":"%s/bad.jsonl"}' "$TMPDIR_BASE")" "$FAKEBIN"
check "missing jq → silent" 0 0

# (c) cwd outside any git repo → \$REPO empty → silent (even on a malformed receipt)
NONREPO="$TMPDIR_BASE/nonrepo"
mkdir -p "$NONREPO"
run_hook "$NONREPO" "$(printf '{"transcript_path":"%s/bad.jsonl"}' "$TMPDIR_BASE")"
check "cwd outside any repo → silent" 0 0

# (c/M2) \$REPO resolves to a repo with NO scripts/rcpt_verify.py → silent, NO advisory
NONCRUCIBLE="$TMPDIR_BASE/noncrucible"
mkdir -p "$NONCRUCIBLE"
git -C "$NONCRUCIBLE" init -q
run_hook "$NONCRUCIBLE" "$(printf '{"transcript_path":"%s/bad.jsonl"}' "$TMPDIR_BASE")"
check "non-crucible repo (M2 script-absent gate) → silent" 0 0

# (9) pure observer — no writes. Stand up a fake repo WITH a copy of rcpt_verify.py
# so the advisory path actually runs, then assert the cwd file-set is unchanged.
WRITEREPO="$TMPDIR_BASE/writerepo"
mkdir -p "$WRITEREPO/scripts"
git -C "$WRITEREPO" init -q
cp "$REPO_ROOT/scripts/rcpt_verify.py" "$WRITEREPO/scripts/"
BEFORE="$(cd "$WRITEREPO" && find . -type f | sort)"
run_hook "$WRITEREPO" "$(printf '{"transcript_path":"%s/bad.jsonl"}' "$TMPDIR_BASE")"
AFTER="$(cd "$WRITEREPO" && find . -type f | sort)"
# transcript is outside WRITEREPO; assert advisory fired AND no files were created
TRANSCRIPT_BEFORE="$(cat "$TMPDIR_BASE/bad.jsonl")"
if [ "$RC" -eq 0 ] && [ "$ADVISORY" -eq 1 ] && [ "$BEFORE" = "$AFTER" ] \
   && [ "$TRANSCRIPT_BEFORE" = "$(cat "$TMPDIR_BASE/bad.jsonl")" ]; then
  echo "PASS: pure observer — advisory fired, no writes to cwd or transcript"
  PASSED=$((PASSED + 1))
else
  echo "FAIL: pure observer — rc=$RC adv=$ADVISORY before/after-equal=$([ "$BEFORE" = "$AFTER" ] && echo yes || echo no)"
  FAILED=$((FAILED + 1))
fi

# ════════════════════════════════════════════════════════════════════
echo
echo "rcpt-verify-hook: $PASSED passed, $FAILED failed"
[ "$FAILED" -eq 0 ]
