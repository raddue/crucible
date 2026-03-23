---
ticket: "#63"
epic: "none"
title: "Decision Archaeology Log in Cartographer"
date: "2026-03-23"
source: "spec"
---

# Implementation Plan: Decision Archaeology Log in Cartographer

## Task 1: Add Key Decisions Section to Module File Format

**Files:**
- `skills/cartographer-skill/SKILL.md` (lines 97-129): Insert `## Key Decisions` section template between `## Contracts` and `## Gotchas` in the module file format specification.
- `skills/cartographer-skill/SKILL.md` (line 68): Update the `modules/<name>.md` max-lines row note to mention the Key Decisions section as part of the budget.

**Changes:**
- Add the following section to the module file format (after line 123, before line 125):

```markdown
## Key Decisions

- **[Decision title]** ([ISO date], [ticket], [confidence if non-high]): [Why this choice was made]. Alternatives: [Alt 1] (rejected: [reason]), [Alt 2] (rejected: [reason]). Evidence: [what drove the choice].
```

- Add a note to the module file format preamble that Key Decisions should contain 1-5 entries, each 2-3 lines, consuming no more than 15 lines of the 100-line cap.

**Complexity:** Low
**Dependencies:** None — purely additive format change.

---

## Task 2: Add Cross-Cutting Decisions File Specification

**Files:**
- `skills/cartographer-skill/SKILL.md` (lines 42-59): Add `decisions.md` to the storage structure listing.
- `skills/cartographer-skill/SKILL.md` (lines 62-71): Add row to the file size caps table.
- `skills/cartographer-skill/SKILL.md` (line 73): Update the note about what the orchestrator loads (decisions.md is NOT loaded by the orchestrator).

**Changes:**
- Add `decisions.md` to the storage tree after `landmines.md`:
  ```
  decisions.md          # Cross-cutting design decisions with rationale (max 200 lines)
  ```

- Add table row:
  ```
  | `decisions.md` | 200 | Implementer, Reviewer, Red-team subagents | Pasted into dispatch prompt |
  ```

- Add the file format specification after the landmines format (after line 178):

```markdown
**Decisions file (`decisions.md`):**

# Cross-Cutting Decisions

Decisions that span multiple modules or are architectural in nature.
Loaded by implementer and reviewer/red-team subagents alongside module context.

## Decisions

- **[Decision title]** ([ISO date], [ticket], modules: [list], [confidence if non-high]): [Why this choice was made]. Alternatives: [Alt 1] (rejected: [reason]), [Alt 2] (rejected: [reason]). Evidence: [what drove the choice].

## Last Updated

[ISO date]
```

**Complexity:** Low
**Dependencies:** None.

---

## Task 3: Extend Recorder Prompt with Decision Extraction Mode

**Files:**
- `skills/cartographer-skill/recorder-prompt.md` (after line 250, the end of the Defect Signature Recording section): Add a new "Decision Extraction Recording" section.

**Changes:**
Add a new mode block structured like the existing Defect Signature Recording mode (lines 152-250 of `recorder-prompt.md`):

