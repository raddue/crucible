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
# Absolute, resolved BEFORE the cd below. `${BASH_SOURCE[0]}` is relative to the caller's
# cwd, so re-using it after `cd "$REPO_ROOT"` re-anchors it to the wrong directory: the
# freeze-guard measured `bash crucible/scripts/run_tests.sh` from the parent giving
# `flock: cannot open lock file … No such file or directory`, exit 66, ZERO of the suites
# run. The quieter half is worse — invoked as `bash run_tests.sh` from `scripts/`, flock
# CREATES the missing lock file (flock(1): "created … if it does not already exist") in
# the repo root and execs that empty file: zero tests, exit 0, a silent GREEN from the
# script CLAUDE.md calls the single source of truth. Derived from BASH_SOURCE rather than
# spelled `$REPO_ROOT/scripts/run_tests.sh` so a rename cannot desynchronise it.
SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
cd "$REPO_ROOT" || exit 1

# --- One invocation at a time, per checkout (round-1/C3-R1-S5) --------------------
# Two invocations in flight against the same checkout do NOT produce an independent
# second reading of the suite; they corrupt each other. Reproduced: three concurrent
# runs, one of which failed `pytest skills/siege/evals/` with
# `FileNotFoundError: skills/siege/evals/last_run.json` — that suite save-restores a
# path INSIDE the checkout (`_EVALS_DIR / "last_run.json"`, mirrored in delve's), so
# run B's tearDown unlinks the file run A is between writing and reading. Nothing about
# it is a regression, and per-invocation scratch directories cannot fix it: the shared
# fixture is a repo path, not a temp one. Serializing here is what makes a concurrent
# invocation safe, and it is cheap — the second run waits instead of lying.
#
# The lock is taken on THIS SCRIPT: no new file, no gitignore question, correct in a
# git worktree, and per-checkout by construction. A fixed lock path under /tmp was
# rejected for the reason `scripts/compass.py` records — a co-tenant can pre-create it.
# `flock` is util-linux; where it is absent the suite runs exactly as before, since the
# serialization is a safety net and not a correctness precondition for a single run.
if [ -z "${CRUCIBLE_SUITE_SERIALIZED:-}" ] && command -v flock >/dev/null 2>&1; then
  export CRUCIBLE_SUITE_SERIALIZED=1
  # Re-exec through the interpreter, not the path: the file is mode 644 in this repo
  # (`bash scripts/run_tests.sh` is the documented invocation), so `flock <lock> <path>`
  # would exec it directly and die with EACCES.
  exec flock "$SELF" "${BASH:-bash}" "$SELF" "$@"
fi

# --- Test isolation: one PRIVATE temp namespace per invocation (round-1/C3-R1-S5) ---
# Every suite below builds its scratch through `tempfile` (Python) or `mktemp` (bash),
# and both resolve against $TMPDIR — by default the SHARED /tmp. Two invocations in
# flight at once therefore share one temp namespace. Individual scratch DIRECTORIES are
# already unique (`TemporaryDirectory()` / `mktemp -d`), but the NAMESPACE is not, so any
# suite that reasons about the namespace rather than about its own directory — e.g.
# `skills/inquisitor/evals/test_fixtures.py`, which globs `gettempdir()/variant-*` before
# and after a call to assert the fixture cleaned up after itself — sees the other run's
# files and goes red for a reason that is not a regression. A spurious RED is the same
# class of defect as a spurious GREEN: both make the suite unusable as evidence.
# Scoping $TMPDIR here removes the class for every suite at once, and costs one mkdir.
_SUITE_TMPDIR="$(mktemp -d "${TMPDIR:-/tmp}/crucible-suite-XXXXXXXX")" || exit 1
export TMPDIR="$_SUITE_TMPDIR"
trap 'rm -rf -- "$_SUITE_TMPDIR"' EXIT

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

