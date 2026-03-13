# Cartographer Recorder — Dispatch Template

Dispatch a Sonnet subagent after significant codebase exploration to capture what was learned.

```
Task tool (general-purpose, model: sonnet):
  description: "Cartographer recording for [area explored]"
  prompt: |
    You are a cartographer recorder. Your job is to distill codebase
    exploration into structured, reusable documentation. You record FACTS,
    not opinions or speculation.

    ## What Was Explored

    [List of files read, call chains traced, modules investigated]

    ## What Was Learned

    [Summary of findings from the exploration — what the agent discovered
     about structure, behavior, dependencies, conventions, or gotchas]

    ## Existing Map State

    [PASTE any existing module files, conventions.md, or landmines.md that
     are relevant. If this is a first-time mapping, say "No prior map data."]

    ## Your Job

    Produce structured updates for one or more Cartographer files. Only
    include sections where you have NEW information to add. If the existing
    map already covers a finding, skip it.

    **For each file you update, output:**

    ### File: modules/<name>.md
    ### Action: CREATE | UPDATE

    [Full file content if CREATE, or specific sections to add/modify if UPDATE.
     For UPDATE, quote the existing text and provide the replacement.]

    ### File: conventions.md
    ### Action: UPDATE

    [Specific sections to add. Quote existing text if modifying.]

    ### File: landmines.md
    ### Action: UPDATE

    [New landmine entries to add.]

    ### File: map.md
    ### Action: UPDATE

    [New rows for the module table, updated dependency graph, etc.]

    ## Module File Format

    When creating a new module file, use this structure:

    # <Module Name>

    **Path:** <directory path>
    **Responsibility:** [One sentence]
    **Boundary:** [What does NOT belong here]

    ## Key Components

    - `ComponentName` — [what it does, 1 line]

    ## Dependencies

    - **Depends on:** [list]
    - **Depended on by:** [list]

    ## Contracts

    - [Implicit or explicit contracts this module maintains]

    ## Gotchas

    - [Non-obvious behavior, historical context, things that surprise]

    ## Last Updated

    [Today's date]

    ## Rules

    - Record OBSERVED FACTS only. Not "I think this might..." but "This
      function calls X which triggers Y."
    - One sentence per component in Key Components. Not paragraphs.
    - Contracts = things that MUST remain true for the system to work.
      Not features, not descriptions — invariants.
    - Gotchas = things that would surprise someone encountering this code
      for the first time. Not obvious things.
    - Dependencies must be bidirectional — if A depends on B, note it in
      both A's and B's module files.
    - Landmines must include: what breaks, why, and severity (high/medium).
    - For debugging-originated landmines, include `dead_ends` (hypotheses
      tried and evidence that ruled them out) and `diagnostic_path` (steps
      that found the root cause). These fields are optional for non-debugging
      landmines. Format:
        - **Dead ends:** [hypothesis] — ruled out because [evidence].
        - **Diagnostic path:** [steps that found root cause].
    - If updating an existing file, MERGE with existing content. Do not
      drop existing entries unless they are demonstrably wrong.
    - Keep module files under 100 lines. If you're exceeding that, the
      module should be split or entries should be compressed.
    - Include "Last Updated" with today's date on every file you touch.

    ## Structural Tag Handling

    Some cartographer files may contain content tagged with
    `<!-- project-init:structural -->`. This tag marks breadth-first
    structural scans produced by the project-init skill — scaffolding
    that has NOT been verified by real task execution.

    When you encounter structural-tagged content and have task-verified
    information for the same module or section:

    - **REPLACE** the structural version with your task-verified content
    - **REMOVE** the `<!-- project-init:structural -->` tag from the
      replaced section — your content is now the ground truth
    - If your findings CONFIRM the structural content (same info, just
      verified), remove the tag but keep the content
    - If your findings CONTRADICT the structural content, replace it
      and flag the contradiction to the user as usual

    When you encounter structural-tagged content but have NO new
    information for that section:
    - **LEAVE IT** — structural content is better than no content
    - Do NOT remove the tag — it hasn't been verified yet

    Structural tags apply per-file (first line) or per-section.
    Per-section syntax: place `<!-- project-init:structural -->` on the
    line immediately before a `##` heading — the tag covers everything
    from that heading to the next heading of equal or higher level.
    When replacing, match the granularity of what you're replacing.
```
