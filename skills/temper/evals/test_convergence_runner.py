"""TDD test suite for convergence_runner.py convergence checks (#333).

These tests drive the fix-verification convergence model: the tracked-set T
lifecycle, the four terminal verdicts + two continuation outcomes, the discharge
paths, once-only defer, and the §3.5 branch table (one test per branch).

Synthetic multi-round transcript strings drive PASS/FAIL pairs for each check.
"""

from __future__ import annotations

import pytest

from skills.temper.evals.convergence_runner import (
    _is_gating,
    _parse_findings,
    aggregate_replicates,
    all_findings_have_file_line,
    defer_once_only,
    evaluate_expectation,
    finding_body_contains,
    finding_body_does_not_contain,
    findings_count_at_least,
    member_discharged_refuted_after_fix,
    member_downgraded,
    member_enters_T,
    member_escalated,
    member_resolved,
    new_admit_round_not_clean,
    report_has_block,
    stagnation_subordinate_to_escalation,
    verdict_is,
)


# ---------------------------------------------------------------------------
# Transcript fixtures
# ---------------------------------------------------------------------------

CLEAN_AFTER_RESOLVE = """
### Pre-flight
- substantive diff.

### Round 1
- Round-Verdict: Issues-Found

1. row.tier read with no migration guard
   - File: src/handler.py:88
   - Summary: row.tier read with no migration guard
   - Severity: Important
   - Verdict: CONFIRMED
   - Admitted: 1
   - Readjudicated: false

### Round 2
- Round-Verdict: Clean

1. row.tier read with no migration guard
   - File: src/handler.py:88
   - Summary: row.tier read with no migration guard
   - Severity: Important
   - Verdict: CONFIRMED
   - Admitted: 1
   - Outcome: RESOLVED
   - Readjudicated: true

### Verdict
- Final-Verdict: Clean
"""

REFUTED_AFTER_FIX = """
### Round 1
- Round-Verdict: Issues-Found

1. possible race
   - File: src/counter.py:22
   - Summary: possible race
   - Severity: Critical
   - Verdict: PLAUSIBLE
   - Admitted: 1
   - Readjudicated: false

### Round 2
- Round-Verdict: Clean

1. possible race
   - File: src/counter.py:22
   - Summary: possible race
   - Severity: Critical
   - Verdict: REFUTED
   - Admitted: 1
   - Outcome: REFUTED-after-fix
   - Readjudicated: true

### Verdict
- Final-Verdict: Clean
"""

DOWNGRADE = """
### Round 1
- Round-Verdict: Issues-Found

1. path leak
   - File: src/log.py:14
   - Summary: path leak
   - Severity: Important
   - Verdict: CONFIRMED
   - Admitted: 1
   - Readjudicated: false

### Round 2
- Round-Verdict: Clean

1. path leak
   - File: src/log.py:14
   - Summary: path leak
   - Severity: Minor
   - Verdict: CONFIRMED
   - Admitted: 1
   - Outcome: DOWNGRADED
   - Readjudicated: true

### Verdict
- Final-Verdict: Clean
"""

# §3.5 row 1: SOLELY escalation-eligible -> Architectural (deferred at R2 first).
ARCHITECTURAL = """
### Round 1
- Round-Verdict: Issues-Found

1. ordering hazard
   - File: src/cache.py:60
   - Summary: ordering hazard
   - Severity: Critical
   - Verdict: PLAUSIBLE
   - Admitted: 1
   - Readjudicated: false

### Round 2
- Round-Verdict: Defer-one-round

1. ordering hazard
   - File: src/cache.py:60
   - Summary: ordering hazard
   - Severity: Critical
   - Verdict: PLAUSIBLE
   - Admitted: 1
   - Outcome: STILL-GATING
   - Readjudicated: false

### Round 3
- Round-Verdict: Architectural

1. ordering hazard
   - File: src/cache.py:60
   - Summary: ordering hazard
   - Severity: Critical
   - Verdict: PLAUSIBLE
   - Admitted: 1
   - Outcome: ESCALATE
   - Readjudicated: true

### Verdict
- Final-Verdict: Architectural
"""

