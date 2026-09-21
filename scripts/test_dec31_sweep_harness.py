#!/usr/bin/env python3
"""#488 c1 — permanent tests for the DEC-31 mutant HARNESS itself.

Run from repo root:  python3 scripts/test_dec31_sweep_harness.py

The subject here is `scripts/dec31_sweep.py` — its control flow, its keep-tree
contract, and its coupling to `scripts/run_tests.sh` — NOT `scripts/rcpt_verify.py`'s
behaviour. `scripts/test_488_name_space.py` owns that, and these tests deliberately
do not live there: one of the three findings below is precisely that the sweep must
stop being coupled to that file's test COUNT, so adding to it here would be
self-defeating.

Promoted from three inquisitor dimension-scratch files (`test_488_wiring.py`,
`test_488_regression_inquisitor.py`, `test_488_inquisitor_state.py`) after the
findings they reproduced were fixed. Three findings, found independently by three of
the five dimensions running against `fa108d2..HEAD`:

  1. a kept tree was built under `$TMPDIR`, which `scripts/run_tests.sh` scopes per
     invocation and `rm -rf`s from an EXIT trap — so through the gating entry point,
     the sweep's one diagnostic was deleted before the path naming it could be read;
  2. the suite's test count was a hard-coded literal that had already been hand-bumped
     twice on this branch, and whose staleness failed all sixteen rows while blaming
     `rcpt_verify.py` for what was an addition to a test file;
  3. a stale anchor raised `SystemExit` from `_apply` — a process abort, not a row
     verdict — so every row ordered after the tripping one was silently never run.

COST. Each real-tree row costs one full run of the 174-test acceptance suite (~4 s),
so the sixteen-row sweep is ~70 s and `scripts/run_tests.sh` already pays that once.
The two tests below that need the REAL tree therefore run two rows apiece, with
`MUTANTS` narrowed in-process, rather than a full sweep; the rest run against a
synthetic three-file mini-repo, where the machinery under test (`_apply`'s raise,
`main`'s loop, `_keep`'s move) is identical and a row costs milliseconds.
"""
import contextlib
import importlib.util
import io
import pathlib
import re
import shutil
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent
REPO = SCRIPTS.parent

# A row-1 anchor these tests reuse. Its whitespace variant is the smallest
# behaviour-preserving edit to `rcpt_verify.py` there is, and it is what the
# Regression dimension measured taking the sweep from 16 rows evaluated to 2.
ROW1_ANCHOR = "    if strict and is_path_shaped(name):"
ROW1_RESPACED = "    if strict and  is_path_shaped(name):"

STUB_SUITE = '''import unittest

import rcpt_verify  # noqa: F401  -- a mutation to it must be able to break collection


class TestStub(unittest.TestCase):
    def test_a(self):
        pass

    def test_b(self):
        pass


if __name__ == "__main__":
    unittest.main()
'''
STUB_LINTER = "MARKER_ONE = 1\nMARKER_TWO = 2\n"


