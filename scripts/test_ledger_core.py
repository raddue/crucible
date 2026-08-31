#!/usr/bin/env python3
"""Phase 1 (#398) — pure-core unit tests for ledger_append.

The ledger is "the epistemic backbone" (CLAUDE.md): every Tier-A verdict and
every calibration-weighted dispatch reads it. A silent regression in
append/dedup/truncation corrupts the corpus all gating decisions trust.

Covers ledger_append's deterministic, IO-light core: caller_dedup (L-2),
_truncate_payload (L-8), append against a tmp store (success / kill-switch
no-op / oversize rejection / truncation + sidecar), valid_ledger_identity
(#408 F9), and default_repo's symlink-safe realpath (#401). The lock state
machine + crash recovery are Phase 2 (test_locks.py).

ledger_reduce's and reconcile_ledger's pure-core coverage moved to
raddue/crucible-eval with those modules (#460) — this file now covers only
the Crucible-resident ledger_append surface.

Pure stdlib `unittest`. Machine-local central store is NEVER touched — every
case writes to a tmp dir (the pure functions take explicit paths; append() is
pointed at a tmp ledger_path). No git, no subprocess.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts import ledger_append as la  # noqa: E402


# --------------------------------------------------------------------------- #
# ledger_append — caller_dedup (L-2)                                          #
# --------------------------------------------------------------------------- #

class CallerDedupTest(unittest.TestCase):
    def _write(self, path, rows):
        with open(path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    def test_missing_file_is_not_dup(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(la.caller_dedup(os.path.join(d, "nope.jsonl"),
                                             "r1", "siege"))

    def test_match_on_run_id_and_skill(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            self._write(p, [{"run_id": "r1", "skill": "siege"}])
            self.assertTrue(la.caller_dedup(p, "r1", "siege"))

    def test_same_run_id_different_skill_is_not_dup(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            self._write(p, [{"run_id": "r1", "skill": "siege"}])
            # (run_id, skill) is the composite identity — skill must match too.
            self.assertFalse(la.caller_dedup(p, "r1", "delve"))

    def test_malformed_and_blank_lines_skipped_not_fatal(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            with open(p, "w", encoding="utf-8") as f:
                f.write("\n")
                f.write("{ not json\n")
                f.write(json.dumps({"run_id": "r1", "skill": "siege"}) + "\n")
            self.assertTrue(la.caller_dedup(p, "r1", "siege"))
            self.assertFalse(la.caller_dedup(p, "rX", "siege"))


# --------------------------------------------------------------------------- #
# ledger_append — _truncate_payload (L-8)                                     #
# --------------------------------------------------------------------------- #

class TruncatePayloadTest(unittest.TestCase):
    def test_gated_files_truncated_with_overflow_returned(self):
        entry = {"gated_files": [f"f{i}.py" for i in range(10)]}
        out, overflow = la._truncate_payload(entry, max_gated_files=3,
                                              max_highest_finding_chars=256)
        self.assertEqual(out["gated_files"], ["f0.py", "f1.py", "f2.py"])
        self.assertEqual(out["gated_files_truncated"], 7)
        self.assertEqual(len(overflow), 10)   # full original list for the sidecar

    def test_under_cap_sets_truncated_zero_no_overflow(self):
        entry = {"gated_files": ["a.py", "b.py"]}
        out, overflow = la._truncate_payload(entry, max_gated_files=500,
                                              max_highest_finding_chars=256)
        self.assertEqual(out["gated_files_truncated"], 0)
        self.assertIsNone(overflow)

    def test_highest_finding_clamped(self):
        entry = {"highest_finding": "x" * 1000}
        out, _ = la._truncate_payload(entry, max_gated_files=500,
                                      max_highest_finding_chars=256)
        self.assertEqual(len(out["highest_finding"]), 256)

    def test_does_not_mutate_input(self):
        entry = {"gated_files": [f"f{i}.py" for i in range(10)]}
        la._truncate_payload(entry, max_gated_files=3, max_highest_finding_chars=256)
        self.assertEqual(len(entry["gated_files"]), 10)   # original untouched


# --------------------------------------------------------------------------- #
# ledger_append — append() against a tmp ledger (no lock contention here)     #
# --------------------------------------------------------------------------- #

def _save_kill_switch():
    """Pop CRUCIBLE_CALIBRATION_DISABLED and return its prior value (or None)."""
    return os.environ.pop("CRUCIBLE_CALIBRATION_DISABLED", None)


def _restore_kill_switch(saved):
    """UNCONDITIONAL restore: always clear the var first, then re-set it only if
    it was present at setUp. The non-leak guarantee holds ONLY for the classes
    that call these helpers in setUp/tearDown (AppendTest, ReconcileTest,
    ReconcilePredicatesTest) — it is not a whole-file property. For those classes,
    on a clean checkout `saved` is None, so a test that set the var to "1" can NOT
    leak it to a sibling test or out of the process.
    """
    os.environ.pop("CRUCIBLE_CALIBRATION_DISABLED", None)
    if saved is not None:
        os.environ["CRUCIBLE_CALIBRATION_DISABLED"] = saved


# NOTE (kill-switch guard scope): classes that never reach _ledger_append do NOT
# need the setUp/tearDown above and intentionally omit it (ComputeBrierTest,
# HashAndLoadTest are pure read/compute). If a future case in ANY such class
# starts appending to a ledger (directly or via reconcile/reconcile_predicates),
# it MUST adopt the _save_kill_switch/_restore_kill_switch guard, or it will go
# RED under an ambient CRUCIBLE_CALIBRATION_DISABLED=1.


class AppendTest(unittest.TestCase):
    def setUp(self):
        # Kill-switch must be OFF for the happy-path cases.
        self._saved = _save_kill_switch()

    def tearDown(self):
        _restore_kill_switch(self._saved)

    def _last_line(self, path):
        with open(path, "rb") as f:
            return json.loads(f.read().splitlines()[-1])

    def test_append_writes_one_jsonl_line(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            self.assertTrue(la.append(p, {"run_id": "r1", "skill": "siege"}))
            obj = self._last_line(p)
            self.assertEqual(obj["run_id"], "r1")
            self.assertEqual(obj["skill"], "siege")

    def test_append_is_append_only(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            la.append(p, {"run_id": "r1", "skill": "siege"})
            # Snapshot the FIRST line's exact bytes after the first append.
            with open(p, "rb") as f:
                first_after_one = f.read().splitlines()[0]
            la.append(p, {"run_id": "r2", "skill": "delve"})
            with open(p, "rb") as f:
                lines = [ln for ln in f.read().splitlines() if ln.strip()]
            self.assertEqual(len(lines), 2)   # L-1: never rewrites a prior line
            # L-1 (the real guarantee): the prior line is byte-for-byte untouched.
            self.assertEqual(lines[0], first_after_one)

    def test_kill_switch_is_noop_returns_false(self):
        os.environ["CRUCIBLE_CALIBRATION_DISABLED"] = "1"
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            self.assertFalse(la.append(p, {"run_id": "r1", "skill": "siege"}))
            # L-6: no file created, no lock acquired.
            self.assertFalse(os.path.exists(p))

    def test_lock_released_after_append(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            la.append(p, {"run_id": "r1", "skill": "siege"})
            self.assertFalse(os.path.exists(os.path.join(d, la.LOCK_DIRNAME)))

    def test_oversize_after_truncation_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            # A single highest_finding under the char-cap but a payload that
            # blows the byte-cap: force rejection via a tiny max_line_bytes.
            ok = la.append(p, {"run_id": "r1", "skill": "siege",
                               "blob": "x" * 1000}, max_line_bytes=50)
            self.assertFalse(ok)
            # Oversize rejection returns BEFORE _acquire_lock, so no lock is ever
            # created (asserting "release" here would be vacuous — nothing was
            # acquired). The intent-precise invariant: no ledger file was created
            # and no lock dir exists. (We assert exactly that, not whole-dir
            # emptiness, which would couple to append's internal validation
            # ordering. Real lock-release-after-contention coverage is Phase 2 /
            # test_locks.py.)
            self.assertFalse(os.path.exists(p))
            self.assertFalse(os.path.exists(os.path.join(d, la.LOCK_DIRNAME)))

    def test_truncation_writes_overflow_sidecar(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            ok = la.append(p, {"run_id": "r1", "skill": "siege",
                               "gated_files": [f"f{i}.py" for i in range(600)]},
                           max_gated_files=500)
            self.assertTrue(ok)
            obj = self._last_line(p)
            self.assertEqual(len(obj["gated_files"]), 500)
            self.assertEqual(obj["gated_files_truncated"], 100)
            sidecar = os.path.join(d, "overflow", "r1.siege.txt")
            self.assertTrue(os.path.exists(sidecar))
            with open(sidecar) as f:
                self.assertEqual(len(f.read().splitlines()), 600)

    def test_oversize_rejection_writes_no_sidecar(self):
        # S-3: sidecar I/O is deferred until AFTER the size check, so a rejected
        # oversize append must not leak an orphan sidecar.
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            ok = la.append(p, {"run_id": "r1", "skill": "siege",
                               "gated_files": [f"f{i}.py" for i in range(600)]},
                           max_gated_files=500, max_line_bytes=50)
            self.assertFalse(ok)
            self.assertFalse(os.path.exists(os.path.join(d, "overflow",
                                                         "r1.siege.txt")))

    # ----------------------------------------------------------------------- #
    # #402 identity rejection — an entry lacking a non-empty string run_id OR  #
    # skill has no join key (ledger_entry_hash collapses to the shared         #
    # "unknown" bucket, colliding across repos in the central store). append() #
    # is the chokepoint: refuse + warn rather than write an identity-less row. #
    # ----------------------------------------------------------------------- #

    def _assert_refused_clean(self, d, p):
        # A refused append writes NOTHING and leaves NO lock — same contract as
        # the kill-switch / oversize rejections above.
        self.assertFalse(os.path.exists(p))
        self.assertFalse(os.path.exists(os.path.join(d, la.LOCK_DIRNAME)))

    def test_append_refuses_missing_run_id(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            self.assertFalse(la.append(p, {"skill": "siege"}))
            self._assert_refused_clean(d, p)

    def test_append_refuses_missing_skill(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            self.assertFalse(la.append(p, {"run_id": "r1"}))
            self._assert_refused_clean(d, p)

    def test_append_refuses_empty_run_id(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            self.assertFalse(la.append(p, {"run_id": "", "skill": "siege"}))
            self._assert_refused_clean(d, p)

    def test_append_refuses_whitespace_only_skill(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            self.assertFalse(la.append(p, {"run_id": "r1", "skill": "   "}))
            self._assert_refused_clean(d, p)

    def test_append_refuses_nonstring_identity(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            # a non-string run_id (e.g. a dict/int from a malformed emitter) has
            # no stable join key — refuse rather than coerce.
            self.assertFalse(la.append(p, {"run_id": 123, "skill": "siege"}))
            self._assert_refused_clean(d, p)


# --------------------------------------------------------------------------- #
# ledger_append.valid_ledger_identity (#408 F9) + default_repo realpath (#401) #
# --------------------------------------------------------------------------- #

class ValidLedgerIdentityTest(unittest.TestCase):
    """The (run_id, skill) join-identity guard, factored out of the ×5 inlined
    copies in reconcile_ledger / render_ledger (#408 F9)."""

    def test_both_present_is_valid(self):
        self.assertTrue(la.valid_ledger_identity(
            {"run_id": "r1", "skill": "siege"}))

    def test_missing_or_empty_or_nonstring_is_invalid(self):
        for e in (
            {"skill": "siege"},                       # no run_id
            {"run_id": "r1"},                         # no skill
            {"run_id": "", "skill": "siege"},         # empty run_id
            {"run_id": "r1", "skill": "   "},         # whitespace skill
            {"run_id": 123, "skill": "siege"},        # non-string run_id
            {},                                       # neither
        ):
            self.assertFalse(la.valid_ledger_identity(e), e)


class DefaultRepoRealpathTest(unittest.TestCase):
    """#401: default_repo realpaths before taking the basename, so a repo reached
    via a symlink yields the same label the grudge store derives."""

    def test_symlinked_dir_resolves_to_real_basename(self):
        with tempfile.TemporaryDirectory() as d:
            real = os.path.join(d, "realrepo")
            os.mkdir(real)
            link = os.path.join(d, "linked")
            os.symlink(real, link)
            # Not a git repo → falls back to realpath(abspath(base)) basename.
            self.assertEqual(la.default_repo(start_dir=link), "realrepo")


# --------------------------------------------------------------------------- #
# #400 corruption surfacing: tolerant readers count unparseable lines and warn #
# ONCE per read (a torn central store of thousands of lines → one summary line,#
# not thousands). The skip behavior itself is unchanged (characterization).    #
# --------------------------------------------------------------------------- #

class TolerantReaderWarnTest(unittest.TestCase):
    def _capture_stderr(self, fn):
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            result = fn()
        return result, buf.getvalue()

    def test_caller_dedup_warns_on_corrupt_lines(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            with open(p, "w") as f:
                f.write("{broken\n")
                f.write(json.dumps({"run_id": "r1", "skill": "siege"}) + "\n")
            found, err = self._capture_stderr(
                lambda: la.caller_dedup(p, "r1", "siege"))
            self.assertTrue(found)                    # good line still matched
            self.assertIn("skipped 1", err)


if __name__ == "__main__":
    unittest.main()
