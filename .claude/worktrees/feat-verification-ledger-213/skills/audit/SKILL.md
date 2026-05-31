---
name: audit
description: "Adversarial review of code subsystems or non-code artifacts (design docs, plans, concepts) through parallel analytical lenses. Triggers on 'audit', 'review subsystem', 'audit this design', 'review this plan', 'audit concept', 'check the save system', 'examine the UI code', or any task requesting adversarial review of existing artifacts."
---

# Audit

Adversarial review of code subsystems or non-code artifacts. Dispatches parallel analysis agents across four lenses adapted to the artifact type, synthesizes findings, and offers to file them in the user's issue tracker.

**Announce at start:** "Running audit on [target name] (type: [artifact type])."

**Skill type:** Rigid -- follow exactly, no shortcuts.

**Purpose:** Review existing subsystems in a repo and report findings. Distinct from quality-gate (which fixes artifacts in a loop) -- audit is find-and-report only.

**Model:** Opus (orchestrator and analysis agents). Sonnet (scoping exploration). If the orchestrator session is not running Opus, warn: "Audit requires Opus-level reasoning for synthesis. Results may be degraded."

<!-- CANONICAL: shared/dispatch-convention.md -->
All subagent dispatches use disk-mediated dispatch. See `shared/dispatch-convention.md` for the full protocol.

## Artifact Types

Audit supports 4 artifact types, each with tailored analytical lenses:

| Artifact Type | Lens 1 | Lens 2 | Lens 3 | Lens 4 |
|---|---|---|---|---|
| `code` (default) | Correctness | Robustness | Consistency | Architecture |
| `design` | Technical Soundness | Integration Impact | Edge Cases | Scope Clarity |
| `plan` | Feasibility | Risk & Dependencies | Completeness | Assumptions |
| `concept` | Problem-Solution Fit | Feasibility & Cost | Stakeholder Alignment | Blind Assumptions |

### Invocation

```
/audit save/load                                          # code (default)
/audit docs/plans/2026-04-01-auth-design.md               # auto-detects design
/audit docs/plans/2026-04-01-plan.md artifact_type: plan   # explicit type
/audit "We should build a CLI tool that..."               # auto-detects concept
```

**Parameters:**
- `target` (required) — subsystem name, file path, or freeform text
- `artifact_type` (optional) — `code | design | plan | concept`. Auto-detected if omitted.

### Auto-Detection

Priority chain when `artifact_type` is not provided:

1. Directory or subsystem name → `code` (existing behavior)
2. File with code extension (`.py`, `.ts`, `.go`, etc.) → `code`
3. YAML frontmatter contains `source: "design"` or `source: "spec"` → `design`
4. YAML frontmatter contains `source: "plan"` or title contains "implementation plan" → `plan`
5. No file path (freeform text input) → `concept`
6. Ambiguous → ask user: "I detected a markdown document but can't determine its type. Is this a design doc, plan, or concept?"

**Limitation:** Frontmatter-based detection relies on Crucible's `source` field convention. Repos without this convention will hit the "ambiguous → ask user" fallback more often. The explicit `artifact_type` parameter is the reliable path for any repo.

### Non-Code Lens Configurations

#### `design` — Design Documents

| Lens | Core Question | Focus Areas | Exclusions |
|---|---|---|---|
| Technical Soundness | "Are the technical decisions well-reasoned?" | Trade-off analysis quality, constraint identification, decision-evidence alignment, alternative exploration depth | Integration concerns (Integration Impact lens), boundary conditions (Edge Cases lens), scope questions (Scope Clarity lens) |
| Integration Impact | "How does this design interact with existing systems?" | Breaking changes identified, migration path, dependency awareness, blast radius assessment | Decision quality (Technical Soundness lens), boundary conditions (Edge Cases lens), scope questions (Scope Clarity lens) |
| Edge Cases | "What happens at the boundaries?" | Failure modes addressed, boundary conditions, concurrent usage, data edge cases, degraded-mode behavior | Decision quality (Technical Soundness lens), integration concerns (Integration Impact lens), scope questions (Scope Clarity lens) |
| Scope Clarity | "Is the scope well-defined and appropriate?" | Non-goals stated, scope-to-problem fit, YAGNI compliance, acceptance criteria testability | Decision quality (Technical Soundness lens), integration concerns (Integration Impact lens), boundary conditions (Edge Cases lens) |

