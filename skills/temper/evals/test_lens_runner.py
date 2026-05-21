"""TDD test suite for lens_runner.py (Task 5b).

Synthetic reviewer-output strings drive PASS/FAIL pairs for each
mechanical check defined in Design D7. The substring-collision
regression test is load-bearing: it guards against the (re-attributed)
suffix being matched by a bare-lens `Lens: <name>` regex.
"""

from __future__ import annotations

import pytest

from skills.temper.evals.lens_runner import (
    aggregate_replicates,
    all_findings_have_file_line,
    evaluate_expectation,
    lens_finding_cites_file,
    lens_finding_does_not_fire,
    lens_finding_fires,
    lens_findings_in_allowed_files,
    no_lens_findings_overlap_region,
    reattributed_finding_fires,
)


# ---------------------------------------------------------------------------
# Synthetic reviewer-output fixtures
# ---------------------------------------------------------------------------

SAMPLE_DRY_DIRECT = """
### Code Review
- Verdict: Issues Found
- Issues:

1. **Duplicate helper logic**
   - File: src/util.py:42-48
   - Severity: Minor
   - Lens: DRY
   - Issue: Same five-line guard appears in two call sites.
"""

SAMPLE_DRY_REATTRIBUTED = """
### Code Review
- Verdict: Issues Found

### Correctness
- Verdict: Issues Found
- Issues:

1. **Divergent bound check across copies**
   - File: src/util.py:42-48
   - Severity: Important
   - Lens: DRY (re-attributed)
   - Issue: Two copies of the bound check disagree on the upper bound.
"""

SAMPLE_NO_FINDINGS = """
### Code Review
- Verdict: Clean
- Issues: none
"""

SAMPLE_PATHLESS_FINDING = """
### Code Review
- Verdict: Issues Found
- Issues:

1. **Something vague**
   - Severity: Minor
   - Lens: DRY
   - Issue: No file cited.
"""

SAMPLE_OCP_DIRECT = """
### Code Review
- Verdict: Issues Found
- Issues:

1. **Dispatch table grew**
   - File: src/dispatch.py:10-12
   - Severity: Minor
   - Lens: OCP
   - Issue: New case added to switch.
"""

SAMPLE_SRP_AND_DRY_DISJOINT = """
### Code Review
- Verdict: Issues Found
- Issues:

1. **SRP mixing**
   - File: src/svc.py:10-20
   - Severity: Minor
   - Lens: SRP
   - Issue: Two responsibilities.

2. **DRY repeat**
   - File: src/svc.py:50-55
   - Severity: Minor
   - Lens: DRY
   - Issue: Helper duplicated.
"""

SAMPLE_SRP_AND_DRY_OVERLAP = """
### Code Review
- Verdict: Issues Found
- Issues:

1. **SRP mixing**
   - File: src/svc.py:10-20
   - Severity: Minor
   - Lens: SRP
   - Issue: Two responsibilities.

2. **DRY repeat**
   - File: src/svc.py:15-25
   - Severity: Minor
   - Lens: DRY
   - Issue: Helper duplicated.
"""

FIXTURE_DRY = {"allowed_files": ["src/util.py"]}
FIXTURE_OCP = {"allowed_files": ["src/feature.py"]}  # dispatch.py NOT listed
FIXTURE_SVC = {"allowed_files": ["src/svc.py"]}


# ---------------------------------------------------------------------------
# all_findings_have_file_line
# ---------------------------------------------------------------------------


def test_all_findings_have_file_line_pass():
    verdict, _ = all_findings_have_file_line(SAMPLE_DRY_DIRECT)
    assert verdict == "PASS"


def test_all_findings_have_file_line_fail():
    verdict, _ = all_findings_have_file_line(SAMPLE_PATHLESS_FINDING)
    assert verdict == "FAIL"


def test_all_findings_have_file_line_na_when_no_findings():
    verdict, _ = all_findings_have_file_line(SAMPLE_NO_FINDINGS)
    assert verdict == "N/A"


# ---------------------------------------------------------------------------
# lens_findings_in_allowed_files
# ---------------------------------------------------------------------------


def test_lens_findings_in_allowed_files_pass():
    verdict, _ = lens_findings_in_allowed_files(
        SAMPLE_DRY_DIRECT, FIXTURE_DRY, ocp_carveout=True
    )
    assert verdict == "PASS"


def test_lens_findings_in_allowed_files_fail():
    # DRY finding cites src/util.py but allowlist is src/feature.py
    verdict, _ = lens_findings_in_allowed_files(
        SAMPLE_DRY_DIRECT, FIXTURE_OCP, ocp_carveout=True
    )
    assert verdict == "FAIL"


def test_lens_findings_in_allowed_files_ocp_carveout_permits_out_of_scope():
    # OCP finding cites src/dispatch.py NOT in allowed_files → carve-out allows it
    verdict, _ = lens_findings_in_allowed_files(
        SAMPLE_OCP_DIRECT, FIXTURE_OCP, ocp_carveout=True
    )
    assert verdict == "PASS"


