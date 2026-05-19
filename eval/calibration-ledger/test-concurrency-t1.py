#!/usr/bin/env python3
"""T-1: concurrency + stale-recovery branches A-alive, A-dead, B-missing.

Spawns real subprocesses via subprocess.Popen against scripts/ledger_append.py
through this same file's __main__ worker branch. Tests must be self-contained
and exit 0 = PASS, non-zero = FAIL.

Assertion groups:
  1-4. Base concurrency: 200 lines, all parse, no interleaving, no partials.
  5. Branch A alive (kill -0 returns 0) — holder remains, no rmdir.
  6. Branch A dead (ESRCH) — recovery unlinks + rmdirs + retries.
  7. Branch B missing/malformed — recovery rmdirs.
  8. UUIDv7: 1000 unique, version nibble = 7, timestamps monotone-non-decreasing.

Usage:
  python eval/calibration-ledger/test-concurrency-t1.py            # runs all tests
  python eval/calibration-ledger/test-concurrency-t1.py --worker <ledger> <skill> <n>
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

# Locate repo root so subprocesses can import scripts.*
HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _make_entry(skill: str, i: int) -> dict:
    from scripts.uuid7 import uuid7
    return {
        "schema_version": 1,
        "run_id": uuid7(),
        "skill": skill,
        "tier": "A",
        "artifact_type": "code",
        "verdict": "PASS",
        "confidence": 0.9,
        "artifact_hash": "a" * 64,
        "chunk_hash": None,
        "gated_files": [f"{skill}/file_{i}.py"],
        "findings_count": 0,
        "severity_histogram": {"fatal": 0, "significant": 0, "minor": 0, "nit": 0},
        "highest_finding": None,
        "would_have_shipped_without_gate": False,
        "rounds": 1,
        "timestamp": "2026-05-19T00:00:00Z",
        "backfilled": False,
        "falsified": None,
        "falsified_by": None,
        "gated_files_truncated": 0,
        "comment": f"{skill}:{i}",
        "predicted_falsifier": None,
    }


def _worker_main(ledger_path: str, skill: str, n: int) -> int:
    """Subprocess entry: append n lines under the canonical protocol."""
    from scripts.ledger_append import append
    ok = 0
    for i in range(n):
        if append(ledger_path, _make_entry(skill, i)):
            ok += 1
    return 0 if ok == n else 1


def _spawn_worker(ledger_path: str, skill: str, n: int) -> subprocess.Popen:
    cmd = [sys.executable, os.path.abspath(__file__), "--worker", ledger_path, skill, str(n)]
    env = dict(os.environ)
    env["PYTHONPATH"] = REPO_ROOT + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.Popen(cmd, env=env)


_results = []


def _check(label: str, cond: bool, detail: str = "") -> None:
    tag = "[PASS]" if cond else "[FAIL]"
    msg = f"{tag} {label}"
    if detail and not cond:
        msg += f"  -- {detail}"
    print(msg)
    _results.append(cond)


# ---------- Test groups ----------

def test_base_concurrency() -> None:
    tmp = tempfile.mkdtemp(prefix="t1-base-")
    ledger = os.path.join(tmp, "runs.jsonl")
    try:
        p1 = _spawn_worker(ledger, "quality-gate", 100)
        p2 = _spawn_worker(ledger, "siege", 100)
        rc1 = p1.wait(timeout=120)
        rc2 = p2.wait(timeout=120)
        _check("T-1.1 worker exit codes 0", rc1 == 0 and rc2 == 0, f"rc1={rc1} rc2={rc2}")

        with open(ledger, "rb") as f:
            raw = f.read()
        lines = raw.split(b"\n")
        if lines and lines[-1] == b"":
            lines = lines[:-1]
        _check("T-1.1 line count == 200", len(lines) == 200, f"got {len(lines)}")

        # T-1.2 every line parses
        all_parse = True
        objs = []
        for ln in lines:
            try:
                objs.append(json.loads(ln))
            except Exception:
                all_parse = False
                break
        _check("T-1.2 every line parses as JSON", all_parse)

        # T-1.3 no interleaving — each line's `skill` belongs to exactly one emitter
        # and the line contains no substring from the other emitter's comment marker
        no_interleave = all(
            (b'"comment":"quality-gate:' in ln) ^ (b'"comment":"siege:' in ln)
            for ln in lines
        )
        _check("T-1.3 no interleaved emitter payloads", no_interleave)

        # T-1.4 every line ends with newline boundary (trailing \n in file) and is complete
        _check("T-1.4 no partial trailing line", raw.endswith(b"\n"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_branch_a_alive() -> None:
    """Branch A — alive holder: B continues spinning under 300s cap; no rmdir."""
    from scripts.ledger_append import LOCK_DIRNAME, HOLDER_FILENAME, STALE_THRESHOLD_S
    tmp = tempfile.mkdtemp(prefix="t1-Aalive-")
    ledger = os.path.join(tmp, "runs.jsonl")
    lockdir = os.path.join(tmp, LOCK_DIRNAME)
    holder = os.path.join(lockdir, HOLDER_FILENAME)
    try:
        # Manually create a lockdir with a holder pointing at our OWN pid (definitely alive)
        os.makedirs(tmp, exist_ok=True)
        os.mkdir(lockdir)
        with open(holder, "w") as f:
            f.write(f"run-x:quality-gate:{os.getpid()}:2026-05-19T00:00:00Z")
        # Backdate the lockdir mtime past the stale threshold so B enters recovery.
        old_t = time.time() - (STALE_THRESHOLD_S + 5)
        os.utime(lockdir, (old_t, old_t))

        # Spawn a worker that should observe alive holder and keep spinning (NOT rmdir).
        # We give it a short budget (~2s) and then release the lock manually.
        p = _spawn_worker(ledger, "quality-gate", 1)
        time.sleep(2.0)
        # The lockdir should still exist (B did NOT rmdir because holder is alive).
        still_held = os.path.isdir(lockdir) and os.path.exists(holder)
        _check("T-1.5 alive-holder: lockdir + holder still present after spin", still_held)

        # Release: unlink holder, rmdir lockdir, then worker should succeed.
        try: os.unlink(holder)
        except OSError: pass
        try: os.rmdir(lockdir)
        except OSError: pass
        rc = p.wait(timeout=60)
        _check("T-1.5 alive-holder: worker succeeded after release", rc == 0, f"rc={rc}")

        with open(ledger, "rb") as f:
            line_count = sum(1 for _ in f)
        _check("T-1.5 alive-holder: 1 line landed cleanly", line_count == 1, f"got {line_count}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_branch_a_dead() -> None:
    """Branch A — dead holder (ESRCH): recovery unlinks + rmdirs + retries."""
    from scripts.ledger_append import LOCK_DIRNAME, HOLDER_FILENAME, STALE_THRESHOLD_S
    tmp = tempfile.mkdtemp(prefix="t1-Adead-")
    ledger = os.path.join(tmp, "runs.jsonl")
    lockdir = os.path.join(tmp, LOCK_DIRNAME)
    holder = os.path.join(lockdir, HOLDER_FILENAME)
    try:
        # Spawn and immediately SIGKILL a placeholder process so we have a dead pid.
        dead = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        dead_pid = dead.pid
        dead.send_signal(signal.SIGKILL)
        dead.wait(timeout=10)
        # Give the OS a moment to reap.
        time.sleep(0.5)

        os.mkdir(lockdir)
        with open(holder, "w") as f:
            f.write(f"run-y:quality-gate:{dead_pid}:2026-05-19T00:00:00Z")
        old_t = time.time() - (STALE_THRESHOLD_S + 5)
        os.utime(lockdir, (old_t, old_t))

        # Now run a worker — it should detect the lockdir is stale, holder pid is dead,
        # rmdir, and successfully append.
        p = _spawn_worker(ledger, "quality-gate", 1)
        rc = p.wait(timeout=60)
        _check("T-1.6 dead-holder: worker succeeded via recovery", rc == 0, f"rc={rc}")

        # Lockdir should be gone after recovery + release.
        _check("T-1.6 dead-holder: lockdir cleaned up", not os.path.isdir(lockdir))
        with open(ledger, "rb") as f:
            line_count = sum(1 for _ in f)
        _check("T-1.6 dead-holder: 1 line landed", line_count == 1, f"got {line_count}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_branch_b_missing() -> None:
    """Branch B — missing/malformed holder: recovery rmdirs after >60s."""
    from scripts.ledger_append import LOCK_DIRNAME, STALE_THRESHOLD_S
    tmp = tempfile.mkdtemp(prefix="t1-Bmiss-")
    ledger = os.path.join(tmp, "runs.jsonl")
    lockdir = os.path.join(tmp, LOCK_DIRNAME)
    try:
        os.mkdir(lockdir)  # no holder file written
        old_t = time.time() - (STALE_THRESHOLD_S + 5)
        os.utime(lockdir, (old_t, old_t))

        p = _spawn_worker(ledger, "quality-gate", 1)
        rc = p.wait(timeout=60)
        _check("T-1.7 missing-holder: worker recovered + succeeded", rc == 0, f"rc={rc}")
        _check("T-1.7 missing-holder: lockdir cleaned up", not os.path.isdir(lockdir))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_uuid7_sub() -> None:
    """T-1.8 UUIDv7: 1000 unique, version 7, timestamps monotone-non-decreasing."""
    from scripts.uuid7 import uuid7
    vals = [uuid7() for _ in range(1000)]
    _check("T-1.8 UUIDv7: 1000 unique", len(set(vals)) == 1000)
    _check("T-1.8 UUIDv7: version nibble == 7 on all", all(v[14] == "7" for v in vals))
    # Timestamps live in the first 12 hex chars (48 bits, big-endian)
    ts_ints = [int(v.replace("-", "")[:12], 16) for v in vals]
    monotone = all(ts_ints[i] <= ts_ints[i + 1] for i in range(len(ts_ints) - 1))
    _check("T-1.8 UUIDv7: timestamps monotone-non-decreasing", monotone)


def main() -> int:
    test_base_concurrency()
    test_branch_a_alive()
    test_branch_a_dead()
    test_branch_b_missing()
    test_uuid7_sub()
    failures = sum(1 for r in _results if not r)
    if failures:
        print(f"\n{failures} assertion(s) FAILED")
        return 1
    print(f"\nALL {len(_results)} assertions PASSED")
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--worker":
        # Worker invocation: --worker <ledger_path> <skill> <n>
        sys.exit(_worker_main(sys.argv[2], sys.argv[3], int(sys.argv[4])))
    sys.exit(main())