#### `plan` — Strategic Plans, Implementation Plans, PRDs

| Lens | Core Question | Focus Areas | Exclusions |
|---|---|---|---|
| Feasibility | "Can this actually be executed as described?" | Resource requirements vs availability, timeline realism, skill/capability assumptions, tooling prerequisites | Risk identification (Risk & Dependencies lens), missing sections (Completeness lens), environmental assumptions (Assumptions lens) |
| Risk & Dependencies | "What could derail execution?" | External dependency risks, sequencing risks, single points of failure, rollback provisions, blast radius of partial failure | Execution feasibility (Feasibility lens), missing sections (Completeness lens), environmental assumptions (Assumptions lens) |
| Completeness | "What's missing from this plan?" | Phases covered, milestones defined, success criteria measurable, testing strategy present, communication plan | Execution feasibility (Feasibility lens), risk identification (Risk & Dependencies lens), environmental assumptions (Assumptions lens) |
| Assumptions | "What's being taken for granted?" | Environmental assumptions, team capacity assumptions, technical assumptions, timeline assumptions, stakeholder alignment assumptions | Execution feasibility (Feasibility lens), risk identification (Risk & Dependencies lens), missing sections (Completeness lens) |

#### `concept` — Product Concepts, Proposals, Early-Stage Ideas

| Lens | Core Question | Focus Areas | Exclusions |
|---|---|---|---|
| Problem-Solution Fit | "Does this concept solve a real problem?" | Problem definition clarity, target audience identified, value proposition specificity, differentiation from existing solutions | Build feasibility (Feasibility & Cost lens), stakeholder concerns (Stakeholder Alignment lens), hidden assumptions (Blind Assumptions lens) |
| Feasibility & Cost | "Is this achievable and worth the investment?" | Build vs buy analysis, resource requirements, timeline expectations, opportunity cost, maintenance burden | Problem-solution fit (Problem-Solution Fit lens), stakeholder concerns (Stakeholder Alignment lens), hidden assumptions (Blind Assumptions lens) |
| Stakeholder Alignment | "Who needs to agree and will they?" | Decision-makers identified, conflicting incentives surfaced, adoption path realistic, organizational readiness | Problem-solution fit (Problem-Solution Fit lens), build feasibility (Feasibility & Cost lens), hidden assumptions (Blind Assumptions lens) |
| Blind Assumptions | "What is this concept taking for granted?" | Market assumptions, user behavior assumptions, technical assumptions, competitive landscape assumptions, sustainability assumptions | Problem-solution fit (Problem-Solution Fit lens), build feasibility (Feasibility & Cost lens), stakeholder concerns (Stakeholder Alignment lens) |

### Non-Code Finding Format

Non-code findings use the same severity levels (Fatal/Significant/Minor) but replace code-specific fields:

| Field | Code | Non-Code |
|---|---|---|
| Location | `file` + `line_range` | `section` (nearest markdown heading, e.g., `## Key Decisions > DEC-3`) |
| Lens-specific | `scenario`, `failure_scenario`, `convention_violated`, `impact` | `concern` |
| Evidence | Code quotes | Document text quotes |

For artifacts without markdown headings, `section` uses a brief quoted phrase from the opening of the relevant paragraph.

### Non-Code Blind-Spots Categories

When auditing non-code artifacts, the blind-spots agent hunts for document-level gaps:

- Internal contradictions (artifact says X in one section, Y in another)
- Unstated assumptions (decisions depending on undocumented conditions)
- Missing stakeholder perspectives (who would disagree with this?)
- Scope boundary gaps (what's just outside scope that could cause problems?)
- Silent dependencies (external factors assumed to remain true)
- Logical leaps (conclusions not supported by the preceding argument)

## Why This Exists

Per-task quality gates (red-team, inquisitor) review artifacts produced during development. But the bugs that accumulate in stable code -- the ones nobody's looked at critically in months -- live in subsystems that passed their original review but have drifted, accrued inconsistencies, or developed subtle failure modes. The audit skill performs a focused adversarial review of any existing subsystem on demand.

## Distinction from Related Skills

| Skill | Reviews | When | Fixes? | Scope |
|-------|---------|------|--------|-------|
| red-team | A single artifact just produced | During creation | Yes (loop) | One doc/plan/impl |
| inquisitor | A complete implementation diff | During build phase 4 | Yes (automated fix cycle) | Changes only (diffs) |
| **audit** | Existing code subsystems or non-code artifacts | On demand | No (reports only) | Existing codebase or documents |

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

> "Phase 2 (design audit): Technical Soundness and Integration Impact complete (3 findings, 1 finding). Edge Cases and Scope Clarity still in flight."

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
**Skill:** audit
**Phase:** <current phase, e.g. "2 — Analysis">
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
## Lenses (code audit)
- Correctness: DONE (4 findings)
- Robustness: DONE (2 findings)
- Architecture: IN PROGRESS
- Consistency: PENDING
- Blind-spots: PENDING

## Lenses (design audit — example)
- Technical Soundness: DONE (3 findings)
- Integration Impact: DONE (1 finding)
- Edge Cases: IN PROGRESS
- Scope Clarity: PENDING
- Blind-spots: PENDING
```

Use the lens names matching the current artifact type.

### Health State Machine

Health transitions are one-directional within a phase: GREEN -> YELLOW -> RED. Phase boundaries reset to GREEN.

- **Phase boundaries** (reset to GREEN): Phase 1->2, 2->2.5, 2.5->3, 3->4
- **YELLOW:** lens agent running longer than 10 minutes, blind-spots agent finds significant gap
- **RED:** multiple lens agents fail, user gate timeout

When health is YELLOW or RED, include `**Suggested Action:**` with a concrete, context-specific sentence (e.g., "Architecture lens running >10 minutes. May be processing a large subsystem — check if scope needs narrowing.").

### Inline CLI Format

Output concise inline status alongside the status file write:
- **Minor transitions** (dispatch, completion): one-liner, e.g. `Phase 2 [3/5 lenses] Robustness complete (2 findings) | GREEN | 22m`
- **Phase changes and escalations**: expanded block with `---` separators
- **Health transitions**: always expanded with old -> new health

### Compaction Recovery

After compaction, before re-writing the status file:
1. Read the existing `pipeline-status.md` to recover `Started` timestamp and `Recent Events` buffer
2. Reconstruct phase, health, and skill-specific body from internal state files
3. Write the updated status file
4. Output inline status to CLI

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

After context compaction, the orchestrator must first determine whether this is a code or non-code audit:

### Step 1: Detect Audit Type

Read `scratch/<run-id>/artifact-type.md`. If present and not `code`, follow non-code recovery. If absent, follow code recovery (existing behavior).

### Code Recovery (artifact_type: code)

1. Read `scratch/<run-id>/` to determine current state:
   - `manifest.md` exists → Phase 1 scoping is complete (whether produced by recon's subsystem-manifest or the fallback scoping agent -- both write the same format)
   - `gate-approved.md` exists → user confirmed scope, Phase 2 can proceed
   - `<lens>-partition.md` files → those lenses' Tier 2 source partitions are recorded
   - `<lens>-findings.md` files → those lenses have reported
   - `consistency-a-findings.md` without `consistency-b-findings.md` → Agent B still needed
   - `blindspots-findings.md` exists → Phase 2.5 is complete
   - `report.md` exists → Phase 3 synthesis is complete, proceed to Phase 4
2. Re-read relevant files from disk based on current phase
3. Output current status to user before continuing
4. Continue with the appropriate phase

**Phase-specific recovery (code):**
- **Phase 1:** If `manifest.md` exists but `gate-approved.md` does not, re-present the manifest to the user for confirmation.
- **Phase 2:** Check which lenses have findings files. Dispatch any remaining lenses.
- **Phase 2.5:** If all four lens findings files exist but `blindspots-findings.md` does not, rebuild the coverage map from partition records and findings files (see Coverage Map Construction), then dispatch the blind-spots agent. If `blindspots-findings.md` exists, Phase 2.5 is complete.
- **Phase 3:** If compaction occurs during synthesis, re-read all findings files (including blindspots) and re-run synthesis. This is safe — synthesis is idempotent.
- **Phase 4:** If `report.md` exists, re-read it and continue with cross-referencing/filing.

### Non-Code Recovery (artifact_type: design | plan | concept)

1. Read `artifact-type.md` to recover the artifact type
2. **Phase 1 recovery:** If `artifact-type.md` exists but `gate-approved.md` does not, re-present the scope summary to the user for confirmation
3. **Phase 2 recovery:** Look for `<lens-name-kebab>-findings.md` files matching the type's lens names (e.g., `technical-soundness-findings.md` for design). Dispatch any lenses that don't have findings files.
4. **Phase 2.5 recovery:** If all 4 lens findings exist but `noncode-blindspots-findings.md` does not, build the lens summary and dispatch the non-code blind-spots agent. If `noncode-blindspots-findings.md` exists, Phase 2.5 is complete.
5. **Phase 3/4 recovery:** Same as code path — re-read findings, re-run synthesis if needed, continue with reporting.

## Phase 1: Scoping

### Code Path (artifact_type: code)

1. User names a subsystem ("save/load", "UI", "networking")
2. Consult cartographer data if it exists for subsystem boundaries
3. **Dispatch recon** with subsystem-manifest module:

   ```
   /recon
     task: "Subsystem manifest for audit: <subsystem name>"
     scope: "<subsystem-path or cartographer-identified boundary>"
     modules: ["subsystem-manifest"]
   ```

   Parse the subsystem manifest from recon's brief to produce the file list + role descriptions for the USER GATE. Write to `scratch/<run-id>/manifest.md` in the same format the scoping agent produces (file paths + brief role descriptions). This format compatibility ensures all downstream code (Phase 2, compaction recovery) works without modification.

   **On recon failure:** "Recon failed: [reason]. Falling back to scoping exploration agent." Dispatch the fallback scoping agent: `Agent tool (subagent_type: Explore, model: sonnet)` using `audit-scoping-prompt.md` (existing behavior).

4. If the subsystem cannot be cleanly scoped (files share no common dependency chain, naming convention, or functional cohesion), report the scoping difficulty to the user and ask for clarification or a file list.
5. **Output:** A manifest of files belonging to the subsystem (paths + brief role descriptions). Write to `scratch/<run-id>/manifest.md`.

**USER GATE:** Present the manifest to the user. Do not proceed to Phase 2 until the user confirms the scope is correct. User may add/remove files or refine the boundary. When the user approves, write `scratch/<run-id>/gate-approved.md` (contents: timestamp + user confirmation) as a compaction recovery marker.

If the user removes all files or the manifest is empty: abort cleanly with "No files in scope -- audit cancelled."

### Non-Code Path (artifact_type: design | plan | concept)

No scoping agent needed — the artifact IS the scope. The orchestrator:

1. **Validate artifact:** Read the file or accept freeform text input. If file does not exist, abort.
2. **Detect or confirm type:** Apply auto-detection (see Auto-Detection above) or use explicit `artifact_type`.
3. **Write type marker:** Write `scratch/<run-id>/artifact-type.md` containing the detected type. This file is the compaction recovery marker for non-code audits.
4. **Gather supporting context:** Parse the artifact for references:
   - Markdown links (`[text](path)`)
   - File paths (`path/to/file.ext`)
   - Issue references (`#NNN`)
   - Explicit "see also" references
   For each referenced file that exists locally: read and include as supporting context. For issue references: fetch title and body via `gh issue view`. **Soft cap: 2000 lines total.** If exceeded: prioritize files referenced in decision-critical sections (Key Decisions, Risk Areas) over background references. Truncate with note: "[truncated — 2000-line context cap reached]". If no references found: proceed with artifact-only context.
5. **Present user gate:** "Auditing [artifact name] as a [type]. Supporting context: [list of referenced docs, if any]. Proceed?"
6. **Write gate marker:** Write `scratch/<run-id>/gate-approved.md` (same as code path).

## Phase 2: Analysis

### Non-Code Dispatch (artifact_type: design | plan | concept)

Dispatch: `Task tool (general-purpose, model: opus)` per lens, in parallel, using `audit-noncode-lens-prompt.md` with lens-specific instruction injection.

For each of the 4 lenses matching the artifact type (see Artifact Types table):
1. Fill the template placeholders: `{{LENS_NAME}}`, `{{LENS_QUESTION}}`, `{{LENS_FOCUS_AREAS}}`, `{{LENS_EXCLUSIONS}}`, `{{ARTIFACT_TYPE}}`, `{{ARTIFACT_CONTENT}}`, `{{SUPPORTING_CONTEXT}}`
2. Dispatch via disk-mediated dispatch
3. Write findings to `scratch/<run-id>/<lens-name-kebab>-findings.md` (e.g., `technical-soundness-findings.md`)

**Key differences from code path:**
- Full artifact content to each lens (no Tier 1/Tier 2 tiering — non-code artifacts are small)
- All single-agent (no dual-agent Consistency pattern)
- No partition records (all lenses see the full artifact)
- Findings use `section` instead of `file` + `line_range`, and `concern` instead of lens-specific code fields

After all 4 lenses complete, proceed to Phase 2.5 (non-code blind-spots).

### Code Dispatch (artifact_type: code)

Dispatch: `Task tool (general-purpose, model: opus)` per lens, in parallel (matching inquisitor pattern). Fallback if parallel dispatch fails: dispatch sequentially via `Task tool (general-purpose, model: opus)`, with a one-time note to user: "Parallel dispatch unavailable -- running analysis lenses sequentially."

**Write-on-complete:** As each agent completes, immediately write its findings to `scratch/<run-id>/<lens>-findings.md`. Do not wait for Phase 3. For the Consistency lens, use distinct filenames: `consistency-a-findings.md` for Agent A's triage output, `consistency-b-findings.md` for Agent B's confirmed findings.

**Write partition records:** Before dispatching each lens, write the list of files sent as **full source** (not overflow summaries) to `scratch/<run-id>/<lens>-partition.md` (one file path per line). For Consistency, write only `consistency-b-partition.md` (Agent A receives the Tier 1 overview, not a Tier 2 source partition, so no partition record is needed for Agent A). These records are used by Phase 2.5 to build the coverage map and must survive compaction. Files sent as 2-3 line overflow summaries are NOT included in partition records -- those files count as never-examined for blind-spots purposes.

**Note on Consistency Agent A triage:** Agent A reads the Tier 1 overview and triages all manifest files, flagging some for Agent B. Files Agent A did not flag appear as "never-examined" in the coverage map. This is intentional -- overview-level triage (reading a 1-line role description) is categorically different from source-level examination. The blind-spots agent examining those files for security, performance, and concurrency issues is valuable regardless of Consistency triage.

### Context Management

**Tier 1 -- Overview:** The orchestrator builds a condensed summary of the subsystem: file manifest with role descriptions, key public interfaces/contracts, dependency graph. **Target: 500 lines. Flexible up to 800 lines for subsystems with complex API surfaces.** If the subsystem exceeds what can be summarized in 800 lines, chunk the subsystem (see Chunking below).

**Tier 2 -- Deep dive:** The orchestrator partitions source files across agents by relevance to their lens. **Hard cap: 1500 lines of total prompt content per agent** (Tier 1 overview + Tier 2 source + prompt template). If a lens requires more files than fit, the orchestrator generates brief summaries of overflow files (2-3 lines per file: path, responsibility, key interfaces) and includes those instead of full source. If an agent's findings reference a summarized file, the orchestrator may dispatch a **follow-up agent** for that lens with the flagged files at full source.

### Chunking (Large Subsystems)

If the subsystem is too large to summarize within the 800-line Tier 1 cap:

- Split by dependency subgraph -- files that call each other stay together. Prefer natural boundaries (directories, modules, namespaces).
- **Soft cap: 4 chunks maximum.** If more than 4 chunks would be needed, advise the user to narrow the subsystem scope instead.
- Present the chunking plan at the Phase 1 user gate: "This subsystem is large. I'll audit it in N chunks (~6N+1 agents: 5 analysis + 1 blind-spots per chunk, plus 1 cross-chunk blind-spots). Chunk descriptions: [list]. Approve?"
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

## Phase 2.5: Blind Spots

### Non-Code Blind-Spots (artifact_type: design | plan | concept)

Dispatch: `Task tool (general-purpose, model: opus)` using `audit-noncode-blindspots-prompt.md`. Runs AFTER all Phase 2 non-code lenses have reported, BEFORE Phase 3 synthesis.

**No coverage map needed** — all lenses see the full artifact. Instead, the orchestrator builds a **lens summary** with this format:

```
## Lens Summary
- **[Lens Name]** — [Core Question]. Findings: N (Fatal: N, Significant: N, Minor: N). Focus areas: [brief list].
[repeat for each lens]
```

The blind-spots agent receives the full artifact content + lens summary and hunts for document-level gaps (see Non-Code Blind-Spots Categories above). Write findings to `scratch/<run-id>/noncode-blindspots-findings.md`.

**No follow-up dispatches** for non-code (the artifact is fully visible to the blind-spots agent — there are no "never-examined files").

### Code Blind-Spots (artifact_type: code)

Dispatch: `Task tool (general-purpose, model: opus)` using `audit-blindspots-prompt.md`. Runs AFTER all Phase 2 lenses have reported (including Consistency Agent B), BEFORE Phase 3 synthesis.

**Purpose:** The four lenses share structural blind spots -- issues that fall between lenses, emerge from combinations of findings, or belong to categories no single lens covers (security, performance, concurrency, silent failures). A fresh agent hunts specifically in those gaps.

**Write-on-complete:** Write findings to `scratch/<run-id>/blindspots-findings.md`.

### Coverage Map (not raw findings)

The blind-spots agent does NOT receive raw findings from the other lenses. Instead, the orchestrator builds a **coverage map** -- a condensed summary of where the other lenses looked, without the evidence details that cause anchoring. This preserves independent judgment while directing attention to uncovered areas.

**Coverage map format** (orchestrator generates this from the lens findings files and Tier 2 partition records):

```
## Coverage Map

### Files Examined by Lens (included in Tier 2 source)
- path/to/file.ext: Correctness (2 findings), Architecture (1 finding)
- path/to/other.ext: Robustness (1 finding), Correctness (0 findings)
- path/to/examined-clean.ext: Architecture (0 findings)

### Files Never Examined (in manifest but not in any Tier 2 source)
- path/to/genuinely-unseen.ext
- path/to/another-unseen.ext
```

**Target: 30-50 lines.** No finding summaries, no concern category descriptions (the agent already knows the four lenses' domains from its prompt). Just the file-to-lens mapping and the examined/never-examined distinction. This maximizes source code budget.

### Coverage Map Construction (Orchestrator)

To build the coverage map:
1. Read all partition records from disk: `correctness-partition.md`, `robustness-partition.md`, `consistency-b-partition.md`, `architecture-partition.md`. These list the files each lens received as full source (written during Phase 2). Union of all partition files = the **examined set**.
2. Read the Phase 1 manifest. Any manifest file NOT in the examined set = **never examined**.
3. Read all findings files: correctness, robustness, consistency-b, architecture. Do NOT include consistency-a (triage only). Extract finding counts per lens per file.
4. Overlay finding counts onto the examined set. Files in the examined set with no findings get "(0 findings)" for the lenses that examined them.
5. List examined files with lens names and finding counts. List never-examined files separately.
6. If the map exceeds 50 lines, abbreviate by grouping never-examined files by directory instead of listing individually.

### Input

The blind-spots agent receives:
- Tier 1 overview (same as other lenses)
- Coverage map (see above, ~30-50 lines)
- Targeted source files. Subject to the same 1500-line hard cap as other lenses.

### Source File Selection

**Priority order (strict -- not a judgment call):**
1. **At least 60% of source file budget** goes to **never-examined** files (not in any lens's Tier 2 source partition). These are the genuine blind spots -- code no lens read.
2. **Remaining budget** goes to files flagged by multiple lenses (interaction points where cross-cutting concerns are likeliest).

If there are no never-examined files (every manifest file was in at least one Tier 2 partition), allocate the full budget to multi-lens interaction points.

**Narration:** Status update when dispatching ("Phase 2.5: All 4 lenses complete. Dispatching blind-spots agent to hunt cross-cutting concerns.") and when it completes ("Phase 2.5 complete. Blind-spots agent found N additional findings. Moving to Phase 3 synthesis.").

### Follow-Up Dispatches

If the blind-spots agent lists files in "Files Needing Deeper Inspection" AND the audit is under the ~20 agent budget, dispatch one follow-up blind-spots agent with those files at full source. The follow-up receives the same coverage map but new source files. Write follow-up findings to `scratch/<run-id>/blindspots-followup-findings.md`. Phase 3 synthesis reads this file if it exists.

If the audit is at or near the agent budget, skip the follow-up and include the "Files Needing Deeper Inspection" list in the Phase 3 report as "Areas not fully covered."

### Chunked Audits

For chunked subsystems, the blind-spots agent runs **once per chunk** (not once for all chunks), receiving that chunk's coverage map + cross-chunk interface section. This keeps each dispatch within the 1500-line hard cap.

**Cross-chunk blind spots:** After all per-chunk blind-spots agents complete, dispatch one additional **cross-chunk blind-spots agent**. This agent receives a purpose-built cross-chunk overview (NOT all individual coverage maps stacked):
- A single merged view (~50-80 lines) listing only boundary files (files that appear in multiple chunks' interface sections) with their lens coverage across chunks
- Source files from those cross-chunk boundaries
- Subject to the same 1500-line hard cap

Per-chunk interior coverage is irrelevant to cross-chunk analysis -- keep it out. This agent targets issues that span chunk boundaries (e.g., one chunk deserializes input, another trusts it without validation). Write findings to `scratch/<run-id>/blindspots-crosschunk-findings.md`. Skip this dispatch if the subsystem is single-chunk.

**Cross-chunk boundary overview construction (orchestrator):**
1. Identify boundary files: files that appear in 2+ chunks' Tier 1 "cross-chunk interface" sections.
2. For each boundary file, collect lens coverage from all chunks' partition records + finding counts from all chunks' findings files.
3. Format as: `path/file.ext: Chunk A [Correctness (1), Robustness (0)], Chunk B [Architecture (2)]`
4. List only boundary files. Interior files are irrelevant to cross-chunk analysis.
5. If >80 lines, group by chunk boundary pair (e.g., "Chunk A <-> Chunk B boundary files").

After all blind-spots agents complete, findings from all chunks (including cross-chunk) flow into Phase 3 synthesis.

### Compounding Risk Analysis

The blind-spots agent does NOT analyze compounding risks from existing findings. That responsibility belongs to Phase 3 synthesis, which already reads all findings and deduplicates. Adding a synthesis step for compounding is natural and costs zero additional agents. See Phase 3 below.

## Phase 3: Synthesis

### Reading Findings

**Code audits:** Read `correctness-findings.md`, `robustness-findings.md`, `consistency-b-findings.md`, `architecture-findings.md`, `blindspots-findings.md`, and if they exist: `blindspots-followup-findings.md`, `blindspots-crosschunk-findings.md`. Do NOT read `consistency-a-findings.md` (triage data, not confirmed findings).

**Non-code audits:** Read `<lens-name-kebab>-findings.md` for each of the 4 type-specific lenses (e.g., `technical-soundness-findings.md`, `integration-impact-findings.md`, `edge-cases-findings.md`, `scope-clarity-findings.md` for design), plus `noncode-blindspots-findings.md`.

1. **Deduplicate:** When two findings reference the same location and describe the same underlying concern, merge into one finding noting both lenses. For code audits, match on overlapping `file` + `line_range`. For non-code audits, match on identical `section` headings. Use common fields (severity, evidence, description) for similarity comparison. Preserve lens-specific fields from both. **Tie-breaking rule:** When in doubt, keep both findings as separate items but note they may be related. Err on the side of presenting more findings rather than silently merging.
2. **Compounding risks:** After dedup, scan pairs of findings from different lenses that touch the same file or related files. Flag as compounding ONLY when you can articulate the specific mechanism by which the two findings combine into a worse problem (e.g., "this robustness gap means malformed input reaches this code path, where this correctness edge case causes data corruption"). File proximity alone is not compounding -- the findings must be causally related. Add a "Compounding" tag with the mechanism description to the grouped output.
3. **Severity-rank:** Fatal first, then Significant, then Minor.
4. **Group by theme** (e.g., "Error Handling," "State Management," "API Contracts").
5. **Write report** to `scratch/<run-id>/report.md`.

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

4. **Record to cartographer (code audits only):** After completion, dispatch cartographer recorder (Mode 1) with the Phase 1 manifest only. The manifest was deliberately scoped during exploration and is reliable structural data. Do NOT feed incidental observations from Phase 2 bug-hunting agents to cartographer -- those are unverified structural inferences. **Skip for non-code audits** — no subsystem manifest to record.

5. **Cleanup:** Delete the `scratch/<run-id>/` directory only after ALL Phase 4 actions are complete (issue filing, cartographer recording). Do not clean up prematurely -- the report on disk is needed for compaction recovery during Phase 4.

## Prompt Templates

### Code Audit Templates

- `audit-scoping-prompt.md` -- Phase 1 subsystem scoping dispatch (`Agent tool, subagent_type: Explore, model: sonnet`)

Analysis lens templates (all use `Task tool, general-purpose, model: opus`):
- `audit-correctness-prompt.md` -- Correctness lens dispatch
- `audit-robustness-prompt.md` -- Robustness lens dispatch
- `audit-consistency-prompt.md` -- Consistency lens dispatch (documents two-agent protocol)
- `audit-architecture-prompt.md` -- Architecture lens dispatch

Blind-spots template (`Task tool, general-purpose, model: opus`):
- `audit-blindspots-prompt.md` -- Phase 2.5 gap-hunting dispatch (receives coverage map)

### Non-Code Audit Templates

- `audit-noncode-lens-prompt.md` -- Parameterized lens dispatch for all non-code artifact types. Orchestrator fills `{{LENS_NAME}}`, `{{LENS_QUESTION}}`, `{{LENS_FOCUS_AREAS}}`, `{{LENS_EXCLUSIONS}}`, `{{ARTIFACT_TYPE}}`, `{{ARTIFACT_CONTENT}}`, `{{SUPPORTING_CONTEXT}}`.
- `audit-noncode-blindspots-prompt.md` -- Non-code blind-spots dispatch (receives lens summary, not coverage map)

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
- Exceed 5 findings per lens without strong justification (focus on highest-impact issues). Exception: blind-spots lens cap is 8 findings due to its multi-category scope.

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

| Skill | How Used | When |
|-------|----------|------|
| `crucible:recon` | Subsystem-manifest module | Phase 1 Code Path (subsystem scoping via structured manifest). Fallback: dispatch scoping agent via `audit-scoping-prompt.md`. |
| `crucible:cartographer` | Consult mode | Phase 1 (subsystem scoping and conventions) |
| `crucible:cartographer` | Record mode | Phase 4 (Phase 1 manifest only) |

- **Dispatches:** Code audit templates (correctness, robustness, consistency [2 agents], architecture, blind-spots) and non-code templates (noncode-lens [parameterized], noncode-blindspots). Scoping via recon (primary) or `audit-scoping-prompt.md` (fallback).
- **Pairs with:** `crucible:forge` -- audit findings could inform retrospective if they reveal systemic patterns
- **Called by:** Standalone only (user invokes directly). Not part of any pipeline.
- **Does NOT use:** `crucible:quality-gate` (audit is not a fix loop), `crucible:red-team` (designed for single artifacts), `crucible:assay` (audit is find-and-report, not decision evaluation)
