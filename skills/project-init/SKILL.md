---
name: project-init
description: Use when onboarding to an unfamiliar codebase and want full structural context before the first real task. Deep-scans the repo and discovers cross-repo topology.
---

# Project Init

## Overview

<!-- CANONICAL: shared/dispatch-convention.md -->
All subagent dispatches use disk-mediated dispatch. See `shared/dispatch-convention.md` for the full protocol.

Eliminate cold-start penalty by proactively mapping the current repo and its neighborhood. Instead of re-discovering the codebase during every first task, project-init builds structural context upfront so that build, design, and debugging skills start informed.

**Invocation:** User runs `/project-init`. Not auto-triggered.

**Two tiers:**
- **Tier 1** — Single repo deep scan. Fan-out partition explorers, fan-in to cartographer format.
- **Tier 2** — Cross-repo discovery. Scan sibling repos for topology and dependency relationships.

**Output:**
- Tier 1 writes to cartographer's existing data structures (`memory/cartographer/`)
- Tier 2 writes to `memory/topology/`

**Coverage distinction:** All output is tagged `<!-- project-init:structural -->`, marking it as breadth-first structural mapping. This is distinct from task-verified content produced by cartographer record mode during real work. Task-verified content is always preserved over structural content.

**Announce at start:** "I'm using the project-init skill to map this codebase and its neighborhood."

---

## Pre-flight: Scope Estimation

Before dispatching any agents, the orchestrator estimates work scope:

1. **Count top-level source directories** by scanning for files with recognized extensions: `.ts`, `.js`, `.py`, `.go`, `.rs`, `.java`, `.cs`, `.rb`, `.swift`, `.kt`, `.c`, `.cpp`, `.h`
2. **Count manifest files** (`package.json`, `go.mod`, `Cargo.toml`, `pyproject.toml`, `docker-compose.yml`) and **sibling repos** (git repos in parent directory)

Present the estimate to the user:

> "Found **N** source directories and **M** sibling repos. This will dispatch ~**X** agents. Proceed?"

**User options:**
- **Approve** — run both tiers
- **Skip Tier 2** — run Tier 1 only (single repo scan)
- **Narrow scope** — user specifies which directories or repos to include

Wait for user confirmation before proceeding. Do not dispatch agents without approval.

---

## Tier 1: Single Repo Deep Scan

### Step 0: Cleanup

Delete `/tmp/crucible-project-init/` if it exists from a prior run, then recreate it. This ensures a clean workspace for temp files.

```bash
rm -rf /tmp/crucible-project-init && mkdir -p /tmp/crucible-project-init
```

### Step 1: Detect Project Structure

Scan the repository to determine:

- **Source directories** — top-level directories containing files with recognized source extensions (`.ts`, `.js`, `.py`, `.go`, `.rs`, `.java`, `.cs`, `.rb`, `.swift`, `.kt`, `.c`, `.cpp`, `.h`)
- **Ecosystem** — inferred from manifest files:
  - `package.json` → Node/JavaScript/TypeScript
  - `go.mod` → Go
  - `Cargo.toml` → Rust
  - `pyproject.toml` / `requirements.txt` → Python
  - `pom.xml` / `build.gradle` → Java/Kotlin
  - `*.csproj` / `*.sln` → C#/.NET
  - `Gemfile` → Ruby
  - `Package.swift` → Swift
- **Config/doc directories** — directories with no source files (docs, config, assets)

### Small Repo Shortcut

If the entire repository has fewer than 20 source files (across all directories), skip the partition/fan-out/fan-in pipeline. Instead, dispatch a single Partition Explorer for the repo root and pass its output directly to the Init Recorder as a single partition report. This avoids unnecessary overhead for small codebases.

### Step 2: Partition

Split the repository into partitions for parallel exploration:

1. **One partition per top-level source directory** (e.g., `src/`, `lib/`, `pkg/`, `cmd/`)
2. **Small directories (<20 source files)** — single explorer handles the entire directory
3. **Doc/config-only directories** — lightweight explorer (reports "No source modules. Purpose: docs/config/assets")
4. **Large directories (50+ source files)** — sub-partition by next directory level. For example, `src/` with 80 files becomes `src/auth/`, `src/api/`, `src/models/`, etc.
   - **Max 1 level of sub-partitioning.** If a sub-partition still has 50+ files, the explorer handles it as a large partition (it will apply its own internal triage)

### Step 3: Fan-out — Partition Explorers

Dispatch parallel Explore subagents, one per partition:

```
Agent tool (subagent_type: Explore, model: sonnet)
```

Use the prompt template at `./partition-explorer-prompt.md`. Fill in the template variables:
- `[partition name]` — the partition directory name
- `[Partition root directory path]` — absolute path to the partition
- `[Source file extensions detected in this partition]` — which extensions were found
- `[Project ecosystem context]` — ecosystem info from Step 1

**When each explorer returns:** The orchestrator captures the return value and writes it to `/tmp/crucible-project-init/<partition-name>.md`. The explorer itself does not write files — the orchestrator does.

### Step 4: Fan-in — Init Recorder

Dispatch the Init Recorder to merge all partition reports into cartographer format:

```
Task tool (general-purpose, model: sonnet)
```

Use the prompt template at `./init-recorder-prompt.md`. Fill in the template variables:
- `[N]` — number of partition reports
- `[File paths to partition exploration reports]` — paths to temp files from Step 3
- `[Existing cartographer data]` — read and paste existing `memory/cartographer/map.md`, `conventions.md`, `landmines.md` if they exist, or say "No prior cartographer data."
- `[Project name and ecosystem]` — from Step 1
- `[Output directory]` — the project's `memory/cartographer/` path

**Batching for large repos (6+ partitions):** When there are 6 or more partition reports:
1. Group reports into batches of 5
2. Dispatch one Init Recorder per batch with "batch mode" in the description — each writes its merged output to `/tmp/crucible-project-init/batch-N.md` in **explorer format** (the same `## Modules Found`, `## Conventions Observed`, etc. sections used by partition explorers), NOT cartographer format. This is a consolidation pass, not a formatting pass. Set the Output Directory to `/tmp/crucible-project-init/batch-N.md`.
3. Dispatch a final Init Recorder (without "batch mode") that receives the batch output file paths and produces the definitive cartographer files. The final recorder treats batch files exactly like partition reports — same input format, same processing steps.
4. The final pass handles deduplication and conflict resolution across batches

The orchestrator passes **file paths, not content** for partition reports to the Init Recorder — the recorder reads the partition reports itself. Existing cartographer data (for re-invocation merge) is included directly in the dispatch file since it's small and needed for merge decisions.

### Step 5: Validation Gate

After the Init Recorder completes, run a three-way check:

**(a) Partition completeness** — Verify each partition explorer returned a non-empty result. Check that temp files exist at `/tmp/crucible-project-init/<partition-name>.md` and contain non-trivial content (more than 3 lines). Also check for the completion sentinel: `<!-- partition-explorer:complete -->` means full scan, `<!-- partition-explorer:partial -->` means some directories were unscanned (flag these in `map.md` Unmapped Areas).

**(b) Map representation** — Verify every partition that returned results is REPRESENTED in `map.md` — either as individual modules OR as a collapsed group in "Other" (collapsed partitions count as represented). Unrepresented partitions trigger focused re-recording: dispatch the Init Recorder again with just the missing partition reports.

**(c) Module field completeness** — Verify module entries have required fields populated: Path, Responsibility, Key Components must all be non-empty. Also verify that a `modules/<name>.md` file exists for each module listed in `map.md` with `Mapped Detail = Yes`.

Partitions that returned empty results are flagged as "unmapped" in `map.md` under the Unmapped Areas section.

### Step 6: Context Scan

Read the following files if they exist:
- `README.md` — project purpose, setup instructions
- `CONTRIBUTING.md` — contribution guidelines, review process
- `CLAUDE.md` — existing agent instructions

