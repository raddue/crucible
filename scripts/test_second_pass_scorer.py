#!/usr/bin/env python3
"""#583 inquisitor — Integration / Edge Cases dimensions.

Regression coverage for `second_pass_scorer.py`'s entry-identity de-dup key
(`_norm` + `_dedupe_entries`). Two distinct crafted-string collisions were
found by an inquisitor adversarial pass and are pinned here so a future edit
to `_norm`/`_dedupe_entries` cannot silently reopen either:

  * Edge Cases AV2 — a `#### __pos_5`-style title collides with the
    positional sentinel `_dedupe_entries` mints for an UNTITLED entry at that
    same position, because both lived in one string-keyed namespace.
  * Edge Cases AV3 — a title using a non-ASCII whitespace-class code point
    (e.g. NBSP U+00A0) folded, under a Unicode-mode `\\s+`, onto the same
    normalized key as a visually-identical title using plain ASCII spaces.

Both bugs have the same observable shape: a genuine Fatal finding is silently
dropped by `_dedupe_entries` because it collides with an unrelated entry, and
`score()` reports `clean_pass=True` on a findings file that declares a Fatal.

Run from repo root:  python3 scripts/test_second_pass_scorer.py
"""
import importlib.util
import pathlib
import sys
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent / "second_pass_scorer.py"


