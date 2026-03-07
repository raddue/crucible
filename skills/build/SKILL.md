---
name: build
description: Use when starting any feature development, building new functionality, implementing a design, or going from idea to working code. Triggers on "build", "implement", "add feature", or any task requiring design-through-execution.
---

# Build

## Overview

End-to-end development pipeline: interactive design, autonomous planning with adversarial review, team-based execution with per-task code and test review. One command, idea to completion.

**Announce at start:** "I'm using the build skill to run the full development pipeline."

**Guiding principle:** Quality over velocity. This pipeline produces correct, well-integrated, maintainable output — even if slower. Parallel execution is available for independent work, but sequential with quality gates is the default.

## Phase 1: Brainstorm (Interactive)

- **Model:** Opus (creative/architectural work needs the best model)
- **Mode:** Interactive with the user
- **RECOMMENDED SUB-SKILL:** Use crucible:forge (feed-forward mode) — consult past lessons before starting
- **RECOMMENDED SUB-SKILL:** Use crucible:cartographer (consult mode) — review codebase map for structural awareness
- **REQUIRED SUB-SKILL:** Use crucible:design
- Follow design skill for design refinement, section-by-section validation, and saving the design doc
- **OVERRIDE:** When brainstorming completes and the design doc is saved, do NOT follow design's "Implementation" section (do not chain into planning or worktree from there). Return control to this build skill — Phase 2 handles planning with its own subagent-based approach.
- Phase ends when user approves the design (says "go", "looks good", "proceed", etc.)
- **Everything after this point is autonomous** — tell the user: "Design approved. Starting autonomous pipeline — I'll only interrupt for escalations."

### Step 2: Innovate and Red-Team the Design

After the user approves the design and before starting Phase 2:

1. **Innovate:** Dispatch `crucible:innovate` on the design doc. Plan Writer incorporates the proposal.
2. **Red-team:** Dispatch `crucible:red-team` on the (potentially updated) design doc. Iterates until clean or stagnation.
3. If the red team requires changes, the Plan Writer updates the design doc and re-commits.
4. Design doc is now finalized — proceed to acceptance tests.

### Step 3: Generate Acceptance Tests (RED)

Before planning, define "done" with executable tests:

1. Dispatch an **Acceptance Test Writer** subagent (Opus) using `./acceptance-test-writer-prompt.md`
   - Input: finalized design doc (especially acceptance criteria)
   - Output: integration-level test file(s) that verify feature behavior end-to-end
