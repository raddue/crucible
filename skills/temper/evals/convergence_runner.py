"""Convergence-check matcher module for temper fix-verification evals (#333).

This module replaces the old lens/count-delta check set with the
fix-verification **convergence** model (plan #333 §3). The harness no longer
tests finder angles (that recall surface moved into delve-engine); it tests the
tracked-set ``T`` lifecycle, the four terminal verdicts + two continuation
outcomes, the discharge paths, once-only defer, and the §3.5 branch table.

Transcript format the checks parse
-----------------------------------
A fixture's reviewer output is a **multi-round convergence transcript**. It is
plain markdown with structured per-round / per-member fields so the mechanical
checks can read it without an LLM:

    ### Round 1
    - Round-Verdict: Issues-Found

    1. row.tier read with no migration
       - File: src/handler.py:88
       - Summary: row.tier read with no migration
       - Severity: Important
       - Verdict: CONFIRMED
       - Admitted: 1
       - Readjudicated: false

    ### Round 2
    - Round-Verdict: Clean

    1. row.tier read with no migration
       - File: src/handler.py:88
       - Summary: row.tier read with no migration
       - Severity: Important
       - Verdict: CONFIRMED
       - Outcome: RESOLVED
       - Readjudicated: true

    ### Verdict
    - Final-Verdict: Clean

Member identity is the **five-field tuple** ``{file, line, summary, severity,
verdict}`` (plan §3.1). ``T`` membership is the **gating 2×2**: ``verdict ∈
{CONFIRMED, PLAUSIBLE}`` AND ``severity ∈ {Critical, Important}``.

Per-member ``Outcome`` (R2+ adjudication) is one of:
``RESOLVED | REFUTED-after-fix | DOWNGRADED | STILL-GATING | ESCALATE |
unreviewable``.

Reused infra (model-agnostic, retained from the old harness): the finding
parser primitives, ``finding_body_contains/_not``, ``report_has_block``,
``findings_count_at_least``, ``all_findings_have_file_line``, the
``evaluate_expectation`` dispatcher, and ``aggregate_replicates``.

Stdlib only.
"""

from __future__ import annotations

import re
from typing import Literal

Verdict = Literal["PASS", "FAIL", "N/A"]
Result = tuple[Verdict, str]


# ---------------------------------------------------------------------------
# Gating 2x2 (severity-verdict-contract §3): T = {CONFIRMED,PLAUSIBLE}×{Critical,Important}
# ---------------------------------------------------------------------------

_GATING_VERDICTS = frozenset({"CONFIRMED", "PLAUSIBLE"})
_GATING_SEVERITIES = frozenset({"Critical", "Important"})

# Terminal merge verdicts (loop stops) + continuation outcomes (loop continues).
_TERMINAL_VERDICTS = frozenset({"Clean", "Stagnation", "Architectural", "Max-Rounds"})
_CONTINUATION_VERDICTS = frozenset({"Issues-Found", "Defer-one-round"})
_ALL_VERDICTS = _TERMINAL_VERDICTS | _CONTINUATION_VERDICTS

# Per-member R2+ adjudication outcomes (temper-reviewer.md emits exactly one).
_DISCHARGE_OUTCOMES = frozenset({"RESOLVED", "REFUTED-after-fix", "DOWNGRADED"})
_LIVE_OUTCOMES = frozenset({"STILL-GATING", "ESCALATE"})


def _is_gating(severity: str | None, verdict: str | None) -> bool:
    """True iff the (severity, verdict) pair is in the gating 2×2 (in `T`)."""
    return verdict in _GATING_VERDICTS and severity in _GATING_SEVERITIES


# Report-prose sections under which numbered/list items are NOT findings.
_REPORT_SECTIONS = frozenset(
    {"Pre-flight", "Strengths", "Overall", "Recommendations", "Assessment", "Verdict"}
)

_HEADING_ANNOTATION_RE = re.compile(r"\s*\([^)]*\)\s*$")


