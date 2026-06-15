#!/usr/bin/env python3
"""stage() tests for the inquisitor fan-out eval harness (#424).

stdlib unittest (D1 — pytest cannot gate in this repo). Invoked as a bare script
by scripts/run_tests.sh, so bootstrap repo-root onto sys.path before importing the
package (sys.path[0] is the script dir, not repo root).
"""
import os
import pathlib
import re
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from skills.inquisitor.evals import run_evals  # noqa: E402


class StageTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        # resolve_dispatch_dir uses XDG_RUNTIME_DIR (or /tmp) + USER; pin both so
        # the dispatch dir lands inside the temp dir and is isolated per test.
        self._env = mock.patch.dict(
            os.environ, {"XDG_RUNTIME_DIR": self._tmp.name, "USER": "tester"})
        self._env.start()

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()


class TestStageManifestCount(StageTestBase):
    def test_manifest_count_3arm(self):
        """Test 1: (6+1+1) per-cell dispatch files × fixtures × trials, plus the
        two shared prompt files; the manifest enumerates the same per-cell count."""
        trials = 2
        dd = run_evals.stage("run-count", trials=trials)
        import json
        manifest = json.loads((dd / "stage-manifest.json").read_text())
        n_fixtures = manifest["fixtures"]
        self.assertEqual(manifest["trials"], trials)

        cells = manifest["cells"]
        # 3 arms per (fixture, trial)
        self.assertEqual(len(cells), 3 * n_fixtures * trials)
        with_cells = [c for c in cells if c["arm"] == "with"]
        mid_cells = [c for c in cells if c["arm"] == "mid"]
        wo_cells = [c for c in cells if c["arm"] == "without"]
        self.assertTrue(all(len(c["dispatch_files"]) == 6 for c in with_cells))
        self.assertTrue(all(len(c["dispatch_files"]) == 1 for c in mid_cells))
        self.assertTrue(all(len(c["dispatch_files"]) == 1 for c in wo_cells))

        per_cell_total = sum(len(c["dispatch_files"]) for c in cells)
        self.assertEqual(per_cell_total, (6 + 1 + 1) * n_fixtures * trials)

        # shared files present + on disk
        self.assertEqual(manifest["shared_files"],
                         ["aggregation-prompt.md", "judge-prompt.md"])
        self.assertTrue((dd / "aggregation-prompt.md").exists())
        self.assertTrue((dd / "judge-prompt.md").exists())

        # .md dispatch files on disk = per-cell files + the 2 shared files
        md_files = {p.name for p in dd.glob("*.md")}
        self.assertEqual(len(md_files), per_cell_total + 2)


class TestNeutralization(StageTestBase):
    def test_without_instruction_is_neutral(self):
        """Test 2: the WITHOUT instruction carries no dimension name, no fan-out."""
        instr = run_evals.WITHOUT_PROMPT
        for title in run_evals.DIMENSION_TITLES:
            self.assertNotIn(title, instr)
        self.assertNotIn("fan-out", instr.lower())

        dd = run_evals.stage("run-neutral", trials=1, fixture=1)
        wo = (dd / "f1-t1-without.md").read_text()
        self.assertTrue(wo.startswith(instr))

    def test_mid_has_all_lenses_and_aggregation(self):
        """Test 2: the MID dispatch carries all 5 dimension names + the shared
        aggregation framing."""
        dd = run_evals.stage("run-mid", trials=1, fixture=1)
        mid = (dd / "f1-t1-mid.md").read_text()
        for title in run_evals.DIMENSION_TITLES:
            self.assertIn(title, mid)
        # the byte-identical aggregation framing is embedded
        agg = run_evals._AGG_PROMPT.read_text()
        self.assertIn("consolidated", agg)  # marker exists in the shared prompt
        self.assertIn(agg.strip(), mid)

    def test_mid_carries_with_procedural_scaffold(self):
        """S1: the MID dispatch must carry the SAME per-dimension procedural
        scaffold the WITH agents get (reused from _template_region), so WITH−MID
        isolates ONLY the fan-out delivery mechanism — not the procedural prompt.
        Asserts the persona, the `## Your Job` steps, the NOT-do guard, the
        Report-Format marker, all 5 dimension titles, the aggregation framing, and
        NO residual [DIMENSION_*] slot."""
        dd = run_evals.stage("run-mid-scaffold", trials=1, fixture=1)
        mid = (dd / "f1-t1-mid.md").read_text()
        # procedural scaffold reused from the WITH template region
        self.assertIn("relentless hunter", mid)            # persona
        self.assertIn("## Your Job", mid)                  # 6-step procedure
        self.assertIn("## What You Must NOT Do", mid)      # NOT-do guard
        self.assertIn("## Report Format", mid)             # report shell
        self.assertIn("INQUISITOR DIMENSION REPORT", mid)  # report header
        # all 5 lens titles present (the all-five-dimensions swap)
        for title in run_evals.DIMENSION_TITLES:
            self.assertIn(title, mid)
        # aggregation framing byte-identical to WITH's embedding
        agg = run_evals._AGG_PROMPT.read_text()
        self.assertIn(agg.strip(), mid)
        # the single-dimension lens block was SWAPPED, not appended
        self.assertNotIn("## Your Dimension:", mid)
        # no residual single-dimension slot survives
        self.assertEqual(run_evals._DIMENSION_SLOT_RE.findall(mid), [])

    def test_mid_budget_is_per_dimension_scoped_and_with_unchanged(self):
        """F1: WITH−MID must isolate ONLY the fan-out delivery mechanism, so the two
        arms must carry EQUAL AGGREGATE output budget against the K-bug primary pool.

        WITH's "3-5 vectors" / "no more than 5 tests" cap binds each of 5 parallel
        agents (≈25 total); the SAME string copied verbatim into MID's single
        all-dimensions agent caps it at ≈5 total — confounding the delta with a 5×
        per-arm budget asymmetry. The rescoped MID expresses the cap PER DIMENSION
        (per-dimension cap × 5 dimensions == WITH's 5 × per-agent cap), and drops
        the incoherent single-agent "stay in your lane" line. WITH must keep its
        per-agent cap unchanged (regression guard the fix did not bleed into WITH)."""
        dd = run_evals.stage("run-mid-budget", trials=1, fixture=1)
        mid = (dd / "f1-t1-mid.md").read_text()
        # MID carries per-dimension / aggregate-scoped budget phrasing on both the
        # attack-vector and the test-count budget lines.
        self.assertIn("3-5 attack vectors per dimension", mid)
        self.assertIn("up to ~25 total", mid)
        self.assertIn("Do NOT describe more than 5 tests per dimension", mid)
        # MID does NOT carry the bare single-agent stay-in-your-lane line.
        self.assertNotIn("stay in", mid)
        self.assertIn("Cross-dimension reasoning is expected", mid)

        # WITH keeps the per-agent cap unchanged — the fix is render_mid-only.
        wd = (dd / "f1-t1-with-dim1-wiring.md").read_text()
        self.assertIn("**Identify 3-5 attack vectors** specific to your dimension",
                      wd)
        self.assertIn("Do NOT describe more than 5 tests", wd)
        self.assertNotIn("per dimension", wd)  # WITH cap is NOT rescoped
        self.assertIn("stay in", wd)           # WITH keeps its single-lane guard


