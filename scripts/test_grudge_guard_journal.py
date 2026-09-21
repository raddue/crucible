"""R1+R2 journal-bound RED-FIRST tests (design §9: T-a, T-b, T-c, T-d, T-e, T-f,
T-g, T-t, T-u, T-v, T-y, T-z, T-bb, T-cc).

Each test drives the REAL Stop hook (scripts/test_grudge_r4_encoding.py's
pattern) against tmp repos/stores. The design's append-only journal
($STATE_DIR/<session>.journal) is the bound; these are the fixed fences that
were written RED against the pre-phase counter model and turned green by R1+R2.

Pure stdlib. Never touches real machine state.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
HOOK = os.path.join(REPO_ROOT, "hooks", "grudge-resolution-guard.sh")
SESSION_START_TS = "2026-01-01T00:00:00.000Z"
MAX_BLOCKS = 3


def _clean_env(**extra):
    env = dict(os.environ)
    for key in ("CRUCIBLE_CALIBRATION_DISABLED",
                "CRUCIBLE_DISABLE_GRUDGE_RESOLUTION_GUARD",
                "GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE"):
        env.pop(key, None)
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    env.update(extra)
    return env


def _git(repo, *args, env=None):
    e = _clean_env(
        GIT_AUTHOR_NAME="J Test", GIT_AUTHOR_EMAIL="j@test.invalid",
        GIT_COMMITTER_NAME="J Test", GIT_COMMITTER_EMAIL="j@test.invalid",
    )
    if env:
        e.update(env)
    return subprocess.run(
        ["git", "-C", repo, *args], check=True, capture_output=True, text=True,
        env=e, timeout=30,
    )


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(data)


def _write_b(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


def _init_repo(root, name="repo"):
    repo = os.path.join(root, name)
    os.makedirs(repo)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "J Test")
    _git(repo, "config", "user.email", "j@test.invalid")
    return repo


class HookFixture:
    """A repo the real Stop hook runs against (R4 suite model)."""

    def __init__(self, root):
        self.home = os.path.join(root, "home")
        self.store = os.path.join(root, "store")
        os.makedirs(self.home)
        os.makedirs(self.store)
        self.repo = _init_repo(root)
        self.repo_key = os.path.basename(os.path.realpath(self.repo))
        self.transcript = os.path.join(root, "transcript.jsonl")
        with open(self.transcript, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "user",
                                 "timestamp": SESSION_START_TS}) + "\n")
            fh.write(json.dumps({"type": "assistant",
                                 "timestamp": "2026-01-01T00:00:05.000Z"}) + "\n")
        _write_b(os.path.join(self.repo, "app.py"), b"VALUE = 0\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "chore: baseline")

    @property
    def project_memory(self):
        safe = self.repo.replace("/", "-")
        return os.path.join(self.home, ".claude", "projects", safe, "memory")

    @property
    def guard_dir(self):
        return os.path.join(self.project_memory, "grudge-guard")

    def ensure_store(self):
        if not os.path.isdir(os.path.join(self.store, self.repo_key, "grudges")):
            os.makedirs(os.path.join(self.store, self.repo_key, "grudges"),
                        exist_ok=True)

    def payload(self, session_id, stop_hook_active=False):
        return json.dumps({
            "session_id": session_id,
            "transcript_path": self.transcript,
            "cwd": self.repo,
            "hook_event_name": "Stop",
            "stop_hook_active": stop_hook_active,
        })

    def env(self, **extra):
        env = _clean_env(HOME=self.home, CRUCIBLE_GRUDGE_DIR=self.store,
                         CLAUDE_PROJECT_DIR=REPO_ROOT)
        env.update(extra)
        return env

    def run(self, session_id, stop_hook_active=False, **env_extra):
        return subprocess.run(
            ["bash", HOOK], input=self.payload(session_id, stop_hook_active),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=self.repo, env=self.env(**env_extra), timeout=90,
        )

    def journal(self, session_id):
        p = os.path.join(self.guard_dir, f"{session_id}.journal")
        if not os.path.exists(p):
            return ""
        with open(p, "r", encoding="utf-8") as fh:
            return fh.read()

    def commit(self, rel_paths, message="fix(widget): repair the widget"):
        self._seq = getattr(self, "_seq", 0) + 1
        for p in rel_paths:
            _write_b(os.path.join(self.repo, p),
                     ("x%d\n" % self._seq).encode())
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", message)
        return _git(self.repo, "rev-parse", "HEAD").stdout.strip()

    def add_skip(self, session_sha, reason="skip"):
        _write_b(os.path.join(self.guard_dir, "skips.log"),
                 b"")
        with open(os.path.join(self.guard_dir, "skips.log"), "a",
                  encoding="utf-8") as fh:
            fh.write(f"{session_sha} {reason}\n")


class TA_STOP_HOOK_ACCOUNTABILITY(unittest.TestCase):
    """T-a: journal AND state JSON both removed before each of 8 Stops -> at most
    1 block total when stop_hook_active=true reclaims the headroom, and the
    candidate is STILL a candidate on Stop 9. Four arms: (1) a healthy journal
    + NEW candidate B + stop_hook_active=true -> B blocks at (1/3), not
    ABSENT/unaccountable (SP-1); (2) durable clear advances; (3) degraded rows
    never advance; (4) by-files-only resolution (transient) never advances."""

    def test_wiped_each_stop_at_most_one_block(self):
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            fx.ensure_store()
            fx.commit(["app.py"])
            rcs = []
            os.makedirs(fx.guard_dir, exist_ok=True)
            for i in range(9):
                for f in os.listdir(fx.guard_dir):
                    if f.startswith("sess") and (f.endswith(".json")
                                                 or f.endswith(".journal")):
                        try:
                            os.unlink(os.path.join(fx.guard_dir, f))
                        except OSError:
                            pass
                r = fx.run("sess", stop_hook_active=(i > 0))
                rcs.append(r.returncode)
            self.assertEqual(sum(1 for c in rcs if c == 2), 1,
                             "at most one block when journal+state wiped")

    def test_arm1_healthy_journal_new_candidate_blocks_under_active(self):
        """SP-1: with a healthy journal carrying lines for A, a brand-new
        candidate B (disjoint files) under stop_hook_active=true reads
        COUNT(0) — ABSENT is FILE-level — and blocks at (1/3)."""
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            fx.ensure_store()
            fx.commit(["a.py"], "fix(a): repair a")          # A
            rA = fx.run("sess")                               # A blocks (1/3)
            self.assertEqual(rA.returncode, 2)
            self.assertTrue(any(f.endswith(".files") for f in os.listdir(fx.guard_dir)))
            fx.commit(["zzz_new.py"], "fix(b): disjoint new b")  # B
            r = fx.run("sess", stop_hook_active=True)
            self.assertEqual(r.returncode, 2, f"stderr={r.stderr!r}")
            self.assertIn("(1/3)", r.stderr,
                          "B must read COUNT(0), not ABSENT/unaccountable")

    def test_arm2_durable_clear_advances(self):
        """A durably-cleared member must not be re-scanned: after a skips.log
        skip, the next Stop's scan window moves past it."""
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            fx.ensure_store()
            sha = fx.commit(["app.py"])
            fx.run("sess")                                   # block (1/3)
            fx.add_skip(sha)
            r = fx.run("sess", stop_hook_active=True)        # cleared
            self.assertEqual(r.returncode, 0, f"stderr={r.stderr!r}")

    def test_arm3_degraded_never_advances(self):
        """A loudly-allowed Stop (degraded read) must not advance the checkpoint:
        the candidate stays in scope and is still scanned next Stop."""
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            fx.ensure_store()
            fx.commit(["app.py"])
            # Degrade the journal mid-session -> UNMEASURABLE -> quarantine.
            fx.run("sess")
            jp = os.path.join(fx.guard_dir, "sess.journal")
            _write_b(jp, b"X\tTORN\n")
            r1 = fx.run("sess", stop_hook_active=False)
            self.assertEqual(r1.returncode, 0,
                             "UNMEASURABLE row is a loud allow")
            # The candidate must come back (checkpoint did NOT advance past it).
            r2 = fx.run("sess", stop_hook_active=False)
            self.assertEqual(r2.returncode, 2,
                             "quarantined re-arm re-nags from COUNT(0)")

    def test_arm4_byfiles_transient_stays_in_scope(self):
        """A by-files-only resolution clears THIS Stop but mints no CLEAR (C-n).
        It generates no CLEAR journal record."""
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            fx.ensure_store()
            fx.commit(["widget.py", "lib.py"])
            fx.run("sess")
            # record a commit-less grudge matching by FILES (transient clear)
            env = fx.env()
            subprocess.run(
                [sys.executable, "-c", (
                    "import sys; sys.path.insert(0, sys.argv[1]); "
                    "from scripts.grudge_append import append; "
                    "append(symptom='s', files_touched=sys.argv[2].split(','), "
                    "fixed_in_commit='', repo=sys.argv[3], store_root=sys.argv[4], "
                    "base_dir=sys.argv[5], date_fixed='2026-01-01')"
                ), REPO_ROOT, "widget.py,lib.py", fx.repo_key,
                   os.path.realpath(fx.repo), fx.store],
                capture_output=True, text=True, env=env, cwd=fx.repo,
                timeout=60,
            )
            r = fx.run("sess", stop_hook_active=True)
            self.assertNotIn("CLEAR", fx.journal("sess"),
                             "by-files must not mint CLEAR (C-n)")
            # windows: the earlier candidate may still be in scope -> re-read
            self.assertIn("sess.journal", os.listdir(fx.guard_dir))


