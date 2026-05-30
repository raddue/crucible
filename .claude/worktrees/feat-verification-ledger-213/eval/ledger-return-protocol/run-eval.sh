#!/usr/bin/env bash
# End-to-end eval for the Ledger Return Protocol (issue #202 AC#4).
#
# Runs three checks:
#   1. Context-reduction metric on the hand-authored sample corpus
#      (5 representative dispatches). Target: p50 ratio <= 0.25.
#   2. Sample-corpus receipts all pass the reference linter.
#   3. All synthetic injections (attack shapes a/b/c/d) are caught
#      by the reference linter.
#
# The sample corpus is a small hand-authored stand-in. A full replay
# against a past /build run is future work (follow-up issue noted in
# the PR body).

set -euo pipefail

cd "$(dirname "$0")"

echo "=== Check 1: context-reduction metric (sample corpus) ==="
python3 measure.py sample-corpus/prose-returns.jsonl sample-corpus/receipts.jsonl
echo

echo "=== Check 2: sample-corpus receipts must all LINT-PASS ==="
python3 lint.py sample-corpus/receipts.jsonl | tee /tmp/lint-sample.out
fails=$(grep -c LINT-FAIL /tmp/lint-sample.out || true)
if [[ "$fails" -ne 0 ]]; then
  echo "FAIL: $fails sample receipts failed lint"
  exit 1
fi
echo "PASS: all sample receipts lint clean"
echo

echo "=== Check 3: synthetic injections must all LINT-FAIL ==="
for shape in inject/shape-*.jsonl; do
  echo "-- $shape --"
  python3 lint.py "$shape" | tee /tmp/lint-inject.out
  passes=$(grep -c LINT-PASS /tmp/lint-inject.out || true)
  if [[ "$passes" -ne 0 ]]; then
    echo "FAIL: $passes injections slipped past the linter in $shape"
    exit 1
  fi
  echo "PASS: all injections in $shape correctly flagged"
done

echo
echo "=== Check 4: Layer 2 tripwire scenarios must all pass ==="
for s in tripwire/scenario-*.jsonl; do
  echo "-- $s --"
  python3 tripwire/sweep.py "$s" | tee /tmp/sweep-result.out
  fails=$(grep -c "^  FAIL" /tmp/sweep-result.out || true)
  if [[ "$fails" -ne 0 ]]; then
    echo "FAIL: $fails tripwire check(s) failed in $s"
    exit 1
  fi
done
echo "PASS: all tripwire scenarios pass"
echo

echo "=== ALL CHECKS PASSED ==="
