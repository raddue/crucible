import json
from pathlib import Path

import pytest

from skills.build.evals.fixture_loader import Fixture, FixtureSchemaError, load_fixture


def _write_fixture(root: Path, fixture_id: str, data: dict, *, seed: bool = True, mui: bool = False) -> Path:
    fdir = root / fixture_id
    fdir.mkdir()
    (fdir / "fixture.json").write_text(json.dumps(data))
    if seed:
        (fdir / "seed").mkdir()
        (fdir / "seed" / "marker.txt").write_text("hi")
    if mui:
        (fdir / "mock-user-input").mkdir()
    return fdir


def test_load_minimal_fixture(tmp_path: Path) -> None:
    d = _write_fixture(tmp_path, "f", {"id": "f", "task": "do thing", "expectations": []})
    fx = load_fixture(d)
    assert isinstance(fx, Fixture)
    assert fx.id == "f"
    assert fx.task == "do thing"
    assert fx.expectations == []
    assert fx.mode is None
    assert fx.mock_user_input_dir is None
    assert fx.no_mock is False


def test_load_with_mode_and_mock_user_input(tmp_path: Path) -> None:
    d = _write_fixture(
        tmp_path,
        "f",
        {"id": "f", "task": "x", "expectations": [], "mode": "refactor"},
        mui=True,
    )
    fx = load_fixture(d)
    assert fx.mode == "refactor"
    assert fx.mock_user_input_dir == d / "mock-user-input"


def test_load_with_no_mock_flag(tmp_path: Path) -> None:
    d = _write_fixture(tmp_path, "smoke", {"id": "smoke", "task": "x", "expectations": [], "no_mock": True})
    assert load_fixture(d).no_mock is True


def test_missing_fixture_json_raises(tmp_path: Path) -> None:
    (tmp_path / "f").mkdir()
    (tmp_path / "f" / "seed").mkdir()
    with pytest.raises(FixtureSchemaError, match="missing fixture.json"):
        load_fixture(tmp_path / "f")


def test_malformed_json_raises(tmp_path: Path) -> None:
    d = tmp_path / "f"
    d.mkdir()
    (d / "fixture.json").write_text("{not valid json")
    (d / "seed").mkdir()
    with pytest.raises(FixtureSchemaError, match="invalid JSON"):
        load_fixture(d)


def test_missing_required_keys_raises(tmp_path: Path) -> None:
    d = tmp_path / "f"
    d.mkdir()
    (d / "fixture.json").write_text(json.dumps({"id": "x"}))
    (d / "seed").mkdir()
    with pytest.raises(FixtureSchemaError, match="missing required keys"):
        load_fixture(d)


def test_missing_seed_raises(tmp_path: Path) -> None:
    d = tmp_path / "f"
    d.mkdir()
    (d / "fixture.json").write_text(json.dumps({"id": "f", "task": "x", "expectations": []}))
    with pytest.raises(FixtureSchemaError, match="missing seed/"):
        load_fixture(d)


def test_expectations_must_be_list(tmp_path: Path) -> None:
    d = tmp_path / "f"
    d.mkdir()
    (d / "fixture.json").write_text(json.dumps({"id": "f", "task": "x", "expectations": "not a list"}))
    (d / "seed").mkdir()
    with pytest.raises(FixtureSchemaError, match="must be a list"):
        load_fixture(d)
