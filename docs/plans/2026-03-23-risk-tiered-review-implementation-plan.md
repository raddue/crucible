---
ticket: "#62"
epic: "none"
title: "Risk-Tiered Review Depth for Build Pipeline Tasks"
date: "2026-03-23"
source: "spec"
---

# Implementation Plan: Risk-Tiered Review Depth for Build Pipeline Tasks

## Task 1: Add Review-Tier Field to Plan Writer Prompt

- **Files:** `skills/build/plan-writer-prompt.md` (1 file)
- **Complexity:** Low
- **Dependencies:** None
- **Review-Tier:** 1

### Description

Extend the per-task metadata block in the plan writer prompt template to include a `Review-Tier` field. Add the tier classification algorithm and the tier definition reference table.

### Changes

In `skills/build/plan-writer-prompt.md`, within the "Per-Task Metadata (REQUIRED)" section (lines 26-36):

1. Add `Review-Tier` to the required metadata block example:

```markdown
### Task N: [Description]
- **Files:** file1.cs, file2.cs (N files)
- **Complexity:** Low | Medium | High
- **Dependencies:** Task X, Task Y (or "None")
- **Review-Tier:** 1 | 2 | 3
```

2. After the existing complexity tiers block (lines 33-36), add the review tier classification rules:

```markdown
Review tier classification (compute for every task):
- **Tier 1 (Light):** Low complexity AND 1-3 files AND no cross-system dependencies AND no cartographer landmine proximity. Pipeline: implementer -> cleanup -> single-pass code review.
- **Tier 2 (Standard):** Medium complexity OR 3-6 files OR single-system behavioral changes. Not eligible if any Tier 3 trigger applies. Pipeline: implementer -> cleanup -> iterative code review -> single-pass test review -> adversarial tester.
- **Tier 3 (Heavy):** High complexity OR 6+ files OR cross-system dependencies OR new public API surface OR cartographer landmine proximity. Pipeline: full current review flow.

Escalation rules (tier can only increase, never decrease):
- Cross-system dependencies -> minimum Tier 2
- New public API (interface, endpoint, event) -> minimum Tier 2
- Cartographer landmine proximity (any task file in a landmine directory) -> Tier 3
```

3. Add tier to the "Before Reporting Back" checklist (line 104):

```markdown
- Does every task have a Review-Tier computed from the classification rules?
- Are Review-Tier assignments consistent with the tier criteria (no High-complexity task at Tier 1)?
```

### Verification

- Read the updated prompt template and confirm the `Review-Tier` field is present in the metadata example block.
- Confirm the classification rules are unambiguous and deterministic (no "lead decides" language in tier assignment).
- Confirm the checklist includes tier validation.

---

## Task 2: Add Tier Validation to Plan Reviewer Prompt

- **Files:** `skills/build/plan-reviewer-prompt.md` (1 file)
- **Complexity:** Low
- **Dependencies:** Task 1
- **Review-Tier:** 1

### Description

Extend the plan reviewer prompt template to validate review tier assignments against the classification rules.

### Changes

In `skills/build/plan-reviewer-prompt.md`, within the "Task Quality" checklist (lines 29-38):

1. Add tier validation checks after the existing metadata check (line 29):

```markdown
- Does every task have a Review-Tier (1, 2, or 3)?
- Are Review-Tier assignments consistent with the classification rules?
  - No task with High complexity or 6+ files at Tier 1 or 2
  - No task with cross-system dependencies at Tier 1
  - No task introducing a new public API at Tier 1
  - Tasks near cartographer landmines must be Tier 3
- Are any tasks under-tiered? (err toward higher tier when uncertain)
```

2. In the "Report Format" section (lines 53-60), add tier findings to the task quality issues output:

```markdown
- **Tier classification issues:** [Tasks with incorrect or questionable tier assignments]
```

### Verification

- Read the updated prompt template and confirm tier validation appears in the Task Quality checklist.
- Confirm the report format includes a tier-specific findings field.

---

## Task 3: Add Tier-Based Routing Logic to SKILL.md Phase 3

- **Files:** `skills/build/SKILL.md` (1 file)
- **Complexity:** Medium
- **Dependencies:** Task 1, Task 2
- **Review-Tier:** 2

### Description

Modify the Phase 3 execution section of `SKILL.md` to route tasks through different review pipelines based on their `Review-Tier` metadata. This is the core change: the orchestrator reads the tier and dispatches only the appropriate review steps.

### Changes

#### 3a: Add Tier Routing Table

In `skills/build/SKILL.md`, after the "Two-Pass Review Cycle" section (after line 441), insert a new section:

```markdown
#### Review Tier Routing

Each task's `Review-Tier` (from the plan) determines which review steps execute. Phase 4 full-implementation gates are NOT affected by per-task tiers.

| Step | Tier 1 | Tier 2 | Tier 3 |
|------|--------|--------|--------|
| Implementer | Yes | Yes | Yes |
| De-sloppify cleanup | Yes | Yes | Yes |
| Pass 1: Code review | Single pass | Iterative | Iterative |
| Implementer fixes (code) | If findings | If findings | If findings |
| Pass 2: Test quality review | SKIP | Single pass (non-iterative) | Iterative |
| Implementer fixes (test) | SKIP | If critical findings only | If findings |
| Test alignment audit | SKIP | SKIP | Yes |
| Test gap writer | SKIP | SKIP | Yes |
| Adversarial tester | SKIP | Yes | Yes |

**Tier 1 "single pass" code review:** Dispatch one reviewer. If findings are Clean, task is complete. If findings include Critical or Important issues, dispatch implementer to fix, then the task is complete (no re-review). If findings include an Architectural Concern, escalate as normal.

**Tier 2 "single pass" test review:** Dispatch one test quality reviewer. Report findings but do NOT enter the iterative review loop. If the single pass surfaces Critical findings, escalate the task to Tier 3 for full iterative treatment.

**Tier 2 "iterative" code review:** Same as current behavior -- fresh reviewer each round, track issue count, loop until clean or stagnation.
```

