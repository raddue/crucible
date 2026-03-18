---
name: pathfinder
description: "Map a GitHub organization's service topology — repos, dependencies, communication edges. Triggers on 'map services', 'service topology', 'what depends on X', 'blast radius', or any task requesting cross-repo dependency analysis."
---

# Pathfinder

Maps an entire GitHub org's (or multiple orgs') service topology — what repos are services, how they talk to each other, and what infrastructure they share. Produces Mermaid diagrams, structured JSON, and a human-readable markdown report.

**Announce at start:** "Running pathfinder on [org names]."

**Skill type:** Rigid -- follow exactly, no shortcuts.

**Two modes:**
- **Full scan** — Three-phase execution: discover repos, analyze dependencies, synthesize topology.
- **Query mode** — Graph traversal on persisted topology data. Answers upstream/downstream/blast-radius questions without re-scanning.

**Invocation:**
- Full scan: `crucible:pathfinder <org1> [org2] [org3...]`
- Query mode: `crucible:pathfinder query <type> <target>`

## Model

- **Orchestrator:** Opus
- **Discovery classifier (Phase 1):** Sonnet via Task tool (general-purpose)
- **Analysis agents (Phase 2):** Sonnet via Agent tool (subagent_type: Explore)
- **Synthesis agent (Phase 3):** Opus via Agent tool (subagent_type: general-purpose)
- **Query handler:** Sonnet via Task tool (general-purpose)

## Communication Requirement (Non-Negotiable)

**Between every agent dispatch and every agent completion, output a status update to the user.** This is NOT optional -- the user cannot see agent activity without your narration.

Every status update must include:
1. **Current phase** -- Which phase you're in (Discovery, Analysis Tier 1, Analysis Tier 2, Synthesis)
2. **What just completed** -- What the last agent reported (repo count, edge count, errors)
3. **What's being dispatched next** -- What you're about to do and why
4. **Progress counts** -- Repos completed/remaining, edges found so far, errors encountered

**After compaction:** Re-read the state file at `/tmp/pathfinder-state.json` and current phase state before continuing. See Compaction Recovery below.

**Examples of GOOD narration:**
> "Phase 2 (Tier 1): Wave 1 complete — 10/45 repos analyzed, 23 edges found so far. Dispatching wave 2 (repos 11-20)."

> "Phase 2 (Tier 1): All 45 repos analyzed. Found 68 services, 94 edges (79 HIGH, 15 MEDIUM). Presenting checkpoint before Tier 2."

> "Phase 3: Synthesis agent dispatched. Processing 45 per-repo result files to build unified topology."

## Scratch and State

- **State file:** `/tmp/pathfinder-state.json` -- written by orchestrator, updated after each repo completes. Schema:
  ```json
  {
    "orgs": ["acme-platform"],
    "phase": "analysis-tier1",
    "repos_total": 45,
    "repos_completed": ["acme-platform/orders-api", "acme-platform/auth-service"],
    "repos_remaining": ["acme-platform/payments-service"],
    "clone_paths": { "acme-platform/orders-api": "/tmp/pathfinder/acme-platform/orders-api/" }
  }
  ```
  All repo names in `repos_completed`, `repos_remaining`, and `clone_paths` must use qualified `org/repo` format for multi-org disambiguation.

- **Per-repo results:** `/tmp/pathfinder/<org>/repos/<repo-name>.json` -- written immediately on agent completion, survives compaction.
- **Clone directory:** `/tmp/pathfinder/<org>/<repo>/` -- shallow clones performed by orchestrator.
- **Output directory:** `docs/pathfinder/<org-name>/` (single org) or `docs/pathfinder/<combined-name>/` (multi-org, alpha-sorted org names joined by `+`, e.g., `acme-infra+acme-platform`).
- **Persistence path:** `~/.claude/memory/pathfinder/<org-name>/topology.json` -- well-known absolute path, outside project-hash system. Multi-org stored under combined name.

## Phase 1: Discovery

### Pre-flight Checks

Before any scanning, verify the environment:

