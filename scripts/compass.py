#!/usr/bin/env python3
"""Canonical compass implementation — per-repo arc-state file at docs/compass.md.

Protocol-as-spec lives in skills/shared/compass-protocol.md; on drift, this
script wins. Stdlib only.
"""
import argparse
import datetime as _dt
import errno
import hashlib
import os
import re
import sys
import tempfile
import time
from pathlib import Path

# ── Module-level constants ────────────────────────────────────────────────────
MAX_LINES = 40
MAX_OPEN_LOOPS_HARD = 10        # absolute reject threshold (raises OpenLoopsCapError)
OPEN_LOOPS_DISPLAY_CAP = 5      # visible/per-list cap (raises ValueError if exceeded)
MAX_DONT_FORGET = 3
FIELD_TYPES = {
    'current_arc': 'scalar',
    'last_meaningful_commit': 'scalar',
    'next_move': 'scalar',
    'open_loops': 'list',
    'dont_forget': 'list',
}
MUTEX_PAIRS = {frozenset({'current_arc', 'open_loops'})}
LOCK_INNER_SPIN_S = 2
LOCK_OUTER_CAP_S = 30
STALE_TTL_S = 30
DEFAULT_STALE_DAYS = 14
SPIN_INTERVAL_S = 0.05

PAUSED_LINE_RE = re.compile(
    r"^\[paused\] #(?P<id>\d+): .+ @ \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$"
)
TICKET_ID_RE = re.compile(r"^#(\d+):")
CURRENT_ARC_GRAMMAR_RE = re.compile(r"^#\d+:\s")
COMMIT_GRAMMAR_RE = re.compile(r"^[^:]+:.+")  # sha:subject (must contain colon)


class CompassFullError(Exception):
    pass


class OpenLoopsCapError(ValueError):
    pass


# ── Test-sleep helper (honors CRUCIBLE_COMPASS_TEST_SLEEP_MS, bounded 0..5000) ─
def _test_sleep():
    """CRUCIBLE_COMPASS_TEST_SLEEP_MS hook — bounded sleep at well-defined points.
    Used by tests for orchestrating contention (lock acquire) and slow-write
    (atomic_write) scenarios. No effect when env var unset/zero. Intentional.
    """
    try:
        ms = int(os.environ.get("CRUCIBLE_COMPASS_TEST_SLEEP_MS", "0"))
    except ValueError:
        ms = 0
    ms = max(0, min(5000, ms))
    if ms:
        time.sleep(ms / 1000.0)


# ── Lock ──────────────────────────────────────────────────────────────────────
def _lockdir_for(repo_root):
    h = hashlib.sha1(str(Path(repo_root).resolve()).encode()).hexdigest()[:8]
    return f"/tmp/.lock-compass-{h}"


def _holder_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True


def _try_recover_stale(lockdir):
    """Return True if recovered (lockdir gone)."""
    holder = os.path.join(lockdir, "holder")
    is_stale = False
    try:
        st = os.stat(holder)
        age = time.time() - st.st_mtime
    except FileNotFoundError:
        # No holder under existing lockdir — definitely stale
        is_stale = True
        age = None
    except OSError:
        return False

    if age is not None:
        # Read PID up-front so we can distinguish the suspicious case
        # (alive-PID + old-mtime → possible PID reuse) from the normal
        # crash-recovery case (dead PID, age irrelevant).
        pid = None
        try:
            with open(holder, "r", encoding="utf-8") as f:
                data = f.read().strip()
            pid_str = data.split("@", 1)[0]
            pid = int(pid_str)
        except (OSError, ValueError):
            # Unreadable holder → treat as stale
            is_stale = True

        if not is_stale:
            pid_dead = not _holder_alive(pid) if pid is not None else True
            age_exceeded = age > STALE_TTL_S
            if pid_dead:
                is_stale = True  # crash recovery — fine to evict
            elif age_exceeded:
                # Alive PID but old mtime. We still evict (a legitimate holder
                # shouldn't hold >30s), but flag the suspicious case in case it
                # was a reused PID for an unrelated process.
                is_stale = True
                print(
                    f"[compass] warning: evicting lock held by alive pid {pid} "
                    f"with mtime age {age:.0f}s (>{STALE_TTL_S}s) — possible "
                    f"PID reuse; see protocol doc 'Concurrency / lock protocol'.",
                    file=sys.stderr,
                )

    if not is_stale:
        return False

    try:
        try:
            os.unlink(holder)
        except OSError:
            pass
        os.rmdir(lockdir)
        return True
    except OSError:
        return False


