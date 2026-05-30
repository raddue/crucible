"""Mechanical-check matcher module for temper lens evals (Task 5).

Implements the v1 mechanical check set per Design D7. Drives the
structured-expectation discriminator in `skills/temper/evals/evals.json`.

Parser assumptions (documented inline rather than in a doc block so
maintainers reading the regexes see them immediately):

- Findings are list items under an `### Issues` or `### Code Review`/
  similar section. We accept three numbered-item shapes: `N.`, `**N.**`,
  and `- N.` because reviewer output varies in markdown decoration.
- A finding "block" runs from its header line until the next finding
  header OR the next `###` heading OR EOF — whichever comes first.
- Inside a block we scan child lines (any indentation) for
  `File: <path>:<lo>-<hi>` (or `:<line>`), `Severity: <Word>`,
  `Lens: <Name>` or `Lens: <Name> (re-attributed)`.
- The `section` field is the text of the nearest preceding `###`
  heading (e.g., "Correctness", "Code Review"). It scopes the
  reattributed_finding_fires check.
- Substring-collision guard: lens matching uses an anchored regex
  `^Lens:\\s+<lens>\\s*(\\(re-attributed\\))?\\s*$` (per Design D7),
  so `Lens: DRY (re-attributed)` cannot leak into a `lens="DRY"`
  direct-fire query without the `include_reattributed` opt-in.
"""

from __future__ import annotations

import re
from typing import Literal

Verdict = Literal["PASS", "FAIL", "N/A"]
Result = tuple[Verdict, str]


class MutexViolationError(ValueError):
    """Raised when a single finding is tagged with both Lens: and Category:.

    These dimensions are mutually exclusive per Design D7. The scorer catches
    this and fails the fixture loudly rather than silently merging both fields.
    """

    pass


# Report-prose sections under which numbered/list items are NOT findings.
# A `### Pre-flight` block (and friends) may contain numbered checklists; those
# must not be parsed as phantom findings.
_REPORT_SECTIONS = frozenset(
    {"Pre-flight", "Strengths", "Overall", "Recommendations", "Assessment"}
)

# Trailing parenthetical annotation on a heading, e.g. the "(feature delivery)"
# in `### Pre-flight (feature delivery)`. Stripped before the _REPORT_SECTIONS
# membership test so a decorated heading still suppresses phantom findings.
_HEADING_ANNOTATION_RE = re.compile(r"\s*\([^)]*\)\s*$")


def _section_key(heading: str | None) -> str | None:
    """Normalize a `### ` heading to its bare section name for _REPORT_SECTIONS
    lookup: drop a trailing parenthetical annotation and a trailing colon."""
    if heading is None:
        return None
    return _HEADING_ANNOTATION_RE.sub("", heading).strip().rstrip(":")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^###\s+(.+?)\s*$")
# Finding header: numbered item, optionally bold/bulleted.
_FINDING_HEADER_RE = re.compile(r"^\s*(?:-\s+)?(?:\*\*)?(\d+)\.\s+")
_FILE_RE = re.compile(r"^\s*[-*]?\s*File:\s+(\S+?):(\d+)(?:-(\d+))?\s*$")
_SEVERITY_RE = re.compile(r"^\s*[-*]?\s*Severity:\s+(\w+)\s*$")
_LENS_RE = re.compile(r"^\s*[-*]?\s*Lens:\s+(\S+)\s*(\(re-attributed\))?\s*$")
_CATEGORY_RE = re.compile(r"^\s*[-*]?\s*Category:\s+(\S+)\s*$")


