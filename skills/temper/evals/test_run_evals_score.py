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


def test_write_baseline_produces_matching_baseline_json(monkeypatch, tmp_path):
    """Task 8 AC-10b: --write-baseline emits baseline.json mirroring last_run
    verdicts + a template_sha header (SP-1)."""
    d = _seed_dispatch_dir(monkeypatch, tmp_path, "R-base")
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    score("R-base", write_baseline=True)
    # F-1: read via module attributes (monkeypatched to tmp_path) — NOT via
    # hardcoded skills/temper/evals/ paths.
    baseline = json.loads(run_evals._BASELINE_PATH.read_text())
    last_run = json.loads(run_evals._LAST_RUN.read_text())
    # Header carries template_sha (SP-1)
    assert "template_sha" in baseline
    # Verdicts match
    assert [f["verdict"] for f in baseline["fixtures"]] == [
        f["verdict"] for f in last_run["fixtures"]
    ]


def test_compare_baseline_exits_nonzero_on_regression(monkeypatch, tmp_path):
    """Task 8 AC-10c: --compare-baseline returns non-zero when current verdicts
    regress relative to baseline."""
    d = _seed_dispatch_dir(monkeypatch, tmp_path, "R-cmp")
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    score("R-cmp", write_baseline=True)
    # F-1: mutate via module-attribute path (monkeypatched to tmp_path)
    baseline = json.loads(run_evals._BASELINE_PATH.read_text())
    if baseline["fixtures"]:
        baseline["fixtures"][0]["verdict"] = "PASS"  # claim baseline was PASS
    run_evals._BASELINE_PATH.write_text(json.dumps(baseline))
    # New run with all-N/A (no results) — compare should detect regression
    rc = score("R-cmp", compare_baseline=True)
    # rc==1 iff regression; rc==2 if incomplete-blocked; either signals nonzero
    assert rc != 0


def test_compare_baseline_refuses_incomplete(monkeypatch, tmp_path):
    """AC-13 + Override Flags: --compare-baseline refuses to compare incomplete."""
    _seed_dispatch_dir(monkeypatch, tmp_path, "R-incomplete")
    # Skip .collect-status
    score("R-incomplete", allow_incomplete=True)  # writes incomplete: true
    rc = score("R-incomplete", compare_baseline=True, allow_incomplete=True)
    assert rc == 2  # explicit refusal exit


def test_compare_baseline_warns_on_template_drift(monkeypatch, tmp_path, capsys):
    """SP2 R8: when current template_sha differs from baseline.template_sha,
    --compare-baseline emits a `[warn]` line to stderr (apples-to-oranges narration).

    Asserts the warn-not-refuse asymmetry documented in Task 8's M6 R6 note:
    template_sha drift is informational; the comparison still proceeds.
    """
    d = _seed_dispatch_dir(monkeypatch, tmp_path, "R-drift")
    (d / ".collect-status").write_text("complete\nerrors: 0/0\n")
    score("R-drift", write_baseline=True)
    # Mutate baseline.template_sha to a different value to simulate drift
    baseline = json.loads(run_evals._BASELINE_PATH.read_text())
    baseline["template_sha"] = "0" * 64  # bogus sha, certain to differ from current
    run_evals._BASELINE_PATH.write_text(json.dumps(baseline))
    capsys.readouterr()  # clear prior output
    score("R-drift", compare_baseline=True)
    captured = capsys.readouterr()
    assert "[warn]" in captured.err
    assert "template_sha drift" in captured.err, (
        "SP2 R8: --compare-baseline must emit a template_sha drift warning"
    )


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


# ---------------------------------------------------------------------------
# Task 7: structural DISPATCH_STATUS sentinel parser (S-1, I-T6)
# ---------------------------------------------------------------------------


def test_parse_result_file_ok(tmp_path):
    """M-2: use tmp_path, not hardcoded /tmp/, to avoid parallel-test collisions."""
    from skills.temper.evals.run_evals import _parse_result_file
    p = tmp_path / "test-result-ok.md"
    p.write_text("DISPATCH_STATUS: OK\n\n### Code Review\nVerdict: Clean\n")
    out = _parse_result_file(p)
    assert out is not None
    assert "Code Review" in out
    assert "DISPATCH_STATUS" not in out  # stripped from body


def test_parse_result_file_error_returns_none(tmp_path):
    from skills.temper.evals.run_evals import _parse_result_file
    p = tmp_path / "test-result-err.md"
    p.write_text("DISPATCH_STATUS: ERROR: timeout\n\n")
    out = _parse_result_file(p)
    assert out is None


def test_parse_result_file_collision_safety(tmp_path):
    """I-T6: reviewer body containing literal 'DISPATCH_STATUS:' must not flip parse."""
    from skills.temper.evals.run_evals import _parse_result_file
    p = tmp_path / "test-result-collision.md"
    p.write_text(
        "DISPATCH_STATUS: OK\n\n"
        "### Code Review\nThe code mentions DISPATCH_STATUS: ERROR but that's a quote.\n"
    )
    out = _parse_result_file(p)
    assert out is not None
    assert "DISPATCH_STATUS: ERROR" in out  # body preserved


def test_parse_result_file_empty_body_returns_none(tmp_path):
    """S1: `OK\\n\\n` with empty body returns None, not empty string."""
    from skills.temper.evals.run_evals import _parse_result_file
    p = tmp_path / "test-result-empty.md"
    p.write_text("DISPATCH_STATUS: OK\n\n")
    out = _parse_result_file(p)
    assert out is None


def test_parse_result_file_whitespace_only_body_returns_none(tmp_path):
    """S1 R10: `OK` with whitespace-only body returns None — strip-check
    semantics align with SKILL.md Step 7's empty-body promotion gate."""
    from skills.temper.evals.run_evals import _parse_result_file
    p = tmp_path / "test-result-ws.md"
    p.write_text("DISPATCH_STATUS: OK\n\n   \n\t\n")
    out = _parse_result_file(p)
    assert out is None
