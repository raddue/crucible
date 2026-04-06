<!-- DISPATCH: disk-mediated | This template is written to a dispatch file,
     not pasted into the Agent tool prompt. See shared/dispatch-convention.md -->

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

    ## Key Decisions

    - **[Decision title]** ([date], [ticket]): [Reasoning]. Alternatives: [rejected options]. Evidence: [observable facts].

    ## Gotchas

    - [Non-obvious behavior, historical context, things that surprise]

    ## Last Updated

    [Today's date]

    ## Rules

    - Key Decisions entries must be 2-3 lines each, max 15 lines total per module.
      If exceeding, move oldest to decisions.md or compress.

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
        - **Dead ends:** [hypothesis] — ruled out because [evidence]. (source: debugging)
        - **Diagnostic path:** [steps that found root cause].
    - For QG-originated landmines (from forge step 6b), dead-end entries
      describe fix strategies rather than diagnostic hypotheses. Format:
        - **Dead ends:** [fix strategy] — ruled out because [reason]. (source: qg)
        - **Diagnostic path:** [round progression].
    - **Dedup on UPDATE:** When updating existing landmine entries with new
      dead-end evidence, preserve each distinct failure description as a
      separate bullet. Do not merge two different failure descriptions into
      one sentence. Two dead-ends that share a file path but describe
      different failure modes remain as separate bullets within the same entry.
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

    **Tag granularity migration:** If a file has a per-file structural
    tag (line 1 only, no per-section tags) and you are ADDING
    task-verified content to it (not replacing everything), you must
    migrate the tagging:
    1. Remove the per-file tag from line 1
    2. Add `<!-- project-init:structural -->` before each `##` heading
       whose content is still structural (i.e., you have no task-verified
       replacement for it)
    3. Do NOT tag your new task-verified sections
    This ensures that a future project-init re-invocation only overwrites
    the sections that are still structural, preserving your additions.

    ## Defect Signature Recording

    When the orchestrator dispatches you with Phase 4.5 scan report data and
    the directive "Record defect signature", follow these instructions instead
    of the standard module/convention/landmine recording flow above.

    ### Input You Receive

    - Phase 4.5 scan report: generalized pattern, "Siblings Fixed" list
      (with justifications), "Siblings Reverted" list (with revert reasons),
      "Siblings Skipped" list (with skip reasons)
    - Original fix metadata: file path, commit SHA, commit message summary,
      issue number or bug description
    - Cartographer module names (or directory prefix fallbacks)
    - Optional: `update_path` — an existing signature file to merge into

    ### Your Job

    Produce exactly ONE signature file and optionally ONE non-match companion
    file. You do NOT manage count enforcement, pruning, dedup detection, or
    cross-file validation — the orchestrator handles all of that.

    **If `update_path` is provided (merge into existing):**
    1. Read the existing signature file at `update_path`
    2. Merge new siblings into the existing file:
       - Add new Confirmed Siblings entries (from "Siblings Fixed")
       - Add new Unresolved Siblings entries (from "Siblings Reverted")
       - Preserve all existing entries
       - Deduplicate by file path (if a path appears in both old and new, keep
         the newer entry)
    3. Update the `Date` field to today
    4. Set `Last loaded` to today
    5. Enforce the 30-entry sibling cap (Confirmed + Unresolved combined):
       if entries exceed 30, truncate Confirmed Siblings from the bottom;
       never truncate Unresolved Siblings
    6. If a companion non-match file exists alongside the existing signature,
       merge new non-match entries (from "Siblings Skipped") into it.
       Enforce the 100-entry cap: if entries exceed 100 after merge, drop
       oldest entries from the top of the list
    7. Report back: updated signature file path, companion file path (if any)
       — the orchestrator will rename the file to use today's date prefix

    **If no `update_path` (new signature):**
    1. Generate slug: first 8 hex characters of a SHA-256 hash of the
       generalized pattern text
    2. Write signature file to `defect-signatures/YYYY-MM-DD-<slug>.md`
    3. Write non-match companion file to
       `defect-signatures/YYYY-MM-DD-<slug>.non-matches.md`
       (only if "Siblings Skipped" entries exist in the scan report)
    4. Map scan report fields to signature sections:
       - "Siblings Fixed" -> `## Confirmed Siblings`
       - "Siblings Reverted" -> `## Unresolved Siblings`
       - "Siblings Skipped" -> non-match companion file entries
    5. Enforce the 30-entry sibling cap (same rules as merge)
    6. Enforce the 100-entry non-match companion cap
    7. Set `Last loaded` to `never`
    8. Report back: signature file path, companion file path

    ### Signature File Format

    # Defect Signature: <short title derived from the pattern>

    **Date:** YYYY-MM-DD
    **Source:** <issue number or bug description>
    **Modules:** <comma-separated cartographer module names>
    **Last loaded:** never
    **Original fix:** <file:path> — <commit SHA> — <one-line commit message summary>

    ## Generalized Pattern

    <2-3 sentence pattern description from Phase 4.5 Step 1>

    ## Confirmed Siblings

    - <file:path> — <one-line semantic justification>

    ## Unresolved Siblings

    - <file:path> — <reason fix was reverted (test failure summary)>

    ### Non-Match Companion File Format

    # Non-Matches: <same short title>

    - <file:path> — <one-line reason why pattern does not apply>

    ### Rules

    - Record OBSERVED FACTS only — the scan report is your source of truth
    - Short title: derive from the generalized pattern, max ~8 words
    - Confirmed Siblings justifications come from the scan report's
      justification text for "Siblings Fixed" entries
    - Unresolved Siblings reasons come from the scan report's test failure
      summaries for "Siblings Reverted" entries
    - Non-match reasons come from the scan report's skip reasons for
      "Siblings Skipped" entries
    - Do NOT add entries that are not in the scan report
    - Do NOT evaluate or re-judge the scan report's classifications

    ## Decision Extraction Recording

    When the orchestrator dispatches you with decision source data and
    the directive "Extract decisions for cartographer", follow these instructions
    instead of the standard module/convention/landmine recording flow.

    ### Input You Receive

    - Decision source: either the contents of a spec scratch `decisions.md` or
      a build decision journal, annotated with file paths from design docs
    - Module mapping: cartographer module names with their `Path:` fields
    - Existing module files: current content of relevant module files
    - Existing `decisions.md`: current content (if it exists)

    ### Your Job

    Extract substantive design decisions and write them into the appropriate
    cartographer files. You do NOT extract operational decisions (model selection,
    gate rounds, task grouping).

    ### Extraction Criteria

    Persist a decision if ANY of these are true:
    - Confidence is medium or low (uncertainty worth preserving)
    - Decision affects module-level architecture or cross-ticket interfaces
    - Decision records why a viable alternative was rejected
    - Decision references a constraint that is non-obvious from the code

    Do NOT persist:
    - High-confidence implementation details (loop style, variable naming)
    - Decisions fully captured in contract `ambiguity_resolutions` (avoid duplication)
    - Routing/operational decisions (reviewer model, gate round counts)

    ### Module Mapping Rules

    1. Read each decision's associated file paths (from design doc or ticket)
    2. Match file paths to cartographer modules using `Path:` prefix matching
    3. If a decision maps to exactly one module: write to that module's `## Key Decisions`
    4. If a decision maps to 2+ modules: write to `decisions.md` with `modules:` tag
    5. If a decision maps to no module (new area): write to `decisions.md`

    ### Output Format

    For each module file update, output:

    ### File: modules/<name>.md
    ### Action: UPDATE
    ### Section: Key Decisions

    - **[title]** ([date], [ticket]): [reasoning]. Alternatives: [list]. Evidence: [evidence].

    For cross-cutting decisions, output:

    ### File: decisions.md
    ### Action: CREATE | UPDATE

    [Entry in cross-cutting format]

    ### Rules

    - Compress each decision to 2-3 lines. No paragraphs.
    - Include date and source ticket for every entry.
    - Include confidence level only if non-high.
    - Always include at least one rejected alternative with reason.
    - Evidence must reference specific, observable facts (test results, API docs, load test numbers), not opinions.
    - If a module file would exceed 100 lines with the new entries, move the oldest or lowest-value existing decisions to `decisions.md` before adding new ones.
    - If `decisions.md` would exceed 200 lines, compress oldest entries (remove evidence detail, keep decision + alternative + date) or prune entries older than 20 sessions.
    - MERGE with existing Key Decisions entries. Do not drop existing entries unless they are demonstrably obsolete (the constraint they reference no longer exists).
    - When an existing decision contradicts a new one, flag to user: "Prior decision [X] conflicts with new decision [Y]. Which is current?"
```
