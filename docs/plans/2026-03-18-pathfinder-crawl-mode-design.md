# Pathfinder Crawl Mode — Seed-Based Bidirectional Dependency Discovery

**Date:** 2026-03-18
**Status:** Design approved, quality-gated
**Branch:** feat/pathfinder-skill
**Issue:** #40

## Overview

Adds a third mode to the pathfinder skill — **crawl mode** — which starts from a seed repo and discovers connected services by tracing dependencies bidirectionally. Unlike full scan mode (which enumerates an entire org top-down), crawl mode follows dependency threads from a known starting point.

**Primary use case:** Large orgs (100+ repos) where full enumeration is impractical. Start from one service you know, discover what's connected.

**Invocation:**
```
crucible:pathfinder crawl <org>/<repo> [--depth N] [--orgs org1,org2]
```

- `<org>/<repo>` — the seed repo to start from
- `--depth N` — max hop count from seed (default: 3, max: 10)
- `--orgs org1,org2` — which orgs to search for reverse references (required for fan-in). If omitted, uses only the seed repo's org — with an explicit notice at pre-flight (see below).

## Bidirectional Crawl

The key innovation over a naive forward-only crawl. Each discovered repo gets two types of analysis:

1. **Fan-out (forward):** Analyze the repo's manifests/code to find what it calls — same as existing Tier 1/Tier 2 analysis
2. **Fan-in (reverse):** Search across specified orgs for repos that reference *this* repo — solves the unidirectional dependency blind spot where only the caller knows about a connection

**Why bidirectional:** If Service A calls Service B, but Service B has no reference back to Service A, a forward-only crawl seeded from Service B would never discover Service A. Fan-in fixes this by searching the org for references TO each discovered repo.

## Execution Flow

Crawl mode uses **named phases** (not numbered) to avoid confusion with full scan's Phase 1-4:

- **Pre-flight** → **Seed** → **Crawl** → **Tier 2 (opt-in)** → **Synthesis** → **Report**

### Pre-flight

- Same as full scan: `gh auth status`, rate limit check, org access verification for seed org + all `--orgs`
- Verify seed repo exists: `gh repo view <org>/<repo>`
- **Code search availability check:** For each org in `--orgs`, test code search with `gh api search/code -f q="test org:<org>" --jq '.total_count'`. If 403/422, warn: "Code search unavailable for `<org>`. Reverse search will not cover this org." Offer to continue with forward-only crawl for that org.
- **Single-org notice:** If `--orgs` is omitted, display: "Reverse search will only cover the `<seed-org>` org. To discover cross-org callers, add `--orgs org1,org2`. Continue with single-org reverse search?"
- **Reverse search time estimate:** Based on org repo count and estimated signals per repo, display: "Estimated reverse search: ~N API calls across M orgs. At GitHub's code search rate (10 req/min), this may take ~X minutes."
- Initialize state file at `/tmp/pathfinder-state.json` with `"mode": "crawl"` (shared state file with mode discriminator — see State Management below)

### Seed

- Clone seed repo (or use local if found in `../`) following full scan cloning rules:
  - Check `../` for existing clone first (local resolution)
  - Large repos (>1GB disk usage): manifest-only scan, skip clone
  - Clone to `/tmp/pathfinder/<org>/<repo>/` via `gh repo clone <org>/<repo> -- --depth=1`
- Run full Tier 1 analysis on seed (reuse existing `tier1-analyzer-prompt.md`)
- Tier 1 analyzer outputs both standard edge data AND **identity signals** (see Agent Dispatch below)
- Extract all outbound references (forward edges) and identity signals from Tier 1 output
- **Seed with no manifests fallback:** If Tier 1 returns zero outbound edges and no identity signals beyond the repo name, inform the user: "Seed repo has no detectable dependencies or identity signals beyond its name. Reverse search will use repo name only. Results may be limited." Still proceed with repo-name-only reverse search.
- Present seed findings to user: "Seed repo is a TypeScript API service. Found 5 outbound references and 3 identity signals. Proceeding to discover neighbors."

### Crawl (Iterative Discovery)