def _parse_findings(output: str) -> list[dict]:
    """Return list of findings with keys file, line_range, severity, lens,
    lens_reattributed, category, cited_files, body, section. Pathless findings
    include file=None. A MutexViolationError is raised when a finding carries
    both Lens: and Category: lines (mutex tripwire — fails the parse).

    Numbered/list items inside report-prose sections (see _REPORT_SECTIONS,
    esp. `### Pre-flight`) are skipped — they are not findings."""
    lines = output.splitlines()

    # Pre-pass: identify boundary line indices (finding headers + ### headings).
    boundaries: list[int] = []
    for i, line in enumerate(lines):
        if _FINDING_HEADER_RE.match(line) or _HEADING_RE.match(line):
            boundaries.append(i)
    boundaries.append(len(lines))

    findings: list[dict] = []
    current_section: str | None = None

    for idx, line in enumerate(lines):
        h = _HEADING_RE.match(line)
        if h:
            current_section = h.group(1)
            continue

        if not _FINDING_HEADER_RE.match(line):
            continue

        # Numbered/list items inside report-prose sections (esp. Pre-flight)
        # are NOT findings — skip them. Boundary pre-pass is unchanged so block
        # extents for real findings stay correct.
        if _section_key(current_section) in _REPORT_SECTIONS:
            continue

        # Find this finding's end: next boundary strictly after idx.
        end = next(b for b in boundaries if b > idx)

        block = lines[idx + 1 : end]
        header_line = line
        cited_files: list[tuple[str, tuple[int, int]]] = []
        file_path: str | None = None
        line_range: tuple[int, int] | None = None
        severity: str | None = None
        lens: str | None = None
        reattributed = False
        category: str | None = None

        for child in block:
            m = _FILE_RE.match(child)
            if m:
                lo = int(m.group(2))
                hi = int(m.group(3)) if m.group(3) else lo
                cited_files.append((m.group(1), (lo, hi)))
                continue
            m = _SEVERITY_RE.match(child)
            if m:
                severity = m.group(1)
                continue
            m = _LENS_RE.match(child)
            if m:
                lens = m.group(1)
                reattributed = m.group(2) is not None
                continue
            m = _CATEGORY_RE.match(child)
            if m:
                category = m.group(1)
                continue

        # First citation drives the back-compat scalar file/line_range fields.
        if cited_files:
            file_path = cited_files[0][0]
            line_range = cited_files[0][1]

        # Mutex tripwire: a finding cannot carry both a Lens: and a Category:.
        if lens is not None and category is not None:
            raise MutexViolationError(
                f"finding tagged both Lens: {lens} and Category: {category}"
            )

        # Capture finding body (header + block lines, joined) for
        # finding-body-does-not-contain pattern scans. Keep raw casing here;
        # the matcher handles case-insensitive matching downstream.
        body = "\n".join([header_line, *block])

        findings.append(
            {
                "file": file_path,
                "line_range": line_range,
                "cited_files": cited_files,
                "severity": severity,
                "lens": lens,
                "lens_reattributed": reattributed,
                "category": category,
                "body": body,
                "section": current_section,
            }
        )

    return findings


def _report_blocks(output: str, heading: str) -> list[str]:
    """Return the text blocks under every `### <heading>` section.

    Each block runs from the line after the heading to the next `### ` heading
    or EOF, joined by newlines. The heading line itself is excluded."""
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
# Check functions
# ---------------------------------------------------------------------------


def all_findings_have_file_line(output: str) -> Result:
    findings = _parse_findings(output)
    if not findings:
        return ("N/A", "no findings parsed")
    missing = [f for f in findings if f["file"] is None or f["line_range"] is None]
    if missing:
        return ("FAIL", f"{len(missing)} finding(s) without File:line")
    return ("PASS", f"all {len(findings)} finding(s) cite File:line")


def lens_findings_in_allowed_files(
    output: str, fixture: dict, ocp_carveout: bool = True
) -> Result:
    allowed = set(fixture.get("allowed_files", []))
    findings = _parse_findings(output)
    lens_findings = [f for f in findings if f["lens"]]
    if not lens_findings:
        return ("N/A", "no lens-tagged findings")

    violations: list[str] = []
    for f in lens_findings:
        if f["file"] is None:
            continue  # covered by all_findings_have_file_line
        if f["file"] in allowed:
            continue
        if ocp_carveout and f["lens"] == "OCP":
            continue  # carve-out applies to both direct and re-attributed
        violations.append(f"{f['lens']}{' (re-attributed)' if f['lens_reattributed'] else ''} cites {f['file']}")

    if violations:
        return ("FAIL", "; ".join(violations))
    return ("PASS", f"all {len(lens_findings)} lens finding(s) in allowed_files")


