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
A kept tree is MOVED to `<repo>/.dec31-keep/row-<id>/` before its path is printed.
`tempfile.mkdtemp` resolves against `$TMPDIR`, and `scripts/run_tests.sh` -- the one
entry point CLAUDE.md mandates and CI invokes -- scopes `$TMPDIR` per invocation and
`rm -rf`s it from an EXIT trap, so a tree left where it was BUILT is deleted before
anyone can read the path naming it: through the gating harness the keep-on-failure
contract was void, and on CI the one artifact explaining a red row was already gone.
`.dec31-keep/` is gitignored and is CLEARED at the start of every run, so kept trees
are bounded by one run's failures rather than accumulating across a session.

A row whose anchor no longer occurs exactly once is its own verdict -- `ANCHOR-STALE`
-- not a process abort: it is recorded, the sweep CONTINUES to the next row, and the
final summary lists every anchor-stale row with each anchor's expected vs. actual
occurrence count. That is load-bearing. The abort it replaces was a `SystemExit` out
of `_apply`, so one behaviour-preserving edit to `rcpt_verify.py` (a rewrap, an
autoformatter, a renamed local) silently dropped every row ordered AFTER it, with
nothing on the channel saying which pins went unchecked. Measured both ways: one
extra space inside row 1's anchor took the sweep from 16 rows evaluated to 2, and a
real parser fix on this branch aborted it at row 5, skipping rows 6-15. An
anchor-stale row still exits non-zero -- something moved, and that is a signal.

