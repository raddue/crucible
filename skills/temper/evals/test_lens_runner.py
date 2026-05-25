"""TDD test suite for lens_runner.py (Task 5b).

Synthetic reviewer-output strings drive PASS/FAIL pairs for each
mechanical check defined in Design D7. The substring-collision
regression test is load-bearing: it guards against the (re-attributed)
suffix being matched by a bare-lens `Lens: <name>` regex.
"""

from __future__ import annotations

import json

import pytest

from skills.temper.evals.lens_runner import (
    aggregate_replicates,
    all_findings_have_file_line,
    category_finding_does_not_fire,
    category_finding_fires,
    evaluate_expectation,
    finding_body_does_not_contain,
    findings_count_at_least,
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
# Category checks (#267 — Tenancy / Rollback disciplines)
# ---------------------------------------------------------------------------

SAMPLE_TENANCY = """
### Code Review
- Verdict: Issues Found

1. **Forged-callback can reach foreign-tenant row**
   - File: src/webhooks.py:14-20
   - Severity: Important
   - Category: Tenancy
   - Issue: UPDATE filters by order_id only, not tenant_id.
"""

SAMPLE_ROLLBACK = """
### Code Review
- Verdict: Issues Found

1. **downgrade leaves orphan FK column**
   - File: migrations/20260521_add_regions.py:30-34
   - Severity: Important
   - Category: Rollback
   - Issue: downgrade() drops parent CASCADE but leaves customers.region_id column.
"""

SAMPLE_TENANCY_CRITICAL = """
### Code Review

1. **Exploitable cross-tenant reach**
   - File: src/api.py:12
   - Severity: Critical
   - Category: Tenancy
"""

SAMPLE_NO_CATEGORY = """
### Code Review
- Verdict: Clean
"""

SAMPLE_AI_SLOP = """
### Code Review

1. **Over-defensive null check**
   - File: src/foo.py:5
   - Severity: Minor
   - Issue: This is over-defensive error handling for a case that can't occur.
"""

SAMPLE_CLEAN_ENGAGED = """
### Code Review
- Verdict: Issues Found

1. **Typo in docstring**
   - File: src/orders.py:6
   - Severity: Suggestion
   - Issue: minor typo fix is fine but unrelated to the main change.
"""


def test_category_finding_fires_exact_severity():
    verdict, _ = category_finding_fires(SAMPLE_TENANCY, "Tenancy", severity="Important")
    assert verdict == "PASS"


def test_category_finding_fires_severity_at_least():
    verdict, _ = category_finding_fires(
        SAMPLE_TENANCY_CRITICAL, "Tenancy", severity_at_least="Important"
    )
    assert verdict == "PASS"  # Critical ≥ Important


def test_category_finding_fires_severity_at_least_fails_below_floor():
    sample = """
### Code Review

1. **Minor tenancy nit**
   - File: src/foo.py:1
   - Severity: Minor
   - Category: Tenancy
"""
    verdict, _ = category_finding_fires(
        sample, "Tenancy", severity_at_least="Important"
    )
    assert verdict == "FAIL"


def test_category_finding_fires_wrong_category():
    verdict, _ = category_finding_fires(SAMPLE_TENANCY, "Rollback")
    assert verdict == "FAIL"


def test_category_finding_fires_no_findings():
    verdict, _ = category_finding_fires(SAMPLE_NO_CATEGORY, "Tenancy")
    assert verdict == "FAIL"


def test_category_finding_does_not_fire_clean():
    verdict, _ = category_finding_does_not_fire(SAMPLE_NO_CATEGORY, "Tenancy")
    assert verdict == "PASS"


def test_category_finding_does_not_fire_fails_when_present():
    verdict, _ = category_finding_does_not_fire(SAMPLE_TENANCY, "Tenancy")
    assert verdict == "FAIL"


def test_category_finding_does_not_fire_orthogonal_category_clean():
    # Rollback finding present, but does-not-fire for Tenancy passes.
    verdict, _ = category_finding_does_not_fire(SAMPLE_ROLLBACK, "Tenancy")
    assert verdict == "PASS"


def test_finding_body_does_not_contain_clean():
    verdict, _ = finding_body_does_not_contain(
        SAMPLE_TENANCY, patterns=["over-defensive", "redundant check"]
    )
    assert verdict == "PASS"


def test_finding_body_does_not_contain_fails_on_match():
    verdict, _ = finding_body_does_not_contain(
        SAMPLE_AI_SLOP, patterns=["over-defensive"]
    )
    assert verdict == "FAIL"


def test_finding_body_does_not_contain_case_insensitive():
    verdict, _ = finding_body_does_not_contain(
        SAMPLE_AI_SLOP, patterns=["OVER-DEFENSIVE"], case_insensitive=True
    )
    assert verdict == "FAIL"


def test_finding_body_does_not_contain_no_findings_na():
    verdict, _ = finding_body_does_not_contain(
        SAMPLE_NO_CATEGORY, patterns=["over-defensive"]
    )
    assert verdict == "N/A"


def test_findings_count_at_least_pass():
    verdict, _ = findings_count_at_least(SAMPLE_CLEAN_ENGAGED, n=1)
    assert verdict == "PASS"


def test_findings_count_at_least_fail():
    verdict, _ = findings_count_at_least(SAMPLE_NO_CATEGORY, n=1)
    assert verdict == "FAIL"


def test_category_does_not_leak_into_lens_field():
    """A Category-tagged finding must NOT be picked up by lens_finding_fires."""
    from skills.temper.evals.lens_runner import _parse_findings

    findings = _parse_findings(SAMPLE_TENANCY)
    assert len(findings) == 1
    assert findings[0]["category"] == "Tenancy"
    assert findings[0]["lens"] is None  # category does not populate lens field


def test_mutex_tripwire_warns_on_both_tags(capsys):
    """When a finding has both Lens: and Category:, parser logs WARNING to
    stderr but still parses both fields. Verdict-affecting checks may then
    flag the inconsistency independently."""
    sample = """
### Code Review

1. **Mutex violation**
   - File: src/foo.py:1
   - Severity: Minor
   - Lens: DRY
   - Category: Tenancy
"""
    from skills.temper.evals.lens_runner import _parse_findings

    findings = _parse_findings(sample)
    assert len(findings) == 1
    assert findings[0]["lens"] == "DRY"
    assert findings[0]["category"] == "Tenancy"
    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert "Lens: DRY" in captured.err
    assert "Category: Tenancy" in captured.err


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


# ---------------------------------------------------------------------------
# Task 4 (#290 F2): _check_pr_description_leakage tests
# ---------------------------------------------------------------------------


def test_pr_desc_leak_substring_match_srp_related():
    # Design wants `srp-related` flagged via substring (NOT word-boundary).
    # Verifies the substring-mode (vs word-boundary) for lens-vocab patterns.
    from skills.temper.evals.run_evals import _check_pr_description_leakage
    warnings = _check_pr_description_leakage(
        "Some srp-related cleanup", fixture_id="t1"
    )
    assert "srp" in warnings


def test_pr_desc_leak_word_boundary_protects_tenancy_rollback(capsys):
    from skills.temper.evals.run_evals import _check_pr_description_leakage
    # tenant_id and rollback_handler are NOT bare-word matches
    warnings = _check_pr_description_leakage(
        "Add tenant_id filter to rollback_handler function",
        fixture_id="t2",
    )
    assert "tenancy" not in warnings
    assert "rollback" not in warnings


def test_pr_desc_leak_word_boundary_catches_bare_words():
    from skills.temper.evals.run_evals import _check_pr_description_leakage
    warnings = _check_pr_description_leakage(
        "This change touches tenancy semantics and triggers a rollback.",
        fixture_id="t2b",
    )
    assert "tenancy" in warnings
    assert "rollback" in warnings


def test_pr_desc_leak_blacklist_warns_not_fails(capsys):
    from skills.temper.evals.run_evals import _check_pr_description_leakage
    # "this is surgical" → warning to stderr, NOT FixtureValidationError
    warnings = _check_pr_description_leakage(
        "this is surgical work on the parser", fixture_id="t3"
    )
    assert "surgical" in warnings
    err = capsys.readouterr().err
    assert "WARNING" in err
    assert "surgical" in err
    assert "t3" in err


def test_pr_desc_leak_semantic_primes_warn():
    from skills.temper.evals.run_evals import _check_pr_description_leakage
    warnings = _check_pr_description_leakage(
        "Extract the duplicate code into a helper.", fixture_id="t4"
    )
    assert "extract" in warnings
    assert "duplicate" in warnings


def test_pr_desc_leak_lens_line_match_is_fatal():
    from skills.temper.evals.run_evals import (
        FixtureValidationError,
        _check_pr_description_leakage,
    )
    with pytest.raises(FixtureValidationError, match="Lens:"):
        _check_pr_description_leakage(
            "Some scope.\nLens: Surgical\nMore prose.", fixture_id="t5"
        )


def test_pr_desc_leak_lens_line_match_case_insensitive():
    from skills.temper.evals.run_evals import (
        FixtureValidationError,
        _check_pr_description_leakage,
    )
    with pytest.raises(FixtureValidationError):
        _check_pr_description_leakage(
            "scope\nlens: dry\nrest", fixture_id="t6"
        )


def test_pr_desc_leak_clean_text_returns_empty():
    from skills.temper.evals.run_evals import _check_pr_description_leakage
    warnings = _check_pr_description_leakage(
        "Add a slugify helper to support max-length truncation.",
        fixture_id="t7",
    )
    assert warnings == []


# ---------------------------------------------------------------------------
# Task 5 (#290 S2): lens_column enum + forward-compat allowlist tests
# ---------------------------------------------------------------------------


def test_lens_column_enum_accepts_known_values():
    from skills.temper.evals.run_evals import _validate_lens_column
    for v in ("Surgical", "DRY", "SRP", "OCP", "none"):
        _validate_lens_column(v, fixture_id="ok")  # must not raise


def test_lens_column_enum_rejects_typo():
    from skills.temper.evals.run_evals import (
        FixtureValidationError,
        _validate_lens_column,
    )
    with pytest.raises(FixtureValidationError, match="Surigcal"):
        _validate_lens_column("Surigcal", fixture_id="x")


def test_lens_column_future_compat_constant_documented():
    # Module-level constant _LENS_COLUMN_FUTURE must list "Tenancy", "Rollback"
    # so future widening fails loud not silent.
    from skills.temper.evals.run_evals import _LENS_COLUMN_FUTURE
    assert {"Tenancy", "Rollback"} <= set(_LENS_COLUMN_FUTURE)


def test_lens_column_mixed_accepts_list():
    from skills.temper.evals.run_evals import _validate_lens_column
    _validate_lens_column(["Surgical", "OCP"], fixture_id="mixed-1")  # ok


def test_lens_column_mixed_rejects_none_in_list():
    from skills.temper.evals.run_evals import (
        FixtureValidationError,
        _validate_lens_column,
    )
    with pytest.raises(FixtureValidationError):
        _validate_lens_column(["Surgical", "none"], fixture_id="m2")


def test_lens_column_tenancy_fail_loud():
    from skills.temper.evals.run_evals import (
        FixtureValidationError,
        _validate_lens_column,
    )
    with pytest.raises(
        FixtureValidationError,
        match=r"lens_column 'Tenancy' is reserved for future use; not yet wired\.",
    ):
        _validate_lens_column("Tenancy", fixture_id="future-t")


def test_lens_column_rollback_fail_loud():
    from skills.temper.evals.run_evals import (
        FixtureValidationError,
        _validate_lens_column,
    )
    with pytest.raises(
        FixtureValidationError,
        match=r"lens_column 'Rollback' is reserved for future use; not yet wired\.",
    ):
        _validate_lens_column("Rollback", fixture_id="future-r")


def test_lens_column_rejects_non_string_non_list():
    from skills.temper.evals.run_evals import (
        FixtureValidationError,
        _validate_lens_column,
    )
    with pytest.raises(FixtureValidationError, match="must be str or list"):
        _validate_lens_column(42, fixture_id="bad")


def test_lens_column_rejects_empty_list():
    from skills.temper.evals.run_evals import (
        FixtureValidationError,
        _validate_lens_column,
    )
    with pytest.raises(FixtureValidationError, match="empty list"):
        _validate_lens_column([], fixture_id="bad-empty")


# ---------------------------------------------------------------------------
# Task 9 (#290 S3): per-lens-column PASS for mixed fixtures
# ---------------------------------------------------------------------------


def test_non_mixed_fixture_per_lens_pass_all_true():
    from skills.temper.evals.run_evals import _compute_per_lens_pass
    fixture = {
        "id": "ex-1",
        "lens_column": "Surgical",
        "expectations": [
            {"check": "lens-finding-fires", "params": {"lens": "Surgical"}},
            {"check": "all-findings-have-file-line"},
        ],
    }
    assert _compute_per_lens_pass(fixture, [True, True]) == {"Surgical": True}


def test_non_mixed_fixture_per_lens_pass_one_false():
    from skills.temper.evals.run_evals import _compute_per_lens_pass
    fixture = {
        "id": "ex-2",
        "lens_column": "DRY",
        "expectations": [
            {"check": "lens-finding-fires", "params": {"lens": "DRY"}},
            {"check": "all-findings-have-file-line"},
        ],
    }
    assert _compute_per_lens_pass(fixture, [True, False]) == {"DRY": False}


def test_mixed_fixture_per_lens_pass_partitioned():
    from skills.temper.evals.run_evals import _compute_per_lens_pass
    fixture = {
        "id": "mixed-real",
        "lens_column": ["Surgical", "OCP"],
        "expectations": [
            {"check": "lens-finding-fires", "params": {"lens": "Surgical"}},
            {"check": "lens-finding-fires", "params": {"lens": "OCP"}},
            {"check": "all-findings-have-file-line"},  # global
        ],
    }
    # surgical PASS, ocp FAIL, global PASS → {Surgical: True, OCP: False}
    result = _compute_per_lens_pass(fixture, [True, False, True])
    assert result == {"Surgical": True, "OCP": False}


def test_mixed_fixture_global_fail_taints_all_columns():
    from skills.temper.evals.run_evals import _compute_per_lens_pass
    fixture = {
        "id": "mixed-2",
        "lens_column": ["Surgical", "OCP"],
        "expectations": [
            {"check": "lens-finding-fires", "params": {"lens": "Surgical"}},
            {"check": "lens-finding-fires", "params": {"lens": "OCP"}},
            {"check": "all-findings-have-file-line"},  # global
        ],
    }
    # global fails → both columns fail regardless of lens-specific verdict
    result = _compute_per_lens_pass(fixture, [True, True, False])
    assert result == {"Surgical": False, "OCP": False}


def test_mixed_fixture_drift_delta_decoupled():
    # 5 trials simulated: per-trial per-lens map collected externally;
    # this test verifies a single mixed trial returns DECOUPLED per-lens bools.
    from skills.temper.evals.run_evals import _compute_per_lens_pass
    fixture = {
        "id": "mixed-3",
        "lens_column": ["Surgical", "OCP"],
        "expectations": [
            {"check": "lens-finding-fires", "params": {"lens": "Surgical"}},
            {"check": "lens-finding-fires", "params": {"lens": "OCP"}},
        ],
    }
    # All-Surgical-pass / all-OCP-fail across 5 trials → Surgical rate 1.0, OCP 0.0
    per_trial_maps = [_compute_per_lens_pass(fixture, [True, False]) for _ in range(5)]
    surg_rate = sum(1 for m in per_trial_maps if m["Surgical"]) / 5
    ocp_rate = sum(1 for m in per_trial_maps if m["OCP"]) / 5
    assert surg_rate == 1.0
    assert ocp_rate == 0.0


def test_mixed_fixture_cross_leakage_raises():
    from skills.temper.evals.run_evals import _compute_per_lens_pass
    fixture = {
        "id": "bad-leak",
        "lens_column": ["Surgical", "OCP"],
        "expectations": [
            {"check": "lens-finding-fires", "params": {"lens": "Surgical"}},
            {"check": "lens-finding-fires", "params": {"lens": "DRY"}},  # leak!
        ],
    }
    with pytest.raises(ValueError, match="cross-leakage"):
        _compute_per_lens_pass(fixture, [True, True])


def test_compute_per_lens_pass_length_mismatch_raises():
    from skills.temper.evals.run_evals import _compute_per_lens_pass
    fixture = {
        "id": "ex-len",
        "lens_column": "Surgical",
        "expectations": [{"check": "x", "params": {"lens": "Surgical"}}],
    }
    with pytest.raises(ValueError, match="length"):
        _compute_per_lens_pass(fixture, [True, True])


def test_compute_per_lens_pass_accepts_dict_outcomes():
    from skills.temper.evals.run_evals import _compute_per_lens_pass
    fixture = {
        "id": "ex-d",
        "lens_column": "SRP",
        "expectations": [
            {"check": "lens-finding-fires", "params": {"lens": "SRP"}},
            {"check": "all-findings-have-file-line"},
        ],
    }
    # dict keyed by expectation index
    assert _compute_per_lens_pass(fixture, {0: True, 1: True}) == {"SRP": True}


# ---------------------------------------------------------------------------
# Task 2 (#290 S1): empirical tolerance calibration baseline
# ---------------------------------------------------------------------------


def test_calibration_json_schema():
    """The committed calibration.json carries the required header keys."""
    import json
    from pathlib import Path

    cal_path = (
        Path(__file__).resolve().parent / "calibration.json"
    )
    cal = json.loads(cal_path.read_text(encoding="utf-8"))
    assert "per_lens_sigma_empirical" in cal
    assert "tolerance" in cal
    assert "baseline_runs" in cal and cal["baseline_runs"] >= 3
    assert set(cal["per_lens_sigma_empirical"].keys()) >= {
        "Surgical",
        "DRY",
        "SRP",
        "OCP",
    }
    # Clamping invariants
    assert 0.447 <= cal["tolerance"] <= 0.7
    assert cal["analytic_floor"] == 0.447
    assert cal["design_ceiling"] == 0.7


def test_write_calibration_placeholder_creates_when_missing(tmp_path, monkeypatch):
    """`_write_calibration_placeholder()` writes a placeholder when absent."""
    from skills.temper.evals import run_evals

    target = tmp_path / "calibration.json"
    monkeypatch.setattr(run_evals, "_CALIBRATION_PATH", target)
    assert not target.exists()
    wrote = run_evals._write_calibration_placeholder()
    assert wrote is True
    assert target.exists()
    payload = json.loads(target.read_text())
    assert payload["tolerance"] >= 0.447
    assert "Surgical" in payload["per_lens_sigma_empirical"]


def test_write_calibration_placeholder_noop_when_present(tmp_path, monkeypatch):
    """`_write_calibration_placeholder()` returns False if file already present."""
    from skills.temper.evals import run_evals

    target = tmp_path / "calibration.json"
    target.write_text('{"tolerance": 0.5}', encoding="utf-8")
    monkeypatch.setattr(run_evals, "_CALIBRATION_PATH", target)
    wrote = run_evals._write_calibration_placeholder()
    assert wrote is False
    # Pre-existing content untouched
    assert json.loads(target.read_text()) == {"tolerance": 0.5}


def test_calibrate_tolerance_script_clamps_to_floor(tmp_path):
    """`scripts/calibrate_tolerance.py` clamps t_emp < floor up to 0.447."""
    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / "scripts"))
    try:
        import calibrate_tolerance  # type: ignore[import-not-found]
    finally:
        _sys.path.pop(0)

    # Fabricate 3 minimal baseline last_run.json files with identical PASS rates
    # so sigma=0 across runs => t_emp=0 => floor binds at 0.447.
    fake_evals = tmp_path / "evals.json"
    fake_evals.write_text(json.dumps({
        "evals": [
            {"id": "x", "lens_column": "Surgical"},
        ]
    }), encoding="utf-8")
    inputs = []
    for i in range(3):
        p = tmp_path / f"run-{i}.json"
        p.write_text(json.dumps({
            "fixtures": [{
                "id": "x",
                "expectations": [
                    {"per_trial_verdicts": ["PASS", "PASS", "PASS"]},
                ],
            }],
        }), encoding="utf-8")
        inputs.append(p)
    artifact = calibrate_tolerance.calibrate(inputs, fake_evals)
    assert artifact["tolerance"] == 0.45  # round(0.447, 2) == 0.45
    assert artifact["floor_binding"] is True
    assert artifact["ceiling_binding"] is False
    assert set(artifact["per_lens_sigma_empirical"].keys()) == {
        "Surgical", "DRY", "SRP", "OCP",
    }


