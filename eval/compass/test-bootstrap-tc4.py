"""T-C4: Bootstrap — missing file created on first update; D8.5 combined path.

RED phase: scripts/compass.py does not exist. Tests will fail at subprocess
invocation. Collection must succeed.

KEY: R15-S2 pin — external set of current_arc to '<pending>' raises ValueError.
"""
import os
import re
import sys
import subprocess
import concurrent.futures
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


def _parse_compass(text: str) -> dict:
    state = {
        "current_arc": None,
        "last_meaningful_commit": None,
        "updated": None,
        "open_loops": [],
        "next_move": "",
        "dont_forget": [],
    }
    section = None
    for line in text.splitlines():
        if line.startswith("**Current arc:**"):
            state["current_arc"] = line[len("**Current arc:**"):].strip()
        elif line.startswith("**Last meaningful commit:**"):
            state["last_meaningful_commit"] = line[len("**Last meaningful commit:**"):].strip()
        elif line.startswith("**Updated:**"):
            state["updated"] = line[len("**Updated:**"):].strip()
        elif line == "## Open loops":
            section = "open_loops"
        elif line == "## Next move":
            section = "next_move"
        elif line == "## Don't forget":
            section = "dont_forget"
        elif line.startswith("## "):
            section = None
        elif section == "open_loops" and line.startswith("- "):
            state["open_loops"].append(line[2:].rstrip())
    return state


# ── T-C4.1: File created on first update ───────────────────────────────────────

def test_tc4_1_file_created_on_first_update(tmp_path):
    """Missing docs/compass.md is created on first compass update call."""
    compass_path = tmp_path / COMPASS_REL
    assert not compass_path.exists(), "Precondition: file must not exist"

    r = _update(tmp_path, "next_move", ["first update"])
    assert r.returncode == 0, f"First update failed: {r.stderr}"
    assert compass_path.exists(), "docs/compass.md must be created on first update"


def test_tc4_2_template_fields_populated(tmp_path):
    """Bootstrap creates file with all required template fields."""
    r = _update(tmp_path, "next_move", ["first update"])
    assert r.returncode == 0, f"First update failed: {r.stderr}"

    compass_path = tmp_path / COMPASS_REL
    content = compass_path.read_text()
    required_sections = ["# Compass", "**Current arc:**", "**Last meaningful commit:**",
                         "**Updated:**", "## Open loops", "## Next move", "## Don't forget"]
    for section in required_sections:
        assert section in content, f"Bootstrap template missing: {section!r}"


def test_tc4_3_last_meaningful_commit_is_pending_sentinel(tmp_path):
    """Bootstrap sets last_meaningful_commit to the literal '<pending>' sentinel."""
    r = _update(tmp_path, "next_move", ["first update"])
    assert r.returncode == 0, f"First update failed: {r.stderr}"

    compass_path = tmp_path / COMPASS_REL
    content = compass_path.read_text()
    state = _parse_compass(content)
    assert state["last_meaningful_commit"] == "<pending>", (
        f"Bootstrap last_meaningful_commit must be '<pending>', got: {state['last_meaningful_commit']!r}"
    )


def test_tc4_4_current_arc_pending_sentinel_and_r15_s2_pin(tmp_path):
    """Bootstrap sets current_arc to '<pending>' sentinel; external set of '<pending>' raises ValueError (R15-S2).

    R15-S2 pin: 'compass update --field current_arc --value <pending>' from external callers
    must raise ValueError. The <pending> sentinel is INTERNAL to bootstrap only.
    """
    # Bootstrap: update next_move only (not current_arc)
    r = _update(tmp_path, "next_move", ["first update"])
    assert r.returncode == 0, f"First update failed: {r.stderr}"

    compass_path = tmp_path / COMPASS_REL
    content = compass_path.read_text()
    state = _parse_compass(content)
    assert state["current_arc"] == "<pending>", (
        f"Bootstrap current_arc must be '<pending>', got: {state['current_arc']!r}"
    )

    # R15-S2: external attempt to set current_arc to '<pending>' must fail
    r = _update(tmp_path, "current_arc", ["<pending>"])
    assert r.returncode != 0, (
        "R15-S2: external 'compass update --field current_arc --value <pending>' "
        "must fail (ValueError). The <pending> sentinel is internal to bootstrap only."
    )
    # Must be ValueError, NOT argparse.ArgumentError
    assert "argparse.ArgumentError" not in r.stderr, (
        "R15-S2: error must be ValueError, not argparse.ArgumentError. "
        f"stderr: {r.stderr!r}"
    )
    assert "ValueError" in r.stderr or "pending" in r.stderr.lower(), (
        f"R15-S2: expected ValueError mentioning '<pending>', got: {r.stderr!r}"
    )


