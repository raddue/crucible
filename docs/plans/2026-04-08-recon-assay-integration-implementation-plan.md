---
ticket: "#147"
title: "Integrate /recon and /assay into consuming skills — Implementation Plan"
date: "2026-04-08"
source: "spec"
---

# Implementation Plan: Integrate /recon and /assay into Consuming Skills

## Wave 0: Pre-flight Validation (no consumer changes)

### Task 0.1: Verify recon/assay API compatibility [S]

**Files:** `skills/recon/SKILL.md`, `skills/assay/SKILL.md`

Verify that the existing invocation APIs support all identified consumer use cases without modification:

- Recon: `task`, `context`, `session_id`, `modules`, `scope` parameters cover design (task + session_id + impact-analysis), spec (task + session_id + impact-analysis), migrate (task + context.target + consumer-registry), audit (task + scope + subsystem-manifest)
- Assay: `question`, `context`, `decision_type`, `approaches`, `cascading_decisions` parameters cover design (architecture), spec (architecture, autonomous), migrate (strategy)

**Done when:** Confirmation that no API changes are needed, or a list of required changes with implementation.

### Task 0.2: Verify recon sub-skill invocation mechanics [S]

**Files:** `skills/shared/dispatch-convention.md`

Verify that a consumer skill can dispatch `/recon` as a sub-skill and receive the Investigation Brief inline. Recon's "When invoked as sub-skill" section (line 112) describes this: narration under `## Recon Progress` section, brief returned as agent output.

Confirm that:
- The dispatch convention supports skill-to-skill dispatch (not just skill-to-agent)
- The brief's section headers are stable (Brief Schema Stability section confirms this)
- Depth module outputs are appended after the `---` separator

**Done when:** Dispatch pattern documented for consumers to follow, or blockers identified.

---

## Wave 1: Design Integration (highest-impact consumer)

### Task 1.1: Add recon dispatch to design Phase 2 [M]

**Files to modify:**
- `skills/design/SKILL.md` — Add Step 0 before the dimension loop in Phase 2

**Changes:**
1. Add new subsection "### Step 0: Recon Dispatch" before Step 1 (Identify the Design Dimension):
   ```
   Dispatch /recon with:
     task: [user's feature request / design goal]
     session_id: "<design-run-timestamp>"
     modules: ["impact-analysis"]
   ```
2. Store the Investigation Brief in the design session's scratch directory
3. Add fallback: "If recon fails, proceed without recon context — dimension investigations explore from scratch (existing behavior)."
4. Update the Communication Requirement examples to include recon narration

**Done when:** Design SKILL.md includes recon dispatch at Phase 2 start with fallback behavior.

### Task 1.2: Delete Codebase Scout from design investigation [M]

**Files to modify:**
- `skills/design/investigation-prompts.md` — Delete the Codebase Scout template section
- `skills/design/SKILL.md` — Update Steps 3, 4, 5 references

**Changes:**
1. Delete the "## Codebase Scout" section from `investigation-prompts.md` (lines 8-49)
2. Update Step 3 (Triage Depth):
   - "Quick scan" tier: change from "Single codebase scout" to "Read relevant sections of the recon brief (no agent dispatch needed)"
   - "Deep dive" tier: change from "3 parallel agents + challenger" to "2 parallel agents (Domain Researcher + Impact Analyst) + challenger, with recon brief as context"
3. Update Step 4 (Dispatch Investigation):
   - "Deep dive" spawns two agents (not three): Domain Researcher and Impact Analyst
   - Both agents receive `[RECON_BRIEF]` placeholder with relevant sections of the Investigation Brief
   - "Quick scan" dispatches no agents — reads the recon brief directly
4. Update Step 5 (Synthesize): remove Codebase Scout references from the synthesis input list

**Done when:** Codebase Scout template is deleted. Deep dive dispatches 2 agents. Quick scan reads recon brief.

### Task 1.3: Update Domain Researcher and Impact Analyst prompts [S]

**Files to modify:**
- `skills/design/investigation-prompts.md` — Domain Researcher and Impact Analyst templates

**Changes:**
1. Add `[RECON_BRIEF]` placeholder to both templates' input context sections
2. Domain Researcher: "The recon brief provides codebase patterns and structure. Focus your research on approaches and trade-offs, not codebase discovery."
3. Impact Analyst: "The recon brief includes a task-level impact analysis. Focus on dimension-specific impact — how does THIS decision affect systems beyond what the task-level analysis covers."

**Done when:** Both templates accept and reference recon brief context.

### Task 1.4: Add assay dispatch to design Step 5 [M]

