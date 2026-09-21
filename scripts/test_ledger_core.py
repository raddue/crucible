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
    that call these helpers in setUp/tearDown (AppendTest, TierNullSemanticsTest)
    — it is not a whole-file property. For those classes, on a clean checkout
    `saved` is None, so a test that set the var to "1" can NOT leak it to a
    sibling test or out of the process.
    """
    os.environ.pop("CRUCIBLE_CALIBRATION_DISABLED", None)
    if saved is not None:
        os.environ["CRUCIBLE_CALIBRATION_DISABLED"] = saved


# NOTE (kill-switch guard scope): classes that never reach _ledger_append do NOT
# need the setUp/tearDown above and intentionally omit it (CallerDedupTest,
# TruncatePayloadTest, ValidLedgerIdentityTest, DefaultRepoRealpathTest,
# TolerantReaderWarnTest, Uuid7Test are pure read/compute). If a future case in
# ANY such class starts appending to a ledger, it MUST adopt the
# _save_kill_switch/_restore_kill_switch guard, or it will go RED under an
# ambient CRUCIBLE_CALIBRATION_DISABLED=1.


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

    # ----------------------------------------------------------------------- #
    # S1 (round-4 quality-gate): the L-8 DEFAULT caps (max_line_bytes=16384,   #
    # max_gated_files=500, max_highest_finding_chars=256) had zero coverage   #
    # exercising the defaults — every case above passes an explicit override. #
    # These three call append() with NO cap kwargs at all.                    #
    # ----------------------------------------------------------------------- #

    def test_default_gated_files_cap_truncates_at_500(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            ok = la.append(p, {"run_id": "r1", "skill": "siege",
                               "gated_files": [f"f{i}.py" for i in range(501)]})
            self.assertTrue(ok)
            obj = self._last_line(p)
            self.assertEqual(len(obj["gated_files"]), 500)
            self.assertEqual(obj["gated_files_truncated"], 1)

    def test_default_highest_finding_cap_truncates_at_256(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            ok = la.append(p, {"run_id": "r1", "skill": "siege",
                               "highest_finding": "x" * 300})
            self.assertTrue(ok)
            obj = self._last_line(p)
            self.assertEqual(len(obj["highest_finding"]), 256)

    def test_default_line_bytes_cap_rejects_oversize_no_sidecar(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            ok = la.append(p, {"run_id": "r1", "skill": "siege",
                               "comment": "x" * 20000})
            self.assertFalse(ok)
            self.assertFalse(os.path.exists(p))
            self.assertFalse(os.path.exists(os.path.join(d, "overflow")))


# --------------------------------------------------------------------------- #
# ledger_append.valid_ledger_identity (#408 F9) + default_repo realpath (#401) #
# --------------------------------------------------------------------------- #

class ValidLedgerIdentityTest(unittest.TestCase):
    """The (run_id, skill) join-identity guard, factored out of the ×5 inlined
    copies in reconcile_ledger / render_ledger (moved to raddue/crucible-eval,
    #460) (#408 F9)."""

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

    def test_caller_dedup_skips_non_dict_json_line(self):
        # #400/L-9: a valid-JSON-but-non-object line (e.g. `[1,2,3]`) has no
        # `.get` — must be treated as corruption, not raise AttributeError.
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            with open(p, "w") as f:
                f.write(json.dumps([1, 2, 3]) + "\n")
                f.write(json.dumps({"run_id": "r1", "skill": "siege"}) + "\n")
            found, err = self._capture_stderr(
                lambda: la.caller_dedup(p, "r1", "siege"))
            self.assertTrue(found)                    # good line still matched
            self.assertIn("skipped 1", err)


# --------------------------------------------------------------------------- #
# ledger_append — Tier-B null semantics — restored from                       #
# eval/calibration-ledger/test-stub-reader-t7.py (moved to                    #
# raddue/crucible-eval, #460 with the rest of that eval harness). T-7's       #
# reader-tolerance assertions moved with it; these 2 writer-side assertions   #
# pin what append() itself must preserve.                                     #
# --------------------------------------------------------------------------- #

class TierNullSemanticsTest(unittest.TestCase):
    """Tier-B stub entries carry the calibration keys PRESENT with value null
    (not absent); Tier-A entries carry tier=="A" plus a dict
    severity_histogram. Still mandated verbatim by shared/ledger-append.md's
    "Tier-B null semantics" rule and by 3 surviving SKILL.md files."""

    _NULL_KEYS = (
        "severity_histogram", "highest_finding",
        "would_have_shipped_without_gate", "findings_count",
        "confidence", "chunk_hash", "rounds", "predicted_falsifier",
    )

    def setUp(self):
        # Kill-switch must be OFF for the happy-path cases.
        self._saved = _save_kill_switch()

    def tearDown(self):
        _restore_kill_switch(self._saved)

    def _tier_b(self, run_id, skill):
        return {
            "run_id": run_id, "skill": skill, "tier": "B",
            "confidence": None, "findings_count": None,
            "severity_histogram": None, "highest_finding": None,
            "would_have_shipped_without_gate": None, "rounds": None,
            "chunk_hash": None, "comment": None,
            "predicted_falsifier": None,
        }

    def _tier_a(self, run_id, skill):
        return {
            "run_id": run_id, "skill": skill, "tier": "A",
            "confidence": 0.9, "findings_count": 0,
            "severity_histogram": {"fatal": 0, "significant": 0, "minor": 0, "nit": 0},
            "would_have_shipped_without_gate": False, "rounds": 1,
        }

    def test_tier_b_calibration_keys_present_and_null(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            self.assertTrue(la.append(p, self._tier_b("r-rt", "red-team")))
            with open(p, encoding="utf-8") as f:
                obj = json.loads(f.readline())
            for k in self._NULL_KEYS:
                self.assertIn(k, obj)
                self.assertIsNone(obj[k])

    def test_tier_a_has_tier_and_dict_histogram(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "runs.jsonl")
            self.assertTrue(la.append(p, self._tier_a("r-qg", "quality-gate")))
            with open(p, encoding="utf-8") as f:
                obj = json.loads(f.readline())
            self.assertEqual(obj.get("tier"), "A")
            self.assertIsInstance(obj.get("severity_histogram"), dict)


# --------------------------------------------------------------------------- #
# scripts/uuid7.py — restored from                                            #
# eval/calibration-ledger/test-concurrency-t1.py::test_uuid7_sub (moved to    #
# raddue/crucible-eval, #460). That file's other 7 assertion groups covered   #
# ledger_append: groups 1-4 (real subprocess.Popen lock contention on one     #
# runs.jsonl) are restored as LedgerContentionTest in scripts/test_locks.py;  #
# groups 5-7 (stale-recovery branches: alive/dead/malformed holder) were      #
# already covered there by LedgerStaleRecoveryTest / LedgerAcquireLockTest.   #
# This is the only executable exercise of uuid7 left in this repo.           #
# --------------------------------------------------------------------------- #

class Uuid7Test(unittest.TestCase):
    def test_unique_version_and_monotone_timestamps(self):
        from scripts.uuid7 import uuid7
        vals = [uuid7() for _ in range(1000)]
        self.assertEqual(len(set(vals)), 1000)                       # T-1.8
        self.assertTrue(all(v[14] == "7" for v in vals))              # version nibble
        # Timestamps live in the first 12 hex chars (48 bits, big-endian).
        ts_ints = [int(v.replace("-", "")[:12], 16) for v in vals]
        self.assertTrue(all(ts_ints[i] <= ts_ints[i + 1]
                             for i in range(len(ts_ints) - 1)))


if __name__ == "__main__":
    unittest.main()
