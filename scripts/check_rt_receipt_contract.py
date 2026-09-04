#!/usr/bin/env python3
"""Structural checker for the #366 red-team ↔ quality-gate Evidence Receipt contract.

Invocation (from repo root):
    python3 scripts/check_rt_receipt_contract.py
    python3 scripts/check_rt_receipt_contract.py --selftest

Acceptance test for #366 (design:
`docs/plans/2026-06-06-366-rt-qg-receipt-contract-design.md`). Asserts the design's
acceptance criteria over exactly FOUR named skill-methodology Markdown files:

    skills/red-team/red-team-prompt.md   — Report Format / RCPT v1.1 / worked examples
    skills/quality-gate/SKILL.md         — consumption + fix-agent supersession + writer-inversion
    skills/red-team/SKILL.md             — standalone consumption (Tier-1 lint, no Layer-2 sweep)
    skills/shared/return-convention.md   — kind=grep artifact/range clarification

Each assertion is keyed to a design AC and carries an ID prefix ([A1], [C13], …) in
its violation string. Every assertion pins on a token/phrase the corresponding edit
INTRODUCES (absent in the unedited file) so it discriminates RED→GREEN; [A6] is the
sole exception — a retain-guard that is GREEN at baseline and only goes RED if a
future edit DELETES the rich findings sections.

The quality-gate/SKILL.md present-pins that used to assert verbatim English prose
([C14] "orchestrator-supplied", [C15] "cited artifact", [C18] witness phrasing, [C18b]
"initial writer") were migrated to structural `<!-- CONTRACT:NAME -->` anchors (#399)
so a benign wording edit on the repo's hottest file no longer trips CI — the anchor is
the regression guard, the prose inside is freely editable. The code-token pins
([C13] `### … Challenges`, [C16] `TRIPWIRE: none`, [C17] `ARTIFACTS`) stay verbatim:
editing those IS a contract change. See scripts/CHECKER_CONVENTIONS.md.

NO directory tree-walk: only the four named files are read, so the checker can never
self-match its own literal pin strings (CONTRACT anchors included). Stdlib only
(`pathlib`, `re`, `sys`).
Exits 0 if all assertions hold, 1 with a bulleted violation list otherwise.

Mirrors `scripts/check_canonical_drift.py` and `scripts/check_i2_marker.py`.
"""
from __future__ import annotations
import pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
RT_PROMPT = ROOT / "skills/red-team/red-team-prompt.md"
QG_SKILL = ROOT / "skills/quality-gate/SKILL.md"
RT_SKILL = ROOT / "skills/red-team/SKILL.md"
RETURN_CONV = ROOT / "skills/shared/return-convention.md"

# Worked-example markers Task 1 DECLARES and Task 2 emits verbatim (load-bearing
# coupling — the checker keys block extraction off these exact strings).
PASS_MARKER = "<!-- worked-example: PASS -->"
FAIL_MARKER = "<!-- worked-example: FAIL -->"

# Polarity guard (#561 round 1 S1): a negation token immediately before an
# anchor phrase flips the rule's meaning while leaving the anchor phrase's
# bare substring intact — e.g. "NOT the same population" still contains "same
# population", and "explicitly EXCLUDING ... Second Pass Findings" still
# contains "Second Pass Findings". `[^.]{0,40}` keeps the check within the
# same clause.
_NEGATION_TOKENS = (
    r"(?:not|never|excluding|except|ignor\w*|less|minus|omitting|"
    r"apart\s+from|other\s+than)"
)
# FA2-2 (PR #583 warden gate): the pre-existing closed vocabulary (not/never/
# excluding/except/ignor*) was trivially evaded by "less"/"minus"/"omitting"/
# "apart from"/"other than" — verified live: replacing "plus any Fatal/
# Significant..." with "less any..." in red-team/SKILL.md inverts the
# polarity of #561's entire thesis and every checker relying on this
# vocabulary still PASSed. Not a full fix for the general "oracle-pattern
# vocabulary-only pin" class (tracked separately) — a narrower vocabulary
# expansion for this specific, verified evasion.


def _negates(anchor: str, scope: str) -> bool:
    """#561 fresh round 12 S3: a negation token immediately followed by a
    hyphen is part of a compound term (e.g. "NOT-SATISFIABLE"), not a
    negation of whatever follows it in prose — without the `(?!-)` guard,
    the literal state name "NOT-SATISFIABLE" false-positives every polarity
    check on an anchor phrase appearing anywhere in the same clause after
    it, live-verified against `skills/red-team/SKILL.md` step 4's own
    NOT-SATISFIABLE treatment sentence."""
    return re.search(rf"(?i)\b{_NEGATION_TOKENS}\b(?!-)[^.]{{0,40}}{re.escape(anchor)}", scope) is not None


# Detail-token set for the #561 second-pass-population parse's stale-prone
# normalization/boundary/fence-parity content — shared by [A6e] (the
# red-team-prompt.md bracket) and [D19]/[D19b] (red-team/SKILL.md's step-3/
# step-4 restatement homes, #561 fresh round 6 S4). Mirrors
# check_qg_second_pass_score.py's own `_pointer_or_complete` and its
# `detail_tokens` tuple (own copy, per this repo's stdlib-only/no-cross-file-
# import convention — see module docstring).
_DETAIL_TOKENS = (
    "markdown emphasis markers",
    # (#561 fresh round 6 S2): "immediately followed" alone is a loose proxy
    # any unrelated sentence can satisfy — pin the full charset-enumeration
    # substring, byte-identical between SKILL.md and red-team-prompt.md.
    "immediately followed by end-of-line, or by one of `(`, `[`, `,`, `.`, `:`, `;`",
    "ODD number of triple-backtick delimiters",
)


def _pointer_or_complete(scope: str, label: str) -> str | None:
    """Return an error string if `scope` neither points at the
    `qg-score-second-pass-population` CONTRACT block nor carries the full
    detail-token set, or carries a pointer beside a PARTIAL (contradictory)
    detail-token set (#561 fresh round 5 S1/S2). Returns None when clean."""
    present = [tok in scope for tok in _DETAIL_TOKENS]
    has_all_details = all(present)
    has_pointer = "qg-score-second-pass-population" in scope and "CONTRACT block" in scope
    has_partial_details = any(present) and not has_all_details
    if has_all_details or (has_pointer and not has_partial_details):
        return None
    if has_pointer and has_partial_details:
        return (
            f"{label} carries a CONTRACT-block pointer alongside a PARTIAL "
            "restatement (#561 fresh round 5 S2: at least one, but not all "
            "three, of the stale-prone detail tokens is present beside the "
            "pointer)"
        )
    return (
        f"{label} neither carries the full normalization + boundary-"
        "character-list + fence-parity detail set nor points cleanly at the "
        "`qg-score-second-pass-population` CONTRACT block"
    )


# Part 2 structural self-check, mirrored for [A6h]'s pin set (#561 fresh
# round 10 dispatch). Same rationale as check_qg_second_pass_score.py's own
# `_SECTION_LOC_UNIQUE_ANCHORS`/`check_section_location_anchor_uniqueness`:
# a bare `phrase in _sl` presence pin cannot tell WHICH sentence in the
# red-team-prompt.md Section-location mirror supplied the match, so a later
# sentence reusing an earlier one's exact anchor phrase silently converts
# the earlier [A6h] pin into a no-op. Enumerated explicitly, kept in sync
# with the literal presence-check strings [A6h] uses above.
_A6H_UNIQUE_ANCHORS = {
    "four-section FOUR marker": "FOUR sections",
    "START consequence": "earliest occurrence of such a heading line in the file",
    "START closing clause": "never overrides an earlier one as the section's start",
    "union trigger consequence": "counts the union of all matching sections",
    "union de-dup basis": "de-duplicated by entry identity",
    "zero-match trigger": "drives that section's matching-heading count to zero",
    "zero-match both-predicates": "both the start and end of that section",
    "zero-match end-to-end": "raw-heading location end-to-end",
    "END consequence": "extends to the end of the cited file",
    "missing-second-pass-section flag": "flags `missing-second-pass-section` in the narration log",
    "Scope sentence trigger (fresh round 8 SP1)": "reads the bytes of your findings file itself",
    "Scope sentence consequence (fresh round 8 SP1)": "does not change what counts as",
    "zero-match generalized-trigger clause (fresh round 12 S1)": "the fallback triggers on this OBSERVABLE condition itself",
    "zero-match balanced-fence alternative cause (fresh round 12 S1)": "otherwise-BALANCED, CLOSED fence, with no stray fence anywhere in the file",
}

# (#561 fresh round 10 follow-up 2) The two Scope-sentence entries above are
# KEPT, not removed, for the same reason `_SECTION_LOC_UNIQUE_ANCHORS` keeps
# its own Scope-sentence entries in check_qg_second_pass_score.py: the
# direct [A6h] Scope pin below now checks the sentence's positive
# consequence verbatim within a bounded window (what actually closes the
# relocation-attack gap — a count-only registry entry cannot distinguish
# "the real sentence, unmoved" from "a decoy elsewhere supplying the same
# two substrings"), but the registry still catches a DIFFERENT attack shape:
# a future sentence duplicating either phrase far outside the bounded
# window, which the direct pin below would not notice.

# Unlike the SKILL.md-side clause, the mirror currently phrases its END
# predicate as "the next such unfenced, unquoted heading" rather than
# repeating the full fence/blockquote phrase — so it has no known
# intentionally-shared phrase requiring a distinguisher pairing today. Kept
# as an explicit (currently empty) registry, not omitted, so a future round
# that DOES introduce a shared phrase in the mirror has an obvious place to
# register its distinguishers, mirroring `_SECTION_LOC_SHARED_ANCHORS`.
_A6H_SHARED_ANCHORS: dict[str, list[str]] = {}


def check_a6h_anchor_uniqueness(section_loc_mirror: str) -> list[str]:
    """Part 2 structural self-check (#561 fresh round 10 dispatch), mirrored
    for [A6h]'s pin set. See
    `check_qg_second_pass_score.check_section_location_anchor_uniqueness`
    for the full rationale — this is the same check applied to the
    red-team-prompt.md Section-location mirror instead of SKILL.md's
    CONTRACT-block clause."""
    errs: list[str] = []

    for label, phrase in _A6H_UNIQUE_ANCHORS.items():
        count = section_loc_mirror.count(phrase)
        if count == 0:
            errs.append(
                f"[A6h] ANCHOR-UNIQUENESS: '{label}' anchor phrase "
                f"{phrase!r} not found in the Section location mirror at "
                "all (#561 fresh round 10 Part 2 self-check)"
            )
        elif count > 1:
            errs.append(
                f"[A6h] ANCHOR-UNIQUENESS COLLISION: '{label}' anchor "
                f"phrase {phrase!r} occurs {count} times in the Section "
                "location mirror — a presence-only pin on this phrase can "
                "no longer tell which sentence supplied the match, so a "
                "different sentence's copy of the same phrase silently "
                "converts this pin into a no-op (#561 fresh round 10 Part "
                "2 self-check)"
            )

    for shared_phrase, distinguishers in _A6H_SHARED_ANCHORS.items():
        occurrences = section_loc_mirror.count(shared_phrase)
        if occurrences != len(distinguishers):
            errs.append(
                "[A6h] ANCHOR-UNIQUENESS COLLISION: the shared phrase "
                f"{shared_phrase!r} occurs {occurrences} times in the "
                f"Section location mirror but only {len(distinguishers)} "
                "distinguishing anchor(s) are registered for it in "
                "`_A6H_SHARED_ANCHORS` (#561 fresh round 10 Part 2 "
                "self-check)"
            )
        for d in distinguishers:
            if d not in section_loc_mirror:
                errs.append(
                    f"[A6h] ANCHOR-UNIQUENESS: distinguishing anchor {d!r} "
                    f"registered for the shared phrase {shared_phrase!r} "
                    "is missing from the Section location mirror (#561 "
                    "fresh round 10 Part 2 self-check)"
                )

    return errs


# ---------------------------------------------------------------------------
# A. red-team-prompt.md — Report Format / RCPT v1.1 (design AC#1, #2)
# ---------------------------------------------------------------------------