_SEVERITY_ORDER = {"Critical": 4, "Important": 3, "Minor": 2, "Suggestion": 1}


def _severity_at_least(actual: str | None, floor: str) -> bool:
    """True if `actual` severity is >= `floor`. Unknown actual severity = False."""
    if actual is None:
        return False
    a = _SEVERITY_ORDER.get(actual, 0)
    f = _SEVERITY_ORDER.get(floor, 0)
    return a >= f


def lens_finding_fires(
    output: str,
    lens: str,
    severity: str,
    include_reattributed: bool = False,
) -> Result:
    findings = _parse_findings(output)
    for f in findings:
        if f["lens"] != lens:
            continue
        if f["lens_reattributed"] and not include_reattributed:
            continue
        if f["severity"] == severity:
            return ("PASS", f"Lens: {lens} at {severity} fires")
    return ("FAIL", f"no Lens: {lens} finding at Severity: {severity}")


def category_finding_fires(
    output: str,
    category: str,
    severity: str | None = None,
    severity_at_least: str | None = None,
) -> Result:
    """Mirror of lens_finding_fires for Category-tagged findings.

    `severity` (exact match) and `severity_at_least` (≥ floor) are mutually
    optional. If both are specified, both must match. If neither is
    specified, any matching Category fires.
    """
    findings = _parse_findings(output)
    for f in findings:
        if f["category"] != category:
            continue
        if severity is not None and f["severity"] != severity:
            continue
        if severity_at_least is not None and not _severity_at_least(
            f["severity"], severity_at_least
        ):
            continue
        return ("PASS", f"Category: {category} at {f['severity']} fires")
    descr = (
        f"Severity: {severity}"
        if severity
        else f"Severity ≥ {severity_at_least}"
        if severity_at_least
        else "any severity"
    )
    return ("FAIL", f"no Category: {category} finding at {descr}")


def category_finding_does_not_fire(output: str, category: str) -> Result:
    findings = _parse_findings(output)
    for f in findings:
        if f["category"] == category:
            return (
                "FAIL",
                f"unexpected Category: {category} finding at {f['file']} "
                f"(severity {f['severity']})",
            )
    return ("PASS", f"no Category: {category} findings")


def finding_body_does_not_contain(
    output: str,
    patterns: list[str],
    case_insensitive: bool = True,
) -> Result:
    """FAIL if any finding's body text contains any pattern (substring match).
    Used to verify counter-rule effectiveness — e.g., assert no finding's
    prose contains AI-Slop "over-defensive" trigger phrases."""
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


def findings_count_at_least(output: str, n: int) -> Result:
    """PASS if the parsed findings count is >= n. Used as a positive
    co-assertion alongside negative checks (distinguishes 'reviewer engaged'
    from 'reviewer silent')."""
    findings = _parse_findings(output)
    actual = len(findings)
    if actual >= n:
        return ("PASS", f"{actual} finding(s) ≥ {n} required")
    return ("FAIL", f"only {actual} finding(s), need ≥ {n}")


def lens_finding_does_not_fire(
    output: str, lens: str, include_reattributed: bool = False
) -> Result:
    findings = _parse_findings(output)
    for f in findings:
        if f["lens"] != lens:
            continue
        if f["lens_reattributed"] and not include_reattributed:
            continue
        return ("FAIL", f"unexpected Lens: {lens} finding at {f['file']}")
    return ("PASS", f"no Lens: {lens} direct findings")


