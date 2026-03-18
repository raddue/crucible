---
name: pathfinder
description: "Map a GitHub organization's service topology — repos, dependencies, communication edges — and detect topology drift over time. Triggers on 'map services', 'service topology', 'what depends on X', 'blast radius', 'what changed', 'topology drift', 'diff', or any task requesting cross-repo dependency analysis."
---

# Pathfinder

Maps an entire GitHub org's (or multiple orgs') service topology — what repos are services, how they talk to each other, and what infrastructure they share. Detects structural drift by comparing current scans against baselines to surface new services, severed edges, confidence changes, and cluster restructuring. Produces Mermaid diagrams, structured JSON, and a human-readable markdown report.

**Announce at start:** "Running pathfinder on [org names]."

**Skill type:** Rigid -- follow exactly, no shortcuts.

**Four modes:**
- **Full scan** — Three-phase execution: discover repos, analyze dependencies, synthesize topology.
- **Query mode** — Graph traversal on persisted topology data. Answers upstream/downstream/blast-radius questions without re-scanning.
- **Crawl mode** — Seed-based bidirectional discovery: start from one repo, trace dependencies forward and reverse to discover connected services. For large orgs where full enumeration is impractical.
- **Diff mode** — Compare a current topology scan against a baseline to surface structural drift: new services, severed edges, confidence changes, cluster restructuring. Transforms pathfinder from a snapshot tool into a change-detection system.

**Invocation:**
- Full scan: `crucible:pathfinder <org1> [org2] [org3...]`
- Query mode: `crucible:pathfinder query <type> <target>`
- Crawl mode: `crucible:pathfinder crawl <org>/<repo> [--depth N] [--orgs org1,org2]`
- Full-scan diff: `crucible:pathfinder diff <org>`
- Crawl diff: `crucible:pathfinder diff <org>/<repo> [--depth N] [--orgs org1,org2]`
- File comparison: `crucible:pathfinder diff --baseline path/old.json --current path/new.json`

Common diff options:
- `--tier 2` — run deep code scan during rescan (default: Tier 1 only)

## Model

- **Orchestrator:** Opus
- **Discovery classifier (Phase 1):** Sonnet via Task tool (general-purpose)
- **Analysis agents (Phase 2):** Sonnet via Agent tool (subagent_type: Explore)
- **Synthesis agent (Phase 3):** Opus via Agent tool (subagent_type: general-purpose)
- **Query handler:** Sonnet via Task tool (general-purpose)
- **Reverse Searcher (Crawl mode):** Sonnet via Agent tool (subagent_type: general-purpose)
- **Diff Analyzer (Diff mode):** Sonnet via Task tool (general-purpose)

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

> "Crawl (Seed): Seed analysis complete — TypeScript API, 5 outbound refs, 3 identity signals. Dispatching reverse search + depth 1 forward analysis."

> "Crawl (Depth 2): Wave complete — discovered 8 new repos (total: 14), 31 edges. Top-scored: acme/event-bus (importance: 9). Presenting checkpoint."

## Scratch and State

- **State file:** `/tmp/pathfinder-state.json` -- written by orchestrator, updated after each repo completes.

  The state file uses a `"mode"` field to discriminate between full scan, crawl, and diff schemas:
  - `"mode": "full-scan"` — existing full scan schema (unchanged)
  - `"mode": "crawl"` — crawl mode schema (see Crawl Mode section below)
  - `"mode": "diff"` — diff mode schema (see Diff Mode section below)

  **Full scan state schema:**
  ```json
  {
    "mode": "full-scan",
    "orgs": ["acme-platform"],
    "phase": "analysis-tier1",
    "repos_total": 45,
    "repos_completed": ["acme-platform/orders-api", "acme-platform/auth-service"],
    "repos_remaining": ["acme-platform/payments-service"],
    "clone_paths": { "acme-platform/orders-api": "/tmp/pathfinder/acme-platform/orders-api/" }
  }
  ```

  **Crawl mode state schema:**
  ```json
  {
    "mode": "crawl",
    "seed": "acme/funding-api",
    "orgs": ["acme", "acme-infra"],
    "max_depth": 3,
    "current_depth": 2,
    "current_phase": "crawl",
    "discovered": {
      "acme/funding-api": { "depth": 0, "found_via": "seed", "status": "analyzed", "importance": 10, "signal_sources": [] },
      "acme/payments-service": { "depth": 1, "found_via": "forward:env_var:PAYMENTS_SERVICE_URL", "status": "analyzed", "importance": 8, "signal_sources": [{"type": "env_var", "source_repo": "acme/funding-api"}] }
    },
    "frontier": ["acme/billing-worker"],
    "unresolved": [
      { "signal": "NOTIFICATION_URL=http://notify:3000", "source_repo": "acme/payments-service", "type": "env_var", "resolution": "pending" }
    ],
    "clone_paths": { "acme/funding-api": "../funding-api", "acme/payments-service": "/tmp/pathfinder/acme/payments-service/" },
    "edges_found": 12
  }
  ```

  **Diff mode state schema:**
  ```json
  {
    "mode": "diff",
    "diff_type": "full-scan",
    "org": "acme-platform",
    "phase": "rescan-tier1",
    "baseline_path": "~/.claude/memory/pathfinder/acme-platform/topology.json",
    "baseline_timestamp": "2026-03-11T14:30:00Z",
    "repos_total": 47,
    "repos_to_rescan": ["acme/orders-api", "acme/new-gateway"],
    "repos_reused": ["acme/auth-service"],
    "repos_remaining": ["acme/payments-service"],
    "clone_paths": {}
  }
  ```

  Crawl diff state adds `seed`, `orgs`, `max_depth`, `current_depth`, `frontier` — same fields as crawl mode, nested under `"diff_type": "crawl"`.

  **Diff mode phases:** `pre-flight` -> `discovery` -> `rescan-tier1` -> `rescan-tier2` (if --tier 2) -> `synthesis` -> `diff` -> `attribution` -> `impact-ranking` -> `report`

  All repo names in `repos_completed`, `repos_remaining`, and `clone_paths` must use qualified `org/repo` format for multi-org disambiguation.

