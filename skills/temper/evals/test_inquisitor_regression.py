"""Inquisitor Regression dimension (#297).

Hunts breakage of pre-#297 functionality. Existing AC-3 / legacy_modes tests
cover --mock-reviewer end-to-end via subprocess; these tests probe the CLI
surface contracts and the legacy code paths from different angles.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from skills.temper.evals import run_evals


# Vector 1: pre-#297, `python -m run_evals` with NO subcommand and NO flags
# attempted live dispatch. Post-#297, that path is dead. The CLI must NOT
# crash with a Python traceback — it must produce a clear operator-facing
# fatal explaining the new stage/score subcommand workflow.
def test_legacy_main_no_flags_produces_guided_fatal_not_traceback(tmp_path):
    """Bare `python -m run_evals` (no subcommand, no flags) must guide the
    operator to the new workflow, not crash."""
    env = {**os.environ, "TEMPER_LAST_RUN_OVERRIDE": str(tmp_path / "lr.json")}
    result = subprocess.run(
        [sys.executable, "-m", "skills.temper.evals.run_evals"],
        capture_output=True, text=True, timeout=30, env=env,
    )
    assert result.returncode != 0  # must be fatal
    combined = result.stdout + result.stderr
    assert "Traceback" not in combined, (
        f"Bare invocation crashed with traceback: {combined}"
    )
    # Must mention the new workflow
    assert "stage" in combined or "/temper-eval-collect" in combined, (
        f"Fatal message does not guide operator to new workflow: {combined}"
    )


# Vector 2: --replay still works. This is the pre-#297 replay mode for
# re-evaluating a captured last_run.json. The legacy code path was rewired
# (template arg removed from _resolve_output, etc.); a regression that
# accidentally drops --replay support would silently break re-evaluation
# of historical runs.
def test_legacy_replay_mode_still_works(monkeypatch, tmp_path):
    """--replay reads outputs from a prior last_run.json and re-evaluates."""
    # Fabricate a minimal prior-run last_run.json
    fake_last_run = tmp_path / "fake_prior.json"
    fake_last_run.write_text(json.dumps({
        "run_at": "2026-01-01T00:00:00Z",
        "fixtures": [
            {
                "id": "1a",  # real fixture id from evals.json
                "verdict": "PASS",
                "trials": 1,
                "threshold": 1,
                "reviewer_outputs": [
                    "### Code Review\nVerdict: changes-requested\n\n### Issues\nFinding text\n"
                ],
                "expectations": [],
            }
        ],
    }))
    out = tmp_path / "last_run.json"
    env = {**os.environ, "TEMPER_LAST_RUN_OVERRIDE": str(out)}
    result = subprocess.run(
        [sys.executable, "-m", "skills.temper.evals.run_evals",
         "--replay", str(fake_last_run), "--legacy-fixture", "1a"],
        capture_output=True, text=True, timeout=30, env=env,
    )
    # Replay mode must not crash with traceback even if verdicts are N/A
    assert "Traceback" not in (result.stdout + result.stderr), (
        f"--replay regressed: {result.stderr}"
    )
    assert out.exists()


# Vector 3: convergence_runner.evaluate_expectation and aggregate_replicates
# contracts remained intact through the refactor. _aggregate_from_outputs is the
# new wrapper that calls them; verify with a real expectation that they still work.
# (Renamed from lens_runner -> convergence_runner in #333; this is a misfiled
# temper-harness test that still lives in the inquisitor regression file —
# relocation tracked as a follow-up.)
def test_convergence_runner_evaluate_contract_unchanged():
    """The convergence_runner public surface used by score()/legacy must still work."""
    from skills.temper.evals import convergence_runner
    # Use a real fixture's expectation shape (verdict_contains is common)
    fix = {"id": "x", "expected_output": "test"}
    expectation = {"check": "verdict_contains", "params": {"value": "approve"}}
    reviewer_out = "### Code Review\nVerdict: approve\nNo findings.\n"
    verdict, rationale = convergence_runner.evaluate_expectation(expectation, reviewer_out, fix)
    assert verdict in ("PASS", "FAIL", "N/A")
    assert isinstance(rationale, str)


# Vector 4: subprocess module was removed from run_evals.py (was used only
# by the deleted _dispatch_live). Verify it's truly absent — keeping a stale
# `import subprocess` would mean dead-code lint trips and would mask any
# future re-introduction of subprocess shell-outs.
def test_subprocess_import_removed_from_run_evals():
    """#297 removed the only subprocess.run() call; the import should be gone."""
    import inspect
    src = inspect.getsource(run_evals)
    # Allow subprocess in docstrings (post-#297 references it in deprecation note)
    # but it must not be imported.
    assert "\nimport subprocess" not in src, (
        "subprocess module still imported in run_evals.py — dead code or "
        "silent re-introduction of banned subprocess dispatch"
    )


# Vector 5: argparse flag rename --fixture -> --legacy-fixture for the root
# parser (pre-existing) must NOT have broken the `stage --fixture` subparser
# flag. A naive find/replace during the refactor could have inadvertently
# renamed the stage subparser's --fixture too, breaking the calibrate skill's
# documented `--fixture <id>` pass-through.
def test_stage_fixture_flag_not_renamed_to_legacy_fixture(tmp_path, monkeypatch):
    """The stage subparser's --fixture flag must remain --fixture (not
    --legacy-fixture). Calibrate skill passes --fixture through verbatim."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("USER", "tester")
    # `stage R-x --fixture 1a` must succeed (or fail for fixture-not-found
    # reasons, NOT for "unrecognized arguments" reasons).
    result = subprocess.run(
        [sys.executable, "-m", "skills.temper.evals.run_evals",
         "stage", "R-fixflag", "--fixture", "1a"],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "XDG_RUNTIME_DIR": str(tmp_path), "USER": "tester"},
    )
    # If --fixture was renamed, argparse error would mention "unrecognized"
    assert "unrecognized arguments" not in result.stderr.lower(), (
        f"stage --fixture flag broken: {result.stderr}"
    )
    # And it should produce a dispatch dir
    assert (tmp_path / "tester-crucible-dispatch-R-fixflag").exists()