# ---------------------------------------------------------------------------
# Task 3 (#290 S1): drift-delta gate reads calibrated tolerance
# ---------------------------------------------------------------------------


def _drift_payload(fid: str, n_pass: int, n_total: int, verdict: str = "PASS") -> dict:
    """Build a fixture payload with controllable per-trial pass rate.

    `verdict` is the aggregated verdict (independent of per-trial counts so
    the swing-tolerance gate can be tested without tripping the
    PASS->FAIL/N/A regression branch).
    """
    verdicts = ["PASS"] * n_pass + ["FAIL"] * (n_total - n_pass)
    return {
        "id": fid,
        "verdict": verdict,
        "expectations": [{"per_trial_verdicts": verdicts}],
    }


def test_drift_gate_reads_calibration_tolerance(tmp_path, monkeypatch):
    """When delta > calibrated tolerance, _compare_baseline flags drift (rc=1)."""
    from skills.temper.evals import run_evals

    cal = tmp_path / "calibration.json"
    cal.write_text(json.dumps({"tolerance": 0.3}), encoding="utf-8")
    baseline_path = tmp_path / "baseline.json"
    baseline = {
        "template_sha": "abc",
        "fixtures": [_drift_payload("x", 5, 5)],  # base rate 1.0
    }
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

    monkeypatch.setattr(run_evals, "_CALIBRATION_PATH", cal)
    monkeypatch.setattr(run_evals, "_BASELINE_PATH", baseline_path)

    # keep verdict=PASS so regression branch does not preempt drift gate
    payload = {"fixtures": [_drift_payload("x", 2, 5, verdict="PASS")]}  # delta=0.6
    rc = run_evals._compare_baseline(
        payload,
        "abc",
        incomplete=False,
        evals_fixture_ids={"x"},
    )
    assert rc == 1


