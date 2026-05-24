"""Inquisitor State & Lifecycle dimension (#297).

Hunts state-mismanagement across the stage -> collect -> score lifecycle
and across consecutive runs with the same / overlapping run-ids.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skills.temper.evals import run_evals
from skills.temper.evals._dispatch_paths import resolve_dispatch_dir
from skills.temper.evals.run_evals import score, stage


def _seed(monkeypatch, tmp_path, run_id):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("USER", "tester")
    monkeypatch.setattr(run_evals, "_LAST_RUN", tmp_path / "last_run.json")
    monkeypatch.setattr(run_evals, "_BASELINE_PATH", tmp_path / "baseline.json")
    monkeypatch.setattr(run_evals, "_EVALS_DIR", tmp_path)
    return stage(run_id)


# Vector 1: score-before-stage. Operator invokes `score R-typo` without first
# staging — must produce a clear fatal (rc=2) about the missing manifest,
# not crash with an opaque FileNotFoundError. Lifecycle violation must be
# diagnosed.
def test_score_without_stage_returns_fatal_not_traceback(monkeypatch, tmp_path):
    """Score-before-stage must return rc=2, not raise an unhandled exception."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("USER", "tester")
    monkeypatch.setattr(run_evals, "_LAST_RUN", tmp_path / "last_run.json")
    monkeypatch.setattr(run_evals, "_BASELINE_PATH", tmp_path / "baseline.json")
    monkeypatch.setattr(run_evals, "_EVALS_DIR", tmp_path)
    # No stage was called for R-no-stage
    rc = score("R-no-stage")
    assert rc == 2  # fatal but graceful


# Vector 2: stage->stage (re-stage without --force). The second stage MUST
# refuse with FileExistsError (idempotency-preserving). A silent overwrite
# would race with any in-flight `/temper-eval-collect` invocation against
# the original stage.
def test_restage_without_force_refuses(monkeypatch, tmp_path):
    """Re-staging the same run-id without --force protects in-flight collects."""
    _seed(monkeypatch, tmp_path, "R-restage")
    with pytest.raises(FileExistsError):
        stage("R-restage")


# Vector 3: stage->stage(force)->score lifecycle. After a forced re-stage,
# the OLD result files are wiped (rmtree). If score holds stale file handles
# from a prior invocation, it would read garbage. Verify clean lifecycle:
# force-restage produces an empty dispatch dir, score sees only new content.
def test_force_restage_wipes_stale_result_files(monkeypatch, tmp_path):
    """Force re-stage MUST rmtree the dispatch dir so stale result files
    from a prior collect cannot contaminate the new score."""
    d = _seed(monkeypatch, tmp_path, "R-wipe")
    # Simulate a prior collect: drop result files + collect-status + a sentinel
    manifest = json.loads((d / "stage-manifest.json").read_text())
    first_trial = manifest["trials"][0]
    (d / first_trial["result_file"]).write_text("DISPATCH_STATUS: OK\n\nstale body\n")
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    (d / "operator-marker").write_text("would survive a soft restage")

    # Force re-stage
    d2 = stage("R-wipe", force=True)
    assert d2 == d
    # All non-stage files must be gone
    assert not (d / first_trial["result_file"]).exists()
    assert not (d / ".collect-status").exists()
    assert not (d / "operator-marker").exists()
    # Stage artifacts re-created
    assert (d / "stage-manifest.json").exists()


# Vector 4: per-iter output directory creation. score(..., per_iter=True)
# writes to `.calibrate-state/last_run-<rid>.json`. The directory must be
# created lazily on first call (operators don't pre-create it). If it's
# missing AND mkdir isn't called, the write raises FileNotFoundError —
# which would corrupt a calibrate sweep mid-iteration.
def test_per_iter_creates_calibrate_state_dir_lazily(monkeypatch, tmp_path):
    """First-ever --per-iter score must lazy-create `.calibrate-state/`."""
    d = _seed(monkeypatch, tmp_path, "R-lazy")
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    # Confirm the dir does NOT exist before score
    cal_dir = tmp_path / ".calibrate-state"
    assert not cal_dir.exists()
    rc = score("R-lazy", per_iter=True, allow_incomplete=False)
    assert rc in (0, 1)
    # Now it MUST exist with the per-iter file inside
    assert cal_dir.exists() and cal_dir.is_dir()
    assert (cal_dir / "last_run-R-lazy.json").exists()


# Vector 5: consecutive per-iter scores with same run-id. Calibrate's
# idempotency check (sentinel + last_run-<i>.json with matching run_id)
# guards against re-running. But what if the operator manually invokes
# `score R-x --per-iter` twice without the calibrate skill's sentinel? The
# SECOND write must succeed (no lock file blocks it) AND must overwrite
# cleanly (no partial-write residue from the first).
def test_per_iter_score_can_safely_re_run(monkeypatch, tmp_path):
    """Manually re-running `score --per-iter` overwrites cleanly."""
    d = _seed(monkeypatch, tmp_path, "R-rerun")
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    score("R-rerun", per_iter=True, allow_incomplete=False)
    per_iter_path = tmp_path / ".calibrate-state" / "last_run-R-rerun.json"
    assert per_iter_path.exists()
    first = json.loads(per_iter_path.read_text())
    # Second run must succeed without error
    score("R-rerun", per_iter=True, allow_incomplete=False)
    second = json.loads(per_iter_path.read_text())
    # Both must have run_id field set correctly (no partial-write corruption)
    assert first["run_id"] == "R-rerun"
    assert second["run_id"] == "R-rerun"
