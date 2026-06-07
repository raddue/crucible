#!/usr/bin/env python3
"""Hermetic acceptance test for scripts/catalog.py (the skill-catalog drift
gate). RED→GREEN spec for #364.

Invocation (from repo root):
    python scripts/test_catalog.py

This is a self-contained stdlib `unittest` script (NO pytest, NO yaml). Because
Python puts the script's own directory (`scripts/`) on `sys.path[0]`, a plain
`import catalog` resolves with no package-qualified import or `sys.path`
manipulation needed (even though `scripts/` carries an `__init__.py`).

The `import catalog` is GUARDED below so the RED checkpoint (catalog.py absent)
fails with a clear, single reason rather than an opaque collection error: every
test is skipped with the import message, and a dedicated guard test FAILS so the
suite is RED. Once catalog.py exists (Task 2) the guard passes and the real
assertions run.

Contract this test pins (catalog.py — Task 2 — is written to satisfy it):
  - catalog.check(root) -> list[str]   (read-only drift bullets; [] == clean)
  - catalog.render(root)               (mutate docs/skills.md between
                                        <!-- CATALOG:START/END --> markers +
                                        the registered count-token files)
  - catalog.parse_skill_names(root) -> set[str]
  - catalog.CATEGORIES                 (ordered category -> [skill names])
All callables accept a `root` param (a tmp dir), so the live repo is untouched.
"""
from __future__ import annotations

import pathlib
import re
import shutil
import tempfile
import unittest

# --- Guarded import: RED signal when catalog.py is absent ------------------
try:
    import catalog  # noqa: E402  (scripts/ is on sys.path[0] at runtime)
    CATALOG_IMPORT_ERROR = None
except Exception as exc:  # ModuleNotFoundError at the RED checkpoint
    catalog = None
    CATALOG_IMPORT_ERROR = exc


def _require_catalog():
    """Skip a test cleanly if catalog.py is not importable yet."""
    if catalog is None:
        raise unittest.SkipTest(f"catalog module not importable: {CATALOG_IMPORT_ERROR!r}")


class CatalogImportGuard(unittest.TestCase):
    """A dedicated FAILING test so the suite is RED while catalog.py is absent.

    The behavioral tests SKIP when the module is missing (so their intent
    stays legible); this one test turns the run red for the right reason.
    """

    def test_catalog_module_importable(self):
        self.assertIsNone(
            CATALOG_IMPORT_ERROR,
            f"catalog.py not importable (expected RED until Task 2): {CATALOG_IMPORT_ERROR!r}",
        )


