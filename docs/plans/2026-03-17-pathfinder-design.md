# Pathfinder — Cross-Org Service Discovery & Dependency Mapping

**Date:** 2026-03-17
**Status:** Design approved
**Branch:** feat/repo-hopper-skill
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

**Phase 2: Analysis** (parallel shallow clones)
- **Local-first resolution:** Check configurable search paths (default `../`) for existing clones before shallow-cloning to `/tmp/pathfinder/<org>/`
- **Parallel agents:** One per repo, scanning manifest + config files
- **Two-tier detection with interactive checkpoint:**
  - **Tier 1 (automatic):** Manifest + config scanning — package deps, env vars, docker-compose, proto files, Dockerfiles, k8s manifests
  - **Tier 1 Checkpoint:** Present initial findings to user — "Found N services, M edges. Would you like me to run a deep code scan for additional edges?"
  - **Tier 2 (opt-in):** Deep code scanning — grep source for HTTP client calls, topic names, connection strings. Merges with Tier 1.

**Phase 3: Synthesis** (single agent)
- Cross-references all per-repo findings
- Resolves dependency edges via producer→consumer matching
- Detects service clusters (by shared infrastructure, communication patterns, monorepo membership)
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
- **Source** → **Target** (repo or shared resource)
- **Type:** HTTP, Kafka, gRPC, shared-db, shared-package, infrastructure
- **Direction:** Unidirectional (calls/events) or bidirectional (shared resources)
- **Confidence:** HIGH / MEDIUM / LOW
- **Evidence:** File path, line, matched pattern that produced this edge
- **Label:** Topic name, endpoint path, package name — the specific identifier

**Deduplication:** Multiple evidence points for the same logical edge merge into one edge with accumulated evidence. More evidence = higher confidence.

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
- Env var URLs → extract hostname, match to repo names
- Proto imports → match to repos containing the referenced .proto
- Docker-compose service references → match to repo service definitions
- Kafka/RabbitMQ/SQS topic/queue names → match producers to consumers across repos

#### Tier 2: Deep Code Scan (Opt-in)

**Additional files scanned:**
- `src/**/*.{ts,js,py,go,java,rb,cs}` — source files
- Focus on: HTTP client instantiation, queue producer/consumer calls, gRPC channel creation

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

**Treatment:**
- Each service within a monorepo becomes its own node in the graph
- Repo name used as grouping label (Mermaid `subgraph`)
- Internal edges within monorepo tracked but visually distinguished from cross-repo edges

## Output Artifacts

