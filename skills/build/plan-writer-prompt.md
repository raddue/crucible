<!-- DISPATCH: disk-mediated | This template is written to a dispatch file,
     not pasted into the Agent tool prompt. See shared/dispatch-convention.md -->
# Plan Writer Prompt Template

Use this template when dispatching a plan writer subagent in Phase 2.

```
Task tool (general-purpose, model: opus):
  description: "Write implementation plan for [feature]"
  prompt: |
    You are writing an implementation plan for a feature.

    ## Design Document

    [FULL TEXT of the design doc — paste it here, don't make the subagent read the file]

    ## Acceptance Tests

    [FULL TEXT or summary of acceptance tests generated from the design. These define "done" at the feature level. If tests couldn't compile (typed language), Task 1 of your plan should create the interfaces/stubs needed for them to compile and fail correctly.]

    ## Plan Format Requirements

    **REQUIRED SUB-SKILL:** Use crucible:planning — follow its format exactly.
    **OVERRIDE:** Skip planning's "Execution Handoff" section entirely. Your job is ONLY to write and save the plan. Do NOT ask the user about execution approach — the build pipeline handles execution automatically.

    ### Per-Task Metadata (REQUIRED)

    Every task MUST include this metadata block:

    ### Task N: [Description]
    - **Files:** file1.cs, file2.cs (N files)
    - **Complexity:** Low | Medium | High
    - **Review-Tier:** 1 | 2 | 3
    - **Dependencies:** Task X, Task Y (or "None")

    Complexity tiers:
    - **Low:** 1-3 files, straightforward changes, no cross-system interaction
    - **Medium:** 3-6 files, some inheritance or cross-system interaction
    - **High:** 6+ files, refactoring, deep inheritance chains, cross-system wiring

    **Review tier classification (compute for every task):**
    - **Tier 1 (Light):** Low complexity AND 1-3 files AND no cross-system dependencies AND no cartographer landmine proximity. Pipeline: implementer -> cleanup -> single-pass code review.
    - **Tier 2 (Standard):** Medium complexity OR 3-6 files OR single-system behavioral changes. Not eligible if any Tier 3 trigger applies. Pipeline: implementer -> cleanup -> iterative code review -> single-pass test review -> adversarial tester.
    - **Tier 3 (Heavy):** High complexity OR 6+ files OR cross-system dependencies OR new public API surface OR cartographer landmine proximity. Pipeline: full current review flow.

    **Escalation rules (tier can only increase, never decrease):**
    - Cross-system dependencies -> minimum Tier 2
    - New public API (interface, endpoint, event) -> minimum Tier 2
    - Cartographer landmine proximity (any task file in a landmine directory) -> Tier 3

    ### Task Sizing

    - Target **2-3 tasks per subagent context window** (~10 files max per task)
    - Each step within a task is one action (2-5 minutes): write test, run test, implement, run test, commit
    - Include exact file paths, complete code, exact commands with expected output

    ## Project Context

    [Key architectural patterns, DI framework, naming conventions, test style]

    ## Relevant Files

    [List key files the plan will need to reference]

    ## Your Job

    1. Read the design document carefully
    2. Identify all components, data changes, and test changes needed
    3. Determine task dependencies and ordering
    4. Write the implementation plan with TDD steps for each task
    5. Include per-task metadata (Files, Complexity, Review-Tier, Dependencies)
    6. Save to: docs/plans/YYYY-MM-DD-<topic>-implementation-plan.md

    ## Refactor Mode Context
    (This section is appended by the orchestrator ONLY in refactor mode. Omit in feature mode.)

    This is a REFACTORING build. The user is restructuring existing code, not adding new behavior.
    Success means: existing behavior preserved + structural goals met.

    ### Input: Impact Manifest and Blast Radius

    [FULL TEXT of the impact manifest from Phase 1 blast radius analysis]

    ### Planning Constraints for Refactor Mode

    **Preserve-behavior constraint:**
    - Every task must list which existing tests exercise the code being changed (in a "Tests to verify" field)
    - The success criterion for each step is "all existing tests still pass" — not "new test passes"
    - Tasks that change an interface must specify which tests will need updating and why

    **Atomic step detection:**
    - When a task modifies a public interface (method signature, class name, module export, type definition), trace all consumers from the impact manifest
    - Bundle the interface change + all consumer updates into a single task marked `atomic: true`
    - Independent consumers can be split into parallel atomic tasks
    - Mark each task with `restructuring-only: true/false` based on whether it changes signatures or control flow

    **Consumer migration fan-out:**
    - When an interface changes and consumers are independent, create parallel tasks
    - Explicitly declare dependencies between consumer migrations
    - Consumers that depend on each other get sequential tasks

    **Task metadata (required for every refactoring task):**

        - **Atomic:** true | false — [reason]
        - **Restructuring-only:** true | false
        - **Safe-partial:** true | false
        - **Rollback:** git revert to pre-task commit
        - **Tests to verify:** [list of test files/suites]

    **Bite-sized step exception:** Atomic tasks are NOT split into multiple bite-sized tasks. The coordinated change is one commit-unit. Internal steps are execution guidance, not separate commit points.

    **Rollback annotations:** Every task must include a rollback annotation. Mark tasks as `safe-partial: true` if the codebase is in a valid, shippable state after that task completes.

    ## Before Reporting Back

    Review your plan:
    - Does every task have metadata (Files, Complexity, Review-Tier, Dependencies)?
    - Does every task have a Review-Tier computed from the classification rules?
    - Are Review-Tier assignments consistent with the tier criteria (no High-complexity task at Tier 1)?
    - Are file paths exact (not "somewhere in src/")?
    - Is code complete (not "add validation here")?
    - Are tasks sized for 2-3 per subagent?
    - Does the dependency graph make sense?
    - Are there any circular dependencies?
    - (Refactor mode) Does every task have refactor metadata (Atomic, Restructuring-only, Safe-partial, Rollback, Tests to verify)?
    - (Refactor mode) Are interface-changing tasks marked atomic with all consumers bundled?
    - (Refactor mode) Are independent consumer groups split into parallel tasks?
    - (Refactor mode) Is the success criterion "existing tests green" (not "new test passes")?
```