1. **Authentication:** Run `gh auth status`. If not authenticated, stop with a clear message: "GitHub CLI is not authenticated. Run `gh auth login` first."
2. **Rate limit budget:** Run `gh api rate_limit`. Estimate API calls needed: `(repo_count / 30) + clone_count`. If remaining budget is less than the estimate, warn user: "Rate limit budget may be insufficient. Estimated need: N calls, remaining: M. Proceed anyway?"
3. **Org access:** For each provided org, run `gh repo list <org> --limit 1`. If any org is inaccessible, report which ones failed and offer to continue with accessible orgs only.

### Repo Enumeration

For each provided org, fetch repo metadata:

```bash
gh repo list <org> --json name,description,primaryLanguage,repositoryTopics,isArchived,diskUsage,pushedAt --limit 1000
```

### Classification Dispatch

Dispatch the discovery classifier via Task tool (general-purpose, model: Sonnet) using `./discovery-classifier-prompt.md`.

**Input:** Org name and the full JSON array of repo metadata.

**Output:** Classified repo list with type, confidence, monorepo flags, and exclusions.

### User Confirmation Gate

Present a summary to the user:

> "Found 147 repos across 2 orgs. 68 look like services, 22 libraries, 12 infrastructure, 45 unknown. 8 archived (excluded). Proceed?"

**Do NOT proceed without user confirmation.** The user may:
- Exclude specific repos by name
- Narrow scope to specific repo types
- Abort entirely

### Exclusions

Archived repos and empty repos (diskUsage = 0) are excluded by default. They are listed in the appendix of the classification results so the user can see what was excluded and override if needed.

## Phase 2: Analysis

### Local Resolution

Before cloning, check `../` for existing clones matching repo names from the classification results.

Report to user:
> "Found 23 repos locally. Will shallow-clone the remaining 45 to /tmp/pathfinder/."

Local repos are used in-place -- no copying. The orchestrator passes their existing paths to analysis agents.

### Orchestrator-Managed Cloning

The orchestrator performs all cloning sequentially. Subagents never clone.

```bash
gh repo clone <org>/<repo> /tmp/pathfinder/<org>/<repo>/ -- --depth=1
```

- Write progress to state file after each clone completes.
- **Large repos (>1GB disk usage from metadata):** Skip clone. Perform manifest-only scan by dispatching a Tier 1 agent with a note that only manifests from the GitHub API are available. Inform user: "Skipping clone for <repo> (>1GB). Manifest-only scan."
- **Clone failure:** Skip the repo, log the error to the state file, continue with remaining repos. Report to user.

### Tier 1 Analysis

Dispatch analysis agents in waves of max 10 concurrent via Agent tool (subagent_type: Explore, model: Sonnet) using `./tier1-analyzer-prompt.md`.

Each agent receives:
- Repo path on disk (pre-cloned or local)
- Classification from Phase 1 (type, language, confidence, monorepo status)
- All repo names in this scan (for internal package detection)
- Org names being scanned (for scope matching)

**Per-repo results:** Written to `/tmp/pathfinder/<org>/repos/<repo-name>.json` immediately on agent completion.

**State updates:** After each agent completes, update the state file (move repo from `repos_remaining` to `repos_completed`).

**Batching:** For orgs with 50+ repos, batch into waves of 10. Complete one wave before starting the next. Output a status update after each wave completes.

### Tier 1 Checkpoint

After all Tier 1 agents complete, present initial findings to the user:

> "Tier 1 complete. Found 68 services, 94 edges (79 HIGH, 15 MEDIUM). Here's the overview. Would you like me to run a deep code scan for additional edges?"

Include a summary table:
- Edge types found (HTTP: N, Kafka: N, gRPC: N, shared-db: N, shared-package: N, infrastructure: N)
- Services with no detected edges (potential orphans or miscategorized repos)
- Monorepos with sub-service counts

**User options:**
- **Proceed to Tier 2** -- deep code scan for additional edges
- **Skip to synthesis** -- generate topology from Tier 1 findings only
- **Abort** -- stop without generating output