def reattributed_finding_fires(
    output: str,
    lens: str,
    severity: str,
    section: str | None = None,
) -> Result:
    findings = _parse_findings(output)
    for f in findings:
        if f["lens"] != lens or not f["lens_reattributed"]:
            continue
        if f["severity"] != severity:
            continue
        if section is not None and f["section"] != section:
            continue
        return ("PASS", f"Lens: {lens} (re-attributed) at {severity} fires")
    scope = f" in section {section!r}" if section else ""
    return ("FAIL", f"no Lens: {lens} (re-attributed) at {severity}{scope}")


def lens_finding_cites_file(
    output: str, lens: str, file: str, include_reattributed: bool = False
) -> Result:
    findings = _parse_findings(output)
    for f in findings:
        if f["lens"] != lens:
            continue
        if f["lens_reattributed"] and not include_reattributed:
            continue
        if f["file"] == file:
            return ("PASS", f"Lens: {lens} cites {file}")
    return ("FAIL", f"no Lens: {lens} finding cites {file}")


def _ranges_overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def no_lens_findings_overlap_region(
    output: str, primary_lens: str, secondary_lens: str
) -> Result:
    findings = _parse_findings(output)
    primary = [
        f for f in findings
        if f["lens"] == primary_lens and not f["lens_reattributed"]
        and f["file"] and f["line_range"]
    ]
    secondary = [
        f for f in findings
        if f["lens"] == secondary_lens and not f["lens_reattributed"]
        and f["file"] and f["line_range"]
    ]
    for p in primary:
        for s in secondary:
            if p["file"] == s["file"] and _ranges_overlap(p["line_range"], s["line_range"]):
                return (
                    "FAIL",
                    f"{primary_lens} {p['file']}:{p['line_range']} overlaps "
                    f"{secondary_lens} {s['file']}:{s['line_range']}",
                )
    return ("PASS", f"no overlap between {primary_lens} and {secondary_lens} regions")


def finding_cites_n_files(
    output: str,
    n: int | None = None,
    files: list[str] | None = None,
    lens: str | None = None,
    category: str | None = None,
) -> Result:
    """Assert findings cite enough File: sites and/or specific paths.

    `n` counts File: citation SITES (not distinct paths) across matching
    findings. `files` checks distinct-path coverage. Findings are filtered by
    `lens`/`category` when given. At least one of n/files is required."""
    findings = _parse_findings(output)
    matching = [
        f
        for f in findings
        if (lens is None or f["lens"] == lens)
        and (category is None or f["category"] == category)
    ]

    if n is None and files is None:
        return ("N/A", "no n or files param")

    if n is not None:
        sites = sum(len(f["cited_files"]) for f in matching)
        if sites < n:
            return ("FAIL", f"{sites} File: citation site(s), need ≥ {n}")

    if files is not None:
        distinct_paths = {
            path for f in matching for (path, _rng) in f["cited_files"]
        }
        missing = set(files) - distinct_paths
        if missing:
            return ("FAIL", f"missing cited path(s): {', '.join(sorted(missing))}")

    scope = []
    if n is not None:
        scope.append(f"≥ {n} site(s)")
    if files is not None:
        scope.append(f"{len(files)} required path(s) covered")
    return ("PASS", "; ".join(scope))


def finding_body_contains(
    output: str, pattern: str, case_insensitive: bool = True
) -> Result:
    """Positive mirror of finding_body_does_not_contain. PASS if ANY finding's
    body contains `pattern` (substring match)."""
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
    """PASS if a `### <heading>` block exists with >= min_chars non-whitespace
    characters. Distinguishes 'no heading' from 'heading present but empty'."""
    blocks = _report_blocks(output, heading)
    if not blocks:
        return ("FAIL", f"no ### {heading} heading")
    nonws = sum(1 for c in "\n".join(blocks) if not c.isspace())
    if nonws >= min_chars:
        return ("PASS", f"### {heading} block has {nonws} non-ws char(s)")
    return ("FAIL", f"### {heading} block empty ({nonws} < {min_chars} non-ws char(s))")