def _import_scorer():
    spec = importlib.util.spec_from_file_location("second_pass_scorer", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclass field resolution needs this registered first
    spec.loader.exec_module(mod)
    return mod


sps = _import_scorer()


def _findings_block(fatal_title: str, other_title: str) -> str:
    return (
        "### Second Pass Findings\n\n"
        f"#### {fatal_title}\n"
        "**Finding:** the real defect.\n"
        "**Best Defense:** none.\n"
        "**Why The Defense Fails:** it fails.\n"
        "**Severity:** Fatal\n"
        "**Proposed Fix:** fix it.\n\n"
        f"#### {other_title}\n"
        "**Finding:** an unrelated Minor note.\n"
        "**Best Defense:** n/a.\n"
        "**Why The Defense Fails:** n/a.\n"
        "**Severity:** Minor\n"
        "**Proposed Fix:** n/a.\n"
    )


class TestATitleCannotImpersonateTheUntitledEntrySentinel(unittest.TestCase):
    """AV2: a titled entry whose `_norm()`'d title equals another entry's
    positional sentinel (`__pos_<start>`) must not collide with it."""

    def test_the_fatal_entry_is_not_swallowed_by_the_sentinel_collision(self):
        # An untitled entry has no `####` line of its own — it is identified
        # positionally. A titled entry using literally that sentinel string
        # must not be treated as "the same entry".
        text = (
            "### Second Pass Findings\n\n"
            "**Finding:** the real defect (untitled).\n"
            "**Best Defense:** none.\n"
            "**Why The Defense Fails:** it fails.\n"
            "**Severity:** Fatal\n"
            "**Proposed Fix:** fix it.\n\n"
            "#### __pos_5\n"
            "**Finding:** an unrelated Minor note.\n"
            "**Best Defense:** n/a.\n"
            "**Why The Defense Fails:** n/a.\n"
            "**Severity:** Minor\n"
            "**Proposed Fix:** n/a.\n"
        )
        result = sps.score(text)
        self.assertEqual(result.fatal_count, 1, "the Fatal was swallowed by the sentinel collision")
        self.assertFalse(result.clean_pass)


class TestUnicodeWhitespaceTitlesAreDistinctEntries(unittest.TestCase):
    """AV3: a title using a non-ASCII whitespace code point must not collide,
    via `_norm`'s whitespace folding, with a visually-identical ASCII-space
    title."""

    def test_two_visually_identical_titles_do_not_delete_the_second_finding(self):
        ascii_title = "Fatal Race Condition"
        nbsp_title = "Fatal Race Condition"  # visually identical, byte-distinct
        text = _findings_block(ascii_title, nbsp_title)
        result = sps.score(text)
        self.assertEqual(result.fatal_count, 1, "the Fatal was swallowed by a Unicode-whitespace collision")
        self.assertFalse(result.clean_pass)

    def test_normalize_does_not_fold_non_ascii_whitespace_onto_ascii_space(self):
        self.assertNotEqual(sps._norm("a b"), sps._norm("a b"))
        self.assertNotEqual(sps._norm("a b"), sps._norm("a b"))
        self.assertNotEqual(sps._norm("a b"), sps._norm("a b"))
        self.assertNotEqual(sps._norm("a　b"), sps._norm("a b"))

    def test_ascii_whitespace_runs_still_fold_for_genuine_reformatting(self):
        # The narrowed fold must still collapse ordinary re-flowed ASCII
        # whitespace (multiple spaces / tabs), so a genuinely-duplicated
        # finding restated with different ASCII spacing still dedupes.
        self.assertEqual(sps._norm("a   b"), sps._norm("a b"))
        self.assertEqual(sps._norm("a\tb"), sps._norm("a b"))
        self.assertEqual(sps._norm("  Fatal Thing  "), sps._norm("Fatal Thing"))


class TestDashBoundaryRequiresWhitespace(unittest.TestCase):
    """SIEGE-FA-2 (PR #583 warden gate): both prose homes
    (quality-gate/SKILL.md:324, red-team-prompt.md:156) state explicitly that
    the severity-token dash boundary requires whitespace before the dash — "a
    spaced dash counts; an unspaced one does not" — unlike the punctuation
    boundary (`(`, `[`, `,`, `.`, `:`, `;`), which allows optional whitespace.
    The #583 Edge Cases AV4 change widened the dash arm to optional
    whitespace on the theory that requiring it was an oversight; it was not —
    the spec's own worked examples are pinned here directly, with zero prior
    regression coverage before this test (FA-4)."""

    def test_spaced_hyphen_recognises(self):
        # Spec worked example: "Fatal - blocks the release" recognises as Fatal.
        token, annotated = sps.parse_severity_token("Fatal - blocks the release")
        self.assertEqual(token, "Fatal")
        self.assertTrue(annotated)

    def test_spaced_em_dash_recognises(self):
        token, annotated = sps.parse_severity_token("Fatal — blocks the release")
        self.assertEqual(token, "Fatal")
        self.assertTrue(annotated)

    def test_unspaced_em_dash_does_not_recognise(self):
        # Spec: an unspaced dash does NOT count — falls through to the
        # fail-loud malformed default (caller scores this Significant).
        token, annotated = sps.parse_severity_token("Fatal—rationale")
        self.assertIsNone(token)

    def test_minor_to_significant_hedge_does_not_recognise_as_minor(self):
        # The spec's own named counter-example: "Minor-to-Significant" begins
        # with "Minor" but has no whitespace before its hyphen — must NOT
        # recognise as Minor (which would wrongly exclude it from the
        # weighted score as non-gating).
        token, annotated = sps.parse_severity_token("Minor-to-Significant")
        self.assertIsNone(token)

    def test_minor_to_significant_entry_scores_significant_not_minor(self):
        # End-to-end: an entry declaring this hedge must count toward the
        # weighted score as Significant (fail-loud default), not be silently
        # excluded as a non-gating Minor.
        text = (
            "### Second Pass Findings\n\n"
            "#### Ambiguous severity hedge\n"
            "**Finding:** the reviewer would not commit to a severity.\n"
            "**Best Defense:** none.\n"
            "**Why The Defense Fails:** it fails.\n"
            "**Severity:** Minor-to-Significant\n"
            "**Proposed Fix:** state the real severity.\n"
        )
        result = sps.score(text)
        self.assertEqual(result.significant_count, 1)
        self.assertEqual(result.minor_count, 0)
        self.assertNotEqual(result.route, "clean-pass")


if __name__ == "__main__":
    unittest.main(verbosity=2)