This is a direct read by the orchestrator, not a subagent dispatch. The orchestrator uses the extracted context for two purposes:
1. **CLAUDE.md proposal filtering** (Step 7) — avoid proposing content that duplicates existing CLAUDE.md
2. **Memory creation** — if README reveals project purpose, team conventions, or setup requirements not already in memory, save as `project` type memories via the auto-memory system

### Step 7: CLAUDE.md Proposal (Non-blocking)

If the Init Recorder produced `/tmp/crucible-project-init/claude-md-proposal.md`:

1. Read the existing project `CLAUDE.md` (if any) to identify already-configured content
2. Filter out proposals that duplicate existing CLAUDE.md content
3. Write the filtered proposal to `/tmp/crucible-project-init/claude-md-proposal-filtered.md` — this survives context compaction during Tier 2
4. **Do not present proposals yet** — continue to Tier 2. Proposals are presented at the END of the full run (after both tiers complete)

This step does NOT block Tier 2 — the pipeline continues autonomously.

### Size Caps

| File | Target | Hard Cap |
|------|--------|----------|
| `map.md` | 140 lines | 200 lines |
| `conventions.md` | 105 lines | 150 lines |
| `landmines.md` | 70 lines | 100 lines |
| `modules/<name>.md` | 70 lines | 100 lines |

Target 70% of caps — leave room for task-verified additions by cartographer record mode.

### Large Monorepo Triage

When the repository has many top-level source directories:

- **20+ partitions:** Warn user: "Large monorepo detected (N source directories). Recommend narrowing scope to specific areas." Offer to scan a subset.
- **Collapsed modules:** If the unified module count exceeds the map.md cap, collapse low-file-count modules into an "Other" row with count: `| Other | various | 12 single-file modules | No |`
- **Sub-partitioning cap:** Never sub-partition more than 1 level deep. Large sub-partitions are handled by the explorer's own triage logic.

**Orchestrator writes Tier 1 results to disk before proceeding to Tier 2.**

---

## Tier 2: Cross-Repo Discovery

### Step 0: Permission Probe

Before scanning neighbors, verify filesystem access:

1. Attempt to list the parent directory (`../`)
2. Attempt to read a file from a detected sibling repo

If access is denied, emit a clear skip message and end Tier 2:

> "Cross-repo discovery requires filesystem access to the parent directory. Skipping Tier 2."

### Step 1: Manifest Parsing

Parse supported manifest formats for cross-repo references:

| Format | What to Extract |
|--------|----------------|
| `package.json` | `dependencies`, `devDependencies` — look for `file:../` or workspace references |
| `go.mod` | `require` directives — look for local `replace` directives pointing to siblings |
| `Cargo.toml` | `[dependencies]` — look for `path = "../"` references |
| `pyproject.toml` | `[project.dependencies]` — look for local path references |
| `docker-compose.yml` | `services` — look for `build` paths pointing to siblings, shared networks/volumes |

Note detected-but-unparsed formats (e.g., `pom.xml` found but not parsed) so the user knows what was skipped.

### Step 2: Local Sibling Detection

Scan the parent directory for git repos:
- List directories in `../`
- Check each for `.git/` directory
- Cross-reference with manifest references from Step 1
- Classify each sibling:
  - **Manifest-referenced** — found in a manifest file (pre-selected for scanning)
  - **Co-located** — git repo in same parent directory, no manifest reference

### Step 3: User Confirmation

Present discovered repos to user before scanning:

> "Found **N** sibling repos. **M** are referenced in manifests (pre-selected). Confirm which to scan:"
>
> - [x] `../auth-service` (referenced in docker-compose.yml)
> - [x] `../shared-types` (referenced in package.json)
> - [ ] `../unrelated-project` (co-located, no reference)

Wait for user confirmation. Do not scan repos the user did not confirm.

### Step 4: Lightweight Neighbor Scan

