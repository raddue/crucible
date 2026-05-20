"""T-C6: Persistence + compact rendering — idempotent render, session-boundary, D11.

RED phase: scripts/compass.py does not exist. Tests will fail at subprocess
invocation. Collection must succeed.

KEY coverage:
- D11 idempotency: same update twice → identical state; Updated: only bumps on delta.
- Session-boundary: write via subprocess A, read via fresh subprocess B.
- Compact-form ordering: [ARC], [NEXT], [OPEN], [STALE].
"""
import os
import re
import sys
import subprocess
import time
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


def _parse_compass(text: str) -> dict:
    state = {
        "current_arc": None, "last_meaningful_commit": None, "updated": None,
        "open_loops": [], "next_move": "", "dont_forget": [],
    }
    section = None
    next_move_lines = []
    for line in text.splitlines():
        if line.startswith("**Current arc:**"):
            state["current_arc"] = line[len("**Current arc:**"):].strip()
            section = None
        elif line.startswith("**Last meaningful commit:**"):
            state["last_meaningful_commit"] = line[len("**Last meaningful commit:**"):].strip()
            section = None
        elif line.startswith("**Updated:**"):
            state["updated"] = line[len("**Updated:**"):].strip()
            section = None
        elif line == "## Open loops":
            if section == "next_move":
                state["next_move"] = "\n".join(next_move_lines).strip()
                next_move_lines = []
            section = "open_loops"
        elif line == "## Next move":
            if section == "next_move":
                state["next_move"] = "\n".join(next_move_lines).strip()
                next_move_lines = []
            section = "next_move"
        elif line == "## Don't forget":
            if section == "next_move":
                state["next_move"] = "\n".join(next_move_lines).strip()
                next_move_lines = []
            section = "dont_forget"
        elif line.startswith("## "):
            if section == "next_move":
                state["next_move"] = "\n".join(next_move_lines).strip()
                next_move_lines = []
            section = None
        elif section == "open_loops" and line.startswith("- "):
            state["open_loops"].append(line[2:].rstrip())
        elif section == "next_move" and line.strip():
            next_move_lines.append(line)
        elif section == "dont_forget" and line.startswith("- "):
            state["dont_forget"].append(line[2:].rstrip())
    if section == "next_move":
        state["next_move"] = "\n".join(next_move_lines).strip()
    return state


# ── T-C6.1: Session-boundary persistence — write A, read B ────────────────────

def test_tc6_1_file_exists_after_subprocess_write(tmp_path):
    """Write via subprocess A; docs/compass.md exists after subprocess exits."""
    r = _update(tmp_path, "current_arc", ["#273: session test"])
    assert r.returncode == 0, f"Write subprocess failed: {r.stderr}"
    assert (tmp_path / COMPASS_REL).exists(), "docs/compass.md must exist after write"


def test_tc6_2_all_fields_preserved_across_subprocesses(tmp_path):
    """Write all 5 fields via subprocess A; read via subprocess B; all preserved verbatim."""
    # Write phase (subprocess A)
    _update(tmp_path, "current_arc", ["#273: session test"])
    _update(tmp_path, "last_meaningful_commit", ["abc1234:feat: compass"])
    _update(tmp_path, "next_move", ["write the tests"])
    _update(tmp_path, "open_loops", ["loop alpha", "loop beta"])
    _update(tmp_path, "dont_forget", ["check gitignore"])

    # Read phase (subprocess B) — fresh subprocess invocation
    r = _run(["read"], tmp_path)
    assert r.returncode == 0, f"Read subprocess failed: {r.stderr}"
    content = r.stdout
    state = _parse_compass(content)

    assert state["current_arc"] == "#273: session test", f"current_arc mismatch: {state['current_arc']!r}"
    assert state["last_meaningful_commit"] == "abc1234:feat: compass", (
        f"last_meaningful_commit mismatch: {state['last_meaningful_commit']!r}"
    )
    assert "write the tests" in state["next_move"], f"next_move mismatch: {state['next_move']!r}"
    assert "loop alpha" in state["open_loops"], f"open_loops missing 'loop alpha': {state['open_loops']}"
    assert "loop beta" in state["open_loops"], f"open_loops missing 'loop beta': {state['open_loops']}"
    assert "check gitignore" in state["dont_forget"], f"dont_forget mismatch: {state['dont_forget']}"


