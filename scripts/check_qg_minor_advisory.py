#!/usr/bin/env python3
"""Structural check: clean-pass Minor advisory (#362).

Invocation (from repo root):
    python3 scripts/check_qg_minor_advisory.py
    python3 scripts/check_qg_minor_advisory.py --selftest

Path-pinned to exactly ONE target file — the quality-gate SKILL.md. This checker
NEVER rglobs; the path pinning is what prevents a self-match (a checker that never
globs cannot read itself), so the pinned phrases need NOT be obfuscated/split.

Path-pinning to `quality-gate/SKILL.md` is load-bearing (mirrors the sibling
check_qg_stagnation_minor.py): the checker must NOT scan `red-team/SKILL.md`, whose
"Only Fatal and Significant count" / Minors-"don't count toward stagnation" lines are
deliberately retained per the #358 two-vocabulary separation — they would be
false-positive matches for a Minor-semantics checker. It is therefore intentionally
scoped away from those intentionally-retained lines.

Asserts (INV-T17) against `skills/quality-gate/SKILL.md`:
  (a) the `MinorAdvisory` marker enum `density | trajectory | density+trajectory`
      is present AND declared omit-when-none;
  (b) the `MinorTrajectory` marker field is present AND described as mirroring
      `ScoreTrajectory`;
  (c) the convergence-log `minor_advisory` value-set is present inside the
      `<!-- CONTRACT:qg-minor-advisory:START -->` … `:END -->` block, carrying the
      quoted enum forms `"density"`, `"trajectory"`, `"density+trajectory"` and the
      `| null` value-set token (enumeration form — the JSON contract, not editable
      prose);
  (d) a REQUIRED-PRESENT guard that the advisory text states it never changes the
      verdict / never blocks;
  (e) the COMPLETE constant pin set `{ K = 5, R ≥ 3, ≥1-recurring-Minor }` — each of
      `K = 5`, `R ≥ 3`, and the recurrence threshold "≥1 Minor recurring across all
      three rounds R-2, R-1, R" — so no load-bearing constant can silently drift.

Exits 0 when aligned, 1 with a `- <error>` list otherwise. Stdlib only.
See scripts/CHECKER_CONVENTIONS.md.
"""
from __future__ import annotations
import pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills/quality-gate/SKILL.md"


def check_skill(text: str) -> list[str]:
    errs: list[str] = []

    # (a) MinorAdvisory marker enum + omit-when-none.
    if "MinorAdvisory" not in text:
        errs.append("SKILL: missing 'MinorAdvisory' marker field")
    if "density | trajectory | density+trajectory" not in text:
        errs.append(
            "SKILL: missing MinorAdvisory enum "
            "'density | trajectory | density+trajectory'"
        )
    if "omit-when-none" not in text:
        errs.append(
            "SKILL: MinorAdvisory not declared 'omit-when-none' (presence convention drift)"
        )

    # (b) MinorTrajectory present + mirrors ScoreTrajectory.
    if "MinorTrajectory" not in text:
        errs.append("SKILL: missing 'MinorTrajectory' marker field")
    if "mirroring ScoreTrajectory" not in text:
        errs.append(
            "SKILL: MinorTrajectory not described as 'mirroring ScoreTrajectory'"
        )

    # (c) convergence-log minor_advisory value-set, CONTRACT-block scoped.
    m = re.search(
        r"<!-- CONTRACT:qg-minor-advisory:START.*?-->(.*?)<!-- CONTRACT:qg-minor-advisory:END",
        text, re.DOTALL,
    )
    if m is None:
        errs.append(
            "SKILL: minor_advisory CONTRACT block not found "
            "(<!-- CONTRACT:qg-minor-advisory:START --> … :END -->)"
        )
    else:
        block = m.group(1)
        if not block.strip():
            errs.append("SKILL: minor_advisory CONTRACT block is empty")
        else:
            for quoted in ('"density"', '"trajectory"', '"density+trajectory"'):
                if quoted not in block:
                    errs.append(
                        f"SKILL: minor_advisory CONTRACT block missing quoted enum value {quoted}"
                    )
            if "| null" not in block:
                errs.append(
                    "SKILL: minor_advisory CONTRACT block missing the `| null` value-set token"
                )

    # (d) never-changes-verdict / never-blocks guard.
    if "never changes the verdict" not in text:
        errs.append(
            "SKILL: missing the advisory 'never changes the verdict' guarantee"
        )
    if "never blocks" not in text:
        errs.append("SKILL: missing the advisory 'never blocks' guarantee")

    # (e) complete constant pin set { K = 5, R ≥ 3, ≥1-recurring-Minor }.
    if "K = 5" not in text:
        errs.append("SKILL: missing density constant 'K = 5'")
    if "R ≥ 3" not in text:
        errs.append("SKILL: missing trajectory window constant 'R ≥ 3'")
    if "≥1 Minor recurring across all three rounds R-2, R-1, R" not in text:
        errs.append(
            "SKILL: missing trajectory recurrence threshold "
            "'≥1 Minor recurring across all three rounds R-2, R-1, R'"
        )

    return errs