Dispatch parallel Explore subagents, one per confirmed neighbor:

```
Agent tool (subagent_type: Explore, model: sonnet)
```

Use the prompt template at `./neighbor-scanner-prompt.md`. Fill in the template variables:
- `[repo name]` — the neighbor repository name
- `[Neighbor repo path]` — path to the neighbor
- `[Connection context]` — how it was discovered (manifest reference details)
- `[Current repo name and purpose]` — from Tier 1 results

Write each result to `/tmp/crucible-project-init/neighbors/<repo-name>.md`.

### Step 5: Relevance Ranking

After all neighbor scans complete, the orchestrator assigns relevance:

| Relevance | Criteria | Example |
|-----------|----------|---------|
| **High** | Direct dependency — imported, called, or required by current repo | `file:../shared-types` in package.json |
| **Medium** | Shared infrastructure — common services, shared DB, docker-compose links | Both use same Redis instance |
| **Low** | Co-located, no detected link — just happens to be in same parent directory | `../unrelated-tool` |

### Step 6: Topology Output

Dispatch the Topology Recorder to synthesize neighbor scans:

```
Task tool (general-purpose, model: sonnet)
```

Use the prompt template at `./topology-recorder-prompt.md`. Fill in the template variables:
- `[N]` — number of neighbor scans
- `[File paths to neighbor scan results]` — paths to temp files from Step 4
- `[Current repo name, ecosystem, purpose]` — from Tier 1
- `[Relevance scores]` — per-neighbor relevance from Step 5
- `[Existing topology data]` — read and paste existing `memory/topology/topology.md` if it exists, or say "No prior topology data."
- `[Output directory]` — the project's `memory/topology/` path

### Output Structure

After both tiers complete, the following structure exists:

```
~/.claude/projects/<project-hash>/memory/
  cartographer/
    map.md                    # Module map (← Tier 1)
    conventions.md            # Codebase patterns (← Tier 1)
    landmines.md              # Non-obvious breakage (← Tier 1)
    modules/
      <name>.md               # Per-module detail (← Tier 1)
  topology/
    topology.md               # Cross-repo dependency map (← Tier 2)
    <neighbor-name>.md        # Per-neighbor detail (← Tier 2)
```

---

## Completion: CLAUDE.md Proposal

After BOTH tiers complete (or after Tier 1 if Tier 2 was skipped), present the CLAUDE.md proposal if one was generated. Read from `/tmp/crucible-project-init/claude-md-proposal-filtered.md` (the filtered version from Step 7):

> "Structural mapping complete. Also generated CLAUDE.md proposals based on what I found. Review below — merge what's useful."
>
> [display proposal content]

**User options:**
- Accept all — orchestrator appends all proposed content to the project's CLAUDE.md
- Accept selectively — user indicates which sections to keep
- Skip — no changes to CLAUDE.md

The orchestrator appends accepted content to the project's CLAUDE.md (creating the file if it doesn't exist). Appended content is added under a clear heading.

---

## Subagent Dispatch Summary

| Agent | Model | Dispatch | Prompt Template |
|-------|-------|----------|-----------------|
| Partition Explorer | Sonnet | Agent tool (Explore) | `./partition-explorer-prompt.md` |
| Init Recorder | Sonnet | Task tool (general-purpose) | `./init-recorder-prompt.md` |
| Neighbor Scanner | Sonnet | Agent tool (Explore) | `./neighbor-scanner-prompt.md` |
| Topology Recorder | Sonnet | Task tool (general-purpose) | `./topology-recorder-prompt.md` |

Explorers are dispatched via the Agent tool with the specified `subagent_type`. Recorders are dispatched via the Task tool (general-purpose). Use the prompt templates verbatim, filling in only the bracketed template variables.

---

## Agent Teams Fallback

If agent teams are not available (Agent tool does not support parallel dispatch), fall back to sequential dispatch with a one-time warning:

> "Agent teams not available. Running sequentially — this will take longer."

