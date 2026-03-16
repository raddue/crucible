---
name: audit
description: "Review existing subsystems for bugs, robustness gaps, inconsistencies, and architecture issues. Triggers on 'audit', 'review subsystem', 'check the save system', 'examine the UI code', or any task requesting adversarial review of existing (not newly written) code."
---

# Audit

Adversarial review of existing subsystems. Dispatches parallel analysis agents across four lenses, synthesizes findings, and offers to file them in the user's issue tracker.

**Announce at start:** "Running audit on [subsystem name]."

**Skill type:** Rigid -- follow exactly, no shortcuts.

**Purpose:** Review existing subsystems in a repo and report findings. Distinct from quality-gate (which fixes artifacts in a loop) -- audit is find-and-report only.

**Model:** Opus (orchestrator and analysis agents). Sonnet (scoping exploration). If the orchestrator session is not running Opus, warn: "Audit requires Opus-level reasoning for synthesis. Results may be degraded."

## Why This Exists

Per-task quality gates (red-team, inquisitor) review artifacts produced during development. But the bugs that accumulate in stable code -- the ones nobody's looked at critically in months -- live in subsystems that passed their original review but have drifted, accrued inconsistencies, or developed subtle failure modes. The audit skill performs a focused adversarial review of any existing subsystem on demand.

## Distinction from Related Skills

| Skill | Reviews | When | Fixes? | Scope |
|-------|---------|------|--------|-------|
| red-team | A single artifact just produced | During creation | Yes (loop) | One doc/plan/impl |
| inquisitor | A complete implementation diff | During build phase 4 | Yes (automated fix cycle) | Changes only (diffs) |
| **audit** | Existing code in a subsystem | On demand | No (reports only) | Existing codebase |

## Communication Requirement (Non-Negotiable)

**Between every agent dispatch and every agent completion, output a status update to the user.** This is NOT optional -- the user cannot see agent activity without your narration.

Every status update must include:
1. **Current phase** -- Which phase you're in
2. **What just completed** -- What the last agent reported
3. **What's being dispatched next** -- What you're about to do and why
4. **Lens status** -- Which lenses have reported vs. still in flight, finding counts so far

**After compaction:** Re-read the scratch directory and current state before continuing. See Compaction Recovery below.

**Examples of GOOD narration:**
> "Phase 2: Correctness and Robustness lenses complete (4 findings, 2 findings). Architecture still in flight. Consistency Agent A returned -- flagged 6 files, dispatching Agent B."

> "Phase 2 complete. All 4 lenses reported: 14 total findings. Moving to Phase 3 synthesis."

## Design Decisions

1. **Find and report only** -- no fixing. Audit surfaces issues; user decides what to act on.
2. **Cross-reference existing open issues** -- avoid filing duplicates, using whatever tools are available in the environment.
3. **Issue filing format is user's choice** -- offer individual issues per finding OR one umbrella issue with checklist. Let user pick.
4. **Tracker-agnostic** -- the skill stores which tracker and project the user uses, not how to use it. The agent uses whatever tools are available in the environment (MCP servers, CLIs, APIs) to interact with the tracker. If the agent can't figure out how to file, it asks the user. If the user mentions a different tracker or project during an invocation, update the stored preference.

## Preferences Storage

Stored in `~/.claude/projects/<project-hash>/memory/audit/preferences.md`:

```markdown
## Issue Tracker
- Tracker: github
- Project: owner/repo
```

First audit run: ask the user which tracker and project. Persist for future runs. Update if user indicates a change.

## Scratch Directory

**Canonical path:** `~/.claude/projects/<project-hash>/memory/audit/scratch/<run-id>/`

The `<run-id>` is a timestamp generated at the start of Phase 1 (e.g., `2026-03-15T14-30-00`). This same identifier is used for all scratch files and session logs throughout the run.

All relative paths in this document (e.g., `scratch/<run-id>/manifest.md`) are relative to `~/.claude/projects/<project-hash>/memory/audit/`.

**Stale cleanup:** At the start of each audit run, delete scratch directories whose timestamps are older than 1 hour. Do not delete recent directories (could belong to concurrent sessions).

## Session Tracking