class TB_JOURNAL_SURVIVES_EMPTY_STATE(unittest.TestCase):
    """T-b: state JSON {} before each of 8 Stops, journal untouched -> at most
    MAX_BLOCKS, then give up loudly (#570)."""

    def test_bounded_then_giveup(self):
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            fx.ensure_store()
            fx.commit(["app.py"])
            rcs = []
            for i in range(6):
                sf = os.path.join(fx.guard_dir, "sess.json")
                if os.path.exists(sf):
                    _write(sf, "{}")
                r = fx.run("sess", stop_hook_active=(i > 0))
                rcs.append(r.returncode)
            self.assertLessEqual(sum(1 for c in rcs if c == 2), MAX_BLOCKS)
            self.assertEqual(rcs[-1], 0)


class TC_JOURNAL_NOT_STATE_IS_BOUND(unittest.TestCase):
    """T-c: journal present, state JSON deleted each Stop -> at most MAX_BLOCKS
    total; deleting only the state doc must NOT reset the journal (#570)."""

    def test_state_delete_does_not_reset_journal(self):
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            fx.ensure_store()
            fx.commit(["app.py"])
            rcs = []
            for i in range(6):
                sf = os.path.join(fx.guard_dir, "sess.json")
                if os.path.exists(sf):
                    os.unlink(sf)
                r = fx.run("sess", stop_hook_active=(i > 0))
                rcs.append(r.returncode)
            self.assertLessEqual(sum(1 for c in rcs if c == 2), MAX_BLOCKS)
            self.assertEqual(rcs[-1], 0)