def check_rt_prompt(text: str) -> list[str]:
    errs: list[str] = []

    # [A1] receipt header token
    if "RCPT v1.1" not in text:
        errs.append("[A1] red-team-prompt.md: missing receipt header token 'RCPT v1.1'")

    # [A2] all seven receipt section labels — CASE-SENSITIVE uppercase labels.
    # The existing prose `Verdict:` / `Confidence` must NOT satisfy these pins.
    for label in ("VERDICT", "ARTIFACTS", "TRACE", "CLAIMS", "WITNESS", "SUSPICION", "NEXT"):
        if label not in text:
            errs.append(f"[A2] red-team-prompt.md: missing uppercase receipt label '{label}'")

    # [A3] mandatory v1.1 lines
    for tok in ("TRIPWIRE:", "SUPERSEDES:"):
        if tok not in text:
            errs.append(f"[A3] red-team-prompt.md: missing mandatory v1.1 line token '{tok}'")

    # [A4] findings-output placeholder
    if "[FINDINGS_OUTPUT_PATH]" not in text:
        errs.append("[A4] red-team-prompt.md: missing placeholder '[FINDINGS_OUTPUT_PATH]'")

    # [A5] counts-line spec token + field names
    if "SEVERITY-COUNTS:" not in text:
        errs.append("[A5] red-team-prompt.md: missing counts-line token 'SEVERITY-COUNTS:'")
    for field in ("fatal=", "significant=", "minor="):
        if field not in text:
            errs.append(f"[A5] red-team-prompt.md: missing SEVERITY-COUNTS field name '{field}'")

    # [A6] RETAIN-GUARD: rich findings sections still present. GREEN at baseline;
    # goes RED only if a future edit deletes these sections.
    for section in ("### Fatal Challenges", "### Significant Challenges",
                    "### Minor Observations", "### Dimension Coverage",
                    "### Second Pass Findings"):
        if section not in text:
            errs.append(f"[A6] red-team-prompt.md: rich findings section '{section}' was DELETED (retain-guard)")

    # [A6b] RETAIN-GUARD: the Second Pass section's REQUIRED-ness, not just its
    # heading (#561 round 2 S4) — a future edit could keep the heading but
    # downgrade "## Second Pass (REQUIRED)" to "(optional)", silently collapsing
    # the score population [A6] alone would not catch.
    if "## Second Pass (REQUIRED)" not in text:
        errs.append(
            "[A6b] red-team-prompt.md: '## Second Pass (REQUIRED)' token was DELETED or "
            "downgraded (retain-guard — the second pass must stay REQUIRED, not optional)"
        )

    # [A6c] the REVIEWER-facing half of the entry definition (#561 round 1 S4):
    # the orchestrator-facing half is pinned hard by
    # check_qg_second_pass_score.py's assertion (e1); this half — what the
    # reviewer is told to write, in the '### Second Pass Findings' report-format
    # bracket — had NO structural guard before. Scoped to that bracket, not the
    # whole file, so an unrelated mention elsewhere cannot satisfy it.
    sp_bracket_m = re.search(r"### Second Pass Findings\n\s*\[.*\]", text)
    sp_bracket = sp_bracket_m.group(0) if sp_bracket_m else ""
    if not sp_bracket_m:
        errs.append(
            "[A6c] red-team-prompt.md: '### Second Pass Findings' report-format "
            "bracket not found"
        )
    else:
        if not re.search(
            r"first non-whitespace characters are `\*\*Finding:\*\*`.{0,200}and/or"
            r".{0,150}first non-whitespace characters are `\*\*Severity:\*\*`",
            sp_bracket, re.DOTALL,
        ):
            errs.append(
                "[A6c] red-team-prompt.md: the '### Second Pass Findings' bracket is "
                "missing the LINE-ANCHORED content-marker construction ('a line whose "
                "first non-whitespace characters are **Finding:** ... and/or ... a "
                "line whose first non-whitespace characters are **Severity:**') that "
                "must mirror the orchestrator-facing rule (#561 round 1 S2/S4)"
            )
        if not re.search(r"heading itself is never what makes text scored", sp_bracket):
            errs.append(
                "[A6c] red-team-prompt.md: the '### Second Pass Findings' bracket is "
                "missing the 'heading itself is never what makes text scored' clause "
                "(#561 round 4 F1 / round 1 S4: the reviewer-facing half must state the "
                "same rule as the orchestrator-facing one)"
            )
        # (#561 round 4 F1): the entry BOUNDARY rule — where one entry ends and
        # the next begins — must be mirrored to the reviewer, not only stated
        # for the orchestrator, or a reviewer filing a single Steel-Man block
        # (one **Finding:** line, its own **Severity:** line later) has no way
        # to know it is one entry, not two.
        if not re.search(r"entry begins at the first line-initial.{0,400}whichever comes first", sp_bracket, re.DOTALL):
            errs.append(
                "[A6c] red-team-prompt.md: the '### Second Pass Findings' bracket is "
                "missing the entry-boundary rule ('an entry begins at the first "
                "line-initial **Finding:** or **Severity:** marker and extends to the "
                "line before the next #### heading or the next line-initial **Finding:** "
                "marker, whichever comes first') (#561 round 4 F1)"
            )
        # (#561 round 3 S1): the reviewer-facing halves of round 2's S2
        # (severity parse) and S3 (fenced/blockquote exclusion) fixes had NO
        # structural guard — deleting either left the full 86-suite green.
        # Anchored on "line inside a fenced code block" (#561 fresh round 6,
        # collision fix), not the bare "inside a fenced code block" fragment
        # — the S6 entry-boundary terminator clause below also legitimately
        # contains "not itself inside a fenced code block" (a condition on
        # the TERMINATOR, unrelated to this exclusion-rule sentence), which
        # the bare fragment's whole-bracket `_negates` scan misfires on.
        if not re.search(r"(?i)line inside a fenced code block", sp_bracket):
            errs.append(
                "[A6c] red-team-prompt.md: the '### Second Pass Findings' bracket is "
                "missing the fenced-code-block exclusion sentence (#561 round 3 S1: "
                "the reviewer-facing half of round 2's S3 fix had no structural guard)"
            )
        elif _negates("line inside a fenced code block", sp_bracket):
            errs.append(
                "[A6c] red-team-prompt.md: the fenced-code-block exclusion sentence "
                "NEGATES 'inside a fenced code block' instead of asserting it "
                "(#561 round 1 S1 polarity guard)"
            )
        if not re.search(r"beginning with a blockquote marker", sp_bracket):
            errs.append(
                "[A6c] red-team-prompt.md: the '### Second Pass Findings' bracket is "
                "missing the blockquote-marker exclusion sentence (#561 round 3 S1)"
            )
        elif _negates("beginning with a blockquote marker", sp_bracket):
            errs.append(
                "[A6c] red-team-prompt.md: the blockquote-marker exclusion sentence "
                "NEGATES 'beginning with a blockquote marker' instead of asserting it "
                "(#561 round 1 S1 polarity guard)"
            )
        if not re.search(r"begins with `Fatal` */ *`Significant` */ *`Minor`", sp_bracket):
            errs.append(
                "[A6c] red-team-prompt.md: the '### Second Pass Findings' bracket is "
                "missing the severity-value sentence ('begins with `Fatal` / "
                "`Significant` / `Minor`') (#561 round 3 S1: the reviewer-facing half "
                "of round 2's S2 fix had no structural guard)"
            )
        elif _negates("begins with", sp_bracket):
            errs.append(
                "[A6c] red-team-prompt.md: the severity-value sentence NEGATES "
                "'begins with' (e.g. 'does not begin with') instead of asserting it "
                "(#561 round 1 S1 polarity guard)"
            )
        if not re.search(r"scored as Significant by default", sp_bracket):
            errs.append(
                "[A6c] red-team-prompt.md: the '### Second Pass Findings' bracket is "
                "missing the malformed-default clause ('scored as Significant by "
                "default ... flagged as malformed') (#561 round 3 S1)"
            )
        elif _negates("scored as Significant by default", sp_bracket):
            errs.append(
                "[A6c] red-team-prompt.md: the malformed-default clause NEGATES "
                "'scored as Significant by default' instead of asserting it "
                "(#561 round 1 S1 polarity guard)"
            )

        # [A6c] continued — S5 sweep, CONSEQUENCE pins for four reviewer-facing
        # clauses (#561 fresh round 7 S5): the checks above pin each clause's
        # TRIGGER phrase but not, in every case, its own CONSEQUENCE — mirrors
        # check_qg_second_pass_score.py's identical sweep of the
        # orchestrator-facing side of the same four clauses.
        fence_bq_rt_m = re.search(r"beginning with a blockquote marker.{0,150}", sp_bracket, re.DOTALL)
        if not (fence_bq_rt_m and "is never an entry-opening line" in fence_bq_rt_m.group(0)):
            errs.append(
                "[A6c] red-team-prompt.md: the fenced-code-block/blockquote "
                "exclusion sentence does not carry its own CONSEQUENCE ('is "
                "never an entry-opening line') within reach of its trigger "
                "phrases (#561 fresh round 7 S5)"
            )
        elif _negates("is never an entry-opening line", fence_bq_rt_m.group(0)):
            errs.append(
                "[A6c] red-team-prompt.md: the fenced-code-block/blockquote "
                "consequence NEGATES 'is never an entry-opening line' instead "
                "of asserting it (#561 round 1 S1 polarity guard)"
            )

        if not re.search(r"mid-sentence or quoted occurrence", sp_bracket):
            errs.append(
                "[A6c] red-team-prompt.md: the '### Second Pass Findings' "
                "bracket is missing the mid-sentence/quoted-occurrence "
                "exclusion sentence (#561 fresh round 7 S5: the reviewer-"
                "facing half of round 1's S2 fix had no structural guard at "
                "all in this checker)"
            )
        else:
            mid_sentence_rt_m = re.search(r"mid-sentence or quoted occurrence.{0,180}", sp_bracket, re.DOTALL)
            if not (mid_sentence_rt_m and "does NOT make surrounding text an entry" in mid_sentence_rt_m.group(0)):
                errs.append(
                    "[A6c] red-team-prompt.md: the mid-sentence/quoted-"
                    "occurrence exclusion sentence does not carry its own "
                    "CONSEQUENCE ('does NOT make surrounding text an entry') "
                    "(#561 fresh round 7 S5)"
                )
            elif _negates("does NOT make surrounding text an entry", mid_sentence_rt_m.group(0)):
                errs.append(
                    "[A6c] red-team-prompt.md: the mid-sentence/quoted-"
                    "occurrence consequence NEGATES 'does NOT make surrounding "
                    "text an entry' instead of asserting it (#561 round 1 S1 "
                    "polarity guard)"
                )

        malformed_default_rt_m = re.search(r"scored as Significant by default.{0,60}", sp_bracket, re.DOTALL)
        if not (malformed_default_rt_m and "flagged as malformed" in malformed_default_rt_m.group(0)):
            errs.append(
                "[A6c] red-team-prompt.md: the malformed-default clause does "
                "not carry its 'flagged as malformed' consequence within "
                "reach of 'scored as Significant by default' (#561 fresh "
                "round 7 S5)"
            )
        elif _negates("flagged as malformed", malformed_default_rt_m.group(0)):
            errs.append(
                "[A6c] red-team-prompt.md: the malformed-default clause "
                "NEGATES 'flagged as malformed' instead of asserting it "
                "(#561 round 1 S1 polarity guard)"
            )

        # Window widened #561 fresh round 12 (M2: this pattern of undersized
        # fixed windows has recurred three times — widen with real headroom):
        # the round-12 Second Pass finding's trailing-whitespace-strip clause
        # added ~300 chars between the trigger and its consequence (measured
        # live at ~970 chars), pushing the old 650-char window past the
        # consequence phrase entirely.
        recognised_rt_m = re.search(r"begins with `Fatal` */ *`Significant` */ *`Minor`.{0,1400}", sp_bracket, re.DOTALL)
        if not (recognised_rt_m and "the entry is scored at that recognised severity" in recognised_rt_m.group(0)):
            errs.append(
                "[A6c] red-team-prompt.md: the severity-value sentence does "
                "not carry its own CONSEQUENCE ('the entry is scored at that "
                "recognised severity') within reach of the 'begins with "
                "Fatal/Significant/Minor' trigger (#561 fresh round 7 S5)"
            )
        elif _negates("the entry is scored at that recognised severity", recognised_rt_m.group(0)):
            errs.append(
                "[A6c] red-team-prompt.md: the recognised-severity consequence "
                "NEGATES 'the entry is scored at that recognised severity' "
                "instead of asserting it (#561 round 1 S1 polarity guard)"
            )

        # [A6e] F2 pointer-or-complete parity for the reviewer-facing bracket
        # (#561 fresh round 5 S1): check_qg_second_pass_score.py's (p)
        # assertion's `_pointer_or_complete` covers only two of what is now a
        # SIX-home restatement census (#561 fresh round 6 S4 widened the
        # census from four to six — see [D19]/[D19b] below, red-team/SKILL.md's
        # two standalone-consumption sites): (1) the anti-rationalization row
        # and (2) INV-561-1, both in SKILL.md, are pinned by
        # check_qg_second_pass_score.py's (p); `red-team-prompt.md`'s bracket
        # ([A6e], here) carries the LARGEST full restatement of the rule and
        # was pinned for structure by [A6c] above, but never for the three
        # stale-prone detail tokens that rule's normalization/boundary/
        # fence-parity fixes introduced — live-verified that reverting the
        # bracket to the stale pre-round-3/4 parse left the full suite green.
        _a6e_err = _pointer_or_complete(
            sp_bracket,
            "[A6e] red-team-prompt.md: the '### Second Pass Findings' bracket",
        )
        if _a6e_err:
            errs.append(
                _a6e_err + " (#561 fresh round 5 S1: this is the largest full "
                "restatement of the rule and must go stale-proof the same way "
                "check_qg_second_pass_score.py's (p) assertion protects the "
                "other two restatement homes; a PARTIAL detail-token set "
                "beside a pointer is rejected the same way per #561 fresh "
                "round 5 S2)"
            )

        # [A6f] SP1 entry-boundary terminator fence/blockquote qualifier (#561
        # fresh round 5 SP1, mirrored from SKILL.md; referent made explicit
        # #561 fresh round 6 S6): the terminator clause must be qualified
        # against the fence/blockquote CONDITION itself, not the fence/
        # blockquote exclusion rule's OPENING-line predicate (undefined for a
        # `####` heading, which is never an entry-opening line regardless of
        # fencing — the predicate-based wording let the diff's own eval #19
        # adopt the vacuous reading under which no `####` heading terminates
        # an entry), or a fenced `####`/`**Finding:**` inside a quoted excerpt
        # can terminate an open entry even though it cannot open one.
        if not re.search(
            r"marker that is not itself inside a fenced code block or "
            r"prefixed by a blockquote marker \(`> `\), whichever comes first",
            sp_bracket,
        ):
            errs.append(
                "[A6f] red-team-prompt.md: the '### Second Pass Findings' "
                "bracket's entry-boundary terminator clause does not state the "
                "explicit, condition-based referent ('that is not itself "
                "inside a fenced code block or prefixed by a blockquote "
                "marker (`> `)') (#561 fresh round 5 SP1 / fresh round 6 S6)"
            )

        # [A6g] SP2 list-marker stripping (#561 fresh round 5 SP2, mirrored
        # from SKILL.md): a list-marker-prefixed `- **Severity:** Fatal` line
        # was silently not an entry — the reviewer-facing half needs the same
        # stripping rule as the orchestrator-facing one.
        if not re.search(r"strip an optional leading list marker", sp_bracket):
            errs.append(
                "[A6g] red-team-prompt.md: the '### Second Pass Findings' "
                "bracket is missing the list-marker stripping clause (#561 "
                "fresh round 5 SP2)"
            )
        elif _negates("strip an optional leading list marker", sp_bracket):
            errs.append(
                "[A6g] red-team-prompt.md: the list-marker stripping clause "
                "NEGATES 'strip an optional leading list marker' instead of "
                "asserting it (#561 round 1 S1 polarity guard)"
            )

        # [A6g] continued — S1(b) positive-CONSEQUENCE pin (#561 fresh round 6
        # S1(b)): `_negates` only looks BACKWARDS from an anchor, so it does
        # not guard a rewrite of the clause's own second half. Mirrors
        # check_qg_second_pass_score.py's equivalent SKILL.md-side pin.
        list_marker_rt_m = re.search(r"strip an optional leading list marker.{0,300}", sp_bracket, re.DOTALL)
        if not (list_marker_rt_m and "still opens (or carries) an entry" in list_marker_rt_m.group(0)):
            errs.append(
                "[A6g] red-team-prompt.md: the list-marker stripping clause "
                "does not carry its own positive CONSEQUENCE ('still opens "
                "(or carries) an entry') within reach of its trigger phrase "
                "(#561 fresh round 6 S1(b): a rewrite that keeps 'strip an "
                "optional leading list marker' but flips the second half to a "
                "NOT-an-entry consequence is otherwise undetected)"
            )
        elif list_marker_rt_m and _negates("still opens (or carries) an entry", list_marker_rt_m.group(0)):
            errs.append(
                "[A6g] red-team-prompt.md: the list-marker stripping "
                "consequence NEGATES 'still opens (or carries) an entry' "
                "instead of asserting it (#561 round 1 S1 polarity guard)"
            )

        # [A6h] section-location mirror parity (#561 fresh round 8 S3): the
        # SKILL.md clause governs FOUR sections with a zero-match rule, a
        # union tiebreak, and an explicit end definition (#561 fresh round 8
        # F1/S1/S4/S5/SP2) — the reviewer-facing mirror had none of the
        # tiebreak/zero-match/fourth-section content and was checked by
        # nothing at all; live-verified deleting the whole Section location
        # sentence from the bracket left the suite green. Window widened
        # #561 fresh round 9 (F1/S1/S2 grew the mirror to ~1900 chars);
        # widened again #561 fresh round 10 (S5's missing-second-pass-
        # section sentence grew it to ~2332 chars, measured live, headroom
        # kept above per round 8's own M1 lesson); widened again #561 fresh
        # round 10 follow-up Gap A (the Scope sentence pin added this round
        # sits at ~2790 chars in, measured live against the real on-disk
        # clause — the round-10 cap of 2700 cut it off); widened again #561
        # fresh round 12 (M2: real headroom this time — this pattern of
        # undersized fixed windows has recurred three times): the S1
        # generalized-trigger rewording pushed 'does not change what counts
        # as' to ~3116 chars, measured live.
        section_loc_rt_m = re.search(r"Section location.{0,3900}", sp_bracket, re.DOTALL)
        if not section_loc_rt_m:
            errs.append(
                "[A6h] red-team-prompt.md: the '### Second Pass Findings' "
                "bracket is missing the Section location mirror entirely "
                "(#561 fresh round 8 S3)"
            )
        else:
            _sl = section_loc_rt_m.group(0)
            if not (
                "### Fatal Challenges" in _sl
                and "### Significant Challenges" in _sl
                and "### Minor Observations" in _sl
                and re.search(r"FOUR sections", _sl)
            ):
                errs.append(
                    "[A6h] red-team-prompt.md: the Section location mirror "
                    "does not name all four sections (`### Fatal Challenges` "
                    "/ `### Significant Challenges` / `### Second Pass "
                    "Findings` / `### Minor Observations`) — (#561 fresh "
                    "round 8 SP2/S3)"
                )
            # Section START definition, with its OWN distinguishing
            # consequence (#561 fresh round 10 F1): every other pin in this
            # `[A6h]` set (four-section, union, zero-match, END) covers
            # content the START sentence itself does NOT restate, so none
            # of them detects a START-specific deletion or reversal (e.g.
            # "the LAST `###`-level heading ... governs, fenced or quoted
            # or not") — the mirror's START clause had no pin of its own at
            # all before this round. Mirrors the SKILL.md-side fix's
            # ordinal-position consequence exactly.
            if not (
                "earliest occurrence of such a heading line in the file" in _sl
                and "never overrides an earlier one as the section's start" in _sl
            ):
                errs.append(
                    "[A6h] red-team-prompt.md: the Section location mirror "
                    "does not define the section's START with its own "
                    "distinguishing consequence ('earliest occurrence of "
                    "such a heading line in the file' / 'never overrides an "
                    "earlier one as the section's start') — without this "
                    "the START clause is pinned only by a fence/blockquote "
                    "phrase the END clause also carries verbatim, so the "
                    "START clause can be deleted or reversed to 'the LAST "
                    "heading governs' undetected (#561 fresh round 10 F1)"
                )
            elif _negates("earliest occurrence of such a heading line in the file", _sl):
                errs.append(
                    "[A6h] red-team-prompt.md: the Section location mirror's "
                    "START definition NEGATES 'earliest occurrence of such "
                    "a heading line in the file' instead of asserting it "
                    "(#561 fresh round 10 F1 polarity guard)"
                )
            # Scope sentence (#561 fresh round 8 SP1, mirror-side pin added
            # fresh round 10 follow-up Gap A; consequence-anchored fresh
            # round 10 follow-up 2): the parse target is the cited findings
            # file's own bytes, not an enclosing document (e.g. an eval
            # prompt) that happens to quote it — this had NO pin on the
            # mirror side at all; deleting the sentence tripped nothing.
            #
            # (#561 fresh round 10 follow-up 2) The follow-up Gap A pin
            # originally required only bare, UNBOUNDED co-occurrence of the
            # trigger phrase and the generic token "does not change what
            # counts as" anywhere in the whole mirror window — weaker even
            # than the SKILL.md-side pin this same follow-up fixes (that one
            # at least bounded a 250-char window). A relocation attack —
            # delete the real sentence, add a decoy elsewhere in the mirror
            # asserting the opposite meaning while still containing both
            # phrases once each — passed this check undetected for the same
            # structural reason round-10-followup-verification.md documented
            # on the SKILL.md side (a bare co-occurrence check cannot tell
            # WHICH sentence supplied the match). Require the real
            # sentence's own consequence clause VERBATIM within the
            # trigger's own captured window instead of a bare co-occurrence.
            scope_sentence_rt_m = re.search(
                r"reads the bytes of your findings file itself.{0,250}",
                _sl, re.DOTALL,
            )
            scope_sentence_rt_window = (
                scope_sentence_rt_m.group(0) if scope_sentence_rt_m else ""
            )
            if not (
                scope_sentence_rt_m
                and 'does not change what counts as "the file"' in scope_sentence_rt_window
            ):
                errs.append(
                    "[A6h] red-team-prompt.md: the Section location mirror "
                    "does not scope itself to the cited findings file's own "
                    "bytes with its own positive-consequence clause verbatim "
                    "('this location step reads the bytes of your findings "
                    "file itself ... does not change what counts as \"the "
                    "file\"') — a bare, unbounded co-occurrence of the "
                    "trigger phrase and a generic token is satisfiable by a "
                    "decoy sentence elsewhere in the mirror that asserts the "
                    "opposite meaning while preserving both phrases' counts "
                    "(#561 fresh round 8 SP1, mirror-side pin added fresh "
                    "round 10 follow-up Gap A; consequence-anchored fresh "
                    "round 10 follow-up 2)"
                )
            elif _negates('does not change what counts as "the file"', scope_sentence_rt_window):
                errs.append(
                    "[A6h] red-team-prompt.md: the Section location mirror's "
                    "Scope sentence NEGATES 'does not change what counts as "
                    "\"the file\"' via a prepended double-negation instead of "
                    "asserting it plainly (#561 fresh round 10 follow-up 2 "
                    "polarity guard)"
                )
            if not (
                re.search(r"counts the union of all matching sections", _sl)
                and "malformed-second-pass-sectioning" in _sl
            ):
                errs.append(
                    "[A6h] red-team-prompt.md: the Section location mirror "
                    "does not state the union tiebreak + "
                    "`malformed-second-pass-sectioning` flag on a >1 match, "
                    "matching SKILL.md's orchestrator-facing rule (#561 "
                    "fresh round 8 S3/S5: the prompt previously carried NO "
                    "tiebreak at all)"
                )
            elif _negates("union", _sl):
                errs.append(
                    "[A6h] red-team-prompt.md: the Section location mirror "
                    "NEGATES 'union' instead of asserting union-counting "
                    "(#561 round 1 S1 polarity guard)"
                )
            # Union de-dup basis (#561 fresh round 9 S2): the union rule's
            # parenthetical used to delegate de-dup to the cross-section
            # rules below, which are silent on a same-named-section
            # duplicate — the only kind the union can produce.
            if "de-duplicated by entry identity" not in _sl:
                errs.append(
                    "[A6h] red-team-prompt.md: the Section location mirror's "
                    "union tiebreak does not state its own entry-identity "
                    "de-dup basis for a same-named-section duplicate (#561 "
                    "fresh round 9 S2)"
                )
            elif _negates("de-duplicated by entry identity", _sl):
                errs.append(
                    "[A6h] red-team-prompt.md: the Section location mirror "
                    "NEGATES 'de-duplicated by entry identity' instead of "
                    "asserting it (#561 fresh round 9 S2 polarity guard)"
                )
            if not re.search(r"drives that section's matching-heading count to zero", _sl):
                errs.append(
                    "[A6h] red-team-prompt.md: the Section location mirror "
                    "does not state the zero-match rule (a fence-parity "
                    "defect driving a section's matching-heading count to "
                    "zero must not be read as an empty section) — #561 fresh "
                    "round 8 F1/S3"
                )
            # Zero-match rule, generalized OBSERVABLE trigger (#561 fresh
            # round 12 S1): a section whose only matching heading sits
            # inside an otherwise-BALANCED, CLOSED fence (no stray fence
            # anywhere) produced a zero matching-heading count that neither
            # this fallback (conditioned on a diagnosed stray fence) nor the
            # missing-second-pass-section flag (conditioned on no matching
            # heading existing at all) covered.
            if "the fallback triggers on this OBSERVABLE condition itself" not in _sl:
                errs.append(
                    "[A6h] red-team-prompt.md: the Section location mirror's "
                    "zero-match rule does not condition the fallback on the "
                    "OBSERVABLE zero-matching-heading-count condition itself "
                    "(rather than on a diagnosed stray-fence cause) — without "
                    "this, a section whose only matching heading sits inside "
                    "an otherwise-balanced, closed fence produces a zero "
                    "count that neither this fallback nor the missing-"
                    "section flag covers (#561 fresh round 12 S1)"
                )
            elif _negates("the fallback triggers on this OBSERVABLE condition itself", _sl):
                errs.append(
                    "[A6h] red-team-prompt.md: the Section location mirror "
                    "NEGATES the observable-trigger clause instead of "
                    "asserting it (#561 round 1 S1 polarity guard)"
                )
            # Zero-match rule, BOTH predicates (#561 fresh round 9 S1): the
            # mirror previously said nothing about whether the suspension
            # covers the section's END search too.
            if not (
                "both the start and end of that section" in _sl
                and "raw-heading location end-to-end" in _sl
            ):
                errs.append(
                    "[A6h] red-team-prompt.md: the Section location mirror's "
                    "zero-match rule does not state that the fence exclusion "
                    "is suspended for BOTH the start and end of the section "
                    "— raw-heading location end-to-end (#561 fresh round 9 "
                    "S1)"
                )
            elif _negates("both the start and end of that section", _sl):
                errs.append(
                    "[A6h] red-team-prompt.md: the Section location mirror "
                    "NEGATES 'both the start and end of that section' "
                    "instead of asserting it (#561 fresh round 9 S1 polarity "
                    "guard)"
                )
            # Section END definition with its own positive CONSEQUENCE
            # (#561 fresh round 9 F1): a bare substring pin here previously
            # had no consequence anchor at all — the same gap the F1 finding
            # closed on the SKILL.md side.
            if "extends to the end of the cited file" not in _sl:
                errs.append(
                    "[A6h] red-team-prompt.md: the Section location mirror "
                    "does not define the section's END with its own "
                    "positive consequence ('extends to the end of the cited "
                    "file') (#561 fresh round 8 S4/S3, consequence pin added "
                    "#561 fresh round 9 F1)"
                )
            elif _negates("extends to the end of the cited file", _sl):
                errs.append(
                    "[A6h] red-team-prompt.md: the Section location mirror's "
                    "END definition NEGATES 'extends to the end of the "
                    "cited file' instead of asserting it (#561 fresh round 9 "
                    "F1 polarity guard)"
                )
            # missing-second-pass-section (#561 fresh round 10 S5): resolved
            # as a narration-only flag, matching SKILL.md's own fix.
            if "flags `missing-second-pass-section` in the narration log" not in _sl:
                errs.append(
                    "[A6h] red-team-prompt.md: the Section location mirror "
                    "does not flag `missing-second-pass-section` in the "
                    "narration log when one of the four mandated headings "
                    "is missing from the reviewer's report entirely (#561 "
                    "fresh round 10 S5)"
                )
            elif _negates("flags `missing-second-pass-section` in the narration log", _sl):
                errs.append(
                    "[A6h] red-team-prompt.md: the Section location mirror's "
                    "`missing-second-pass-section` clause NEGATES its own "
                    "trigger instead of asserting it (#561 fresh round 10 S5 "
                    "polarity guard)"
                )

            # Part 2 structural self-check (#561 fresh round 10 dispatch):
            # sweep the whole mirror for anchor-phrase collisions.
            errs.extend(check_a6h_anchor_uniqueness(_sl))

    # [A6i] the anti-inflation sentence for the Second Pass mandate (#561
    # fresh round 8 M2): "the ≥3 target is a search-effort floor, not a
    # filing quota" had no checker pin at all — deleting it left the suite
    # green, though it is the only counterweight to the incentive #561's
    # widening creates (second-pass findings now move the score).
    if "the ≥3 target is a search-effort floor, not a filing quota" not in text:
        errs.append(
            "[A6i] red-team-prompt.md: missing the anti-inflation sentence "
            "'the ≥3 target is a search-effort floor, not a filing quota' "
            "(#561 fresh round 8 M2)"
        )

    # [A6d] the widened SEVERITY-COUNTS sentence (#561 round 1 S4, narrowed round
    # 4 S4): a bare co-presence check ("Second Pass Findings" and "same
    # population" appear somewhere in the window) is defeated by an
    # out-of-vocabulary synonym that never uses the enumerated negation tokens
    # — e.g. rewording the clause to "<F>/<S> cover only first-pass sections
    # and OMIT entries you place under Second Pass Findings" leaves both
    # anchor phrases intact. This assertion therefore pins the POSITIVE
    # connective itself — the literal `include` clause — rather than the
    # absence of a negative, the same style (l)/(h) already use for their
    # literal-phrase pins. What is enforced: the exact substring `<F>`/`<S>`
    # include ... Fatal/Significant entries you place under ### Second Pass
    # Findings survives verbatim; a synonym rewrite that drops this literal
    # phrase trips the assertion regardless of what vocabulary replaces it.
    sc_idx = text.find("SEVERITY-COUNTS: fatal=<F> significant=<S> minor=<M>")
    sc_scope = text[sc_idx:sc_idx + 500] if sc_idx != -1 else ""
    if sc_idx == -1 or not re.search(
        r"<F>`/`<S>` include\s+Fatal/Significant entries you place under\s+"
        r"`### Second Pass Findings`",
        sc_scope,
    ):
        errs.append(
            "[A6d] red-team-prompt.md: the SEVERITY-COUNTS field-name paragraph does "
            "not carry the literal '<F>`/`<S>` include ... Fatal/Significant entries "
            "you place under `### Second Pass Findings`' clause (#561 round 4 S4: a "
            "bare co-presence check is defeated by an out-of-vocabulary synonym like "
            "'omit'/'disregard' that never trips the enumerated negation-token guard)"
        )
    elif "same population" not in sc_scope:
        errs.append(
            "[A6d] red-team-prompt.md: the SEVERITY-COUNTS field-name paragraph does "
            "not pin '<F>'/'<S>' to 'the same population' the orchestrator counts "
            "(#561 round 1 S4)"
        )
    elif _negates("Second Pass Findings", sc_scope):
        errs.append(
            "[A6d] red-team-prompt.md: the SEVERITY-COUNTS field-name paragraph "
            "NEGATES '### Second Pass Findings' (e.g. 'explicitly EXCLUDE' immediately "
            "before it) instead of including it (#561 round 1 S1: a bare co-presence "
            "check is satisfied by the negated sentence too)"
        )

    # [A7] count-derived VERDICT mapping: '0 Fatal' co-located with 'PASS'.
    if not (re.search(r"0\s+[Ff]atal", text) and "PASS" in text):
        errs.append("[A7] red-team-prompt.md: missing count-derived VERDICT mapping ('0 Fatal' → 'PASS')")

    # ---- worked PASS/FAIL example pair (design AC#2b) ----
    pass_marks = text.count(PASS_MARKER)
    fail_marks = text.count(FAIL_MARKER)

    # [A8] both example markers present, each exactly once
    if pass_marks != 1 or fail_marks != 1:
        errs.append(
            f"[A8] red-team-prompt.md: worked-example markers not found exactly once "
            f"(PASS marker x{pass_marks}, FAIL marker x{fail_marks}; expected 1 each)"
        )
        # Cannot extract blocks reliably — A9/A9b/A10/A11/A12 all depend on the
        # markers; report them as un-evaluable and return.
        errs.append("[A9] red-team-prompt.md: WITNESS byte-identity unverifiable — example markers missing")
        errs.append("[A9b] red-team-prompt.md: WITNESS polarity unverifiable — example markers missing")
        errs.append("[A10] red-team-prompt.md: PASS-example zero-counts unverifiable — example markers missing")
        errs.append("[A11] red-team-prompt.md: FAIL-example nonzero-count unverifiable — example markers missing")
        errs.append("[A12] red-team-prompt.md: FAIL-example internal consistency unverifiable — example markers missing")
        return errs

    # Each worked example is an indented ```…``` code fence: the marker is followed by
    # an opening fence, the receipt body, then the receipt's own (indented) closing
    # fence. Bound each block on that closing fence rather than on a "next ### heading"
    # — the headings here are indented 4 spaces inside the outer fence, so a bare
    # "\n### " never matches and the old logic let the block run to EOF (dead boundary).
    def example_block(marker: str) -> str:
        start = text.index(marker)
        body = text[start:]
        # opening fence (indented ```), then the closing fence that ends the receipt.
        m_open = re.search(r"\n[ \t]*```[^\n]*\n", body)
        if m_open is None:
            return body  # no fence found — fall back to remainder (markers guaranteed present)
        after_open = m_open.end()
        m_close = re.search(r"\n[ \t]*```[ \t]*(?:\n|$)", body[after_open:])
        if m_close is None:
            return body  # unterminated fence — fall back to remainder
        return body[: after_open + m_close.end()]

    pass_block = example_block(PASS_MARKER)
    fail_block = example_block(FAIL_MARKER)

    # [A9] WITNESS line byte-identical between the two examples (strip ONE trailing newline).
    def witness_line(block: str) -> str | None:
        m = re.search(r"^[ \t>]*WITNESS .*$", block, re.MULTILINE)
        return m.group(0) if m else None

    w_pass = witness_line(pass_block)
    w_fail = witness_line(fail_block)
    if w_pass is None or w_fail is None:
        errs.append("[A9] red-team-prompt.md: WITNESS line missing in PASS and/or FAIL example block")
    else:
        if w_pass.rstrip("\n") != w_fail.rstrip("\n"):
            errs.append(
                "[A9] red-team-prompt.md: WITNESS lines differ between PASS and FAIL examples "
                "(must be byte-identical):\n"
                f"        PASS: {w_pass!r}\n        FAIL: {w_fail!r}"
            )
        # [A9b] shared WITNESS line carries correct semantic polarity.
        shared = w_pass
        m_pat = re.search(r"pattern=(\S+)", shared)
        pat = m_pat.group(1) if m_pat else ""
        ok_a9b = (
            "fatal=[1-9]" in shared
            and "significant=[1-9]" in shared
            and "expect-fail=match" in shared
        )
        if not ok_a9b:
            errs.append(
                "[A9b] red-team-prompt.md: shared WITNESS line lacks correct polarity — "
                "pattern= must contain both 'fatal=[1-9]' and 'significant=[1-9]' AND the line "
                f"must carry 'expect-fail=match' (got pattern={pat!r})"
            )

    # [A10] PASS example: fatal-count=0 AND significant-count=0 in CLAIMS,
    #       AND a SEVERITY-COUNTS line with fatal=0 significant=0.
    a10_ok = (
        "fatal-count=0" in pass_block
        and "significant-count=0" in pass_block
        and re.search(r"SEVERITY-COUNTS:.*fatal=0", pass_block)
        and re.search(r"SEVERITY-COUNTS:.*significant=0", pass_block)
    )
    if not a10_ok:
        errs.append(
            "[A10] red-team-prompt.md: PASS example must carry CLAIMS 'fatal-count=0' + "
            "'significant-count=0' AND a 'SEVERITY-COUNTS:' line with fatal=0 significant=0"
        )

    # [A11] FAIL example: a non-zero fatal-count= or significant-count=.
    if not re.search(r"(fatal|significant)-count=[1-9]", fail_block):
        errs.append(
            "[A11] red-team-prompt.md: FAIL example must carry a non-zero "
            "'(fatal|significant)-count=[1-9]'"
        )

    # [A12] FAIL example internally consistent: CLAIMS pattern value-pins match the
    #       FAIL block's own SEVERITY-COUNTS line. Field-order/whitespace tolerant.
    sc = re.search(r"SEVERITY-COUNTS:(.*)", fail_block)
    if sc is None:
        errs.append("[A12] red-team-prompt.md: FAIL example missing its own 'SEVERITY-COUNTS:' line")
    else:
        sc_line = sc.group(1)
        m_a = re.search(r"fatal=(\d+)", sc_line)
        m_b = re.search(r"significant=(\d+)", sc_line)
        # pattern=fatal=(\d+) cannot latch onto the witness line because the witness
        # pattern= is immediately followed by '/' (a non-digit) — see M5 note in plan.
        m_c = re.search(r"pattern=fatal=(\d+)", fail_block)
        m_d = re.search(r"pattern=significant=(\d+)", fail_block)
        if not (m_a and m_b and m_c and m_d):
            errs.append(
                "[A12] red-team-prompt.md: FAIL example missing parseable SEVERITY-COUNTS "
                "fatal=/significant= AND CLAIMS pattern=fatal=/pattern=significant= value-pins"
            )
        else:
            a, b, c, d = (m_a.group(1), m_b.group(1), m_c.group(1), m_d.group(1))
            if a != c or b != d:
                errs.append(
                    "[A12] red-team-prompt.md: FAIL example CLAIMS value-pins contradict its own "
                    f"SEVERITY-COUNTS line (counts fatal={a} significant={b}; "
                    f"CLAIMS pattern=fatal={c} pattern=significant={d})"
                )

    # [A13] CLAIMS citations use the convention's two-endpoint range form
    #       (<artifact>#L<a>-L<b>; return-convention.md:94), NOT a bare <artifact>#L<n>.
    #       Bare #L<n> is not an enumerated citation grammar form. Scans every CLAIMS
    #       `from=` in both worked-example blocks: each must carry an L-range, and NONE
    #       may carry a bare #L<n> with no '-L' suffix.
    for label, block in (("PASS", pass_block), ("FAIL", fail_block)):
        from_cites = re.findall(r"from=\S+#L\d+(?:-L\d+)?", block)
        bad = [c for c in from_cites if not re.search(r"#L\d+-L\d+$", c)]
        if not from_cites:
            errs.append(
                f"[A13] red-team-prompt.md: {label} example has no CLAIMS 'from=...#L<a>-L<b>' "
                "citation (expected the SEVERITY-COUNTS line range form)"
            )
        elif bad:
            errs.append(
                f"[A13] red-team-prompt.md: {label} example CLAIMS citation uses the "
                "non-conformant bare '#L<n>' form instead of the convention's '#L<a>-L<b>' "
                f"range form (return-convention.md:94): {bad}"
            )

    return errs