# --- warden structural checks (#464) ---
run python3 scripts/check_warden_structure.py --selftest
run python3 scripts/check_warden_structure.py
run python3 scripts/check_build_clean_tree_contract.py --selftest
run python3 scripts/check_build_clean_tree_contract.py
run python3 scripts/check_warden_integration.py --selftest
run python3 scripts/check_warden_integration.py

# --- Receipt-verify (rcpt_verify) ---
run python3 scripts/rcpt_verify.py --selftest
run python3 scripts/test_rcpt_verify.py
run python3 scripts/measure_474_denominators.py
run python3 scripts/test_measure_474.py
run python3 scripts/test_measure_486.py
run bash hooks/tests/test-rcpt-verify-hook.sh

# --- #488 c1 receipt name-space acceptance tests ---
run python3 scripts/test_488_name_space.py
run python3 scripts/dec31_sweep.py          # AC-6 DEC-31 mutant sweep (#488 c1)
run python3 scripts/test_dec31_sweep_harness.py   # the sweep HARNESS itself

# --- #488 c1 warden-leg-2 (inquisitor) cross-component robustness pins ---
run python3 scripts/test_488_wiring.py
run python3 scripts/test_488_inquisitor_integration.py
run python3 scripts/test_488_inquisitor_edge.py
run python3 scripts/test_488_inquisitor_state.py
run python3 scripts/test_488_regression_inquisitor.py

# --- Calibration dispatch / Brier advisory ---
run python3 scripts/check_calibration_dispatch.py --selftest
run python3 scripts/check_calibration_dispatch.py
run python3 scripts/test_brier_advise.py
run python3 scripts/test_calibrate_tolerance.py

# --- Ledger pipeline pure core (#398 Phase 1) ---
run python3 scripts/test_ledger_core.py

# --- Ledger GIT layer: falsification discovery (#439 / #441) ---
run python3 scripts/test_reconcile_git.py

# --- Path-aware glob single-source-of-truth (#401) ---
run python3 scripts/test_pathmatch.py

# --- crucible-qg-fix model-pin regression (#537) ---
run python3 scripts/test_qg_fix_pin.py

# --- compass parser/patch/render core (#408 F16a) ---
run python3 scripts/test_compass.py

# --- ledger weekly render core (#408 F16b) ---
run python3 scripts/test_render_ledger.py

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
# REQUIRES pytest (uses parametrize/fixtures); CI provisions pytest==9.0.3. The
# suite has two -m pytest lines (this and skills/temper/evals/ below) — bare
# `python3 file.py` would silently skip the pytest-collected tests.
run python3 -m pytest skills/build/evals/minimalism-ladder/ -q

# --- Temper eval harness (#290/#297/#424) — pytest-collected ---
# Gated here (#404): previously UNRUN. The temper/evals tests are pytest-collected
# (bare `python3 file.py` silently skips them), and no -m pytest line covered them,
# so CI never exercised temper/evals at all — the 162 tests behind temper's
# run_evals stage/score, convergence_runner, _dispatch_paths, _runid, legacy modes,
# global expectations, and the #297 inquisitor-dimension suites.
run python3 -m pytest skills/temper/evals/ -q

# --- Delve eval harness (#373) ---
run python3 -m pytest skills/delve/evals/ -q
run python3 scripts/check_delve_helper_drift.py --selftest
run python3 scripts/check_delve_helper_drift.py
run python3 scripts/check_delve_gt_provenance.py --selftest
run python3 scripts/check_delve_gt_provenance.py

# --- Siege eval harness (#373) ---
run python3 -m pytest skills/siege/evals/ -q
run python3 scripts/check_siege_helper_drift.py --selftest
run python3 scripts/check_siege_helper_drift.py
run python3 scripts/check_siege_gt_provenance.py --selftest
run python3 scripts/check_siege_gt_provenance.py

# --- warden eval harness (#464) ---
run python3 -m pytest skills/warden/evals/ -q
run python3 scripts/check_warden_helper_drift.py --selftest
run python3 scripts/check_warden_helper_drift.py

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