def _section_key(heading: str | None) -> str | None:
    """Normalize a `### ` heading to its bare section name for _REPORT_SECTIONS
    lookup: drop a trailing parenthetical annotation and a trailing colon, and
    strip a leading `Round N` so per-round member lists still parse."""
    if heading is None:
        return None
    bare = _HEADING_ANNOTATION_RE.sub("", heading).strip().rstrip(":")
    # A `### Round N` heading is a member-list container, not a report-prose
    # section; normalize it to the literal "Round" so the membership test below
    # never suppresses its findings.
    m = re.match(r"^Round\s+\d+", bare)
    if m:
        return "Round"
    return bare


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^###\s+(.+?)\s*$")
_ROUND_HEADING_RE = re.compile(r"^###\s+Round\s+(\d+)\s*$")
# Finding/member header: numbered item, optionally bold/bulleted.
_FINDING_HEADER_RE = re.compile(r"^\s*(?:-\s+)?(?:\*\*)?(\d+)\.\s+")
# File: path:lo[-hi]  — line range optional (a bare `File: path` is allowed and
# the explicit `Line:` field below supplies the line).
_FILE_RE = re.compile(r"^\s*[-*]?\s*File:\s+(\S+?)(?::(\d+)(?:-(\d+))?)?\s*$")
_LINE_RE = re.compile(r"^\s*[-*]?\s*Line:\s+(\d+)(?:-(\d+))?\s*$")
_SEVERITY_RE = re.compile(r"^\s*[-*]?\s*Severity:\s+(\w+)\s*$")
_SUMMARY_RE = re.compile(r"^\s*[-*]?\s*Summary:\s+(.+?)\s*$")
_VERDICT_RE = re.compile(r"^\s*[-*]?\s*Verdict:\s+(CONFIRMED|PLAUSIBLE|REFUTED)\s*$", re.I)
_OUTCOME_RE = re.compile(
    r"^\s*[-*]?\s*Outcome:\s+"
    r"(RESOLVED|REFUTED-after-fix|DOWNGRADED|STILL-GATING|ESCALATE|unreviewable[\w \-]*)\s*$",
    re.I,
)
_READJUD_RE = re.compile(r"^\s*[-*]?\s*Readjudicated:\s+(true|false)\s*$", re.I)
_ADMITTED_RE = re.compile(r"^\s*[-*]?\s*Admitted:\s+(\d+)\s*$")

# Canonical-case maps so case-insensitive matches normalize to the spec spelling.
_OUTCOME_CANON = {
    "resolved": "RESOLVED",
    "refuted-after-fix": "REFUTED-after-fix",
    "downgraded": "DOWNGRADED",
    "still-gating": "STILL-GATING",
    "escalate": "ESCALATE",
}


def _canon_outcome(raw: str) -> str:
    low = raw.strip().lower()
    if low.startswith("unreviewable"):
        return "unreviewable"
    return _OUTCOME_CANON.get(low, raw.strip())


