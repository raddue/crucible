# Pathfinder — Cross-Org Service Discovery & Dependency Mapping

**Date:** 2026-03-17
**Status:** Design approved
**Branch:** feat/pathfinder-skill
**Issue:** #39

## Overview

Pathfinder is a crucible skill that maps an entire GitHub organization's (or multiple orgs') service topology — what repos are services, how they talk to each other, and what infrastructure they share. It produces Mermaid diagrams, structured JSON, and a human-readable markdown report.

**Primary use case:** Point pathfinder at one or more GitHub orgs, get back a complete map of services and their dependencies. Feed the JSON into NotebookLM for prettier visualizations or deeper exploration.

## Architecture

### Three-Phase Execution

**Phase 1: Discovery** (no cloning)
- `gh repo list <org> --json` for each provided org
- Fetches metadata: name, description, language, topics, archived status, disk usage, push date
- Classifies each repo as: API / Worker / Frontend / Serverless / Library / Infrastructure / Tool / Unknown
- Presents summary to user for confirmation before proceeding
- **Pre-flight rate budget:** Before scanning, call `gh api rate_limit` and estimate API calls needed (repos / 30 pages + clone count). Warn user if budget is insufficient.

**Phase 2: Analysis** (parallel shallow clones)
- **Local-first resolution:** Check `../` (hardcoded default) for existing clones before shallow-cloning to `/tmp/pathfinder/<org>/<repo>/`. Configurable search paths are a future enhancement.
- **Orchestrator-managed cloning:** The orchestrator performs all cloning sequentially (or in controlled batches) before dispatching subagents. Each subagent receives a pre-existing path to analyze — subagents never clone.
- **Parallel analysis agents:** Dispatched via Agent tool (`subagent_type: Explore`, model: Sonnet). Max 10 concurrent agents. For orgs with 50+ repos, batch into waves of 10.
- **Two-tier detection with interactive checkpoint:**
  - **Tier 1 (automatic):** Manifest + config scanning — package deps, env vars, docker-compose, proto files, Dockerfiles, k8s manifests
  - **Tier 1 Checkpoint:** Present initial findings to user — "Found N services, M edges. Would you like me to run a deep code scan for additional edges?"
  - **Tier 2 (opt-in):** Deep code scanning — grep source for HTTP client calls, topic names, connection strings. Merges with Tier 1. Per-repo limits: max 200 source files scanned, max 50 grep matches retained. Prioritize recently modified files. Agents report at 50% context usage.
- **Per-repo results:** Each agent writes findings to `/tmp/pathfinder/<org>/repos/<repo-name>.json` immediately on completion.

**Phase 3: Synthesis** (single agent)
- Dispatched via Agent tool (`subagent_type: general-purpose`, model: Opus)
- Cross-references all per-repo findings
- Resolves dependency edges via producer→consumer matching
- Detects service clusters (algorithm defined below)
- Generates all output artifacts

### Multi-Org Support

Pathfinder accepts one or more org names. All orgs are enumerated and analyzed together. The dependency graph spans org boundaries — a service in one org calling a service in another org shows as a cross-org edge.

**Invocation:** `crucible:pathfinder <org1> [org2] [org3...]`

## Service Classification

Each repo is classified based on metadata and manifest signals:

| Type | Signals |
|------|---------|
| **API** | Dockerfile + framework detection (Express, FastAPI, Spring Boot, etc.) + port binding |
| **Worker** | Dockerfile + queue consumer patterns, no exposed HTTP ports |
| **Frontend** | React/Vue/Angular/Next.js, static hosting configs |
| **Serverless** | serverless.yml, SAM templates, Lambda handler patterns |
| **Library** | No Dockerfile, published to package registry, consumed by other repos |
| **Infrastructure** | Terraform, Pulumi, CloudFormation definitions |
| **Tool** | CLI utilities, scripts, dev tooling — not deployed as a running service |
| **Unknown** | Insufficient signals to classify confidently |

**Confidence scoring:** Each classification gets HIGH/MEDIUM/LOW confidence. LOW-confidence items are flagged in the report for human review.

**Exclusions:** Archived and empty repos excluded by default, listed in appendix.

## Edge Detection & Dependency Mapping

### Edge Types (in scan priority order)