# ---------------------------------------------------------------------------
# C. quality-gate/SKILL.md — consumption + supersession + writer-inversion
# ---------------------------------------------------------------------------

def check_qg(text: str) -> list[str]:
    errs: list[str] = []

    # [C13] score computed from findings-file severity sections, NOT from CLAIMS.
    if not ("### Fatal Challenges" in text and "### Significant Challenges" in text
            and "cross-check" in text):
        errs.append(
            "[C13] quality-gate/SKILL.md: missing score-source wording pinning the weighted "
            "score to counting '### Fatal Challenges' / '### Significant Challenges' sections of "
            "the cited findings file with an explicit CLAIMS 'cross-check' disclaimer"
        )

    # [C15] :30 no longer implies red-team prose is linted-to-BLOCKED. Keyed to the
    #       rule's structural CONTRACT anchor, not its prose — the rewrite's wording
    #       ("findings come from the cited artifact") is now freely editable; only the
    #       anchor is the regression guard (#399; see scripts/CHECKER_CONVENTIONS.md).
    if "CONTRACT:rt-redteam-receipts-lint-clean" not in text:
        errs.append(
            "[C15] quality-gate/SKILL.md: missing CONTRACT anchor "
            "'rt-redteam-receipts-lint-clean' marking the red-team-receipts-lint-clean rule "
            "(the rule's home paragraph was deleted, not merely reworded)"
        )

    # [C16] SP2 clean-PASS TRIPWIRE predicate as a contextual POINTER to the convention.
    c16_ok = (
        "TRIPWIRE: none" in text
        and "SUSPICION=0.00" in text
        and "return-convention.md" in text
    )
    if not c16_ok:
        errs.append(
            "[C16] quality-gate/SKILL.md: missing SP2 pointer — 'TRIPWIRE: none' co-located with "
            "'SUSPICION=0.00' AND a 'return-convention.md' reference (link, not redeclaration)"
        )

    # [C17] SP3 negative invariant: no manifest-sweep re-hashes pinned ARTIFACTS after insertion.
    c17_ok = ("re-hash" in text and "ARTIFACTS" in text and "after insertion" in text)
    if not c17_ok:
        errs.append(
            "[C17] quality-gate/SKILL.md: missing SP3 negative invariant (no manifest-sweep step "
            "'re-hash'es a prior entry's pinned 'ARTIFACTS' 'after insertion')"
        )

    # [C18] fix-agent test-less superseding-witness pattern. Keyed to the rule's
    #       CONTRACT anchor (#399) — the witness prose ('finding-anchor … no longer
    #       appears') is now freely editable; the anchor is the regression guard.
    if "CONTRACT:rt-fix-test-less-witness" not in text:
        errs.append(
            "[C18] quality-gate/SKILL.md: missing CONTRACT anchor 'rt-fix-test-less-witness' "
            "marking the fix-agent test-less superseding-witness rule"
        )

    # [C14]+[C18b] findings-path & writer-inversion rule. ONE anchor guards both the
    #       former [C14] ([FINDINGS_OUTPUT_PATH] is orchestrator-supplied) and [C18b]
    #       (reviewer is the initial writer) — they share a home paragraph (#399).
    if "CONTRACT:rt-findings-writer-inversion" not in text:
        errs.append(
            "[C14][C18b] quality-gate/SKILL.md: missing CONTRACT anchor "
            "'rt-findings-writer-inversion' marking the findings-path/writer-inversion rule "
            "(orchestrator-supplied [FINDINGS_OUTPUT_PATH] + reviewer-as-initial-writer)"
        )

    return errs