def _import(name):
    """Import a scripts/ module by path — they are scripts, not a package."""
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _SweepCase(unittest.TestCase):
    """Every test gets its OWN import of the sweep and its own tree root, so the
    module globals it repoints (`REPO`, `KEEP_DIR`, `MUTANTS`) cannot leak into
    another test, and nothing here can touch the real checkout."""

    def setUp(self):
        self.sweep = _import("dec31_sweep")

    def point_at(self, root):
        """Repoint the sweep at `root` — both the tree it copies FROM and the
        directory it keeps failing trees IN."""
        self.sweep.REPO = root
        self.sweep.KEEP_DIR = root / ".dec31-keep"

    def mini_repo(self):
        """A synthetic three-file tree with the shape `COPY_DIRS` requires."""
        root = pathlib.Path(tempfile.mkdtemp(prefix="dec31-mini-"))
        self.addCleanup(shutil.rmtree, root, True)
        (root / "scripts").mkdir()
        (root / "eval").mkdir()
        (root / "docs").mkdir()
        (root / "scripts" / "test_488_name_space.py").write_text(STUB_SUITE)
        (root / "scripts" / "rcpt_verify.py").write_text(STUB_LINTER)
        self.point_at(root)
        return root

    def real_repo_copy(self):
        """A copy of the real `COPY_DIRS`, so a test may edit the tree the sweep
        copies from without touching the checkout."""
        root = pathlib.Path(tempfile.mkdtemp(prefix="dec31-src-"))
        self.addCleanup(shutil.rmtree, root, True)
        for d in self.sweep.COPY_DIRS:
            shutil.copytree(REPO / d, root / d,
                            ignore=shutil.ignore_patterns("__pycache__"))
        self.point_at(root)
        return root

    def row1(self):
        """The real row 1, skipped when its anchor is no longer file-unique."""
        row = next(r for r in self.sweep.MUTANTS if r["id"] == 1)
        self.assertEqual(row["edits"][0][0], ROW1_ANCHOR,
                         "row 1's anchor moved; update ROW1_ANCHOR")
        return row

    def run_main(self):
        """`main()`'s exit code and everything it printed."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = self.sweep.main()
        return rc, buf.getvalue()


class TestAKeptTreeSurvivesTheHarnessThatRunsIt(_SweepCase):
    """FINDING 1 — `dec31_sweep.py` builds every tree with `tempfile.mkdtemp()`,
    which resolves against `$TMPDIR`; `scripts/run_tests.sh` exports a PRIVATE
    `$TMPDIR` per invocation and `rm -rf`s it from an EXIT trap. Through the only
    harness the sweep is wired into — the one CLAUDE.md mandates and CI invokes —
    every tree it deliberately KEEPS was destroyed before anyone could look at it,
    and the path it printed was dangling by the time the run finished.

    Neither half is wrong alone: the TMPDIR scoping and the keep-on-failure contract
    were authored against different concerns. The interaction only exists once the
    sweep is added to the harness, which is what this build did.

    Fixed in `dec31_sweep.py`, not in `run_tests.sh`: the TMPDIR scoping there is
    load-bearing for other suites (`skills/inquisitor/evals/test_fixtures.py` globs
    the temp NAMESPACE). The sweep moves a kept tree into `<repo>/.dec31-keep/`
    instead."""

    def setUp(self):
        super().setUp()
        self.root = self.mini_repo()
        # A row that FAILS: nothing is mutated, but a pin is expected to fire and
        # cannot, so the row is red and its tree is kept.
        self.sweep.MUTANTS = [dict(id=7, criterion="synthetic",
                                   what="a row whose pin cannot fire",
                                   edits=[], expect={"NoSuchClass.test_nope"})]
        # The per-invocation $TMPDIR run_tests.sh creates. Assigned to
        # `tempfile.tempdir` rather than to the environment because
        # `tempfile.gettempdir()` caches its answer on first use.
        self.private = pathlib.Path(tempfile.mkdtemp(prefix="crucible-suite-"))
        self.addCleanup(shutil.rmtree, self.private, True)
        self.prev_tempdir = tempfile.tempdir
        self.addCleanup(setattr, tempfile, "tempdir", self.prev_tempdir)
        tempfile.tempdir = str(self.private)

    def test_the_path_the_sweep_prints_survives_the_tmpdir_trap(self):
        rc, out = self.run_main()
        self.assertEqual(rc, 1, out)
        kept = re.findall(r"tree kept for inspection: (\S+)", out)
        self.assertEqual(len(kept), 1, out)
        kept = pathlib.Path(kept[0])
        self.assertTrue(kept.exists(), f"precondition: {kept} was written")
        self.assertEqual(kept.parent, self.root / ".dec31-keep", out)
        self.assertNotIn(self.private, kept.parents,
                         "the kept tree is still inside the per-invocation $TMPDIR")

        # Exactly what run_tests.sh's `trap 'rm -rf -- "$_SUITE_TMPDIR"' EXIT` does.
        shutil.rmtree(self.private, ignore_errors=True)

        self.assertTrue(
            kept.exists(),
            f"dec31_sweep.py printed '{kept}' as kept for inspection, but "
            "run_tests.sh's per-invocation $TMPDIR teardown deleted it. Through "
            "the gating harness the sweep's only diagnostic is unreachable.")

    def test_the_keep_directory_is_cleared_at_the_start_of_a_run(self):
        """The other half of moving kept trees into the checkout: nothing else ever
        prunes them. The dimension run that found this left 42 trees / 199 MB behind
        in one session, because a failing row keeps its tree BY DESIGN and no bound
        existed. Clearing on entry bounds the total to one run's failures."""
        stale = self.root / ".dec31-keep" / "row-999"
        stale.mkdir(parents=True)
        (stale / "leftover").write_text("from a previous run\n")
        self.run_main()
        self.assertFalse(stale.exists(),
                         ".dec31-keep/ accumulates trees across runs unbounded")