| Priority | Edge Type | Detection Method | Default Confidence |
|----------|-----------|------------------|--------------------|
| 1 | Shared Package | Both repos import same internal org package (package.json, go.mod, requirements.txt) | HIGH |
| 2 | Event Stream | Kafka topic / RabbitMQ exchange / SQS queue — producer↔consumer matching | HIGH |
| 3 | gRPC | Shared .proto files or generated client stubs | HIGH |
| 4 | HTTP/REST (config) | Env var URLs (`AUTH_SERVICE_URL`), config files, API client configs | HIGH |
| 5 | Shared Database | Same DB name or connection string across services | HIGH |
| 6 | Shared Infrastructure | Same Redis host, Elasticsearch cluster, S3 bucket | MEDIUM |
| 7 | HTTP/REST (code) | Source-level HTTP calls with service hostnames (Tier 2 only) | MEDIUM |

### Edge Data Model

Each edge records:
- **Source** → **Target** (using qualified `org/repo` identifiers to avoid cross-org name collisions)
- **Type:** HTTP, Kafka, gRPC, shared-db, shared-package, infrastructure
- **Direction:** Unidirectional (calls/events) or bidirectional (shared resources)
- **Confidence:** HIGH / MEDIUM / LOW
- **Evidence:** File path, line, matched pattern that produced this edge
- **Label:** Topic name, endpoint path, package name — the specific identifier

**Edge identity:** Two edges are the same if they share the same `source + target + type + label`. On merge, confidence takes the max, evidence is unioned, direction is flagged if contradictory.

**Deduplication:** Multiple evidence points for the same logical edge merge into one edge with accumulated evidence. More evidence = higher confidence.

### Internal Package Detection