#### 3b: Add Runtime Tier Escalation

After the tier routing table, add:

```markdown
#### Runtime Tier Escalation

The orchestrator may escalate a task's review tier during execution. Escalation is one-directional (up only).

**Triggers:**
- Implementer reports unexpected complexity or cross-system interaction not anticipated in the plan
- Single-pass reviewer (Tier 1 code review or Tier 2 test review) reports Critical findings
- Implementer touches significantly more files than the plan specified

**Process:**
1. Log escalation to decision journal: `[timestamp] DECISION: review-tier | choice=escalate T1->T2 | reason=<trigger> | alternatives=none`
2. Execute the additional review steps for the new tier (from the point where the current tier's pipeline diverges)
3. Update the task status display to show the escalated tier
```

#### 3c: Update Decision Journal Types

In the "Pipeline Decision Journal" section (around line 659), add a new decision type to the list:

```markdown
- `review-tier` — tier assignment read from plan, runtime escalation reason if applicable
```

#### 3d: Update Session Metrics

In the "Session Metrics" section (around line 636), add tier distribution to the completion summary:

```markdown
  Task tiers:           3 Tier 1, 3 Tier 2, 2 Tier 3
  Subagent savings:     ~21 dispatches skipped vs all-Tier-3
```

#### 3e: Modify Step 3 Dispatch Logic

In Phase 3 Step 3 "Execute Tasks" (lines 380-511), modify the task execution flow. The existing numbered steps (1-4) remain, but after step 3 (de-sloppify cleanup), add tier-aware routing:

Replace the unconditional dispatch of reviewer, test-coverage, test-gap-writer, and adversarial-tester with a tier-conditional block:

```markdown
5. **Tier-aware review routing:** Read the task's `Review-Tier` from plan metadata.
   - **Tier 1:** Dispatch single-pass code reviewer (Sonnet). If Clean or Minor-only: task complete. If Critical/Important: dispatch implementer fix, then task complete. If Architectural Concern: escalate.
   - **Tier 2:** Dispatch iterative code review (per existing loop). Then dispatch single-pass test reviewer. If test review surfaces Critical findings, escalate to Tier 3. Then dispatch adversarial tester (per existing logic). Task complete.
   - **Tier 3:** Follow current full pipeline (no changes to existing flow).
```

### Verification

- Read the updated SKILL.md and trace each tier through the routing table to confirm it matches the design doc's tier definitions.
- Confirm the routing table is placed after the existing two-pass review cycle documentation so the full pipeline description remains intact for Tier 3 reference.
- Confirm runtime escalation is documented with specific triggers and process.
- Confirm decision journal and metrics sections are updated.

---

## Task 4: Update Pipeline Status Display for Tier Awareness

- **Files:** `skills/build/SKILL.md` (1 file)
- **Complexity:** Low
- **Dependencies:** Task 3
- **Review-Tier:** 1

### Description

Update the pipeline status file format and task progress table to show each task's review tier, so the user has visibility into which review depth each task is receiving.

### Changes

In `skills/build/SKILL.md`, in the "Skill-Specific Body" section of Pipeline Status (around line 67):

1. Add a `Tier` column to the task progress table:

```markdown
## Task Progress
| # | Task | Tier | Status | Duration |
|---|------|------|--------|----------|
| 1 | Auth middleware | T3 | DONE | 12m |
| 2 | Route handlers | T2 | IN REVIEW (code, pass 1) | 18m+ |
| 3 | Config wiring | T1 | PENDING | -- |
```

2. Add tier summary to the Quality Gates section:

```markdown
## Quality Gates
- Design: PASSED (2 rounds)
- Plan: PASSED (1 round)
- Task tiers: 1x T1, 1x T2, 1x T3
- Code: not yet reached
```

### Verification

- Read the updated status file format and confirm the Tier column is present in the example table.
- Confirm the tier summary is included in the Quality Gates section.

---

## Dependency Graph

```
Task 1 (plan-writer-prompt.md)
  |
  v
Task 2 (plan-reviewer-prompt.md)
  |
  v
Task 3 (SKILL.md -- routing logic)    [depends on Task 1 and Task 2]
  |
  v
Task 4 (SKILL.md -- status display)   [depends on Task 3]
```

Tasks 1 and 2 can execute in parallel (they touch different files). Task 3 depends on both because it references the tier definitions established in Tasks 1-2. Task 4 depends on Task 3 because it extends the same SKILL.md section.

## Execution Waves

- **Wave 1:** Task 1 + Task 2 (parallel -- different files)
- **Wave 2:** Task 3 (sequential -- depends on Wave 1)
- **Wave 3:** Task 4 (sequential -- depends on Task 3)

## Estimated Impact

For Tasks 1-2: ~5-8 lines added to each prompt template.
For Task 3: ~30-40 lines added to SKILL.md (routing table, escalation rules, decision journal type, metrics addition, dispatch logic modification).
For Task 4: ~5 lines modified in SKILL.md status format.

Total: ~45-60 lines across 3 files. Zero new files, zero new skills, zero new prompt templates.