# ---------------------------------------------------------------------------
# D. red-team/SKILL.md — standalone consumption (design AC#4)
# ---------------------------------------------------------------------------

# Hard SAFETY CEILING for [D19]/[D19b]'s scope, not the primary boundary —
# see `_paragraph_scope` below (#561 fresh round 7 second-pass finding: a
# fixed-length window is a sliding window over a shrinking paragraph, so
# removing pinned content from the paragraph slides the window into the
# following bullet list, which independently contains '### Second Pass
# Findings' — the checker then passed on a reverted paragraph). Bounded so a
# stray mention of the same headings elsewhere in this 200+-line file cannot
# satisfy either assertion even if a run's paragraph carries no blank line at
# all (#561 round 2 S3: a whole-file `in text` check is decoy-satisfiable).
#
# (#561 fresh round 8 S2): raised above the LIVE measured paragraph lengths
# — step 3's "Single source of truth" paragraph measures 1180 chars, step
# 4's re-review paragraph measures 1133 chars — with headroom, since
# `_paragraph_scope` is now fail-loud (not fail-truncate) when a real
# paragraph exceeds this ceiling: at the old 900-char [D19b] window, the
# live 1133-char paragraph silently narrowed scope and made [D19b]'s
# round-7 fix inoperative — an in-place contradiction inserted past the
# truncation point shipped green.
_D19_WINDOW = 1500
# Raised #561 fresh round 12 S3: step 4's re-review paragraph measures ~2796
# chars live after replacing the vacuous UNLESS-forcing with the
# NOT-SATISFIABLE treatment — headroom kept above the measured length per
# round 8's own M1/S2 lesson about undersized fixed windows (M2's own
# observation that this pattern keeps recurring — see round-11-findings.md
# M2 — is why this window is also now the SOLE window for this paragraph;
# [D21]'s step-4 pins below reuse `d19b_scope` rather than recomputing a
# second, independently-drifting fixed-length window over the same anchor).
_D19B_WINDOW = 3600

# [D22]'s round-ledger paragraph measures 612 chars live — headroom kept
# above the measured length per round 8's own M1/S2 lesson about undersized
# fixed windows (#561 fresh round 10 S1).
_D22_WINDOW = 950


def _paragraph_scope(
    m: "re.Match[str] | None",
    text: str,
    max_window: int,
    errs: list[str] | None = None,
    label: str = "",
) -> str:
    """Bound a regex match's span to the END OF ITS OWN PARAGRAPH — the next
    blank line (`\\n\\n`) — rather than a fixed character count (#561 fresh
    round 7 second-pass finding).

    A heading anchor (e.g. `### 4. Re-review after fixes`) is immediately
    followed by its own heading-to-body blank-line separator, which is NOT
    the paragraph's end — skip exactly one such zero-distance separator
    before treating the next blank line as the real boundary.

    `max_window` is a hard ceiling for the ONE case it was built for — a
    malformed file with no blank line within reach at all (`para_end == -1`),
    where there is no real paragraph boundary to report a violation against
    and truncating is the only available fallback. It is FAIL-LOUD, not a
    silent truncation, for the other case — a real paragraph boundary WAS
    found but the paragraph is longer than `max_window` (#561 fresh round 8
    S2: silently narrowing scope there made [D19b]'s round-7 fix inoperative
    on the live 1133-char artifact against a 900-char window — the last 233
    characters, including the tail of the paragraph's own directional-
    exception sentence, were silently dropped from the scope, and an
    in-place contradiction inserted past the truncation point shipped
    green). In that case the FULL real paragraph is returned (never
    truncated to `max_window`) and, when `errs` is supplied, a violation
    naming the measured length is appended — a canary that fires only if a
    future edit grows the paragraph past the window this round sized for it,
    at which point the window (not the scope) is what needs raising.
    """
    if m is None:
        return ""
    start = m.start()
    search_from = m.end()
    para_end = text.find("\n\n", search_from)
    if para_end == search_from:
        para_end = text.find("\n\n", search_from + 2)
    if para_end == -1:
        para_end = min(start + max_window, len(text))
    elif para_end - start > max_window:
        if errs is not None:
            errs.append(
                f"{label}: paragraph at offset {start} measures "
                f"{para_end - start} chars, exceeding the {max_window}-char "
                "ceiling — raise the window rather than silently narrowing "
                "scope (#561 fresh round 8 S2: a fail-truncate here made "
                "[D19b]'s round-7 fix inoperative on the live artifact)"
            )
    return text[start:para_end]


