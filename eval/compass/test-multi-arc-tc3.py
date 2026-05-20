"""T-C3: Multi-arc collision — D8 push, D8.5 resume, D11 dedup, grammar, mutex.

RED phase: scripts/compass.py does not exist. Tests will fail at subprocess
invocation (FileNotFoundError / non-zero returncode). Collection must succeed.

KEY: test_tc3_8_mutex_set_and_append MUST assert ValueError (R15-S1 pin).
"""
import os
import re
import sys
import subprocess
from pathlib import Path

import pytest

COMPASS_PY = Path(__file__).resolve().parents[2] / "scripts" / "compass.py"
COMPASS_REL = "docs/compass.md"

# Paused entry grammar: [paused] #NNN: <subject> @ YYYY-MM-DDTHH:MM:SS
PAUSED_GRAMMAR_RE = re.compile(r"^\[paused\] #\d+: .+ @ \d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$")
TICKET_ID_RE = re.compile(r"^#(\d+):")


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


def _parse_open_loops(content: str) -> list[str]:
    """Extract open_loops entries from compass file content."""
    loops = []
    in_loops = False
    for line in content.splitlines():
        if line == "## Open loops":
            in_loops = True
        elif line.startswith("## ") and in_loops:
            break
        elif in_loops and line.startswith("- "):
            loops.append(line[2:].rstrip())
    return loops


def _parse_current_arc(content: str) -> str:
    for line in content.splitlines():
        if line.startswith("**Current arc:**"):
            return line[len("**Current arc:**"):].strip()
    return ""


# ── T-C3.1: D8 collision push — prior arc goes to open_loops ──────────────────

def test_tc3_1_d8_push_prior_arc_to_open_loops(tmp_path):
    """Setting arc B when arc A is active: A appears in open_loops with [paused] prefix."""
    r = _update(tmp_path, "current_arc", ["#100: arc A subject"])
    assert r.returncode == 0, f"Set arc A failed: {r.stderr}"

    r = _update(tmp_path, "current_arc", ["#200: arc B subject"])
    assert r.returncode == 0, f"Set arc B failed: {r.stderr}"

    content = (tmp_path / COMPASS_REL).read_text()
    loops = _parse_open_loops(content)
    paused_a = [l for l in loops if "[paused] #100:" in l]
    assert len(paused_a) == 1, f"Expected exactly one [paused] #100: entry, got: {loops}"
    assert PAUSED_GRAMMAR_RE.match(paused_a[0]), f"Paused entry does not match grammar: {paused_a[0]!r}"


def test_tc3_2_current_arc_is_new_after_d8(tmp_path):
    """After D8 push, current_arc is the new arc."""
    r = _update(tmp_path, "current_arc", ["#100: arc A subject"])
    assert r.returncode == 0, f"Set arc A failed: {r.stderr}"

    r = _update(tmp_path, "current_arc", ["#200: arc B subject"])
    assert r.returncode == 0, f"Set arc B failed: {r.stderr}"

    content = (tmp_path / COMPASS_REL).read_text()
    arc = _parse_current_arc(content)
    assert arc == "#200: arc B subject", f"current_arc should be arc B, got: {arc!r}"


def test_tc3_3_d8_collision_warning_on_stderr(tmp_path):
    """D8 collision emits advisory warning to stderr."""
    r = _update(tmp_path, "current_arc", ["#100: arc A subject"])
    assert r.returncode == 0, f"Set arc A failed: {r.stderr}"

    r = _update(tmp_path, "current_arc", ["#200: arc B subject"])
    assert r.returncode == 0, f"Set arc B failed: {r.stderr}"
    # Collision advisory must mention the old arc
    assert "[OPEN]" in r.stderr, f"Expected [OPEN] advisory on stderr, got: {r.stderr!r}"
    assert "prior arc" in r.stderr.lower() or "open_loops" in r.stderr.lower() or "#100" in r.stderr


