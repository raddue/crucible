#!/usr/bin/env bash
# End-to-end eval for the Invariant Cairn (issue #204).
#
# Runs seven checks:
#   1. Clean fixture passes phase-entry-check + reconciliation (happy path).
#   2. Recovery correctness: a cairn written, destroyed in memory, re-read —
#      all INVARIANTS + OPEN_OBLIGATIONS + PHASE recoverable.
#   3. Schema-lint rejects crafted malformed cairns.
#   4. Reconciliation catches each of the five drift modes (a/b/c/d/e).
#   5. Integration: a receipt with ran=SKIPPED promoted → OPEN_OBLIGATIONS,
#      later closed by a real exec receipt, passes reconciliation.
#   6. Skill-qualified cross-skill partition: a ledger shared by build + QG;
#      the QG cairn counts only its quality-gate:round/1 entries.
#   7. Drift-f: a 12-char prefix collision across the run escalates (Rules 2/4).

set -euo pipefail

cd "$(dirname "$0")"

echo "=== Check 1: clean cairn passes lint + reconciliation ==="
python3 cairn_lint.py check fixtures/cairn-2026-04-20T12-00-00.md
python3 cairn_lint.py reconcile fixtures/cairn-2026-04-20T12-00-00.md fixtures/receipt-ledger.jsonl fixtures/tripwire-manifest.json fixtures/active-run.md
echo

echo "=== Check 2: recovery correctness (round-trip read) ==="
python3 - <<'EOF'
from pathlib import Path
import sys
sys.path.insert(0, ".")
from cairn_lint import phase_entry_check, parse_phase, parse_invariants, parse_obligations

original = Path("fixtures/recovery-before.md").read_text()
# Simulate "orchestrator in-memory state destroyed" — nothing to do; just re-parse.
sections = phase_entry_check(original)
phase = parse_phase(sections["PHASE"])
invs = parse_invariants(sections["INVARIANTS"])
obls = parse_obligations(sections["OPEN_OBLIGATIONS"])

# Assertions
assert phase["phase"] == "execute", f"phase {phase['phase']}"
assert phase["counter"] == 3, f"counter {phase['counter']}"
assert len(invs) == 3, f"invariants {len(invs)}"
assert [i["ord"] for i in invs] == [1, 2, 3], f"ords {[i['ord'] for i in invs]}"
assert len(obls) == 2, f"obligations {len(obls)}"
assert obls[0]["closed"] is False
assert obls[1]["closed"] is True
print("  PASS  recovery preserves phase, all 3 invariants, both obligations with correct states")
EOF
echo

echo "=== Check 3: schema lint rejects malformed cairns ==="
# Missing section
python3 - <<'EOF'
import sys
sys.path.insert(0, ".")
from cairn_lint import phase_entry_check, CairnError
cases = [
    ("missing-section", """# Cairn — test
## PHASE
phase: x / 1
started-at: 2026-04-20T00:00:00Z
parent-skill: build
## INVARIANTS
## OPEN_OBLIGATIONS
"""),
    ("out-of-order", """# Cairn — test
## INVARIANTS
## PHASE
phase: x / 1
started-at: 2026-04-20T00:00:00Z
parent-skill: build
## OPEN_OBLIGATIONS
## LEDGER
"""),
    ("duplicate-I-NN", """# Cairn — test
## PHASE
phase: x / 1
started-at: 2026-04-20T00:00:00Z
parent-skill: build
## INVARIANTS
I-01: foo
I-01: dup
## OPEN_OBLIGATIONS
## LEDGER
"""),
    ("over-240-char-invariant", """# Cairn — test
## PHASE
phase: x / 1
started-at: 2026-04-20T00:00:00Z
parent-skill: build
## INVARIANTS
I-01: """ + ("x" * 250) + """
## OPEN_OBLIGATIONS
## LEDGER
"""),
    ("TODO-placeholder", """# Cairn — test
## PHASE
phase: x / 1
started-at: 2026-04-20T00:00:00Z
parent-skill: build
## INVARIANTS
I-01: TODO fill this in
## OPEN_OBLIGATIONS
## LEDGER
"""),
]
failed = 0
for name, text in cases:
    try:
        phase_entry_check(text)
        print(f"  FAIL  {name} — should have been rejected")
        failed += 1
    except CairnError as e:
        print(f"  PASS  {name}: {str(e)[:80]}")
