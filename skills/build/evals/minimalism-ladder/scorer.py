"""Scorer: run a task's assertions against a solution dir and grade it.

Phase 1 scores PRE-GENERATED solution dirs (the fixtures). The `codegen` seam is
the Phase-2 hook: a generator that, given a Task, produces a populated solution
dir. It is intentionally NOT built here — pass a populated `solution_dir` and
leave `codegen=None`.
"""
from __future__ import annotations

import importlib.util
import itertools
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import loc

_MODULE_COUNTER = itertools.count()


@dataclass(frozen=True)
class TrialResult:
    non_test_source_loc: int
    # Pass rate over the NON-carve-out correctness assertions only.
    assertion_pass_rate: float
    # Whether every carve-out assertion passed (absolute gate, graded separately).
    carve_out_passed: bool


def _load_solution_module(solution_dir: Path):
    """Load solution.py under a unique module name (no sys.modules collision)."""
    unique_name = f"_ml_solution_{next(_MODULE_COUNTER)}"
    spec = importlib.util.spec_from_file_location(
        unique_name, solution_dir / "solution.py"
    )
    module = importlib.util.module_from_spec(spec)
    # Intentionally NOT registered in sys.modules: avoids global pollution and
    # .pyc-staleness across calls (each trial gets a fresh load under a unique
    # name). The Phase-2 live-codegen seam may need to register it if generated
    # solutions rely on sys.modules[__name__] (pickling, self-relative imports).
    spec.loader.exec_module(module)
    return module


def score_solution(
    task,
    solution_dir: Path,
    *,
    codegen: Optional[Callable[[object], Path]] = None,
) -> TrialResult:
    """Grade a solution dir against `task`.

    `assertion_pass_rate` is the pass rate over the NON-carve-out correctness
    assertions only; carve-outs are graded separately by `carve_out_passed`
    (every carve-out must pass).

    `codegen` (Phase-2 hook, unused in Phase 1): if provided, it would populate
    and return the solution dir to score; the default None scores the already-
    populated `solution_dir`.
    """
    solution_dir = Path(solution_dir).resolve()
    if codegen is not None:
        solution_dir = Path(codegen(task)).resolve()

    module = _load_solution_module(solution_dir)

    # `assertion_pass_rate` is the pass rate over the NON-carve-out correctness
    # assertions only. Carve-outs are graded separately by `carve_out_passed`
    # (every carve-out must pass) so a non-carve correctness regression cannot
    # be masked by passing carve-outs (design criterion 1).
    non_carve_passes = 0
    non_carve_total = 0
    carve_out_passed = True
    original_cwd = os.getcwd()
    os.chdir(solution_dir)
    try:
        for assertion in task.assertions:
            try:
                assertion.check(module)
                passed = True
            except Exception:
                passed = False
            if assertion.carve_out:
                if not passed:
                    carve_out_passed = False
            else:
                non_carve_total += 1
                if passed:
                    non_carve_passes += 1
    finally:
        os.chdir(original_cwd)

    assertion_pass_rate = (
        non_carve_passes / non_carve_total if non_carve_total else 1.0
    )
    return TrialResult(
        non_test_source_loc=loc.count_non_test_source_loc(solution_dir),
        assertion_pass_rate=assertion_pass_rate,
        carve_out_passed=carve_out_passed,
    )