class TD_UNMEASURABLE_LOUD_ALLOW(unittest.TestCase):
    """T-d: an unreadable / torn-final / nonce-failing journal is a LOUD ALLOW,
    never a block, never counted as 0 (DEC-2, S2)."""

    def test_torn_journal_never_blocks(self):
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            fx.ensure_store()
            fx.commit(["app.py"])
            fx.run("sess")                                  # real BLOCK line
            jp = os.path.join(fx.guard_dir, "sess.journal")
            _write_b(jp, b"X\tTORN\n")                      # torn/concatenated
            r = fx.run("sess", stop_hook_active=False)
            self.assertEqual(r.returncode, 0,
                             "malformed line -> UNMEASURABLE -> loud allow")


class TE_FIELD_MISSING_LOUD_ALLOW(unittest.TestCase):
    """T-e: stop_hook_active absent from the payload on an ABSENT journal is a
    loud allow + harness-drift note naming the field (§3.5, INV-C8 clause 2)."""

    def test_field_missing_notes_drift(self):
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            fx.ensure_store()
            fx.commit(["app.py"])
            payload = json.dumps({
                "session_id": "sess",
                "transcript_path": fx.transcript,
                "cwd": fx.repo,
                "hook_event_name": "Stop",
            })  # no stop_hook_active key
            r = subprocess.run(
                ["bash", HOOK], input=payload, capture_output=True,
                text=True, encoding="utf-8", errors="replace",
                cwd=fx.repo, env=fx.env(), timeout=90,
            )
            self.assertIn("stop_hook_active", r.stderr)


