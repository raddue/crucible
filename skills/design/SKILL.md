---
name: design
description: "You MUST use this before any creative work - creating features, building components, adding functionality, or modifying behavior. Explores user intent, requirements and design before implementation."
---

# Brainstorming Ideas Into Designs

## Overview

Turn ideas into fully formed designs through investigated, collaborative dialogue.

Every significant design question is backed by parallel investigation agents that research the codebase, explore approaches, and assess impact BEFORE the question reaches the user. Questions arrive informed, not naive.

## The Process

### Phase 1: Context Gathering

- **RECOMMENDED:** Use crucible:forge (feed-forward mode) — consult past lessons
- **RECOMMENDED:** Use crucible:cartographer (consult mode) — review codebase map
- Check current project state (files, docs, recent commits)
- Understand the user's initial idea through open conversation

### Phase 2: Investigated Questions

For each design dimension that needs a decision, follow this loop:

#### Step 1: Identify the Design Dimension

Before asking anything, name the decision needed (e.g., "persistence strategy," "component communication pattern," "UI architecture").

#### Step 2: State Your Hypothesis

Write down what you EXPECT to find before dispatching agents. After agents return, compare. **Surprises get highlighted** — they're the most valuable insights.

#### Step 3: Triage Depth

| Tier | When | Effort |
|------|------|--------|
| **Deep dive** | Architectural decisions, integration points, pattern choices, anything constraining future work | 3 parallel agents + challenger |
| **Quick scan** | Implementation approach within decided architecture, which existing pattern to follow | Single codebase scout |
| **Direct ask** | Naming, UI placement, priority ordering — no technical implications | Ask directly |

#### Step 4: Dispatch Investigation

**Deep dive** — spawn three agents in parallel (templates in `investigation-prompts.md`):

1. **Codebase Scout** — What does the codebase already do in this area? Existing patterns, conventions, constraints.
2. **Domain Researcher** — What are the viable approaches? Trade-offs, best practices, precedents.
3. **Impact Analyst** — What existing systems does this decision affect? What could break?

Pass the **cascading context** (all prior decisions and rationale) to each agent.

**Quick scan** — dispatch only the Codebase Scout.

#### Step 5: Synthesize

After agents return:

1. **Compare to hypothesis** — note surprises
2. **Check for auto-resolution** — if only one viable path exists, inform the user rather than asking: "Investigation showed X is the only viable approach because [reasons]. Moving on." User can interrupt if they disagree.
3. **Check for question redirection** — if agents found the wrong question is being asked, redirect: "Was going to ask about X, but investigation revealed the real decision is Y."
4. **Synthesize into 2-3 informed options** with a recommended choice

#### Step 6: Challenge (Deep Dive Only)

Dispatch a **Challenger** agent (template in `investigation-prompts.md`):
- Attacks the recommendation's assumptions
- Checks for conflicts with prior decisions
- Identifies blind spots in the investigation
- Brief output — this is lightweight, not a full red-team

#### Step 7: Present to User

```
### [Design Dimension]

**Hypothesis:** [what you expected]
**Surprises:** [anything that contradicted expectations — highlight these]

**Investigation:**
- **Codebase:** [2-3 sentence summary]
- **Approaches:** [2-3 sentence summary of viable options]
- **Impact:** [2-3 sentence summary of affected systems]

**Challenge:** [1-2 sentence summary of what the challenger raised]

**Recommendation:** [your recommended option and why]

**Question:** [the refined question, prefer multiple choice]
```

For auto-resolved questions:

```
### [Design Dimension] — Auto-Resolved

[Why only one viable path exists. Decision made.]
*Speak up if you disagree.*
```

#### Step 8: Cascade

After the user answers, add the decision and rationale to the running context. All subsequent agents receive this.

### Phase 3: Design Presentation

Once key dimensions are decided:
- Present design in sections of 200-300 words
- Ask after each section whether it looks right
- Cover: architecture, components, data flow, error handling, testing
- Be ready to go back and re-investigate if something doesn't make sense

## Before Saving the Design

Scan for gaps (use judgment — not every item applies):

- [ ] **Acceptance criteria** — Concrete and testable?
- [ ] **Testing strategy** — Unit vs integration coverage?
- [ ] **Integration impact** — Touchpoints addressed?
- [ ] **Failure modes** — Invalid data, missing dependencies, unexpected state?
- [ ] **Edge cases** — Boundary conditions?

Raise critical gaps with the user before saving.

## After the Design

- Write to `docs/plans/YYYY-MM-DD-<topic>-design.md`
- Commit the design document

**Implementation (if continuing):**
- Ask: "Ready to set up for implementation?"
- Use crucible:worktree, then crucible:planning

## Quality Gate

This skill produces **design docs**. When used standalone, invoke `crucible:quality-gate` after the design document is saved and committed. When used as a sub-skill of build, the parent orchestrator handles gating.

## Key Principles

- **Investigated questions** — Never ask a significant question without research backing
- **One question at a time** — Don't overwhelm
- **Auto-resolve when possible** — Don't waste user attention on decided questions
- **Hypothesis-first** — State expectations, highlight surprises
- **Cascading context** — Each decision informs subsequent investigations
- **YAGNI ruthlessly** — Remove unnecessary features
- **Depth-appropriate effort** — Not every question needs deep investigation

## Integration

**Related skills:** crucible:planning, crucible:worktree, crucible:forge, crucible:cartographer, crucible:quality-gate

**Prompt templates:** `design/investigation-prompts.md`
