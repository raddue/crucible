"""Inquisitor Wiring dimension (#297 full-feature scan).

Hunts cross-component wiring bugs: new entry points / helpers that exist but
are not actually reachable from intended callers.

Per-task tests verify each helper in isolation. These tests verify the seams
between the helper, the CLI surface, and the SKILL.md documented invocations.
"""
from __future__ import annotations

import importlib
import re
from pathlib import Path

from skills.temper.evals import run_evals


# Vector 1: every flag the calibrate SKILL.md tells operators to pass to `score`
# must actually exist on the score subparser. The calibrate skill shells out via
# bash; a typo in either side would silently fail at runtime, not at import.
def test_calibrate_skill_score_flags_exist_on_score_subparser():
    """Calibrate skill Step 3e shell-outs: `score $RUN_ID --per-iter [--write-baseline]
    [--compare-baseline]`. Every flag mentioned must exist on the score subparser.
    """
    skill = Path("skills/temper-eval-calibrate/SKILL.md").read_text()
    # Extract the score invocation line
    m = re.search(r"score[^\n]*--per-iter[^\n]*", skill)
    assert m, "calibrate SKILL.md no longer shells out to `score ... --per-iter`"
    flags_in_skill = set(re.findall(r"--[a-z][a-z-]*", m.group(0)))

    # Pull score subparser's actual flags
    parser = importlib.reload(run_evals)._parse_args.__wrapped__ if hasattr(
        run_evals._parse_args, "__wrapped__"
    ) else None
    # Direct approach: invoke `score --help` machinery via argparse introspection
    import argparse
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")
    # Re-derive via _parse_args by feeding `score --help` style probe is hard;
    # instead, parse a known-good `score` invocation and check available actions.
    # Simpler: stage manifest of available flags from source of truth.
    src = Path("skills/temper/evals/run_evals.py").read_text()
    # find sp_score block
    score_block = re.search(
        r"sp_score = sub\.add_parser.*?(?=\n[a-zA-Z#])", src, re.DOTALL
    )
    assert score_block, "sp_score block not found in run_evals.py"
    declared_flags = set(re.findall(r'add_argument\("(--[a-z-]+)"', score_block.group(0)))

    missing = flags_in_skill - declared_flags
    assert not missing, (
        f"calibrate SKILL.md references {missing} on `score` subparser but those "
        f"flags are not declared. Declared: {sorted(declared_flags)}"
    )


# Vector 2: the collect skill's bash example sanitize_summary shell-out imports
# `sanitize_summary` from `skills.temper.evals._runid`. If the helper is moved
# or renamed, the SKILL.md example silently rots — no test catches it because
# the skill body is a markdown doc, not code. Verify the symbol path.
def test_collect_skill_sanitize_summary_symbol_resolves():
    """SKILL.md Step 7 shell-out: `from skills.temper.evals._runid import sanitize_summary`.
    A future refactor that moves the helper to a different module would silently
    break the shell-out at runtime. Pin the symbol path here.
    """
    skill = Path("skills/temper-eval-collect/SKILL.md").read_text()
    assert "from skills.temper.evals._runid import sanitize_summary" in skill, (
        "collect SKILL.md no longer references the documented import path"
    )
    # Now verify the import actually works
    from skills.temper.evals._runid import sanitize_summary  # noqa
    assert callable(sanitize_summary)


# Vector 3: `_resolve_output_path` exists as a documented helper (S4 R6) and
# is supposed to be the SOLE routing function for both shared and per-iter
# paths. Verify it is actually called from `score()` — not just defined.
# A regression where score() reverts to direct `_LAST_RUN` writes would
# silently break the per-iter routing.
def test_score_uses_resolve_output_path_helper():
    """S4 R6: score() must route via _resolve_output_path. Hard-coding the
    output path inline would re-introduce the import-time vs runtime asymmetry
    the helper was extracted to eliminate.
    """
    import inspect
    src = inspect.getsource(run_evals.score)
    assert "_resolve_output_path(" in src, (
        "score() no longer routes via _resolve_output_path — per-iter writes "
        "may be hard-coded again, breaking test isolation"
    )


# Vector 4: the `stage` subparser must be wired into main()'s dispatch chain.
# `_parse_args` could declare the subparser AND main() could omit the
# `if args.cmd == "stage"` branch — argparse would parse fine, main() would
# silently fall through to legacy_main and fail with a confusing error.
def test_stage_subcommand_main_dispatch_wired():
    """Wiring: `_parse_args` declares stage; `main()` must dispatch to stage()."""
    import inspect
    src = inspect.getsource(run_evals.main)
    assert 'args.cmd == "stage"' in src, "main() does not dispatch the stage subcommand"
    assert "stage(" in src, "main() does not call stage()"


# Vector 5: bootstrap_snapshot.py is a standalone script. Operators invoke it
# as `python -m skills.temper.evals.bootstrap_snapshot`. If `__main__` block
# is dropped or the module path moves, the documented invocation silently
# breaks. Verify the entry point exists.
def test_bootstrap_snapshot_has_main_entrypoint():
    """bootstrap_snapshot.py must be runnable as `python -m ...` per its
    docstring. A missing `if __name__ == "__main__":` block would make the
    documented invocation a no-op."""
    src = Path("skills/temper/evals/bootstrap_snapshot.py").read_text()
    assert 'if __name__ == "__main__":' in src, (
        "bootstrap_snapshot.py missing __main__ block — documented "
        "`python -m skills.temper.evals.bootstrap_snapshot` invocation will silently no-op"
    )
    # Verify the test_legacy_modes failure-message points to the right command
    legacy = Path("skills/temper/evals/test_legacy_modes.py").read_text()
    assert "python -m skills.temper.evals.bootstrap_snapshot" in legacy, (
        "test_legacy_modes failure message references a different bootstrap command"
    )
