#!/usr/bin/env python3
"""#488 c1 / AC-6 — the DEC-31 mutant sweep, as a runner instead of a one-shot.

AC-6 asks that every leg of this ticket's rule be verified against a DELIBERATELY
BROKEN copy of the build. Five legs need no constructed copy — the shipped build
*was* the broken copy, and Tasks 3/4/5's own RED->GREEN transitions discharge them
(T10's three parser legs, T2's silence, T7 leg 2's walk-only shape). The fifteen
rows below are the copies that are NOT the shipped build.

Each row gets a FRESH `tempfile.mkdtemp()` tree (`scripts` + `eval` + `docs`), has
its mutation applied to that copy's `scripts/rcpt_verify.py`, and runs
`scripts/test_488_name_space.py` with that tree as cwd. No repo file is mutated, no
`git checkout --` revert dance, and no row can contaminate another.

`docs` is NOT optional: without it `TestTheRulingIsRecorded` cannot find the ruling
and EVERY row skews by +1 failure / +1 error. `skills/` is deliberately not copied
and must not be — no test in the suite reads anything under it.

Exit 0 with sixteen `-- ok` lines when every pin still discriminates exactly as
recorded. Any symmetric difference is a non-zero exit naming the row, printing
`unexpected` (a pin fired that was not expected — an over-broad mutation, or a new
test) and `missing` (a pin did NOT fire — the vacuity signal this arc has hit four
times) as separate lines, and leaving that row's tree on disk with its path printed.

Every `expect` set and `TOTAL_TESTS` below is MEASURED against the tree as it
stands, never transcribed from the plan: Task 5's five review rounds grew
`scripts/test_488_name_space.py` from 54 tests to 160, and the plan's own tables
were written before that. When the suite legitimately gains a test, this file goes
red twice over -- once on the `Ran N tests` count, once as `unexpected` on any row
the new test reaches -- and the fix is to RE-MEASURE and record what is true now,
never to widen a set until it stops complaining. A set that has to LOSE a member is
the signal this harness exists for: a pin that stopped discriminating.

This harness does NOT discharge AC-6 on its own: it makes and mutates the copy and
reports the diff; the implementer still reads that output and signs it off in the PR
body. Automating the mechanical half is not the verification.

NOT AC-9. AC-9's `scripts/check_488_gates.py` (the five ordering gates' XOR) is
ruled text-only for this ticket and does not land here. This file asserts a
different subject: that #488 c1's pins still discriminate against the known-broken
builds.
"""
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
COPY_DIRS = ("scripts", "eval", "docs")
SUITE = "scripts/test_488_name_space.py"

# The whole suite must still be COLLECTED on every row, row 0 included: a mutation
# that changes the NUMBER of tests has broken the tree, not a pin.
TOTAL_TESTS = 160

_HDR = re.compile(r"^(?:FAIL|ERROR): (\S+) \((.+?)\)", re.M)


def _ids(text):
    """Failing tests as `Class.method`. Tolerates both unittest spellings: 3.11+
    renders `(__main__.C.test_x)`, older renders `(__main__.C)`.

    Qualified ids, never bare method names: `test_no_note_is_emitted` and
    `test_the_sub_count_stays_zero` each name TWO different tests in this suite
    (`TestATopLevelResolutionIsNotCounted` and
    `TestAnotherRootsGitToplevelDoesNotFlagATopLevelName`), and rows 8, 10 and 15
    turn on which. FAIL: and ERROR: both count, into ONE set — several rows redden
    by exception rather than by assertion (row 10's `cov.bump` keys into a dict the
    tuple no longer seeds), and which of the two a build produces is not the
    property under test."""
    out = set()
    for meth, dotted in _HDR.findall(text):
        dotted = dotted.removeprefix("__main__.")
        out.add(dotted if dotted.endswith("." + meth) else f"{dotted}.{meth}")
    return out


def _apply(path, edits):
    """Substring substitution, with EVERY anchor checked for uniqueness FIRST.

    FIRST is literal: one pre-pass over all of a row's anchors against the
    UNMUTATED text, then a second pass that substitutes. Checking each anchor
    against the partially-mutated text would make an anchor's verdict depend on
    the edits ordered before it; a stale anchor also now leaves the copy
    untouched rather than half-mutated.

    Uniqueness is SUBSTRING uniqueness (`str.count`), not line uniqueness, and the
    difference is not academic: `    return notes` is line-unique in
    `rcpt_verify.py` but occurs twice as a substring, inside `        return
    notes_ambiguous + ...`. Row 4's anchor carries its surrounding newlines for
    exactly that reason. A row that trips this clause is an ANCHOR bug (the source
    moved under it), not a pin bug — which is why it reads as its own error rather
    than as a confusing failure count."""
    text = path.read_text()
    for anchor, _ in edits:
        n = text.count(anchor)
        if n != 1:
            raise SystemExit(f"stale anchor (occurs {n}x, expected 1):\n{anchor}")
    for anchor, repl in edits:
        text = text.replace(anchor, repl)
    path.write_text(text)


# --------------------------------------------------------------------------- #
# Block constants, extracted VERBATIM from the current scripts/rcpt_verify.py.
# Each is file-unique on the finished build; `_apply` proves that on every run.
# --------------------------------------------------------------------------- #

# `_below_top_level`'s loop body: `for r in _as_roots(root):` .. `return None`.
DEPTH_BODY = '''    for r in _as_roots(root):
        try:
            rel = resolved.relative_to(r)
        except ValueError:      # not under this root — PurePath op, never OSError
            continue
        if len(rel.parts) > 1:
            return rel
    return None
'''