A package is considered "internal" (org-owned) if:
- Its scope matches an org name (e.g., `@acme-platform/shared-types` when scanning `acme-platform`)
- It is published by a repo within the scanned orgs (detected by checking if any scanned repo's name matches the package name)
- It uses `file:../` or `workspace:` references (local workspace dependency)

External packages (e.g., `express`, `lodash`) are ignored for edge detection.

### Env Var URL Matching

To match env var hostnames to repos:
1. **Exact match:** hostname equals a repo name (`auth-service` → repo `auth-service`)
2. **Prefix match:** hostname is a prefix of a repo name (`auth` → repo `auth-service`)
3. **Denylist:** Skip known infrastructure vars: `DATABASE_URL`, `REDIS_URL`, `CACHE_URL`, `MONGO_URI`, `ELASTICSEARCH_URL` — these map to shared-infrastructure edges, not service edges

Unresolvable references are flagged as "unresolved" in the report.

### Shared Database Limitation

Database connection strings are typically in secrets managers, not committed config. Detection is limited to cases where DB names appear in docker-compose files, config templates, `.env.example` files, or migration configs. Real production connection strings are unlikely to be in source.

### Detection Patterns

#### Tier 1: Manifest + Config (Automatic)

**Files scanned per repo:**
- `package.json`, `go.mod`, `requirements.txt`, `pyproject.toml`, `Cargo.toml`, `pom.xml`, `build.gradle`
- `*.env*`, `.env.example`, `docker-compose.yml`, `docker-compose*.yml`
- `**/*.proto`
- `Dockerfile`, `k8s/**/*.yaml`, `helm/**/*.yaml`
- `serverless.yml`, `template.yaml` (SAM)
- `openapi.yaml`, `swagger.json`

**Matching logic:**
- Internal package imports → search for repos publishing that package
- Env var URLs → extract hostname, match to repo names (see matching rules above)
- Proto imports → match to repos containing the referenced .proto
- Docker-compose service references → match to repo service definitions
- Kafka/RabbitMQ/SQS topic/queue names → match producers to consumers across repos

#### Tier 2: Deep Code Scan (Opt-in)

**Additional files scanned:**
- `src/**/*.{ts,js,py,go,java,rb,cs}` — source files
- Focus on: HTTP client instantiation, queue producer/consumer calls, gRPC channel creation
- **Per-repo limits:** Max 200 source files (prioritize by recency), max 50 grep matches retained

**Grep patterns by edge type:**
- HTTP clients: `requests.get`, `fetch(`, `axios.`, `http.Get`, `HttpClient`
- Kafka: `producer.send`, `consumer.subscribe`, topic name strings
- gRPC: `NewServiceClient(`, `ServiceStub(`, `grpc.secure_channel`
- Redis: `redis.StrictRedis`, `RedisClient`, `ioredis`
- Elasticsearch: `Elasticsearch(`, `ElasticsearchClient`
- S3: `s3.get_object`, `s3.putObject`, bucket name strings

**False positive mitigation:**
- Exclude `**/test/**`, `**/spec/**`, `**/mock/**`, `**/__tests__/**`
- Exclude commented-out lines
- Rank by frequency (single reference = lower confidence than 10+ references)

## Monorepo Handling

**Detection signals:**
- Workspace configs: npm `workspaces`, `go.work`, Cargo.toml `[workspace]`, Bazel `WORKSPACE`
- Multiple Dockerfiles in subdirectories
- Multiple independent CI/CD pipelines per subdirectory

**Sub-service enumeration:** Each directory containing a Dockerfile (or listed as a workspace member) is treated as a separate service node.

**Naming convention:** Sub-services are named `<repo>/<subdir>` (e.g., `platform/services/auth`) to avoid collisions with standalone repos.

**Treatment:**
- Each service within a monorepo becomes its own node in the graph
- Repo name used as grouping label (Mermaid `subgraph`)
- Internal edges within monorepo tracked but visually distinguished from cross-repo edges

## Output Artifacts

All output written to the current working directory at `docs/pathfinder/<org-name>/` (single org) or `docs/pathfinder/<combined-name>/` (multi-org, where `<combined-name>` is alpha-sorted org names joined by `+`, e.g., `acme-infra+acme-platform`).

### 1. `topology.json` — Source of Truth

```json
{
  "meta": {
    "orgs": ["acme-platform", "acme-infrastructure"],
    "scan_timestamp": "2026-03-17T14:30:00Z",
    "tier_depth": 1,
    "repo_count": 47,
    "service_count": 28,
    "edge_count": 41,
    "service_coverage": { "high": 22, "medium": 5, "low": 1 },
    "edge_coverage": { "high": 34, "medium": 7, "low": 0 }
  },
  "services": [
    {
      "name": "acme-platform/orders-api",
      "repo": "acme-platform/orders-api",
      "org": "acme-platform",
      "type": "API",
      "language": "TypeScript",
      "framework": "Express",
      "confidence": "HIGH",
      "status": "active",
      "metadata": { "topics": ["orders"], "last_push": "2026-03-15" }
    }
  ],
  "edges": [
    {
      "source": "acme-platform/orders-api",
      "target": "acme-platform/payments-service",
      "type": "HTTP",
      "direction": "unidirectional",
      "confidence": "HIGH",
      "label": "PAYMENTS_SERVICE_URL",
      "evidence": [
        { "file": ".env.example", "line": 12, "match": "PAYMENTS_SERVICE_URL=http://payments:8080" }
      ]
    }
  ],
  "clusters": [
    {
      "name": "orders-cluster",
      "services": ["acme-platform/orders-api", "acme-platform/orders-worker", "acme-platform/orders-common"],
      "description": "Core order processing pipeline"
    }
  ]
}
```

### 2. `topology.mermaid.md` — Full Org Graph

Full overview with all services and edges. Nodes shaped by type, edges labeled by communication type. Monorepo services grouped in subgraphs. Line style indicates confidence (solid = HIGH, dashed = MEDIUM, dotted = LOW).

**For orgs with 30+ services:** The full graph renders at cluster level (one node per cluster, edges between clusters with multiplicity). Per-cluster diagrams provide service-level detail.

### 3. `clusters/` — Per-Cluster Sub-Diagrams

One Mermaid file per detected cluster (e.g., `clusters/orders-cluster.mermaid.md`). Focused view of tightly-coupled service groups with their internal and external edges.

### 4. `report.md` — Human-Readable Summary

- Service inventory table (name, type, language, org, confidence)
- Dependency matrix
- Cluster descriptions with embedded Mermaid diagrams (both full and cluster views)
- Flagged items: LOW-confidence classifications, unresolved edges, scan errors
- Recommendations for further investigation

### 5. `scan-log.json` — Scan Metadata

Per-repo timing, errors, skipped repos, rate limit usage. Supports incremental re-runs.

## Execution Flow

1. **Pre-flight** — Verify `gh auth`, check rate limit budget via `gh api rate_limit`, confirm org access for each provided org. Estimate API budget needed (repo count / page size + clone count). Stop early with clear message if issues.

2. **Discovery** — Enumerate all repos across all provided orgs. Present summary:
   > "Found 147 repos across 2 orgs. 68 look like services, 22 libraries, 12 infrastructure, 45 unknown. 8 archived (excluded). Proceed?"

3. **Local Resolution** — Check `../` for existing clones matching repo names. Report:
   > "Found 23 repos locally. Will shallow-clone the remaining 45 to /tmp/pathfinder/."

4. **Orchestrator Cloning** — Clone repos sequentially to `/tmp/pathfinder/<org>/<repo>/` using `gh repo clone <org>/<repo> -- --depth=1`. Write progress to state file.

5. **Tier 1 Analysis** — Dispatch analysis agents in waves of max 10. Each agent receives a pre-cloned repo path. Per-repo findings written to `/tmp/pathfinder/<org>/repos/<repo-name>.json`. Status updates as agents complete.

6. **Tier 1 Checkpoint** — Present initial map:
   > "Tier 1 complete. Found 68 services, 94 edges (79 HIGH, 15 MEDIUM). Here's the overview. Would you like me to run a deep code scan for additional edges?"

7. **Tier 2 Analysis** (if opted in) — Dispatch analysis agents in waves of max 10 for deep code scan. Merge with Tier 1 findings.

8. **Synthesis** — Dispatch Opus agent. Cross-reference findings, resolve edges, detect clusters, generate all artifacts.

9. **Report** — Present results, commit to `docs/pathfinder/<org-name>/`.

## Cluster Detection Algorithm

Services are grouped into clusters using the following algorithm:

1. **Monorepo clusters:** Services within the same monorepo always form a cluster, named after the repo.
2. **Affinity clusters:** Services that share 2+ edges of any type form a candidate cluster. Use connected components on the subgraph of services with 2+ shared edges.
3. **Naming:** Clusters are named after their most-connected service or shared resource (e.g., "orders-cluster" if `orders-api` has the most edges).
4. **Singletons:** Services with no cluster affinity appear as standalone nodes.

Clusters are always recomputed from scratch on the full edge set (not incrementally).

## Query Mode — Blast Radius Oracle

After an initial scan, pathfinder's topology becomes a persistent, queryable data source. Other crucible skills (or the user directly) can interrogate the graph without re-scanning.

### Storage

`topology.json` is persisted to `~/.claude/memory/pathfinder/<org-name>/topology.json` (well-known absolute path, outside the project-hash system). For multi-org scans, stored under the combined name (e.g., `~/.claude/memory/pathfinder/acme-infra+acme-platform/topology.json`). This allows any crucible session in any repo to access the topology regardless of working directory.

### Query Types

| Query | Description | Example |
|-------|-------------|---------|
| `upstream <service>` | Who calls this service? (consumers) | "What services depend on auth-api?" |
| `downstream <service>` | What does this service call? (dependencies) | "What does orders-api talk to?" |
| `blast-radius <service>` | If this service changes, what breaks? (transitive, with cycle detection) | "What's the blast radius of changing payments-service?" |
| `shared-infra <resource>` | Which services share this resource? | "Who else uses the shared-redis instance?" |
| `path <service-A> <service-B>` | How do these services communicate? (direct or transitive) | "How does the frontend reach the billing service?" |

**Cycle detection:** Blast-radius and path queries use BFS with a visited set. Cycles are detected and reported: "Circular dependency detected: A -> B -> A."

### Integration with Other Skills

Query mode is RECOMMENDED (not required) — skills check for pathfinder data and use it if available, gracefully degrade if not.

- **crucible:build** — Phase 1 blast radius analysis extends across repos when pathfinder data exists. "This API change also affects 3 services in other repos: [list]."
- **crucible:design** — Investigation agents consult pathfinder to understand cross-service impact before asking the user.
- **crucible:audit** — Subsystem audit scope can include immediate upstream/downstream neighbors, catching contract violations at service boundaries.

### Invocation

- **Automatic:** Other skills read `topology.json` from the well-known path when they need cross-repo context.
- **Explicit:** User invokes `crucible:pathfinder query upstream auth-api` for direct queries. Returns structured results with service names, edge types, and confidence.

### Cold Start

If no topology.json exists, query mode returns empty results and suggests running a full scan. No errors, no blocking — graceful degradation.

## Persistence & Incremental Runs

- Each scan writes results to both `docs/pathfinder/<org>/` (committed artifacts) and `~/.claude/memory/pathfinder/<org>/` (queryable store)
- Subsequent runs merge with existing data:
  - **New repos:** Added with `status: "active"`
  - **Removed repos:** `status` set to `"stale"`, kept in topology for one more run, then removed
  - **Existing repos:** Classification and edges updated; confidence takes max of old/new
  - **Edge merge:** Edges matched by `source + target + type + label`. Confidence: take max. Evidence: union. Direction: flag if contradictory.
  - **Clusters:** Always recomputed from scratch on the merged edge set
- Mermaid diagrams regenerate from merged JSON
- Separate orgs (or org combinations) maintain separate output directories

## Compaction Recovery

Pathfinder's Phase 2 with many parallel agents is compaction-prone. State persistence:

1. **State file:** `/tmp/pathfinder-state.json` — written by orchestrator, updated after each repo completes:
   ```json
   {
     "orgs": ["acme-platform"],
     "phase": "analysis-tier1",
     "repos_total": 45,
     "repos_completed": ["orders-api", "auth-service", "..."],
     "repos_remaining": ["payments-service", "..."],
     "clone_paths": { "orders-api": "/tmp/pathfinder/acme-platform/orders-api/" }
   }
   ```
2. **Per-repo results:** Already written to `/tmp/pathfinder/<org>/repos/<repo-name>.json` on completion — these survive compaction.
3. **On compaction:** Read state file first. Skip completed repos. Resume from remaining list.

## Estimated Runtime

| Org Size | Repos | Estimated Time |
|----------|-------|----------------|
| Small | <20 services | ~10-15 min |
| Medium | 20-50 services | ~20-30 min |
| Large | 100+ services | May need multiple sessions with incremental merging |

## Acceptance Criteria

1. Given one or more GitHub org names, pathfinder enumerates all repos and classifies each by type
2. Given repos with known inter-service dependencies, pathfinder detects edges with correct type and direction
3. Given a monorepo with multiple services, pathfinder identifies each service as a separate node with `<repo>/<subdir>` naming
4. Output Mermaid renders correctly and matches the JSON topology data
5. Local repos are detected and used instead of cloning when available
6. Tier 1 completes and presents checkpoint before offering Tier 2
7. Incremental re-runs merge with existing data (edge identity: source+target+type+label)
8. Multi-org scanning produces a unified graph spanning org boundaries with qualified service names
9. Query mode returns correct upstream/downstream/blast-radius results from persisted topology
10. Query mode gracefully returns empty results when no topology data exists
11. Blast-radius queries detect and report cycles

## Error Handling

- `gh auth` failure → stop with clear message
- Rate limit hit → pause, report remaining budget, offer to continue with reduced parallelism
- Rate budget insufficient at pre-flight → warn user with estimate before starting
- Clone failure (single repo) → skip, log to scan-log.json, continue with remaining repos
- Unresolvable edge references → flag in report as "unresolved", don't silently drop
- Large repos (>1GB disk usage) → manifest-only scan, skip clone
- Org membership limitations → warn that only visible repos are scanned (private repos require org membership)
- Service name collision across orgs → prevented by qualified `org/repo` identifiers

## Future Enhancements

- **Crawl mode** (issue #40): Seed-based discovery — start from one repo, fan out by tracing dependencies. Useful for exploring a specific service's neighborhood without scanning entire orgs.
- **Contract sync verification** (issue #41): Extract API contracts on both sides of every edge (proto, OpenAPI, GraphQL schemas) and detect mismatches — version skew, phantom dependencies, schema drift.
- **Configurable search paths:** Allow users to specify custom local clone directories via `.pathfinder.yml` or CLI flags.
- **Figma API integration:** Push topology data to Figma for visual editing and annotation.
- **Live dashboard:** Watch mode that re-scans periodically and diffs against previous topology.
- **Dependency health scoring:** Flag stale dependencies, unused edges, orphaned services.