def check_rt_skill(text: str) -> list[str]:
    errs: list[str] = []

    # [D19] both qualitative branch + weighted-score loop derive from the same single
    #       source: the orchestrator's count of the cited findings file's sections,
    #       widened (#561) to also cover Second Pass Findings. Scoped to the step-3
    #       single-source paragraph itself (anchored on its stable lead-in phrase),
    #       NOT the whole file — a whole-file check is decoy-satisfiable by an
    #       unrelated stray mention of the same three tokens elsewhere (#561 round 2
    #       S3, verified: reverting all three widenings + one stray mention passed
    #       the old check).
    d19_m = re.search(r"Single source of truth", text)
    d19_scope = _paragraph_scope(
        d19_m, text, _D19_WINDOW, errs,
        "[D19] red-team/SKILL.md: the 'Single source of truth' paragraph",
    )
    d19_ok = (bool(d19_m)
              and "cited findings" in d19_scope
              and ("### Fatal Challenges" in d19_scope or "### Significant Challenges" in d19_scope)
              and ("single source" in d19_scope or "same source" in d19_scope
                   or "same single source" in d19_scope)
              and "### Second Pass Findings" in d19_scope)
    if not d19_ok:
        errs.append(
            "[D19] red-team/SKILL.md: the 'Single source of truth' paragraph is missing "
            "wording pinning BOTH the qualitative branch and the weighted-score loop to "
            "the cited findings file's severity sections, widened to include "
            "'### Second Pass Findings' (#561) (e.g. 'cited findings' + section heading "
            "+ 'same/single source' + 'Second Pass Findings', all within the paragraph "
            "itself — a mention elsewhere in the file does not satisfy this)"
        )
    elif _negates("Second Pass Findings", d19_scope):
        errs.append(
            "[D19] red-team/SKILL.md: the 'Single source of truth' paragraph NEGATES "
            "'### Second Pass Findings' (e.g. 'explicitly EXCLUDING' immediately before "
            "it) instead of widening the population to include it (#561 round 1 S1: a "
            "bare co-presence check is satisfied by the negated sentence too)"
        )
    else:
        # (#561 fresh round 6 S4): the widening tokens above are present, but
        # standalone red-team never loads quality-gate/SKILL.md's CONTRACT
        # block by default — this paragraph is a fifth restatement home for
        # the entry/severity parse and must go stale-proof the same way [A6e]
        # protects red-team-prompt.md's bracket.
        d19_pointer_err = _pointer_or_complete(
            d19_scope, "[D19] red-team/SKILL.md: the 'Single source of truth' paragraph"
        )
        if d19_pointer_err:
            errs.append(
                d19_pointer_err + " (#561 fresh round 6 S4: standalone red-team "
                "loads neither red-team-prompt.md's report-format bracket detail "
                "nor quality-gate/SKILL.md's CONTRACT block by default — the "
                "parse must be pointed-to or fully restated here)"
            )

    # [D19b] step 4's standalone re-review score-comparison loop, separately from
    #        [D19]'s step-3 paragraph (#561 round 2 S3 — step 4 had no guard at all).
    d19b_m = re.search(r"### 4\. Re-review after fixes", text)
    d19b_scope = _paragraph_scope(
        d19b_m, text, _D19B_WINDOW, errs,
        "[D19b] red-team/SKILL.md: step 4's re-review score-comparison paragraph",
    )
    d19b_ok = (bool(d19b_m)
               and "cited findings" in d19b_scope
               and ("single source" in d19b_scope or "same source" in d19b_scope
                    or "same single source" in d19b_scope)
               and "### Second Pass Findings" in d19b_scope)
    if not d19b_ok:
        errs.append(
            "[D19b] red-team/SKILL.md: step 4's re-review score-comparison paragraph is "
            "missing wording widening its weighted-score loop to include "
            "'### Second Pass Findings' (#561) — a mention in the step-3 paragraph "
            "([D19]) does not satisfy this; step 4 is a separate live entry point"
        )
    elif _negates("Second Pass Findings", d19b_scope):
        errs.append(
            "[D19b] red-team/SKILL.md: step 4's re-review score-comparison paragraph "
            "NEGATES '### Second Pass Findings' (e.g. 'explicitly EXCLUDING' "
            "immediately before it) instead of widening the population to include it "
            "(#561 round 1 S1: a bare co-presence check is satisfied by the negated "
            "sentence too)"
        )
    else:
        # (#561 fresh round 6 S4): a sixth restatement home, mirroring [D19]'s
        # pointer-or-complete requirement above.
        d19b_pointer_err = _pointer_or_complete(
            d19b_scope, "[D19b] red-team/SKILL.md: step 4's re-review score-comparison paragraph"
        )
        if d19b_pointer_err:
            errs.append(
                d19b_pointer_err + " (#561 fresh round 6 S4: standalone red-team "
                "loads neither red-team-prompt.md's report-format bracket detail "
                "nor quality-gate/SKILL.md's CONTRACT block by default — the "
                "parse must be pointed-to or fully restated here)"
            )

    # [D22] round-ledger 'Total findings' counts consumer (#561 fresh round
    #       10 S1): INV-561-1's twelfth declared consumer (#561 fresh round
    #       9 S4) — the round ledger's `Total findings: N (F: x, S: y, M: z)`
    #       counts derive from the same widened population the Score source
    #       rule defines — had ZERO checker assertion anywhere in this file;
    #       live-verified deleting the entire clause left the suite green.
    d22_m = re.search(r"The ledger is emitted every round", text)
    d22_scope = _paragraph_scope(
        d22_m, text, _D22_WINDOW, errs,
        "[D22] red-team/SKILL.md: the round-ledger 'Total findings' paragraph",
    )
    d22_ok = (bool(d22_m)
              and "Total findings" in d22_scope
              and "cited findings file" in d22_scope
              and ("single source" in d22_scope or "same source" in d22_scope
                   or "same single source" in d22_scope))
    if not d22_ok:
        errs.append(
            "[D22] red-team/SKILL.md: the round-ledger 'Total findings: N "
            "(F: x, S: y, M: z)' paragraph does not state that its counts "
            "derive from the cited findings file's own section count — the "
            "same single source the Score source rule (quality-gate/"
            "SKILL.md's `qg-score-second-pass-population` CONTRACT block, "
            "step 7) defines — INV-561-1's twelfth consumer had no checker "
            "assertion at all (#561 fresh round 10 S1)"
        )
    elif _negates("cited findings file", d22_scope):
        errs.append(
            "[D22] red-team/SKILL.md: the round-ledger 'Total findings' "
            "paragraph NEGATES its population source instead of asserting "
            "it (#561 fresh round 10 S1 polarity guard)"
        )

    # [D20] Tier-1 structural lint applied AND NOT the Layer-2 sweep.
    d20_ok = (("Tier-1" in text or "Tier 1" in text)
              and ("Layer-2 sweep" in text or "Layer 2 sweep" in text))
    if not d20_ok:
        errs.append(
            "[D20] red-team/SKILL.md: missing standalone Tier-1-lint pin AND a 'Layer-2 sweep' "
            "(QG-only / 'no Layer-2 sweep') exclusion pin"
        )

    # [D21] S4 standalone directional exception (#561 fresh round 7 S4): the
    # 'No Fatal/Significant issues' approve branch at step 3 adopted the
    # widened second-pass population but not the directional SEVERITY-COUNTS
    # discrepancy exception that makes the widened, strict parse safe to rely
    # on — a well-intentioned but malformed second-pass Fatal (eval #15's
    # exact fixture shape) produces ESCALATED in quality-gate but a false
    # "Artifact is approved" in standalone without this exception.
    directional_m = re.search(r"\*\*No Fatal/Significant issues\*\*.{0,900}", text, re.DOTALL)
    if not (
        directional_m
        and "EXCEEDS the orchestrator's own counted population" in directional_m.group(0)
        and "NOT approved" in directional_m.group(0)
    ):
        errs.append(
            "[D21] red-team/SKILL.md: the 'No Fatal/Significant issues' approve "
            "branch does not carry the directional SEVERITY-COUNTS discrepancy "
            "exception — a declared fatal+significant total EXCEEDING the "
            "orchestrator's own counted population must make the artifact NOT "
            "approved, even at a 0/0 own count (#561 fresh round 7 S4)"
        )
    elif _negates("EXCEEDS the orchestrator's own counted population", directional_m.group(0)):
        errs.append(
            "[D21] red-team/SKILL.md: the directional SEVERITY-COUNTS "
            "discrepancy exception NEGATES 'EXCEEDS the orchestrator's own "
            "counted population' instead of asserting it (#561 round 1 S1 "
            "polarity guard)"
        )

    # [D21] continued — Empty-work-order carve-out (#561 fresh round 9 S3):
    # the directional exception above routed a 0/0 own-count discrepancy
    # straight into the fix mechanism, contradicting quality-gate's own
    # Empty-work-order exception for the IDENTICAL condition (#561 round 4
    # SP1: dispatching a fix agent against an empty work order is
    # reachable only via a wrongly-attributed no-op-fix/Stagnation
    # escalation).
    empty_wo_rt_m = re.search(r"Empty-work-order carve-out.{0,600}", text, re.DOTALL)
    if not (
        empty_wo_rt_m
        and "0 Fatal and 0 Significant" in empty_wo_rt_m.group(0)
        and "does NOT route to the fix mechanism" in empty_wo_rt_m.group(0)
        and "escalate to the user" in empty_wo_rt_m.group(0)
    ):
        errs.append(
            "[D21] red-team/SKILL.md: the directional exception's approve-"
            "void branch is missing the Empty-work-order carve-out — on a "
            "0/0 own-count discrepancy, standalone red-team must escalate "
            "to the user (declared + counted numbers) rather than "
            "dispatching a fix, mirroring quality-gate's own Empty-work-"
            "order exception for the identical condition (#561 fresh round "
            "9 S3)"
        )
    elif _negates("does NOT route to the fix mechanism", empty_wo_rt_m.group(0)):
        errs.append(
            "[D21] red-team/SKILL.md: the Empty-work-order carve-out "
            "NEGATES 'does NOT route to the fix mechanism' instead of "
            "asserting it (#561 fresh round 9 S3 polarity guard)"
        )

    # [D21] continued — step-4 by-reference pointer (#561 fresh round 7 S4):
    # step 4's re-review comparison must point back at step 3's directional
    # exception so its own own-count comparison is not spoofable the same way.
    # Reuses `d19b_scope` (#561 fresh round 12 S3) rather than recomputing an
    # independent fixed-length window over the same `### 4. Re-review after
    # fixes` anchor — round 11's own M2 flagged three separate fixed windows
    # guarding this clause as a recurring drift risk; this pin and [D19b]'s
    # now share the one paragraph-bounded scope instead of adding a fourth.
    step4_scope = d19b_scope
    if "Directional exception" not in step4_scope:
        errs.append(
            "[D21] red-team/SKILL.md: step 4's re-review comparison does not "
            "reference the step-3 directional SEVERITY-COUNTS discrepancy "
            "exception by name (#561 fresh round 7 S4)"
        )

    # [D21] continued — step-4 empty-work-order carve-out (#561 fresh round
    # 10 S2): step 4 had NO carve-out for a 0/0 own-count discrepancy, unlike
    # step 3 — reachable via round N's real findings (own count non-zero) →
    # fix → round N+1's malformed second-pass Fatal (own count 0/0, declared
    # total 1) → processed through step 4, not step 3 → the exact wrongly-
    # attributed Stagnation escalation step 3's own carve-out exists to
    # prevent. Scoped to `step4_scope` specifically (NOT a bare global
    # `re.search` on the shared "Empty-work-order carve-out" phrase) — step
    # 3 already has its own occurrence of that phrase, and a global first-
    # match search would resolve to step 3's content regardless of what step
    # 4 says, exactly the anchor-collision shape this round's Part 2 exists
    # to catch. Step 4's carve-out therefore uses its own distinguishing
    # label, "Step-4 empty-work-order carve-out", pinned only within
    # `step4_scope`.
    if not (
        "Step-4 empty-work-order carve-out" in step4_scope
        and "0 Fatal and 0 Significant" in step4_scope
        and "skips the not-satisfiable loop and escalates to the user directly" in step4_scope
    ):
        errs.append(
            "[D21] red-team/SKILL.md: step 4 is missing its own Empty-work-"
            "order carve-out — on a 0/0 own-count discrepancy, step 4 must "
            "escalate to the user directly rather than looping as "
            "not-satisfiable, mirroring step 3's own carve-out for the "
            "identical condition (#561 fresh round 10 S2; reworded #561 "
            "fresh round 12 S3 alongside the NOT-SATISFIABLE replacement)"
        )
    elif _negates("skips the not-satisfiable loop and escalates to the user directly", step4_scope):
        errs.append(
            "[D21] red-team/SKILL.md: step 4's empty-work-order carve-out "
            "NEGATES 'skips the not-satisfiable loop and escalates to the "
            "user directly' instead of asserting it (#561 fresh round 10 S2 "
            "polarity guard)"
        )

    # [D21] continued — step-4 NOT-SATISFIABLE replacement (#561 fresh round
    # 12 S3): round 10 S2's UNLESS-carve-out pin above was itself vacuous —
    # round 11 S3 proved the UNLESS clause is the exact logical complement
    # of the Progress/Stagnation branch split (own-count-lower+discrepancy
    # -> UNLESS fires -> Progress; own-count-same-or-higher+discrepancy ->
    # forced non-progress -> Stagnation — identical to the unaided branches),
    # so it could never change an outcome, and this checker was pinning
    # prose with no behaviour. Replaced with step 4's own not-satisfiable
    # treatment, mirroring quality-gate's Comparability gate: on a
    # discrepancy, draw NEITHER a progress NOR a regression conclusion —
    # loop back to step 3 instead of forcing either branch.
    if not (
        "NOT-SATISFIABLE" in step4_scope
        and "draw neither a progress nor a regression conclusion" in step4_scope
        and "loop back to step 3, per the not-satisfiable treatment above" in step4_scope
    ):
        errs.append(
            "[D21] red-team/SKILL.md: step 4's directional exception does "
            "not replace the vacuous UNLESS-forcing with its own "
            "NOT-SATISFIABLE treatment ('draw neither a progress nor a "
            "regression conclusion' / 'loop back to step 3, per the "
            "not-satisfiable treatment above') — #561 round 11 S3 proved "
            "the prior UNLESS clause is the exact logical complement of the "
            "branch split below and can never change an outcome; this "
            "checker must not keep pinning that vacuous prose (#561 fresh "
            "round 12 S3)"
        )
    elif _negates("draw neither a progress nor a regression conclusion", step4_scope):
        errs.append(
            "[D21] red-team/SKILL.md: step 4's NOT-SATISFIABLE treatment "
            "NEGATES 'draw neither a progress nor a regression conclusion' "
            "instead of asserting it (#561 round 1 S1 polarity guard)"
        )
    if "Discrepancy is not-satisfiable" not in step4_scope:
        errs.append(
            "[D21] red-team/SKILL.md: step 4's own branch enumeration does "
            "not include the not-satisfiable discrepancy case as its own "
            "listed outcome, distinct from Progress and Stagnation (#561 "
            "fresh round 12 S3)"
        )

    return errs


# ---------------------------------------------------------------------------
# E. return-convention.md — kind=grep clarification (design AC#4c)
# ---------------------------------------------------------------------------

def check_return_conv(text: str) -> list[str]:
    errs: list[str] = []

    # [E21] one statement: for kind=grep the cited artifact/range are the payload's own
    #       #<range>; out= resolution is kind=exec-only; scope references Tier-1 + Tier-2.
    # Pin on NEW phrases ('payload's own' + an out=…exec-only clause) — 'kind=grep',
    # 'Tier-1', 'Tier-2', 'out=' all pre-exist and cannot discriminate alone.
    has_payload_range = "payload's own" in text
    has_out_exec_only = bool(re.search(r"out=[^\n]{0,60}?\bexec[`)]?-only", text))
    has_scope = ("Tier-1" in text and "Tier-2" in text)
    if not (has_payload_range and has_out_exec_only and has_scope):
        missing = []
        if not has_payload_range:
            missing.append("\"payload's own\" range wording")
        if not has_out_exec_only:
            missing.append("an 'out=' resolution is 'exec-only' clause")
        if not has_scope:
            missing.append("Tier-1 + Tier-2 scope reference")
        errs.append(
            "[E21] return-convention.md: missing the kind=grep artifact/range clarification — "
            + "; ".join(missing)
        )

    return errs


# ---------------------------------------------------------------------------
# Selftest — negative controls for [D19]/[D19b]/[A6]/[A6b] (#561 round 2 S3, S4).
#
# S3 demonstrated live that the OLD [D19] (a whole-file `in text` check) passed
# on a fixture with all three red-team/SKILL.md widenings reverted PLUS one
# unrelated stray mention of "### Second Pass Findings" elsewhere in the file.
# S4 demonstrated live that deleting red-team-prompt.md's `### Second Pass
# Findings` section and downgrading "## Second Pass (REQUIRED)" to "(optional)"
# passed the full suite, because [A6]'s section tuple omitted that heading and
# nothing pinned the REQUIRED-ness. These fixtures reproduce both shapes.
# ---------------------------------------------------------------------------

# Pointer sentence for [D19]/[D19b]'s #561 fresh round 6 S4 fix — identical
# text appended to both the step-3 and step-4 paragraphs, mirroring the real
# red-team/SKILL.md edit.
_D19_POINTER = (
    " See `skills/quality-gate/SKILL.md`'s `qg-score-second-pass-population` "
    "CONTRACT block (Score source, step 7) for the parse."
)

# Filler between step 3 and step 4 large enough that [D19]'s widened window
# (1300 chars, sized for the real file's longer pointer sentence) ends inside
# it rather than reaching step 4's own content — preserving [D19]/[D19b]
# isolation in this much-shorter synthetic fixture.
_D19_FILLER = (
    "Unrelated filler text separating step 3 from step 4 in this minimal "
    "fixture, padding distance for window isolation. "
) * 6

_D21_STEP3_DIRECTIONAL = (
    " Directional exception: this approval is void when the declared "
    "SEVERITY-COUNTS total EXCEEDS the orchestrator's own counted population "
    "— the artifact is NOT approved."
)
_D21_EMPTY_WO_CARVEOUT = (
    " Empty-work-order carve-out: when the orchestrator's own counted "
    "population is 0 Fatal and 0 Significant, this discrepancy does NOT "
    "route to the fix mechanism — escalate to the user instead."
)
_D21_STEP4_POINTER = (
    " Directional exception, NOT-SATISFIABLE treatment (see step 3) "
    "applies here too — the comparison is NOT-SATISFIABLE: draw neither a "
    "progress nor a regression conclusion from it. Discrepancy is "
    "not-satisfiable: loop back to step 3, per the not-satisfiable "
    "treatment above. Step-4 empty-work-order carve-out: when the "
    "orchestrator's own counted population is 0 Fatal and 0 Significant, "
    "this discrepancy skips the not-satisfiable loop and escalates to the "
    "user directly."
)

# [D22]'s round-ledger paragraph (#561 fresh round 10 S1) — a sixth
# restatement home, structurally identical to [D19]/[D19b]'s.
_D22_LEDGER_PARAGRAPH = (
    "The ledger is emitted every round. The ledger format is unchanged; its "
    "`Total findings: N (F: x, S: y, M: z)` counts now derive from the "
    "orchestrator's own section count of the cited findings file — the same "
    "single source as the score, with the receipt's SEVERITY-COUNTS line as "
    "a declared cross-check.\n"
)

_D19_GOOD_RT_SKILL = (
    "\n### 3. Process findings\n\n"
    "Single source of truth (#366, widened #561). The reviewer WROTEs its rich findings to the cited findings file and returns a receipt citing it. Both the qualitative branches below and the weighted-score loop (step 4) derive from the orchestrator's own count of the cited findings file's `### Fatal Challenges` / `### Significant Challenges` sections, plus any Fatal/Significant-severity entries under `### Second Pass Findings` — the same single source, so the qualitative verdict and the score cannot diverge."
    + _D19_POINTER
    + "\n\n- **No Fatal/Significant issues**: Artifact is approved."
    + _D21_STEP3_DIRECTIONAL
    + _D21_EMPTY_WO_CARVEOUT
    + "\n\n"
    + _D19_FILLER
    + "\n\n### 4. Re-review after fixes\n\n"
    "Dispatch a NEW Devil's Advocate subagent. Compute the weighted score from the same single source — the orchestrator's count of the new round's cited findings file's `### Fatal Challenges` / `### Significant Challenges` sections, plus any Fatal/Significant-severity entries under `### Second Pass Findings` — and compare."
    + _D19_POINTER
    + _D21_STEP4_POINTER
    # (#561 fresh round 8 SP1): a real blank line closing step 4's own
    # paragraph, so `_paragraph_scope` takes the paragraph-bounded path here
    # (not the `text.find` == -1 ceiling fallback) — exercising the actual
    # boundary this fixture is meant to test.
    + "\n\n"
    "Trailing paragraph marking the end of step 4's own paragraph.\n"
    + "\n\n"
    + _D22_LEDGER_PARAGRAPH
    + "\n\n"
    "Trailing paragraph marking the end of the round-ledger paragraph.\n"
)