class TestSliceScopedParse(StageTestBase):
    def setUp(self):
        super().setUp()
        self.template = run_evals._DIM_TEMPLATE.read_text()

    def test_stray_header_outside_slice_ignored(self):
        """Test 2b: a stray '### ' header OUTSIDE the Dimension Reference slice
        does not perturb the parse — still exactly 5 blocks, correct titles."""
        injected = self.template.replace(
            "## Dimension Reference",
            "### Stray Report-Format Header\n\nnoise\n\n## Dimension Reference", 1)
        blocks = run_evals.parse_dimension_blocks(injected)
        self.assertEqual([t for t, _ in blocks], run_evals.DIMENSION_TITLES)

    def test_extra_block_inside_slice_raises(self):
        """A 6th '### ' block INSIDE the slice fails the count assertion."""
        injected = self.template.rstrip() + "\n\n### Bogus Dimension\n\n- noise\n"
        with self.assertRaises(ValueError):
            run_evals.parse_dimension_blocks(injected)

    def test_count_preserving_title_swap_raises(self):
        """A header-count-preserving rename (still 5 blocks, wrong title set) is
        caught by the literal-title-set assertion (S3)."""
        injected = self.template.replace("### Wiring", "### Plumbing", 1)
        with self.assertRaises(ValueError):
            run_evals.parse_dimension_blocks(injected)


class TestWithRenderSlots(StageTestBase):
    def test_no_residual_dimension_slot_and_question_matches(self):
        """Test 2c: each rendered WITH dimension dispatch has no residual
        [DIMENSION_*] slot, and its question matches the source Core question."""
        dd = run_evals.stage("run-slots", trials=1, fixture=1)
        blocks = run_evals.parse_dimension_blocks(
            run_evals._DIM_TEMPLATE.read_text())
        slot_re = re.compile(r"\[DIMENSION_[A-Z_]*\]")
        for n, (title, block) in enumerate(blocks, 1):
            slug = run_evals._slug(title)
            text = (dd / f"f1-t1-with-dim{n}-{slug}.md").read_text()
            self.assertEqual(slot_re.findall(text), [],
                             f"residual slot in dim {title}")
            fields = run_evals.extract_dimension_fields(title, block)
            self.assertIn(fields["question"], text)
            # the dimension name appears (report header + dimension section)
            self.assertIn(title, text)

    def test_validate_raises_on_underfilled_render(self):
        """Test 2c: the _validate_rendered_prompt guard RAISES on a leftover slot."""
        with self.assertRaises(ValueError):
            run_evals._validate_rendered_prompt(
                "a render with a leftover [DIMENSION_NAME] slot")
        # a residual non-dimension [PASTE: slot also raises (S1)
        with self.assertRaises(ValueError):
            run_evals._validate_rendered_prompt(
                "a render with a leftover [PASTE: project test conventions]")
        # a fully-filled render does not raise
        run_evals._validate_rendered_prompt("no slots here, all filled")

    def test_no_residual_paste_slot_in_with_or_mid(self):
        """S1: no unfilled [PASTE: slot survives into a WITH dimension render or
        the MID render (an arm-asymmetric prompt confound — WITH/MID carrying a
        dangling unfulfillable PASTE instruction the WITHOUT baseline lacks)."""
        dd = run_evals.stage("run-paste", trials=1, fixture=1)
        mid = (dd / "f1-t1-mid.md").read_text()
        self.assertNotIn("[PASTE:", mid)
        blocks = run_evals.parse_dimension_blocks(
            run_evals._DIM_TEMPLATE.read_text())
        for n, (title, _block) in enumerate(blocks, 1):
            slug = run_evals._slug(title)
            text = (dd / f"f1-t1-with-dim{n}-{slug}.md").read_text()
            self.assertNotIn("[PASTE:", text,
                             f"residual [PASTE: slot in dim {title}")


