#!/usr/bin/env python3
"""Executable oracle for the Second-Pass-Findings scoring rule (#561 fresh round 12 F1).

Faithful executable transcription of the `qg-score-second-pass-population`
CONTRACT block in `skills/quality-gate/SKILL.md` (Score source, step 7) and its
mirror in `skills/red-team/red-team-prompt.md`'s `### Second Pass Findings`
bracket. Both prose homes describe ONE parsing/scoring rule; this module is
that rule's single executable implementation, so a round-11-style in-place
prose inversion that keeps every checker-pinned phrase intact but flips the
rule's actual behavior is caught by re-running this scorer against the
`skills/quality-gate/evals/evals.json` fixtures (see
`scripts/run_second_pass_evals.py`), not by grepping for phrases.

Round 11 F1 found FIVE independent, live-verified in-place inversions of this
clause, each leaving the phrase-pin checkers green:
  1. Zero-match rule consequence (score 0/empty instead of raw-heading relocation)
  2. Section-END consequence (empty instead of extends-to-end-of-file)
  3. Union tiebreak consequence (last-match-only instead of union)
  4. `missing-second-pass-section` default framing (silent vs. flagged)
  5. Mirror-side (red-team-prompt.md) zero-match consequence — same rule as (1)

This module's design closes that gap: rules (1)/(2)/(3)/(5) are single code
paths shared between what SKILL.md and red-team-prompt.md both describe (one
executable rule, not two divergent prose restatements), and (4) is made an
observable, distinct code path (the `missing-second-pass-section` flag is only
set on the true "no heading anywhere, not even raw" branch, never on the
zero-match-relocated branch) so a mutation that drops the flag is
distinguishable from one that doesn't.

Round 12 fixes folded into this rule as the reference implementation (not
patched on afterward):
  - S1: the zero-match fallback triggers on the OBSERVABLE condition
    (unexcluded-matching-heading count == 0), not on a diagnosis of *why* it
    is zero — a fence-parity defect is one cause among several (a heading
    sitting inside a balanced, closed fence is another) that reach the same
    raw-heading relocation behavior.
  - Second Pass finding: the severity-token boundary rule strips trailing
    whitespace from the `**Severity:**` line's value before the boundary
    test, symmetric with the leading-whitespace strip it already performs —
    `**Severity:** Fatal ` (one trailing space) now recognises as Fatal.

Stdlib only. See scripts/CHECKER_CONVENTIONS.md for the general checker/oracle
conventions this repo follows (this is an oracle, not a `check_*.py`
structural checker, so it is invoked as a library by
`scripts/run_second_pass_evals.py`, not as a standalone pass/fail script).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

SECTION_NAMES = [
    "Fatal Challenges",
    "Significant Challenges",
    "Second Pass Findings",
    "Minor Observations",
]

FINDING_MARK = "**Finding:**"
SEVERITY_MARK = "**Severity:**"

_FENCE_LINE_RE = re.compile(r"^\s*`{3,}\S*\s*$")
_BLOCKQUOTE_RE = re.compile(r"^\s*>")
_HEADING3_RE = re.compile(r"^(#{3})(?!#)\s+(.*?)\s*$")
_HEADING4_RE = re.compile(r"^(#{4})(?!#)\s+(.*?)\s*$")
_LIST_MARKER_RE = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+")
_DECLARED_RE = re.compile(
    r"^SEVERITY-COUNTS:\s*fatal=(\d+)\s+significant=(\d+)\s+minor=(\d+)"
)

# Boundary-rule punctuation set: token immediately followed by end-of-line, or
# by one of these chars with optional whitespace before it.
_BOUNDARY_PUNCT_RE = re.compile(r"^\s*[(\[,.:;]")
# ...or by whitespace (required, not optional) followed by a dash.
_BOUNDARY_DASH_RE = re.compile(r"^\s+[-–—]")

_WRAP_MARKERS = ("**", "__", "*", "_", "`")

_SEVERITY_TOKENS = ("Fatal", "Significant", "Minor")


def _norm(title: str) -> str:
    return re.sub(r"\s+", " ", title.strip().lower())


def _fence_state_before(lines: list[str]) -> list[bool]:
    """`states[i]` is True iff line i sits inside a fenced code block (parity
    of fence-toggle lines strictly before it is odd). `states` has one extra
    trailing entry (`states[len(lines)]`) giving the fence state after the
    whole text — this is what lets `_section_fence_disabled` read the state
    at a section's END boundary even when that boundary is end-of-file."""
    states = []
    in_fence = False
    for line in lines:
        states.append(in_fence)
        if _FENCE_LINE_RE.match(line):
            in_fence = not in_fence
    states.append(in_fence)
    return states