def _acquire_lock(repo_root):
    lockdir = _lockdir_for(repo_root)
    start = time.monotonic()
    while True:
        try:
            os.mkdir(lockdir)
            holder = os.path.join(lockdir, "holder")
            # Write holder under SAME mkdir (C-2)
            try:
                with open(holder, "w", encoding="utf-8") as f:
                    f.write(f"{os.getpid()}@{int(time.time())}")
            except OSError:
                # Holder write failed — release the mkdir and propagate
                try:
                    os.rmdir(lockdir)
                except OSError:
                    pass
                raise
            # Test sleep hook (contention orchestration)
            _test_sleep()
            return lockdir
        except FileExistsError:
            pass
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise

        elapsed = time.monotonic() - start
        if elapsed > LOCK_INNER_SPIN_S:
            # Try stale recovery
            if _try_recover_stale(lockdir):
                continue
        if elapsed > LOCK_OUTER_CAP_S:
            raise TimeoutError(f"compass: failed to acquire lock at {lockdir}")
        time.sleep(SPIN_INTERVAL_S)


def _release_lock(lockdir):
    try:
        os.unlink(os.path.join(lockdir, "holder"))
    except OSError:
        pass
    try:
        os.rmdir(lockdir)
    except OSError:
        pass


# ── Parser / renderer ─────────────────────────────────────────────────────────
BOOTSTRAP_STATE = {
    "current_arc": "<pending>",
    "last_meaningful_commit": "<pending>",
    "updated": "",
    "open_loops": [],
    "next_move": "",
    "dont_forget": [],
}

HEADERS_ORDER = ["**Current arc:**", "**Last meaningful commit:**", "**Updated:**"]
SECTIONS_ORDER = ["## Open loops", "## Next move", "## Don't forget"]


def _parse(text):
    """Strict parser. Returns dict. Raises ValueError on malformed structure."""
    state = {
        "current_arc": None,
        "last_meaningful_commit": None,
        "updated": None,
        "open_loops": [],
        "next_move": "",
        "dont_forget": [],
    }
    lines = text.splitlines()
    if not lines or lines[0].strip() != "# Compass":
        raise ValueError("missing or misplaced '# Compass' header")

    # Track header order
    header_idx = {}
    section_idx = {}
    for i, line in enumerate(lines):
        for h in HEADERS_ORDER:
            if line.startswith(h):
                if h in header_idx:
                    raise ValueError(f"duplicate header: {h}")
                header_idx[h] = i
        for s in SECTIONS_ORDER:
            if line == s:
                if s in section_idx:
                    raise ValueError(f"duplicate section: {s}")
                section_idx[s] = i

    # All required present
    for h in HEADERS_ORDER:
        if h not in header_idx:
            raise ValueError(f"missing header: {h}")
    for s in SECTIONS_ORDER:
        if s not in section_idx:
            raise ValueError(f"missing section: {s}")

    # Enforce ordering: headers come before sections; headers in order; sections in order
    last = -1
    for h in HEADERS_ORDER:
        idx = header_idx[h]
        if idx <= last:
            raise ValueError(f"out-of-order header: {h}")
        last = idx
    for s in SECTIONS_ORDER:
        idx = section_idx[s]
        if idx <= last:
            raise ValueError(f"out-of-order header: {s}")
        last = idx

    # Reject stray content between header block (H-3). Only blank lines and
    # the three header lines themselves are permitted between the first and
    # third header line.
    first_h_idx = header_idx[HEADERS_ORDER[0]]
    last_h_idx = header_idx[HEADERS_ORDER[-1]]
    allowed_header_prefixes = tuple(HEADERS_ORDER)
    for j in range(first_h_idx, last_h_idx + 1):
        ln = lines[j]
        if not ln.strip():
            continue
        if ln.startswith(allowed_header_prefixes):
            continue
        raise ValueError(
            f"malformed compass: stray content between header block at line "
            f"{j + 1}: {ln!r}"
        )

    # Extract scalars
    state["current_arc"] = lines[header_idx["**Current arc:**"]][len("**Current arc:**"):].strip()
    state["last_meaningful_commit"] = lines[header_idx["**Last meaningful commit:**"]][len("**Last meaningful commit:**"):].strip()
    state["updated"] = lines[header_idx["**Updated:**"]][len("**Updated:**"):].strip()

    # Extract list sections + next_move
    def _slice(start_label, end_idx):
        start = section_idx[start_label] + 1
        return lines[start:end_idx]

    ol_end = section_idx["## Next move"]
    nm_end = section_idx["## Don't forget"]
    df_end = len(lines)

    for line in _slice("## Open loops", ol_end):
        s = line.rstrip()
        if not s:
            continue
        if s.startswith("- "):
            state["open_loops"].append(s[2:].rstrip())
        elif s.startswith("* ") or (s.startswith(("*", "+")) and len(s) > 1 and s[1] == " "):
            raise ValueError(f"wrong bullet character (use '-'): {s!r}")
        else:
            raise ValueError(f"unexpected line in open_loops: {s!r}")

    nm_lines = []
    for line in _slice("## Next move", nm_end):
        nm_lines.append(line)
    # Strip leading/trailing empty lines from next_move
    while nm_lines and not nm_lines[0].strip():
        nm_lines.pop(0)
    while nm_lines and not nm_lines[-1].strip():
        nm_lines.pop()
    state["next_move"] = "\n".join(nm_lines)

    for line in _slice("## Don't forget", df_end):
        s = line.rstrip()
        if not s:
            continue
        if s.startswith("- "):
            state["dont_forget"].append(s[2:].rstrip())
        elif s.startswith("* "):
            raise ValueError(f"wrong bullet character in don't forget: {s!r}")
        else:
            raise ValueError(f"unexpected line in dont_forget: {s!r}")

    return state


