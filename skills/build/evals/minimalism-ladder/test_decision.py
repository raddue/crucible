"""Unit tests for the decision rule's edges not pinned by the acceptance suite.

Covers: the innovate 0-LOC floor guard (and its ordering vs reject), the
band-touch boundary `WITH_Q3 == WITHOUT_Q1` both ways (n=5 expand / n=10 skip),
and a band where minmax overlaps while IQR separates. Band bounds below were
computed with `statistics.quantiles(..., n=4, method="inclusive")`.
"""
from __future__ import annotations

import pytest

import decision
import scorer


def _r(loc_val, *, pass_rate=1.0, carve=True):
    return scorer.TrialResult(
        non_test_source_loc=loc_val,
        assertion_pass_rate=pass_rate,
        carve_out_passed=carve,
    )


def test_empty_arm_raises_valueerror():
    # A truncated/empty arm (e.g. a collect run that lost trials to throttling)
    # must raise a clear ValueError, not a bare StatisticsError from median().
    with pytest.raises(ValueError):
        decision.decide([], [_r(90)])
    with pytest.raises(ValueError):
        decision.decide([_r(40)], [])


def test_zero_loc_trial_forces_skip_even_when_all_adopt_conditions_hold():
    # One 0-LOC trial; the rest is a textbook adopt (>=15% reduction, full
    # majority, separated bands, carve-outs all pass). Carve-outs PASS so the
    # reject check does not fire -> the step-2 floor guard produces skip.
    with_arm = [_r(0), _r(42), _r(44), _r(46), _r(48)]
    without_arm = [_r(90), _r(92), _r(94), _r(96), _r(98)]
    assert decision.decide(with_arm, without_arm) == "skip"


def test_zero_loc_with_carveout_failure_still_rejects():
    # A degenerate arm that ALSO fails the carve-out gate must surface as reject
    # (step 1, before the step-2 floor guard), not be masked as skip.
    with_arm = [_r(0, carve=False), _r(42), _r(44), _r(46), _r(48)]
    without_arm = [_r(90), _r(92), _r(94), _r(96), _r(98)]
    assert decision.decide(with_arm, without_arm) == "reject"


def test_band_touch_boundary_expands_at_n5():
    # Exact touch: WITH_Q3 == WITHOUT_Q1 == 55. reduction 28.6%, full majority
    # (so the borderline trigger is the band touch, not a minimum majority).
    with_arm = [_r(40), _r(45), _r(50), _r(55), _r(60)]      # Q3 = 55
    without_arm = [_r(40), _r(55), _r(70), _r(85), _r(100)]  # Q1 = 55
    assert decision.decide(with_arm, without_arm) == "expand"


def test_band_touch_boundary_skips_at_n10():
    # Same exact-touch boundary (WITH_Q3 == WITHOUT_Q1 == 73.75) scaled to n=10
    # -> borderline is terminal at n>=10 -> skip (expansion does not loop).
    with_arm = [_r(40), _r(45), _r(50), _r(55), _r(60),
                _r(65), _r(70), _r(75), _r(80), _r(85)]       # Q3 = 73.75
    without_arm = [_r(40), _r(55), _r(70), _r(85), _r(100),
                   _r(115), _r(130), _r(145), _r(160), _r(175)]  # Q1 = 73.75
    assert decision.decide(with_arm, without_arm) == "skip"


def test_minmax_overlaps_where_iqr_separates():
    # An outlier (95) makes WITH's max reach WITHOUT's min (minmax overlap) while
    # the IQR quartiles stay separated.
    with_arm = [_r(40), _r(42), _r(44), _r(46), _r(95)]     # IQR Q3 = 46, max 95
    without_arm = [_r(90), _r(92), _r(94), _r(96), _r(98)]  # IQR Q1 = 92, min 90
    assert decision.decide(with_arm, without_arm, band="iqr") == "adopt"
    assert decision.decide(with_arm, without_arm, band="minmax") == "expand"