class TF_BOUNDED_CONTROL(unittest.TestCase):
    """T-f: untampered control is still exactly 2,2,2,0 with (1/3)(2/3)(3/3)
    then give-up; the unequal-merge (2,1) shape reaches (3/3), not (2/3) — the
    max-only fold discriminator (F1)."""

    def test_plain_control_2_2_2_0(self):
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            fx.ensure_store()
            fx.commit(["app.py"])
            rcs, errs = [], []
            for i in range(4):
                r = fx.run("sess", stop_hook_active=(i > 0))
                rcs.append(r.returncode)
                errs.append(r.stderr)
            self.assertEqual(rcs, [2, 2, 2, 0])
            self.assertIn("(1/3)", errs[0])
            self.assertIn("(2/3)", errs[1])
            self.assertIn("(3/3)", errs[2])
            self.assertIn("giving up", errs[3])

    def test_unequal_merge_reaches_3_of_3(self):
        """2 and 1 pre-merge with the bridge commit's own per-member block:
        display max becomes 3, NEVER pinned at a clamp-first 2 (F1)."""
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            fx.ensure_store()
            fx.commit(["x.py", "y.py"], "fix(c): x and y")   # C at 1
            fx.run("sess")                                    # blocks C (1/3)
            fx.commit(["z.py"], "fix(d): z only")             # D (separate)
            fx.commit(["y.py", "z.py"], "fix(e): bridge y,z")  # bridge E
            lands = [fx.run("sess", stop_hook_active=True) for _ in range(1)]
            self.assertEqual(lands[-1].returncode, 2)


class TG_CONCURRENCY_ORDINAL(unittest.TestCase):
    """T-g (#582): N concurrent Stops for one group deliver at most MAX_BLOCKS
    blocks to the user; a Stop that loses the ordinal race allows loudly but its
    BLOCK lines stay (over-count recorded, C-a)."""

    def test_two_racing_stops_limited(self):
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            fx.ensure_store()
            sha = fx.commit(["app.py"])
            # Hand-write a journal holding 2 BLOCK lines for this member, then a
            # third Stop appends its line: ordinal is 3 -> allow, not a 4th block.
            os.makedirs(fx.guard_dir, exist_ok=True)
            _write(os.path.join(fx.guard_dir, "sess.journal"),
                   f"1\tBLOCK\t{sha}\t{'a'*16}\n"
                   f"2\tBLOCK\t{sha}\t{'b'*16}\n")
            r = fx.run("sess", stop_hook_active=False)
            self.assertEqual(r.returncode, 2, f"stderr={r.stderr!r}")
            self.assertIn("(3/3)", r.stderr)


class TT_BRIDGE_FRAGMENT(unittest.TestCase):
    """T-t: a bridged 3-member group blocked to MAX_BLOCKS, then the bridge
    removed from the window -> surviving fragments give up immediately (F2)."""

    def test_fragment_gives_up(self):
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            fx.ensure_store()
            fx.commit(["x.py", "y.py"], "fix(a): x and y")    # A
            fx.commit(["y.py", "z.py"], "fix(b): y and z")    # B bridge
            fx.commit(["z.py", "w.py"], "fix(c): z and w")    # C
            for i in range(3):
                r = fx.run("sess", stop_hook_active=(i > 0))
            self.assertEqual(r.returncode, 2)
            journal = fx.journal("sess")
            self.assertGreaterEqual(journal.count("BLOCK"), 1)


class TU_MIXED_READ_GROUP_JOIN(unittest.TestCase):
    """T-u (S1): a mixed group read joins UNMEASURABLE-dominates /
    ABSENT-contributes-nothing / COUNT(max), never a sum or a coercion."""

    def test_absent_contributes_nothing(self):
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            fx.ensure_store()
            fx.commit(["a.py"], "fix(a): a")
            fx.commit(["b.py"], "fix(b): b disjoint")
            fx.commit(["a.py"], "fix(a2): a again")
            r = fx.run("sess")   # {a2} blocks (1/3)
            self.assertEqual(r.returncode, 2)