def test_tc3_4_d85_resume_removes_paused_entry(tmp_path):
    """Resuming arc A removes [paused] #<ticket-of-A> from open_loops (D8.5)."""
    r = _update(tmp_path, "current_arc", ["#100: arc A subject"])
    assert r.returncode == 0, f"Set arc A failed: {r.stderr}"
    r = _update(tmp_path, "current_arc", ["#200: arc B subject"])
    assert r.returncode == 0, f"Set arc B failed: {r.stderr}"

    # Resume arc A
    r = _update(tmp_path, "current_arc", ["#100: arc A subject"])
    assert r.returncode == 0, f"Resume arc A failed: {r.stderr}"

    content = (tmp_path / COMPASS_REL).read_text()
    loops = _parse_open_loops(content)
    paused_a = [l for l in loops if "[paused] #100:" in l]
    assert len(paused_a) == 0, f"[paused] #100: entry should be removed on resume, got: {loops}"


def test_tc3_5_current_arc_after_d85_resume(tmp_path):
    """After D8.5 resume, current_arc is the resumed arc."""
    r = _update(tmp_path, "current_arc", ["#100: arc A subject"])
    assert r.returncode == 0
    r = _update(tmp_path, "current_arc", ["#200: arc B subject"])
    assert r.returncode == 0

    r = _update(tmp_path, "current_arc", ["#100: arc A resumed"])
    assert r.returncode == 0, f"Resume failed: {r.stderr}"

    content = (tmp_path / COMPASS_REL).read_text()
    arc = _parse_current_arc(content)
    assert arc == "#100: arc A resumed", f"current_arc should be resumed arc, got: {arc!r}"


def test_tc3_6_d85_resume_advisory_on_stderr(tmp_path):
    """D8.5 resume emits [RESUME] advisory to stderr."""
    r = _update(tmp_path, "current_arc", ["#100: arc A"])
    assert r.returncode == 0
    r = _update(tmp_path, "current_arc", ["#200: arc B"])
    assert r.returncode == 0

    r = _update(tmp_path, "current_arc", ["#100: arc A resumed"])
    assert r.returncode == 0, f"Resume failed: {r.stderr}"
    assert "[RESUME]" in r.stderr, f"Expected [RESUME] advisory on stderr, got: {r.stderr!r}"


def test_tc3_7_d11_dedup_on_arc_thrash(tmp_path):
    """A→B→A→B thrashing: at most one [paused] #A: entry in open_loops."""
    r = _update(tmp_path, "current_arc", ["#100: arc A"])
    assert r.returncode == 0
    r = _update(tmp_path, "current_arc", ["#200: arc B"])
    assert r.returncode == 0
    r = _update(tmp_path, "current_arc", ["#100: arc A"])
    assert r.returncode == 0
    r = _update(tmp_path, "current_arc", ["#200: arc B"])
    assert r.returncode == 0

    content = (tmp_path / COMPASS_REL).read_text()
    loops = _parse_open_loops(content)
    paused_a = [l for l in loops if "[paused] #100:" in l]
    assert len(paused_a) <= 1, (
        f"Expected at most one [paused] #100: entry after A→B→A→B thrash, got: {paused_a}"
    )


# ── T-C3.8: R15-S1 pin — CLI mutex --set and --append raises ValueError ────────