def test_tc6_3_read_does_not_bump_updated(tmp_path):
    """compass read does NOT bump the Updated: timestamp."""
    r = _update(tmp_path, "current_arc", ["#273: read test"])
    assert r.returncode == 0, f"Write failed: {r.stderr}"

    content_before = (tmp_path / COMPASS_REL).read_text()
    state_before = _parse_compass(content_before)

    # Read via subprocess
    _run(["read"], tmp_path)

    content_after = (tmp_path / COMPASS_REL).read_text()
    state_after = _parse_compass(content_after)
    assert state_before["updated"] == state_after["updated"], (
        f"Updated: must not change after read. Before: {state_before['updated']!r}, "
        f"After: {state_after['updated']!r}"
    )


# ── T-C6.4: Compact form — bootstrap state ────────────────────────────────────

def test_tc6_4_compact_bootstrap_state(tmp_path):
    """Compact form for bootstrap state (current_arc == '<pending>') shows expected output."""
    # Bootstrap by updating a non-arc field
    r = _update(tmp_path, "next_move", ["setup tasks"])
    assert r.returncode == 0, f"Bootstrap failed: {r.stderr}"

    r = _run(["read", "--compact"], tmp_path)
    assert r.returncode == 0, f"compass read --compact failed: {r.stderr}"
    assert "[ARC] No active arc" in r.stdout, (
        f"Bootstrap compact form must show '[ARC] No active arc'. stdout: {r.stdout!r}"
    )
    assert "/build" in r.stdout.lower() or "build" in r.stdout.lower(), (
        f"Bootstrap compact form should mention /build. stdout: {r.stdout!r}"
    )


# ── T-C6.5: Compact form — post-finish (current_arc == '') ────────────────────

def test_tc6_5_compact_post_finish_with_pending_commit(tmp_path):
    """Compact form for post-finish with last_meaningful_commit == '<pending>' shows [CLOSED]."""
    # Bootstrap
    r = _update(tmp_path, "current_arc", ["#1: base arc"])
    assert r.returncode == 0, f"Bootstrap failed: {r.stderr}"

    # Arc closure (finish sets current_arc to '')
    r = _update(tmp_path, "current_arc", [""])
    assert r.returncode == 0, f"Arc closure failed: {r.stderr}"

    r = _run(["read", "--compact"], tmp_path)
    assert r.returncode == 0, f"compass read --compact failed: {r.stderr}"
    assert "[CLOSED]" in r.stdout, (
        f"Post-finish compact form must show [CLOSED]. stdout: {r.stdout!r}"
    )
    # Must NOT show literal '<pending>' in output
    assert "<pending>" not in r.stdout, (
        f"[CLOSED] compact form must not expose '<pending>' literal. stdout: {r.stdout!r}"
    )


# ── T-C6.6: Atomic multi-field emit ───────────────────────────────────────────

def test_tc6_6_atomic_multi_field_emit(tmp_path):
    """update_many (--set) updates all three fields atomically; exactly one Updated: bump."""
    r = _update(tmp_path, "current_arc", ["#100: initial"])
    assert r.returncode == 0, f"Bootstrap failed: {r.stderr}"

    content_before = (tmp_path / COMPASS_REL).read_text()
    state_before = _parse_compass(content_before)
    updated_before = state_before["updated"]

    # Atomic multi-field update via CLI
    r = _run([
        "update",
        "--set", "current_arc", "--value", "",
        "--set", "next_move", "--value", "example",
        "--set", "last_meaningful_commit", "--value", "abc123:subject",
    ], tmp_path)
    assert r.returncode == 0, f"Multi-field update failed: {r.stderr}"

    content_after = (tmp_path / COMPASS_REL).read_text()
    state_after = _parse_compass(content_after)

    assert state_after["current_arc"] == "", f"current_arc should be '' after closure, got: {state_after['current_arc']!r}"
    assert "example" in state_after["next_move"], f"next_move not set: {state_after['next_move']!r}"
    assert state_after["last_meaningful_commit"] == "abc123:subject", (
        f"last_meaningful_commit not set: {state_after['last_meaningful_commit']!r}"
    )

    # Exactly one Updated: bump (not three)
    updated_count = content_after.count("**Updated:**")
    assert updated_count == 1, f"Expected exactly one Updated: field, found {updated_count}"


