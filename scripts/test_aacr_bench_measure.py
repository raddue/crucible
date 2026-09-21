#!/usr/bin/env python3
"""Stdlib unittest suite for scripts/aacr_bench_measure.py (#631).

Pins the DETERMINISTIC core of the AACR-Bench review-gate measurement — the pieces
that must be reproducible without an LLM: PR subset selection (seeded), ground-truth
reference extraction (label=1 comments), the four-stage finding↔reference matcher
(path → side → line(k) → lexical, mirroring alibaba/aacr-bench `evaluation/judge.py`),
and the precision/recall/F1/noise arithmetic. The live gate run (the LLM seam) is NOT
tested here: it is the manual/periodic half, exactly as delve/siege/temper harnesses
split stage (deterministic, CI) from the live run.

The suite ALSO pins matcher determinism (same inputs → same match assignment) and the
noise-rate formula — the two ways a "measured number" in docs/evals.md can silently
rot (a matching order that flips on rerun, or a denominator used twice).

Run from repo root:  python3 scripts/test_aacr_bench_measure.py
"""
import importlib.util
import pathlib
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent / "aacr_bench_measure.py"


def _import_module():
    spec = importlib.util.spec_from_file_location("aacr_bench_measure", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ── AACR-Bench shape, minimal required fields ──────────────────────────────────
def _sample(pr_url, path, frm, to, label, note, side="right", sloc=10):
    return {
        "pr_url": pr_url, "path": path, "from_line": frm, "to_line": to,
        "label": label, "note": note, "side": side, "pr_change_line_count": sloc,
        "project_main_language": "Python", "pr_category": "Bug Fix",
    }


class TestPickPrs(unittest.TestCase):
    def setUp(self):
        self.m = _import_module()

    def test_seeded_selection_is_reproducible(self):
        base = [_sample(f"https://github.com/x/y/pull/{i}",
                        f"src/f{i}.py", 1, 1, 1, f"note {i}") for i in range(1, 21)]
        a = self.m.pick_prs(base, seed=631, limit=6)
        b = self.m.pick_prs(base, seed=631, limit=6)
        self.assertEqual(a, b)

    def test_different_seeds_give_different_subsets(self):
        base = [_sample(f"https://github.com/x/y/pull/{i}",
                        f"src/f{i}.py", 1, 1, 1, f"note {i}") for i in range(1, 21)]
        self.assertNotEqual(self.m.pick_prs(base, seed=1, limit=6),
                            self.m.pick_prs(base, seed=2, limit=6))

    def test_limit_respected_and_unique(self):
        base = [_sample(f"https://github.com/x/y/pull/{i}",
                        f"src/f{i}.py", 1, 1, 1, f"note {i}") for i in range(1, 21)]
        out = self.m.pick_prs(base, seed=631, limit=4)
        self.assertEqual(len(out), 4)
        self.assertEqual(len(set(out)), 4)

    def test_prs_with_no_correct_comment_are_excluded(self):
        # A PR whose only samples are all label=0 has no positive-expected
        # denominator; it cannot be recalled against, so it must not be chosen.
        base = [_sample("https://github.com/x/y/pull/1", "a.py", 1, 1, 0, "bad")]
        self.assertEqual(self.m.pick_prs(base, seed=631, limit=1), [])


class TestReferenceComments(unittest.TestCase):
    def setUp(self):
        self.m = _import_module()

    def test_only_label_1_comments_are_expected(self):
        samples = [
            _sample("P1", "a.py", 1, 1, 1, "correct"),
            _sample("P1", "a.py", 2, 2, 0, "false positive"),
            _sample("P1", "b.py", 5, 5, 1, "also correct"),
        ]
        refs = self.m.reference_comments(samples)
        self.assertEqual(len(refs), 2)
        self.assertTrue(all(r["label"] == 1 for r in refs))

    def test_expected_counts_as_denominator(self):
        samples = [_sample("P1", "a.py", i, i, 1, f"n{i}") for i in range(3)]
        self.assertEqual(len(self.m.reference_comments(samples)), 3)


class TestDiffLocationIsSame(unittest.TestCase):
    def setUp(self):
        self.m = _import_module()

    def test_overlapping_ranges_match(self):
        self.assertTrue(self.m.diff_location_is_same(10, 20, 15, 25, k=1))

    def test_proximity_within_k_matches(self):
        self.assertTrue(self.m.diff_location_is_same(10, 10, 11, 11, k=1))
        self.assertFalse(self.m.diff_location_is_same(10, 10, 13, 13, k=1))

    def test_disjoint_beyond_k_does_not(self):
        self.assertFalse(self.m.diff_location_is_same(1, 5, 10, 15, k=1))


class TestLexicalSimilar(unittest.TestCase):
    def setUp(self):
        self.m = _import_module()

    def test_identical_notes_match(self):
        self.assertTrue(self.m.lexical_similar("fix the index", "fix the index"))

    def test_unrelated_notes_do_not(self):
        self.assertFalse(self.m.lexical_similar("no such variable exists",
                                                "consider renaming the method"))

    def test_paraphrase_of_same_concern_matches(self):
        # AACR mock semantics: SequenceMatcher >= 0.4 OR word-jaccard >= 0.3.
        self.assertTrue(
            self.m.lexical_similar(
                "this should validate the input before use",
                "the input needs validation before it is used"))


class TestMatchAndMetrics(unittest.TestCase):
    def setUp(self):
        self.m = _import_module()

    def _gated_verdict(self, kept=True):
        return "CONFIRMED" if kept else "REFUTED"

    def test_perfect_precision_and_recall(self):
        refs = [{"path": "a.py", "side": "right", "from_line": 1, "to_line": 1,
                 "note": "the loop never terminates", "label": 1}]
        findings = [{"file": "a.py", "from_line": 1, "to_line": 1,
                     "severity": "Important",
                     "verdict": self._gated_verdict(True),
                     "summary": "the loop never terminates"}]
        matched, n_matched = self.m.match_results(refs, findings)
        metrics = self.m.metrics(refs, findings, n_matched)
        self.assertEqual(metrics["precision"], 1.0)
        self.assertEqual(metrics["recall"], 1.0)
        self.assertEqual(metrics["f1"], 1.0)
        self.assertEqual(metrics["noise"], 0.0)

    def test_wrong_location_finding_is_not_a_match(self):
        refs = [{"path": "a.py", "side": "right", "from_line": 1, "to_line": 1,
                 "note": "the loop never terminates", "label": 1}]
        findings = [{"file": "a.py", "from_line": 100, "to_line": 100,
                     "severity": "Important",
                     "verdict": self._gated_verdict(True),
                     "summary": "the loop never terminates"}]
        matched, n_matched = self.m.match_results(refs, findings)
        self.assertEqual(n_matched, 0)
        metrics = self.m.metrics(refs, findings, n_matched)
        self.assertEqual(metrics["precision"], 0.0)
        self.assertEqual(metrics["recall"], 0.0)

    def test_false_positive_finding_hurts_precision_not_recall(self):
        refs = [{"path": "a.py", "side": "right", "from_line": 1, "to_line": 1,
                 "note": "the loop never terminates", "label": 1}]
        findings = [
            {"file": "a.py", "from_line": 1, "to_line": 1, "severity": "Important",
             "verdict": self._gated_verdict(True), "summary": "the loop never terminates"},
            {"file": "a.py", "from_line": 50, "to_line": 50, "severity": "Minor",
             "verdict": self._gated_verdict(True), "summary": "cosmetic nitpick"},
        ]
        _m, n_matched = self.m.match_results(refs, findings)
        metrics = self.m.metrics(refs, findings, n_matched)
        self.assertEqual(metrics["recall"], 1.0)
        self.assertEqual(metrics["precision"], 0.5)
        self.assertEqual(metrics["noise"], 0.5)

    def test_missing_real_issue_hurts_recall(self):
        refs = [
            {"path": "a.py", "side": "right", "from_line": 1, "to_line": 1,
             "note": "the loop never terminates", "label": 1},
            {"path": "a.py", "side": "right", "from_line": 2, "to_line": 2,
             "note": "the buffer overflows", "label": 1},
        ]
        findings = [{"file": "a.py", "from_line": 1, "to_line": 1,
                     "severity": "Important",
                     "verdict": self._gated_verdict(True),
                     "summary": "the loop never terminates"}]
        _m, n_matched = self.m.match_results(refs, findings)
        metrics = self.m.metrics(refs, findings, n_matched)
        self.assertEqual(metrics["recall"], 0.5)
        self.assertEqual(metrics["precision"], 1.0)
        self.assertAlmostEqual(metrics["f1"], 0.6666666, places=5)

    def test_signature_token_fallback_matches_paraphrased_same_identifier(self):
        # Real pair from the #631 aacr-results-2 run (pull/15267): the gate's summary
        # ("Generated json_extract call missing comma between field and pattern")
        # paraphrases the reference's concern in different words, naming the same
        # identifier "json_extract". seq-ratio 0.25 / jaccard 0.05 FAIL the lexical
        # gate — the signature-token fallback (shared ≥5-char identifier word among
        # line-matched candidates) must still reach it.
        refs = [{"path": "packages/support/src/helpers.php", "side": "right",
                 "from_line": 184, "to_line": 188,
                 "note": "The new condition for '->' JSON syntax must skip columns "
                         "starting with json_extract()",
                 "label": 1}]
        findings = [{"file": "packages/support/src/helpers.php", "from_line": 184,
                     "to_line": 188, "severity": "Important", "verdict": "CONFIRMED",
                     "summary": "Generated json_extract call missing comma between "
                                "field and pattern"}]
        self.assertFalse(self.m.lexical_similar(refs[0]["note"],
                                                findings[0]["summary"]))
        _m, n_matched = self.m.match_results(refs, findings)
        self.assertEqual(n_matched, 1)

    def test_signature_fallback_does_not_match_unrelated_finding_at_same_line(self):
        # The fallback must NOT bridge a finding at the right line about a different
        # defect: same location but no shared identifier ⇒ no match.
        refs = [{"path": "a.py", "side": "right", "from_line": 5, "to_line": 5,
                 "note": "the buffer overflows on large input", "label": 1}]
        findings = [{"file": "a.py", "from_line": 5, "to_line": 5,
                     "severity": "Important", "verdict": "CONFIRMED",
                     "summary": "cosmetic whitespace nitpick here"}]
        _m, n_matched = self.m.match_results(refs, findings)
        self.assertEqual(n_matched, 0)

    def test_refuted_findings_are_excluded_from_generated_count(self):
        # The gate DROPS REFUTED candidates (severity-verdict-contract §2). A
        # REFUTED finding must neither match nor inflate the generated denominator.
        refs = [{"path": "a.py", "side": "right", "from_line": 1, "to_line": 1,
                 "note": "real deadlock", "label": 1}]
        findings = [
            {"file": "a.py", "from_line": 1, "to_line": 1, "severity": "Critical",
             "verdict": self._gated_verdict(True), "summary": "real deadlock"},
            {"file": "a.py", "from_line": 2, "to_line": 2, "severity": "Minor",
             "verdict": self._gated_verdict(False), "summary": "drop me"},
        ]
        _m, n_matched = self.m.match_results(refs, findings)
        metrics = self.m.metrics(refs, findings, n_matched)
        self.assertEqual(n_matched, 1)
        # generated = kept findings only (1), not 2
        self.assertEqual(metrics["precision"], 1.0)
        self.assertEqual(metrics["recall"], 1.0)

    def test_matcher_is_deterministic_across_calls(self):
        refs = [{"path": "a.py", "side": "right", "from_line": i, "to_line": i,
                 "note": f"issue {i}", "label": 1} for i in range(1, 5)]
        findings = [{"file": "a.py", "from_line": i, "to_line": i,
                     "severity": "Important", "verdict": "CONFIRMED",
                     "summary": f"issue {i}"} for i in [1, 2, 3, 4]]
        r1 = self.m.match_results(refs, findings)
        r2 = self.m.match_results(refs, findings)
        self.assertEqual([x[0] for x in r1[0]], [x[0] for x in r2[0]])
        self.assertEqual([x[1] for x in r1[0]], [x[1] for x in r2[0]])
        self.assertEqual(r1[1], r2[1])


class TestAggregate(unittest.TestCase):
    def setUp(self):
        self.m = _import_module()

    def test_aggregate_metrics_pool_findings_and_references(self):
        refs = [
            {"path": "a.py", "side": "right", "from_line": 1, "to_line": 1,
             "note": "x", "label": 1},
            {"path": "b.py", "side": "right", "from_line": 2, "to_line": 2,
             "note": "y", "label": 1},
        ]
        findings = [
            {"file": "a.py", "from_line": 1, "to_line": 1, "severity": "Important",
             "verdict": "CONFIRMED", "summary": "x"},
            {"file": "b.py", "from_line": 2, "to_line": 2, "severity": "Important",
             "verdict": "CONFIRMED", "summary": "y"},
            {"file": "c.py", "from_line": 9, "to_line": 9, "severity": "Minor",
             "verdict": "CONFIRMED", "summary": "noise"},
        ]
        _m, n_matched = self.m.match_results(refs, findings)
        metrics = self.m.metrics(refs, findings, n_matched)
        self.assertEqual(metrics["precision"], 2 / 3)
        self.assertEqual(metrics["recall"], 1.0)
        self.assertAlmostEqual(metrics["f1"], 0.8, places=5)
        self.assertAlmostEqual(metrics["noise"], 1 / 3)


if __name__ == "__main__":
    unittest.main()