# `parse_artifacts`'s anchored `(none)` handling (Task 3's shipped form) and the
# pre-Task-3 in-loop `return {}` form it replaced. WHOLE BLOCKS including the inline
# "# body is indented lines..." comment, which sits BETWEEN the guard and the loop
# and is required for each to be a CONTIGUOUS substring of its file.
NONE_NEW = '''    out = {}
    if _none_sentinel(body, "ARTIFACTS"):
        return {}
    # body is indented lines; skip blanks
    for raw in body:
        line = raw.strip()
        if not line:
            continue
'''
NONE_OLD = '''    out = {}
    # body is indented lines; skip blanks and "(none)"
    for raw in body:
        line = raw.strip()
        if not line:
            continue
        if line == "(none)":
            return {}
'''

# tier2_witness's C1-R3-S2 mirror, the insertion point row 13 sites round 3's
# witness-leg emission at.
MIRROR = ('            if notes_out is not None:\n'
          '                notes_out.extend(notes_ambiguous)\n')

# --------------------------------------------------------------------------- #
# Reverted builds. These shipped in this arc and were reverted, so they exist
# nowhere else in the tree: this file is their source of truth.
# --------------------------------------------------------------------------- #

ROUND5_BODY = '''    best = None
    for r in _as_roots(root):
        for base in (r, _git_toplevel(r)):
            if base is None:
                continue
            try:
                rel = resolved.relative_to(base.resolve())
            except (ValueError, OSError):
                continue
            if best is None or len(rel.parts) < len(best.parts):
                best = rel
    return best if best is not None and len(best.parts) > 1 else None
'''
ROUND6_BODY = '''    best = None
    for r in _as_roots(root):
        closest = None
        for base in (r, _git_toplevel(r)):
            if base is None:
                continue
            try:
                rel = resolved.relative_to(base.resolve())
            except (ValueError, OSError):
                continue
            if closest is None or len(rel.parts) < len(closest.parts):
                closest = rel
        if closest is None or len(closest.parts) <= 1:
            continue
        if best is None or len(closest.parts) < len(best.parts):
            best = closest
    return best
'''
# Round 3's witness-leg form: sited BELOW the `resolved is None` early return (so it
# needs no None guard) and routed into `notes_refused`, i.e. onto the return value
# _verify_single discards.
ROUND3_WIT = '''            _rel = _below_top_level(resolved, root)
            if _rel is not None:
                notes_refused = notes_refused + [_walk_note(art_name, _rel)]
                if cov is not None:
                    cov.bump("resolved-by-walk")
'''

# --------------------------------------------------------------------------- #
# Class shorthands, so an expect set reads one line per class rather than two per
# test.
# --------------------------------------------------------------------------- #

PROV = "TestATraceNameAbsentFromArtifactsIsNotSilent"
KEYED = "TestTheNoteIsKeyedOnVerifiedBasenames"
PTRUNC = "TestTheNoteSurvivesATruncatedRun"
ESC = "TestTheNoteEscapesTheLeastConstrainedNameInTheGrammar"
HARDFAIL = "TestAnUnresolvablePathShapedArtifactStillFailsUnderStrict"
CLI = "TestTheNoneSentinelCannotEmptyArtifactsAtTheCli"
BODY = "TestTheNoneSentinelIsAnchoredToASingleLineBody"
BELOW = "TestABelowTopLevelResolutionIsCounted"
WTRUNC = "TestTheWalkNoteSurvivesATruncatedRun"
WSTRICT = "TestTheWitnessLegsWalkNoteSurvivesTheStrictAmbiguityRaise"
ASTRICT = "TestTheArtifactsLegsWalkNoteSurvivesTheStrictAmbiguityRaise"
MIRRORARM = "TestNoCallerSuppliedParameterCanMaskAnInFlightRaise"
TOPLVL = "TestATopLevelResolutionIsNotCounted"
NESTED = "TestASecondNestedRootDoesNotSilenceTheCounter"
GITTOP = "TestAnotherRootsGitToplevelDoesNotFlagATopLevelName"
COLLISION = "TestTheBasenameKeyIsSilentOnASameBasenameCollision"

# Task 5's five review rounds grew this suite from 54 to 160 tests, and the new
# classes reach these mutants too. Every class named in any `expect` set below has a
# shorthand here, so a set reads one line per class.
MALFORM = "TestAMalformedTraceEntryCannotMaskAnInFlightRaise"
NONSTR = "TestANonStringArtifactsKeyCannotMaskAnInFlightRaise"
EMITMASK = "TestTheEmitterCannotMaskAnInFlightRaise"
EMITSHAPE = "TestTheEmitterCannotRaiseOutOfTheFinallyOnAnyShape"
SLASHTRUNC = "TestTheTruncationRuleHoldsForSlashSuffixedNames"
CLEANPATH = "TestTheEmitterGuardsLayerCorrectlyOnTheCleanPath"
COFIRE = "TestTheWalkNoteAndTheProvenanceNoteCoFire"
SCALE = "TestTheTruncationPartitionHoldsAtScale"
TWINS = "TestTwoArtifactsKeysWithTheSameSpellingDoNotMerge"
TRAILSLASH = "TestATrailingSlashArtifactNameCannotSilenceUnrelatedNames"
SIBLING = "TestAVerifiedSiblingCannotSilenceADeclaredUnverifiedName"
EVERY = "TestEveryBelowTopLevelEntryInOneRunIsCountedAndNoted"
SYMLINK = "TestABareBasenameResolvedThroughASymlinkStillFires"
DISJOINT = "TestALaterDisjointRootAnswersTheDepthKey"
RELHALF = "TestTheRelpathHalfAloneCannotForgeTheChannel"
WESC = "TestTheWalkNoteEscapesTheNameHalfToo"
WMISMATCH = "TestTheWalkNoteSurvivesAMismatchRaiseOnItsOwnEntry"
GITDEEP = "TestAGitToplevelDeepResolutionIsSilent"
WITMASK = "TestNoHostileNotesOutCanMaskTheWitnessLegsInFlightRaise"
EXACTSENT = "TestOnlyTheExactSentinelIsEverTreatedAsOne"
INLINEHDR = "TestTheSentinelRuleReachesTheInlineHeaderBodyShape"


