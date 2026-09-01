#!/usr/bin/env python3
"""Structural check: #366 Score source widened to cover Second Pass Findings (#561).

Invocation (from repo root):
    python3 scripts/check_qg_second_pass_score.py
    python3 scripts/check_qg_second_pass_score.py --selftest

Path-pinned to exactly ONE target file — the quality-gate SKILL.md. This checker
NEVER rglobs; the path pinning is what prevents a self-match, so the pinned
phrases need NOT be obfuscated/split.

Background (#561): the #366 Score source rule computed the weighted score (and
therefore the candidate-clean / clean-pass determination, since both are zero
iff the same two counts are zero) from the cited findings file's
`### Fatal Challenges` / `### Significant Challenges` sections ONLY. A Fatal or
Significant finding that a reviewer's REQUIRED second pass surfaces and places
under `### Second Pass Findings` (per `red-team-prompt.md`) was invisible to
that count — a round whose only Fatal lived there scored 0 and could exit
clean-pass even though the reviewer's own `SEVERITY-COUNTS:` line and receipt
VERDICT both disagreed.

Asserts against `skills/quality-gate/SKILL.md`:
  (a) the Score source rule's OWN text — scoped to the text STRICTLY BEFORE
      the `qg-score-second-pass-population` CONTRACT:START marker (the rule
      sentence itself), NOT a window spanning the block interior (#561 round
      3 F2: the block's own de-dup clause independently contains all three
      co-location tokens, so a window including the block is satisfied by
      block content regardless of what the rule sentence itself says) —
      explicitly adds Second-Pass entries to the two pre-existing headings;
  (b) that addition lives inside a
      `<!-- CONTRACT:qg-score-second-pass-population:START -->` … `:END -->`
      block (point anchor per scripts/CHECKER_CONVENTIONS.md would not do —
      the interior carries a real invariant: the un-spoofability preservation
      argument, the Minor carve-out, the mechanical severity rule, and the
      de-dup clause below), and the block is non-empty;
  (c) the block states widening the population does NOT weaken un-spoofability
      (the orchestrator still counts from on-disk text, not a declared
      number);
  (d) the block states the Minor carve-out: a Second-Pass entry counts only
      when it is itself classified Fatal or Significant — a Minor-severity
      second-pass entry belongs under `### Minor Observations` and does not
      count;
  (e) the block states the mechanical severity rule and the LINE-ANCHORED
      content-marker entry definition:
      (e1) "Entry" is scoped by CONTENT MARKER, not by a `####` delimiter
      (#561 round 4 F1: a delimiter-only definition means a correctly
      `**Severity:** Fatal`-labelled entry that merely omits a heading scores
      0, silently — #561's exact bug, re-opened by the round-3 fix): text
      under `### Second Pass Findings` is an entry iff it carries a LINE
      whose first non-whitespace characters are `**Finding:**` (the
      Steel-Man-Then-Kill Protocol's mandatory marker) and/or a line whose
      first non-whitespace characters are `**Severity:**` — either
      line-initial marker alone suffices, and a mid-sentence or quoted
      occurrence of either marker string does NOT qualify (#561 round 1 S2:
      an unanchored substring test miscounts a reviewer's own prose
      discussing these markers, which fires on every Crucible self-gate).
      The mandated clean-second-pass narrative ("what I re-examined and why
      it's clean") carries neither line-initial marker, so it is non-entry
      prose and scores 0 regardless of whether it happens to carry a `####`
      heading;
      (e2) an entry counts at the severity its own `**Severity:**` line
      declares, parsed by FIRST RECOGNISED TOKEN, not exact equality (#561
      round 2 S2: exact equality mis-scored an annotated line like
      `**Severity:** Minor (non-blocking)` — the exact form
      `red-team-prompt.md` itself teaches for Minor Observations — as
      Significant, blocking clean-pass; and a line like `**Severity:** Fatal
      (unchanged from round N)` as Significant instead of Fatal, manufacturing
      false stagnation progress): if the line's value BEGINS WITH `Fatal` /
      `Significant` / `Minor`, the entry counts at THAT severity and the
      orchestrator flags `annotated-second-pass-severity` in the narration
      log. The `malformed-second-pass-entry` → Significant default is
      reserved for a line whose value matches NONE of the three tokens —
      absent, `**Severity:** High`, empty, or unrecognizable prose — fail-LOUD
      rather than fail-zero (#561 round 1 S3's present-but-invalid-value gap,
      still closed: an unrecognised value still lands on the same fail-loud
      default, only a RECOGNISED-but-annotated value now counts at its own
      severity instead);
  (f) the block states the de-dup clause: a Second-Pass entry that restates
      or elaborates an already-counted Fatal/Significant Challenges entry
      counts ONCE, at the higher severity (without this, the widened
      population is a double-counting channel with no de-dup guard);
  (g) a Red Flags bullet names this failure mode by mistake-shape, so the
      orchestrator has a vigilance entry at execution time, not only a
      document-shape guard (#561);
  (h) the look-harder confirm/demote predicate (a fourth consumer of the same
      population, missed by the initial #561 fix — round 2 F1) carries the
      same population qualifier as the Score source rule, on BOTH branches
      (0F/0S confirm, Fatal/Significant demote);
  (i) the step-5 candidate-clean predicate and (j) Exit Precedence slot #1
      (Clean pass) each carry the same population qualifier — two of
      INV-561-1's nine declared consumers that, unlike the look-harder
      branches, had no structural guard at all until now (#561 round 3 S5);
  (k) the `qg-score-population` convergence-log CONTRACT block's declared
      value-set (`"second-pass-inclusive" | "mixed" | absent`) and
      key-presence semantics (no `marker_version` bump) — that block's own
      anchor comment names THIS checker as its enforcer, but nothing asserted
      its content until now (#561 round 4 S1: a checker-attribution claim
      with no matching assertion is worse than an acknowledged gap). Also
      pins that fragility-rate denominators filter on the
      `"second-pass-inclusive"` value specifically, NOT bare key-presence
      (#561 round 2 S4: a `"mixed"` entry has the key too, and is defined as
      "not fully comparable" — key-presence alone would pull it into the
      denominator anyway);
  (l) the Fatal count tracking rule (Stagnation Detection) — INV-561-1's
      fifth declared consumer, and the only one with no structural guard at
      all (#561 round 2 S1: deleting or negating its "same population"
      sentence left the full suite green);
  (m) the SEVERITY-COUNTS discrepancy clause (Score source rule, step 7)
      carries the directional exception: a declared fatal+significant total
      EXCEEDING the orchestrator's own counted population makes the round
      NOT candidate-clean (#561 round 2 F1: the un-spoofability argument that
      justifies trusting the orchestrator's own (lower) count for SCORING was,
      before this fix, reused unchanged to also justify ignoring a DEFLATION
      discrepancy on the candidate-clean GATE — the one direction #561 is
      about);
  (n) the entry definition's fenced-code-block / blockquote exclusion (#561
      round 2 S3: a marker line inside a fenced code block satisfies the
      line-anchored entry definition exactly, since "first non-whitespace
      characters of a line" does not exclude fenced content — this is round 1
      S2's self-gate-miscount bug reopened through a different door, since
      this diff's own evals embed fenced findings-file excerpts with
      line-initial Severity markers);
  (o) [fresh round 5 S5] the Empty-work-order exception extends to the
      look-harder demotion path, not only step-5's own routing; [fresh round
      5 S4] `severity-counts-discrepancy` is enumerated as its own Exit
      Precedence slot (outranking no-op-fix) and carries a Reason-token-mapping
      bullet, so an unenumerated co-fire cannot resolve to the wrongly-
      attributed `no-op-fix` escalation the exception exists to prevent;
  (e0/e2 cont'd) [fresh round 5 SP1] the entry-boundary rule's terminator
      clause is qualified against the fenced-code-block/blockquote exclusion,
      so a fenced `####` or `**Finding:**` inside a quoted excerpt cannot
      terminate an open entry (only opening it was excluded before); [fresh
      round 5 SP2] a leading list marker (`-`, `*`, `+`, `<digits>.`) is
      stripped before either marker is tested, closing the one malformation
      (a list-bulleted `**Severity:**` line) that raised no fail-loud flag at
      all; [fresh round 5 S3] the Minor-population-join clause's three named
      sinks (`round-N-score.md`'s Minor count, `MinorTrajectory`/
      `minor_trajectory`, `m_exit`) are pinned — INV-561-1's seventh declared
      consumer had zero structural guard before this;
  (p cont'd) [fresh round 5 S1/S2] `_pointer_or_complete`'s coverage is
      extended to `red-team-prompt.md`'s bracket (via
      check_rt_receipt_contract.py's [A6e]), and its `has_pointer or
      has_all_details` short-circuit — which let a pointer site carry a
      contradictory PARTIAL restatement beside its pointer — is tightened to
      `has_all_details` OR (`has_pointer` AND NOT `has_partial_details`).

Polarity guard (#561 round 1 S1): assertions (a), (h), (i), (j), and (m) each
also reject a NEGATED form of their pin — e.g. "explicitly EXCLUDING any
entries under `### Second Pass Findings`" or "(NOT the same population...)" —
a bare substring/window presence test is satisfied by the negated sentence
just as much as the real one, so a revert-in-place that flips the rule's
polarity while keeping its home paragraph intact would otherwise leave the
full suite green. Demonstrated live: negating every consumer qualifier in
place passed both this checker and check_rt_receipt_contract.py's
[D19]/[D19b] before this fix. Assertion (l) is run through the same
`_negates` guard (#561 round 2 S1).

Exits 0 when aligned, 1 with a `- <error>` list otherwise. Stdlib only.
See scripts/CHECKER_CONVENTIONS.md.
"""
from __future__ import annotations
import pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills/quality-gate/SKILL.md"

CONTRACT_NAME = "qg-score-second-pass-population"

# How far before the CONTRACT:START marker assertion (a) is allowed to look for
# the rule's own "### Fatal Challenges" / "### Significant Challenges" mentions.
# Wide enough to cover the Score-source rule's opening sentence, narrow enough
# that unrelated prose elsewhere in the 1000+-line file cannot satisfy it.
_RULE_WINDOW = 500

_RED_FLAG_PIN = "ignoring Fatal/Significant entries under `### Second Pass Findings` (#561)"

# Polarity guard (#561 round 1 S1): a negation token immediately before an
# anchor phrase flips the rule's meaning while leaving the anchor phrase's
# bare substring intact — e.g. "(NOT the same population...)" still contains
# "same population". `[^.]{0,40}` keeps the check within the same clause (not
# crossing a sentence boundary into unrelated prose).
_NEGATION_TOKENS = r"(?:not|never|excluding|except|ignor\w*)"


def _negates(anchor: str, scope: str) -> bool:
    return re.search(rf"(?i)\b{_NEGATION_TOKENS}\b[^.]{{0,40}}{re.escape(anchor)}", scope) is not None


# Anchors that must each occur EXACTLY ONCE in the Section-location clause —
# one per sentence/sub-rule the checker's own assertions above rely on to
# identify that specific sentence's presence and consequence. Enumerated
# explicitly, not auto-discovered (#561 fresh round 10 Part 2 dispatch
# instruction) — auto-discovery cannot distinguish a legitimately-reused
# vocabulary token from a genuine collision, so this list is a hand-picked
# census of the "identify ONE sentence" pins only, kept in sync with the
# presence-check literals used earlier in `check_skill()`. Two categories
# named in the dispatch are deliberately EXCLUDED here, not overlooked:
# the four-section enumeration ("### Fatal Challenges" etc. + "four
# sections") legitimately repeats — the same heading names are used again,
# for the unrelated de-dup/restatement rule, later in this same clause —
# and no single assertion relies on any one of them occurring exactly once
# to identify a specific sentence, only on all four co-occurring somewhere
# in the clause (a completeness check, not a uniqueness pin); the
# `malformed-second-pass-sectioning` flag name is likewise intentionally
# reused — flagged by BOTH the zero-match rule and the union tiebreak, by
# design, as the same narration-log flag for two different triggers of the
# same underlying condition class (a section that cannot be unambiguously
# located).
_SECTION_LOC_UNIQUE_ANCHORS = {
    "START ordinal-position consequence (fresh round 10 F1)": "earliest occurrence of such a heading line in the file",
    "START ordinal-position closing clause (fresh round 10 F1)": "never overrides an earlier one as the section's start",
    "END consequence (fresh round 9 F1)": "extends to the end of the cited file",
    "zero-match trigger consequence (fresh round 8 F1)": "does NOT apply at the heading level",
    "zero-match not-found-as-empty sentence (fresh round 8 F1)": 'never treat "not found" as "empty"',
    "zero-match both-predicates clause (fresh round 9 S1)": "both the start and end predicates",
    "zero-match end-to-end clause (fresh round 9 S1)": "raw-heading location end-to-end",
    "missing-second-pass-section flag (fresh round 10 S5)": "flags `missing-second-pass-section` in the narration log",
    "missing-second-pass-section narration-only framing (fresh round 10 S5)": "this default is narration-only",
    "union tiebreak trigger anchor (fresh round 8 S1/S5)": "more than one such heading matches",
    "union tiebreak consequence (fresh round 8 S1/S5)": "counts the **union** of all matching sections",
    "union de-dup basis (fresh round 9 S2)": "de-duplicated by entry identity",
    "Scope sentence trigger (fresh round 8 SP1)": "this location step applies to the bytes of the cited findings file itself",
    "Scope sentence consequence (fresh round 8 SP1)": "enclosing document's",
    "zero-match generalized-trigger clause (fresh round 12 S1)": "the fallback triggers on this OBSERVABLE condition itself, not on a diagnosis of why it is zero",
    "zero-match balanced-fence alternative cause (fresh round 12 S1)": "sits inside an otherwise-BALANCED, CLOSED fence is another",
}

# (#561 fresh round 10 follow-up 2) The two Scope-sentence entries above are
# KEPT, not removed, even though the direct SP1 pin below now also checks
# the sentence's positive consequence verbatim (which is what actually
# closes the relocation-attack gap this follow-up fixes — a count-only
# registry entry cannot distinguish "the real sentence, unmoved" from "a
# decoy elsewhere supplying the same two substrings", so it was never
# sufficient on its own). They still add value for a DIFFERENT attack shape
# this registry is designed for: a future sentence that duplicates either
# phrase elsewhere in the clause for an unrelated reason (a genuine
# collision, count > 1) — the direct SP1 pin below only checks the window
# right after the trigger, so it would not notice a stray duplicate of
# "enclosing document's" showing up far away in the clause.

# Phrases that are legitimately shared across more than one sentence BY
# DESIGN — the F1 fix's own resolution for the START/END fence-blockquote
# collision is that both sentences keep this shared base phrase, but each
# ALSO carries its own distinguishing anchor (registered here) that a bare
# substring pin on the shared phrase alone cannot provide. If a THIRD
# sentence starts reusing the shared phrase without registering its own
# distinguishing anchor here, the occurrence count below stops matching the
# distinguisher count and this check fails loud.
_SECTION_LOC_SHARED_ANCHORS = {
    "neither inside a fenced code block nor prefixed by a blockquote marker": [
        "earliest occurrence of such a heading line in the file",  # START's own
        "extends to the end of the cited file",  # END's own
    ],
}


def check_section_location_anchor_uniqueness(section_loc: str) -> list[str]:
    """Part 2 structural self-check (#561 fresh round 10 dispatch).

    Rounds 5-10 each found a FRESH anchor-collision defect in this one
    clause: a presence-only pin (`phrase in section_loc`) cannot tell WHICH
    sentence supplied a match, so when a later round's new sentence reuses
    an earlier sentence's exact anchor phrase, the earlier pin silently
    becomes a no-op — the earlier sentence can then be deleted or
    polarity-reversed with the full suite green, because the later
    sentence's copy of the same phrase still satisfies the bare check.
    Round 10's F1 was the sixth instance (START's fence/blockquote phrase,
    hollowed out by round 8's END sentence reusing it verbatim).

    This function makes that failure mode fail loud automatically instead
    of requiring a reviewer to manually rediscover a fresh instance each
    round: every anchor phrase this file's own assertions rely on to
    identify ONE specific sentence must occur EXACTLY ONCE in the clause
    (`_SECTION_LOC_UNIQUE_ANCHORS`), and every phrase that is legitimately
    shared by design must be paired 1:1 with its own registered
    distinguishing anchors (`_SECTION_LOC_SHARED_ANCHORS`) — a new,
    unregistered sentence reusing a shared phrase trips this the same way
    an unregistered duplicate of a unique anchor does.
    """
    errs: list[str] = []

    for label, phrase in _SECTION_LOC_UNIQUE_ANCHORS.items():
        count = section_loc.count(phrase)
        if count == 0:
            errs.append(
                f"ANCHOR-UNIQUENESS: '{label}' anchor phrase {phrase!r} "
                "not found in the Section-location clause at all (#561 "
                "fresh round 10 Part 2 self-check)"
            )
        elif count > 1:
            errs.append(
                f"ANCHOR-UNIQUENESS COLLISION: '{label}' anchor phrase "
                f"{phrase!r} occurs {count} times in the Section-location "
                "clause — a presence-only pin on this phrase can no longer "
                "tell which sentence supplied the match, so a different "
                "sentence's copy of the same phrase silently converts this "
                "pin into a no-op (#561 fresh round 10 Part 2 self-check — "
                "the structural fix for six consecutive anchor-collision "
                "Fatals in this clause, rounds 5-10)"
            )

    for shared_phrase, distinguishers in _SECTION_LOC_SHARED_ANCHORS.items():
        occurrences = section_loc.count(shared_phrase)
        if occurrences != len(distinguishers):
            errs.append(
                "ANCHOR-UNIQUENESS COLLISION: the shared phrase "
                f"{shared_phrase!r} occurs {occurrences} times in the "
                f"Section-location clause but only {len(distinguishers)} "
                "distinguishing anchor(s) are registered for it in "
                "`_SECTION_LOC_SHARED_ANCHORS` — either a sentence was "
                "deleted without removing its distinguisher, or a NEW "
                "sentence has started reusing this shared phrase without "
                "registering a distinguishing anchor of its own here, "
                "reopening the exact anchor-collision shape #561 fresh "
                "round 10 F1 fixed for START vs END (#561 fresh round 10 "
                "Part 2 self-check)"
            )
        for d in distinguishers:
            if d not in section_loc:
                errs.append(
                    f"ANCHOR-UNIQUENESS: distinguishing anchor {d!r} "
                    f"registered for the shared phrase {shared_phrase!r} "
                    "is missing from the Section-location clause (#561 "
                    "fresh round 10 Part 2 self-check)"
                )

    return errs