def test_lens_findings_in_allowed_files_ocp_reattributed_carveout():
    sample = SAMPLE_OCP_DIRECT.replace("Lens: OCP", "Lens: OCP (re-attributed)")
    verdict, _ = lens_findings_in_allowed_files(
        sample, FIXTURE_OCP, ocp_carveout=True
    )
    assert verdict == "PASS"


# ---------------------------------------------------------------------------
# lens_finding_fires
# ---------------------------------------------------------------------------


def test_lens_finding_fires_pass():
    verdict, _ = lens_finding_fires(SAMPLE_DRY_DIRECT, lens="DRY", severity="Minor")
    assert verdict == "PASS"


def test_lens_finding_fires_fail_wrong_severity():
    verdict, _ = lens_finding_fires(
        SAMPLE_DRY_DIRECT, lens="DRY", severity="Important"
    )
    assert verdict == "FAIL"


def test_lens_finding_fires_excludes_reattributed_by_default():
    # Re-attributed DRY should NOT count as direct DRY fire
    verdict, _ = lens_finding_fires(
        SAMPLE_DRY_REATTRIBUTED, lens="DRY", severity="Important"
    )
    assert verdict == "FAIL"


def test_lens_finding_fires_includes_reattributed_when_opted_in():
    verdict, _ = lens_finding_fires(
        SAMPLE_DRY_REATTRIBUTED,
        lens="DRY",
        severity="Important",
        include_reattributed=True,
    )
    assert verdict == "PASS"


# ---------------------------------------------------------------------------
# lens_finding_does_not_fire (incl. load-bearing substring test)
# ---------------------------------------------------------------------------


def test_lens_finding_does_not_fire_pass():
    verdict, _ = lens_finding_does_not_fire(SAMPLE_NO_FINDINGS, lens="DRY")
    assert verdict == "PASS"


def test_lens_finding_does_not_fire_fail():
    verdict, _ = lens_finding_does_not_fire(SAMPLE_DRY_DIRECT, lens="DRY")
    assert verdict == "FAIL"


def test_lens_finding_does_not_fire_excludes_reattributed():
    """Load-bearing substring-collision regression test.

    A `Lens: DRY (re-attributed)` line must NOT match a bare `lens="DRY"`
    direct-fire check. If the matcher uses `Lens: DRY` as a substring/prefix,
    this test will fail.
    """
    verdict, _ = lens_finding_does_not_fire(
        SAMPLE_DRY_REATTRIBUTED, lens="DRY", include_reattributed=False
    )
    assert verdict == "PASS"


# ---------------------------------------------------------------------------
# reattributed_finding_fires
# ---------------------------------------------------------------------------


def test_reattributed_finding_fires_pass():
    verdict, _ = reattributed_finding_fires(
        SAMPLE_DRY_REATTRIBUTED, lens="DRY", severity="Important"
    )
    assert verdict == "PASS"


def test_reattributed_finding_fires_fail_when_only_direct():
    verdict, _ = reattributed_finding_fires(
        SAMPLE_DRY_DIRECT, lens="DRY", severity="Minor"
    )
    assert verdict == "FAIL"


def test_reattributed_finding_fires_with_section_scoping_pass():
    verdict, _ = reattributed_finding_fires(
        SAMPLE_DRY_REATTRIBUTED,
        lens="DRY",
        severity="Important",
        section="Correctness",
    )
    assert verdict == "PASS"


def test_reattributed_finding_fires_with_section_scoping_fail():
    verdict, _ = reattributed_finding_fires(
        SAMPLE_DRY_REATTRIBUTED,
        lens="DRY",
        severity="Important",
        section="Performance",
    )
    assert verdict == "FAIL"


# ---------------------------------------------------------------------------
# lens_finding_cites_file
# ---------------------------------------------------------------------------


def test_lens_finding_cites_file_pass():
    verdict, _ = lens_finding_cites_file(
        SAMPLE_DRY_DIRECT, lens="DRY", file="src/util.py"
    )
    assert verdict == "PASS"


def test_lens_finding_cites_file_fail():
    verdict, _ = lens_finding_cites_file(
        SAMPLE_DRY_DIRECT, lens="DRY", file="src/other.py"
    )
    assert verdict == "FAIL"


# ---------------------------------------------------------------------------
# no_lens_findings_overlap_region
# ---------------------------------------------------------------------------


def test_no_lens_findings_overlap_region_pass():
    verdict, _ = no_lens_findings_overlap_region(
        SAMPLE_SRP_AND_DRY_DISJOINT, primary_lens="SRP", secondary_lens="DRY"
    )
    assert verdict == "PASS"


def test_no_lens_findings_overlap_region_fail():
    verdict, _ = no_lens_findings_overlap_region(
        SAMPLE_SRP_AND_DRY_OVERLAP, primary_lens="SRP", secondary_lens="DRY"
    )
    assert verdict == "FAIL"


