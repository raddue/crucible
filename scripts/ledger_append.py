#!/usr/bin/env python3
"""Canonical ledger append protocol — mkdir-lock + holder file + single-write() syscall.

Protocol-as-spec lives in skills/shared/ledger-append.md. This module is the
importable, executable single source of truth used by T-1 subprocesses, by Tier A
emit call-sites, and by the Phase 3 backfill script.

Invariants enforced here:
- L-1 append-only (O_APPEND, never rewrite a line)
- L-6 kill-switch (CRUCIBLE_CALIBRATION_DISABLED=1 → no-op return BEFORE any lock)
- L-8 16 KiB line cap + gated_files truncation at 500 + highest_finding cap at 256 chars
- #402 identity gate: refuse an entry lacking a non-empty string run_id AND skill
  (the (run_id, skill) join key must never collapse to the shared "unknown" bucket)
- Crash-window recovery (>60s stale lockdir with branch A live/dead, branch B malformed)

Pure stdlib. No third-party deps.
"""
import datetime as _dt
import errno
import json
import os
import sys
import time
from typing import Optional

LOCK_DIRNAME = ".lock-runs-jsonl"
HOLDER_FILENAME = "holder"
SPIN_INTERVAL_S = 0.05          # 50 ms backoff
INITIAL_SPIN_CAP_S = 5.0        # initial spin cap before stale-recovery
RECOVERY_SPIN_CAP_S = 300.0     # cap once we know holder is alive (branch A EPERM/0)
STALE_THRESHOLD_S = 60.0        # lockdir age past which we enter stale-recovery


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _kill_switch_active() -> bool:
    return os.environ.get("CRUCIBLE_CALIBRATION_DISABLED") == "1"


# --------------------------------------------------------------------------- #
# Central-store path + provenance resolution (#270).                          #
#                                                                             #
# The live ledger is machine-local and aggregates EVERY repo's gating runs    #
# into one place — never inside any git repo, because entries carry private   #
# file paths and verbatim finding quotes and crucible is a public repo.       #
# These helpers are the single source of truth for the path; render_ledger    #
# imports them. default_repo() shells to git and is therefore CLI-only —      #
# append() stays free of git/subprocess side effects (INV-2).                 #
# --------------------------------------------------------------------------- #
SCHEMA_VERSION = 2


def default_ledger_dir() -> str:
    """Directory holding the live ledger. A non-empty CRUCIBLE_LEDGER_DIR wins
    (tests, fixtures); an empty/unset value falls back to ~/.claude/crucible/
    ledger — a ~-rooted path that is never inside a git working tree (INV-1)."""
    env = os.environ.get("CRUCIBLE_LEDGER_DIR")
    if env:
        return env
    return os.path.join(os.path.expanduser("~"), ".claude", "crucible", "ledger")


def default_ledger_path() -> str:
    return os.path.join(default_ledger_dir(), "runs.jsonl")