def check_skill(text: str) -> list[str]:
    errs: list[str] = []

    # Locate the CONTRACT block first — assertion (a) is scoped to a bounded
    # window around it, not the whole file (S1: a whole-file grep is
    # decoy-satisfiable by unrelated prose that mentions the same headings).
    start_m = re.search(rf"<!-- CONTRACT:{CONTRACT_NAME}:START.*?-->", text, re.DOTALL)
    end_m = re.search(rf"<!-- CONTRACT:{CONTRACT_NAME}:END.*?-->", text, re.DOTALL)

    if start_m is None or end_m is None or end_m.start() < start_m.start():
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block not found "
            f"(<!-- CONTRACT:{CONTRACT_NAME}:START --> … :END -->)"
        )
        block = ""
        scope = text
    else:
        block = text[start_m.end():end_m.start()]
        if not block.strip():
            errs.append(f"SKILL: {CONTRACT_NAME} CONTRACT block is empty")
        # Scoped to the text STRICTLY BEFORE CONTRACT:START (the rule's own
        # sentence) — NOT a window spanning the block interior. The block's
        # own de-dup clause independently contains all three co-location
        # tokens ("Fatal Challenges" / "Significant Challenges" / "Second
        # Pass Findings"), so a window that includes the block is satisfied
        # by block content regardless of what the rule sentence itself says
        # (#561 round 3 F2).
        window_start = max(0, start_m.start() - _RULE_WINDOW)
        scope = text[window_start:start_m.start()]

    # (a) widened population: Second Pass Findings added to the score source,
    # scoped to the rule's own text — not the whole file.
    if "### Second Pass Findings" not in scope:
        errs.append(
            "SKILL: Score source rule does not mention '### Second Pass Findings' "
            "(population not widened)"
        )
    if not re.search(
        r"Fatal Challenges.{0,400}Significant Challenges.{0,400}Second Pass Findings",
        scope, re.DOTALL,
    ):
        errs.append(
            "SKILL: '### Second Pass Findings' is not co-located with the existing "
            "'### Fatal Challenges' / '### Significant Challenges' population in the "
            "Score source rule's own text (widening must extend the same population, "
            "not a separate one mentioned elsewhere in the file)"
        )
    # (a) continued — POSITIVE-connective pin (#561 round 4 S4): the co-location
    # + negation-token checks above are defeated by an out-of-vocabulary synonym
    # that never uses the enumerated `_NEGATION_TOKENS` (e.g. "entries under
    # ### Second Pass Findings are DISREGARDED for scoring purposes" keeps all
    # three headings co-located and trips no negation token). Pinning the exact
    # positive phrase closes that gap regardless of what vocabulary a rewrite
    # uses, the same style assertions (m)/(h) already use for their
    # literal-phrase pins.
    if not re.search(
        r"plus\s+any Fatal/Significant-severity entries under\s+`### Second Pass Findings`",
        scope,
    ):
        errs.append(
            "SKILL: the Score source rule's own text is missing the literal 'plus "
            "any Fatal/Significant-severity entries under `### Second Pass "
            "Findings`' phrase (#561 round 4 S4: co-location + negation-token "
            "checks alone are defeated by an out-of-vocabulary synonym like "
            "'disregarded'/'omit' that trips no enumerated negation token)"
        )
    if _negates("Second Pass Findings", scope):
        errs.append(
            "SKILL: the Score source rule's own text NEGATES '### Second Pass "
            "Findings' (e.g. 'explicitly EXCLUDING'/'ignores' immediately before it) "
            "instead of adding it to the counted population (#561 round 1 S1: a bare "
            "co-location check is satisfied by the negated sentence too)"
        )

    # (b) already reported above if block missing/empty.

    # (c) un-spoofability preservation argument, inside the block.
    if "un-spoofab" not in block:
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block missing the un-spoofability "
            "preservation argument (widening the population must not be silently "
            "read as weakening the un-spoofable-score guarantee)"
        )

    # (c) continued — S1 section-location clause (#561 fresh round 7 S1;
    # completeness pass fresh round 8 F1/S1/S3/S4/S5/SP1/SP2): the rest of
    # this block presupposes the FOUR sections this parse reads are already
    # correctly located. Round 7 specified only the three severity-bearing
    # sections' START and a last-match tiebreak, leaving the zero-match case
    # (F1: an unbalanced fence anywhere above a heading zeroed the whole
    # population, and round 3's fence-parity fail-loud guard cannot fire
    # because it presupposes the section is already located), the section's
    # END (S4), the fourth section (`### Minor Observations`, SP2), and the
    # tiebreak's own directional correctness (S5: last-match silently drops
    # real entries under an earlier matching heading) all undefined or wrong.
    # Window widened to cover the completed, multi-paragraph clause (widened
    # again #561 fresh round 9 F1/S1/S2: the clause grew to ~4790 chars with
    # the section-END consequence pin, the zero-match both-predicates
    # clarification, and the union de-dup-basis sentence — measured live
    # against the real on-disk clause, headroom kept above the measured
    # length per round 8's own M1 lesson about undersized fixed windows;
    # widened again #561 fresh round 10 F1: the clause grew to ~5534 chars
    # with the section-START consequence pin, measured live against the
    # real on-disk clause; widened again #561 fresh round 12 (M2: this
    # pattern of undersized fixed windows has recurred three times — widen
    # with REAL headroom this time): the zero-match rule's generalized-
    # trigger rewording (S1) pushed the clause's last required literal
    # ('de-duplicated by entry identity') to ~6410 chars from this anchor,
    # measured live; ~800 chars of headroom kept above that measurement).
    section_loc_m = re.search(r"Section location.{0,7200}", block, re.DOTALL)
    section_loc = section_loc_m.group(0) if section_loc_m else ""
    if not section_loc_m:
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block missing the section-location "
            "clause entirely (#561 fresh round 7 S1)"
        )
    else:
        # Four-section enumeration (SP2): `### Minor Observations` is
        # load-bearing for the de-dup guard and the Minor population join,
        # and retains the same fenced-heading exposure as its three
        # severity-bearing siblings if left unlocated.
        if not (
            "### Fatal Challenges" in section_loc
            and "### Significant Challenges" in section_loc
            and "### Second Pass Findings" in section_loc
            and "### Minor Observations" in section_loc
            and re.search(r"[Ff]our sections", section_loc)
        ):
            errs.append(
                f"SKILL: {CONTRACT_NAME} CONTRACT block's section-location "
                "clause does not enumerate all FOUR sections the parse reads "
                "(`### Fatal Challenges` / `### Significant Challenges` / "
                "`### Second Pass Findings` / `### Minor Observations`) — "
                "(#561 fresh round 8 SP2)"
            )

        # Fence/blockquote exclusion at the heading (section-start) level.
        if "neither inside a fenced code block nor prefixed by a blockquote marker" not in section_loc:
            errs.append(
                f"SKILL: {CONTRACT_NAME} CONTRACT block missing the section-location "
                "clause's fence/blockquote exclusion at the heading level (#561 "
                "fresh round 7 S1)"
            )
        elif _negates("neither inside a fenced code block nor prefixed by a blockquote marker", section_loc):
            errs.append(
                f"SKILL: {CONTRACT_NAME} CONTRACT block's section-location clause "
                "NEGATES its fence/blockquote exclusion instead of asserting it "
                "(#561 round 1 S1 polarity guard)"
            )

        # Section START definition, with its OWN distinguishing consequence
        # (#561 fresh round 10 F1): the fence/blockquote check just above is
        # a bare substring test anywhere in section_loc, so it is satisfied
        # by the START sentence OR by the END sentence's own verbatim copy
        # of that exact phrase eleven words later — round 8 added the END
        # sentence, which retroactively hollowed out the round-7 START pin
        # into a no-op. Live-verified: the START sentence can be deleted or
        # polarity-reversed to "the LAST `###`-level heading ... governs,
        # fenced or not, blockquoted or not" and the check above stays
        # green because the END sentence still supplies the phrase.
        # Anchor narrowly on the START sentence's own literal prefix (a
        # mutation that changes "the first" also breaks this anchor) and
        # require an ordinal-position consequence the END sentence does
        # NOT carry, mirroring the section-END fix's own consequence-pin
        # shape (#561 fresh round 9 F1).
        start_def_m = re.search(
            r"section's \*\*start\*\* is the first `###`-level heading line "
            r"matching that exact heading text which is itself \*{0,2}"
            r"neither inside a fenced code block nor prefixed by a "
            r"blockquote marker\*{0,2}.{0,600}",
            section_loc, re.DOTALL,
        )
        if not (
            start_def_m
            and "earliest occurrence of such a heading line in the file" in start_def_m.group(0)
            and "never overrides an earlier one as the section's start" in start_def_m.group(0)
        ):
            errs.append(
                f"SKILL: {CONTRACT_NAME} CONTRACT block's section-location "
                "clause does not define the section's START with its own "
                "distinguishing consequence ('earliest occurrence of such a "
                "heading line in the file' / 'never overrides an earlier "
                "one as the section's start') — without this, the START "
                "sentence is pinned only by a fence/blockquote phrase the "
                "END sentence also carries verbatim, so the START sentence "
                "can be deleted or reversed to 'the LAST heading governs' "
                "undetected (#561 fresh round 10 F1)"
            )
        elif _negates("earliest occurrence of such a heading line in the file", start_def_m.group(0)):
            errs.append(
                f"SKILL: {CONTRACT_NAME} CONTRACT block's section-START "
                "definition NEGATES 'earliest occurrence of such a heading "
                "line in the file' instead of asserting it (#561 fresh "
                "round 10 F1 polarity guard)"
            )

        # Scope sentence (SP1): the parse target is the cited findings file's
        # own bytes, not an enclosing document (e.g. an eval prompt) that
        # happens to quote it — without this, the clause's own worked
        # example (a heading inside a quoted excerpt) contradicts the eval
        # fixtures that embed a whole findings file inside a prompt fence.
        #
        # (#561 fresh round 10 follow-up 2) This pin previously required
        # only the trigger phrase followed by the bare token "enclosing
        # document's" anywhere within 250 chars — a pure co-occurrence
        # check, exactly the shape the START/END/zero-match pins above were
        # already fixed away from. Live-verified relocation attack: delete
        # the real Scope sentence, add a decoy elsewhere in the clause that
        # asserts the OPPOSITE meaning ("ordinarily parsing defers to the
        # enclosing document's own structure and content instead") while
        # still containing both the trigger phrase and "enclosing
        # document's" exactly once each — the old pin stayed green because
        # it never checked the sentence's actual POSITIVE CONSEQUENCE, only
        # that the two substrings co-occurred within the window. Require the
        # real sentence's own consequence clause VERBATIM within the
        # trigger's own captured window, not just a generic token.
        #
        # NOTE on the `_negates` guard below: it deliberately anchors on
        # "is parsed as that file's own content", NOT on "the enclosing
        # document's". The genuine, correct sentence itself reads "...is
        # parsed as that file's own content, not as the enclosing
        # document's." — that "not" is what makes the sentence CORRECT (it
        # is asserting the parse target is NOT the enclosing document). A
        # `_negates` guard anchored on "the enclosing document's" would
        # match that "not" and misfire on the real sentence; anchoring on
        # "is parsed as that file's own content" instead only fires if a
        # negation token is inserted directly before THAT clause (e.g. "is
        # NOT parsed as that file's own content"), which is the actual
        # polarity-flip attack this guard exists to catch.
        scope_sentence_m = re.search(
            r"this location step applies to the bytes of the cited findings "
            r"file itself.{0,300}",
            section_loc, re.DOTALL,
        )
        scope_sentence_window = scope_sentence_m.group(0) if scope_sentence_m else ""
        if not (
            scope_sentence_m
            and "is parsed as that file's own content, not as the enclosing document's"
            in scope_sentence_window
        ):
            errs.append(
                f"SKILL: {CONTRACT_NAME} CONTRACT block's section-location "
                "clause does not scope itself to the cited findings file's "
                "own bytes with its own positive-consequence clause verbatim "
                "('this location step applies to the bytes of the cited "
                "findings file itself ... is parsed as that file's own "
                "content, not as the enclosing document's') — a bare "
                "co-occurrence of the trigger phrase and the token 'enclosing "
                "document's' is satisfiable by a decoy sentence elsewhere in "
                "the clause that asserts the opposite meaning while "
                "preserving both phrases' counts (#561 fresh round 8 SP1; "
                "consequence-anchored fresh round 10 follow-up 2)"
            )
        elif _negates("is parsed as that file's own content", scope_sentence_window):
            errs.append(
                f"SKILL: {CONTRACT_NAME} CONTRACT block's Scope sentence "
                "NEGATES 'is parsed as that file's own content' instead of "
                "asserting it (#561 fresh round 10 follow-up 2 polarity "
                "guard)"
            )

        # Section END definition (S4): without it, three consumers (the
        # entry-boundary's 'end of the section' fallback, the fence-parity
        # trigger's 'section boundary', and the fence-parity count's own
        # span) read an undefined span.
        #
        # (#561 fresh round 9 F1) This pin previously stopped at the bare
        # trigger phrase, with no `_negates` guard and no check on the
        # fallback's own CONSEQUENCE — unlike its three siblings in this
        # same clause (fence/blockquote exclusion, zero-match rule, union
        # tiebreak, all `_negates`-guarded). Live-verified that inverting
        # the fallback's polarity in place ("the section ends at its own
        # heading line and is read as EMPTY rather than running to the end
        # of the cited file") kept both anchor phrases intact and left the
        # full suite green — reopening #561's original bug on a report
        # whose trailing heading is quoted inside a fence. Require the
        # fallback's own positive-consequence phrase and guard it.
        end_def_m = re.search(
            r"section's \*\*end\*\* is the next `###`-level heading line "
            r"that is itself neither inside a fenced code block nor "
            r"prefixed by a blockquote marker.{0,300}",
            section_loc, re.DOTALL,
        )
        if not (
            end_def_m
            and "extends to the end of the cited file" in end_def_m.group(0)
        ):
            errs.append(
                f"SKILL: {CONTRACT_NAME} CONTRACT block's section-location "
                "clause does not define the section's END with its own "
                "positive consequence ('extends to the end of the cited "
                "file' when no following heading exists) (#561 fresh round "
                "8 S4, consequence pin added #561 fresh round 9 F1)"
            )
        elif _negates("extends to the end of the cited file", end_def_m.group(0)):
            errs.append(
                f"SKILL: {CONTRACT_NAME} CONTRACT block's section-END "
                "fallback NEGATES 'extends to the end of the cited file' "
                "instead of asserting it (#561 fresh round 9 F1 polarity "
                "guard)"
            )

        # Zero-match rule (F1): a fence-parity defect anywhere above a
        # heading must not silently zero the section — the fence exclusion
        # must be suspended at the heading-location level too, with a
        # fail-loud flag, and 'not found' must never be read as 'empty'.
        # Window widened #561 fresh round 12 S1 (M2: real headroom this
        # time): the generalized-trigger rewording pushed
        # 'this default is narration-only' to ~2663 chars from the
        # "Zero-match rule" anchor, measured live — widen to 3200 with
        # headroom above that measurement.
        # Window widened #561 fresh round 10 S5: the zero-match rule's
        # trailing sentence (missing-second-pass-section) now measures
        # ~1989 chars from the "Zero-match rule" anchor — the old 1300-char
        # window stopped mid-sentence, before this sentence's checker-
        # relevant tokens, so nothing in this file could pin it at all.
        zero_match_m = re.search(r"Zero-match rule.{0,3200}", section_loc, re.DOTALL)
        if not (
            zero_match_m
            and "does NOT apply at the heading level" in zero_match_m.group(0)
            and "malformed-second-pass-sectioning" in zero_match_m.group(0)
            and re.search(r"never treat .not found. as .empty.", zero_match_m.group(0))
        ):
            errs.append(
                f"SKILL: {CONTRACT_NAME} CONTRACT block's section-location "
                "clause is missing the zero-match rule — a fence-parity "
                "defect that drives a section's matching-heading count to "
                "zero must not zero the section: the fence exclusion must "
                "not apply at the heading level either, re-locating over the "
                "raw heading lines with a `malformed-second-pass-sectioning` "
                "flag, and 'section not found' must never be read as "
                "'section empty' (#561 fresh round 8 F1: without this, an "
                "unbalanced fence anywhere above a heading reopens #561's "
                "original bug through the section-location step, and round "
                "3's fence-parity fail-loud guard cannot fire because it "
                "presupposes the section is already located)"
            )
        elif _negates("does NOT apply at the heading level", zero_match_m.group(0)):
            errs.append(
                f"SKILL: {CONTRACT_NAME} CONTRACT block's zero-match rule "
                "NEGATES 'does NOT apply at the heading level' instead of "
                "asserting it (#561 round 1 S1 polarity guard)"
            )

        # Zero-match rule, generalized OBSERVABLE trigger (#561 fresh round
        # 12 S1): a section whose only matching heading sits inside an
        # otherwise-BALANCED, CLOSED fence (no fence-parity defect anywhere
        # in the file) produced a zero unexcluded-match count that neither
        # the old defect-diagnosed trigger nor the missing-section flag
        # covered — nothing was flagged at all. Fixed by conditioning the
        # fallback on the observable zero count, not on a diagnosed cause.
        if not (
            zero_match_m
            and "the fallback triggers on this OBSERVABLE condition itself, not on a diagnosis of why it is zero"
            in zero_match_m.group(0)
        ):
            errs.append(
                f"SKILL: {CONTRACT_NAME} CONTRACT block's zero-match rule "
                "does not condition the fallback on the OBSERVABLE zero-"
                "unexcluded-match condition itself (rather than on a "
                "diagnosed fence-parity-defect cause) — without this, a "
                "section whose only matching heading sits inside an "
                "otherwise-balanced, closed fence produces a zero count "
                "that neither this fallback nor the missing-section flag "
                "covers, and nothing is flagged at all (#561 fresh round "
                "12 S1)"
            )
        elif _negates(
            "the fallback triggers on this OBSERVABLE condition itself",
            zero_match_m.group(0),
        ):
            errs.append(
                f"SKILL: {CONTRACT_NAME} CONTRACT block's zero-match rule "
                "NEGATES the observable-trigger clause instead of asserting "
                "it (#561 round 1 S1 polarity guard)"
            )

        # Zero-match rule, BOTH predicates (#561 fresh round 9 S1): the
        # fallback previously suspended the fence exclusion "for this
        # location step only" — ambiguous as to whether the END search is
        # part of that step. Under the strict reading the START re-locates
        # over raw headings while the END still consults the very fence
        # state the fallback exists because it cannot be trusted, letting
        # one zero-matched section's span strictly contain a later
        # section's entire span.
        if not (
            zero_match_m
            and "both the start and end predicates" in zero_match_m.group(0)
            and "raw-heading location end-to-end" in zero_match_m.group(0)
        ):
            errs.append(
                f"SKILL: {CONTRACT_NAME} CONTRACT block's zero-match rule "
                "does not state that the fence exclusion is suspended for "
                "BOTH the start and end predicates of the section — raw-"
                "heading location end-to-end — so the section still "
                "terminates at the next raw `###` heading rather than "
                "running to end-of-file merely because the END search still "
                "trusted broken fence state (#561 fresh round 9 S1)"
            )
        elif _negates("both the start and end predicates", zero_match_m.group(0)):
            errs.append(
                f"SKILL: {CONTRACT_NAME} CONTRACT block's zero-match rule "
                "NEGATES 'both the start and end predicates' instead of "
                "asserting it (#561 fresh round 9 S1 polarity guard)"
            )

        # missing-second-pass-section (#561 fresh round 10 S5): the
        # zero-match rule's trailing sentence — the case where no heading
        # matches even under the raw-heading fallback — used to call itself
        # a "fail-loud escalation" with no `Reason:` token, no Exit
        # Precedence slot, and no checker pin anywhere, while its three
        # siblings in the same paragraph all use "flags X in the narration
        # log" phrasing. Resolved as a narration-only flag, matching its
        # siblings; pin both the flag token and the narration-only framing.
        if not (
            zero_match_m
            and "flags `missing-second-pass-section` in the narration log" in zero_match_m.group(0)
            and "this default is narration-only" in zero_match_m.group(0)
        ):
            errs.append(
                f"SKILL: {CONTRACT_NAME} CONTRACT block's zero-match rule "
                "does not flag `missing-second-pass-section` in the "
                "narration log as a narration-only default (matching its "
                "three siblings in the same paragraph) when no heading "
                "matches even under the raw-heading fallback (#561 fresh "
                "round 10 S5)"
            )
        elif _negates("flags `missing-second-pass-section` in the narration log", zero_match_m.group(0)):
            errs.append(
                f"SKILL: {CONTRACT_NAME} CONTRACT block's "
                "`missing-second-pass-section` clause NEGATES its own "
                "trigger instead of asserting it (#561 fresh round 10 S5 "
                "polarity guard)"
            )

        # >1-match tiebreak (S1/S5): UNION counting, not last-match-only — a
        # last-only reading silently drops real entries under an earlier,
        # equally-real matching heading. Pinned on the clause's own literal
        # rule text (not a bare 4-letter substring), with a consequence and
        # a `_negates` guard.
        union_m = re.search(r"more than one such heading matches.{0,1300}", section_loc, re.DOTALL)
        if not (
            union_m
            and re.search(r"counts the \*\*union\*\* of all matching sections", union_m.group(0))
            and "malformed-second-pass-sectioning" in union_m.group(0)
        ):
            errs.append(
                f"SKILL: {CONTRACT_NAME} CONTRACT block's section-location "
                "clause does not state UNION counting on a >1-match tiebreak "
                "('counts the **union** of all matching sections' entries') "
                "— a last-match-only (or first-match-only) reading silently "
                "drops every real entry under an earlier, equally-real "
                "matching heading (#561 fresh round 8 S1/S5: this contradicts "
                "the fail-toward-counting discipline every sibling default in "
                "this population uses, and the prior anchor — a bare "
                "case-insensitive 'last' substring — was live-flipped to "
                "'first' with the full suite green)"
            )
        elif _negates("union", union_m.group(0)):
            errs.append(
                f"SKILL: {CONTRACT_NAME} CONTRACT block's section-location "
                "tiebreak NEGATES 'union' instead of asserting union-counting "
                "(#561 round 1 S1 polarity guard)"
            )

        # Union de-dup basis (#561 fresh round 9 S2): the union rule's
        # parenthetical used to claim duplicates are "de-duplicated by the
        # de-dup clause below" — that clause covers only cross-section
        # restatements (Second-Pass vs. Fatal/Significant/Minor), never a
        # duplicate produced by the union of two matching same-named
        # sections, which is the only kind the union can produce.
        if not (
            union_m
            and "de-duplicated by entry identity" in union_m.group(0)
        ):
            errs.append(
                f"SKILL: {CONTRACT_NAME} CONTRACT block's section-location "
                "union tiebreak does not state its own entry-identity "
                "de-dup basis for a same-named-section duplicate — the "
                "de-dup clause below only covers cross-section restatements "
                "and cannot perform this de-dup (#561 fresh round 9 S2)"
            )
        elif _negates("de-duplicated by entry identity", union_m.group(0)):
            errs.append(
                f"SKILL: {CONTRACT_NAME} CONTRACT block's union tiebreak "
                "NEGATES 'de-duplicated by entry identity' instead of "
                "asserting it (#561 fresh round 9 S2 polarity guard)"
            )

        # Part 2 structural self-check (#561 fresh round 10 dispatch): sweep
        # the whole extracted clause for anchor-phrase collisions, not just
        # the ones this round's findings named. Runs on every invocation of
        # `check_skill()` — both the bare and `--selftest` entry points call
        # this function, so no separate wiring is needed at `main()`.
        errs.extend(check_section_location_anchor_uniqueness(section_loc))

    # (d) Minor carve-out, inside the block.
    if "### Minor Observations" not in block:
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block missing the Minor carve-out's "
            "'### Minor Observations' redirect"
        )
    if not re.search(r"\bMinor\b.{0,80}does not count", block, re.DOTALL):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block missing the explicit "
            "'Minor ... does not count' carve-out"
        )

    # (e1) entry definition is CONTENT-MARKER-based (**Finding:** and/or
    # **Severity:**), not `####`-delimiter-based (#561 round 4 F1: a
    # delimiter-only definition scores a correctly-labelled Fatal missing
    # only its heading as 0) — AND line-anchored (#561 round 1 S2: an
    # unanchored substring test also miscounts prose that merely quotes
    # either marker mid-sentence).
    if not re.search(
        r"first non-whitespace characters are `\*\*Finding:\*\*`.{0,200}and/or"
        r".{0,150}first non-whitespace characters are `\*\*Severity:\*\*`",
        block, re.DOTALL,
    ):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block missing the LINE-ANCHORED "
            "content-marker entry definition ('a line whose first non-whitespace "
            "characters are **Finding:** ... and/or ... a line whose first "
            "non-whitespace characters are **Severity:**' — either line-initial "
            "marker alone makes text a scored entry, #561 round 4 F1 / round 1 S2)"
        )
    # (e0) ENTRY BOUNDARY (#561 round 4 F1): the content-marker rule above says
    # what makes a LINE entry-opening, but not where the entry it opens ENDS —
    # without a boundary, a single Steel-Man-Then-Kill block (one **Finding:**
    # line, its own **Severity:** line later) is read as TWO entries under the
    # literal per-line rule, and the diff's own eval #11/#14 fixtures are
    # unreproducible without this clause (2 entries → 4, not the graded 3).
    if not re.search(
        r"entry \*\*begins\*\* at the first line-initial `\*\*Finding:\*\*` or "
        r"`\*\*Severity:\*\*` marker and \*\*extends\*\* to the line before the "
        r"next `####` heading or the next line-initial `\*\*Finding:\*\*` marker",
        block, re.DOTALL,
    ):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block missing the entry-boundary rule "
            "('an entry begins at the first line-initial **Finding:** or "
            "**Severity:** marker and extends to the line before the next #### "
            "heading or the next line-initial **Finding:** marker') — #561 round 4 "
            "F1: without it, a single Finding+Severity block is read as two "
            "entries, and eval #11/#14 are unreproducible from the rule as written"
        )
    # No `_negates` guard on the closing clause below: its correct baseline is
    # itself negative ("does NOT open"), so a bare negation-token search would
    # misfire on the correct text (same reason the look-harder confirm branch's
    # "has NOT fired" pin above uses literal presence only, not `_negates`).
    if not re.search(r"does not open a second entry", block):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block missing the entry-boundary "
            "rule's closing clause — a `**Severity:**` line inside an already-open "
            "entry is that entry's own severity line and does NOT open a second "
            "entry (#561 round 4 F1)"
        )
    # (e0) continued — SP1 terminator fence/blockquote qualifier (#561 fresh
    # round 5 SP1), referent made explicit/condition-based (#561 fresh round 6
    # S6): the boundary rule's terminator clause ("the next #### heading or
    # the next line-initial **Finding:** marker") must be qualified against
    # the fence/blockquote CONDITION itself — not the fence/blockquote
    # exclusion rule's OPENING-line PREDICATE, which is undefined for a
    # `####` heading (never an entry-opening line regardless of fencing) and
    # was live-shown to admit the vacuous reading under which no `####`
    # heading ever terminates an entry (the diff's own eval #19 adopted it).
    if not re.search(
        r"marker \*?\*?that is not itself inside a fenced code block or "
        r"prefixed by a blockquote marker \(`> `\)\*?\*?, whichever comes first",
        block,
    ):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block's entry-boundary terminator "
            "clause does not state the explicit, condition-based referent "
            "('that is not itself inside a fenced code block or prefixed by a "
            "blockquote marker (`> `)') for its `####`/`**Finding:**` "
            "terminator (#561 fresh round 6 S6: a predicate-based referent — "
            "'excluded by the fenced-code-block or blockquote rule below' — is "
            "undefined for a `####` heading, which the fence/blockquote rule "
            "never treats as entry-opening regardless of fencing)"
        )
    if not re.search(r"strip an optional leading list marker", block):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block missing the list-marker "
            "stripping clause (#561 fresh round 5 SP2: a list-marker-prefixed "
            "`- **Severity:** Fatal` line was silently not an entry, the only "
            "malformation that raised no fail-loud narration-log flag)"
        )
    elif _negates("strip an optional leading list marker", block):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block NEGATES the list-marker "
            "stripping clause instead of asserting it (#561 round 1 S1 polarity "
            "guard)"
        )
    if not re.search(r"blockquote marker `> ` (?:below )?is a distinct exclusion", block):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block missing the list-marker-vs-"
            "blockquote distinct-exclusion clause (#561 fresh round 5 SP2: `> ` "
            "denotes quotation while a list marker denotes formatting, and the "
            "two must not be conflated)"
        )
    if not re.search(r"mid-sentence or quoted occurrence", block):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block missing the mid-sentence/quoted-"
            "occurrence exclusion clause (#561 round 1 S2: a marker string merely "
            "quoted or discussed in prose, not opening a line, must not make that "
            "prose a scored entry — this is what keeps a reviewer's own narrative "
            "about these markers from miscounting itself)"
        )
    # (n) continued — S5 sweep, mid-sentence/quoted-occurrence CONSEQUENCE pin
    # (#561 fresh round 7 S5): the check above pins only the TRIGGER phrase,
    # with no `_negates` guard at all (the pre-existing gap this finding
    # names) — live-verified that flipping "does not make surrounding prose
    # an entry" to "makes the surrounding prose a scored entry" leaves the
    # trigger phrase untouched and restores round 1's S2 bug.
    mid_sentence_m = re.search(r"mid-sentence or quoted occurrence.{0,150}", block, re.DOTALL)
    if not (mid_sentence_m and "does not make surrounding prose an entry" in mid_sentence_m.group(0)):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block's mid-sentence/quoted-"
            "occurrence exclusion does not carry its own CONSEQUENCE ('does "
            "not make surrounding prose an entry') within reach of its "
            "trigger phrase (#561 fresh round 7 S5: a rewrite that keeps the "
            "trigger phrase but flips the consequence restores round 1's S2 "
            "bug undetected)"
        )
    elif _negates("does not make surrounding prose an entry", mid_sentence_m.group(0)):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block's mid-sentence/quoted-"
            "occurrence consequence NEGATES 'does not make surrounding prose "
            "an entry' instead of asserting it (#561 round 1 S1 polarity "
            "guard)"
        )
    if not re.search(r"heading.{0,80}never itself what makes text an entry", block, re.DOTALL):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block missing the explicit statement "
            "that a `####` heading is never itself what makes text an entry (#561 "
            "round 4 F1: closes the gap where a missing heading alone zeroes a "
            "correctly-labelled Fatal)"
        )

    # (e2) mechanical severity rule — FIRST RECOGNISED TOKEN, not exact
    # equality (#561 round 2 S2: exact equality mis-scored an annotated line
    # like `**Severity:** Minor (non-blocking)` as Significant — blocking
    # clean-pass — and `**Severity:** Fatal (unchanged from round N)` as
    # Significant instead of Fatal, manufacturing false stagnation progress).
    if not re.search(
        r"begins with\s*`?Fatal`?\s*,?\s*`?Significant`?,?\s*or\s*`?Minor`?",
        block, re.DOTALL,
    ):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block missing the first-recognised-"
            "token severity parse ('if the line's value begins with Fatal, "
            "Significant, or Minor ... counts at that severity') — #561 round 2 "
            "S2: an annotated severity line (e.g. 'Minor (non-blocking)', the exact "
            "form red-team-prompt.md teaches for Minor Observations) must count at "
            "its own recognised severity, not fall into the malformed default"
        )
    # (e2) continued — normalization + word-boundary (#561 round 3 S4): an
    # unnormalized, unbounded prefix match mis-scores `**Severity:** **Fatal**`
    # as the malformed-default Significant (a Fatal counted as Significant —
    # the exact false-stagnation-progress harm round 2's S2 named) and fails
    # open to 0 on a hedge like `**Severity:** Minor-to-Significant`, whose
    # value merely begins with `Minor` with no boundary enforced.
    if not re.search(r"strip.{0,40}(leading )?markdown emphasis markers", block, re.IGNORECASE):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block missing the normalization step "
            "('strip ... markdown emphasis markers') before parsing the severity "
            "value (#561 round 3 S4: `**Severity:** **Fatal**` must not mis-score "
            "as the malformed-default Significant)"
        )
    # (e2) continued — trailing-whitespace strip (#561 fresh round 12 Second
    # Pass finding): the value's own TRAILING whitespace was never stripped
    # (only the line's leading whitespace and a leading list marker were),
    # so `**Severity:** Fatal ` (one trailing space) fell through to the
    # malformed-second-pass-entry default and mis-scored a real Fatal as
    # Significant — moving the weighted score 3->1 and granting false
    # stagnation Progress on an open Fatal (Fatal count reads 0 against the
    # prior round's 1). Pinned as its own assertion, distinct from the
    # markdown-emphasis-marker strip above, since the two are independent
    # normalization steps a mutation could drop separately.
    if "strip any leading and trailing WHITESPACE from the value" not in block:
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block missing the trailing-"
            "whitespace strip on the severity value ('strip any leading and "
            "trailing WHITESPACE from the value itself') before the boundary "
            "test — symmetric with the existing leading-whitespace strip "
            "(#561 fresh round 12 Second Pass finding: `**Severity:** Fatal ` "
            "with one trailing space must recognise as Fatal, not fall "
            "through to the malformed-second-pass-entry Significant default)"
        )
    elif _negates("strip any leading and trailing WHITESPACE from the value", block):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block NEGATES the trailing-"
            "whitespace strip instead of asserting it (#561 round 1 S1 "
            "polarity guard)"
        )
    if "code-span backtick" not in block:
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block missing the code-span-backtick "
            "stripping half of the normalization step (#561 round 3 S4: "
            "`` `Fatal` `` must recognise the same as bare `Fatal`)"
        )
    if not re.search(
        r"immediately followed by end-of-line, or by one of"
        r".{0,10}`\(`.{0,10}`\[`.{0,10}`,`.{0,10}`\.`.{0,10}`:`.{0,10}`;`",
        block, re.DOTALL,
    ):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block missing the word-boundary rule's "
            "end-of-line/punctuation set ('immediately followed by end-of-line, or "
            "by one of (, [, ,, ., :, ;') on the recognised severity token (#561 "
            "round 4 S1: the punctuation set must include the ordinary terminal "
            "punctuation, not just the original (, [, —, , set)"
        )
    if not re.search(
        r"whitespace followed by a dash.{0,40}`-`.{0,10}`–`.{0,10}`—`",
        block, re.DOTALL,
    ):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block missing the spaced-dash boundary "
            "clause ('whitespace followed by a dash — `-`, `–`, or `—`') (#561 round "
            "4 S1: without requiring whitespace before it, the ordinary hyphen-minus "
            "form `Fatal - blocks the release` either mis-scores as the "
            "malformed-default Significant, or a bare hyphen fails to discriminate "
            "it from `Minor-to-Significant`)"
        )
    if "Fatal - blocks the release" not in block:
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block missing the worked positive "
            "example 'Fatal - blocks the release' proving the spaced-hyphen form "
            "recognises (#561 round 4 S1)"
        )
    if "Minor-to-Significant" not in block:
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block missing the "
            "'Minor-to-Significant' negative example proving the word-boundary "
            "rule actually excludes an unbounded-prefix hedge (#561 round 3 S4)"
        )
    if not re.search(r"no whitespace precedes the hyphen", block):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block missing the explicit "
            "'no whitespace precedes the hyphen' discriminator explaining why "
            "`Minor-to-Significant` stays excluded under the widened spaced-dash "
            "boundary (#561 round 4 S1)"
        )
    if not re.search(r"flags `annotated-second-pass-severity`", block):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block missing the "
            "'flags `annotated-second-pass-severity`' narration-log obligation for "
            "a recognised-but-annotated `**Severity:**` line (#561 round 2 S2)"
        )
    # (e2) continued — S5 sweep, recognised-token CONSEQUENCE pin (#561 fresh
    # round 7 S5): the checks above pin the TRIGGER ('begins with Fatal,
    # Significant, or Minor') but not the clause's own CONSEQUENCE — live-
    # verified that flipping "counts the entry at that recognised severity"
    # to "is recorded for narration only and the entry is scored 0" leaves
    # the trigger regex and the `annotated-second-pass-severity` flag name
    # both untouched.
    recognised_m = re.search(r"A recognised token.{0,150}", block, re.DOTALL)
    if not (recognised_m and "counts the entry at that recognised severity" in recognised_m.group(0)):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block's recognised-token rule does "
            "not carry its own CONSEQUENCE ('counts the entry at that recognised "
            "severity') within reach of the trigger phrase (#561 fresh round 7 "
            "S5: a rewrite that keeps the trigger phrase and flag name but flips "
            "the consequence to a not-counted reading is otherwise undetected)"
        )
    elif _negates("counts the entry at that recognised severity", recognised_m.group(0)):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block's recognised-token consequence "
            "NEGATES 'counts the entry at that recognised severity' instead of "
            "asserting it (#561 round 1 S1 polarity guard)"
        )
    if not re.search(r"matches NONE of the three", block):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block missing the explicit 'matches "
            "NONE of the three' scoping of the malformed-second-pass-entry default "
            "to a value that recognises none of Fatal/Significant/Minor (#561 round "
            "1 S3 / round 2 S2: the default must not also catch a recognised-but-"
            "annotated value)"
        )
    if not re.search(r"flags `malformed-second-pass-entry`", block):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block missing the "
            "'flags `malformed-second-pass-entry`' narration-log obligation for a "
            "malformed second-pass entry"
        )

    # (e2) continued — malformed-default CONSEQUENCE pin (#561 round 4 S2):
    # verified live that flipping "is counted as **Significant**" to "is NOT
    # counted at all (scored 0)" leaves the trigger phrase ("matches NONE of
    # the three") and the flag name ("flags `malformed-second-pass-entry`")
    # both untouched, so the checks above stay green on the flip — #561's
    # exact bug restored. Scoped tightly to the sentence around the trigger
    # phrase so `_negates` cannot misfire on an unrelated "Significant" token
    # elsewhere in the block.
    malformed_default_m = re.search(
        r"matches NONE of the three.{0,250}",
        block, re.DOTALL,
    )
    if not (malformed_default_m and "counted as **Significant**" in malformed_default_m.group(0)):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block does not state the "
            "malformed-second-pass-entry default's CONSEQUENCE as 'counted as "
            "**Significant**' (#561 round 4 S2: verified live that flipping this "
            "consequence to 'NOT counted at all (scored 0)' — #561's exact bug — "
            "leaves the trigger phrase and flag name both untouched and the full "
            "suite green)"
        )
    elif _negates("counted as", malformed_default_m.group(0)):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block NEGATES the malformed-default "
            "consequence ('counted as **Significant**') instead of asserting it "
            "(#561 round 1 S1 polarity guard)"
        )

    # (e2) continued — S3 Minor-population-join structural guard (#561 fresh
    # round 5 S3): round 4's S3 fix added a Minor-join clause naming three
    # sinks (`round-N-score.md`'s Minor count, `MinorTrajectory`/
    # `minor_trajectory`, `m_exit`) as INV-561-1's seventh declared consumer,
    # but no assertion in check_skill() ever referenced it — deleting the
    # whole clause left the full 86-suite green.
    minor_join_m = re.search(r"Minor population join.{0,500}", block, re.DOTALL)
    if not (
        minor_join_m
        and "round-N-score.md" in minor_join_m.group(0)
        and "Minor count" in minor_join_m.group(0)
        and re.search(r"MinorTrajectory|minor_trajectory", minor_join_m.group(0))
        and "m_exit" in minor_join_m.group(0)
        and "join the round's Minor population" in minor_join_m.group(0)
    ):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block missing (or incomplete) the "
            "Minor-population-join clause pinning its three named sinks "
            "(`round-N-score.md`'s Minor count, `MinorTrajectory`/"
            "`minor_trajectory`, `m_exit`) — #561 fresh round 5 S3: INV-561-1's "
            "seventh declared consumer had zero structural guard"
        )
    elif _negates("join the round's Minor population", minor_join_m.group(0)):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block NEGATES the Minor-"
            "population-join clause instead of asserting it (#561 round 1 S1 "
            "polarity guard)"
        )

    # (f) de-dup clause, inside the block.
    if not re.search(r"counts\s+ONCE", block):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block missing the de-dup clause's "
            "'counts ONCE' rule"
        )
    if "higher of the two severities" not in block:
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block missing the de-dup clause's "
            "'higher of the two severities' rule"
        )
    # (f) continued — S5 sweep, de-dup ADJACENCY pin (#561 fresh round 7 S5):
    # the two checks above pin 'counts ONCE' and 'higher of the two
    # severities' as independent substrings anywhere in the block — live-
    # verified that inserting "**per section**" between them ("counts ONCE
    # **per section**, at the higher of the two severities") leaves both
    # substrings intact while turning the de-dup guard into a double-counting
    # channel. Require the exact adjacency instead.
    if not re.search(r"counts ONCE,\s*at the higher of the two severities", block):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block's de-dup clause does not "
            "state 'counts ONCE, at the higher of the two severities' as one "
            "adjacent phrase (#561 fresh round 7 S5: a decoy insertion like "
            "'counts ONCE **per section**, at the higher of the two "
            "severities' leaves both substrings intact while turning the "
            "guard into a double-counting channel)"
        )

    # (g) Red Flags vigilance entry naming this failure mode.
    if _RED_FLAG_PIN not in text:
        errs.append(
            "SKILL: Red Flags list is missing the #561 vigilance bullet "
            f"(expected phrase: {_RED_FLAG_PIN!r})"
        )

    # (h) look-harder confirm/demote predicate — the fourth consumer (round 2 F1)
    # — carries the same population qualifier on BOTH branches. Scoped to a
    # window after each branch's own trigger phrase, not the whole file.
    # NOT re.DOTALL: each branch is a single list-item line in the source, so a
    # `.` window cannot cross into the OTHER branch's own qualifier on the next line.
    confirm_m = re.search(r"look-harder returns \*\*0F/0S\*\*.{0,450}", text)
    if not (confirm_m and "same population" in confirm_m.group(0)):
        errs.append(
            "SKILL: look-harder's 0F/0S confirm branch does not carry the 'same "
            "population' qualifier tying it to the Score source rule's population "
            "(#561 round 2 F1: the fourth consumer)"
        )
    elif _negates("same population", confirm_m.group(0)):
        errs.append(
            "SKILL: look-harder's 0F/0S confirm branch NEGATES the 'same population' "
            "qualifier (e.g. 'NOT the same population') instead of asserting it "
            "(#561 round 1 S1)"
        )
    # (h) continued — discrepancy-exception qualifier on the confirm branch
    # (#561 round 3 F2): the population qualifier alone is not enough — a
    # look-harder receipt whose own declared SEVERITY-COUNTS exceeds its own
    # counted population must not confirm. The correct assertion is inherently
    # negative ("has NOT fired"), so it is pinned as a literal presence check
    # (deletion/reword-sensitive), the same way (m) pins 'NOT candidate-clean'
    # — a plain _negates() guard would misfire on this baseline's own 'not'.
    if not (confirm_m and "discrepancy exception at step 7 has not fired" in confirm_m.group(0)):
        errs.append(
            "SKILL: look-harder's 0F/0S confirm branch does not carry the "
            "SEVERITY-COUNTS discrepancy-exception qualifier ('... has not fired on "
            "look-harder's own receipt') — routing a real Fatal through look-harder "
            "must not confirm just because look-harder's own count agrees with its "
            "declared total being non-discrepant (#561 round 3 F2)"
        )
    demote_m = re.search(r"look-harder returns \*\*Fatal/Significant\*\*.{0,450}", text)
    if not (demote_m and "same population" in demote_m.group(0)):
        errs.append(
            "SKILL: look-harder's Fatal/Significant demote branch does not carry the "
            "'same population' qualifier tying it to the Score source rule's "
            "population (#561 round 2 F1: the fourth consumer)"
        )
    elif _negates("same population", demote_m.group(0)):
        errs.append(
            "SKILL: look-harder's Fatal/Significant demote branch NEGATES the 'same "
            "population' qualifier (e.g. 'NOT the same population') instead of "
            "asserting it (#561 round 1 S1)"
        )
    # (h) continued — discrepancy-exception qualifier on the demote branch
    # (#561 round 3 F2): here the correct assertion IS positive ('has fired',
    # no built-in negation), so the same _negates() guard used by (m) applies
    # directly, anchored on 'fired' within the demote-branch window (the only
    # 'fired' token in this window is the one being pinned).
    if not (demote_m and "discrepancy exception at step 7 has fired" in demote_m.group(0)):
        errs.append(
            "SKILL: look-harder's Fatal/Significant demote branch does not carry the "
            "SEVERITY-COUNTS discrepancy-exception qualifier ('... has fired on "
            "look-harder's own receipt') as an alternative demotion trigger "
            "(#561 round 3 F2)"
        )
    elif _negates("fired", demote_m.group(0)):
        errs.append(
            "SKILL: look-harder's demote-branch discrepancy-exception qualifier "
            "NEGATES 'fired' (e.g. 'has NOT fired') instead of asserting it "
            "(#561 round 1 S1 polarity guard)"
        )

    # (i) step-5 candidate-clean predicate — a THIRD consumer INV-561-1 names
    # but which, unlike the look-harder branches, had no structural guard at
    # all until now (#561 round 3 S5). Same anchored-window shape as (h) —
    # NOT re.DOTALL, for the same reason: the predicate is a single paragraph
    # in the source, and an unwindowed `.` would risk reaching a DIFFERENT
    # consumer's qualifier on a later line.
    step5_m = re.search(r"zero Fatal and zero Significant issues.{0,300}", text)
    if not (step5_m and "same population" in step5_m.group(0)):
        errs.append(
            "SKILL: the step-5 candidate-clean predicate does not carry the 'same "
            "population' qualifier tying it to the Score source rule's population "
            "(#561 round 3 S5: a declared INV-561-1 consumer with no structural guard)"
        )
    elif _negates("same population", step5_m.group(0)):
        errs.append(
            "SKILL: the step-5 candidate-clean predicate NEGATES the 'same "
            "population' qualifier (e.g. 'NOT the same population') instead of "
            "asserting it (#561 round 1 S1)"
        )

    # (j) Exit Precedence slot #1 (Clean pass) — the fourth INV-561-1 consumer
    # with no structural guard at all until now (#561 round 3 S5). Same
    # NOT-re.DOTALL rationale as (i).
    slot1_m = re.search(r"1\.\s*\*\*Clean pass\*\*.{0,300}", text)
    if not (slot1_m and "same population" in slot1_m.group(0)):
        errs.append(
            "SKILL: Exit Precedence slot #1 (Clean pass) does not carry the 'same "
            "population' qualifier tying it to the Score source rule's population "
            "(#561 round 3 S5: a declared INV-561-1 consumer with no structural guard)"
        )
    elif _negates("same population", slot1_m.group(0)):
        errs.append(
            "SKILL: Exit Precedence slot #1 (Clean pass) NEGATES the 'same "
            "population' qualifier (e.g. 'NOT the same population') instead of "
            "asserting it (#561 round 1 S1)"
        )

    # (k) the `qg-score-population` convergence-log CONTRACT block names THIS
    # checker as its enforcer but nothing here ever asserted its content
    # (#561 round 4 S1) — pin the score_population value-set and its
    # key-presence semantics so the marker's attribution is true.
    pop_start = re.search(r"<!-- CONTRACT:qg-score-population:START.*?-->", text, re.DOTALL)
    pop_end = re.search(r"<!-- CONTRACT:qg-score-population:END.*?-->", text, re.DOTALL)
    if pop_start is None or pop_end is None or pop_end.start() < pop_start.start():
        errs.append(
            "SKILL: qg-score-population CONTRACT block not found "
            "(<!-- CONTRACT:qg-score-population:START --> … :END -->)"
        )
    else:
        pop_block = text[pop_start.end():pop_end.start()]
        if '"second-pass-inclusive" | "mixed" | absent' not in pop_block:
            errs.append(
                "SKILL: qg-score-population CONTRACT block missing the "
                '`"second-pass-inclusive" | "mixed" | absent` value-set pin '
                "(#561 round 1 SP1: `mixed` records an incomplete intra-run backfill)"
            )
        frag_m = re.search(r"Fragility-rate denominators.{0,400}", text)
        if not (frag_m and 'score_population == "second-pass-inclusive"' in frag_m.group(0)):
            errs.append(
                'SKILL: the fragility-rate denominator rule does not filter on '
                '`score_population == "second-pass-inclusive"` specifically '
                "(#561 round 2 S4: bare key-presence also pulls a `\"mixed\"` "
                "entry into the denominator, even though `\"mixed\"` is defined "
                "as 'not fully comparable')"
            )
        if "no `marker_version` bump" not in pop_block:
            errs.append(
                "SKILL: qg-score-population CONTRACT block missing the "
                "'no `marker_version` bump' key-presence-semantics pin"
            )

    # (k) continued — S6 Minor-population backfill extension (#561 fresh
    # round 8 S6): the intra-run backfill recounts ScoreTrajectory/MaxScore
    # on a mid-run population change, but round 4's S3 also widened the
    # Minor population, and until this fix the backfill was never extended
    # to it — MinorTrajectory/minor_trajectory and round-K-score.md's Minor
    # count silently kept narrow counts for rounds before the change and
    # widened counts after, which the #362 trajectory rule and the
    # stagnation judge's Minor-accumulation counter both read as a false
    # recurrence/decrease signal. Anchored on the intra-run backfill
    # paragraph itself so an in-place revert of either added clause is
    # caught, not just a deletion.
    # Window widened #561 fresh round 12 (M2: real headroom this time): the
    # S2 fix's durable score-comparable / non-comparable-reason clause
    # pushed 'Minor-accumulation counter not-satisfiable for the affected
    # rounds' to ~2543 chars from this anchor, measured live.
    backfill_m = re.search(r"\*\*intra-run\*\*.{0,3200}", text, re.DOTALL)
    if not (
        backfill_m
        and "recounting each round's Minor population" in backfill_m.group(0)
        and "`MinorTrajectory`/`minor_trajectory` and `round-K-score.md`'s Minor count" in backfill_m.group(0)
    ):
        errs.append(
            "SKILL: the intra-run backfill clause does not extend the "
            "ScoreTrajectory/MaxScore recount to the Minor population "
            "('recounting each round's Minor population ... "
            "MinorTrajectory`/`minor_trajectory` and `round-K-score.md`'s "
            "Minor count') (#561 fresh round 8 S6: without this, MinorTrajectory "
            "holds narrow counts before a mid-run population change and widened "
            "counts after, which the #362 trajectory rule and the stagnation "
            "judge's Minor-accumulation counter both read as a false signal)"
        )
    elif _negates("recounting each round's Minor population", backfill_m.group(0)):
        errs.append(
            "SKILL: the intra-run backfill's Minor-population extension NEGATES "
            "'recounting each round's Minor population' instead of asserting it "
            "(#561 round 1 S1 polarity guard)"
        )

    if not (
        backfill_m
        and "an incomplete Minor backfill is the same incompleteness" in backfill_m.group(0)
        and "makes the #362 trajectory rule" in backfill_m.group(0)
        and "Minor-accumulation counter not-satisfiable for the affected rounds" in backfill_m.group(0)
    ):
        errs.append(
            "SKILL: the intra-run backfill clause does not extend the "
            "not-satisfiable treatment to an incomplete Minor backfill "
            "('an incomplete Minor backfill is the same incompleteness ... "
            "makes the #362 trajectory rule ... and the stagnation judge's "
            "Minor-accumulation counter not-satisfiable for the affected "
            "rounds') (#561 fresh round 8 S6)"
        )
    elif _negates("makes the #362 trajectory rule", backfill_m.group(0)):
        errs.append(
            "SKILL: the intra-run backfill's Minor not-satisfiable extension "
            "NEGATES 'makes the #362 trajectory rule ... not-satisfiable' "
            "instead of asserting it (#561 round 1 S1 polarity guard)"
        )

    # S2 (#561 fresh round 12): the intra-run backfill's not-satisfiable
    # status must reach the Comparability gate through the SAME durable,
    # on-disk channel the discrepancy exception uses (`score-comparable:
    # false` in round-N-score.md) — before this fix, `score_population:
    # mixed` was the only record, and that key lives in the terminal
    # convergence-log entry only, which the Comparability gate never reads,
    # so a backfill-incomplete round's not-satisfiable status did not
    # survive a compaction recovery mid-run.
    if not (
        backfill_m
        and "have the backfill pass itself write `score-comparable: false` and `non-comparable-reason: incomplete-backfill`"
        in backfill_m.group(0)
    ):
        errs.append(
            "SKILL: the intra-run backfill clause does not have the backfill "
            "pass itself write `score-comparable: false` / "
            "`non-comparable-reason: incomplete-backfill` to the affected "
            "round's `round-N-score.md` — without this, `score_population: "
            "mixed` (a terminal-convergence-log-only field) is the only "
            "record of a backfill-incomplete round, and the Comparability "
            "gate never reads that key, so the round's not-satisfiable "
            "status does not survive a compaction recovery mid-run and gets "
            "silently treated as comparable (#561 fresh round 12 S2)"
        )
    elif _negates(
        "have the backfill pass itself write `score-comparable: false`",
        backfill_m.group(0),
    ):
        errs.append(
            "SKILL: the intra-run backfill's durable score-comparable write "
            "NEGATES itself instead of asserting it (#561 round 1 S1 "
            "polarity guard)"
        )
    # (l) Fatal count tracking (Stagnation Detection) — INV-561-1's fifth
    # declared consumer, with no structural guard at all until now (#561
    # round 2 S1: deleting or negating its "same population" sentence left
    # the full suite green). Same anchored-window shape as (h)/(i)/(j) — NOT
    # re.DOTALL, single-line paragraph in the source.
    fatal_count_m = re.search(r"Stagnation uses \*\*weighted scoring\*\*.{0,200}", text)
    if not (fatal_count_m and "same population" in fatal_count_m.group(0)):
        errs.append(
            "SKILL: the Fatal count tracking rule (Stagnation Detection) does not "
            "carry the 'same population' qualifier tying it to the Score source "
            "rule's population (#561 round 2 S1: INV-561-1's fifth declared "
            "consumer, with no structural guard at all)"
        )
    elif _negates("same population", fatal_count_m.group(0)):
        errs.append(
            "SKILL: the Fatal count tracking rule NEGATES the 'same population' "
            "qualifier (e.g. 'NOT the same population') instead of asserting it "
            "(#561 round 1 S1)"
        )

    # (m) SEVERITY-COUNTS discrepancy clause (Score source rule, step 7)
    # carries the directional exception (#561 round 2 F1): a declared
    # fatal+significant total EXCEEDING the orchestrator's own counted
    # population makes the round NOT candidate-clean. Anchored on the
    # pre-existing discrepancy clause's own trigger phrase — NOT re.DOTALL,
    # single-line paragraph in the source.
    discrepancy_m = re.search(r"flags the discrepancy.{0,700}", text)
    if not (
        discrepancy_m
        and "exceeds" in discrepancy_m.group(0)
        and "NOT candidate-clean" in discrepancy_m.group(0)
    ):
        errs.append(
            "SKILL: the SEVERITY-COUNTS discrepancy clause (Score source rule, "
            "step 7) does not carry the directional exception — a declared "
            "fatal+significant total EXCEEDING the orchestrator's own counted "
            "population must make the round NOT candidate-clean (#561 round 2 F1: "
            "the discrepancy signal was previously logged but never gated on)"
        )
    elif _negates("exceeds", discrepancy_m.group(0)):
        errs.append(
            "SKILL: the SEVERITY-COUNTS discrepancy exception NEGATES 'exceeds' "
            "(e.g. 'does not exceed') instead of asserting the directional "
            "trigger (#561 round 1 S1 polarity guard)"
        )

    # (m) continued — non-comparability clause (#561 round 3 F1): a
    # discrepancy-blocked round (and a discrepancy-demoted look-harder round)
    # must be marked score-comparable: false and excluded (not-satisfiable)
    # from the First-Pass progress check / Oscillation detection /
    # Sustained-regression comparison, or the loop's non-clean ⟹ score ≥ 1
    # invariant breaks and manufactures a false regression off the artificial
    # 0 floor a discrepancy-blocked round is pinned to. Anchored on the
    # clause's own heading.
    compat_m = re.search(r"Comparability of a discrepancy-blocked round.{0,900}", text)
    if not (
        compat_m
        and "score-comparable: false" in compat_m.group(0)
        and "not-satisfiable" in compat_m.group(0)
    ):
        errs.append(
            "SKILL: the SEVERITY-COUNTS discrepancy exception (Score source rule, "
            "step 7) does not mark a discrepancy-blocked round `score-comparable: "
            "false` and treat it as not-satisfiable for cross-round score "
            "comparisons (#561 round 3 F1: without this, a discrepancy-blocked "
            "round is simultaneously non-clean and weighted score 0, breaking "
            "non-clean ⟹ score ≥ 1 and manufacturing a false regression on the "
            "following round)"
        )
    elif _negates("score-comparable: false", compat_m.group(0)):
        errs.append(
            "SKILL: the discrepancy-blocked-round comparability clause NEGATES "
            "`score-comparable: false` instead of asserting it (#561 round 1 S1 "
            "polarity guard)"
        )

    # (m) continued — the First-Pass Check's own consumption of
    # score-comparable: false (#561 round 3 F1): the Comparability of a
    # discrepancy-blocked round clause above is not self-enforcing — the
    # Stagnation Detection section must independently exclude a
    # score-comparable: false round from its own comparison window.
    fp_compat_m = re.search(r"\*\*Comparability gate.{0,700}", text, re.DOTALL)
    if not (
        fp_compat_m
        and "score-comparable: false" in fp_compat_m.group(0)
        and "not-satisfiable" in fp_compat_m.group(0)
    ):
        errs.append(
            "SKILL: Stagnation Detection > First-Pass Check does not carry a "
            "'Comparability gate' excluding score-comparable: false rounds "
            "(not-satisfiable) from Progress / Oscillation / Sustained-regression "
            "comparisons (#561 round 3 F1)"
        )
    elif "draw neither a progress nor a regression conclusion" not in fp_compat_m.group(0):
        # (#561 fresh round 7 S5): the checks above pin only 'score-comparable:
        # false' and 'not-satisfiable', not the clause's own CONSEQUENCE — live-
        # verified that flipping "draw neither a progress nor a regression
        # conclusion" to "draw the ordinary progress/regression conclusion"
        # leaves both pinned tokens (each present elsewhere in the same
        # sentence) untouched and restores round 3's F1 bug.
        errs.append(
            "SKILL: the Comparability gate does not state its own CONSEQUENCE "
            "('draw neither a progress nor a regression conclusion') alongside "
            "'not-satisfiable' (#561 fresh round 7 S5: a rewrite that keeps "
            "'not-satisfiable' but flips this consequence to an ordinary "
            "progress/regression reading restores round 3's F1 bug undetected)"
        )

    # (m) continued — M7 crash-window default (#561 round 4 M7): a
    # discrepancy-demoted look-harder round's `score-comparable` write sits
    # outside the demotion crash-window protocol. Absent the carve-out below,
    # a crash between the demotion's Phase 2 flags write and the round's own
    # `round-N-score.md` write leaves `look-harder-fired-on-round: <N>`
    # populated with no `score-comparable` key, which the true-by-default
    # rule reads as comparable — resuming comparison across exactly the
    # boundary this rule exists to exclude.
    m7_m = re.search(r"Comparisons resume normally.{0,900}", text, re.DOTALL)
    if not (
        m7_m
        and "look-harder-fired-on-round" in m7_m.group(0)
        and re.search(r"read as `false`, not `true`", m7_m.group(0))
    ):
        errs.append(
            "SKILL: the Comparability gate's default-`true` rule does not carve "
            "out a round whose `round-N-flags.md` carries `look-harder-fired-on-"
            "round: <N>` — an absent `score-comparable` key there must be read as "
            "`false`, not `true` (#561 round 4 M7: otherwise a crash between the "
            "demotion's Phase 2 flags write and the round's score-file write "
            "silently reads as comparable across the boundary this gate exists to "
            "exclude)"
        )

    # (o) SP1 empty-work-order exception (#561 round 4 SP1): a discrepancy-
    # blocked round with an orchestrator count of 0F/0S has no actionable
    # findings — dispatching a fix agent against an empty work order is
    # reachable only through a wrongly-attributed no-op-fix escalation or a
    # fabricated cosmetic edit. The round must instead exit ESCALATED with its
    # own reason token, and that token must be a member of the verdict-marker
    # Reason enumeration and of the pre-threshold exit list (so it fires
    # regardless of `suppression_threshold`).
    empty_wo_m = re.search(r"Empty-work-order exception.{0,1900}", text, re.DOTALL)
    # (#561 fresh round 7 S2): a bare containment test for the shared fragment
    # "0 Fatal and 0 Significant" cannot distinguish SP1's own trigger from
    # the S5 Look-harder-path clause's copy of the same string a few hundred
    # characters later in the SAME 1900-char window — live-verified that
    # inverting SP1's trigger alone, leaving S5's clause untouched, still
    # passed the old containment check because S5's own occurrence satisfied
    # it. Pin SP1's FULL, clause-specific literal phrase instead — inherently
    # unique to SP1's own sentence, since S5's parallel sentence says
    # "look-harder's own counted population", never "the orchestrator's own
    # counted population".
    sp1_trigger = (
        "the directional exception above fires AND the orchestrator's own "
        "counted population is 0 Fatal and 0 Significant"
    )
    if not (
        empty_wo_m
        and sp1_trigger in empty_wo_m.group(0)
        and "does NOT route into the normal fix loop" in empty_wo_m.group(0)
        and "ESCALATED, Reason: severity-counts-discrepancy" in empty_wo_m.group(0)
    ):
        errs.append(
            "SKILL: the Score source rule's SEVERITY-COUNTS discrepancy exception "
            "does not carry an empty-work-order exception routing a 0F/0S "
            "orchestrator-count discrepancy-blocked round to "
            "`ESCALATED, Reason: severity-counts-discrepancy` instead of the "
            "normal fix loop, pinned by SP1's own clause-specific trigger "
            "phrase rather than a fragment shared with the S5 clause below "
            "(#561 round 4 SP1; anchor tightened #561 fresh round 7 S2)"
        )
    elif _negates(
        "the orchestrator's own counted population is 0 Fatal and 0 Significant",
        empty_wo_m.group(0),
    ):
        errs.append(
            "SKILL: the Empty-work-order exception's SP1 trigger NEGATES 'the "
            "orchestrator's own counted population is 0 Fatal and 0 "
            "Significant' instead of asserting it (#561 round 1 S1 polarity "
            "guard; anchor scoped to SP1's own clause #561 fresh round 7 S2)"
        )

    # (o) continued — S5 look-harder-path extension (#561 fresh round 5 S5):
    # SP1's empty-work-order exception was scoped to step-5 routing only, not
    # to the look-harder demote branch, which is a separate entry point that
    # reaches the same state (an empty work order) through a competing
    # imperative ("MUST execute the following three writes"). Without this
    # extension, a discrepancy-demoted look-harder round with a 0F/0S own
    # count would still proceed into the fix loop against an empty file.
    if not (
        empty_wo_m
        and "Look-harder path" in empty_wo_m.group(0)
        and "look-harder's own receipt" in empty_wo_m.group(0)
        and "look-harder's own counted population is 0 Fatal and 0 Significant" in empty_wo_m.group(0)
        and "demotion protocol's three writes" in empty_wo_m.group(0)
    ):
        errs.append(
            "SKILL: the Empty-work-order exception does not extend to the "
            "look-harder demotion path — a discrepancy-demoted look-harder round "
            "with a 0F/0S own count must still perform the demotion protocol's "
            "three writes (so the artifacts stay legible) and then exit "
            "`ESCALATED, Reason: severity-counts-discrepancy`, not proceed into "
            "the fix loop against an empty work order (#561 fresh round 5 S5)"
        )
    elif _negates(
        "look-harder's own counted population is 0 Fatal and 0 Significant",
        empty_wo_m.group(0),
    ):
        errs.append(
            "SKILL: the Empty-work-order exception's S5 Look-harder-path "
            "trigger NEGATES 'look-harder's own counted population is 0 "
            "Fatal and 0 Significant' instead of asserting it (#561 round 1 "
            "S1 polarity guard; #561 fresh round 7 S2)"
        )
    reason_line_m = re.search(r"^Reason:.*$", text, re.MULTILINE)
    if not (reason_line_m and "severity-counts-discrepancy" in reason_line_m.group(0)):
        errs.append(
            "SKILL: the verdict-marker `Reason:` enumeration does not carry the "
            "`severity-counts-discrepancy` token (#561 round 4 SP1)"
        )
    if not re.search(r"pre-threshold exits are:.{0,700}severity-counts-discrepancy", text, re.DOTALL):
        errs.append(
            "SKILL: the pre-threshold exit list does not include the "
            "`severity-counts-discrepancy` empty-work-order exit — without it, "
            "the exit would be read as gated by `suppression_threshold` instead "
            "of firing unconditionally (#561 round 4 SP1)"
        )

    # (o) continued — S4 Exit Precedence slot + Reason-token-mapping bullet
    # (#561 fresh round 5 S4): the `severity-counts-discrepancy` terminal exit
    # is a member of the verdict-marker Reason enum and the pre-threshold exit
    # list (both pinned above), but was absent from Exit Precedence's slot
    # list and the Reason token mapping — so on co-fire with a no-op-fix (round
    # N's fix agent returns a byte-identical artifact while round N+1's
    # reviewer's own findings file has zero counted entries against a nonzero
    # declared SEVERITY-COUNTS total) the unenumerated exit does not compete in
    # precedence and resolves to the wrongly-attributed `no-op-fix` escalation
    # this exception exists to prevent.
    precedence_m = re.search(r"### Exit Precedence.*?## Red Flags", text, re.DOTALL)
    precedence_scope = precedence_m.group(0) if precedence_m else ""
    sc_slot_idx = precedence_scope.find("severity-counts-discrepancy")
    noop_slot_idx = precedence_scope.find("No-op fix ESCALATED")
    if sc_slot_idx == -1:
        errs.append(
            "SKILL: Exit Precedence does not enumerate a `severity-counts-"
            "discrepancy` slot (#561 fresh round 5 S4: an unenumerated "
            "discrepancy exit does not compete in precedence, and co-fire with "
            "no-op-fix resolves to the wrongly-attributed `no-op-fix` "
            "escalation the empty-work-order exception exists to prevent)"
        )
    elif noop_slot_idx != -1 and sc_slot_idx > noop_slot_idx:
        errs.append(
            "SKILL: Exit Precedence's `severity-counts-discrepancy` slot must "
            "outrank `No-op fix ESCALATED` (#561 fresh round 5 S4: the "
            "discrepancy is a review-side condition that makes a co-firing "
            "fix-side no-op unattributable)"
        )
    if not re.search(r"`severity-counts-discrepancy` — Verdict: ESCALATED", text):
        errs.append(
            "SKILL: the Reason token mapping list is missing the "
            "`severity-counts-discrepancy` bullet (#561 fresh round 5 S4: the "
            "canonical Verdict↔Reason contract carries a bullet for every "
            "other Reason token, including the thirteen pre-existing ones, but "
            "not this one)"
        )

    # (o) continued — S1(a) consequence pin for Exit Precedence slot #4 (#561
    # fresh round 6 S1(a)): the assertions above pin only the slot's TOKEN and
    # ORDERING, not its own verdict CONSEQUENCE. Live-verified that replacing
    # slot #4's body with "this condition is recorded ... for telemetry and
    # does not itself select a verdict; the round continues into the normal
    # fix loop and whichever lower slot fires governs the verdict" — keeping
    # the slot's token and position intact — restores S4's exact bug (a slot
    # that declines to select a verdict is functionally identical to no slot;
    # the co-firing no-op wins) and stays green under the assertions above alone.
    if sc_slot_idx != -1:
        slot4_next = precedence_scope.find("\n5.", sc_slot_idx)
        slot4_scope = (
            precedence_scope[sc_slot_idx:slot4_next]
            if slot4_next != -1
            else precedence_scope[sc_slot_idx:sc_slot_idx + 600]
        )
        if "Verdict: `ESCALATED`, reason `severity-counts-discrepancy`" not in slot4_scope:
            errs.append(
                "SKILL: Exit Precedence slot #4's own text does not carry its "
                "verdict CONSEQUENCE ('Verdict: `ESCALATED`, reason "
                "`severity-counts-discrepancy`') — a slot pinned by token and "
                "position alone, but whose own text declines to select a "
                "verdict, is functionally identical to no slot at all (#561 "
                "fresh round 6 S1(a))"
            )
        elif _negates("ESCALATED", slot4_scope):
            errs.append(
                "SKILL: Exit Precedence slot #4's verdict consequence NEGATES "
                "'ESCALATED' instead of asserting it (#561 round 1 S1 polarity "
                "guard)"
            )

    # (p) F2 pointer-or-complete (#561 round 4 F2): the entry/severity rule is
    # restated in the anti-rationalization table row (:202) and INV-561-1
    # (:1397) in addition to the CONTRACT block and red-team-prompt.md. Round
    # 3's normalization + boundary-character-list + fence-parity fixes landed
    # in only two of those four homes, leaving the other two stating a STALE
    # pre-fix parse that no checker read. Require each restatement site to
    # EITHER be pointer-only (name the population, then point at the CONTRACT
    # block, carrying none of the three stale-prone detail tokens) OR, if a
    # restatement is kept, carry all three detail tokens so a future in-place
    # fix landing in only one of four homes fails the suite.
    def _pointer_or_complete(scope: str, label: str) -> str | None:
        has_pointer = (
            "qg-score-second-pass-population" in scope and "CONTRACT block" in scope
        )
        detail_tokens = (
            "markdown emphasis markers",
            # (#561 fresh round 6 S2): "immediately followed" alone is a loose
            # proxy any unrelated sentence can satisfy — live-verified that
            # replacing the actual boundary-character-set enumeration with "or
            # by any other character whatsoever" leaves this bare fragment
            # intact (it sits in the untouched lead-in clause). Pinning the
            # full charset-enumeration substring — byte-identical between
            # SKILL.md and red-team-prompt.md — requires the enumeration
            # itself to survive, not just its introduction.
            "immediately followed by end-of-line, or by one of `(`, `[`, `,`, `.`, `:`, `;`",
            "ODD number of triple-backtick delimiters",
        )
        present = [tok in scope for tok in detail_tokens]
        has_all_details = all(present)
        # (#561 fresh round 5 S2): the old `has_pointer or has_all_details`
        # short-circuited on the pointer alone, so a pointer site could carry a
        # PARTIAL, contradictory restatement beside its pointer — worse than an
        # incomplete restatement alone, since a reader resolves the conflict in
        # favour of the nearer text. `has_partial_details` closes that gap: a
        # pointer is only clean when it carries NONE of the three detail tokens.
        has_partial_details = any(present) and not has_all_details
        if has_all_details:
            return None
        if has_pointer and not has_partial_details:
            return None
        if has_pointer and has_partial_details:
            return (
                f"SKILL: {label} carries a CONTRACT-block pointer alongside a "
                "PARTIAL restatement (#561 fresh round 5 S2: at least one, but "
                "not all three, of the stale-prone detail tokens is present "
                "beside the pointer — a contradictory or incomplete restatement "
                "next to a pointer is worse than an incomplete restatement "
                "alone, since a reader resolves the conflict in favour of the "
                "nearer text)"
            )
        return (
            f"SKILL: {label} neither points at the `qg-score-second-pass-"
            "population` CONTRACT block nor carries the full normalization + "
            "boundary-character-list + fence-parity detail set (#561 round 4 F2: "
            "a restatement missing even one of those tokens can go stale the next "
            "time the CONTRACT block's parse rule changes, exactly as round 3's "
            "fixes did here)"
        )

    antirat_m = re.search(r"The Fatal is only in the second-pass section, the real count is zero\.[^\n]*", text)
    if antirat_m is None:
        errs.append(
            "SKILL: anti-rationalization table row for the second-pass-Fatal "
            "rationalization ('The Fatal is only in the second-pass section...') "
            "not found (#561 round 4 F2)"
        )
    else:
        err = _pointer_or_complete(antirat_m.group(0), "the anti-rationalization row (:202)")
        if err:
            errs.append(err)

    invrow_m = re.search(r"\| INV-561-1 \|[^\n]*", text)
    if invrow_m is None:
        errs.append("SKILL: INV-561-1 invariant-table row not found (#561 round 4 F2)")
    else:
        err = _pointer_or_complete(invrow_m.group(0), "the INV-561-1 row (:1397)")
        if err:
            errs.append(err)

        # S4 (#561 fresh round 9): the Minor-sink sub-list was short by one
        # (three sinks named, vs. the four the Minor population join clause
        # above actually defines — round 8's M3 fourth sink was never
        # back-ported here), and the census omitted the round-ledger site
        # (`red-team/SKILL.md`'s `Total findings:` line, #561 fresh round 7
        # M6) as a consumer entirely, though it meets INV-561-1's own
        # membership test. Pin the sink list itself, not just the count
        # word, so join/invariant drift trips the suite going forward.
        if not (
            "round-N-score.md" in invrow_m.group(0)
            and re.search(r"MinorTrajectory|minor_trajectory", invrow_m.group(0))
            and "m_exit" in invrow_m.group(0)
            and "round-ledger" in invrow_m.group(0)
            and re.search(r"Total findings: N \(F: x, S: y, M: z\)", invrow_m.group(0))
            and "twelve consumers total" in invrow_m.group(0)
        ):
            errs.append(
                "SKILL: INV-561-1 row's Minor-sink sub-list and/or consumer "
                "census is stale (#561 fresh round 9 S4): must name all FOUR "
                "Minor sinks (`round-N-score.md`'s Minor count, "
                "`MinorTrajectory`/`minor_trajectory`, `m_exit`, and "
                "`red-team/SKILL.md`'s round-ledger Minor count) and count "
                "TWELVE consumers total, including the round-ledger site "
                "itself as a consumer"
            )

    # (n) fenced-code-block / blockquote exclusion (#561 round 2 S3), parallel
    # to the existing mid-sentence/quoted-occurrence assertion (e1): a marker
    # line inside a fenced code block or beginning with a blockquote marker
    # is never an entry-opening line, regardless of what follows.
    if not re.search(r"inside a fenced code block", block):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block missing the fenced-code-block "
            "exclusion clause (#561 round 2 S3: a marker line inside a fenced "
            "code block satisfies the line-anchored entry definition exactly, "
            "since 'first non-whitespace characters of a line' does not by "
            "itself exclude fenced content)"
        )
    if not re.search(r"beginning with a blockquote marker", block):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block missing the blockquote-marker "
            "exclusion clause (#561 round 2 S3)"
        )

    # (n) continued — S5 sweep, fenced-block/blockquote CONSEQUENCE pin (#561
    # fresh round 7 S5): the two checks above pin only the TRIGGER phrases
    # ("inside a fenced code block" / "beginning with a blockquote marker"),
    # not the clause's own CONSEQUENCE — live-verified that flipping "is
    # never an entry-opening line" to "is treated as an ordinary
    # entry-opening line, exactly like any other line" leaves both trigger
    # phrases untouched and restores round 2's S3 bug.
    fence_bq_m = re.search(r"beginning with a blockquote marker.{0,120}", block, re.DOTALL)
    if not (fence_bq_m and "is never an entry-opening line" in fence_bq_m.group(0)):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block's fenced-code-block/"
            "blockquote exclusion does not carry its own CONSEQUENCE ('is "
            "never an entry-opening line') within reach of its trigger "
            "phrases (#561 fresh round 7 S5: a rewrite that keeps both "
            "trigger phrases but flips the consequence to an ordinary-entry "
            "reading restores round 2's S3 bug undetected)"
        )
    elif _negates("is never an entry-opening line", fence_bq_m.group(0)):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block's fenced-code-block/"
            "blockquote consequence NEGATES 'is never an entry-opening line' "
            "instead of asserting it (#561 round 1 S1 polarity guard)"
        )

    # (n) continued — fence-parity fail-loud clause (#561 round 3 S3): the
    # fenced-code-block exclusion above is fail-open on an odd number of
    # triple-backtick delimiters or an unclosed fence — one stray or unclosed
    # triple-backtick before a run of entries would otherwise silently zero
    # every subsequent second-pass entry (#561's exact bug, reopened).
    if not re.search(r"ODD number of triple-backtick delimiters", block):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block missing the fence-parity "
            "fail-loud clause ('ODD number of triple-backtick delimiters ... the "
            "fenced-code-block exclusion does NOT apply') — #561 round 3 S3: a "
            "single stray or unclosed triple-backtick before a run of entries "
            "must not silently zero every entry that follows it"
        )
    elif _negates("ODD number of triple-backtick delimiters", block):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block NEGATES the fence-parity "
            "fail-loud trigger instead of asserting it (#561 round 1 S1 polarity "
            "guard)"
        )
    if not re.search(r"flags `malformed-second-pass-fencing`", block):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block missing the "
            "'flags `malformed-second-pass-fencing`' narration-log obligation "
            "(#561 round 3 S3)"
        )

    # (n) continued — fence-parity CONSEQUENCE pin (#561 round 4 S2): verified
    # live that flipping "the fenced-code-block exclusion does NOT apply ...
    # every ... marker ... counts, fence or no fence" to "the remainder of the
    # section is treated as entirely fenced and counts nothing" leaves the
    # trigger phrase ("ODD number of triple-backtick delimiters") and the flag
    # name ("flags `malformed-second-pass-fencing`") both untouched, and trips
    # no `_negates` token (the flip contains no not/never/excluding/except/
    # ignor* token) — round 3 S3's bug restored verbatim. Scoped to the text
    # strictly AFTER "does NOT apply" so `_negates` cannot misfire on the
    # correct baseline's own "NOT".
    fence_consequence_m = re.search(r"ODD number of triple-backtick delimiters.{0,250}", block, re.DOTALL)
    apply_idx = block.find("does NOT apply", fence_consequence_m.start()) if fence_consequence_m else -1
    if apply_idx == -1:
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block does not state the fence-parity "
            "consequence as 'does NOT apply' (#561 round 4 S2: verified live that "
            "flipping this consequence to 'is treated as entirely fenced and counts "
            "nothing' — round 3 S3's bug restored — leaves the trigger phrase and "
            "flag name both untouched and trips no negation token)"
        )
    else:
        after_scope = block[apply_idx + len("does NOT apply"):apply_idx + len("does NOT apply") + 300]
        if not re.search(r"every.{0,80}marker.{0,80}counts", after_scope, re.DOTALL):
            errs.append(
                f"SKILL: {CONTRACT_NAME} CONTRACT block's fence-parity clause does "
                "not state the consequence that every line-initial marker in the "
                "section counts once the exclusion no longer applies (#561 round 4 S2)"
            )
        elif _negates("counts", after_scope):
            errs.append(
                f"SKILL: {CONTRACT_NAME} CONTRACT block's fence-parity consequence "
                "NEGATES 'counts' (e.g. 'does not count') instead of asserting it "
                "(#561 round 1 S1 polarity guard)"
            )

    # (n) continued — S1(b) list-marker stripping CONSEQUENCE pin (#561 fresh
    # round 6 S1(b)): the (n)-family assertions above pin only the TRIGGER
    # phrase ("strip an optional leading list marker"), not its own positive
    # CONSEQUENCE. `_negates` only looks BACKWARDS from an anchor, so it does
    # not guard a rewrite of the clause's second half. Live-verified that
    # flipping "still opens (or carries) an entry under this rule" to "for
    # READABILITY ONLY; a list-bulleted line ... is still NOT an entry and
    # scores 0" reverts SP2 in place while leaving the trigger phrase intact.
    list_marker_m = re.search(r"strip an optional leading list marker.{0,300}", block, re.DOTALL)
    if not (list_marker_m and "still opens (or carries) an entry" in list_marker_m.group(0)):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block's list-marker stripping "
            "clause does not carry its own positive CONSEQUENCE ('still opens "
            "(or carries) an entry under this rule') within reach of its "
            "trigger phrase (#561 fresh round 6 S1(b): a rewrite that keeps "
            "'strip an optional leading list marker' but flips the second half "
            "to a NOT-an-entry consequence is otherwise undetected)"
        )
    elif list_marker_m and _negates("still opens (or carries) an entry", list_marker_m.group(0)):
        errs.append(
            f"SKILL: {CONTRACT_NAME} CONTRACT block's list-marker stripping "
            "consequence NEGATES 'still opens (or carries) an entry' instead "
            "of asserting it (#561 round 1 S1 polarity guard)"
        )

    # (q-cont) S5 three-branch write-ordering enumeration (#561 fresh round 6
    # S5, same root cause as F1): the Phase 2 paragraph's "Phase 2 is never
    # the round's last flags write" universal was a two-branch statement that
    # round 5's S5 invalidated by adding a third branch (the discrepancy
    # exception's Look-harder path) on which Phase 2 IS the last write and
    # Phase 3 never runs. Pin the third branch alongside the two-branch text.
    phase2_m = re.search(r"Phase 2 is never the round's last flags write.{0,900}", text, re.DOTALL)
    if not (
        phase2_m
        and "Third branch" in phase2_m.group(0)
        and "Phase 2 IS the round's last flags write" in phase2_m.group(0)
        and "Phase 3 never runs on this branch" in phase2_m.group(0)
    ):
        errs.append(
            "SKILL: the write-ordering protocol's Phase 2 paragraph does not "
            "enumerate the third branch (the discrepancy exception's "
            "Look-harder path) on which Phase 2 IS the round's last flags "
            "write and Phase 3 never runs (#561 fresh round 6 S5: round 5's "
            "S5 invalidated the pre-existing two-branch universal by adding "
            "this branch, same root cause as F1)"
        )

    # (r) S3 m_exit DEFINITION-SITE population qualifier (#561 fresh round 6
    # S3): INV-561-1's seventh consumer, `m_exit`, was widened in the CONTRACT
    # block's Minor population join clause above but not at ITS OWN defining
    # site — `## Minor Issue Handling > Clean-Pass Minor Advisory (#362)`'s
    # `density` bullet, which is OUTSIDE this CONTRACT block. No checker
    # asserted the definition site before this. Anchored on the bullet's own
    # stable lead-in phrase, NOT re.DOTALL scoped narrowly (single bullet).
    # (#561 fresh round 7 S3): round 6's fix widened only the FIRST operand
    # (round-R-findings.md's Minors) of the union — the SECOND operand
    # (round-R-look-harder.md's Minors) is live only on the confirmed
    # clean-exit case, which is the only exit on which m_exit is computed at
    # all, so an under-count there is not a corner case. Widened window to
    # cover both operands; require the qualifier phrase to appear BOTH before
    # AND after the `round-R-look-harder.md` mention, not merely once
    # anywhere in the window (a single occurrence before the mention would
    # satisfy the old bare-presence check while leaving the second operand
    # unqualified).
    m_exit_m = re.search(r"`m_exit` is the clean exit round's Minor count.{0,950}", text, re.DOTALL)
    if not (
        m_exit_m
        and "Minor population join" in m_exit_m.group(0)
    ):
        errs.append(
            "SKILL: the Clean-Pass Minor Advisory's `m_exit` DEFINITION site "
            "(`## Minor Issue Handling > Clean-Pass Minor Advisory`, the "
            "`density` bullet) does not carry the population qualifier tying "
            "it to the Score source rule's Minor population join, step 7 — "
            "unlike every other INV-561-1 consumer, this one was widened "
            "inside the CONTRACT block's cross-reference but not at its own "
            "defining site (#561 fresh round 6 S3)"
        )
    else:
        m_exit_scope = m_exit_m.group(0)
        _qualifier = "Minor`-first-token entries under `### Second Pass Findings`"
        lh_idx = m_exit_scope.find("round-R-look-harder.md")
        first_idx = m_exit_scope.find(_qualifier)
        second_idx = m_exit_scope.find(_qualifier, first_idx + 1) if first_idx != -1 else -1
        if not (
            lh_idx != -1
            and first_idx != -1 and first_idx < lh_idx
            and second_idx != -1 and second_idx > lh_idx
        ):
            errs.append(
                "SKILL: the `m_exit` DEFINITION site's population qualifier is "
                "attached to only ONE operand of the Minor union — round 6's "
                "S3 fix widened round-R-findings.md's operand but "
                "round-R-look-harder.md's operand (the operand live on the "
                "confirmed clean-exit case, the only exit m_exit is computed "
                "on) needs the identical site-local qualifier for the "
                "identical reason (#561 fresh round 7 S3)"
            )
        elif _negates("Minor population join", m_exit_scope):
            errs.append(
                "SKILL: the `m_exit` definition site's population qualifier "
                "NEGATES the Minor population join reference instead of "
                "asserting it (#561 round 1 S1 polarity guard)"
            )

    # (s) F1/S5 terminal-sentinel consequence pin (#561 fresh round 6 F1/S5):
    # round 5's S5 made the Empty-work-order exception's Look-harder path
    # TERMINAL, but the demote branch's own round-closing text ("the terminal
    # sentinel round-N-complete.md is NOT written") was not carved out for it,
    # and round-N-complete.md's own contract makes that decisive: its absence
    # means the round must be DISCARDED on recovery. Live-verified: without
    # the carve-out, compaction recovery reads a completed ESCALATED gate as
    # an in-progress round, discards the demotion's evidence, and resumes
    # into the exact empty-work-order fix dispatch SP1/S5 exist to prevent.
    # Pinned at BOTH sites — the demote-branch sentinel sentence and the S5
    # clause's own paragraph — since #561's own history shows a fix landing
    # in only one of several homes goes stale at the other.
    sentinel_m = re.search(r"terminal sentinel `round-N-complete\.md` is NOT written.{0,700}", text, re.DOTALL)
    if not (
        sentinel_m
        and "discrepancy exception's Look-harder path" in sentinel_m.group(0)
        and "IS terminal" in sentinel_m.group(0)
        and "MUST" in sentinel_m.group(0)
        and "terminal: ESCALATED" in sentinel_m.group(0)
    ):
        errs.append(
            "SKILL: the demote branch's 'terminal sentinel is NOT written' "
            "sentence does not carve out the Empty-work-order exception's "
            "Look-harder path — on that path the round IS terminal and "
            "`round-N-complete.md` MUST be written with `terminal: ESCALATED` "
            "(#561 fresh round 6 F1: without this carve-out, recovery reads a "
            "completed ESCALATED gate as in-progress and discards the "
            "demotion's evidence)"
        )
    s5_sentinel_m = re.search(r"Look-harder path \(#561 fresh round 5 S5\)\..{0,900}", text, re.DOTALL)
    if not (
        s5_sentinel_m
        and "round-N-complete.md" in s5_sentinel_m.group(0)
        and "terminal: ESCALATED" in s5_sentinel_m.group(0)
    ):
        errs.append(
            "SKILL: the S5 Look-harder path clause's own paragraph does not "
            "restate the terminal-sentinel obligation ('round-N-complete.md "
            "MUST be written with terminal: ESCALATED') — mirrored at its own "
            "site, not only at the demote branch's sentinel sentence (#561 "
            "fresh round 6 F1)"
        )

    return errs