Behavior is unchanged except parallel dispatch becomes sequential. All steps, validation, and output remain the same.

---

## Re-invocation Merge Strategy

When project-init is run again on a repo with existing cartographer or topology data:

| Existing Content | Action |
|------------------|--------|
| `<!-- project-init:structural -->` tagged | **Overwrite** with fresh scan data |
| Task-verified (no structural tag) | **Preserve** — never modify or remove |
| New modules/neighbors not in prior data | **Add** with structural tag |
| Prior modules/neighbors absent from scan | **Flag** with `[STALE?]` marker — do not remove |
| Overflow after merge | **Prioritize** task-verified content, compress structural |

This strategy ensures that knowledge accumulated through real task work is never lost by a re-scan.

---

## Context Management

Project-init is context-intensive. Follow these rules to prevent context exhaustion:

1. **Tier 1 and Tier 2 are separate phases** — complete Tier 1 and write all results to disk before starting Tier 2
2. **Explorer outputs go to temp files** — the orchestrator writes explorer return values to `/tmp/crucible-project-init/` and passes file paths (not content) to recorders
3. **Never hold all explorer outputs in orchestrator context** — write each to disk as it returns
4. **Context pressure at 50%** — if the orchestrator reaches 50% context utilization, write accumulated data to disk, report partial progress to the user, and continue with remaining work
5. **Batching for large repos** — 6+ partition reports are batched through multiple recorder passes (see Step 4)

---

## Red Flags

**Never:**
- Hold all explorer outputs in orchestrator context simultaneously
- Exceed file size caps (200 lines map.md, 150 conventions.md, 100 landmines.md, 100 module files)
- Produce speculative content — record observed facts only
- Scan repos the user didn't confirm in Tier 2
- Skip the permission probe before Tier 2
- Skip the scope estimation or proceed without user approval

**Always:**
- Write to disk between tiers
- Tag all output with `<!-- project-init:structural -->`
- Present scope estimate and wait for user confirmation
- Respect the user's scope narrowing choices
- Validate after fan-in (three-way check)
- Preserve task-verified content during re-invocation
- Clean up `/tmp/crucible-project-init/` at the start of each run

---

## Integration

### Required Downstream Change

Cartographer `recorder-prompt.md` must handle structural tags — when updating files that contain `<!-- project-init:structural -->` content, the recorder preserves that tag on structural sections and omits it on task-verified additions.

### Downstream Consumption

Skills that benefit from project-init output:

| Skill | How It Uses project-init Data |
|-------|-------------------------------|
| `crucible:cartographer` (consult) | Reads `map.md` — structural content provides baseline even before any task exploration |
| `crucible:cartographer` (load) | Loads `modules/*.md` into subagent prompts — structural context prevents wrong assumptions |
| `crucible:build` | Gets structural awareness from cartographer consult at task start |
| `crucible:design` | Knows module boundaries and dependencies before proposing architecture |
| `crucible:debugging` | Loads module context and landmines for investigators |

### Does NOT

- Seed forge (forge learns from agent behavior, not codebase structure)
- Clone remote repos (works only with local filesystem)
- Run tests or install dependencies (read-only scan)
- Modify any source code

### Related Skills

- `crucible:cartographer` — ongoing codebase mapping (project-init bootstraps, cartographer maintains)
- `crucible:build` — implementation workflow (consumes cartographer data)
- `crucible:design` — architecture planning (consumes map and topology)
- `crucible:debugging` — investigation workflow (consumes modules and landmines)

**Does not dispatch /recon** -- bootstraps the cartographer data that /recon consults. Complementary, not overlapping. See #147 for rationale.

---

## Prompt Templates

- `./partition-explorer-prompt.md` — Structured exploration per partition for Tier 1
- `./init-recorder-prompt.md` — Multi-source fan-in recorder for Tier 1
- `./neighbor-scanner-prompt.md` — Lightweight neighbor exploration for Tier 2
- `./topology-recorder-prompt.md` — Topology file writer for Tier 2
