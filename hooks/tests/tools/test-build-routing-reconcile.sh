#!/usr/bin/env bash
# hooks/tests/tools/test-build-routing-reconcile.sh
# Synthetic 2-PR fixture test for build-routing-reconcile.sh (#174 T9 step 10).
#
# Builds a temp repo with 2 merge commits:
#   - PR #101 branch=feat-a — ledger has "Status: PASS" tagged with branch
#   - PR #102 branch=feat-b — ledger has NO PASS line for this branch
# Asserts: flagged count == 1 (PR #102 only).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RECON="$SCRIPT_DIR/build-routing-reconcile.sh"

TMP="$(mktemp -d)"
FAKE_HOME="$TMP/home"
REPO="$TMP/repo"
mkdir -p "$FAKE_HOME" "$REPO"

cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

# ── Build minimal git repo with 2 fake PR merges ───────────────────────
(
  cd "$REPO"
  git init -q -b main
  git config user.email t@t
  git config user.name t
  git commit -q --allow-empty -m "init"

  # PR #101 — has gate PASS
  git checkout -q -b feat-a
  echo a > a.txt; git add a.txt; git commit -q -m "feat-a work"
  git checkout -q main
  git merge -q --no-ff feat-a -m "Merge pull request #101 from u/feat-a"

  # PR #102 — missing gate PASS
  git checkout -q -b feat-b
  echo b > b.txt; git add b.txt; git commit -q -m "feat-b work"
  git checkout -q main
  git merge -q --no-ff feat-b -m "Merge pull request #102 from u/feat-b"
) >/dev/null 2>&1

# ── Seed the gate-ledger with PASS only for feat-a ─────────────────────
REPO_ABS="$(cd "$REPO" && pwd)"
PROJECT_HASH="$(echo "$REPO_ABS" | tr '/' '-')"
LEDGER_DIR="$FAKE_HOME/.claude/projects/$PROJECT_HASH/memory"
mkdir -p "$LEDGER_DIR"
cat > "$LEDGER_DIR/build-gate-ledger.md" <<EOF
# Build Gate Ledger

## Entry 1
branch: feat-a
Status: PASS
pipeline-id: abc123
EOF

# ── Run reconciler (force gh unavailable → git-log fallback) ───────────
# Use PATH trick to hide `gh` so fallback path exercises.
HIDE_GH="$TMP/bin"
mkdir -p "$HIDE_GH"
cat > "$HIDE_GH/gh" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$HIDE_GH/gh"

REPORT_OUT="$TMP/report.md"
HOME="$FAKE_HOME" PATH="$HIDE_GH:$PATH" \
  bash "$RECON" \
    --since "30 days ago" \
    --repo "$REPO" \
    --output "$REPORT_OUT"
RC=$?

if [ $RC -ne 0 ]; then
  echo "FAIL: reconciler exited $RC" >&2
  exit 1
fi

# ── Assertions ─────────────────────────────────────────────────────────
PASS=0
FAIL=0

grep -q "Flagged (no gate-ledger PASS): 1" "$REPORT_OUT" \
  && { PASS=$((PASS+1)); echo "PASS: flagged count == 1"; } \
  || { FAIL=$((FAIL+1)); echo "FAIL: expected flagged count == 1"; cat "$REPORT_OUT"; }

grep -q "PR #102" "$REPORT_OUT" \
  && { PASS=$((PASS+1)); echo "PASS: PR #102 flagged"; } \
  || { FAIL=$((FAIL+1)); echo "FAIL: PR #102 not in flagged list"; }

grep -q "PR #101" "$REPORT_OUT" \
  && { FAIL=$((FAIL+1)); echo "FAIL: PR #101 should NOT be flagged"; cat "$REPORT_OUT"; } \
  || { PASS=$((PASS+1)); echo "PASS: PR #101 not flagged"; }

grep -q "Total merged PRs in window: 2" "$REPORT_OUT" \
  && { PASS=$((PASS+1)); echo "PASS: total PRs == 2"; } \
  || { FAIL=$((FAIL+1)); echo "FAIL: expected total PRs == 2"; }

grep -q "Mode: DEGRADED" "$REPORT_OUT" \
  && { PASS=$((PASS+1)); echo "PASS: degradation notice present"; } \
  || { FAIL=$((FAIL+1)); echo "FAIL: missing degradation notice"; }

echo ""
echo "─── Results: $PASS passed, $FAIL failed ───"
[ $FAIL -eq 0 ] && exit 0 || exit 1