def E(*groups):
    """(class, *methods) groups -> the set of qualified `Class.method` ids."""
    return {f"{c}.{m}" for c, *ms in groups for m in ms}


BASELINE = dict(id=0, criterion="baseline", what="unmutated finished build",
                edits=[], expect=set())

MUTANTS = [
    # Three, not two: T6's own two pins PLUS the Task-4-owned truncation pin that
    # exercises the same raise. That is why row 1's set is larger than T6's pin count.
    dict(id=1, criterion="AC-6 T6", what="the --strict path-shaped raise disabled",
         edits=[("    if strict and is_path_shaped(name):",
                 "    if False and strict and is_path_shaped(name):")],
         expect=E((CLI,
                   "test_the_honest_receipt_hard_fails_on_the_path_shaped_name"),
                  (EMITMASK,
                   "test_a_none_trace_does_not_mask_an_in_flight_lint_error",
                   "test_the_control_shows_the_same_call_really_reaches_the_emitter"),
                  (EMITSHAPE,
                   "test_a_generator_that_raises_mid_iteration_loses_only_the_rest",
                   "test_a_hostile_entry_object_cannot_raise_out_of_the_emitter",
                   "test_a_truthy_non_iterable_trace_does_not_replace_the_lint_error",
                   "test_an_artifacts_key_whose_str_raises_cannot_mask_the_lint_error",
                   "test_one_malformed_entry_does_not_cost_the_other_entries_their_notes",
                   "test_the_control_shows_a_well_formed_trace_still_emits"),
                  (HARDFAIL,
                   "test_the_strict_run_hard_fails_and_says_which_name_and_why"),
                  (MALFORM,
                   "test_no_malformed_entry_shape_replaces_the_real_lint_error",
                   "test_the_control_shows_the_same_call_really_reaches_the_emitter"),
                  (MIRRORARM,
                   "test_all_three_caller_supplied_parameters_hostile_at_once",
                   "test_no_hostile_notes_out_shape_replaces_the_real_lint_error",
                   "test_the_mirror_arm_still_delivers_the_notes_it_exists_for",
                   "test_the_walk_note_site_is_actually_reached_by_this_fixture"),
                  (NONSTR,
                   "test_it_does_not_mask_on_the_production_notes_requested_shape",
                   "test_it_does_not_mask_when_the_caller_wants_no_notes",
                   "test_the_whole_finally_body_is_skipped_when_no_notes_were_asked_for"),
                  (PTRUNC,
                   "test_truncation_by_the_strict_path_shaped_raise_behaves_identically"),
                  (SLASHTRUNC,
                   "test_a_never_reached_slash_suffixed_name_stays_silent",
                   "test_an_undeclared_slash_suffixed_name_still_speaks"))),

    # A literal key also mislabels the collision fixture's verified `ARTIFACTS` name
    # (`chunk-A/fix-journal.md`) against its own TRACE forms, so COLLISION reddens
    # here too -- measured, not predicted from the class's stated subject.
    #
    # The match anchor is the CURRENT two-line `if base and (...)` form (the empty-
    # basename guard landed after the plan's text was written); the mutation is the
    # same one the plan names -- key the verified test on the LITERAL name.
    dict(id=2, criterion="AC-6 T2 leg 4", what="the literal parts[0] key",
         edits=[("                    if base and (base in verified_bases\n"
                 "                                 or base in unevaluated_bases):",
                 "                    if name in verified_bases or base in unevaluated_bases:"),
                ("                verified_bases.add(vbase)",
                 "                verified_bases.add(str(name))")],
         expect=E((CLEANPATH,
                   "test_a_real_list_receives_the_note_and_the_run_is_clean",
                   "test_the_fixture_produces_no_provenance_note"),
                  (COFIRE,
                   "test_both_channels_fire_and_neither_suppresses_the_other",
                   "test_the_two_channels_interleave_in_production_order"),
                  (COLLISION,
                   "test_the_collision_is_silent"),
                  (KEYED,
                   "test_a_trace_absolute_path_of_a_verified_artifact_emits_nothing",
                   "test_a_trace_name_matching_an_unresolved_artifact_still_emits_the_note"),
                  (SLASHTRUNC,
                   "test_an_undeclared_slash_suffixed_name_still_speaks"))),

    # The build stays SILENT where the rule demands a note -- the failure direction
    # grudge e0f0a6b75692 names.
    dict(id=3, criterion="AC-6 T2 leg 5", what="the verified-BLIND basename key",
         edits=[("                    trace, verified_bases,\n",
                 '                    trace, {str(n).rsplit("/", 1)[-1] for n in artifacts},\n')],
         expect=E((KEYED,
                   "test_a_trace_name_matching_a_hash_mismatched_artifact_still_emits_the_note",
                   "test_a_trace_name_matching_an_unresolved_artifact_still_emits_the_note"),
                  (PTRUNC,
                   "test_truncation_by_hash_mismatch_keeps_the_evaluated_half_audible",
                   "test_truncation_by_the_strict_path_shaped_raise_behaves_identically"))),

    # The `finally:` still fills `_late`; the `return` that would carry it never runs.
    # Rows 4 and 5 fail the SAME tests from OPPOSITE directions -- #4 loses the
    # evaluated half, #5 invents the un-evaluated one -- which is why leg 6 counts as
    # two copies in AC-6's arithmetic, and why one build plus a coincidence would not do.
    dict(id=4, criterion="AC-6 T2 leg 6 (build 1)", what="notes returned BY VALUE",
         edits=[("    evaluated = set()\n", "    evaluated = set()\n    _late = []\n"),
                ("                    {str(n) for n in evaluated if n not in verified_keys},\n"
                 "                    notes_out)",
                 "                    {str(n) for n in evaluated if n not in verified_keys},\n"
                 "                    _late)"),
                # NOT the bare `    return notes`: anchors are matched with `str.count`,
                # and that string is a SUBSTRING of `        return notes_ambiguous + ...`
                # in tier2_witness, so the bare form counts 2 and trips `_apply`'s
                # uniqueness clause. The surrounding newlines make it exact.
                ("\n    return notes\n", "\n    return notes + _late\n")],
         expect=E((EMITMASK,
                   "test_the_control_shows_the_same_call_really_reaches_the_emitter"),
                  (EMITSHAPE,
                   "test_a_generator_that_raises_mid_iteration_loses_only_the_rest",
                   "test_a_hostile_entry_object_cannot_raise_out_of_the_emitter",
                   "test_one_malformed_entry_does_not_cost_the_other_entries_their_notes",
                   "test_the_control_shows_a_well_formed_trace_still_emits"),
                  (KEYED,
                   "test_a_trace_name_matching_a_hash_mismatched_artifact_still_emits_the_note"),
                  (MALFORM,
                   "test_the_control_shows_the_same_call_really_reaches_the_emitter"),
                  (MIRRORARM,
                   "test_the_mirror_arm_still_delivers_the_notes_it_exists_for"),
                  (NONSTR,
                   "test_it_does_not_mask_on_the_production_notes_requested_shape"),
                  (PTRUNC,
                   "test_truncation_by_hash_mismatch_keeps_the_evaluated_half_audible",
                   "test_truncation_by_the_strict_path_shaped_raise_behaves_identically"),
                  (SCALE,
                   "test_all_four_dispositions_are_right_on_one_truncated_run"),
                  (SLASHTRUNC,
                   "test_an_undeclared_slash_suffixed_name_still_speaks",
                   "test_the_same_name_speaks_once_the_loop_actually_reaches_it"),
                  (TWINS,
                   "test_the_unverified_twin_keeps_its_note"))),

    # The truncation rule has TWO legs on the current build -- the exact-name leg
    # (`unevaluated_names`) and the basename leg (`unevaluated_bases`). Dropping the
    # RULE means dropping BOTH, which is why this row carries two edits where the
    # plan carried one.
    #
    # MEASURED three ways on the tip, because the reason matters more than the
    # verdict: both legs dropped (the form shipped here) reddens 4 pins; the plan's
    # literal single anchor -- the basename leg alone -- reddens 2, PTRUNC's pair,
    # which is exactly the expect set the plan itself recorded; the exact-name leg
    # alone reddens 1, SLASHTRUNC's never-reached name. So NEITHER single-leg copy is
    # vacuous. Each is simply a strictly weaker copy that drops half the rule instead
    # of the rule, and only the two-edit form reddens all four pins the rule owns.
    dict(id=5, criterion="AC-6 T2 leg 6 (build 2)", what="the truncation rule dropped",
         edits=[("                if name in unevaluated_names:\n"
                 "                    continue\n", ""),
                ("                    if base and (base in verified_bases\n"
                 "                                 or base in unevaluated_bases):",
                 "                    if base and base in verified_bases:")],
         expect=E((PTRUNC,
                   "test_truncation_by_hash_mismatch_keeps_the_evaluated_half_audible",
                   "test_truncation_by_the_strict_path_shaped_raise_behaves_identically"),
                  (SCALE,
                   "test_all_four_dispositions_are_right_on_one_truncated_run"),
                  (SLASHTRUNC,
                   "test_a_never_reached_slash_suffixed_name_stays_silent"))),

    dict(id=6, criterion="AC-6 T2 leg 7", what="raw name interpolation (no _show_path)",
         edits=[('                    f"PROVENANCE-ONLY: {_show_path(name)} "',
                 '                    f"PROVENANCE-ONLY: {name} "')],
         expect=E((ESC,
                   "test_neither_the_nul_nor_the_ansi_escape_reaches_the_channel_raw"))),

    # The copy round 1 substituted away. "The shipped build is the named broken copy"
    # is a DIFFERENT failure set for T2's verb scoping: the shipped build fails Task
    # 4's, the genuine verb-keyed build fails these. AC-6 T2 mandates this one.
    dict(id=7, criterion="AC-6 T2", what="the VERB-keyed build (READ dropped)",
         edits=[('_PROVENANCE_VERBS = frozenset({"READ", "EDIT", "WROTE"})',
                 '_PROVENANCE_VERBS = frozenset({"EDIT", "WROTE"})')],
         expect=E((COFIRE,
                   "test_both_channels_fire_and_neither_suppresses_the_other",
                   "test_the_two_channels_interleave_in_production_order"),
                  (EMITMASK,
                   "test_the_control_shows_the_same_call_really_reaches_the_emitter"),
                  (EMITSHAPE,
                   "test_a_generator_that_raises_mid_iteration_loses_only_the_rest",
                   "test_a_hostile_entry_object_cannot_raise_out_of_the_emitter",
                   "test_one_malformed_entry_does_not_cost_the_other_entries_their_notes",
                   "test_the_control_shows_a_well_formed_trace_still_emits",
                   "test_the_emitter_itself_swallows_a_non_iterable_trace"),
                  (ESC,
                   "test_neither_the_nul_nor_the_ansi_escape_reaches_the_channel_raw",
                   "test_the_hostile_trace_name_is_still_reported"),
                  (KEYED,
                   "test_a_trace_name_matching_a_hash_mismatched_artifact_still_emits_the_note",
                   "test_a_trace_name_matching_an_unresolved_artifact_still_emits_the_note"),
                  (MALFORM,
                   "test_the_control_shows_the_same_call_really_reaches_the_emitter"),
                  (MIRRORARM,
                   "test_the_mirror_arm_still_delivers_the_notes_it_exists_for"),
                  (NONSTR,
                   "test_it_does_not_mask_on_the_production_notes_requested_shape"),
                  (PROV,
                   "test_a_read_only_name_emits_the_note"),
                  (PTRUNC,
                   "test_truncation_by_hash_mismatch_keeps_the_evaluated_half_audible",
                   "test_truncation_by_the_strict_path_shaped_raise_behaves_identically"),
                  (SCALE,
                   "test_all_four_dispositions_are_right_on_one_truncated_run"),
                  (SIBLING,
                   "test_the_control_without_the_colliding_sibling_emits_the_note",
                   "test_the_trace_citation_of_that_same_name_still_emits_the_note"),
                  (SLASHTRUNC,
                   "test_an_undeclared_slash_suffixed_name_still_speaks",
                   "test_the_same_name_speaks_once_the_loop_actually_reaches_it"),
                  (TRAILSLASH,
                   "test_an_unrelated_trace_name_ending_in_a_slash_still_emits_the_note",
                   "test_the_control_without_the_trailing_slash_emits_the_note"),
                  (TWINS,
                   "test_the_unverified_twin_keeps_its_note"))),

    # The single-root control is what tells this copy apart from row 15: dropping the
    # key breaks the base case, readmitting derived bases does not.
    dict(id=8, criterion="AC-6 T7 leg 2", what="the depth key dropped (fires on every resolution)",
         edits=[("        if len(rel.parts) > 1:\n            return rel\n",
                 "        return rel\n")],
         expect=E((ASTRICT,
                   "test_without_strict_the_note_and_the_counter_both_fire"),
                  (EVERY,
                   "test_each_below_top_level_entry_gets_its_own_note_in_declaration_order",
                   "test_the_counter_accumulates_across_entries",
                   "test_the_top_level_sibling_stays_silent_in_the_same_run"),
                  (GITTOP,
                   "test_no_note_is_emitted",
                   "test_the_single_root_control_is_silent_too",
                   "test_the_sub_count_stays_zero",
                   "test_the_verdict_does_not_depend_on_root_ORDER"),
                  (NESTED,
                   "test_the_nested_root_does_not_silence_the_note"),
                  (TOPLVL,
                   "test_no_note_is_emitted",
                   "test_the_sub_count_stays_zero"),
                  (WTRUNC,
                   "test_a_later_hash_mismatch_does_not_silence_the_earlier_walk_note"))),

    # The witness leg's copy is left in place, which is what makes this row separable
    # from 10. `_rel = None` rather than deleting the emission block: Task 5's round-3
    # fix wrapped both legs' emission in `_emit_walk_note` and interleaved the block
    # with explanatory comments, so the block is no longer a comment-free contiguous
    # run. Nulling the depth result is the same copy by construction -- neither the
    # `cov.bump` nor the note runs -- without pinning this file to the wording of
    # twenty lines of comment.
    dict(id=9, criterion="AC-6 T7 leg 2", what="the artifacts leg goes silent",
         edits=[("            _rel = _below_top_level(resolved, root)\n",
                 "            _rel = None\n")],
         expect=E((ASTRICT,
                   "test_the_strict_raise_does_not_silence_them",
                   "test_without_strict_the_note_and_the_counter_both_fire"),
                  (BELOW,
                   "test_a_below_top_level_clause_one_resolution_emits_the_note",
                   "test_the_census_carries_a_resolved_by_walk_sub_count"),
                  (CLEANPATH,
                   "test_a_none_out_parameter_still_counts_and_never_raises",
                   "test_a_raising_append_manufactures_no_verdict_on_the_clean_path",
                   "test_a_real_list_receives_the_note_and_the_run_is_clean",
                   "test_an_interrupt_is_not_swallowed_by_either_layer",
                   "test_the_fixture_produces_no_provenance_note"),
                  (COFIRE,
                   "test_both_channels_fire_and_neither_suppresses_the_other",
                   "test_the_census_counts_only_the_walk_channel",
                   "test_the_two_channels_interleave_in_production_order"),
                  (DISJOINT,
                   "test_the_non_containing_first_root_does_not_zero_the_counter",
                   "test_the_note_carries_the_relpath_from_the_second_root"),
                  (EVERY,
                   "test_each_below_top_level_entry_gets_its_own_note_in_declaration_order",
                   "test_the_counter_accumulates_across_entries",
                   "test_the_thirty_one_component_relpath_renders_untruncated"),
                  (MIRRORARM,
                   "test_the_mirror_arm_still_delivers_the_notes_it_exists_for",
                   "test_the_walk_note_site_is_actually_reached_by_this_fixture"),
                  (NESTED,
                   "test_the_nested_root_does_not_silence_the_note",
                   "test_the_nested_root_does_not_zero_the_counter",
                   "test_the_verdict_does_not_depend_on_root_ORDER"),
                  (RELHALF,
                   "test_the_hostile_relpath_renders_fully_escaped",
                   "test_the_run_completes_and_the_note_fires"),
                  (SYMLINK,
                   "test_the_note_and_the_counter_both_fire"),
                  (WESC,
                   "test_both_halves_of_the_note_render_escaped",
                   "test_the_ansi_escape_never_reaches_the_channel_raw"),
                  (WMISMATCH,
                   "test_the_note_for_the_raising_entry_survives_exactly_once",
                   "test_the_unreached_entry_contributes_no_note_and_no_count"),
                  (WTRUNC,
                   "test_a_later_hash_mismatch_does_not_silence_the_earlier_walk_note"))),

    # Several `test_the_run_completes` are in this set because `cov.bump("resolved-by-
    # walk")` now keys into a dict the tuple no longer seeds: the run RAISES rather
    # than mis-renders, which is why this copy is worth constructing separately from
    # #9. TOPLVL's and GITTOP's `test_the_run_completes` stay green -- neither fixture
    # reaches the bump. COLLISION's `test_the_collision_is_silent` joins this
    # raises-rather-than-mis-renders set for the same reason: its fixture cites
    # `chunk-A/fix-journal.md`, a below-top-level resolution on the ARTIFACTS leg, so
    # it reaches the same `cov.bump` KeyError -- not predictable from the class's
    # stated subject, only from tracing which fixtures reach the bump.
    #
    # The anchor is the counter's own name-bearing SUBSTRING, not the tuple's full
    # source line: a full-line anchor stales the moment a NINTH counter is inserted
    # anywhere else in `_COV_COUNTERS`. `'"resolved-by-walk", '` occurs exactly once
    # in the finished build regardless of what else the tuple gains (`cov.bump(
    # "resolved-by-walk")` ends in `)`, not `, `), and deleting it produces the
    # byte-identical result a full-line anchor would.
    dict(id=10, criterion="AC-6 T7 leg 2", what="the counter dropped from the census",
         edits=[('"resolved-by-walk", ', '')],
         expect=E((ASTRICT,
                   "test_the_strict_raise_does_not_silence_them",
                   "test_without_strict_the_note_and_the_counter_both_fire"),
                  (BELOW,
                   "test_a_below_top_level_clause_one_resolution_emits_the_note",
                   "test_the_census_carries_a_resolved_by_walk_sub_count",
                   "test_the_run_completes",
                   "test_the_sub_count_is_reported_beside_the_floor_and_not_summed_into_it"),
                  (CLEANPATH,
                   "test_a_none_out_parameter_still_counts_and_never_raises",
                   "test_a_raising_append_manufactures_no_verdict_on_the_clean_path",
                   "test_a_real_list_receives_the_note_and_the_run_is_clean",
                   "test_an_interrupt_is_not_swallowed_by_either_layer",
                   "test_the_fixture_produces_no_provenance_note"),
                  (COFIRE,
                   "test_both_channels_fire_and_neither_suppresses_the_other",
                   "test_the_census_counts_only_the_walk_channel",
                   "test_the_run_completes",
                   "test_the_two_channels_interleave_in_production_order"),
                  (COLLISION,
                   "test_the_collision_is_silent"),
                  (DISJOINT,
                   "test_the_non_containing_first_root_does_not_zero_the_counter",
                   "test_the_note_carries_the_relpath_from_the_second_root",
                   "test_the_run_completes"),
                  (EVERY,
                   "test_each_below_top_level_entry_gets_its_own_note_in_declaration_order",
                   "test_the_counter_accumulates_across_entries",
                   "test_the_run_completes_and_every_entry_verified",
                   "test_the_thirty_one_component_relpath_renders_untruncated"),
                  (GITDEEP,
                   "test_the_sub_count_stays_zero"),
                  (GITTOP,
                   "test_the_single_root_control_is_silent_too",
                   "test_the_sub_count_stays_zero",
                   "test_the_verdict_does_not_depend_on_root_ORDER"),
                  (MIRRORARM,
                   "test_the_walk_note_site_is_actually_reached_by_this_fixture"),
                  (NESTED,
                   "test_the_nested_root_does_not_silence_the_note",
                   "test_the_nested_root_does_not_zero_the_counter",
                   "test_the_run_completes",
                   "test_the_verdict_does_not_depend_on_root_ORDER"),
                  (RELHALF,
                   "test_the_hostile_relpath_renders_fully_escaped",
                   "test_the_run_completes_and_the_note_fires"),
                  (SIBLING,
                   "test_the_run_says_out_loud_that_the_cited_name_is_unverified",
                   "test_the_trace_citation_of_that_same_name_still_emits_the_note"),
                  (SYMLINK,
                   "test_the_note_and_the_counter_both_fire"),
                  (TOPLVL,
                   "test_the_sub_count_stays_zero"),
                  (WESC,
                   "test_both_halves_of_the_note_render_escaped",
                   "test_the_ansi_escape_never_reaches_the_channel_raw"),
                  (WITMASK,
                   "test_the_counter_and_the_note_cannot_disagree"),
                  (WMISMATCH,
                   "test_the_mismatch_is_the_verdict",
                   "test_the_note_for_the_raising_entry_survives_exactly_once",
                   "test_the_unreached_entry_contributes_no_note_and_no_count"),
                  (WSTRICT,
                   "test_the_strict_raise_does_not_silence_them",
                   "test_without_strict_the_note_and_the_counter_both_fire"),
                  (WTRUNC,
                   "test_a_later_hash_mismatch_does_not_silence_the_earlier_walk_note"))),

    dict(id=11, criterion="AC-6 T10 CLI leg + T6's (none)-defeat leg",
         what="the (none) sentinel un-anchored in parse_artifacts, D6 off",
         edits=[(NONE_NEW, NONE_OLD),
                ('    if witness["kind"] == "grep" and witness["range_kind"] is not None:',
                 '    if False and witness["kind"] == "grep" '
                 'and witness["range_kind"] is not None:')],
         expect=E((BODY,
                   "test_artifacts_none_after_an_entry_is_a_lint_error",
                   "test_artifacts_none_before_an_entry_is_a_lint_error",
                   "test_the_sentinel_raise_precedes_the_name_legality_raise",
                   "test_two_artifacts_nones_are_a_lint_error"),
                  (CLI,
                   "test_one_injected_none_line_cannot_turn_that_hard_fail_into_exit_zero"),
                  (EXACTSENT,
                   "test_a_nbsp_cloaked_sentinel_is_still_bound_by_the_co_occurrence_rule"),
                  (INLINEHDR,
                   "test_a_sentinel_on_the_header_line_still_binds_the_indented_entry",
                   "test_an_entry_on_the_header_line_still_binds_the_indented_sentinel"))),

    # Row 4's exact analogue for the walk note. The census still reads
    # `resolved-by-walk 1` while stderr carries zero RESOLVED-BY-WALK: lines. Rows 4
    # and 12 fail DIFFERENT tests despite being the same defect in two note families:
    # the PROVENANCE-ONLY family is emitted from a `finally:` and so is dropped only by
    # the return-value routing, while the walk note is emitted mid-loop and needs its
    # own truncation fixture to see it.
    #
    # TWO edits, not one. Round-4-of-this-gate's S1 added a second, independent rescue
    # for the same fact this row's mutation severs: tier2_artifacts's `except
    # BaseException:` arm mirrors the leg's own `notes` onto `notes_out` on ANY raise,
    # so a build that only re-routes the walk note onto `notes` still gets it onto
    # `notes_out` via that arm before the raise propagates -- the row stops
    # discriminating. The second edit severs that mirror in THIS ROW'S COPY ONLY,
    # reproducing the pre-S1 shipped shape row 12 is named for. It neuters the arm's
    # `.extend` rather than deleting the whole arm: the arm is now thirty-odd lines of
    # which three are code, and the observable difference between "no arm" and "an arm
    # that mirrors nothing" is nil -- the `raise` re-raises either way.
    dict(id=12, criterion="AC-6 T7 leg 2",
         what="round 2's build: artifacts note on the RETURN VALUE, AND the "
              "round-4-of-this-gate S1 rescue arm severed",
         edits=[("                _emit_walk_note(notes_out, name, _rel)\n",
                 "                notes.append(_walk_note(name, _rel))\n"),
                ("            if notes_out is not None:\n"
                 "                notes_out.extend(notes)\n",
                 "            pass\n")],
         expect=E((ASTRICT,
                   "test_the_strict_raise_does_not_silence_them"),
                  (CLEANPATH,
                   "test_a_real_list_receives_the_note_and_the_run_is_clean",
                   "test_an_interrupt_is_not_swallowed_by_either_layer",
                   "test_the_fixture_produces_no_provenance_note"),
                  (COFIRE,
                   "test_the_two_channels_interleave_in_production_order"),
                  (MIRRORARM,
                   "test_the_mirror_arm_still_delivers_the_notes_it_exists_for"),
                  (PTRUNC,
                   "test_truncation_by_hash_mismatch_keeps_the_evaluated_half_audible",
                   "test_truncation_by_the_strict_path_shaped_raise_behaves_identically"),
                  (WMISMATCH,
                   "test_the_note_for_the_raising_entry_survives_exactly_once",
                   "test_the_unreached_entry_contributes_no_note_and_no_count"),
                  (WTRUNC,
                   "test_a_later_hash_mismatch_does_not_silence_the_earlier_walk_note"))),

    # Rows 12 and 13 are both "the note is owed and the build is silent", but 12 loses
    # it to a CHANNEL (a return value nobody drains) and 13 to ORDERING (an emission
    # below a raise); neither failure set overlaps the other's. Row 13 is the only copy
    # whose discriminator is a FLAG rather than a fixture -- its non-vacuity sibling
    # `test_without_strict_...` stays GREEN. Measured, same receipt one flag apart: no
    # --strict, `ambiguous 1 ... resolved-by-walk 1` plus the note; --strict,
    # `resolved-by-walk 0 ... partial` and NO note.
    #
    # First edit nulls the in-place witness emission (see row 9 for why nulling rather
    # than deleting); second re-sites round 3's own emission below the ambiguity raise.
    dict(id=13, criterion="AC-6 T7 leg 2", what="round 3's build: witness emission BELOW the raise",
         edits=[("            _rel = (_below_top_level(resolved, root)\n"
                 "                    if resolved is not None else None)\n",
                 "            _rel = None\n"),
                (MIRROR, ROUND3_WIT + MIRROR)],
         expect=E((WITMASK,
                   "test_a_real_list_still_receives_the_note",
                   "test_the_counter_and_the_note_cannot_disagree"),
                  (WSTRICT,
                   "test_the_strict_raise_does_not_silence_them"))),

    # UNDER-fires on the supplied-roots key: NESTED's three pins redden, and its
    # `test_the_run_completes` sibling stays green (the run still exits 0; it goes
    # silent, it does not crash).
    #
    # MEASURED, and the plan's prose is stale here: this build is NOT purely an
    # under-fire. Admitting git toplevels into the depth key ALSO over-fires on a
    # resolution that is deep under a root's git toplevel but at that root's own top
    # level -- `TestAGitToplevelDeepResolutionIsSilent`, a class Task 5's review
    # rounds added after Task 7's plan text was written. That class is the ONE overlap
    # between rows 14 and 15: it catches the derived-base admission both reverted
    # builds share. GITTOP's pins still separate them -- green here, red on 15 -- and
    # NESTED's still separate them the other way, so the pair remains a matched pair
    # that a build passing both is keyed on the SUPPLIED roots alone.
    dict(id=14, criterion="AC-6 T7 leg 2",
         what="round 5's build: ONE GLOBAL MINIMUM over roots and git toplevels",
         edits=[(DEPTH_BODY, ROUND5_BODY)],
         expect=E((GITDEEP,
                   "test_no_note_is_emitted",
                   "test_the_sub_count_stays_zero"),
                  (NESTED,
                   "test_the_nested_root_does_not_silence_the_note",
                   "test_the_nested_root_does_not_zero_the_counter",
                   "test_the_verdict_does_not_depend_on_root_ORDER"))),

    # OVER-fires -- a note emitted where silence is owed. GITTOP's
    # `test_the_single_root_control_is_silent_too` stays green (no build in this arc
    # gets that one wrong), and BOTH under-fire pins in row 14's class stay green,
    # because round 6's build fixed that direction. It shares
    # `TestAGitToplevelDeepResolutionIsSilent` with row 14 and nothing else; see row
    # 14's comment for why that overlap is the derived-base admission itself.
    dict(id=15, criterion="AC-6 T7 leg 2",
         what="round 6's build: per root, that root's OWN CLOSEST BASE",
         edits=[(DEPTH_BODY, ROUND6_BODY)],
         expect=E((GITDEEP,
                   "test_no_note_is_emitted",
                   "test_the_sub_count_stays_zero"),
                  (GITTOP,
                   "test_no_note_is_emitted",
                   "test_the_sub_count_stays_zero",
                   "test_the_verdict_does_not_depend_on_root_ORDER"))),
]


