---
ticket: "#62"
epic: "none"
title: "Risk-Tiered Review Depth for Build Pipeline Tasks"
date: "2026-03-23"
source: "spec"
---

# Risk-Tiered Review Depth for Build Pipeline Tasks

## Current State Analysis

### Phase 3 Per-Task Review Flow

Every task in the build pipeline traverses the same 10-step review gauntlet regardless of risk or complexity (`skills/build/SKILL.md`, lines 429-441):

```
Implementer builds + tests
  -> De-sloppify cleanup
  -> Pass 1: Code Review
  -> Implementer fixes code findings
  -> Pass 2: Test Quality Review
  -> Implementer fixes test findings
  -> Test Alignment Audit (crucible:test-coverage)
  -> Test Gap Writer
  -> Adversarial Tester
  -> Task complete
```

### Existing Per-Task Metadata

The plan writer already computes three metadata fields per task (`skills/build/plan-writer-prompt.md`, lines 26-36):

- **Files:** explicit file list with count (e.g., `file1.cs, file2.cs (2 files)`)
- **Complexity:** Low | Medium | High, with defined thresholds:
  - Low: 1-3 files, straightforward changes, no cross-system interaction
  - Medium: 3-6 files, some inheritance or cross-system interaction
  - High: 6+ files, refactoring, deep inheritance chains, cross-system wiring
- **Dependencies:** explicit task dependency list

### Existing Reviewer Model Selection

The lead already selects reviewer models per-task based on complexity (`skills/build/SKILL.md`, lines 416-423):

| Task Complexity | Reviewer Model |
|----------------|----------------|
| Low (1-3 files, straightforward) | Sonnet |
| Medium (3-6 files, some cross-system) | Lead decides (default Opus) |
| High (6+ files, refactoring, deep chains) | Opus |

### Existing Skip Conditions

Two Phase 3 steps already have conditional skip logic:

1. **Test Alignment Audit** (`skills/build/SKILL.md`, line 474): "Skip this step if the task made no behavioral source changes (only `.md`, `.json`, config files)."
2. **Adversarial Tester** (`skills/build/SKILL.md`, lines 513-516): Skip when diff contains no behavioral source files or no tests were written during implementation (pure scaffolding).
3. **Test Gap Writer** (`skills/build/SKILL.md`, line 498): "Skip this step if the Pass 2 test reviewer reported zero missing coverage gaps."

### The Problem

A trivial 2-file wiring task (add a config entry, register a new service) goes through cleanup, two-pass code review, test-coverage audit, test gap writer, and adversarial tester -- the same treatment as a complex cross-system refactoring. For low-risk tasks, most review agents return "nothing found," consuming Opus context windows and wall-clock time for zero signal.

For a typical 8-task feature with 3 low-risk, 3 medium-risk, and 2 high-risk tasks, this means approximately 21 unnecessary subagent dispatches (~26% of total), adding 40-90 minutes of pipeline time with no quality benefit.

## Target State

### Review Tier System

Each task receives a **review tier** assignment (Tier 1, 2, or 3) computed by the plan writer and validated by the plan reviewer. The tier gates which Phase 3 review steps execute for that task.

### Tier Definitions and Review Pipelines

**Tier 1 (Light) -- Low-risk wiring/scaffolding/config:**

- Criteria: 1-3 files, Low complexity, no cross-system dependencies, no cartographer landmine proximity
- Pipeline: Implementer -> De-sloppify cleanup -> Single-pass code review (code only, no test pass)
- Skipped: Pass 2 (test quality review), test alignment audit, test gap writer, adversarial tester
- Reviewer model: Sonnet (per existing Low complexity rule)

**Tier 2 (Standard) -- Moderate behavioral changes within one system:**

- Criteria: 3-6 files, Medium complexity, single-system behavioral changes, no cartographer landmine proximity
- Pipeline: Implementer -> De-sloppify cleanup -> Pass 1: Code review (iterative) -> Implementer fixes -> Pass 2: Test quality review (single pass, non-iterative) -> Adversarial tester
- Skipped: Test alignment audit, test gap writer
- Reviewer model: Lead decides (default Opus, per existing Medium complexity rule)

**Tier 3 (Heavy) -- High-risk, cross-system, or landmine-adjacent:**

- Criteria: 6+ files, High complexity, cross-system dependencies, new public API surface, OR cartographer landmine proximity
- Pipeline: Full current pipeline (no changes)
- Skipped: Nothing
- Reviewer model: Opus (per existing High complexity rule)

### Tier Classification Rules

The review tier is computed deterministically from existing plan metadata plus one new signal:

