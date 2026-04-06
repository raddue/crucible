---
ticket: "#126, #127, #128"
title: "Design Enhancements — Implementation Plan"
date: "2026-04-06"
source: "spec"
---

# Design Enhancements — Implementation Plan

## Task Overview

3 tasks, all modifying `skills/design/SKILL.md`. Independent of each other.

### Task 1: Add scope absorption test (#126)

**Files:** `skills/design/SKILL.md`
**Complexity:** Low
**Dependencies:** None

Insert a new item in Phase 2, Step 5 (Synthesize), between items 2 and 3 (after "Check for auto-resolution", before "Check for question redirection"):

Add item "2.5 **Scope absorption test**" with:
- Trigger: feature targets an existing system (not greenfield)
- 4-question test (data model, interaction pattern, same users, survives replacement)
- Threshold: fewer than 3 "yes" → flag to user
- One-sentence-description test: each application should be describable in one sentence

### Task 2: Add data modeling grain test (#127)

**Files:** `skills/design/SKILL.md`
**Complexity:** Low
**Dependencies:** None

Two insertions:

1. **Step 3 Triage table:** Add a note after the table: "**Data model dimensions:** Decisions involving database schema, data model, or persistent storage always warrant Deep dive. Apply the grain test during synthesis."

2. **Gap scan checklist (Before Saving the Design):** Add a new checklist item:
   `- [ ] **Data model grain** — Can you answer "what is one row?" in a single sentence for every new table? Relationships obvious from schema alone? Schema durable beyond the application?`

### Task 3: Add decision stall-breaker protocol (#128)

**Files:** `skills/design/SKILL.md`
**Complexity:** Low
**Dependencies:** None

Insert a new section after Step 8 (Cascade), before Phase 3:

**Step 9: Stall-Breaker (Conditional)**

- Trigger: same dimension discussed 2+ exchanges without new information or a decision
- 3-tier tiebreaker protocol (eliminate technically wrong → pick more reversible → pick ships sooner)
- Presentation format: "We've been deliberating on [dimension]... Here's my tiebreaker recommendation..."
- User can always override

## Dependency Graph

```
Task 1 (scope absorption) — independent
Task 2 (grain test) — independent
Task 3 (stall-breaker) — independent
```

All three modify SKILL.md at different locations. No ordering constraints.

## Implementation Notes

- **Single file, three non-overlapping insertions.** All edits are in `skills/design/SKILL.md` at different locations.
- **No new files.** These are orchestrator-level heuristics, not investigation agent instructions.
- **Additive only.** Existing Phase 2 flow is preserved. Each enhancement is conditional.