- **Per-repo results:** `/tmp/pathfinder/<org>/repos/<repo-name>.json` -- written immediately on agent completion, survives compaction.
- **Per-repo persistence:** `~/.claude/memory/pathfinder/<org>/repos/<repo-name>.json` -- durable copy of per-repo results. Written alongside the `/tmp/` copy after each Tier 1/Tier 2 analysis completes. Used by diff mode's smart rescan to skip re-analysis of unchanged repos across sessions.
- **Crawl snapshot:** `~/.claude/memory/pathfinder/<org>/crawl-<seed-repo>/snapshot.json` -- written after each crawl completes. Contains the crawl-specific topology with full `crawl_metadata` (importance scores, discovery paths, depth info). `<seed-repo>` is the short repo name only (e.g., `crawl-funding-api`, NOT `crawl-acme/funding-api`). Used as the baseline for crawl diff mode's crawl-specific change categories.
- **Clone directory:** `/tmp/pathfinder/<org>/<repo>/` -- shallow clones performed by orchestrator.
- **Output directory:** `docs/pathfinder/<org-name>/` (single org) or `docs/pathfinder/<combined-name>/` (multi-org, alpha-sorted org names joined by `+`, e.g., `acme-infra+acme-platform`).
- **Persistence path:** `~/.claude/memory/pathfinder/<org-name>/topology.json` -- well-known absolute path, outside project-hash system. Multi-org stored under combined name.
- **Diff output (full-scan):** `docs/pathfinder/<org>/diffs/YYYY-MM-DD/`
- **Diff output (crawl):** `docs/pathfinder/<org>/crawl-<seed-repo>/diffs/YYYY-MM-DD/`
- **Diff output (file comparison):** `docs/pathfinder/manual-diffs/YYYY-MM-DD/`
- **Latest diff persistence:** `~/.claude/memory/pathfinder/<org>/latest-diff.json` — overwritten each run with the `topology-diff.json` contents. Consuming skills check this file opportunistically.

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

**Per-repo persistence:** After writing to `/tmp/`, also copy each per-repo result to `~/.claude/memory/pathfinder/<org>/repos/<repo-name>.json`. This durable copy survives across sessions and is read by diff mode's smart rescan. The orchestrator performs this copy — subagents are unaware of the persistence path.

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
- **Per-repo persistence:** After Tier 2 merging updates the per-repo JSON in `/tmp/`, also copy the updated file to `~/.claude/memory/pathfinder/<org>/repos/<repo-name>.json`.

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

## Crawl Mode

Crawl mode starts from a seed repo and discovers connected services by tracing dependencies bidirectionally. Unlike full scan (which enumerates an entire org top-down), crawl mode follows dependency threads from a known starting point. Use for large orgs (100+ repos) where full enumeration is impractical.

**Parameters:**
- `<org>/<repo>` — the seed repo to start from
- `--depth N` — max hop count from seed (default: 3, max: 10)
- `--orgs org1,org2` — which orgs to search for reverse references. If omitted, uses only the seed repo's org.

Named phases: **Pre-flight** → **Seed** → **Crawl** → **Tier 2 (opt-in)** → **Synthesis** → **Report**

### Pre-flight

- Same pre-flight checks as full scan: `gh auth status`, rate limit check, org access verification for seed org + all `--orgs`
- Verify seed repo exists: `gh repo view <org>/<repo>`. If not found, stop with clear message: "Seed repo `<org>/<repo>` not found or inaccessible."
- **Code search availability check:** For each org in `--orgs`, test code search with `gh api search/code -f q="test org:<org>" --jq '.total_count'`. If 403/422, warn: "Code search unavailable for `<org>`. Reverse search will not cover this org." Offer to continue with forward-only crawl.
- **Single-org notice:** If `--orgs` is omitted, display: "Reverse search will only cover the `<seed-org>` org. To discover cross-org callers, add `--orgs org1,org2`. Continue with single-org reverse search?"
- **Reverse search time estimate:** Based on org repo count and estimated signals per repo, display: "Estimated reverse search: ~N API calls across M orgs. At GitHub's code search rate (10 req/min), this may take ~X minutes."
- Initialize state file at `/tmp/pathfinder-state.json` with `"mode": "crawl"`

### Seed