def test_drift_gate_within_tolerance_no_flag(tmp_path, monkeypatch):
    """When delta <= calibrated tolerance, no drift flag fires."""
    from skills.temper.evals import run_evals

    cal = tmp_path / "calibration.json"
    cal.write_text(json.dumps({"tolerance": 0.5}), encoding="utf-8")
    baseline_path = tmp_path / "baseline.json"
    baseline = {
        "template_sha": "abc",
        "fixtures": [_drift_payload("x", 5, 5)],
    }
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

    monkeypatch.setattr(run_evals, "_CALIBRATION_PATH", cal)
    monkeypatch.setattr(run_evals, "_BASELINE_PATH", baseline_path)

    payload = {"fixtures": [_drift_payload("x", 4, 5, verdict="PASS")]}  # delta=0.2
    rc = run_evals._compare_baseline(
        payload,
        "abc",
        incomplete=False,
        evals_fixture_ids={"x"},
    )
    assert rc == 0


def test_drift_gate_falls_back_to_analytic_floor_when_calibration_absent(
    tmp_path, monkeypatch
):
    """When calibration.json is absent, tolerance defaults to 0.447 floor."""
    from skills.temper.evals import run_evals

    missing_cal = tmp_path / "calibration.json"  # does not exist
    monkeypatch.setattr(run_evals, "_CALIBRATION_PATH", missing_cal)
    assert run_evals._drift_tolerance() == 0.447


