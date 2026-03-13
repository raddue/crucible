# Init Recorder — Dispatch Template

Dispatch a Sonnet subagent for Tier 1 fan-in — merges multiple partition explorer outputs into cartographer format.

```
Task tool (general-purpose, model: sonnet):
  description: "Init recording — merging [N] partition reports into cartographer format"
  prompt: |
    You are an init recorder. Your job is to merge multiple partition
    exploration reports into a coherent set of cartographer files. You
    synthesize and deduplicate, resolving conflicts with clear markers.

    ## Partition Reports

    [PASTE: File paths to partition exploration reports on disk — e.g.,
     /tmp/crucible-project-init/src.md, /tmp/crucible-project-init/lib.md]

    ## Existing Cartographer Data

    [PASTE: Existing cartographer data, if any (map.md, conventions.md,
     landmines.md). Say "No prior cartographer data." if first run]

    ## Project

    [PASTE: Project name and ecosystem]

    ## Output Directory

    [PASTE: Output directory for cartographer files — e.g., memory/cartographer/]

    ## Your Job

    1. **Read each partition report** from the provided file paths.

    2. **Build a unified module list** — deduplicate modules reported by
       multiple partitions. When the same module appears in multiple
       reports, prefer the report from the partition containing the
       module's root directory.

    3. **Resolve conflicts** — if partitions disagree on a module's
       responsibility or boundary, include both versions with a
       `[NEEDS VERIFICATION]` marker.

    4. **Merge conventions** across partitions — group by category
       (Naming, Error Handling, Testing, API Patterns), deduplicate
       identical entries.

    5. **Merge gotchas** — deduplicate, keep all unique entries.

    6. **Build the dependency digraph** from cross-partition dependency
       lists reported by each explorer.

    7. **Apply large monorepo triage** if needed:
       - Include modules with 3+ source files
       - Collapse single-file modules into an "Other" row with count
       - Group by subsystem if module count still exceeds the map cap

    8. **Synthesize operational observations** from all partition reports
       into a claude-md-proposal.md file.

    ## Output Files

    Produce these files exactly, writing each to the output directory
    (except claude-md-proposal.md which goes to /tmp/crucible-project-init/).

    ---

    ### File: map.md

    Target 140 lines, hard cap 200.

    ```
    <!-- project-init:structural -->
    # Codebase Map — [Project Name]

    **Last updated:** [today's date]
    **Modules mapped:** N
    **Coverage:** structural scan (breadth-first, not task-verified)

    ## Module Overview

    | Module | Path | Responsibility | Mapped Detail |
    |--------|------|----------------|---------------|
    | ... | ... | ... | Yes |

    ## High-Level Dependencies

    ```dot
    digraph deps { ... }
    ```

    ## Unmapped Areas

    - [directories not scanned or skipped]

    ## Key Architectural Decisions

    - [top-level structural observations]
    ```

    ---

    ### File: conventions.md

    Target 105 lines, hard cap 150.

    ```
    <!-- project-init:structural -->
    # Conventions — [Project Name]

    **Last updated:** [today's date]

    ## Naming

    - [naming conventions observed, deduplicated across partitions]

    ## Error Handling

    - [error handling patterns]

    ## Testing

    - [testing conventions]

    ## API Patterns

    - [API structure conventions]
    ```

    ---

    ### File: landmines.md

    Target 70 lines, hard cap 100.

    ```
    <!-- project-init:structural -->
    # Landmines — [Project Name]

    **Last updated:** [today's date]

    ## [Category]

    - **[Landmine title]** (severity: high|medium) — [description of
      what breaks, why, and how to avoid it]
    ```

    Only include items explorers flagged as gotchas with high surprise
    factor. Not every gotcha is a landmine — promote only genuinely
    surprising ones.

    ---

    ### File: modules/<name>.md

    Target 70 lines, hard cap 100 each. One file per module from the
    unified module list.

    ```
    <!-- project-init:structural -->
    # <Module Name>

    **Path:** <directory path>
    **Responsibility:** [one sentence]
    **Boundary:** [what does NOT belong here]

    ## Key Components

    - `ComponentName` — [what it does, 1 line]

    ## Dependencies

    - **Depends on:** [list]
    - **Depended on by:** [list]

    ## Gotchas

    - [non-obvious behavior, 1 line each]

    ## Last Updated

    [today's date]
    ```

    ---

    ### File: /tmp/crucible-project-init/claude-md-proposal.md

    No line cap — this is a proposal, not a final artifact. Write to
    `/tmp/crucible-project-init/claude-md-proposal.md` (NOT the
    cartographer output directory).

    ```
    <!-- project-init:structural -->
    # Proposed CLAUDE.md Additions

    Review and merge what's useful. These are suggestions from structural
    analysis, not ground truth.

    ## Build & Test Commands

    [build, test, lint commands with correct flags — from explorer
     Operational Observations sections]

    ## Environment Prerequisites

    [services, env vars, Docker deps needed to run]

    ## Framework & Tooling Notes

    [framework idioms, ORM patterns, bundler config that affect how
     agents work]

    ## CI/CD Overview

    [CI system, pipeline stages, deployment targets]
    ```

    Omit categories where no explorers reported findings.

    ## Merge Rules (Re-invocation)

    When existing cartographer data is provided:

    1. **Per-file structural tag** (line 1 is
       `<!-- project-init:structural -->`, no per-section tags):
       **overwrite** the entire file with fresh data from this scan.
    2. **Per-section structural tags** (some `##` headings preceded by
       `<!-- project-init:structural -->`, others not): only overwrite
       structural-tagged sections. **PRESERVE** untagged sections
       (task-verified content) exactly as they are — splice your fresh
       structural sections around the preserved content.
    3. Lines WITHOUT any structural tag (task-verified content):
       **PRESERVE** — do not modify or remove.
    4. New modules not in existing data: **add** with per-file
       structural tag.
    5. Modules in existing data but absent from this scan: add
       `[STALE?]` marker — do NOT remove them.
    6. If map.md would exceed 200 lines after merge: prioritize
       task-verified modules, compress structural-only modules.

    **How to detect tag granularity:** If line 1 of an existing file is
    `<!-- project-init:structural -->` AND no `##` headings have their
    own `<!-- project-init:structural -->` on the preceding line, the
    tag is per-file. If any `##` heading has its own tag, treat the
    file as per-section — even if line 1 also has a tag (line 1 tag
    is then cosmetic; per-section rules apply).

    ## Batching Mode

    When this recorder is dispatched as a BATCH pass (the orchestrator
    will say "batch mode" in the description), produce a SINGLE
    consolidated file in explorer format instead of cartographer files:

    ```
    ## Modules Found
    [merged modules from all input partition reports]

    ## Conventions Observed
    [merged, deduplicated conventions]

    ## Gotchas Noted
    [merged, deduplicated gotchas]

    ## Entry Points
    [merged entry points]

    ## Dependencies
    [merged cross-partition dependencies]

    ## Operational Observations
    [merged operational observations]
    ```

    Write this to the output path specified by the orchestrator (e.g.,
    `/tmp/crucible-project-init/batch-1.md`). Do NOT produce map.md,
    conventions.md, modules/, or other cartographer files in batch mode.

    Only the FINAL recorder pass (non-batch) produces cartographer files.

    ## Rules

    - Every output file MUST start with `<!-- project-init:structural -->`
      on the first line.
    - Module files: one sentence per Key Component, no paragraphs.
    - Gotchas in landmines.md must include severity (high/medium) — only
      promote explorer-reported gotchas that are genuinely surprising.
    - If conventions contradict across partitions, note both versions
      with which partition they were observed in.
    - Target 70% of line caps — leave room for task-verified additions.
    - Record observed facts only — not opinions or speculation.
    - Dependencies must be bidirectional — if A depends on B, note it
      in both module files.

    ## Context Self-Monitoring

    If you reach 50%+ context utilization with reports remaining, write
    what you have to disk and report which partitions still need
    processing.
```
