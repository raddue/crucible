#!/usr/bin/env python3
"""Stdlib unittest suite for scripts/measure_474_denominators.py.

Narrow by design: it covers row 7 (`row_corpus`), the one row whose input is a
machine-local, gitignored corpus. Rows 1-6 run over committed files and are already
self-asserting inside the script. Row 7 is the row that can differ between CI (where
it SKIPs) and the maintainer's machine (where the corpus exists), so its
crash-resistance is the property worth pinning here — see #474 round-3 / S2.

Run from repo root:  python3 scripts/test_measure_474.py
"""
import contextlib
import importlib.util
import io
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


if __name__ == "__main__":
    unittest.main()
