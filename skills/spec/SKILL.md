---
name: spec
description: "Use when you have a GitHub epic (or equivalent) with child tickets and want to autonomously produce design docs, implementation plans, and machine-readable contracts for each ticket without human interaction. Triggers on /spec, 'spec out', 'write specs for', 'spec this epic'."
---

# Autonomous Spec Writer

## Overview

Fully autonomous skill that takes a GitHub epic (or equivalent issue tracker artifact), processes child tickets without human interaction, and produces complete design docs + implementation plans + machine-readable contracts per ticket. Designed to run unattended while a separate agent (or human) handles implementation.

**The core insight:** Separate the cognitive work (design, investigation, decision-making, planning) from the execution work (implementation, testing). One agent specs autonomously, another builds. The spec agent requires no human input after the initial invocation -- it investigates the codebase, makes design decisions, documents its reasoning, and flags uncertainty via terminal alerts rather than blocking on human answers. Contracts solve the hard problem of two async agents communicating through prose -- prose is ambiguous, contracts make inter-ticket interfaces structural and verifiable.

**Invocation:**
```
/spec https://github.com/org/repo/issues/123
/spec PROJ-456    # if Jira/Atlassian MCP is available
```

**Announce at start:** "I'm using the spec skill to autonomously produce design docs, implementation plans, and contracts for this epic."

## Communication Requirement (Non-Negotiable)

**After each wave completes and after each ticket within a wave reports back, output a status update to the terminal.** This is NOT optional -- the user cannot see agent activity without your narration.

Every status update must include:
1. **Current wave** -- Which wave is in progress or just completed
2. **Tickets completed / remaining** -- Counts for the current wave and overall
3. **Alerts emitted** -- Any medium/low/block confidence decisions from that wave
4. **Re-queued tickets** -- Any tickets moved to a later wave due to dependency discovery

**After compaction:** If you just experienced context compaction, follow the Compaction Recovery procedure, re-read state from the scratch directory, and output current status before continuing. Do NOT proceed silently.

**Example of GOOD narration:**
> "Wave 2 complete. 3/3 tickets committed. 1 medium-confidence alert on #45 (chose Redis over Postgres for session store). #67 re-queued to Wave 3 (new dependency on #45 discovered). Overall: 7/12 tickets done, 5 remaining across 2 waves."

## Pipeline Status

Write a status file to `~/.claude/projects/<hash>/memory/pipeline-status.md` at every narration point. This file is overwritten (not appended) and provides ambient awareness for the user in a second terminal.

### Write Triggers

Write the status file at every point where the Communication Requirement mandates narration: before dispatch, after completion, phase transitions, health changes, escalations, and after compaction recovery.

### Status File Format

The status file uses this structure (overwritten in full each time):

```
# Pipeline Status
**Updated:** <current timestamp>
**Started:** <timestamp from first write — persisted across compaction>
**Skill:** spec
**Phase:** <current phase, e.g. "Wave 2 (3/4 tickets in progress)">
**Health:** <GREEN|YELLOW|RED>
**Suggested Action:** <omit when GREEN; concrete one-sentence action when YELLOW/RED>
**Elapsed:** <computed from Started>

## Recent Events
- [HH:MM] <most recent event>
- [HH:MM] <previous event>
(last 5 events, newest first)
```

### Skill-Specific Body

Append after the shared header:

```
## Tickets
- Wave 1: 3/3 complete
- Wave 2: 2/4 in progress (#45 writing, #67 investigating)
- Alerts: 1 medium-confidence on #45

## Compression State
Goal: [epic URL and description]
Key Decisions:
- [accumulated decisions, max 10]
Active Constraints:
- [dependency constraints, re-queued tickets]
Next Steps:
1. [immediate next action]
2. [subsequent actions]
```

### Health State Machine

Health transitions are one-directional within a phase: GREEN -> YELLOW -> RED. Phase boundaries reset to GREEN.

- **Phase boundaries** (reset to GREEN): each new wave
- **YELLOW:** ticket re-queued more than once, teammate failure on a ticket, medium-confidence alert
- **RED:** 2+ tickets failed in same wave, unresolvable dependency cycle, block-confidence alert

When health is YELLOW or RED, include `**Suggested Action:**` with a concrete, context-specific sentence (e.g., "Ticket #45 re-queued twice — may have an unresolvable dependency. Check dependency graph.").

### Inline CLI Format

Output concise inline status alongside the status file write:
- **Minor transitions** (dispatch, completion): one-liner, e.g. `Wave 2 [7/12] #45 spec committed | GREEN | 45m`
- **Phase changes and escalations**: expanded block with `---` separators
- **Health transitions**: always expanded with old -> new health

### Compaction Recovery

After compaction, before re-writing the status file:
0. Read the `## Compression State` section from `pipeline-status.md` — recover Goal, Key Decisions, Active Constraints, and Next Steps. If absent, skip to step 1.
1. Read the rest of `pipeline-status.md` to recover `Started` timestamp and `Recent Events` buffer
2. Reconstruct phase, health, and skill-specific body from internal state files
3. Emit a Compression State Block into the conversation to seed the new context window
4. Write the updated status file
5. Output inline status to CLI

## Epic Extraction

GitHub has no first-class "epic with child tickets" API. Use a fallback chain to extract scope units from the provided issue:

### Extraction Strategy (ordered fallback)

