"""Tests for score() subcommand (Task 6 of #297).

SP3 / F-1: All tests in this file MUST use module-attribute access
(`run_evals._LAST_RUN`, `run_evals._BASELINE_PATH`) — never hardcode
`skills/temper/evals/...` paths. The shared `_seed_dispatch_dir` helper
monkeypatches _LAST_RUN, _BASELINE_PATH, and _EVALS_DIR to tmp_path,
so any test that wants to read or assert against these files must do so
through the module attribute (which the helper has redirected) — not via
`Path("skills/temper/evals/baseline.json")` which would bypass the redirect.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skills.temper.evals import run_evals
from skills.temper.evals.run_evals import score, stage


def _seed_dispatch_dir(monkeypatch, tmp_path, run_id="R-score"):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("USER", "tester")
    # SP3 / F-1: redirect last_run.json, baseline.json, AND _EVALS_DIR to tmp_path
    monkeypatch.setattr(run_evals, "_LAST_RUN", tmp_path / "last_run.json")
    monkeypatch.setattr(run_evals, "_BASELINE_PATH", tmp_path / "baseline.json")
    monkeypatch.setattr(run_evals, "_EVALS_DIR", tmp_path)
    dispatch_dir = stage(run_id)
    return dispatch_dir


def test_score_with_no_results_returns_n_a(monkeypatch, tmp_path):
    d = _seed_dispatch_dir(monkeypatch, tmp_path)
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    rc = score("R-score", allow_incomplete=False)
    assert rc in (0, 1)
    out = json.loads(run_evals._LAST_RUN.read_text())
    assert "fixtures" in out
    for fr in out["fixtures"]:
        assert all(o is None for o in fr["reviewer_outputs"])


def test_score_refuses_when_collect_status_absent(monkeypatch, tmp_path):
    """2P-2 R5: score() returns rc (no sys.exit) — assert return-code."""
    _seed_dispatch_dir(monkeypatch, tmp_path)
    rc = score("R-score")
    assert rc == 2


def test_score_allow_incomplete_writes_incomplete_header(monkeypatch, tmp_path):
    _seed_dispatch_dir(monkeypatch, tmp_path)
    score("R-score", allow_incomplete=True)
    out = json.loads(run_evals._LAST_RUN.read_text())
    assert out.get("incomplete") is True
    assert "incomplete-cause" not in out  # cause undetermined per S-2


def test_score_all_error_sets_incomplete_cause(monkeypatch, tmp_path):
    """M-4 R5 / AC-14: when all dispatches errored, last_run.json header carries
    `incomplete-cause: all-error` AND score refuses to PASS.
    """
    d = _seed_dispatch_dir(monkeypatch, tmp_path, "R-allerr")
    manifest = json.loads((d / "stage-manifest.json").read_text())
    total = len(manifest["trials"])
    (d / ".collect-status").write_text(f"complete\nerrors: {total}/{total}\n")
    rc = score("R-allerr", allow_incomplete=False)
    assert rc == 2
    score("R-allerr", allow_incomplete=True)
    out = json.loads(run_evals._LAST_RUN.read_text())
    assert out.get("incomplete") is True
    assert out.get("incomplete-cause") == "all-error", (
        f"AC-14: expected incomplete-cause: all-error, got {out.get('incomplete-cause')!r}"
    )


def test_score_no_stage_manifest_returns_fatal(monkeypatch, tmp_path):
    """No stage-manifest.json at dispatch dir → rc=2."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("USER", "tester")
    monkeypatch.setattr(run_evals, "_LAST_RUN", tmp_path / "last_run.json")
    monkeypatch.setattr(run_evals, "_BASELINE_PATH", tmp_path / "baseline.json")
    monkeypatch.setattr(run_evals, "_EVALS_DIR", tmp_path)
    rc = score("R-nonexistent")
    assert rc == 2


def test_score_baseline_stubs_raise_not_implemented(monkeypatch, tmp_path):
    """S-R4-1: --write-baseline / --compare-baseline raise NotImplementedError
    cleanly between Task 6 and Task 8 commits."""
    d = _seed_dispatch_dir(monkeypatch, tmp_path, "R-stub")
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    with pytest.raises(NotImplementedError, match="Task 8"):
        score("R-stub", write_baseline=True)
    with pytest.raises(NotImplementedError, match="Task 8"):
        score("R-stub", compare_baseline=True)


def test_aggregate_from_outputs_matches_run_fixture_legacy(monkeypatch):
    """SP2 / F-2: _aggregate_from_outputs(fix, outs) == _run_fixture(fix, replay_outputs=outs).

    F-2: To guard against silent regression where some future refactor causes
    replay_outputs=[None,...] to trigger live dispatch, we monkeypatch
    subprocess.run to RAISE — any subprocess call during this test fails loud.
    """
    import subprocess

    from skills.temper.evals.run_evals import _aggregate_from_outputs, _run_fixture

    def _no_subprocess(*a, **kw):
        raise AssertionError(
            "F-2 violation: _run_fixture(replay_outputs=[None]*n) attempted a subprocess call; "
            "the replay branch must not invoke live dispatch."
        )
    monkeypatch.setattr(subprocess, "run", _no_subprocess)

    evals = json.loads(Path("skills/temper/evals/evals.json").read_text())
    fix = evals["evals"][0]
    rule = fix.get("replicate_rule", {"trials": 1, "threshold": 1})
    n_trials = rule.get("trials", 1)
    threshold = rule.get("threshold", 1)
    outs = [None] * n_trials
    legacy_result = _run_fixture(
        fix,
        template=None,
        mock_dir=None,
        replay_outputs=outs,
        trials_override=None,
        timeout=0,
    )
    extracted_result = _aggregate_from_outputs(
        fix, outs, n_trials=n_trials, threshold=threshold
    )
    assert legacy_result == extracted_result


def test_aggregate_from_outputs_has_no_implicit_closure_leak():
    """S2 R8/R9: closure-dep enumeration is read from /tmp/_aggregate_closure_deps.txt
    (populated by Task 6 Step 0's inspection). The helper's kwarg signature
    must match exactly — catches operator forgetting to mirror Step 0 findings.
    """
    import inspect

    from skills.temper.evals.run_evals import _aggregate_from_outputs

    closure_deps_file = Path("/tmp/_aggregate_closure_deps.txt")
    assert closure_deps_file.exists(), (
        "S2 R9: closure-deps file missing — run Task 6 Step 0 inspection first "
        "and write findings to /tmp/_aggregate_closure_deps.txt."
    )
    expected = set(closure_deps_file.read_text().split())
    sig = inspect.signature(_aggregate_from_outputs)
    params = set(sig.parameters)
    assert "fix" in params
    assert "reviewer_outputs" in params
    kwargs = params - {"fix", "reviewer_outputs"}
    assert kwargs == expected, (
        f"S2 R9: closure-dep mismatch: signature has {kwargs}, expected {expected}. "
        f"Update _aggregate_from_outputs signature OR re-run Step 0 inspection."
    )
