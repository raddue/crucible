"""Decision rule: turn paired WITH/WITHOUT trial results into a verdict.

`decide(with_results, without_results, *, band="iqr") -> {adopt|skip|reject|expand}`

The step ordering is load-bearing — reject precedes every skip, the 0-LOC floor
guard sits AFTER reject (so a degenerate arm that also fails the carve-out gate
still surfaces as reject), and the borderline check precedes the plain
band-overlap skip. Bands default to IQR (Q3 of WITH vs Q1 of WITHOUT); the
`minmax` alternative uses WITH's max vs WITHOUT's min. Bands are SEPARATED iff
`WITH_Q3 < WITHOUT_Q1`, and TOUCH/OVERLAP iff `WITH_Q3 >= WITHOUT_Q1`.
"""
from __future__ import annotations

import statistics
from typing import List

REDUCTION_THRESHOLD = 0.15


def _median_loc(results) -> float:
    return statistics.median(r.non_test_source_loc for r in results)


def _mean_pass_rate(results) -> float:
    return statistics.mean(r.assertion_pass_rate for r in results)


def _band_bounds(results, band: str):
    """Return (lower_bound, upper_bound) of the arm's LOC band."""
    locs = [r.non_test_source_loc for r in results]
    if band == "minmax":
        return min(locs), max(locs)
    if band == "iqr":
        q1, _q2, q3 = statistics.quantiles(locs, n=4, method="inclusive")
        return q1, q3
    raise ValueError(f"unknown band: {band!r}")


def decide(with_results: List, without_results: List, *, band: str = "iqr") -> str:
    if not with_results or not without_results:
        raise ValueError("decide() requires non-empty with/without result lists")
    n = len(with_results)
    with_median = _median_loc(with_results)
    without_median = _median_loc(without_results)
    with_pass = _mean_pass_rate(with_results)
    without_pass = _mean_pass_rate(without_results)
    cuts_loc = with_median < without_median  # ANY reduction

    # 1. Reject — cuts LOC but breaks the absolute carve-out gate or regresses
    #    non-carve correctness below WITHOUT.
    if cuts_loc and (
        any(not r.carve_out_passed for r in with_results)
        or with_pass < without_pass
    ):
        return "reject"

    # 2. Degenerate-solution floor guard (after reject so a carve-out-failing
    #    degenerate arm is rejected above, not masked as skip here).
    if any(r.non_test_source_loc <= 0 for r in with_results):
        return "skip"

    # 3. Correctness gate.
    if with_pass < without_pass:
        return "skip"

    # 4. Reduction must be >= 15% of WITHOUT median.
    if with_median > without_median * (1 - REDUCTION_THRESHOLD):
        return "skip"

    # 5. Majority of WITH trials must beat the WITHOUT median.
    majority = sum(1 for r in with_results if r.non_test_source_loc < without_median)
    minimum_majority = n // 2 + 1
    if majority < minimum_majority:
        return "skip"

    # Band separation (deterministic): SEPARATED iff WITH_Q3 < WITHOUT_Q1.
    _with_lo, with_q3 = _band_bounds(with_results, band)
    without_q1, _without_hi = _band_bounds(without_results, band)
    bands_overlap = with_q3 >= without_q1

    # 6. Borderline (exactly-minimum majority OR bands touch/overlap) — precedes
    #    the plain band-overlap skip. Terminal at n>=10 to bound expansion.
    if majority == minimum_majority or bands_overlap:
        return "expand" if n < 10 else "skip"

    # 7. Plain band-overlap skip (defensive net; subsumed by step 6's overlap
    #    clause, kept to match the gated ordering).
    if bands_overlap:
        return "skip"

    # 8. Otherwise adopt.
    return "adopt"