def test_drift_tolerance_loader_handles_malformed_calibration(
    tmp_path, monkeypatch
):
    """Malformed calibration.json => analytic floor fallback (not crash)."""
    from skills.temper.evals import run_evals

    cal = tmp_path / "calibration.json"
    cal.write_text("not json{", encoding="utf-8")
    monkeypatch.setattr(run_evals, "_CALIBRATION_PATH", cal)
    assert run_evals._drift_tolerance() == 0.447


# ---------------------------------------------------------------------------
# Task 8 (#290 F2/S3): _validate_fixtures + FixtureValidationError gates (a)-(m)
# ---------------------------------------------------------------------------


def _minimal_fixture(**overrides) -> dict:
    """Build a minimal fixture passing all gates (a)-(k) for selective override."""
    base = {
        "id": "fx",
        "source": "synthetic",
        "lens_column": "Surgical",
        "pr_description": "Add a helper that wraps an existing utility.",
        "prompt": "Review the diff.\n\n```diff\n+x = 1\n```",
        "expected_output": "Some expected output rationale.",
        "files": ["src/x.py"],
        "allowed_files": ["src/x.py"],
        "lens_under_test": "surgical",
        "replicate_rule": {"trials": 5, "threshold": 3},
        "expectations": [],
    }
    base.update(overrides)
    return base


