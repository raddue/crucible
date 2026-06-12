#!/usr/bin/env python3
"""Structural checker for the #366 red-team ↔ quality-gate Evidence Receipt contract.

Invocation (from repo root):
    python3 scripts/check_rt_receipt_contract.py

Acceptance test for #366 (design:
`docs/plans/2026-06-06-366-rt-qg-receipt-contract-design.md`). Asserts the design's
acceptance criteria over exactly FOUR named skill-methodology Markdown files:

    skills/red-team/red-team-prompt.md   — Report Format / RCPT v1.1 / worked examples
    skills/quality-gate/SKILL.md         — consumption + fix-agent supersession + writer-inversion
    skills/red-team/SKILL.md             — standalone consumption (Tier-1 lint, no Layer-2 sweep)
    skills/shared/return-convention.md   — kind=grep artifact/range clarification

Each assertion is keyed to a design AC and carries an ID prefix ([A1], [C13], …) in
its violation string. Every assertion pins on a token/phrase the corresponding edit
INTRODUCES (absent in the unedited file) so it discriminates RED→GREEN; [A6] is the
sole exception — a retain-guard that is GREEN at baseline and only goes RED if a
future edit DELETES the rich findings sections.

The quality-gate/SKILL.md present-pins that used to assert verbatim English prose
([C14] "orchestrator-supplied", [C15] "cited artifact", [C18] witness phrasing, [C18b]
"initial writer") were migrated to structural `<!-- CONTRACT:NAME -->` anchors (#399)
so a benign wording edit on the repo's hottest file no longer trips CI — the anchor is
the regression guard, the prose inside is freely editable. The code-token pins
([C13] `### … Challenges`, [C16] `TRIPWIRE: none`, [C17] `ARTIFACTS`) stay verbatim:
editing those IS a contract change. See scripts/CHECKER_CONVENTIONS.md.

NO directory tree-walk: only the four named files are read, so the checker can never
self-match its own literal pin strings (CONTRACT anchors included). Stdlib only
(`pathlib`, `re`, `sys`).
Exits 0 if all assertions hold, 1 with a bulleted violation list otherwise.

Mirrors `scripts/check_canonical_drift.py` and `scripts/check_i2_marker.py`.
"""
from __future__ import annotations
import pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
RT_PROMPT = ROOT / "skills/red-team/red-team-prompt.md"
QG_SKILL = ROOT / "skills/quality-gate/SKILL.md"
RT_SKILL = ROOT / "skills/red-team/SKILL.md"
RETURN_CONV = ROOT / "skills/shared/return-convention.md"

# Worked-example markers Task 1 DECLARES and Task 2 emits verbatim (load-bearing
# coupling — the checker keys block extraction off these exact strings).
PASS_MARKER = "<!-- worked-example: PASS -->"
FAIL_MARKER = "<!-- worked-example: FAIL -->"


# ---------------------------------------------------------------------------
# A. red-team-prompt.md — Report Format / RCPT v1.1 (design AC#1, #2)
# ---------------------------------------------------------------------------