def _build_tree():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="dec31-"))
    for d in COPY_DIRS:
        shutil.copytree(REPO / d, tmp / d,
                        ignore=shutil.ignore_patterns("__pycache__"))
    return tmp


def _run_row(row):
    """Returns (tree, actual-failing-id-set, raw-output).

    Any early abort -- a stale anchor's `SystemExit`, or anything else raised
    between building the tree and reading the run -- prints this row's tree path
    before propagating. Without it the abort path orphans a ~13MB tree silently
    while the ordinary failing-row path prints its own, which is the opposite of
    the contract: a row that aborted is exactly the one whose copy you want to
    look at. The failure still propagates, so the exit stays non-zero."""
    tree = _build_tree()
    try:
        _apply(tree / "scripts" / "rcpt_verify.py", row["edits"])
        proc = subprocess.run([sys.executable, SUITE], cwd=tree,
                              capture_output=True, text=True)
    except BaseException:
        print(f"row {row['id']:>2}  ABORTED before a verdict; "
              f"tree kept for inspection: {tree}", flush=True)
        raise
    return tree, _ids(proc.stdout + proc.stderr), proc.stdout + proc.stderr


def main():
    bad = 0
    for row in [BASELINE] + MUTANTS:
        tree, actual, out = _run_row(row)
        label = f"row {row['id']:>2}  {row['criterion']:<38}  {row['what']}"
        problems = []
        if f"Ran {TOTAL_TESTS} tests" not in out:
            ran = re.search(r"^Ran (\d+) tests", out, re.M)
            problems.append(
                f"  test COUNT moved: expected {TOTAL_TESTS}, saw "
                f"{ran.group(1) if ran else '<no Ran line>'} "
                f"-- the tree is broken, not a pin")
        unexpected = sorted(actual - row["expect"])
        missing = sorted(row["expect"] - actual)
        if unexpected:
            problems.append("  unexpected (fired, not expected): "
                            + ", ".join(unexpected))
        if missing:
            problems.append("  missing (did NOT fire -- vacuity signal): "
                            + ", ".join(missing))
        if problems:
            bad += 1
            print(f"{label}  red={len(actual)} -- FAILED")
            for p in problems:
                print(p)
            print(f"  tree kept for inspection: {tree}")
        else:
            print(f"{label}  red={len(actual)} -- ok")
            shutil.rmtree(tree, ignore_errors=True)
    if bad:
        print(f"\ndec31_sweep: {bad} row(s) no longer discriminate as recorded.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