def test_validate_fixtures_evals_key_required():
    from skills.temper.evals.run_evals import (
        FixtureValidationError,
        _validate_fixtures,
    )
    with pytest.raises(FixtureValidationError, match="evals"):
        _validate_fixtures({"fixtures": []})
    with pytest.raises(FixtureValidationError, match="evals"):
        _validate_fixtures({})


def test_validate_fixtures_gate_a_missing_source():
    from skills.temper.evals.run_evals import (
        FixtureValidationError,
        _validate_fixtures,
    )
    fx = _minimal_fixture()
    fx.pop("source")
    with pytest.raises(FixtureValidationError, match="source"):
        _validate_fixtures({"evals": [fx]})


def test_validate_fixtures_gate_b_real_pr_malformed_source_pr():
    from skills.temper.evals.run_evals import (
        FixtureValidationError,
        _validate_fixtures,
    )
    fx = _minimal_fixture(source="real-pr", source_pr="not-a-pr-ref")
    with pytest.raises(FixtureValidationError, match="source_pr"):
        _validate_fixtures({"evals": [fx]})


def test_validate_fixtures_gate_b_real_pr_valid_sha():
    """`#123 @ deadbee` (7 hex) is accepted."""
    from skills.temper.evals.run_evals import _validate_fixtures
    fx = _minimal_fixture(
        id="real",
        source="real-pr",
        source_pr="#123 @ deadbee",
        synthetic_pair=None,
    )
    # No raise expected
    _validate_fixtures({"evals": [fx]})