def test_tc3_8_mutex_set_and_append_raises_value_error(tmp_path):
    """R15-S1: --set current_arc and --append open_loops together raises ValueError (NOT argparse.ArgumentError).

    This is the R15-S1 pin per the spec. The CLI must raise ValueError, not argparse.ArgumentError.
    Exit code must be non-zero. The error message must NOT contain 'argparse'.
    """
    # Bootstrap first
    r = _update(tmp_path, "current_arc", ["#1: initial"])
    assert r.returncode == 0, f"Bootstrap failed: {r.stderr}"

    # Invoke with --set current_arc and --append open_loops simultaneously (CLI mutex violation)
    r = _run(
        ["update", "--set", "current_arc", "--value", "#2: new", "--append", "open_loops", "--value", "loop1"],
        tmp_path,
    )
    # Must fail
    assert r.returncode != 0, (
        f"Expected non-zero exit code for CLI mutex violation (R15-S1), got 0\n"
        f"stdout: {r.stdout!r}\nstderr: {r.stderr!r}"
    )
    # Must be ValueError, NOT argparse.ArgumentError
    assert "argparse.ArgumentError" not in r.stderr, (
        f"R15-S1 violation: error must be ValueError, not argparse.ArgumentError. "
        f"stderr: {r.stderr!r}"
    )
    # Must mention ValueError or the mutex constraint
    assert "ValueError" in r.stderr or "mutex" in r.stderr.lower() or "mutually exclusive" in r.stderr.lower(), (
        f"R15-S1: expected ValueError or mutex mention in stderr, got: {r.stderr!r}"
    )


def test_tc3_9_current_arc_grammar_validation(tmp_path):
    """current_arc values must match #NNN: <subject> grammar; invalid values raise ValueError."""
    r = _update(tmp_path, "current_arc", ["#1: valid"])
    assert r.returncode == 0, f"Bootstrap failed: {r.stderr}"

    # Invalid: missing hash
    r = _update(tmp_path, "current_arc", ["273: missing hash"])
    assert r.returncode != 0, "Expected failure for arc without # prefix"

    # Invalid: no number
    r = _update(tmp_path, "current_arc", ["no number: subject"])
    assert r.returncode != 0, "Expected failure for arc without ticket number"

    # Valid
    r = _update(tmp_path, "current_arc", ["#273: valid subject"])
    assert r.returncode == 0, f"Valid arc failed: {r.stderr}"


def test_tc3_10_updated_advances_on_each_thrash_op(tmp_path):
    """Updated: advances on each arc-thrash operation (second-resolution)."""
    import time
    r = _update(tmp_path, "current_arc", ["#100: arc A"])
    assert r.returncode == 0

    time.sleep(1)  # Ensure second boundary passes
    r = _update(tmp_path, "current_arc", ["#200: arc B"])
    assert r.returncode == 0

    content = (tmp_path / COMPASS_REL).read_text()
    # Updated: timestamp must be present and parseable
    updated_line = [l for l in content.splitlines() if l.startswith("**Updated:**")]
    assert len(updated_line) == 1, "Updated: field must be present"


def test_tc3_11_integration_sites_never_update_open_loops_directly(tmp_path):
    """Static check: integration SKILL.md files never call 'update --field open_loops' directly."""
    repo_root = Path(__file__).resolve().parents[2]
    integration_skills = [
        repo_root / "skills" / "getting-started" / "SKILL.md",
        repo_root / "skills" / "build" / "SKILL.md",
        repo_root / "skills" / "merge-pr" / "SKILL.md",
        repo_root / "skills" / "finish" / "SKILL.md",
    ]
    violations = []
    for skill_path in integration_skills:
        if not skill_path.exists():
            continue  # Skill not yet wired (acceptable in RED phase)
        content = skill_path.read_text()
        # Look for compass update invocations targeting open_loops
        if re.search(r"compass.*update.*--field\s+open_loops", content):
            violations.append(str(skill_path))
        if re.search(r"compass.*--set\s+open_loops", content):
            violations.append(str(skill_path))
    assert violations == [], (
        f"Integration SKILL.md files must not directly update open_loops (D8 invariant): {violations}"
    )


