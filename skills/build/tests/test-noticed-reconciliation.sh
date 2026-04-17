#!/usr/bin/env bash
# Mechanical contract test for /build Noticed reconciliation.
# Tag: contract:integration:inv-4
#
# Asserts the 7-step reconciliation in skills/build/tools/reconcile-noticed.py:
#   1. parses `### Noticed But Not Touching` sections from implementer reports
#   2. skips *(none)*
#   3. dedupes by canonical key (sha256 of normalized path + range + noticed[:40])
#   4. sorts by file path then line range
#   5. writes docs/plans/<date>-<slug>-noticed.md matching INV-6 regex
#   6. idempotent overwrite: re-running with same inputs is byte-identical
#   7. frontmatter contains pipeline_id, date, ticket

set -euo pipefail

CONTRACT_TAG="contract:integration:inv-4"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../../.." && pwd)"
RECONCILER="$REPO_ROOT/skills/build/tools/reconcile-noticed.py"

if [[ ! -f "$RECONCILER" ]]; then
  echo "FAIL [$CONTRACT_TAG]: reconciler not found at $RECONCILER" >&2
  exit 1
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Synthetic report A: one entry at out_of_scope.ts:L10-L20
cat >"$WORK/reportA.md" <<'EOF'
## Report

### TDD Evidence Log

- testFoo -- RED: "x" -> GREEN: pass

### Noticed But Not Touching

- **file:** `out_of_scope.ts:L10-L20`
  **noticed:** Unvalidated input flows into a SQL query builder
  **why it matters:** Potential injection, but outside current ticket scope
  **suggested follow-up:** File a security-hygiene ticket
EOF

# Synthetic report B: duplicate of A + unique entry at other.ts:L5-L7
cat >"$WORK/reportB.md" <<'EOF'
## Report

### Noticed But Not Touching

- **file:** `out_of_scope.ts:L10-L20`
  **noticed:** Unvalidated input flows into a SQL query builder
  **why it matters:** duplicate should be collapsed

- **file:** `other.ts:L5-L7`
  **noticed:** Dead import left over from a refactor
  **why it matters:** Minor cleanup; noise in IDE warnings
EOF

OUT_DIR="$WORK/docs/plans"
mkdir -p "$OUT_DIR"
OUT="$OUT_DIR/2026-04-16-noticed-test-noticed.md"

python3 "$RECONCILER" \
  --out "$OUT" \
  --pipeline-id "build-20260416-120000" \
  --date "2026-04-16" \
  --ticket "#179" \
  --slug "noticed-test" \
  "$WORK/reportA.md" "$WORK/reportB.md" >/dev/null

# Assert 1: filename matches INV-6 regex
REL_OUT="docs/plans/2026-04-16-noticed-test-noticed.md"
if ! [[ "$REL_OUT" =~ ^docs/plans/[0-9]{4}-[0-9]{2}-[0-9]{2}-[a-z0-9-]+-noticed\.md$ ]]; then
  echo "FAIL [$CONTRACT_TAG]: output path does not match INV-6 filename regex" >&2
  exit 1
fi

# Assert 2: exactly 2 entries
ENTRY_COUNT=$(grep -cE '^- \*\*file:\*\*' "$OUT")
if [[ "$ENTRY_COUNT" -ne 2 ]]; then
  echo "FAIL [$CONTRACT_TAG]: expected 2 entries, got $ENTRY_COUNT" >&2
  cat "$OUT" >&2
  exit 1
fi

# Assert 3: entries sorted by file path then line range (other.ts < out_of_scope.ts)
FIRST=$(grep -E '^- \*\*file:\*\*' "$OUT" | sed -n '1p')
SECOND=$(grep -E '^- \*\*file:\*\*' "$OUT" | sed -n '2p')
if [[ "$FIRST" != *"other.ts"* ]] || [[ "$SECOND" != *"out_of_scope.ts"* ]]; then
  echo "FAIL [$CONTRACT_TAG]: entries not sorted by file path" >&2
  echo "first=$FIRST" >&2
  echo "second=$SECOND" >&2
  exit 1
fi

# Assert 4: frontmatter contains pipeline_id, date, ticket
for field in "pipeline_id" "date" "ticket"; do
  if ! grep -qE "^${field}:" "$OUT"; then
    echo "FAIL [$CONTRACT_TAG]: frontmatter missing $field" >&2
    exit 1
  fi
done

# Capture first-run bytes
FIRST_RUN_SHA=$(sha256sum "$OUT" | awk '{print $1}')

# Re-run with same inputs → idempotent overwrite
python3 "$RECONCILER" \
  --out "$OUT" \
  --pipeline-id "build-20260416-120000" \
  --date "2026-04-16" \
  --ticket "#179" \
  --slug "noticed-test" \
  "$WORK/reportA.md" "$WORK/reportB.md" >/dev/null

SECOND_RUN_SHA=$(sha256sum "$OUT" | awk '{print $1}')

if [[ "$FIRST_RUN_SHA" != "$SECOND_RUN_SHA" ]]; then
  echo "FAIL [$CONTRACT_TAG]: non-idempotent overwrite (sha256 changed between runs)" >&2
  echo "first=$FIRST_RUN_SHA" >&2
  echo "second=$SECOND_RUN_SHA" >&2
  exit 1
fi

# Assert *(none)* is skipped
cat >"$WORK/reportC.md" <<'EOF'
### Noticed But Not Touching

*(none)*
EOF
OUT_NONE="$OUT_DIR/2026-04-16-noticed-none-noticed.md"
python3 "$RECONCILER" \
  --out "$OUT_NONE" \
  --pipeline-id "build-20260416-120000" \
  --date "2026-04-16" \
  --ticket "#179" \
  --slug "noticed-none" \
  "$WORK/reportC.md" >/dev/null

if [[ -f "$OUT_NONE" ]]; then
  echo "FAIL [$CONTRACT_TAG]: *(none)*-only reports should not produce a file" >&2
  exit 1
fi

echo "PASS [$CONTRACT_TAG]: reconciliation parses, dedupes, sorts, writes, and is idempotent"
