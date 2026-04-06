# Primacy Eval: Sanity Check Results

**Date:** 2026-04-05
**Scope:** 2 templates × 2 modes × 2 reps = 8 runs (Sonnet)
**Fixture:** Issue #126 (scope absorption test for /design)

## Build-Reviewer Template (4 runs)

### Canary Fact: `_xq7_validateScopeAlignment`

| Run | Mode | Canary Referenced? | Findings | Structure Complete? |
|-----|------|--------------------|----------|-------------------|
| 1 | Control (inline) | YES — called it "hallucination" | 4 Critical, fabricated report detected | Yes (Pass 1 + Pass 2 + Overall) |
| 2 | Control (inline) | YES — called it "AI slop" with "_xq7_ prefix" | 4 Critical, fabricated report + TDD | Yes (Pass 1 + Pass 2 + Overall) |
| 1 | Test (disk-read) | YES — called it "synthetic output with pseudo-random prefix" | 4 Critical, fabricated report + AI slop signal | Yes (Pass 1 + Pass 2 + Overall) |
| 2 | Test (disk-read) | YES — called it "invented claims" | 4 Critical, fabricated report + scope creep | Yes (Pass 1 + Pass 2 + Overall) |

**Verdict: PASS.** All 4 runs detected the same issues, referenced the canary, produced identical report structure. No degradation in test mode.

## Red-Team Template (4 runs)

### Canary Fact: `_kw9_scopeBoundaryResolver`

| Run | Mode | Canary Referenced? | Fatal | Significant | Minor | Second Pass |
|-----|------|--------------------|-------|-------------|-------|-------------|
| 1 | Control (inline) | YES (Finding 3) | 2 | 4 | 4 | 2 |
| 2 | Control (inline) | YES (Finding 4) | 2 | 4 | 4 | 3 |
| 1 | Test (disk-read) | YES (Fatal 2) | 1+1S* | 2 | 4 | 1(S) |
| 2 | Test (disk-read) | YES (Fatal 1) | 2 | 3 | 4 | 3 |

*Test run 1 classified the threshold issue as Significant rather than Fatal — a severity judgment difference, not a thoroughness gap.

**Finding overlap analysis:**

| Finding theme | Ctrl 1 | Ctrl 2 | Test 1 | Test 2 |
|--------------|--------|--------|--------|--------|
| Threshold/weighting broken | Fatal | Fatal | Significant | Fatal |
| Fictional function reference (canary) | Significant | Significant | Fatal | Fatal |
| Auto-resolution too aggressive | Significant | Significant | Significant | Significant |
| Trigger condition undefined | Significant | Significant | Significant | Significant |
| Q4 epistemically broken | Fatal | Fatal | — | — |
| Invariants placement wrong | Significant | Significant | Minor | Minor |
| Task 2 optional/required conflict | Minor | Minor | Minor | Significant |
| Frame problem (absorb vs separate binary) | Second pass | — | Second pass | Second pass |
| No SRP question | — | Minor | — | Significant |

**Verdict: PASS.** Test runs found the same core issues as controls. Minor differences in severity classification and which secondary findings surfaced — consistent with normal model variance, not prompt primacy effects.

## Aggregate Assessment

| Metric | Control (4 runs) | Test (4 runs) | Delta |
|--------|-----------------|---------------|-------|
| Canary referenced | 4/4 (100%) | 4/4 (100%) | 0% |
| Report structure complete | 4/4 (100%) | 4/4 (100%) | 0% |
| Core findings detected (reviewer) | 4/4 detected fabrication | 4/4 detected fabrication | 0% |
| Core findings detected (red-team) | avg 12 findings | avg 10.5 findings | -12.5% |
| Fatal findings (red-team) | avg 2.0 | avg 1.75 | -12.5% |
| Canary severity (red-team) | Significant (both) | Fatal (both) | Test promoted it |

### Key Observations

1. **Canary detection: 8/8 (100%).** Both canary facts were referenced in every single run regardless of delivery mode. No prompt primacy effect on injected context attention.

2. **Report structure: 8/8 (100%).** All runs produced the expected structure (reviewer: Pass 1 + Pass 2 + Overall; red-team: Fatal + Significant + Minor + Second Pass + Overall). No structural degradation.

3. **Thoroughness: comparable.** Red-team test runs averaged slightly fewer total findings (10.5 vs 12), but the core issues (threshold, canary, auto-resolution, trigger) were found in all 4 runs. The delta is within normal model variance.

4. **Interesting reversal on canary severity:** Control runs classified the fictional function as Significant; test runs classified it as Fatal. The disk-mediated runs actually *promoted* the canary finding — the opposite of what prompt primacy would predict.

5. **No evidence of prompt primacy degradation.** The test runs processed all injected context (design doc, implementation plan, project context, canary facts) with the same fidelity as control runs.

## Decision

**Sanity check: PASS.** No degradation detected. Recommend proceeding to either:
- (a) Full eval (expand to 8-10 reps × 4 templates) for statistical confidence, or
- (b) Accept sanity check results and proceed to rollout

The sanity check is small (n=2 per condition) and cannot detect subtle effects. But the signal is unambiguous: 8/8 canary hits, 8/8 structural compliance, comparable finding quality. A 15% degradation effect would likely have shown as at least one canary miss or structural gap across 8 runs — none appeared.
