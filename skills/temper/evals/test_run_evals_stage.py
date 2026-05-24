"""Tests for stage() subcommand (Task 3 of #297)."""

import json
import sys

import pytest

from skills.temper.evals.run_evals import _validate_rendered_prompt, stage


def test_stage_produces_dispatch_files(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("USER", "tester")

    dispatch_dir = stage("R-test")

    # Manifest exists and well-formed
    manifest = json.loads((dispatch_dir / "stage-manifest.json").read_text())
    assert manifest["run_id"] == "R-test"
    assert manifest["reviewer_model"] == "opus"
    assert "template_sha" in manifest
    assert manifest["dispatch_timeout"] == 300

    # N fixtures × M trials dispatch files exist (count from evals.json)
    evals = json.loads(open("skills/temper/evals/evals.json").read())
    expected_count = sum(
        f.get("replicate_rule", {}).get("trials", 1) for f in evals["evals"]
    )
    actual = list(dispatch_dir.glob("*-reviewer.md"))
    assert len(actual) == expected_count == len(manifest["trials"])

    # Each trial entry well-formed
    for entry in manifest["trials"]:
        assert entry["seq"] >= 1
        assert "fixture_id" in entry
        assert "fixture_sha" in entry
        assert (dispatch_dir / entry["dispatch_file"]).exists()


def test_stage_refuses_existing_dir_without_force(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("USER", "tester")
    stage("R-test")
    with pytest.raises(FileExistsError):
        stage("R-test")


def test_stage_force_overwrites(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("USER", "tester")
    stage("R-test")
    stage("R-test", force=True)  # no raise


def test_stage_rejects_bad_run_id(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("USER", "tester")
    with pytest.raises(ValueError):
        stage("../etc")


# ---------------------------------------------------------------------------
# Task 4: stage CLI flag tests
# ---------------------------------------------------------------------------


def test_stage_cli_source_filter(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("USER", "tester")
    from skills.temper.evals.run_evals import main
    rc = main(["stage", "R-syn", "--source", "synthetic"])
    assert rc == 0
    assert (tmp_path / "tester-crucible-dispatch-R-syn").exists()


def test_stage_cli_force(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("USER", "tester")
    from skills.temper.evals.run_evals import main
    main(["stage", "R-force"])
    rc = main(["stage", "R-force", "--force"])
    assert rc == 0


def test_stage_cli_timeout_recorded(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("USER", "tester")
    from skills.temper.evals.run_evals import main
    main(["stage", "R-to", "--timeout", "600"])
    manifest = json.loads(
        (tmp_path / "tester-crucible-dispatch-R-to" / "stage-manifest.json").read_text()
    )
    assert manifest["dispatch_timeout"] == 600


def test_stage_timeout_not_demoted_to_legacy(monkeypatch, tmp_path):
    """S3: `--timeout 600` on stage subcommand must NOT silently fall through to legacy_timeout."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("USER", "tester")
    from skills.temper.evals.run_evals import _parse_args
    args = _parse_args(["stage", "R-x", "--timeout", "600"])
    assert args.cmd == "stage"
    assert args.timeout == 600
    assert getattr(args, "legacy_timeout", 120) == 120


def test_legacy_main_runs_without_attribute_error(tmp_path, monkeypatch):
    """S-2: after flag rename, _legacy_main must reference renamed attrs, not old ones."""
    import os
    import shutil
    import subprocess
    from pathlib import Path
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    src_fixtures = repo_root / "skills" / "temper" / "evals" / "mock-fixtures"
    if not src_fixtures.exists():
        pytest.skip("mock-fixtures not yet present — Task 8.5 lands later in this plan")
    dst_fixtures = tmp_path / "mock-fixtures"
    shutil.copytree(src_fixtures, dst_fixtures)
    last_run_out = tmp_path / "last_run.json"
    env = {**os.environ, "TEMPER_LAST_RUN_OVERRIDE": str(last_run_out)}
    repo_tracked = repo_root / "skills" / "temper" / "evals" / "last_run.json"
    repo_tracked_mtime_pre = repo_tracked.stat().st_mtime if repo_tracked.exists() else None
    result = subprocess.run(
        # Task 8.5 deviation: use sys.executable so the test runs under
        # environments where `python` is not on PATH (e.g. Debian/Ubuntu
        # without `python-is-python3`). Necessary now that mock-fixtures
        # exists and this test un-skips.
        [sys.executable, "-m", "skills.temper.evals.run_evals",
         "--mock-reviewer", str(dst_fixtures)],
        capture_output=True, text=True, timeout=120,
        cwd=str(repo_root), env=env,
    )
    assert last_run_out.exists(), (
        f"TEMPER_LAST_RUN_OVERRIDE ignored — output missing at {last_run_out}. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    if repo_tracked_mtime_pre is None:
        assert not repo_tracked.exists(), (
            f"TEMPER_LAST_RUN_OVERRIDE bypassed — subprocess wrote to repo-tracked "
            f"path: {repo_tracked}"
        )
    else:
        assert repo_tracked.stat().st_mtime == repo_tracked_mtime_pre, (
            f"TEMPER_LAST_RUN_OVERRIDE bypassed — repo-tracked path was modified: "
            f"{repo_tracked}"
        )
    assert "AttributeError" not in result.stderr, (
        f"_legacy_main attribute rename incomplete: {result.stderr}"
    )


def test_rendered_prompt_validator_rejects_small():
    with pytest.raises(ValueError, match="length"):
        _validate_rendered_prompt("tiny")


def test_rendered_prompt_validator_rejects_unsubstituted_placeholder():
    # >200 bytes so length-floor passes, but contains a placeholder marker
    body = "x" * 300 + " {DESCRIPTION} " + "y" * 100
    with pytest.raises(ValueError, match="placeholder"):
        _validate_rendered_prompt(body)


def test_rendered_prompt_validator_accepts_clean():
    clean = "a" * 500
    assert "{" not in clean
    _validate_rendered_prompt(clean)  # should not raise


def test_stage_rejects_zero_trials_override(monkeypatch, tmp_path):
    """QG R1 Fix 4: --trials-override 0 must rc=2, not silent-empty-manifest
    (which would PASS vacuously)."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("USER", "tester")
    from skills.temper.evals.run_evals import main
    rc = main(["stage", "R-zero-t", "--trials-override", "0"])
    assert rc == 2


def test_stage_rejects_zero_timeout(monkeypatch, tmp_path):
    """QG R1 Fix 4: --timeout 0 must rc=2 (defense against unusable manifest)."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("USER", "tester")
    from skills.temper.evals.run_evals import main
    rc = main(["stage", "R-zero-to", "--timeout", "0"])
    assert rc == 2


def test_stage_rejects_template_with_unsubstituted_placeholder(monkeypatch, tmp_path):
    """I-T9 integration: stage() must fail-fast if the template after substitution
    still contains `{` — even though fixture body legitimately contains `{`.
    Validates that validation scope is template-only (not full rendered prompt)."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("USER", "tester")
    bad_template_path = tmp_path / "bad-template.md"
    bad_template_path.write_text(
        "# Reviewer\n" + "x" * 250 + " {UNSUBSTITUTED_VAR} more text\n"
    )
    from skills.temper.evals import run_evals
    monkeypatch.setattr(run_evals, "_REVIEWER_PROMPT", bad_template_path)
    with pytest.raises(ValueError, match="placeholder"):
        run_evals.stage("R-bad")
