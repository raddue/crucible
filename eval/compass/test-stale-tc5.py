"""T-C5: Stale flag — Updated > CRUCIBLE_COMPASS_STALE_DAYS triggers [STALE].

ALL 4 CASES ARE MARKED pytest.mark.skip per the design AC:
  "APFS T-C5 deferred per design AC"

RED phase: scripts/compass.py does not exist. Collection must succeed.
"""
import os
import sys
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

COMPASS_PY = Path(__file__).resolve().parents[2] / "scripts" / "compass.py"
COMPASS_REL = "docs/compass.md"

_SKIP_REASON = "APFS T-C5 deferred per design AC"

COMPASS_BOOTSTRAP_TEMPLATE = """\
# Compass

**Current arc:** #1: stale test arc
**Last meaningful commit:** <pending>
**Updated:** {updated}

## Open loops

## Next move
some next move

## Don't forget
"""


def _run(args: list[str], cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = {**os.environ, **(env or {})}
    return subprocess.run(
        [sys.executable, str(COMPASS_PY)] + args,
        capture_output=True, text=True, cwd=str(cwd), env=full_env,
    )


def _write_stale_compass(tmp_path: Path, days_ago: int) -> None:
    """Write a compass file with Updated: timestamp N days in the past."""
    past = datetime.now(timezone.utc) - timedelta(days=days_ago)
    updated_str = past.strftime("%Y-%m-%d %H:%M")
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / COMPASS_REL).write_text(
        COMPASS_BOOTSTRAP_TEMPLATE.format(updated=updated_str)
    )


# ── T-C5.1: Stale flag fires when Updated > 14 days ───────────────────────────

@pytest.mark.skip(reason=_SKIP_REASON)
def test_tc5_1_stale_flag_fires_at_15_days(tmp_path):
    """[STALE] line appears in compact output when Updated is 15 days in the past."""
    _write_stale_compass(tmp_path, days_ago=15)

    env = {**os.environ}
    env.pop("CRUCIBLE_COMPASS_STALE_DAYS", None)  # Use default (14)
    r = _run(["read", "--compact"], tmp_path, env=env)
    assert r.returncode == 0, f"compass read failed: {r.stderr}"
    assert "[STALE]" in r.stdout, (
        f"Expected [STALE] in compact output for 15-day-old compass (default 14-day threshold). "
        f"stdout: {r.stdout!r}"
    )
    assert "days ago" in r.stdout.lower() or "15" in r.stdout, (
        f"[STALE] line should mention age in days. stdout: {r.stdout!r}"
    )


# ── T-C5.2: Threshold env-var mutation honored per-call ───────────────────────

@pytest.mark.skip(reason=_SKIP_REASON)
def test_tc5_2_stale_threshold_honored_per_call(tmp_path):
    """CRUCIBLE_COMPASS_STALE_DAYS read per-call; mutation between calls takes effect."""
    _write_stale_compass(tmp_path, days_ago=15)

    # Default threshold (14): stale should fire
    env_default = {**os.environ}
    env_default.pop("CRUCIBLE_COMPASS_STALE_DAYS", None)
    r = _run(["read", "--compact"], tmp_path, env=env_default)
    assert "[STALE]" in r.stdout, (
        f"Expected [STALE] with default threshold (14 days, 15-day-old file). stdout: {r.stdout!r}"
    )

    # Override to 20 days: stale should NOT fire (15d < 20d)
    env_20 = {**os.environ, "CRUCIBLE_COMPASS_STALE_DAYS": "20"}
    r = _run(["read", "--compact"], tmp_path, env=env_20)
    assert "[STALE]" not in r.stdout, (
        f"Expected NO [STALE] with 20-day threshold (15-day-old file). stdout: {r.stdout!r}"
    )

    # Override to 7 days: stale should fire again (15d > 7d)
    env_7 = {**os.environ, "CRUCIBLE_COMPASS_STALE_DAYS": "7"}
    r = _run(["read", "--compact"], tmp_path, env=env_7)
    assert "[STALE]" in r.stdout, (
        f"Expected [STALE] with 7-day threshold (15-day-old file). stdout: {r.stdout!r}"
    )


# ── T-C5.3: update() does NOT emit stale advisories ───────────────────────────

@pytest.mark.skip(reason=_SKIP_REASON)
def test_tc5_3_update_does_not_emit_stale(tmp_path):
    """compass update does NOT emit [STALE] advisory (design D6 invariant)."""
    _write_stale_compass(tmp_path, days_ago=15)

    env = {**os.environ}
    env.pop("CRUCIBLE_COMPASS_STALE_DAYS", None)
    r = _run(["update", "--field", "next_move", "--value", "x"], tmp_path, env=env)
    assert r.returncode == 0, f"update failed: {r.stderr}"
    assert "[STALE]" not in r.stdout, (
        f"update() must NOT emit [STALE] to stdout (D6). stdout: {r.stdout!r}"
    )
    assert "[STALE]" not in r.stderr, (
        f"update() must NOT emit [STALE] to stderr (D6). stderr: {r.stderr!r}"
    )

    # Updated: must be bumped to now (delta from next_move change)
    compass_path = tmp_path / COMPASS_REL
    content = compass_path.read_text()
    updated_line = [l for l in content.splitlines() if l.startswith("**Updated:**")]
    assert len(updated_line) == 1, "Updated: field must be present after update"
    # Timestamp should be recent (within last few minutes)
    updated_str = updated_line[0][len("**Updated:**"):].strip()
    try:
        updated_dt = datetime.strptime(updated_str, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        age_minutes = (now - updated_dt).total_seconds() / 60
        assert age_minutes < 2, (
            f"Updated: should be recent after update, but shows {age_minutes:.1f} minutes old"
        )
    except ValueError:
        pytest.fail(f"Updated: has unexpected format: {updated_str!r}")


# ── T-C5.4: Non-stale compass does NOT emit [STALE] ──────────────────────────

@pytest.mark.skip(reason=_SKIP_REASON)
def test_tc5_4_no_stale_flag_when_recent(tmp_path):
    """No [STALE] in compact output when Updated is 5 days ago (below default 14d threshold)."""
    _write_stale_compass(tmp_path, days_ago=5)

    env = {**os.environ}
    env.pop("CRUCIBLE_COMPASS_STALE_DAYS", None)
    r = _run(["read", "--compact"], tmp_path, env=env)
    assert r.returncode == 0, f"compass read failed: {r.stderr}"
    assert "[STALE]" not in r.stdout, (
        f"Expected NO [STALE] for 5-day-old compass (default 14-day threshold). "
        f"stdout: {r.stdout!r}"
    )