def test_validate_fixtures_gate_c_synthetic_pair_unresolved():
    from skills.temper.evals.run_evals import (
        FixtureValidationError,
        _validate_fixtures,
    )
    fx = _minimal_fixture(
        id="real",
        source="real-pr",
        source_pr="#1 @ abcdef0",
        synthetic_pair="ghost-id",
    )
    with pytest.raises(FixtureValidationError, match="synthetic_pair"):
        _validate_fixtures({"evals": [fx]})


def test_validate_fixtures_gate_c_pair_lens_column_mismatch():
    from skills.temper.evals.run_evals import (
        FixtureValidationError,
        _validate_fixtures,
    )
    twin = _minimal_fixture(id="twin", lens_column="DRY")
    fx = _minimal_fixture(
        id="real",
        source="real-pr",
        source_pr="#1 @ abcdef0",
        synthetic_pair="twin",
        lens_column="Surgical",  # mismatch with twin's DRY
    )
    with pytest.raises(FixtureValidationError, match="lens_column"):
        _validate_fixtures({"evals": [twin, fx]})


def test_validate_fixtures_gate_d_empty_pr_description():
    from skills.temper.evals.run_evals import (
        FixtureValidationError,
        _validate_fixtures,
    )
    fx = _minimal_fixture(pr_description="")
    with pytest.raises(FixtureValidationError, match="pr_description"):
        _validate_fixtures({"evals": [fx]})