class TestAStaleAnchorIsARowVerdictNotAProcessAbort(_SweepCase):
    """FINDING 3 (machinery) — `_apply` raised `SystemExit` the moment an anchor was
    not found exactly once. `SystemExit` is not a row verdict: it terminated the
    whole sweep, so every row ORDERED AFTER the tripping one was never evaluated at
    all, with nothing on the channel saying which pins went unchecked. The gate went
    red and the mutation coverage it exists to provide was lost silently.

    The synthetic tree is the point: what is under test is `main`'s loop and
    `_apply`'s raise, neither of which reads a row's CONTENT. The measured, real-tree
    reproduction is the next class."""

    def setUp(self):
        super().setUp()
        self.mini_repo()
        self.sweep.MUTANTS = [
            dict(id=1, criterion="synthetic", what="an anchor that moved",
                 edits=[("ANCHOR_THAT_IS_NOT_THERE", "x")], expect=set()),
            dict(id=2, criterion="synthetic",
                 what="a row ORDERED AFTER the stale one",
                 edits=[("MARKER_ONE", "MARKER_TWO")], expect=set()),
        ]

    def test_the_row_after_a_stale_anchor_is_still_evaluated(self):
        rc, out = self.run_main()
        self.assertIn("row  1", out)
        self.assertIn("ANCHOR-STALE", out)
        self.assertRegex(
            out, r"row  2.*-- ok",
            "the row ordered AFTER the anchor-stale row was never evaluated — a "
            "stale anchor is still aborting the sweep instead of scoring a row")
        self.assertEqual(rc, 1, "an anchor-stale row must still exit non-zero")

    def test_the_summary_names_the_stale_row_and_its_occurrence_counts(self):
        _, out = self.run_main()
        tail = out.split("ANCHOR-STALE rows")[-1]
        self.assertIn("row  1", tail)
        self.assertIn("expected 1 occurrence, found 0", tail)
        self.assertIn("ANCHOR_THAT_IS_NOT_THERE", tail)

    def test_every_missed_anchor_of_one_row_is_reported_not_just_the_first(self):
        """A row may carry several anchors. Reporting only the first means a second
        `_apply` after the first is fixed, which is a second ~70 s sweep."""
        self.sweep.MUTANTS = [dict(
            id=1, criterion="synthetic", what="two anchors, both moved",
            edits=[("FIRST_MISSING_ANCHOR", "x"), ("SECOND_MISSING_ANCHOR", "y")],
            expect=set())]
        _, out = self.run_main()
        self.assertIn("FIRST_MISSING_ANCHOR", out)
        self.assertIn("SECOND_MISSING_ANCHOR", out)

    def test_a_stale_row_does_not_leave_its_tree_behind(self):
        """`_apply` checks every anchor BEFORE substituting any, so a stale row's
        copy is byte-identical to the shipped build — there is nothing in it to
        inspect, and keeping one costs ~5 MB for no diagnostic."""
        self.run_main()
        keep = self.sweep.KEEP_DIR
        self.assertFalse(keep.exists() and any(keep.iterdir()),
                         "an anchor-stale row kept an unmutated tree")


