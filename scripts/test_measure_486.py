#!/usr/bin/env python3
"""Stdlib unittest suite for scripts/measure_486_corpus.py.

Narrow by design — two properties, both about inputs the committed tree does not
contain. The three real corpora are machine-local and gitignored, so what CI can pin
is not their figures but the script's behaviour on a corpus that has gone wrong:

  * **Crash-resistance.** Every reachable way a corpus entry can be unmeasurable must
    produce a NAMED outcome, never a traceback. One test per reachable class rather
    than one representative — copied from `test_measure_474.py:66-147`, where that
    guard was wrong twice (the round-3 fix wrapped the parse but left the READ one line
    above the try). The classes: an absent corpus directory, a non-UTF-8 file matching
    the receipt glob, a directory matching it, an unreadable file, a receipt a Tier-1
    rule rejects, and a witness timeout.
  * **Denominator visibility.** `measured + skipped == receipts` on every one of those
    inputs, so a rejected or unreadable receipt cannot quietly shrink the denominator
    criteria 1, 12 and 13 are computed over. The script already commits to this in
    prose (`tier1-rejects 1 … individually accounted for`); this pins the claim.

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
import os
import pathlib
import tempfile
import unittest

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


class TestWitnessTimeoutIsANamedStopNotADisposition(_SyntheticCorpus):
    """Round-4/SIG-3. `WitnessTimeout` subclasses `LintError`, so `except
    rv.WitnessTimeout` must precede every `except rv.LintError` on all four call sites
    (`lint_receipt`, the section parses, `tier2_artifacts`, `tier2_witness`). If any
    one of them is reordered, the timeout is reported as a disposition and the figures
    ship with a timed-out receipt inside them."""

    def _timeout_receipt(self):
        """VERDICT is **PASS**, deliberately. On a FAIL leg the witness lands on
        `not-applicable (fail-leg-no-range)` without ever evaluating the predicate, so a
        FAIL receipt times out on the PASS-SYNTHETIC pass only — and the as-returned
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


if __name__ == "__main__":
    unittest.main()