# §3.5 row 2: SOLELY not-yet-re-adjudicated -> Defer-one-round.
DEFER_SOLELY = """
### Round 1
- Round-Verdict: Issues-Found

1. off-by-one
   - File: src/window.py:12
   - Summary: off-by-one
   - Severity: Important
   - Verdict: CONFIRMED
   - Admitted: 1
   - Readjudicated: false

### Round 2
- Round-Verdict: Defer-one-round

1. off-by-one
   - File: src/window.py:12
   - Summary: off-by-one
   - Severity: Important
   - Verdict: CONFIRMED
   - Admitted: 1
   - Outcome: STILL-GATING
   - Readjudicated: false

### Verdict
- Final-Verdict: Defer-one-round
"""

# §3.5 row 3: MIXED escalation-eligible + not-yet-re-adjudicated, no genuinely-stuck.
DEFER_MIXED = """
### Round 1
- Round-Verdict: Issues-Found

1. lost wakeup
   - File: src/queue.py:48
   - Summary: lost wakeup
   - Severity: Critical
   - Verdict: PLAUSIBLE
   - Admitted: 1
   - Readjudicated: false

2. missing length check
   - File: src/queue.py:71
   - Summary: missing length check
   - Severity: Important
   - Verdict: CONFIRMED
   - Admitted: 1
   - Readjudicated: false

### Round 2
- Round-Verdict: Defer-one-round

1. lost wakeup
   - File: src/queue.py:48
   - Summary: lost wakeup
   - Severity: Critical
   - Verdict: PLAUSIBLE
   - Admitted: 1
   - Outcome: ESCALATE
   - Readjudicated: true

2. missing length check
   - File: src/queue.py:71
   - Summary: missing length check
   - Severity: Important
   - Verdict: CONFIRMED
   - Admitted: 1
   - Outcome: STILL-GATING
   - Readjudicated: false

### Verdict
- Final-Verdict: Defer-one-round
"""

# §3.5 row 4: genuinely-stuck -> Stagnation; R+2 earliest fire after once-only defer.
STAGNATION = """
### Round 1
- Round-Verdict: Issues-Found

1. overflow
   - File: src/sizer.py:33
   - Summary: overflow
   - Severity: Critical
   - Verdict: CONFIRMED
   - Admitted: 1
   - Readjudicated: false

### Round 2
- Round-Verdict: Defer-one-round

1. overflow
   - File: src/sizer.py:33
   - Summary: overflow
   - Severity: Critical
   - Verdict: CONFIRMED
   - Admitted: 1
   - Outcome: STILL-GATING
   - Readjudicated: false

### Round 3
- Round-Verdict: Issues-Found

1. overflow
   - File: src/sizer.py:33
   - Summary: overflow
   - Severity: Critical
   - Verdict: CONFIRMED
   - Admitted: 1
   - Outcome: STILL-GATING
   - Readjudicated: true

### Round 4
- Round-Verdict: Stagnation

1. overflow
   - File: src/sizer.py:33
   - Summary: overflow
   - Severity: Critical
   - Verdict: CONFIRMED
   - Admitted: 1
   - Outcome: STILL-GATING
   - Readjudicated: true

### Verdict
- Final-Verdict: Stagnation
"""

ISSUES_FOUND_NEW_ADMIT = """
### Round 1
- Round-Verdict: Issues-Found

1. retry loop
   - File: src/client.py:40
   - Summary: retry loop
   - Severity: Critical
   - Verdict: CONFIRMED
   - Admitted: 1
   - Readjudicated: false

### Round 2
- Round-Verdict: Issues-Found

1. retry loop
   - File: src/client.py:40
   - Summary: retry loop
   - Severity: Critical
   - Verdict: CONFIRMED
   - Admitted: 1
   - Outcome: RESOLVED
   - Readjudicated: true

2. dropped timeout
   - File: src/client.py:55
   - Summary: dropped timeout
   - Severity: Important
   - Verdict: CONFIRMED
   - Admitted: 2
   - Readjudicated: false

### Verdict
- Final-Verdict: Issues-Found
"""