class TestATreeThatWillNotBuildIsARowVerdictNotASweepAbort(_SweepCase):
    """#488 warden-r2/F5 — `main`'s docstring promised that "an anchor that moved, a
    mutation that breaks collection, a tree that will not build — each is one row's
    verdict, and the rows after it still run". Only `StaleAnchor` was ever caught.

    `_build_tree()` was called OUTSIDE `_run_row`'s `try:`, so a build failure — an
    unreadable file under a `COPY_DIRS` member, a `COPY_DIRS` member that is not
    there, a full disk — propagated straight out of `main`'s loop and aborted the
    whole sweep, in the worst case with ZERO rows evaluated. That is the same
    silent-row-drop failure class `c307528` was written to eliminate, reached down a
    different exception path, and the same is true of anything else `_apply` or the
    subprocess call could raise.

    The synthetic tree is the point, as for the anchor-stale class above: what is
    under test is `main`'s loop and `_build_tree`'s failure path, neither of which
    reads a row's CONTENT."""

    def setUp(self):
        super().setUp()
        self.root = self.mini_repo()
        # The tree cannot be built: `COPY_DIRS` names `docs`, and `copytree` of a
        # source that is not there raises. Chosen over a chmod because a
        # permission-based fixture is a no-op for a root-owned CI runner.
        (self.root / "docs").rmdir()
        self.sweep.MUTANTS = [
            dict(id=1, criterion="synthetic", what="the first mutant row",
                 edits=[("MARKER_ONE", "MARKER_TWO")], expect=set()),
            dict(id=2, criterion="synthetic",
                 what="a row ORDERED AFTER the unbuildable one",
                 edits=[("MARKER_TWO", "MARKER_ONE")], expect=set()),
        ]
        # `_build_tree` uses `tempfile.mkdtemp`, so pointing `tempfile.tempdir` at a
        # private directory makes the orphan check below exact.
        self.private = pathlib.Path(tempfile.mkdtemp(prefix="crucible-suite-"))
        self.addCleanup(shutil.rmtree, self.private, True)
        self.addCleanup(setattr, tempfile, "tempdir", tempfile.tempdir)
        tempfile.tempdir = str(self.private)

    def test_every_row_is_still_reported_when_no_tree_can_be_built(self):
        rc, out = self.run_main()
        reported = set(re.findall(r"^row +(\d+)", out, re.M))
        self.assertEqual(
            reported, {"0", "1", "2"},
            "a tree that will not build aborted the sweep instead of scoring a "
            f"row — only {sorted(reported)} were reported.\n{out}")
        self.assertEqual(out.count("-- ROW-ERROR:"), 3, out)
        self.assertEqual(rc, 1, "a row that produced no verdict must exit non-zero")

    def test_the_summary_says_those_rows_pins_went_unchecked(self):
        """A ROW-ERROR row is NOT a row that discriminates — booking it under the
        pin count would report the sweep as having measured something it did not."""
        _, out = self.run_main()
        tail = out.split("ROW-ERROR rows")[-1]
        self.assertIn("UNCHECKED", tail)
        self.assertIn("FileNotFoundError", tail)
        # The closing arithmetic must name BOTH non-verdict classes and must not
        # charge these rows to the pin count.
        self.assertIn("3 row(s) failed -- 0 that no longer discriminate as "
                      "recorded, 0 anchor-stale, 3 row-error.", out)

    def test_a_failed_build_does_not_orphan_its_partial_tree(self):
        """`copytree` had already copied `scripts/` and `eval/` before `docs/`
        raised, so without the cleanup each failed row leaks a partial tree into
        `$TMPDIR` with no handle left anywhere to remove it."""
        self.run_main()
        self.assertEqual(
            sorted(p.name for p in self.private.glob("dec31-*")), [],
            "a tree that failed to build was left behind in $TMPDIR")


