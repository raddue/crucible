---
name: quality-gate
description: Iterative red-teaming of any artifact (design docs, plans, code, hypotheses, mockups). Loops until clean or stagnation. Invoked by artifact-producing skills or their parent orchestrator.
origin: crucible
---

# Quality Gate

Shared iterative red-teaming mechanism invoked at the end of artifact-producing skills. Provides rigorous adversarial review as the core quality mechanism.

**Announce at start:** "Running quality gate on [artifact type]."

## How It Works

1. Receives: artifact content, artifact type, project context
2. Invokes `crucible:red-team` on the artifact
3. If red-team finds issues: revise the artifact, invoke a FRESH red-team (no anchoring)
4. Track weighted score between rounds (Fatal=3, Significant=1):
   - **Strictly lower score** → progress, loop again
   - **Same or higher score** → stagnation, escalate to user
5. **Global safety limit: 15 rounds.** Loop continues as long as progress is being made, up to a maximum of 15 rounds. This is a runaway protection circuit-breaker, not a quality target — if you hit 15, something has gone wrong. Escalate to user with full round history.

### Artifact Types

| Type | Produced By | Gate Trigger |
|------|-------------|-------------|
| design | `crucible:design` | After design doc is saved |
| plan | `crucible:planning` | After plan passes review |
| hypothesis | `crucible:debugging` | Phase 3.5, before implementation |
| code | `crucible:debugging`, build | After implementation/fix |
| mockup | `crucible:mockup-builder` | After mockup is created |
| translation | `crucible:mock-to-unity` | After self-verification |

## Invocation Convention

Quality gate is invoked by the **outermost orchestrator only** — not self-invoked by child skills. This avoids double-gating that arises because subagents have isolated contexts.

### When Used Standalone

The skill itself is the outermost orchestrator. It invokes quality gate at the end.

Example: User runs `/design` directly → design skill creates the doc → design skill invokes quality gate.

### When Used as a Sub-Skill of Build

Build is the outermost orchestrator and controls all quality gates:

- **Phase 1 (after design):** Quality gate on design doc (artifact type: design)
- **Phase 2 (after plan review):** Quality gate on plan (artifact type: plan)
- **Phase 4 (after implementation):** Quality gate on full implementation (artifact type: code)

Child skills (`crucible:design`, `crucible:planning`) document that they produce gateable artifacts but do NOT self-invoke quality gate when called by build.

### Documentation Convention

Each artifact-producing skill's SKILL.md documents:

> "This skill produces **[artifact type]**. When used standalone, invoke `crucible:quality-gate` after [trigger]. When used as a sub-skill of build, the parent orchestrator handles gating."

## Escalation

- Stagnation (weighted score same or higher) → escalate to user with findings from both rounds
- Global safety limit reached (15 rounds) → escalate to user with full round history
- Architectural concerns → escalate immediately (bypass loop)
- User can interrupt at any time to skip the gate

## Red Flags

- Rationalizing away red-team findings instead of addressing them
- Skipping the gate without user approval
- Exceeding the 15-round safety limit without escalating
- Using the same red-team agent across rounds (always dispatch fresh)
- Declaring stagnation on raw issue count without using weighted score (Fatal=3, Significant=1)

## Integration

- **crucible:red-team** — The engine that performs each review round
- **crucible:design** — Produces design docs (standalone: gates itself)
- **crucible:planning** — Produces plans (standalone: gates itself)
- **crucible:debugging** — Produces hypotheses and fixes
- **crucible:mockup-builder** — Produces mockups
- **crucible:mock-to-unity** — Produces translation maps and implementations
- **crucible:build** — Outermost orchestrator, controls all gates in pipeline