Every `expect` set below is MEASURED against the tree as it stands, never
transcribed from the plan: Task 5's five review rounds grew
`scripts/test_488_name_space.py` from 54 tests to 160, and temper leg-1 grew it
again to 168; the plan's own tables were written before that. When the suite
legitimately gains a test, this file goes red only where that test actually
reaches a mutation -- as `unexpected` on that row -- and the fix is to RE-MEASURE
and record what is true now, never to widen a set until it stops complaining. (The
suite's test COUNT is deliberately NOT among the things recorded here; see `_RAN`.)
A set that has to LOSE a member is
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
# Where a FAILING row's tree is moved to before its path is printed. Inside the
# checkout on purpose (`.gitignore` carries it); see `_keep`.
KEEP_DIR = REPO / ".dec31-keep"

# The whole suite must still be COLLECTED on every mutant row: a mutation that moves
# the NUMBER of tests collected has broken the tree, not a pin. That count is DERIVED
# per run, from row 0 -- the unmutated baseline, which is by construction the right
# count for whatever tree this is -- and is never pinned to a literal. A literal was
# tried and does not survive contact with this repo: it is a snapshot of
# `scripts/test_488_name_space.py`, the file every task, review round and fix in this
# build appends to, and it had already been hand-bumped twice on this branch alone
# (160 -> 168 -> 174). The churn was the smaller half. The message was the larger: a
# pin that had merely gone STALE failed all sixteen rows with `the tree is broken,
# not a pin`, blaming `scripts/rcpt_verify.py` for an addition to a test file, and
# then went on to print per-row `unexpected`/`missing` diffs computed against a tree
# it had just declared broken -- noise shaped exactly like the vacuity signal this
# harness exists to catch.
_RAN = re.compile(r"^Ran (\d+) tests?", re.M)   # `tests?`: unittest prints "1 test"

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


def _ran(text):
    """Tests COLLECTED by one row's run -- the `Ran N tests` count -- or None when
    the run never got as far as printing one.

    #488 warden-r2/F6 -- NOT "an import-time break in the copy", which is what this
    used to claim and which this suite's own shape rules out: `test_488_name_space.py`
    imports `rcpt_verify` LAZILY (`_import_rv()`, per test), so a mutation that makes
    the linter unimportable still collects the whole suite and still prints a `Ran`
    line -- the tests merely error. What actually produces None is the runner never
    reaching its summary at all: a mutation that breaks the TEST FILE's own import
    (none of the rows below touch it), or the subprocess dying first. Overstating the
    catch matters because `main` reports None as `<no Ran line>` and blames the
    row's mutation for breaking collection."""
    m = _RAN.search(text)
    return int(m.group(1)) if m else None


class StaleAnchor(Exception):
    """One row's anchors no longer occur exactly once in `rcpt_verify.py`.

    A ROW verdict, not a process abort -- see the module docstring. `.stale` is
    `[(anchor, occurrences), ...]` for EVERY anchor of that row that missed, not
    just the first, so one run reports everything that moved under the row."""

    def __init__(self, stale):
        self.stale = stale
        super().__init__(f"{len(stale)} anchor(s) no longer occur exactly once")


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
    than as a confusing failure count.

    `StaleAnchor`, not `SystemExit`: the raise is caught PER ROW by `main`, which
    records `ANCHOR-STALE` and moves to the next row. `SystemExit` here aborted the
    whole process, dropping every row ordered after the tripping one."""
    text = path.read_text()
    stale = []
    for anchor, _ in edits:
        n = text.count(anchor)
        if n != 1:
            stale.append((anchor, n))
    if stale:
        raise StaleAnchor(stale)
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
# inquisitor/D2 — the materialisation carries into NONE_NEW because the anchor is a
# contiguous block and `body = list(body)` sits inside it. NONE_OLD deliberately does
# NOT carry it: that build iterates `body` exactly once, which is why the drain did not
# exist before the sentinel helper did.
NONE_NEW = '''    out = {}
    # #488 inquisitor/D2 — materialise BEFORE the scan: `_none_sentinel` consumes
    # `body`, and the entry loop below iterates it again. See its docstring.
    body = list(body)
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
# inquisitor/D2 — only the CO-OCCURRENCE arm pins row 11. The two one-shot arms
# pass against that mutant for a real reason, not by coincidence: NONE_OLD iterates
# `body` exactly ONCE, so there is no drain to survive there. The drain is a
# property of the sentinel HELPER, which that build does not have.
ONESHOT = "TestAOneShotSectionBodyIsNotDrainedByTheSentinel"
INLINEHDR = "TestTheSentinelRuleReachesTheInlineHeaderBodyShape"
# temper/leg-1 — the degenerate-basename fail-open and the verified set's
# exact-name leg. DEGEN's `..` arm is driven by the `--strict` path-shaped
# raise (it needs a TRUNCATED run to populate `unevaluated_bases`), which is
# why it joins row 1's set and not only its own.
DEGEN = "TestADegenerateVerifiedBasenameCannotSilenceUnrelatedNames"
VERBATIM = "TestAVerifiedNameCitedVerbatimIsSilent"

# inquisitor/D1 — the unevaluated/unverified SPELLING collision. Both arms cite
# their TRACE entry with READ and read the note off the OUT-PARAMETER, so both go
# red under row 7's global silencer and row 4's by-value routing. The control
# going red alongside the defect arm is the point, the same way DEGEN's controls
# are: a class whose non-vacuity control survives a global silencer would be
# passing by coincidence.
UNEVALTWIN = "TestAnUnreachedTwinCannotSilenceAnEvaluatedUnverifiedName"

# inquisitor/AV1 (edge) — the exact-name override against §3.2's MANDATED absolute
# TRACE spelling. Two of its three arms cite with READ (row 7's silencer) and both
# declare a NESTED name, so both also resolve below a root's top level and go red
# when row 10 drops the walk sub-count from the census ordering. Its third arm
# (`test_a_verified_name_cited_absolutely_is_still_silent`) declares a TOP-LEVEL
# name and is in neither set, which is what keeps the two rows discriminating
# rather than merely large.
ABSSPELL = "TestTheExactNameOverrideSurvivesTheMandatedAbsoluteSpelling"

# warden-r2/F3 — ABSSPELL's fixture reached through a SYMLINKED `--root`. Same two
# legs, so it lands in the same two rows and for the same two reasons: BOTH arms
# cite with READ (row 7's silencer), and BOTH declare the same NESTED `a/x.md`, so
# both resolve below the root's top level and go red when row 10 drops the walk
# sub-count. Unlike ABSSPELL there is no third, top-level arm to leave out — this
# class is two arms, both in both rows.
SYMROOT = "TestTheExactNameOverrideSurvivesASymlinkedRoot"

# warden-r2/F4 — the root-join's degenerate-basename screen. Row 7 ONLY: both arms
# cite with READ and assert a note FIRES, so the global silencer reddens the defect
# arm and its non-vacuity control alike. Row 10 does NOT reach it — both declared
# names sit at a root's TOP LEVEL, so nothing resolves by walk and the dropped
# sub-count is never bumped. That asymmetry against SYMROOT above is measured, not
# assumed, and it is what keeps the two rows discriminating rather than merely large.
DEGENJOIN = "TestTheRootJoinDoesNotWidenADegenerateDeclaration"

# inquisitor/AV4 (edge) — the ACCEPTED-limitation pin on `_PROVENANCE_VERBS`. Only
# its READ non-vacuity CONTROL belongs to row 7: the class's other two arms assert
# SILENCE (a CONSULTED citation emits nothing, and the limitation is recorded in
# the source), and a build that silences READ satisfies both for free.
VERBSCOPE = "TestTheAdvisoryScopeIsDeliberatelyNarrowerThanTheTraceVerbSet"


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
                  (DEGEN,
                   "test_a_dotdot_suffixed_artifact_cannot_silence_an_undeclared_read"),
                  (SLASHTRUNC,
                   "test_a_never_reached_slash_suffixed_name_stays_silent",
                   "test_an_undeclared_slash_suffixed_name_still_speaks"))),

    # A literal key also mislabels the collision fixture's verified `ARTIFACTS` name
    # (`chunk-A/fix-journal.md`) against its own TRACE forms, so COLLISION reddens
    # here too -- measured, not predicted from the class's stated subject.
    #
    # The match anchor is the CURRENT three-line `if base not in _DEGENERATE_BASES
    # and (...)` form (the empty-basename guard landed after the plan's text was
    # written, and temper leg-1 widened it to the whole degenerate set); the
    # mutation is the same one the plan names -- key the verified test on the
    # LITERAL name.
    dict(id=2, criterion="AC-6 T2 leg 4", what="the literal parts[0] key",
         edits=[("                    if base not in _DEGENERATE_BASES and (\n"
                 "                            base in verified_bases\n"
                 "                            or base in unevaluated_bases):",
                 "                    if name in verified_bases or base in unevaluated_bases:"),
                ("                verified_bases.add(vbase)",
                 "                verified_bases.add(str(name))")],
         # #488 inquisitor (correctness fixer) — RE-MEASURED, and this row LOST six
         # pins: CLEANPATH's two, COFIRE's two, and KEYED's two. One cause for all
         # six, and it is a FIX rather than a rot: every one of them cites a
         # VERIFIED artifact by §3.2's absolute form, and the three exact-name sets
         # now carry that spelling (`_declared_spellings`), so the suppression
         # happens at the exact-name leg BEFORE the basename guard this row mutates
         # is ever consulted. The mutation is therefore genuinely less harmful than
         # it was — the literal-`parts[0]` key's headline cost (13 verified entries
         # mislabelled across the three corpora, `_emit_provenance_notes`'s first
         # bullet) is now covered by a second, independent mechanism — and the six
         # pins stopped discriminating because the behaviour they pin no longer
         # depends on the mutated key. The three that REMAIN all turn on the
         # basename key alone (a same-basename collision, a degenerate `..` base,
         # and a `/`-suffixed undeclared name), so the row still discriminates.
         expect=E((COLLISION,
                   "test_the_collision_is_silent"),
                  # temper/leg-1 — this mutation replaces the WHOLE widened guard,
                  # so the `_DEGENERATE_BASES` screening goes with it and the `..`
                  # silencing returns.
                  (DEGEN,
                   "test_a_dotdot_suffixed_artifact_cannot_silence_an_undeclared_read"),
                  (SLASHTRUNC,
                   "test_an_undeclared_slash_suffixed_name_still_speaks"))),

    # The build stays SILENT where the rule demands a note -- the failure direction
    # grudge e0f0a6b75692 names.
    dict(id=3, criterion="AC-6 T2 leg 5", what="the verified-BLIND basename key",
         edits=[("                    trace, verified_bases,\n",
                 '                    trace, {str(n).rsplit("/", 1)[-1] for n in artifacts},\n')],
         # #488 inquisitor (correctness fixer) — RE-MEASURED, one pin LOST:
         # KEYED's hash-mismatch arm. Same cause as row 2's six: it cites the
         # mismatched artifact by §3.2's absolute form, which `unverified_names`
         # now carries, and that override is tested BEFORE the basename key this
         # row blinds. The row still discriminates on the arm whose TRACE name is
         # NOT a spelling of any declared name (`/elsewhere/absent-bare.md`), which
         # no exact-name set can reach, plus PTRUNC's two.
         expect=E((KEYED,
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
                # The anchor carries temper leg-1's `verified_names` argument, which
                # sits BETWEEN `notes_out` and the close paren -- so the pre-leg-1
                # two-line form no longer occurs and would abort the row.
                #
                # #488 inquisitor (correctness fixer) -- RE-ANCHORED. The unverified
                # set is now built by `_declared_spellings` rather than by an inline
                # comprehension over `evaluated`, so the previous three-line literal
                # occurs 0x and this row went ANCHOR-STALE (its mutation unapplied,
                # its pins UNCHECKED). What the anchor has to pin is unchanged: the
                # `notes_out,` ARGUMENT POSITION, which is what the mutation swaps.
                ("                        all_roots, resolutions),\n"
                 "                    notes_out,\n",
                 "                        all_roots, resolutions),\n"
                 "                    _late,\n"),
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
                  # temper/leg-1 — both arms assert a note that this build routes onto
                  # the return value, so both lose it. VERBATIM's two silent arms stay
                  # green: a build that emits nothing satisfies "no note" for free,
                  # which is why only its speaking arm is here.
                  (DEGEN,
                   "test_a_dotdot_suffixed_artifact_cannot_silence_an_undeclared_read"),
                  (VERBATIM,
                   "test_an_unverified_spelling_still_speaks"),
                  (UNEVALTWIN,
                   "test_the_evaluated_unverified_name_keeps_its_note",
                   "test_the_control_without_the_unreached_twin_emits"),
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
         edits=[("                    if name in unevaluated_names:\n"
                 "                        continue\n", ""),
                ("                    if base not in _DEGENERATE_BASES and (\n"
                 "                            base in verified_bases\n"
                 "                            or base in unevaluated_bases):",
                 "                    if base not in _DEGENERATE_BASES and (\n"
                 "                            base in verified_bases):")],
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
                  # temper/leg-1 — every arm of both classes cites its TRACE entry with
                  # READ, so this build silences all of them. DEGEN loses all four (two
                  # defect arms plus both non-vacuity controls, which is the point: the
                  # controls are what make the class fail LOUDLY under a global silencer
                  # rather than passing by coincidence). VERBATIM loses only its
                  # speaking arm — its two silent arms are satisfied for free by a
                  # build that emits nothing.
                  (DEGEN,
                   "test_a_dot_suffixed_artifact_cannot_silence_an_undeclared_dot_read",
                   "test_a_dotdot_suffixed_artifact_cannot_silence_an_undeclared_read",
                   "test_the_control_with_a_plain_artifact_name_emits",
                   "test_the_control_with_a_plain_trace_name_emits"),
                  (VERBATIM,
                   "test_an_unverified_spelling_still_speaks"),
                  (UNEVALTWIN,
                   "test_the_evaluated_unverified_name_keeps_its_note",
                   "test_the_control_without_the_unreached_twin_emits"),
                  # #488 inquisitor (correctness fixer) — three pins GAINED, all
                  # new regression tests that cite their TRACE entry with READ.
                  (ABSSPELL,
                   "test_the_bare_declared_spelling_keeps_its_note",
                   "test_the_mandated_absolute_spelling_keeps_its_note_too"),
                  # #488 warden-r2 — four pins GAINED, same reason as the three
                  # above: every arm cites its TRACE entry with READ and asserts a
                  # note fires, so the global silencer reddens defect arms and
                  # non-vacuity controls alike.
                  (SYMROOT,
                   "test_the_realpath_spelling_keeps_its_note",
                   "test_the_as_supplied_symlinked_spelling_keeps_its_note_too"),
                  (DEGENJOIN,
                   "test_a_cross_root_degenerate_citation_is_not_silenced",
                   "test_an_ordinary_cross_root_citation_still_speaks"),
                  (VERBSCOPE,
                   "test_a_read_citation_of_an_undeclared_file_speaks"),
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
         # #488 inquisitor (correctness fixer) — two pins GAINED: ABSSPELL's two
         # nested-name arms resolve below a root's top level, so dropping the
         # sub-count from the census ordering reaches them. Its top-level arm does
         # not, and is deliberately absent.
         expect=E((ABSSPELL,
                   "test_the_bare_declared_spelling_keeps_its_note",
                   "test_the_mandated_absolute_spelling_keeps_its_note_too"),
                  # #488 warden-r2 — two pins GAINED. SYMROOT is ABSSPELL's fixture
                  # through a symlinked root, so both its arms declare the same
                  # nested `a/x.md` and reach this counter the same way. DEGENJOIN
                  # is deliberately ABSENT: its names are top-level, so no walk
                  # resolution happens and this mutation cannot reach it.
                  (SYMROOT,
                   "test_the_realpath_spelling_keeps_its_note",
                   "test_the_as_supplied_symlinked_spelling_keeps_its_note_too"),
                  (ASTRICT,
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
                  (ONESHOT,
                   "test_a_one_shot_body_mixing_the_sentinel_with_an_entry_still_raises"),
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


def _keep(tree, row_id):
    """Move a failing row's tree OUT of `$TMPDIR` and return where it now lives.

    Trees are built under `$TMPDIR`, which `scripts/run_tests.sh` scopes per
    invocation and deletes from an EXIT trap — so the path this sweep prints for a
    kept tree is dangling by the time the harness finishes, which is every CI run
    and the invocation CLAUDE.md mandates. `.dec31-keep/` is inside the checkout,
    gitignored, and outlives the trap. The `run_tests.sh` side is deliberately NOT
    touched: its TMPDIR scoping is load-bearing for other suites.

    A move that fails returns the ORIGINAL path rather than raising: a doomed path
    is still better than losing the row's verdict to an exception on the way out."""
    dest = KEEP_DIR / f"row-{row_id}"
    try:
        KEEP_DIR.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(dest, ignore_errors=True)
        shutil.move(str(tree), str(dest))
    except OSError:
        return tree
    return dest


def _build_tree():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="dec31-"))
    # #488 warden-r2/F5 — a copytree that raises part-way (an unreadable file under
    # a COPY_DIRS member, a full disk) used to orphan the partial tree in $TMPDIR
    # AND leave `_run_row` with no handle to keep or clean, because the assignment
    # had not happened yet. Nothing is kept here on purpose: a tree that never
    # finished building is not a mutation artefact worth inspecting, unlike the
    # ABORTED-after-build case `_run_row` prints.
    try:
        for d in COPY_DIRS:
            shutil.copytree(REPO / d, tmp / d,
                            ignore=shutil.ignore_patterns("__pycache__"))
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return tmp