- Clone seed repo following full scan cloning rules (local resolution in `../`, large repo handling, clone to `/tmp/pathfinder/<org>/<repo>/`)
- Run full Tier 1 analysis on seed using `./tier1-analyzer-prompt.md` — outputs both standard edge data AND identity signals
- Extract all outbound references (forward edges) and identity signals from Tier 1 output
- **Seed with no manifests fallback:** If Tier 1 returns zero outbound edges and no identity signals beyond the repo name, inform user: "Seed repo has no detectable dependencies or identity signals beyond its name. Reverse search will use repo name only. Results may be limited." Proceed with repo-name-only reverse search.
- **Present seed findings** to user before proceeding: "Seed repo is a [type] service ([language]). Found N outbound references and M identity signals. Proceeding to discover neighbors."

### Cloning

Crawl mode inherits all full scan cloning rules:
- **Local resolution:** Check `../` for existing clones matching repo names before cloning
- **Large repos (>1GB disk usage):** Skip clone, manifest-only scan. Inform user.
- **Clone path:** `/tmp/pathfinder/<org>/<repo>/` — same convention as full scan
- **Clone persistence:** Clones are NOT cleaned up between depth levels. The `clone_paths` map in the state file tracks all cloned repos. When a repo appears in the frontier that's already in `clone_paths`, skip cloning.
- **Clone failure:** Skip repo, log error, continue with remaining repos. Report to user.

### Crawl (Iterative Discovery)

```
# Seed is already analyzed in the Seed phase — use its results directly
discovered = {seed_repo: {depth: 0, found_via: "seed", status: "analyzed", importance: 10}}

# Depth 1 frontier comes from seed's forward refs + reverse search results
seed_forward_refs = seed_tier1_results.edges  # from Seed phase
seed_identity = seed_tier1_results.identity_signals
seed_reverse_refs = search_orgs_for_references(seed_identity, orgs)
frontier = resolve_references(seed_forward_refs + seed_reverse_refs)
depth = 1

while frontier is not empty AND depth <= max_depth:
    next_frontier = []
    for each repo in frontier:
        # Forward: what does this repo call?
        forward_refs = analyze_outbound(repo)  # Tier 1 analysis

        # Reverse: who calls this repo? (inline, not a separate phase)
        identity = repo.identity_signals  # from Tier 1 output
        reverse_refs = search_orgs_for_references(identity, orgs)

        # Resolve references to actual repos
        resolved = resolve_references(forward_refs + reverse_refs)

        for each new_repo in resolved:
            if new_repo not in discovered:
                score = compute_importance(new_repo, signal_sources)
                discovered[new_repo] = {depth: depth+1, found_via: ..., importance: score}
                next_frontier.append(new_repo)

    # Sort frontier by importance — structurally important repos analyzed first
    frontier = sort_by_importance(next_frontier)
    depth += 1

    # Adaptive depth: if all new candidates score below LOW_THRESHOLD, recommend termination
    if max(score for repo in next_frontier) < LOW_THRESHOLD:
        "All new repos at depth N are low-confidence single-signal matches. Recommend synthesis. Continue anyway?"

    # Checkpoint: present discoveries + batched unresolved references to user
    "Depth 2 complete: discovered 8 new repos (total: 14). Continue to depth 3?"
```

**Key details:**
- Each depth level is a wave — clone all new repos, analyze in parallel (max 10 concurrent, same as full scan)
- **User checkpoint after each depth level** — user can stop, exclude repos, or continue
- Forward analysis reuses the existing Tier 1 analyzer agents unchanged
- **Reverse search happens inline** during each crawl iteration (not as a separate phase) — dispatched via `./reverse-search-prompt.md`
- State file updated after each repo completes (compaction-safe)
- Per-repo persistence follows the same rule as full scan: after each Tier 1 analysis completes during crawl, copy the result to `~/.claude/memory/pathfinder/<org>/repos/<repo-name>.json`.
- Clones persist across depth levels — `clone_paths` in state file prevents re-cloning

### Bidirectional Analysis

Each discovered repo gets two types of analysis:

- **Fan-out (forward):** Analyze the repo's manifests/code to find what it calls — same as existing Tier 1/Tier 2 analysis
- **Fan-in (reverse):** Search across specified orgs for repos that reference this repo — uses identity signals from Tier 1 output

**Why bidirectional matters:** If Service A calls Service B, but Service B has no reference back to Service A, a forward-only crawl seeded from Service B would never discover Service A. Fan-in fixes this by searching the org for references TO each discovered repo.

### Reference Resolution

Layered confidence strategy for mapping references to actual repos:

| Strategy | Confidence |
|----------|-----------|
| Exact package match (go.mod, package.json) | HIGH |
| Docker image match | HIGH |
| Proto import match | HIGH |
| Env var hostname = repo name | MEDIUM |
| Env var hostname prefix match | LOW |
| Code search string match | LOW |

### Cross-Org Resolution

When `--orgs` includes multiple orgs, resolution searches all of them. A reference to `payments-service` checks `org1/payments-service`, `org2/payments-service`, etc. If found in exactly one org, auto-resolve. If found in multiple, add to the ambiguous queue.

### False Positive Mitigation for Reverse Search

