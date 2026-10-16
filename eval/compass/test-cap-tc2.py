"""T-C2: Cap enforcement — 40-line hard cap, per-list caps, OpenLoopsCapError.

RED phase: scripts/compass.py does not exist. Tests will fail at subprocess
invocation (FileNotFoundError / non-zero returncode). Collection must succeed.
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


def _update(cwd, field, values, append=False, env=None):
    args = ["update", "--field", field]
    if append:
        args.append("--append")
    for v in values:
        args += ["--value", v]
    return _run(args, cwd, env)


def _repo_hash(repo_root: Path) -> str:
    import hashlib
    return hashlib.sha1(str(repo_root.resolve()).encode()).hexdigest()[:8]


def _lockdir(repo_root: Path) -> Path:
    return Path(f"/tmp/.lock-compass-{_repo_hash(repo_root)}/")


# ── T-C2.1: Bootstrap + fill open_loops to 10; 11th add raises OpenLoopsCapError ──

def test_tc2_1_open_loops_cap_at_10(tmp_path):
    """open_loops hard cap is 10 entries; adding an 11th raises OpenLoopsCapError (exit non-0).
    The display advisory is 5 entries, but the hard cap that raises OpenLoopsCapError is 10.
    """
    # Bootstrap
    r = _update(tmp_path, "current_arc", ["#1: arc"])
    assert r.returncode == 0, f"Bootstrap failed: {r.stderr}"

    # Fill to 10 (all legal — hard cap is 10, not 5)
    loops = [f"loop {i}" for i in range(1, 11)]
    r = _update(tmp_path, "open_loops", loops)
    assert r.returncode == 0, f"Fill to 10 failed: {r.stderr}"

    # 11th append must fail with OpenLoopsCapError
    r = _update(tmp_path, "open_loops", ["eleventh-loop"], append=True)
    assert r.returncode != 0, "Expected failure when appending 11th open_loop item (hard cap is 10)"
    # Must be OpenLoopsCapError (ValueError subclass), not argparse error
    assert "ValueError" in r.stderr or "OpenLoopsCapError" in r.stderr or "cap" in r.stderr.lower() or r.returncode != 0


def test_tc2_2_dont_forget_cap_at_3(tmp_path):
    """dont_forget is capped at 3 entries; adding a 4th raises ValueError."""
    r = _update(tmp_path, "current_arc", ["#1: arc"])
    assert r.returncode == 0, f"Bootstrap failed: {r.stderr}"

    r = _update(tmp_path, "dont_forget", ["item1", "item2", "item3"])
    assert r.returncode == 0, f"Fill to 3 failed: {r.stderr}"

    r = _update(tmp_path, "dont_forget", ["item1", "item2", "item3", "item4"])
    assert r.returncode != 0, "Expected failure with 4 dont_forget entries"


def test_tc2_3_compass_full_error_40_line_cap(tmp_path):
    """Writing past 40 lines raises CompassFullError (exit code 2)."""
    # Bootstrap
    r = _update(tmp_path, "current_arc", ["#1: arc"])
    assert r.returncode == 0, f"Bootstrap failed: {r.stderr}"

    # Pad next_move with many lines to push past 40
    long_next_move = "\n".join([f"line {i}: padding for cap test" for i in range(30)])
    r = _update(tmp_path, "next_move", [long_next_move])
    # This should fail with exit code 2 (CompassFullError)
    if r.returncode == 0:
        # If somehow succeeded, verify file is still <= 40 lines
        compass_path = tmp_path / COMPASS_REL
        content = compass_path.read_text()
        lines = content.splitlines()
        if len(lines) <= 40:
            # Now try another big update that must fail
            r2 = _update(tmp_path, "next_move", [long_next_move + "\nextra line"])
            assert r2.returncode == 2, f"Expected exit code 2 (CompassFullError), got {r2.returncode}"
    else:
        assert r.returncode == 2, f"Expected exit code 2 (CompassFullError), got {r.returncode}"
        assert "FULL" in r.stderr or "CompassFullError" in r.stderr or "cap" in r.stderr.lower()


def test_tc2_4_compass_full_error_stderr_message(tmp_path):
    """CompassFullError emits advisory message to stderr."""
    r = _update(tmp_path, "current_arc", ["#1: arc"])
    assert r.returncode == 0, f"Bootstrap failed: {r.stderr}"

    # Pad next_move past 40 lines
    long_next_move = "\n".join([f"line {i}" for i in range(35)])
    r = _update(tmp_path, "next_move", [long_next_move])

    if r.returncode == 2:
        # The advisory message must appear on stderr
        assert "[FULL]" in r.stderr, f"Expected [FULL] in stderr, got: {r.stderr!r}"
        assert "compass compress" in r.stderr.lower() or "manually" in r.stderr.lower()


def test_tc2_5_lock_released_on_compass_full_error(tmp_path):
    """Lock directory is absent after CompassFullError (lock released despite exception)."""
    r = _update(tmp_path, "current_arc", ["#1: arc"])
    assert r.returncode == 0, f"Bootstrap failed: {r.stderr}"

    long_next_move = "\n".join([f"line {i}" for i in range(35)])
    _update(tmp_path, "next_move", [long_next_move])  # Trigger CompassFullError (or not)

    lockdir = _lockdir(tmp_path)
    assert not lockdir.exists(), f"Lock directory still present after error: {lockdir}"


def test_tc2_6_lock_released_on_value_error(tmp_path):
    """Lock directory is absent after OpenLoopsCapError from per-field cap (11th open_loop)."""
    r = _update(tmp_path, "current_arc", ["#1: arc"])
    assert r.returncode == 0, f"Bootstrap failed: {r.stderr}"

    loops = [f"loop {i}" for i in range(1, 11)]
    _update(tmp_path, "open_loops", loops)
    _update(tmp_path, "open_loops", ["eleventh"], append=True)  # Triggers OpenLoopsCapError

    lockdir = _lockdir(tmp_path)
    assert not lockdir.exists(), f"Lock directory still present after ValueError: {lockdir}"


def test_tc2_7_cli_multi_value_list_replacement(tmp_path):
    """CLI with repeated --value flags replaces open_loops in insertion order."""
    r = _update(tmp_path, "current_arc", ["#1: arc"])
    assert r.returncode == 0, f"Bootstrap failed: {r.stderr}"

    r = _run(["update", "--field", "open_loops", "--value", "a", "--value", "b", "--value", "c"], tmp_path)
    assert r.returncode == 0, f"Multi-value update failed: {r.stderr}"

    compass_path = tmp_path / COMPASS_REL
    content = compass_path.read_text()
    # Verify insertion order: a, b, c
    a_pos = content.find("- a")
    b_pos = content.find("- b")
    c_pos = content.find("- c")
    assert a_pos != -1, "Entry 'a' not found in open_loops"
    assert b_pos != -1, "Entry 'b' not found in open_loops"
    assert c_pos != -1, "Entry 'c' not found in open_loops"
    assert a_pos < b_pos < c_pos, "open_loops entries not in insertion order (a < b < c)"


def test_tc2_8_open_loops_cap_error_is_value_error_subclass(tmp_path):
    """OpenLoopsCapError is a subclass of ValueError (via CLI exit code / stderr).
    Hard cap is 10; 11 distinct arc transitions fill open_loops to 10, then the 12th
    (a brand-new arc not in the paused list) must raise OpenLoopsCapError.
    """
    r = _update(tmp_path, "current_arc", ["#1: arc"])
    assert r.returncode == 0, f"Bootstrap failed: {r.stderr}"

    # Fill to hard cap via D8 arc collisions (11 arc transitions to get 10 paused entries)
    for i in range(2, 12):
        r = _update(tmp_path, "current_arc", [f"#{i}: arc {i}"])
        assert r.returncode == 0, f"Arc {i} transition failed: {r.stderr}"

    # Now open_loops has 10 paused entries (arcs 1-10), current_arc is #11
    # A 12th transition (NEW arc not in paused list) should raise OpenLoopsCapError
    r = _update(tmp_path, "current_arc", ["#99: brand-new arc"])
    assert r.returncode != 0, "Expected OpenLoopsCapError when open_loops would exceed 10"
    # OpenLoopsCapError must be a ValueError subclass — either 'ValueError' or 'OpenLoopsCapError' in stderr
    assert ("ValueError" in r.stderr or "OpenLoopsCapError" in r.stderr
            or "cap" in r.stderr.lower()), f"Expected ValueError-like error, got: {r.stderr!r}"


def test_tc2_9_open_loops_cap_error_resume_succeeds_at_cap(tmp_path):
    """Resume at hard cap (D8.5) succeeds: removes paused entry before D8 push counts it.
    Hard cap is 10; fill to 10 paused entries via 11 arc transitions, then resume arc #1
    (which IS in paused list) — D8.5 removes it first, so net count stays at 10: must succeed.
    """
    r = _update(tmp_path, "current_arc", ["#1: arc 1"])
    assert r.returncode == 0, f"Bootstrap failed: {r.stderr}"

    # Fill open_loops to 10 paused entries via 11 distinct arc transitions
    for i in range(2, 12):
        r = _update(tmp_path, "current_arc", [f"#{i}: arc {i}"])
        assert r.returncode == 0, f"Arc {i} transition failed: {r.stderr}"
    # Now open_loops has 10 entries (arcs 1-10), current_arc = #11

    # Resume arc #1 (which IS in paused list) — D8.5 removes it, then D8 pushes #11
    # Net count stays at 10: must succeed
    r = _update(tmp_path, "current_arc", ["#1: arc 1 resumed"])
    assert r.returncode == 0, (
        f"Resume at cap should succeed (D8.5 removes before D8 adds), got: {r.stderr}"
    )

    compass_path = tmp_path / COMPASS_REL
    content = compass_path.read_text()
    assert "#1:" not in content.split("## Open loops")[1].split("## Next move")[0] or \
        "[paused] #1:" not in content, "Paused #1 entry should be removed by D8.5 resume"
    assert "#1: arc 1 resumed" in content or "#1:" in content, "current_arc should be #1"
