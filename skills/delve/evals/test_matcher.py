#!/usr/bin/env python3
"""Deterministic matcher tests for the delve eval harness (#373) — the design's
acceptance criterion #1 (the worked recall + FP example).

stdlib unittest. The matcher is LLM-free, pure, stdlib-only; these tests pin its
arithmetic exactly so a regression in the scorer (the CI-gated half of the harness)
is caught. No live dispatch.
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from skills.delve.evals._matcher import match, parse_line  # noqa: E402


# ---------------------------------------------------------------------------
# The worked example (acceptance #1). Four planted bugs; a recorded-findings set
# mixing true hits, a positional false-positive, a miss, a double-finding on one
# bug, and a ±LINE_SLOP boundary hit.
# ---------------------------------------------------------------------------

GROUND_TRUTH = [
    # b1: a true hit — a finding lands exactly here with a matching signature.
    {"bug_id": "sm-b1", "file": "calc.py", "line_lo": 10, "line_hi": 10,
     "signature": ["off-by-one", "slice"]},
    # b2: a slop-boundary hit — the finding's line is line_hi + LINE_SLOP (12 + 2 = 14).
    {"bug_id": "sm-b2", "file": "calc.py", "line_lo": 12, "line_hi": 12,
     "signature": ["mutable default"]},
    # b3: TWO findings land on this bug — must be credited exactly once (one-to-one).
    {"bug_id": "sm-b3", "file": "util.py", "line_lo": 20, "line_hi": 25,
     "signature": ["comparison operator", "wrong operator"]},
    # b4: a MISS — no finding covers it (the one finding at its line is the FP, which
    #     is signature-mismatched, so it does not score for b4 either).
    {"bug_id": "sm-b4", "file": "util.py", "line_lo": 40, "line_hi": 40,
     "signature": ["resource leak", "not closed"]},
]

FINDINGS = [
    # F0 → b1 (exact line + signature "off-by-one" present in summary).
    {"file": "calc.py", "line": 10,
     "summary": "off-by-one error in the slice bound drops the last element"},
    # F1 → b2 via the ±LINE_SLOP boundary: line 14 = b2.line_hi(12) + slop(2).
    {"file": "calc.py", "line": 14,
     "summary": "mutable default argument shared across calls"},
    # F2 → b3 (line 22 overlaps 20-25; signature "wrong operator" present).
    {"file": "util.py", "line": 22,
     "summary": "uses == where >= was intended, a wrong operator"},
    # F3 → ALSO on b3 (line 24 overlaps; "comparison operator" present). Must NOT
    # double-count: b3 is already credited by F2 (one-to-one), so F3 is an
    # unmatched kept finding → a false positive.
    {"file": "util.py", "line": 24,
     "summary": "the comparison operator here is also suspicious"},
    # F4 → positional FP: lands at b4's planted line (40) but the summary contains
    # NONE of b4's signatures ("resource leak"/"not closed") → must NOT match b4.
    {"file": "util.py", "line": 40,
     "summary": "this loop could be rewritten more clearly for readability"},
]


class TestMatcherWorkedExample(unittest.TestCase):
    def setUp(self):
        self.result = match(FINDINGS, GROUND_TRUTH, line_slop=2)

    def test_recall(self):
        # 3 of 4 planted bugs matched (b1, b2, b3); b4 missed.
        self.assertEqual(self.result.recall, 3 / 4)

    def test_false_positive_rate(self):
        # 5 kept findings, 2 unmatched (F3 the double, F4 the positional FP) → 2/5.
        self.assertEqual(self.result.false_positive_rate, 2 / 5)

    def test_one_to_one_bipartite(self):
        # Each bug at most once, each finding at most once.
        bug_ids = [b for (b, _f) in self.result.matched]
        finding_idxs = [f for (_b, f) in self.result.matched]
        self.assertEqual(len(bug_ids), len(set(bug_ids)),
                         "a bug was credited more than once")
        self.assertEqual(len(finding_idxs), len(set(finding_idxs)),
                         "a finding was consumed more than once")
        self.assertEqual(len(self.result.matched), 3)

    def test_matched_pairs(self):
        # b3 is credited to F2 (the deterministic tie-break: greedy by overlap then
        # bug_id then finding index; F2 precedes F3).
        self.assertEqual(set(self.result.matched),
                         {("sm-b1", 0), ("sm-b2", 1), ("sm-b3", 2)})

    def test_unmatched(self):
        self.assertEqual(self.result.unmatched_bugs, ["sm-b4"])
        self.assertEqual(sorted(self.result.unmatched_findings), [3, 4])

    def test_positional_fp_does_not_match(self):
        # F4 is at b4's exact line but signature-mismatched → b4 stays unmatched and
        # F4 is a false positive. (This is the core of the signature gate.)
        self.assertIn("sm-b4", self.result.unmatched_bugs)
        self.assertIn(4, self.result.unmatched_findings)


class TestSlopBoundary(unittest.TestCase):
    def test_just_inside_slop_matches(self):
        gt = [{"bug_id": "b", "file": "a.py", "line_lo": 10, "line_hi": 10,
               "signature": ["bug"]}]
        # line 12 = 10 + slop(2) → inside.
        r = match([{"file": "a.py", "line": 12, "summary": "a bug here"}], gt,
                  line_slop=2)
        self.assertEqual(r.recall, 1.0)

    def test_just_outside_slop_misses(self):
        gt = [{"bug_id": "b", "file": "a.py", "line_lo": 10, "line_hi": 10,
               "signature": ["bug"]}]
        # line 13 = 10 + slop(2) + 1 → outside.
        r = match([{"file": "a.py", "line": 13, "summary": "a bug here"}], gt,
                  line_slop=2)
        self.assertEqual(r.recall, 0.0)
        self.assertEqual(r.false_positive_rate, 1.0)


class TestSignatureFallbackAndNormalization(unittest.TestCase):
    def test_signature_falls_back_to_failure_scenario(self):
        gt = [{"bug_id": "b", "file": "a.py", "line_lo": 5, "line_hi": 5,
               "signature": ["deadlock"]}]
        # summary has no signature token; failure_scenario does → match via fallback.
        f = [{"file": "a.py", "line": 5, "summary": "something is wrong",
              "failure_scenario": "two threads deadlock under contention"}]
        r = match(f, gt, line_slop=2)
        self.assertEqual(r.recall, 1.0)

    def test_file_normalization_posix(self):
        gt = [{"bug_id": "b", "file": "src/a.py", "line_lo": 5, "line_hi": 5,
               "signature": ["bug"]}]
        # backslash-separated + ./ prefix on the finding must normalize to match.
        f = [{"file": ".\\src\\a.py", "line": 5, "summary": "a bug"}]
        r = match(f, gt, line_slop=2)
        self.assertEqual(r.recall, 1.0)

    def test_signature_case_insensitive(self):
        gt = [{"bug_id": "b", "file": "a.py", "line_lo": 5, "line_hi": 5,
               "signature": ["SQL Injection"]}]
        f = [{"file": "a.py", "line": 5, "summary": "possible sql injection sink"}]
        r = match(f, gt, line_slop=2)
        self.assertEqual(r.recall, 1.0)


class TestMaximumCardinality(unittest.TestCase):
    """Regression: greedy-by-weight understated recall (S1). A high-weight edge
    (a finding spanning two bugs) could consume a bug that a unique low-weight edge
    needed, dropping recall below the true maximum one-to-one matching."""

    def test_high_weight_edge_does_not_starve_unique_edge(self):
        # B1 at 20-20, B2 at 24-26 (both signature ["bug"]). At slop=2:
        #   F0 spans "20-26" → overlaps BOTH B1 (overlap 1) and B2 (overlap 3).
        #   F1 at line 25 → overlaps ONLY B2 (overlap 1).
        # Greedy takes F0→B2 first (overlap 3) and leaves B1 with no finding (F1
        # can't reach B1) → recall 0.5. Maximum matching is F0→B1, F1→B2 → recall 1.0.
        gt = [
            {"bug_id": "B1", "file": "inventory.py", "line_lo": 20, "line_hi": 20,
             "signature": ["bug"]},
            {"bug_id": "B2", "file": "inventory.py", "line_lo": 24, "line_hi": 26,
             "signature": ["bug"]},
        ]
        findings = [
            {"file": "inventory.py", "line": "20-26", "summary": "a bug spans here"},
            {"file": "inventory.py", "line": 25, "summary": "a bug here"},
        ]
        r = match(findings, gt, line_slop=2)
        self.assertEqual(r.recall, 1.0)
        # Both bugs matched, one-to-one (each bug once, each finding once).
        matched_bugs = [b for (b, _f) in r.matched]
        matched_findings = [f for (_b, f) in r.matched]
        self.assertEqual(sorted(matched_bugs), ["B1", "B2"])
        self.assertEqual(sorted(matched_findings), [0, 1])
        self.assertEqual(r.unmatched_bugs, [])


class TestMalformedLineIsFalsePositive(unittest.TestCase):
    """R2-S1 regression: a recorded finding with an unparseable `line` must NOT crash
    the matcher (parse_line raises ValueError/TypeError for None, "12-", …). The
    candidate-build loop swallows it so the malformed finding produces no edge and is
    counted as a kept-but-unmatched finding (a false positive); valid findings on the
    same run still match."""

    GT = [{"bug_id": "b", "file": "a.py", "line_lo": 5, "line_hi": 5,
           "signature": ["x"]}]

    def test_none_line_does_not_crash_and_is_fp(self):
        findings = [
            {"file": "a.py", "line": 5, "summary": "x here"},   # valid → matches b
            {"file": "a.py", "line": None, "summary": "x here too"},  # malformed → FP
        ]
        r = match(findings, self.GT, line_slop=2)
        self.assertEqual(r.recall, 1.0)              # the valid finding still matches
        self.assertEqual(r.matched, [("b", 0)])
        self.assertIn(1, r.unmatched_findings)       # malformed finding is unmatched
        self.assertEqual(r.false_positive_rate, 1 / 2)  # 1 of 2 kept findings is FP

    def test_malformed_range_does_not_crash_and_is_fp(self):
        # "12-" → int("") raises ValueError inside parse_line.
        findings = [
            {"file": "a.py", "line": 5, "summary": "x here"},
            {"file": "a.py", "line": "12-", "summary": "x here too"},
        ]
        r = match(findings, self.GT, line_slop=2)
        self.assertEqual(r.recall, 1.0)
        self.assertEqual(r.matched, [("b", 0)])
        self.assertIn(1, r.unmatched_findings)


class TestParseLine(unittest.TestCase):
    def test_int(self):
        self.assertEqual(parse_line(12), (12, 12))

    def test_numeric_string(self):
        self.assertEqual(parse_line("12"), (12, 12))

    def test_range_string(self):
        self.assertEqual(parse_line("12-15"), (12, 15))

    def test_whitespace_range(self):
        self.assertEqual(parse_line(" 12 - 15 "), (12, 15))


class TestEmptyInputs(unittest.TestCase):
    def test_no_findings(self):
        gt = [{"bug_id": "b", "file": "a.py", "line_lo": 1, "line_hi": 1,
               "signature": ["x"]}]
        r = match([], gt)
        self.assertEqual(r.recall, 0.0)
        # No kept findings → FP rate is 0.0 (0/0 guarded).
        self.assertEqual(r.false_positive_rate, 0.0)
        self.assertEqual(r.unmatched_bugs, ["b"])

    def test_no_ground_truth(self):
        f = [{"file": "a.py", "line": 1, "summary": "x"}]
        r = match(f, [])
        # No planted bugs → recall is 1.0 (0/0 guarded — vacuously complete); every
        # finding is a false positive.
        self.assertEqual(r.recall, 1.0)
        self.assertEqual(r.false_positive_rate, 1.0)


if __name__ == "__main__":
    unittest.main()
