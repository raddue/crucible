"""AC-10: argparse --help output golden test.

Uses substring assertions on flag names rather than full byte-equality
to survive argparse's formatting drift across Python versions / terminal widths.
"""
import subprocess
import sys


def _help_text(argv: list[str]) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "skills.temper.evals.run_evals", *argv, "--help"],
        capture_output=True, text=True, timeout=30,
    )
    return result.stdout + result.stderr


def test_stage_help_lists_all_flags():
    out = _help_text(["stage"])
    for flag in ["--force", "--source", "--fixture", "--trials-override", "--timeout"]:
        assert flag in out, f"missing {flag} in `stage --help`"
    assert "run_id" in out


def test_score_help_lists_all_flags():
    # F-R4-1: `--per-iter` is asserted by Task 13's `test_score_help_lists_per_iter`
    # (S-1 R5; added in the same atomic commit that declares + wires the flag).
    # It is NOT asserted here because the flag does not exist on the score
    # subparser until Task 13 lands.
    out = _help_text(["score"])
    for flag in ["--write-baseline", "--compare-baseline", "--force-rescore",
                 "--allow-incomplete"]:
        assert flag in out, f"missing {flag} in `score --help`"
    assert "run_id" in out


def test_root_help_lists_legacy_flags():
    out = _help_text([])
    for flag in ["--legacy-fixture", "--legacy-timeout", "--legacy-trials-override",
                 "--mock-reviewer", "--replay"]:
        assert flag in out, f"missing {flag} in root --help"


def test_root_help_lists_subcommands():
    out = _help_text([])
    assert "stage" in out and "score" in out
