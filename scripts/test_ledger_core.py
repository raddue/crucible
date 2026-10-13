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


# S4 (round 7): the only roles design §9/§12 tie to a MODEL-REQ-bearing agent def.
# An out-of-scope dispatch in the round (e.g. `siege`, `quality-gate/SKILL.md:976`)
# must not silently acquire a ledger entry: the reference populator rejects any
# role outside this set rather than copying the whole round-dispatch map.
MODEL_RESOLUTION_ROLES = {
    "red-team",
    "qg-fix",
    "qg-verifier",
    "qg-judge",
}


def build_model_resolution(round_summary):
    """Reference implementation of the Task 10 populator contract.

    round_summary keys:
      roles             -> {role: [<nominal entry>, ...], ...} — the NOMINAL
                           per-dispatch entries are counted, never recorded: design
                           §9's `ran` is endpoint-reported-id|unknown and v1 has no
                           endpoint report, so every emitted entry is uniform
                           unknown/indeterminate/intent (S2, round 6)
      review_per_model  -> per_model list from consensus_query(mode="review"), or None
      review_used       -> True only when that review result was completed/partial
                           AND actually used for this round (S1, round 5); an
                               a used review whose list was not retained makes
                               the whole result `None` (S3, round 8)
                           unavailable result can carry a nonempty per_model list
      verdict_per_model -> per_model list from consensus_query(mode="verdict"), or None

    Returns the object (never `{}`); None when nothing contributed.
    """
    out = {}
    for role, entries in round_summary.get("roles", {}).items():
        # S4 (round 7): fail loud on an undeclared role rather than emitting an
        # entry design §9 never authorizes.
        if role not in MODEL_RESOLUTION_ROLES:
            raise ValueError(
                f"undeclared role {role!r} in roles map — only "
                f"{sorted(MODEL_RESOLUTION_ROLES)} may contribute")
        if not entries:
            continue
        out[role] = [
            # S2, round 6: design §9's `ran` is endpoint-reported-id|unknown and no
            # endpoint report exists in v1, so EVERY entry — including a
            # type-resolution failure (S1, round 4) — is uniform unknown/
            # indeterminate/intent. The role KEY and the array LENGTH carry the
            # attribution; the nominal pin does not.
            {"ran": "unknown", "basis": "indeterminate", "prov": "intent"}
            for _ in entries
        ]
    rm = round_summary.get("review_per_model")
    if round_summary.get("review_used") and not rm:
        # SP2 (round 15): `not rm` covers the missing list AND the EMPTY list.
        # A used review with zero recorded members is not a completed review:
        # publishing {"consensus": []} would advertise a populated reviewer key
        # while attesting no member at all - that is the data-loss branch below,
        # not a review, and it must not masquerade as one after recovery.
        # S3 (round 8): a used consensus review whose membership list was NOT
        # retained cannot be attributed. Returning a partly-sampled object here
        # (e.g. only qg-judge plus the accepted fixer) would advertise a populated
        # review record while hiding the reviewer that actually decided the
        # verdict — indistinguishable from a genuinely reviewer-free round. The
        # documented data-loss branch is therefore `None`, whole-row.
        return None
    if rm and round_summary.get("review_used"):
        # S2/S7 (round 4): config-derived ids are not endpoint-observed, so
        # EVERY consensus member is unknown/indeterminate; the array's
        # LENGTH still attests the review call's membership.
        out["consensus"] = [
            {"ran": "unknown", "basis": "indeterminate", "prov": "intent"}
            for _ in rm
        ]
    return out or None


