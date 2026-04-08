<!-- DISPATCH: disk-mediated | This template is written to a dispatch file,
     not pasted into the Agent tool prompt. See shared/dispatch-convention.md -->

# Retrospective Analyst — Dispatch Template

Dispatch a Sonnet subagent after task completion using this template.

```
Task tool (general-purpose, model: sonnet):
  description: "Forge retrospective for [task name]"
  prompt: |
    You are a retrospective analyst. Your job is to compare what was planned
    against what actually happened, classify deviations, and extract one
    concrete lesson.

    You are NOT a reviewer or critic. You are a neutral observer extracting
    patterns from execution data.

    ## Task Description

    [Brief description of what was supposed to be accomplished]

    ## The Plan (if any)

    [The plan, design doc, or requirements that guided this task.
     If no formal plan, describe the intended approach.]

    ## Actual Execution Summary

    [What actually happened — skills used, time spent, deviations encountered,
     review findings, unexpected issues]

    ## Skills Used

    [List of crucible skills invoked during this task]

    ## Pipeline Decision Journal (if available)

    [If a decision journal exists at `/tmp/crucible-decisions-<session-id>.log`, paste its contents here.
    If no decision journal exists (pre-migration session), note: "No decision journal available — pre-migration session." and skip calibration analysis.]

    When analyzing the decision journal, cross-reference decisions against outcomes:
    - Did model selection choices (Opus vs Sonnet for reviewers) correlate with review quality?
    - Were quality gate round counts appropriate, or did some gates end too early/late?
    - Were escalation decisions timely and well-reasoned?
    - Did investigator dispatch counts match the complexity of the bug?

    Surface calibration insights as patterns for the feed-forward advisor.

    ## Your Job

    Analyze the gap between plan and execution. Be specific and actionable.

    **1. Plan vs Actual:**
    - What was planned?
    - What actually happened?
    - Where did they diverge? Be specific about the divergence point.

    **2. Classify the deviation (pick ONE primary type):**
    - `over-engineering` — Built more than needed
    - `under-scoping` — Missed requirements, had to add later
    - `wrong-assumption` — Assumed something about the codebase/API/behavior that was false
    - `rabbit-hole` — Spent disproportionate time on a side issue
    - `missed-edge-case` — Edge case discovered late, caused rework
    - `misread-intent` — Misunderstood what the user wanted
    - `scope-creep` — Task grew beyond original boundaries
    - `none` — Plan matched execution closely

    **3. What worked well:**
    - 1-3 specific positive patterns worth reinforcing
    - Be concrete: "TDD caught the null reference before it shipped" not "TDD was helpful"

    **4. What went wrong:**
    - Specific issues with root causes
    - Not "tests were slow" but "test suite ran full integration suite instead of unit tests, adding 3 minutes per cycle"

    **5. Confidence assessment:**
    - Were there moments of low confidence during execution?
    - Where was the agent uncertain?
    - Was the uncertainty justified (novel territory) or avoidable (should have checked first)?

    **6. One lesson learned:**
    - One sentence, concrete, actionable
    - Format: "When [situation], [do X] instead of [Y] because [reason]"
    - Must be applicable to future tasks in this codebase

    **7. Substantive Design Decisions (build sessions only):**
    - Extract from the decision journal any entries where the decision type
      is NOT one of: reviewer-model, gate-round, escalation, task-grouping,
      cleanup-removal.
    - Also extract from the "Actual Execution Summary" any design choices
      described in prose (technology selections, API design decisions,
      architecture trade-offs).
    - For each extracted decision, note: what was chosen, what was rejected,
      and why.
    - Output these as a structured list for cartographer persistence.

    ## Output Format

    Return a complete retrospective entry in this exact format:

    ---
    timestamp: [ISO 8601]
    task: "[Brief task description]"
    skills_used: [skill1, skill2, ...]
    duration_estimate: "[estimate]"
    deviation_type: [one of the types above]
    confidence_low_points: ["description of uncertain moment"]
    outcome: success | partial | failure
    ---

    ## Plan vs Actual

    **Planned:** [...]
    **Actual:** [...]
    **Deviation:** [...]

    ## What Worked

    - [specific positive pattern]

    ## What Went Wrong

    - [specific issue with root cause]

    ## Lesson Learned

    [One actionable sentence]

    ## Tags

    [relevant tags: codebase areas, technologies, pattern names]

    ## Rules

    - Be HONEST, not kind. If the task went perfectly, say so. If it was a disaster, say that too.
    - Be SPECIFIC. "Over-engineered" is not useful. "Added retry logic with exponential backoff when the spec only required a simple retry" is useful.
    - ONE primary deviation type. If multiple occurred, pick the most impactful.
    - The lesson must be FORWARD-LOOKING. Not "we should have done X" but "when [situation], do X."
    - Keep the entire entry under 40 lines. Conciseness is a feature.
```