1. **Start with complexity-based tier:** Low -> Tier 1, Medium -> Tier 2, High -> Tier 3
2. **Escalate for cross-system dependencies:** If task dependencies span multiple systems/modules -> minimum Tier 2
3. **Escalate for landmine proximity:** If any task file falls within a directory containing a cartographer landmine entry -> Tier 3
4. **Escalate for new public API:** If the task introduces a new public interface, endpoint, or event -> minimum Tier 2
5. **Tier never decreases:** Escalation rules can only raise the tier, never lower it

### Runtime Tier Escalation

The orchestrator can escalate a task's tier during execution if the implementer reports unexpected complexity. This handles cases where the plan writer underestimated risk. The escalation is one-directional (up only) and triggers the additional review steps for the new tier. The orchestrator logs the escalation in the decision journal with reason.

## Key Decisions

### Decision 1: Tier computed by plan writer, not orchestrator

**Choice:** The plan writer computes the review tier as part of per-task metadata, and the plan reviewer validates tier assignments.

**Reasoning:** The plan writer already has all the inputs (file count, complexity, dependencies) and the plan reviewer already validates per-task metadata. Adding a `Review-Tier` field to the existing metadata block is a natural extension. Having the orchestrator compute tiers at execution time would require it to re-derive information already available in the plan, adding complexity to the lead agent's coordination logic.

**Alternative rejected:** Orchestrator computes tier at dispatch time. Rejected because it adds complexity to the lead (which should stay thin per `skills/build/SKILL.md` line 688) and prevents the plan reviewer from catching tier misclassifications.

### Decision 2: Tier 1 retains de-sloppify cleanup

**Choice:** Even Tier 1 tasks go through de-sloppify cleanup before the single-pass code review.

**Reasoning:** Cleanup is cheap (one agent, bounded scope) and catches debug logging, commented-out code, and over-defensive checks that even simple tasks can produce. The cleanup prompt (`skills/build/cleanup-prompt.md`) is specifically designed for removal-only work and has a fast return path ("No cleanup needed") when nothing is found.

**Alternative rejected:** Skip cleanup for Tier 1. Rejected because the cost is low and the cleanup catches sloppiness that a single-pass code review might accept (reviewer focuses on correctness, not cleanup categories).

### Decision 3: Tier 2 gets single-pass test review (non-iterative)

**Choice:** Tier 2 tasks get Pass 2 (test quality review) but as a single non-iterative pass. Findings are reported but do not enter the iterative fix-review loop.

**Reasoning:** Medium-complexity tasks benefit from a test quality sanity check, but the iterative loop (dispatch fresh reviewer, compare issue counts, loop until clean) is the expensive part. A single pass catches obvious test quality issues while skipping 2-3 additional reviewer dispatches per task. If the single pass surfaces critical findings, the orchestrator can escalate the task to Tier 3 for full treatment.

**Alternative rejected:** Skip test review entirely for Tier 2. Rejected because medium-complexity tasks (3-6 files, some cross-system interaction) can have meaningful test quality gaps that a single pass catches cheaply.

### Decision 4: Cartographer landmine proximity forces Tier 3

**Choice:** Any task touching files in a directory with known cartographer landmines is automatically Tier 3.

**Reasoning:** Landmines represent historically problematic areas where previous builds encountered unexpected failures. These areas deserve the full review gauntlet precisely because they have a demonstrated history of producing subtle bugs. The cost of over-reviewing a landmine-adjacent task is far lower than the cost of under-reviewing it and letting a defect through. Cartographer landmine data is already loaded for implementer dispatch (`skills/build/SKILL.md`, lines 327-340), so the proximity check adds no new data dependencies.

**Alternative rejected:** Landmines escalate to minimum Tier 2 instead of Tier 3. Rejected because landmines exist precisely to flag areas where the standard review depth was insufficient in the past.

### Decision 5: Phase 4 gates remain unchanged (safety net)

**Choice:** Phase 4 full-implementation gates (code-review, inquisitor, quality-gate) are not affected by per-task tier assignments.

**Reasoning:** Phase 4 reviews the complete feature diff, not individual tasks. It catches integration issues, cross-task regressions, and anything the per-task reviews missed. This provides a safety net that makes the per-task tier system low-risk: the worst case is that a Tier 1 task introduces an issue that the Phase 4 full-feature review catches. The Phase 4 safety net is what makes the entire tier system viable.

### Decision 6: No new prompt templates, skills, or subagent types

**Choice:** Implement entirely through modifications to existing files: `SKILL.md`, `plan-writer-prompt.md`, and `plan-reviewer-prompt.md`.

**Reasoning:** The tier system gates which existing steps execute, not how those steps work. The reviewer prompt (`skills/build/build-reviewer-prompt.md`) already supports both passes; the orchestrator simply dispatches fewer passes for lower tiers. No behavioral changes to any agent -- only routing changes in the orchestrator.

## Migration/Implementation Path

### Phase 1: Plan Writer Metadata Extension