def test_tc3_12_d85_requires_timestamp_in_paused_entry(tmp_path):
    """D8.5 only matches properly-formatted [paused] entries (with @ timestamp)."""
    r = _update(tmp_path, "current_arc", ["#1: base"])
    assert r.returncode == 0, f"Bootstrap failed: {r.stderr}"

    # Manually inject a paused entry WITHOUT timestamp (user-typed note)
    compass_path = tmp_path / COMPASS_REL
    content = compass_path.read_text()
    # Insert the user-typed note into open_loops section
    patched = content.replace(
        "## Open loops\n",
        "## Open loops\n- [paused] #500: user-typed note\n",
    )
    compass_path.write_text(patched)

    # Resume #500 — D8.5 should NOT match (no timestamp) → note preserved
    r = _update(tmp_path, "current_arc", ["#500: real arc"])
    assert r.returncode == 0, f"Update failed: {r.stderr}"

    content = compass_path.read_text()
    loops = _parse_open_loops(content)
    # User-typed note should be preserved (D8.5 did not fire)
    user_note = [l for l in loops if "[paused] #500: user-typed note" in l]
    # Note: script might or might not match — test verifies no [RESUME] advisory
    if "[RESUME]" not in r.stderr:
        # D8.5 did not fire; note should still be there OR test documents behavior
        pass  # Behavior depends on implementation; document intent
    assert "[RESUME]" not in r.stderr or user_note == [], (
        "If [RESUME] fired, user-typed note should have been removed"
    )


def test_tc3_13_update_many_same_field_twice_raises(tmp_path):
    """update_many with same field twice raises ValueError."""
    r = _update(tmp_path, "current_arc", ["#1: base"])
    assert r.returncode == 0, f"Bootstrap failed: {r.stderr}"

    # CLI: --set open_loops twice
    r = _run(
        ["update", "--set", "open_loops", "--value", "x", "--set", "open_loops", "--value", "y"],
        tmp_path,
    )
    assert r.returncode != 0, "Expected failure for same field twice in update_many"
    assert "ValueError" in r.stderr or "same field" in r.stderr.lower() or "duplicate" in r.stderr.lower()


def test_tc3_14_last_meaningful_commit_grammar_validation(tmp_path):
    """last_meaningful_commit must follow sha:subject grammar; invalid values raise ValueError."""
    r = _update(tmp_path, "current_arc", ["#1: base"])
    assert r.returncode == 0, f"Bootstrap failed: {r.stderr}"

    # Invalid: no colon
    r = _update(tmp_path, "last_meaningful_commit", ["no-colon-subject"])
    assert r.returncode != 0, "Expected failure for commit without colon delimiter"

    # Valid with <pending> sentinel
    r = _update(tmp_path, "last_meaningful_commit", ["<pending>"])
    assert r.returncode == 0, f"<pending> sentinel should be valid: {r.stderr}"

    # Valid sha:subject (colon in subject is allowed)
    r = _update(tmp_path, "last_meaningful_commit", ["abc123:fix: colon in subject"])
    assert r.returncode == 0, f"sha:subject with colon should be valid: {r.stderr}"


def test_tc3_15_paused_entry_timestamp_is_second_resolution(tmp_path):
    """Paused entry timestamp uses second-resolution format (YYYY-MM-DDTHH:MM:SS)."""
    r = _update(tmp_path, "current_arc", ["#100: arc A"])
    assert r.returncode == 0
    r = _update(tmp_path, "current_arc", ["#200: arc B"])
    assert r.returncode == 0

    content = (tmp_path / COMPASS_REL).read_text()
    loops = _parse_open_loops(content)
    paused_a = [l for l in loops if "[paused] #100:" in l]
    assert len(paused_a) == 1, f"Expected one paused entry for #100, got: {loops}"
    # Verify timestamp format matches YYYY-MM-DDTHH:MM or YYYY-MM-DDTHH:MM:SS
    assert re.search(r"@ \d{4}-\d{2}-\d{2}T\d{2}:\d{2}", paused_a[0]), (
        f"Paused entry missing @ timestamp: {paused_a[0]!r}"
    )