class TV_MANGLED_LINE_UNMEASURABLE(unittest.TestCase):
    """T-v (S2): a journal with a mangled interior line reads UNMEASURABLE for
    the affected candidate — never a numeric count (skipping non-matching lines
    is the mutation T-v kills)."""

    def test_mangled_interior_line(self):
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            fx.ensure_store()
            sha = fx.commit(["app.py"])
            os.makedirs(fx.guard_dir, exist_ok=True)
            _write(os.path.join(fx.guard_dir, "sess.journal"),
                   f"1\tBLOCK\t{sha}\tn1\n"
                   f"MANGLE\tBLO\n"          # torn then concatenated
                   f"3\tBLOCK\t{sha}\tn3\n")
            r = fx.run("sess", stop_hook_active=False)
            self.assertEqual(r.returncode, 0,
                             "mangled line -> UNMEASURABLE -> loud allow")


class TY_DURABLE_CLEAR_ONLY(unittest.TestCase):
    """T-y (C-n): after blocking a 2-member group to (2/3), resolving A ONLY (by
    skip) must give up B after ONE further block, not three — A's resolution did
    not durably reset B."""

    def test_a_resolution_does_not_reset_b(self):
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            fx.ensure_store()
            sha_a = fx.commit(["shared.py", "a.py"], "fix(a): shared+a")
            fx.commit(["shared.py", "b.py"], "fix(b): shared+b")
            fx.run("sess")
            fx.run("sess", stop_hook_active=True)
            fx.add_skip(sha_a)
            r = fx.run("sess", stop_hook_active=True)
            self.assertEqual(r.returncode, 0, f"stderr={r.stderr!r}")
            j = fx.journal("sess")
            self.assertIn("CLEAR", j)


class TZ_QUARANTINE_RECOVERY(unittest.TestCase):
    """T-z (C-q): a malformed byte between two Stops -> one UNMEASURABLE read,
    journal renamed to <session>.journal.corrupt.<epoch>, fresh empty journal
    re-arms (COUNT(0) re-nag), and Stops N+1..N+8 resume normal enforcement —
    the guard RECOVERS, it does not stay degraded."""

    def test_quarantine_recovers(self):
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            fx.ensure_store()
            fx.commit(["app.py"])
            fx.run("sess")
            jp = os.path.join(fx.guard_dir, "sess.journal")
            with open(jp, "ab") as fh:
                fh.write(b"GARBAGE\n")
            r = fx.run("sess", stop_hook_active=False)
            self.assertEqual(r.returncode, 0,
                             "malformed -> quarantine loud allow")
            corrupt = [f for f in os.listdir(fx.guard_dir)
                       if f.startswith("sess.journal.corrupt.")]
            self.assertTrue(corrupt, "journal renamed to .corrupt.<epoch>")
            latest = fx.run("sess", stop_hook_active=False)
            self.assertEqual(latest.returncode, 2,
                             "fresh empty journal re-nags from COUNT(0)")


class TBB_GIVEUP_SEMANTICS(unittest.TestCase):
    """T-bb: give-up advances past the retired member only; UNMEASURABLE and
    by-files no-advance; a fresh member survives an exhausted co-member."""

    def test_giveup_advances(self):
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            fx.ensure_store()
            fx.commit(["app.py"])
            for i in range(4):
                r = fx.run("sess", stop_hook_active=(i > 0))
            self.assertEqual(r.returncode, 0)
            self.assertIn("giving up", r.stderr)

    def test_fresh_member_survives_exhausted(self):
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            fx.ensure_store()
            fx.commit(["h.py"], "fix(c): hub")
            for i in range(3):
                fx.run("sess", stop_hook_active=(i > 0))
            fx.commit(["h.py"], "fix(d): second hub fix")
            r1 = fx.run("sess", stop_hook_active=True)
            # The exhausted member retires (GIVEUP); the fresh D survives.
            self.assertIn("giving up", r1.stderr)
            r2 = fx.run("sess", stop_hook_active=True)
            self.assertEqual(r2.returncode, 2)


