"""Tests for stage() subcommand (Task 3 of #297)."""

import json

import pytest

from skills.temper.evals.run_evals import stage


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
        ["python", "-m", "skills.temper.evals.run_evals",
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
