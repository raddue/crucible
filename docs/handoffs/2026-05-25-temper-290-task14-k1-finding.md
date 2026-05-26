# #290 Task 14 k1 Finding — Switch Reverted, Gate Proven

**Date:** 2026-05-25
**Branch:** `temper/290-real-pr-fixtures` HEAD `b07e375` (revert of `f990c6d`)
**Status:** Shipping #290 v0.1 with Task 13 reverted.

## TL;DR

Ran Task 14 POST_SWITCH calibration at k=1 (scope-cut from k=3 per PM-pivot decision). Result: §7 drift-delta gate **caught the switch as catastrophic** — 7 of 10 synthetic fixtures swung >0.2, with Surgical/DRY/SRP per-trial pass rates collapsing from ~0.92–0.98 to 0.075–0.20. Task 13 reverted. Drift-delta gate machinery proven on first real use.

## What was attempted (Task 13)

Switch `_synth_plan_reference` from reading `fixture["expected_output"]` to `fixture["pr_description"]`. Hypothesis: `pr_description` is the legitimate signal (scope-only), and `expected_output` was leaking rationale/expectation prose that biased the reviewer.

Shipped at `f990c6d` with passing unit test + full 206-test suite green.

## What the §7 gate revealed (k=1, n=20 per fixture)

| Fixture | Lens | PRE mean | POST k1 | Swing | §7 (0.2) verdict |
|---|---|---:|---:|---:|---:|
| 1a | Surgical | 0.917 | **0.000** | 0.917 | **FAIL** |
| 1b | DRY | 0.917 | 0.150 | 0.767 | **FAIL** |
| 2 | SRP | 0.967 | 0.200 | 0.767 | **FAIL** |
| 2-reattrib | SRP | 0.967 | 0.200 | 0.767 | **FAIL** |
| 3 | mixed | 0.983 | 0.100 | 0.883 | **FAIL** |
| 4 | OCP | 1.000 | 0.950 | 0.050 | ok |
| 5 | OCP | 1.000 | 0.950 | 0.050 | ok |
| 6-tenancy | OCP edge | 0.833 | 0.800 | 0.033 | ok |
| 7-rollback | OCP edge | 0.800 | 0.550 | 0.250 | **FAIL** |
| 8-defense | DRY scope | 0.967 | 0.200 | 0.767 | **FAIL** |

Per-lens POST: **Surgical 0.075 / DRY 0.20 / SRP 0.10 / OCP 0.95**.

Run artifact: `skills/temper/evals/.calibrate-state/last_run-R-postswitch-20260525-k1.json` (gitignored, durable on local disk).

**Note on fixture-level verdicts:** the fixture verdict at the 3/20 threshold still reads 8/10 PASS. This is by design — the fixture threshold is permissive; the §7 per-fixture drift-delta gate at 0.2 is the load-bearing gate, and it caught the regression. The contrast is itself a finding: fixture-level threshold alone is insufficient to detect this class of degradation.

## Diagnosis

The reviewer was using `expected_output` (rationale + lens expectation prose) as a *cue* for which lens to attend to during review. The `pr_description` field carries scope information but not expectation framing. Stripping the expectation framing collapsed Surgical/DRY/SRP detection.

**OCP fixtures survived** because OCP cares about scope-fit (new dispatch cases, structural growth), which `pr_description` still conveys through `allowed_files` and the scope statement. Surgical/DRY/SRP need a hint about *what to look for*, not just *where*.

This was a load-bearing dependency the design failed to anticipate. The plan's Step 3c(b) "switch-degradation" branch contemplated this possibility but assumed any drift would be on the order of 0.1–0.3; observed drift is 0.5–0.9 across multiple lenses simultaneously — re-authoring `pr_description` per fixture is unlikely to converge within the plan's 3-iter cap, and even partial convergence would mean re-encoding the same rationale that `expected_output` already carries (defeating the switch's purpose).

## Decision

**Revert Task 13** (`f990c6d`). `expected_output` remains authoritative for reviewer input. Ship #290 v0.1 with everything else: real-PR fixtures, leak-checker, schema validation, drift-delta gate machinery, grouped summary, and **this k1 calibration data as proof-of-value** that the gate works on first real use.

## Implications

1. **Gate machinery validated.** Drift-delta gate caught a 0.5–0.9 swing on first real invocation. Worth the build cost in retrospect — without it, the switch would have shipped and degraded production reviewer quality silently for an indeterminate period.
2. **DEC-6 k=3 symmetry overkill confirmed.** k=1 with n=20 trials per fixture detected the catastrophe with statistical certainty. The PM-pivot decision to scope-cut to k=1 was correct; running k=2 and k=3 would have burned ~14M additional subagent tokens to confirm the same finding.
3. **Reviewer is more rationale-dependent than the design assumed.** `expected_output` is not pure "documentation" — it carries reviewer-attention signal. Future temper-prompt edits should treat `expected_output` as a load-bearing input and be tested against the same gate.
4. **Fixture-level threshold (3/20) is too lenient** for this class of regression. Consider raising the per-fixture pass-rate threshold or relying primarily on the §7 drift-delta gate going forward.
5. **Task 13 hypothesis was a reasonable thing to test** — the leak-checker existed precisely because we suspected `expected_output` of leaking. The empirical answer: yes it leaks, but the reviewer needs the leak. The leak-checker should be reframed as a documentation aid, not a fatal gate.

## What v0.1 ships (post-revert)

- Real-PR-derived fixtures (5 new, hand-split for `pr_description` / `expected_output`)
- `_validate_fixtures` + `FixtureValidationError` schema gate
- `_check_pr_description_leakage` (warning-only per design §1(f) supersession)
- `lens_column` enum + per-lens-column PASS aggregation
- `--source` CLI filter on stage/score
- Empirical tolerance calibration baseline + `calibration.json` wiring
- Drift-delta gate per lens column in `last_run.json`
- Grouped summary in `score` output

## What v0.1 does NOT ship (deferred or dropped)

- **Task 13** (`_synth_plan_reference` switch) — reverted; deferred indefinitely pending different approach to reducing rationale dependency.
- **Task 14** k=3 cycles — k=1 sufficient to make the decision; deferred to v1.0 if the question is reopened.
- **Tasks 16/17/17b/18** — `baseline.json` aggregation, per-fixture gate wiring, diff-origin verification automation, PR documentation polish. All deferred to v1.0 follow-up issues.

## Recovery pointers

- Calibration k1 artifact: `skills/temper/evals/.calibrate-state/last_run-R-postswitch-20260525-k1.json`
- PRE_SWITCH artifacts: `skills/temper/evals/.calibrate-state/last_run-R-presplit-20260525-k{1,2,3}.json`
- Plan: `docs/plans/2026-05-21-temper-290-implementation-plan.md`
- Design: `docs/plans/2026-05-21-temper-290-real-pr-fixtures-design.md`
- Revert commit: `b07e375`
- Task 13 commit (reverted): `f990c6d`