```
frontier = [seed_repo]
discovered = {}
depth = 0

while frontier is not empty AND depth < max_depth:
    next_frontier = []
    for each repo in frontier:
        # Forward: what does this repo call?
        forward_refs = analyze_outbound(repo)  # Tier 1 analysis (reused)

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
- **Reverse search happens inline** during each crawl iteration (not as a separate phase) — the "Reverse Search Implementation" section below documents the mechanics
- State file updated after each repo completes (compaction-safe)
- Clones persist across depth levels — `clone_paths` in state file prevents re-cloning

### Cloning

Crawl mode inherits all full scan cloning rules:
- **Local resolution:** Check `../` for existing clones matching repo names before cloning
- **Large repos (>1GB):** Skip clone, manifest-only scan. Inform user.
- **Clone path:** `/tmp/pathfinder/<org>/<repo>/` — same convention as full scan
- **Clone persistence:** Clones are NOT cleaned up between depth levels. The `clone_paths` map in the state file tracks all cloned repos. When a repo appears in the frontier that's already in `clone_paths`, skip cloning.
- **Clone failure:** Skip repo, log error, continue with remaining repos. Report to user.

### Frontier Prioritization (Adaptive Depth)

Instead of treating all frontier repos equally, each candidate is scored by structural importance:

**Scoring function (orchestrator logic, no additional API calls):**
- **Signal density:** How many distinct identity signals from already-analyzed repos point to this candidate? (1 signal = 1pt, 2-3 = 3pts, 4+ = 5pts)
- **Signal diversity:** Was it discovered via multiple independent signal types? (e.g., both package import AND env var = bonus 2pts, single signal type = 0pts)
- **Cross-cluster bridging:** Do the candidate's referrers span different already-identified clusters? (bridges between clusters are architecturally important = bonus 3pts)

**Score ranges:** Minimum 1pt (single weak signal), maximum 10pts (high density + diverse signals + cross-cluster bridge).

**LOW_THRESHOLD = 2** — A repo scoring 2 or below was discovered by a single signal with no diversity or bridging bonus. This is the adaptive termination boundary.

**Score usage:**
- Frontier sorted by score — high-importance repos analyzed first within each wave
- Adaptive depth termination: if the highest-scored candidate in a wave falls below LOW_THRESHOLD (2), the crawl recommends early termination at the user checkpoint
- Synthesis agent uses scores to weight cluster detection, rank services in report, and size Mermaid nodes
- Score breakdown logged in state file and visible at checkpoints for transparency

**Adaptive termination is always a recommendation, never automatic.** The user can override at the checkpoint and continue crawling.

### Reverse Search Implementation

Reverse search happens inline during each crawl loop iteration. For each discovered repo, the orchestrator dispatches a Reverse Searcher agent to search across all `--orgs` for references:

```bash
# For each identity signal, search org repos via GitHub code search
gh api search/code -X GET -f q="<signal> org:<org>" --paginate
```

**Identity signals searched for:**
1. **Repo name** — env vars containing the name (e.g., `AUTH_SERVICE_URL`, `auth-service`)
2. **Package name** — import statements (`@org/package-name`, `org/module`)
3. **Proto service name** — `import "proto/service.proto"` references
4. **Docker image name** — `image: org/repo-name` in docker-compose, k8s manifests
5. **Kafka topics produced** — consumer references in other repos
6. **API base paths** — if OpenAPI spec defines `/api/v1/payments`, search for that path string

**Rate limit budget — realistic estimate:**

GitHub code search rate limit: 10 requests/minute (REST API, authenticated). Each identity signal requires one search per org.

Typical repo signal count: 1 repo name + 1-2 package names + 0-1 proto services + 1 Docker image + 0-2 Kafka topics + 0-1 API paths = **3-7 signals**. With 2 orgs = **6-14 searches per repo**.

**Progressive search strategy:** To manage rate budget:
1. **Always search:** Repo name, package names, Docker image names (HIGH-confidence signals)
2. **Search if budget allows:** Proto services, Kafka topics (MEDIUM-confidence)
3. **Search only on user opt-in:** API base paths, code-level string patterns (LOW-confidence, high noise)

**Budget per repo: 15 searches** (realistic for 2-3 orgs with progressive strategy). For a crawl discovering 30 repos, that's ~450 searches = ~45 minutes of reverse search time. This is reported at pre-flight.

**Compound queries:** Where possible, batch signals: `gh api search/code -f q="payments-service OR @acme/payments-client org:acme"`. GitHub supports OR queries with a max query length of ~256 chars. Batch 2-3 short signals per query to reduce call count by ~40%.

### Tier 2 Deep Scan (Opt-in)

Tier 2 deep code scanning is offered **after all crawl depth levels complete and before synthesis**:

> "Crawl complete. Discovered 23 repos across 3 depth levels with 41 edges. Would you like to run a deep code scan on all/selected repos for additional edges?"

User options:
- **All repos** — Tier 2 on every discovered repo
- **Selected repos** — user specifies which repos (useful for focusing on high-importance nodes)
- **Skip** — proceed to synthesis with Tier 1 findings only

This matches the full scan checkpoint model but avoids prompting at every depth level.

### Synthesis

Dispatch Opus synthesis agent using `./synthesis-prompt.md` with **crawl-specific augmentation**:

**Standard inputs (same as full scan):**
- Paths to all per-repo JSON result files
- Tier depth (1 or 2)
- Output directory path
- Persistence path
- Existing topology.json contents (if incremental run)

**Crawl-specific additions passed to synthesis agent:**
- `"mode": "crawl"` flag so the agent knows to produce crawl-specific output
- `"seed": "<org>/<repo>"` — the starting point
- `"crawl_metadata"` — a map of `repo → {depth, found_via, importance, signal_sources}` extracted from the state file's `discovered` map
- Instructions to produce a **discovery path** section in `report.md` showing how each repo was found (which signal, at what depth, forward or reverse)
- Instructions to use `importance` scores for cluster weighting and Mermaid node sizing

**Per-repo JSON augmentation:** Before dispatching synthesis, the orchestrator annotates each per-repo JSON file with crawl metadata:
```json
{
  "crawl": {
    "depth": 1,
    "found_via": "forward:env_var:PAYMENTS_SERVICE_URL",
    "importance": 7,
    "signal_sources": [{"type": "env_var", "source_repo": "acme/funding-api"}]
  },
  ...existing per-repo fields...
}
```

This keeps the Tier 1 analyzer unchanged — crawl metadata is added by the orchestrator after analysis.

### Report

Same as full scan Phase 4, plus crawl-specific additions:
- **Discovery path visualization** — tree showing seed → depth 1 repos → depth 2 repos with discovery signals
- **Importance heatmap** — repos colored by importance score in the Mermaid diagram
- **Reverse search coverage** — which orgs were searched, which had code search available, how many signals were searched

## Reference Resolution

Layered confidence strategy for mapping references to actual repos:

| Strategy | Confidence | Example |
|----------|-----------|---------|
| **Exact package match** | HIGH | `go.mod` imports `github.com/acme/auth-client` → repo `acme/auth-client` |
| **Docker image match** | HIGH | `image: acme/payments-service` → repo `acme/payments-service` |
| **Proto import match** | HIGH | `import "acme/payments/v1/payments.proto"` → repo containing that proto |
| **Env var hostname = repo name** | MEDIUM | `PAYMENTS_SERVICE_URL=http://payments-service:8080` → repo `payments-service` |
| **Env var hostname prefix** | LOW | `PAYMENTS_URL=http://payments:8080` → maybe repo `payments-service`? |
| **Code search string match** | LOW | `fetch("/api/v1/orders")` found in 3 repos → maybe `orders-api`? |