def _run_row(row):
    """Returns (tree, actual-failing-id-set, raw-output).

    Raises `StaleAnchor` when this row's anchors moved. `main` catches it per row.
    That row's tree is DISCARDED rather than kept: `_apply` checks every anchor
    before substituting any, so the copy is byte-identical to the shipped build and
    has nothing in it to inspect — the anchor text and its occurrence count, which
    the verdict prints, are the whole diagnostic.

    Any OTHER early abort -- anything raised between building the tree and reading
    the run -- moves this row's tree to `.dec31-keep/` and prints it before
    propagating. Without it the abort path orphans a ~5MB tree silently while the
    ordinary failing-row path prints its own, which is the opposite of the
    contract: a row that aborted is exactly the one whose copy you want to look at.
    The failure still propagates, so the exit stays non-zero -- propagation OUT of
    this function is the contract, and `main` is where the per-row catch lives.

    #488 warden-r2/F5 -- the build is INSIDE the `try:`, so this function's stated
    envelope ("anything raised between building the tree and reading the run") is
    true of the build too rather than only of what follows it. STATED PLAINLY,
    because "the pin is green" is not evidence a guard is live: measured by
    reverting this half alone, NOTHING in the harness suite goes red. It is
    behaviour-NEUTRAL today -- a build failure has no tree to keep, so the arm it
    now reaches prints nothing (`tree is not None`) and re-raises exactly as the
    bare propagation did, and what catches it either way is `main`'s per-row
    `except Exception`, which is the half that carries the fix. This is kept for
    envelope integrity: any future statement added before `_apply` would otherwise
    sit outside every handler in this function. Do NOT read it as the mechanism."""
    tree = None
    try:
        tree = _build_tree()
        _apply(tree / "scripts" / "rcpt_verify.py", row["edits"])
        proc = subprocess.run([sys.executable, SUITE], cwd=tree,
                              capture_output=True, text=True)
    except StaleAnchor:
        shutil.rmtree(tree, ignore_errors=True)
        raise
    except BaseException:
        if tree is not None:
            print(f"row {row['id']:>2}  ABORTED before a verdict; "
                  f"tree kept for inspection: {_keep(tree, row['id'])}",
                  flush=True)
        raise
    return tree, _ids(proc.stdout + proc.stderr), proc.stdout + proc.stderr


