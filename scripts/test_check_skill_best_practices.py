#!/usr/bin/env python3
"""Hermetic checks for the warn-only skill practices audit."""
from pathlib import Path
from tempfile import TemporaryDirectory

import check_skill_best_practices as checker


def skill(root: Path, name: str, body: str = "# Skill\n", description: str = "Checks skills when auditing.") -> Path:
    path = root / "skills" / name / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nname: {name}\ndescription: {description}\n---\n{body}")
    return path


def main() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        path = skill(root, "one", "# Skill\n" * 500)
        assert not checker.audit(root)["one"]["Body"]
        path.write_text(path.read_text() + "extra\n")
        assert checker.audit(root)["one"]["Body"]

        path = skill(root, "one", "# Skill\nSee [a](references/a.md) and [b](references/b.md).\n")
        refs = path.parent / "references"
        refs.mkdir()
        (refs / "a.md").write_text("# A\n" + "line\n" * 99)
        (refs / "b.md").write_text("# B\n")
        assert not checker.audit(root)["one"]["Contents"]
        (refs / "a.md").write_text("# A\n" + "line\n" * 100)
        assert checker.audit(root)["one"]["Contents"]
        (refs / "a.md").write_text("# A\n## Contents\n- [Usage](#usage)\n- [Notes](#notes)\n"
                                  + "line\n" * 100 + "## Usage\n## Notes\nSee [b](b.md).\n")
        assert not checker.audit(root)["one"]["Contents"]
        (refs / "a.md").write_text("# A\n## Contents\n- Usage\n- Notes\n"
                                  + "line\n" * 100 + "## Usage\n## Notes\nSee [b](b.md).\n")
        assert not checker.audit(root)["one"]["Contents"]
        assert not checker.audit(root)["one"]["Nesting"]  # b is linked directly
        path.write_text(path.read_text().replace(" and [b](references/b.md)", ""))
        assert checker.audit(root)["one"]["Nesting"]
        path.write_text(path.read_text().replace("[a](references/a.md)", "`references/a.md`"))
        assert not checker.audit(root)["one"]["Nesting"]
        assert not checker.audit(root)["one"]["Contents"]

        skill(root, "bad", description="Use when checking things.")
        assert not checker.audit(root)["bad"]["Frontmatter"]
        skill(root, "bad", description="Checks things when you need them.")
        assert checker.audit(root)["bad"]["Frontmatter"]
        assert not checker.audit(root)["one"]["Frontmatter"]
        skill(root, "bad", description="Checks things.")
        assert any("when" in item.lower() for item in checker.audit(root)["bad"]["Frontmatter"])
        skill(root, "bad", description="Checks things when needed.")
        assert not checker.audit(root)["bad"]["Frontmatter"]
        skill(root, "bad", description="Checks things when needed. Use when checking.")
        assert not checker.audit(root)["bad"]["Frontmatter"]
        skill(root, "bad", description="Checks things when needed. Invoke when checking.")
        assert not checker.audit(root)["bad"]["Frontmatter"]
        for description in ('Triggers on "review my changes".',
                            "Triggers on 'what should I refactor'.",
                            'Checks I/O conventions, i.e. files, before audit.',
                            'Checks skills after changes.'):
            skill(root, "bad", description=description)
            assert not checker.audit(root)["bad"]["Frontmatter"], description
        (root / "skills" / "bad" / "SKILL.md").write_text(
            "---\nname: " + "a" * 65 + "\ndescription: " + "x" * 1025 + "\n---\n# Skill\n")
        assert len(checker.audit(root)["bad"]["Frontmatter"]) >= 2

        path = skill(root, "one", "# Skill\n<!-- CANONICAL: shared/common.md — usage notes -->\n")
        common = root / "skills" / "shared" / "common.md"
        common.parent.mkdir(exist_ok=True)
        common.write_text("# Common\n" + "line\n" * 100 + "See [extra](extra.md).\n")
        (common.parent / "extra.md").write_text("# Extra\n")
        assert any("common.md" in issue for issue in checker.audit(root)["one"]["Contents"])
        assert checker.audit(root)["one"]["Nesting"]
        common.write_text(common.read_text().replace("See [extra](extra.md).", "See `extra.md`."))
        assert not checker.audit(root)["one"]["Nesting"]
        common.write_text(common.read_text().replace("See `extra.md`.", "See [extra](extra.md)."))
        (common.parent / "extra.md").write_text("# Extra\n" + "line\n" * 100)
        assert any("extra.md" in issue for issue in checker.audit(root)["one"]["Contents"])
        for toc in ("**Contents**\n1. Usage\n2. Notes", "## Contents\n1. [Usage](#usage)\n2. [Notes](#notes)",
                    "## Contents\nUsage and notes follow below.",
                    "- Unrelated introduction bullet\n## Contents\n- Usage\n- Notes"):
            common.write_text("# Common\n" + toc + "\n" + "line\n" * 100 + "## Usage\n## Notes\n")
            assert not checker.audit(root)["one"]["Contents"], toc
        common.write_text("# Common\nIntro prose.\n## Contents\nNothing useful listed.\n"
                          + "line\n" * 100 + "## Usage\n## Notes\n")
        assert checker.audit(root)["one"]["Contents"]
        for prose in ("Arbitrary prose unrelated to sections.", "The guidance follows."):
            common.write_text("# Common\n## Contents\n" + prose + "\n" + "line\n" * 100
                              + "## CI — I/O & a\n")
            assert checker.audit(root)["one"]["Contents"], prose
        skill(root, "one", "# Skill\nRun `python3 scripts/helper.py`.\n")
        assert checker.audit(root)["one"]["Scripts"]
        skill(root, "one", "# Skill\nRequires Python 3; no install needed.\nRun `python3 scripts/helper.py`.\n")
        assert not checker.audit(root)["one"]["Scripts"]

        skill(root, "bom", description="Checks BOM when auditing.")
        bom = root / "skills" / "bom" / "SKILL.md"
        bom.write_bytes(b"\xef\xbb\xbf" + bom.read_bytes())
        assert not checker.audit(root)["bom"]["Frontmatter"]
        bom.write_bytes(b"\xff\xfe")
        assert any("cannot read UTF-8" in issue for issue in checker.audit(root)["bom"]["Frontmatter"])
        broken = root / "skills" / "one" / "references" / "broken.md"
        broken.write_bytes(b"\xff\xfe")
        skill(root, "one", "# Skill\nSee [broken](references/broken.md).\n")
        assert checker.audit(root)["one"]["Contents"]
        assert checker.main(root) == 0
        for excluded in ("shared", "skill-selection-evals", "temper-eval-collect", "temper-eval-calibrate"):
            skill(root, excluded, "# Skill\n" * 501)
        result = checker.audit(root)
        assert set(result) == {"one", "bad", "bom"}
        report = checker.render(result)
        assert "| one |" in report and "| bad |" in report and "| TOTAL |" in report
        target = root / "docs" / "skill-practices-audit.md"
        assert not target.exists()
        assert checker.main(root) == 0 and not target.exists()
        assert checker.main(root, write_report=True) == 0 and target.is_file()
        target.write_text("sentinel")
        assert checker.main(root) == 0 and target.read_text() == "sentinel"
    print("skill best practices self-test OK")


if __name__ == "__main__":
    main()
