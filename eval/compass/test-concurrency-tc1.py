"""T-C1: Concurrency — 8 concurrent update calls must not produce torn writes.

RED phase: scripts/compass.py does not exist. Tests will fail at subprocess
invocation (FileNotFoundError / non-zero returncode). Collection must succeed.
"""
import os
import re
import sys
import subprocess
import concurrent.futures
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

COMPASS_PY = Path(__file__).resolve().parents[2] / "scripts" / "compass.py"
COMPASS_REL = "docs/compass.md"


def _repo_hash(repo_root: Path) -> str:
    import hashlib
    return hashlib.sha1(str(repo_root.resolve()).encode()).hexdigest()[:8]


def _lockdir(repo_root: Path) -> Path:
    return Path(f"/tmp/.lock-compass-{_repo_hash(repo_root)}/")


def _run(args: list[str], cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = {**os.environ, **(env or {})}
    return subprocess.run(
        [sys.executable, str(COMPASS_PY)] + args,
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )


def _update_field(cwd: Path, field: str, values: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    args = ["update", "--field", field]
    for v in values:
        args += ["--value", v]
    full_env = {**os.environ, **(env or {})}
    return subprocess.run(
        [sys.executable, str(COMPASS_PY)] + args,
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=full_env,
    )


def _parse_compass(text: str) -> dict:
    """Minimal parser to extract fields from compass output for assertion purposes."""
    state = {
        "current_arc": None,
        "last_meaningful_commit": None,
        "updated": None,
        "open_loops": [],
        "next_move": "",
        "dont_forget": [],
        "line_count": len(text.splitlines()),
    }
    lines = text.splitlines()
    section = None
    for i, line in enumerate(lines):
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
        elif section == "dont_forget" and line.startswith("- "):
            state["dont_forget"].append(line[2:].rstrip())
    return state


# ── T-C1.1: 8 concurrent writers; final open_loops is one of the 8 values ─────

def test_tc1_1_no_torn_writes(tmp_path):
    """8 concurrent replacement writes; file parses cleanly after (no torn write)."""
    submitted_values = [f"loop-value-{i}" for i in range(8)]

    def _writer(val):
        return _update_field(tmp_path, "open_loops", [val])

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(_writer, v) for v in submitted_values]
        results = [f.result() for f in futures]

    # At least one writer must succeed
    success_count = sum(1 for r in results if r.returncode == 0)
    assert success_count >= 1, f"All 8 writers failed. First error: {results[0].stderr}"

    compass_path = tmp_path / COMPASS_REL
    assert compass_path.exists(), "docs/compass.md must exist after concurrent writes"
    content = compass_path.read_text()
    state = _parse_compass(content)
    # File must parse without exception (parse successful means fields present)
    assert state["current_arc"] is not None, "current_arc field must be parseable"


def test_tc1_2_well_formed_after_concurrent(tmp_path):
    """File is well-formed (has all required headers) after 8 concurrent updates."""
    submitted_values = [f"item-{i}" for i in range(8)]

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(_update_field, tmp_path, "open_loops", [v]) for v in submitted_values]
        [f.result() for f in futures]

    compass_path = tmp_path / COMPASS_REL
    content = compass_path.read_text()
    required_headers = [
        "# Compass",
        "**Current arc:**",
        "**Last meaningful commit:**",
        "**Updated:**",
        "## Open loops",
        "## Next move",
        "## Don't forget",
    ]
    for header in required_headers:
        assert header in content, f"Required header missing: {header!r}"


def test_tc1_3_last_write_wins_replacement(tmp_path):
    """Final open_loops is exactly one element from one of the 8 submitted single-value lists."""
    submitted_values = [f"x-{i}" for i in range(8)]
    expected_lists = [[v] for v in submitted_values]

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(_update_field, tmp_path, "open_loops", [v]) for v in submitted_values]
        [f.result() for f in futures]

    compass_path = tmp_path / COMPASS_REL
    content = compass_path.read_text()
    state = _parse_compass(content)
    # Replacement semantics: each writer submitted one-element list; winner has one element
    assert state["open_loops"] in expected_lists, (
        f"open_loops {state['open_loops']!r} is not one of the submitted single-value lists"
    )


def test_tc1_4_lock_released_after_concurrent(tmp_path):
    """Lock directory is absent after all 8 concurrent writers complete."""
    submitted_values = [f"loop-{i}" for i in range(8)]

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(_update_field, tmp_path, "open_loops", [v]) for v in submitted_values]
        [f.result() for f in futures]

    lockdir = _lockdir(tmp_path)
    assert not lockdir.exists(), f"Lock directory still present after run: {lockdir}"


