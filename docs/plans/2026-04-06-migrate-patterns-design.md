---
ticket: "#129"
title: "Add legacy migration patterns to /migrate planning phase"
date: "2026-04-06"
source: "spec"
---

# Add Legacy Migration Patterns to /migrate Planning Phase

## Current State

The `/migrate` skill focuses on technical blast radius and wave decomposition. Phase 3 (Decompose into Phases) uses a Phase Planner agent that produces migration phases with safe stopping points. The standard phase template covers technical steps (introduce new, add compatibility, migrate waves, remove old).

Missing: operational strategy patterns that determine whether a technically sound migration succeeds with real users — parallel operation, rollout groups, data migration avoidance, explicit decommission.

## Change

Add 5 legacy migration heuristics as planning constraints to Phase 3. The Phase Planner agent should check the migration plan against these patterns.

**The 5 patterns:**

1. **Map the territory first** — Understand what the legacy system actually does, not what it was designed to do. Hidden workflows, tribal knowledge, undocumented behaviors ARE the requirements.

2. **Build alongside, not on top of** — New system runs in parallel. Both live. Users try new while old is safety net. Never require hard cutover without a parallel period.

3. **Cut over by group, not by system** — One team/department moves while others stay. Migration plan should identify rollout groups, not just technical phases.

4. **Don't migrate data unless you must** — Historical data stays where it is. New system captures from day one. Build a read-only bridge if historical queries needed. Data migration is the riskiest part.

5. **Kill the old system explicitly** — When the last user is off, archive and remove access. A "still available just in case" system never dies. Plan must include explicit decommission step.

## Insertion Points

1. `skills/migrate/SKILL.md`, Phase 3 — Add patterns as planning constraints the Phase Planner must verify
2. `skills/migrate/phase-planner-prompt.md` — Add the 5 patterns as a checklist the planner applies when structuring phases

## Acceptance Criteria

1. All 5 patterns present in SKILL.md Phase 3
2. Phase planner prompt includes the patterns as a verification checklist
3. Existing phase template and safe-stopping-point invariant preserved
