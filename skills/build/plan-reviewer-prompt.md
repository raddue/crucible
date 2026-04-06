<!-- DISPATCH: disk-mediated | This template is written to a dispatch file,
     not pasted into the Agent tool prompt. See shared/dispatch-convention.md -->
# Plan Reviewer Prompt Template

Use this template when dispatching a plan reviewer subagent in Phase 2.

```
Task tool (general-purpose, model: opus or sonnet — see build skill for decision heuristic):
  description: "Review implementation plan for [feature]"
  prompt: |
    You are reviewing an implementation plan against its design document.

    ## Design Document

    [FULL TEXT of the design doc]

    ## Implementation Plan

    [FULL TEXT of the implementation plan]

    ## Your Job

    Compare the plan against the design doc. Check:

    **Completeness:**
    - Does the plan cover ALL requirements from the design doc?
    - Are there design requirements with no corresponding task?
    - Are there tasks that don't trace back to a design requirement?

    **Task Quality:**
    - Does every task have metadata (Files, Complexity, Review-Tier, Dependencies)?
    - Are file paths exact and correct?
    - Is code complete (not placeholder or "add X here")?
    - Are tasks sized appropriately (2-3 per subagent, ~10 files max)?
    - Do tasks follow TDD (test before implementation)?
    - Does every task have a Review-Tier (1, 2, or 3)?
    - Are Review-Tier assignments consistent with the classification rules?
      - No task with High complexity or 6+ files at Tier 1 or 2
      - No task with cross-system dependencies at Tier 1
      - No task introducing a new public API at Tier 1
      - Tasks near cartographer landmines must be Tier 3
    - Are any tasks under-tiered? (err toward higher tier when uncertain)
    - **Refactor mode:** GREEN-GREEN tasks do NOT have a RED phase. Do not flag the absence of a failing-test-first step as a deficiency on tasks marked `atomic: true` or `restructuring-only: true`. The success criterion for these tasks is "existing tests stay green," not "new test passes." Verify instead that:
      - Each task lists which existing tests must remain passing ("Tests to verify")
      - Atomic tasks bundle the interface change with all consumer updates
      - Tasks have refactor metadata (Atomic, Restructuring-only, Safe-partial, Rollback, Tests to verify)
      - The bite-sized step exception is respected (atomic tasks are not split into multiple tasks)

    **Dependencies:**
    - Is the dependency graph correct? (No missing edges, no cycles)
    - Are shared-file conflicts identified? (Tasks touching same file should be sequential)
    - Is the ordering sensible? (Foundation before features, data before UI)

    **Architectural Alignment:**
    - Does the plan follow the architecture described in the design doc?
    - Are the right patterns being used (DI, events, ScriptableObjects, etc.)?
    - Are there architectural concerns that should be escalated to the user?

    **IMPORTANT:** Architectural concerns are IMMEDIATE escalation — flag them clearly and separately from other findings.

    ## Report Format

    - **Overall:** Approved | Needs revision | Architectural concern (escalate)
    - **Missing requirements:** [List anything from design doc not covered]
    - **Unnecessary tasks:** [List anything not in design doc]
    - **Task quality issues:** [Specific findings with task numbers]
    - **Tier classification issues:** [Tasks with incorrect or questionable tier assignments]
    - **Dependency issues:** [Specific findings]
    - **Architectural concerns:** [If any — these bypass revision loop]
    - **Suggestions:** [Optional improvements, clearly marked as non-blocking]
```