def _selftest_d19() -> list[str]:
    errs: list[str] = []
    # Filtered to [D19]/[D19b]/[D21]/[D22] — this minimal fixture doesn't
    # carry [D20]'s unrelated Tier-1/Layer-2-sweep tokens, which is not what
    # this fixture tests.
    good = [e for e in check_rt_skill(_D19_GOOD_RT_SKILL) if e.startswith(("[D19]", "[D19b]", "[D21]", "[D22]"))]
    if good:
        errs.append(f"selftest: GOOD [D19]/[D19b]/[D21]/[D22] fixture unexpectedly reported errors: {good}")

    _STEP3_WIDENING = ", plus any Fatal/Significant-severity entries under `### Second Pass Findings` — the same single source"
    _STEP4_WIDENING = ", plus any Fatal/Significant-severity entries under `### Second Pass Findings` — and compare."
    assert _D19_GOOD_RT_SKILL.count(_STEP3_WIDENING) == 1
    assert _D19_GOOD_RT_SKILL.count(_STEP4_WIDENING) == 1

    # Revert both widenings (mirrors S3's live exploit — reverting the analogous
    # sentences in the real file) and add one unrelated stray mention of the
    # heading far from either scored paragraph.
    reverted = _D19_GOOD_RT_SKILL.replace(_STEP3_WIDENING, "").replace(_STEP4_WIDENING, "")
    if "### Second Pass Findings" in reverted:
        errs.append("selftest: [D19]/[D19b] revert fixture setup failed to strip both widenings")
    _FILLER = "Unrelated filler paragraph padding out the distance to the stray mention below.\n" * 20
    reverted_plus_stray = reverted + (
        "\n\n" + _FILLER + "\n"
        "## What the Devil's Advocate is NOT\n"
        "- Not a checker for an unrelated `### Second Pass Findings` heading "
        "mentioned only in passing here.\n"
    )
    stray_errs = check_rt_skill(reverted_plus_stray)
    if not any(e.startswith("[D19]") for e in stray_errs):
        errs.append(f"selftest: revert-plus-stray-mention fixture did NOT trip [D19] (errs: {stray_errs})")
    if not any(e.startswith("[D19b]") for e in stray_errs):
        errs.append(f"selftest: revert-plus-stray-mention fixture did NOT trip [D19b] (errs: {stray_errs})")

    # [D19b] isolation: step-3 paragraph widened normally, step-4 paragraph
    # reverted alone — must trip [D19b] specifically, not [D19].
    d19b_only_broken = _D19_GOOD_RT_SKILL.replace(_STEP4_WIDENING, "")
    d19b_errs = check_rt_skill(d19b_only_broken)
    if not any(e.startswith("[D19b]") for e in d19b_errs):
        errs.append("selftest: step-4-only revert did NOT trip [D19b]")
    if any(e.startswith("[D19]") for e in d19b_errs):
        errs.append("selftest: step-4-only revert incorrectly also tripped [D19] (over-scoped window)")

    # Polarity guard negative controls (#561 round 1 S1): mutate by REPLACING
    # each widening clause's pin with its negated form, not by deleting it —
    # demonstrated live: negating "check_rt_receipt_contract.check_rt_skill on
    # red-team/SKILL.md" passed both baseline and negated with zero errors
    # before this fix, because a bare 'Second Pass Findings' co-presence check
    # is satisfied by the negated sentence too.
    step3_negated = _D19_GOOD_RT_SKILL.replace(
        ", plus any Fatal/Significant-severity entries under `### Second Pass Findings` — the same single source",
        ", and explicitly EXCLUDING all entries under `### Second Pass Findings` — the same single source",
    )
    assert step3_negated != _D19_GOOD_RT_SKILL, "selftest setup: step-3 negation needle not found"
    step3_negated_errs = check_rt_skill(step3_negated)
    if not any(e.startswith("[D19]") for e in step3_negated_errs):
        errs.append("selftest: negating the step-3 widening clause in place did NOT trip [D19] (polarity-blind)")

    step4_negated = _D19_GOOD_RT_SKILL.replace(
        ", plus any Fatal/Significant-severity entries under `### Second Pass Findings` — and compare.",
        ", and explicitly EXCLUDING all entries under `### Second Pass Findings` — and compare.",
    )
    assert step4_negated != _D19_GOOD_RT_SKILL, "selftest setup: step-4 negation needle not found"
    step4_negated_errs = check_rt_skill(step4_negated)
    if not any(e.startswith("[D19b]") for e in step4_negated_errs):
        errs.append("selftest: negating the step-4 widening clause in place did NOT trip [D19b] (polarity-blind)")

    # [D19]/[D19b] pointer-or-complete extension (#561 fresh round 6 S4):
    # removing ONLY the pointer sentence (leaving the widened token/section
    # mentions intact) must trip the same `_pointer_or_complete` predicate
    # [A6e] runs — this is the new coverage S4 adds; these two sites carried
    # neither the parse detail nor a CONTRACT-block pointer before this fix.
    d19_pointer_removed = _D19_GOOD_RT_SKILL.replace(_D19_POINTER, "", 1)
    assert d19_pointer_removed != _D19_GOOD_RT_SKILL, "selftest setup: D19 pointer-removal needle not found"
    d19_pointer_errs = check_rt_skill(d19_pointer_removed)
    if not any(e.startswith("[D19]") for e in d19_pointer_errs):
        errs.append(
            "selftest: removing step 3's CONTRACT-block pointer sentence "
            "(leaving the widened tokens intact) did NOT trip [D19] (#561 "
            "fresh round 6 S4)"
        )

    # Remove the SECOND (step-4) pointer occurrence only, leaving step-3's intact.
    _first, _sep, _rest = _D19_GOOD_RT_SKILL.partition(_D19_POINTER)
    d19b_pointer_removed = _first + _sep + _rest.replace(_D19_POINTER, "")
    assert d19b_pointer_removed != _D19_GOOD_RT_SKILL, "selftest setup: D19b pointer-removal needle not found"
    d19b_pointer_errs = check_rt_skill(d19b_pointer_removed)
    if not any(e.startswith("[D19b]") for e in d19b_pointer_errs):
        errs.append(
            "selftest: removing step 4's CONTRACT-block pointer sentence "
            "(leaving step 3's pointer and the widened tokens intact) did "
            "NOT trip [D19b] (#561 fresh round 6 S4)"
        )
    if any(e.startswith("[D19]") for e in d19b_pointer_errs):
        errs.append(
            "selftest: removing ONLY step 4's pointer incorrectly also "
            "tripped [D19] (over-scoped window)"
        )

    # [D21] S4 directional exception negative controls (#561 fresh round 7
    # S4): deleting the step-3 directional exception, and negating it in
    # place, must each trip [D21]; deleting the step-4 by-reference pointer
    # must also trip it.
    d21_step3_deleted = _D19_GOOD_RT_SKILL.replace(_D21_STEP3_DIRECTIONAL, "")
    assert d21_step3_deleted != _D19_GOOD_RT_SKILL, "selftest setup: D21 step-3 deletion needle not found"
    d21_step3_deleted_errs = check_rt_skill(d21_step3_deleted)
    if not any(e.startswith("[D21]") for e in d21_step3_deleted_errs):
        errs.append("selftest: deleting the step-3 directional exception did NOT trip [D21]")

    d21_step3_negated = _D19_GOOD_RT_SKILL.replace(
        "EXCEEDS the orchestrator's own counted population",
        "does NOT EXCEED the orchestrator's own counted population",
    )
    assert d21_step3_negated != _D19_GOOD_RT_SKILL, "selftest setup: D21 step-3 negation needle not found"
    d21_step3_negated_errs = check_rt_skill(d21_step3_negated)
    if not any(e.startswith("[D21]") for e in d21_step3_negated_errs):
        errs.append("selftest: negating the step-3 directional exception in place did NOT trip [D21] (polarity-blind)")

    d21_step4_deleted = _D19_GOOD_RT_SKILL.replace(_D21_STEP4_POINTER, "")
    assert d21_step4_deleted != _D19_GOOD_RT_SKILL, "selftest setup: D21 step-4 pointer-deletion needle not found"
    d21_step4_deleted_errs = check_rt_skill(d21_step4_deleted)
    if not any(e.startswith("[D21]") for e in d21_step4_deleted_errs):
        errs.append("selftest: removing step 4's by-reference pointer to the directional exception did NOT trip [D21]")

    # [D19] sliding-window negative control (#561 fresh round 7 second-pass
    # finding): reproduces the reviewer's live-verified exploit against the
    # OLD fixed-length-window shape — a paragraph whose own end precedes a
    # bullet list that INDEPENDENTLY mentions '### Second Pass Findings'
    # (mirroring the real file: the step-3 paragraph precedes the
    # '**No Fatal/Significant issues**' bullet, which names the heading in
    # its own qualifier). Reverting ONLY the paragraph's widening — leaving
    # the bullet's mention intact — must still trip [D19]: a fixed
    # '.{0,N}' window would have slid past the shrunk paragraph into the
    # bullet and been satisfied by its independent mention; the
    # paragraph-bounded `_paragraph_scope` must not be.
    _slide_widening = ", plus any Fatal/Significant-severity entries under `### Second Pass Findings` — the same single source"
    _slide_fixture = (
        "\n### 3. Process findings\n\n"
        "Single source of truth (#366, widened #561). Both the qualitative branches below and the weighted-score loop (step 4) derive from the orchestrator's own count of the cited findings file's `### Fatal Challenges` / `### Significant Challenges` sections"
        + _slide_widening
        + "."
        + _D19_POINTER
        + "\n\n"
        + "- **No Fatal/Significant issues** (cited findings file has zero `### Fatal Challenges` / `### Significant Challenges` entries, and zero Fatal/Significant-severity entries under `### Second Pass Findings`): Artifact is approved.\n"
    )
    assert _slide_widening in _slide_fixture, "selftest setup: sliding-window needle not found"
    _slide_reverted = _slide_fixture.replace(_slide_widening, "")
    assert "### Second Pass Findings" in _slide_reverted, (
        "selftest setup: sliding-window fixture's bullet must still mention "
        "the heading after the paragraph's own widening is reverted"
    )
    _slide_errs = check_rt_skill(_slide_reverted)
    if not any(e.startswith("[D19]") for e in _slide_errs):
        errs.append(
            "selftest: reverting the step-3 paragraph's widening while "
            "leaving the following bullet's independent '### Second Pass "
            "Findings' mention intact did NOT trip [D19] (#561 fresh round 7 "
            "second-pass finding: fixed-length-window sliding-window defect)"
        )

    # [D22] negative controls (#561 fresh round 10 S1): deleting the
    # round-ledger paragraph entirely, and negating its population-source
    # clause in place, must each trip [D22].
    d22_deleted = _D19_GOOD_RT_SKILL.replace(_D22_LEDGER_PARAGRAPH, "")
    assert d22_deleted != _D19_GOOD_RT_SKILL, "selftest setup: D22 deletion needle not found"
    d22_deleted_errs = [e for e in check_rt_skill(d22_deleted) if e.startswith("[D22]")]
    if not d22_deleted_errs:
        errs.append("selftest: deleting the round-ledger 'Total findings' paragraph did NOT trip [D22] (#561 fresh round 10 S1)")

    d22_negated = _D19_GOOD_RT_SKILL.replace(
        "orchestrator's own section count of the cited findings file",
        "orchestrator's own section count of NOT the cited findings file",
    )
    assert d22_negated != _D19_GOOD_RT_SKILL, "selftest setup: D22 negation needle not found"
    d22_negated_errs = [e for e in check_rt_skill(d22_negated) if e.startswith("[D22]")]
    if not d22_negated_errs:
        errs.append("selftest: negating the round-ledger paragraph's population source in place did NOT trip [D22] (#561 fresh round 10 S1 polarity guard)")

    # [D21] step-4 empty-work-order carve-out negative controls (#561 fresh
    # round 10 S2): deleting step 4's own carve-out — while step 3's
    # differently-labelled carve-out stays intact — must trip [D21]. This
    # is also the anchor-collision regression control: if the checker's
    # pin were a bare global `re.search` on the SHARED "Empty-work-order
    # carve-out" phrase instead of `step4_scope`-scoped, this deletion
    # (which never touches step 3's own occurrence) would pass undetected.
    step4_carveout_deleted = _D19_GOOD_RT_SKILL.replace(
        " Step-4 empty-work-order carve-out: when the orchestrator's own "
        "counted population is 0 Fatal and 0 Significant, this discrepancy "
        "skips the not-satisfiable loop and escalates to the user directly.",
        "",
    )
    assert step4_carveout_deleted != _D19_GOOD_RT_SKILL, "selftest setup: step-4 carve-out deletion needle not found"
    assert "Empty-work-order carve-out" in step4_carveout_deleted, (
        "selftest setup: step-4 carve-out deletion must leave step 3's own "
        "differently-labelled carve-out intact"
    )
    step4_carveout_deleted_errs = [e for e in check_rt_skill(step4_carveout_deleted) if e.startswith("[D21]")]
    if not step4_carveout_deleted_errs:
        errs.append(
            "selftest: deleting step 4's own empty-work-order carve-out "
            "(leaving step 3's differently-labelled carve-out intact) did "
            "NOT trip [D21] (#561 fresh round 10 S2)"
        )

    # (#561 fresh round 12 S3): the reworded carve-out's own assertion is
    # phrased positively ("skips ... and escalates ... directly"), so a
    # polarity-guard test needs a negation token inserted immediately before
    # the still-intact substring, not a swapped NOT/DOES pair as the old
    # "does NOT force" phrasing used.
    step4_carveout_negated = _D19_GOOD_RT_SKILL.replace(
        "this discrepancy skips the not-satisfiable loop",
        "this discrepancy never skips the not-satisfiable loop",
    )
    assert step4_carveout_negated != _D19_GOOD_RT_SKILL, "selftest setup: step-4 carve-out negation needle not found"
    step4_carveout_negated_errs = [e for e in check_rt_skill(step4_carveout_negated) if e.startswith("[D21]")]
    if not step4_carveout_negated_errs:
        errs.append(
            "selftest: inserting 'never' before step 4's carve-out "
            "consequence did NOT trip [D21] (#561 fresh round 10 S2 "
            "polarity guard)"
        )

    # [D21] step-4 NOT-SATISFIABLE treatment negative controls (#561 fresh
    # round 12 S3, replacing the round-10-S2 UNLESS-clause controls above —
    # that clause no longer exists in either the real file or this fixture):
    # deleting the NOT-SATISFIABLE sentence, negating its "draw neither..."
    # assertion in place, and deleting the branch-enumeration bullet must
    # each trip [D21].
    step4_notsat_deleted = _D19_GOOD_RT_SKILL.replace(
        " Directional exception, NOT-SATISFIABLE treatment (see step 3) "
        "applies here too — the comparison is NOT-SATISFIABLE: draw "
        "neither a progress nor a regression conclusion from it.",
        "",
    )
    assert step4_notsat_deleted != _D19_GOOD_RT_SKILL, "selftest setup: step-4 NOT-SATISFIABLE deletion needle not found"
    step4_notsat_deleted_errs = [e for e in check_rt_skill(step4_notsat_deleted) if e.startswith("[D21]")]
    if not step4_notsat_deleted_errs:
        errs.append(
            "selftest: deleting step 4's NOT-SATISFIABLE treatment sentence "
            "did NOT trip [D21] (#561 fresh round 12 S3)"
        )

    # Negation token ("never") inserted immediately before the still-intact
    # "draw neither a progress..." anchor — also exercises that the
    # hyphen-exclusion added to `_negates` for "NOT-SATISFIABLE" does NOT
    # swallow a genuine, non-hyphenated negation nearby (#561 fresh round 12
    # S3: the GOOD fixture's own "NOT-SATISFIABLE:" immediately precedes
    # this anchor and must NOT itself trip this guard — see the "good
    # fixture is clean" assertion above; this control proves a real "never"
    # still does).
    step4_notsat_negated = _D19_GOOD_RT_SKILL.replace(
        "NOT-SATISFIABLE: draw neither a progress",
        "NOT-SATISFIABLE: never draw neither a progress",
    )
    assert step4_notsat_negated != _D19_GOOD_RT_SKILL, "selftest setup: step-4 NOT-SATISFIABLE negation needle not found"
    step4_notsat_negated_errs = [e for e in check_rt_skill(step4_notsat_negated) if e.startswith("[D21]")]
    if not step4_notsat_negated_errs:
        errs.append(
            "selftest: inserting 'never' before step 4's 'draw neither a "
            "progress nor a regression conclusion' assertion did NOT trip "
            "[D21] (#561 fresh round 12 S3 polarity guard / hyphen-exclusion "
            "regression control)"
        )

    step4_branch_deleted = _D19_GOOD_RT_SKILL.replace(
        " Discrepancy is not-satisfiable: loop back to step 3, per the "
        "not-satisfiable treatment above.",
        "",
    )
    assert step4_branch_deleted != _D19_GOOD_RT_SKILL, "selftest setup: step-4 branch-enumeration deletion needle not found"
    step4_branch_deleted_errs = [e for e in check_rt_skill(step4_branch_deleted) if e.startswith("[D21]")]
    if not step4_branch_deleted_errs:
        errs.append(
            "selftest: deleting step 4's 'Discrepancy is not-satisfiable' "
            "branch-enumeration bullet did NOT trip [D21] (#561 fresh round "
            "12 S3)"
        )

    return errs


_A6_SP_BRACKET = (
    "### Second Pass Findings\n"
    "    [Section location: the orchestrator locates each of the FOUR sections this parse reads — `### Fatal Challenges`, `### Significant Challenges`, this section, and `### Minor Observations` — by the first unfenced, unquoted heading — this is the earliest occurrence of such a heading line in the file; a later matching heading line never overrides an earlier one as the section's start; a section's end is the next such heading — when none follows, the section extends to the end of the cited file. If that section's matching-heading count is zero, the fallback triggers on this OBSERVABLE condition itself, not on a diagnosis of why it is zero (a stray fence drives that section's matching-heading count to zero is one cause; the section's only matching heading sitting inside an otherwise-BALANCED, CLOSED fence, with no stray fence anywhere in the file, is another), the fence exclusion stops applying at the heading level too, for both the start and end of that section — raw-heading location end-to-end. If no heading matches even under that fallback, the orchestrator flags `missing-second-pass-section` in the narration log rather than reading the section as empty. If more than one such heading matches, the orchestrator flags `malformed-second-pass-sectioning` and counts the union of all matching sections' entries — de-duplicated by entry identity where the union itself produces a duplicate — rather than just one of them. This location step reads the bytes of your findings file itself — quoting your own file's content inside another document (e.g. an eval prompt) does not change what counts as \"the file\". A block of text here is a scored **entry** if it carries a line whose first non-whitespace characters are `**Finding:**` and/or a line whose first non-whitespace characters are `**Severity:**` — either marker alone is sufficient; the heading itself is never what makes text scored or not. An entry begins at the first line-initial `**Finding:**` or `**Severity:**` marker and extends to the line before the next `####` heading or the next line-initial `**Finding:**` marker that is not itself inside a fenced code block or prefixed by a blockquote marker (`> `), whichever comes first. Before testing either marker, strip an optional leading list marker (`-`, `*`, `+`, or `<digits>.` followed by whitespace); a bulleted line such as `- **Severity:** Fatal` still opens (or carries) an entry. A mid-sentence or quoted occurrence of either marker string does NOT make surrounding text an entry. A line inside a fenced code block or a line beginning with a blockquote marker is never an entry-opening line. If this section contains an ODD number of triple-backtick delimiters, the fenced-code-block exclusion does NOT apply for the rest of the section. Every entry MUST declare, on its `**Severity:**` line, a value that begins with `Fatal` / `Significant` / `Minor`, with the token immediately followed by end-of-line, or by one of `(`, `[`, `,`, `.`, `:`, `;`; strip any leading AND trailing markdown emphasis markers or code-span backticks from the value first — the entry is scored at that recognised severity. A value matching none of the three is scored as Significant by default and flagged as malformed.]\n"
)

