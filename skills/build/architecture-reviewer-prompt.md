<!-- DISPATCH: disk-mediated | This template is written to a dispatch file,
     not pasted into the Agent tool prompt. See shared/dispatch-convention.md -->
# Architecture Reviewer Prompt Template

Use this template at the mid-plan architectural checkpoint to assess whether the emerging system coheres.

**Purpose:** Catch design drift, integration issues, and cohesion problems before the remaining tasks build on a shaky foundation. This is NOT a code quality review — it's a "do the pieces fit together?" check.

```
Task tool (general-purpose):
  description: "Architectural review at mid-plan checkpoint"
  prompt: |
    You are reviewing the architectural cohesion of a partially-completed implementation.

    ## The Plan

    [FULL TEXT of the implementation plan]

    ## What Has Been Completed So Far

    [Summary of completed tasks and their outcomes — task names + brief results]

    ## What Remains

    [List of remaining tasks from the plan]

    ## Diff Summary

    Here is the scope of changes so far:

    ```
    [Paste output of: git diff --stat <base-branch>...HEAD]
    ```

    Key files and systems touched:
    [List the most important files/directories changed, grouped by subsystem]

    ## Your Job

    Assess the system AS A WHOLE — not individual tasks.

    Start by reviewing the diff summary to understand the scope. Then read the
    actual files and diffs you need to assess cohesion. Focus your time on:
    - Files where multiple tasks made changes (integration points)
    - New abstractions and interfaces (are they consistent?)
    - Communication patterns between new components

    Use targeted reads rather than trying to review every line:
    ```bash
    # Read specific files to understand architecture
    # Use git diff <base-branch>...HEAD -- <specific-file> for targeted diffs
    ```

    Answer these questions:

    **Cohesion:**
    - Do the implemented pieces fit together into a coherent system?
    - Are the components communicating in consistent ways (events, DI, direct calls)?
    - Are naming conventions consistent across all new code?
    - Are there emerging patterns that should be formalized, or inconsistencies that should be resolved?

    **Design Drift:**
    - Has the implementation drifted from the plan's architectural intent?
    - Are there places where expedient shortcuts diverged from the intended design?
    - Do the abstractions still make sense given what's been built so far?

    **Integration Risks for Remaining Tasks:**
    - Based on what's been built, will the remaining tasks integrate smoothly?
    - Are there assumptions in the remaining tasks that no longer hold?
    - Are there emerging conflicts or friction points the orchestrator should know about?
    - Should any remaining tasks be re-ordered or adjusted?

    **Duplication and Missed Abstractions:**
    - Is there duplicated logic across tasks that should be consolidated?
    - Are there patterns repeated 3+ times that warrant a shared abstraction?
    - Are there utility functions or helpers that multiple completed tasks reinvented independently?

    **DO NOT:**
    - Review code quality (that's handled by code quality reviewers)
    - Check spec compliance (that's handled by spec reviewers)
    - Suggest optimizations or nice-to-haves
    - Nitpick style or formatting
    - Try to read every file — focus on integration points and architecture

    **DO:**
    - Think about the system as a whole, not individual pieces
    - Flag anything that would be expensive to fix later but cheap to fix now
    - Be specific — reference files and patterns, not vague concerns
    - Use targeted file reads and diffs rather than reviewing everything

    ## Report Format

    - **Cohesion assessment:** [Strong / Minor concerns / Design drift detected]
    - **Issues found:** [List specific concerns with file references]
    - **Recommendations for remaining tasks:** [Adjustments the orchestrator should make]
    - **Overall:** [Continue as planned / Adjust remaining tasks / Stop and discuss with user]
```