def select_review_record(findings_root, chunk, local_round, dispatch_id):
    """Resolve the persisted review record for one round, deterministically (S4, round 13).

    A filename is not an identity: the same local round number exists under every chunk,
    and `cross-chunk` is a coordinate of its own (S4/S5, round 12). Absence, a wrong
    coordinate, or a record written by another dispatch is an error — never a silent
    pick, because a wrong pick is invisible in the emitted row.
    """
    # `findings_root` is the ACTIVE root — `<scratch>/chunk-K`, `<scratch>/cross-chunk`,
    # or `<scratch>` for a flat gate — i.e. the directory that already carries the chunk
    # coordinate and IS the linter's second root. Joining `chunk` again double-prefixed it
    # and found nothing whenever the documented caller passed the real root (F1, round 14).
    # The chunk is therefore checked from the record's own field below, never the path.
    path = os.path.join(findings_root, "round-%d-review-result.json" % local_round)
    if os.path.dirname(os.path.abspath(path)) != os.path.abspath(findings_root):
        raise ValueError("record path %s does not sit directly in the active findings "
                         "root %s" % (path, findings_root))
    try:
        with open(path) as fh:
            rec = json.load(fh)
    except FileNotFoundError:
        raise FileNotFoundError("no review record at %s" % path)
    if rec.get("chunk") != chunk or rec.get("local_round") != local_round:
        raise ValueError("record at %s carries the wrong coordinate (%r, %r)"
                         % (path, rec.get("chunk"), rec.get("local_round")))
    # Fail closed without a dispatch id (S3, round 14): a missing id is NOT a wildcard.
    # An abandoned attempt's record at the expected path would otherwise be consumed
    # silently after a checkpoint drops the in-memory dispatch bookkeeping.
    if not dispatch_id:
        raise ValueError("select_review_record needs the current dispatch id to consume "
                         "%s; refusing to accept a record without one" % path)
    if rec.get("dispatch_id") != dispatch_id:
        raise ValueError("record at %s was written by dispatch %r, not %r"
                         % (path, rec.get("dispatch_id"), dispatch_id))
    return path

MR_ENTRY = {"ran": "unknown", "basis": "indeterminate", "prov": "intent"}


