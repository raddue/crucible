"""T-C7: Doctor subcommand — self-diagnostic, schema validation, C-9 invariant.

RED phase: scripts/compass.py does not exist. Tests will fail at subprocess
invocation. Collection must succeed.
"""
import os
import re
import sys
import subprocess
from pathlib import Path

import pytest

COMPASS_PY = Path(__file__).resolve().parents[2] / "scripts" / "compass.py"
COMPASS_REL = "docs/compass.md"


def _run(args: list[str], cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = {**os.environ, **(env or {})}
    return subprocess.run(
        [sys.executable, str(COMPASS_PY)] + args,
        capture_output=True, text=True, cwd=str(cwd), env=full_env,
    )


def _update(cwd, field, values, append=False):
    args = ["update", "--field", field]
    if append:
        args.append("--append")
    for v in values:
        args += ["--value", v]
    return _run(args, cwd)


CANONICAL_COMPASS = """\
# Compass

**Current arc:** #1: doctor test arc
**Last meaningful commit:** <pending>
**Updated:** 2026-05-19 20:00

## Open loops
- [paused] #999: example @ 2026-05-19T20:00:00

## Next move
tackle next task

## Don't forget
- check C-9 invariant
"""


# ── T-C7.1: doctor exits 0 on valid compass ────────────────────────────────────

def test_tc7_1_doctor_exits_0_on_valid_compass(tmp_path):
    """compass doctor exits 0 for a well-formed compass file."""
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / COMPASS_REL).write_text(CANONICAL_COMPASS)

    r = _run(["doctor"], tmp_path)
    assert r.returncode == 0, (
        f"doctor should exit 0 for valid compass. returncode={r.returncode}, "
        f"stdout={r.stdout!r}, stderr={r.stderr!r}"
    )


def test_tc7_2_doctor_reports_paused_ticket_id(tmp_path):
    """doctor stdout reports the [paused] #999: entry's ticket id."""
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / COMPASS_REL).write_text(CANONICAL_COMPASS)

    r = _run(["doctor"], tmp_path)
    assert r.returncode == 0, f"doctor failed: {r.stderr}"
    assert "#999" in r.stdout, (
        f"doctor must report the [paused] #999: entry. stdout: {r.stdout!r}"
    )


def test_tc7_3_doctor_reports_stale_threshold(tmp_path):
    """doctor stdout reports the effective stale threshold (default 14)."""
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / COMPASS_REL).write_text(CANONICAL_COMPASS)

    env = {**os.environ}
    env.pop("CRUCIBLE_COMPASS_STALE_DAYS", None)
    r = _run(["doctor"], tmp_path, env=env)
    assert r.returncode == 0, f"doctor failed: {r.stderr}"
    assert "14" in r.stdout, (
        f"doctor must report stale threshold (default 14). stdout: {r.stdout!r}"
    )


def test_tc7_4_doctor_reports_line_count(tmp_path):
    """doctor stdout reports line-count headroom (current/40)."""
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / COMPASS_REL).write_text(CANONICAL_COMPASS)

    r = _run(["doctor"], tmp_path)
    assert r.returncode == 0, f"doctor failed: {r.stderr}"
    # Should mention line count and cap
    assert "40" in r.stdout or "line" in r.stdout.lower(), (
        f"doctor must report line count/headroom. stdout: {r.stdout!r}"
    )


def test_tc7_5_doctor_exits_2_when_file_exceeds_40_lines(tmp_path):
    """doctor exits 2 when file content exceeds 40 lines (bypassing update cap)."""
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)

    # Write a file that exceeds 40 lines by direct write (bypassing update validation)
    bloated = CANONICAL_COMPASS + "\n".join([f"- extra line {i}" for i in range(50)])
    (tmp_path / COMPASS_REL).write_text(bloated)

    r = _run(["doctor"], tmp_path)
    assert r.returncode == 2, (
        f"doctor should exit 2 when file exceeds 40 lines. returncode={r.returncode}, "
        f"stdout={r.stdout!r}, stderr={r.stderr!r}"
    )