# --------------------------------------------------------------------------
# Fixture builder
# --------------------------------------------------------------------------
class CatalogTestBase(unittest.TestCase):
    """Builds a hermetic fake repo root in a tmp dir; tears it down.

    Helpers write a `skills/<name>/SKILL.md` tree, a `docs/skills.md` with
    CATALOG markers, and the count-token files (README.md,
    skills/workshop/SKILL.md, .claude-plugin/plugin.json).
    """

    def setUp(self):
        _require_catalog()
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="catalog_test_"))
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)

    # -- low-level fixture writers ----------------------------------------
    def write_skill(self, name: str, description: str | None = None,
                    raw_frontmatter: str | None = None):
        """Create skills/<name>/SKILL.md with a YAML frontmatter block.

        `raw_frontmatter` (if given) is the literal text placed between the two
        `---` fences (used for folded-scalar / double-quoted fixtures). Else a
        plain single-line `name:`/`description:` block is written.
        """
        d = self.root / "skills" / name
        d.mkdir(parents=True, exist_ok=True)
        if raw_frontmatter is not None:
            body = f"---\n{raw_frontmatter}\n---\n\n# {name}\n"
        else:
            desc = description if description is not None else f"{name} does a thing."
            body = f"---\nname: {name}\ndescription: {desc}\n---\n\n# {name}\n"
        (d / "SKILL.md").write_text(body, encoding="utf-8")

    def write_count_files(self, digit_form):
        """Write the four count-token surfaces.

        `digit_form` is a dict supplying the token strings, e.g. for the clean
        n=3 baseline: {"space": "3", "tilde": "~3", "hyphen": "3", "agent": "3"}.
        We always write the canonical forms (space/tilde/hyphen on README &
        workshop, agent on plugin.json).
        """
        readme = self.root / "README.md"
        readme.write_text(
            f"# Repo\n\nA toolkit of {digit_form['space']} skills.\n", encoding="utf-8"
        )
        wsdir = self.root / "skills" / "workshop"
        wsdir.mkdir(parents=True, exist_ok=True)
        (wsdir / "SKILL.md").write_text(
            f"---\nname: workshop\ndescription: tour\n---\n\n"
            f"About {digit_form['tilde']} skills here. "
            f"The {digit_form['hyphen']}-skill catalog tour.\n",
            encoding="utf-8",
        )
        plugdir = self.root / ".claude-plugin"
        plugdir.mkdir(parents=True, exist_ok=True)
        (plugdir / "plugin.json").write_text(
            '{\n  "name": "crucible",\n'
            f'  "description": "{digit_form["agent"]} agent skills."\n' + "}\n",
            encoding="utf-8",
        )

    def write_skills_doc(self, body: str):
        """Write docs/skills.md (caller supplies full content incl. markers)."""
        d = self.root / "docs"
        d.mkdir(parents=True, exist_ok=True)
        (d / "skills.md").write_text(body, encoding="utf-8")

    @staticmethod
    def catalog_block(rows_by_category, intro="# Skill Catalog\n\n"):
        """Render a docs/skills.md body with CATALOG markers.

        `rows_by_category` is a list of (category, [(name, description), ...]).
        Intro prose sits OUTSIDE (before) the START marker.
        """
        out = [intro, "<!-- CATALOG:START -->\n"]
        for cat, rows in rows_by_category:
            out.append(f"## {cat}\n\n")
            out.append("| Skill | Description |\n")
            out.append("|---|---|\n")
            for name, desc in rows:
                out.append(f"| **{name}** | {desc} |\n")
            out.append("\n")
        out.append("<!-- CATALOG:END -->\n")
        return "".join(out)

    # workshop is a real on-disk skill (write_count_files creates it with
    # `name: workshop`), so it is ALWAYS part of n. Fixtures must treat it as a
    # first-class member — categorized, given a catalog row, and counted — so the
    # ONLY drift/error in any fixture is the one the test intends to inject.
    WORKSHOP_DESC = "Tour of the workshop."

    def _count_tokens(self, n):
        """The four canonical count-token strings for a given runtime n."""
        s = str(n)
        return {"space": s, "tilde": f"~{s}", "hyphen": s, "agent": s}

    # -- a complete clean fixture (content skills + workshop) --------------
    def build_clean_fixture(self, content_skills=("alpha", "bravo", "charlie")):
        """content_skills + workshop, all categorized + rowed, counts == true n.

        n = len(content_skills) + 1 (the +1 for the always-present `workshop`
        skill that write_count_files plants). The clean baseline must therefore
        register workshop in CATEGORIES, in the doc rows, and in the count token.
        """
        content = list(content_skills)
        for nm in content:
            self.write_skill(nm)
        names = content + ["workshop"]
        self._install_categories({"Core": list(names)})
        rows = [("Core",
                 [(nm, f"{nm} does a thing.") for nm in content]
                 + [("workshop", self.WORKSHOP_DESC)])]
        self.write_skills_doc(self.catalog_block(rows))
        # write_count_files plants skills/workshop/SKILL.md, so workshop is on
        # disk and the count tokens read the true n (content + workshop).
        n = len(names)
        self.write_count_files(self._count_tokens(n))

    def _install_categories(self, mapping):
        """Override catalog.CATEGORIES for the duration of one test.

        catalog.CATEGORIES is the project-level category map; the hermetic test
        must drive it against the tmp fixture's skill set, so we monkeypatch it
        and restore on cleanup.
        """
        original = catalog.CATEGORIES
        catalog.CATEGORIES = dict(mapping)
        self.addCleanup(lambda: setattr(catalog, "CATEGORIES", original))