class TestModelResolution(unittest.TestCase):
    """The fourteen acceptance cases, plus the persisted-record selector (S2/S4, round 13)."""

    def _row(self, **kw):
        summary = {"roles": {}, "review_per_model": None, "review_used": False,
                   "verdict_per_model": None}
        summary.update(kw)
        return build_model_resolution(summary)

    def test_case01_review_not_verdict_membership(self):
        row = self._row(review_used=True, review_per_model=["a", "b", "c"],
                        verdict_per_model=["d"])
        self.assertEqual(row, {"consensus": [MR_ENTRY] * 3})

    def test_case02_unavailable_consensus_records_no_nominal_pin(self):
        row = self._row(roles={"red-team": [{"ran": "opus", "basis": "asserted"}]})
        self.assertEqual(row, {"red-team": [MR_ENTRY]})

    def test_case03_mixed_bridged_and_failed_members(self):
        row = self._row(review_used=True,
                        review_per_model=[{"responded": True}, {"responded": True},
                                          {"responded": False}])
        self.assertEqual(row, {"consensus": [MR_ENTRY] * 3})

    def test_case04_consensus_only_round_is_non_null(self):
        row = self._row(review_used=True, review_per_model=["a"])
        self.assertIsNotNone(row)
        self.assertEqual(list(row), ["consensus"])

    def test_case05_terminal_round_only(self):
        row = self._row(roles={"red-team": [{"ran": "opus", "basis": "asserted"}]})
        self.assertEqual(list(row), ["red-team"])

    def test_case06_type_resolution_fallback(self):
        row = self._row(roles={"qg-verifier": [{"resolution_failed": True}]})
        self.assertEqual(row, {"qg-verifier": [MR_ENTRY]})

    def test_case07_alias_request_versus_response_name(self):
        row = self._row(review_used=True,
                        review_per_model=[{"model_id": "cfg-a",
                                           "reported": "endpoint-b"}])
        self.assertEqual(row["consensus"], [MR_ENTRY])

    def test_case08_unused_nonempty_list_must_not_key_the_row(self):
        row = self._row(roles={"red-team": [{"ran": "opus", "basis": "asserted"}]},
                        review_per_model=[{"failed": True}, {"failed": True}])
        self.assertEqual(list(row), ["red-team"])

    def test_case09_two_call_threshold_invents_no_judge_key(self):
        row = self._row(review_used=True, review_per_model=["a", "b", "c"],
                        verdict_per_model=["j"])
        self.assertEqual(list(row), ["consensus"])
        self.assertEqual(len(row["consensus"]), 3)

    def test_case10_look_harder_dispatch_is_not_pooled(self):
        row = self._row(review_used=True, review_per_model=["a", "b", "c"],
                        roles={"red-team": [{"ran": "opus", "basis": "asserted"}]})
        self.assertEqual(sorted(row), ["consensus", "red-team"])
        self.assertEqual(len(row["consensus"]), 3)
        self.assertEqual(len(row["red-team"]), 1)

    def test_case11_out_of_scope_role_is_rejected(self):
        with self.assertRaises(ValueError):
            self._row(roles={"siege": [{"ran": "sonnet"}]})

    def test_case12_partial_consensus_is_attempted_membership(self):
        row = self._row(review_used=True,
                        review_per_model=[{"responded": True}, {"responded": False},
                                          {"responded": True}])
        self.assertEqual(len(row["consensus"]), 3)

    def test_case13_pre_projection_join_leaves_one_qg_fix_entry(self):
        # Dispatch-level identity is asserted against the EMITTED ROW by the retained
        # gate-real script; the helper-side invariant is that the pre-projection join
        # hands it exactly the accepted fixer.
        row = self._row(roles={"qg-fix": [{"dispatch_id": "accepted"}],
                               "red-team": [{"ran": "opus", "basis": "asserted"}]})
        self.assertEqual(row["qg-fix"], [MR_ENTRY])
        self.assertEqual(len(row["qg-fix"]), 1)

    def test_case14_unattributable_used_review_is_whole_row_null(self):
        row = self._row(roles={"qg-judge": [{"ran": "sonnet"}]}, review_used=True,
                        review_per_model=None)
        self.assertIsNone(row)

    def test_selector_resolves_the_coordinate_and_rejects_collisions(self):
        # The caller passes the ACTIVE findings root — the dir that already carries the
        # chunk coordinate (F1, round 14) — so chunk-1 and cross-chunk each get their
        # own root, and a flat gate passes its root directly.
        with tempfile.TemporaryDirectory() as scratch:
            for chunk, dispatch in (("chunk-1", "d1"), ("cross-chunk", "d2")):
                root = os.path.join(scratch, chunk)
                os.makedirs(root)
                with open(os.path.join(root, "round-1-review-result.json"), "w") as fh:
                    json.dump({"chunk": chunk, "local_round": 1,
                               "dispatch_id": dispatch}, fh)
                self.assertEqual(
                    select_review_record(root, chunk, 1, dispatch),
                    os.path.join(root, "round-1-review-result.json"))
            chunk1 = os.path.join(scratch, "chunk-1")
            with self.assertRaises(ValueError):
                select_review_record(chunk1, "chunk-1", 1, "d2")   # foreign dispatch
            with self.assertRaises(FileNotFoundError):
                select_review_record(chunk1, "chunk-1", 2, "d1")   # absent round
            # S3 (round 14): a record written by an abandoned attempt must NOT be
            # consumed when the caller has no current dispatch id — no wildcard.
            stale = os.path.join(scratch, "cross-chunk")
            with open(os.path.join(stale, "round-3-review-result.json"), "w") as fh:
                json.dump({"chunk": "cross-chunk", "local_round": 3,
                           "dispatch_id": "old"}, fh)
            with self.assertRaises(ValueError):
                select_review_record(stale, "cross-chunk", 3, None)
            with self.assertRaises(ValueError):
                select_review_record(stale, "cross-chunk", 3, "old-other")
            # a flat gate keeps its record directly in the root it passes
            flat = os.path.join(scratch, "flat")
            os.makedirs(flat)
            with open(os.path.join(flat, "round-1-review-result.json"), "w") as fh:
                json.dump({"chunk": "solo", "local_round": 1,
                           "dispatch_id": "d9"}, fh)
            self.assertEqual(select_review_record(flat, "solo", 1, "d9"),
                             os.path.join(flat, "round-1-review-result.json"))

if __name__ == "__main__":
    unittest.main()