ADMISSION_GATE = """
### Round 1
- Round-Verdict: Issues-Found

1. null-deref
   - File: src/io.py:12
   - Summary: null-deref
   - Severity: Critical
   - Verdict: CONFIRMED
   - Admitted: 1
   - Readjudicated: false

2. naming nit
   - File: src/io.py:40
   - Summary: naming nit
   - Severity: Minor
   - Verdict: CONFIRMED
   - Admitted: 1
   - Readjudicated: false

3. false positive
   - File: src/io.py:55
   - Summary: false positive
   - Severity: Important
   - Verdict: REFUTED
   - Admitted: 1
   - Readjudicated: false

### Verdict
- Final-Verdict: Issues-Found
"""

NO_MEMBERS = """
### Round 1
- Round-Verdict: Clean

### Verdict
- Final-Verdict: Clean
"""


# ---------------------------------------------------------------------------
# Parser + gating 2x2
# ---------------------------------------------------------------------------


def test_gating_2x2():
    assert _is_gating("Critical", "CONFIRMED")
    assert _is_gating("Important", "PLAUSIBLE")
    assert not _is_gating("Minor", "CONFIRMED")       # below C/I
    assert not _is_gating("Critical", "REFUTED")      # not a gating verdict
    assert not _is_gating(None, None)


def test_parse_findings_extracts_member_fields():
    members = _parse_findings(CLEAN_AFTER_RESOLVE)
    assert len(members) == 2
    r1 = members[0]
    assert r1["file"] == "src/handler.py"
    assert r1["line"] == 88
    assert r1["severity"] == "Important"
    assert r1["verdict"] == "CONFIRMED"
    assert r1["round"] == 1
    assert r1["admitted"] == 1
    assert r1["readjudicated"] is False
    r2 = members[1]
    assert r2["round"] == 2
    assert r2["outcome"] == "RESOLVED"
    assert r2["readjudicated"] is True


def test_parse_findings_skips_report_prose_blocks():
    members = _parse_findings(CLEAN_AFTER_RESOLVE)
    assert all(m["section"] != "Pre-flight" for m in members)


# ---------------------------------------------------------------------------
# member-enters-T (verdict×severity gating 2×2 admission gate)
# ---------------------------------------------------------------------------


def test_member_enters_T_pass():
    v, _ = member_enters_T(
        CLEAN_AFTER_RESOLVE, "src/handler.py", "Important", "CONFIRMED", round=1
    )
    assert v == "PASS"


def test_member_enters_T_below_ci_excluded():
    v, why = member_enters_T(ADMISSION_GATE, "src/io.py", "Minor", "CONFIRMED",
                             round=1, summary="naming nit")
    assert v == "FAIL"
    assert "gating 2" in why or "NOT in the gating" in why


def test_member_enters_T_refuted_excluded():
    v, _ = member_enters_T(ADMISSION_GATE, "src/io.py", "Important", "REFUTED",
                           round=1, summary="false positive")
    assert v == "FAIL"


def test_member_enters_T_critical_confirmed_admitted():
    v, _ = member_enters_T(ADMISSION_GATE, "src/io.py", "Critical", "CONFIRMED",
                           round=1, summary="null-deref")
    assert v == "PASS"


# ---------------------------------------------------------------------------
# member-resolved / discharge paths
# ---------------------------------------------------------------------------


def test_member_resolved_pass():
    v, _ = member_resolved(CLEAN_AFTER_RESOLVE, "src/handler.py", round=2)
    assert v == "PASS"


def test_member_resolved_fail_when_still_gating():
    v, _ = member_resolved(STAGNATION, "src/sizer.py", round=4)
    assert v == "FAIL"


def test_member_discharged_refuted_after_fix_pass():
    v, _ = member_discharged_refuted_after_fix(REFUTED_AFTER_FIX, "src/counter.py", round=2)
    assert v == "PASS"


def test_member_discharged_refuted_after_fix_fail_on_resolved():
    v, _ = member_discharged_refuted_after_fix(CLEAN_AFTER_RESOLVE, "src/handler.py", round=2)
    assert v == "FAIL"


def test_member_downgraded_pass():
    v, _ = member_downgraded(DOWNGRADE, "src/log.py", round=2)
    assert v == "PASS"