def check_rt_prompt(text: str) -> list[str]:
    errs: list[str] = []

    # [A1] receipt header token
    if "RCPT v1.1" not in text:
        errs.append("[A1] red-team-prompt.md: missing receipt header token 'RCPT v1.1'")

    # [A2] all seven receipt section labels — CASE-SENSITIVE uppercase labels.
    # The existing prose `Verdict:` / `Confidence` must NOT satisfy these pins.
    for label in ("VERDICT", "ARTIFACTS", "TRACE", "CLAIMS", "WITNESS", "SUSPICION", "NEXT"):
        if label not in text:
            errs.append(f"[A2] red-team-prompt.md: missing uppercase receipt label '{label}'")

    # [A3] mandatory v1.1 lines
    for tok in ("TRIPWIRE:", "SUPERSEDES:"):
        if tok not in text:
            errs.append(f"[A3] red-team-prompt.md: missing mandatory v1.1 line token '{tok}'")

    # [A4] findings-output placeholder
    if "[FINDINGS_OUTPUT_PATH]" not in text:
        errs.append("[A4] red-team-prompt.md: missing placeholder '[FINDINGS_OUTPUT_PATH]'")

    # [A5] counts-line spec token + field names
    if "SEVERITY-COUNTS:" not in text:
        errs.append("[A5] red-team-prompt.md: missing counts-line token 'SEVERITY-COUNTS:'")
    for field in ("fatal=", "significant=", "minor="):
        if field not in text:
            errs.append(f"[A5] red-team-prompt.md: missing SEVERITY-COUNTS field name '{field}'")

    # [A6] RETAIN-GUARD: rich findings sections still present. GREEN at baseline;
    # goes RED only if a future edit deletes these sections.
    for section in ("### Fatal Challenges", "### Significant Challenges",
                    "### Minor Observations", "### Dimension Coverage"):
        if section not in text:
            errs.append(f"[A6] red-team-prompt.md: rich findings section '{section}' was DELETED (retain-guard)")

    # [A7] count-derived VERDICT mapping: '0 Fatal' co-located with 'PASS'.
    if not (re.search(r"0\s+[Ff]atal", text) and "PASS" in text):
        errs.append("[A7] red-team-prompt.md: missing count-derived VERDICT mapping ('0 Fatal' → 'PASS')")

    # ---- worked PASS/FAIL example pair (design AC#2b) ----
    pass_marks = text.count(PASS_MARKER)
    fail_marks = text.count(FAIL_MARKER)

    # [A8] both example markers present, each exactly once
    if pass_marks != 1 or fail_marks != 1:
        errs.append(
            f"[A8] red-team-prompt.md: worked-example markers not found exactly once "
            f"(PASS marker x{pass_marks}, FAIL marker x{fail_marks}; expected 1 each)"
        )
        # Cannot extract blocks reliably — A9/A9b/A10/A11/A12 all depend on the
        # markers; report them as un-evaluable and return.
        errs.append("[A9] red-team-prompt.md: WITNESS byte-identity unverifiable — example markers missing")
        errs.append("[A9b] red-team-prompt.md: WITNESS polarity unverifiable — example markers missing")
        errs.append("[A10] red-team-prompt.md: PASS-example zero-counts unverifiable — example markers missing")
        errs.append("[A11] red-team-prompt.md: FAIL-example nonzero-count unverifiable — example markers missing")
        errs.append("[A12] red-team-prompt.md: FAIL-example internal consistency unverifiable — example markers missing")
        return errs

    # Each worked example is an indented ```…``` code fence: the marker is followed by
    # an opening fence, the receipt body, then the receipt's own (indented) closing
    # fence. Bound each block on that closing fence rather than on a "next ### heading"
    # — the headings here are indented 4 spaces inside the outer fence, so a bare
    # "\n### " never matches and the old logic let the block run to EOF (dead boundary).
    def example_block(marker: str) -> str:
        start = text.index(marker)
        body = text[start:]
        # opening fence (indented ```), then the closing fence that ends the receipt.
        m_open = re.search(r"\n[ \t]*```[^\n]*\n", body)
        if m_open is None:
            return body  # no fence found — fall back to remainder (markers guaranteed present)
        after_open = m_open.end()
        m_close = re.search(r"\n[ \t]*```[ \t]*(?:\n|$)", body[after_open:])
        if m_close is None:
            return body  # unterminated fence — fall back to remainder
        return body[: after_open + m_close.end()]

    pass_block = example_block(PASS_MARKER)
    fail_block = example_block(FAIL_MARKER)

    # [A9] WITNESS line byte-identical between the two examples (strip ONE trailing newline).
    def witness_line(block: str) -> str | None:
        m = re.search(r"^[ \t>]*WITNESS .*$", block, re.MULTILINE)
        return m.group(0) if m else None

    w_pass = witness_line(pass_block)
    w_fail = witness_line(fail_block)
    if w_pass is None or w_fail is None:
        errs.append("[A9] red-team-prompt.md: WITNESS line missing in PASS and/or FAIL example block")
    else:
        if w_pass.rstrip("\n") != w_fail.rstrip("\n"):
            errs.append(
                "[A9] red-team-prompt.md: WITNESS lines differ between PASS and FAIL examples "
                "(must be byte-identical):\n"
                f"        PASS: {w_pass!r}\n        FAIL: {w_fail!r}"
            )
        # [A9b] shared WITNESS line carries correct semantic polarity.
        shared = w_pass
        m_pat = re.search(r"pattern=(\S+)", shared)
        pat = m_pat.group(1) if m_pat else ""
        ok_a9b = (
            "fatal=[1-9]" in shared
            and "significant=[1-9]" in shared
            and "expect-fail=match" in shared
        )
        if not ok_a9b:
            errs.append(
                "[A9b] red-team-prompt.md: shared WITNESS line lacks correct polarity — "
                "pattern= must contain both 'fatal=[1-9]' and 'significant=[1-9]' AND the line "
                f"must carry 'expect-fail=match' (got pattern={pat!r})"
            )

    # [A10] PASS example: fatal-count=0 AND significant-count=0 in CLAIMS,
    #       AND a SEVERITY-COUNTS line with fatal=0 significant=0.
    a10_ok = (
        "fatal-count=0" in pass_block
        and "significant-count=0" in pass_block
        and re.search(r"SEVERITY-COUNTS:.*fatal=0", pass_block)
        and re.search(r"SEVERITY-COUNTS:.*significant=0", pass_block)
    )
    if not a10_ok:
        errs.append(
            "[A10] red-team-prompt.md: PASS example must carry CLAIMS 'fatal-count=0' + "
            "'significant-count=0' AND a 'SEVERITY-COUNTS:' line with fatal=0 significant=0"
        )

    # [A11] FAIL example: a non-zero fatal-count= or significant-count=.
    if not re.search(r"(fatal|significant)-count=[1-9]", fail_block):
        errs.append(
            "[A11] red-team-prompt.md: FAIL example must carry a non-zero "
            "'(fatal|significant)-count=[1-9]'"
        )

    # [A12] FAIL example internally consistent: CLAIMS pattern value-pins match the
    #       FAIL block's own SEVERITY-COUNTS line. Field-order/whitespace tolerant.
    sc = re.search(r"SEVERITY-COUNTS:(.*)", fail_block)
    if sc is None:
        errs.append("[A12] red-team-prompt.md: FAIL example missing its own 'SEVERITY-COUNTS:' line")
    else:
        sc_line = sc.group(1)
        m_a = re.search(r"fatal=(\d+)", sc_line)
        m_b = re.search(r"significant=(\d+)", sc_line)
        # pattern=fatal=(\d+) cannot latch onto the witness line because the witness
        # pattern= is immediately followed by '/' (a non-digit) — see M5 note in plan.
        m_c = re.search(r"pattern=fatal=(\d+)", fail_block)
        m_d = re.search(r"pattern=significant=(\d+)", fail_block)
        if not (m_a and m_b and m_c and m_d):
            errs.append(
                "[A12] red-team-prompt.md: FAIL example missing parseable SEVERITY-COUNTS "
                "fatal=/significant= AND CLAIMS pattern=fatal=/pattern=significant= value-pins"
            )
        else:
            a, b, c, d = (m_a.group(1), m_b.group(1), m_c.group(1), m_d.group(1))
            if a != c or b != d:
                errs.append(
                    "[A12] red-team-prompt.md: FAIL example CLAIMS value-pins contradict its own "
                    f"SEVERITY-COUNTS line (counts fatal={a} significant={b}; "
                    f"CLAIMS pattern=fatal={c} pattern=significant={d})"
                )

    # [A13] CLAIMS citations use the convention's two-endpoint range form
    #       (<artifact>#L<a>-L<b>; return-convention.md:85), NOT a bare <artifact>#L<n>.
    #       Bare #L<n> is not an enumerated citation grammar form. Scans every CLAIMS
    #       `from=` in both worked-example blocks: each must carry an L-range, and NONE
    #       may carry a bare #L<n> with no '-L' suffix.
    for label, block in (("PASS", pass_block), ("FAIL", fail_block)):
        from_cites = re.findall(r"from=\S+#L\d+(?:-L\d+)?", block)
        bad = [c for c in from_cites if not re.search(r"#L\d+-L\d+$", c)]
        if not from_cites:
            errs.append(
                f"[A13] red-team-prompt.md: {label} example has no CLAIMS 'from=...#L<a>-L<b>' "
                "citation (expected the SEVERITY-COUNTS line range form)"
            )
        elif bad:
            errs.append(
                f"[A13] red-team-prompt.md: {label} example CLAIMS citation uses the "
                "non-conformant bare '#L<n>' form instead of the convention's '#L<a>-L<b>' "
                f"range form (return-convention.md:85): {bad}"
            )

    return errs


