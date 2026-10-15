---
name: recon
description: "Investigate unfamiliar code before a task, onboard to a whole repository and local neighbors, consult or maintain a persistent codebase map, or discover architectural friction and refactor candidates. Use for codebase investigation, first-time repository mapping, codebase maps, architecture friction, refactor discovery, project initialization, and “what should I refactor?” requests; search for cartographer and prospector tasks to route them to the matching recon mode."
---

# Recon

## Contents

- [Modes](#modes)
- [Overview](#overview)
- [Invocation API](#invocation-api)
- [Communication requirements](#communication-requirements-non-negotiable)
- [Investigation workflow](#investigation-workflow)
- [Output and return](#output-and-return)
- [Scratch directory](#scratch-directory-and-context-management)
- [Compaction recovery](#compaction-recovery)
- [Error handling](#error-handling)
- [Brief schema](#brief-schema-stability)
- [Verification ledger](#verification-ledger)
- [Guardrails](#design-principles-and-guardrails)
- [Integration](#integration)

## Modes

Select exactly one mode from user intent; default to task-scoped investigation:

- **Task investigation:** follow the core brief and optional depth-module workflow below.
- **Whole-repo onboarding:** select for first-time full-repository mapping; follow [`whole-repo-onboarding.md`](whole-repo-onboarding.md) for partitioned repo scans, optional sibling-repo topology, and structural bootstrap. It feeds the same persistent map described below.
- **Persistent map:** select for consulting or updating accumulated codebase knowledge; follow [`persistent-map.md`](persistent-map.md) for consult, load, record, and defect-signature workflows; use [`cartographer/recorder-prompt.md`](cartographer/recorder-prompt.md) for record format. Storage remains in the harness project memory directory. Whole-repo onboarding's structural tags and precedence rules remain authoritative.
- **Improvement discovery:** select for open-ended improvement discovery; follow [`improvement-discovery.md`](improvement-discovery.md) for friction analysis, genealogy, prioritization, and competing redesign proposals. Use `/design` to develop a selected redesign proposal; recon does not absorb design decisions or implementation.

These are modes of `/recon`, not separate skills. For specialized output instructions, read the selected mode guide and its prompt/reference files before dispatching. In whole-repo onboarding, announce the mode and follow its tiered workflow. In persistent-map work, perform the requested consult/load/record action. In improvement discovery, preserve its advisory/read-only boundary and route proposals to `/design`.

## Overview

<!-- CANONICAL: shared/dispatch-convention.md -->
All subagent dispatches use disk-mediated dispatch. See `shared/dispatch-convention.md` for the full protocol.

<!-- CANONICAL: shared/model-tier-policy.md -->
Dispatch profiles (`high`, `standard`, `fast`) are recommendations resolved per harness; missing mappings must not stop a live dispatch. See `shared/model-tier-policy.md` for resolution, fallback, and trust rules.

<!-- Trust framework: see [skills/getting-started/trust-hierarchy.md](../getting-started/trust-hierarchy.md). -->

Structured, parallel codebase investigation with a layered output model. Produces a core Investigation Brief that all consumers share, plus optional depth modules for consumer-specific needs.

**Skill type:** Rigid — follow exactly, no shortcuts.

**Models:**
- Core scouts: standard (via Explore agents)
- Judgment depth agents (impact-analysis, friction-scan, diagnostic-context): high
- Mechanical depth agents (consumer-registry, subsystem-manifest, execution-readiness): standard
- Claude Code tool calls map `standard` to `model: sonnet` and `high` to `model: opus`; other harnesses use supported mappings or omit unsupported model fields per `shared/model-tier-policy.md`.
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
| `impact-analysis` | Impact Analyst | high | `/design`, `/build` |
| `consumer-registry` | Consumer Mapper | standard | `/migrate` |
| `friction-scan` | Friction Scanner | high | `/recon` improvement-discovery mode |
| `subsystem-manifest` | Manifest Builder | standard | `/audit` |
| `diagnostic-context` | Diagnostic Gatherer | high | `/debugging` |
| `execution-readiness` | Readiness Checker | standard | `/build` |

Most invocations request 0-1 depth modules. Omit for core-only output (cheapest).

**Auto-inclusion:** Debugging-keyword tasks automatically add `diagnostic-context` (see Phase 4 Auto-Inclusion). Pass `modules: []` (explicit empty list) to suppress auto-inclusion — omitting `modules:` does not suppress it.

**`scope`** (optional)
Directory constraint. When provided, overrides scout scope suggestions entirely — scouts constrain exploration to the given path(s). Cheaper, faster.

### Behavior Matrix

| Configuration | Behavior |
|---|---|
| With task | Scouts focus on task-relevant areas |
| With context | Prior decisions passed to scouts alongside task |
| Without task | Full repo recon, including onboarding-mode cold starts |
| With scope | Explicit scope overrides scout suggestions |
| With modules | Depth agents dispatched after core synthesis |
| No modules | Core layer only — cheapest possible recon |
| With session_id | Structure Scout cached, Pattern Scout always fresh |

### Cost Profile

| Configuration | Agents | Profile mix | Routing intent |
|---|---|---|---|
| Core only | 2 | 2x standard | Lower-cost profile mix |
| Core + 1 mechanical module | 3 | 3x standard | Lower-cost profile mix |
| Core + 1 judgment module | 3 | 2x standard + 1x high | More judgment capacity |
| Core + 2 modules (mixed) | 4 | 2-3x standard + 1-2x high | More judgment capacity |
| Full repo, no task | 2 | 2x standard | Lower-cost profile mix (but slower) |

These profiles describe routing intent, not portable billed cost; each harness can map them to different models.

## Communication Requirements (Non-Negotiable)

Recon narrates its progress at these points — **every one is mandatory**:

1. **Before dispatching scouts** — "Dispatching Structure Scout and Pattern Scout [with cartographer context / cold start]."
2. **After scout completion, before synthesis** — "Scouts complete. Synthesizing core brief. [N conflicts detected.]"
3. **After depth module completion, before returning** — "Depth module [name] complete. Returning Investigation Brief."
4. **On overflow re-run** — "Scout [name] exceeded token budget. Re-running with narrowed scope: [new scope]."
5. **On cartographer conflict** — "Persistent-map conflict detected: [brief description]. Flagged as [auto-updated / unresolved]."
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

## Investigation workflow

Follow [`investigation-workflow.md`](investigation-workflow.md) for the full Phase 1–5 sequence, templates, recovery, and ledger assembly.

## Output and Return

Return the Investigation Brief as the agent output (inline return to parent skill).

The brief follows the exact core template assembled in
[Phase 3 — Assemble the Investigation Brief](investigation-workflow.md#assemble-the-investigation-brief)
(metadata block + core sections through the Verification Ledger). Do not re-echo
that template here — it is the authoritative template in `investigation-workflow.md`.

When depth modules ran, append their sections after a `---` separator, in this
order (only the requested modules' sections appear):

1. `## Impact Analysis`
2. `## Consumer Registry`
3. `## Friction Scan`
4. `## Subsystem Manifest`
5. `## Diagnostic Context`
6. `## Execution Readiness` — **Test command** / **Lint command** / **CI checks** / **Manual verification**

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
- `## Verification Ledger` — present in every brief (may contain only an HTML-comment placeholder when no causal claims detected). Consumers that do not parse the ledger can ignore it; the section is additive. The per-entry format is a reader-friendly convention, not a strict grammar.

**Semi-stable (consumers that request specific modules depend on these):**
- Depth module section headers: `## Impact Analysis`, `## Consumer Registry`, `## Friction Scan`, `## Subsystem Manifest`, `## Diagnostic Context`, `## Execution Readiness`
- Execution Readiness structured subfields: `Test command`, `Lint command`, `CI checks`, `Manual verification` — parsed by `/build`, must not be renamed without updating consumers

**Unstable (internal content, not parsed by header):**
- Content within sections — formatting, subheadings, bullet structure may evolve

**Process:** Any change to a stable or semi-stable header is a breaking change. The PR must update all consumer skill templates that reference the changed header. **Exception: adding a new semi-stable header is additive and non-breaking.** Consumers that don't parse the new section are unaffected. Renaming or semantically changing an existing header is still breaking. Adding new depth modules is non-breaking.

## Verification Ledger

See [`verification-ledger.md`](verification-ledger.md) for scope, entry format, empty state, and falsification instructions. In a repo with `docs/decisions/`, falsifications belong under the trailing `## Falsifications` heading. <!-- CONTRACT:adr-falsification-home -->

## Design Principles and Guardrails

See [`guardrails.md`](guardrails.md) for operating principles and red flags.

## Integration

**Dispatches:**
- `structure-scout-prompt.md` — Structure Scout (standard, Explore)
- `pattern-scout-prompt.md` — Pattern Scout (standard, Explore)
- `impact-analyst-prompt.md` — Impact Analyst (high)
- `consumer-mapper-prompt.md` — Consumer Mapper (standard)
- `friction-scanner-prompt.md` — Friction Scanner (high)
- `manifest-builder-prompt.md` — Manifest Builder (standard)
- `diagnostic-gatherer-prompt.md` — Diagnostic Gatherer (high)
- `readiness-checker-prompt.md` — Readiness Checker (standard)

**Consults:** `/recon` persistent-map mode (consult mode — direct file read of `map.md`)

**Records to:** `/recon` persistent-map mode (recorder dispatch after investigation, using `cartographer/recorder-prompt.md`)

**Called by:** `/design` (Phase 2 context + impact-analysis), `/spec` (per-ticket investigation + impact-analysis), `/migrate` (Phase 0 + consumer-registry), `/audit` (Phase 1 code scoping + subsystem-manifest)

**Not called by (investigated, not a fit):** `/debugging` (specialized investigation pipeline), `/build` (inherits via /design). Improvement discovery and whole-repo onboarding are modes of this skill, not callers. See #147 for the remaining rationale.

**Pairs with:** `/design` approach evaluation (sequential — recon produces evidence, design evaluates options)