- Exclude archived repos
- Exclude the repo being searched for (self-references)
- Exclude test/mock/example directories
- Require 2+ distinct references in a repo to count as a real edge (single mention = LOW confidence, noted but not auto-followed)
- Exclude well-known external service names (e.g., a repo named `redis` shouldn't match every Redis client config)

### Frontier Prioritization

**Scoring function (orchestrator logic, no additional API calls):**
- **Signal density:** How many distinct signals point to this candidate? (1 signal = 1pt, 2-3 = 3pts, 4+ = 5pts)
- **Signal diversity:** Discovered via multiple independent signal types? (bonus 2pts) vs single type (0pts)
- **Cross-cluster bridging:** Candidate's referrers span different already-identified clusters? (bonus 3pts)

**Score ranges:** Minimum 1pt, maximum 10pts.

**LOW_THRESHOLD = 2** — A repo scoring 2 or below was discovered by a single signal with no diversity or bridging bonus.

- Frontier sorted by score — high-importance repos analyzed first within each wave
- Score breakdown logged in state file and visible at checkpoints for transparency
- **Adaptive depth termination:** If the highest-scored candidate in a wave falls below LOW_THRESHOLD, recommend termination at the user checkpoint. Adaptive termination is always a recommendation, never automatic.

### Ambiguous Reference Handling

When a reference cannot be auto-resolved or has LOW confidence, queue for user input.

- Batched at end of each depth level and presented together at checkpoint
- User options per reference: skip, enter repo name, search orgs, pick from candidates
- **Resolution persistence:** User decisions stored in state file's `unresolved` array with `resolution` field — survives compaction

### Tier 2 (Opt-in)

Tier 2 deep code scanning is offered after all crawl depth levels complete, before synthesis:

> "Crawl complete. Discovered N repos across M depth levels with K edges. Would you like to run a deep code scan on all/selected repos for additional edges?"

User options: all repos, selected repos, or skip.

### Synthesis (Crawl)

- Dispatch Opus synthesis agent using `./synthesis-prompt.md` with crawl-specific augmentation
- Standard inputs same as full scan plus: `"mode": "crawl"`, `"seed": "<org>/<repo>"`, `crawl_metadata` map
- **Per-repo JSON augmentation:** Before dispatching synthesis, the orchestrator annotates each per-repo JSON file with a `"crawl_metadata"` block containing `depth`, `found_via`, `importance`, and `signal_sources` from the state file's discovered map. This keeps the Tier 1 analyzer unchanged — crawl metadata is added by the orchestrator after analysis.
- Produces discovery path section in report.md, uses importance scores for cluster weighting and Mermaid node sizing
- **Crawl snapshot persistence:** After synthesis completes, write a crawl-specific snapshot to `~/.claude/memory/pathfinder/<org>/crawl-<seed-repo>/snapshot.json`. This file contains the full topology.json output from this crawl (including `crawl_metadata`) BEFORE merging with existing full-scan topology. The snapshot preserves crawl-specific data (importance, discovery paths, depth) that gets diluted in the merged topology.json. The `<seed-repo>` uses the short repo name (e.g., `funding-api`).

### Merge Rules (Crawl)

- Edge identity matching same as full scan: `source + target + type + label`, confidence takes max, evidence unions
- **No stale-marking** for crawl merges — crawl results are intentionally partial. Stale-marking only applies to full scan mode.
- Crawl provenance preserved in topology.json's `crawl_metadata` section
- Reverse-search edges are new edge types that full scan doesn't produce; they merge normally

### Output Directories (Crawl)

- **Single-org crawl:** `docs/pathfinder/<org-name>/crawl-<seed-repo>/` where `<seed-repo>` is the short repo name (e.g., `crawl-funding-api`, NOT `crawl-acme/funding-api`)
- **Multi-org crawl:** `docs/pathfinder/<combined-orgs>/crawl-<seed-repo>/` (alpha-sorted, `+`-joined)
- **Persistence path:** `~/.claude/memory/pathfinder/<org-name>/topology.json` (same as full scan — crawl results merge into unified topology)
- **Crawl snapshot path:** `~/.claude/memory/pathfinder/<org>/crawl-<seed-repo>/snapshot.json` (durable, for crawl diff baselines)

## Diff Mode

Diff mode compares a current topology scan against a baseline to surface structural drift. It operates in three forms based on invocation:

- **Full-scan diff** (`crucible:pathfinder diff <org>`): Rescan the org using smart delta detection, compare against persisted topology.
- **Crawl diff** (`crucible:pathfinder diff <org>/<repo> [--depth N] [--orgs org1,org2]`): Re-crawl from seed, compare against persisted crawl topology. The distinction is natural: org name only = full-scan diff, org/repo = crawl diff.
- **File comparison** (`crucible:pathfinder diff --baseline path/old.json --current path/new.json`): Compare any two topology files directly. No rescanning.

Named phases: **Pre-flight** -> **Discovery** -> **Rescan Tier 1** -> **Rescan Tier 2 (if --tier 2)** -> **Synthesis** -> **Diff** -> **Attribution** -> **Impact Ranking** -> **Report**

### Pre-flight (Diff)

1. **Authentication and rate limit:** Same checks as full scan — `gh auth status`, `gh api rate_limit`.

2. **Baseline loading:**
   - **Full-scan diff:** Load baseline from `~/.claude/memory/pathfinder/<org>/topology.json`. If the file does not exist, stop: "No topology data for `<org>`. Run `crucible:pathfinder <org>` first."
   - **Crawl diff:** Load TWO baselines:
     - Unified topology from `~/.claude/memory/pathfinder/<org>/topology.json` (for service/edge/cluster diffs)
     - Crawl snapshot from `~/.claude/memory/pathfinder/<org>/crawl-<seed-repo>/snapshot.json` (for crawl-specific metadata diffs). If the snapshot does not exist, warn: "No crawl snapshot for `<org>/<repo>`. Crawl-specific changes (importance, discovery path) will not be computed. Service/edge/cluster diffs will still work." Proceed with topology.json only.
   - **File comparison:** Load baseline from `--baseline` path, current from `--current` path. Validate both are parseable JSON with the topology.json schema. If either fails to parse, stop: "Cannot parse [path]: [error]. Ensure the file is a valid pathfinder topology.json."

3. **Baseline validation:**
   - Extract `meta.scan_timestamp` from the baseline — this becomes `baseline_timestamp` used throughout.
   - If the baseline has no `scan_timestamp`, stop: "Baseline topology has no scan_timestamp. It may be from an older pathfinder version. Re-run a full scan to generate a timestamped topology."

4. **File comparison: mismatched mode warning:**
   - If baseline has `crawl_metadata` and current does not (or vice versa), warn: "Baseline is [crawl/full-scan], current is [full-scan/crawl]. Crawl-specific changes will not be computed."
   - If baseline covers different orgs than current, warn: "Baseline covers orgs [A, B], current covers [A, C]. Diff will only cover overlapping orgs."

5. **File comparison exits early:** For `--baseline`/`--current` invocations, skip directly to the Diff phase (no Discovery, no Rescan, no Synthesis). The two loaded files ARE the baseline and current topologies.

6. **Initialize state file:** Write `/tmp/pathfinder-state.json` with `"mode": "diff"`, `"diff_type": "full-scan"` or `"crawl"`, current phase `"pre-flight"`, and baseline path/timestamp.

### Discovery (Diff — Smart Rescan)

The goal is to identify which repos changed since the baseline and need re-analysis, and which can reuse their persisted per-repo JSON.

#### Full-Scan Diff Discovery

1. **Enumerate current repos:**
   ```bash
   gh repo list <org> --json name,description,primaryLanguage,repositoryTopics,isArchived,diskUsage,pushedAt --limit 1000
   ```

2. **Delta detection:** For each repo in the enumeration:
   - Find the matching service in the baseline topology by `name` (qualified as `org/repo`).
   - Compare the repo's `pushedAt` (full ISO 8601) against the service's `metadata.last_push`.
   - If `pushedAt > last_push`: mark as **"changed"** — needs re-analysis.
   - If `pushedAt <= last_push`: mark as **"unchanged"** — reuse persisted per-repo JSON.
   - If the repo is not in the baseline: mark as **"new"** — needs full analysis.
   - If a baseline service has no matching repo in the enumeration: it will appear as "removed" in the diff naturally.

3. **Per-repo cache check:** For each "unchanged" repo, verify the persisted per-repo JSON exists at `~/.claude/memory/pathfinder/<org>/repos/<repo-name>.json`.
   - If the file exists: confirmed reusable.
   - If the file is missing (cache miss — e.g., first diff run after upgrading from a pre-diff pathfinder version): re-mark as **"changed"** and log the cache miss.

4. **Confirm new repos:** If there are repos not seen in the baseline (genuinely new services), present them to the user: "Found N new repos not in the baseline: [list]. These will be cloned and analyzed. Proceed?" Do NOT proceed without confirmation.

5. **Update state file** with `repos_to_rescan` (changed + new), `repos_reused` (unchanged with valid cache), `repos_total`.

6. **Report to user:**
   > "Delta detection: N total repos. M unchanged (reusing cached results), K changed since baseline, J newly discovered. Proceeding to rescan K+J repos."

#### Crawl Diff Discovery

Same `pushedAt` optimization. Re-crawl from seed using crawl mode's iterative discovery, but at each depth level:
- **Unchanged repos** (pushedAt <= baseline last_push AND per-repo cache exists): skip Tier 1, reuse persisted JSON.
- **Changed/new repos:** Full Tier 1 analysis.
- **Reverse search always re-runs** at each depth level — org-wide code references may have changed even if the target repo's code didn't.
- Crawl depth checkpoints are inherited from crawl mode (user confirms after each depth level).

### User Gates (Diff Mode)

Diff mode streamlines user confirmations for speed:

- **No discovery confirmation** — you already know the org from the baseline.
- **No Tier 1 checkpoint** — diff is meant to be quick. The `--tier 2` flag replaces the interactive Tier 2 opt-in.
- **Confirm before cloning new repos** — repos not seen in the baseline (genuinely new services) require user confirmation before cloning. "Found N new repos not in the baseline: [list]. Clone and analyze?"
- **Crawl diff: checkpoint after each depth level** — inherited from crawl mode. User can stop, exclude repos, or continue at each depth.

### Rescan Tier 1 (Diff)

Only repos in `repos_to_rescan` (changed + new) are cloned and analyzed. This reuses the existing Tier 1 analysis infrastructure.

**If `repos_to_rescan` is empty** (all repos unchanged): skip the entire rescan phase. Proceed directly to synthesis with all results loaded from the persistence path. The diff will compare the baseline against the reconstructed topology (which should be identical, producing an empty diff).

1. **Local resolution:** Check `../` for existing local clones of repos to rescan (same as full scan).
2. **Clone repos to rescan:** Clone changed/new repos to `/tmp/pathfinder/<org>/<repo>/` using the same cloning rules as full scan (large repo handling, sequential cloning, state file updates).
3. **Dispatch Tier 1 agents** in waves of max 10 concurrent, using `./tier1-analyzer-prompt.md` (unchanged). Each agent receives the same inputs as full scan Tier 1.
4. **Write per-repo results** to both `/tmp/pathfinder/<org>/repos/<repo-name>.json` and `~/.claude/memory/pathfinder/<org>/repos/<repo-name>.json`.
5. **State file updates** after each agent completes — move repo from `repos_remaining` to completed.
6. **No Tier 1 checkpoint** — diff mode skips the interactive Tier 1 checkpoint. Diff is meant to be quick.

### Rescan Tier 2 (Diff — Only with --tier 2)

Only runs if the user passed `--tier 2` at invocation. There is no interactive Tier 2 opt-in in diff mode — the CLI flag replaces the checkpoint.

1. Dispatch Tier 2 agents for repos in `repos_to_rescan` only, in waves of max 10.
2. Uses `./tier2-analyzer-prompt.md` (unchanged).
3. Merge Tier 2 results into per-repo JSON (same merge rules as full scan Tier 2).
4. Write updated per-repo JSON to both `/tmp/` and persistence paths.

### Synthesis (Diff)

After rescan completes, merge reused + fresh per-repo results into a new topology.

1. **Collect all per-repo JSON:** For reused repos, load from `~/.claude/memory/pathfinder/<org>/repos/<repo-name>.json`. For rescanned repos, load from `/tmp/pathfinder/<org>/repos/<repo-name>.json`.
2. **Dispatch synthesis agent** using `./synthesis-prompt.md` (unchanged) with the collected per-repo results. Pass the existing topology.json as the incremental merge baseline.
3. **For crawl diffs:** Pass crawl metadata (seed, depth, importance) same as regular crawl synthesis. **Crawl diff synthesis inherits crawl mode's merge rules: no stale-marking of repos absent from the re-crawl.** Crawl results are intentionally partial — only repos discovered during the crawl are present. Do NOT mark missing repos as stale.
4. **Synthesis produces a new topology.json** written to both the output directory and the persistence path. This updates the persisted topology — running diff keeps your topology fresh.
5. **For crawl diffs:** Also write an updated crawl snapshot to `~/.claude/memory/pathfinder/<org>/crawl-<seed-repo>/snapshot.json`.
6. The new topology.json becomes the "current" topology for the diff phase.

### Diff

Dispatch the Diff Analyzer to compare baseline vs current topology.

1. **Dispatch Diff Analyzer** via Task tool (general-purpose, model: Sonnet) using `./diff-analyzer-prompt.md`.
2. **Inputs:**
   - `diff_type`: "full-scan", "crawl", or "file-comparison"
   - `baseline`: The baseline topology JSON loaded in pre-flight
   - `current`: The new topology JSON from synthesis (or the `--current` file for file comparison)
   - `crawl_baseline`: The crawl snapshot JSON (crawl diffs only, "N/A" otherwise)
3. **Output:** Structured diff JSON (`topology-diff.json` schema).
4. **Validation:** Verify the diff output is valid JSON and contains all required top-level fields (`meta`, `services`, `edges`, `clusters`, `summary`). If invalid, report error and offer to re-dispatch.

### Causal Commit Attribution

After the Diff Analyzer produces the structured diff, enrich edge-level changes and service additions with commit and PR attribution. This step is performed by the orchestrator directly (no subagent).

**Skip this step entirely for file-comparison mode** (`--baseline`/`--current`) — no cloned repos are available.

**Scope:** Attribution applies to:
- **Edge-level changes** (additions, confidence upgrades, confidence degrades, evidence changes): Each edge's evidence points to a file in a rescanned repo.
- **Removed edges in rescanned repos:** Run git log on the removed edge's evidence file — the log shows commits that deleted or modified the reference. For removed edges in repos NOT rescanned (or repos removed entirely), set `caused_by` to `null`.
- **Service additions:** Attributed to the repo's recent commits overall.
- **Does NOT apply to:** Service reclassifications, confidence changes, cluster changes, crawl-specific metadata changes (these are derived computations, not file-level changes).

**For each attributable change:**

1. Identify the repo from the change's evidence or service name.
2. Only run attribution on repos in the `repos_rescanned` set (repos that were cloned are available at their clone paths).
3. Run git log scoped to the evidence file:
   ```bash
   git -C {clone_path} log --since="{baseline_timestamp}" --format="%H %ae %s" -- {evidence_file}
   ```
4. Cross-reference with merged PRs:
   ```bash
   gh search prs --repo {org}/{repo} --merged-at ">={baseline_date}" --json number,title,author,mergedAt
   ```
   Where `baseline_date` is the date portion of `baseline_timestamp`.
5. Inject the `caused_by` field into the change entry in the diff JSON:
   ```json
   {
     "caused_by": {
       "repo": "org/repo",
       "commits": [{"sha": "abc123", "author": "alice", "message": "Add gateway integration", "date": "2026-03-16T14:22:00Z"}],
       "pull_requests": [{"number": 247, "title": "Integrate new API gateway", "author": "alice", "merged_at": "2026-03-16T15:00:00Z"}]
     }
   }
   ```
6. If git log or PR search fails for a repo, log the error in diff-log.json and leave the `caused_by` field as `null` for that change. Do not fail the entire attribution step.

**Cost:** Only runs on repos in `repos_rescanned`, scoped to evidence files. For a typical weekly diff with ~10 changed repos and ~20 structural changes, this is ~20-50 API calls.

### Impact Ranking

After attribution, rank each structural change by its transitive downstream footprint in the current topology. This reuses query mode's existing blast-radius BFS traversal — no new subagent needed.

**Performed by the orchestrator directly on the current topology.json:**

1. For each **edge change** (added, removed, confidence upgraded/degraded): identify the `target` service. Run BFS from that service following outbound edges to count transitive downstream services.
2. For each **service change** (added, removed, renamed): run BFS from that service to count transitive downstream services.
3. For each **cluster change** (membership changed): run BFS from the changed services to compute aggregate downstream impact.
4. Inject an `impact` field into each change entry in the diff JSON:
   ```json
   {
     "impact": {
       "downstream_count": 23,
       "affected_services": ["org/svc-a", "org/svc-b", "..."],
       "severity": "high"
     }
   }
   ```
5. **Severity classification** based on downstream_count:
   - **high:** 10+ downstream services
   - **medium:** 3-9 downstream services
   - **low:** 0-2 downstream services (leaf nodes)

**Cost:** BFS on an in-memory JSON graph. For 30 changes across a 200-service topology, this is sub-second computation. No API calls, no subagents.

**Impact on summary:**
The diff summary gains severity breakdown: "3 high-impact changes (affecting 40+ downstream services), 12 low-impact changes (leaf nodes only)." This transforms the weekly drift check from a flat change list into prioritized triage.

### Report (Diff)

Generate diff output artifacts in the appropriate output directory:
- Full-scan diff: `docs/pathfinder/<org>/diffs/YYYY-MM-DD/`
- Crawl diff: `docs/pathfinder/<org>/crawl-<seed-repo>/diffs/YYYY-MM-DD/`
- File comparison: `docs/pathfinder/manual-diffs/YYYY-MM-DD/`

Where `YYYY-MM-DD` is today's date. Timestamped directories accumulate diff history across runs.

#### Artifact 1: `topology-diff.json`

Write the (attribution-enriched) structured diff JSON from the Diff phase. This is the machine-readable output. Also write a copy to `~/.claude/memory/pathfinder/<org>/latest-diff.json` (overwriting any previous copy). Consuming skills check this file opportunistically.

#### Artifact 2: `diff-report.md`

Human-readable report with:
- **Summary table** of all changes (services added/removed/renamed/reclassified, edges added/removed/upgraded/degraded, clusters new/dissolved/changed)
- **Mermaid diagram with visual diff:**
  - Added edges: green (`style` directives with `stroke:green`)
  - Removed edges: dashed + red (`style` directives with `stroke:red,stroke-dasharray: 5 5`)
  - Confidence changes: yellow (`style` directives with `stroke:orange`)
  - Unchanged edges: default gray
  - New services: green node fill
  - Removed services: red node fill with dashed border
  - **Impact sizing:** High-impact changes get thicker edges and larger nodes; low-impact use default sizing
- **Impact-ranked change list** — changes sorted by severity (high first), showing downstream count and affected service names
- **Per-change detail** with evidence (which file changed, old/new value)
- **Causal attribution section** — for each change with a `caused_by` field, show the commits and PRs that caused it
- **Crawl diffs: discovery tree comparison** showing which repos appeared/disappeared at each depth level
- If no structural changes were detected, the report states: "No structural changes detected since [baseline timestamp]." Artifacts are still produced (empty diff).

#### Artifact 3: `diff-log.json`

Scan metadata:
- Per-repo: rescanned vs reused, timing, errors
- Cache miss count (repos that should have been reusable but had no persisted per-repo JSON)
- `pushedAt` deltas that triggered re-analysis
- Rate limit usage
- Attribution errors (if any)

#### Present results to user:

> "Diff complete. Comparing [baseline timestamp] -> [current timestamp]:
> - Services: +N added, -M removed, K renamed, J reclassified
> - Edges: +N added, -M removed, K confidence changes
> - Clusters: +N new, -M dissolved, K membership changes
> - Impact: H high-impact changes, M medium, L low
> - Rescanned N repos (M reused from cache)
> Output: [output directory path]"

Show the diff Mermaid diagram inline.

**Offer to commit output** to the output directory.

### Integration with Consuming Skills

No changes to consuming skills are required. Integration is additive and opportunistic.

**Well-known path:** `~/.claude/memory/pathfinder/<org>/latest-diff.json`

**Schema:** Same as `topology-diff.json` — the structured diff output.

**Consuming skill pattern:**
```
If latest-diff.json exists AND its meta.current_timestamp is within 7 days:
  Read and incorporate change awareness into the current task
Else:
  Proceed without diff data (existing behavior, no degradation)
```

**Potential consumers (documented for future reference, NOT implemented in this task):**
- **Build skill:** Refactor mode blast radius gains cross-repo change awareness. "This refactoring also affects 3 services that recently changed their edges to this service."
- **Design skill:** Investigation agents get topology change context. "Edge to X was added recently — may be unstable."
- **Audit skill:** Subsystem scoping gains neighbor change awareness. "This subsystem gained 2 new consumers since last week."
- **Query mode:** Unchanged. Queries run against `topology.json` which is updated by the rescan.

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
  "mode": "full-scan",
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

**Crawl mode recovery:** The compaction recovery logic reads `/tmp/pathfinder-state.json` and branches on the `mode` field:
- If `mode: "crawl"`: Read `current_phase` to determine resume point (seed, crawl, tier2, synthesis). Read `current_depth` and `frontier` for crawl progress. Skip repos with `status: "analyzed"` — resume from `status: "pending"`. Re-present only `unresolved` entries with `"resolution": "pending"`.
- If `mode: "full-scan"`: Existing recovery logic (unchanged).
- If `mode: "diff"`: Read `phase` to determine resume point. Branch on `diff_type`:
  - `"full-scan"`: Read `repos_to_rescan`, `repos_reused`, `repos_remaining`. Skip repos already completed. Resume from current phase (`discovery`, `rescan-tier1`, `rescan-tier2`, `synthesis`, `diff`, `attribution`, `report`).
  - `"crawl"`: Same as crawl mode recovery, plus diff-specific fields (`baseline_path`, `baseline_timestamp`).
  - The baseline topology is always available at the persistence path (never modified mid-run — only updated after synthesis completes).
  - Per-repo results on disk survive compaction.

**After recovery:** Output a status update to the user before continuing:
> "Recovered from compaction. Phase 2 (Tier 1): 23/45 repos complete. Resuming from repo 24."

> "Recovered from compaction. Crawl depth 2: 6/9 repos analyzed. Resuming from pending repos."

> "Recovered from compaction. Diff rescan: 15/22 repos re-analyzed. Resuming from repo 16."

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
| Seed repo not found | Stop with clear message: "Seed repo `<org>/<repo>` not found or inaccessible." |
| Seed repo has no manifests | Warn user, proceed with repo-name-only reverse search |
| Code search unavailable (403/422) | Warn: "Code search unavailable for `<org>`. Reverse search will not cover this org." Offer forward-only crawl. |
| Code search rate limit hit | Pause reverse search, present partial results, offer to continue with forward-only crawl |
| Code search returns 1000+ results | Signal too generic — skip it, log as "too broad", continue with other signals |
| No new repos discovered at depth level | Natural termination — proceed to synthesis |
| All references at a depth level are ambiguous | Present full unresolved list to user, don't auto-follow any |
| No baseline topology exists | Stop: "No topology data for `<org>`. Run `crucible:pathfinder <org>` first." |
| Baseline topology is corrupt/unparseable | Stop with clear message, suggest re-running full scan |
| `pushedAt` not available for a repo | Conservative: re-analyze that repo (don't skip) |
| All repos unchanged (zero delta) | Report "No structural changes detected since [baseline timestamp]." Still produce artifacts (empty diff). |
| Partial rescan failure (some repos error) | Skip errored repos, flag in diff-log.json, note in report: "N repos could not be rescanned — changes in those repos may be missed" |
| File comparison with mismatched orgs | Warn about overlap, diff only covers overlapping orgs |
| File comparison with mismatched modes | Skip crawl-specific changes with warning |

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
- Proceed past a crawl depth checkpoint without user confirmation
- Auto-follow ambiguous references — always present to user at checkpoint
- Mark non-crawled repos as stale when merging crawl results
- Modify the baseline topology during a diff run (it is read-only until synthesis produces a new topology)
- Skip causal attribution for rescan-based diffs (only skip for file-comparison mode)
- Run reverse search for full-scan diffs (reverse search is crawl-only)

## Red Flags

- Cloning inside subagents instead of the orchestrator
- Skipping the Tier 1 checkpoint before Tier 2
- Silently dropping unresolved references instead of flagging them
- Running synthesis before all analysis agents complete
- Exceeding 10 concurrent agents in any wave
- Proceeding past any user gate without confirmation
- Marking repos as stale during crawl mode merge (crawl is partial by design)
- Skipping user checkpoints between crawl depth levels
- Auto-resolving ambiguous references without user input
- Modifying the baseline topology before diff completes
- Skipping delta detection and re-analyzing all repos (defeats the smart rescan optimization)
- Running attribution on file-comparison diffs (no cloned repos available)
- Producing diff output without the visual Mermaid diagram

## Integration

- **Consults:** None (standalone initial scan)
- **Consumed by:** `crucible:build` (blast-radius extends across repos), `crucible:design` (cross-service impact analysis), `crucible:audit` (upstream/downstream neighbor scope)
- **Query mode consumers:** Other skills read `topology.json` from well-known persistence path (`~/.claude/memory/pathfinder/<org>/topology.json`)
- **Produces:** `~/.claude/memory/pathfinder/<org>/latest-diff.json` (diff mode, consumed by build/design/audit opportunistically)
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
| Reverse Searcher | Sonnet | Agent tool (general-purpose) | `./reverse-search-prompt.md` |
| Diff Analyzer | Sonnet | Task tool (general-purpose) | `./diff-analyzer-prompt.md` |

## Prompt Templates

- `./discovery-classifier-prompt.md` -- Phase 1 repo classification from metadata
- `./tier1-analyzer-prompt.md` -- Phase 2 Tier 1 manifest and config scanning
- `./tier2-analyzer-prompt.md` -- Phase 2 Tier 2 deep code scanning
- `./synthesis-prompt.md` -- Phase 3 cross-reference, edge resolution, cluster detection, output generation
- `./query-handler-prompt.md` -- Query mode graph traversal and blast-radius computation
- `./reverse-search-prompt.md` -- Crawl mode reverse search across orgs for fan-in dependencies
- `./diff-analyzer-prompt.md` -- Diff mode comparison of baseline vs current topology