def report_block_contains(
    output: str, heading: str, pattern: str, case_insensitive: bool = True
) -> Result:
    """PASS if `pattern` matches (regex search) within the union of all
    `### <heading>` blocks. Blocks are joined with a newline so a pattern can
    never falsely match across a block boundary (e.g. two Pre-flight sections)."""
    union = "\n".join(_report_blocks(output, heading))
    flags = re.I if case_insensitive else 0
    if re.search(pattern, union, flags):
        return ("PASS", f"{pattern!r} found in ### {heading} block(s)")
    return ("FAIL", f"{pattern!r} not found in ### {heading} block(s)")


# ---------------------------------------------------------------------------
# Dispatcher + replicate aggregator
# ---------------------------------------------------------------------------

# Registry keyed by canonical kebab-case check names (per Design D7). Snake-case
# aliases accepted for ergonomic Python use; both forms route to the same fn.
_CHECK_REGISTRY = {
    "all-findings-have-file-line": all_findings_have_file_line,
    "lens-findings-in-allowed-files": lens_findings_in_allowed_files,
    "lens-finding-fires": lens_finding_fires,
    "lens-finding-does-not-fire": lens_finding_does_not_fire,
    "reattributed-finding-fires": reattributed_finding_fires,
    "lens-finding-cites-file": lens_finding_cites_file,
    "no-lens-findings-overlap-region": no_lens_findings_overlap_region,
    "category-finding-fires": category_finding_fires,
    "category-finding-does-not-fire": category_finding_does_not_fire,
    "finding-body-does-not-contain": finding_body_does_not_contain,
    "finding-body-contains": finding_body_contains,
    "findings-count-at-least": findings_count_at_least,
    "finding-cites-n-files": finding_cites_n_files,
    "report-has-block": report_has_block,
    "report-block-contains": report_block_contains,
}

# Checks that take (output, fixture, ocp_carveout) — fixture-aware.
_FIXTURE_AWARE_CHECKS = {"lens-findings-in-allowed-files"}


def _normalize_check_name(name: str | None) -> str | None:
    if name is None:
        return None
    return name.replace("_", "-")


def evaluate_expectation(
    expectation: dict, reviewer_output: str, fixture: dict
) -> Result:
    """Dispatch by expectation['type']='mechanical' + expectation['check'].

    Schema (per Design D7):
      {"type": "mechanical", "check": "<kebab-case-name>", "params": {...},
       "prerequisite": <inline-expectation-dict> | <kebab-name>}

    Both 'params' (canonical per design) and 'args' (legacy) accepted.
    Both kebab-case and snake_case check names accepted.

    Prerequisite resolution:
      - If 'prerequisite' is a dict (an inline expectation object), it is
        evaluated via evaluate_expectation recursively — carrying its own
        params. This is the production path; required for checks like
        lens-finding-fires that need lens/severity args.
      - If 'prerequisite' is a string (legacy by-name reference), the named
        check is re-run with no args. Only works for zero-arg checks like
        all-findings-have-file-line.
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
            prereq_label = str(prereq)  # preserve original casing in rationale
        if prereq_verdict != "PASS":
            return ("N/A", f"prereq {prereq_label} failed")

    check_name = _normalize_check_name(expectation.get("check"))
    fn = _CHECK_REGISTRY.get(check_name)
    if fn is None:
        return ("FAIL", f"unknown check {expectation.get('check')!r}")

    # Accept both 'params' (canonical) and 'args' (legacy); params wins on collision.
    args = {**expectation.get("args", {}), **expectation.get("params", {})}
    if check_name in _FIXTURE_AWARE_CHECKS:
        return fn(reviewer_output, fixture, **args)
    return fn(reviewer_output, **args)


def aggregate_replicates(
    per_trial_verdicts: list[Verdict], threshold: int
) -> Verdict:
    """Returns N/A if all trials N/A; PASS if ≥threshold of non-N/A trials
    are PASS; FAIL otherwise."""
    non_na = [v for v in per_trial_verdicts if v != "N/A"]
    if not non_na:
        return "N/A"
    passes = sum(1 for v in non_na if v == "PASS")
    return "PASS" if passes >= threshold else "FAIL"