def _parse_findings(output: str) -> list[dict]:
    """Return the list of finding/member records parsed from a transcript.

    Each record carries: file, line (int|None), line_range, summary, severity,
    verdict (contract verdict), outcome (R2+ adjudication or None), readjudicated
    (bool|None), admitted (int|None), round (int|None — the `### Round N` it sits
    under), cited_files, body, section.

    Numbered/list items inside report-prose sections (see _REPORT_SECTIONS) are
    skipped.
    """
    lines = output.splitlines()

    boundaries: list[int] = []
    for i, line in enumerate(lines):
        if _FINDING_HEADER_RE.match(line) or _HEADING_RE.match(line):
            boundaries.append(i)
    boundaries.append(len(lines))

    findings: list[dict] = []
    current_section: str | None = None
    current_round: int | None = None

    for idx, line in enumerate(lines):
        rh = _ROUND_HEADING_RE.match(line)
        if rh:
            current_round = int(rh.group(1))
            current_section = rh.group(0).removeprefix("### ").strip()
            continue
        h = _HEADING_RE.match(line)
        if h:
            current_section = h.group(1)
            continue

        if not _FINDING_HEADER_RE.match(line):
            continue

        if _section_key(current_section) in _REPORT_SECTIONS:
            continue

        end = next(b for b in boundaries if b > idx)
        block = lines[idx + 1 : end]
        header_line = line

        cited_files: list[tuple[str, tuple[int, int]]] = []
        file_path: str | None = None
        line_range: tuple[int, int] | None = None
        explicit_line: int | None = None
        severity: str | None = None
        summary: str | None = None
        verdict: str | None = None
        outcome: str | None = None
        readjudicated: bool | None = None
        admitted: int | None = None

        for child in block:
            m = _FILE_RE.match(child)
            if m:
                fp = m.group(1)
                if m.group(2):
                    lo = int(m.group(2))
                    hi = int(m.group(3)) if m.group(3) else lo
                    cited_files.append((fp, (lo, hi)))
                else:
                    cited_files.append((fp, (0, 0)))
                if file_path is None:
                    file_path = fp
                continue
            m = _LINE_RE.match(child)
            if m:
                lo = int(m.group(1))
                hi = int(m.group(2)) if m.group(2) else lo
                explicit_line = lo
                line_range = (lo, hi)
                continue
            m = _SUMMARY_RE.match(child)
            if m:
                summary = m.group(1)
                continue
            m = _SEVERITY_RE.match(child)
            if m:
                severity = m.group(1)
                continue
            m = _VERDICT_RE.match(child)
            if m:
                verdict = m.group(1).upper()
                continue
            m = _OUTCOME_RE.match(child)
            if m:
                outcome = _canon_outcome(m.group(1))
                continue
            m = _READJUD_RE.match(child)
            if m:
                readjudicated = m.group(1).lower() == "true"
                continue
            m = _ADMITTED_RE.match(child)
            if m:
                admitted = int(m.group(1))
                continue

        # Resolve the back-compat scalar file/line_range fields. An explicit
        # `Line:` wins; otherwise the first `File: path:lo-hi` citation supplies it.
        if cited_files and file_path is None:
            file_path = cited_files[0][0]
        if line_range is None and cited_files and cited_files[0][1] != (0, 0):
            line_range = cited_files[0][1]
        line_val = explicit_line
        if line_val is None and line_range is not None:
            line_val = line_range[0]

        body = "\n".join([header_line, *block])

        findings.append(
            {
                "file": file_path,
                "line": line_val,
                "line_range": line_range,
                "cited_files": cited_files,
                "summary": summary,
                "severity": severity,
                "verdict": verdict,
                "outcome": outcome,
                "readjudicated": readjudicated,
                "admitted": admitted,
                "round": current_round,
                "body": body,
                "section": current_section,
            }
        )

    return findings


def _member_identity(f: dict) -> tuple:
    """Five-field identity tuple {file, line, summary, severity, verdict}."""
    return (f.get("file"), f.get("line"), f.get("summary"), f.get("severity"), f.get("verdict"))


def _round_verdicts(output: str) -> dict[int, str]:
    """Map round-index → Round-Verdict declared in each `### Round N` block."""
    result: dict[int, str] = {}
    lines = output.splitlines()
    current: int | None = None
    rv_re = re.compile(r"^\s*[-*]?\s*Round-Verdict:\s+(\S+)\s*$")
    for line in lines:
        rh = _ROUND_HEADING_RE.match(line)
        if rh:
            current = int(rh.group(1))
            continue
        if _HEADING_RE.match(line):
            current = None
            continue
        m = rv_re.match(line)
        if m and current is not None:
            result[current] = m.group(1)
    return result


def _final_verdict(output: str) -> str | None:
    """Parse the run-level `### Verdict` block's `Final-Verdict:` field."""
    blocks = _report_blocks(output, "Verdict")
    fv_re = re.compile(r"^\s*[-*]?\s*Final-Verdict:\s+(\S+)\s*$", re.MULTILINE)
    for b in blocks:
        m = fv_re.search(b)
        if m:
            return m.group(1)
    return None