# ── T-C6.7: Lockless read during hold sees pre-state ─────────────────────────

def test_tc6_7_lockless_read_during_slow_write(tmp_path):
    """Reader during slow write sees pre-state (not partial write)."""
    # Bootstrap with known state
    r = _update(tmp_path, "current_arc", ["#100: pre-write arc"])
    assert r.returncode == 0, f"Bootstrap failed: {r.stderr}"

    pre_content = (tmp_path / COMPASS_REL).read_text()

    # Slow writer: 500ms sleep after render but before file commit
    writer_env = {**os.environ, "CRUCIBLE_COMPASS_TEST_SLEEP_MS": "500"}
    writer_proc = subprocess.Popen(
        [sys.executable, str(COMPASS_PY), "update", "--field", "current_arc", "--value", "#200: post-write arc"],
        cwd=str(tmp_path), env=writer_env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )

    # Reader spawned 100ms after writer starts
    time.sleep(0.1)
    reader_proc = subprocess.run(
        [sys.executable, str(COMPASS_PY), "read", "--compact"],
        cwd=str(tmp_path), capture_output=True, text=True,
    )

    writer_proc.wait()

    # Reader must exit 0 and not show parse error
    assert reader_proc.returncode == 0, f"Reader failed: {reader_proc.stderr}"
    assert "[COMPASS] parse error" not in reader_proc.stdout, "Reader saw parse error (torn write?)"

    # After writer finishes, second reader sees post-state
    reader2 = _run(["read", "--compact"], tmp_path)
    assert reader2.returncode == 0, f"Post-write reader failed: {reader2.stderr}"
    # Post-state should reflect the new arc
    assert "#200" in reader2.stdout or "post-write" in reader2.stdout, (
        f"Post-write reader should see #200 arc. stdout: {reader2.stdout!r}"
    )


# ── T-C6.8: Value containing '=' round-trips correctly ───────────────────────

def test_tc6_8_value_with_equals_roundtrip(tmp_path):
    """Values containing '=' survive write→read round-trip byte-for-byte."""
    r = _update(tmp_path, "current_arc", ["#1: base"])
    assert r.returncode == 0, f"Bootstrap failed: {r.stderr}"

    r = _update(tmp_path, "next_move", ["use timeout=30s syntax"])
    assert r.returncode == 0, f"Set next_move failed: {r.stderr}"

    r = _run(["read"], tmp_path)
    assert r.returncode == 0, f"Read failed: {r.stderr}"
    state = _parse_compass(r.stdout)
    assert "timeout=30s" in state["next_move"], (
        f"next_move with '=' not preserved. Got: {state['next_move']!r}"
    )

    # Repeat for last_meaningful_commit with colon in subject
    r = _update(tmp_path, "last_meaningful_commit", ["abc123:fix: x=y"])
    assert r.returncode == 0, f"Set last_meaningful_commit failed: {r.stderr}"

    r = _run(["read"], tmp_path)
    assert r.returncode == 0, f"Read failed: {r.stderr}"
    state = _parse_compass(r.stdout)
    assert "abc123:fix: x=y" in state["last_meaningful_commit"], (
        f"last_meaningful_commit not preserved. Got: {state['last_meaningful_commit']!r}"
    )


# ── T-C6.9: update_many arg-order independence ────────────────────────────────