def test_tc4_5_concurrent_bootstrap_4_writers(tmp_path):
    """4 concurrent writers on missing compass: file parses cleanly; one wins; others paused."""
    compass_path = tmp_path / COMPASS_REL
    assert not compass_path.exists(), "Precondition: file must not exist"

    arc_values = [f"#{i}: arc {i}" for i in range(1, 5)]

    def _writer(val):
        return subprocess.run(
            [sys.executable, str(COMPASS_PY), "update", "--field", "current_arc", "--value", val],
            capture_output=True, text=True, cwd=str(tmp_path),
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futures = [ex.submit(_writer, v) for v in arc_values]
        results = [f.result() for f in futures]

    assert compass_path.exists(), "docs/compass.md must exist after concurrent bootstrap"
    content = compass_path.read_text()
    state = _parse_compass(content)

    # File must parse cleanly
    assert state["current_arc"] is not None, "current_arc must be parseable"

    # Winning current_arc must be one of the submitted values
    assert state["current_arc"] in arc_values, (
        f"current_arc {state['current_arc']!r} not in submitted arc values {arc_values}"
    )

    # File must not exceed 40 lines
    lines = content.splitlines()
    assert len(lines) <= 40, f"File exceeds 40-line cap: {len(lines)} lines"

    # No torn template / duplicate headers
    assert content.count("# Compass") == 1, "Duplicate '# Compass' header detected (torn template)"
    assert content.count("**Current arc:**") == 1, "Duplicate 'Current arc' header detected"


def test_tc4_6_bootstrap_combined_with_d85(tmp_path):
    """Bootstrap + D8.5: injecting paused entry before first arc; resume removes it."""
    # First, bootstrap with a non-arc field
    r = _update(tmp_path, "next_move", ["bootstrap"])
    assert r.returncode == 0, f"Bootstrap failed: {r.stderr}"

    # Manually inject a properly-formatted paused entry
    compass_path = tmp_path / COMPASS_REL
    content = compass_path.read_text()
    state = _parse_compass(content)
    assert state["current_arc"] == "<pending>", f"Expected <pending>, got {state['current_arc']!r}"

    # Inject paused entry directly into file
    patched = content.replace(
        "## Open loops\n",
        "## Open loops\n- [paused] #500: prior @ 2026-05-19T10:00:00\n",
    )
    compass_path.write_text(patched)

    # Now resume #500 — D8.5 should fire even from <pending> state
    r = _update(tmp_path, "current_arc", ["#500: resume after bootstrap"])
    assert r.returncode == 0, f"Resume from bootstrap state failed: {r.stderr}"

    content_after = compass_path.read_text()
    state_after = _parse_compass(content_after)

    # current_arc must be set
    assert state_after["current_arc"] == "#500: resume after bootstrap", (
        f"current_arc should be '#500: resume after bootstrap', got: {state_after['current_arc']!r}"
    )

    # [paused] #500: must be removed (D8.5 resume)
    paused_500 = [l for l in state_after["open_loops"] if "[paused] #500:" in l]
    assert len(paused_500) == 0, f"[paused] #500: should be removed by D8.5 on resume: {state_after['open_loops']}"

    # [RESUME] advisory must appear on stderr (D8.5 fired, not D8 step 4 bypass)
    assert "[RESUME]" in r.stderr, (
        f"Expected [RESUME] advisory (D8.5 fired), not [OPEN] (D8 step 4 bypass). "
        f"stderr: {r.stderr!r}"
    )
    # Must NOT say "First arc set" (that's D8 step 4, not D8.5)
    assert "First arc set" not in r.stderr, (
        "D8.5 resume advisory should NOT say 'First arc set'. stderr: {r.stderr!r}"
    )