def test_validate_fixtures_gate_e_bad_lens_column():
    from skills.temper.evals.run_evals import (
        FixtureValidationError,
        _validate_fixtures,
    )
    fx = _minimal_fixture(lens_column="Surigcal")
    with pytest.raises(FixtureValidationError):
        _validate_fixtures({"evals": [fx]})


def test_validate_fixtures_gate_f_lens_line_pr_description_fatal():
    from skills.temper.evals.run_evals import (
        FixtureValidationError,
        _validate_fixtures,
    )
    fx = _minimal_fixture(pr_description="Some text\nLens: Surgical\nmore")
    with pytest.raises(FixtureValidationError, match="Lens"):
        _validate_fixtures({"evals": [fx]})


def test_validate_fixtures_gate_g_lens_line_in_prompt_warns_not_fatal(capsys):
    from skills.temper.evals.run_evals import _validate_fixtures
    # `^\s*Lens:` regex requires line-start (or whitespace) before `Lens:`.
    fx = _minimal_fixture(
        prompt="Review diff.\nLens: SRP\nLong enough." + "x" * 200,
    )
    _validate_fixtures({"evals": [fx]})  # warning only — no raise
    err = capsys.readouterr().err
    assert "Lens" in err or "lens" in err


def test_validate_fixtures_gate_i_trials_uniformity():
    from skills.temper.evals.run_evals import (
        FixtureValidationError,
        _validate_fixtures,
    )
    fx = _minimal_fixture(replicate_rule={"trials": 3, "threshold": 2})
    with pytest.raises(FixtureValidationError, match="trials"):
        _validate_fixtures({"evals": [fx]})


