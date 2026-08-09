#!/usr/bin/env python3
"""Stdlib unittest suite for scripts/measure_474_denominators.py.

Narrow by design — two properties, both about what the script does on inputs the
committed tree does not contain:

  * row 7 (`row_corpus`) reads a machine-local, gitignored corpus, so it can differ
    between CI (where it SKIPs) and the maintainer's machine (where the corpus exists).
    Its crash-resistance is the property pinned here — #474 round-3 / S2, widened in
    round-4 / M5 to cover the file READ and not only the parse.
  * row 4's gate is the PRESENCE of RED test 15's calibration pin, not a census of
    `scripts/test_rcpt_verify.py` (round-4 / S1). Both directions are pinned: an
    unrelated `out=` token must not turn the row red, and deleting the pin must.

Rows 1-3 and 5-6 run over committed files and are self-asserting inside the script.

Run from repo root:  python3 scripts/test_measure_474.py
"""
import contextlib
import importlib.util
import io
import os
import pathlib
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent / "measure_474_denominators.py"


def _import_m474():
    spec = importlib.util.spec_from_file_location("measure_474", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


H64 = "ab" * 32


def _receipt(witness):
    return (f"RCPT v1 red-team/9-devils-advocate\n"
            f"VERDICT  FAIL  conf=0.90\n"
            f"ARTIFACTS\n"
            f"  findings.md  sha256:{H64}  100\n"
            f"TRACE\n"
            f"  1  WROTE  findings.md  sha256:{H64}\n"
            f"CLAIMS\n"
            f"  (none)\n"
            f"WITNESS    {witness}\n"
            f"SUSPICION  0.10\n"
            f"NEXT       (none)\n")


# Rejected by a Tier-1 rule THIS BRANCH introduced: `expect-fail=match` on a rangeless
# grep payload. Receipts of exactly this shape sit in as-returned corpora written
# before the rule landed, which is what made row 7 abort instead of measure.
REJECTED = _receipt("grep:findings.md  pattern=/significant=[1-9]/  "
                    "expect-fail=match  ran=TRACE#1")
MEASURABLE = _receipt("grep:findings.md#L1-L1  pattern=/significant=[1-9]/  "
                      "expect-fail=match  ran=TRACE#1")


class TestRowCorpusSkipsRatherThanCrashes(unittest.TestCase):
    def setUp(self):
        self.m = _import_m474()
        self._td = tempfile.TemporaryDirectory()
        self.corpus = pathlib.Path(self._td.name)
        self.addCleanup(self._td.cleanup)

    def _run(self):
        rep = self.m.Report()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.m.row_corpus(self.m.load_rcpt_verify(), rep, self.corpus)
        return rep, out.getvalue()

    def test_receipt_rejected_by_a_new_tier1_rule_is_skipped_not_raised(self):
        (self.corpus / "rcpt-99-asreturned.txt").write_text(REJECTED)
        rep, out = self._run()          # the bug was an uncaught LintError here
        self.assertIn("skipped=1", out)
        self.assertIn("SKIPPED     : rcpt-99-asreturned.txt", out)
        self.assertEqual(rep.errors, [])

    def test_the_skip_names_the_rule_that_rejected_the_receipt(self):
        # A silent skip is the failure mode this row was demoted to advisory to avoid.
        (self.corpus / "rcpt-99-asreturned.txt").write_text(REJECTED)
        _, out = self._run()
        self.assertIn("requires a ranged grep payload", out)

    def test_a_skip_is_visible_in_the_denominator_not_silently_dropped(self):
        # measured + skipped must account for every file, so a rejected receipt cannot
        # quietly shrink the denominator the figures below are computed over.
        (self.corpus / "rcpt-98-asreturned.txt").write_text(REJECTED)
        (self.corpus / "rcpt-99-asreturned.txt").write_text(MEASURABLE)
        _, out = self._run()
        self.assertIn("receipts=2 measured=1 skipped=1", out)

    def test_a_clean_corpus_still_measures_every_file(self):
        # Discriminator: without this, the tests above are satisfied by a row_corpus
        # that skips unconditionally.
        (self.corpus / "rcpt-99-asreturned.txt").write_text(MEASURABLE)
        _, out = self._run()
        self.assertIn("receipts=1 measured=1 skipped=0", out)
        self.assertIn("kind=grep=1 ranged=1", out)

    # --- round-4 / M5 — the guard covers the READ, not only the parse. The round-3 fix
    #     wrapped parse_receipt but left `read_text()` one line above the try, so the
    #     three failure modes reachable through the documented `--corpus DIR` flag still
    #     aborted a run_tests.sh-gated script. Second time this guard has been wrong,
    #     hence one test per reachable class rather than one representative.
    def test_a_non_utf8_corpus_file_is_skipped_not_raised(self):
        # UnicodeDecodeError is a ValueError, NOT an OSError — an `except OSError` alone
        # would leave this one crashing.
        (self.corpus / "rcpt-97-asreturned.txt").write_bytes(b"RCPT v1 x/1\n\xff\xfe\n")
        rep, out = self._run()
        self.assertIn("skipped=1", out)
        self.assertIn("SKIPPED     : rcpt-97-asreturned.txt", out)
        self.assertEqual(rep.errors, [])

    def test_a_directory_matching_the_corpus_glob_is_skipped_not_raised(self):
        # `rcpt-*-asreturned.txt` is a glob; nothing stops a directory from matching it.
        (self.corpus / "rcpt-96-asreturned.txt").mkdir()
        rep, out = self._run()
        self.assertIn("skipped=1", out)
        self.assertIn("SKIPPED     : rcpt-96-asreturned.txt", out)
        self.assertEqual(rep.errors, [])

    def test_an_unreadable_corpus_file_is_skipped_not_raised(self):
        p = self.corpus / "rcpt-95-asreturned.txt"
        p.write_text(MEASURABLE)
        p.chmod(0o000)
        self.addCleanup(p.chmod, 0o600)
        if os.access(p, os.R_OK):       # root ignores the mode bits
            self.skipTest("running as a user that can read a 0o000 file")
        rep, out = self._run()
        self.assertIn("skipped=1", out)
        self.assertEqual(rep.errors, [])

    def test_a_read_failure_does_not_shrink_the_denominator_silently(self):
        # Same accounting rule as the LintError skip: measured + skipped == receipts.
        (self.corpus / "rcpt-97-asreturned.txt").write_bytes(b"\xff\xfe\n")
        (self.corpus / "rcpt-99-asreturned.txt").write_text(MEASURABLE)
        _, out = self._run()
        self.assertIn("receipts=2 measured=1 skipped=1", out)


# Row 4's gate is the PRESENCE of RED test 15's calibration pin — not a census of a
# high-churn file (round-4 / S1). The pin token carries a trailing `"` because
# TOKENIZATION is `out=\S+` over raw text and the pin sits inside a double-quoted Python
# string literal in the test file.
PIN = 'out=a.log#L1-L100"'
WANT4 = dict(literal=None, range_shaped=None, accepted=None, max_l_span=99,
             in_band_tokens=[(PIN, 99)])


class TestRow4GatesThePinNotTheCensus(unittest.TestCase):
    def setUp(self):
        self.m = _import_m474()
        self.rv = self.m.load_rcpt_verify()      # BEFORE ROOT is redirected
        self._td = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._td.name)
        self.addCleanup(self._td.cleanup)
        self.m.ROOT = self.root

    def _run_row4(self, body):
        (self.root / "test_rcpt_verify.py").write_text(body)
        rep = self.m.Report()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.m.row_exec_file(self.rv, rep, "test_rcpt_verify.py", 4, WANT4,
                                 assert_counts=False, pin_token=PIN)
        return rep, out.getvalue()

    def test_the_pin_alone_is_clean(self):
        rep, out = self._run_row4(f'args = "{PIN[:-1]}"\n')
        self.assertEqual(rep.errors, [])
        self.assertIn("calibration pin present", out)

    def test_an_unrelated_out_of_band_token_does_not_turn_the_row_red(self):
        # THE regression this row's demotion exists for: a future rcpt_verify test that
        # happens to carry an out= token moved `max #L span` AND the exact in-band list,
        # producing 2 gated failures with test 15's pin fully intact.
        rep, out = self._run_row4(f'a = "{PIN[:-1]}"\nb = "out=b.log#L1-L300"\n')
        self.assertEqual(rep.errors, [])
        self.assertIn("DIFF test_rcpt_verify.py max #L span", out)

    def test_deleting_the_pin_still_fails(self):
        # The check that stops the demotion from becoming "assert nothing".
        rep, _ = self._run_row4('b = "out=b.log#L1-L300"\n')
        self.assertEqual(len(rep.errors), 1)
        self.assertIn("calibration pin present", rep.errors[0])

    def test_an_empty_file_fails_too(self):
        # Discriminator for the above: the pin check must fire on absence generally,
        # not only when some other in-band token is present.
        rep, _ = self._run_row4("# no tokens here\n")
        self.assertEqual(len(rep.errors), 1)
        self.assertIn("calibration pin present", rep.errors[0])

    def test_the_two_demoted_figures_are_still_printed_and_compared(self):
        # Advisory means printed and compared, never dropped.
        _, out = self._run_row4(f'a = "{PIN[:-1]}"\nb = "out=b.log#L1-L300"\n')
        self.assertIn("max #L span", out)
        self.assertIn("in_band_tokens", out)
        self.assertIn("advisory — expected", out)

    def test_the_gated_form_is_unchanged_for_the_stable_files(self):
        # pin_token is opt-in: with it absent, both figures stay GATING (that is what
        # rows 2 and 3 rely on over return-convention.md / red-team-prompt.md).
        (self.root / "stable.md").write_text('x = "out=b.log#L1-L300"\n')
        rep = self.m.Report()
        with contextlib.redirect_stdout(io.StringIO()):
            self.m.row_exec_file(self.rv, rep, "stable.md", 2,
                                 dict(literal=1, range_shaped=1, accepted=1,
                                      max_l_span=0, in_band_blocks=[]))
        self.assertEqual(len(rep.errors), 2)


if __name__ == "__main__":
    unittest.main()
