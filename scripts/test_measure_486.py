#!/usr/bin/env python3
"""Stdlib unittest suite for scripts/measure_486_corpus.py.

Narrow by design. The three real corpora are machine-local and gitignored, so what CI
can pin is not their figures but (a) the script's behaviour on a corpus that has gone
wrong and (b) the committed-file facts #486 publishes:

  * **Crash-resistance.** Every reachable way a corpus entry can be unmeasurable must
    produce a NAMED outcome, never a traceback. One test per reachable class rather
    than one representative — copied from `test_measure_474.py:66-147`, where that
    guard was wrong twice (the round-3 fix wrapped the parse but left the READ one line
    above the try). The classes: an absent corpus directory, a non-UTF-8 file matching
    the receipt glob, a directory matching it, an unreadable file, a receipt a Tier-1
    rule rejects, a witness timeout, and — added round-1/C3-R1-F1, the one reachable
    class this enumeration used to omit — an ENUMERATED MEMBER ABSENT FROM DISK.
  * **Denominator visibility.** `measured + skipped == receipts` on every one of those
    inputs, so a rejected or unreadable receipt cannot quietly shrink the denominator
    criteria 1, 12 and 13 are computed over. The script already commits to this in
    prose (`tier1-rejects 1 … individually accounted for`); this pins the claim. Round-1
    adds the other half: a corpus that has LOST members is exit 1, never a full set of
    figures at exit 0, and every figure carries `computed-over=` — the count its pass
    actually measured — beside the constant enumeration size `n=`.
  * **Committed-file figures (round-1/C3-R1-S3).** The gated half of the #474 split
    #486 was missing: the six `two-root-*` fixture rows, their root/expect/strict
    triples, and the linter's `_MULTI_ROOT_FIXTURE_IDS` presence guard. See
    `TestCommittedFiguresAreGated`.

The witness-timeout class is separate and carries three assertions rather than one
(#486 plan round-4/SIG-3): a timeout must land on `skipped` with reason
`witness-timeout`, force a **non-zero exit**, and never appear as a disposition or
inside a published counter. `WitnessTimeout` is a `LintError` SUBCLASS, so a bare
`except rv.LintError` silently converts it into a disposition indistinguishable from a
real lint failure. Without an executing owner that rule is prose, and the swallow
reappears on the first refactor.

**The one non-obvious mechanic.** `main()` calls `measure_486_corpus.load_rcpt_verify()`
itself and gets its OWN `rcpt_verify` module instance, so patching this file's import of
`rcpt_verify` would NOT reach it. Tests that need a patched `rv` wrap `m.load_rcpt_verify`
instead (`_patch_rv` below). Synthetic corpora are registered the same way, into the
module-level `m.CORPORA` dict — both hooks exist in the script for this suite.

Run from repo root:  python3 scripts/test_measure_486.py
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

SCRIPT = pathlib.Path(__file__).resolve().parent / "measure_486_corpus.py"


def _import_m486():
    spec = importlib.util.spec_from_file_location("measure_486", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


H64 = "ab" * 32

# `/(a+)+$/` against a non-matching body is the catastrophic-backtracking pair the
# gated rcpt_verify suite already uses (`test_rcpt_verify.py:1905-1906`).
CATASTROPHIC = "/(a+)+$/"
CATASTROPHIC_BODY = "a" * 34 + "b\n"


def _receipt(witness, artifacts=None, trace=None, verdict="FAIL"):
    """A lint-shaped receipt. Same helper shape as `test_measure_474.py:43-54`."""
    artifacts = artifacts or [("findings.md", H64, "100")]
    trace = trace or [f"WROTE  findings.md  sha256:{H64}"]
    art = "".join(f"  {n}  sha256:{h}  {s}\n" for n, h, s in artifacts)
    tr = "".join(f"  {i}  {t}\n" for i, t in enumerate(trace, 1))
    return (f"RCPT v1 red-team/9-devils-advocate\n"
            f"VERDICT  {verdict}  conf=0.90\n"
            f"ARTIFACTS\n{art}"
            f"TRACE\n{tr}"
            f"CLAIMS\n"
            f"  (none)\n"
            f"WITNESS    {witness}\n"
            f"SUSPICION  0.10\n"
            f"NEXT       (none)\n")


# Rejected by a Tier-1 rule: `expect-fail=match` on a RANGELESS grep payload. Receipts
# of exactly this shape sit in real as-returned corpora written before the rule landed —
# `codegate22`'s `r3/probe/fakecorpus/rcpt-99` is one, and it is the receipt the pinned
# `tier1-rejects 1` counts.
REJECTED = _receipt("grep:findings.md  pattern=/significant=[1-9]/  "
                    "expect-fail=match  ran=TRACE#1")
MEASURABLE = _receipt("grep:findings.md#L1-L1  pattern=/significant=[1-9]/  "
                      "expect-fail=match  ran=TRACE#1")


class _SyntheticCorpus(unittest.TestCase):
    """Registers a synthetic corpus into the script's module-level CORPORA dict and
    drives `main()` over it with stdout captured. A fresh module per test, so the
    registration cannot leak between cases."""

    def setUp(self):
        self.m = _import_m486()
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = pathlib.Path(self._td.name)
        self.corpus_dir = self.tmp / "corpus"
        self.corpus_dir.mkdir()
        self.root = self.tmp / "root"
        self.root.mkdir()

    def _patch_rv(self, **attrs):
        """Inject a pre-patched `rcpt_verify` into the instance `main()` loads."""
        real = self.m.load_rcpt_verify

        def loader():
            rv = real()
            for k, v in attrs.items():
                setattr(rv, k, v)
            return rv

        self.m.load_rcpt_verify = loader

    def _run(self, names, expect_size=None):
        root = self.root
        self.m.CORPORA["synthetic"] = self.m.Corpus(
            "synthetic", self.corpus_dir, names,
            "synthetic tempdir corpus supplied by test_measure_486.py",
            lambda: ([root], [root], []))
        n = len(names) if expect_size is None else expect_size
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = self.m.main(["--corpus", "synthetic", "--expect-size", str(n)])
        return rc, out.getvalue()

    def assertAccounted(self, out, receipts, measured, skipped):
        """`measured + skipped == receipts`, and the script says so itself."""
        self.assertIn(f"receipts={receipts} measured={measured} skipped={skipped}", out)
        self.assertNotIn("ACCOUNTING BROKEN", out)
        self.assertEqual(measured + skipped, receipts)


class TestUnmeasurableInputsAreNamedNotRaised(_SyntheticCorpus):
    """One test per reachable class. `main()` returning an int at all is the
    crash-resistance assertion — a traceback propagates out of `redirect_stdout`."""

    def test_an_absent_corpus_directory_is_a_named_skip(self):
        # The whole corpus is machine-local and gitignored, so absence is the CI case.
        self.corpus_dir = self.tmp / "does-not-exist"
        rc, out = self._run(["rcpt-1-asreturned.txt"])
        self.assertEqual(rc, 1)
        self.assertIn("SKIP: corpus directory absent", out)
        self.assertAccounted(out, 1, 0, 1)

    def test_a_non_utf8_corpus_file_is_skipped_not_raised(self):
        # UnicodeDecodeError is a ValueError, NOT an OSError — an `except OSError`
        # alone would leave this one crashing.
        (self.corpus_dir / "rcpt-97-asreturned.txt").write_bytes(
            b"RCPT v1 x/1\n\xff\xfe\n")
        rc, out = self._run(["rcpt-97-asreturned.txt"])
        self.assertEqual(rc, 0)
        self.assertIn("SKIPPED  rcpt-97-asreturned.txt: UnicodeDecodeError", out)
        self.assertAccounted(out, 1, 0, 1)

    def test_a_directory_matching_the_receipt_glob_is_skipped_not_raised(self):
        # `rcpt-*-asreturned.txt` is a glob; nothing stops a directory from matching it.
        (self.corpus_dir / "rcpt-96-asreturned.txt").mkdir()
        rc, out = self._run(["rcpt-96-asreturned.txt"])
        self.assertEqual(rc, 0)
        self.assertIn("SKIPPED  rcpt-96-asreturned.txt: IsADirectoryError", out)
        self.assertAccounted(out, 1, 0, 1)

    def test_an_unreadable_corpus_file_is_skipped_not_raised(self):
        p = self.corpus_dir / "rcpt-95-asreturned.txt"
        p.write_text(MEASURABLE)
        p.chmod(0o000)
        self.addCleanup(p.chmod, 0o600)
        if os.access(p, os.R_OK):       # root ignores the mode bits
            self.skipTest("running as a user that can read a 0o000 file")
        rc, out = self._run(["rcpt-95-asreturned.txt"])
        self.assertEqual(rc, 0)
        self.assertIn("SKIPPED  rcpt-95-asreturned.txt: PermissionError", out)
        self.assertAccounted(out, 1, 0, 1)

    def test_a_tier1_rejected_receipt_is_named_and_individually_accounted(self):
        # NOT a skip: it is measured, named, and kept OUT of every counter (D8.2
        # sub-decision 6 — reported as unmeasured, never as a zero). The bug this
        # pins is the ordering one: parsing the sections before `lint_receipt`
        # attributes the rejection to "unparseable" and drops the receipt, which on
        # `codegate22` silently turns the pinned `tier1-rejects 1` into 0.
        (self.corpus_dir / "rcpt-99-asreturned.txt").write_text(REJECTED)
        rc, out = self._run(["rcpt-99-asreturned.txt"])
        self.assertEqual(rc, 0)
        self.assertIn("tier1-reject  rcpt-99-asreturned.txt", out)
        self.assertIn("requires a ranged grep payload", out)   # names the rule
        self.assertAccounted(out, 1, 1, 0)
        self.assertIn("(of which tier1-rejected 1)", out)

    def test_a_tier1_rejects_entries_are_reported_as_unmeasured_not_bucketed(self):
        # The other half of sub-decision 6, and the reconciliation the plan's
        # `tier1-rejects` row governs: the entries are PRINTED with the bucket they
        # would have taken, so a two-instrument difference stays diagnosable instead
        # of being silently folded into a counter.
        (self.corpus_dir / "rcpt-99-asreturned.txt").write_text(REJECTED)
        _, out = self._run(["rcpt-99-asreturned.txt"])
        self.assertIn("unmeasured entry  findings.md", out)
        self.assertIn("NOT counted above", out)


class TestFdLeakGuardSurvivesABuildRaise(unittest.TestCase):
    """R2 finding on the first fix attempt for the temper-R1 fd-leak finding (scoped
    re-temper, warden 2026-08-31T-563-warden-r2). `_build_identity_cache` now opens and
    HOLDS a real fd per resolved name; `measure_receipt`'s first fix bound `cache` to
    `_cache_for(...)`'s RETURN value, which is only produced on `_build_identity_cache`'s
    own success — an exception from inside it (e.g. `WitnessTimeout` mid-resolve;
    UNREACHABLE TODAY by policy, per this module's docstring, but the defensive shape
    must not silently depend on that staying true) left `cache` unbound to whatever the
    dict already held, so every fd already opened for names resolved before the raise
    was unreachable to any cleanup. Fixed by creating `cache = {}` in `measure_receipt`'s
    own frame and passing it BY REFERENCE into `_build_identity_cache`, inside the `try`
    whose `finally` always closes it — the same pattern `rcpt_verify.py`'s own
    `_selftest_run_fixture` uses for this exact hazard."""

    def test_fds_opened_before_a_build_raise_are_still_closed(self):
        m = _import_m486()
        rv = m.load_rcpt_verify()
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "f.md").write_bytes(b"hi")
            h = hashlib.sha256(b"hi").hexdigest()
            text = _receipt(
                "grep:f.md#L1-L1  pattern=/x/  expect-fail=match  ran=TRACE#1",
                artifacts=[("f.md", h, "2")], trace=[f"WROTE  f.md  sha256:{h}"],
                verdict="PASS")

            real_build = rv._build_identity_cache
            leaked = []

            def spy_build(artifacts, trace, witnesses, verdict, roots, cache):
                # A real name resolves and its fd is genuinely opened and held, exactly
                # as `_resolve_once` does — THEN the call raises before returning, as a
                # mid-resolve `WitnessTimeout` would.
                real_build(artifacts, trace, witnesses, verdict, roots, cache)
                leaked.append(cache["f.md"]["fd"])
                raise rv.WitnessTimeout("synthetic mid-build timeout")

            with mock.patch.object(rv, "_build_identity_cache", spy_build):
                with self.assertRaises(rv.WitnessTimeout):
                    m.measure_receipt(rv, text, [root], False)

            self.assertEqual(len(leaked), 1)
            self.assertIsNotNone(leaked[0])
            # The fd must have been closed by `measure_receipt`'s `finally`, not merely
            # dropped: a second close on the same (now-invalid) fd number raises EBADF.
            with self.assertRaises(OSError):
                os.close(leaked[0])


class TestWitnessTimeoutIsANamedStopNotADisposition(_SyntheticCorpus):
    """Round-4/SIG-3. `WitnessTimeout` subclasses `LintError`, so `except
    rv.WitnessTimeout` must precede every `except rv.LintError`, or the timeout is
    reported as a disposition and the figures ship with a timed-out receipt inside them.

    ⚠ WHAT THESE TESTS ACTUALLY PIN (round-1/C3-R1-S4). The rule is applied at five
    sites in `measure_486_corpus.py` (`lint_receipt`, the section parses,
    `tier2_artifacts`, `tier2_witness`, and `witness_name`); exactly **one** of them is
    REACHABLE and therefore exactly one is pinned here — the `tier2_witness` arm. The
    watchdog is armed at a single place in the linter, `rcpt_verify.py`'s
    `with _witness_bound():` inside `tier2_witness`; `_compile_guard` /
    `_reject_unsatisfiable` are static analyses, and the ARTIFACTS leg is documented in
    `rcpt_verify.py` as running "OUTSIDE _witness_bound() — it has no timeout of any
    kind". Measured: deleting the other arms leaves this file green; deleting the
    `tier2_witness` arm turns three of these tests red.

    The other four arms are uniform-BY-POLICY, not covered-by-test, and the earlier
    version of this docstring claimed otherwise — which is worse than no arm, because it
    tells the next maintainer that the refactor named in `rcpt_verify.py` (arming a bound
    on the ARTIFACTS leg) is already under test. It is not. If that bound lands, the
    `tier2_artifacts` arm goes live with nothing behind it, and a test belongs here at
    that moment."""

    def _timeout_receipt(self):
        """VERDICT is **PASS**, deliberately. On a FAIL leg this witness — a ranged
        `kind=grep` payload — IS sourced and read since GH #501, but the leg discards the
        predicate's result (no `exit=` on the cited entry), so the census bills it
        `witness 0/1 … discarded 1 (fail-leg-no-exit-evidence)`. Two earlier codes named
        this state and both retired: `not-applicable (fail-leg-no-range)` (C1-R3-F1) and
        then `unreached (fail-leg-payload-not-sourced)` (#501).
        What matters for the PASS choice is unchanged and is the *evaluation*, not the
        bucket: a FAIL receipt times out on the PASS-SYNTHETIC pass only — and the as-returned
        pass, which is the one every counter row is stated over, publishes a full set of
        figures first. Pinning the timeout on the as-returned pass is what makes these
        assertions about the published rows rather than about the second pass.
        A receipt that is already PASS also has no synthetic second leg
        (`pass_leg_synthetic` returns None), so the timeout is reached exactly once."""
        note = self.root / "verify-note.md"
        note.write_text(CATASTROPHIC_BODY)
        h = hashlib.sha256(note.read_bytes()).hexdigest()
        return _receipt(
            f"grep:verify-note.md#L1-L1  pattern={CATASTROPHIC}  "
            "expect-fail=match  ran=TRACE#1",
            artifacts=[("verify-note.md", h, str(note.stat().st_size))],
            trace=[f"WROTE  verify-note.md  sha256:{h}"],
            verdict="PASS")

    def test_a_timeout_is_a_named_skip_with_a_non_zero_exit(self):
        (self.corpus_dir / "rcpt-1-asreturned.txt").write_text(self._timeout_receipt())
        self._patch_rv(WITNESS_TIMEOUT_S=0.001)
        rc, out = self._run(["rcpt-1-asreturned.txt"])
        self.assertEqual(rc, 1)                                # never a clean exit
        self.assertIn("SKIPPED  rcpt-1-asreturned.txt: witness-timeout", out)
        self.assertIn("STOP-AND-DECLARE", out)
        self.assertAccounted(out, 1, 0, 1)

    def test_a_timed_out_receipt_reaches_no_disposition_and_no_counter(self):
        # The discriminating half: a swallowed timeout does not merely mislabel the
        # receipt, it lands inside `unreached`/`not-reachable` and inside the witness
        # dispositions the design's `27 clean / 1 unverifiable / 1 raise` row is
        # compared against.
        (self.corpus_dir / "rcpt-1-asreturned.txt").write_text(self._timeout_receipt())
        self._patch_rv(WITNESS_TIMEOUT_S=0.001)
        _, out = self._run(["rcpt-1-asreturned.txt"])
        self.assertNotIn("clean=", out)
        self.assertNotIn("unverifiable=", out)
        self.assertNotIn("raise=", out)
        for counter in ("unreached", "not-reachable", "ambiguous",
                        "wrong-name", "not-applicable"):
            self.assertIn(f"{counter:<46s} artifacts-leg 0  witness-leg 0  total 0", out)

    def test_a_timeout_does_not_suppress_the_rest_of_the_corpus(self):
        # Denominator visibility with a timeout in the mix: the clean receipt is still
        # measured, and the accounting still balances. Without this, a script that
        # aborted the whole run on the first timeout would satisfy the two tests above.
        (self.corpus_dir / "rcpt-1-asreturned.txt").write_text(self._timeout_receipt())
        (self.corpus_dir / "rcpt-2-asreturned.txt").write_text(MEASURABLE)
        self._patch_rv(WITNESS_TIMEOUT_S=0.001)
        rc, out = self._run(["rcpt-1-asreturned.txt", "rcpt-2-asreturned.txt"])
        self.assertEqual(rc, 1)
        self.assertAccounted(out, 2, 1, 1)


class TestTheDenominatorCannotShrinkSilently(_SyntheticCorpus):
    """`measured + skipped == receipts` with a mix, plus the discriminator that stops
    every test above from being satisfied by a script that skips unconditionally."""

    def test_a_mixed_corpus_accounts_for_every_file(self):
        (self.corpus_dir / "rcpt-97-asreturned.txt").write_bytes(b"\xff\xfe\n")
        (self.corpus_dir / "rcpt-98-asreturned.txt").write_text(REJECTED)
        (self.corpus_dir / "rcpt-99-asreturned.txt").write_text(MEASURABLE)
        rc, out = self._run(["rcpt-97-asreturned.txt", "rcpt-98-asreturned.txt",
                             "rcpt-99-asreturned.txt"])
        self.assertEqual(rc, 0)
        self.assertAccounted(out, 3, 2, 1)          # the rejected one is MEASURED
        self.assertIn("(of which tier1-rejected 1)", out)

    def test_a_clean_corpus_measures_every_file(self):
        (self.corpus_dir / "rcpt-99-asreturned.txt").write_text(MEASURABLE)
        rc, out = self._run(["rcpt-99-asreturned.txt"])
        self.assertEqual(rc, 0)
        self.assertAccounted(out, 1, 1, 0)
        self.assertIn("(of which tier1-rejected 0)", out)
        self.assertIn("### done", out)

    def test_an_enumeration_that_disagrees_with_expect_size_stops(self):
        # Rule (4): the corpus definition and the pinned expectation must agree, or the
        # run stops rather than reporting against a silently-changed denominator.
        (self.corpus_dir / "rcpt-99-asreturned.txt").write_text(MEASURABLE)
        rc, out = self._run(["rcpt-99-asreturned.txt"], expect_size=17)
        self.assertEqual(rc, 1)
        self.assertIn("STOP: enumeration is 1, --expect-size 17", out)

    def test_a_receipt_on_disk_outside_the_enumeration_stops(self):
        # Rule (1): the enumeration IS the corpus definition; a bare glob is what lets
        # a corpus grow under a published figure.
        (self.corpus_dir / "rcpt-99-asreturned.txt").write_text(MEASURABLE)
        (self.corpus_dir / "rcpt-100-asreturned.txt").write_text(MEASURABLE)
        rc, out = self._run(["rcpt-99-asreturned.txt"])
        self.assertEqual(rc, 1)
        self.assertIn("outside the enumeration", out)
        self.assertIn("rcpt-100-asreturned.txt", out)


class TestTheCorpusCannotShrinkQuietly(_SyntheticCorpus):
    """Round-1/C3-R1-F1 — the SHRINK direction of the enumeration/disk reconciliation.

    `test_a_receipt_on_disk_outside_the_enumeration_stops` above covers the GROW
    direction only, and `--expect-size` structurally cannot see the shrink: it compares
    `len(corpus.names)` against a CLI integer, one hard-coded constant against another,
    and never touches the disk. Before this class, a corpus whose members had vanished
    fell through to `path.read_text()`, became ordinary skips, and the script published a
    complete set of figures — every one of them stamped with the ENUMERATION's size — at
    `### done` and exit 0. Exit code is the machine-readable channel and it said clean.

    Total loss and partial loss are both pinned, because partial loss is the quieter and
    likelier one: six SKIPPED lines inside a 200-line dump, then a figure that a reader
    lifts into prose against a denominator it was not computed over."""

    def test_an_enumerated_receipt_absent_from_disk_stops(self):
        (self.corpus_dir / "rcpt-99-asreturned.txt").write_text(MEASURABLE)
        rc, out = self._run(["rcpt-99-asreturned.txt", "rcpt-98-asreturned.txt"])
        self.assertEqual(rc, 1)                      # NOT a clean exit
        self.assertIn("the corpus shrank", out)
        self.assertIn("rcpt-98-asreturned.txt", out)
        self.assertNotIn("### done", out)            # and no figures were published

    def test_a_wholly_absent_corpus_stops_even_though_the_directory_exists(self):
        # The E9 shape: directory present, every enumerated member gone. Previously
        # exit 0 with `entry resolution 0/0` and all six counters at zero.
        rc, out = self._run(["rcpt-1-asreturned.txt", "rcpt-2-asreturned.txt"])
        self.assertEqual(rc, 1)
        self.assertIn("2 enumerated receipt(s) are absent from disk", out)
        self.assertNotIn("### done", out)


class TestFiguresCarryWhatTheyWereComputedOver(_SyntheticCorpus):
    """Round-1/C3-R1-F1, second half. `fig`'s `n=` tag exists so "the corpus size …
    travel[s] with EVERY figure" — but `n=` is the enumeration and is a constant, so a
    run that measured fewer members than it enumerated still labelled every figure with
    the full size. `computed-over=` is the count the pass actually measured, so the two
    disagree in the output exactly when the denominator moved."""

    def test_a_skip_moves_computed_over_but_not_n(self):
        # One measurable receipt, one that cannot be decoded: measured=1 of an
        # enumeration of 2. The shrink guard does not fire — both files are on disk.
        (self.corpus_dir / "rcpt-97-asreturned.txt").write_bytes(b"\xff\xfe\n")
        (self.corpus_dir / "rcpt-99-asreturned.txt").write_text(MEASURABLE)
        rc, out = self._run(["rcpt-97-asreturned.txt", "rcpt-99-asreturned.txt"])
        self.assertEqual(rc, 0)
        self.assertAccounted(out, 2, 1, 0 + 1)
        self.assertIn("n=2 computed-over=1 pass=as-returned", out)
        self.assertNotIn("n=2 computed-over=2 pass=as-returned", out)

    def test_a_clean_run_stamps_the_enumeration_on_every_figure(self):
        # The discriminator: without it, a `computed-over` hard-wired to something
        # smaller than `n` would satisfy the test above.
        (self.corpus_dir / "rcpt-99-asreturned.txt").write_text(MEASURABLE)
        rc, out = self._run(["rcpt-99-asreturned.txt"])
        self.assertEqual(rc, 0)
        self.assertIn("n=1 computed-over=1 pass=as-returned", out)
        for line in out.splitlines():
            if "[corpus=synthetic" in line:
                self.assertIn("computed-over=", line)


class TestCriterion13PublishesBothHalvesOfItsDelta(_SyntheticCorpus):
    """Round-1/C3-R1-S2 — criterion 13 is stated as a delta (`0/89 → 88/89`) and this
    script is its sole designated discharge, but it emitted only the right-hand side:
    `roots_one` was computed on every path and used for criterion 1's name leg only.
    Criterion 1 prints both root-count legs on adjacent lines; the ARTIFACTS leg now
    does too, so the artifact backing the delta reproduces the `0` as well as the `88`."""

    def test_the_one_root_artifacts_baseline_is_emitted(self):
        (self.corpus_dir / "rcpt-99-asreturned.txt").write_text(MEASURABLE)
        rc, out = self._run(["rcpt-99-asreturned.txt"])
        self.assertEqual(rc, 0)
        self.assertIn("entry resolution, ONE root (baseline)", out)
        # …tagged with the ONE-root probe count, beside the two-root figure it is read
        # against. The synthetic corpus declares the same dir for both, so the assertion
        # is on the tag being emitted per-leg, not on the two ratios differing.
        base = [l for l in out.splitlines()
                if "entry resolution, ONE root (baseline)" in l]
        self.assertEqual(len(base), 1, out)
        self.assertIn("roots=1", base[0])
        self.assertIn("leg=artifacts", base[0])


class TestCommittedFiguresAreGated(unittest.TestCase):
    """Round-1/C3-R1-S3 — the half of the #474 split #486 was missing.

    #474 ships a PAIR: `measure_474_corpus.py` (machine-local, ungated, the true analogue
    of `measure_486_corpus.py`) and `measure_474_denominators.py`, which IS on
    `run_tests.sh` and re-derives from COMMITTED files every figure its plan quotes, "so
    a figure that rots fails CI instead of aging quietly inside a document". #486 shipped
    only the first, and its docstring justified the omission by naming the second as
    though it were the first.

    The corpus figures genuinely cannot be gated — all three corpora are machine-local
    and gitignored — but #486 does publish committed-file facts, and those can be. These
    are them: the six `two-root-*` fixture rows that are the corpus-level coverage of
    multi-root resolution, their `root`/`expect`/`strict` triples, and the linter's own
    `_MULTI_ROOT_FIXTURE_IDS` presence guard agreeing with the manifest. Reads only
    committed files, so it returns the same verdict on CI and on any checkout."""

    REPO = pathlib.Path(__file__).resolve().parent.parent
    MANIFEST = (REPO / "eval/ledger-return-protocol/tier2-fixtures/manifest.jsonl")

    # id -> (roots, expect, strict). The row whose subject is #486's headline behaviour
    # is `two-root-second-root-resolves`, and it is PATH-SHAPED under --strict on
    # purpose (C3-R1-S1): a bare basename that resolves nowhere degrades to UNVERIFIABLE
    # and still returns "pass", so the row would have been satisfied by the very bug it
    # is named for.
    EXPECT = {
        "two-root-second-root-resolves": (["p1", "p2"], "pass", True),
        "two-root-declaration-order-first-hit": (["p1", "p2"], "fail", False),
        "two-root-ambiguous-strict-fail": (["p1", "p2"], "fail", True),
        "two-root-ambiguous-identical-bytes-strict-fail": (["p1", "p3"], "fail", True),
        "two-root-dedup-noop": (["p1", "p1"], "pass", True),
        "two-root-tampered-hash-second-root": (["p1", "p2"], "fail", True),
    }

    def _rows(self):
        rows = {}
        for line in self.MANIFEST.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                rows[r["id"]] = r
        return rows

    def test_the_two_root_rows_and_their_triples_are_unchanged(self):
        rows = self._rows()
        for fid, (roots, expect, strict) in self.EXPECT.items():
            self.assertIn(fid, rows, f"{fid} pruned from manifest.jsonl")
            self.assertEqual(rows[fid]["root"], roots, fid)
            self.assertEqual(rows[fid]["expect"], expect, fid)
            self.assertEqual(rows[fid]["strict"], strict, fid)

    def test_the_linters_presence_guard_agrees_with_the_manifest(self):
        spec = importlib.util.spec_from_file_location(
            "rv_committed_fig", self.REPO / "scripts/rcpt_verify.py")
        rv = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rv)
        self.assertEqual(set(rv._MULTI_ROOT_FIXTURE_IDS), set(self.EXPECT))

    def test_the_headline_row_names_a_path_shaped_artifact(self):
        """C3-R1-S1's repair, pinned as a committed-file fact rather than as prose: if
        the row reverts to a bare basename it silently stops discriminating — it goes
        green with its own subject file deleted — and `--selftest` cannot tell."""
        spec = importlib.util.spec_from_file_location(
            "rv_committed_fig2", self.REPO / "scripts/rcpt_verify.py")
        rv = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rv)
        row = self._rows()["two-root-second-root-resolves"]
        self.assertTrue(row["strict"], "the --strict FAIL arm is the discriminator")
        arts = rv.parse_artifacts(rv.parse_receipt(row["receipt"])["ARTIFACTS"])
        self.assertTrue(arts, "the row declares no artifact at all")
        for name in arts:
            self.assertTrue(rv.is_path_shaped(name),
                            f"{name!r} is a bare basename — unresolved it degrades to "
                            f"UNVERIFIABLE and the row passes with the file deleted")


if __name__ == "__main__":
    unittest.main()
