#!/usr/bin/env python3
"""Build the producer dispatch list for the Phase-1b exec collect (NO judges).

Reads the exec/pilot `stage-manifest.json` and emits a self-contained JSON object
the orchestrator fans out: one work-unit per producer (WITH 5 + POOL 5 + MID 1 +
WITHOUT 1 per repo×trial; or 1 neutral-proxy per cell in pilot mode). Each unit
carries the absolute dispatch-file path, the absolute repo-copy path the agent
writes/runs its tests in, and the cell's result_file (where collect writes the
harvested `*-tests.json` per the C4 contract).

Phase 1b has NO judge agents — `_oracle` scores mechanically — so this drops the
Phase-1 judge inputs (dim_paths/mid_path/without_path/items/judge_prompt) entirely.
The harvest *output* shape (the `*-tests.json` the oracle reads) is the C4 collect
contract, defined/tested separately; this builds only the dispatch *args*.
"""
import json
import sys
from pathlib import Path


def build(dispatch_dir) -> dict:
    disp = Path(dispatch_dir).resolve()
    manifest = json.loads((disp / "stage-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("mode") not in ("phase1b-exec", "pilot"):
        raise SystemExit(
            "build_collect_args is exec/pilot-only "
            f"(manifest mode={manifest.get('mode')!r}; "
            "point it at a phase1b-exec or pilot stage-manifest.json)")
    units = []
    for cell in manifest["cells"]:
        for p in cell["producers"]:
            units.append({
                "repo_id": cell["repo_id"],
                "trial": cell["trial"],
                "arm": cell["arm"],
                "agent": p["agent"],
                "dispatch_file": str(disp / p["dispatch_file"]),
                "repo_copy": str(disp / p["repo_copy"]),
                "result_file": str(disp / cell["result_file"]),
            })
    return {
        "dispatch_dir": str(disp),
        "mode": manifest["mode"],
        "arms": manifest["arms"],
        "units": units,
    }


if __name__ == "__main__":
    print(json.dumps(build(sys.argv[1])))