All output written to `docs/pathfinder/<org-name>/` (or `docs/pathfinder/<combined-name>/` for multi-org).

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
    "coverage": { "high_confidence": 34, "medium": 7, "low": 0 }
  },
  "services": [
    {
      "name": "orders-api",
      "repo": "acme-platform/orders-api",
      "org": "acme-platform",
      "type": "API",
      "language": "TypeScript",
      "framework": "Express",
      "confidence": "HIGH",
      "metadata": { "topics": ["orders"], "last_push": "2026-03-15" }
    }
  ],
  "edges": [
    {
      "source": "orders-api",
      "target": "payments-service",
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
      "services": ["orders-api", "orders-worker", "orders-common"],
      "description": "Core order processing pipeline"
    }
  ]
}
```

### 2. `topology.mermaid.md` — Full Org Graph

Full overview with all services and edges. Nodes shaped by type, edges labeled by communication type. Monorepo services grouped in subgraphs. Line style indicates confidence (solid = HIGH, dashed = MEDIUM, dotted = LOW).

### 3. `clusters/` — Per-Cluster Sub-Diagrams

One Mermaid file per detected cluster (e.g., `clusters/funding-cluster.mermaid.md`). Focused view of tightly-coupled service groups with their internal and external edges.

### 4. `report.md` — Human-Readable Summary

- Service inventory table (name, type, language, org, confidence)
- Dependency matrix
- Cluster descriptions with embedded Mermaid diagrams (both full and cluster views)
- Flagged items: LOW-confidence classifications, unresolved edges, scan errors
- Recommendations for further investigation

### 5. `scan-log.json` — Scan Metadata

Per-repo timing, errors, skipped repos, rate limit usage. Supports incremental re-runs.

## Execution Flow

1. **Pre-flight** — Verify `gh auth`, check rate limit budget, confirm org access for each provided org. Stop early with clear message if issues.

2. **Discovery** — Enumerate all repos across all provided orgs. Present summary:
   > "Found 147 repos across 2 orgs. 68 look like services, 22 libraries, 12 infrastructure, 45 unknown. 8 archived (excluded). Proceed?"

3. **Local Resolution** — Check configurable search paths for existing clones. Report:
   > "Found 23 repos locally. Will shallow-clone the remaining 45 to /tmp/pathfinder/."

4. **Tier 1 Analysis** — Parallel agents scan each repo (manifest + config). Per-repo findings written to `/tmp/pathfinder/<org>/repos/<repo-name>.json`. Status updates as agents complete.

5. **Tier 1 Checkpoint** — Present initial map:
   > "Tier 1 complete. Found 68 services, 94 edges (79 HIGH, 15 MEDIUM). Here's the overview. Would you like me to run a deep code scan for additional edges?"

6. **Tier 2 Analysis** (if opted in) — Parallel agents grep source files. Merge with Tier 1.

7. **Synthesis** — Cross-reference findings, resolve edges, detect clusters, generate all artifacts.

8. **Report** — Present results, commit to `docs/pathfinder/<org-name>/`.

## Query Mode — Blast Radius Oracle

After an initial scan, pathfinder's topology becomes a persistent, queryable data source. Other crucible skills (or the user directly) can interrogate the graph without re-scanning.

### Storage

`topology.json` is persisted to `~/.claude/projects/<org-hash>/memory/pathfinder/topology.json` (org-level, not repo-level), following the cartographer storage pattern. Any crucible session in any repo under that org can read it.

### Query Types

| Query | Description | Example |
|-------|-------------|---------|
| `upstream <service>` | Who calls this service? (consumers) | "What services depend on auth-api?" |
| `downstream <service>` | What does this service call? (dependencies) | "What does orders-api talk to?" |
| `blast-radius <service>` | If this service changes, what breaks? (transitive) | "What's the blast radius of changing payments-service?" |
| `shared-infra <resource>` | Which services share this resource? | "Who else uses the shared-redis instance?" |
| `path <service-A> <service-B>` | How do these services communicate? (direct or transitive) | "How does the frontend reach the billing service?" |

### Integration with Other Skills

Query mode is RECOMMENDED (not required) — skills check for pathfinder data and use it if available, gracefully degrade if not.

- **crucible:build** — Phase 1 blast radius analysis extends across repos when pathfinder data exists. "This API change also affects 3 services in other repos: [list]."
- **crucible:design** — Investigation agents consult pathfinder to understand cross-service impact before asking the user.
- **crucible:audit** — Subsystem audit scope can include immediate upstream/downstream neighbors, catching contract violations at service boundaries.

### Invocation

- **Automatic:** Other skills read `topology.json` directly when they need cross-repo context.
- **Explicit:** User invokes `crucible:pathfinder query upstream auth-api` for direct queries. Returns structured results with service names, edge types, and confidence.

### Cold Start

If no topology.json exists, query mode returns empty results and suggests running a full scan. No errors, no blocking — graceful degradation.

## Persistence & Incremental Runs

- Each scan writes results to both `docs/pathfinder/<org>/` (committed artifacts) and `~/.claude/projects/<org-hash>/memory/pathfinder/` (queryable store)
- Subsequent runs merge: new repos added, removed repos flagged, changed edges updated
- Mermaid diagrams regenerate from merged JSON
- Separate orgs (or org combinations) maintain separate output directories

## Estimated Runtime

| Org Size | Repos | Estimated Time |
|----------|-------|----------------|
| Small | <20 services | ~10-15 min |
| Medium | 20-50 services | ~20-30 min |
| Large | 100+ services | May need multiple sessions with incremental merging |

## Acceptance Criteria

1. Given one or more GitHub org names, pathfinder enumerates all repos and classifies each by type
2. Given repos with known inter-service dependencies, pathfinder detects edges with correct type and direction
3. Given a monorepo with multiple services, pathfinder identifies each service as a separate node
4. Output Mermaid renders correctly and matches the JSON topology data
5. Local repos are detected and used instead of cloning when available
6. Tier 1 completes and presents checkpoint before offering Tier 2
7. Incremental re-runs merge with existing data rather than overwriting
8. Multi-org scanning produces a unified graph spanning org boundaries
9. Query mode returns correct upstream/downstream/blast-radius results from persisted topology
10. Query mode gracefully returns empty results when no topology data exists

## Error Handling

- `gh auth` failure → stop with clear message
- Rate limit hit → pause, report remaining budget, offer to continue with reduced parallelism
- Clone failure (single repo) → skip, log to scan-log.json, continue with remaining repos
- Unresolvable edge references → flag in report as "unresolved", don't silently drop
- Large repos (>1GB disk usage) → manifest-only scan, skip clone
- Org membership limitations → warn that only visible repos are scanned (private repos require org membership)

## Future Enhancements

- **Crawl mode** (issue #40): Seed-based discovery — start from one repo, fan out by tracing dependencies. Useful for exploring a specific service's neighborhood without scanning entire orgs.
- **Contract sync verification** (issue #41): Extract API contracts on both sides of every edge (proto, OpenAPI, GraphQL schemas) and detect mismatches — version skew, phantom dependencies, schema drift.
- **Figma API integration:** Push topology data to Figma for visual editing and annotation.
- **Live dashboard:** Watch mode that re-scans periodically and diffs against previous topology.
- **Dependency health scoring:** Flag stale dependencies, unused edges, orphaned services.