# ---------------------------------------------------------------------------
# C. quality-gate/SKILL.md — consumption + supersession + writer-inversion
# ---------------------------------------------------------------------------

def check_qg(text: str) -> list[str]:
    errs: list[str] = []

    # [C13] score computed from findings-file severity sections, NOT from CLAIMS.
    if not ("### Fatal Challenges" in text and "### Significant Challenges" in text
            and "cross-check" in text):
        errs.append(
            "[C13] quality-gate/SKILL.md: missing score-source wording pinning the weighted "
            "score to counting '### Fatal Challenges' / '### Significant Challenges' sections of "
            "the cited findings file with an explicit CLAIMS 'cross-check' disclaimer"
        )

    # [C15] :30 no longer implies red-team prose is linted-to-BLOCKED. Keyed to the
    #       rule's structural CONTRACT anchor, not its prose — the rewrite's wording
    #       ("findings come from the cited artifact") is now freely editable; only the
    #       anchor is the regression guard (#399; see scripts/CHECKER_CONVENTIONS.md).
    if "CONTRACT:rt-redteam-receipts-lint-clean" not in text:
        errs.append(
            "[C15] quality-gate/SKILL.md: missing CONTRACT anchor "
            "'rt-redteam-receipts-lint-clean' marking the red-team-receipts-lint-clean rule "
            "(the rule's home paragraph was deleted, not merely reworded)"
        )

    # [C16] SP2 clean-PASS TRIPWIRE predicate as a contextual POINTER to the convention.
    c16_ok = (
        "TRIPWIRE: none" in text
        and "SUSPICION=0.00" in text
        and "return-convention.md" in text
    )
    if not c16_ok:
        errs.append(
            "[C16] quality-gate/SKILL.md: missing SP2 pointer — 'TRIPWIRE: none' co-located with "
            "'SUSPICION=0.00' AND a 'return-convention.md' reference (link, not redeclaration)"
        )

    # [C17] SP3 negative invariant: no manifest-sweep re-hashes pinned ARTIFACTS after insertion.
    c17_ok = ("re-hash" in text and "ARTIFACTS" in text and "after insertion" in text)
    if not c17_ok:
        errs.append(
            "[C17] quality-gate/SKILL.md: missing SP3 negative invariant (no manifest-sweep step "
            "'re-hash'es a prior entry's pinned 'ARTIFACTS' 'after insertion')"
        )

    # [C18] fix-agent test-less superseding-witness pattern. Keyed to the rule's
    #       CONTRACT anchor (#399) — the witness prose ('finding-anchor … no longer
    #       appears') is now freely editable; the anchor is the regression guard.
    if "CONTRACT:rt-fix-test-less-witness" not in text:
        errs.append(
            "[C18] quality-gate/SKILL.md: missing CONTRACT anchor 'rt-fix-test-less-witness' "
            "marking the fix-agent test-less superseding-witness rule"
        )

    # [C14]+[C18b] findings-path & writer-inversion rule. ONE anchor guards both the
    #       former [C14] ([FINDINGS_OUTPUT_PATH] is orchestrator-supplied) and [C18b]
    #       (reviewer is the initial writer) — they share a home paragraph (#399).
    if "CONTRACT:rt-findings-writer-inversion" not in text:
        errs.append(
            "[C14][C18b] quality-gate/SKILL.md: missing CONTRACT anchor "
            "'rt-findings-writer-inversion' marking the findings-path/writer-inversion rule "
            "(orchestrator-supplied [FINDINGS_OUTPUT_PATH] + reviewer-as-initial-writer)"
        )

    return errs