**Do NOT proceed to Tier 2 without explicit user opt-in.**

### Tier 2 Analysis (Opt-in)

Dispatch deep scan agents in waves of max 10 via Agent tool (subagent_type: Explore, model: Sonnet) using `./tier2-analyzer-prompt.md`.

Each agent receives:
- Repo path on disk
- Tier 1 findings JSON for that repo (so it knows what edges were already found)
- All repo and service names in this scan
- Org names being scanned

**Per-repo limits:** Max 200 source files scanned, max 50 grep matches retained. Prioritize recently modified files (by filesystem timestamps).

**Context self-monitoring:** Agents report at 50% context usage.

**Result merging:** Tier 2 results merge with Tier 1:
- New edges added to the per-repo JSON
- Existing edges upgraded if code evidence confirms config evidence (confidence boost)
- Updated per-repo JSON files written to disk

## Phase 3: Synthesis

Dispatch a single synthesis agent via Agent tool (subagent_type: general-purpose, model: Opus) using `./synthesis-prompt.md`.

**Input:**
- Paths to all per-repo JSON result files
- Tier depth (1 or 2)
- Output directory path
- Persistence path
- Existing topology.json contents (if incremental run, otherwise "No prior topology data.")

**The synthesis agent produces all output artifacts:**

1. **`topology.json`** -- Source of truth. Contains meta, services, edges, and clusters arrays. Written to BOTH the output directory and the persistence path.
2. **`topology.mermaid.md`** -- Full org graph. Nodes shaped by type, edges labeled by type, monorepo services in subgraph blocks. Line style: solid = HIGH, dashed = MEDIUM, dotted = LOW. For 30+ services, render at cluster level.
3. **`clusters/<cluster-name>.mermaid.md`** -- One Mermaid file per detected cluster with internal and external edges.
4. **`report.md`** -- Human-readable summary: service inventory, dependency matrix, cluster descriptions, flagged items, recommendations.
5. **`scan-log.json`** -- Scan metadata: per-repo timing, errors, skipped repos, rate limit usage.

**Orchestrator verification:** After the synthesis agent completes, verify:
- `topology.json` exists and is valid JSON
- `report.md` exists and is non-empty
If verification fails, report the failure to the user and offer to re-dispatch synthesis.

## Phase 4: Report

Present results to the user with key metrics:
- Service count, edge count, cluster count
- Coverage breakdown (HIGH/MEDIUM/LOW confidence services and edges)

Show the full Mermaid graph (or cluster-level graph if 30+ services).

Highlight flagged items:
- LOW-confidence classifications requiring human review
- Unresolved edge references (env vars or hostnames that could not be matched)
- Scan errors (clone failures, malformed manifests, skipped repos)

**Offer to commit output** to `docs/pathfinder/<org>/` (or combined directory for multi-org).

## Query Mode

Triggered by `crucible:pathfinder query <type> <target>`.

### Storage

Read topology data from `~/.claude/memory/pathfinder/<org-name>/topology.json` -- the well-known absolute path outside the project-hash system. Multi-org topologies are stored under the combined name (alpha-sorted org names joined by `+`).

### Query Types

| Query | Description | Example |
|-------|-------------|---------|
| `upstream <service>` | Who calls this service? | "What services depend on auth-api?" |
| `downstream <service>` | What does this service call? | "What does orders-api talk to?" |
| `blast-radius <service>` | If this service changes, what breaks? (transitive) | "What's the blast radius of changing payments-service?" |
| `shared-infra <resource>` | Which services share this resource? | "Who else uses the shared-redis instance?" |
| `path <service-A> <service-B>` | How do these services communicate? | "How does the frontend reach billing?" |

### Integration with Other Skills

Query mode is RECOMMENDED (not required) -- skills check for pathfinder data and use it if available, gracefully degrade if not.

- **`crucible:build`** -- Phase 1 blast radius analysis extends across repos when pathfinder data exists.
- **`crucible:design`** -- Investigation agents consult pathfinder to understand cross-service impact.
- **`crucible:audit`** -- Subsystem audit scope can include immediate upstream/downstream neighbors.