### Ambiguous Resolution — Interactive Fallback

When a reference can't be auto-resolved or has LOW confidence, queue it for user input:

```
Unresolved references (3):
  1. NOTIFICATION_URL=http://notify:3000  — no repo named "notify" or "notification*" found
     → [skip] [enter repo name] [search orgs]
  2. import "@acme/shared-utils" — matches 2 repos: acme/shared-utils, acme/shared-utilities
     → [pick one] [skip]
  3. consumer.subscribe("user-events") — topic produced by unknown repo
     → [skip] [enter repo name]
```

Batched at the end of each depth level and presented together at the checkpoint.

**Resolution persistence:** User decisions are stored in the state file's `unresolved` array with a `resolution` field (see State Management). This survives compaction — already-resolved ambiguities are not re-presented.

### Cross-Org Resolution

When `--orgs` includes multiple orgs, resolution searches all of them. A reference to `payments-service` checks `org1/payments-service`, `org2/payments-service`, etc. If found in exactly one org, auto-resolve. If found in multiple, add to the ambiguous queue.

### False Positive Mitigation for Reverse Search

- Exclude archived repos
- Exclude the repo being searched *for* (self-references)
- Exclude test/mock/example directories
- Require 2+ distinct references in a repo to count as a real edge (single mention = LOW confidence, noted but not auto-followed)
- Exclude well-known external service names (e.g., a repo named `redis` shouldn't match every Redis client config)

## State Management & Compaction Recovery

### Unified State File

Crawl mode uses the **same state file path** as full scan: `/tmp/pathfinder-state.json`. A `"mode"` field discriminates between schemas.

**Crawl mode schema:**

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
    "acme/payments-service": { "depth": 1, "found_via": "forward:env_var:PAYMENTS_SERVICE_URL", "status": "analyzed", "importance": 8, "signal_sources": [{"type": "env_var", "source_repo": "acme/funding-api"}] },
    "acme/billing-worker": { "depth": 1, "found_via": "reverse:code_search:funding-api", "status": "pending", "importance": 7, "signal_sources": [{"type": "code_search", "source_repo": "acme/funding-api"}, {"type": "env_var", "source_repo": "acme/payments-service"}] }
  },
  "frontier": ["acme/billing-worker"],
  "unresolved": [
    { "signal": "NOTIFICATION_URL=http://notify:3000", "source_repo": "acme/payments-service", "type": "env_var", "resolution": "pending" }
  ],
  "clone_paths": { "acme/funding-api": "../funding-api", "acme/payments-service": "/tmp/pathfinder/acme/payments-service/" },
  "edges_found": 12
}
```

**Full scan schema** retains its existing structure with `"mode": "full-scan"` added.

### Compaction Recovery

The orchestrator's compaction recovery logic reads `/tmp/pathfinder-state.json` and branches on the `mode` field:

1. **Read state file** → check `mode`
2. **If `mode: "crawl"`:**
   - Read `current_phase` to determine where to resume (seed, crawl, tier2, synthesis)
   - Read `current_depth` and `frontier` to determine crawl progress
   - Skip repos with `status: "analyzed"` — resume from `status: "pending"` repos
   - Re-present only `unresolved` entries with `"resolution": "pending"` (don't re-ask resolved ones)
   - Per-repo JSON results on disk survive compaction
   - Status update: "Recovered from compaction. Crawl depth 2: 6/9 repos analyzed. Resuming."
3. **If `mode: "full-scan"`:** Existing recovery logic (unchanged)
4. **If both modes' data exists** (shouldn't happen — one run at a time): Warn user, ask which to resume.

### Merge with Existing Topology

If pathfinder data already exists for these orgs (from a prior full scan or crawl), the crawl results merge with **crawl-aware rules**:

- **Edge identity matching:** Same as full scan — `source + target + type + label`. Confidence takes max, evidence unions.
- **No stale-marking for crawl merges:** Crawl results are intentionally partial (only discovered repos). Repos absent from the crawl are NOT marked stale. Stale-marking only applies when `mode: "full-scan"` (which is comprehensive).
- **Crawl provenance preserved:** Merged topology.json gains a `crawl_metadata` section with discovery paths. This coexists with full scan data.
- **Reverse-search edges:** These are new edge types that full scan doesn't produce. They merge normally — if full scan later confirms the same edge via forward analysis, evidence unions and confidence takes max.

### Output Directories & Persistence

**Output directory:**
- Single-org crawl: `docs/pathfinder/<org-name>/crawl-<seed-repo>/`
- Multi-org crawl (with `--orgs`): `docs/pathfinder/<combined-orgs>/crawl-<seed-repo>/` where `<combined-orgs>` follows the full scan convention (alpha-sorted, `+`-joined)

Example: `crucible:pathfinder crawl acme/funding-api --orgs acme,acme-infra` → `docs/pathfinder/acme+acme-infra/crawl-funding-api/`

**Persistence path (for query mode):**
- Single-org: `~/.claude/memory/pathfinder/<org-name>/topology.json`
- Multi-org: `~/.claude/memory/pathfinder/<combined-orgs>/topology.json`

Crawl results are **merged into** the same persistence path as full scan results. Query mode sees a unified topology regardless of whether data came from full scan, crawl, or both. The `crawl_metadata` section in topology.json is additive — it doesn't conflict with full scan data.

## Integration with Existing Skill

### Changes to SKILL.md

1. **"Two modes" → "Three modes"** with crawl listed
2. **New invocation line:** `crucible:pathfinder crawl <org>/<repo> [--depth N] [--orgs org1,org2]`
3. **New "Crawl Mode" section** after Phase 4 (Report) and before Query Mode
4. **New prompt template:** `./reverse-search-prompt.md`
5. **Modified prompt template:** `./tier1-analyzer-prompt.md` gains an `identity_signals` output field
6. **New agent dispatch entry:**

| Agent | Model | Dispatch | Prompt Template |
|-------|-------|----------|-----------------|
| Reverse Searcher | Sonnet | Agent tool (general-purpose) | `./reverse-search-prompt.md` |

7. **Tier 1 Analyzer extended** — no separate Identity Extractor agent needed. The Tier 1 analyzer already scans manifests for package names, proto definitions, Kafka topics, and Docker images. Adding an `identity_signals` output field to its prompt captures this data without a second agent dispatch per repo.
8. **State file section** updated to document the `"mode"` field discriminator and crawl-specific schema
9. **Compaction recovery** updated to branch on `mode` field
10. **Synthesis prompt** gains a crawl-mode augmentation section (orchestrator appends crawl metadata when dispatching)
11. **Communication Requirement examples** updated with crawl-specific narration:

> "Crawl (Seed): Seed analysis complete — TypeScript API, 5 outbound refs, 3 identity signals. Dispatching reverse search + depth 1 forward analysis."

> "Crawl (Depth 2): Wave complete — discovered 8 new repos (total: 14), 31 edges. Top-scored: acme/event-bus (importance: 9). Presenting checkpoint."

### What Stays the Same

- All existing edge detection patterns, confidence scoring, and false positive mitigation
- Tier 1/Tier 2 analysis agents and their prompts (Tier 1 gains one output field)
- Synthesis agent and output artifact format (topology.json, Mermaid, report.md) — augmented, not replaced
- Query mode — works on crawl-produced topology.json identically
- Monorepo handling
- Error handling table (extended, not replaced)
- All guardrails and red flags

## Acceptance Criteria

12. Given a seed repo with known dependencies, crawl mode discovers connected repos via forward fan-out
13. Given a seed repo that is called by other repos, crawl mode discovers callers via reverse search
14. Crawl respects depth limits and stops when no new repos are found
15. User checkpoint after each depth level with option to stop, exclude repos, or continue
16. Ambiguous references are batched and presented to user at checkpoints, not silently dropped or guessed
17. Crawl results merge with existing topology data using standard edge identity rules, without marking non-crawled repos as stale
18. Crawl state survives compaction and resumes correctly, including user resolution decisions
19. Given a crawl wave with multiple discovered repos, repos with higher importance scores are analyzed before lower-scored repos
20. Given a crawl wave where all candidates score below LOW_THRESHOLD (2), the system recommends termination rather than silently continuing
21. When `--orgs` is omitted, the system displays an explicit notice about single-org reverse search limitation
22. Tier 2 deep scan is offered after all crawl depth levels complete, before synthesis

(Numbered 12-22 continuing from the existing 11 acceptance criteria in the v1 design)

## Error Handling (Additions)

| Error | Response |
|-------|----------|
| Seed repo not found | Stop with clear message: "Seed repo `<org>/<repo>` not found or inaccessible." |
| Seed repo has no manifests | Warn user, proceed with repo-name-only reverse search |
| Code search rate limit hit | Pause reverse search, present partial results, offer to continue with forward-only crawl |
| Code search unavailable (403/422) | Warn: "Code search unavailable for `<org>`. Reverse search will not cover this org." Offer forward-only crawl for that org. |
| Code search returns 1000+ results for a signal | Signal is too generic — skip it, log as "too broad", continue with other signals |
| No new repos discovered at a depth level | Natural termination — proceed to synthesis with what's been found |
| All references at a depth level are ambiguous | Present full unresolved list to user, don't auto-follow any |

## Future Enhancements

- **Crawl + full scan merge:** Run crawl first for focused discovery, then full scan to fill gaps. Merge automatically.
- **Watched crawl:** Re-run crawl periodically, diff against previous topology, alert on new connections.
- **Crawl from multiple seeds:** `crucible:pathfinder crawl org/repo1 org/repo2` — two starting points, discover the bridge between them.
