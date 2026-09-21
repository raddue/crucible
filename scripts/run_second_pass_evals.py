#!/usr/bin/env python3
"""Eval harness for `scripts/second_pass_scorer.py` (#561 fresh round 12 F1/M3).

Invocation (from repo root):
    python3 scripts/run_second_pass_evals.py

Loads `skills/quality-gate/evals/evals.json`, extracts the findings-file text
each relevant fixture quotes inside a fenced code block, runs it through
`second_pass_scorer.score()`, and asserts the result against a hand-mapped
expected-result table built by reading each fixture's `expected_output`
prose (the fixtures predate this harness and encode their expected result as
prose for a human/LLM reviewer, not as structured fields — #561 fresh round
12 dispatch explicitly allows hand-mapping this, documented here rather than
attempted via NLP extraction).

**Scope (documented judgment call).** `evals.json` holds 28 fixtures total
(25 pre-existing + 3 added by fresh round 12, ids 26-28). Evals #1-10 are
general, pre-#561 quality-gate behavioral fixtures (iterative convergence,
checkpoint behavior, etc.) — none of them embeds an already-written findings
file with a single verifiable weighted score; they test different behavior
than this rule and are not fenced findings-file fixtures at all
(grep-verified: #3/#7/#10 embed fenced *code under review*, not a findings
file). Evals #11-25 are the fixtures #561 fresh round 10 S3 added
specifically for Score-source/second-pass-population coverage (see
SKILL.md's INV-T18, which already claims these ids as coverage — M3 in
round-11-findings.md is exactly the gap that #11-25 existing but ungated
left open). Evals #26-28 are fresh round 12's additions: #26 covers S1 (a
section's only matching heading inside a BALANCED, closed fence), #27 covers
the `missing-second-pass-section` flag (a section heading entirely absent),
and #28 covers the severity-token trailing-whitespace fix. Eval #22, despite
sitting inside the #11-25 range round 10 S3 added, is a compaction-recovery
scenario (Round History and Compaction Recovery step 2's terminal-sentinel
carve-out) with no embedded findings file at all — grep-verified no fenced
code block in its prompt — so it is out of scope for the same reason #1-10
are. This harness scores #11-21 and #23-28 and reports #1-10 and #22 as
out-of-scope rather than silently skipped.

Exits 0 with a summary line on success ("N/N evals passed"); exits 1 with a
per-eval mismatch report on failure. Stdlib only.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import second_pass_scorer as spc  # noqa: E402

EVALS_PATH = ROOT / "skills/quality-gate/evals/evals.json"

_FENCE_LINE_RE = re.compile(r"^(`{3,})(\S*)\s*$")

# Evals #1-10 predate this harness and do not embed an already-written
# findings file with a single verifiable score; #22 sits inside the #11-25
# range but is a compaction-recovery scenario with no embedded findings file
# either (see module docstring).
_OUT_OF_SCOPE_IDS = set(range(1, 11)) | {22}


def extract_fenced_block(prompt: str) -> str:
    """Extract the content of the FIRST fenced code block in `prompt`,
    matching the OUTER fence's own backtick run-length for the close (so a
    quoted excerpt's own nested fence, of a shorter run, cannot prematurely
    close it — several fixtures deliberately quote a findings file that
    itself contains nested triple-backtick fences, wrapped in a longer
    4-backtick outer fence for exactly this reason)."""
    lines = prompt.split("\n")
    open_idx = None
    fence_len = None
    for i, line in enumerate(lines):
        m = _FENCE_LINE_RE.match(line)
        if m:
            open_idx = i
            fence_len = len(m.group(1))
            break
    if open_idx is None:
        raise ValueError("no fenced code block found in prompt")
    close_re = re.compile(rf"^`{{{fence_len}}}(?!`)\s*$")
    for j in range(open_idx + 1, len(lines)):
        if close_re.match(lines[j]):
            return "\n".join(lines[open_idx + 1 : j])
    raise ValueError(f"fenced code block (len {fence_len}) not closed")


# ---------------------------------------------------------------------------
# Hand-mapped expected results, keyed by eval id, built by reading each
# fixture's `expected_output` / `expectations` fields (see module docstring).
# `weighted_score` and `clean_pass` are the two fields every fixture states
# unambiguously; `flags`/`minor_count`/`route` are checked only where a
# fixture explicitly speaks to them.
# ---------------------------------------------------------------------------
EXPECTED: dict[int, dict] = {
    11: dict(weighted_score=3, clean_pass=False),
    12: dict(weighted_score=3, clean_pass=False),
    13: dict(weighted_score=0, clean_pass=True),
    14: dict(weighted_score=3, clean_pass=False),
    15: dict(
        weighted_score=0,
        clean_pass=True,
        candidate_clean=False,
        discrepancy=True,
        empty_work_order_escalation=True,
        route="escalate-empty-work-order",
    ),
    16: dict(weighted_score=0, clean_pass=True, minor_count=1),
    17: dict(weighted_score=0, clean_pass=True),
    18: dict(
        weighted_score=1,
        clean_pass=False,
        discrepancy=True,
        empty_work_order_escalation=False,
        route="fix-loop-discrepancy",
    ),
    19: dict(weighted_score=3, clean_pass=False),
    20: dict(weighted_score=6, clean_pass=False),
    21: dict(weighted_score=3, clean_pass=False),
    23: dict(weighted_score=3, clean_pass=False),
    24: dict(weighted_score=9, clean_pass=False, flags={"malformed-second-pass-sectioning"}),
    25: dict(weighted_score=3, clean_pass=False, flags={"malformed-second-pass-sectioning"}),
    # ------------------------------------------------------------------
    # Fresh round 12 additions (added to evals.json itself, not just this
    # harness, per the round-12 dispatch's S1 / Second-Pass-finding fix
    # shape).
    # ------------------------------------------------------------------
    # S1 (Significant): a section whose only matching heading sits inside a
    # BALANCED, CLOSED fence — no fence-parity defect at all — must still
    # trigger the zero-match/raw-heading-relocation fallback (round-12 fix:
    # trigger on the observable zero-unexcluded-match count, not on a
    # diagnosed cause).
    26: dict(weighted_score=3, clean_pass=False, flags={"malformed-second-pass-sectioning"}),
    # missing-second-pass-section: `### Minor Observations` is entirely
    # absent from the file (not even under the raw-heading fallback) — the
    # flag must be set (fresh round 12 F1 inversion 4: an equivalent-shaped
    # mutation drops this flag while leaving the score unaffected, so the
    # flag itself is the only observable signal this fixture can pin).
    27: dict(weighted_score=0, clean_pass=True, flags={"missing-second-pass-section"}),
    # Second Pass finding: severity-token trailing whitespace. A Fatal entry
    # whose `**Severity:**` line has exactly one trailing space must still
    # recognise as Fatal (round-12 fix: strip trailing whitespace from the
    # value before the boundary test, symmetric with the existing
    # leading-whitespace strip).
    28: dict(weighted_score=3, clean_pass=False),
}

def _check(eval_id, result: spc.ScoreResult, expected: dict) -> list[str]:
    errs = []
    for field_name, want in expected.items():
        if field_name == "flags":
            got = result.flags
            if not want.issubset(got):
                errs.append(f"eval {eval_id}: expected flags {want} subset of got {got}")
            continue
        got = getattr(result, field_name)
        if got != want:
            errs.append(f"eval {eval_id}: expected {field_name}={want!r}, got {got!r}")
    return errs


def main() -> int:
    data = json.loads(EVALS_PATH.read_text())
    evals = {e["id"]: e for e in data["evals"]}

    all_errors: list[str] = []
    passed = 0
    total = 0

    for eval_id, expected in sorted(EXPECTED.items()):
        total += 1
        ev = evals.get(eval_id)
        if ev is None:
            all_errors.append(f"eval {eval_id}: not found in evals.json")
            continue
        try:
            findings_text = extract_fenced_block(ev["prompt"])
        except ValueError as exc:
            all_errors.append(f"eval {eval_id}: {exc}")
            continue
        result = spc.score(findings_text)
        errs = _check(eval_id, result, expected)
        if errs:
            all_errors.extend(errs)
        else:
            passed += 1

    out_of_scope = sorted(set(evals.keys()) & _OUT_OF_SCOPE_IDS)

    if all_errors:
        print(f"FAIL: {passed}/{total} evals passed", file=sys.stderr)
        for e in all_errors:
            print(f"- {e}", file=sys.stderr)
        return 1

    print(f"{passed}/{total} evals passed")
    print(
        f"(evals {out_of_scope} are out-of-scope general behavioral fixtures — "
        "no embedded findings file with a single verifiable score; see module docstring)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