def _report_blocks(output: str, heading: str) -> list[str]:
    """Return the text blocks under every `### <heading>` section."""
    heading_re = re.compile(rf"^###\s+{re.escape(heading)}\s*$")
    next_heading_re = re.compile(r"^###\s+")
    lines = output.splitlines()
    blocks: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        if heading_re.match(lines[i]):
            j = i + 1
            while j < n and not next_heading_re.match(lines[j]):
                j += 1
            blocks.append("\n".join(lines[i + 1 : j]))
            i = j
        else:
            i += 1
    return blocks


# ---------------------------------------------------------------------------
# Generic / reused checks
# ---------------------------------------------------------------------------


def all_findings_have_file_line(output: str) -> Result:
    findings = _parse_findings(output)
    if not findings:
        return ("N/A", "no findings parsed")
    missing = [
        f for f in findings if f["file"] is None or f["line"] is None
    ]
    if missing:
        return ("FAIL", f"{len(missing)} finding(s) without File:line")
    return ("PASS", f"all {len(findings)} finding(s) cite File:line")


def findings_count_at_least(output: str, n: int) -> Result:
    findings = _parse_findings(output)
    actual = len(findings)
    if actual >= n:
        return ("PASS", f"{actual} finding(s) ≥ {n} required")
    return ("FAIL", f"only {actual} finding(s), need ≥ {n}")


def finding_body_does_not_contain(
    output: str,
    patterns: list[str],
    case_insensitive: bool = True,
) -> Result:
    """FAIL if any finding's body text contains any pattern (substring match)."""
    findings = _parse_findings(output)
    if not findings:
        return ("N/A", "no findings parsed")
    hits: list[str] = []
    for f in findings:
        body = f["body"]
        haystack = body.lower() if case_insensitive else body
        for p in patterns:
            needle = p.lower() if case_insensitive else p
            if needle in haystack:
                hits.append(f"{p!r} in finding at {f['file']}")
                break
    if hits:
        return ("FAIL", "; ".join(hits))
    return ("PASS", f"no listed patterns appear in any of {len(findings)} finding(s)")


def finding_body_contains(
    output: str, pattern: str, case_insensitive: bool = True
) -> Result:
    """PASS if ANY finding's body contains `pattern` (substring match)."""
    findings = _parse_findings(output)
    if not findings:
        return ("N/A", "no findings")
    needle = pattern.lower() if case_insensitive else pattern
    for f in findings:
        haystack = f["body"].lower() if case_insensitive else f["body"]
        if needle in haystack:
            return ("PASS", f"{pattern!r} appears in finding at {f['file']}")
    return ("FAIL", f"{pattern!r} appears in no finding body")


def report_has_block(output: str, heading: str, min_chars: int = 1) -> Result:
    """PASS if a `### <heading>` block exists with >= min_chars non-ws chars."""
    blocks = _report_blocks(output, heading)
    if not blocks:
        return ("FAIL", f"no ### {heading} heading")
    nonws = sum(1 for c in "\n".join(blocks) if not c.isspace())
    if nonws >= min_chars:
        return ("PASS", f"### {heading} block has {nonws} non-ws char(s)")
    return ("FAIL", f"### {heading} block empty ({nonws} < {min_chars} non-ws char(s))")


# ---------------------------------------------------------------------------
# Convergence checks (the #333 model)
# ---------------------------------------------------------------------------


def _members_in_round(output: str, round: int) -> list[dict]:
    return [f for f in _parse_findings(output) if f["round"] == round]


def _find_member(
    output: str,
    file: str,
    *,
    round: int | None = None,
    summary: str | None = None,
    line: int | None = None,
) -> dict | None:
    """Locate a single member record by file (+ optional round/summary/line)."""
    candidates = _parse_findings(output)
    matches = [f for f in candidates if f["file"] == file]
    if round is not None:
        matches = [f for f in matches if f["round"] == round]
    if summary is not None:
        matches = [f for f in matches if (f["summary"] or "") == summary]
    if line is not None:
        matches = [f for f in matches if f["line"] == line]
    if not matches:
        return None
    # Prefer the latest round if several survive the filter.
    matches.sort(key=lambda f: (f["round"] if f["round"] is not None else -1))
    return matches[-1]


