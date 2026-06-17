#!/usr/bin/env python3
"""Empirical tolerance calibration script for the temper lens evals.

This script computes the swing tolerance used by `run_evals.py`'s drift-delta
gate from k empirical baseline runs (per-fixture / per-lens-column PASS rates),
clamped between an analytic floor (0.447, worst-case binomial-trial spread)
and the design's ceiling (0.7, Harness §7).

Method (Design DEC-6 / #290 Task 2):
    sigma_worst = max over C in {Surgical, DRY, SRP, OCP} of stdev(pass_rate(C))
    t_emp       = 2 * sigma_worst
    tolerance   = round(min(max(t_emp, 0.447), 0.7), 2)

The script is reproducible: re-running with the same input baselines yields
the same calibration.json.

## Running the script

This script consumes the `last_run.json` artifacts produced by k=3 back-to-back
live eval runs of the temper harness. To produce those artifacts, you MUST use
the post-#297 3-step protocol (`feedback_no_claude_p` is binding in this repo;
`claude -p` is NOT used here):

    for i in 1 2 3; do
      RID="R-cal-task2-$(date -u +%Y%m%d)-$i"
      python -m skills.temper.evals.run_evals stage "$RID" --source all
      # Operator step (one invocation per i):
      #   /temper-eval-collect $RID
      python -m skills.temper.evals.run_evals score "$RID"
      cp skills/temper/evals/last_run.json /tmp/cal-calibration-$i.json
    done

Then invoke:

    python scripts/calibrate_tolerance.py \\
        --inputs /tmp/cal-calibration-1.json /tmp/cal-calibration-2.json \\
                 /tmp/cal-calibration-3.json \\
        --out skills/temper/evals/calibration.json

This is the calibration artifact's authoring path. The script alone does not
dispatch reviewer prompts — the operator steps above do, via the disk-mediated
collect skill.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import statistics
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.atomic_write import atomic_write_text  # noqa: E402

_LENS_COLUMNS = ("Surgical", "DRY", "SRP", "OCP")
_ANALYTIC_FLOOR = 0.447
_DESIGN_CEILING = 0.7


def _per_fixture_pass_rate(fixture_result: dict) -> float:
    """Return per-fixture PASS rate (fraction of trials returning PASS).

    Uses per-expectation per-trial verdicts to derive the fixture-level
    per-trial verdict (all expectations PASS => trial PASS).
    """
    expectations = fixture_result.get("expectations", [])
    if not expectations:
        return 0.0
    # All expectations share trial count; pull from first.
    per_trial_lists = [er["per_trial_verdicts"] for er in expectations]
    n_trials = len(per_trial_lists[0]) if per_trial_lists else 0
    if n_trials == 0:
        return 0.0
    passes = 0
    for t in range(n_trials):
        if all(per_trial_lists[i][t] == "PASS" for i in range(len(per_trial_lists))):
            passes += 1
    return passes / n_trials


def _fixture_lens_column(fixture_result: dict) -> str | list[str] | None:
    """Extract lens_column from a scored fixture result.

    last_run.json stores the fixture id only; lens_column lives in evals.json.
    Callers must pass a lookup dict mapping fixture_id -> lens_column.
    """
    return None  # placeholder; resolved by caller via evals.json lookup


def _load_evals_lens_column_map(evals_json_path: Path) -> dict:
    data = json.loads(evals_json_path.read_text(encoding="utf-8"))
    return {f["id"]: f.get("lens_column") for f in data.get("evals", [])}


def calibrate(
    input_paths: list[Path],
    evals_json_path: Path,
) -> dict:
    """Compute the calibration artifact from k baseline last_run.json files."""
    if not input_paths:
        raise ValueError("at least one baseline run is required")

    lens_col_map = _load_evals_lens_column_map(evals_json_path)

    # per_column_rates[column] -> list of per-run per-fixture pass rates
    per_column_rates: dict[str, list[float]] = {c: [] for c in _LENS_COLUMNS}

    for p in input_paths:
        data = json.loads(p.read_text(encoding="utf-8"))
        for fr in data.get("fixtures", []):
            fid = fr.get("id")
            lc = lens_col_map.get(fid)
            rate = _per_fixture_pass_rate(fr)
            if isinstance(lc, str) and lc in per_column_rates:
                per_column_rates[lc].append(rate)
            elif isinstance(lc, list):
                for entry in lc:
                    if entry in per_column_rates:
                        per_column_rates[entry].append(rate)

    sigma_empirical: dict[str, float] = {}
    for col in _LENS_COLUMNS:
        rates = per_column_rates[col]
        if len(rates) >= 2:
            sigma_empirical[col] = float(statistics.pstdev(rates))
        else:
            sigma_empirical[col] = 0.0

    sigma_worst = max(sigma_empirical.values()) if sigma_empirical else 0.0
    t_emp = 2.0 * sigma_worst
    raw = min(max(t_emp, _ANALYTIC_FLOOR), _DESIGN_CEILING)
    tolerance = round(raw, 2)

    floor_binding = t_emp < _ANALYTIC_FLOOR
    ceiling_binding = t_emp > _DESIGN_CEILING

    return {
        "calibrated_at": _dt.datetime.now(_dt.timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
        "baseline_runs": len(input_paths),
        "per_lens_sigma_empirical": {
            c: round(sigma_empirical[c], 4) for c in _LENS_COLUMNS
        },
        "sigma_worst": round(sigma_worst, 4),
        "t_emp": round(t_emp, 4),
        "analytic_floor": _ANALYTIC_FLOOR,
        "floor_binding": floor_binding,
        "tolerance": tolerance,
        "design_ceiling": _DESIGN_CEILING,
        "ceiling_binding": ceiling_binding,
        "method": (
            "min(max(2x empirical sigma over k=3 synth-only baseline runs, "
            "0.447 analytic floor), 0.7 design ceiling)"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    p.add_argument(
        "--inputs",
        nargs="+",
        required=True,
        type=Path,
        help="k baseline last_run.json paths (k>=3 recommended).",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=Path("skills/temper/evals/calibration.json"),
        help="output path for calibration.json",
    )
    p.add_argument(
        "--evals-json",
        type=Path,
        default=Path("skills/temper/evals/evals.json"),
        help="path to evals.json for lens_column lookups",
    )
    args = p.parse_args(argv)

    artifact = calibrate(args.inputs, args.evals_json)
    # #400: torn-write-safe — a half-written calibration.json would silently
    # degrade every downstream tolerance lookup.
    atomic_write_text(str(args.out), json.dumps(artifact, indent=2) + "\n")
    print(f"wrote {args.out} (tolerance={artifact['tolerance']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
