#!/usr/bin/env bash
# End-to-end eval for the Verification Ledger (issue #213).
#
# Runs nine checks against the ledger_scorer reference implementation:
#   1.  Brief with 3 deduplicated causal claims -> 3 ledger entries (INV-7, N-count variant).
#   1b. Minimal fixture: 2 identical causal claims -> exactly 1 ledger entry (INV-7, isolated-merge variant).
#   2.  Brief with 0 causal keyword matches -> header + placeholder comment only (INV-8).
#   3.  Scout omits [evidence:] tag -> entry emitted with method: none, evidence: -- .
#   4.  [evidence: structural-only:...] tag -> disposition: awaiting (INV-9).
#   5.  Phase 5 grep match fixture -> one "landmine dispatch" dry-run line (INV-10).
#   6.  Phase 5 no-match fixture -> zero dispatches, silent skip (INV-10 negative case).
#   7.  Re-run idempotence: same input assembled twice produces byte-identical output (innovate).
#   8.  Structural-only tie-break suppresses dual-scout override (INV-9 variant).
#   9.  Phase 5 grep ignores fenced code blocks (inquisitor fix).

set -euo pipefail
cd "$(dirname "$0")"

echo "=== Check 1: 3 dedup'd causal claims produce 3 ledger entries (INV-7 N-count) ==="
python3 ledger_scorer.py assemble fixtures/brief-3-claims-input.md | diff - fixtures/brief-3-claims-expected.md
echo "  PASS"

echo "=== Check 1b: isolated dedup — 2 identical claims merge to 1 entry (INV-7 isolated merge) ==="
count=$(python3 ledger_scorer.py assemble fixtures/fixture-inv7-dedup/input.md | grep -c '^- \*\*L-')
[ "$count" = "1" ] || { echo "  FAIL expected 1 ledger entry, got $count"; exit 1; }
echo "  PASS"

echo "=== Check 2: empty-state brief ==="
python3 ledger_scorer.py assemble fixtures/brief-0-claims-input.md | diff - fixtures/brief-0-claims-expected.md
echo "  PASS"

echo "=== Check 3: scout omits [evidence:] tag → method: none ==="
python3 ledger_scorer.py assemble fixtures/scout-omits-tag-input.md | grep -q 'method: `none`, evidence: `—`'
echo "  PASS"

echo "=== Check 4: structural-only tag → disposition: awaiting (INV-9) ==="
python3 ledger_scorer.py assemble fixtures/structural-only-input.md | grep -q 'disposition: `awaiting`'
echo "  PASS"

echo "=== Check 5: Phase 5 grep finds falsification sentence → 1 landmine ==="
hits=$(python3 ledger_scorer.py phase5-grep fixtures/phase5-grep-match | wc -l)
[ "$hits" = "1" ] || { echo "  FAIL expected 1 hit, got $hits"; exit 1; }
echo "  PASS"

echo "=== Check 6: Phase 5 no matches → zero dispatches ==="
hits=$(python3 ledger_scorer.py phase5-grep fixtures/phase5-no-matches | wc -l)
[ "$hits" = "0" ] || { echo "  FAIL expected 0 hits, got $hits"; exit 1; }
echo "  PASS"

echo "=== Check 7: re-run idempotence — same input twice produces byte-identical output ==="
diff <(python3 ledger_scorer.py assemble fixtures/fixture-idempotent/input.md) \
     <(python3 ledger_scorer.py assemble fixtures/fixture-idempotent/input.md)
echo "  PASS"

echo "=== Check 8: structural-only-merge — dual-scout merge attempted but structural-only wins (INV-9 tie-break) ==="
output=$(python3 ledger_scorer.py assemble fixtures/fixture-structural-only-merge/input.md)
echo "$output" | grep -q 'method: `structural-only`' || { echo "  FAIL expected method: structural-only"; exit 1; }
echo "$output" | grep -q 'disposition: `awaiting`' || { echo "  FAIL expected disposition: awaiting"; exit 1; }
if echo "$output" | grep -q 'method: `dual-scout`'; then echo "  FAIL dual-scout must not appear"; exit 1; fi
diff <(echo "$output") fixtures/fixture-structural-only-merge/expected.md
echo "  PASS"

echo "=== Check 9: Phase 5 grep ignores fenced code blocks (inquisitor fix) ==="
hits=$(python3 ledger_scorer.py phase5-grep fixtures/phase5-grep-fenced | wc -l)
[ "$hits" = "1" ] || { echo "  FAIL expected 1 hit (non-fenced only), got $hits"; exit 1; }
echo "  PASS"

echo "=== ALL CHECKS PASSED (9/9) ==="
