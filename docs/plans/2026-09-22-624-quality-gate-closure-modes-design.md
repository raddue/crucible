---
ticket: "#624"
title: "Quality-gate closure modes"
date: "2026-09-22"
source: "design"
status: "proposed"
---

# Design — Quality-gate closure modes (#624)

## Problem

`/quality-gate` currently treats a fresh review as clean only at `0 Fatal / 0 Significant`.
Unattended runs can spend many rounds removing low-value Significant findings after all Fatal
risk is gone. This makes standard use expensive and leaves no explicit way to request the
strict bar.

## Decision

Add one invocation argument, `mode: standard | full`, defaulting to `standard`.

- **standard (default / auto):** retain all existing review, fix, verifier, receipt-lint,
  siege, discrepancy, no-op, architectural, regression, and round-cap protections. A fresh
  review with `0 Fatal` is closure-eligible **only after any preceding actionable round has
  completed its existing fix + verifier path**. A round with `0 Fatal` but one or more
  Significant findings is actionable (not an immediate PASS), so those findings still route
  through the fix agent and verifier. On the required post-fix fresh reverify, Significant
  and Minor findings that remain are residuals, not a clean-pass blocker; they are disclosed
  in the verdict marker and return summary. A first round with `0 Fatal, 0 Significant` may
  enter the normal look-harder path without inventing an empty fix. Closure still requires
  that fresh reverify (including mandatory look-harder unless a mechanical skip condition
  applies).
- **full (explicit):** preserve the current strict closure bar: fresh review and reverify
  must have `0 Fatal / 0 Significant`. Minors remain advisory under existing rules.

Absent `mode` means `standard`; no environment variable, runtime dependency, automatic mode
selection, or live skill mutation is introduced. Any value other than `standard` or `full` is
rejected before round 1; callers must not coerce invalid values to `standard`. Parent
orchestrators may pass `mode: full` when a strict gate is required.

## State machine

1. A red-team round counts Fatal, Significant, and Minor using the existing score-source
   contract.
2. `full` uses the existing candidate-clean predicate (`Fatal == 0 AND Significant == 0`).
3. `standard` allows candidate-clean at `0 Fatal` only for the required post-fix fresh
   reverify, or for a truly clean first round at `0 Fatal / 0 Significant`. A first-round
   `0 Fatal / >0 Significant` result is actionable and MUST enter fix + verifier; before
   required reverify, standard is non-clean when `Fatal > 0 OR Significant > 0`. A `0 Fatal`
   round reached after that path is the required fresh reverify; any remaining
   Significant/Minor findings on this final fresh receipt are disclosed residuals. No fix
   is invented for a genuinely empty first-round work order.
4. Look-harder uses the active mode's predicate. `full` requires `0F/0S`; `standard` may
   disclose Significant/Minor residuals only when look-harder belongs to the required
   post-fix fresh reverify. A pre-fix look-harder result with `0F/>0S` is actionable and
   returns to fix + verifier; it cannot become residual disclosure.
5. Siege failure, receipt-lint failure, severity-count discrepancy, unresolved Fatal,
   no-op-fix, architectural block, sustained regression, user interrupt, and the 15-round
   cap block or escalate in both modes. A truly clean first-round `0F/0S` may use the normal
   candidate-clean/look-harder path; this exception never applies to first-round `0F/>0S`.
6. Standard PASS writes `Mode: standard`, `ResidualSignificant`, and `ResidualMinor` as
   nonnegative counts sourced from the terminal qualifying fresh receipt. Full PASS writes
   `Mode: full` and `ResidualSignificant: 0`; existing Minor advisory behavior remains
   unchanged. Parent consumers inspect mode before treating PASS as strict.

## Safety invariants

- Fatal findings never become residuals. Standard PASS is impossible with `Fatal > 0`.
- Full mode remains behavior-compatible with the current `0F/0S` closure rule.
- A fix is never considered a reverify; a fresh red-team review is required after fixes.
- Look-harder, siege, receipt verification, and discrepancy handling remain mandatory and
  mode-aware; mode does not bypass them.
- Weighted score and stagnation math remain `Fatal=3, Significant=1`; Minors stay out of
  score and escalation predicates.
- Marker/log/return output names the active mode and residual counts so downstream
  build/spec consumers cannot mistake standard PASS for strict PASS. Counts come from the
  terminal qualifying fresh-review set: the required reverify plus any confirming
  look-harder receipt, unioned by normalized finding identity (duplicate identity counts
  once). They never come from an earlier pre-fix receipt or an un-deduplicated sum. A
  demoting look-harder receipt replaces the candidate findings and becomes authoritative
  for the next fix cycle; only that cycle's later required reverify can qualify. Every
  required reverify is a distinct red-team dispatch with its own receipt.

## Surface changes

- `skills/quality-gate/SKILL.md`: argument, state-machine, closure, marker, return, and
  anti-rationalization contracts.
- `skills/build/SKILL.md`, `skills/spec/SKILL.md`, `skills/migrate/SKILL.md`: parent-gate
  wording becomes mode-aware; default callers remain standard, strict callers pass `full`.
  Selected QG mode persists through nested calls, retries, compaction recovery, and resume.
- `scripts/check_qg_closure_modes.py`: path-pinned structural contract check with self-test.
- `scripts/run_tests.sh`: run the new checker.
- `skills/quality-gate/evals/evals.json`: add standard residual-significant and explicit-full
  scenarios after the structural contract lands.

## Non-goals

No change to severity weights, red-team prompts, siege thresholds, fix-agent model pins,
receipt grammar, runtime code, or automatic adoption of `full`. No attempt to make residual
Significants disappear from reports; standard mode makes them explicit.

## Verification

- Structural checker passes its positive fixture and fails when mode, Fatal-only standard
  closure, full strict closure, residual telemetry, or parent mode propagation is removed.
- Existing QG structural checks and second-pass scorer remain green.
- `bash scripts/run_tests.sh` passes.