def _read(path: pathlib.Path, errs: list[str]) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, UnicodeDecodeError, OSError) as err:
        errs.append(f"{path} missing or unreadable: {err}")
        return None


# A minimal fixture carrying every pinned phrase — the positive control for
# --selftest. If check_skill reports any error on this, the checker is broken.
_GOOD_FIXTURE = """
MinorTrajectory: <per-round Minor counts; exactly mirroring ScoreTrajectory>
MinorAdvisory: density | trajectory | density+trajectory   # omit-when-none
The advisory never changes the verdict or precedence; it never blocks.
Constants { K = 5, R ≥ 3, ≥1-recurring-Minor }: density fires at K = 5; trajectory
fires when R ≥ 3 AND ≥1 Minor recurring across all three rounds R-2, R-1, R.
<!-- CONTRACT:qg-minor-advisory:START -->
- minor_advisory value set: "density" | "trajectory" | "density+trajectory" | null
<!-- CONTRACT:qg-minor-advisory:END -->
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

    # Mutations that must each be detected (one pinned phrase removed per case).
    mutations = {
        "MinorAdvisory field": "MinorAdvisory",
        "MinorAdvisory enum": "density | trajectory | density+trajectory",
        "omit-when-none": "omit-when-none",
        "MinorTrajectory field": "MinorTrajectory",
        "mirroring ScoreTrajectory": "mirroring ScoreTrajectory",
        "never changes the verdict": "never changes the verdict",
        "never blocks": "never blocks",
        "K = 5": "K = 5",
        "R ≥ 3": "R ≥ 3",
        "recurrence threshold": "≥1 Minor recurring across all three rounds R-2, R-1, R",
        "CONTRACT block": "<!-- CONTRACT:qg-minor-advisory:END",
        "| null value-set token": "| null",
        "quoted enum \"density\"": '"density"',
        "quoted enum \"trajectory\"": '"trajectory"',
        "quoted enum \"density+trajectory\"": '"density+trajectory"',
    }
    for label, needle in mutations.items():
        broken = _GOOD_FIXTURE.replace(needle, "")  # remove ALL occurrences
        if not check_skill(broken):
            errs.append(
                f"selftest: removing '{label}' did NOT trip the checker (no-op grep)"
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
        print("QG MINOR-ADVISORY DRIFT DETECTED:")
        for e in errs:
            print(f"  - {e}")
        return 1
    print(
        "OK — clean-pass Minor advisory: MinorAdvisory/MinorTrajectory marker fields, "
        "convergence-log minor_advisory schema, never-blocks guarantee, and the "
        "{ K=5, R≥3, ≥1-recurring-Minor } constant set all present and aligned."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