- **Metrics:** Log agent dispatches, completion times, finding counts to `/tmp/crucible-audit-metrics-<run-id>.log`
- **Decision journal:** Log scoping decisions, chunking rationale, dedup merges to `/tmp/crucible-audit-decisions-<run-id>.log`

The `<run-id>` is the same timestamp used for the scratch directory.

## Compaction Recovery

After context compaction, the orchestrator must:
1. Read `scratch/<run-id>/` to determine current state:
   - `manifest.md` exists → Phase 1 scoping is complete
   - `gate-approved.md` exists → user confirmed scope, Phase 2 can proceed
   - `<lens>-findings.md` files → those lenses have reported
   - `consistency-a-findings.md` without `consistency-b-findings.md` → Agent B still needed
   - `report.md` exists → Phase 3 synthesis is complete, proceed to Phase 4
2. Re-read relevant files from disk based on current phase
3. Output current status to user before continuing
4. Continue with the appropriate phase

**Phase-specific recovery:**
- **Phase 1:** If `manifest.md` exists but `gate-approved.md` does not, re-present the manifest to the user for confirmation.
- **Phase 2:** Check which lenses have findings files. Dispatch any remaining lenses.
- **Phase 3:** If compaction occurs during synthesis, re-read all findings files and re-run synthesis. This is safe — synthesis is idempotent.
- **Phase 4:** If `report.md` exists, re-read it and continue with cross-referencing/filing.

## Phase 1: Scoping

Dispatch: `Agent tool (subagent_type: Explore, model: sonnet)` using `audit-scoping-prompt.md`

1. User names a subsystem ("save/load", "UI", "networking")
2. Consult cartographer data if it exists for subsystem boundaries
3. If no cartographer data: dispatch a Sonnet exploration agent to identify the subsystem boundary using the scoping prompt template.
4. If the subsystem cannot be cleanly scoped (files share no common dependency chain, naming convention, or functional cohesion), report the scoping difficulty to the user and ask for clarification or a file list.
5. **Output:** A manifest of files belonging to the subsystem (paths + brief role descriptions). Write to `scratch/<run-id>/manifest.md`.

**USER GATE:** Present the manifest to the user. Do not proceed to Phase 2 until the user confirms the scope is correct. User may add/remove files or refine the boundary. When the user approves, write `scratch/<run-id>/gate-approved.md` (contents: timestamp + user confirmation) as a compaction recovery marker.

If the user removes all files or the manifest is empty: abort cleanly with "No files in scope -- audit cancelled."

## Phase 2: Analysis

Dispatch: `Task tool (general-purpose, model: opus)` per lens, in parallel (matching inquisitor pattern). Fallback if parallel dispatch fails: dispatch sequentially via `Task tool (general-purpose, model: opus)`, with a one-time note to user: "Parallel dispatch unavailable -- running analysis lenses sequentially."

**Write-on-complete:** As each agent completes, immediately write its findings to `scratch/<run-id>/<lens>-findings.md`. Do not wait for Phase 3. For the Consistency lens, use distinct filenames: `consistency-a-findings.md` for Agent A's triage output, `consistency-b-findings.md` for Agent B's confirmed findings.

### Context Management

**Tier 1 -- Overview:** The orchestrator builds a condensed summary of the subsystem: file manifest with role descriptions, key public interfaces/contracts, dependency graph. **Target: 500 lines. Flexible up to 800 lines for subsystems with complex API surfaces.** If the subsystem exceeds what can be summarized in 800 lines, chunk the subsystem (see Chunking below).

**Tier 2 -- Deep dive:** The orchestrator partitions source files across agents by relevance to their lens. **Hard cap: 1500 lines of total prompt content per agent** (Tier 1 overview + Tier 2 source + prompt template). If a lens requires more files than fit, the orchestrator generates brief summaries of overflow files (2-3 lines per file: path, responsibility, key interfaces) and includes those instead of full source. If an agent's findings reference a summarized file, the orchestrator may dispatch a **follow-up agent** for that lens with the flagged files at full source.

### Chunking (Large Subsystems)

If the subsystem is too large to summarize within the 800-line Tier 1 cap:

- Split by dependency subgraph -- files that call each other stay together. Prefer natural boundaries (directories, modules, namespaces).
- **Soft cap: 4 chunks maximum.** If more than 4 chunks would be needed, advise the user to narrow the subsystem scope instead.
- Present the chunking plan at the Phase 1 user gate: "This subsystem is large. I'll audit it in N chunks (~5N analysis agents including Consistency two-phase). Chunk descriptions: [list]. Approve?"
- Each chunk gets its own set of analysis agents.
- Synthesis (Phase 3) merges findings across all chunks.
- Cross-chunk concerns: the Tier 1 overview for each chunk includes a "cross-chunk interface" section describing how this chunk interacts with others. All lenses receive this section and should consider cross-chunk issues within their domain.

### The 4 Lenses

Each lens is dispatched as a parallel agent using its prompt template.

All lenses output structured findings with these common fields: `{severity, file, line_range, evidence, description}`. Individual lenses add lens-specific fields (e.g., Correctness adds `scenario`, Robustness adds `failure_scenario`, Architecture adds `impact`, Consistency adds `convention_violated`). The orchestrator's Phase 3 deduplication uses the common fields for matching; lens-specific fields are preserved in the final report.

#### Correctness

**Prompt:** `audit-correctness-prompt.md`
**Question:** "What's actually broken or will break?"
**Looks for:** Bugs, race conditions, edge cases, logic errors, off-by-one, null dereferences, unreachable code paths.
**Gets:** Files with core logic, state management, data flow.
**Dispatch:** Single agent.

#### Robustness

**Prompt:** `audit-robustness-prompt.md`
**Question:** "What happens when things go wrong?"
**Looks for:** Missing error handling at boundaries, unhandled failure modes, missing validation, silent data corruption, resource leaks.
**Gets:** Files at system boundaries, I/O, serialization.
**Dispatch:** Single agent.

#### Consistency

**Prompt:** `audit-consistency-prompt.md`
**Question:** "Does this code follow its own patterns?"
**Looks for:** Pattern violations, naming drift, convention breaks, inconsistent error handling styles, mixed paradigms.
**Dispatch:** Two sequential agents (orchestrator dispatches Agent A, reads results, then dispatches a separate Agent B).

- **Agent A:** Receives the Tier 1 overview (which includes the file manifest with role descriptions) + conventions.md from cartographer if available. The overview IS the summary -- do not add additional file-level summaries. Returns: list of files flagged for suspected inconsistencies with rationale. Subject to the 1500-line hard cap.
- **Agent B:** Receives full source for Agent A's flagged files only. Subject to the same 1500-line hard cap. If Agent A flags more files than fit, the orchestrator applies the same overflow-summary mechanism (summarize overflow files, include full source for highest-priority flags, dispatch follow-up if needed). Returns: confirmed findings with evidence.
- **Timing:** Agent A dispatches in parallel with the other three lenses. Agent B dispatches after Agent A completes. The orchestrator proceeds to Phase 3 once all lenses (including Consistency Agent B) have reported. The other three lenses may finish earlier -- this is expected and acceptable.

#### Architecture

**Prompt:** `audit-architecture-prompt.md`
**Question:** "Is this well-structured?"
**Looks for:** Coupling issues, abstraction leaks, missing contracts, dependency direction violations, god objects, circular dependencies.
**Gets:** Tier 1 overview + public API surfaces.
**Dispatch:** Single agent.

## Phase 3: Synthesis

Orchestrator reads all confirmed findings from `scratch/<run-id>/` on disk. Read `correctness-findings.md`, `robustness-findings.md`, `consistency-b-findings.md`, and `architecture-findings.md`. Do NOT read `consistency-a-findings.md` (triage data, not confirmed findings).

1. **Deduplicate:** When two findings reference overlapping file + line_range and describe the same underlying concern (using common fields: severity, file, line_range, evidence, description), merge into one finding noting both lenses. Preserve lens-specific fields from both. **Tie-breaking rule:** When in doubt, keep both findings as separate items but note they may be related. Err on the side of presenting more findings rather than silently merging.
2. **Severity-rank:** Fatal first, then Significant, then Minor.
3. **Group by theme** (e.g., "Error Handling," "State Management," "API Contracts").
4. **Write report** to `scratch/<run-id>/report.md`.

