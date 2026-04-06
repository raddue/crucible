---
ticket: "#126, #127, #128"
title: "Three /design skill enhancements"
date: "2026-04-06"
source: "spec"
---

# Three /design Skill Enhancements

## Overview

Three independent enhancements to `/design`'s Phase 2 investigated-questions loop. Each adds a structured heuristic that triggers under specific conditions. All modify `skills/design/SKILL.md` only.

## Enhancement 1: Scope Absorption Test (#126)

### Current State

The design skill explores dimensions but has no structured test for "should this feature even go in the target system?" Scope creep through absorption — adding features to the nearest existing system rather than evaluating independently — is a common failure mode.

### Change

Add a scope absorption test that triggers when a feature targets an existing system. Insert as a check in **Step 5: Synthesize**, after agents return but before presenting options to the user.

**The 4-question test:**
1. Does this share the same data model as the host application?
2. Does this share the same interaction pattern (form entry vs. dashboard vs. real-time)?
3. Does this serve the same users with the same workflows?
4. Would this feature survive if the host application were replaced tomorrow?

If fewer than 3 answers are "yes," flag to the user: "This feature may not belong in [target system]. Consider whether it deserves its own application."

**Trigger condition:** The task targets an existing system (not greenfield). The orchestrator determines this from the user's description and Phase 1 context — if modifying or extending an existing codebase, the test applies.

### Insertion Point

`skills/design/SKILL.md`, Phase 2, Step 5 (Synthesize), as a new item 2.5 between "Check for auto-resolution" and "Check for question redirection":

```
2.5. **Scope absorption test** — If this feature targets an existing system, apply the 4-question test...
```

## Enhancement 2: Data Modeling Grain Test (#127)

### Current State

The design skill has no specific data modeling heuristics. Bad data models are expensive — they cascade through every query and are painful to migrate.

### Change

Add a data modeling grain test that triggers when a design dimension involves schema or data layer changes. Insert as an addition to the **Phase 3 gap scan checklist** and as guidance in the **Step 3 Triage** table.

**Three-level evaluation:**

1. **Grain test:** "What is one row in this table?" Must be answerable in a single sentence. Bad signs: rows that mean different things depending on a type column, rows containing multiple independent facts.

2. **Relationship clarity:** Every foreign key tells a story. Parent-child relationships should be obvious from the schema alone. If you need a whiteboard to explain how two tables relate, add an intermediate table or rethink the relationship.

3. **Durability:** The schema outlives the application. Design tables as if the application will be replaced but the data must survive. Use simple types, avoid application-specific encoding.

**Trigger condition:** The design dimension involves database schema, data model, or persistent storage decisions.

### Insertion Points

1. `skills/design/SKILL.md`, **Step 3 Triage table** — Add a note: "Dimensions involving data model or schema changes: always Deep dive. Apply grain test during synthesis."

2. `skills/design/SKILL.md`, **Phase 3 gap scan checklist** — Add: "Data model grain — Can you answer 'what is one row?' for every new table? Relationships obvious from schema? Schema durable beyond the application?"

## Enhancement 3: Decision Stall-Breaker Protocol (#128)

### Current State

Design's dimension loop can stall when the user faces two reasonable options and keeps asking for more analysis. More analysis rarely breaks the tie — it just burns context.

### Change

Add a stall-breaker protocol that the orchestrator applies when deliberation loops without new information. Insert as a new section after Step 8 (Cascade).

**Stall detection:** The same design dimension has been discussed for 2+ exchanges without new information or a decision.

**The tiebreaker protocol (applied in order):**
1. Can you identify a concrete technical reason one option is wrong? Eliminate it.
2. Are both viable? Pick the one that's simpler to reverse if you're wrong.
3. Still stuck? Pick the one that ships sooner. Shipping teaches things deliberation cannot.

**Presentation:** "We've been deliberating on [dimension] for a while without new information surfacing. Here's my tiebreaker recommendation: [option], because [reversibility/shipping reason]. If you disagree, tell me — otherwise I'll proceed with this."

The user can always override. This is a nudge, not a forced decision.

### Insertion Point

`skills/design/SKILL.md`, new **Step 8.5: Stall-Breaker** between Step 8 (Cascade) and Phase 3, or as an addition to Step 7 (Present to User) with a conditional trigger.

## Key Decisions

### DEC-1: All three embed in SKILL.md only (High Confidence)

No new prompt templates needed. These are orchestrator-level heuristics, not investigation agent instructions. The agents don't need to know about them — the orchestrator applies them after agents return.

### DEC-2: Scope absorption test at Step 5 synthesis (High Confidence)

Not at Step 1 (too early — no investigation results yet) or Step 7 (too late — already presenting to user). Step 5 is the natural place: agents returned, orchestrator is synthesizing, right before forming options.

### DEC-3: Grain test as triage guidance + gap checklist (High Confidence)

Not a separate Phase 2 step (over-engineered for a checklist). The triage table tells the orchestrator to go deep; the gap checklist ensures the design doc includes the grain assessment.

### DEC-4: Stall-breaker as a separate step, not modifying Step 7 (High Confidence)

The stall-breaker is an orchestrator behavior triggered by conversation state (2+ exchanges, no progress), not part of the standard presentation flow. Keeping it separate makes the trigger condition clear.

## Acceptance Criteria

1. Scope absorption test: 4-question test in Step 5, conditional on targeting existing system
2. Data modeling grain test: triage table note + gap checklist item for schema dimensions
3. Decision stall-breaker: protocol with 3-tier tiebreaker, 2+ exchange trigger
4. All changes in SKILL.md only — no new files
5. Existing Phase 2 flow preserved — enhancements are additive