def test_member_escalated_pass():
    v, _ = member_escalated(ARCHITECTURAL, "src/cache.py", round=3)
    assert v == "PASS"


def test_member_escalated_fail_when_resolved():
    v, _ = member_escalated(CLEAN_AFTER_RESOLVE, "src/handler.py", round=2)
    assert v == "FAIL"


# ---------------------------------------------------------------------------
# verdict-is (four terminal + two continuation)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "txt,verdict",
    [
        (CLEAN_AFTER_RESOLVE, "Clean"),
        (STAGNATION, "Stagnation"),
        (ARCHITECTURAL, "Architectural"),
        (ISSUES_FOUND_NEW_ADMIT, "Issues-Found"),
        (DEFER_SOLELY, "Defer-one-round"),
    ],
)
def test_verdict_is_final(txt, verdict):
    v, _ = verdict_is(txt, verdict)
    assert v == "PASS"


def test_verdict_is_round_scoped():
    v, _ = verdict_is(STAGNATION, "Stagnation", round=4)
    assert v == "PASS"
    v, _ = verdict_is(STAGNATION, "Defer-one-round", round=2)
    assert v == "PASS"


def test_verdict_is_wrong_verdict_fails():
    v, _ = verdict_is(CLEAN_AFTER_RESOLVE, "Stagnation")
    assert v == "FAIL"


def test_verdict_is_unknown_verdict_name_fails():
    v, why = verdict_is(CLEAN_AFTER_RESOLVE, "Bogus")
    assert v == "FAIL"
    assert "not a known verdict" in why


# ---------------------------------------------------------------------------
# new-admit-round-never-Clean
# ---------------------------------------------------------------------------


def test_new_admit_round_not_clean_pass():
    v, _ = new_admit_round_not_clean(ISSUES_FOUND_NEW_ADMIT, round=2)
    assert v == "PASS"


def test_new_admit_round_not_clean_na_when_no_new_member():
    v, _ = new_admit_round_not_clean(CLEAN_AFTER_RESOLVE, round=2)
    assert v == "N/A"


def test_new_admit_round_not_clean_fail_if_clean_with_new_admit():
    bad = ISSUES_FOUND_NEW_ADMIT.replace(
        "### Round 2\n- Round-Verdict: Issues-Found",
        "### Round 2\n- Round-Verdict: Clean",
    )
    v, why = new_admit_round_not_clean(bad, round=2)
    assert v == "FAIL"
    assert "Clean" in why


# ---------------------------------------------------------------------------
# §3.5 branch table — one test per branch
# ---------------------------------------------------------------------------


def test_branch_solely_escalation_to_architectural():
    v, _ = stagnation_subordinate_to_escalation(ARCHITECTURAL, round=3)
    assert v == "PASS"
    v2, _ = verdict_is(ARCHITECTURAL, "Architectural")
    assert v2 == "PASS"


def test_branch_solely_not_readjudicated_to_defer():
    v, _ = verdict_is(DEFER_SOLELY, "Defer-one-round", round=2)
    assert v == "PASS"


def test_branch_mixed_to_defer():
    v, _ = verdict_is(DEFER_MIXED, "Defer-one-round", round=2)
    assert v == "PASS"
    sub, _ = stagnation_subordinate_to_escalation(DEFER_MIXED, round=2)
    assert sub == "N/A"


def test_branch_genuinely_stuck_to_stagnation():
    v, _ = verdict_is(STAGNATION, "Stagnation", round=4)
    assert v == "PASS"


def test_solely_escalation_requires_readjudicated_true():
    # A subset that is solely ESCALATE but NOT yet readjudicated (readjudicated
    # == false) is NOT escalation-eligible (§3.5: escalation-eligible only after
    # the re-verification pass). It must NOT satisfy the SOLELY-escalation ->
    # Architectural row — the check is N/A, not a PASS/FAIL on that row.
    not_yet = ARCHITECTURAL.replace(
        "   - Outcome: ESCALATE\n   - Readjudicated: true",
        "   - Outcome: ESCALATE\n   - Readjudicated: false",
    )
    v, _ = stagnation_subordinate_to_escalation(not_yet, round=3)
    assert v == "N/A"