class TestFixtureDiffWithSlotShapedTokens(StageTestBase):
    """S1: _validate_rendered_prompt validates the slot-filled template BEFORE the
    fixture diff is embedded (sentinel-consumed git-diff slot), so a fixture diff
    that legitimately CONTAINS a `[DIMENSION_*]`- or `[PASTE:`-shaped token (plausible
    in JS/TS or dispatch/template code-review fixtures) stages successfully instead of
    false-tripping the residual-slot guard — and those tokens survive verbatim into
    the rendered WITH-dimension and MID prompts (they are fixture content, not slots).
    """

    SYNTH = {
        "id": "synth-slotshaped",
        "prompt": (
            "Feature under review: a config lookup.\n"
            "+ const k = obj[DIMENSION_KEY];  // bracket-key access\n"
            "+ // doc note: [PASTE: something] is a literal token here\n"
        ),
    }

    def test_fixture_with_slot_shaped_tokens_stages_and_survives_verbatim(self):
        with mock.patch.object(run_evals, "_load_fixtures",
                               return_value=[self.SYNTH]):
            # Must NOT raise (pre-fix this crashed with a misleading residual-slot
            # / residual-[PASTE: error because the guard scanned the fixture bytes).
            dd = run_evals.stage("run-slotshaped", trials=1, fixture="synth-slotshaped")

        # the fixture's slot-shaped tokens survive verbatim in every WITH dim render
        blocks = run_evals.parse_dimension_blocks(
            run_evals._DIM_TEMPLATE.read_text())
        for n, (title, _b) in enumerate(blocks, 1):
            slug = run_evals._slug(title)
            text = (dd / f"fsynth-slotshaped-t1-with-dim{n}-{slug}.md").read_text()
            self.assertIn("obj[DIMENSION_KEY]", text)
            self.assertIn("[PASTE: something]", text)
            # no residual REAL git-diff slot remains (the sentinel round-tripped)
            self.assertNotIn("[PASTE: git diff", text)

        mid = (dd / "fsynth-slotshaped-t1-mid.md").read_text()
        self.assertIn("obj[DIMENSION_KEY]", mid)
        self.assertIn("[PASTE: something]", mid)
        self.assertNotIn("[PASTE: git diff", mid)


class TestFixtureOpenerNeutralized(StageTestBase):
    """S-3: the evals.json skill-naming opener "Run the inquisitor against this
    feature diff for …" must be neutralized in the embedded fixture content of ALL
    THREE arms, so the methodology difference comes only from the arm scaffold and
    the WITHOUT baseline is not primed with the methodology it is meant to lack."""

    def test_helper_mirrors_provenance_neutralization(self):
        """The helper reproduces the provenance build's exact substitution."""
        self.assertEqual(
            run_evals._neutralize_fixture_opener(
                "Run the inquisitor against this feature diff for a new "
                "'Scheduled Notifications' feature."),
            "Feature under review: a new 'Scheduled Notifications' feature.")
        # text without the opener is left untouched
        self.assertEqual(
            run_evals._neutralize_fixture_opener("Feature under review: x"),
            "Feature under review: x")

    def test_no_arm_names_the_inquisitor_and_without_is_neutral(self):
        """No rendered arm (WITH dims, MID, WITHOUT) carries the skill-naming
        opener, and the WITHOUT diff opens with the neutral framing."""
        dd = run_evals.stage("run-opener", trials=1, fixture=1)
        blocks = run_evals.parse_dimension_blocks(
            run_evals._DIM_TEMPLATE.read_text())
        rendered = []
        for n, (title, _b) in enumerate(blocks, 1):
            slug = run_evals._slug(title)
            rendered.append((dd / f"f1-t1-with-dim{n}-{slug}.md").read_text())
        rendered.append((dd / "f1-t1-mid.md").read_text())
        wo = (dd / "f1-t1-without.md").read_text()
        rendered.append(wo)
        for text in rendered:
            self.assertNotIn("Run the inquisitor", text)
        # WITHOUT embeds the neutral framing (after the bare instruction + ## Diff)
        self.assertIn("Feature under review: ", wo)


if __name__ == "__main__":
    unittest.main()