**Files to modify:**
- `skills/design/SKILL.md` — Update Step 5 (Synthesize) for Deep Dive dimensions

**Changes:**
1. After agents return and comparison to hypothesis is done, dispatch `/assay` for Deep Dive dimensions:
   ```
   /assay
     question: "<design dimension question>"
     context: { recon brief sections + agent findings }
     decision_type: "architecture"
     cascading_decisions: [<prior dimension decisions>]
   ```
2. Replace the informal "Synthesize into 2-3 informed options with a recommended choice" prose with: "Use assay's recommendation as the starting point. Present assay's constraint_fit scoring, kill criteria, and confidence level to the user."
3. Update Step 7 (Present to User) format to include assay output fields:
   - **Constraint Fit:** [from assay report]
   - **Kill Criteria:** [when to revisit this decision]
   - **Confidence:** [high/medium/low]
4. Add fallback: "If assay fails, synthesize options manually (existing behavior)."
5. Quick scan and Direct ask dimensions do NOT dispatch assay — only Deep Dive.

**Done when:** Deep dive dimensions use assay for structured evaluation. Presentation format includes constraint fit and kill criteria.

### Task 1.5: Update design Integration section [S]

**Files to modify:**
- `skills/design/SKILL.md` — Integration section at bottom

**Changes:**
1. Add to Related skills: `crucible:recon` (Phase 2 context), `crucible:assay` (Phase 2 decision evaluation)
2. Add note: "Recon is dispatched once at Phase 2 start. Assay is dispatched per Deep Dive dimension during synthesis."

**Done when:** Integration section reflects actual recon/assay dispatch.

---

## Wave 2: Spec Integration (mirrors design)

### Task 2.1: Add recon dispatch to spec per-ticket investigation [M]

**Files to modify:**
- `skills/spec/SKILL.md` — Per-Ticket Spec Writing section (Step 1: Investigation)
- `skills/spec/spec-writer-prompt.md` — Add recon dispatch instructions

**Changes:**
1. Add recon dispatch at the start of each ticket's investigation step:
   ```
   /recon
     task: "<ticket title and description>"
     session_id: "<spec-epic-run-id>"
     modules: ["impact-analysis"]
   ```
2. The `session_id` is the epic run's session ID — shared across all tickets for structure cache reuse. This means the Structure Scout runs once for the first ticket and is cached for all subsequent tickets.
3. Add fallback on recon failure.

**Done when:** spec-writer-prompt.md dispatches recon at investigation start.

### Task 2.2: Delete Codebase Scout from spec investigation [M]

**Files to modify:**
- `skills/spec/SKILL.md` — Step 1: Investigation subsection
- `skills/spec/spec-writer-prompt.md` — Investigation instructions

**Changes:**
1. Update the investigation description: remove "3 parallel agents (codebase scout, domain researcher, impact analyst)" and replace with "2 parallel agents (domain researcher, impact analyst) with recon brief context"
2. Update Quick scan path: "Read recon brief (no agent dispatch)"
3. Update the complex ticket rule: "5+ design dimensions or 3+ upstream contracts → use quick-scan for ALL dimensions" still applies, but quick-scan is now "read recon brief" instead of "dispatch codebase scout"

**Done when:** Codebase Scout removed from spec's investigation. Deep dive dispatches 2 agents.

### Task 2.3: Add assay dispatch to spec decision evaluation [M]

**Files to modify:**
- `skills/spec/SKILL.md` — Per-Ticket Spec Writing section
- `skills/spec/spec-writer-prompt.md` — Decision-making instructions

**Changes:**
1. For architectural dimensions (Deep Dive), dispatch assay after investigation:
   ```
   /assay
     question: "<dimension question>"
     context: { recon brief + investigation findings }
     decision_type: "architecture"
     cascading_decisions: [<prior decisions from decisions log>]
   ```
2. Add autonomous decision logic based on assay confidence:
   - `high` confidence: Accept assay recommendation. Log decision. Proceed.
   - `medium` confidence: Accept recommendation but emit terminal alert with assay's `missing_information` field.
   - `low` confidence: Emit `block` terminal alert. Log as uncertain decision.
3. Add fallback: "If assay fails, make decision based on investigation findings (existing behavior)."

**Done when:** Spec writer uses assay for architectural decisions with confidence-based alert routing.

### Task 2.4: Update spec Integration section [S]

**Files to modify:**
- `skills/spec/SKILL.md` — Integration section

**Changes:**
1. Add recon and assay to the integration table with dispatch details

**Done when:** Integration section reflects actual dispatch.