def _read(path: pathlib.Path, errs: list[str]) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as err:
        errs.append(f"{path} missing or unreadable: {err}")
        return None


# A minimal fixture carrying every pinned phrase — the positive control for
# --selftest. If check_skill reports any error on this, the checker is broken.
_GOOD_FIXTURE = """
The weighted score is computed by the orchestrator counting the cited findings
file's `### Fatal Challenges` / `### Significant Challenges` sections, plus
any Fatal/Significant-severity entries under `### Second Pass Findings`.
<!-- CONTRACT:qg-score-second-pass-population:START -->
Widening this population does not weaken un-spoofability: the orchestrator
still counts from the cited artifact's on-disk text, not from a declared
number. Section location: the four sections this parse reads — `### Fatal Challenges`, `### Significant Challenges`, `### Second Pass Findings`, `### Minor Observations` — are already correctly located; that location step is itself a parse, not a given. Each section's **start** is the first `###`-level heading line matching that exact heading text which is itself neither inside a fenced code block nor prefixed by a blockquote marker. This is the earliest occurrence of such a heading line in the file: a heading line matching later in the file never overrides an earlier one as the section's start. Scope: this location step applies to the bytes of the cited findings file itself; a findings file quoted inside another document — including an eval prompt — is parsed as that file's own content, not as the enclosing document's. A section's **end** is the next `###`-level heading line that is itself neither inside a fenced code block nor prefixed by a blockquote marker; when none follows, the section extends to the end of the cited file. Zero-match rule: if the matching-heading count for any section is zero, the fallback triggers on this OBSERVABLE condition itself, not on a diagnosis of why it is zero (a fence-parity defect elsewhere in the file is one cause; a section whose only matching heading sits inside an otherwise-BALANCED, CLOSED fence is another), the fence exclusion does NOT apply at the heading level either — for both the start and end predicates of that section, raw-heading location end-to-end — re-locate over the raw heading lines, flag `malformed-second-pass-sectioning`, and never treat "not found" as "empty". If no heading line matching that section's text exists in the file at all, even under this raw-heading fallback, the orchestrator flags `missing-second-pass-section` in the narration log rather than silently treating the section as present-but-empty; this default is narration-only, like its siblings, and does not itself change the verdict. If more than one such heading matches after that exclusion, flag `malformed-second-pass-sectioning` and counts the **union** of all matching sections' entries — de-duplicated by entry identity where the union itself produces a duplicate — rather than any single one of them. A Second-Pass entry carries a line whose first non-whitespace characters are `**Finding:**` and/or a line whose first non-whitespace characters are `**Severity:**`. An entry **begins** at the first line-initial `**Finding:**` or `**Severity:**` marker and **extends** to the line before the next `####` heading or the next line-initial `**Finding:**` marker **that is not itself inside a fenced code block or prefixed by a blockquote marker (`> `)**, whichever comes first, or to the end of the section; a `**Severity:**` line inside an already-open entry is that entry's own severity line and does not open a second entry. A mid-sentence or quoted occurrence of either marker string does not make surrounding prose an entry. Before testing either marker, strip an optional leading list marker (`-`, `*`, `+`, or `<digits>.` followed by whitespace); a list-bulleted line such as `- **Severity:** Fatal` still opens (or carries) an entry under this rule. A line inside a fenced code block or a line beginning with a blockquote marker is never an entry-opening line either — the blockquote marker `> ` is a distinct exclusion, not a stripped prefix. If `### Second Pass Findings` contains an ODD number of triple-backtick delimiters, or a fence left open at the section boundary, the fenced-code-block exclusion does NOT apply anywhere in the section: every line-initial marker in the section counts, fence or no fence, and the orchestrator flags `malformed-second-pass-fencing` in the narration log. A `####` heading is recommended formatting; it is
never itself what makes text an entry. A Second-Pass entry counts only
when it is itself classified Fatal or Significant; a Minor-severity
second-pass entry belongs under `### Minor Observations` and does not count here. **Minor population join:** a `Minor`-first-token entry does join the round's Minor population for `round-N-score.md`'s Minor count, `MinorTrajectory`, and `m_exit`, de-duplicated against `### Minor Observations`.

An entry counts toward the score at the severity its own `**Severity:**` line declares. First strip any leading and trailing WHITESPACE from the value itself, then strip any leading AND TRAILING markdown emphasis markers and code-span backticks from the value, then check whether it begins with `Fatal`, `Significant`, or `Minor` immediately followed by end-of-line, or by one of `(`, `[`, `,`, `.`, `:`, `;`, or by whitespace followed by a dash — `-`, `–`, or `—`; a value like `Minor-to-Significant` does not recognise (no whitespace precedes the hyphen), but `Fatal - blocks the release` does recognise. A recognised token — whether declared bare or annotated — counts the entry at that recognised severity, and the orchestrator flags `annotated-second-pass-severity` in the narration log when annotated. A line whose value matches NONE of the three is counted as **Significant**, and the orchestrator flags `malformed-second-pass-entry` in the narration log.

A Second-Pass entry that restates or elaborates a finding already counted
under `### Fatal Challenges` / `### Significant Challenges` counts ONCE,
at the higher of the two severities.
<!-- CONTRACT:qg-score-second-pass-population:END -->

Red Flags:
- Counting the weighted score from `### Fatal Challenges` / `### Significant Challenges` only, ignoring Fatal/Significant entries under `### Second Pass Findings` (#561)

If red-team finds zero Fatal and zero Significant issues (same population as the Score source rule, step 7): candidate PASS.

1. **Clean pass** (0 Fatal, 0 Significant — same population as the Score source rule, step 7) — overrides every other entry.

If look-harder returns **0F/0S** (the same population as the Score source rule) and the discrepancy exception at step 7 has not fired on look-harder's own receipt: confirms the round.
If look-harder returns **Fatal/Significant** (also the same population) or the discrepancy exception at step 7 has fired on look-harder's own receipt: demotes the round.

Phase 2 is never the round's last flags write, on the confirm or ordinary-demote branch. Third branch (#561 fresh round 6 S5): Phase 2 IS the round's last flags write and completes the invariant; Phase 3 never runs on this branch.

Stagnation uses **weighted scoring** (Fatal=3, Significant=1) AND Fatal count tracking, counted over the same population as the Score source rule.

`m_exit` is the clean exit round's Minor count: round-R-findings.md Minors (including `Minor`-first-token entries under `### Second Pass Findings`, per the Score source rule's Minor population join, step 7) union confirmed round-R-look-harder.md Minors (likewise including `Minor`-first-token entries under `### Second Pass Findings` there, per the same Minor population join, step 7).

The terminal sentinel `round-N-complete.md` is NOT written on the ordinary demote path. On the discrepancy exception's Look-harder path the round IS terminal and `round-N-complete.md` MUST be written with `terminal: ESCALATED` before the verdict marker.

**Look-harder path (#561 fresh round 5 S5).** On this path `round-N-complete.md` MUST be written with `terminal: ESCALATED` before the verdict marker.

The receipt's SEVERITY-COUNTS line is a reviewer-declared cross-check; on disagreement the orchestrator trusts its own count for scoring and flags the discrepancy in the narration log. When the declared total exceeds the orchestrator's own count, the round is NOT candidate-clean.

Comparability of a discrepancy-blocked round: a discrepancy-blocked round is recorded `score-comparable: false` and treated as not-satisfiable for cross-round score comparisons.

Stagnation Detection > First-Pass Check > **Comparability gate**: a round marked `score-comparable: false` is not-satisfiable for the Progress / Oscillation / Sustained-regression comparisons: draw neither a progress nor a regression conclusion.

Comparisons resume normally once every round in the window is `score-comparable: true` — except a round whose `round-N-flags.md` carries a non-null `look-harder-fired-on-round: <N>` value: an absent `score-comparable` key there is read as `false`, not `true`.

**Empty-work-order exception.** When the directional exception above fires AND the orchestrator's own counted population is 0 Fatal and 0 Significant, the round does NOT route into the normal fix loop. Instead the orchestrator exits immediately with `Verdict: ESCALATED, Reason: severity-counts-discrepancy`. **Look-harder path.** This exception also covers the look-harder demotion path: when the discrepancy exception fires on look-harder's own receipt AND look-harder's own counted population is 0 Fatal and 0 Significant, the demotion protocol's three writes are still performed, then the round takes this same exit instead of the fix loop.

The only pre-threshold exits are: clean pass; architectural concerns; sustained-regression; no-op fix; severity-counts-discrepancy; consensus-stagnation; or explicit user interrupt.

Reason: clean-pass | siege-blocked | severity-counts-discrepancy

### Exit Precedence

1. **Clean pass** — overrides every other entry.
2. **ARCHITECTURAL_BLOCK**
3. **SUSTAINED_REGRESSION**
4. **severity-counts-discrepancy ESCALATED** — from the Score source rule's Empty-work-order exception. Verdict: `ESCALATED`, reason `severity-counts-discrepancy`.
5. **No-op fix ESCALATED** — byte-identical artifact.

## Red Flags

- `severity-counts-discrepancy` — Verdict: ESCALATED, from the Score source rule's Empty-work-order exception.

| "The Fatal is only in the second-pass section, the real count is zero." | rationalization | Count Fatal/Significant entries from all three sections — parsed per the `qg-score-second-pass-population` CONTRACT block (Score source, step 7). |

| INV-561-1 | Score source population: all consumers — including, for a `Minor`-first-token entry, the round's Minor population (`round-N-score.md`'s Minor count, `MinorTrajectory`/`minor_trajectory`, `m_exit`, and `red-team/SKILL.md`'s round-ledger `Total findings: N (F: x, S: y, M: z)` Minor count) — twelve consumers total — count the population parsed per the `qg-score-second-pass-population` CONTRACT block (Score source, step 7). |

<!-- CONTRACT:qg-score-population:START -->
- `score_population`: cross-run comparability marker. Value set:
  `"second-pass-inclusive" | "mixed" | absent`. Key-presence semantics, matching the
  `dr_cause` precedent: no `marker_version` bump.
<!-- CONTRACT:qg-score-population:END -->

Fragility-rate denominators filter on `score_population == "second-pass-inclusive"` specifically, not bare key-presence.

Comparability: scores computed under this widened population are not directly
comparable to pre-#561 stored `ScoreTrajectory` / `MaxScore` values. (1)
**intra-run** — on the first round after a mid-run population change, recount
every `round-K-findings.md` still on disk and overwrite `ScoreTrajectory`,
likewise recounting each round's Minor population and overwriting the corresponding entries of `MinorTrajectory`/`minor_trajectory` and `round-K-score.md`'s Minor count, in the same backfill pass, and recompute `MaxScore`. If any `round-K-findings.md` for this run is not on disk, the backfill is incomplete — record `score_population: mixed`, and have the backfill pass itself write `score-comparable: false` and `non-comparable-reason: incomplete-backfill` to the affected round's own `round-N-score.md`; an incomplete Minor backfill is the same incompleteness, and likewise makes the #362 trajectory rule and the stagnation judge's Minor-accumulation counter not-satisfiable for the affected rounds.
"""


