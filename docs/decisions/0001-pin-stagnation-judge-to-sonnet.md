# ADR-0001: Pin the quality-gate fix agent to Sonnet

## Status
ACCEPTED

## Date
2026-09-10

## Context

Quality-gate's main loop is a sequence of subagent roles: a red-team (adversarial
review), a fix agent that revises the artifact, a verifier that checks the fix,
and a stagnation judge that decides when the loop is no longer making progress.
The red-team role is calibration-recall-critical and stays on Opus. The fix agent,
verifier, and stagnation judge are cheaper, more mechanical roles.

Before #537 the fix agent ran `model: inherit` (whatever model the session used).
That made its tier unrecorded and unenforceable — nothing in the tracked suite
asserted the pin, so a silent revert passed CI. #528 measured a 38% iatrogenic
rate (fix-authored defects breeding across generations) under that pre-#537
fixer.

## Decision

Pin `crucible-qg-fix` (and the mechanically-similar `crucible-qg-judge` /
`crucible-qg-verifier` stagnation-judge roles) to Sonnet, and add a regression
test that fails if the agent def's `model:` frontmatter silently drifts back to
`inherit`.

The rationale: these roles are mechanical and cheap. A weaker fix is caught
downstream — the fix output is re-reviewed by a subsequent Opus red-team round
on single-model rounds — so paying for a stronger per-turn model buys marginal
output quality at ~2.6× cost. The `Eval-before-default` rule (no model flip
without an A/B eval) is waived for this downgrade, with the per-round Opus
re-review as a partial measurement surrogate.

## Alternatives Considered

### Keep the fix agent on Opus (eval-before-default, no waiver)
- Pros: maximum output quality; the downgrade's other named concern (calibration
  distribution) is left unmeasured by the waiver.
- Cons: ~2.6× effective cost on a mechanical role whose weaker output is caught
  by the per-round red-team re-review. The waiver explicitly trades this away.
- Rejected: the cost is not justified for a role whose failures are caught
  downstream; the counter-evidence (#528's 38% iatrogenic rate) is worse under
  the unrecorded `inherit` state, not under a recorded Sonnet pin.

### Leave the fix agent unrecorded (`inherit`) as before
- Pros: no change.
- Cons: the tier is unenforceable — a silent revert passes CI, exactly the #537
  defect. Round-count and calibration-distribution effects stay unmeasured.
- Rejected: recording the pin (with a regression test) is the whole point of
  #537.

## Consequences

Makes the fix-agent tier a checked property rather than an operator convention.
Makes a weaker fix possible in exchange for a bounded-measurement surrogate
(per-round red-team re-review) and a waived eval, both tracked in #537/#539.
Records the known residual: the downgrade's calibration-distribution effect
remains unmeasured.