---
name: recon
description: "Standalone codebase investigation. Produces a layered Investigation Brief with core findings (structure, patterns, scope, prior art) plus optional depth modules. Dispatches parallel scouts, synthesizes findings, and feeds cartographer. Use before any task requiring codebase understanding."
---

# Recon

## Overview

Structured, parallel codebase investigation with a layered output model. Produces a core Investigation Brief that all consumers share, plus optional depth modules for consumer-specific needs.

**Skill type:** Rigid — follow exactly, no shortcuts.

**Models:**
- Core scouts: Sonnet (via Explore agents)
- Judgment depth agents (impact-analysis, friction-scan, diagnostic-context): Opus
- Mechanical depth agents (consumer-registry, subsystem-manifest, execution-readiness): Sonnet
- Orchestrator: runs on whatever model the session uses

**Announce at start:** "Running recon [with task: X / full repo scan] [scope: Y / full repo]."

## Invocation API

```
/recon
  task: "Add REST endpoint for user profiles"       # optional — omit for full repo scan
  context: { decisions: [...], constraints: [...] }   # optional — structured prior decisions
  session_id: "design-20260404-abc123"                # optional — enables cross-invocation caching
  modules: ["impact-analysis", "execution-readiness"] # optional — depth modules to produce
  scope: "src/api/"                                   # optional — directory constraint
```

### Parameters

**`task`** (optional)
Free-text description of the task being investigated. Scouts focus exploration on task-relevant areas. Omit for a full repository scan.