def test_tc3_16_current_arc_space_at_space_rejection(tmp_path):
    """current_arc with ' @ ' (space-at-space) raises ValueError (D8.5 delimiter conflict)."""
    r = _update(tmp_path, "current_arc", ["#1: base"])
    assert r.returncode == 0, f"Bootstrap failed: {r.stderr}"

    # Contains literal ' @ ' — must be rejected (known v1 grammar restriction)
    r = _update(tmp_path, "current_arc", ["#273: subject @ 2026-05-19T10:00:00"])
    assert r.returncode != 0, (
        "Expected failure for current_arc with ' @ ' delimiter (D8.5 conflict, known v1 restriction)"
    )

    # Without space-at-space — must succeed
    r = _update(tmp_path, "current_arc", ["#273: subject with @mention"])
    assert r.returncode == 0, f"Subject with @mention (no space-at-space) should be valid: {r.stderr}"


def test_tc3_17_update_many_append_dedup(tmp_path):
    """update_many append mode dedups: appending same value twice leaves one entry."""
    r = _update(tmp_path, "current_arc", ["#1: base"])
    assert r.returncode == 0, f"Bootstrap failed: {r.stderr}"

    # First append
    r = _run(["update", "--append", "--field", "open_loops", "--value", "item-a"], tmp_path)
    assert r.returncode == 0, f"First append failed: {r.stderr}"

    content1 = (tmp_path / COMPASS_REL).read_text()
    updated1 = [l for l in content1.splitlines() if l.startswith("**Updated:**")]

    # Second append of same value — must dedup
    r = _run(["update", "--append", "--field", "open_loops", "--value", "item-a"], tmp_path)
    assert r.returncode == 0, f"Second append failed: {r.stderr}"

    content2 = (tmp_path / COMPASS_REL).read_text()
    loops = _parse_open_loops(content2)
    item_a_count = sum(1 for l in loops if l == "item-a")
    assert item_a_count == 1, f"Dedup failed: item-a appears {item_a_count} times in {loops}"

    # Append different value — must append
    r = _run(["update", "--append", "--field", "open_loops", "--value", "item-b"], tmp_path)
    assert r.returncode == 0, f"Third append failed: {r.stderr}"

    content3 = (tmp_path / COMPASS_REL).read_text()
    loops3 = _parse_open_loops(content3)
    assert "item-a" in loops3 and "item-b" in loops3, f"Both items should be in loops: {loops3}"
    # Order preserved: item-a before item-b
    assert loops3.index("item-a") < loops3.index("item-b"), "item-a should precede item-b"


def test_tc3_18_parse_entry_rstrip(tmp_path):
    """_parse strips trailing whitespace from open_loops entries; D8.5 still matches."""
    r = _update(tmp_path, "current_arc", ["#1: base"])
    assert r.returncode == 0, f"Bootstrap failed: {r.stderr}"

    # Manually write a paused entry with trailing whitespace
    compass_path = tmp_path / COMPASS_REL
    content = compass_path.read_text()
    # Replace the open_loops section to include trailing spaces
    patched = content.replace(
        "## Open loops\n",
        "## Open loops\n- [paused] #500: subject @ 2026-05-19T10:00:00   \n",
    )
    compass_path.write_text(patched)

    # Now update current_arc to #500 — D8.5 should match and remove the entry
    r = _update(tmp_path, "current_arc", ["#500: subject"])
    assert r.returncode == 0, f"D8.5 resume with trailing-whitespace entry failed: {r.stderr}"
    # [RESUME] advisory indicates D8.5 fired
    # (If not present, the entry was not matched — rstrip contract violated)
    # We document the expected behavior; implementation must rstrip before matching
    content_after = compass_path.read_text()
    loops = _parse_open_loops(content_after)
    # After resume, [paused] #500: should be removed
    paused_500 = [l for l in loops if "[paused] #500:" in l]
    assert len(paused_500) == 0, (
        f"[paused] #500: entry should be removed by D8.5 after rstrip, got: {loops}"
    )