def _render(state):
    """Idempotent render. Insertion-order lists. Trailing-space empty-field
    convention is NOT used — we use clean trailing-empty (no trailing whitespace).
    """
    out = []
    out.append("# Compass")
    out.append("")
    out.append(f"**Current arc:** {state['current_arc']}")
    out.append(f"**Last meaningful commit:** {state['last_meaningful_commit']}")
    out.append(f"**Updated:** {state['updated']}")
    out.append("")
    out.append("## Open loops")
    for entry in state["open_loops"]:
        out.append(f"- {entry}")
    out.append("")
    out.append("## Next move")
    if state["next_move"]:
        out.append(state["next_move"])
    out.append("")
    out.append("## Don't forget")
    for entry in state["dont_forget"]:
        out.append(f"- {entry}")
    return "\n".join(out) + "\n"


def _validate(text):
    """Raises CompassFullError on >40 lines, OpenLoopsCapError on >10 open_loops,
    ValueError on per-list cap violations.
    """
    lines = text.splitlines()
    # Strip a single trailing empty line for cap measurement (renderer adds final \n)
    if len(lines) > MAX_LINES:
        raise CompassFullError(
            "[FULL] Compass at cap. Run 'compass compress' or edit "
            "docs/compass.md manually before retrying."
        )
    state = _parse(text)
    if len(state["open_loops"]) > MAX_OPEN_LOOPS_HARD:
        raise OpenLoopsCapError(
            f"open_loops hard cap exceeded ({len(state['open_loops'])} > {MAX_OPEN_LOOPS_HARD})"
        )
    if len(state["dont_forget"]) > MAX_DONT_FORGET:
        raise ValueError(
            f"dont_forget exceeds cap of {MAX_DONT_FORGET} entries "
            f"(got {len(state['dont_forget'])})"
        )