---

## Wave 3: Migrate Integration

### Task 3.1: Add recon dispatch to migrate Phase 0 [M]

**Files to modify:**
- `skills/migrate/SKILL.md` — Phase 0: Pre-flight section

**Changes:**
1. After cartographer consult and forge feed-forward, dispatch recon:
   ```
   /recon
     task: "Map structure and consumers for migration: <migration target>"
     context: { target: "<migration-target-symbol>" }
     modules: ["consumer-registry"]
   ```
2. Write recon's Investigation Brief to `scratch/<run-id>/recon-brief.md`
3. Write recon's Consumer Registry to `scratch/<run-id>/consumer-registry-from-recon.md`
4. Add fallback: "If recon fails, Blast Radius Mapper discovers consumers from scratch (existing behavior)."

**Done when:** Phase 0 dispatches recon with consumer-registry module.

### Task 3.2: Update Blast Radius Mapper to consume consumer registry [M]

**Files to modify:**
- `skills/migrate/SKILL.md` — Phase 2: Map Blast Radius section
- `skills/migrate/blast-radius-mapper-prompt.md` — Add consumer registry input

**Changes:**
1. Add `[CONSUMER_REGISTRY]` placeholder to the blast-radius-mapper prompt template
2. Update Phase 2 description: "When recon's consumer registry is available, the mapper receives pre-discovered direct consumers and focuses on transitive dependencies, test coverage, and configuration/wiring."
3. Remove "Direct consumers" from the mapper's discovery instructions and replace with: "Verify and augment the consumer registry from recon. Focus investigation on transitive dependents, test coverage, and configuration references."
4. If consumer registry is not available (recon failed), mapper falls back to full discovery (existing behavior).

**Done when:** Blast Radius Mapper consumes consumer-registry input and skips redundant direct consumer discovery.

### Task 3.3: Add assay dispatch at User Gate [M]

**Files to modify:**
- `skills/migrate/SKILL.md` — User Gate section (after Phase 5)

**Changes:**
1. Before presenting the migration plan to the user, dispatch assay:
   ```
   /assay
     question: "Is this migration approach the best strategy for <target>?"
     context: { recon brief + migration analysis + blast radius summary }
     decision_type: "strategy"
   ```
2. Include assay's output in the User Gate presentation:
   - **Strategy Confidence:** [from assay]
   - **Kill Criteria:** [from assay — when to abort this migration approach]
   - **Missing Information:** [from assay — what would increase confidence]
3. Add fallback: "If assay fails, present plan without structured evaluation (existing behavior)."

**Done when:** User Gate includes assay's strategy evaluation with kill criteria.

### Task 3.4: Update migrate Integration table [S]

**Files to modify:**
- `skills/migrate/SKILL.md` — Integration section

**Changes:**
1. Add recon (Phase 0, consumer-registry) and assay (User Gate, strategy evaluation) rows to the Integration table

**Done when:** Integration table reflects actual dispatch.

---

## Wave 4: Audit Integration

### Task 4.1: Replace audit scoping agent with recon dispatch [M]

**Files to modify:**
- `skills/audit/SKILL.md` — Phase 1: Scoping (Code Path) section

**Changes:**
1. Replace the Sonnet Explore scoping agent dispatch with recon dispatch:
   ```
   /recon
     task: "Subsystem manifest for audit: <subsystem name>"
     scope: "<subsystem-path or cartographer-identified boundary>"
     modules: ["subsystem-manifest"]
   ```
2. Delete the scoping agent dispatch instructions (the 5-step scoping process in the Code Path)
3. Replace with: "Dispatch recon with subsystem-manifest module. Parse the manifest from recon's brief to produce the file list + role descriptions for the USER GATE."
4. Keep the USER GATE unchanged — user still confirms the manifest
5. Keep the cartographer consult fallback logic: if no cartographer data, recon explores from scratch
6. Add fallback: "If recon fails, dispatch the scoping exploration agent (existing behavior preserved in audit-scoping-prompt.md as fallback template)."
7. Note: do NOT delete `audit-scoping-prompt.md` — keep it as the fallback template. Mark it with a comment: `<!-- FALLBACK: used when recon dispatch fails. Primary path is /recon with subsystem-manifest. -->`

**Done when:** Code audits dispatch recon for scoping. Scoping agent is fallback-only.

### Task 4.2: Update audit Compaction Recovery [S]

**Files to modify:**
- `skills/audit/SKILL.md` — Compaction Recovery section (Code Recovery)

