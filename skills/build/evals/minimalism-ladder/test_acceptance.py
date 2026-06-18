"""Acceptance tests for the minimalism-ladder eval harness (Phase 1 RED).

These integration-level tests define "done" for the eval harness and MUST FAIL
until the harness modules exist. They drive the runner/scorer with PRE-GENERATED
fixture solution dirs (no live LLM dispatch) — codegen is a pluggable step the
implementer must keep injectable so these tests can supply solution dirs directly.

Proposed public API the implementer must satisfy (importable as top-level names
because the committed dir is hyphenated; conftest puts the dir on sys.path):

    loc.count_non_test_source_loc(solution_dir: Path) -> int

    scorer.TrialResult(non_test_source_loc: int,
                       assertion_pass_rate: float,
                       carve_out_passed: bool)            # frozen dataclass
    scorer.score_solution(task, solution_dir: Path) -> TrialResult

    tasks.load_task(name: str) -> Task
    tasks.TASKS: dict[str, Task]
    Task.assertions: list[Assertion]
    Task.carve_out_assertions: list[Assertion]   # assertions with carve_out=True

    decision.decide(with_results: list[TrialResult],
                    without_results: list[TrialResult],
                    *, band: str = "iqr") -> str   # {adopt, skip, reject, expand}
"""
from __future__ import annotations

from pathlib import Path

import pytest

import loc  # noqa: E402
import scorer  # noqa: E402
import decision  # noqa: E402
import tasks  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


# --------------------------------------------------------------------------
# 1. LOC counter
# --------------------------------------------------------------------------

def test_loc_counts_non_blank_non_comment_source_lines():
    # loc_sample/solution.py has exactly 5 countable lines
    # (import os, def f, return x+1, def g, return 2); blanks + comment-only
    # lines are excluded, and test_solution.py is excluded as a test file.
    n = loc.count_non_test_source_loc(FIXTURES / "loc_sample")
    assert n == 5


def test_loc_excludes_test_files():
    # Removing the test file must NOT change the count -> test files were excluded.
    sample = loc.count_non_test_source_loc(FIXTURES / "loc_sample")
    # The fixture dir contains a test_solution.py with countable lines; if it were
    # counted the number would be > 5.
    assert sample == 5


def test_bloated_solution_counts_strictly_more_than_minimal():
    minimal = loc.count_non_test_source_loc(FIXTURES / "cli_wordcount" / "minimal")
    bloated = loc.count_non_test_source_loc(FIXTURES / "cli_wordcount" / "bloated")
    assert bloated > minimal


# --------------------------------------------------------------------------
# 2. Runner/scorer end-to-end (no live codegen)
# --------------------------------------------------------------------------

def test_minimal_solution_passes_all_assertions_including_carveout():
    task = tasks.load_task("cli_wordcount")
    res = scorer.score_solution(task, FIXTURES / "cli_wordcount" / "minimal")
    assert res.assertion_pass_rate == 1.0
    assert res.carve_out_passed is True
    assert res.non_test_source_loc > 0


def test_carveout_violation_fails_gate_cli():
    # Drops the path-traversal / missing-arg guard: happy-path counting still
    # works, but the carve-out assertions fail.
    task = tasks.load_task("cli_wordcount")
    res = scorer.score_solution(
        task, FIXTURES / "cli_wordcount" / "carveout_violating"
    )
    assert res.carve_out_passed is False


def test_carveout_violation_fails_gate_fixture_loader():
    task = tasks.load_task("fixture_loader")
    res = scorer.score_solution(
        task, FIXTURES / "fixture_loader" / "carveout_violating"
    )
    assert res.carve_out_passed is False


def test_fixture_loader_minimal_passes_carveout():
    task = tasks.load_task("fixture_loader")
    res = scorer.score_solution(
        task, FIXTURES / "fixture_loader" / "minimal"
    )
    assert res.assertion_pass_rate == 1.0
    assert res.carve_out_passed is True


# --------------------------------------------------------------------------
# 3. Decision rule
# --------------------------------------------------------------------------

