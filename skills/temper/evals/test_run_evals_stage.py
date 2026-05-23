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
