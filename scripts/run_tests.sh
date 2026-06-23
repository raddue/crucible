#!/usr/bin/env bash
# scripts/run_tests.sh
# Canonical test runner for Crucible — the single source of truth for the
# repo's gating suite. Both CI (.github/workflows/ci.yml) and humans invoke
# THIS script, so the local suite and the CI suite can never drift.
#
# Runs every suite even if an earlier one fails (no `set -e`), collects the
# failures, and exits non-zero iff any suite failed. `::group::`/`::endgroup::`
# markers fold each suite in the GitHub Actions log (and print harmlessly as
# plain lines locally).
#
# Adding a suite? Add ONE `run` line below — it is then covered locally and in
# CI atomically.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

failed=()
total=0

run() {
  total=$((total + 1))
  echo "::group::$*"
  if "$@"; then
    echo "::endgroup::"
  else
    echo "::endgroup::"
    failed+=("$*")
  fi
}

# --- Structural / canonical checks ---
run python3 scripts/check_canonical_drift.py
run python3 scripts/check_i2_marker.py
run python3 scripts/check_qg_stagnation_minor.py
run python3 scripts/check_qg_minor_advisory.py --selftest
run python3 scripts/check_qg_minor_advisory.py
run python3 scripts/check_crossref.py --selftest
run python3 scripts/check_crossref.py
run python3 scripts/catalog.py check

# --- Receipt-verify (rcpt_verify) ---
run python3 scripts/rcpt_verify.py --selftest
run python3 scripts/test_rcpt_verify.py
run bash hooks/tests/test-rcpt-verify-hook.sh

# --- Calibration dispatch / Brier advisory ---
run python3 scripts/check_calibration_dispatch.py --selftest
run python3 scripts/check_calibration_dispatch.py
run python3 scripts/test_brier_advise.py

# --- Ledger pipeline pure core (#398 Phase 1) ---
run python3 scripts/test_ledger_core.py

# --- Ledger GIT layer: falsification discovery (#439 / #441) ---
run python3 scripts/test_reconcile_git.py

# --- Lock state machines + crash recovery (#398 Phase 2) ---
run python3 scripts/test_locks.py

# --- Central-store mutators: grudge / render_ledger / backfill (#398 Phase 3) ---
run python3 scripts/test_stores.py

# --- Model-pin guardrail ---
run python3 scripts/check_model_pins.py --selftest
run python3 scripts/check_model_pins.py

# --- Ledger write-path guard ---
run python3 scripts/check_ledger_write_path.py --selftest
run python3 scripts/check_ledger_write_path.py

# --- #366 red-team <-> quality-gate receipt contract ---
run python3 scripts/check_rt_receipt_contract.py

# --- Inquisitor eval harness (#424) ---
run python3 scripts/check_inquisitor_helper_drift.py --selftest
run python3 scripts/check_inquisitor_helper_drift.py
run python3 scripts/check_judge_prompt_contract.py --selftest
run python3 scripts/check_judge_prompt_contract.py
run python3 scripts/check_ground_truth_provenance.py --selftest
run python3 scripts/check_ground_truth_provenance.py
run python3 scripts/check_inquisitor_secondary_count.py --selftest
run python3 scripts/check_inquisitor_secondary_count.py
run python3 skills/inquisitor/evals/test_run_evals_stage.py
run python3 skills/inquisitor/evals/test_run_evals_score.py
run python3 skills/inquisitor/evals/test_runid.py
# --- Phase 1b: seeded-repo fixtures + variant materialization + oracle (#424) ---
run python3 skills/inquisitor/evals/test_fixtures.py
run python3 skills/inquisitor/evals/test_oracle.py
run python3 skills/inquisitor/evals/test_run_evals_exec.py
run python3 skills/inquisitor/evals/test_build_collect_args.py
run python3 scripts/check_fixture_independence.py --selftest
run python3 scripts/check_fixture_independence.py
run python3 scripts/check_fixture_gt_provenance.py --selftest
run python3 scripts/check_fixture_gt_provenance.py
run python3 scripts/check_fixture_producer_blind.py --selftest
run python3 scripts/check_fixture_producer_blind.py
run python3 scripts/check_inquisitor_phase1b_invariants.py --selftest
run python3 scripts/check_inquisitor_phase1b_invariants.py

# --- Minimalism-ladder eval harness (#425) ---
# REQUIRES pytest (uses parametrize/fixtures); CI provisions pytest==9.0.3. This
# is the only -m pytest line in the suite — bare `python3 file.py` would silently
# skip the pytest-collected tests.
run python3 -m pytest skills/build/evals/minimalism-ladder/ -q

# --- Catalog unit suite ---
run python3 scripts/test_catalog.py

# --- Build-routing advisor + reconcile hooks ---
run bash hooks/tests/test-build-routing-advisor.sh
run bash hooks/tests/test-gate-ledger-guard.sh
run bash hooks/tests/tools/test-build-routing-reconcile.sh

# --- Summary ---
if [ ${#failed[@]} -ne 0 ]; then
  echo
  echo "FAILED (${#failed[@]}):"
  for f in "${failed[@]}"; do echo "  - $f"; done
  exit 1
fi

echo
echo "All ${total} suite invocations passed."