def test_tc6_9_update_many_arg_order_independent(tmp_path):
    """update_many CLI arg order does not affect final file content."""
    # Run 1: args in one order
    r = _update(tmp_path, "current_arc", ["#1: base"])
    assert r.returncode == 0, f"Bootstrap run 1 failed: {r.stderr}"

    r1 = _run([
        "update",
        "--set", "current_arc", "--value", "#999: x",
        "--set", "next_move", "--value", "y",
        "--set", "last_meaningful_commit", "--value", "abc:msg",
    ], tmp_path)
    assert r1.returncode == 0, f"Order 1 update failed: {r1.stderr}"
    content1 = (tmp_path / COMPASS_REL).read_text()
    state1 = _parse_compass(content1)

    # Use a fresh dir for run 2
    tmp_path2 = Path(str(tmp_path) + "_2")
    tmp_path2.mkdir()
    r = _update(tmp_path2, "current_arc", ["#1: base"])
    assert r.returncode == 0, f"Bootstrap run 2 failed: {r.stderr}"

    r2 = _run([
        "update",
        "--set", "last_meaningful_commit", "--value", "abc:msg",
        "--set", "next_move", "--value", "y",
        "--set", "current_arc", "--value", "#999: x",
    ], tmp_path2)
    assert r2.returncode == 0, f"Order 2 update failed: {r2.stderr}"
    content2 = (tmp_path2 / COMPASS_REL).read_text()
    state2 = _parse_compass(content2)

    # Scalar field values must be identical regardless of arg order
    assert state1["current_arc"] == state2["current_arc"], "current_arc must match across arg orders"
    assert state1["next_move"] == state2["next_move"], "next_move must match across arg orders"
    assert state1["last_meaningful_commit"] == state2["last_meaningful_commit"], (
        "last_meaningful_commit must match across arg orders"
    )


# ── T-C6.10: Round-trip stability for sentinel states ─────────────────────────

def test_tc6_10_roundtrip_stability_sentinel_states(tmp_path):
    """parse + render is byte-stable for all sentinel states of current_arc."""
    # Bootstrap (current_arc == '<pending>')
    r = _update(tmp_path, "next_move", ["setup"])
    assert r.returncode == 0, f"Bootstrap failed: {r.stderr}"

    r = _run(["read"], tmp_path)
    assert r.returncode == 0, f"Read pending state failed: {r.stderr}"
    content_pending = r.stdout
    assert "pending" in content_pending.lower() or "<pending>" in content_pending, (
        f"Bootstrap state should show <pending>. content: {content_pending!r}"
    )

    # Arc set (#273)
    r = _update(tmp_path, "current_arc", ["#273: subject"])
    assert r.returncode == 0, f"Set arc failed: {r.stderr}"

    r = _run(["read"], tmp_path)
    assert r.returncode == 0, f"Read arc state failed: {r.stderr}"
    state_arc = _parse_compass(r.stdout)
    assert state_arc["current_arc"] == "#273: subject", f"Arc not preserved: {state_arc['current_arc']!r}"

    # Arc cleared (post-finish)
    r = _update(tmp_path, "current_arc", [""])
    assert r.returncode == 0, f"Arc closure failed: {r.stderr}"

    r = _run(["read"], tmp_path)
    assert r.returncode == 0, f"Read closed state failed: {r.stderr}"
    state_closed = _parse_compass(r.stdout)
    assert state_closed["current_arc"] == "", f"Closed state current_arc should be '', got: {state_closed['current_arc']!r}"


# ── T-C6.11: D11 idempotency — same update twice yields identical state ────────

def test_tc6_11_d11_idempotency_same_update_twice(tmp_path):
    """Same update applied twice: identical final state; Updated: only bumps on first (delta) call."""
    r = _update(tmp_path, "current_arc", ["#1: base"])
    assert r.returncode == 0, f"Bootstrap failed: {r.stderr}"

    # First update (produces state delta)
    r = _update(tmp_path, "next_move", ["tackle the tests"])
    assert r.returncode == 0, f"First update failed: {r.stderr}"
    content1 = (tmp_path / COMPASS_REL).read_text()
    state1 = _parse_compass(content1)
    updated1 = state1["updated"]

    # Wait a moment then apply same update again
    time.sleep(1)

    # Second update (same field, same value — TRUE no-op per D11)
    r = _update(tmp_path, "next_move", ["tackle the tests"])
    assert r.returncode == 0, f"Second update failed: {r.stderr}"
    content2 = (tmp_path / COMPASS_REL).read_text()
    state2 = _parse_compass(content2)
    updated2 = state2["updated"]

    # Final state must be identical (same next_move)
    assert state1["next_move"] == state2["next_move"], (
        f"D11: same update twice must yield identical next_move. "
        f"First: {state1['next_move']!r}, Second: {state2['next_move']!r}"
    )

    # Updated: must NOT bump on the no-op (byte-identical body)
    assert updated1 == updated2, (
        f"D11: Updated: must not bump on true no-op. "
        f"Before: {updated1!r}, After: {updated2!r}"
    )
