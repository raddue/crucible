#!/usr/bin/env python3
"""T-4: Brier advisory prints/silences on the n + brier thresholds (design §5).

Direct unit test of scripts.brier_advisory.advisory_line() (PURE core). No
subprocesses, no central-store IO.

Assertions:
  1. n=5, brier=0.30  -> PRINTS (n>=5 AND brier>0.25).
  2. n=4, brier=0.30  -> SILENT (n below 5).
  3. n=5, brier=0.20  -> SILENT (brier at/below 0.25).
  4. n=5, brier=0.25  -> SILENT (boundary: strictly-greater, not >=).
  5. skill absent from brier map -> SILENT.
  6. printed line carries the n and brier values, formatted to 2 dp.
  7. fresh data (staleness ~0) prints NO staleness suffix.
  8. data 7-30 days stale prints the staleness suffix; >30 days is SILENT.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

_results = []


def _check(label, cond, detail=""):
    tag = "[PASS]" if cond else "[FAIL]"
    msg = f"{tag} {label}"
    if detail and not cond:
        msg += f"  -- {detail}"
    print(msg)
    _results.append(cond)


def _adv(brier, skill, staleness_days=0.0):
    from scripts.brier_advisory import advisory_line
    return advisory_line(
        brier, skill,
        falsification_exists=True,
        staleness_days=staleness_days,
        disabled=False,
    )


def test_prints_at_threshold():
    line = _adv({"quality-gate": {"n": 5, "brier": 0.30}}, "quality-gate")
    _check("T-4.1 n=5 brier=0.30 -> prints", line is not None, f"got {line!r}")


def test_silent_below_n():
    line = _adv({"quality-gate": {"n": 4, "brier": 0.30}}, "quality-gate")
    _check("T-4.2 n=4 -> silent", line is None, f"got {line!r}")


def test_silent_below_brier():
    line = _adv({"quality-gate": {"n": 5, "brier": 0.20}}, "quality-gate")
    _check("T-4.3 brier=0.20 -> silent", line is None, f"got {line!r}")


def test_silent_at_brier_boundary():
    line = _adv({"quality-gate": {"n": 5, "brier": 0.25}}, "quality-gate")
    _check("T-4.4 brier=0.25 (boundary) -> silent", line is None, f"got {line!r}")


def test_silent_skill_absent():
    line = _adv({"siege": {"n": 9, "brier": 0.40}}, "quality-gate")
    _check("T-4.5 skill not in map -> silent", line is None, f"got {line!r}")


def test_line_carries_values():
    line = _adv({"siege": {"n": 7, "brier": 0.337}}, "siege")
    cond = line is not None and "last 7 verdicts" in line and "0.34" in line
    _check("T-4.6 line carries n and brier (2dp)", cond, f"got {line!r}")


def test_no_suffix_when_fresh():
    line = _adv({"quality-gate": {"n": 5, "brier": 0.30}}, "quality-gate",
                staleness_days=0.0)
    cond = line is not None and "stale" not in line
    _check("T-4.7 fresh data -> no staleness suffix", cond, f"got {line!r}")


def test_silent_on_bool_fields():
    # bool is a subclass of int/float; a malformed `"brier": true` must NOT
    # print "Brier of 1.00" — it must degrade to silent.
    _check("T-4.9a brier=true -> silent",
           _adv({"quality-gate": {"n": 9, "brier": True}}, "quality-gate") is None)
    _check("T-4.9b n=true -> silent",
           _adv({"quality-gate": {"n": True, "brier": 0.40}}, "quality-gate") is None)
    # NaN/Infinity (json.load parses bare NaN/Infinity) must degrade to silent,
    # not print "Brier of inf"/"Brier of nan".
    _check("T-4.9c brier=inf -> silent",
           _adv({"quality-gate": {"n": 9, "brier": float("inf")}}, "quality-gate") is None)
    _check("T-4.9d brier=nan -> silent",
           _adv({"quality-gate": {"n": 9, "brier": float("nan")}}, "quality-gate") is None)


def test_suffix_when_stale_window():
    line = _adv({"quality-gate": {"n": 5, "brier": 0.30}}, "quality-gate",
                staleness_days=12.0)
    cond = line is not None and "12-day-stale" in line
    _check("T-4.8a 7-30d stale -> suffix", cond, f"got {line!r}")
    line2 = _adv({"quality-gate": {"n": 5, "brier": 0.30}}, "quality-gate",
                 staleness_days=45.0)
    _check("T-4.8b >30d stale -> silent", line2 is None, f"got {line2!r}")


def main():
    test_prints_at_threshold()
    test_silent_below_n()
    test_silent_below_brier()
    test_silent_at_brier_boundary()
    test_silent_skill_absent()
    test_silent_on_bool_fields()
    test_line_carries_values()
    test_no_suffix_when_fresh()
    test_suffix_when_stale_window()
    failures = sum(1 for r in _results if not r)
    if failures:
        print(f"\n{failures} assertion(s) FAILED")
        return 1
    print(f"\nALL {len(_results)} assertions PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