def member_enters_T(
    output: str,
    file: str,
    severity: str,
    verdict: str,
    round: int = 1,
    summary: str | None = None,
) -> Result:
    """Verdict×severity gating-2×2 admission check.

    PASS iff a member with the given (severity, verdict) at `file` is present in
    `round` AND that pair is in the gating 2×2 (so it belongs in `T`). A
    below-C/I severity or a REFUTED verdict does NOT enter T → FAIL with the
    reason (this encodes the new-member admission gate, §3.4).
    """
    m = _find_member(output, file, round=round, summary=summary)
    if m is None:
        return ("FAIL", f"no member at {file} in round {round}")
    sev = m["severity"]
    vrd = m["verdict"]
    if sev != severity or vrd != verdict:
        return (
            "FAIL",
            f"member at {file} is ({sev},{vrd}), expected ({severity},{verdict})",
        )
    if not _is_gating(severity, verdict):
        return (
            "FAIL",
            f"({severity},{verdict}) is NOT in the gating 2×2 — does not enter T",
        )
    return ("PASS", f"member at {file} enters T as ({severity},{verdict}) in round {round}")


def member_resolved(
    output: str, file: str, round: int, summary: str | None = None
) -> Result:
    """PASS iff the member at `file` in `round` carries Outcome: RESOLVED."""
    m = _find_member(output, file, round=round, summary=summary)
    if m is None:
        return ("FAIL", f"no member at {file} in round {round}")
    if m["outcome"] == "RESOLVED":
        return ("PASS", f"member at {file} RESOLVED in round {round}")
    return ("FAIL", f"member at {file} outcome is {m['outcome']!r}, expected RESOLVED")


def member_discharged_refuted_after_fix(
    output: str, file: str, round: int, summary: str | None = None
) -> Result:
    """PASS iff the member discharges via REFUTED-after-fix (the §3.3 path).

    Encodes that a repro-less PLAUSIBLE@C/I discharges ONLY by an actively
    re-derived REFUTED — never on fixer prose.
    """
    m = _find_member(output, file, round=round, summary=summary)
    if m is None:
        return ("FAIL", f"no member at {file} in round {round}")
    if m["outcome"] == "REFUTED-after-fix":
        return ("PASS", f"member at {file} REFUTED-after-fix in round {round}")
    return (
        "FAIL",
        f"member at {file} outcome is {m['outcome']!r}, expected REFUTED-after-fix",
    )


def member_downgraded(
    output: str, file: str, round: int, summary: str | None = None
) -> Result:
    """PASS iff the member discharges via a code-based DOWNGRADED (below C/I)."""
    m = _find_member(output, file, round=round, summary=summary)
    if m is None:
        return ("FAIL", f"no member at {file} in round {round}")
    if m["outcome"] == "DOWNGRADED":
        return ("PASS", f"member at {file} DOWNGRADED below C/I in round {round}")
    return ("FAIL", f"member at {file} outcome is {m['outcome']!r}, expected DOWNGRADED")


def member_escalated(
    output: str, file: str, round: int, summary: str | None = None
) -> Result:
    """PASS iff the member is ESCALATE (escalation-eligible repro-less PLAUSIBLE@C/I).

    An escalation-eligible member stays LIVE in T and blocks Clean (§3.3) — this
    check asserts the outcome, not removal from T.
    """
    m = _find_member(output, file, round=round, summary=summary)
    if m is None:
        return ("FAIL", f"no member at {file} in round {round}")
    if m["outcome"] == "ESCALATE":
        return ("PASS", f"member at {file} ESCALATE (live, blocks Clean) in round {round}")
    return ("FAIL", f"member at {file} outcome is {m['outcome']!r}, expected ESCALATE")