# ---------------------------------------------------------------------------
# D. red-team/SKILL.md — standalone consumption (design AC#4)
# ---------------------------------------------------------------------------

def check_rt_skill(text: str) -> list[str]:
    errs: list[str] = []

    # [D19] both qualitative branch + weighted-score loop derive from the same single
    #       source: the orchestrator's count of the cited findings file's sections.
    d19_ok = ("cited findings" in text
              and ("### Fatal Challenges" in text or "### Significant Challenges" in text)
              and ("single source" in text or "same source" in text or "same single source" in text))
    if not d19_ok:
        errs.append(
            "[D19] red-team/SKILL.md: missing single-source-of-truth wording pinning BOTH the "
            "qualitative branch and the weighted-score loop to the cited findings file's severity "
            "sections (e.g. 'cited findings' + section heading + 'same/single source')"
        )

    # [D20] Tier-1 structural lint applied AND NOT the Layer-2 sweep.
    d20_ok = (("Tier-1" in text or "Tier 1" in text)
              and ("Layer-2 sweep" in text or "Layer 2 sweep" in text))
    if not d20_ok:
        errs.append(
            "[D20] red-team/SKILL.md: missing standalone Tier-1-lint pin AND a 'Layer-2 sweep' "
            "(QG-only / 'no Layer-2 sweep') exclusion pin"
        )

    return errs


