---
name: innovate
description: Use when a design doc or implementation plan is finalized and you want a divergent creativity injection before adversarial review. Proposes the single most impactful addition.
---

# Innovate

## Overview

<!-- CANONICAL: shared/dispatch-convention.md -->
All subagent dispatches use disk-mediated dispatch. See `shared/dispatch-convention.md` for the full protocol.

Divergent creativity injection. Dispatches an Innovation subagent to propose the single most impactful addition to an artifact. One shot, not iterative — the red-team that follows is the quality gate.

**Core principle:** The best ideas often come from asking "what's missing?" after you think you're done.

**Announce at start:** "I'm using the innovate skill to explore potential improvements."

## When to Use

- After a design doc is approved by the user (before red-teaming)
- After an implementation plan passes review (before red-teaming)
- Anytime you want a creative enhancement pass on a finalized artifact
- When the build pipeline calls for innovation

## The Process

1. Dispatch an Innovation subagent (Opus) with the artifact and context
2. Subagent proposes the single most impactful addition
3. Incorporate the proposal into the artifact (Plan Writer or equivalent)
4. Proceed to red-teaming — the red team is the YAGNI gate

**Not iterative.** One shot per artifact. The red-team loop handles quality from there.

## How to Use

### 1. Dispatch Innovation subagent

Use the `innovate-prompt.md` template in this directory. Provide:
- The full artifact content
- Project context (existing systems, constraints, tech stack)
- What the artifact is trying to accomplish

Model: **Opus** (creative/architectural work needs the best model)

### 2. Process the proposal

The subagent returns:
- **The Single Best Addition** — what to add and why
- **Why This Over Alternatives** — brief comparison to runners-up
- **Impact** — what it enables
- **Cost** — what it adds to scope/complexity

### 3. Incorporate and move on

Have the Plan Writer (or equivalent) incorporate the proposal into the artifact. Then proceed to red-teaming — if the addition is YAGNI, the red team will kill it.

## What the Innovator is NOT

- A scope expander — one carefully chosen addition, not a feature wishlist
- A reviewer — they don't check quality or find bugs
- Iterative — one shot, move on

## Integration

**Called by:**
- **crucible:build** — Phase 1 (after design), Phase 2 (after plan review)

**Pairs with:**
- **crucible:quality-gate** — always runs after innovate to validate the addition

See prompt template: `innovate/innovate-prompt.md`