# ---------------------------------------------------------------------------
# Prerequisite-N/A dispatch path
# ---------------------------------------------------------------------------


def test_evaluate_expectation_prerequisite_na():
    """When prereq FAILs, expectation returns N/A — not vacuous pass."""
    expectation = {
        "type": "mechanical",
        "check": "lens_finding_does_not_fire",
        "args": {"lens": "DRY"},
        "prerequisite": "surgical_fires",
    }
    # Force prereq FAIL by registering the named check via fixture
    fixture = {
        "allowed_files": ["src/util.py"],
        "_prereq_overrides": {"surgical_fires": ("FAIL", "stub")},
    }
    verdict, rationale = evaluate_expectation(
        expectation, SAMPLE_DRY_DIRECT, fixture
    )
    assert verdict == "N/A"
    assert "surgical_fires" in rationale


def test_evaluate_expectation_dispatches_check():
    expectation = {
        "type": "mechanical",
        "check": "lens_finding_fires",
        "args": {"lens": "DRY", "severity": "Minor"},
    }
    verdict, _ = evaluate_expectation(expectation, SAMPLE_DRY_DIRECT, FIXTURE_DRY)
    assert verdict == "PASS"


# ---------------------------------------------------------------------------
# Schema-form regression: kebab-case check names + 'params' field (D7 canonical)
# ---------------------------------------------------------------------------


def test_evaluate_expectation_kebab_case_check_name():
    """Canonical kebab-case check names per Design D7 must dispatch."""
    expectation = {
        "type": "mechanical",
        "check": "lens-finding-fires",
        "params": {"lens": "DRY", "severity": "Minor"},
    }
    verdict, _ = evaluate_expectation(expectation, SAMPLE_DRY_DIRECT, FIXTURE_DRY)
    assert verdict == "PASS"


def test_evaluate_expectation_params_field_canonical():
    """'params' is the canonical field per D7; must be honored."""
    expectation = {
        "type": "mechanical",
        "check": "lens-finding-does-not-fire",
        "params": {"lens": "Surgical"},
    }
    verdict, _ = evaluate_expectation(expectation, SAMPLE_DRY_DIRECT, FIXTURE_DRY)
    assert verdict == "PASS"


def test_evaluate_expectation_inline_prerequisite_with_args():
    """Production prereq path: prereq is a dict carrying its own args.
    Required for fixture 1b: surgical-fires prereq needs lens+severity."""
    # Output where Surgical fires at Important → prereq passes → expectation evaluates
    output_with_surgical = (
        "### Code Review\n- Verdict: Issues Found\n\n"
        "### Issues\n\n"
        "1. **Drive-by reformat**\n"
        "   - File: src/foo.py:10-20\n"
        "   - Severity: Important\n"
        "   - Lens: Surgical\n"
        "   - Issue: ...\n"
    )
    expectation = {
        "type": "mechanical",
        "check": "lens-finding-does-not-fire",
        "params": {"lens": "DRY"},
        "prerequisite": {
            "type": "mechanical",
            "check": "lens-finding-fires",
            "params": {"lens": "Surgical", "severity": "Important"},
        },
    }
    fixture = {"allowed_files": ["src/foo.py"]}
    verdict, _ = evaluate_expectation(expectation, output_with_surgical, fixture)
    assert verdict == "PASS"  # prereq passed AND DRY did not fire


def test_evaluate_expectation_inline_prerequisite_fails_returns_na():
    """When inline prereq FAILs, expectation returns N/A (not vacuous pass)."""
    output_no_surgical = SAMPLE_DRY_DIRECT  # no Surgical finding
    expectation = {
        "type": "mechanical",
        "check": "lens-finding-does-not-fire",
        "params": {"lens": "DRY"},
        "prerequisite": {
            "type": "mechanical",
            "check": "lens-finding-fires",
            "params": {"lens": "Surgical", "severity": "Important"},
        },
    }
    fixture = {"allowed_files": ["src/util.py"]}
    verdict, rationale = evaluate_expectation(expectation, output_no_surgical, fixture)
    assert verdict == "N/A"
    assert "prereq" in rationale


# ---------------------------------------------------------------------------
# aggregate_replicates
# ---------------------------------------------------------------------------


def test_aggregate_replicates_pass_majority():
    assert aggregate_replicates(["PASS", "PASS", "PASS", "FAIL", "FAIL"], 3) == "PASS"


def test_aggregate_replicates_fail_when_below_threshold():
    assert aggregate_replicates(["PASS", "FAIL", "FAIL", "FAIL", "FAIL"], 3) == "FAIL"


def test_aggregate_replicates_all_na_returns_na():
    assert aggregate_replicates(["N/A", "N/A", "N/A"], 2) == "N/A"


def test_aggregate_replicates_na_excluded_from_denominator():
    # 2 of 3 non-N/A trials PASS, threshold 2 → PASS
    assert aggregate_replicates(["PASS", "PASS", "N/A", "FAIL"], 2) == "PASS"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