sys.exit(1 if failed else 0)
EOF
echo

echo "=== Check 4: reconciliation catches each drift mode ==="
for drift in a b c d e; do
  case $drift in
    a) cairn=fixtures/drift-a-ledger-undercount.md; manifest=fixtures/tripwire-manifest.json; active=fixtures/active-run.md ;;
    b) cairn=fixtures/drift-b-skip-close.md; manifest=fixtures/tripwire-manifest.json; active=fixtures/active-run.md ;;
    c) cairn=fixtures/cairn-2026-04-20T12-00-00.md; manifest=fixtures/tripwire-manifest.json; active=fixtures/drift-c-active-run-mismatch.md ;;
    d) cairn=fixtures/drift-d-unaddressed-supersession.md; manifest=fixtures/tripwire-manifest-with-supersession.json; active=fixtures/active-run.md ;;
    e) cairn=fixtures/drift-e-phase-gap.md; manifest=fixtures/tripwire-manifest.json; active=fixtures/active-run.md ;;
  esac
  out=$(python3 cairn_lint.py reconcile "$cairn" fixtures/receipt-ledger.jsonl "$manifest" "$active" 2>&1 || true)
  if echo "$out" | grep -q "^FAIL"; then
    echo "  PASS  drift-$drift caught: $(echo "$out" | head -1)"
  else
    echo "  FAIL  drift-$drift NOT caught: $out"
    exit 1
  fi
done
echo

echo "=== Check 5: Layer 1+2 integration (SKIPPED-promoted obligation closed by real exec) ==="
# The clean cairn already has: SKIPPED witness (execute/3-impl-1, hash 9876abcdef01)
# → obligation with ref=9876abcdef01; later receipt fedcba987654 closes it with
# witness_ran=TRACE#2 (not SKIPPED). Reconciliation pass in Check 1 already
# validated this flow. Re-run explicitly as a named check:
python3 cairn_lint.py reconcile fixtures/cairn-2026-04-20T12-00-00.md fixtures/receipt-ledger.jsonl fixtures/tripwire-manifest.json fixtures/active-run.md
echo "  PASS  Layer 1+2 integration verified"
echo

echo "=== Check 6: skill-qualified cross-skill partition ==="
# A single ledger shared by TWO skills (build:plan/2 + quality-gate:round/1).
# The QG cairn's LEDGER says round/1 dispatches=3; the ledger has exactly 3
# quality-gate:round/1 entries (the co-resident build:* entries must NOT inflate
# the count). Positive proof Rule 1's skill-qualified phase partitions cleanly.
python3 cairn_lint.py reconcile fixtures/cairn-multiskill-qg.md fixtures/receipt-ledger-multiskill.jsonl fixtures/tripwire-manifest.json fixtures/active-run-multiskill.md
echo "  PASS  cross-skill partition: QG cairn counts only quality-gate:round/1 (build:* ignored)"
# Negative sub-case: a stray siege:round/1 entry (sibling sub-skill sharing round/N)
# must NOT change the QG cairn's count — distinct skill prefix disambiguates.
tmp_ledger=$(mktemp)
cat fixtures/receipt-ledger-multiskill.jsonl > "$tmp_ledger"
printf '%s\n' '{"dispatch_id":"7-siege","phase":"siege:round/1","hash_prefix":"d0000001aaaa","verdict":"PASS","witness_ran":"TRACE#1"}' >> "$tmp_ledger"
python3 cairn_lint.py reconcile fixtures/cairn-multiskill-qg.md "$tmp_ledger" fixtures/tripwire-manifest.json fixtures/active-run-multiskill.md
rm -f "$tmp_ledger"
echo "  PASS  stray siege:round/1 entry does not inflate quality-gate:round/1 count"
echo

echo "=== Check 7: drift-f — 12-char prefix collision escalates (Rules 2/4) ==="
out=$(python3 cairn_lint.py reconcile fixtures/cairn-2026-04-20T12-00-00.md fixtures/drift-f-prefix-collision.jsonl fixtures/tripwire-manifest.json fixtures/active-run.md 2>&1 || true)
if echo "$out" | grep -q "12-char prefix collision across run"; then
  echo "  PASS  drift-f caught: $(echo "$out" | head -1)"
else
  echo "  FAIL  drift-f NOT caught: $out"
  exit 1
fi
echo

echo "=== ALL CHECKS PASSED ==="