1. **Sub-issues via GraphQL:** Query the `trackedIssues` field on the issue. If the issue has sub-issues, use them as scope units.
2. **Task list checkboxes:** Parse the issue body for task list items (`- [ ]` / `- [x]`) that reference issues via `#NNN` syntax. Extract referenced issue numbers as scope units.
3. **Body issue references:** Parse the issue body for any GitHub issue URLs (`https://github.com/.../issues/NNN`) or `#NNN` references not inside task lists. Extract as scope units.
4. **Manual identification:** If none of the above yield scope units, present the full issue body to the user and ask: "I couldn't find discrete child tickets. Can you identify the scope units for this work? You can provide issue numbers, paste URLs, or describe the work items and I'll create tickets for each."

### Handling No Discrete Tickets

If the epic represents a single monolithic piece of work (no children, user confirms it's one unit), process it as a single-ticket run: one investigation, one design doc, one contract. The orchestration flow still applies, just with a single item in the queue.

## Scratch Directory

**Canonical path:** `~/.claude/projects/<project-hash>/memory/spec/scratch/<run-id>/`

The `<run-id>` is a timestamp generated at run start (e.g., `2026-03-21T14-30-00`). All state is persisted to disk -- the orchestrator never relies solely on context memory for critical state.

### Shared Files (written only by the orchestrator)

- **`invocation.md`** -- Written at run start. Contains: epic URL, extraction method used, user preferences (auto-PR yes/no).
- **`scope-units.json`** -- Extracted ticket list with titles and numbers.
  ```json
  {
    "tickets": [
      { "number": "#123", "title": "Add auth middleware" },
      { "number": "#124", "title": "Refactor token validation" }
    ]
  }
  ```
- **`dependency-graph.json`** -- DAG of ticket dependencies. Updated by the orchestrator after each wave completes, incorporating discoveries from teammates.
  ```json
  {
    "edges": [
      { "from": "#124", "to": "#123", "reason": "Token validation depends on auth middleware interface" }
    ]
  }
  ```
- **`wave-schedule.json`** -- Ordered list of execution waves, each containing a list of ticket numbers. Updated when dependency discovery causes re-queuing.
  ```json
  {
    "waves": [
      { "wave": 1, "tickets": ["#123", "#125", "#127"] },
      { "wave": 2, "tickets": ["#124", "#126"] }
    ]
  }
  ```
- **`contracts/`** -- Directory containing committed contract YAML files, indexed by ticket number. Cross-referenced during cascading.
- **`decisions.md`** -- Append-only log of autonomous decisions across all tickets. Each entry: ticket number, decision ID, choice made, alternatives considered, confidence score. Updated by the orchestrator after each wave completes using teammate outputs.
- **`ticket-status.json`** -- Per-ticket status tracking. Updated only by the orchestrator.
  ```json
  {
    "#123": { "status": "committed", "reason": null, "wave": 1 },
    "#124": { "status": "pending", "reason": null, "wave": 2 },
    "#125": { "status": "failed", "reason": "Contract validation failed after retry", "wave": 1 }
  }
  ```
  Valid statuses: `pending`, `investigating`, `dependency-check`, `writing`, `validating`, `committed`, `failed`, `blocked`, `re-queued`, `needs-respec`.
  Terminal states: `committed`, `failed`, `blocked`, `needs-respec`.

### Per-Ticket Directories (written by teammates)

Each teammate writes exclusively to `scratch/<run-id>/tickets/<ticket-number>/`. This prevents concurrent modification of shared files when multiple teammates run in parallel within a wave.

- **`tickets/<ticket-number>/output/`** -- Design doc, implementation plan, and contract produced by this ticket's teammate.
- **`tickets/<ticket-number>/decisions.md`** -- Decisions made during this ticket's investigation. The orchestrator merges these into the shared `decisions.md` after the wave completes.
- **`tickets/<ticket-number>/discoveries.json`** -- New dependency discoveries found during investigation.
  ```json
  {
    "dependencies": [
      { "from": "#123", "to": "#126", "reason": "Auth middleware needs event bus from #126" }
    ]
  }
  ```
- **`tickets/<ticket-number>/status.json`** -- This ticket's final status and any error details. The orchestrator merges into shared `ticket-status.json` after the wave completes.
  ```json
  {
    "status": "committed",
    "alerts": [
      { "ticket": "#123", "confidence": "medium", "decision": "DEC-1", "summary": "Chose Redis over Postgres for session store" }
    ]
  }
  ```

### Orchestrator Reconciliation

After each wave completes, the orchestrator reads all per-ticket directories from that wave and updates the shared state files (dependency graph, decisions log, ticket status, wave schedule). This serialized update eliminates race conditions while preserving parallel execution within waves.

**Contract cascading:** After reconciliation, copy newly emitted contracts from `tickets/<ticket-number>/output/` into the shared `contracts/` directory so downstream waves have access to upstream contracts.

### Stale Cleanup

Delete scratch directories older than 24 hours at run start, but only when ALL tickets in that directory's `ticket-status.json` are in `committed` status. Directories containing any ticket in `needs-respec`, `blocked`, or `failed` status are preserved regardless of age -- these terminal states expect re-invocation and user action, and deleting them would lose the recovery context.

### Project-Hash Recovery

If the expected scratch directory is not found at the canonical path (e.g., because the repo moved or the project hash changed), search all project hashes under `~/.claude/projects/*/memory/spec/scratch/` for any `invocation.md` containing the current epic URL. If a match is found, adopt that scratch directory for the current run. If no match is found, start a fresh run.

## Context Budget Management

Processing 5+ tickets will exhaust the orchestrator's context window. The skill uses cascading context compression:

### Preemptive Context Checkpoint

The orchestrator triggers a planned save-and-compact cycle: **compact after every 2 waves, or after any single wave that contained 4+ tickets.** These thresholds are tied to the amount of work processed rather than unreliable context capacity estimates.

When a checkpoint triggers:
1. Persist all current state to the scratch directory (ticket statuses, dependency graph, wave schedule, decisions log).
2. Emit a Compression State Block into the conversation capturing Goal, accumulated decisions, active constraints, and next steps.
3. Trigger compaction explicitly between waves rather than hitting mid-ticket compaction.
4. After compaction, recover state via the Compaction Recovery procedure below.
5. Resume processing with the next wave.

This prevents mid-ticket compaction, which wastes partial investigation work. The checkpoint always occurs at a clean boundary between waves.

### Per-Ticket Context Lifecycle

1. **Before ticket investigation:** Read only the ticket body, dependency graph, and upstream contracts relevant to this ticket from the scratch directory. Do not load prior tickets' full investigation results into context.
2. **During investigation:** Run investigation agents as sub-agents (Agent tool). They return summaries, not full search results.
3. **After ticket completion:** Write all outputs to disk (design doc, contract, status update). Compress the ticket's context contribution to a single-paragraph summary appended to `decisions.md`. Release the full investigation context.

### Ticket Complexity Triage

Teammates run as sub-agents with their own context windows. Complex tickets can exhaust a teammate's context before investigation completes. Mitigate by triaging complexity before dispatch:

1. **Complexity signal:** Count the number of design dimensions requiring investigation (inferred from ticket body + upstream dependency count + codebase area size from cartographer). If a ticket has **5+ design dimensions** or **3+ upstream contracts** to consume, flag it as "complex."
2. **Simplified investigation for complex tickets:** Complex tickets use quick-scan investigation for ALL dimensions (single codebase scout per dimension instead of 3-agent deep dive), with more aggressive summarization. The teammate's task description includes: "This ticket is flagged as complex. Use quick-scan investigation for all dimensions. Summarize each finding to 2-3 sentences before proceeding to the next dimension."
3. **Two-phase split for very large tickets:** If a ticket has **8+ design dimensions**, the orchestrator splits investigation into two phases with an intermediate disk persist. Phase A investigates the first half of dimensions, writes findings to `tickets/<ticket-number>/partial-investigation.md`, and completes. Phase B reads the partial investigation from disk, investigates the remaining dimensions, and proceeds to writing. This doubles the effective context budget at the cost of one extra sub-agent dispatch.

### Compaction Recovery

After context compaction:
0. Read `## Compression State` from pipeline-status.md — recover Goal, Key Decisions, Active Constraints, Next Steps. If absent, skip to step 1.
1. Read `scratch/<run-id>/invocation.md` first -- recover epic URL, extraction method, and user preferences.
2. Read `scratch/<run-id>/ticket-status.json` -- determine which tickets are complete, in-progress, or pending.
3. Read `scratch/<run-id>/wave-schedule.json` -- recover the current wave schedule.
4. Read `scratch/<run-id>/dependency-graph.json` -- recover the current dependency DAG.
5. Read `scratch/<run-id>/decisions.md` -- recover the decision log for context cascading to remaining tickets.
6. For any ticket with status `investigating`, `dependency-check`, `writing`, or `validating`: restart from the beginning of its current phase.
7. Emit a Compression State Block into the conversation to seed the new context window.
8. Resume processing from the wave schedule, skipping completed/committed tickets.

### Checkpoint Timing

Emit a Compression State Block at:
- **Wave boundaries:** After each wave completes, before starting the next
- **Preemptive context checkpoints:** After every 2 waves, or after any single wave with 4+ tickets
- **Ticket re-queues:** When tickets are re-queued to later waves due to dependency discovery
- **Escalations:** Before any escalation to user
- **Health transitions:** On any GREEN->YELLOW or YELLOW->RED transition

## Orchestration Flow

```
/spec <epic-url>
  |
  +-- [1] Consult cartographer (once) + forge feed-forward (once)
  |
  +-- [2] Fetch epic, extract child tickets (fallback chain)
  |
  +-- [3] Read ALL tickets upfront
  |
  +-- [4] Content-analyze tickets, infer dependency graph
  |
  +-- [5] Build wave schedule from dependency graph
  |       Group independent tickets into waves. Within a wave,
  |       all tickets are guaranteed to have no cross-dependencies.
  |
  +-- [6] Present execution plan to user
  |       "Wave 1: #1, #3, #5 (independent). Wave 2: #2 (depends on #1), #4..."
  |
  +-- [7] Ask: "Auto-create a PR for the epic, or just commit to the branch?"
  |
  +-- [8] Persist initial state to scratch directory
  |       Write invocation.md, scope-units.json, dependency-graph.json,
  |       wave-schedule.json, ticket-status.json (all pending)
  |
  +-- [9] Create team + tasks (Agent Teams, with sequential fallback)
  |
  +-- [10] Process waves sequentially, tickets within each wave in parallel
  |        |
  |        +-- Per wave:
  |            +-- Preemptive context checkpoint (every 2 waves, or after large waves)
  |            +-- Dispatch all tickets in wave as parallel teammates
  |            +-- Per ticket (teammate writes to tickets/<ticket-number>/):
  |                +-- Skip if completed (silent)
  |                +-- Skip if spec docs exist (mention in output)
  |                +-- Update local status -> "investigating"
  |                +-- Run investigation (same depth as /design)
  |                +-- Dependency discovery check -> write discoveries.json
  |                +-- Update local status -> "writing"
  |                +-- Write design doc + implementation plan + contract to output/
  |                +-- Contract schema validation
  |                +-- Update local status -> "validating"
  |                +-- Lightweight per-ticket validation (5 checks)
  |                +-- Update local status -> "committed"
  |                +-- Persist outputs + local decisions to ticket dir
  |                +-- (On failure: local status -> "failed", log reason, continue)
  |            +-- After wave completes (orchestrator):
  |                +-- Reconcile per-ticket outputs into shared state files
  |                +-- Cascade contracts: copy to shared contracts/ directory
  |                +-- Copy outputs from ticket dirs to docs/plans/
  |                +-- Commit outputs to spec/<epic-number> branch (serialized)
  |                +-- Check for re-queued tickets, update wave schedule
  |                +-- Output status update to terminal
  |
  +-- [11] End-of-run quality gate
  |        +-- Phase 1: Per-document gates (design + plan per ticket, in parallel)
  |        +-- Phase 2: Cross-ticket integration check (contracts + dep graph only)
  |
  +-- [12] Summary report
```

### Step-by-Step Detail

**[1] Consult cartographer + forge:** Use `crucible:cartographer` (consult mode) to review the codebase map and `crucible:forge` (feed-forward mode) to consult past lessons. Run once at the start of the run.

**[2] Fetch epic, extract child tickets:** Use the extraction fallback chain (sub-issues, task list checkboxes, body references, manual identification). See Epic Extraction section.

**[3] Read ALL tickets upfront:** Fetch the full title, body, labels, and linked issues for every extracted ticket. This enables dependency analysis before any investigation begins.

**[4] Content-analyze tickets, infer dependency graph:** Read every ticket's content and identify explicit references ("after #123 is done", "depends on the interface from #456") and implicit dependencies (ticket A defines an interface, ticket B consumes it). Build a DAG. See Dependency Analysis section for cycle handling.

**[5] Build wave schedule:** Topological sort the dependency graph. Assign each ticket to the earliest wave where all upstream dependencies are in prior waves. No intra-wave dependencies. See Wave-Based Scheduling section.

**[6] Present execution plan:** Show the user the wave schedule with ticket groupings and dependency rationale. The user can override (reorder, force sequential, etc.) or approve.

**[7] Ask about auto-PR:** "Auto-create a PR for the epic, or just commit to the branch?"

**[8] Persist initial state:** Write `invocation.md`, `scope-units.json`, `dependency-graph.json`, `wave-schedule.json`, and `ticket-status.json` (all tickets as `pending`) to the scratch directory.

**[9] Create team + tasks:** Use Agent Teams (TeamCreate/TaskCreate) for parallel execution. If Agent Teams unavailable, fall back to sequential subagent dispatch. See Parallel Execution section.

**[10] Process waves:** Sequential between waves, parallel within waves. Per-wave details in the flow diagram above. Post-wave reconciliation updates shared state, cascades contracts, copies outputs to `docs/plans/`, commits to the epic branch, and checks for re-queued tickets.

**[11] End-of-run quality gate:** Two phases -- per-document gates on each design doc and plan, then cross-ticket integration check on contracts and dependency graph. See End-of-Run Quality Gate section.

### Decision Extraction (After All Waves Complete)

After all waves complete and before branch/PR operations:
1. Read `scratch/<run-id>/decisions.md` (shared decision log)
2. For each ticket in committed status, read `tickets/<ticket-number>/decisions.md`
3. Collect all file paths from committed design docs (the `Path:` or file references within each design doc's Current State Analysis)
4. Map decisions to cartographer modules using file path prefix matching
5. Dispatch cartographer recorder with directive "Extract decisions for cartographer"
   Input: collected decisions, module mapping, existing module files, existing decisions.md
6. Write recorder output to cartographer storage
7. This step is RECOMMENDED, not REQUIRED -- failure does not block the spec run

**[12] Summary report:** Output a final report with: tickets completed, tickets failed (with reasons), tickets blocked (with decision context), alerts emitted, contracts produced, and the branch/PR URL.

## Parallel Execution via Agent Teams

The orchestrator uses Agent Teams (TeamCreate/TaskCreate) to dispatch tickets within a wave in parallel:

1. **Create team** at run start:
   ```
   TeamCreate: team_name="spec-<epic-number>", description="Speccing epic #NNN"
   ```

2. **Create tasks** for each ticket via TaskCreate, with description containing the ticket body, upstream contracts, and relevant decisions log entries.

3. **Dispatch teammates** for each ticket in the current wave. Each teammate writes all outputs to its isolated scratch directory (`tickets/<ticket-number>/output/`). Teammates do not perform any git operations -- the orchestrator handles all git work after the wave completes.

4. **Track completion** via TaskGet/TaskList. As teammates complete, the orchestrator collects results and updates the scratch directory.

### Agent Teams Fallback

If `TeamCreate` fails (agent teams not available), output a clear one-time warning:

> Agent teams are not available. Recommended: set `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`
> Falling back to sequential subagent dispatch via Agent tool.

Then fall back to sequential subagent dispatch via the Agent tool. Each ticket in a wave is dispatched sequentially instead of in parallel. All other behavior (wave scheduling, dependency discovery, validation, quality gate) is unchanged -- the run is slower but functionally identical.

## Wave-Based Scheduling

Tickets are grouped into execution waves based on the dependency graph. This eliminates the need for runtime cancellation of in-progress tickets -- a capability Claude Code does not support.

### Wave Construction

1. Topological sort the dependency graph.
2. Assign each ticket to the earliest wave where all its upstream dependencies are in prior waves.
3. All tickets within a single wave are guaranteed independent of each other -- no ticket in wave N depends on another ticket in wave N.
4. Persist the wave schedule to `scratch/<run-id>/wave-schedule.json`.

### Wave Execution

Waves execute sequentially. Within each wave, all tickets execute in parallel (via Agent Teams) or sequentially (via Agent tool fallback). A wave does not begin until all tickets in the prior wave have reached a terminal state (committed or failed).

### Re-queuing on Dependency Discovery

If investigation reveals a new dependency between two tickets assigned to the same wave:

1. The downstream ticket's status is set to `"re-queued"` with reason "new upstream dependency discovered from #NNN".
2. The downstream ticket is removed from the current wave and added to the next wave (or a new wave is created if none exists).
3. The wave schedule is persisted to disk.
4. The downstream ticket's work products (if any) are discarded -- it will restart from scratch in its new wave.

Because all tickets within a wave are dispatched simultaneously, the re-queued ticket may already be in progress. This is acceptable: the teammate will complete its work, but the orchestrator discards the results and re-processes the ticket in the correct wave with the upstream dependency's outputs available. No runtime cancellation is needed -- the wasted work is bounded to a single ticket's investigation and writing.

## Per-Ticket Spec Writing

Each ticket goes through the same investigation process as `/design`, but fully autonomous. The per-ticket flow is encoded in the prompt template `spec/spec-writer-prompt.md`.

### Step 1: Investigation

Same depth as `/design` Phase 2 -- for each design dimension:
- **Deep dive** (architectural decisions): 3 parallel agents (codebase scout, domain researcher, impact analyst) + challenger
- **Quick scan** (implementation approach): single codebase scout
- **Direct resolution** (no technical implications): decide immediately

All investigation results cascade -- prior ticket decisions inform subsequent investigations via the decisions log in the scratch directory.

If the ticket is flagged "complex" (5+ design dimensions or 3+ upstream contracts), use quick-scan for ALL dimensions. Summarize each finding to 2-3 sentences.

### Step 2: Dependency Discovery

After investigation completes but before writing begins:
1. Compare investigation findings against the current dependency graph.
2. If new cross-ticket dependencies found, write to `tickets/<ticket-number>/discoveries.json`.
3. If no new dependencies, write empty discoveries: `{ "dependencies": [] }`.

The orchestrator reconciles all discoveries after the wave completes:
- **Downstream ticket pending:** Update graph. Re-queue if same wave.
- **Downstream ticket in same wave (already dispatched):** Mark as `re-queued`. Orchestrator discards results and re-processes in a subsequent wave.
- **Downstream ticket already committed:** Set to `needs-respec`. Emit terminal alert. Add to summary report.

### Step 3: Autonomous Decision-Making

Where `/design` presents options and waits for the user, `/spec` decides:
- Synthesizes investigation results
- Picks the recommended option (or the only viable path)
- Documents reasoning in the design doc
- Assigns a confidence level to each decision

**Decision thresholds:**

| Confidence | Criteria | Action |
|------------|----------|--------|
| **High** | One option clearly dominates on technical merit, codebase alignment, and risk | Decide silently, document in design doc |
| **Medium** | 2+ viable options with trade-offs that could go either way | Decide, emit terminal alert. Err on the side of alerting. |
| **Low** | Requires domain knowledge, business context, or has irreversible consequences | Decide with strong recommendation to review. Emit terminal alert. |
| **Block** | Irreversible AND security/data-integrity implications (encryption, data migration, auth model) | Do NOT decide. Set ticket to `blocked`. Document context and options. Emit alert. |

**Alert format:**
```
SPEC ALERT [#123] (medium confidence): Chose X over Y -- see design doc for reasoning
SPEC ALERT [#123] (low confidence): Chose X over Y -- REVIEW RECOMMENDED before /build picks this up
SPEC ALERT [#123] (blocked): Cannot decide autonomously -- irreversible security/data-integrity decision. See scratch dir for options. Provide input on re-invocation.
```

### Step 4: Document Generation

Produces three artifacts per ticket in `tickets/<ticket-number>/output/`. The orchestrator copies these to `docs/plans/` after the wave completes:

**a. Design doc** (`YYYY-MM-DD-<topic>-design.md`):

Frontmatter:
```yaml
---
ticket: "#123"
epic: "#100"
title: "Brief ticket title"
date: "2026-03-21"
source: "spec"
---
```

Body sections:
- Current state analysis
- Target state
- Key decisions with confidence scores and alternatives considered
- Migration/implementation path (high-level direction, not task-level)
- Risk areas
- Acceptance criteria

**b. Implementation plan** (`YYYY-MM-DD-<topic>-implementation-plan.md`):

Same frontmatter as design doc (`ticket`, `epic`, `title`, `date`, `source` fields). Task-level granularity: which files to touch, approach per task, dependencies between tasks. Uses the crucible:planning task metadata format (Files, Complexity, Dependencies). NOT bite-sized TDD steps -- `/build`'s Plan Writer fills in that detail. `/build` still runs Plan Review + quality-gate on this plan.

**c. Contract** (`YYYY-MM-DD-<topic>-contract.yaml`):

See Contract Format section below for the full schema.

### Step 5: Contract Schema Validation

After generating the contract YAML, validate against the schema:

1. **Required fields present:** Verify `version`, `ticket`, `epic`, `title`, `date`, `api_surface`, and `invariants` all exist.
2. **Field value validation:**
   - `api_surface[].type` must be one of: `function`, `class`, `interface`, `endpoint`, `event`
   - `api_surface[].params` must be present for `function`, `class`, and `interface` types. Each param must have `name`, `type`, and `required` fields.
   - `invariants.checkable[].check_method` must be one of: `grep`, `code-inspection`, `file-structure`
   - `invariants.testable[].test_tag` must match the pattern `contract:<category>:<id>`
3. **Integration point validation:** For each entry in `integration_points`, verify that the referenced contract file exists in `docs/plans/` or the scratch directory's `contracts/` folder. If the referenced contract does not yet exist (upstream ticket not yet processed), log a warning but do not block.
4. **On validation failure:** Report specific errors. Re-dispatch the contract generation step with the validation errors as feedback. If the second attempt also fails, log the errors, mark the contract as having validation warnings, and continue -- do not block the entire run on a malformed contract.

### Step 6: Lightweight Per-Ticket Validation

Five checks before committing:

1. **Contract schema check:** Verify the contract passed Step 5 validation without errors.
2. **Acceptance criteria present:** Verify the design doc contains an acceptance criteria section with at least one concrete criterion.
3. **Invariants defined:** Verify the contract contains at least one checkable or testable invariant.
4. **Frontmatter complete:** Verify all required frontmatter fields (`ticket`, `epic`, `title`, `date`, `source`) are present in both the design doc and implementation plan.
5. **Cross-reference check:** Verify the design doc, implementation plan, and contract all reference the same ticket number.

If any check fails, set ticket status to `"failed"` with the specific validation errors. Log and continue.

### Step 7: Error Handling

On any failure during per-ticket processing:
1. Write status to `tickets/<ticket-number>/status.json`: set status to `"failed"`, record the error reason.
2. Log the failure to the terminal with the ticket number and error summary.
3. Continue processing remaining tickets -- do not halt the entire run.
4. Include failed tickets in the summary report with failure reasons.

**Re-invocation resume logic:**

On re-invocation of `/spec` with the same epic URL:
1. Detect existing scratch directory (match on epic URL in `invocation.md`). If not found at the canonical path, use the project-hash recovery procedure.
2. Read `ticket-status.json` to determine resume point.
3. **Skip** `committed` tickets. **Retry** `failed` and `re-queued` tickets. **Resume** `pending` tickets. **Re-process** `needs-respec` tickets with upstream contracts now available. **Unblock** `blocked` tickets: present blocking decision context and options to user, collect input, then resume.
4. Present the resume plan to the user before proceeding.

## Quality Gate Requirement (Non-Negotiable)

**Every quality gate in this pipeline MUST run to completion.** This is NOT optional — you may NOT self-assess whether a quality gate is "needed" based on ticket size, complexity, or scope. Spec dispatches quality gates on every committed ticket (potentially dozens), which creates strong temptation to skip on "simple" tickets. Do not yield to this temptation.

**Fixing findings is NOT the same as passing the gate.** The iteration loop must complete with a clean verification round (0 Fatal, 0 Significant on a fresh review). Spec is the highest-volume gate dispatcher — the short-circuit temptation is strongest here.

**The only valid skip** is an unambiguous user instruction specifically referencing the gate. General feedback is not skip approval.

**Gate tracking:** Before compiling the end-of-run summary, verify that every committed ticket has per-document gate round counts >= 1 with clean final rounds. If any gate was skipped with explicit user approval, record it as `USER_SKIP`. A zero without user approval indicates a gate was dropped — report this in the summary.

## End-of-Run Quality Gate

After all waves complete and all tickets are in terminal states, run a two-phase quality gate.

### Phase 1: Per-Document Quality Gates

For each committed ticket, dispatch two standard quality gate passes using existing artifact types:

1. **Design doc gate:** **(Non-negotiable — see Quality Gate Requirement.)** Dispatch `crucible:quality-gate` with artifact type `design` on the ticket's design doc. Review scope: Are decisions well-reasoned? Are acceptance criteria testable? Is the current-state analysis accurate?
2. **Implementation plan gate:** **(Non-negotiable — see Quality Gate Requirement.)** Dispatch `crucible:quality-gate` with artifact type `plan` on the ticket's implementation plan. Review scope: Are tasks concrete? Do they align with the design doc? Are dependencies between tasks identified?

These use the quality gate's existing iterative fix loop. Each gate runs within normal context budgets (one document per gate invocation). Per-document gates can run in parallel across tickets (via Agent Teams, or sequentially via Agent tool fallback).

### Phase 2: Cross-Ticket Integration Check

After all per-document gates pass, run a mandatory integration check across ticket boundaries using the prompt template `spec/integration-check-prompt.md`. **(Non-negotiable — see Quality Gate Requirement.)** This check is mandatory but is NOT dispatched through `crucible:quality-gate`'s iterative loop — it is a focused consistency review with targeted remediation.

**Input (kept small for context budget):**
- All contract YAML files (500-1000 tokens each)
- The final dependency graph
- The decisions log, **filtered**: only cross-ticket decisions and medium/low/block confidence decisions. Single-ticket high-confidence decisions are excluded to keep context within budget.

**Review scope:**
- Do contracts at integration points agree on signatures, types, and params?
- Are there contradictory decisions across tickets?
- Does the dependency graph match the actual integration points declared in contracts?
- Are there gaps -- tickets that should have integration points but don't?

**On findings:** Each finding identifies a specific ticket and document. The orchestrator routes the fix based on finding type:
- **Design or plan findings:** Dispatch a per-document quality gate (`design` or `plan` artifact type) on the identified document, with the integration finding included as review context.
- **Contract findings** (mismatched signatures, missing integration points, contradictory surface declarations): Re-run the contract generation pipeline for the affected ticket -- re-execute Step 4 (contract portion) and Step 5 (validation). Contracts are re-derived from the source of truth rather than patched by a fix agent.

**Verification re-pass:** After all integration-triggered fixes complete, re-run the cross-ticket integration check exactly once as a verification pass. If the verification pass finds new issues, do NOT enter another fix cycle -- escalate to the user: "Integration verification found [N] new issue(s) after fix pass. These require manual review: [list findings]." Include unresolved findings in the summary report. This bounds the integration check to exactly two passes (initial + verification).

## Dependency Analysis

The skill reads all tickets upfront and infers the dependency graph from content analysis:

- Reads every ticket's title, body, labels, and any linked issues
- Identifies explicit references ("after #123 is done", "depends on the interface from #456")
- Identifies implicit dependencies (ticket A defines an interface, ticket B consumes it)
- Builds a DAG, detects cycles

### Cycle Detection

On cycle detection:

1. **Present the cycle concretely:** Display the cycle as a list of edges: "#A depends on #B depends on #C depends on #A" with the specific dependency reason for each edge.
2. **Suggest breaking strategies:** For each edge in the cycle, assess which dependency is weakest and suggest: (a) merge the cyclic tickets if tightly coupled, (b) defer the weakest dependency edge -- process downstream without upstream contract, mark for re-validation, or (c) remove a dependency edge if the user determines it is not a true blocker.
3. **User resolves:** The user selects a breaking strategy or removes a specific dependency edge. The orchestrator updates the dependency graph, persists the modified `dependency-graph.json` with an annotation in `decisions.md`, and re-runs wave construction.
4. **If user unavailable (re-invocation scenario):** Apply the weakest-edge deferral strategy automatically. Remove the weakest edge, log the decision as a medium-confidence autonomous decision with a terminal alert, and continue. The deferred ticket is marked for re-validation after its upstream completes.

The dependency graph is presented to the user before execution begins. The user can override (reorder, force sequential, etc.) or approve.

The dependency graph is a living document -- it may be updated during investigation (see Dependency Discovery in Step 2). The initial graph is the best guess from ticket content; investigation reveals ground truth from the codebase.

## Skip Logic

- **Completed tickets** (checked off in the epic): skipped silently.
- **Committed tickets** (status `committed` in `ticket-status.json`): skipped silently on re-invocation.
- **Tickets with existing spec docs** (matching frontmatter `ticket` field in `docs/plans/*-design.md`): mentioned in output, skipped. User sees: "Skipping #123 -- spec doc already exists at `docs/plans/2026-03-15-auth-refactor-design.md`"
- **Needs-respec tickets** (status `needs-respec` in `ticket-status.json`): re-processed on re-invocation with upstream contracts available. If the re-processed ticket generates a filename matching an existing file in `docs/plans/`, the new output overwrites the old file.

## Branch Strategy

All tickets in an epic commit to a single branch: `spec/<epic-number>`. This avoids merge conflicts -- each ticket produces new files in `docs/plans/` with unique names, so parallel commits to the same branch never conflict.

- **Branch naming:** `spec/<epic-number>` (e.g., `spec/123`)
- **No per-teammate worktrees:** Teammates do not use git worktrees. Each teammate writes all outputs to its isolated scratch directory. Teammates perform no git operations.
- **Orchestrator handles git:** After each wave completes, the orchestrator copies outputs from per-ticket scratch directories to `docs/plans/`, then commits to the `spec/<epic-number>` branch. All git operations are serialized through the orchestrator. If the orchestrator needs a worktree for the epic branch (e.g., the user's working tree is on a different branch), it creates a single worktree for its own use.
- **Commit ordering:** Within a wave, the orchestrator commits each ticket's outputs sequentially. Across waves, commits are naturally sequential.
- **PR creation:** A single PR is created (if user opted in) from the `spec/<epic-number>` branch after all tickets complete.

## Contract Format

Machine-readable contracts solve the core challenge of two async agents communicating about interdependent work. Prose is ambiguous -- two LLMs reading the same paragraph extract different implications. Contracts make the seams structural.

### Schema

```yaml
# docs/plans/YYYY-MM-DD-<topic>-contract.yaml
version: "1.0"
ticket: "#123"
epic: "#100"
title: "Brief ticket title"
date: "2026-03-21"

# Public API surface -- what this ticket exposes
api_surface:
  - name: "FunctionOrClassName"
    type: "function|class|interface|endpoint|event"
    signature: "def function_name(param: Type) -> ReturnType"  # human-readable
    params:  # structured for machine comparison
      - name: "param"
        type: "Type"
        required: true
    returns: "ReturnType"
    description: "One-line purpose"
  - name: "/api/v2/resource"
    type: "endpoint"
    method: "POST"
    request_schema: "{ field: Type }"
    response_schema: "{ field: Type }"
    description: "One-line purpose"

# Hard constraints -- if violated, the implementation is wrong
# Split into checkable (verified by inspection) and testable (require runtime tests)
invariants:
  checkable:
    - id: "INV-1"
      description: "Must not add a runtime dependency on X"
      verification: "No import/require of X in production code"
      check_method: "grep"  # grep | code-inspection | file-structure
    - id: "INV-2"
      description: "Must be idempotent"
      verification: "Calling twice with same input produces same result"
      check_method: "code-inspection"
  testable:
    - id: "INV-3"
      description: "Response time < 200ms for the common case"
      verification: "Benchmark test with representative data"
      test_tag: "contract:perf:inv-3"  # implementer must write a test with this tag
    - id: "INV-4"
      description: "Must handle concurrent writes without data loss"
      verification: "Concurrent test with 10 writers"
      test_tag: "contract:concurrency:inv-4"

# Cross-ticket dependencies -- which other contracts this references
integration_points:
  - contract: "2026-03-21-auth-refactor-contract.yaml"
    ticket: "#124"
    relationship: "consumes"
    surface: "AuthService.validate_token"
    notes: "Depends on the new token format from #124"

# Decisions made where multiple viable paths existed
ambiguity_resolutions:
  - id: "AMB-1"
    decision: "Chose event-driven over polling"
    confidence: "high"
    alternatives: ["Polling every 5s", "WebSocket push"]
    reasoning: "Event-driven aligns with existing message bus; polling adds unnecessary load"
    reversibility: "Medium -- would require changing 3 consumers"
```

### Version Rejection Rule

Consumers encountering an unknown schema version must **reject** the contract with a clear error rather than silently ignoring unknown fields. This prevents silent incompatibility when the schema evolves.

### Invariant Categories

- **Checkable invariants** (`checkable`): Can be verified by code inspection, grep, or structural analysis during quality gate. The `check_method` field indicates how:
  - `grep` -- simple pattern matching in production code
  - `code-inspection` -- reading and reasoning about code
  - `file-structure` -- checking file existence/organization

- **Testable invariants** (`testable`): Cannot be verified by inspection alone -- they require runtime behavior. Each testable invariant has a `test_tag` that the implementer must use when writing the corresponding test. The quality gate verifies that a test with the matching tag exists and passes, but the implementer is responsible for writing a test that actually validates the invariant. This is an honest boundary: the quality gate can check that the test exists and passes, but cannot guarantee the test faithfully represents the invariant.

### Contract Cascading

When `/spec` resolves an ambiguity or defines an API surface on ticket N that affects ticket M:
1. The dependency graph identifies the impact.
2. Ticket M's contract is updated with the integration point.
3. Ticket M's spec-writing agent receives the upstream contract as context.
4. If ticket M is already in progress (same wave), the wave-based re-queuing mechanism handles the conflict -- ticket M is re-queued to the next wave where it will be re-processed with the upstream contract available.

### Required Fields Summary

| Field | Required | Notes |
|-------|----------|-------|
| `version` | Yes | Must be `"1.0"` |
| `ticket` | Yes | `"#NNN"` format |
| `epic` | Yes | `"#NNN"` format |
| `title` | Yes | Brief ticket title |
| `date` | Yes | `YYYY-MM-DD` format |
| `api_surface` | Yes | At least one entry |
| `api_surface[].type` | Yes | `function`, `class`, `interface`, `endpoint`, or `event` |
| `api_surface[].params` | Conditional | Required for `function`, `class`, `interface` types |
| `invariants` | Yes | Must have at least one checkable or testable |
| `invariants.checkable[].check_method` | Yes | `grep`, `code-inspection`, or `file-structure` |
| `invariants.testable[].test_tag` | Yes | Pattern: `contract:<category>:<id>` |
| `integration_points` | No | May be empty if no cross-ticket deps |
| `ambiguity_resolutions` | No | May be empty if all decisions were high-confidence |

## Red Flags

- Skipping Compression State Block emission at checkpoint boundaries
- Emitting a Compression State Block with stale or missing Key Decisions (decisions must be cumulative across all prior blocks)
- Allowing the Goal field to drift across successive Compression State Blocks (must match original user request)
- Exceeding 10 entries in the Key Decisions list without overflow-compressing the oldest
- Skipping a per-document quality gate because the ticket seems "small", "simple", or "trivial"
- Self-assessing that a quality gate is unnecessary based on perceived ticket complexity
- Declaring a quality gate "done" after fixing findings without a clean verification round (fixing is not passing)
- Skipping the integration check because "all per-document gates passed so it's fine"
- Interpreting general user feedback as approval to skip a quality gate that has not yet run — once a gate has run and presented findings to the user, the user's decision to proceed is authoritative

## Integration

**Sub-skills used:**
- **crucible:cartographer** -- consult mode, once at start of run
- **crucible:forge** -- feed-forward mode, once at start of run
- **crucible:design** -- investigation prompts (parallel agents) reused for autonomous investigation. Templates in `design/investigation-prompts.md`.
- **crucible:quality-gate** -- per-document gates (artifact types `design` and `plan`) + cross-ticket integration check on contracts
- **crucible:worktree** -- orchestrator-only, for the epic branch if the user's working tree is on a different branch

**Prompt templates:**
- `spec/spec-writer-prompt.md` -- Per-ticket teammate prompt encoding the full 7-step spec writing flow
- `spec/integration-check-prompt.md` -- Cross-ticket integration check prompt for Phase 2 quality gate

**Trigger words:** `/spec`, "spec out", "write specs for", "spec this epic"

**Contract between /spec and /build:** `/spec` produces files in `docs/plans/` with the naming convention `YYYY-MM-DD-<topic>-{design,implementation-plan,contract}.{md,yaml}`, with YAML frontmatter containing `ticket`, `epic`, `title`, `date`, and `source` fields. `/build` locates these files by scanning `docs/plans/` for frontmatter with a matching `ticket` field. The contract YAML schema (version 1.0) is the interface format -- both skills must agree on it.

## Key Principles

- **Autonomous execution** -- No human input after initial invocation. Investigate, decide, document, flag uncertainty.
- **Wave-based parallelism** -- Independent tickets run in parallel within waves. Dependent tickets are sequenced across waves. No runtime cancellation needed.
- **Contract-first output** -- Machine-readable contracts are a first-class output, not an afterthought. Contracts make inter-ticket interfaces structural and verifiable.
- **Disk-persisted state** -- All critical state lives on disk in the scratch directory. Context compaction cannot lose progress. The orchestrator never relies solely on context memory.
- **Graceful degradation** -- Agent Teams fallback to sequential dispatch. Re-invocation resumes from scratch directory state. Failed tickets are isolated. Blocked tickets defer to the user.
- **Cascading context** -- Every decision informs subsequent investigations. Upstream contracts flow to downstream tickets. The decisions log is the running memory of the epic.
- **Quality over velocity** -- Per-ticket validation, per-document quality gates, cross-ticket integration checks. The pipeline produces correct, consistent output even at the cost of additional passes.