def test_stagnation_subordinate_fails_if_escalation_subset_mislabeled():
    bad = ARCHITECTURAL.replace(
        "### Round 3\n- Round-Verdict: Architectural",
        "### Round 3\n- Round-Verdict: Stagnation",
    )
    v, why = stagnation_subordinate_to_escalation(bad, round=3)
    assert v == "FAIL"
    assert "Architectural" in why


# ---------------------------------------------------------------------------
# defer-once-only
# ---------------------------------------------------------------------------


def test_defer_once_only_pass():
    v, _ = defer_once_only(STAGNATION, "src/sizer.py")
    assert v == "PASS"


def test_defer_once_only_pass_architectural():
    v, _ = defer_once_only(ARCHITECTURAL, "src/cache.py")
    assert v == "PASS"


def test_defer_once_only_fail_on_double_defer():
    double = """
### Round 1
- Round-Verdict: Issues-Found

1. m
   - File: src/x.py:1
   - Summary: m
   - Severity: Important
   - Verdict: CONFIRMED
   - Admitted: 1
   - Readjudicated: false

### Round 2
- Round-Verdict: Defer-one-round

1. m
   - File: src/x.py:1
   - Summary: m
   - Severity: Important
   - Verdict: CONFIRMED
   - Admitted: 1
   - Outcome: STILL-GATING
   - Readjudicated: false

### Round 3
- Round-Verdict: Defer-one-round

1. m
   - File: src/x.py:1
   - Summary: m
   - Severity: Important
   - Verdict: CONFIRMED
   - Admitted: 1
   - Outcome: STILL-GATING
   - Readjudicated: false

### Verdict
- Final-Verdict: Defer-one-round
"""
    v, why = defer_once_only(double, "src/x.py")
    assert v == "FAIL"
    assert "once-only" in why


def test_defer_once_only_pass_carry_through_readjudicated_true():
    # CORRECTED SEMANTICS (replaces the old fail_on_redefer_of_readjudicated test,
    # which encoded the now-known-WRONG model). A member deferred-FOR once in R2
    # (readjudicated==false), then appearing in a SECOND Defer round R3 with
    # readjudicated==TRUE, is CARRIED-THROUGH in R3, NOT deferred-for again
    # (deferring SETS the flag; an already-set member does not defer again, §3.5).
    # R3 deferred because of a *different* not-yet-readjudicated sibling. The
    # member is deferred-for in exactly ONE round -> PASS (no once-only violation).
    carry_through = """
### Round 1
- Round-Verdict: Issues-Found

1. m
   - File: src/x.py:1
   - Summary: m
   - Severity: Important
   - Verdict: CONFIRMED
   - Admitted: 1
   - Readjudicated: false

2. sibling
   - File: src/x.py:9
   - Summary: sibling
   - Severity: Important
   - Verdict: CONFIRMED
   - Admitted: 1
   - Readjudicated: false

### Round 2
- Round-Verdict: Defer-one-round

1. m
   - File: src/x.py:1
   - Summary: m
   - Severity: Important
   - Verdict: CONFIRMED
   - Admitted: 1
   - Outcome: STILL-GATING
   - Readjudicated: false

2. sibling
   - File: src/x.py:9
   - Summary: sibling
   - Severity: Important
   - Verdict: CONFIRMED
   - Admitted: 1
   - Outcome: STILL-GATING
   - Readjudicated: true

### Round 3
- Round-Verdict: Defer-one-round

1. m
   - File: src/x.py:1
   - Summary: m
   - Severity: Important
   - Verdict: CONFIRMED
   - Admitted: 1
   - Outcome: STILL-GATING
   - Readjudicated: true

2. sibling
   - File: src/x.py:9
   - Summary: sibling
   - Severity: Important
   - Verdict: CONFIRMED
   - Admitted: 1
   - Outcome: STILL-GATING
   - Readjudicated: false

### Verdict
- Final-Verdict: Defer-one-round
"""
    # `m` is deferred-for in R2 only (readjudicated==false); in R3 it is
    # carried-through (readjudicated==true) -> not deferred-for again -> PASS.
    v, why = defer_once_only(carry_through, "src/x.py", "m")
    assert v == "PASS", why