def _section_fence_disabled(lines: list[str], fence_before: list[bool], start: int, end: int) -> bool:
    """Fence-parity fail-loud clause (#561 round 3 S3, generalized fresh
    round 12 to cover the zero-match-relocated case #561 fresh round 11 F1
    instance 1/5 and S1 exercise): if a section's own span contains an ODD
    number of triple-backtick delimiters, OR a fence is still open at the
    section's end boundary (inherited-open counts — #561 fresh round 12,
    exercised by a zero-match-relocated section whose content sits inside
    the very fence that zeroed its heading match), the fenced-code-block
    exclusion does NOT apply anywhere in that section: every line-initial
    marker counts, fence or no fence. Blockquote exclusion is untouched — it
    is a distinct exclusion, not covered by this clause."""
    exiting_state = fence_before[end] if end < len(fence_before) else fence_before[-1]
    local_toggle_count = sum(1 for line in lines[start + 1 : end] if _FENCE_LINE_RE.match(line))
    return bool(exiting_state) or (local_toggle_count % 2 == 1)


def _is_blockquoted(line: str) -> bool:
    return bool(_BLOCKQUOTE_RE.match(line))


def _strip_list_marker(line: str) -> str:
    return _LIST_MARKER_RE.sub("", line, count=1)


def _classify_line(line: str, fenced: bool, blockquoted: bool):
    """Returns ('finding', None) | ('severity', <raw value text>) | None.

    Blockquote exclusion is a DISTINCT exclusion, not a stripped prefix — it
    is checked against the raw line, before list-marker stripping (#561
    fresh round 5 SP2 / the prompt's own "distinct exclusion" clause).
    """
    if fenced or blockquoted:
        return None
    content = _strip_list_marker(line).lstrip()
    if content.startswith(FINDING_MARK):
        return ("finding", None)
    if content.startswith(SEVERITY_MARK):
        return ("severity", content[len(SEVERITY_MARK):])
    return None


def _is_heading4(line: str, fenced: bool, blockquoted: bool) -> bool:
    if fenced or blockquoted:
        return False
    return bool(_HEADING4_RE.match(line))


def parse_severity_token(raw_value: str | None) -> tuple[str | None, bool]:
    """First-recognised-token-over-a-normalized-value parse of a
    `**Severity:**` line's value.

    Returns (token, annotated) where token is one of Fatal/Significant/Minor
    or None (does not recognise -> caller applies the malformed-second-pass-
    entry fail-loud default), and annotated is True iff the value carries
    text beyond the bare token.

    Round-12 fix (Second Pass finding): strips BOTH leading and trailing
    whitespace from the value before the boundary test — the rule already
    stripped leading whitespace (the line's own leading whitespace); trailing
    whitespace on the value was never stripped, so `**Severity:** Fatal `
    (one trailing space) fell through to the malformed default and scored
    Significant instead of Fatal. This is the symmetric fix.
    """
    if raw_value is None:
        return None, False
    v = raw_value.strip()
    changed = True
    while changed:
        changed = False
        for marker in _WRAP_MARKERS:
            if len(v) >= 2 * len(marker) and v.startswith(marker) and v.endswith(marker):
                v = v[len(marker):-len(marker)]
                changed = True
        v = v.strip()
    for token in _SEVERITY_TOKENS:
        if v.startswith(token):
            rest = v[len(token):]
            if rest == "":
                return token, False
            if _BOUNDARY_PUNCT_RE.match(rest):
                return token, True
            if _BOUNDARY_DASH_RE.match(rest):
                return token, True
    return None, False