Add `Review-Tier` field to per-task metadata in `plan-writer-prompt.md`. Define the classification algorithm using existing metadata fields (Files count, Complexity, Dependencies) plus cartographer landmine proximity.

### Phase 2: Plan Reviewer Validation

Add tier validation to the plan reviewer checklist in `plan-reviewer-prompt.md`. The reviewer checks that tier assignments are consistent with the classification rules and flags any tier that appears under-classified.

### Phase 3: Orchestrator Routing

Add tier-based routing logic to Phase 3 Step 3 in `SKILL.md`. The orchestrator reads the `Review-Tier` field from each task's metadata and dispatches only the review steps appropriate for that tier. Add runtime escalation logic for when implementers report unexpected complexity.

### Rollout Safety

The change is inherently safe because:

1. Phase 4 gates are unchanged -- they catch anything per-task reviews miss
2. Tier escalation is one-directional -- tasks can only get more review, never less
3. The plan reviewer validates tier assignments -- misclassifications are caught before execution
4. The orchestrator can escalate at runtime -- unexpected complexity triggers full review

## Risk Areas

### Risk 1: Plan writer misclassifies a high-risk task as Tier 1

**Likelihood:** Low. The classification rules are deterministic based on file count, complexity, and dependencies -- all of which the plan writer already computes.

**Mitigation:** Plan reviewer validates tier assignments. Phase 4 full-implementation gates catch anything that slips through.

**Residual risk:** If both the plan writer and plan reviewer miss a misclassification AND the Phase 4 gates miss the resulting defect. This requires three independent failures.

### Risk 2: Cartographer landmine data is unavailable

**Likelihood:** Medium. Cartographer is a recommended (not required) sub-skill, so landmine data may not exist for all projects.

**Mitigation:** When cartographer data is unavailable, the landmine proximity check is simply skipped. Tasks are classified based on file count, complexity, and dependencies alone. This is strictly more conservative than the current system (which has no tier gating at all), so unavailable landmine data does not reduce review depth below the status quo.

### Risk 3: Runtime escalation not triggered when needed

**Likelihood:** Low. The escalation trigger is the implementer reporting unexpected complexity, which is already part of the implementer prompt (`skills/build/build-implementer-prompt.md`, lines 116-118: "Message the lead if you encounter unexpected findings or blockers").

**Mitigation:** The implementer's existing communication protocol already covers this. The orchestrator simply adds tier escalation as a response to "unexpected complexity" reports.

### Risk 4: Tier definitions become stale as the pipeline evolves

**Likelihood:** Medium (long-term). If new review steps are added to Phase 3, the tier routing table must be updated to include them.

**Mitigation:** The tier routing table is defined in one place (`SKILL.md` Phase 3 Step 3). Any change to the Phase 3 review flow naturally requires updating the routing table. Document this coupling explicitly.

## Acceptance Criteria

1. **Plan writer computes `Review-Tier`:** Every task in a generated plan includes a `Review-Tier: 1|2|3` field in its metadata block, computed from Files count, Complexity, Dependencies, and landmine proximity.

2. **Tier classification is deterministic:** Given the same task metadata and landmine data, the tier assignment is always the same. No discretionary "lead decides" element in tier assignment (only in runtime escalation).

3. **Plan reviewer validates tiers:** The plan reviewer's checklist includes tier validation. A task with High complexity classified as Tier 1 is flagged as a deficiency.

4. **Tier 1 pipeline is shorter:** A Tier 1 task dispatches exactly: implementer, cleanup agent, single-pass code reviewer. No test reviewer, test-coverage, test gap writer, or adversarial tester dispatches occur.

5. **Tier 2 pipeline is shorter:** A Tier 2 task dispatches exactly: implementer, cleanup agent, iterative code reviewer, single-pass test reviewer, adversarial tester. No test-coverage audit or test gap writer dispatches occur.

6. **Tier 3 pipeline is unchanged:** A Tier 3 task follows the exact same review flow as the current pipeline (all steps).

7. **Runtime escalation works:** When the orchestrator receives an "unexpected complexity" report from an implementer on a Tier 1 or Tier 2 task, it escalates the task's tier and dispatches the additional review steps for the new tier.

8. **Phase 4 is unmodified:** Phase 4 completion gates (code-review, inquisitor, quality-gate) execute identically regardless of per-task tier assignments.

9. **Decision journal logs tier decisions:** Each tier routing decision and any runtime escalation is logged to the decision journal (`/tmp/crucible-decisions-<session-id>.log`) with the `review-tier` decision type.

10. **Metrics capture tier distribution:** The session metrics summary includes a breakdown of tasks by tier (e.g., "Tasks: 3 Tier 1, 3 Tier 2, 2 Tier 3") and total subagent dispatches saved vs. the all-Tier-3 baseline.