_A6_SC_PARAGRAPH = (
    "    SEVERITY-COUNTS: fatal=<F> significant=<S> minor=<M>\n"
    "    ```\n\n"
    "    where `<F>`/`<S>` include Fatal/Significant entries you place under `### Second Pass Findings` — the same population the orchestrator counts.\n"
)

_A6_GOOD_RT_PROMPT = f"""
### Fatal Challenges
### Significant Challenges
### Minor Observations
### Dimension Coverage
{_A6_SP_BRACKET}## Second Pass (REQUIRED)

Second-pass findings are scored at the same weight as first-pass findings. Apply the same inflation check here as anywhere else — the ≥3 target is a search-effort floor, not a filing quota.

{_A6_SC_PARAGRAPH}
"""


def _selftest_a6() -> list[str]:
    errs: list[str] = []
    good = check_rt_prompt(_A6_GOOD_RT_PROMPT)
    a6_good_errs = [e for e in good if e.startswith("[A6")]
    if a6_good_errs:
        errs.append(f"selftest: GOOD [A6]/[A6b]/[A6c]/[A6d] fixture unexpectedly reported errors: {a6_good_errs}")

    # S4's live exploit: delete the Second Pass Findings section AND downgrade
    # REQUIRED to optional. The SEVERITY-COUNTS paragraph also cross-references
    # '### Second Pass Findings' by name (needed for [A6d]'s literal-phrase
    # pin), so [A6]'s bare substring retain-guard is satisfied by that
    # cross-reference alone unless it too is scrubbed here.
    deleted = _A6_GOOD_RT_PROMPT.replace(_A6_SP_BRACKET, "")
    deleted = deleted.replace("## Second Pass (REQUIRED)", "## Second Pass (optional)")
    deleted = deleted.replace("### Second Pass Findings", "")
    deleted_errs = [e for e in check_rt_prompt(deleted) if e.startswith("[A6")]
    if not any(e.startswith("[A6]") for e in deleted_errs):
        errs.append("selftest: deleting '### Second Pass Findings' did NOT trip [A6]")
    if not any(e.startswith("[A6b]") for e in deleted_errs):
        errs.append("selftest: downgrading '## Second Pass (REQUIRED)' did NOT trip [A6b]")
    if not any(e.startswith("[A6c]") for e in deleted_errs):
        errs.append("selftest: deleting the '### Second Pass Findings' bracket did NOT trip [A6c]")

    # [A6c] negative controls, deletion AND negation (#561 round 1 S4, per S1):
    # narrowing 'and/or' to 'and' is the round-4-F1 shape (require BOTH markers
    # instead of either); negating 'never' to 'always' reverts to the
    # delimiter-based rule the redesign repudiates.
    a6c_and_only = _A6_GOOD_RT_PROMPT.replace(
        "`**Finding:**` and/or a line whose first non-whitespace characters are `**Severity:**`",
        "`**Finding:**` and a line whose first non-whitespace characters are `**Severity:**`",
    )
    assert a6c_and_only != _A6_GOOD_RT_PROMPT, "selftest setup: A6c and/or-narrowing needle not found"
    a6c_and_only_errs = [e for e in check_rt_prompt(a6c_and_only) if e.startswith("[A6c]")]
    if not a6c_and_only_errs:
        errs.append("selftest: narrowing 'and/or' to 'and' did NOT trip [A6c]")

    a6c_negated_heading = _A6_GOOD_RT_PROMPT.replace(
        "the heading itself is never what makes text scored or not",
        "the heading itself is always what makes text scored or not",
    )
    assert a6c_negated_heading != _A6_GOOD_RT_PROMPT, "selftest setup: A6c heading-negation needle not found"
    a6c_negated_errs = [e for e in check_rt_prompt(a6c_negated_heading) if e.startswith("[A6c]")]
    if not a6c_negated_errs:
        errs.append("selftest: negating 'never' to 'always' in the heading clause did NOT trip [A6c]")

    # [A6c] fenced-code-block / blockquote / severity-value negative controls
    # (#561 round 3 S1): the round-2 S2/S3 fixes' reviewer-facing halves had
    # NO structural guard at all — deleting either left the full 86-suite
    # green (verified live). Deletion AND negation, same discipline as above.
    a6c_fence_deleted = _A6_GOOD_RT_PROMPT.replace(
        " A line inside a fenced code block or a line beginning with a blockquote marker is never an entry-opening line.",
        "",
    )
    assert a6c_fence_deleted != _A6_GOOD_RT_PROMPT, "selftest setup: A6c fenced-code-block sentence needle not found"
    a6c_fence_deleted_errs = [e for e in check_rt_prompt(a6c_fence_deleted) if e.startswith("[A6c]")]
    if not a6c_fence_deleted_errs:
        errs.append("selftest: deleting the fenced-code-block/blockquote sentence did NOT trip [A6c]")

    a6c_fence_negated = _A6_GOOD_RT_PROMPT.replace(
        "A line inside a fenced code block",
        "A line NOT inside a fenced code block",
    )
    assert a6c_fence_negated != _A6_GOOD_RT_PROMPT, "selftest setup: A6c fenced-code-block negation needle not found"
    a6c_fence_negated_errs = [e for e in check_rt_prompt(a6c_fence_negated) if e.startswith("[A6c]")]
    if not a6c_fence_negated_errs:
        errs.append("selftest: negating 'inside a fenced code block' did NOT trip [A6c] (polarity-blind)")

    a6c_blockquote_negated = _A6_GOOD_RT_PROMPT.replace(
        "a line beginning with a blockquote marker",
        "a line NOT beginning with a blockquote marker",
    )
    assert a6c_blockquote_negated != _A6_GOOD_RT_PROMPT, "selftest setup: A6c blockquote negation needle not found"
    a6c_blockquote_negated_errs = [e for e in check_rt_prompt(a6c_blockquote_negated) if e.startswith("[A6c]")]
    if not a6c_blockquote_negated_errs:
        errs.append("selftest: negating 'beginning with a blockquote marker' did NOT trip [A6c] (polarity-blind)")

    a6c_severity_deleted = _A6_GOOD_RT_PROMPT.replace(
        " Every entry MUST declare, on its `**Severity:**` line, a value that begins with `Fatal` / `Significant` / `Minor`, with the token immediately followed by end-of-line, or by one of `(`, `[`, `,`, `.`, `:`, `;`; strip any leading AND trailing markdown emphasis markers or code-span backticks from the value first — the entry is scored at that recognised severity. A value matching none of the three is scored as Significant by default and flagged as malformed.",
        "",
    )
    assert a6c_severity_deleted != _A6_GOOD_RT_PROMPT, "selftest setup: A6c severity-value sentence needle not found"
    a6c_severity_deleted_errs = [e for e in check_rt_prompt(a6c_severity_deleted) if e.startswith("[A6c]")]
    if not a6c_severity_deleted_errs:
        errs.append("selftest: deleting the severity-value sentence did NOT trip [A6c]")

    a6c_severity_negated = _A6_GOOD_RT_PROMPT.replace(
        "a value that begins with `Fatal`",
        "a value that does not begin with `Fatal`",
    )
    assert a6c_severity_negated != _A6_GOOD_RT_PROMPT, "selftest setup: A6c severity-value negation needle not found"
    a6c_severity_negated_errs = [e for e in check_rt_prompt(a6c_severity_negated) if e.startswith("[A6c]")]
    if not a6c_severity_negated_errs:
        errs.append("selftest: negating 'begins with' in the severity-value sentence did NOT trip [A6c] (polarity-blind)")

    # FA2-2 (PR #583 warden gate): "less"/"minus"/"omitting"/"apart from"/
    # "other than" must now trip the same polarity guard as not/never/etc. —
    # verified live this gate run that "less" alone evaded the pre-fix
    # closed vocabulary across 5 checkers.
    a6c_severity_less = _A6_GOOD_RT_PROMPT.replace(
        "a value that begins with `Fatal`",
        "a value that less begins with `Fatal`",
    )
    assert a6c_severity_less != _A6_GOOD_RT_PROMPT, "selftest setup: A6c severity-value 'less' needle not found"
    a6c_severity_less_errs = [e for e in check_rt_prompt(a6c_severity_less) if e.startswith("[A6c]")]
    if not a6c_severity_less_errs:
        errs.append(
            "selftest: inserting 'less' before 'begins with' in the severity-value "
            "sentence did NOT trip [A6c] (FA2-2 — closed-vocabulary evasion)"
        )

    a6c_malformed_negated = _A6_GOOD_RT_PROMPT.replace(
        "is scored as Significant by default",
        "is NOT scored as Significant by default",
    )
    assert a6c_malformed_negated != _A6_GOOD_RT_PROMPT, "selftest setup: A6c malformed-default negation needle not found"
    a6c_malformed_negated_errs = [e for e in check_rt_prompt(a6c_malformed_negated) if e.startswith("[A6c]")]
    if not a6c_malformed_negated_errs:
        errs.append("selftest: negating 'scored as Significant by default' did NOT trip [A6c] (polarity-blind)")

    # [A6d] deletion AND negation controls (#561 round 1 S4, per S1). The
    # negation mirrors S1's demonstrated exploit shape: negating only the
    # 'include' clause leaves 'the same population' intact later in the same
    # sentence, so a bare co-presence check would not catch it.
    a6d_deleted = _A6_GOOD_RT_PROMPT.replace(_A6_SC_PARAGRAPH, "    SEVERITY-COUNTS: fatal=<F> significant=<S> minor=<M>\n    ```\n")
    assert a6d_deleted != _A6_GOOD_RT_PROMPT, "selftest setup: A6d deletion needle not found"
    a6d_deleted_errs = [e for e in check_rt_prompt(a6d_deleted) if e.startswith("[A6d]")]
    if not a6d_deleted_errs:
        errs.append("selftest: deleting the widened SEVERITY-COUNTS sentence did NOT trip [A6d]")

    a6d_negated = _A6_GOOD_RT_PROMPT.replace(
        "include Fatal/Significant entries you place under `### Second Pass Findings`",
        "explicitly EXCLUDING entries you place under `### Second Pass Findings`",
    )
    assert a6d_negated != _A6_GOOD_RT_PROMPT, "selftest setup: A6d negation needle not found"
    a6d_negated_errs = [e for e in check_rt_prompt(a6d_negated) if e.startswith("[A6d]")]
    if not a6d_negated_errs:
        errs.append("selftest: negating the SEVERITY-COUNTS 'include' clause in place did NOT trip [A6d] (polarity-blind)")

    # [A6e] F2 pointer-or-complete parity controls (#561 fresh round 5 S1/S2):
    # reverting the bracket to the stale pre-round-3/4 parse (deleting the
    # normalization + boundary-character-list + fence-parity detail tokens)
    # must trip [A6e]; a PARTIAL detail-token set must also trip it, even
    # standalone with no pointer phrase present (has_pointer is False here,
    # so has_all_details must hold or the site is rejected).
    a6e_reverted = _A6_GOOD_RT_PROMPT.replace(
        "with the token immediately followed by end-of-line, or by one of `(`, `[`, `,`, `.`, `:`, `;`; strip any leading AND trailing markdown emphasis markers or code-span backticks from the value first",
        "with no further qualification",
    )
    a6e_reverted = a6e_reverted.replace(
        " If this section contains an ODD number of triple-backtick delimiters, the fenced-code-block exclusion does NOT apply for the rest of the section.",
        "",
    )
    assert a6e_reverted != _A6_GOOD_RT_PROMPT, "selftest setup: A6e revert needle not found"
    a6e_reverted_errs = [e for e in check_rt_prompt(a6e_reverted) if e.startswith("[A6e]")]
    if not a6e_reverted_errs:
        errs.append("selftest: reverting the bracket's detail tokens to the stale pre-round-3/4 parse did NOT trip [A6e]")

    a6e_partial = _A6_GOOD_RT_PROMPT.replace(
        " If this section contains an ODD number of triple-backtick delimiters, the fenced-code-block exclusion does NOT apply for the rest of the section.",
        "",
    )
    assert a6e_partial != _A6_GOOD_RT_PROMPT, "selftest setup: A6e partial-detail needle not found"
    a6e_partial_errs = [e for e in check_rt_prompt(a6e_partial) if e.startswith("[A6e]")]
    if not a6e_partial_errs:
        errs.append("selftest: dropping ONE of the three detail tokens (fence-parity) did NOT trip [A6e]")

    # [A6e] continued — S2 divergence-class negative control (#561 fresh
    # round 6 S2, mirroring the reviewer's live exploit): a rule DIVERGENCE
    # that keeps all three proxy substrings intact but changes the boundary-
    # character-set enumeration must still trip [A6e] now that the pin is
    # the full charset-enumeration literal, not the loose "immediately
    # followed" fragment alone.
    a6e_divergent = _A6_GOOD_RT_PROMPT.replace(
        "with the token immediately followed by end-of-line, or by one of `(`, `[`, `,`, `.`, `:`, `;`",
        "with the token immediately followed by any other character whatsoever",
    )
    assert a6e_divergent != _A6_GOOD_RT_PROMPT, "selftest setup: A6e divergence needle not found"
    a6e_divergent_errs = [e for e in check_rt_prompt(a6e_divergent) if e.startswith("[A6e]")]
    if not a6e_divergent_errs:
        errs.append(
            "selftest: a rule DIVERGENCE that changes the boundary-character-"
            "set enumeration while keeping the other two detail tokens intact "
            "did NOT trip [A6e] (#561 fresh round 6 S2)"
        )

    # [A6f] SP1 entry-boundary terminator qualifier deletion control (#561
    # fresh round 5 SP1 / fresh round 6 S6).
    a6f_deleted = _A6_GOOD_RT_PROMPT.replace(
        " that is not itself inside a fenced code block or prefixed by a blockquote marker (`> `)",
        "",
    )
    assert a6f_deleted != _A6_GOOD_RT_PROMPT, "selftest setup: A6f deletion needle not found"
    a6f_deleted_errs = [e for e in check_rt_prompt(a6f_deleted) if e.startswith("[A6f]")]
    if not a6f_deleted_errs:
        errs.append("selftest: deleting the entry-boundary terminator's fence/blockquote qualifier did NOT trip [A6f]")

    # [A6g] SP2 list-marker stripping deletion AND negation controls (#561
    # fresh round 5 SP2).
    a6g_deleted = _A6_GOOD_RT_PROMPT.replace(
        " Before testing either marker, strip an optional leading list marker (`-`, `*`, `+`, or `<digits>.` followed by whitespace); a bulleted line such as `- **Severity:** Fatal` still opens (or carries) an entry.",
        "",
    )
    assert a6g_deleted != _A6_GOOD_RT_PROMPT, "selftest setup: A6g deletion needle not found"
    a6g_deleted_errs = [e for e in check_rt_prompt(a6g_deleted) if e.startswith("[A6g]")]
    if not a6g_deleted_errs:
        errs.append("selftest: deleting the list-marker stripping clause did NOT trip [A6g]")

    a6g_negated = _A6_GOOD_RT_PROMPT.replace(
        "strip an optional leading list marker",
        "do NOT strip an optional leading list marker",
    )
    assert a6g_negated != _A6_GOOD_RT_PROMPT, "selftest setup: A6g negation needle not found"
    a6g_negated_errs = [e for e in check_rt_prompt(a6g_negated) if e.startswith("[A6g]")]
    if not a6g_negated_errs:
        errs.append("selftest: negating 'strip an optional leading list marker' did NOT trip [A6g] (polarity-blind)")

    # [A6g] continued — S1(b) consequence-flip control (#561 fresh round 6
    # S1(b)): keep the trigger phrase, flip the clause's own consequence.
    a6g_consequence_flipped = _A6_GOOD_RT_PROMPT.replace(
        "still opens (or carries) an entry",
        "for READABILITY ONLY; a list-bulleted line is still NOT an entry and scores 0",
    )
    assert a6g_consequence_flipped != _A6_GOOD_RT_PROMPT, "selftest setup: A6g consequence-flip needle not found"
    a6g_flip_errs = [e for e in check_rt_prompt(a6g_consequence_flipped) if e.startswith("[A6g]")]
    if not a6g_flip_errs:
        errs.append(
            "selftest: flipping the list-marker stripping clause's consequence "
            "while keeping its trigger phrase did NOT trip [A6g] (#561 fresh "
            "round 6 S1(b))"
        )

    # [A6c] continued — S5 sweep, four reviewer-facing CONSEQUENCE controls
    # (#561 fresh round 7 S5): each flips a clause's consequence while
    # keeping its trigger phrase intact, mirroring the orchestrator-facing
    # sweep in check_qg_second_pass_score.py.
    a6c_fence_bq_consequence_flipped = _A6_GOOD_RT_PROMPT.replace(
        "is never an entry-opening line.",
        "is treated as an ordinary entry-opening line, exactly like any other line.",
    )
    assert a6c_fence_bq_consequence_flipped != _A6_GOOD_RT_PROMPT, "selftest setup: A6c fence/bq consequence-flip needle not found"
    a6c_fence_bq_flip_errs = [e for e in check_rt_prompt(a6c_fence_bq_consequence_flipped) if e.startswith("[A6c]")]
    if not a6c_fence_bq_flip_errs:
        errs.append(
            "selftest: flipping the fenced-code-block/blockquote clause's "
            "consequence while keeping its trigger phrases did NOT trip "
            "[A6c] (#561 fresh round 7 S5)"
        )

    a6c_mid_sentence_deleted = _A6_GOOD_RT_PROMPT.replace(
        " A mid-sentence or quoted occurrence of either marker string does NOT make surrounding text an entry.",
        "",
    )
    assert a6c_mid_sentence_deleted != _A6_GOOD_RT_PROMPT, "selftest setup: A6c mid-sentence deletion needle not found"
    a6c_mid_sentence_errs = [e for e in check_rt_prompt(a6c_mid_sentence_deleted) if e.startswith("[A6c]")]
    if not a6c_mid_sentence_errs:
        errs.append("selftest: deleting the mid-sentence/quoted-occurrence sentence did NOT trip [A6c] (#561 fresh round 7 S5)")

    a6c_malformed_consequence_flipped = _A6_GOOD_RT_PROMPT.replace(
        "is scored as Significant by default and flagged as malformed.",
        "is scored as Significant by default, for informational purposes only.",
    )
    assert a6c_malformed_consequence_flipped != _A6_GOOD_RT_PROMPT, "selftest setup: A6c malformed-default consequence-flip needle not found"
    a6c_malformed_flip_errs = [e for e in check_rt_prompt(a6c_malformed_consequence_flipped) if e.startswith("[A6c]")]
    if not a6c_malformed_flip_errs:
        errs.append(
            "selftest: dropping the malformed-default's 'flagged as "
            "malformed' consequence while keeping its trigger phrase did NOT "
            "trip [A6c] (#561 fresh round 7 S5)"
        )

    a6c_recognised_consequence_flipped = _A6_GOOD_RT_PROMPT.replace(
        "code-span backticks from the value first — the entry is scored at that recognised severity.",
        "code-span backticks from the value first — the entry is recorded for narration only.",
    )
    assert a6c_recognised_consequence_flipped != _A6_GOOD_RT_PROMPT, "selftest setup: A6c recognised-severity consequence-flip needle not found"
    a6c_recognised_flip_errs = [e for e in check_rt_prompt(a6c_recognised_consequence_flipped) if e.startswith("[A6c]")]
    if not a6c_recognised_flip_errs:
        errs.append(
            "selftest: flipping the recognised-severity consequence while "
            "keeping its trigger phrase did NOT trip [A6c] (#561 fresh round "
            "7 S5)"
        )

    # [A6h] negative controls (#561 fresh round 8 S3): deleting the Section
    # location mirror entirely, reverting its tiebreak to last-only (keeping
    # the malformed flag), and deleting the zero-match/end-definition clauses
    # must each trip [A6h].
    a6h_deleted = _A6_GOOD_RT_PROMPT.replace(
        "Section location: the orchestrator locates each of the FOUR sections this parse reads — `### Fatal Challenges`, `### Significant Challenges`, this section, and `### Minor Observations` — by the first unfenced, unquoted heading — this is the earliest occurrence of such a heading line in the file; a later matching heading line never overrides an earlier one as the section's start; a section's end is the next such heading — when none follows, the section extends to the end of the cited file. If that section's matching-heading count is zero, the fallback triggers on this OBSERVABLE condition itself, not on a diagnosis of why it is zero (a stray fence drives that section's matching-heading count to zero is one cause; the section's only matching heading sitting inside an otherwise-BALANCED, CLOSED fence, with no stray fence anywhere in the file, is another), the fence exclusion stops applying at the heading level too, for both the start and end of that section — raw-heading location end-to-end. If no heading matches even under that fallback, the orchestrator flags `missing-second-pass-section` in the narration log rather than reading the section as empty. If more than one such heading matches, the orchestrator flags `malformed-second-pass-sectioning` and counts the union of all matching sections' entries — de-duplicated by entry identity where the union itself produces a duplicate — rather than just one of them. ",
        "",
    )
    assert a6h_deleted != _A6_GOOD_RT_PROMPT, "selftest setup: A6h deletion needle not found"
    a6h_deleted_errs = [e for e in check_rt_prompt(a6h_deleted) if e.startswith("[A6h]")]
    if not a6h_deleted_errs:
        errs.append("selftest: deleting the Section location mirror entirely did NOT trip [A6h] (#561 fresh round 8 S3)")

    a6h_last_only = _A6_GOOD_RT_PROMPT.replace(
        "the orchestrator flags `malformed-second-pass-sectioning` and counts the union of all matching sections' entries — de-duplicated by entry identity where the union itself produces a duplicate — rather than just one of them.",
        "the orchestrator flags `malformed-second-pass-sectioning` and treats the last matching heading as the section.",
    )
    assert a6h_last_only != _A6_GOOD_RT_PROMPT, "selftest setup: A6h last-only-revert needle not found"
    a6h_last_only_errs = [e for e in check_rt_prompt(a6h_last_only) if e.startswith("[A6h]")]
    if not a6h_last_only_errs:
        errs.append(
            "selftest: reverting the Section location mirror's tiebreak to "
            "last-only (keeping the malformed flag) did NOT trip [A6h] "
            "(#561 fresh round 8 S1/S3)"
        )

    a6h_no_zero_match = _A6_GOOD_RT_PROMPT.replace(
        "If that section's matching-heading count is zero, the fallback triggers on this OBSERVABLE condition itself, not on a diagnosis of why it is zero (a stray fence drives that section's matching-heading count to zero is one cause; the section's only matching heading sitting inside an otherwise-BALANCED, CLOSED fence, with no stray fence anywhere in the file, is another), the fence exclusion stops applying at the heading level too, for both the start and end of that section — raw-heading location end-to-end. ",
        "",
    )
    assert a6h_no_zero_match != _A6_GOOD_RT_PROMPT, "selftest setup: A6h zero-match-deletion needle not found"
    a6h_zero_match_errs = [e for e in check_rt_prompt(a6h_no_zero_match) if e.startswith("[A6h]")]
    if not a6h_zero_match_errs:
        errs.append("selftest: deleting the Section location mirror's zero-match sentence did NOT trip [A6h] (#561 fresh round 8 F1/S3)")

    # [A6h] negative control (#561 fresh round 12 S1): deleting ONLY the
    # generalized-trigger clause (keeping the stray-fence trigger phrase
    # intact) must still trip [A6h] — this is what distinguishes the S1 fix
    # from the round-8 zero-match sentence it's embedded in.
    a6h_no_observable_trigger = _A6_GOOD_RT_PROMPT.replace(
        "the fallback triggers on this OBSERVABLE condition itself, not on a diagnosis of why it is zero (a stray fence drives that section's matching-heading count to zero is one cause; the section's only matching heading sitting inside an otherwise-BALANCED, CLOSED fence, with no stray fence anywhere in the file, is another), ",
        "",
    )
    assert a6h_no_observable_trigger != _A6_GOOD_RT_PROMPT, "selftest setup: A6h observable-trigger-deletion needle not found"
    a6h_observable_trigger_errs = [e for e in check_rt_prompt(a6h_no_observable_trigger) if e.startswith("[A6h]")]
    if not a6h_observable_trigger_errs:
        errs.append("selftest: deleting the Section location mirror's generalized OBSERVABLE-trigger clause did NOT trip [A6h] (#561 fresh round 12 S1)")

    # [A6h] negative controls (#561 fresh round 9 F1/S1/S2): deleting the
    # END-consequence phrase, the zero-match both-predicates phrase, or the
    # union de-dup-basis phrase (each independently) must each trip [A6h].
    a6h_no_end_consequence = _A6_GOOD_RT_PROMPT.replace(
        "extends to the end of the cited file", "runs off the edge of the report",
    )
    assert a6h_no_end_consequence != _A6_GOOD_RT_PROMPT, "selftest setup: A6h END-consequence needle not found"
    a6h_no_end_consequence_errs = [e for e in check_rt_prompt(a6h_no_end_consequence) if e.startswith("[A6h]")]
    if not a6h_no_end_consequence_errs:
        errs.append("selftest: replacing the Section location mirror's END consequence did NOT trip [A6h] (#561 fresh round 9 F1)")

    a6h_no_both_predicates = _A6_GOOD_RT_PROMPT.replace(
        "for both the start and end of that section — raw-heading location end-to-end", "",
    )
    assert a6h_no_both_predicates != _A6_GOOD_RT_PROMPT, "selftest setup: A6h both-predicates needle not found"
    a6h_no_both_predicates_errs = [e for e in check_rt_prompt(a6h_no_both_predicates) if e.startswith("[A6h]")]
    if not a6h_no_both_predicates_errs:
        errs.append("selftest: deleting the Section location mirror's both-predicates phrase did NOT trip [A6h] (#561 fresh round 9 S1)")

    a6h_no_dedup_basis = _A6_GOOD_RT_PROMPT.replace(
        " — de-duplicated by entry identity where the union itself produces a duplicate", "",
    )
    assert a6h_no_dedup_basis != _A6_GOOD_RT_PROMPT, "selftest setup: A6h de-dup-basis needle not found"
    a6h_no_dedup_basis_errs = [e for e in check_rt_prompt(a6h_no_dedup_basis) if e.startswith("[A6h]")]
    if not a6h_no_dedup_basis_errs:
        errs.append("selftest: deleting the Section location mirror's de-dup-basis phrase did NOT trip [A6h] (#561 fresh round 9 S2)")

    # [A6h] negative control (#561 fresh round 10 S5): deleting the
    # missing-second-pass-section narration flag must trip [A6h].
    a6h_no_missing_section = _A6_GOOD_RT_PROMPT.replace(
        "If no heading matches even under that fallback, the orchestrator flags `missing-second-pass-section` in the narration log rather than reading the section as empty. ",
        "",
    )
    assert a6h_no_missing_section != _A6_GOOD_RT_PROMPT, "selftest setup: A6h missing-second-pass-section needle not found"
    a6h_no_missing_section_errs = [e for e in check_rt_prompt(a6h_no_missing_section) if e.startswith("[A6h]")]
    if not a6h_no_missing_section_errs:
        errs.append("selftest: deleting the Section location mirror's missing-second-pass-section flag did NOT trip [A6h] (#561 fresh round 10 S5)")

    # [A6h] negative controls (#561 fresh round 10 F1): the mirror's START
    # clause had no pin of its own before this round — deleting or
    # negating its distinguishing consequence must trip [A6h].
    a6h_no_start_consequence = _A6_GOOD_RT_PROMPT.replace(
        " — this is the earliest occurrence of such a heading line in the file; a later matching heading line never overrides an earlier one as the section's start",
        "",
    )
    assert a6h_no_start_consequence != _A6_GOOD_RT_PROMPT, "selftest setup: A6h START-consequence needle not found"
    a6h_no_start_consequence_errs = [e for e in check_rt_prompt(a6h_no_start_consequence) if e.startswith("[A6h]")]
    if not a6h_no_start_consequence_errs:
        errs.append("selftest: deleting the Section location mirror's START consequence did NOT trip [A6h] (#561 fresh round 10 F1)")

    a6h_start_negated = _A6_GOOD_RT_PROMPT.replace(
        "this is the earliest occurrence of such a heading line in the file",
        "this is NOT the earliest occurrence of such a heading line in the file",
    )
    assert a6h_start_negated != _A6_GOOD_RT_PROMPT, "selftest setup: A6h START negation needle not found"
    a6h_start_negated_errs = [e for e in check_rt_prompt(a6h_start_negated) if e.startswith("[A6h]")]
    if not a6h_start_negated_errs:
        errs.append("selftest: negating the Section location mirror's START consequence in place did NOT trip [A6h] (#561 fresh round 10 F1 polarity guard)")

    # [A6h] negative controls (#561 fresh round 10 follow-up 2): the mirror's
    # Scope-sentence pin previously required only bare, unbounded
    # co-occurrence of the trigger phrase and a generic consequence token —
    # weaker than even the pre-fix SKILL.md-side pin. Deleting the real
    # sentence's consequence clause, and negating it in place via a
    # prepended double-negation while keeping the consequence phrase itself
    # intact, must each trip [A6h].
    a6h_no_scope_consequence = _A6_GOOD_RT_PROMPT.replace(
        'does not change what counts as "the file"',
        'is scoped exactly the same way regardless of what counts as "the file"',
    )
    assert a6h_no_scope_consequence != _A6_GOOD_RT_PROMPT, "selftest setup: A6h Scope-consequence needle not found"
    a6h_no_scope_consequence_errs = [e for e in check_rt_prompt(a6h_no_scope_consequence) if e.startswith("[A6h]")]
    if not a6h_no_scope_consequence_errs:
        errs.append("selftest: replacing the Section location mirror's Scope consequence did NOT trip [A6h] (#561 fresh round 10 follow-up 2)")

    a6h_scope_negated = _A6_GOOD_RT_PROMPT.replace(
        "(e.g. an eval prompt) does not change what counts as",
        '(e.g. an eval prompt) it is NOT true that this does not change what counts as',
    )
    assert a6h_scope_negated != _A6_GOOD_RT_PROMPT, "selftest setup: A6h Scope negation needle not found"
    a6h_scope_negated_errs = [e for e in check_rt_prompt(a6h_scope_negated) if e.startswith("[A6h]")]
    if not a6h_scope_negated_errs:
        errs.append("selftest: negating the Section location mirror's Scope consequence via a prepended double-negation did NOT trip [A6h] (#561 fresh round 10 follow-up 2 polarity guard)")

    # [A6i] negative control (#561 fresh round 8 M2): deleting the
    # anti-inflation sentence must trip [A6i].
    a6i_deleted = _A6_GOOD_RT_PROMPT.replace(
        "Second-pass findings are scored at the same weight as first-pass findings. Apply the same inflation check here as anywhere else — the ≥3 target is a search-effort floor, not a filing quota.\n\n",
        "",
    )
    assert a6i_deleted != _A6_GOOD_RT_PROMPT, "selftest setup: A6i deletion needle not found"
    a6i_deleted_errs = [e for e in check_rt_prompt(a6i_deleted) if e.startswith("[A6i]")]
    if not a6i_deleted_errs:
        errs.append("selftest: deleting the anti-inflation sentence did NOT trip [A6i] (#561 fresh round 8 M2)")

    return errs


def selftest() -> int:
    errs = _selftest_d19() + _selftest_a6()
    if errs:
        print("SELFTEST FAILED:")
        for e in errs:
            print(f"  - {e}")
        return 1
    print("OK — selftest: [D19]/[D19b]/[A6]/[A6b] good fixtures clean; negative controls detected.")
    return 0


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if "--selftest" in argv:
        return selftest()

    errs: list[str] = []
    errs += check_rt_prompt(RT_PROMPT.read_text(encoding="utf-8"))
    errs += check_qg(QG_SKILL.read_text(encoding="utf-8"))
    errs += check_rt_skill(RT_SKILL.read_text(encoding="utf-8"))
    errs += check_return_conv(RETURN_CONV.read_text(encoding="utf-8"))

    if errs:
        print("RT-RECEIPT-CONTRACT VIOLATIONS:")
        for e in errs:
            print(f"  - {e}")
        return 1
    print("OK — #366 red-team↔quality-gate receipt contract satisfied across all four files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
