---
name: quality-gate
description: Iterative red-teaming of any artifact (design docs, plans, code, hypotheses, mockups). Default 3-round cap. Invoked by artifact-producing skills or their parent orchestrator.
origin: crucible
---

# Quality Gate

Shared iterative red-teaming mechanism invoked at the end of artifact-producing skills. Provides rigorous adversarial review as the core quality mechanism.

**Announce at start:** "Running quality gate on [artifact type]."

## How It Works

1. Receives: artifact content, artifact type, project context
2. Invokes `crucible:red-team` on the artifact
3. If red-team finds issues: revise the artifact, invoke a FRESH red-team (no anchoring)
4. Track issue count between rounds:
   - **Strictly fewer issues** → progress, loop again
   - **Same or more issues** → stagnation, escalate to user
5. **Default 3-round cap.** If still finding Fatal issues after 3 rounds, escalate to user with findings. User can override with "keep going" but the default is capped.

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

- After 3 rounds with remaining Fatal issues → escalate to user
- Stagnation (same or more issues) → escalate immediately
- User can say "keep going" to extend beyond 3 rounds
- User can interrupt at any time to skip the gate

## Red Flags

- Rationalizing away red-team findings instead of addressing them
- Skipping the gate without user approval
- Running more than 3 rounds without escalating
- Using the same red-team agent across rounds (always dispatch fresh)

## Integration

- **crucible:red-team** — The engine that performs each review round
- **crucible:design** — Produces design docs (standalone: gates itself)
- **crucible:planning** — Produces plans (standalone: gates itself)
- **crucible:debugging** — Produces hypotheses and fixes
- **crucible:mockup-builder** — Produces mockups
- **crucible:mock-to-unity** — Produces translation maps and implementations
- **crucible:build** — Outermost orchestrator, controls all gates in pipeline
