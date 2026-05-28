import json
from pathlib import Path

from skills.build.evals.run_evals import score, stage


def _mk_fixture(root: Path, fixture_id: str, *, mode: str | None = None, no_mock: bool = False,
                expectations: list[dict] | None = None, mui: bool = False) -> Path:
    fdir = root / fixture_id
    fdir.mkdir(parents=True)
    body: dict = {"id": fixture_id, "task": "do thing", "expectations": expectations or []}
    if mode is not None:
        body["mode"] = mode
    if no_mock:
        body["no_mock"] = True
    (fdir / "fixture.json").write_text(json.dumps(body))
    seed = fdir / "seed"
    seed.mkdir()
    (seed / "src").mkdir()
    (seed / "src" / "__init__.py").write_text("")
    (fdir / "mock-dispatch").mkdir()
    if mui:
        (fdir / "mock-user-input").mkdir()
    return fdir


# ---- stage ----

def test_stage_creates_workdir_and_git_init(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    _mk_fixture(fixtures, "f")
    out = stage("f", tmp_path / "work", fixtures_root=fixtures)
    assert out.workdir.is_dir()
    assert (out.workdir / ".git").is_dir()
    assert (out.workdir / "src" / "__init__.py").exists()
    assert (out.workdir / ".eval-baseline-sha").read_text() == out.baseline_sha
    assert len(out.baseline_sha) >= 7  # short SHA at minimum


def test_stage_env_for_mock_fixture(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    _mk_fixture(fixtures, "f", mode="feature")
    out = stage("f", tmp_path / "work", fixtures_root=fixtures)
    assert "CRUCIBLE_BUILD_EVAL_MOCK_DIR" in out.env
    assert out.env["CRUCIBLE_BUILD_EVAL_MODE"] == "feature"
    assert out.env["HOME"].endswith(".home")


def test_stage_env_for_no_mock_fixture_omits_mock_vars(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    _mk_fixture(fixtures, "smoke", no_mock=True)
    out = stage("smoke", tmp_path / "work", fixtures_root=fixtures)
    assert "CRUCIBLE_BUILD_EVAL_MOCK_DIR" not in out.env
    assert "CRUCIBLE_BUILD_EVAL_MODE" not in out.env
    assert "CRUCIBLE_BUILD_EVAL_USER_INPUT_DIR" not in out.env
    assert out.env["HOME"].endswith(".home")


def test_stage_env_for_b4_with_empty_mock_user_input(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    _mk_fixture(fixtures, "b4", mode="feature", mui=True)
    out = stage("b4", tmp_path / "work", fixtures_root=fixtures)
    assert "CRUCIBLE_BUILD_EVAL_USER_INPUT_DIR" in out.env


# ---- score ----

def test_score_empty_build_output_fails_all(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    _mk_fixture(fixtures, "f", expectations=[
        {"type": "file_exists", "path": "expected.py"},
        {"type": "function_defined", "file": "expected.py", "name": "foo"},
    ])
    empty = tmp_path / "empty"
    empty.mkdir()
    r = score("f", empty, fixtures_root=fixtures)
    assert not r.passed
    assert all(not exp["passed"] for exp in r.expectations)


def test_score_passes_when_all_expectations_pass(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    _mk_fixture(fixtures, "f", expectations=[{"type": "file_exists", "path": "src/__init__.py"}])
    # use stage so we get a proper workdir with seed copied in
    staged = stage("f", tmp_path / "work", fixtures_root=fixtures)
    r = score("f", staged.workdir, fixtures_root=fixtures)
    assert r.passed
    assert all(exp["passed"] for exp in r.expectations)


def test_score_baseline_placeholder_uses_stage_file(tmp_path: Path) -> None:
    """`working_tree_unchanged_from` with baseline_sha=BASELINE should resolve from .eval-baseline-sha."""
    fixtures = tmp_path / "fixtures"
    _mk_fixture(fixtures, "f", expectations=[
        {"type": "working_tree_unchanged_from", "baseline_sha": "BASELINE"},
    ])
    staged = stage("f", tmp_path / "work", fixtures_root=fixtures)
    r = score("f", staged.workdir, fixtures_root=fixtures)
    assert r.passed, r.expectations