# ---------------------------------------------------------------------------
# E. return-convention.md — kind=grep clarification (design AC#4c)
# ---------------------------------------------------------------------------

def check_return_conv(text: str) -> list[str]:
    errs: list[str] = []

    # [E21] one statement: for kind=grep the cited artifact/range are the payload's own
    #       #<range>; out= resolution is kind=exec-only; scope references Tier-1 + Tier-2.
    # Pin on NEW phrases ('payload's own' + an out=…exec-only clause) — 'kind=grep',
    # 'Tier-1', 'Tier-2', 'out=' all pre-exist and cannot discriminate alone.
    has_payload_range = "payload's own" in text
    has_out_exec_only = bool(re.search(r"out=[^\n]{0,60}?\bexec[`)]?-only", text))
    has_scope = ("Tier-1" in text and "Tier-2" in text)
    if not (has_payload_range and has_out_exec_only and has_scope):
        missing = []
        if not has_payload_range:
            missing.append("\"payload's own\" range wording")
        if not has_out_exec_only:
            missing.append("an 'out=' resolution is 'exec-only' clause")
        if not has_scope:
            missing.append("Tier-1 + Tier-2 scope reference")
        errs.append(
            "[E21] return-convention.md: missing the kind=grep artifact/range clarification — "
            + "; ".join(missing)
        )

    return errs


def main() -> int:
    errs: list[str] = []
    errs += check_rt_prompt(RT_PROMPT.read_text(encoding="utf-8"))
    errs += check_qg(QG_SKILL.read_text(encoding="utf-8"))
    errs += check_rt_skill(RT_SKILL.read_text(encoding="utf-8"))
    errs += check_return_conv(RETURN_CONV.read_text(encoding="utf-8"))

    if errs:
        print("RT-RECEIPT-CONTRACT VIOLATIONS:")
        for e in errs:
            print(f"  - {e}")
        return 1
    print("OK — #366 red-team↔quality-gate receipt contract satisfied across all four files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