def _atomic_write(path, text):
    """Atomic write via tempfile in same dir + os.replace (same-FS guarantee)."""
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    # Test sleep hook between render and tempfile creation (T-C6 #7 slow-write)
    _test_sleep()
    fd, tmp = tempfile.mkstemp(prefix=".compass.", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _now_minute_str():
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M")


def _now_second_str():
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _ticket_id_of(value):
    m = TICKET_ID_RE.match(value)
    if m:
        return m.group(1)
    return None


# ── Patch application ─────────────────────────────────────────────────────────
def _validate_value(field, value):
    """Per-field value validation (grammar). Raises ValueError on failure."""
    # Reject control chars that corrupt the line-based markdown schema.
    # `next_move` is a paragraph field and legitimately contains '\n' (the
    # renderer joins/splits on newline), so newlines are permitted there;
    # CR and TAB remain rejected everywhere.
    if isinstance(value, str):
        bad = ['\r', '\t']
        if field != "next_move":
            bad.append('\n')
        if any(c in value for c in bad):
            raise ValueError(
                f"{field} cannot contain control chars (newline/CR/tab); "
                f"got {value!r}"
            )
    if field == "current_arc":
        if value in ("", "<pending>"):
            # empty is arc-closure; <pending> is rejected at higher level (R15-S2)
            return
        if " @ " in value:
            raise ValueError(
                f"current_arc cannot contain literal ' @ ' (space-at-space) — "
                f"this is a known v1 grammar restriction (D8.5 delimiter conflict). "
                f"Got: {value!r}"
            )
        if not CURRENT_ARC_GRAMMAR_RE.match(value):
            raise ValueError(
                f"current_arc must match '#NNN: <subject>' grammar, got: {value!r}"
            )
    elif field == "last_meaningful_commit":
        if value == "<pending>":
            return
        if ":" not in value:
            raise ValueError(
                f"last_meaningful_commit must follow 'sha:subject' grammar, got: {value!r}"
            )


def _apply_patch(state, field, value, append, advisories):
    """Apply a single patch. Mutates state in place. Appends stderr advisories.
    Returns True if state changed (excluding Updated:)."""
    if field not in FIELD_TYPES:
        raise ValueError(f"unknown field: {field!r}")

    ftype = FIELD_TYPES[field]
    if append and ftype != "list":
        raise ValueError(f"--append only valid for list fields, not {field!r}")

    if ftype == "scalar":
        if not isinstance(value, str):
            raise ValueError(f"scalar field {field!r} requires string value")
        _validate_value(field, value)
        if field == "current_arc":
            return _apply_current_arc(state, value, advisories)
        old = state[field]
        if old == value:
            return False
        state[field] = value
        return True
    else:
        # list field
        if append:
            # value is single scalar
            if not isinstance(value, str):
                raise ValueError(f"--append requires single scalar value")
            _validate_value(field, value)
            if value in state[field]:
                return False  # dedup
            state[field].append(value)
            return True
        else:
            # replacement
            if isinstance(value, str):
                new_list = [value]
            else:
                new_list = list(value)
            for entry in new_list:
                if not isinstance(entry, str):
                    raise ValueError(f"list field {field!r} entries must be strings")
                _validate_value(field, entry)
            if state[field] == new_list:
                return False
            state[field] = new_list
            return True


def _apply_current_arc(state, new_value, advisories):
    """D8/D8.5/D11 carve-out ordering. Returns True if any state changed."""
    changed = False
    did_resume = False  # D8.5 actually removed a paused entry
    existing = state["current_arc"]

    # Step 1: D8.5 first — resume removal
    new_ticket = _ticket_id_of(new_value) if new_value else None
    if new_ticket:
        prefix = f"[paused] #{new_ticket}:"
        removed = []
        kept = []
        for entry in state["open_loops"]:
            stripped = entry.rstrip()
            if stripped.startswith(prefix) and PAUSED_LINE_RE.match(stripped):
                removed.append(stripped)
            else:
                kept.append(entry)
        if removed:
            state["open_loops"] = kept
            changed = True
            did_resume = True
            advisories.append(f"[RESUME] Resuming paused arc {new_value}")

    # Step 2: no-op short-circuit
    if new_value == existing:
        return changed

    # Step 3: empty-string carve-out (arc-closure)
    if new_value == "":
        state["current_arc"] = ""
        return True

    # Step 4: <pending> bootstrap
    if existing == "<pending>":
        state["current_arc"] = new_value
        if not did_resume:
            advisories.append(f"[OPEN] First arc set: {new_value}")
        return True

    # Step 5: post-closure cleared
    if existing == "":
        state["current_arc"] = new_value
        if not did_resume:
            advisories.append(f"[OPEN] New arc set: {new_value}")
        return True

    # Step 6: collision push
    # Push prior arc onto open_loops with [paused] prefix + timestamp
    old_ticket = _ticket_id_of(existing)
    ts = _now_second_str()
    paused_entry = f"[paused] {existing} @ {ts}"
    # Dedup: if [paused] #<old-id>: already exists, update in place
    if old_ticket:
        dedup_prefix = f"[paused] #{old_ticket}:"
        replaced = False
        new_loops = []
        for entry in state["open_loops"]:
            stripped = entry.rstrip()
            if stripped.startswith(dedup_prefix) and PAUSED_LINE_RE.match(stripped):
                new_loops.append(paused_entry)
                replaced = True
            else:
                new_loops.append(entry)
        if not replaced:
            new_loops.append(paused_entry)
        state["open_loops"] = new_loops
    else:
        state["open_loops"].append(paused_entry)

    state["current_arc"] = new_value
    advisories.append(
        f"[OPEN] Started new arc {new_value} with prior arc {existing} "
        f"still active — prior arc moved to open_loops"
    )
    return True


# ── Read / Update entry points ────────────────────────────────────────────────
def _read_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None


def read(path="docs/compass.md", compact=False):
    """Return file contents (full or compact form). Empty if missing."""
    if not os.path.exists(path):
        return ""
    text = _read_file(path)
    if text is None:
        return ""
    if not compact:
        return text
    try:
        state = _parse(text)
    except ValueError:
        return "[COMPASS] parse error — run 'compass doctor' to inspect\n"
    return _render_compact(state)


def _render_compact(state):
    lines = []
    arc = state["current_arc"]
    if arc == "<pending>":
        lines.append("[ARC] No active arc — run any /build to set current_arc")
    elif arc == "":
        lmc = state["last_meaningful_commit"]
        if lmc == "<pending>" or not lmc:
            lines.append("[CLOSED] No recorded commit")
        else:
            tid = _ticket_id_of(lmc)
            # lmc grammar is sha:subject — we want a friendly ref, not <pending>
            ref = tid if tid else lmc.split(":", 1)[0]
            lines.append(f"[CLOSED] Last arc closed: {ref}")
    else:
        lines.append(f"[ARC] {arc}")

    if state["next_move"]:
        # Single line: first line of next_move
        first = state["next_move"].splitlines()[0]
        lines.append(f"[NEXT] {first}")

    if state["open_loops"]:
        top = state["open_loops"][0]
        lines.append(f"[OPEN] {len(state['open_loops'])} loops (top: {top})")

    # Stale check
    try:
        days = int(os.environ.get("CRUCIBLE_COMPASS_STALE_DAYS", str(DEFAULT_STALE_DAYS)))
    except ValueError:
        days = DEFAULT_STALE_DAYS
    if state["updated"]:
        try:
            upd = _dt.datetime.strptime(state["updated"], "%Y-%m-%d %H:%M").replace(
                tzinfo=_dt.timezone.utc
            )
            age_days = (_dt.datetime.now(_dt.timezone.utc) - upd).days
            if age_days > days:
                lines.append(f"[STALE] last updated {age_days} days ago")
        except ValueError:
            pass

    return "\n".join(lines) + "\n"


def _bootstrap_state():
    return {
        "current_arc": "<pending>",
        "last_meaningful_commit": "<pending>",
        "updated": _now_minute_str(),
        "open_loops": [],
        "next_move": "",
        "dont_forget": [],
    }


def update(field, value, append=False, path="docs/compass.md"):
    """Single-field update entry point."""
    return update_many([(field, value, append)], path=path)


def update_many(patches, path="docs/compass.md"):
    """Atomic multi-field update under one lock."""
    # R15-S2: <pending> external set rejection (BEFORE everything else)
    for f, v, _a in patches:
        if f == "current_arc" and v == "<pending>":
            raise ValueError(
                "<pending> is an internal bootstrap sentinel and cannot "
                "be set externally"
            )

    # Same-field-twice rejection (T-C3 #13)
    seen = set()
    for f, _v, _a in patches:
        if f in seen:
            raise ValueError(f"update_many: duplicate field {f!r}")
        seen.add(f)

    # Mutex enforcement (current_arc + open_loops together)
    fields_set = {f for f, _v, _a in patches}
    for pair in MUTEX_PAIRS:
        if pair.issubset(fields_set):
            raise ValueError(
                f"update_many: mutex violation — fields {sorted(pair)!r} "
                "cannot be set in the same atomic update"
            )

    repo_root = os.path.dirname(os.path.abspath(path)) or "."
    # Use the parent of docs/ (the cwd typically) as repo_root for lock hashing
    # to keep tests' _lockdir computation consistent.
    if os.path.basename(repo_root) == "docs":
        repo_root = os.path.dirname(repo_root) or "."

    lockdir = _acquire_lock(repo_root)
    try:
        text = _read_file(path)
        if text is None:
            state = _bootstrap_state()
        else:
            try:
                state = _parse(text)
            except ValueError as e:
                raise ValueError(f"parse error on read: {e}")

        pre_state = {k: (list(v) if isinstance(v, list) else v) for k, v in state.items()}
        pre_state.pop("updated", None)

        advisories = []
        any_changed = False
        for f, v, a in patches:
            if _apply_patch(state, f, v, a, advisories):
                any_changed = True

        # D11: bump Updated: only if any field (excluding Updated:) changed
        post_state = {k: v for k, v in state.items() if k != "updated"}
        if any_changed or pre_state != post_state:
            state["updated"] = _now_minute_str()
        # If file didn't exist, ensure updated is set
        if text is None and not state["updated"]:
            state["updated"] = _now_minute_str()

        rendered = _render(state)
        # Validate (once, on final body)
        _validate(rendered)

        _atomic_write(path, rendered)

        # Emit advisories
        for adv in advisories:
            print(adv, file=sys.stderr)
    finally:
        _release_lock(lockdir)


# ── Doctor ───────────────────────────────────────────────────────────────────
def _cmd_doctor(path="docs/compass.md"):
    """Self-diagnostic subcommand. Returns exit code: 0=healthy, 1=error, 2=cap."""
    issues = []
    warnings = []
    info = []

    # Stale threshold (report regardless of file state)
    try:
        stale_days = int(os.environ.get("CRUCIBLE_COMPASS_STALE_DAYS", str(DEFAULT_STALE_DAYS)))
    except ValueError:
        stale_days = DEFAULT_STALE_DAYS
    info.append(f"stale-threshold: {stale_days} days")

    # File existence
    text = _read_file(path)
    if text is None:
        info.append(f"file: {path} — NOT FOUND (bootstrap state will be used on next update)")
        # Still report line count as 0
        info.append("lines: 0/40")
        # C-9 invariant: check git check-ignore
        _doctor_c9(path, issues)
        # Lock state
        _doctor_lock(path, info)
        _print_doctor(info, warnings, issues)
        return 0 if not issues else 1

    # Line count check
    lines = text.splitlines()
    line_count = len(lines)
    if line_count > MAX_LINES:
        issues.append(f"line-cap exceeded: {line_count}/40 lines (cap is {MAX_LINES})")
    elif line_count >= MAX_LINES - 5:
        warnings.append(f"lines: {line_count}/40 (approaching cap)")
    else:
        info.append(f"lines: {line_count}/40")

    # Schema validation (parse)
    state = None
    try:
        state = _parse(text)
        info.append("schema: OK")
    except ValueError as e:
        msg = str(e)
        # Surface offending excerpt if recognizable
        issues.append(f"parse error: {msg}")
        # Identify bullet/header context for better output
        if "bullet" in msg or "wrong bullet" in msg or "* " in msg:
            issues.append("bullet: use '-' for list items, not '*' or '+'")
        elif "out-of-order" in msg or "order" in msg:
            # Extract section name from message for clarity
            issues.append(f"order: sections/headers must follow canonical order")
        _print_doctor(info, warnings, issues)
        return 1 if line_count <= MAX_LINES else 2

    # Stale status (only if parse succeeded)
    if state and state.get("updated"):
        try:
            upd = _dt.datetime.strptime(state["updated"], "%Y-%m-%d %H:%M").replace(
                tzinfo=_dt.timezone.utc
            )
            age_days = (_dt.datetime.now(_dt.timezone.utc) - upd).days
            if age_days > stale_days:
                warnings.append(f"stale: last updated {age_days} days ago (threshold: {stale_days})")
            else:
                info.append(f"updated: {state['updated']} ({age_days} days ago)")
        except ValueError:
            warnings.append(f"updated: unparseable timestamp {state['updated']!r}")

    # Report open loops (paused ticket ids)
    if state:
        paused = [e for e in state.get("open_loops", []) if e.startswith("[paused]")]
        if paused:
            for entry in paused:
                # Extract ticket id for reporting
                m = re.search(r"#(\d+)", entry)
                tid = f"#{m.group(1)}" if m else "?"
                info.append(f"open-loop (paused): {tid} — {entry}")
        else:
            info.append(f"open-loops: {len(state.get('open_loops', []))} (none paused)")

    # C-9 invariant: docs/compass.md must not be gitignored
    _doctor_c9(path, issues)

    # Lock state
    _doctor_lock(path, info)

    _print_doctor(info, warnings, issues)

    if line_count > MAX_LINES:
        return 2
    return 0 if not issues else 1


def _doctor_c9(path, issues):
    """Check C-9: docs/compass.md must NOT be gitignored."""
    import subprocess as _sp
    try:
        r = _sp.run(
            ["git", "check-ignore", path],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            issues.append(
                f"C-9 violation: {path} is gitignored — "
                "compass.md is repo-scoped persistent state and must be committed"
            )
        # Non-zero = not ignored = good (no issue added)
    except FileNotFoundError:
        # git not available — skip check
        pass


def _doctor_lock(path, info):
    """Report lock state."""
    repo_root = os.path.dirname(os.path.abspath(path)) or "."
    if os.path.basename(repo_root) == "docs":
        repo_root = os.path.dirname(repo_root) or "."
    lockdir = _lockdir_for(repo_root)
    if os.path.isdir(lockdir):
        holder = os.path.join(lockdir, "holder")
        try:
            st = os.stat(holder)
            age = time.time() - st.st_mtime
            info.append(f"lock: present (age {age:.0f}s) — may be stale if holder is dead")
        except OSError:
            info.append(f"lock: present (no holder file) — stale")
    else:
        info.append("lock: clear")


def _print_doctor(info, warnings, issues):
    """Print doctor report to stdout."""
    print("=== compass doctor ===")
    for line in info:
        print(f"  [ok] {line}")
    for line in warnings:
        print(f"  [warn] {line}")
    for line in issues:
        print(f"  [FAIL] {line}")
    if issues:
        print(f"  --- {len(issues)} issue(s) found ---")
    else:
        print("  --- healthy ---")


# ── CLI ───────────────────────────────────────────────────────────────────────
def _cli_preparse(argv):
    """Parse CLI argv for 'update' subcommand. Returns (mode, patches, path).
    mode is 'single' or 'multi'.

    Raises ValueError on mutex / mode-conflict / scalar-multi-value / same-field errors.
    """
    # Extract --path (consumed first; not in patch list)
    path = "docs/compass.md"
    new_argv = []
    i = 0
    while i < len(argv):
        if argv[i] == "--path" and i + 1 < len(argv):
            path = argv[i + 1]
            i += 2
        else:
            new_argv.append(argv[i])
            i += 1
    argv = new_argv

    has_set = "--set" in argv
    has_append = "--append" in argv
    has_field = "--field" in argv

    # R15-S1: --set vs --append mutex
    if has_set and has_append:
        raise ValueError(
            "--set and --append are mutually exclusive (mutex violation)"
        )

    if has_set:
        return _parse_multi(argv, path)
    else:
        return _parse_single(argv, path)


def _parse_single(argv, path):
    """Legacy single-field mode: --field X --value Y [--value Y2 ...] [--append]"""
    field = None
    values = []
    append = False
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--field":
            if field is not None:
                raise ValueError("--field specified more than once")
            if i + 1 >= len(argv):
                raise ValueError("--field requires a value")
            field = argv[i + 1]
            i += 2
        elif tok == "--value":
            if i + 1 >= len(argv):
                raise ValueError("--value requires a value")
            # Inside-value state machine: unconditionally consume next token
            values.append(argv[i + 1])
            i += 2
        elif tok == "--append":
            append = True
            i += 1
        else:
            raise ValueError(f"unexpected argument: {tok!r}")

    if field is None:
        raise ValueError("--field required")
    if not values:
        raise ValueError("--value required")

    ftype = FIELD_TYPES.get(field)
    if ftype == "scalar" and len(values) > 1:
        raise ValueError(f"scalar field {field!r} accepts at most one --value")

    if ftype == "list" and not append:
        value = values
    elif ftype == "list" and append:
        if len(values) > 1:
            raise ValueError("--append with --value: pass exactly one value")
        value = values[0]
    else:
        value = values[0]

    return "single", [(field, value, append)], path


def _parse_multi(argv, path):
    """Multi-field --set mode: --set field --value V [--set field2 --value V2 ...]"""
    patches = []
    current_field = None
    current_values = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--set":
            # Flush prior
            if current_field is not None:
                patches.append(_finalize_multi_patch(current_field, current_values))
                current_field = None
                current_values = []
            if i + 1 >= len(argv):
                raise ValueError("--set requires a field name")
            current_field = argv[i + 1]
            i += 2
        elif tok == "--value":
            if i + 1 >= len(argv):
                raise ValueError("--value requires a value")
            current_values.append(argv[i + 1])
            i += 2
        elif tok == "--field":
            raise ValueError("--field cannot be combined with --set")
        else:
            raise ValueError(f"unexpected argument: {tok!r}")

    if current_field is not None:
        patches.append(_finalize_multi_patch(current_field, current_values))

    if not patches:
        raise ValueError("at least one --set required")

    return "multi", patches, path


def _finalize_multi_patch(field, values):
    if not values:
        raise ValueError(f"--set {field}: no --value provided")
    ftype = FIELD_TYPES.get(field)
    if ftype == "scalar":
        if len(values) > 1:
            raise ValueError(f"scalar field {field!r} accepts at most one --value")
        return (field, values[0], False)
    elif ftype == "list":
        return (field, list(values), False)
    else:
        # unknown field — let _apply_patch raise
        return (field, values[0] if len(values) == 1 else list(values), False)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: compass.py {read,update,compress,doctor} [args]", file=sys.stderr)
        return 2

    sub = argv[0]
    rest = argv[1:]

    if sub == "read":
        compact = "--compact" in rest
        path = "docs/compass.md"
        # consume --path
        try:
            idx = rest.index("--path")
            path = rest[idx + 1]
        except (ValueError, IndexError):
            pass
        out = read(path=path, compact=compact)
        if out:
            sys.stdout.write(out)
        return 0

    if sub == "update":
        try:
            mode, patches, path = _cli_preparse(rest)
            update_many(patches, path=path)
        except CompassFullError as e:
            print(str(e), file=sys.stderr)
            return 2
        except OpenLoopsCapError as e:
            print(f"OpenLoopsCapError: {e}", file=sys.stderr)
            return 2
        except ValueError as e:
            print(f"ValueError: {e}", file=sys.stderr)
            return 2
        return 0

    if sub == "update-many":
        # `--field X --value Y [...]` where each `--field` introduces a new
        # patch; subsequent `--value` flags before the next `--field` are values
        # for that field. Same mutex/duplicate rules apply via update_many().
        try:
            path = "docs/compass.md"
            argv2 = []
            i = 0
            while i < len(rest):
                if rest[i] == "--path" and i + 1 < len(rest):
                    path = rest[i + 1]
                    i += 2
                else:
                    argv2.append(rest[i])
                    i += 1
            patches = []
            cur_field = None
            cur_values = []
            i = 0
            while i < len(argv2):
                tok = argv2[i]
                if tok == "--field":
                    if cur_field is not None:
                        patches.append(_finalize_multi_patch(cur_field, cur_values))
                    if i + 1 >= len(argv2):
                        raise ValueError("--field requires a value")
                    cur_field = argv2[i + 1]
                    cur_values = []
                    i += 2
                elif tok == "--value":
                    if i + 1 >= len(argv2):
                        raise ValueError("--value requires a value")
                    if cur_field is None:
                        raise ValueError("--value before any --field")
                    cur_values.append(argv2[i + 1])
                    i += 2
                else:
                    raise ValueError(f"unexpected argument: {tok!r}")
            if cur_field is not None:
                patches.append(_finalize_multi_patch(cur_field, cur_values))
            if not patches:
                raise ValueError("update-many: at least one --field required")
            update_many(patches, path=path)
        except CompassFullError as e:
            print(str(e), file=sys.stderr)
            return 2
        except OpenLoopsCapError as e:
            print(f"OpenLoopsCapError: {e}", file=sys.stderr)
            return 2
        except ValueError as e:
            print(f"ValueError: {e}", file=sys.stderr)
            return 2
        return 0

    if sub == "append":
        # `--field X --value Y` — delegates to update(field=X, value=Y, append=True)
        try:
            path = "docs/compass.md"
            field = None
            value = None
            i = 0
            while i < len(rest):
                tok = rest[i]
                if tok == "--path" and i + 1 < len(rest):
                    path = rest[i + 1]
                    i += 2
                elif tok == "--field":
                    if i + 1 >= len(rest):
                        raise ValueError("--field requires a value")
                    field = rest[i + 1]
                    i += 2
                elif tok == "--value":
                    if i + 1 >= len(rest):
                        raise ValueError("--value requires a value")
                    if value is not None:
                        raise ValueError("append: only one --value permitted")
                    value = rest[i + 1]
                    i += 2
                else:
                    raise ValueError(f"unexpected argument: {tok!r}")
            if field is None or value is None:
                raise ValueError("append requires --field and --value")
            update(field=field, value=value, append=True, path=path)
        except CompassFullError as e:
            print(str(e), file=sys.stderr)
            return 2
        except OpenLoopsCapError as e:
            print(f"OpenLoopsCapError: {e}", file=sys.stderr)
            return 2
        except ValueError as e:
            print(f"ValueError: {e}", file=sys.stderr)
            return 2
        return 0

    if sub == "compress":
        print(
            "[v1.1] compress not yet implemented — edit docs/compass.md manually",
            file=sys.stderr,
        )
        return 0

    if sub == "doctor":
        path = "docs/compass.md"
        # consume --path
        try:
            idx = rest.index("--path")
            path = rest[idx + 1]
        except (ValueError, IndexError):
            pass
        return _cmd_doctor(path)

    print(f"unknown subcommand: {sub!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