2. Run the acceptance tests — verify they **FAIL** (the feature doesn't exist yet)
   - If tests pass: something is wrong — investigate before proceeding
   - If tests error (won't compile): this is expected in typed languages — note which tests exist and what they verify. They become the first implementation task.
3. Commit: `test: add acceptance tests for [feature] (RED)`

These tests define the feature-level RED-GREEN cycle that wraps the entire pipeline. The pipeline is done when these tests pass.

## Phase 2: Plan (Autonomous)

### Step 1: Write the Plan

Dispatch a **Plan Writer** subagent (Opus):

- Read the design doc produced in Phase 1 and the acceptance tests from Step 3
- Write an implementation plan following the `crucible:planning` format
- If acceptance tests couldn't compile (typed language), Task 1 should create the interfaces/stubs needed for them to compile and fail correctly
- Include per-task metadata: Files (with count), Complexity (Low/Medium/High), Dependencies
- Save to `docs/plans/YYYY-MM-DD-<topic>-implementation-plan.md`
- Plan tasks should be scoped to 2-3 per subagent, ~10 files max (context budget awareness)

Use `./plan-writer-prompt.md` template for the dispatch prompt.

### Step 2: Review the Plan

Dispatch a **Plan Reviewer** subagent:

Reviewer model selection:
- Plan touches **4+ systems** or has **10+ tasks** → Opus
- Plan touches **1-3 systems** with **<10 tasks** → Sonnet
- When in doubt → Opus

Review protocol (iterative):
- Dispatch Plan Reviewer to check plan against design doc
- If issues found: record issue count, dispatch Plan Writer to revise
- Dispatch NEW fresh Plan Reviewer on revised plan (no anchoring)
- Compare issue count to prior round:
  - Strictly fewer issues → progress, loop again
  - Same or more issues → stagnation, **escalate to user** with findings from both rounds
- Loop until plan passes with no issues
- **Architectural concerns bypass the loop** — immediate escalation regardless of round

Use `./plan-reviewer-prompt.md` template for the dispatch prompt.

### Step 3: Innovate and Red-Team the Plan

**After the plan passes review:**

1. **Innovate:** Dispatch `crucible:innovate` on the approved plan. Plan Writer incorporates the proposal into the plan.
2. **Red-team:** Dispatch `crucible:red-team` on the (potentially updated) plan. Provides the plan and design doc as context.

The red-team skill handles the iterative loop — fresh Devil's Advocate each round, stagnation detection, escalation. See `crucible:red-team` for details.

## Phase 3: Execute (Autonomous, Team-Based)

### Step 0: Load Module Context for Subagents

- **RECOMMENDED SUB-SKILL:** Use crucible:cartographer (load mode) — when dispatching implementers and reviewers, paste relevant module files, conventions.md, and landmines.md into their prompts

### Step 1: Create Team and Task List

Create a team using `TeamCreate`:
```
team_name: "build-<feature-name>"
description: "Building <feature description>"
```

Read the approved plan. Create tasks via `TaskCreate` for each plan task, including:
- Subject from plan task title
- Description with full plan task text (subagents should never read the plan file)
- Dependencies via `TaskUpdate` with `addBlockedBy`

### Step 2: Analyze Dependencies and Execution Order

Before dispatching:
1. Map the dependency graph from plan task metadata
2. Identify independent tasks (no shared files, no sequential dependencies)
3. Group into execution waves — independent tasks parallel, dependent tasks sequential
4. Assess complexity per task for reviewer model selection

### Step 3: Execute Tasks

For each task (or wave of parallel tasks):

1. Mark task `in_progress` via `TaskUpdate`
2. Spawn **Implementer** teammate (Opus) via Task tool with `team_name` and `subagent_type="general-purpose"`
   - Use `./build-implementer-prompt.md` template
   - Pass full task text, file paths, project conventions
   - Implementer follows TDD, writes tests, runs tests, commits, self-reviews
3. When Implementer reports completion, spawn **Reviewer** teammate
   - Use `./build-reviewer-prompt.md` template

#### Reviewer Model Selection (Lead Decides Per-Task)

| Task Complexity | Reviewer Model |
|----------------|----------------|
| Low (1-3 files, straightforward) | Sonnet |
| Medium (3-6 files, some cross-system) | Lead decides (default Opus) |
| High (6+ files, refactoring, deep chains) | Opus |
| When in doubt | Opus |

#### Two-Pass Review Cycle

Each task gets TWO review passes before completion:

```dot
digraph review {
  "Implementer builds + tests" -> "Pass 1: Code Review";
  "Pass 1: Code Review" -> "Implementer fixes code findings";
  "Implementer fixes code findings" -> "Pass 2: Test Review";
  "Pass 2: Test Review" -> "Implementer fixes test findings";
  "Implementer fixes test findings" -> "Task complete";
}
```

**Pass 1 — Code Review:** Architecture, patterns, correctness, wiring (actually connected, not just existing?)

**Pass 2 — Test Review:** Stale tests? Missing coverage? Tests need updating? Dead tests to delete? Edge cases untested?

#### Iterative Review Loop

Each review pass (code and test) uses the iterative loop:
- After fixes, dispatch a **NEW fresh Reviewer** (no anchoring to prior findings)
- Track issue count between rounds
- **Strictly fewer issues** → progress, loop again
- **Same or more issues** → stagnation, **escalate to user**
- Loop until clean
- Architectural concerns → **immediate escalation** regardless of round

#### Verification Gates

After each wave completes:
1. Run full test suite (not just current wave's tests)
2. Check compilation
3. Failures → identify which task caused regression before fixing
4. Clean → proceed to next wave

#### Architectural Checkpoint

For plans with 10+ tasks, at ~50% completion or after a major subsystem:
- Dispatch architecture reviewer using `./architecture-reviewer-prompt.md`
- Design drift → escalate to user
- Minor concerns → adjust prompts for remaining tasks
- All clear → continue

## Phase 4: Completion

After all tasks complete:
1. Run acceptance tests from Phase 1 Step 3 — verify they **PASS** (GREEN)
   - If any fail: implementation is incomplete. Identify what's missing, dispatch implementer to fix, re-run.
   - If all pass: feature is verifiably done. Proceed.
2. Run full test suite (unit + integration)
3. **REQUIRED SUB-SKILL:** Use crucible:code-review on full implementation (iterative until clean)
4. **REQUIRED SUB-SKILL:** Use crucible:red-team on full implementation (iterative until clean)
5. **RECOMMENDED SUB-SKILL:** Use crucible:forge (retrospective mode) — capture what happened vs what was planned
6. **RECOMMENDED SUB-SKILL:** Use crucible:cartographer (record mode) — persist any new codebase knowledge discovered during build
7. Compile summary: what was built, acceptance tests passing, review findings addressed, concerns
8. Report to user
9. **REQUIRED SUB-SKILL:** Use crucible:finish

## Escalation Triggers (Any Phase)

**STOP and ask the user when:**
- Architectural concerns in plan or code review
- Review loop stagnation (same or more issues after fixes — any phase)
- Test suite failures not obviously fixable
- Multiple teammates fail on different tasks
- Teammate reports context pressure at 50%+ with significant work remaining

**Minor issues:** Log, work around, include in final report.

## What the Lead Should NOT Do

- Implement code (dispatch implementers)
- Read large files (spawn Haiku researcher)
- Debug failing tests (dispatch implementer)
- Make architectural decisions (escalate to user)

## Context Management

- **One task per agent** — always spawn a fresh implementer for each task. Never send a second task to a running agent via SendMessage. Reusing agents accumulates context and causes exhaustion.
- "2-3 per subagent, ~10 files max" refers to **plan design** — group small steps into one task at planning time, not sequential dispatch to a running agent
- Lead stays thin — coordination only
- All important state on disk (plan files, task list)
- Teammates report at 50%+ context usage
- Lead compaction acceptable — task list is source of truth

## Prompt Templates

- `./acceptance-test-writer-prompt.md` — Phase 1 acceptance test generation
- `./plan-writer-prompt.md` — Phase 2 plan writer dispatch
- `./plan-reviewer-prompt.md` — Phase 2 plan reviewer dispatch
- `./build-implementer-prompt.md` — Phase 3 implementer dispatch
- `./build-reviewer-prompt.md` — Phase 3 reviewer dispatch
- `./architecture-reviewer-prompt.md` — Mid-plan checkpoint

Red-team and innovate prompts live in their respective skills:
- `crucible:red-team` — `skills/red-team/red-team-prompt.md`
- `crucible:innovate` — `skills/innovate/innovate-prompt.md`

## Integration

**Required sub-skills:**
- **crucible:design** — Phase 1
- **crucible:finish** — Phase 4
- **crucible:red-team** — Adversarial review at each quality gate
- **crucible:innovate** — Creative enhancement before red-teaming

**Recommended sub-skills:**
- **crucible:forge** — Feed-forward at Phase 1 start, retrospective at Phase 4 completion
- **crucible:cartographer** — Consult at Phase 1 start, load at Phase 3 dispatches, record at Phase 4

**Implementer sub-skills:**
- **crucible:test-driven-development** — TDD within each task