## Phase 4: Reporting

1. Present the ranked, grouped findings to user.

2. **Cross-reference existing issues:** Using whatever tools are available in the environment (MCP servers, CLIs, etc.), search for existing open issues using specific file paths and error descriptions from findings as search terms.
   - **Budget:** Cross-reference the top 10 findings by severity (Fatal first, then Significant). Check at most 2-3 search queries per finding.
   - If the tracker is slow or unresponsive after 3+ failed/timed-out queries, skip remaining cross-references.
   - Present at most 2-3 candidate matches per finding.
   - Flag likely duplicates with "Possible existing issue: [reference]" -- never silently drop a finding; let user decide.
   - If cross-referencing isn't possible (no tools available, tracker not configured), skip it and just present findings.

3. Ask user: **"File as individual issues, one umbrella issue with checklist, or skip filing?"**
   - If filing: use available environment tools to create issues with structured body (severity tag, file references, evidence snippet).

4. **Record to cartographer:** After completion, dispatch cartographer recorder (Mode 1) with the Phase 1 manifest only. The manifest was deliberately scoped during exploration and is reliable structural data. Do NOT feed incidental observations from Phase 2 bug-hunting agents to cartographer -- those are unverified structural inferences.

5. **Cleanup:** Delete the `scratch/<run-id>/` directory only after ALL Phase 4 actions are complete (issue filing, cartographer recording). Do not clean up prematurely -- the report on disk is needed for compaction recovery during Phase 4.

## Prompt Templates

- `audit-scoping-prompt.md` -- Phase 1 subsystem scoping dispatch (`Agent tool, subagent_type: Explore, model: sonnet`)

Analysis lens templates (all use `Task tool, general-purpose, model: opus`):
- `audit-correctness-prompt.md` -- Correctness lens dispatch
- `audit-robustness-prompt.md` -- Robustness lens dispatch
- `audit-consistency-prompt.md` -- Consistency lens dispatch (documents two-agent protocol)
- `audit-architecture-prompt.md` -- Architecture lens dispatch

Each analysis template includes:
- Dispatch metadata (for orchestrator reference): `Task tool (general-purpose, model: opus)`
- The lens definition and what to look for
- Placeholders for: Tier 1 overview, Tier 2 source partition
- Output format with common fields (`severity, file, line_range, evidence, description`) plus lens-specific fields
- Instruction: "Only flag issues you can point to specific code evidence for. No speculative findings."
- Context self-monitoring (report partial progress at 50%+ utilization)

## Guardrails

**Analysis agents must NOT:**
- Modify any code (audit is read-only)
- Flag issues without specific code evidence (no speculation)
- Overlap with another lens's findings (if borderline, the more specific lens owns it)
- Exceed 5 findings per lens without strong justification (focus on highest-impact issues)

**The orchestrator must NOT:**
- Proceed to Phase 2 without user-confirmed scoping manifest
- File issues without explicit user approval
- Silently drop findings that match existing issues (always show, let user decide)
- Exceed 1500 lines of total prompt content in any agent dispatch
- Feed Phase 2 structural inferences to cartographer (Phase 1 manifest only)
- Skip narration between agent dispatches (Communication Requirement)
- Dispatch more than ~20 agents without user awareness (chunking approval includes agent count)

## Red Flags

- Treating this as a fix loop (audit reports, it does not fix)
- Hardcoding tracker-specific commands (use available environment tools)
- Losing agent results to context compaction (write to disk immediately)
- Skipping session metrics or decision journal
- Cleaning up scratch directory before Phase 4 is fully complete

## Integration

- **Dispatches:** Audit-specific prompt templates (scoping, correctness, robustness, consistency [2 agents], architecture)
- **Consults:** `crucible:cartographer` (Mode 2: consult map) for subsystem scoping and conventions
- **Records to:** `crucible:cartographer` (Mode 1: record discovery) -- Phase 1 manifest only
- **Pairs with:** `crucible:forge` -- audit findings could inform retrospective if they reveal systemic patterns
- **Called by:** Standalone only (user invokes directly). Not part of any pipeline.
- **Does NOT use:** `crucible:quality-gate` (audit is not a fix loop), `crucible:red-team` (designed for single artifacts)