**Changes:**
1. Add: if recon brief exists in scratch directory, Phase 1 scoping is complete (same as current `manifest.md` check)
2. Write recon's subsystem manifest to `scratch/<run-id>/manifest.md` in the same format the scoping agent currently produces — this makes all downstream code (Phase 2, recovery) work without modification

**Done when:** Compaction recovery handles recon-sourced manifests.

### Task 4.3: Update audit Integration section [S]

**Files to modify:**
- `skills/audit/SKILL.md` — Add recon to integration notes (no formal Integration table exists, add one)

**Done when:** Audit documents recon dependency.

---

## Wave 5: Documentation Updates (non-integrated consumers)

### Task 5.1: Update recon "Called by" list [S]

**Files to modify:**
- `skills/recon/SKILL.md` — Integration section (line 561)

**Changes:**
Update from:
```
**Called by:** /design, /build, /debugging, /migrate, /audit, /prospector (supplementary), /project-init
```
To:
```
**Called by:** /design (Phase 2 context + impact-analysis), /spec (per-ticket investigation + impact-analysis), /migrate (Phase 0 + consumer-registry), /audit (Phase 1 code scoping + subsystem-manifest)
**Not called by (investigated, not a fit):** /debugging (specialized investigation pipeline), /build (inherits via /design), /prospector (organic exploration is different), /project-init (bootstraps cartographer, complementary purpose)
```

**Done when:** Called by list matches reality.

### Task 5.2: Update assay "Called by" table [S]

**Files to modify:**
- `skills/assay/SKILL.md` — Integration > Called by table (lines 183-190)

**Changes:**
Update the table to reflect actual integration:
- `/design` — `architecture` — Recon brief + cascading decisions — **Evaluator generates** (actual)
- `/spec` — `architecture` — Recon brief + cascading decisions — **Evaluator generates** (actual, autonomous)
- `/migrate` — `strategy` — Recon brief + migration analysis — **Evaluator generates** (actual)
- `/debugging` — REMOVE (not integrated; hypothesis evaluation uses quality-gate, not assay)
- `/prospector` — REMOVE (not integrated; competing design evaluation is more sophisticated)

**Done when:** Called by table matches reality.

### Task 5.3: Update debugging, build, prospector, project-init integration sections [S]

**Files to modify:**
- `skills/debugging/SKILL.md` — Integration/Related skills section
- `skills/build/SKILL.md` — Integration section
- `skills/prospector/SKILL.md` — Integration section
- `skills/project-init/SKILL.md` — Integration section

**Changes:**
- Debugging: Add note "Does not dispatch /recon or /assay — uses specialized investigation agents. See #147 for rationale."
- Build: Add note "Inherits recon/assay context through /design (Phase 1). No direct dispatch."
- Prospector: Add note "Does not dispatch /recon — organic exploration serves a different purpose. Does not dispatch /assay — competing design evaluation is more specialized. See #147 for rationale."
- Project-init: Add note "Bootstraps cartographer data that /recon consults. Complementary, not overlapping. See #147 for rationale."

**Done when:** All non-integrated consumers document why they do not dispatch recon/assay.

---

## Summary

| Wave | Tasks | Complexity | Files Modified |
|---|---|---|---|
| 0 | 2 tasks (validation) | 2x S | recon SKILL.md, assay SKILL.md, dispatch-convention.md |
| 1 | 5 tasks (design) | 1S + 3M + 1S | design/SKILL.md, design/investigation-prompts.md |
| 2 | 4 tasks (spec) | 1S + 3M | spec/SKILL.md, spec/spec-writer-prompt.md |
| 3 | 4 tasks (migrate) | 1S + 3M | migrate/SKILL.md, migrate/blast-radius-mapper-prompt.md |
| 4 | 3 tasks (audit) | 1M + 2S | audit/SKILL.md |
| 5 | 3 tasks (docs) | 3x S | recon/SKILL.md, assay/SKILL.md, debugging/SKILL.md, build/SKILL.md, prospector/SKILL.md, project-init/SKILL.md |

**Total: 21 tasks. 7M + 14S. 13 files modified.**

## Sequencing Rationale

- **Wave 0 first:** Validates that no API changes are needed before touching consumers.
- **Wave 1 before Wave 2:** Spec mirrors design's integration. Design is the template; spec follows.
- **Wave 3 independent of Wave 1-2:** Migrate's integration (consumer-registry) is structurally different from design/spec's (context enrichment).
- **Wave 4 independent of Wave 1-3:** Audit's integration (subsystem-manifest scoping replacement) is self-contained.
- **Wave 5 last:** Documentation updates reference the completed integrations.
