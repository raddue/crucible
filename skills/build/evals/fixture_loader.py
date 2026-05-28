"""Fixture loader for build-evals harness.

Loads a fixture directory (fixture.json + seed/ + mock-dispatch/ + optional mock-user-input/)
into a typed Fixture dataclass for the harness to stage and score.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class FixtureSchemaError(Exception):
    pass


@dataclass
class Fixture:
    id: str
    task: str
    expectations: list[dict]
    seed_dir: Path
    mock_dispatch_dir: Path
    mock_user_input_dir: Path | None
    mode: str | None
    no_mock: bool = False


_REQUIRED_KEYS = {"id", "task", "expectations"}


def load_fixture(fixture_dir: Path) -> Fixture:
    """Load a fixture from disk. Raises FixtureSchemaError on any structural problem."""
    fixture_dir = Path(fixture_dir)
    fjson = fixture_dir / "fixture.json"
    if not fjson.exists():
        raise FixtureSchemaError(f"missing fixture.json in {fixture_dir}")
    try:
        data = json.loads(fjson.read_text())
    except json.JSONDecodeError as e:
        raise FixtureSchemaError(f"invalid JSON in {fjson}: {e}") from e
    if not isinstance(data, dict):
        raise FixtureSchemaError(f"fixture.json must be an object, got {type(data).__name__}")
    missing = _REQUIRED_KEYS - set(data)
    if missing:
        raise FixtureSchemaError(f"fixture.json missing required keys: {sorted(missing)}")
    if not isinstance(data["expectations"], list):
        raise FixtureSchemaError("fixture.json 'expectations' must be a list")

    seed = fixture_dir / "seed"
    if not seed.is_dir():
        raise FixtureSchemaError(f"missing seed/ directory in {fixture_dir}")

    mui = fixture_dir / "mock-user-input"
    return Fixture(
        id=data["id"],
        task=data["task"],
        expectations=data["expectations"],
        seed_dir=seed,
        mock_dispatch_dir=fixture_dir / "mock-dispatch",
        mock_user_input_dir=mui if mui.is_dir() else None,
        mode=data.get("mode"),
        no_mock=bool(data.get("no_mock", False)),
    )