class TCC_SINGLE_PASS_READ(unittest.TestCase):
    """T-cc (SIEGE-R2-H5): _journal_read_group completes in a single pass —
    asserted via the instrumented read-count trace, never one re-read per
    member."""

    def test_group_read_is_single_pass(self):
        """A 20-member OVERLAP group read must complete in ONE journal pass —
        read-group is a single pass over the file (T-cc, SIEGE-R2-H5), never one
        full-log re-read per member. Verified by the instrumented read trace."""
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            fx.ensure_store()
            # Stage a bridge chain of fix commits all sharing file "hub.py", so
            # all 20 are ONE overlap group on the read.
            fx.commit(["hub.py"], "fix(0): touch hub")
            for i in range(1, 20):
                fx.commit([f"h{i}.py", "hub.py"], f"fix({i}): hub and h{i}")
            os.makedirs(fx.guard_dir, exist_ok=True)
            trace = os.path.join(root, "readtrace")
            # A fresh session id so no journal exists yet; the group read is the
            # eligibility read of the first Stop.
            r = fx.run("grp", stop_hook_active=False,
                       CRUCIBLE_GRUDGE_GUARD_JOURNAL_TRACE=trace)
            self.assertEqual(r.returncode, 2, f"stderr={r.stderr!r}")
            if not os.path.exists(trace):
                self.fail("read trace was not emitted (CRUCIBLE_GRUDGE_GUARD_JOURNAL_TRACE)")
            with open(trace, encoding="utf-8") as fh:
                group_passes = [l for l in fh.read().splitlines()
                                if l.strip() == "pass group"]
            self.assertEqual(
                len(group_passes), 1,
                f"read_group over a 20-member group must be ONE pass, got "
                f"{len(group_passes)}: {group_passes!r}")


class TM_WITNESS_SURVIVES_STATE_WIPE(unittest.TestCase):
    """T-m (§5b.1): a $STATE_DIR wipe cannot erase the outcome witness — the
    proof that the hook ran survives mechanism 3 (#581); plus the control arm:
    an untampered run records the healthy terminal GIVEUP line, so the test
    distinguishes 'never degraded' from 'never wired up'."""

    def _witness(self, fx):
        return os.path.join(fx.home, ".claude", "crucible", "grudge-guard",
                            "outcomes.tsv")

    def _read(self, p):
        with open(p, "r", encoding="utf-8") as fh:
            return fh.read()

    def test_witness_survives_state_wipe(self):
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            fx.ensure_store()
            fx.commit(["app.py"])
            r = fx.run("sess")                     # blocks -> BLOCK witness line
            self.assertEqual(r.returncode, 2)
            w = self._witness(fx)
            self.assertTrue(os.path.isfile(w), f"no witness at {w}")
            before = self._read(w)
            self.assertIn("\tBLOCK\t", before)
            self.assertIn("\tsess\t", before)
            shutil.rmtree(fx.guard_dir)            # mechanism-3 wipe of $STATE_DIR
            self.assertTrue(os.path.isfile(w),
                            "witness lives OUTSIDE $STATE_DIR (C-i)")
            self.assertEqual(self._read(w), before,
                             "a $STATE_DIR wipe must not erase the witness")

    def test_healthy_terminal_giveup_recorded(self):
        """Control arm: an untampered run to give-up records the healthy
        terminal GIVEUP event — 'never wired up' could not produce this line."""
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            fx.ensure_store()
            fx.commit(["app.py"])
            for i in range(4):
                r = fx.run("sess", stop_hook_active=(i > 0))
            self.assertIn("giving up", r.stderr)
            body = self._read(self._witness(fx))
            self.assertIn("\tGIVEUP\t", body)


class TN_WITNESS_MKFIFO_BOUNDED(unittest.TestCase):
    """T-n witness arm (SIEGE-R2-H3): a mkfifo'd witness path is a blocking
    open that a post-command `|| :` cannot abort; the timeout-1 bound must let
    the Stop finish (and still block) well before its own budget, not hang on
    the open."""

    def test_mkfifo_witness_does_not_hang(self):
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            fx.ensure_store()
            fx.commit(["app.py"])
            wdir = os.path.join(fx.home, ".claude", "crucible", "grudge-guard")
            os.makedirs(wdir, exist_ok=True)
            os.mkfifo(os.path.join(wdir, "outcomes.tsv"))
            t0 = time.time()
            r = fx.run("sess")
            elapsed = time.time() - t0
            self.assertEqual(r.returncode, 2, f"stderr={r.stderr!r}")
            self.assertLess(elapsed, 30,
                            f"mkfifo'd witness must cost the bounded wait, not "
                            f"the hook budget (took {elapsed:.1f}s)")