def default_repo(start_dir: Optional[str] = None) -> str:
    """Provenance label for the repo a gating run happened in: the basename of
    the git toplevel, falling back to the basename of the start dir / cwd when
    not in a git repo (or git is absent). Never raises (INV-7). CLI-only — not
    reachable from append() (INV-2)."""
    base = start_dir or os.getcwd()
    try:
        import subprocess
        proc = subprocess.run(
            ["git", "-C", base, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        top = proc.stdout.strip()
        if proc.returncode == 0 and top:
            return os.path.basename(top.rstrip("/")) or top
    except Exception:  # noqa: BLE001 — provenance is best-effort, never fatal
        pass
    return os.path.basename(os.path.abspath(base)) or "unknown"


def _warn(msg: str) -> None:
    print(f"[ledger_append WARN] {msg}", file=sys.stderr)


def _valid_identity(value) -> bool:
    """True iff `value` is a non-empty, non-whitespace string — the requirement
    for either half of the (run_id, skill) ledger join key (#402). A missing,
    empty, whitespace-only, or non-string value has no stable identity."""
    return isinstance(value, str) and value.strip() != ""


def _truncate_payload(entry: dict, max_gated_files: int,
                       max_highest_finding_chars: int) -> tuple[dict, Optional[list]]:
    """Apply L-8 truncation in-place on a shallow copy.

    Returns (truncated_entry, overflow_list_or_None). Sidecar I/O is the caller's
    responsibility — deferred to AFTER the line-bytes size check passes to avoid
    orphan-sidecar leaks on oversize rejection (review finding S-3).
    """
    out = dict(entry)
    overflow: Optional[list] = None
    gated = out.get("gated_files")
    if isinstance(gated, list) and len(gated) > max_gated_files:
        overflow = list(gated)
        out["gated_files"] = overflow[:max_gated_files]
        out["gated_files_truncated"] = len(overflow) - max_gated_files
    else:
        out.setdefault("gated_files_truncated", 0)

    hf = out.get("highest_finding")
    if isinstance(hf, str) and len(hf) > max_highest_finding_chars:
        out["highest_finding"] = hf[:max_highest_finding_chars]
    return out, overflow


def caller_dedup(ledger_path: str, run_id: str, skill: str) -> bool:
    """L-2 caller-side dedup. Returns True if (run_id, skill) already in ledger.

    Callers MUST invoke this BEFORE append() to honor invariant L-2. The append
    helper does not scan for prior entries. Full-scan; bounded by current ledger
    size (acceptable while ledger is sub-MB; future rotation lands in v1.1).
    """
    if not os.path.exists(ledger_path):
        return False
    try:
        with open(ledger_path, "rb") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if obj.get("run_id") == run_id and obj.get("skill") == skill:
                    return True
    except OSError:
        return False
    return False


def _try_stale_recovery(lockdir: str) -> bool:
    """Returns True if recovery freed the lockdir (caller should retry mkdir).

    Branch A: holder file present and parses → check liveness via os.kill(pid, 0).
      - returns 0 (alive): keep waiting, do NOT rmdir.
      - ProcessLookupError (ESRCH): dead → unlink holder + rmdir + signal retry.
      - PermissionError (EPERM): alive under another uid → keep waiting.
    Branch B: holder missing or malformed → definitively crashed mid-acquire; rmdir.
    """
    holder = os.path.join(lockdir, HOLDER_FILENAME)
    try:
        with open(holder, "r", encoding="utf-8") as f:
            line = f.read().strip()
        # holder format: <run_id>:<skill>:<pid>:<iso_ts>
        parts = line.split(":")
        if len(parts) < 4:
            raise ValueError("malformed holder")
        pid = int(parts[2])
    except (OSError, ValueError):
        # Branch B: missing or malformed holder
        try:
            try:
                os.unlink(holder)
            except OSError:
                pass
            os.rmdir(lockdir)
            return True
        except OSError:
            return False

    # Branch A: liveness probe
    try:
        os.kill(pid, 0)
        # Alive — do NOT rmdir
        return False
    except ProcessLookupError:
        # Dead (ESRCH) — recover
        try:
            os.unlink(holder)
        except OSError:
            pass
        try:
            os.rmdir(lockdir)
            return True
        except OSError:
            return False
    except PermissionError:
        # EPERM — alive under another uid; keep waiting
        return False


def _acquire_lock(lockdir: str) -> bool:
    """Block until lockdir is acquired or recovery escalation gives up.

    Returns True on acquisition. Returns False if all recovery paths exhausted.
    Total max wait: ~5s initial spin + ~300s recovery spin = 305s per attempt.
    """
    spin_started = time.monotonic()
    while True:
        try:
            os.mkdir(lockdir)
            return True
        except FileExistsError:
            pass
        except OSError as e:
            if e.errno != errno.EEXIST:
                _warn(f"mkdir lockdir errored: {e}")
                return False

        elapsed = time.monotonic() - spin_started
        # Check lockdir age for stale-recovery eligibility
        try:
            st = os.stat(lockdir)
            lockdir_age = time.time() - st.st_mtime
        except FileNotFoundError:
            # vanished between EEXIST and stat — retry immediately
            continue

        if lockdir_age > STALE_THRESHOLD_S:
            recovered = _try_stale_recovery(lockdir)
            if recovered:
                continue  # retry mkdir
            # alive-holder branch — keep spinning under the extended cap
            if elapsed > RECOVERY_SPIN_CAP_S:
                _warn(f"lock acquisition exhausted recovery cap at {lockdir}")
                return False
        else:
            if elapsed > INITIAL_SPIN_CAP_S:
                # Loop continues; we'll re-evaluate stale once lockdir_age crosses threshold
                pass
            if elapsed > (INITIAL_SPIN_CAP_S + RECOVERY_SPIN_CAP_S):
                _warn(f"lock acquisition timed out at {lockdir}")
                return False
        time.sleep(SPIN_INTERVAL_S)


def append(
    ledger_path: str,
    entry: dict,
    *,
    max_line_bytes: int = 16384,
    max_gated_files: int = 500,
    max_highest_finding_chars: int = 256,
    overflow_dir: Optional[str] = None,
) -> bool:
    """Append one JSONL line to ledger_path under the canonical lock protocol.

    Returns True on successful append; False on kill-switch no-op or rejection.
    """
    # L-6 kill-switch: BEFORE any lock acquisition or filesystem state change.
    if _kill_switch_active():
        return False

    # #402 identity gate. append() serves BOTH central stores, which carry
    # different join keys:
    #   - runs.jsonl  → (run_id, skill)        (reconcile_ledger.ledger_entry_hash)
    #   - falsification log → ledger_entry_hash (the walkback / predicate rows)
    # An entry carrying NEITHER key collapses to the shared "unknown" bucket —
    # silently merging unrelated runs across every repo in the machine-local
    # central store, where caller_dedup drops the second as a "duplicate" and
    # compute_brier mis-buckets them. Require at least one valid join key.
    # The OR-rule's soundness depends on ledger_entry_hash appearing ONLY on
    # falsification-log rows (never on a runs-ledger row); the consumer-side
    # "unknown" fallback in reconcile_ledger.compute_brier is a known residual
    # deliberately deferred to the read-path follow-up PR.
    run_id = entry.get("run_id")
    skill = entry.get("skill")
    entry_hash = entry.get("ledger_entry_hash")
    has_runs_identity = _valid_identity(run_id) and _valid_identity(skill)
    if not (has_runs_identity or _valid_identity(entry_hash)):
        _warn(
            f"identity-less entry rejected (run_id={run_id!r} skill={skill!r} "
            f"ledger_entry_hash={entry_hash!r}); a non-empty string (run_id AND "
            "skill) or ledger_entry_hash is required (#402)"
        )
        return False
    # Lock-holder identity + diagnostics prefer (run_id, skill); a falsification
    # row carries no run_id/skill, so fall back to its ledger_entry_hash key.
    if not _valid_identity(run_id):
        run_id = entry_hash
    if not _valid_identity(skill):
        skill = "falsification"

    if overflow_dir is None:
        overflow_dir = os.path.join(os.path.dirname(ledger_path) or ".", "overflow")

    # L-8 truncation. Sidecar I/O is deferred until after the size check (S-3 fix).
    payload, overflow_files = _truncate_payload(
        entry, max_gated_files, max_highest_finding_chars,
    )

    line = json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n"
    line_bytes = line.encode("utf-8")
    if len(line_bytes) > max_line_bytes:
        _warn(
            f"oversize line rejected after truncation (run_id={run_id} "
            f"skill={skill} bytes={len(line_bytes)} cap={max_line_bytes})"
        )
        return False

    ledger_dir = os.path.dirname(ledger_path) or "."
    try:
        os.makedirs(ledger_dir, exist_ok=True)
    except OSError as e:
        _warn(f"could not create ledger dir {ledger_dir}: {e}")
        return False

    lockdir = os.path.join(ledger_dir, LOCK_DIRNAME)
    if not _acquire_lock(lockdir):
        _warn(f"failed to acquire lock for {ledger_path} (run_id={run_id} skill={skill})")
        return False

    holder_path = os.path.join(lockdir, HOLDER_FILENAME)
    try:
        # Step 2: write identity inside the lockdir
        with open(holder_path, "w", encoding="utf-8") as hf:
            hf.write(f"{run_id}:{skill}:{os.getpid()}:{_now_iso()}")

        # L-8 sidecar: write only AFTER the size check passed, inside the lock.
        # Avoids orphan-sidecar leaks when the ledger append itself is rejected.
        if overflow_files is not None:
            try:
                os.makedirs(overflow_dir, exist_ok=True)
                sidecar = os.path.join(overflow_dir, f"{run_id}.{skill}.txt")
                with open(sidecar, "w", encoding="utf-8") as f:
                    for p in overflow_files:
                        f.write(p + "\n")
            except OSError as e:
                _warn(f"sidecar write failed for run_id={run_id} skill={skill}: {e}")

        # Step 3: single-write() syscall append. ≤16 KiB ⇒ atomic on ext4/APFS/9p.
        fd = os.open(ledger_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            written = os.write(fd, line_bytes)
            if written != len(line_bytes):
                # L-1 hazard: a partial line is on disk. Terminate it with a
                # newline so the reducer's per-line JSON parse skips this
                # fragment cleanly rather than corrupting downstream lines.
                # We still report failure to the caller.
                try:
                    os.write(fd, b"\n")
                    os.fsync(fd)
                except OSError:
                    pass
                _warn(
                    f"short write detected; line terminator forced "
                    f"(wrote={written} expected={len(line_bytes)} "
                    f"run_id={run_id} skill={skill})"
                )
                return False
            os.fsync(fd)
        finally:
            os.close(fd)
        return True
    finally:
        # Step 4: release — unlink holder first, then rmdir lockdir.
        try:
            os.unlink(holder_path)
        except OSError:
            pass
        try:
            os.rmdir(lockdir)
        except OSError:
            pass


def _cli_emit(ledger_arg: str, entry: dict) -> int:
    """`emit` subcommand: the canonical forward-capture write path.

    Resolves '-' to the central default, honors the kill-switch as a graceful
    skip, dedups by (run_id, skill), fills `repo` when absent and forces
    `schema_version` to the current value, then appends. Pure stdlib + invoked
    by absolute path ⇒ no PYTHONPATH and no cwd dependency (INV-5/INV-6).
    Graceful no-ops (kill-switch, duplicate) return 0; only a real append
    rejection returns 1 (INV-9)."""
    ledger_path = default_ledger_path() if ledger_arg == "-" else ledger_arg

    # L-6 graceful skip: kill-switch is a no-op, not a failure.
    if _kill_switch_active():
        print("[ledger_append] calibration disabled; emit skipped", file=sys.stderr)
        return 0

    # `emit` is always a current-schema forward capture: stamp schema_version
    # unconditionally (an emitter sending the stale `1` must not produce a
    # hybrid v1+repo row). Fill `repo` when absent OR explicitly null/empty —
    # setdefault would miss the null case, silently voiding provenance.
    if not entry.get("repo"):
        entry["repo"] = default_repo()
    entry["schema_version"] = SCHEMA_VERSION

    run_id = entry.get("run_id", "unknown")
    skill = entry.get("skill", "unknown")
    if caller_dedup(ledger_path, run_id, skill):
        print(f"[ledger_append] duplicate (run_id={run_id} skill={skill}); "
              f"emit skipped", file=sys.stderr)
        return 0

    return 0 if append(ledger_path, entry) else 1


if __name__ == "__main__":
    # Two CLI forms:
    #   emit <ledger_path|-> <json>   — dedup + auto-fill + append (canonical)
    #   <ledger_path> <json>          — legacy append-only (back-compat)
    argv = sys.argv
    if len(argv) >= 4 and argv[1] == "emit":
        sys.exit(_cli_emit(argv[2], json.loads(argv[3])))
    if len(argv) >= 3 and argv[1] != "emit":
        ok = append(argv[1], json.loads(argv[2]))
        sys.exit(0 if ok else 1)
    print("usage: ledger_append.py emit <ledger_path|-> <json-entry>\n"
          "       ledger_append.py <ledger_path> <json-entry>  (legacy, append-only)",
          file=sys.stderr)
    sys.exit(2)