# ---------------------------------------------------------------------------
# defer-once-only: FOUR boundary tests locking all sides (#333)
#
#   #1 legal single defer-for          -> PASS
#   #2 legal MIXED carry-through       -> PASS
#   #3 illegal deferred-for-twice      -> FAIL
#   #4 drift-immune deferred-for-twice -> FAIL (line/verdict differ between rounds)
#
# #3 and #4 are verified to FAIL against a wrong implementation and PASS only
# against the correct deferred-for + stable-key model.
# ---------------------------------------------------------------------------


def test_defer_once_only_boundary1_legal_single_defer_for_passes():
    # #1: a member deferred-FOR in EXACTLY ONE Defer-one-round round -> PASS.
    single = """
### Round 1
- Round-Verdict: Issues-Found

1. solo
   - File: src/s.py:5
   - Summary: solo
   - Severity: Critical
   - Verdict: CONFIRMED
   - Admitted: 1
   - Readjudicated: false

### Round 2
- Round-Verdict: Defer-one-round

1. solo
   - File: src/s.py:5
   - Summary: solo
   - Severity: Critical
   - Verdict: CONFIRMED
   - Admitted: 1
   - Outcome: STILL-GATING
   - Readjudicated: false

### Round 3
- Round-Verdict: Issues-Found

1. solo
   - File: src/s.py:5
   - Summary: solo
   - Severity: Critical
   - Verdict: CONFIRMED
   - Admitted: 1
   - Outcome: STILL-GATING
   - Readjudicated: true

### Verdict
- Final-Verdict: Issues-Found
"""
    v, why = defer_once_only(single, "src/s.py")
    assert v == "PASS", why


def test_defer_once_only_boundary2_legal_mixed_carry_through_passes():
    # #2: a Defer-one-round round defers because of a readjudicated==false sibling;
    # a readjudicated==true ESCALATE member is carried through that Defer round
    # (and a later one) but is NEVER deferred-for -> PASS.
    mixed = """
### Round 1
- Round-Verdict: Issues-Found

1. escalator
   - File: src/q.py:48
   - Summary: escalator
   - Severity: Critical
   - Verdict: PLAUSIBLE
   - Admitted: 1
   - Readjudicated: false

2. laggard
   - File: src/q.py:71
   - Summary: laggard
   - Severity: Important
   - Verdict: CONFIRMED
   - Admitted: 1
   - Readjudicated: false

### Round 2
- Round-Verdict: Defer-one-round

1. escalator
   - File: src/q.py:48
   - Summary: escalator
   - Severity: Critical
   - Verdict: PLAUSIBLE
   - Admitted: 1
   - Outcome: ESCALATE
   - Readjudicated: true

2. laggard
   - File: src/q.py:71
   - Summary: laggard
   - Severity: Important
   - Verdict: CONFIRMED
   - Admitted: 1
   - Outcome: STILL-GATING
   - Readjudicated: false

### Verdict
- Final-Verdict: Defer-one-round
"""
    # The readjudicated==true escalation-eligible member is carried-through, never
    # deferred-for -> PASS.
    v, why = defer_once_only(mixed, "src/q.py", "escalator")
    assert v == "PASS", why
    # And the whole file passes too (laggard deferred-for once, escalator never).
    v2, why2 = defer_once_only(mixed, "src/q.py")
    assert v2 == "PASS", why2


