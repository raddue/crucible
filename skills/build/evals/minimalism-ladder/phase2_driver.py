"""Phase-2 live-A/B driver for the minimalism-ladder eval (#425).

Scores already-generated solution dirs (one `solution.py` per trial, produced by
live codegen under the WITH/WITHOUT arms) using the UNTOUCHED Phase-1 contract
(`scorer.score_solution(task, dir, codegen=None)`), then applies the gated
`decision.decide()` rule PER TASK and combines conservatively.

Run layout (produced by the dispatch step, kept out of git under /tmp):

    <run_root>/<arm>/<task>/trial<k>/solution.py        # arm in {without, with}
    <run_root>/<arm>/cli_wordcount/trial<k>/fixtures_data/...   # provisioned inputs

decide() compares raw LOC distributions, so it CANNOT pool a ~14-line task with a
6-line task — it is applied per task. The overall verdict is a conservative
combine: reject if ANY task rejects; else expand if ANY task is borderline; else
adopt only if ALL tasks adopt; else skip.

Usage:  python3 phase2_driver.py [run_root]   (default /tmp/ml-phase2)
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

import decision
import tasks
from scorer import score_solution

ARMS = ("without", "with")
TASK_NAMES = ("cli_wordcount", "fixture_loader")


def _score_arm(task, arm_dir: Path):
    results = []
    for trial_dir in sorted(arm_dir.iterdir(), key=lambda p: int("".join(c for c in p.name if c.isdigit()) or 0)):
        if not (trial_dir / task.entry_module).exists():
            raise FileNotFoundError(f"missing {task.entry_module} in {trial_dir}")
        results.append(score_solution(task, trial_dir))
    return results


def _summ(results):
    locs = [r.non_test_source_loc for r in results]
    return {
        "n": len(results),
        "loc": locs,
        "loc_median": statistics.median(locs),
        "mean_noncarve_pass_rate": statistics.mean(r.assertion_pass_rate for r in results),
        "carve_out_all_passed": all(r.carve_out_passed for r in results),
        "carve_out_per_trial": [r.carve_out_passed for r in results],
    }


def _combine(verdicts: dict) -> str:
    vals = set(verdicts.values())
    if "reject" in vals:
        return "reject"
    if "expand" in vals:
        return "expand"
    if vals == {"adopt"}:
        return "adopt"
    return "skip"


def main(run_root: Path) -> dict:
    report = {"run_root": str(run_root), "tasks": {}}
    for name in TASK_NAMES:
        task = tasks.load_task(name)
        arm_results = {arm: _score_arm(task, run_root / arm / name) for arm in ARMS}
        verdict = decision.decide(arm_results["with"], arm_results["without"], band="iqr")
        report["tasks"][name] = {
            "verdict": verdict,
            "without": _summ(arm_results["without"]),
            "with": _summ(arm_results["with"]),
        }
    report["overall"] = _combine({k: v["verdict"] for k, v in report["tasks"].items()})
    return report


def _print(report: dict) -> None:
    print(f"\n=== minimalism-ladder Phase-2 verdict  (run_root={report['run_root']}) ===")
    for name, t in report["tasks"].items():
        w, wo = t["with"], t["without"]
        red = (wo["loc_median"] - w["loc_median"]) / wo["loc_median"] if wo["loc_median"] else 0.0
        print(f"\n[{name}]  verdict: {t['verdict'].upper()}")
        print(f"  WITHOUT  loc={wo['loc']}  median={wo['loc_median']}  "
              f"noncarve_pass={wo['mean_noncarve_pass_rate']:.3f}  carve_all={wo['carve_out_all_passed']}")
        print(f"  WITH     loc={w['loc']}  median={w['loc_median']}  "
              f"noncarve_pass={w['mean_noncarve_pass_rate']:.3f}  carve_all={w['carve_out_all_passed']}")
        print(f"  LOC median reduction (WITH vs WITHOUT): {red*100:+.1f}%  (adopt needs >=15%)")
    print(f"\n=== OVERALL: {report['overall'].upper()} ===\n")


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/ml-phase2")
    rep = main(root)
    _print(rep)
    out = root / "phase2_report.json"
    out.write_text(json.dumps(rep, indent=2, default=str))
    print(f"report written: {out}")
