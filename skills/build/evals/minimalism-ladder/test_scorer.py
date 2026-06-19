"""Unit tests for the scorer: cwd discipline, module isolation, S1 carve-out.

The acceptance suite pins the fixture end-to-end outcomes; these cover the
subtle bits the design flags — cwd restoration on raise, collision-free module
loading across consecutive dirs, fractional pass rates, and the S1 guard (a
carve-out that catches its expected exception internally is PASS; one that lets
it escape is FAIL).
"""
from __future__ import annotations

import os
from pathlib import Path

import scorer
import tasks

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_cwd_restored_after_raising_check():
    before = os.getcwd()
    # cli carve_out_violating makes a carve-out raise; cwd must still restore.
    scorer.score_solution(
        tasks.load_task("cli_wordcount"),
        FIXTURES / "cli_wordcount" / "carveout_violating",
    )
    assert os.getcwd() == before


def test_consecutive_calls_load_correct_solution():
    # If module names collided in sys.modules, the second call would re-run the
    # first dir's code. The two dirs differ in LOC, so the counts diverging
    # proves each loaded its own solution.py.
    minimal = scorer.score_solution(
        tasks.load_task("cli_wordcount"), FIXTURES / "cli_wordcount" / "minimal"
    )
    bloated = scorer.score_solution(
        tasks.load_task("cli_wordcount"), FIXTURES / "cli_wordcount" / "bloated"
    )
    assert minimal.assertion_pass_rate == 1.0
    assert bloated.assertion_pass_rate == 1.0
    assert bloated.non_test_source_loc > minimal.non_test_source_loc


def test_carveout_failures_do_not_lower_correctness_rate():
    # assertion_pass_rate is over NON-carve assertions only. The violating cli
    # passes both happy-path (non-carve) assertions, so its rate stays 1.0 even
    # though both carve-outs fail -> carve_out_passed False. A carve-out
    # regression must NOT be able to mask itself in the correctness rate.
    res = scorer.score_solution(
        tasks.load_task("cli_wordcount"),
        FIXTURES / "cli_wordcount" / "carveout_violating",
    )
    assert res.assertion_pass_rate == 1.0
    assert res.carve_out_passed is False


def test_partial_non_carve_pass_gives_fractional_rate():
    # Two NON-carve assertions, exactly one fails -> 0.5. One check returns None
    # (pass); the other lets a ValueError escape (fail). carve_out_passed stays
    # True because neither failing assertion is a carve-out.
    def passing(m):
        m.load_fixture('{"id": "ok"}')  # returns a dict, no raise -> pass

    def failing(m):
        m.load_fixture('{"id": 123}')  # ValueError escapes -> fail

    task = tasks.Task(
        name="probe",
        prompt="",
        entry_module="solution.py",
        assertions=[
            tasks.Assertion("pass", passing, carve_out=False),
            tasks.Assertion("fail", failing, carve_out=False),
        ],
    )
    res = scorer.score_solution(task, FIXTURES / "fixture_loader" / "minimal")
    assert res.assertion_pass_rate == 0.5
    assert res.carve_out_passed is True


def _result_for(check, *, carve_out):
    task = tasks.Task(
        name="probe",
        prompt="",
        entry_module="solution.py",
        assertions=[tasks.Assertion("probe", check, carve_out=carve_out)],
    )
    return scorer.score_solution(task, FIXTURES / "fixture_loader" / "minimal")


def test_carveout_catching_internally_scores_pass():
    # S1 guard: a check that catches its expected exception internally and
    # returns None is a PASS / carve_out_passed True.
    def check(m):
        try:
            m.load_fixture('{"id": 123}')
        except ValueError:
            return
        raise AssertionError("accepted non-string id")

    res = _result_for(check, carve_out=True)
    assert res.assertion_pass_rate == 1.0
    assert res.carve_out_passed is True


def test_carveout_letting_exception_escape_scores_fail():
    # S1 guard inverse: a check that lets its expected exception escape is a FAIL,
    # recorded via carve_out_passed. assertion_pass_rate is the non-carve rate,
    # so with no non-carve assertions it stays at the 1.0 fallback regardless.
    def check(m):
        m.load_fixture('{"id": 123}')  # ValueError escapes -> carve-out fail

    res = _result_for(check, carve_out=True)
    assert res.assertion_pass_rate == 1.0
    assert res.carve_out_passed is False