```markdown
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

**Complexity:** Medium — requires careful alignment with existing recorder prompt patterns and extraction criteria definition.
**Dependencies:** Task 1 (module format must include the section), Task 2 (cross-cutting file must be specified).

---

## Task 4: Add Spec Post-Completion Extraction Hook

**Files:**
- `skills/spec/SKILL.md` (around line 243, after the Orchestration Flow section, or within the flow itself): Add a new step after the final wave completes.

**Changes:**
Add a step to the orchestration flow (between step [9] wave execution and the final commit/PR step):

```
+-- [10] Extract decisions to cartographer
|       After all waves complete and before branch/PR operations:
|       1. Read scratch/<run-id>/decisions.md (shared decision log)
|       2. For each ticket in committed status, read tickets/<ticket-number>/decisions.md
|       3. Collect all file paths from committed design docs (the `Path:` or file references
|          within each design doc's Current State Analysis or similar sections)
|       4. Map decisions to cartographer modules using file path prefix matching
|       5. Dispatch cartographer recorder with directive "Extract decisions for cartographer"
|          Input: collected decisions, module mapping, existing module files, existing decisions.md
|       6. Write recorder output to cartographer storage
|       7. This step is RECOMMENDED, not REQUIRED — failure does not block the spec run
```

Add a note to the Stale Cleanup section (line 194-196) that decision extraction must complete before the scratch directory becomes eligible for stale cleanup. Specifically: the `ticket-status.json` all-committed check already ensures this, since extraction happens before the status reaches a terminal state for the overall run.

**Complexity:** Medium — requires reading and synthesizing across scratch directory files, mapping to cartographer modules, and dispatching a recorder.
**Dependencies:** Task 3 (recorder prompt must support decision extraction mode).

---

## Task 5: Add Forge/Build Extraction Hook

**Files:**
- `skills/forge-skill/SKILL.md` (around line 74, within the retrospective process description): Add a decision extraction step.
- `skills/forge-skill/retrospective-prompt.md` (around line 80, after the output format): Add a section for extracting substantive design decisions from the decision journal.

**Changes:**

In `skills/forge-skill/SKILL.md`, after step 6 (diagnostic extraction for debugging sessions), add:

```
7. For build sessions with a decision journal, the retrospective also extracts
   substantive design decisions. The retrospective analyst identifies decisions
   that are NOT operational routing (reviewer-model, gate-round, task-grouping,
   cleanup-removal types from the journal) but are substantive design choices
   (technology selection, API design, architecture, constraint trade-offs).
   These are passed to a cartographer recorder dispatch with the
   "Extract decisions for cartographer" directive, alongside the module
   mapping from the build session's task list and design doc.
```

In `skills/forge-skill/retrospective-prompt.md`, add a new analysis section:

```
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
```

Update the Integration table in `skills/forge-skill/SKILL.md` (line 147-155) to add:

```
| `crucible:build` | Retrospective (decision extraction) | After fix verified | Design decisions from journal + execution summary -> cartographer |
```

**Complexity:** Medium — requires the retrospective analyst to distinguish substantive from operational decisions, which is a judgment call that may need iteration.
**Dependencies:** Task 3 (recorder prompt must support decision extraction mode).

---

## Task 6: Update Load Mode Subagent Table

**Files:**
- `skills/cartographer-skill/SKILL.md` (lines 347-353): Update the subagent loading table.
- `skills/cartographer-skill/SKILL.md` (lines 333-336): Update the load process description.

**Changes:**

Update the subagent loading table to add a `decisions.md` column:

```
| Subagent Type | `conventions.md` | `landmines.md` | `modules/*.md` | `defect-signatures/*.md` | `*.non-matches.md` | `decisions.md` |
|---------------|:-:|:-:|:-:|:-:|:-:|:-:|
| Implementer | Yes | No | Yes | Yes (matching modules) | No | Yes |
| Code Reviewer | No | Yes | Yes | No | No | Yes |
| Red-Team | No | Yes | Yes | No | No | Yes |
| Investigator (debug) | No | No | Yes | Yes (matching modules) | Yes (truncated to 50) | No |
| Where Else? scan | No | No | Yes | Yes (max 3, matching modules) | Yes (paths only) | No |
| Plan Writer | No | No | No | No | No | No |
```

Add to the load process (after step 5, around line 336):

```
5b. Also paste `decisions.md` into implementer, reviewer, and red-team prompts.
    This provides cross-cutting decision rationale alongside module-specific context.
```

**Complexity:** Low
**Dependencies:** Task 2 (decisions.md file must be specified).

---

## Task 7: Update Recorder Prompt Module File Template

**Files:**
- `skills/cartographer-skill/recorder-prompt.md` (lines 58-85): Update the module file format template within the recorder prompt to include `## Key Decisions`.

**Changes:**

Insert the Key Decisions section into the template between `## Contracts` and `## Gotchas`:

```markdown
## Key Decisions

- **[Decision title]** ([date], [ticket]): [Reasoning]. Alternatives: [rejected options]. Evidence: [observable facts].
```

Add a rule (around line 107):
```
- Key Decisions entries must be 2-3 lines each, max 15 lines total per module.
  If exceeding, move oldest to decisions.md or compress.
```

**Complexity:** Low
**Dependencies:** Task 1 (main SKILL.md format must be defined first for consistency).

---

## Task 8: Add Red Flags and Rationalization Prevention Entries

**Files:**
- `skills/cartographer-skill/SKILL.md` (lines 395-419): Add entries to Red Flags and Rationalization Prevention sections.

**Changes:**

Add to Red Flags "Never" list:
```
- Record speculative decisions ("we might switch to X later") — only record decisions actually made with evidence
- Put operational routing decisions (model selection, gate rounds) in Key Decisions — those belong in forge
```

Add to Red Flags "Always" list:
```
- Include at least one rejected alternative with reason for every decision entry
- Include date and source ticket for every decision entry
```

Add to Rationalization Prevention table:
```
| "That decision is obvious, no need to record it" | Obvious to you now. Not obvious in 10 sessions when context is gone. Record it. |
| "Too many decisions to persist" | Persist the ones with rejected alternatives. If the choice was unanimous, it doesn't need archaeology. |
```

**Complexity:** Low
**Dependencies:** None.

---

## Execution Order

```
Task 1 ─┐
Task 2 ─┼─> Task 3 ──> Task 4
Task 8 ─┘        └──> Task 5
Task 7 (after Task 1)
Task 6 (after Task 2)
```

Tasks 1, 2, and 8 are independent and can be done in parallel or any order. Task 7 depends on Task 1. Task 3 depends on Tasks 1 and 2. Tasks 4 and 5 depend on Task 3. Task 6 depends on Task 2.

**Total estimated complexity:** Low-Medium. All changes are additive text edits to existing markdown skill files. No new files are created except `decisions.md` (which is a storage file created at runtime by the recorder, not a skill file). No code, no tests, no migrations.