class TestReformattingTheLinterDoesNotSilentlyDropMutationRows(_SweepCase):
    """FINDING 3 (measured) — the same claim against the REAL tree, with the real
    row 1, and the trigger that was actually observed: a BEHAVIOUR-PRESERVING edit to
    `scripts/rcpt_verify.py`. One extra space inside row 1's anchor took the sweep
    from 16 rows evaluated to 2; and it happened for real during the inquisitor run
    that filed this, when a concurrent parser fix moved row 5's anchor and the sweep
    aborted at row 5, skipping rows 6-15.

    Two rows, not sixteen: `MUTANTS` is narrowed in-process to the stale row plus a
    control ordered after it, which is the whole claim and costs one suite run rather
    than fifteen."""

    def setUp(self):
        super().setUp()
        root = self.real_repo_copy()
        self.linter = root / "scripts" / "rcpt_verify.py"
        text = self.linter.read_text()
        if text.count(ROW1_ANCHOR) != 1:
            self.skipTest("row-1 anchor is not present exactly once")
        respaced = text.replace(ROW1_ANCHOR, ROW1_RESPACED)
        # Non-vacuity: the edit is behaviour-preserving. One extra space inside an
        # `if` condition cannot change what the module does, and compiling it proves
        # the file is still the same program rather than a syntax error the suite
        # would have caught for an unrelated reason.
        compile(respaced, str(self.linter), "exec")
        self.linter.write_text(respaced)
        self.sweep.MUTANTS = [
            self.row1(),
            dict(id=99, criterion="control",
                 what="a row ORDERED AFTER the stale one", edits=[], expect=set()),
        ]

    def test_a_whitespace_only_edit_leaves_every_row_evaluated(self):
        rc, out = self.run_main()
        reported = set(re.findall(r"^row +(\d+)", out, re.M))
        self.assertEqual(
            reported, {"0", "1", "99"},
            "a whitespace-only edit to scripts/rcpt_verify.py dropped rows from the "
            f"DEC-31 sweep — only {sorted(reported)} were reported.\n{out}")
        self.assertRegex(out, r"row  1.*ANCHOR-STALE", out)
        self.assertRegex(out, r"row 99.*-- ok", out)
        self.assertEqual(rc, 1, out)


