# ADR-0003: Leave model selection to the host and operator

## Status
ACCEPTED
Supersedes ADR-0001

## Date
2026-09-25

## Context

Crucible skills and agent definitions carried per-role model pins: the red-team
role on the strongest tier, the quality-gate fix/verify/judge roles on a cheaper
tier (ADR-0001). Only one harness binds an agent definition's `model:`
frontmatter. Hosts without a first-class per-agent pin degraded to whatever the
session ran, so the documented recall guarantee was true on one harness and
silently false on the others — and every dispatch call that repeated a selector
was a portability liability rather than an enforcement.

## Decision

Specify roles and tasks only. No model selectors in skill or agent-definition
frontmatter, and none in inline `Task`/`Agent` dispatch calls; the host harness
and operator choose models. Keep the security guardrail: `<!-- MODEL-TIER:
security-hard-out -->` plus `scripts/check_model_pins.py`, which rejects
Fable-family selectors on marked files and requires the marker on every file in
its security-surface allowlist (default-deny).

## Alternatives Considered

### Keep per-role pins and the eval-before-default rule
- Pros: on the one harness that binds agent-def `model:`, the review tier is a
  checked property rather than an operator convention.
- Cons: unenforceable on every other harness, where the pin degrades silently;
  the guarantee reads as repo-wide while holding only in one place.
- Rejected: a guarantee that holds on one host is a portability defect, not an
  enforcement mechanism.

### Drop the security marker and checker along with the pins
- Pros: fewer moving parts; nothing left to keep in sync.
- Cons: loses the only static check that security-surface files never receive a
  Fable-family selector, which is independent of who picks the model.
- Rejected: the guardrail is a marker-coverage check, not a model assignment.

## Consequences

Model choice becomes operator-owned end to end, so review strength on
recall-critical roles now tracks the operator's default model rather than a
repo-side pin. ADR-0001's pin regression test is deleted with the pin it
asserted; measured cost and quality evidence for the old tiers stays in
`docs/evals.md` and the eval fixtures as historical record. The guardrail that
remains checks marker coverage and rejects Fable-family selectors — it does not
inspect runtime host configuration.