def main():
    """Every row is ATTEMPTED and REPORTED. Nothing here may abort the loop: an
    anchor that moved, a mutation that breaks collection, a tree that will not
    build — each is one row's verdict, and the rows after it still run. The exit
    code is the aggregate."""
    # Bounded by one run's failures, not by a session's: kept trees are ~5MB each
    # and nothing else ever prunes them.
    shutil.rmtree(KEEP_DIR, ignore_errors=True)
    bad = 0
    stale_rows = []
    # #488 warden-r2/F5 — rows that raised something other than StaleAnchor. Before
    # this, `StaleAnchor` was the ONLY per-row catch, so a tree that would not build
    # or any exception inside `_apply`/the subprocess call aborted the WHOLE sweep —
    # in the worst case with zero rows evaluated, which is the silent-row-drop class
    # `c307528` was written to eliminate, reached down a different exception path.
    error_rows = []
    expected_ran = None
    for row in [BASELINE] + MUTANTS:
        label = f"row {row['id']:>2}  {row['criterion']:<38}  {row['what']}"
        try:
            tree, actual, out = _run_row(row)
        except StaleAnchor as exc:
            bad += 1
            stale_rows.append((row, exc.stale))
            print(f"{label}  -- ANCHOR-STALE")
            for anchor, n in exc.stale:
                print(f"  anchor occurs {n}x in scripts/rcpt_verify.py, expected "
                      f"1x -- the source moved under this row, so its mutation "
                      f"was NOT applied and its pins went UNCHECKED:")
                for line in anchor.splitlines() or [""]:
                    print(f"    | {line}")
            continue
        except Exception as exc:
            # `Exception`, NOT `BaseException`, deliberately: a KeyboardInterrupt or
            # a SystemExit must still abort the sweep rather than be booked as one
            # row's verdict. The message is truncated because `shutil.Error` embeds
            # every failed path and can run to thousands of characters, which would
            # bury the rows after it.
            bad += 1
            error_rows.append((row, exc))
            msg = f"{type(exc).__name__}: {exc}"
            if len(msg) > 200:
                msg = msg[:197] + "..."
            print(f"{label}  -- ROW-ERROR: {msg}")
            continue
        ran = _ran(out)
        # The count check FIRST, and EXCLUSIVE of the pin diff: a row whose copy
        # did not collect the whole suite has no meaningful pin diff, and printing
        # one anyway is what made a stale count read like a vacuity signal.
        if row is BASELINE:
            expected_ran = ran
            count_problem = None if ran else (
                "  the unmutated baseline collected "
                f"{'no `Ran` line at all' if ran is None else 'ZERO tests'} -- the "
                "TREE is broken (nothing was mutated on this row), and every later "
                "row's count check is skipped because there is nothing to derive")
        elif expected_ran is not None and ran != expected_ran:
            count_problem = (
                f"  test COUNT moved: row 0 (unmutated) collected {expected_ran} "
                f"tests, this row's copy collected "
                f"{'<no Ran line>' if ran is None else ran} -- this row's MUTATION "
                f"broke collection, not a pin. The pin diff is deliberately NOT "
                f"computed for this row: against a tree that did not run whole it "
                f"is noise shaped like the vacuity signal.")
        else:
            count_problem = None
        if count_problem:
            problems = [count_problem]
        else:
            # Row 0 reaches here too, and must: its `expect` is the EMPTY set, so
            # this is the check that the unmutated build reddens nothing at all.
            problems = []
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
            print(f"  tree kept for inspection: {_keep(tree, row['id'])}")
        else:
            print(f"{label}  red={len(actual)} -- ok")
            shutil.rmtree(tree, ignore_errors=True)
    if stale_rows:
        print("\ndec31_sweep: ANCHOR-STALE rows -- their mutation was never "
              "applied, so their pins went UNCHECKED this run:")
        for row, stale in stale_rows:
            for anchor, n in stale:
                first = next((l for l in anchor.splitlines() if l.strip()), "")
                print(f"  row {row['id']:>2}  expected 1 occurrence, found {n}"
                      f"  -- {first.strip()[:72]}")
    if error_rows:
        print("\ndec31_sweep: ROW-ERROR rows -- these rows never produced a "
              "verdict, so their pins went UNCHECKED this run:")
        for row, exc in error_rows:
            print(f"  row {row['id']:>2}  {type(exc).__name__}"
                  f"  -- {row['criterion']}")
    if bad:
        pin_bad = bad - len(stale_rows) - len(error_rows)
        print(f"\ndec31_sweep: {bad} row(s) failed -- {pin_bad} that no longer "
              f"discriminate as recorded, {len(stale_rows)} anchor-stale, "
              f"{len(error_rows)} row-error.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