### Cold Start

If no `topology.json` exists for the queried org, return empty results and suggest running a full scan:

> "No topology data available for [org]. Run `crucible:pathfinder <org>` to perform a full scan."

No errors, no blocking -- graceful degradation.

### Dispatch

Dispatch query handler via Task tool (general-purpose, model: Sonnet) using `./query-handler-prompt.md`.

Pass:
- Query type
- Query target(s)
- Full topology.json contents

Present structured results to the user.

**Cycle detection:** Mandatory for blast-radius and path queries. BFS with a visited set. Cycles are detected and reported explicitly: "Circular dependency detected: A -> B -> A."

## Multi-Org Support

- All provided orgs are enumerated and analyzed together in a single run.
- The dependency graph spans org boundaries -- cross-org edges are shown explicitly.
- All service names are qualified as `org/repo` to prevent name collisions across orgs.
- Output directory for multi-org: `docs/pathfinder/<combined-name>/` where combined name is alpha-sorted org names joined by `+` (e.g., `acme-infra+acme-platform`).
- Persistence path follows the same combined naming convention.

## Monorepo Handling

**Detection signals:**
- Workspace configs: npm `workspaces`, `go.work`, Cargo.toml `[workspace]`, Bazel `WORKSPACE`
- Multiple Dockerfiles in subdirectories
- Multiple independent CI/CD pipelines per subdirectory

**Sub-service enumeration:** Each directory containing a Dockerfile or listed as a workspace member is treated as a separate service node.

**Naming convention:** Sub-services are named `<repo>/<subdir>` (e.g., `platform/services/auth`) to avoid collisions with standalone repos.

**Treatment in output:**
- Each sub-service becomes its own node in the topology graph
- Monorepo sub-services are grouped in Mermaid `subgraph` blocks named after the repo
- Internal monorepo edges are tracked but visually distinguished from cross-repo edges (thinner lines, different color)

## Compaction Recovery

Pathfinder's Phase 2 with many parallel agents is compaction-prone. State is persisted to survive compaction.

**State file:** `/tmp/pathfinder-state.json` -- written by orchestrator, updated after each repo completes.

**State schema:**
```json
{
  "orgs": ["acme-platform"],
  "phase": "analysis-tier1",
  "repos_total": 45,
  "repos_completed": ["acme-platform/orders-api", "acme-platform/auth-service"],
  "repos_remaining": ["acme-platform/payments-service"],
  "clone_paths": { "acme-platform/orders-api": "/tmp/pathfinder/acme-platform/orders-api/" }
}
```

All repo names must use qualified `org/repo` format for multi-org disambiguation.

**Per-repo results:** Already written to `/tmp/pathfinder/<org>/repos/<repo-name>.json` on agent completion -- these survive compaction.

**Recovery logic:**

1. Read the state file to determine current phase.
2. **If Phase 2 (analysis-tier1 or analysis-tier2):** Skip repos listed in `repos_completed`. Resume dispatching agents for repos in `repos_remaining`. Use `clone_paths` to locate pre-cloned repos.
3. **If Phase 3 (synthesis):** Re-dispatch synthesis with all available per-repo result files from `/tmp/pathfinder/<org>/repos/`.
4. **If query mode:** No state needed -- read `topology.json` from persistence path and re-dispatch the query handler.

**After recovery:** Output a status update to the user before continuing:
> "Recovered from compaction. Phase 2 (Tier 1): 23/45 repos complete. Resuming from repo 24."

## Error Handling

