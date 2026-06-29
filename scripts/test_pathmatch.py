#!/usr/bin/env python3
"""Tests for scripts/pathmatch.py — the single source of truth for path-aware
glob, extracted from the verbatim `_glob_match` duplication (#401).

Pins both the matching contract AND the no-drift guarantee: reconcile_ledger
and grudge_query must reference the SAME function object, so a future edit to
one cannot silently diverge the other (the exact hazard #401 flagged — wrong
glob semantics silently flip a Brier `actual`)."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts.pathmatch import glob_match  # noqa: E402


class GlobMatchContractTest(unittest.TestCase):
    def test_exact_match(self):
        self.assertTrue(glob_match("src/auth/token.ts", "src/auth/token.ts"))

    def test_star_matches_within_one_segment(self):
        self.assertTrue(glob_match("src/auth/token.ts", "src/auth/*"))
        self.assertTrue(glob_match("src/auth/token.ts", "src/auth/*.ts"))

    def test_star_does_not_cross_slash(self):
        # the load-bearing property: `*` must NOT match a deeper subtree.
        self.assertFalse(glob_match("src/auth/sub/x.ts", "src/auth/*"))

    def test_segment_count_mismatch_fails(self):
        self.assertFalse(glob_match("src/auth", "src/auth/token.ts"))
        self.assertFalse(glob_match("a/b/c", "a/b"))

    def test_case_sensitive_cross_host(self):
        # fnmatchcase: `Auth` != `auth` regardless of host OS.
        self.assertFalse(glob_match("src/Auth/token.ts", "src/auth/*"))

    def test_question_and_class_metachars_within_segment(self):
        self.assertTrue(glob_match("a/b1.py", "a/b?.py"))
        self.assertTrue(glob_match("a/b1.py", "a/b[0-9].py"))
        self.assertFalse(glob_match("a/bx.py", "a/b[0-9].py"))


class NoDriftIdentityTest(unittest.TestCase):
    """#401 anti-drift: the two former copies are now the SAME object."""

    def test_reconcile_and_grudge_share_one_implementation(self):
        from scripts import reconcile_ledger as rl
        from scripts import grudge_query as gq
        self.assertIs(rl._glob_match, glob_match)
        self.assertIs(gq._glob_match, glob_match)


if __name__ == "__main__":
    unittest.main()