**`context`** (optional)
Structured prior decisions from a parent skill (e.g., accumulated design choices from `/design`'s dimension loop). Passed to scouts alongside the task. Scouts consider these decisions during investigation — avoiding areas already decided, focusing on interfaces affected by prior choices.

- **Input budget:** 4,000 tokens default. Parent skills should compact decisions before passing — each decision as a key-value pair with one-sentence rationale plus affected interfaces.
- **Exceeding budget:** Orchestrator warns but does not reject. Caller proceeds at the cost of reduced scout context budget.
- **Total scout input:** task + context + cartographer should stay under 8,000 tokens for effective exploration.

Distinct from `task:` which describes *what* to investigate; `context:` describes *what's already been decided*.

**Recognized context keys:**
- `decisions` — list of prior design/implementation decisions
- `constraints` — list of constraints affecting investigation
- `target` — specific symbol/module for `consumer-registry` depth module (used by `/migrate`). Falls back to the `task:` string if absent.

**`session_id`** (optional)
Enables cross-invocation caching within a session. When provided, the Structure Scout report is cached and reused on subsequent invocations with the same session_id. Pattern Scout always runs fresh (its output varies with cascading context). Parent skills generate the session_id (e.g., `/design` uses its run timestamp). Without a session_id, no caching occurs.

**`modules`** (optional)
List of depth modules to produce after core synthesis. Valid values:

| Module | Agent | Model | Primary Consumer |
|---|---|---|---|
| `impact-analysis` | Impact Analyst | Opus | `/design`, `/build` |
| `consumer-registry` | Consumer Mapper | Sonnet | `/migrate` |
| `friction-scan` | Friction Scanner | Opus | `/prospector` |
| `subsystem-manifest` | Manifest Builder | Sonnet | `/audit` |
| `diagnostic-context` | Diagnostic Gatherer | Opus | `/debugging` |
| `execution-readiness` | Readiness Checker | Sonnet | `/build` |

Most invocations request 0-1 depth modules. Omit for core-only output (cheapest).

**`scope`** (optional)
Directory constraint. When provided, overrides scout scope suggestions entirely — scouts constrain exploration to the given path(s). Cheaper, faster.

### Behavior Matrix

| Configuration | Behavior |
|---|---|
| With task | Scouts focus on task-relevant areas |
| With context | Prior decisions passed to scouts alongside task |
| Without task | Full repo recon for audit/project-init cold starts |
| With scope | Explicit scope overrides scout suggestions |
| With modules | Depth agents dispatched after core synthesis |
| No modules | Core layer only — cheapest possible recon |
| With session_id | Structure Scout cached, Pattern Scout always fresh |

### Cost Profile

| Configuration | Agents | Models | Relative Cost |
|---|---|---|---|
| Core only | 2 | 2x Sonnet | Low |
| Core + 1 mechanical module | 3 | 3x Sonnet | Low |
| Core + 1 judgment module | 3 | 2x Sonnet + 1x Opus | Medium |
| Core + 2 modules (mixed) | 4 | 2-3x Sonnet + 1-2x Opus | Medium-High |
| Full repo, no task | 2 | 2x Sonnet | Low (but slower) |

## Communication Requirements (Non-Negotiable)

Recon narrates its progress at these points — **every one is mandatory**:

1. **Before dispatching scouts** — "Dispatching Structure Scout and Pattern Scout [with cartographer context / cold start]."
2. **After scout completion, before synthesis** — "Scouts complete. Synthesizing core brief. [N conflicts detected.]"
3. **After depth module completion, before returning** — "Depth module [name] complete. Returning Investigation Brief."
4. **On overflow re-run** — "Scout [name] exceeded token budget. Re-running with narrowed scope: [new scope]."
5. **On cartographer conflict** — "Cartographer conflict detected: [brief description]. Flagged as [auto-updated / unresolved]."
6. **On depth module failure** — "Depth module [name] failed: [timeout / error]. Core brief delivered without this module."

### Direct vs. Sub-Skill Invocation

**When invoked directly** (user calls `/recon`): narration is output to the user in real time.

**When invoked as sub-skill** (called by `/design`, `/build`, etc.): narration lines are included at the top of the returned Investigation Brief under a `## Recon Progress` section. The parent skill can relay these to the user or discard them.

### Pipeline Status

At each narration point, write `pipeline-status.md` to the scratch directory with:

```markdown
# Pipeline Status
**Phase:** dispatching | synthesizing | depth-modules | complete
**Progress:** [free-text description]
**Timestamp:** [ISO-8601]

## Scouts
- Structure Scout: [pending | running | complete | failed | cached]
- Pattern Scout: [pending | running | complete | failed]

## Depth Modules
<!-- Only present if modules requested -->
- [module-name]: [pending | running | complete | failed]

## Cartographer
- Consult: [consulted | cold start | N/A]
- Record: [pending | dispatched | complete | skipped]
```

## Phase 1: Cartographer Consult

Before dispatching scouts, check for existing cartographer data.

1. Read `map.md` from cartographer storage directory (direct file read via Read tool — no agent dispatch)
   - Storage path: `~/.claude/projects/<project-hash>/memory/cartographer/map.md`
2. **If map exists:** Extract relevant module context for scouts. Pass module files, conventions, and landmines as the `[CARTOGRAPHER]` placeholder content.
3. **If cold start (no map):** Set `[CARTOGRAPHER]` to "No cartographer data — explore from scratch." Proceed normally.
4. **Provenance tracking:** Instruct scouts to annotate findings sourced from cartographer with `(cartographer)` in their output. Freshly discovered findings are unmarked. This lets consumers distinguish verified-from-memory vs. discovered-now.

## Phase 2: Scout Dispatch

### Session Cache Check

If `session_id` is provided:
1. Check for cached Structure Scout report at: `~/.claude/projects/<project-hash>/memory/recon/sessions/<session_id>/structure-scout.md`
2. **If cached report exists:** Skip Structure Scout dispatch. Use cached report. Mark Structure Scout as `cached` in pipeline status.
3. **If no cache:** Dispatch normally. After completion, write report to cache path with a metadata line prepended: `<!-- cached-commit: [HEAD SHA] -->`. This line is used for invalidation checks.

Pattern Scout always runs fresh — its output varies with cascading context.

### Dispatch

Dispatch both scouts in parallel (or just Pattern Scout if Structure Scout is cached):

**Structure Scout:**
```
Agent tool (subagent_type: Explore, model: sonnet):
  description: "Structure Scout: map project layout for [task summary]"
```
- Template: `./structure-scout-prompt.md`
- Fill placeholders: `[TASK]`, `[SCOPE]`, `[CONTEXT]`, `[CARTOGRAPHER]`
- **Default values for absent parameters:**
  - `[TASK]` → "Full repository scan — no specific task"
  - `[SCOPE]` → "No scope constraint — explore entire repository"
  - `[CONTEXT]` → "No prior decisions"

**Pattern Scout:**
```
Agent tool (subagent_type: Explore, model: sonnet):
  description: "Pattern Scout: discover conventions and prior art for [task summary]"
```
- Template: `./pattern-scout-prompt.md`
- Fill placeholders: `[TASK]`, `[SCOPE]`, `[CONTEXT]`, `[CARTOGRAPHER]`

On completion, write raw scout reports to scratch directory:
- `<scratch>/structure-scout-report.md`
- `<scratch>/pattern-scout-report.md`

Narrate: "Scouts complete. Synthesizing core brief. [N conflicts detected.]"

## Phase 3: Core Synthesis (Orchestrator-Local)

**No synthesis subagent.** The orchestrator reads both scout reports and assembles the Investigation Brief directly.

### Scope Merging

**If caller provided explicit `scope:` parameter:** Use it directly. Skip scout suggestions entirely.

**Otherwise, merge scout suggestions:**

1. **In Scope:** Union of both scouts' `suggested_scope.in_scope` paths.
   - Paths suggested by **both** scouts: marked `high confidence`
   - Paths suggested by **only one** scout: marked `medium confidence` with attribution (e.g., "suggested by Structure Scout")

2. **Contested paths:** When one scout includes a path and the other excludes it:
   - Place under `### Contested` in Scope Boundaries (not excluded)
   - Include reasoning from each scout
   - **Consumer guidance:** Contested paths should be treated as in-scope unless the consumer has a specific reason to exclude them. The annotation signals lower confidence, not a decision for the consumer to make.

3. **Out of Scope:** Uncontested exclusions — both scouts agree to exclude, or only one scout mentions exclusion and the other is silent.

### Contradiction Detection

Cross-check the two scout reports for conflicting evidence. Examples:
- Structure Scout maps a directory as inactive but Pattern Scout finds live test references to it
- Scouts disagree on module boundaries or build system identification
- One scout identifies a file as an entry point, the other doesn't mention it despite covering the same area

Surface contradictions in `## Conflicts` section with:
- The tension described
- Evidence from Structure Scout (claim + evidence)
- Evidence from Pattern Scout (claim + evidence)
- Confidence assessment (which is stronger and why, or "unresolved")

Conflicts are high-value cartographer feed-back material.

### Cartographer Conflict Resolution

When scouts report `cartographer-conflict` findings, apply this adjudication table:

| Condition | Both scouts agree? | Evidence type | Action |
|---|---|---|---|
| Path no longer exists + both agree | Yes | Negative (absence) | **Auto-update** — path evidence is verifiable |
| Positive assertion + both agree | Yes | Positive (file exists, pattern found) | **Auto-update** — new finding is grounded |
| Both agree, no supporting evidence | Yes | Neither | **Unresolved** — agreement alone insufficient (correlated input priors) |
| Deletion from cartographer | Yes or No | Any | **Always unresolved** — requires user confirmation |
| Single scout only | No | Any | **Unresolved** — prevents single-scout hallucination |

**Why agreement alone is insufficient:** Both scouts receive the same cartographer context and task description as input. Their exploration is correlated, not independent. Two correlated errors do not constitute independent verification. Auto-update requires agreement PLUS verifiable evidence.

For auto-update actions: queue the update for Phase 5 (Cartographer Feedback).
For unresolved actions: surface in the `## Conflicts` section of the brief.

### Open Questions Aggregation

After contradiction detection, aggregate open questions from both scout reports:

1. Collect all items from each scout's `### Open Questions` section
2. Deduplicate — merge questions about the same unknown from both scouts
3. Tag each question with:
   - **Relevant to:** which consumer skills would need this answer (e.g., `/design`, `/build`)
   - **Resolvable by:** what specific investigation or human input would answer it (e.g., "check with team lead", "run integration tests", "read module X in detail")
4. If depth modules also report open questions, merge those in during Phase 4

Open questions that get resolved in subsequent pipeline phases are high-value cartographer recordings — feed them back in Phase 5.

### Assemble the Investigation Brief

Build the Investigation Brief markdown with all core sections:

```markdown
# Investigation Brief
**Brief version:** 1
**Task:** [task description or "Full repository scan"]
**Scope:** [constrained path or "Full repo"]
**Depth modules:** [list or "Core only"]
**Cartographer state:** [consulted / cold start / N/A]
**Commit:** [HEAD SHA at investigation time]

## Project Structure
[From Structure Scout report — module layout, entry points, build system, key directories]

## Existing Patterns
[From Pattern Scout report — conventions, naming, test patterns, abstractions]

## Scope Boundaries
### In Scope
- [path/area] — [why] — [confidence: high/medium]
### Out of Scope
- [path/area] — [why excluded]
### Contested
<!-- Only present if scope conflict between scouts -->
- [path/area] — [scout reasoning from each side]

## Prior Art
[From Pattern Scout report]
- **[Description]** — [file paths] — [relevance to current task]

## Conflicts
<!-- Only present if contradictions detected between scouts -->
- **[Tension]** — Structure Scout: [claim + evidence]. Pattern Scout: [claim + evidence]. Confidence: [assessment].

## Open Questions
<!-- Aggregated from scouts and depth modules — what recon couldn't determine -->
- **[Question]** — [Why it matters] — Relevant to: [consumer list] — Resolvable by: [specific investigation or human input]
```

## Overflow Handling

### Scout Report Overflow

**Detection:** Use line count as a proxy for token budget. If a scout report exceeds 80 lines (scoped) or 160 lines (full-repo), apply overflow handling. Depth modules: 120 lines (80 for readiness-checker). Lines are mechanically countable; token counts are not.

If a scout report exceeds its budget:

1. **Task-aware truncation:** Sections relevant to the current task retain full content (including reasoning prose needed for contradiction detection). Out-of-scope sections are reduced to headings + first-level bullets.
2. **If still over budget:** Request a scoped re-run from the scout with a narrower scope constraint.
   - Narrate: "Scout [name] exceeded token budget. Re-running with narrowed scope: [new scope]."
   - The re-run replaces the original report (not appended).
3. **Flag truncated sections** with `(truncated)` so consumers can request full detail.

### Depth Module Overflow

Same policy applies to depth module outputs (3,000 token budget, 2,000 for readiness-checker):
1. Task-aware truncation first
2. Scoped re-run if still over
3. Flag truncated sections

## Phase 4: Depth Module Dispatch

Only if `modules:` parameter is non-empty. Dispatch **after** core synthesis completes — depth agents receive core findings as input context.

### Dispatch

When multiple modules are requested, dispatch them in parallel. Each depth agent receives the assembled core Investigation Brief via the `[CORE_BRIEF]` placeholder.

| Module | Agent | Dispatch | Template |
|---|---|---|---|
| `impact-analysis` | Impact Analyst | `Agent tool (subagent_type: Explore, model: opus)` | `./impact-analyst-prompt.md` |
| `consumer-registry` | Consumer Mapper | `Agent tool (subagent_type: Explore, model: sonnet)` | `./consumer-mapper-prompt.md` |
| `friction-scan` | Friction Scanner | `Agent tool (subagent_type: Explore, model: opus)` | `./friction-scanner-prompt.md` |
| `subsystem-manifest` | Manifest Builder | `Agent tool (subagent_type: Explore, model: sonnet)` | `./manifest-builder-prompt.md` |
| `diagnostic-context` | Diagnostic Gatherer | `Agent tool (subagent_type: Explore, model: opus)` | `./diagnostic-gatherer-prompt.md` |
| `execution-readiness` | Readiness Checker | `Agent tool (subagent_type: Explore, model: sonnet)` | `./readiness-checker-prompt.md` |

### Placeholder Filling

- `[CORE_BRIEF]` — the assembled core Investigation Brief (all core sections)
- `[TASK]` — the original task description
- `[SCOPE]` — scope constraint (if provided)
- `[TARGET]` — for `consumer-registry` only: the migration target symbol/module. Extract from `context.target` if provided; fall back to the full `task:` string if absent. **Validation:** If `consumer-registry` is requested and neither `context.target` nor `task` is provided, reject with error: "consumer-registry requires a target — provide context.target or task."

### Output Handling

- Write each depth module output to scratch as individual files (e.g., `<scratch>/impact-analysis.md`)
- Append completed depth module sections to the Investigation Brief after the core sections, separated by `---`
- Narrate after each: "Depth module [name] complete. Returning Investigation Brief."

### Depth Module Failure

On failure (timeout, error, or agent did not return useful output):
- Deliver the core brief — it is always complete before depth modules start
- Flag the failed module in the brief:
  ```
  ## [Module Name]
  *Agent did not complete — request this module again or investigate manually.*
  ```
- Narrate: "Depth module [name] failed: [timeout / error]. Core brief delivered without this module."

## Phase 5: Cartographer Feedback

After the Investigation Brief is assembled (core + any depth modules):

1. **Check for new information:** Compare scout findings against cartographer context provided in Phase 1.
2. **If scouts discovered new information not in the map:** Dispatch cartographer recorder:
   ```
   Task tool (general-purpose, model: sonnet):
     description: "Cartographer recording for recon findings"
   ```
   Use the existing `crucible:cartographer` skill's `recorder-prompt.md` template (at `skills/cartographer-skill/recorder-prompt.md`). Note: this is `Task tool`, not `Agent tool (Explore)` — the recorder needs write access to the memory directory. Pass scout findings as input following the recorder's expected format.
   - Include auto-update resolutions from cartographer conflict adjudication
   - New module files, conventions, or landmines flow into cartographer storage
   - **Narrate auto-updates:** "Auto-updating cartographer: [description]. Review with `/cartographer consult`." Auto-updates must be visible — silent persistent changes affect all future sessions.
3. **If nothing new:** Skip recorder dispatch.

**Key constraint:** `/recon` is read-only on the codebase. Cartographer writes go to the memory directory, not the repo.

## Output and Return

Return the Investigation Brief as the agent output (inline return to parent skill).

The brief follows the exact template from the design, including the metadata block:

```markdown
# Investigation Brief
**Brief version:** 1
**Task:** [task description or "Full repository scan"]
**Scope:** [constrained path or "Full repo"]
**Depth modules:** [list or "Core only"]
**Cartographer state:** [consulted / cold start / N/A]
**Commit:** [HEAD SHA at investigation time]

## Project Structure
...

## Existing Patterns
...

## Scope Boundaries
### In Scope
...
### Out of Scope
...
### Contested
...

## Prior Art
...

## Conflicts
...

## Open Questions
...

---
<!-- Depth modules below, only present if requested -->

## Impact Analysis
...

## Consumer Registry
...

## Friction Scan
...

## Subsystem Manifest
...

## Diagnostic Context
...

## Execution Readiness
**Test command:** ...
**Lint command:** ...
**CI checks:** ...
**Manual verification:** ...
```

**When invoked as sub-skill:** Include `## Recon Progress` section at the top with all narration lines from the run.

## Scratch Directory and Context Management

### Scratch Path

`~/.claude/projects/<project-hash>/memory/recon/scratch/<run-id>/`

- `<run-id>` is a timestamp (e.g., `20260404-143022`)
- Access restricted to Write/Read/Glob tools — no Bash commands against `.claude/` paths

### Persisted Artifacts

| File | Purpose |
|---|---|
| `structure-scout-report.md` | Raw Structure Scout output |
| `pattern-scout-report.md` | Raw Pattern Scout output |
| `impact-analysis.md` | Depth module output (if requested) |
| `consumer-registry.md` | Depth module output (if requested) |
| `friction-scan.md` | Depth module output (if requested) |
| `subsystem-manifest.md` | Depth module output (if requested) |
| `diagnostic-context.md` | Depth module output (if requested) |
| `execution-readiness.md` | Depth module output (if requested) |
| `investigation-brief.md` | Final assembled brief |
| `pipeline-status.md` | Current pipeline status |

### Session Caching

Structure Scout reports are cached for cross-invocation reuse within a session:
- Cache path: `~/.claude/projects/<project-hash>/memory/recon/sessions/<session_id>/structure-scout.md`
- When `session_id` is provided, check this path before dispatching Structure Scout
- **Invalidation:** If the cached report's commit SHA (from the `<!-- cached-commit: ... -->` metadata line) differs from current HEAD, discard the cache and re-dispatch. Narrate: "Structure Scout cache invalidated (codebase changed: [old SHA] → [new SHA]). Re-running fresh." This handles cases where the codebase changes mid-session and ensures the parent skill knows the structural basis changed.
- Session cache files follow the same 24-hour stale cleanup as run directories

### Stale Directory Cleanup

At orchestrator startup, prune scratch directories older than 24 hours. Check directory timestamps via Glob and remove stale entries.

**Do not clean scratch until the Investigation Brief is returned to the caller.** Compaction recovery depends on scratch contents being available until the full brief is delivered.

## Compaction Recovery

If the orchestrator hits a compaction boundary mid-run:

1. **Read scratch directory listing** — determine which files exist
2. **Determine phase:**
   - No scout reports → still in Phase 1 or 2, restart from Phase 1
   - Scout reports exist, no `investigation-brief.md` → Phase 3 (synthesis), re-read scout reports
   - Brief exists, no depth module files for requested modules → Phase 4, dispatch remaining modules
   - All expected files present → Phase 5 or complete
3. **Re-read relevant files** from scratch to reconstruct state
4. **Read `pipeline-status.md`** for last known phase and progress
5. **Output status** to user before continuing
6. **Continue** from the determined phase

File presence is the completion signal — no health state machine needed.

## Error Handling

| Scenario | Behavior |
|---|---|
| Scout failure/timeout | Produce partial brief with available sections. Flag missing: `*Scout did not complete — section unavailable.*` |
| Depth module failure | Core brief still delivered. Failed module flagged. |
| No task + no scope + no modules | Valid invocation. Produces core-only full-repo brief. |
| Cartographer unavailable | Scouts explore from scratch (cold-start path). No error. |
| Both scouts fail | Return empty brief with all sections flagged as unavailable. Escalate to caller. |
| Context parameter exceeds budget | Warn but do not reject. Proceed at reduced scout context budget. |

## Brief Schema Stability

The Investigation Brief is consumed by 6+ skills. Section headers are the contract surface — consumers parse by header to extract relevant sections.

**Stable (changing requires updating all consumer templates):**
- Brief metadata fields: `Brief version`, `Task`, `Scope`, `Depth modules`, `Cartographer state`, `Commit`
- Core section headers: `## Project Structure`, `## Existing Patterns`, `## Scope Boundaries`, `## Prior Art`, `## Conflicts`

**Semi-stable (additive, consumers opt-in):**
- `## Open Questions` — present when scouts report unknowns. Consumers that need it parse for it; consumers that don't can ignore it. Not yet validated by consumer integration — promoted to stable once 2+ consumers confirm they consume it.

**Semi-stable (consumers that request specific modules depend on these):**
- Depth module section headers: `## Impact Analysis`, `## Consumer Registry`, `## Friction Scan`, `## Subsystem Manifest`, `## Diagnostic Context`, `## Execution Readiness`
- Execution Readiness structured subfields: `Test command`, `Lint command`, `CI checks`, `Manual verification` — parsed by `/build`, must not be renamed without updating consumers

**Unstable (internal content, not parsed by header):**
- Content within sections — formatting, subheadings, bullet structure may evolve

**Process:** Any change to a stable or semi-stable header is a breaking change. The PR must update all consumer skill templates that reference the changed header. Adding new depth modules is non-breaking.

## Design Principles

- **Read-only** — `/recon` never modifies the codebase
- **Cartographer-aware** — consults first, feeds back after
- **Layered** — core is cheap and universal; depth is on-demand and consumer-specific
- **Evidence-grounded** — produces constraints and evidence, not opinions
- **Prior art is first-class** — finding existing patterns to follow is the single biggest quality lever
- **Assumptions are explicit** — annotated inline on relevant findings, not in a standalone block
- **Token-efficient** — structured markdown, no JSON boilerplate, Sonnet for mechanical work

## Guardrails / Red Flags

- Never modify the codebase
- Never dispatch depth agents before core synthesis completes
- Never skip narration between dispatches
- Never exceed context budgets without overflow handling
- Never auto-update cartographer without both-scout agreement + verifiable evidence
- Never return depth module output without the core brief

## Integration

**Dispatches:**
- `structure-scout-prompt.md` — Structure Scout (Sonnet, Explore)
- `pattern-scout-prompt.md` — Pattern Scout (Sonnet, Explore)
- `impact-analyst-prompt.md` — Impact Analyst (Opus)
- `consumer-mapper-prompt.md` — Consumer Mapper (Sonnet)
- `friction-scanner-prompt.md` — Friction Scanner (Opus)
- `manifest-builder-prompt.md` — Manifest Builder (Sonnet)
- `diagnostic-gatherer-prompt.md` — Diagnostic Gatherer (Opus)
- `readiness-checker-prompt.md` — Readiness Checker (Sonnet)

**Consults:** `crucible:cartographer` (consult mode — direct file read of `map.md`)

**Records to:** `crucible:cartographer` (recorder dispatch after investigation, using `skills/cartographer-skill/recorder-prompt.md`)

**Called by:** `/design`, `/build`, `/debugging`, `/migrate`, `/audit`, `/prospector` (supplementary), `/project-init`

**Pairs with:** `/assay` (sequential — recon produces evidence, assay evaluates options)