def verdict_is(output: str, verdict: str, round: int | None = None) -> Result:
    """PASS iff the declared verdict equals `verdict`.

    When `round` is given, checks that round's `Round-Verdict`; otherwise checks
    the run-level `Final-Verdict`. `verdict` must be one of the four terminal
    verdicts or two continuation outcomes (§3.4 taxonomy) — an unknown verdict
    name FAILs loudly so a typo cannot pass vacuously.
    """
    if verdict not in _ALL_VERDICTS:
        return (
            "FAIL",
            f"{verdict!r} is not a known verdict {sorted(_ALL_VERDICTS)}",
        )
    if round is not None:
        actual = _round_verdicts(output).get(round)
        scope = f"round {round}"
    else:
        actual = _final_verdict(output)
        scope = "final"
    if actual is None:
        return ("FAIL", f"no {scope} verdict declared")
    if actual == verdict:
        return ("PASS", f"{scope} verdict is {verdict}")
    return ("FAIL", f"{scope} verdict is {actual!r}, expected {verdict!r}")


def new_admit_round_not_clean(output: str, round: int) -> Result:
    """PASS iff `round` admits ≥1 new gating member AND its verdict is NOT Clean.

    Encodes §3.4 "a new-admit round is NEVER Clean (→ Issues-Found)": even when
    every carried member resolved, admitting a new gating finding denies Clean.
    """
    members = _members_in_round(output, round)
    admitted_new = [
        m
        for m in members
        if m["admitted"] == round and _is_gating(m["severity"], m["verdict"])
    ]
    if not admitted_new:
        return ("N/A", f"round {round} admits no new gating member")
    rv = _round_verdicts(output).get(round)
    if rv == "Clean":
        return (
            "FAIL",
            f"round {round} admitted {len(admitted_new)} new gating member(s) "
            f"yet declared Clean (must be Issues-Found)",
        )
    return (
        "PASS",
        f"round {round} admitted {len(admitted_new)} new gating member(s); "
        f"verdict {rv!r} (correctly not Clean)",
    )


def stagnation_subordinate_to_escalation(output: str, round: int) -> Result:
    """PASS iff, when round `round`'s previously-seen unresolved subset is SOLELY
    escalation-eligible, the verdict is **Architectural** (not Stagnation).

    Encodes §3.5: Stagnation is SUBORDINATE to escalation — a non-shrinking subset
    that is solely escalation-eligible routes to Architectural and does NOT wait
    for the 2-round Stagnation antecedent (r8fix-S3).
    """
    members = _members_in_round(output, round)
    # The previously-seen unresolved subset = members carried in (admitted before
    # this round) whose outcome leaves them live in T (STILL-GATING / ESCALATE).
    prev_unresolved = [
        m
        for m in members
        if m["admitted"] is not None
        and m["admitted"] < round
        and m["outcome"] in _LIVE_OUTCOMES
    ]
    if not prev_unresolved:
        return ("N/A", f"round {round} has no previously-seen unresolved member")
    solely_escalation = all(
        m["outcome"] == "ESCALATE" and m["readjudicated"] is True
        for m in prev_unresolved
    )
    rv = _round_verdicts(output).get(round)
    if solely_escalation:
        if rv == "Architectural":
            return (
                "PASS",
                f"round {round} subset solely escalation-eligible → Architectural "
                f"(Stagnation subordinate)",
            )
        return (
            "FAIL",
            f"round {round} subset solely escalation-eligible but verdict is "
            f"{rv!r}, expected Architectural (Stagnation must be subordinate)",
        )
    return (
        "N/A",
        f"round {round} subset is not solely escalation-eligible (mixed/stuck)",
    )