class TestTheSuitesTestCountIsDerivedNeverPinned(_SweepCase):
    """FINDING 2, found independently by three dimensions — the sweep hard-pinned
    `TOTAL_TESTS`, a literal count of the tests in `scripts/test_488_name_space.py`.
    That file is the one every task, review round and fix in this build appends to,
    so the pin had already been hand-bumped twice on this branch (160->168->174) and
    every future addition broke it again. When it tripped, ALL SIXTEEN rows failed
    with `the tree is broken, not a pin` — blaming `scripts/rcpt_verify.py` for an
    addition to a test file — and the rows then printed `unexpected`/`missing` diffs
    computed against a tree the harness had just declared broken, noise shaped
    exactly like the vacuity signal the harness exists to catch.

    Both entry points are gated by `scripts/run_tests.sh`, so this turned any test
    addition into a red CI run for the wrong reason.

    The count is now derived per run from row 0, the unmutated baseline, which is by
    construction the right count for whatever tree is being swept."""

    def setUp(self):
        super().setUp()
        self.root = self.real_repo_copy()
        self.suite = self.root / "scripts" / "test_488_name_space.py"

    def test_one_appended_passing_test_leaves_the_sweep_green(self):
        row = self.row1()
        # `_run_row` returns its tree; only `main` disposes of one, so this call
        # site owns it. Left alone it is a ~5MB orphan per standalone run.
        tree, _, out = self.sweep._run_row(self.sweep.BASELINE)
        self.addCleanup(shutil.rmtree, tree, True)
        before = self.sweep._ran(out)
        self.assertIsNotNone(before, "the baseline row printed no `Ran N tests` line")

        text = self.suite.read_text()
        # ABOVE the `__main__` guard, not after it: `unittest.main()` calls
        # `sys.exit()`, so a class appended below the guard is never even defined on
        # a standalone run and the count would not move at all — a vacuous test.
        guard = "\nif __name__ =="
        self.assertIn(guard, text, "acceptance suite has no __main__ guard")
        head, _, tail = text.partition(guard)
        self.suite.write_text(head + '''

class TestAnAppendedTestIsBehaviourless(unittest.TestCase):
    """Asserts nothing about the build; exists only to move the suite's COUNT."""

    def test_true_is_true(self):
        self.assertTrue(True)

''' + guard + tail)

        seen = []
        real_ran = self.sweep._ran
        self.sweep._ran = lambda out: seen.append(real_ran(out)) or seen[-1]
        self.sweep.MUTANTS = [row]
        rc, out = self.run_main()

        # Non-vacuity: the ONLY thing that moved is the number of tests collected,
        # and it really did move, by exactly one.
        self.assertEqual(seen[0], before + 1,
                         "the appended class did not add a test — vacuous run")
        self.assertNotIn("test COUNT moved", out)
        self.assertEqual(
            rc, 0,
            "one behaviourless test appended to scripts/test_488_name_space.py "
            "reddened scripts/dec31_sweep.py, which scripts/run_tests.sh gates:\n"
            + out)


class TestTheDerivedCountStillCatchesABrokenTree(_SweepCase):
    """The other side of finding 2: the check that was traded away must not have been
    traded away. A MUTATION that changes how many tests collect is still a broken
    tree, is still a row failure — it now names the baseline row it disagrees with
    instead of a literal, and it SUPPRESSES that row's pin diff on purpose, because
    against a tree that did not run whole the diff is noise shaped exactly like the
    vacuity signal."""

    def test_a_mutation_that_breaks_collection_is_reported_against_row_0(self):
        self.mini_repo()
        self.sweep.MUTANTS = [dict(
            id=98, criterion="synthetic", what="a mutation that breaks collection",
            edits=[("MARKER_ONE = 1", "MARKER_ONE = 1\nraise SystemExit(3)")],
            expect={"TestStub.test_a"})]
        rc, out = self.run_main()
        self.assertEqual(rc, 1, out)
        self.assertIn("test COUNT moved", out)
        self.assertIn("row 0 (unmutated) collected 2 tests", out)
        self.assertNotIn("vacuity signal)", out)

    def test_row_0_still_has_its_own_pin_diff_computed(self):
        """Row 0's `expect` is the EMPTY set, and that emptiness is a real check: the
        unmutated build must redden NOTHING. Deriving the count from row 0 must not
        turn row 0 into a row that only ever reports a count."""
        self.mini_repo()
        self.sweep.BASELINE = dict(self.sweep.BASELINE,
                                   expect={"TestStub.test_never_fires"})
        self.sweep.MUTANTS = []
        rc, out = self.run_main()
        self.assertEqual(rc, 1, out)
        self.assertIn("TestStub.test_never_fires", out)


class TestTheHarnessPinsNoLiteralTestCount(_SweepCase):

    def test_no_literal_count_of_the_acceptance_suite_is_pinned_here(self):
        """The cheap guard against re-introduction: a count of another file's tests
        has no business being a constant in this one."""
        src = (SCRIPTS / "dec31_sweep.py").read_text()
        self.assertIsNone(
            re.search(r"^TOTAL_TESTS\b", src, re.M),
            "scripts/dec31_sweep.py pins a literal test count again; derive it from "
            "the unmutated baseline row instead (see `_RAN`)")


if __name__ == "__main__":
    unittest.main()
