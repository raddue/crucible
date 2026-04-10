---
name: skill-selection-evals
description: "Eval-only skill for measuring skill routing accuracy. Not invoked directly — contains selection evals that test whether the agent picks the correct skill for a given prompt."
---

# Skill-Selection Evals

This is not an executable skill. It contains evaluation data for measuring the accuracy of skill selection (routing) decisions.

## Purpose

Crucible's 49 execution evals measure quality once a skill is invoked. Selection evals measure whether the **right skill gets invoked** in the first place.

## Eval Types

- **Direct selection**: Given a prompt, does the agent pick the correct skill?
- **Negative selection**: Given a prompt that sounds like skill X but is not, does the agent avoid the false positive?
- **Context-dependent**: Same verb, different context, different correct skill.
- **Cascade ordering**: Multi-skill tasks requiring correct invocation order.

## Boundaries Tested

1. **test-methodology** — TDD vs test-coverage vs adversarial-tester
2. **review-direction** — code-review vs review-feedback
3. **adversarial-scope** — red-team vs inquisitor vs audit vs siege
4. **completion-claims** — verify vs finish
5. **bug-handling** — debugging vs verify vs audit

## See Also

- `evals/evals.json` — the eval data
- `GRADING.md` — grading criteria and baseline measurement protocol
