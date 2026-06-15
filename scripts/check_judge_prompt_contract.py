#!/usr/bin/env python3
"""Judge-prompt contract check for the inquisitor eval harness (#424).

Invocation (from repo root):
    python3 scripts/check_judge_prompt_contract.py            # check committed file
    python3 scripts/check_judge_prompt_contract.py --selftest # built-in logic tests

Asserts `skills/inquisitor/evals/judge-prompt.md` encodes the reconciled
**tagged-union** judge contract (S-FIND-2) AND instructs the **per-item
verdict-record output schema** (S2):

  REQUIRED — the prompt MUST reference the `tag` field and the `primary`/`secondary`
    tag values, AND instruct the per-item output record by naming the `id`, `tag`,
    and `verdict` fields as quoted JSON output keys (not merely mention `tag`).
  FORBIDDEN — the prompt MUST NOT reproduce the gated design's stale per-expectation
    framing (`per-expectation`, or the `(arm output, fixture expectations)` phrasing
    from design L272), which graded `(arm output, fixture expectations)` per
    expectation instead of grading the tagged union per item.

Why this exists separately from the unit tests: the unit tests feed `score`
*synthetic* tagged-union verdict files (tests 3/3b/3c), so they exercise the
*parser* but structurally cannot catch a committed judge prompt that grades
per-expectation OR omits the `id`+`tag`+`verdict` record `score` actually parses.
This static check pins both the input contract and the output schema in CI.

Stdlib only. Exit 0 clean / 1 on violation.
"""
from __future__ import annotations
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
JUDGE_PROMPT = ROOT / "skills/inquisitor/evals/judge-prompt.md"

# Bare-token references to the tagged-union field + values, plus the quoted JSON
# output keys that pin the per-item verdict record (S2 — not merely a `tag` mention),
# plus the load-bearing non-comparative / per-item discipline anchors (S2-followup).
#
# The non-comparative anchors pin judge-prompt.md L11-12 verbatim ("You are grading
# ONE arm's review output … you are NOT comparing one arm's output to another"). A
# comparative-grading rewrite — one that keeps the tagged-union record schema but
# grades "which arm is better / ranks the arms" — silently turns WITH−WITHOUT into a
# verbosity/comparison artifact biased toward the higher-output arm, defeating the
# whole control. Such a rewrite would necessarily drop these sentences → the check
# fails. Anchored as REQUIRED (collision-free) rather than FORBIDDEN: the literal
# "which arm is better" appears in the explanatory L7 HTML comment, so it must NOT be
# added to FORBIDDEN (it would false-FAIL the committed file). "NOT comparing one arm"
# is contiguous in the committed prompt and absent from that comment.
REQUIRED = ("tag", "primary", "secondary", '"id"', '"tag"', '"verdict"',
            "grading ONE arm", "NOT comparing one arm")
# The design's retired per-expectation framing (design L272 / L278-284).
FORBIDDEN = ("per-expectation", "arm output, fixture expectations")


def violations(text: str) -> list:
    """Return contract-violation strings for `text` (empty == compliant)."""
    out = []
    for tok in REQUIRED:
        if tok not in text:
            out.append(f"missing required token {tok!r}")
    for tok in FORBIDDEN:
        if tok in text:
            out.append(f"contains forbidden stale per-expectation phrasing {tok!r}")
    return out


def main() -> int:
    text = JUDGE_PROMPT.read_text(encoding="utf-8")
    errs = violations(text)
    if errs:
        rel = JUDGE_PROMPT.relative_to(ROOT)
        print(f"JUDGE-PROMPT CONTRACT VIOLATIONS in {rel}:")
        for e in errs:
            print(f"  {e}")
        print("\nThe judge prompt must grade the tagged-union item list per item "
              "(referencing `tag` / `primary` / `secondary`) and instruct the "
              'per-item `{"id","tag","verdict"}` output record — not the design\'s '
              "retired per-expectation framing.")
        return 1
    print("OK — judge-prompt.md encodes the tagged-union contract + the per-item "
          "id/tag/verdict record schema, with no stale per-expectation phrasing.")
    return 0


def selftest() -> int:
    """Built-in logic tests (in-memory) for the contract scan."""
    good = (
        "You are grading ONE arm's review output. You are NOT comparing one arm's "
        "output to another.\n"
        "Grade each item by its `tag` (`primary` or `secondary`).\n"
        "For each item: is THIS issue identified? PASS/FAIL.\n"
        'Emit one JSON object per item: {"id": "f1-b1", "tag": "primary", '
        '"verdict": "PASS"}\n'
    )
    bad_per_exp = good + (
        "Grade per-expectation against (arm output, fixture expectations).\n")
    bad_no_tag = (
        "You are grading ONE arm's review output. You are NOT comparing one arm's "
        "output to another.\n"
        'Emit one JSON object per item: {"id": "x", "verdict": "PASS"}\n')
    bad_no_record = (
        "You are grading ONE arm's review output. You are NOT comparing one arm's "
        "output to another.\n"
        "Grade each item by its `tag` (`primary` or `secondary`). Output PASS "
        "or FAIL.\n")
    # S2-followup: a comparative-grading rewrite that keeps the tagged-union record
    # schema (all REQUIRED tag/record tokens) but DROPS the non-comparative anchor
    # and grades "which arm found more / rank the arms" must now FAIL — without the
    # anchor it would pass CI green while turning WITH−WITHOUT into a verbosity
    # artifact. (Note: it includes the L7-comment substring "which arm is better" to
    # prove that string is NOT forbidden — only the REQUIRED anchor catches this.)
    bad_comparative = (
        "Grade each item by its `tag` (`primary` or `secondary`).\n"
        "Compare the arms and rank which found more bugs; decide which arm is "
        "better.\n"
        'Emit one JSON object per item: {"id": "f1-b1", "tag": "primary", '
        '"verdict": "PASS"}\n'
    )
    cases = [
        (good, False, "reconciled tagged-union + per-item record + anchor passes"),
        (bad_per_exp, True, "stale per-expectation phrasing fails"),
        (bad_no_tag, True, "missing tag/primary/secondary references fails"),
        (bad_no_record, True,
         "mentions tag but omits the id+verdict per-item record fails (S2)"),
        (bad_comparative, True,
         "comparative rewrite dropping the non-comparative anchor fails (S2-followup)"),
    ]
    failures = []
    for text, expect_fail, reason in cases:
        got = bool(violations(text))
        if got != expect_fail:
            failures.append(f"  expected fail={expect_fail} ({reason}), got={got}")
    if failures:
        print("SELFTEST FAILED:")
        print("\n".join(failures))
        return 1
    print("SELFTEST OK — contract check fires on stale phrasing, missing "
          "tag-references, a missing per-item id+verdict record, and a comparative "
          "rewrite that drops the non-comparative anchor; the reconciled form passes.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    sys.exit(main())
