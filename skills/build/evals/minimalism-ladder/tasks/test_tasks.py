"""Unit tests for the tasks package: registry shape + carve-out semantics.

The carve-out checks must, against the committed fixtures, PASS vs `minimal` and
FAIL vs `carveout_violating`. The scorer's "exception escaping a check == FAIL"
rule is what makes that work; here we exercise the checks directly by importing
the fixture solutions, independent of the scorer, to pin the catch-internally
shape.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

import tasks

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _load_solution(solution_dir: Path):
    spec = importlib.util.spec_from_file_location(
        f"_t_{solution_dir.parent.name}_{solution_dir.name}",
        solution_dir / "solution.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_load_task_raises_on_unknown():
    with pytest.raises(KeyError):
        tasks.load_task("does_not_exist")


@pytest.mark.parametrize("name", ["cli_wordcount", "fixture_loader"])
def test_task_assertion_lists_non_empty(name):
    task = tasks.load_task(name)
    assert task.assertions
    assert task.carve_out_assertions


def _run_checks(task, solution_dir, *, monkeypatch):
    """Run every carve-out check with cwd at solution_dir; True == all passed."""
    monkeypatch.chdir(solution_dir)
    module = _load_solution(solution_dir)
    for assertion in task.carve_out_assertions:
        try:
            assertion.check(module)
        except Exception:
            return False
    return True


def test_cli_carveouts_pass_minimal_fail_violating(monkeypatch):
    task = tasks.load_task("cli_wordcount")
    base = FIXTURES / "cli_wordcount"
    assert _run_checks(task, base / "minimal", monkeypatch=monkeypatch) is True
    assert _run_checks(task, base / "carveout_violating", monkeypatch=monkeypatch) is False


def test_fixture_loader_carveouts_pass_minimal_fail_violating(monkeypatch):
    task = tasks.load_task("fixture_loader")
    base = FIXTURES / "fixture_loader"
    assert _run_checks(task, base / "minimal", monkeypatch=monkeypatch) is True
    assert _run_checks(task, base / "carveout_violating", monkeypatch=monkeypatch) is False