def test_defer_once_only_boundary3_illegal_deferred_for_twice_fails():
    # #3: the SAME member is deferred-FOR (readjudicated==false trigger) in TWO
    # distinct Defer-one-round rounds -> FAIL. Verified to FAIL against current
    # impl and PASS-the-assertion after the fix.
    double = """
### Round 1
- Round-Verdict: Issues-Found

1. m
   - File: src/x.py:1
   - Summary: m
   - Severity: Important
   - Verdict: CONFIRMED
   - Admitted: 1
   - Readjudicated: false

### Round 2
- Round-Verdict: Defer-one-round

1. m
   - File: src/x.py:1
   - Summary: m
   - Severity: Important
   - Verdict: CONFIRMED
   - Admitted: 1
   - Outcome: STILL-GATING
   - Readjudicated: false

### Round 3
- Round-Verdict: Defer-one-round

1. m
   - File: src/x.py:1
   - Summary: m
   - Severity: Important
   - Verdict: CONFIRMED
   - Admitted: 1
   - Outcome: STILL-GATING
   - Readjudicated: false

### Verdict
- Final-Verdict: Defer-one-round
"""
    v, why = defer_once_only(double, "src/x.py")
    assert v == "FAIL", why
    assert "once-only-defer" in why


def test_defer_once_only_boundary4_drift_immune_deferred_for_twice_fails():
    # #4 (the look-harder regression, LOCKED): same as #3 — the SAME member
    # deferred-for in TWO Defer rounds — but its reported `line` AND `verdict`
    # DIFFER between the two defer rounds (line drifted as code was edited above
    # it; verdict re-derived). Keying once-only on the volatile 5-field identity
    # would split these into two keys and FALSE-PASS. The stable sub-key
    # {file, summary, severity} keeps them fused -> must still FAIL.
    drift = """
### Round 1
- Round-Verdict: Issues-Found

1. m
   - File: src/x.py:1
   - Summary: m
   - Severity: Important
   - Verdict: PLAUSIBLE
   - Admitted: 1
   - Readjudicated: false

### Round 2
- Round-Verdict: Defer-one-round

1. m
   - File: src/x.py:1
   - Summary: m
   - Severity: Important
   - Verdict: PLAUSIBLE
   - Admitted: 1
   - Outcome: STILL-GATING
   - Readjudicated: false

### Round 3
- Round-Verdict: Defer-one-round

1. m
   - File: src/x.py:42
   - Summary: m
   - Severity: Important
   - Verdict: CONFIRMED
   - Admitted: 1
   - Outcome: STILL-GATING
   - Readjudicated: false

### Verdict
- Final-Verdict: Defer-one-round
"""
    # line 1->42 and verdict PLAUSIBLE->CONFIRMED both drift across the two defer
    # rounds; the stable {file, summary, severity} key must still catch the
    # double-defer.
    v, why = defer_once_only(drift, "src/x.py")
    assert v == "FAIL", why
    assert "once-only-defer" in why


def test_defer_once_only_pass_single_defer_escalation_in_mixed():
    # LEGAL boundary (§3.5 branch table, row 3, MIXED): a round resolves to
    # Defer-one-round because of a NOT-YET-readjudicated sibling. An
    # escalation-eligible member (ESCALATE, readjudicated==true) is carried
    # through that SAME single Defer round — deferred only ONCE, not re-deferred.
    # The over-firing prior fix false-FAILed this on the readjudicated==true
    # trigger; the correct once-only discriminator (a member in ≥2 Defer rounds)
    # must return PASS.
    mixed = """
### Round 1
- Round-Verdict: Issues-Found

1. lost wakeup
   - File: src/queue.py:48
   - Summary: lost wakeup
   - Severity: Critical
   - Verdict: PLAUSIBLE
   - Admitted: 1
   - Readjudicated: false

2. missing length check
   - File: src/queue.py:71
   - Summary: missing length check
   - Severity: Important
   - Verdict: CONFIRMED
   - Admitted: 1
   - Readjudicated: false

### Round 2
- Round-Verdict: Defer-one-round

1. lost wakeup
   - File: src/queue.py:48
   - Summary: lost wakeup
   - Severity: Critical
   - Verdict: PLAUSIBLE
   - Admitted: 1
   - Outcome: ESCALATE
   - Readjudicated: true

2. missing length check
   - File: src/queue.py:71
   - Summary: missing length check
   - Severity: Important
   - Verdict: CONFIRMED
   - Admitted: 1
   - Outcome: STILL-GATING
   - Readjudicated: false

### Verdict
- Final-Verdict: Defer-one-round
"""
    # The escalation-eligible member (selected by summary), carried through ONE
    # Defer round only.
    v, why = defer_once_only(mixed, "src/queue.py", "lost wakeup")
    assert v == "PASS", why
    # And the whole file (both members deferred once) must also PASS.
    v2, why2 = defer_once_only(mixed, "src/queue.py")
    assert v2 == "PASS", why2