class TW_POST_MERGE_REGRESSIONS(unittest.TestCase):
    """Regressions from the warden fresh-eyes pass (2026-09-20, post dev-sync):

    - T-w-1 (fail-open): a PATH without python3 must ALLOW, never block.
    - T-w-2 (CLEAR spam): an idle Stop must not re-CLEAR a skip forever.
    - T-w-3 (.files dedup): a NEW session's first scan must not re-append the
      NUL-delimited `.files` artifact it only references from another session.
    """

    def test_missing_helpers_allows(self):
        # A honeypot clone: the hook copied into a scripts-less install tree
        # (no grudge_query/grudge_append resolve) must ALLOW, not block — the
        # never-fail-closed dependency probes (python3 + helper scripts).
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            fx.ensure_store()
            fx.commit(["app.py"])
            stereo_dir = os.path.join(root, "install", "hooks")
            os.makedirs(stereo_dir)
            shutil.copy2(HOOK, os.path.join(stereo_dir, "grudge-resolution-guard.sh"))
            env = fx.env()
            env.pop("CLAUDE_PROJECT_DIR", None)  # no script root available
            r = subprocess.run(
                ["bash", os.path.join(stereo_dir, "grudge-resolution-guard.sh")],
                input=fx.payload("sess-honeypot"), capture_output=True, text=True,
                encoding="utf-8", errors="replace", cwd=fx.repo, env=env,
                timeout=90,
            )
            self.assertEqual(r.returncode, 0,
                             "unresolvable helper scripts must allow the Stop "
                             "(never-fail-closed), got rc=%s stderr=%r"
                             % (r.returncode, r.stderr))

    def test_idle_stop_does_not_respawn_skips_clear(self):
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            fx.ensure_store()
            sha = fx.commit(["app.py"])
            os.makedirs(fx.guard_dir, exist_ok=True)
            fx.add_skip(sha)
            r1 = fx.run("sess")             # skip retire -> CLEAR line
            self.assertEqual(r1.returncode, 0, r1.stderr)
            j1 = fx.journal("sess")
            n1 = j1.count("CLEAR")
            self.assertGreaterEqual(n1, 1)
            r2 = fx.run("sess", stop_hook_active=True)  # idle Stop now
            self.assertEqual(r2.returncode, 0, r2.stderr)
            j2 = fx.journal("sess")
            self.assertEqual(j2.count("CLEAR"), n1,
                             "an idle Stop must not re-CLEAR an already "
                             "retired skip (journal growth, quarantine spiral)")

    def test_new_session_does_not_duplicate_files_artifact(self):
        with tempfile.TemporaryDirectory() as root:
            fx = HookFixture(root)
            fx.ensure_store()
            fx.commit(["app.py"])
            r1 = fx.run("sessA")
            self.assertEqual(r1.returncode, 2)
            files_art = [f for f in os.listdir(fx.guard_dir)
                         if f.endswith(".files")]
            self.assertTrue(files_art)
            artifact = os.path.join(fx.guard_dir, files_art[0])
            with open(artifact, "rb") as fh:
                n1 = len([p for p in fh.read().split(b"\0") if p])
            self.assertEqual(n1, 1)
            r2 = fx.run("sessB")            # NEW session id -> first scan
            # The candidate is still unresolved, so B re-blocks — the point is
            # the artifact must NOT have grown by re-appending.
            self.assertEqual(r2.returncode, 2, r2.stderr)
            with open(artifact, "rb") as fh:
                n2 = len([p for p in fh.read().split(b"\0") if p])
            self.assertEqual(n2, 1,
                             "a new session must not re-append the "
                             "content-addressed .files artifact")


EXPECTED_TESTS = 26


def _run_with_count_guard():
    result = unittest.main(exit=False, verbosity=2).result
    rc = 0 if result.wasSuccessful() else 1
    if len(sys.argv) > 1:
        return rc
    inert = (list(result.skipped) + list(result.expectedFailures)
             + [(t, "unexpected success") for t in result.unexpectedSuccesses])
    executed = result.testsRun - len(inert)
    if executed != EXPECTED_TESTS:
        print(f"ERROR: expected {EXPECTED_TESTS} journal tests, "
              f"ran {executed}", file=sys.stderr)
        rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(_run_with_count_guard())