def test_validate_fixtures_gate_i_none_lens_column_waived():
    """`lens_column='none'` bypasses gate (i)'s trials-uniformity check."""
    from skills.temper.evals.run_evals import _validate_fixtures
    fx = _minimal_fixture(
        lens_column="none",
        replicate_rule={"trials": 3, "threshold": 2},
    )
    _validate_fixtures({"evals": [fx]})  # no raise


def test_validate_fixtures_gate_j_strict_flag_off_does_not_call_git():
    """When --strict-source-pr is OFF, validator does not probe git."""
    from unittest.mock import patch
    from skills.temper.evals.run_evals import _validate_fixtures
    fx = _minimal_fixture(
        id="real",
        source="real-pr",
        source_pr="#1 @ deadbee",
    )
    with patch("subprocess.run") as mrun:
        _validate_fixtures({"evals": [fx]}, strict_source_pr=False)
        for call in mrun.call_args_list:
            args0 = call.args[0] if call.args else []
            if isinstance(args0, list) and args0 and args0[0] == "git":
                assert args0[1] not in ("rev-parse", "cat-file")


def test_validate_fixtures_gate_j_strict_flag_on_missing_sha_fails(monkeypatch):
    from unittest.mock import MagicMock
    from skills.temper.evals.run_evals import (
        FixtureValidationError,
        _validate_fixtures,
    )
    fx = _minimal_fixture(
        id="real",
        source="real-pr",
        source_pr="#1 @ deadbee",
    )

    call_log = []

    def fake_run(args, **kwargs):
        call_log.append(args)
        m = MagicMock()
        if "rev-parse" in args:
            m.returncode = 0
            m.stderr = ""
        else:
            # cat-file: simulate missing SHA
            m.returncode = 1
            m.stderr = "fatal: not a tree object"
        return m

    monkeypatch.setattr("subprocess.run", fake_run)
    with pytest.raises(FixtureValidationError, match="sha"):
        _validate_fixtures({"evals": [fx]}, strict_source_pr=True)


def test_validate_fixtures_gate_k_mixed_fixture_cap():
    from skills.temper.evals.run_evals import (
        FixtureValidationError,
        _validate_fixtures,
    )
    a = _minimal_fixture(
        id="a",
        source="real-pr",
        source_pr="#1 @ abcdef0",
        lens_column=["Surgical", "DRY"],
    )
    b = _minimal_fixture(
        id="b",
        source="real-pr",
        source_pr="#2 @ abcdef0",
        lens_column=["SRP", "OCP"],
    )
    with pytest.raises(FixtureValidationError, match="lens_column"):
        _validate_fixtures({"evals": [a, b]})


def test_validate_fixtures_gap_documented_waives_prompt():
    """gap_documented=True bypasses empty-prompt + empty-pr_description gates."""
    from skills.temper.evals.run_evals import _validate_fixtures
    fx = _minimal_fixture(
        prompt="",
        pr_description="",
        gap_documented=True,
    )
    _validate_fixtures({"evals": [fx]})  # no raise


def test_baseline_quality_error_is_subclass_of_fixture_validation_error():
    """BaselineQualityError preserves rc=2 propagation via FixtureValidationError."""
    from skills.temper.evals.run_evals import (
        BaselineQualityError,
        FixtureValidationError,
    )
    assert issubclass(BaselineQualityError, FixtureValidationError)


def test_strict_source_pr_flag_wired_on_stage_argparser():
    """`stage --strict-source-pr` is accepted by argparse."""
    from skills.temper.evals.run_evals import _parse_args
    ns = _parse_args(["stage", "R-x", "--strict-source-pr"])
    assert ns.cmd == "stage"
    assert ns.strict_source_pr is True


def test_trials_override_flag_wired_on_stage_argparser():
    """`stage --trials-override 10` is accepted by argparse."""
    from skills.temper.evals.run_evals import _parse_args
    ns = _parse_args(["stage", "R-x", "--trials-override", "10"])
    assert ns.cmd == "stage"
    assert ns.trials_override == 10


def test_validate_fixtures_live_evals_json_passes():
    """The committed evals.json passes the validator without warnings."""
    from skills.temper.evals.run_evals import _validate_fixtures, _EVALS_JSON
    data = json.loads(_EVALS_JSON.read_text(encoding="utf-8"))
    _validate_fixtures(data)  # no raise


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
