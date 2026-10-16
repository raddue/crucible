---
name: skill-selection-evals
description: "Eval-only skill for measuring skill routing accuracy. Not invoked directly — contains selection evals that test whether the agent picks the correct skill for a given prompt."
---

# Skill-Selection Evals

This is not an executable skill. It contains evaluation data for measuring the accuracy of skill selection (routing) decisions.

## Purpose

Crucible's 52 execution evals measure quality once a skill is invoked. Selection evals measure whether the **right skill gets invoked** in the first place.

## Eval Types

- **Direct selection**: Given a prompt, does the agent pick the correct skill?
- **Negative selection**: Given a prompt that sounds like skill X but is not, does the agent avoid the false positive?
- **Context-dependent**: Same verb, different context, different correct skill.
- **Cascade ordering**: Multi-skill tasks requiring correct invocation order.

## Boundaries Tested

1. **test-methodology** — TDD vs test-coverage vs inquisitor per-task mode
2. **review-direction** — temper fresh diff review vs temper inbound feedback mode
3. **adversarial-scope** — red-team vs inquisitor vs audit vs siege
4. **completion-claims** — verify vs finish
5. **bug-handling** — debugging vs verify vs audit
6. **build-vs-raw-dispatch** — build (full idea→PR pipeline) vs a single-skill dispatch (planning, test-driven-development, …)
7. **onboarding-entry** — getting-started's on-demand workshop tour vs recon's whole-repository codebase onboarding.
8. **explore-vs-improve** — recon vs other skills for task investigation, whole-repo onboarding, or improvement discovery. This selection suite checks which skill is routed; it does not grade recon's internal mode selection.
9. **session-hub** — getting-started reference modes (compass, forge, handoff, recall, workshop) vs recon, finish, verify, anvil, checkpoint, replay, debugging, and temper.
10. **anvil-skill-audit** — anvil's suite-wide health and efficiency audit vs single-artifact audit or single-skill edit/eval.

## Difficulty Ratings

Each eval is rated easy/medium/hard based on routing ambiguity. This enables stratified baseline measurement — distinguishing between improvements that lift hard cases (high value) vs confirming easy cases already work (low signal).

## See Also

- `evals/evals.json` — the eval data
- `GRADING.md` — grading criteria and baseline measurement protocol