# --------------------------------------------------------------------------
# The behavioral cases
# --------------------------------------------------------------------------
class CatalogChecks(CatalogTestBase):

    # 1
    def test_clean_fixture_passes(self):
        self.build_clean_fixture()
        self.assertEqual(catalog.check(self.root), [])

    # 2
    def test_omission(self):
        self.build_clean_fixture()
        # Add a 4th skill on disk with no row between the markers.
        self.write_skill("delta")
        cats = dict(catalog.CATEGORIES)
        cats["Core"] = cats["Core"] + ["delta"]
        self._install_categories(cats)
        # Counts now drift (n becomes 4); we only assert the omission bullet.
        errs = catalog.check(self.root)
        self.assertTrue(any("delta" in e for e in errs),
                        f"expected an omission bullet naming 'delta': {errs}")

    # 3
    def test_bogus_entry(self):
        self.build_clean_fixture()
        # Inject a row naming a skill with no SKILL.md (the `external review` analogue).
        rows = [("Core", [
            ("alpha", "alpha does a thing."),
            ("bravo", "bravo does a thing."),
            ("charlie", "charlie does a thing."),
            ("external review", "a phantom skill with no SKILL.md."),
        ])]
        self.write_skills_doc(self.catalog_block(rows))
        errs = catalog.check(self.root)
        self.assertTrue(any("external review" in e for e in errs),
                        f"expected a bogus-entry bullet naming 'external review': {errs}")

    # 4
    def test_naming_mismatch(self):
        # Frontmatter says cartographer-skill; the row says cartographer.
        self.write_skill("cartographer-skill")
        self.write_skill("bravo")
        self.write_skill("charlie")
        self._install_categories({"Core": ["cartographer-skill", "bravo", "charlie"]})
        rows = [("Core", [
            ("cartographer", "named wrong — should be cartographer-skill."),
            ("bravo", "bravo does a thing."),
            ("charlie", "charlie does a thing."),
        ])]
        self.write_skills_doc(self.catalog_block(rows))
        self.write_count_files({"space": "3", "tilde": "~3", "hyphen": "3", "agent": "3"})
        errs = catalog.check(self.root)
        self.assertTrue(
            any("cartographer" in e for e in errs),
            f"expected a naming-mismatch bullet about 'cartographer': {errs}")

    # 5
    def test_uncategorized_skill(self):
        self.build_clean_fixture()
        # A skill on disk that is NOT in CATEGORIES.
        self.write_skill("orphan")
        # Give it a row too, so the ONLY problem is uncategorized membership.
        rows = [("Core", [
            ("alpha", "alpha does a thing."),
            ("bravo", "bravo does a thing."),
            ("charlie", "charlie does a thing."),
            ("orphan", "orphan does a thing."),
        ])]
        self.write_skills_doc(self.catalog_block(rows))
        errs = catalog.check(self.root)
        self.assertTrue(
            any("orphan" in e for e in errs),
            f"expected an uncategorized bullet naming 'orphan': {errs}")

    # 6
    def test_dangling_category(self):
        self.build_clean_fixture()
        # Add a CATEGORIES entry whose skill has no SKILL.md on disk.
        cats = dict(catalog.CATEGORIES)
        cats["Core"] = cats["Core"] + ["ghost"]
        self._install_categories(cats)
        errs = catalog.check(self.root)
        self.assertTrue(
            any("ghost" in e for e in errs),
            f"expected a dangling-category bullet naming 'ghost': {errs}")

    # ----- count-drift family (cases 7-10) ------------------------------
    # The fixture is OTHERWISE-CLEAN at true n (content skills + workshop) — all
    # tokens read n except the ONE the case drifts. So `check` returning errs
    # proves count-drift detection, not an unrelated dirty-fixture artifact.
    def _build_count_drift_fixture(self, drift_key, drift_value):
        """Clean fixture at true n=4, then drift ONLY the named count token.

        `drift_key` in {"space","tilde","hyphen","agent"}; `drift_value` is the
        wrong digit form for that token (e.g. "42" / "~42" / "42" / "23").
        """
        # Establish the clean n=4 baseline (alpha/bravo/charlie + workshop).
        self.build_clean_fixture()
        n = len(catalog.parse_skill_names(self.root))
        self.assertEqual(n, 4, "drift fixture baseline must be a clean n=4 set")
        tokens = self._count_tokens(n)
        tokens[drift_key] = drift_value  # perturb exactly one token
        self.write_count_files(tokens)

    @staticmethod
    def _is_count_drift(err):
        e = err.lower()
        return ("count" in e) or ("skill" in e)

    # 7
    def test_count_drift_space_form(self):
        # README "42 skills" while n=4 -> drift.
        self._build_count_drift_fixture("space", "42")
        errs = catalog.check(self.root)
        self.assertTrue(any(self._is_count_drift(e) for e in errs),
                        f"expected a count-drift error for '42 skills': {errs}")

    # 8
    def test_count_drift_tilde_form(self):
        self._build_count_drift_fixture("tilde", "~42")
        errs = catalog.check(self.root)
        self.assertTrue(any(self._is_count_drift(e) for e in errs),
                        f"expected a count-drift error for '~42 skills': {errs}")

    # 9
    def test_count_drift_hyphen_form(self):
        # '42-skill catalog' — pins that ~?42 skills would MISS this.
        self._build_count_drift_fixture("hyphen", "42")
        errs = catalog.check(self.root)
        self.assertTrue(any(self._is_count_drift(e) for e in errs),
                        f"expected a count-drift error for '42-skill': {errs}")

    # 10
    def test_count_drift_agent_form(self):
        # plugin.json '23 agent skills' while n=4 -> drift.
        self._build_count_drift_fixture("agent", "23")
        errs = catalog.check(self.root)
        self.assertTrue(any(self._is_count_drift(e) for e in errs),
                        f"expected a count-drift error for '23 agent skills': {errs}")

    # 11
    def test_idempotence(self):
        self.build_clean_fixture()
        doc = self.root / "docs" / "skills.md"
        catalog.render(self.root)
        first = doc.read_bytes()
        catalog.render(self.root)
        second = doc.read_bytes()
        self.assertEqual(first, second,
                         "second render must be byte-for-byte identical (no-op)")

    # 12
    def test_description_preserved(self):
        self.build_clean_fixture()
        curated = "A carefully curated, hand-written description — keep me verbatim."
        rows = [("Core", [
            ("alpha", curated),
            ("bravo", "bravo does a thing."),
            ("charlie", "charlie does a thing."),
            ("workshop", self.WORKSHOP_DESC),
        ])]
        self.write_skills_doc(self.catalog_block(rows))
        # Frontmatter has a DIFFERENT description so a re-seed would be detectable.
        self.write_skill("alpha", description="frontmatter description for alpha")
        catalog.render(self.root)
        out = (self.root / "docs" / "skills.md").read_text(encoding="utf-8")
        self.assertIn(curated, out,
                      "curated description must survive render unchanged")
        self.assertNotIn("frontmatter description for alpha", out,
                         "render must NOT overwrite a curated row with frontmatter")

    # 13
    def test_new_skill_seeded_from_frontmatter(self):
        # Two skills WITHOUT existing rows: one folded-scalar, one double-quoted.
        # Each must seed a single quote-free, continuation-joined cell.
        folded_fm = (
            "name: foldy\n"
            "description: >\n"
            "  First continuation line of the folded scalar\n"
            "  second continuation line should join with a single space\n"
            "  third line too"
        )
        self.write_skill("foldy", raw_frontmatter=folded_fm)
        quoted_fm = (
            'name: quoty\n'
            'description: "A double-quoted description — strip the quotes."'
        )
        self.write_skill("quoty", raw_frontmatter=quoted_fm)
        self.write_skill("charlie")  # an existing-row skill
        # workshop is planted on disk by write_count_files, so it must be a
        # categorized member too (true n=4: foldy/quoty/charlie/workshop).
        names = ["foldy", "quoty", "charlie", "workshop"]
        self._install_categories({"Core": names})
        # Existing doc has charlie + workshop rows; foldy & quoty are new -> seeded.
        rows = [("Core", [
            ("charlie", "charlie does a thing."),
            ("workshop", self.WORKSHOP_DESC),
        ])]
        self.write_skills_doc(self.catalog_block(rows))
        self.write_count_files(self._count_tokens(4))
        catalog.render(self.root)
        out = (self.root / "docs" / "skills.md").read_text(encoding="utf-8")

        folded_expected = ("First continuation line of the folded scalar "
                           "second continuation line should join with a single space "
                           "third line too")
        self.assertIn(folded_expected, out,
                      "folded-scalar description must be continuation-joined with single spaces")
        quoted_expected = "A double-quoted description — strip the quotes."
        self.assertIn(quoted_expected, out,
                      "double-quoted description must be seeded quote-free")
        # No raw quote-wrapping leaked through.
        self.assertNotIn('"A double-quoted description', out,
                         "double-quoted seed must not be quote-wrapped in the cell")
        # foldy must appear exactly once as a row (single cell, not blank).
        self.assertEqual(
            len(re.findall(r"^\| \*\*foldy\*\* \|", out, re.MULTILINE)), 1,
            "foldy must seed exactly one row")
        self.assertEqual(
            len(re.findall(r"^\| \*\*quoty\*\* \|", out, re.MULTILINE)), 1,
            "quoty must seed exactly one row")

    # 14
    def test_embedded_pipe_row(self):
        # A curated description with a code span `a | b` must stay ONE cell.
        self.build_clean_fixture()  # alpha/bravo/charlie + workshop, clean n=4
        piped = "Handles a `a | b` code span inside the description cell."
        rows = [("Core", [
            ("alpha", piped),
            ("bravo", "bravo does a thing."),
            ("charlie", "charlie does a thing."),
            ("workshop", self.WORKSHOP_DESC),
        ])]
        self.write_skills_doc(self.catalog_block(rows))
        # check must NOT see this as a bogus/extra column (the row stays valid).
        self.assertEqual(catalog.check(self.root), [],
                         "embedded-pipe row must parse as one name + one desc cell")
        catalog.render(self.root)
        out = (self.root / "docs" / "skills.md").read_text(encoding="utf-8")
        self.assertIn(piped, out,
                      "embedded-pipe description must survive render as one cell")

    # 15
    def test_neighbor_digit_non_clobber(self):
        # README:5-analogue line with many numbers; render must touch only the count.
        self.build_clean_fixture()  # true n=4 (alpha/bravo/charlie + workshop)
        n = len(catalog.parse_skill_names(self.root))
        readme = self.root / "README.md"
        # Drift README's count token (42) while leaving four neighbor numbers.
        readme.write_text(
            "A toolkit of 42 skills, 49 execution evals, 18 sequence evals, "
            "+29% and +31% deltas.\n",
            encoding="utf-8",
        )
        catalog.render(self.root)
        out = readme.read_text(encoding="utf-8")
        self.assertIn(f"{n} skills", out, f"count token must be rewritten to n={n}")
        self.assertNotIn("42 skills", out, "old count must be gone")
        for neighbor in ("49 execution evals", "18 sequence evals", "+29%", "+31%"):
            self.assertIn(neighbor, out,
                          f"neighbor number '{neighbor}' must be byte-for-byte unchanged")

    # 16
    def test_count_is_runtime_derived(self):
        # (a) Behavioral render-side proof for K=3 AND K=7.
        for K in (3, 7):
            with self.subTest(K=K):
                # fresh root per K to avoid cross-contamination
                root = pathlib.Path(tempfile.mkdtemp(prefix="catalog_K_"))
                self.addCleanup(lambda r=root: shutil.rmtree(r, ignore_errors=True))
                names = [f"sk{i}" for i in range(K)]
                for nm in names:
                    d = root / "skills" / nm
                    d.mkdir(parents=True, exist_ok=True)
                    (d / "SKILL.md").write_text(
                        f"---\nname: {nm}\ndescription: {nm} thing.\n---\n# {nm}\n",
                        encoding="utf-8")
                wsdir = root / "skills" / "workshop"
                wsdir.mkdir(parents=True, exist_ok=True)
                (wsdir / "SKILL.md").write_text(
                    "---\nname: workshop\ndescription: tour\n---\n\n"
                    "About ~99 skills here. The 99-skill catalog tour.\n",
                    encoding="utf-8")
                (root / "README.md").write_text(
                    "A toolkit of 99 skills.\n", encoding="utf-8")
                plugdir = root / ".claude-plugin"
                plugdir.mkdir(parents=True, exist_ok=True)
                (plugdir / "plugin.json").write_text(
                    '{\n  "description": "99 agent skills."\n}\n', encoding="utf-8")
                docdir = root / "docs"
                docdir.mkdir(parents=True, exist_ok=True)
                allnames = names + ["workshop"]
                rowtext = "".join(f"| **{nm}** | {nm} thing. |\n" for nm in allnames)
                (docdir / "skills.md").write_text(
                    "# Cat\n\n<!-- CATALOG:START -->\n## Core\n\n"
                    "| Skill | Description |\n|---|---|\n"
                    + rowtext + "\n<!-- CATALOG:END -->\n",
                    encoding="utf-8")
                original = catalog.CATEGORIES
                catalog.CATEGORIES = {"Core": list(allnames)}
                try:
                    catalog.render(root)
                finally:
                    catalog.CATEGORIES = original
                # n today = K skills + workshop = K+1
                n_today = K + 1
                readme_out = (root / "README.md").read_text(encoding="utf-8")
                ws_out = (wsdir / "SKILL.md").read_text(encoding="utf-8")
                plug_out = (plugdir / "plugin.json").read_text(encoding="utf-8")
                self.assertIn(f"{n_today} skills", readme_out,
                              f"render must write runtime n={n_today}, not a literal")
                self.assertIn(f"~{n_today} skills", ws_out)
                self.assertIn(f"{n_today}-skill", ws_out)
                self.assertIn(f"{n_today} agent skills", plug_out)
                self.assertNotIn("99 skills", readme_out,
                                 "the wired-in 99 must NOT survive a runtime-derived render")

        # (b) Narrow, threat-specific literal guard: today's total must not be a
        # bare word-boundaried literal in catalog.py source.
        n_today = len(catalog.parse_skill_names(self._live_root()))
        src = self._catalog_source()
        self.assertIsNone(
            re.search(rf"\b{n_today}\b", src),
            f"catalog.py must not hardcode today's total ({n_today}) as a literal — "
            "the count must be runtime-derived",
        )

        # (c) Positive control: a mutant injecting EXPECTED = <today's total>
        # MUST trip the same narrow guard (discrimination proof).
        mutant = src + f"\nEXPECTED = {n_today}\n"
        self.assertIsNotNone(
            re.search(rf"\b{n_today}\b", mutant),
            "the narrow literal guard must FIRE on a mutant injecting the today's-total literal",
        )

    def _live_root(self):
        return pathlib.Path(__file__).resolve().parent.parent

    def _catalog_source(self):
        return (self._live_root() / "scripts" / "catalog.py").read_text(encoding="utf-8")

    # 17
    def test_count_target_path_missing(self):
        self.build_clean_fixture()
        # Remove a registered count-target file (README) -> path-existence bullet.
        (self.root / "README.md").unlink()
        errs = catalog.check(self.root)
        self.assertTrue(
            any("README.md" in e and ("not found" in e or "missing" in e.lower())
                for e in errs),
            f"expected a path-existence bullet for the missing README.md target: {errs}")
        # The path-existence bullet is the ONLY error — no spurious workshop
        # omission/uncategorized (the fixture is otherwise clean at n=4).
        self.assertFalse(
            any("workshop" in e for e in errs),
            f"missing-README fixture must not also flag workshop: {errs}")

    # 18
    def test_section_intro_prose_preserved(self):
        # A category WITH intro prose between heading and table, and a control
        # category with NO intro prose.
        self.write_skill("alpha")
        self.write_skill("bravo")
        self.write_skill("charlie")
        self._install_categories({"Framed": ["alpha", "bravo"], "Plain": ["charlie"]})
        intro_prose = "This section frames the domain-specific skills below."
        body = (
            "# Skill Catalog\n\n"
            "<!-- CATALOG:START -->\n"
            "## Framed\n\n"
            f"{intro_prose}\n\n"
            "| Skill | Description |\n|---|---|\n"
            "| **alpha** | alpha does a thing. |\n"
            "| **bravo** | bravo does a thing. |\n\n"
            "## Plain\n\n"
            "| Skill | Description |\n|---|---|\n"
            "| **charlie** | charlie does a thing. |\n\n"
            "<!-- CATALOG:END -->\n"
        )
        self.write_skills_doc(body)
        self.write_count_files({"space": "3", "tilde": "~3", "hyphen": "3", "agent": "3"})
        doc = self.root / "docs" / "skills.md"

        catalog.render(self.root)
        first = doc.read_text(encoding="utf-8")
        self.assertIn(intro_prose, first,
                      "intra-section intro prose must survive render verbatim")
        # The prose must sit under the Framed heading, ABOVE its table.
        framed_idx = first.index("## Framed")
        prose_idx = first.index(intro_prose)
        table_idx = first.index("| Skill | Description |", framed_idx)
        self.assertLess(framed_idx, prose_idx)
        self.assertLess(prose_idx, table_idx)

        # Second render: prose region byte-identical (round-trip idempotent).
        catalog.render(self.root)
        second = doc.read_text(encoding="utf-8")
        self.assertEqual(first, second,
                         "prose-bearing render must be idempotent on the 2nd render")

        # No-prose control: the Plain section must NOT gain spurious content.
        plain_seg = second[second.index("## Plain"):]
        between = plain_seg.split("| Skill | Description |", 1)[0]
        # only the heading line + blank lines between heading and table
        leftover = between.replace("## Plain", "").strip()
        self.assertEqual(leftover, "",
                         f"no-prose section must gain no spurious content: {leftover!r}")

    # 19
    def test_count_drift_partial_multi_token(self):
        # A single target file with TWO tokens: one == n, one drifted.
        # Pins findall/finditer, not search.
        self.build_clean_fixture()  # true n=4, all tokens correct
        n = len(catalog.parse_skill_names(self.root))
        # workshop's SKILL.md carries multiple count tokens; keep the FIRST
        # correct (~4) and drift a LATER one (42-skill). A .search() first-match
        # implementation would false-PASS; only findall/finditer catches it.
        wsfile = self.root / "skills" / "workshop" / "SKILL.md"
        wsfile.write_text(
            "---\nname: workshop\ndescription: tour\n---\n\n"
            f"About ~{n} skills here. The 42-skill catalog tour.\n",
            encoding="utf-8")
        errs = catalog.check(self.root)
        self.assertTrue(any(self._is_count_drift(e) for e in errs),
                        f"a later drifted token must be flagged (findall, not search): {errs}")

    # 20
    def test_count_target_zero_match(self):
        # A registered target whose token is reworded so the grammar misses it
        # entirely (zero matches) while the file still EXISTS.
        self.build_clean_fixture()
        readme = self.root / "README.md"
        readme.write_text("A toolkit of three Crucible skill modules.\n",
                          encoding="utf-8")  # no digit-form count token
        errs = catalog.check(self.root)
        self.assertTrue(
            any("README.md" in e and ("no count token" in e or "grammar" in e)
                for e in errs),
            f"expected a zero-match bullet for the reworded README count target: {errs}")
        # The zero-match bullet is the ONLY error — fixture otherwise clean at n=4.
        self.assertFalse(
            any("workshop" in e for e in errs),
            f"zero-match fixture must not also flag workshop: {errs}")

    # 21
    def test_eval_claim_phrase_not_a_count_token(self):
        # README carries an eval-claim phrase ("13 core skills are eval-tested")
        # ALONGSIDE the real count token ("4 skills"). The eval phrase has a
        # non-`skills` word ("core") between the digit and "skills", so the
        # generic grammar must NOT capture it as a second count token.
        self.build_clean_fixture()  # true n=4 (alpha/bravo/charlie + workshop)
        n = len(catalog.parse_skill_names(self.root))
        readme = self.root / "README.md"
        # The eval phrase uses a DIFFERENT number (13) deliberately; if it were
        # captured as a count token, check would see 13 != n and false-RED.
        readme.write_text(
            f"A toolkit of {n} skills. 13 core skills are eval-tested.\n",
            encoding="utf-8")
        self.assertEqual(
            catalog.check(self.root), [],
            "the eval-claim phrase '13 core skills' must NOT be captured as a count token")

    # 22 (regression — S2): a multi-paragraph intra-section intro must survive
    # render verbatim (interior blank line preserved) and be idempotent. A
    # non-blank-only join silently fused the two paragraphs into one block.
    def test_section_intro_multiparagraph_preserved(self):
        self.write_skill("alpha")
        self.write_skill("bravo")
        self._install_categories({"Framed": ["alpha", "bravo"]})
        multi = "Para one.\n\nPara two."
        body = (
            "# Skill Catalog\n\n"
            "<!-- CATALOG:START -->\n"
            "## Framed\n\n"
            f"{multi}\n\n"
            "| Skill | Description |\n|---|---|\n"
            "| **alpha** | alpha does a thing. |\n"
            "| **bravo** | bravo does a thing. |\n\n"
            "<!-- CATALOG:END -->\n"
        )
        self.write_skills_doc(body)
        # alpha/bravo + workshop -> true n=3; workshop must be categorized + rowed.
        self._install_categories({"Framed": ["alpha", "bravo"], "Ws": ["workshop"]})
        body = (
            "# Skill Catalog\n\n"
            "<!-- CATALOG:START -->\n"
            "## Framed\n\n"
            f"{multi}\n\n"
            "| Skill | Description |\n|---|---|\n"
            "| **alpha** | alpha does a thing. |\n"
            "| **bravo** | bravo does a thing. |\n\n"
            "## Ws\n\n"
            "| Skill | Description |\n|---|---|\n"
            f"| **workshop** | {self.WORKSHOP_DESC} |\n\n"
            "<!-- CATALOG:END -->\n"
        )
        self.write_skills_doc(body)
        self.write_count_files(self._count_tokens(3))
        doc = self.root / "docs" / "skills.md"

        catalog.render(self.root)
        first = doc.read_text(encoding="utf-8")
        self.assertIn(multi, first,
                      "both paragraphs AND the separating blank line must survive render")

        catalog.render(self.root)
        second = doc.read_text(encoding="utf-8")
        self.assertEqual(first, second,
                         "multi-paragraph-intro render must be idempotent on the 2nd render")

    # 23 (regression — S3): a SKILL.md with no parseable name: must be flagged
    # explicitly (was silently dropped, surfacing only as wrong-total drift).
    def test_unparseable_name_flagged(self):
        self.build_clean_fixture()  # otherwise-clean n=4 (alpha/bravo/charlie+ws)
        # One skill dir whose frontmatter mis-cases the key (`Name:`), so
        # parse_skill_names returns "" for it -> not in disk/CATEGORIES/rows.
        self.write_skill("typo", raw_frontmatter="Name: typo\ndescription: oops")
        errs = catalog.check(self.root)
        self.assertTrue(
            any("skills/typo/SKILL.md" in e and "name" in e.lower() for e in errs),
            f"expected a no-name bullet naming skills/typo/SKILL.md: {errs}")

    # 24 (regression — S4): a missing docs/skills.md must yield a graceful bullet
    # rather than an uncaught FileNotFoundError — AND it must NOT mask the
    # doc-independent count-target checks. A co-occurring count drift (README
    # "999 skills" while n=4) must STILL be reported alongside the missing-doc
    # bullet (the missing-doc early return only short-circuits the bijection).
    def test_missing_skills_doc_graceful(self):
        self.build_clean_fixture()
        n = len(catalog.parse_skill_names(self.root))
        # Drift README's count token so a doc-independent error co-occurs.
        (self.root / "README.md").write_text(
            "A toolkit of 999 skills.\n", encoding="utf-8")
        (self.root / "docs" / "skills.md").unlink()
        try:
            errs = catalog.check(self.root)
        except FileNotFoundError as exc:  # pragma: no cover - guards the fix
            self.fail(f"check must not raise on missing docs/skills.md: {exc!r}")
        self.assertTrue(
            any("docs/skills.md not found" in e for e in errs),
            f"expected a 'docs/skills.md not found' bullet: {errs}")
        self.assertTrue(
            any(self._is_count_drift(e) and "999" in e for e in errs),
            f"missing doc must NOT mask the co-occurring count drift (999 != {n}): {errs}")

    # 25 (regression — R2-Significant): two skills/<dir>/SKILL.md declaring the
    # SAME `name:` dedupe in parse_skill_names's set — undercounting n and making
    # the second dir invisible to every bijection/name guard. The dedicated
    # duplicate-name guard in check() must flag the collision explicitly.
    def test_duplicate_name_flagged(self):
        self.build_clean_fixture()  # otherwise-clean n=4 (alpha/bravo/charlie+ws)
        # Two dirs declaring `name: dup`; the set dedupes them, so without the
        # guard check would silently false-PASS. Give dup a row + category so the
        # ONLY surfaced error is the duplicate-name collision.
        self.write_skill("dup", raw_frontmatter="name: dup\ndescription: dup one")
        d2 = self.root / "skills" / "dup-copy"
        d2.mkdir(parents=True, exist_ok=True)
        (d2 / "SKILL.md").write_text(
            "---\nname: dup\ndescription: dup two\n---\n\n# dup-copy\n",
            encoding="utf-8")
        cats = dict(catalog.CATEGORIES)
        cats["Core"] = cats["Core"] + ["dup"]
        self._install_categories(cats)
        rows = [("Core", [
            ("alpha", "alpha does a thing."),
            ("bravo", "bravo does a thing."),
            ("charlie", "charlie does a thing."),
            ("workshop", self.WORKSHOP_DESC),
            ("dup", "dup does a thing."),
        ])]
        self.write_skills_doc(self.catalog_block(rows))
        errs = catalog.check(self.root)
        self.assertTrue(
            any("duplicate" in e.lower() and "dup" in e for e in errs),
            f"expected a duplicate-name bullet naming 'dup': {errs}")

    # 26 (regression — R2-Minor): render must mirror check's graceful missing-doc
    # handling — a clear SystemExit, not a bare FileNotFoundError (render is
    # operator-invoked, so SystemExit is the right symmetry, not a bullet).
    def test_render_missing_doc_errors(self):
        self.build_clean_fixture()
        (self.root / "docs" / "skills.md").unlink()
        with self.assertRaises(SystemExit):
            catalog.render(self.root)


if __name__ == "__main__":
    unittest.main()