def _stable_member_key(f: dict) -> tuple:
    """Drift-immune sub-identity for once-only defer grouping = {file, summary,
    severity}.

    DELIBERATELY DROPS the volatile ``line`` and ``verdict`` fields from
    ``_member_identity``. The fix-verification loop edits code as it goes, so a
    member's reported ``line`` shifts when lines are inserted/removed above it,
    and its contract ``verdict`` can be re-derived between rounds. Keying the
    once-only count on those volatile fields lets a GENUINE double-defer of the
    SAME member evade detection (it would split into two distinct keys). The
    stable sub-key ``{file, summary, severity}`` keeps the same member fused
    across rounds so a true second defer is always caught.

    DO NOT re-introduce ``line``/``verdict`` into this key — that is the
    look-harder regression this fix locks out.
    """
    return (f.get("file"), f.get("summary"), f.get("severity"))


def defer_once_only(output: str, file: str, summary: str | None = None) -> Result:
    """PASS iff no member at `file` is *deferred-for* in ≥2 Defer-one-round rounds.

    Once-only defer (§3.4/§3.5): "Defer-one-round is ONCE-ONLY per member, keyed
    on ``readjudicated``." A member may *trigger* AT MOST ONE Defer-one-round.

    **deferred-FOR (the trigger) — a member is deferred-for in round R iff ALL:**
      (a) round R's Round-Verdict is ``Defer-one-round``;
      (b) the member is carried-in (``admitted is not None and admitted < R``);
      (c) the member is live (``outcome in _LIVE_OUTCOMES``);
      (d) the member's ``readjudicated is False`` in round R.

    Clause (d) is the crux. ``Defer-one-round`` is a PER-ROUND verdict; a round
    may legitimately defer because of a *not-yet-readjudicated sibling* (the
    §3.5 MIXED row). A member that appears in that same Defer round with
    ``readjudicated is True`` is CARRIED-THROUGH, NOT deferred-for — it already
    had its single defer (deferring SETS the flag; an already-set member does
    NOT defer again, §3.5). So a ``readjudicated == true`` member does NOT
    consume a defer and must NOT count toward the violation. This is what makes
    the legal MIXED carry-through PASS instead of false-FAILing.

    **Once-only rule:** FAIL iff some member is deferred-for in ≥2 DISTINCT
    Defer-one-round rounds. N/A if there are no Defer-one-round rounds at all;
    PASS if there are but no member is deferred-for twice.

    **Drift-immune keying:** the per-member deferred-for rounds are grouped by
    the STABLE sub-identity ``{file, summary, severity}`` (see
    ``_stable_member_key``), NOT the volatile 5-field ``_member_identity`` — so
    a genuine double-defer is caught even when the member's ``line``/``verdict``
    drifted between the two defer rounds.
    """
    findings = [
        f
        for f in _parse_findings(output)
        if f["file"] == file and (summary is None or (f["summary"] or "") == summary)
    ]
    if not findings:
        return ("FAIL", f"no member at {file}")
    round_verdicts = _round_verdicts(output)

    defer_rounds_present = any(v == "Defer-one-round" for v in round_verdicts.values())

    # Group deferred-FOR rounds per member by the drift-immune stable sub-key.
    by_member: dict[tuple, set[int]] = {}
    for f in findings:
        if (
            f["round"] is not None
            and round_verdicts.get(f["round"]) == "Defer-one-round"
            and f["admitted"] is not None
            and f["admitted"] < f["round"]
            and f["outcome"] in _LIVE_OUTCOMES
            and f["readjudicated"] is False
        ):
            # Deferred-FOR: this round deferred BECAUSE this not-yet-readjudicated
            # carried-and-live member needs its re-adjudication pass.
            by_member.setdefault(_stable_member_key(f), set()).add(f["round"])

    # Once-only violation: the same member deferred-for in ≥2 distinct Defer rounds.
    for identity, deferred_for_rounds in by_member.items():
        if len(deferred_for_rounds) >= 2:
            return (
                "FAIL",
                f"once-only-defer violated: member {identity} deferred-for in rounds "
                f"{sorted(deferred_for_rounds)}",
            )

    if not defer_rounds_present:
        return ("N/A", f"no Defer-one-round round at {file}")

    all_defer_for_rounds = sorted({r for rounds in by_member.values() for r in rounds})
    return (
        "PASS",
        f"member(s) at {file} deferred-for in rounds {all_defer_for_rounds} "
        f"(each ≤ 1 — once-only respected)",
    )