def test_tc7_6_doctor_exits_1_on_out_of_order_headers(tmp_path):
    """doctor exits 1 on parse failure from out-of-order headers."""
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)

    # Place ## Open loops BEFORE **Current arc:** (wrong order)
    bad_compass = """\
# Compass

## Open loops
- some loop

**Current arc:** #1: misplaced
**Last meaningful commit:** <pending>
**Updated:** 2026-05-19 20:00

## Next move
next

## Don't forget
- thing
"""
    (tmp_path / COMPASS_REL).write_text(bad_compass)

    r = _run(["doctor"], tmp_path)
    assert r.returncode == 1, (
        f"doctor should exit 1 for out-of-order headers. returncode={r.returncode}, "
        f"stdout={r.stdout!r}"
    )
    # Should report the offending header name
    assert "Open loops" in r.stdout or "header" in r.stdout.lower() or "order" in r.stdout.lower(), (
        f"doctor should identify the offending header. stdout: {r.stdout!r}"
    )


def test_tc7_7_doctor_exits_1_on_wrong_bullet_character(tmp_path):
    """doctor exits 1 when open_loops uses asterisk (*) instead of dash (-) bullets."""
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)

    # Use * instead of - for open_loops bullets
    bad_compass = """\
# Compass

**Current arc:** #1: test arc
**Last meaningful commit:** <pending>
**Updated:** 2026-05-19 20:00

## Open loops
* wrong bullet character

## Next move
next

## Don't forget
- thing
"""
    (tmp_path / COMPASS_REL).write_text(bad_compass)

    r = _run(["doctor"], tmp_path)
    assert r.returncode == 1, (
        f"doctor should exit 1 for wrong bullet character. returncode={r.returncode}, "
        f"stdout={r.stdout!r}"
    )
    # Should mention the bullet/parse issue
    assert "bullet" in r.stdout.lower() or "parse" in r.stdout.lower() or "*" in r.stdout or "asterisk" in r.stdout.lower(), (
        f"doctor should identify the bullet character issue. stdout: {r.stdout!r}"
    )


# ── T-C7.8: C-9 invariant — docs/compass.md is NOT gitignored ─────────────────

def test_tc7_8_c9_invariant_docs_compass_not_gitignored(tmp_path):
    """C-9: doctor checks that docs/compass.md is NOT gitignored.

    Uses git check-ignore semantic check (catches broad patterns like docs/, *.md, etc.).
    This test runs against the ACTUAL repo root (not tmp_path) since .gitignore is repo-scoped.
    """
    repo_root = Path(__file__).resolve().parents[2]
    compass_path = repo_root / "docs" / "compass.md"

    # Use git check-ignore: exit 0 means IS ignored (bad), exit non-0 means NOT ignored (good)
    r = subprocess.run(
        ["git", "check-ignore", "docs/compass.md"],
        cwd=str(repo_root),
        capture_output=True, text=True,
    )
    # Exit 0 from git check-ignore means the file IS gitignored — that would violate C-9
    assert r.returncode != 0, (
        f"C-9 violation: docs/compass.md appears to be gitignored! "
        f"git check-ignore exit={r.returncode}, stdout={r.stdout!r}. "
        "Remove it from .gitignore — compass.md is repo-scoped persistent state and must be committed."
    )


# ── T-C7.9: doctor subcommand is accessible via CLI ───────────────────────────

def test_tc7_9_doctor_subcommand_reachable(tmp_path):
    """compass doctor subcommand is reachable via CLI (exit code is defined, not missing subcommand)."""
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / COMPASS_REL).write_text(CANONICAL_COMPASS)

    r = _run(["doctor"], tmp_path)
    # Exit code must be 0, 1, or 2 (defined doctor exit codes), NOT argparse usage error (2 for unknown)
    # Actually argparse exits 2 for unknown subcommands too; we check output for "invalid choice"
    assert "invalid choice" not in r.stderr, (
        f"'doctor' is not a recognized subcommand. CLI must support it. stderr: {r.stderr!r}"
    )
    assert "unrecognized" not in r.stderr.lower(), (
        f"'doctor' subcommand not recognized. stderr: {r.stderr!r}"
    )
    # Exit code must be 0, 1, or 2 (not 127 "not found" or similar)
    assert r.returncode in (0, 1, 2), (
        f"doctor must exit 0, 1, or 2. Got: {r.returncode}. stderr: {r.stderr!r}"
    )
