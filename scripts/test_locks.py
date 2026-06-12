#!/usr/bin/env python3
"""Phase 2 (#398) — lock state-machine + crash-recovery tests for the two
bespoke mkdir-lock protocols guarding the machine-local stores.

Both protocols are mkdir-as-mutex + a `holder` file + stale-recovery, but they
are SEPARATE implementations with different holder formats and recovery rules:
  - `ledger_append.py` (`_try_stale_recovery`/`_acquire_lock`) guards runs.jsonl
    appends. Holder: `run_id:skill:pid:iso`. Recovery keys on os.kill(pid,0)
    liveness; a >60s lockdir age admits recovery.
  - `compass.py` (`_try_recover_stale`/`_acquire_lock`) guards docs/compass.md.
    Holder: `pid@epoch`. Recovery keys on liveness AND a 30s mtime TTL (an
    alive-PID + old-mtime eviction warns about possible PID reuse).

Before this file BOTH state machines had zero contention/stale/dead-PID tests
(audit F2, FATAL). `compass.py:59-71` even ships a `_test_sleep()` hook
(`CRUCIBLE_COMPASS_TEST_SLEEP_MS`) that no test consumed — the contention test
here is its first consumer.

Two known instance bugs are PINNED as characterization tests here (current
behavior), with the fix deferred to #406 (per the user's decision — surfaced,
not silently fixed):
  - `ledger_append.py:228` — a held-but-FRESH lock spins to the ~305s combined
    cap instead of the documented ~5s initial cap. Pinned via scaled module
    constants so the test runs in milliseconds and asserts the spin overruns the
    initial cap (the bug), without waiting 305s and without a production change.
  - `compass.py:689` — the lock identity derives from `dirname(path)` (dir-scoped),
    so two compass files under different sub-dirs do NOT share a lock. Pinned as
    the current derivation rule.

Pure stdlib `unittest`. All locks live under tmp dirs (ledger lock is beside the
tmp ledger_path; compass lock is `/tmp/.lock-compass-<sha1>` keyed off a tmp
repo_root we create and clean up). The machine-local central store is never
touched.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts import ledger_append as la  # noqa: E402
from scripts import compass as cm  # noqa: E402

COMPASS_SCRIPT = os.path.join(HERE, "compass.py")

# A PID that is essentially guaranteed not to be live. os.kill(DEAD_PID, 0) must
# raise ProcessLookupError. 2**31-1 is above any real PID on Linux/macOS.
DEAD_PID = 0x7FFFFFFF


def _dead_pid():
    """Return a PID that is not currently alive (best-effort, deterministic)."""
    p = DEAD_PID
    # If by absurd luck it is alive, walk down until we find a dead one.
    for _ in range(64):
        try:
            os.kill(p, 0)
            p -= 1
        except ProcessLookupError:
            return p
        except OSError:
            # EPERM (alive under another uid) etc. — not a clean ESRCH, but the
            # pid is unusable as a "dead" sentinel either way; accept and return.
            return p  # treat as "not ours"; a clean dead one is preferred above
    return p


# --------------------------------------------------------------------------- #
# ledger_append — _try_stale_recovery (Branch A liveness / Branch B malformed)  #
# --------------------------------------------------------------------------- #

class LedgerStaleRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.lockdir = os.path.join(self.tmp, la.LOCK_DIRNAME)
        os.mkdir(self.lockdir)
        self.holder = os.path.join(self.lockdir, la.HOLDER_FILENAME)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_holder(self, text):
        with open(self.holder, "w", encoding="utf-8") as f:
            f.write(text)

    def test_dead_pid_holder_recovers(self):
        # Branch A, dead PID (ESRCH) → unlink holder + rmdir + signal retry.
        self._write_holder(f"r1:siege:{_dead_pid()}:2026-01-01T00:00:00Z")
        self.assertTrue(la._try_stale_recovery(self.lockdir))
        self.assertFalse(os.path.exists(self.lockdir))   # lockdir freed

    def test_alive_pid_holder_does_not_recover(self):
        # Branch A, our own (alive) PID → keep waiting, do NOT rmdir.
        self._write_holder(f"r1:siege:{os.getpid()}:2026-01-01T00:00:00Z")
        self.assertFalse(la._try_stale_recovery(self.lockdir))
        self.assertTrue(os.path.exists(self.lockdir))    # lockdir intact

    def test_malformed_holder_too_few_fields_recovers(self):
        # Branch B: holder present but unparseable (<4 colon fields) → crashed
        # mid-acquire → rmdir.
        self._write_holder("garbage-no-colons")
        self.assertTrue(la._try_stale_recovery(self.lockdir))
        self.assertFalse(os.path.exists(self.lockdir))

    def test_non_integer_pid_recovers(self):
        # Branch B: 4 fields but pid is non-integer → ValueError → rmdir.
        self._write_holder("r1:siege:notapid:2026-01-01T00:00:00Z")
        self.assertTrue(la._try_stale_recovery(self.lockdir))
        self.assertFalse(os.path.exists(self.lockdir))

    def test_missing_holder_recovers(self):
        # Branch B: lockdir exists but holder file is absent → crashed between
        # mkdir and holder-write → rmdir.
        self.assertFalse(os.path.exists(self.holder))
        self.assertTrue(la._try_stale_recovery(self.lockdir))
        self.assertFalse(os.path.exists(self.lockdir))


# --------------------------------------------------------------------------- #
# ledger_append — _acquire_lock (free acquire / stale recovery / #406 spin)     #
# --------------------------------------------------------------------------- #

class LedgerAcquireLockTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.lockdir = os.path.join(self.tmp, la.LOCK_DIRNAME)
        # Snapshot the spin/threshold constants so the #406 characterization can
        # scale them down and restore afterward.
        self._consts = {
            k: getattr(la, k) for k in
            ("SPIN_INTERVAL_S", "INITIAL_SPIN_CAP_S",
             "RECOVERY_SPIN_CAP_S", "STALE_THRESHOLD_S")
        }

    def tearDown(self):
        for k, v in self._consts.items():
            setattr(la, k, v)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_acquires_free_lock_immediately(self):
        self.assertTrue(la._acquire_lock(self.lockdir))
        self.assertTrue(os.path.isdir(self.lockdir))

    def test_recovers_dead_pid_stale_lock_then_acquires(self):
        # Pre-create a stale lockdir (age past STALE_THRESHOLD) held by a dead
        # PID. _acquire_lock must recover it and acquire.
        la.SPIN_INTERVAL_S = 0.01
        la.INITIAL_SPIN_CAP_S = 0.05
        la.RECOVERY_SPIN_CAP_S = 0.5
        la.STALE_THRESHOLD_S = 0.0    # any existing lockdir is immediately "stale-eligible"
        os.mkdir(self.lockdir)
        with open(os.path.join(self.lockdir, la.HOLDER_FILENAME), "w") as f:
            f.write(f"r1:siege:{_dead_pid()}:2026-01-01T00:00:00Z")
        self.assertTrue(la._acquire_lock(self.lockdir))
        self.assertTrue(os.path.isdir(self.lockdir))

    def test_held_but_fresh_lock_overruns_initial_cap_BUG_406(self):
        # CHARACTERIZATION of the deferred #406 instance bug (ledger_append.py:228):
        # a held-but-FRESH lock (age < STALE_THRESHOLD) should give up at the
        # ~5s INITIAL cap, but the no-op `pass` branch lets it spin to the
        # combined INITIAL+RECOVERY cap instead. We scale the constants down so
        # the overrun is milliseconds, hold the lock with an ALIVE pid + fresh
        # mtime (so stale-recovery never fires), and assert the acquire (a) fails
        # and (b) took LONGER than the initial cap — i.e. it overran, which is
        # the bug. When #406 fixes it to honor the initial cap, this test will
        # start failing on the elapsed assertion and must be updated.
        la.SPIN_INTERVAL_S = 0.01
        la.INITIAL_SPIN_CAP_S = 0.05
        la.RECOVERY_SPIN_CAP_S = 0.20
        la.STALE_THRESHOLD_S = 1000.0   # fresh lockdir never enters stale-recovery
        os.mkdir(self.lockdir)
        with open(os.path.join(self.lockdir, la.HOLDER_FILENAME), "w") as f:
            f.write(f"r1:siege:{os.getpid()}:2026-01-01T00:00:00Z")  # alive holder
        t0 = time.monotonic()
        acquired = la._acquire_lock(self.lockdir)
        elapsed = time.monotonic() - t0
        self.assertFalse(acquired)   # cannot acquire a live-held lock
        # The bug: it overran the initial cap rather than returning at ~0.05s.
        self.assertGreater(elapsed, la.INITIAL_SPIN_CAP_S,
                           "held-but-fresh lock should overrun the initial cap "
                           "under current (buggy) behavior — see #406")
        # Upper bound: it must still give up at ~the combined cap, not spin
        # forever. Generous slack for scheduler jitter on a loaded CI box.
        self.assertLess(
            elapsed,
            la.INITIAL_SPIN_CAP_S + la.RECOVERY_SPIN_CAP_S + 0.2,
            "held-but-fresh lock should give up by the combined cap, not later")

    def test_alive_foreign_holder_bails_at_recovery_cap_returns_false(self):
        # Integration coverage of the alive-holder recovery-cap give-up branch
        # (ledger_append.py:223-226). With STALE_THRESHOLD_S=0.0 the existing
        # lockdir is immediately stale-eligible, but the holder is an ALIVE pid
        # (our own), so _try_stale_recovery declines (returns False) every spin.
        # The loop therefore keeps spinning under the extended RECOVERY cap and
        # only bails — returning False — once elapsed > RECOVERY_SPIN_CAP_S. This
        # is the safety valve against an unbounded spin on a legitimately-held
        # (but stale-aged) lock.
        la.SPIN_INTERVAL_S = 0.01
        la.INITIAL_SPIN_CAP_S = 0.02
        la.RECOVERY_SPIN_CAP_S = 0.10
        la.STALE_THRESHOLD_S = 0.0    # existing lockdir is immediately stale-eligible
        os.mkdir(self.lockdir)
        with open(os.path.join(self.lockdir, la.HOLDER_FILENAME), "w") as f:
            f.write(f"r1:siege:{os.getpid()}:2026-01-01T00:00:00Z")  # ALIVE holder
        t0 = time.monotonic()
        acquired = la._acquire_lock(self.lockdir)
        elapsed = time.monotonic() - t0
        self.assertFalse(acquired)   # cannot evict a live holder → recovery declines → bails
        # It spun under the extended recovery cap before giving up (the
        # safety-valve path), so elapsed must exceed RECOVERY_SPIN_CAP_S.
        self.assertGreater(
            elapsed, la.RECOVERY_SPIN_CAP_S,
            "alive-holder branch must spin to the recovery cap before bailing")


# --------------------------------------------------------------------------- #
# ledger_append — short-write partial-line hazard (append L307-323)             #
# --------------------------------------------------------------------------- #

class LedgerShortWriteTest(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.pop("CRUCIBLE_CALIBRATION_DISABLED", None)
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        os.environ.pop("CRUCIBLE_CALIBRATION_DISABLED", None)
        if self._saved is not None:
            os.environ["CRUCIBLE_CALIBRATION_DISABLED"] = self._saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_short_write_forces_terminator_and_returns_false(self):
        # Force os.write to report a partial write (fewer bytes than requested).
        # append() must: (a) write a trailing newline so the reducer skips the
        # fragment cleanly, (b) return False, (c) still release the lock.
        p = os.path.join(self.tmp, "runs.jsonl")
        real_write = os.write
        calls = {"n": 0}

        def short_write(fd, data):
            calls["n"] += 1
            if calls["n"] == 1:
                # write only the first byte of the real payload, report short
                real_write(fd, data[:1])
                return 1
            return real_write(fd, data)   # let the forced "\n" terminator through

        with mock.patch.object(la.os, "write", side_effect=short_write):
            ok = la.append(p, {"run_id": "r1", "skill": "siege"})
        self.assertFalse(ok)                                      # reported failure
        self.assertFalse(os.path.isdir(os.path.join(self.tmp, la.LOCK_DIRNAME)))  # lock released
        # The on-disk fragment ends with a newline (terminator forced), so a
        # per-line JSON reader skips it rather than corrupting the next line.
        with open(p, "rb") as f:
            self.assertTrue(f.read().endswith(b"\n"))


# --------------------------------------------------------------------------- #
# compass — _holder_alive                                                       #
# --------------------------------------------------------------------------- #

class CompassHolderAliveTest(unittest.TestCase):
    def test_alive_pid_true(self):
        self.assertTrue(cm._holder_alive(os.getpid()))

    def test_dead_pid_false(self):
        self.assertFalse(cm._holder_alive(_dead_pid()))


# --------------------------------------------------------------------------- #
# compass — _try_recover_stale (mtime TTL + liveness + PID-reuse eviction)      #
# --------------------------------------------------------------------------- #

class CompassStaleRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.lockdir = os.path.join(self.tmp, "lock")
        os.mkdir(self.lockdir)
        self.holder = os.path.join(self.lockdir, "holder")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_holder(self, text, *, age_s=0.0):
        with open(self.holder, "w", encoding="utf-8") as f:
            f.write(text)
        if age_s:
            old = time.time() - age_s
            os.utime(self.holder, (old, old))

    def test_missing_holder_is_stale(self):
        # Lockdir present, holder absent → definitely stale → recovered.
        self.assertTrue(cm._try_recover_stale(self.lockdir))
        self.assertFalse(os.path.exists(self.lockdir))

    def test_dead_pid_holder_is_stale(self):
        self._write_holder(f"{_dead_pid()}@{int(time.time())}")
        self.assertTrue(cm._try_recover_stale(self.lockdir))
        self.assertFalse(os.path.exists(self.lockdir))

    def test_alive_pid_fresh_mtime_not_stale(self):
        # Our PID, fresh mtime, under the 30s TTL → NOT stale → keep waiting.
        self._write_holder(f"{os.getpid()}@{int(time.time())}")
        self.assertFalse(cm._try_recover_stale(self.lockdir))
        self.assertTrue(os.path.exists(self.lockdir))

    def test_alive_pid_old_mtime_evicts_with_warning(self):
        # Our PID (alive) but mtime older than STALE_TTL_S → evict anyway
        # (possible PID reuse; the code warns and recovers).
        self._write_holder(f"{os.getpid()}@{int(time.time())}",
                           age_s=cm.STALE_TTL_S + 5)
        self.assertTrue(cm._try_recover_stale(self.lockdir))
        self.assertFalse(os.path.exists(self.lockdir))

    def test_unreadable_pid_is_stale(self):
        # Holder present with a non-integer pid → unreadable → stale.
        self._write_holder("notapid@123", age_s=1.0)
        self.assertTrue(cm._try_recover_stale(self.lockdir))
        self.assertFalse(os.path.exists(self.lockdir))


# --------------------------------------------------------------------------- #
# compass — _acquire_lock / _release_lock                                       #
# --------------------------------------------------------------------------- #

class CompassAcquireReleaseTest(unittest.TestCase):
    def setUp(self):
        # A tmp repo_root → a deterministic /tmp/.lock-compass-<sha1> we clean up.
        self.repo_root = tempfile.mkdtemp()
        self.lockdir = cm._lockdir_for(self.repo_root)
        self._cleanup_lock()

    def tearDown(self):
        self._cleanup_lock()
        shutil.rmtree(self.repo_root, ignore_errors=True)

    def _cleanup_lock(self):
        try:
            os.unlink(os.path.join(self.lockdir, "holder"))
        except OSError:
            pass
        try:
            os.rmdir(self.lockdir)
        except OSError:
            pass

    def test_acquire_writes_holder_then_release_removes_lockdir(self):
        got = cm._acquire_lock(self.repo_root)
        self.assertEqual(got, self.lockdir)
        self.assertTrue(os.path.isdir(self.lockdir))
        # holder carries `pid@epoch`
        with open(os.path.join(self.lockdir, "holder")) as f:
            pid_str = f.read().split("@", 1)[0]
        self.assertEqual(int(pid_str), os.getpid())
        cm._release_lock(self.lockdir)
        self.assertFalse(os.path.exists(self.lockdir))

    def test_acquire_recovers_dead_pid_stale_lock(self):
        # Pre-create a dead-PID-held lockdir with an OLD mtime so the 2s inner
        # spin reaches stale-recovery quickly.
        os.mkdir(self.lockdir)
        holder = os.path.join(self.lockdir, "holder")
        with open(holder, "w") as f:
            f.write(f"{_dead_pid()}@{int(time.time())}")
        old = time.time() - (cm.STALE_TTL_S + 5)
        os.utime(holder, (old, old))
        # Scale the inner spin so we don't wait the full 2s before recovery.
        saved = cm.LOCK_INNER_SPIN_S
        cm.LOCK_INNER_SPIN_S = 0.05
        try:
            got = cm._acquire_lock(self.repo_root)
        finally:
            cm.LOCK_INNER_SPIN_S = saved
        self.assertEqual(got, self.lockdir)
        self.assertTrue(os.path.isdir(self.lockdir))
        cm._release_lock(self.lockdir)


# --------------------------------------------------------------------------- #
# compass — lock-identity derivation (#406 dir-scoped characterization)         #
# --------------------------------------------------------------------------- #

class CompassLockIdentityTest(unittest.TestCase):
    def test_docs_path_collapses_to_parent_for_lock(self):
        # update_many derives repo_root = dirname(abspath(path)), then collapses
        # a trailing `docs` segment to its parent (compass.py:689-693). So a
        # compass at <root>/docs/compass.md and one addressed at <root>/compass.md
        # hash the SAME lock — pin that collapse rule.
        with tempfile.TemporaryDirectory() as root:
            docs_repo_root = os.path.dirname(os.path.abspath(
                os.path.join(root, "docs", "compass.md")))
            self.assertEqual(os.path.basename(docs_repo_root), "docs")
            collapsed = os.path.dirname(docs_repo_root)
            top_repo_root = os.path.dirname(os.path.abspath(
                os.path.join(root, "compass.md")))
            self.assertEqual(collapsed, top_repo_root)
            self.assertEqual(cm._lockdir_for(collapsed),
                             cm._lockdir_for(top_repo_root))

    def test_docs_path_collapses_to_parent_in_update_many(self):
        # Drive the REAL compass.py:692-693 collapse branch end-to-end:
        # update_many on a <root>/docs/compass.md path must hash its lock at the
        # PARENT (repo root), not the docs dir. We wrap cm._acquire_lock to
        # capture the repo_root it is called with and delegate to the real
        # implementation, then assert it equals the collapsed parent. Unlike the
        # complementary unit check above (which reimplements the dirname logic),
        # deleting the collapse branch would make the captured repo_root be
        # <root>/docs and FAIL this assertEqual — so this test actually pins the
        # production branch.
        real_acquire = cm._acquire_lock
        seen = {}

        def capture(repo_root):
            seen["repo_root"] = repo_root
            return real_acquire(repo_root)

        with tempfile.TemporaryDirectory() as root:
            docs = os.path.join(root, "docs")
            os.makedirs(docs)
            path = os.path.join(docs, "compass.md")
            with mock.patch.object(cm, "_acquire_lock", side_effect=capture):
                cm.update_many([("next_move", "x", False)], path=path)
            # Collapsed to the parent of docs/, NOT docs/ itself.
            self.assertEqual(os.path.realpath(seen["repo_root"]),
                             os.path.realpath(root))
            self.assertNotEqual(os.path.basename(seen["repo_root"]), "docs")

    def test_sibling_subdir_compasses_do_NOT_share_lock_BUG_406(self):
        # CHARACTERIZATION of deferred #406 (compass.py:689): the lock identity
        # is dir-scoped (sha1 of the resolved repo_root), NOT keyed off the
        # compass file's realpath. Two compass files under different sub-dirs of
        # the same project therefore get DIFFERENT locks — concurrent writers to
        # them do not serialize against each other. Pin the current behavior;
        # #406 may revisit the lock-identity derivation.
        with tempfile.TemporaryDirectory() as root:
            a_root = os.path.dirname(os.path.abspath(
                os.path.join(root, "a", "compass.md")))
            b_root = os.path.dirname(os.path.abspath(
                os.path.join(root, "b", "compass.md")))
            self.assertNotEqual(cm._lockdir_for(a_root), cm._lockdir_for(b_root))


# --------------------------------------------------------------------------- #
# compass — real contention through the CLI, consuming the _test_sleep hook     #
# --------------------------------------------------------------------------- #

class CompassContentionTest(unittest.TestCase):
    """First consumer of the `CRUCIBLE_COMPASS_TEST_SLEEP_MS` hook (compass.py
    ships it for exactly this and no test used it). Two concurrent `update`
    subprocesses set DIFFERENT fields on the same compass; the lock must
    serialize them so BOTH writes survive — a lost write would prove the lock
    failed."""

    def setUp(self):
        self.repo_root = tempfile.mkdtemp()
        self.path = os.path.join(self.repo_root, "compass.md")
        self.lockdir = cm._lockdir_for(self.repo_root)
        # Seed the file so both writers read a real (non-bootstrap) base.
        subprocess.run(
            [sys.executable, COMPASS_SCRIPT, "update",
             "--field", "next_move", "--value", "seed", "--path", self.path],
            check=True, capture_output=True, text=True,
        )

    def tearDown(self):
        # Mirror _release_lock's order: unlink the holder file first (a crashed
        # writer would orphan it, making a bare rmdir fail silently), then rmdir.
        try:
            os.unlink(os.path.join(self.lockdir, "holder"))
        except OSError:
            pass
        try:
            os.rmdir(self.lockdir)
        except OSError:
            pass
        shutil.rmtree(self.repo_root, ignore_errors=True)

    def _update(self, field, value, results, idx):
        env = dict(os.environ)
        env["CRUCIBLE_COMPASS_TEST_SLEEP_MS"] = "300"   # hold the lock ~300ms
        r = subprocess.run(
            [sys.executable, COMPASS_SCRIPT, "update",
             "--field", field, "--value", value, "--path", self.path],
            capture_output=True, text=True, env=env, timeout=30,
        )
        results[idx] = r

    def test_concurrent_updates_serialize_both_writes_survive(self):
        results = {}
        t1 = threading.Thread(target=self._update,
                              args=("next_move", "from-writer-A", results, 0))
        t2 = threading.Thread(target=self._update,
                              args=("current_arc", "#777: from-writer-B",
                                    results, 1))
        t1.start()
        t2.start()
        t1.join(timeout=40)
        t2.join(timeout=40)
        self.assertEqual(results[0].returncode, 0, results[0].stderr)
        self.assertEqual(results[1].returncode, 0, results[1].stderr)
        # Both fields must be present — neither writer clobbered the other.
        with open(self.path, encoding="utf-8") as f:
            final = f.read()
        self.assertIn("from-writer-A", final)
        self.assertIn("from-writer-B", final)
        # The lock is released at the end (no orphan lockdir).
        self.assertFalse(os.path.exists(self.lockdir))


if __name__ == "__main__":
    unittest.main()
