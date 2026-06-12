#!/usr/bin/env python3
"""Structural check: Minor-aware stagnation judge + DR-Cause discriminator (#260).

Invocation (from repo root):
    python3 scripts/check_qg_stagnation_minor.py

Path-pinned to exactly two target files — the quality-gate stagnation judge
prompt and the quality-gate SKILL.md. This checker NEVER rglobs; the path
pinning is what prevents a self-match (a checker that never globs cannot read
itself), so the pinned phrases need NOT be obfuscated/split.

Path-pinning to `quality-gate/SKILL.md` is load-bearing: the checker must NOT
scan `red-team/SKILL.md`, whose "Only Fatal and Significant count" /
external-findings "do NOT count toward stagnation scoring" lines are
deliberately retained per the #358 two-vocabulary separation (design D2). It
is therefore intentionally scoped away from those intentionally-retained lines.

Asserts:
  Group A (JUDGE prompt):
    - the Minor-accumulation Mixed-branch rule, signature phrase scoped WITHIN
      the Step-3 `Mixed (some recurring, some new):` block (after that anchor,
      before `### Step 4`) — guards against drift back into the unreachable
      All-new / Step-4 placement;
    - the persisted `Consecutive recurring-Minor rounds` counter line;
    - the bold-safe `DR-Cause:` label AND the bare enum value
      `minor-accumulation | structural-saturation | none` (two separate pins —
      never the combined `**DR-Cause:** value` substring that straddles `**`).
  Group B (SKILL Minor prose):
    - B1: the un-reconciled `do not trigger fix rounds and do not count toward
      stagnation` clause is GONE — a verbatim REQUIRED-ABSENT guard (you cannot
      marker-wrap an absent string; the exact wording is the thing barred);
    - B2: the Minor-accumulation rule is present, asserted via the structural
      `<!-- CONTRACT:qg-minor-stagnation-prose -->` anchor (#399) rather than the
      old verbatim phrase, so the paragraph re-words freely on this hot file.
  Group C (SKILL convergence-log `dr_cause` schema), CONTRACT-block scoped (#399):
    - locate the `<!-- CONTRACT:qg-dr-cause:START -->` … `:END -->` block (this
      replaces the brittle two-stage `**Field semantics…**`→bullet prose regex);
    - require the block non-empty AND carrying the quoted/literal enum forms
      `"minor-accumulation"`, `"structural-saturation"`, `"consensus"`, and the
      `| null` value-set token (enumeration form, not incidental prose; the
      `consensus` sentinel is the load-bearing pin — absent from the judge
      prompt's 3-value enum). The enum VALUES stay pinned: they are the JSON
      contract, not editable prose. See scripts/CHECKER_CONVENTIONS.md.

Every pin lies strictly INTERIOR to any `**…**` bold span (bare labels /
values, never a substring that includes or straddles a `**`). Exits 0 when
aligned, 1 with a `- <error>` list otherwise. Stdlib only.
"""
from __future__ import annotations
import pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
JUDGE = ROOT / "skills/quality-gate/stagnation-judge-prompt.md"
SKILL = ROOT / "skills/quality-gate/SKILL.md"


def check_judge(text: str) -> list[str]:
    errs: list[str] = []

    # Group A: persisted counter line (bare phrase, interior to bold) + the rule.
    if "Consecutive recurring-Minor rounds" not in text:
        errs.append(
            "JUDGE: missing 'Consecutive recurring-Minor rounds' counter line"
        )

    rule_sig = "zero recurring Fatals and zero recurring Significants"
    if rule_sig not in text:
        errs.append(
            f"JUDGE: missing Minor-accumulation rule signature '{rule_sig}'"
        )

    # Section-anchored placement: the signature phrase must occur WITHIN the
    # Step-3 Mixed branch (after its anchor, before `### Step 4`) — block-scoping
    # idiom mirrored from check_canonical_drift.py.
    m = re.search(
        r"Mixed \(some recurring, some new\):(.*?)(?=### Step 4)",
        text, re.DOTALL,
    )
    if m is None:
        errs.append(
            "JUDGE: Step-3 'Mixed (some recurring, some new):' block not found "
            "(before '### Step 4')"
        )
    elif rule_sig not in m.group(1):
        errs.append(
            "JUDGE: Minor-accumulation signature phrase not inside the Step-3 "
            "Mixed block (drifted toward the unreachable All-new/Step-4 placement)"
        )

    # DR-Cause: bold-safe two-pin (bare label + bare enum value).
    if "DR-Cause:" not in text:
        errs.append("JUDGE: missing 'DR-Cause:' label")
    if "minor-accumulation | structural-saturation | none" not in text:
        errs.append(
            "JUDGE: missing DR-Cause enum value "
            "'minor-accumulation | structural-saturation | none'"
        )

    return errs