# ---------------------------------------------------------------------------
# Dispatcher + replicate aggregator
# ---------------------------------------------------------------------------

_CHECK_REGISTRY = {
    # Reused / generic
    "all-findings-have-file-line": all_findings_have_file_line,
    "findings-count-at-least": findings_count_at_least,
    "finding-body-does-not-contain": finding_body_does_not_contain,
    "finding-body-contains": finding_body_contains,
    "report-has-block": report_has_block,
    # Convergence model (#333 §3)
    "member-enters-t": member_enters_T,
    "member-resolved": member_resolved,
    "member-discharged-refuted-after-fix": member_discharged_refuted_after_fix,
    "member-downgraded": member_downgraded,
    "member-escalated": member_escalated,
    "verdict-is": verdict_is,
    "new-admit-round-not-clean": new_admit_round_not_clean,
    "stagnation-subordinate-to-escalation": stagnation_subordinate_to_escalation,
    "defer-once-only": defer_once_only,
}

# No fixture-aware checks remain (lens-findings-in-allowed-files was removed).
_FIXTURE_AWARE_CHECKS: set[str] = set()


def _normalize_check_name(name: str | None) -> str | None:
    if name is None:
        return None
    return name.replace("_", "-").lower()


def evaluate_expectation(
    expectation: dict, reviewer_output: str, fixture: dict
) -> Result:
    """Dispatch by expectation['type']='mechanical' + expectation['check'].

    Schema:
      {"type": "mechanical", "check": "<kebab-case-name>", "params": {...},
       "prerequisite": <inline-expectation-dict> | <kebab-name>}

    Both 'params' (canonical) and 'args' (legacy) accepted; both kebab-case and
    snake_case check names accepted.
    """
    if expectation.get("type") != "mechanical":
        return ("N/A", f"unsupported expectation type {expectation.get('type')!r}")

    prereq = expectation.get("prerequisite")
    if prereq is not None:
        if isinstance(prereq, dict):
            prereq_verdict, _ = evaluate_expectation(prereq, reviewer_output, fixture)
            prereq_label = _normalize_check_name(prereq.get("check")) or "<inline>"
        else:
            prereq_name = _normalize_check_name(prereq)
            overrides = fixture.get("_prereq_overrides", {})
            if prereq in overrides or prereq_name in overrides:
                prereq_verdict = overrides.get(prereq, overrides.get(prereq_name))[0]
            else:
                prereq_fn = _CHECK_REGISTRY.get(prereq_name)
                if prereq_fn is None:
                    return ("N/A", f"unknown prerequisite {prereq!r}")
                prereq_verdict, _ = prereq_fn(reviewer_output)  # type: ignore[call-arg]
            prereq_label = str(prereq)
        if prereq_verdict != "PASS":
            return ("N/A", f"prereq {prereq_label} failed")

    check_name = _normalize_check_name(expectation.get("check"))
    fn = _CHECK_REGISTRY.get(check_name)
    if fn is None:
        return ("FAIL", f"unknown check {expectation.get('check')!r}")

    args = {**expectation.get("args", {}), **expectation.get("params", {})}
    if check_name in _FIXTURE_AWARE_CHECKS:
        return fn(reviewer_output, fixture, **args)
    return fn(reviewer_output, **args)


def aggregate_replicates(
    per_trial_verdicts: list[Verdict], threshold: int
) -> Verdict:
    """Returns N/A if all trials N/A; PASS if ≥threshold of non-N/A trials are
    PASS; FAIL otherwise.

    Finding-set aggregation (#333): convergence transcripts are deterministic, so
    a fixture's replicate trials carry the same transcript; the aggregate is the
    threshold vote over the per-trial convergence-check verdicts.
    """
    non_na = [v for v in per_trial_verdicts if v != "N/A"]
    if not non_na:
        return "N/A"
    passes = sum(1 for v in non_na if v == "PASS")
    return "PASS" if passes >= threshold else "FAIL"
