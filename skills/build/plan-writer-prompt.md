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
    - **Dependencies:** Task X, Task Y (or "None")

    Complexity tiers:
    - **Low:** 1-3 files, straightforward changes, no cross-system interaction
    - **Medium:** 3-6 files, some inheritance or cross-system interaction
    - **High:** 6+ files, refactoring, deep inheritance chains, cross-system wiring

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
    5. Include per-task metadata (Files, Complexity, Dependencies)
    6. Save to: docs/plans/YYYY-MM-DD-<topic>-implementation-plan.md

    ## Before Reporting Back

    Review your plan:
    - Does every task have metadata (Files, Complexity, Dependencies)?
    - Are file paths exact (not "somewhere in src/")?
    - Is code complete (not "add validation here")?
    - Are tasks sized for 2-3 per subagent?
    - Does the dependency graph make sense?
    - Are there any circular dependencies?
```