def _r(loc_val, *, pass_rate=1.0, carve=True):
    return scorer.TrialResult(
        non_test_source_loc=loc_val,
        assertion_pass_rate=pass_rate,
        carve_out_passed=carve,
    )


def test_decision_rule_clear_adopt():
    # WITH band (40-48) entirely below WITHOUT band (90-98); >15% reduction;
    # reduction holds in all 5; carve-outs 100%; non-carve pass >= without.
    with_arm = [_r(40), _r(42), _r(44), _r(46), _r(48)]
    without_arm = [_r(90), _r(92), _r(94), _r(96), _r(98)]
    assert decision.decide(with_arm, without_arm) == "adopt"


def test_decision_rule_clear_skip_overlapping_bands():
    # Heavy overlap -> no separation -> skip.
    with_arm = [_r(80), _r(85), _r(90), _r(95), _r(100)]
    without_arm = [_r(82), _r(88), _r(92), _r(96), _r(101)]
    assert decision.decide(with_arm, without_arm) == "skip"


def test_decision_rule_skip_reduction_under_15pct():
    # Median reduction < 15% -> skip even if bands look separated.
    with_arm = [_r(88), _r(89), _r(90), _r(91), _r(92)]
    without_arm = [_r(98), _r(99), _r(100), _r(101), _r(102)]
    assert decision.decide(with_arm, without_arm) == "skip"


def test_decision_rule_carveout_failure_rejects():
    # WITH clearly cuts LOC but fails the absolute carve-out gate in >=1 trial.
    with_arm = [_r(40), _r(42), _r(44, carve=False), _r(46), _r(48)]
    without_arm = [_r(90), _r(92), _r(94), _r(96), _r(98)]
    assert decision.decide(with_arm, without_arm) == "reject"


def test_decision_rule_reject_on_correctness_regression():
    # WITH cuts LOC but its non-carve-out pass rate drops below WITHOUT.
    with_arm = [_r(40, pass_rate=0.5), _r(42, pass_rate=0.5),
                _r(44, pass_rate=0.5), _r(46, pass_rate=0.5),
                _r(48, pass_rate=0.5)]
    without_arm = [_r(90), _r(92), _r(94), _r(96), _r(98)]
    assert decision.decide(with_arm, without_arm) == "reject"


def test_decision_rule_borderline_expands():
    # >=15% reduction + exactly 3-of-5 majority below WITHOUT median -> borderline
    # at n=5 -> expand. WITHOUT median = 100; 3 WITH values (80,82,84) < 100, the
    # other two (101,103) are not -> exactly 3-of-5.
    with_arm = [_r(80), _r(82), _r(84), _r(101), _r(103)]
    without_arm = [_r(98), _r(99), _r(100), _r(101), _r(102)]
    assert decision.decide(with_arm, without_arm) == "expand"


def test_decision_rule_still_borderline_at_n10_skips():
    # >=15% reduction but the majority is exactly the minimum (6 of 10) -> still
    # borderline at n=10 -> terminal -> skip (expansion does not loop forever).
    with_arm = ([_r(70), _r(72), _r(74), _r(76), _r(78), _r(80)]
                + [_r(101), _r(103), _r(105), _r(107)])
    without_arm = [_r(96), _r(97), _r(98), _r(99), _r(100),
                   _r(101), _r(102), _r(103), _r(104), _r(105)]
    # 6 of 10 WITH values below WITHOUT median (100.5) == minimum majority ->
    # borderline -> at n>=10 route to skip.
    assert decision.decide(with_arm, without_arm) == "skip"


# --------------------------------------------------------------------------
# 4. Both pilot tasks exist and each declares >=1 carve-out assertion
# --------------------------------------------------------------------------

def test_both_pilot_tasks_exist():
    assert set(tasks.TASKS) >= {"cli_wordcount", "fixture_loader"}


@pytest.mark.parametrize("name", ["cli_wordcount", "fixture_loader"])
def test_each_task_declares_at_least_one_carveout(name):
    task = tasks.load_task(name)
    assert len(task.carve_out_assertions) >= 1