def selftest() -> int:
    """Negative-control self-test: assert the checker is not a no-op.

    The good fixture must pass; deleting any single pinned phrase must produce
    at least one error (the grep genuinely fails on a broken artifact).
    """
    errs: list[str] = []
    good = check_skill(_GOOD_FIXTURE)
    if good:
        errs.append(f"selftest: GOOD fixture unexpectedly reported errors: {good}")

    mutations = {
        "Second Pass Findings mention": "### Second Pass Findings",
        "positive-connective literal pin (S4)": "plus\nany Fatal/Significant-severity entries under `### Second Pass Findings`",
        "un-spoofability argument": "un-spoofab",
        "Minor Observations redirect": "### Minor Observations",
        "Minor does-not-count carve-out": "does not count here",
        "content-marker entry definition (Finding, line-anchored)": "first non-whitespace characters are `**Finding:**`",
        "content-marker entry definition (Severity, line-anchored)": "first non-whitespace characters are `**Severity:**`",
        "entry-boundary rule (begins/extends)": "**begins** at the first line-initial `**Finding:**` or `**Severity:**` marker and **extends** to the line before the next `####` heading or the next line-initial `**Finding:**` marker",
        "entry-boundary rule (closing clause)": "does not open a second entry",
        "mid-sentence/quoted-occurrence exclusion clause": "mid-sentence or quoted occurrence",
        "fenced-code-block exclusion clause": "inside a fenced code block",
        "blockquote-marker exclusion clause": "beginning with a blockquote marker",
        "heading-never-itself-makes-an-entry statement": "never itself what makes text an entry",
        "first-recognised-token severity parse": "begins with `Fatal`, `Significant`, or `Minor`",
        "annotated-second-pass-severity flag": "flags `annotated-second-pass-severity`",
        "matches-NONE-of-the-three clause": "matches NONE of the three",
        "flags-malformed-second-pass-entry narration-log obligation": "flags `malformed-second-pass-entry`",
        "malformed-default consequence (counted as Significant)": "counted as **Significant**, and the orchestrator flags `malformed-second-pass-entry`",
        "de-dup counts ONCE": "counts ONCE",
        "de-dup higher-of-two-severities": "higher of the two severities",
        "Red Flags #561 bullet": _RED_FLAG_PIN,
        "CONTRACT block": "<!-- CONTRACT:qg-score-second-pass-population:END -->",
        "look-harder confirm population qualifier": "(the same population as the Score source rule)",
        "look-harder demote population qualifier": "(also the same population)",
        "step-5 candidate-clean population qualifier": "(same population as the Score source rule, step 7): candidate PASS.",
        "Exit Precedence slot #1 population qualifier": "(0 Fatal, 0 Significant — same population as the Score source rule, step 7)",
        "Fatal count tracking population qualifier": "counted over the same population as the Score source rule.",
        "SEVERITY-COUNTS discrepancy exception": "the round is NOT candidate-clean.",
        "score_population value-set pin": '"second-pass-inclusive" | "mixed" | absent',
        "score_population no-marker_version-bump pin": "no `marker_version` bump",
        "fragility-rate second-pass-inclusive filter": 'score_population == "second-pass-inclusive"',
        "fence-parity ODD-number trigger": "ODD number of triple-backtick delimiters",
        "malformed-second-pass-fencing flag": "flags `malformed-second-pass-fencing`",
        "fence-parity consequence (does NOT apply)": "does NOT apply anywhere in the section",
        "fence-parity consequence (every marker counts)": "every line-initial marker in the section counts, fence or no fence",
        "severity normalization (trailing-whitespace strip, fresh round 12)": "strip any leading and trailing WHITESPACE from the value itself",
        "severity normalization (markdown emphasis strip)": "strip any leading AND TRAILING markdown emphasis markers",
        "severity normalization (code-span backtick strip)": "code-span backtick",
        "severity word-boundary rule (end-of-line/punctuation set)": "immediately followed by end-of-line, or by one of `(`, `[`, `,`, `.`, `:`, `;`",
        "severity word-boundary rule (spaced-dash clause)": "whitespace followed by a dash",
        "severity word-boundary positive example (spaced hyphen)": "Fatal - blocks the release",
        "severity word-boundary negative example": "Minor-to-Significant",
        "severity word-boundary negative-example discriminator": "no whitespace precedes the hyphen",
        "look-harder confirm discrepancy-exception qualifier": "and the discrepancy exception at step 7 has not fired on look-harder's own receipt",
        "look-harder demote discrepancy-exception qualifier": "or the discrepancy exception at step 7 has fired on look-harder's own receipt",
        "discrepancy-blocked-round comparability clause": "Comparability of a discrepancy-blocked round",
        "First-Pass Check comparability gate": "**Comparability gate",
        "entry-boundary terminator fence/blockquote qualifier (SP1)": "that is not itself inside a fenced code block or prefixed by a blockquote marker (`> `)",
        "list-marker stripping clause (SP2)": "strip an optional leading list marker",
        "list-marker-vs-blockquote distinct-exclusion clause (SP2)": "is a distinct exclusion, not a stripped prefix",
        "Minor population join label (S3)": "**Minor population join:**",
        "Exit Precedence severity-counts-discrepancy slot (S4)": "severity-counts-discrepancy ESCALATED",
        "Reason-token-mapping severity-counts-discrepancy bullet (S4)": "`severity-counts-discrepancy` — Verdict: ESCALATED",
        "Empty-work-order exception look-harder path (S5)": "Look-harder path.",
        "m_exit definition-site population qualifier (fresh round 6 S3)": "including `Minor`-first-token entries under `### Second Pass Findings`, per the Score source rule's Minor population join, step 7",
        "F1 sentinel carve-out, demote-branch site (fresh round 6 F1)": "discrepancy exception's Look-harder path the round IS terminal and `round-N-complete.md` MUST be written with `terminal: ESCALATED` before the verdict marker",
        "F1 sentinel carve-out, S5-clause site (fresh round 6 F1)": "**Look-harder path (#561 fresh round 5 S5).** On this path `round-N-complete.md` MUST be written with `terminal: ESCALATED` before the verdict marker.",
        "Exit Precedence slot #4 verdict consequence (fresh round 6 S1(a))": "Verdict: `ESCALATED`, reason `severity-counts-discrepancy`.",
        "list-marker positive consequence (fresh round 6 S1(b))": "still opens (or carries) an entry under this rule",
        "S5 three-branch write-ordering enumeration (fresh round 6 S5)": "Third branch (#561 fresh round 6 S5): Phase 2 IS the round's last flags write and completes the invariant; Phase 3 never runs on this branch.",
        "section-location clause (fresh round 7 S1)": "Section location",
        "section-location four-section enumeration (fresh round 8 SP2)": "the four sections this parse reads",
        "section-location scope sentence (fresh round 8 SP1)": "this location step applies to the bytes of the cited findings file itself",
        "section-location end definition (fresh round 8 S4)": "section's **end** is the next `###`-level heading line",
        "section-location zero-match rule (fresh round 8 F1)": "Zero-match rule",
        "section-location zero-match generalized-trigger clause (fresh round 12 S1)": "the fallback triggers on this OBSERVABLE condition itself",
        "section-location zero-match not-found-as-empty sentence (fresh round 8 F1)": 'never treat "not found" as "empty"',
        "section-location union tiebreak (fresh round 8 S1/S5)": "counts the **union** of all matching sections",
        "section-location START consequence pin (fresh round 10 F1)": "earliest occurrence of such a heading line in the file",
        "section-location START consequence pin, closing clause (fresh round 10 F1)": "never overrides an earlier one as the section's start",
        "section-location END consequence pin (fresh round 9 F1)": "extends to the end of the cited file",
        "section-location zero-match both-predicates pin (fresh round 9 S1)": "both the start and end predicates",
        "section-location zero-match end-to-end pin (fresh round 9 S1)": "raw-heading location end-to-end",
        "missing-second-pass-section narration-only flag (fresh round 10 S5)": "flags `missing-second-pass-section` in the narration log",
        "missing-second-pass-section narration-only framing (fresh round 10 S5)": "this default is narration-only",
        "section-location union de-dup-basis pin (fresh round 9 S2)": "de-duplicated by entry identity",
        "m_exit second-operand qualifier (fresh round 7 S3)": " (likewise including `Minor`-first-token entries under `### Second Pass Findings` there, per the same Minor population join, step 7)",
        "fenced/blockquote CONSEQUENCE pin (fresh round 7 S5)": "is never an entry-opening line",
        "mid-sentence CONSEQUENCE pin (fresh round 7 S5)": "does not make surrounding prose an entry",
        "recognised-token CONSEQUENCE pin (fresh round 7 S5)": "counts the entry at that recognised severity",
        "Comparability gate CONSEQUENCE pin (fresh round 7 S5)": "draw neither a progress nor a regression conclusion",
        "intra-run backfill Minor-population recount extension (fresh round 8 S6)": "recounting each round's Minor population",
        "intra-run backfill Minor-population sink pin (fresh round 8 S6)": "`MinorTrajectory`/`minor_trajectory` and `round-K-score.md`'s Minor count",
        "intra-run backfill Minor not-satisfiable extension trigger (fresh round 8 S6)": "an incomplete Minor backfill is the same incompleteness",
        "intra-run backfill Minor not-satisfiable extension consequence (fresh round 8 S6)": "makes the #362 trajectory rule",
        "intra-run backfill durable score-comparable write (fresh round 12 S2)": "have the backfill pass itself write `score-comparable: false` and `non-comparable-reason: incomplete-backfill`",
    }
    for label, needle in mutations.items():
        broken = _GOOD_FIXTURE.replace(needle, "")  # remove ALL occurrences
        if not check_skill(broken):
            errs.append(
                f"selftest: removing '{label}' did NOT trip the checker (no-op grep)"
            )

    # Polarity guard negative controls (#561 round 1 S1): mutate by REPLACING
    # the pin with its negated form, not by deleting it — a deletion-only
    # control certifies detection of a drift class (deletion) that is NOT the
    # class #561's own history exhibits (three in-place rewrites, zero
    # deletions).
    negations = {
        "(a) Score source rule negated in place": (
            "sections, plus\nany Fatal/Significant-severity entries under `### Second Pass Findings`.",
            "sections, and explicitly EXCLUDING\nany entries under `### Second Pass Findings`.",
        ),
        "(a) Score source rule rewritten with an out-of-vocabulary synonym (#561 round 4 S4)": (
            "sections, plus\nany Fatal/Significant-severity entries under `### Second Pass Findings`.",
            "sections; entries under `### Second Pass Findings` are disregarded for scoring purposes.",
        ),
        "(h) look-harder confirm branch negated in place": (
            "(the same population as the Score source rule) and the discrepancy",
            "(NOT the same population as the Score source rule) and the discrepancy",
        ),
        "(h) look-harder demote branch negated in place": (
            "(also the same population) or the discrepancy",
            "(NOT the same population) or the discrepancy",
        ),
        "(i) step-5 candidate-clean predicate negated in place": (
            "(same population as the Score source rule, step 7): candidate PASS.",
            "(NOT the same population as the Score source rule, step 7): candidate PASS.",
        ),
        "(j) Exit Precedence slot #1 negated in place": (
            "(0 Fatal, 0 Significant — same population as the Score source rule, step 7)",
            "(0 Fatal, 0 Significant — NOT the same population as the Score source rule, step 7)",
        ),
        "(l) Fatal count tracking negated in place": (
            "counted over the same population as the Score source rule.",
            "counted over NOT the same population as the Score source rule.",
        ),
        "(m) SEVERITY-COUNTS discrepancy exception negated in place": (
            "the declared total exceeds the orchestrator's own count",
            "the declared total does NOT exceeds the orchestrator's own count",
        ),
        "(n) fence-parity ODD trigger negated in place": (
            "contains an ODD number of triple-backtick delimiters",
            "does NOT contain an ODD number of triple-backtick delimiters",
        ),
        "(n) fence-parity consequence rewritten with no negation token (#561 round 4 S2)": (
            "the fenced-code-block exclusion does NOT apply anywhere in the section: every line-initial marker in the section counts, fence or no fence, and the orchestrator flags `malformed-second-pass-fencing` in the narration log.",
            "the remainder of the section is treated as entirely fenced and counts nothing, and the orchestrator flags `malformed-second-pass-fencing` in the narration log.",
        ),
        "(m) discrepancy-blocked-round comparability clause negated in place": (
            "is recorded `score-comparable: false`",
            "is NOT recorded `score-comparable: false`",
        ),
        "(h) look-harder demote discrepancy 'fired' negated in place": (
            "has fired on look-harder's own receipt: demotes the round.",
            "has NOT fired on look-harder's own receipt: demotes the round.",
        ),
        "(e2) malformed-default consequence negated in place": (
            "is counted as **Significant**, and the orchestrator flags",
            "is NOT counted as **Significant**, and the orchestrator flags",
        ),
        "list-marker stripping clause negated in place (SP2)": (
            "Before testing either marker, strip an optional leading list marker",
            "Before testing either marker, do NOT strip an optional leading list marker",
        ),
        "Minor population join clause negated in place (S3)": (
            "does join the round's Minor population",
            "does NOT join the round's Minor population",
        ),
        "(o) Exit Precedence slot #4 consequence rewritten to a no-op, keeping the token and position (#561 fresh round 6 S1(a))": (
            "4. **severity-counts-discrepancy ESCALATED** — from the Score source rule's Empty-work-order exception. Verdict: `ESCALATED`, reason `severity-counts-discrepancy`.",
            "4. **severity-counts-discrepancy ESCALATED** — from the Score source rule's Empty-work-order exception. This condition is recorded under `CoFiredExits:` for telemetry and does not itself select a verdict; the round continues into the normal fix loop and whichever lower slot fires governs the verdict.",
        ),
        "list-marker stripping consequence flipped to a NOT-an-entry reading, keeping the trigger phrase (#561 fresh round 6 S1(b))": (
            "still opens (or carries) an entry under this rule",
            "for READABILITY ONLY; a list-bulleted line such as `- **Severity:** Fatal` is still NOT an entry and scores 0",
        ),
        "(c) section-location clause negated in place (#561 fresh round 7 S1)": (
            "neither inside a fenced code block nor prefixed by a blockquote marker",
            "regardless of whether it is inside a fenced code block or prefixed by a blockquote marker",
        ),
        "section-location union tiebreak reverted to last-only, keeping the malformed flag (#561 fresh round 8 S1)": (
            "flag `malformed-second-pass-sectioning` and counts the **union** of all matching sections' entries — de-duplicated by entry identity where the union itself produces a duplicate — rather than any single one of them.",
            "flag `malformed-second-pass-sectioning` and treats the **last** matching heading as the section.",
        ),
        "section-location union tiebreak reverted to first-only, keeping the malformed flag (#561 fresh round 8 S1)": (
            "flag `malformed-second-pass-sectioning` and counts the **union** of all matching sections' entries — de-duplicated by entry identity where the union itself produces a duplicate — rather than any single one of them.",
            "flag `malformed-second-pass-sectioning` and treats the **first** matching heading as the section.",
        ),
        "intra-run backfill Minor-population recount extension negated in place (fresh round 8 S6)": (
            "likewise recounting each round's Minor population",
            "likewise NOT recounting each round's Minor population",
        ),
        "intra-run backfill Minor not-satisfiable extension negated in place (fresh round 8 S6)": (
            "and likewise makes the #362 trajectory rule",
            "and likewise NOT makes the #362 trajectory rule",
        ),
        "(n) fenced/blockquote consequence rewritten with no negation token (#561 fresh round 7 S5)": (
            "is never an entry-opening line either — the blockquote marker",
            "is treated as an ordinary entry-opening line, exactly like any other line — the blockquote marker",
        ),
        "(e1) mid-sentence consequence rewritten with no negation token (#561 fresh round 7 S5)": (
            "does not make surrounding prose an entry.",
            "makes the surrounding prose a scored entry.",
        ),
        "(e2) recognised-token consequence rewritten with no negation token (#561 fresh round 7 S5)": (
            "counts the entry at that recognised severity, and the orchestrator flags",
            "is recorded for narration only and the entry is scored 0, and the orchestrator flags",
        ),
        "(f) de-dup clause decoy insertion, keeping both pinned substrings intact (#561 fresh round 7 S5)": (
            "counts ONCE,\nat the higher of the two severities",
            "counts ONCE **per section**,\nat the higher of the two severities",
        ),
        "(m) Comparability gate consequence rewritten with no negation token (#561 fresh round 7 S5)": (
            "comparisons: draw neither a progress nor a regression conclusion.",
            "comparisons: draw the ordinary progress/regression conclusion.",
        ),
        "(o) SP1 trigger inverted ALONE, S5 Look-harder-path clause left untouched (#561 fresh round 7 S2)": (
            "When the directional exception above fires AND the orchestrator's own counted population is 0 Fatal and 0 Significant, the round does NOT route into the normal fix loop.",
            "When the directional exception above fires AND the orchestrator's own counted population is at least 1 Fatal or 1 Significant, the round does NOT route into the normal fix loop.",
        ),
        "(o) S5 Look-harder-path trigger inverted ALONE, SP1 clause left untouched (#561 fresh round 7 S2)": (
            "look-harder's own counted population is 0 Fatal and 0 Significant, the demotion protocol's three writes are still performed",
            "look-harder's own counted population is at least 1 Fatal or 1 Significant, the demotion protocol's three writes are still performed",
        ),
        "section-location START consequence negated in place (#561 fresh round 10 F1)": (
            "This is the earliest occurrence of such a heading line in the file",
            "This is NOT the earliest occurrence of such a heading line in the file",
        ),
        "section-location END consequence negated in place (#561 fresh round 9 F1)": (
            "the section extends to the end of the cited file",
            "the section does NOT extends to the end of the cited file",
        ),
        "section-location zero-match both-predicates clause negated in place (#561 fresh round 9 S1)": (
            "for both the start and end predicates of that section, raw-heading location end-to-end",
            "for NOT both the start and end predicates of that section — only the start, not raw-heading location end-to-end",
        ),
        "section-location union de-dup-basis clause negated in place (#561 fresh round 9 S2)": (
            "de-duplicated by entry identity where the union itself produces a duplicate",
            "NOT de-duplicated by entry identity where the union itself produces a duplicate",
        ),
        "missing-second-pass-section trigger negated in place (#561 fresh round 10 S5)": (
            "flags `missing-second-pass-section` in the narration log",
            "does NOT flag `missing-second-pass-section` in the narration log",
        ),
        "section-location Scope-sentence consequence negated in place, keeping the consequence phrase itself intact (#561 fresh round 10 follow-up 2)": (
            "eval prompt — is parsed as that file's own content, not as the enclosing document's.",
            "eval prompt — it is NOT true that this is parsed as that file's own content, not as the enclosing document's.",
        ),
    }
    for label, (needle, negated) in negations.items():
        assert needle in _GOOD_FIXTURE, f"selftest setup: '{label}' needle not found in fixture"
        mutated = _GOOD_FIXTURE.replace(needle, negated)
        if not check_skill(mutated):
            errs.append(
                f"selftest: negating '{label}' did NOT trip the checker (polarity-blind)"
            )

    # (p) continued — S2 has_pointer-and-partial-details negative/positive
    # controls (#561 fresh round 5 S2): a pointer site carrying a PARTIAL,
    # contradictory restatement beside its pointer must trip (p); a pointer
    # site carrying a benign summary with NONE of the three detail tokens
    # must still pass (demanding a pointer-only site carry zero prose would
    # forbid legitimate summary text the row already carries).
    _antirat_needle = (
        "Count Fatal/Significant entries from all three sections — parsed per "
        "the `qg-score-second-pass-population` CONTRACT block (Score source, "
        "step 7)."
    )
    assert _antirat_needle in _GOOD_FIXTURE, "selftest setup: antirat row needle not found"
    _stale_partial_fixture = _GOOD_FIXTURE.replace(
        _antirat_needle,
        _antirat_needle + " The token must be immediately followed by end-of-line, or by one of "
        "`(`, `[`, `,`, `.`, `:`, `;`.",
    )
    _partial_errs = check_skill(_stale_partial_fixture)
    if not any("PARTIAL restatement" in e for e in _partial_errs):
        errs.append(
            "selftest: a pointer site carrying a PARTIAL restatement beside its "
            "pointer did NOT trip the (p) pointer-or-complete guard (#561 fresh "
            "round 5 S2)"
        )
    _benign_summary_fixture = _GOOD_FIXTURE.replace(
        _antirat_needle,
        _antirat_needle + " Count from all three sections.",
    )
    _benign_errs = check_skill(_benign_summary_fixture)
    if any("anti-rationalization row" in e for e in _benign_errs):
        errs.append(
            "selftest: a pointer site carrying a benign summary (no detail "
            "tokens) was wrongly rejected by the (p) pointer-or-complete guard "
            "(#561 fresh round 5 S2)"
        )

    # Co-location: Second Pass Findings mentioned far from the other two
    # headings (a separate, unrelated population) must still be flagged.
    detached = (
        "`### Fatal Challenges` / `### Significant Challenges`"
        + ("\n" * 500)
        + "`### Second Pass Findings`"
    )
    if not check_skill(detached):
        errs.append(
            "selftest: a detached (non-co-located) '### Second Pass Findings' "
            "mention did NOT trip the co-location check"
        )

    # Near-decoy (#561 round 3 F2, rebuilt from the REAL CONTRACT block
    # content): the Score-source rule's OWN sentence (strictly before
    # CONTRACT:START) is UN-widened — it mentions only the two original
    # headings — but the CONTRACT block interior, the Red Flags bullet, and
    # both look-harder branches are otherwise a complete, correct copy of the
    # real file's content (including the de-dup clause). This isolates
    # assertion (a): the old decoy was a truncated block that failed for 8
    # reasons unrelated to (a) (missing severity pins, missing de-dup clause,
    # etc.) and so was not a valid negative control. This one must fail iff
    # (a) fails — verified below by widening only the rule sentence and
    # confirming that alone clears every error.
    _NEAR_DECOY_FIXTURE = """
The weighted score is computed by the orchestrator counting the cited findings
file's `### Fatal Challenges` / `### Significant Challenges` sections.
<!-- CONTRACT:qg-score-second-pass-population:START -->
Widening this population does not weaken un-spoofability: the orchestrator
still counts from the cited artifact's on-disk text, not from a declared
number. Section location: the four sections this parse reads — `### Fatal Challenges`, `### Significant Challenges`, `### Second Pass Findings`, `### Minor Observations` — are already correctly located; that location step is itself a parse, not a given. Each section's **start** is the first `###`-level heading line matching that exact heading text which is itself neither inside a fenced code block nor prefixed by a blockquote marker. This is the earliest occurrence of such a heading line in the file: a heading line matching later in the file never overrides an earlier one as the section's start. Scope: this location step applies to the bytes of the cited findings file itself; a findings file quoted inside another document — including an eval prompt — is parsed as that file's own content, not as the enclosing document's. A section's **end** is the next `###`-level heading line that is itself neither inside a fenced code block nor prefixed by a blockquote marker; when none follows, the section extends to the end of the cited file. Zero-match rule: if the matching-heading count for any section is zero, the fallback triggers on this OBSERVABLE condition itself, not on a diagnosis of why it is zero (a fence-parity defect elsewhere in the file is one cause; a section whose only matching heading sits inside an otherwise-BALANCED, CLOSED fence is another), the fence exclusion does NOT apply at the heading level either — for both the start and end predicates of that section, raw-heading location end-to-end — re-locate over the raw heading lines, flag `malformed-second-pass-sectioning`, and never treat "not found" as "empty". If no heading line matching that section's text exists in the file at all, even under this raw-heading fallback, the orchestrator flags `missing-second-pass-section` in the narration log rather than silently treating the section as present-but-empty; this default is narration-only, like its siblings, and does not itself change the verdict. If more than one such heading matches after that exclusion, flag `malformed-second-pass-sectioning` and counts the **union** of all matching sections' entries — de-duplicated by entry identity where the union itself produces a duplicate — rather than any single one of them. A Second-Pass entry carries a line whose first non-whitespace characters are `**Finding:**` and/or a line whose first non-whitespace characters are `**Severity:**`. An entry **begins** at the first line-initial `**Finding:**` or `**Severity:**` marker and **extends** to the line before the next `####` heading or the next line-initial `**Finding:**` marker **that is not itself inside a fenced code block or prefixed by a blockquote marker (`> `)**, whichever comes first, or to the end of the section; a `**Severity:**` line inside an already-open entry is that entry's own severity line and does not open a second entry. A mid-sentence or quoted occurrence of either marker string does not make surrounding prose an entry. Before testing either marker, strip an optional leading list marker (`-`, `*`, `+`, or `<digits>.` followed by whitespace); a list-bulleted line such as `- **Severity:** Fatal` still opens (or carries) an entry under this rule. A line inside a fenced code block or a line beginning with a blockquote marker is never an entry-opening line either — the blockquote marker `> ` is a distinct exclusion, not a stripped prefix. If `### Second Pass Findings` contains an ODD number of triple-backtick delimiters, or a fence left open at the section boundary, the fenced-code-block exclusion does NOT apply anywhere in the section: every line-initial marker in the section counts, fence or no fence, and the orchestrator flags `malformed-second-pass-fencing` in the narration log. A `####` heading is recommended formatting; it is
never itself what makes text an entry. A Second-Pass entry counts only
when it is itself classified Fatal or Significant; a Minor-severity
second-pass entry belongs under `### Minor Observations` and does not count here. **Minor population join:** a `Minor`-first-token entry does join the round's Minor population for `round-N-score.md`'s Minor count, `MinorTrajectory`, and `m_exit`, de-duplicated against `### Minor Observations`.

An entry counts toward the score at the severity its own `**Severity:**` line declares. First strip any leading and trailing WHITESPACE from the value itself, then strip any leading AND TRAILING markdown emphasis markers and code-span backticks from the value, then check whether it begins with `Fatal`, `Significant`, or `Minor` immediately followed by end-of-line, or by one of `(`, `[`, `,`, `.`, `:`, `;`, or by whitespace followed by a dash — `-`, `–`, or `—`; a value like `Minor-to-Significant` does not recognise (no whitespace precedes the hyphen), but `Fatal - blocks the release` does recognise. A recognised token — whether declared bare or annotated — counts the entry at that recognised severity, and the orchestrator flags `annotated-second-pass-severity` in the narration log when annotated. A line whose value matches NONE of the three is counted as **Significant**, and the orchestrator flags `malformed-second-pass-entry` in the narration log.

A Second-Pass entry that restates or elaborates a finding already counted
under `### Fatal Challenges` / `### Significant Challenges` counts ONCE,
at the higher of the two severities.
<!-- CONTRACT:qg-score-second-pass-population:END -->

Red Flags:
- Counting the weighted score from `### Fatal Challenges` / `### Significant Challenges` only, ignoring Fatal/Significant entries under `### Second Pass Findings` (#561)

If red-team finds zero Fatal and zero Significant issues (same population as the Score source rule, step 7): candidate PASS.

1. **Clean pass** (0 Fatal, 0 Significant — same population as the Score source rule, step 7) — overrides every other entry.

If look-harder returns **0F/0S** (the same population as the Score source rule) and the discrepancy exception at step 7 has not fired on look-harder's own receipt: confirms the round.
If look-harder returns **Fatal/Significant** (also the same population) or the discrepancy exception at step 7 has fired on look-harder's own receipt: demotes the round.

Phase 2 is never the round's last flags write, on the confirm or ordinary-demote branch. Third branch (#561 fresh round 6 S5): Phase 2 IS the round's last flags write and completes the invariant; Phase 3 never runs on this branch.

Stagnation uses **weighted scoring** (Fatal=3, Significant=1) AND Fatal count tracking, counted over the same population as the Score source rule.

`m_exit` is the clean exit round's Minor count: round-R-findings.md Minors (including `Minor`-first-token entries under `### Second Pass Findings`, per the Score source rule's Minor population join, step 7) union confirmed round-R-look-harder.md Minors (likewise including `Minor`-first-token entries under `### Second Pass Findings` there, per the same Minor population join, step 7).

The terminal sentinel `round-N-complete.md` is NOT written on the ordinary demote path. On the discrepancy exception's Look-harder path the round IS terminal and `round-N-complete.md` MUST be written with `terminal: ESCALATED` before the verdict marker.

**Look-harder path (#561 fresh round 5 S5).** On this path `round-N-complete.md` MUST be written with `terminal: ESCALATED` before the verdict marker.

The receipt's SEVERITY-COUNTS line is a reviewer-declared cross-check; on disagreement the orchestrator trusts its own count for scoring and flags the discrepancy in the narration log. When the declared total exceeds the orchestrator's own count, the round is NOT candidate-clean.

Comparability of a discrepancy-blocked round: a discrepancy-blocked round is recorded `score-comparable: false` and treated as not-satisfiable for cross-round score comparisons.

Stagnation Detection > First-Pass Check > **Comparability gate**: a round marked `score-comparable: false` is not-satisfiable for the Progress / Oscillation / Sustained-regression comparisons: draw neither a progress nor a regression conclusion.

Comparisons resume normally once every round in the window is `score-comparable: true` — except a round whose `round-N-flags.md` carries a non-null `look-harder-fired-on-round: <N>` value: an absent `score-comparable` key there is read as `false`, not `true`.

**Empty-work-order exception.** When the directional exception above fires AND the orchestrator's own counted population is 0 Fatal and 0 Significant, the round does NOT route into the normal fix loop. Instead the orchestrator exits immediately with `Verdict: ESCALATED, Reason: severity-counts-discrepancy`. **Look-harder path.** This exception also covers the look-harder demotion path: when the discrepancy exception fires on look-harder's own receipt AND look-harder's own counted population is 0 Fatal and 0 Significant, the demotion protocol's three writes are still performed, then the round takes this same exit instead of the fix loop.

The only pre-threshold exits are: clean pass; architectural concerns; sustained-regression; no-op fix; severity-counts-discrepancy; consensus-stagnation; or explicit user interrupt.

Reason: clean-pass | siege-blocked | severity-counts-discrepancy

### Exit Precedence

1. **Clean pass** — overrides every other entry.
2. **ARCHITECTURAL_BLOCK**
3. **SUSTAINED_REGRESSION**
4. **severity-counts-discrepancy ESCALATED** — from the Score source rule's Empty-work-order exception. Verdict: `ESCALATED`, reason `severity-counts-discrepancy`.
5. **No-op fix ESCALATED** — byte-identical artifact.

## Red Flags

- `severity-counts-discrepancy` — Verdict: ESCALATED, from the Score source rule's Empty-work-order exception.

| "The Fatal is only in the second-pass section, the real count is zero." | rationalization | Count Fatal/Significant entries from all three sections — parsed per the `qg-score-second-pass-population` CONTRACT block (Score source, step 7). |

| INV-561-1 | Score source population: all consumers — including, for a `Minor`-first-token entry, the round's Minor population (`round-N-score.md`'s Minor count, `MinorTrajectory`/`minor_trajectory`, `m_exit`, and `red-team/SKILL.md`'s round-ledger `Total findings: N (F: x, S: y, M: z)` Minor count) — twelve consumers total — count the population parsed per the `qg-score-second-pass-population` CONTRACT block (Score source, step 7). |

<!-- CONTRACT:qg-score-population:START -->
- `score_population`: cross-run comparability marker. Value set:
  `"second-pass-inclusive" | "mixed" | absent`. Key-presence semantics, matching the
  `dr_cause` precedent: no `marker_version` bump.
<!-- CONTRACT:qg-score-population:END -->

Fragility-rate denominators filter on `score_population == "second-pass-inclusive"` specifically, not bare key-presence.

Comparability: scores computed under this widened population are not directly
comparable to pre-#561 stored `ScoreTrajectory` / `MaxScore` values. (1)
**intra-run** — on the first round after a mid-run population change, recount
every `round-K-findings.md` still on disk and overwrite `ScoreTrajectory`,
likewise recounting each round's Minor population and overwriting the corresponding entries of `MinorTrajectory`/`minor_trajectory` and `round-K-score.md`'s Minor count, in the same backfill pass, and recompute `MaxScore`. If any `round-K-findings.md` for this run is not on disk, the backfill is incomplete — record `score_population: mixed`, and have the backfill pass itself write `score-comparable: false` and `non-comparable-reason: incomplete-backfill` to the affected round's own `round-N-score.md`; an incomplete Minor backfill is the same incompleteness, and likewise makes the #362 trajectory rule and the stagnation judge's Minor-accumulation counter not-satisfiable for the affected rounds.
"""
    near_decoy_errs = check_skill(_NEAR_DECOY_FIXTURE)
    if not near_decoy_errs:
        errs.append(
            "selftest: near-decoy (real CONTRACT-block content, UN-widened rule "
            "sentence) fooled the checker into reporting no errors"
        )
    elif any(
        "does not mention" not in e
        and "is not co-located" not in e
        and "missing the literal 'plus any Fatal" not in e
        for e in near_decoy_errs
    ):
        errs.append(
            f"selftest: near-decoy failed for reasons other than assertion (a): "
            f"{near_decoy_errs}"
        )

    # Confirm the decoy fails IFF (a) fails: widening ONLY the rule sentence
    # (leaving the rest of the near-decoy untouched) must clear every error.
    near_decoy_fixed = _NEAR_DECOY_FIXTURE.replace(
        "`### Fatal Challenges` / `### Significant Challenges` sections.",
        "`### Fatal Challenges` / `### Significant Challenges` sections, plus "
        "any Fatal/Significant-severity entries under `### Second Pass Findings`.",
    )
    fixed_errs = check_skill(near_decoy_fixed)
    if fixed_errs:
        errs.append(
            "selftest: widening only the near-decoy's rule sentence did not clear "
            f"all errors ({fixed_errs}) — the decoy does not isolate assertion (a)"
        )

    if errs:
        print("SELFTEST FAILED:")
        for e in errs:
            print(f"  - {e}")
        return 1
    print("OK — selftest: good fixture clean; all pinned-phrase deletions detected.")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    errs: list[str] = []
    skill_text = _read(SKILL, errs)
    if skill_text is not None:
        errs += check_skill(skill_text)
    if errs:
        print("QG SECOND-PASS-SCORE DRIFT DETECTED:")
        for e in errs:
            print(f"  - {e}")
        return 1
    print(
        "OK — #366 Score source widened to cover Second Pass Findings (#561): "
        "population extension, un-spoofability preservation, mechanical severity "
        "rule, de-dup clause, Minor carve-out, and Red Flags entry all present "
        "and aligned."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