# ---------------------------------------------------------------------------
# Discharge hard-rule: a repro-less PLAUSIBLE@C/I is NOT discharged on prose
# ---------------------------------------------------------------------------


def test_plausible_not_discharged_on_prose():
    txt = ARCHITECTURAL  # round 2 outcome STILL-GATING
    assert member_resolved(txt, "src/cache.py", round=2)[0] == "FAIL"
    assert member_discharged_refuted_after_fix(txt, "src/cache.py", round=2)[0] == "FAIL"
    assert member_downgraded(txt, "src/cache.py", round=2)[0] == "FAIL"


# ---------------------------------------------------------------------------
# Generic / reused checks
# ---------------------------------------------------------------------------


def test_all_findings_have_file_line():
    v, _ = all_findings_have_file_line(CLEAN_AFTER_RESOLVE)
    assert v == "PASS"


def test_all_findings_have_file_line_na_when_no_findings():
    v, _ = all_findings_have_file_line(NO_MEMBERS)
    assert v == "N/A"


def test_findings_count_at_least():
    assert findings_count_at_least(CLEAN_AFTER_RESOLVE, 2)[0] == "PASS"
    assert findings_count_at_least(CLEAN_AFTER_RESOLVE, 5)[0] == "FAIL"


def test_finding_body_contains():
    assert finding_body_contains(CLEAN_AFTER_RESOLVE, "migration")[0] == "PASS"
    assert finding_body_contains(CLEAN_AFTER_RESOLVE, "no-such-text")[0] == "FAIL"


def test_finding_body_does_not_contain():
    assert finding_body_does_not_contain(CLEAN_AFTER_RESOLVE, ["zzz"])[0] == "PASS"
    assert finding_body_does_not_contain(CLEAN_AFTER_RESOLVE, ["migration"])[0] == "FAIL"


def test_report_has_block_preflight():
    assert report_has_block(CLEAN_AFTER_RESOLVE, "Pre-flight")[0] == "PASS"
    assert report_has_block(REFUTED_AFTER_FIX, "Pre-flight")[0] == "FAIL"


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def test_evaluate_expectation_dispatch_member_enters_t():
    exp = {
        "type": "mechanical",
        "check": "member-enters-t",
        "params": {
            "file": "src/handler.py",
            "severity": "Important",
            "verdict": "CONFIRMED",
            "round": 1,
        },
    }
    v, _ = evaluate_expectation(exp, CLEAN_AFTER_RESOLVE, {"id": "x"})
    assert v == "PASS"


def test_evaluate_expectation_snake_case_check_name():
    exp = {"type": "mechanical", "check": "verdict_is", "params": {"verdict": "Clean"}}
    v, _ = evaluate_expectation(exp, CLEAN_AFTER_RESOLVE, {"id": "x"})
    assert v == "PASS"


def test_evaluate_expectation_unknown_check_fails():
    exp = {"type": "mechanical", "check": "no-such-check"}
    v, _ = evaluate_expectation(exp, CLEAN_AFTER_RESOLVE, {"id": "x"})
    assert v == "FAIL"


def test_evaluate_expectation_non_mechanical_na():
    exp = {"type": "semantic", "check": "verdict-is"}
    v, _ = evaluate_expectation(exp, CLEAN_AFTER_RESOLVE, {"id": "x"})
    assert v == "N/A"


# ---------------------------------------------------------------------------
# aggregate_replicates (finding-set aggregation)
# ---------------------------------------------------------------------------


def test_aggregate_replicates_threshold():
    assert aggregate_replicates(["PASS", "PASS", "FAIL"], 2) == "PASS"
    assert aggregate_replicates(["PASS", "FAIL", "FAIL"], 2) == "FAIL"
    assert aggregate_replicates(["N/A", "N/A"], 1) == "N/A"
    assert aggregate_replicates(["N/A", "PASS"], 1) == "PASS"