def _find_end(all_h3, start_idx: int, excluded_ok: bool, total_lines: int) -> int:
    candidates = [i for i, _text, excl in all_h3 if i > start_idx and (excluded_ok or not excl)]
    return min(candidates) if candidates else total_lines


@dataclass
class Section:
    spans: list[tuple[int, int]] = field(default_factory=list)
    missing: bool = False


def locate_sections(lines: list[str], fence_before: list[bool]) -> tuple[dict[str, Section], set[str]]:
    """Section location (SKILL.md CONTRACT block, "Section location" clause).

    Every rule here presupposes the four sections are already correctly
    located; this function IS that location step.

    Round-12 S1 fix: the zero-match fallback triggers on the OBSERVABLE
    condition (unexcluded-matching-heading count == 0 for a section that DOES
    have at least one raw matching heading somewhere in the file), not on a
    diagnosis of *why* the count is zero. A fence-parity defect (odd fence
    count / unclosed fence) is one cause; a heading sitting inside a
    balanced, closed fence — the round-11 S1 gap — is another; both reach the
    same raw-heading relocation behavior.
    """
    all_h3 = []
    for i, line in enumerate(lines):
        m = _HEADING3_RE.match(line)
        if not m:
            continue
        text = m.group(2)
        excluded = fence_before[i] or _is_blockquoted(line)
        all_h3.append((i, text, excluded))

    flags: set[str] = set()
    sections: dict[str, Section] = {}
    total_lines = len(lines)

    for name in SECTION_NAMES:
        matches = [(i, excl) for i, text, excl in all_h3 if text == name]
        unexcluded = [i for i, excl in matches if not excl]
        raw_all = [i for i, _excl in matches]

        if unexcluded:
            starts = unexcluded
            if len(starts) > 1:
                flags.add("malformed-second-pass-sectioning")
            spans = [(s, _find_end(all_h3, s, excluded_ok=False, total_lines=total_lines)) for s in starts]
            sections[name] = Section(spans=spans, missing=False)
        elif raw_all:
            # Zero unexcluded matches but at least one raw match exists
            # somewhere (fenced and/or blockquoted) -> raw-heading relocation,
            # end-to-end (both start and end predicates), never read as empty.
            flags.add("malformed-second-pass-sectioning")
            starts = raw_all
            spans = [(s, _find_end(all_h3, s, excluded_ok=True, total_lines=total_lines)) for s in starts]
            sections[name] = Section(spans=spans, missing=False)
        else:
            # No heading matching this section's text exists anywhere in the
            # file, even under the raw-heading fallback.
            flags.add("missing-second-pass-section")
            sections[name] = Section(spans=[], missing=True)

    return sections, flags


def _count_minor_bullets(
    lines: list[str], fence_before: list[bool], start: int, end: int, fence_disabled: bool = False
) -> int:
    count = 0
    for i in range(start + 1, end):
        line = lines[i]
        fenced = False if fence_disabled else fence_before[i]
        blockquoted = _is_blockquoted(line)
        if fenced or blockquoted:
            continue
        stripped = line.strip()
        if not stripped or stripped == "(none)":
            continue
        if re.match(r"^(?:[-*+]|\d+\.)\s+\S", line.lstrip()):
            count += 1
    return count


def _count_heading4_titles(
    lines: list[str], fence_before: list[bool], start: int, end: int, fence_disabled: bool = False
) -> list[str]:
    titles = []
    for i in range(start + 1, end):
        line = lines[i]
        fenced = False if fence_disabled else fence_before[i]
        blockquoted = _is_blockquoted(line)
        if _is_heading4(line, fenced, blockquoted):
            m = _HEADING4_RE.match(line)
            titles.append(m.group(2))
    return titles