| Error | Response |
|-------|----------|
| `gh auth` failure | Stop with clear message: "GitHub CLI is not authenticated. Run `gh auth login` first." |
| Rate limit hit during execution | Pause, report remaining budget, offer to continue with reduced parallelism (waves of 5 instead of 10). |
| Rate budget insufficient at pre-flight | Warn user with estimate before starting. User decides whether to proceed. |
| Clone failure (single repo) | Skip repo, log error to state file and scan-log.json, continue with remaining repos. |
| Unresolvable edge references | Flag in report as "unresolved" in the Flagged Items section. Do NOT silently drop. |
| Large repos (>1GB disk usage) | Manifest-only scan, skip clone. Inform user. |
| Org membership limitations | Warn: "Only publicly visible repos are scanned. Private repos require org membership." |
| Service name collision across orgs | Prevented by qualified `org/repo` identifiers -- no action needed. |
| Malformed manifest file | Log the parse error, continue scanning other files in the repo. |
| Agent context exhaustion | Agent reports partial results with `partial: true` flag. Orchestrator logs which repos need re-scanning. |

## Persistence and Incremental Runs

Each scan writes to both committed artifacts (`docs/pathfinder/<org>/`) and the queryable store (`~/.claude/memory/pathfinder/<org>/topology.json`).

Subsequent runs merge with existing data using these rules:
- **New repos:** Added with `status: "active"`
- **Removed repos:** `status` set to `"stale"`, kept in topology for one more run, then removed on the next scan
- **Existing repos:** Classification and edges updated; confidence takes max of old/new
- **Edge merge:** Edges matched by identity (`source + target + type + label`). Confidence: take max. Evidence: union. Direction: flag if contradictory.
- **Clusters:** Always recomputed from scratch on the merged edge set (not incrementally)
- **Mermaid diagrams:** Regenerated from merged JSON

Separate orgs (or org combinations) maintain separate output directories and persistence paths.

## Guardrails

**Analysis agents must NOT:**
- Modify any code (pathfinder is read-only)
- Clone repos (orchestrator handles all cloning)
- Scan source code in Tier 1 (configs and manifests only)
- Invent edges without evidence from actual files

**The orchestrator must NOT:**
- Proceed to Phase 2 without user confirmation of discovery results
- Proceed to Tier 2 without explicit user opt-in at the Tier 1 checkpoint
- Run more than 10 concurrent analysis agents
- Skip narration between agent dispatches (Communication Requirement)
- Clone repos larger than 1GB (use manifest-only scan instead)

## Red Flags

- Cloning inside subagents instead of the orchestrator
- Skipping the Tier 1 checkpoint before Tier 2
- Silently dropping unresolved references instead of flagging them
- Running synthesis before all analysis agents complete
- Exceeding 10 concurrent agents in any wave
- Proceeding past any user gate without confirmation

## Integration

- **Consults:** None (standalone initial scan)
- **Consumed by:** `crucible:build` (blast-radius extends across repos), `crucible:design` (cross-service impact analysis), `crucible:audit` (upstream/downstream neighbor scope)
- **Query mode consumers:** Other skills read `topology.json` from well-known persistence path (`~/.claude/memory/pathfinder/<org>/topology.json`)
- **Does NOT:** Modify any code, deploy anything, run tests, install dependencies
- **Related skills:** `crucible:build`, `crucible:design`, `crucible:audit`

## Subagent Dispatch Summary

| Agent | Model | Dispatch | Prompt Template |
|-------|-------|----------|-----------------|
| Discovery Classifier | Sonnet | Task tool (general-purpose) | `./discovery-classifier-prompt.md` |
| Tier 1 Analyzer | Sonnet | Agent tool (Explore) | `./tier1-analyzer-prompt.md` |
| Tier 2 Analyzer | Sonnet | Agent tool (Explore) | `./tier2-analyzer-prompt.md` |
| Synthesis Agent | Opus | Agent tool (general-purpose) | `./synthesis-prompt.md` |
| Query Handler | Sonnet | Task tool (general-purpose) | `./query-handler-prompt.md` |

## Prompt Templates

- `./discovery-classifier-prompt.md` -- Phase 1 repo classification from metadata
- `./tier1-analyzer-prompt.md` -- Phase 2 Tier 1 manifest and config scanning
- `./tier2-analyzer-prompt.md` -- Phase 2 Tier 2 deep code scanning
- `./synthesis-prompt.md` -- Phase 3 cross-reference, edge resolution, cluster detection, output generation
- `./query-handler-prompt.md` -- Query mode graph traversal and blast-radius computation