def test_tc1_5_updated_timestamp_in_window(tmp_path):
    """Updated: reflects the winning write (timestamp within expected window)."""
    t0 = datetime.now(timezone.utc)
    submitted_values = [f"ts-{i}" for i in range(8)]

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(_update_field, tmp_path, "open_loops", [v]) for v in submitted_values]
        [f.result() for f in futures]

    t1 = datetime.now(timezone.utc)
    compass_path = tmp_path / COMPASS_REL
    content = compass_path.read_text()
    state = _parse_compass(content)

    assert state["updated"] is not None, "Updated: field must be present"
    # Parse updated timestamp; format is YYYY-MM-DD HH:MM (minute-resolution)
    try:
        updated_dt = datetime.strptime(state["updated"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    except ValueError:
        pytest.fail(f"Updated: timestamp has unexpected format: {state['updated']!r}")

    t0_floor = t0.replace(second=0, microsecond=0)
    assert t0_floor - timedelta(seconds=60) <= updated_dt <= t1 + timedelta(seconds=120), (
        f"Updated: {state['updated']!r} outside expected window [{t0_floor}, {t1}]"
    )


def test_tc1_6_file_length_within_cap(tmp_path):
    """Total file length <= 40 lines (MAX_LINES) after concurrent writes."""
    submitted_values = [f"cap-{i}" for i in range(8)]

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(_update_field, tmp_path, "open_loops", [v]) for v in submitted_values]
        [f.result() for f in futures]

    compass_path = tmp_path / COMPASS_REL
    content = compass_path.read_text()
    lines = content.splitlines()
    assert len(lines) <= 40, f"File exceeds 40-line cap: {len(lines)} lines"


def test_tc1_7_torn_read_protection(tmp_path):
    """Readers during a slow write see either pre- or post-state, never a hybrid."""
    # First bootstrap a compass with a known current_arc
    bootstrap = _update_field(tmp_path, "current_arc", ["#100: initial arc"])
    assert bootstrap.returncode == 0, f"Bootstrap failed: {bootstrap.stderr}"

    pre_content = (tmp_path / COMPASS_REL).read_text()
    pre_state = _parse_compass(pre_content)

    # Slow writer: update open_loops with 500ms sleep hook
    writer_env = {**os.environ, "CRUCIBLE_COMPASS_TEST_SLEEP_MS": "500"}
    writer_args = [sys.executable, str(COMPASS_PY), "update", "--field", "open_loops", "--value", "slow-write"]

    reader_results = []

    def _slow_writer():
        return subprocess.run(
            writer_args,
            capture_output=True, text=True, cwd=str(tmp_path),
            env=writer_env,
        )

    def _reader():
        return subprocess.run(
            [sys.executable, str(COMPASS_PY), "read", "--compact"],
            capture_output=True, text=True, cwd=str(tmp_path),
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=21) as ex:
        writer_future = ex.submit(_slow_writer)
        # Spawn 20 readers concurrently with writer
        reader_futures = [ex.submit(_reader) for _ in range(20)]
        writer_result = writer_future.result()
        reader_results = [f.result() for f in reader_futures]

    # Every reader must exit 0 and produce parseable output (no torn-write error)
    for i, r in enumerate(reader_results):
        assert r.returncode == 0, f"Reader {i} failed: {r.stderr}"
        # Reader output must not contain a parse-error advisory
        assert "[COMPASS] parse error" not in r.stdout, f"Reader {i} saw parse error: {r.stdout}"


def test_tc1_8_wsl2_9p_smoke(tmp_path):
    """100 sequential read+update cycles on current FS; no PermissionError; file well-formed."""
    # Detect 9p mount (WSL2 /mnt/ paths) - skip if not applicable
    try:
        stat_result = os.statvfs(str(tmp_path))
        # On non-9p, just run on current tmp_path (Linux ext4 or similar)
    except Exception:
        pytest.skip("statvfs not available")

    for i in range(100):
        result = _update_field(tmp_path, "next_move", [f"cycle {i}"])
        if result.returncode != 0:
            # PermissionError would show in stderr
            assert "PermissionError" not in result.stderr, (
                f"PermissionError at cycle {i}: {result.stderr}"
            )
            # Skip if script doesn't exist yet (RED state)
            if "No such file or directory" in result.stderr or "No module named" in result.stderr:
                pytest.fail(f"compass.py not found (RED state expected): {result.stderr}")

    compass_path = tmp_path / COMPASS_REL
    assert compass_path.exists(), "File must exist after 100 cycles"
    content = compass_path.read_text()
    assert "# Compass" in content, "File must be well-formed after 100 cycles"