def _dedupe_titles(span_title_lists: list[list[str]]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for titles in span_title_lists:
        for t in titles:
            key = _norm(t)
            if key in seen:
                continue
            seen.add(key)
            result.append(t)
    return result


@dataclass
class Entry:
    start: int
    end: int
    title: str | None
    severity_raw: str | None
    has_finding: bool


def _parse_entries_in_span(
    lines: list[str], fence_before: list[bool], start: int, end: int, fence_disabled: bool = False
) -> list[Entry]:
    """Entry boundary rule (#561 round 4 F1, refined fresh rounds 5-6).

    An entry begins at the first line-initial `**Finding:**` or
    `**Severity:**` marker and extends to the line before the next `####`
    heading or the next line-initial `**Finding:**` marker (excluded if
    fenced/blockquoted), whichever comes first, or to the end of the section.
    A `**Severity:**` line found inside an already-open entry is that
    entry's own severity line and does not open a second entry.
    """
    entries: list[Entry] = []
    open_entry: dict | None = None
    pending_title: str | None = None

    for i in range(start + 1, end):
        line = lines[i]
        fenced = False if fence_disabled else fence_before[i]
        blockquoted = _is_blockquoted(line)

        if _is_heading4(line, fenced, blockquoted):
            if open_entry is not None:
                open_entry["end"] = i
                entries.append(Entry(**open_entry))
                open_entry = None
            m = _HEADING4_RE.match(line)
            pending_title = m.group(2)
            continue

        cls = _classify_line(line, fenced, blockquoted)
        if cls is None:
            continue
        kind, value = cls

        if kind == "finding":
            if open_entry is not None:
                open_entry["end"] = i
                entries.append(Entry(**open_entry))
            open_entry = {
                "start": i,
                "title": pending_title,
                "severity_raw": None,
                "has_finding": True,
            }
            pending_title = None
        elif kind == "severity":
            if open_entry is not None:
                if open_entry["severity_raw"] is None:
                    open_entry["severity_raw"] = value
            else:
                open_entry = {
                    "start": i,
                    "title": pending_title,
                    "severity_raw": value,
                    "has_finding": False,
                }
                pending_title = None

    if open_entry is not None:
        open_entry["end"] = end
        entries.append(Entry(**open_entry))

    return entries


def _dedupe_entries(span_entry_lists: list[list[Entry]]) -> list[Entry]:
    seen: set[str] = set()
    result: list[Entry] = []
    for entries in span_entry_lists:
        for e in entries:
            key = _norm(e.title) if e.title else f"__pos_{e.start}"
            if key in seen:
                continue
            seen.add(key)
            result.append(e)
    return result


def _entry_severity(entry: Entry) -> tuple[str, bool, str | None]:
    token, annotated = parse_severity_token(entry.severity_raw)
    if token is None:
        return "Significant", True, "malformed-second-pass-entry"
    flag = "annotated-second-pass-severity" if annotated else None
    return token, annotated, flag


def _parse_declared(first_line: str) -> dict | None:
    m = _DECLARED_RE.match(first_line.strip())
    if not m:
        return None
    return {
        "fatal": int(m.group(1)),
        "significant": int(m.group(2)),
        "minor": int(m.group(3)),
    }


@dataclass
class ScoreResult:
    fatal_count: int
    significant_count: int
    minor_count: int
    weighted_score: int
    clean_pass: bool  # orchestrator's own count is 0 Fatal / 0 Significant
    candidate_clean: bool  # clean_pass AND the discrepancy exception has not fired
    discrepancy: bool  # declared fatal+significant total exceeds the own count
    empty_work_order_escalation: bool  # discrepancy fired AND own count is 0/0
    route: str
    flags: set[str]
    declared: dict | None
    second_pass_fatal: list[Entry]
    second_pass_significant: list[Entry]
    second_pass_minor: list[Entry]


def score(text: str) -> ScoreResult:
    """Score a findings-file text per the Score source rule (SKILL.md CONTRACT
    block, step 7). This is the single executable implementation both
    SKILL.md's prose and red-team-prompt.md's mirror describe."""
    lines = text.split("\n")
    fence_before = _fence_state_before(lines)
    sections, flags = locate_sections(lines, fence_before)

    def _disabled(span):
        s, e = span
        d = _section_fence_disabled(lines, fence_before, s, e)
        if d:
            flags.add("malformed-second-pass-fencing")
        return d

    fatal_titles = _dedupe_titles(
        [
            _count_heading4_titles(lines, fence_before, s, e, fence_disabled=_disabled((s, e)))
            for s, e in sections["Fatal Challenges"].spans
        ]
    )
    sig_titles = _dedupe_titles(
        [
            _count_heading4_titles(lines, fence_before, s, e, fence_disabled=_disabled((s, e)))
            for s, e in sections["Significant Challenges"].spans
        ]
    )

    sp_entries = _dedupe_entries(
        [
            _parse_entries_in_span(lines, fence_before, s, e, fence_disabled=_disabled((s, e)))
            for s, e in sections["Second Pass Findings"].spans
        ]
    )

    sp_fatal, sp_significant, sp_minor = [], [], []
    for e in sp_entries:
        sev, _annotated, flag = _entry_severity(e)
        if flag:
            flags.add(flag)
        if sev == "Fatal":
            sp_fatal.append(e)
        elif sev == "Significant":
            sp_significant.append(e)
        elif sev == "Minor":
            sp_minor.append(e)

    minor_obs_count = 0
    for s, e in sections["Minor Observations"].spans:
        minor_obs_count += _count_minor_bullets(lines, fence_before, s, e, fence_disabled=_disabled((s, e)))

    # Cross-section de-dup (#561 round 4 F1 de-dup clause): a Second-Pass
    # entry that restates an already-counted Fatal/Significant Challenges
    # entry counts ONCE, at the higher of the two severities. Matched by
    # normalized `#### <title>` text (the identity basis worked evals use).
    fatal_norm = {_norm(t) for t in fatal_titles}
    sig_norm_remaining = list(sig_titles)
    sig_norm_set = {_norm(t) for t in sig_norm_remaining}

    extra_fatal = []
    for e in sp_fatal:
        key = _norm(e.title) if e.title else None
        if key and key in fatal_norm:
            continue
        if key and key in sig_norm_set:
            sig_norm_set.discard(key)
            sig_norm_remaining = [t for t in sig_norm_remaining if _norm(t) != key]
            flags.add("second-pass-cross-section-dedup")
        extra_fatal.append(e)

    extra_sig = []
    for e in sp_significant:
        key = _norm(e.title) if e.title else None
        if key and (key in fatal_norm or key in sig_norm_set):
            continue
        extra_sig.append(e)

    fatal_count = len(fatal_titles) + len(extra_fatal)
    significant_count = len(sig_norm_remaining) + len(extra_sig)
    minor_count = minor_obs_count + len(sp_minor)

    weighted_score = fatal_count * 3 + significant_count * 1
    clean_pass = fatal_count == 0 and significant_count == 0

    declared = _parse_declared(lines[0]) if lines else None
    discrepancy = False
    own_total = fatal_count + significant_count
    if declared is not None:
        declared_total = declared["fatal"] + declared["significant"]
        if declared_total > own_total:
            discrepancy = True
            flags.add("severity-counts-discrepancy")

    empty_work_order_escalation = discrepancy and own_total == 0
    candidate_clean = clean_pass and not discrepancy

    if empty_work_order_escalation:
        route = "escalate-empty-work-order"
    elif discrepancy:
        route = "fix-loop-discrepancy"
    elif clean_pass:
        route = "clean-pass"
    else:
        route = "fix-loop"

    return ScoreResult(
        fatal_count=fatal_count,
        significant_count=significant_count,
        minor_count=minor_count,
        weighted_score=weighted_score,
        clean_pass=clean_pass,
        candidate_clean=candidate_clean,
        discrepancy=discrepancy,
        empty_work_order_escalation=empty_work_order_escalation,
        route=route,
        flags=flags,
        declared=declared,
        second_pass_fatal=sp_fatal,
        second_pass_significant=sp_significant,
        second_pass_minor=sp_minor,
    )