def check_skill(text: str) -> list[str]:
    errs: list[str] = []

    # Group B: Minor prose reconciliation.
    #   B1 (stale clause must be ABSENT) stays a verbatim guard — you cannot
    #   marker-wrap an absent string, and the exact wording IS the thing barred.
    stale = "do not trigger fix rounds and do not count toward stagnation"
    if stale in text:
        errs.append(
            f"SKILL: un-reconciled Minor clause still present: '{stale}'"
        )
    #   B2 (the reworded anchor must be PRESENT) migrated from verbatim prose to
    #   a structural CONTRACT anchor (#399) — the Minor-stagnation paragraph on
    #   the repo's hottest file is now freely re-wordable; the anchor is the guard.
    if "CONTRACT:qg-minor-stagnation-prose" not in text:
        errs.append(
            "SKILL: missing CONTRACT anchor 'qg-minor-stagnation-prose' marking the "
            "Minor-accumulation stagnation rule (the rule's paragraph was deleted, "
            "not merely reworded)"
        )

    # Group C: convergence-log dr_cause value-set enum. The brittle two-stage
    # prose-anchored scope ('**Field semantics for the new entries:**' → the
    # dr_cause bullet) is replaced by a START/END CONTRACT block (#399); the
    # enum VALUES inside stay pinned — they are the JSON contract, not prose.
    m = re.search(
        r"<!-- CONTRACT:qg-dr-cause:START.*?-->(.*?)<!-- CONTRACT:qg-dr-cause:END",
        text, re.DOTALL,
    )
    if m is None:
        errs.append(
            "SKILL: dr_cause CONTRACT block not found "
            "(<!-- CONTRACT:qg-dr-cause:START --> … <!-- CONTRACT:qg-dr-cause:END -->)"
        )
        return errs

    block = m.group(1)
    if not block.strip():
        errs.append("SKILL: dr_cause CONTRACT block is empty")
        return errs
    for quoted in ('"minor-accumulation"', '"structural-saturation"', '"consensus"'):
        if quoted not in block:
            errs.append(
                f"SKILL: dr_cause CONTRACT block missing quoted enum value {quoted}"
            )
    # Require `null` as a value-set token (enumeration form
    # `... | "consensus" | null`), not incidental prose like "null ambiguity".
    if "| null" not in block:
        errs.append(
            "SKILL: dr_cause CONTRACT block missing the `| null` value-set token"
        )

    return errs


def _read(path: pathlib.Path, errs: list[str]) -> str | None:
    """Read a pinned target file; on failure append a clean error (no crash)."""
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, UnicodeDecodeError, OSError) as err:
        errs.append(f"{path} missing or unreadable: {err}")
        return None


def main() -> int:
    errs: list[str] = []
    judge_text = _read(JUDGE, errs)
    skill_text = _read(SKILL, errs)
    if judge_text is not None:
        errs += check_judge(judge_text)
    if skill_text is not None:
        errs += check_skill(skill_text)
    if errs:
        print("QG STAGNATION-MINOR DRIFT DETECTED:")
        for e in errs:
            print(f"  - {e}")
        return 1
    print(
        "OK — Minor-aware judge rule + DR-Cause enum + reconciled Minor prose "
        "+ convergence-log dr_cause schema all present and aligned."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
