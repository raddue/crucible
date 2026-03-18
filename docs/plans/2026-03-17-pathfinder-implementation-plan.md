# Pathfinder — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use crucible:build to implement this plan task-by-task.

**Goal:** Create the `pathfinder` skill that maps an entire GitHub organization's service topology — enumerating repos, classifying services, detecting inter-service dependencies, and producing Mermaid diagrams, structured JSON, and a human-readable report. Includes a query mode for blast-radius analysis from persisted topology data.

**Architecture:** Markdown-only changes across 8 files (7 new, 1 modified). No application code. The skill consists of a SKILL.md orchestrator definition and 5 prompt templates for subagent dispatch (discovery classifier, Tier 1 analyzer, Tier 2 analyzer, synthesis agent, query handler), plus a README update.

**Design doc:** `docs/plans/2026-03-17-pathfinder-design.md`

---

## Dependency Graph

```
Task 1 (discovery-classifier-prompt.md) ── no deps ──────┐
Task 2 (tier1-analyzer-prompt.md) ── no deps ─────────────┤
Task 3 (tier2-analyzer-prompt.md) ── no deps ─────────────┤
Task 4 (synthesis-prompt.md) ── no deps ──────────────────┤
Task 5 (query-handler-prompt.md) ── no deps ──────────────┤
Task 6 (SKILL.md) ── depends on 1, 2, 3, 4, 5 ───────────┤
Task 7 (integration notes + README) ── depends on 6 ──────┘
```

---

### Task 1: Create Discovery Classifier Prompt Template

Write the subagent dispatch template for Phase 1 — classifies repos from GitHub API metadata into service types.

- **Files:** `skills/pathfinder/discovery-classifier-prompt.md` (1 file)
- **Complexity:** Medium
- **Dependencies:** None

**Steps:**

1. Create `skills/pathfinder/` directory.

2. Write `skills/pathfinder/discovery-classifier-prompt.md` with:
   - Dispatch block header: `Task tool (general-purpose, model: sonnet):`
   - Description placeholder: `"Classify repos for [org name]"`
   - Agent identity: "You are a discovery classifier. Your job is to classify GitHub repositories by service type using metadata and manifest signals. You produce a structured classification for every repo, with confidence scores."
   - Input sections (placeholders for orchestrator to fill):
     - `[PASTE: Org name]`
     - `[PASTE: JSON array of repo metadata from gh repo list — name, description, language, topics, archived status, disk usage, last push date]`
   - Process:
     1. For each repo, classify as one of: API, Worker, Frontend, Serverless, Library, Infrastructure, Tool, Unknown
     2. Apply the classification signal table from the design doc:
        - **API:** Dockerfile + framework detection (Express, FastAPI, Spring Boot, etc.) + port binding
        - **Worker:** Dockerfile + queue consumer patterns, no exposed HTTP ports
        - **Frontend:** React/Vue/Angular/Next.js, static hosting configs
        - **Serverless:** serverless.yml, SAM templates, Lambda handler patterns
        - **Library:** No Dockerfile, published to package registry, consumed by other repos
        - **Infrastructure:** Terraform, Pulumi, CloudFormation definitions
        - **Tool:** CLI utilities, scripts, dev tooling — not deployed as a running service
        - **Unknown:** Insufficient signals to classify confidently
     3. Assign confidence: HIGH (2+ signals match), MEDIUM (1 signal match), LOW (inferred from name/description only)
     4. Mark archived and empty repos as excluded
     5. Detect monorepo signals: workspace configs (npm workspaces, go.work, Cargo.toml [workspace], Bazel WORKSPACE), multiple Dockerfiles, multiple CI pipelines
   - Required output format:
     ```
     ## Classification Results

     ### Summary
     - Total repos: N
     - Services: N (API: N, Worker: N, Frontend: N, Serverless: N)
     - Libraries: N
     - Infrastructure: N
     - Tools: N
     - Unknown: N
     - Excluded (archived/empty): N
     - Monorepos detected: N

     ### Repo Classifications

     | Repo | Type | Language | Confidence | Monorepo | Signals |
     |------|------|----------|------------|----------|---------|
     | repo-name | API | TypeScript | HIGH | No | Express framework, Dockerfile, port 3000 |
     [repeat for each repo]

     ### Monorepo Details
     [For each detected monorepo: repo name, workspace type, detected sub-services]

     ### Excluded Repos
     [Archived and empty repos with reason for exclusion]

     ### Low Confidence Items
     [Repos classified as Unknown or with LOW confidence — flagged for human review]
     ```
   - Rules:
     - Classify based on available metadata only — you do NOT have access to repo contents at this stage
     - Language and topics fields are strong signals for Library vs Service distinction
     - Description field can disambiguate but is LOW confidence on its own
     - When in doubt, classify as Unknown rather than guessing
     - Do NOT attempt to clone or read files — this is metadata-only classification
   - Context self-monitoring: "If you reach 50%+ context utilization with repos remaining, report partial results and list unclassified repos."

**Commit:** `feat: add discovery classifier prompt template for pathfinder`

---

### Task 2: Create Tier 1 Analyzer Prompt Template

Write the subagent dispatch template for Phase 2 Tier 1 — manifest and config scanning for a single pre-cloned repo.

- **Files:** `skills/pathfinder/tier1-analyzer-prompt.md` (1 file)
- **Complexity:** High
- **Dependencies:** None

**Steps:**

1. Write `skills/pathfinder/tier1-analyzer-prompt.md` with:
   - Dispatch block header: `Agent tool (subagent_type: Explore, model: sonnet):`
   - Description placeholder: `"Tier 1 analysis for [org/repo]"`
   - Agent identity: "You are a Tier 1 repo analyzer. Your job is to scan manifest files and configuration in a single repository to identify service characteristics, dependencies, and inter-service edges. You scan configs, NOT source code."
   - Input sections (placeholders for orchestrator to fill):
     - `[PASTE: Org name and repo name — qualified as org/repo]`
     - `[PASTE: Repo path on disk — either local clone path or /tmp/pathfinder/<org>/<repo>/]`
     - `[PASTE: Classification from Phase 1 — type, language, confidence, monorepo status]`
     - `[PASTE: All repo names in this scan — needed for internal package detection and env var URL matching]`
     - `[PASTE: Org names being scanned — needed for internal package scope matching]`
   - Process — scan these files (in order, skipping if not found):
     1. **Package manifests:** `package.json`, `go.mod`, `requirements.txt`, `pyproject.toml`, `Cargo.toml`, `pom.xml`, `build.gradle` (exclude `**/node_modules/**`, `**/vendor/**` for all glob patterns)
        - Extract dependencies — separate internal (org-scoped or matching a scanned repo name) from external
        - Internal package detection rules: scope matches org name (e.g., `@acme-platform/shared-types`), or package name matches a scanned repo name, or uses `file:../` or `workspace:` references
     2. **Environment and config:** `*.env*`, `.env.example`, `docker-compose.yml`, `docker-compose*.yml`
        - Extract env var URLs — hostname matching rules: exact match to repo name, prefix match to repo name
        - Denylist: skip `DATABASE_URL`, `REDIS_URL`, `CACHE_URL`, `MONGO_URI`, `ELASTICSEARCH_URL` for service edges (map to shared-infrastructure edges instead)
        - Docker-compose service references — match to other repo names
     3. **Proto and API definitions:** `**/*.proto` (excluding `**/node_modules/**`, `**/vendor/**`), `openapi.yaml`, `swagger.json`
        - Extract proto imports — match to repos containing referenced .proto files
        - Extract API endpoint definitions
     4. **Infrastructure:** `Dockerfile`, `k8s/**/*.yaml`, `helm/**/*.yaml`, `serverless.yml`, `template.yaml` (SAM)
        - Extract exposed ports, base images, resource requests
        - Kafka/RabbitMQ/SQS topic/queue names — note whether producer or consumer
     5. **Monorepo sub-services:** If monorepo detected, enumerate sub-services:
        - Each directory containing a Dockerfile or listed as a workspace member = separate service node
        - Name as `<repo>/<subdir>` (e.g., `platform/services/auth`)
        - Run the above scans per sub-service directory
   - Edge detection — for each detected dependency, produce an edge with:
     - `source` → `target` (qualified `org/repo` identifiers)
     - `type`: HTTP, Kafka, gRPC, shared-db, shared-package, infrastructure
     - `direction`: unidirectional or bidirectional
     - `confidence`: HIGH, MEDIUM, LOW (based on signal strength)
     - `evidence`: file path, line number, matched pattern
     - `label`: specific identifier (topic name, endpoint path, package name)
   - Required output format — JSON written to stdout:
     ```json
     {
       "service": {
         "name": "org/repo",
         "type": "API",
         "language": "TypeScript",
         "framework": "Express",
         "confidence": "HIGH",
         "status": "active",
         "metadata": { "topics": [], "last_push": "2026-03-15" },
         "sub_services": []
       },
       "edges": [
         {
           "source": "org/repo",
           "target": "org/other-repo",
           "type": "HTTP",
           "direction": "unidirectional",
           "confidence": "HIGH",
           "label": "PAYMENTS_SERVICE_URL",
           "evidence": [
             { "file": ".env.example", "line": 12, "match": "PAYMENTS_SERVICE_URL=http://payments:8080" }
           ]
         }
       ],
       "unresolved": [
         { "reference": "UNKNOWN_SERVICE_URL", "file": ".env.example", "line": 15, "reason": "No matching repo found" }
       ],
       "scan_metadata": {
         "files_scanned": 8,
         "duration_estimate": "fast",
         "errors": []
       }
     }
     ```
   - Rules:
     - Do NOT read source code files (`.ts`, `.js`, `.py`, etc.) — that is Tier 2
     - Do NOT modify any files — read-only scan
     - Unresolvable env var references go in `unresolved`, not silently dropped
     - External packages (express, lodash, etc.) are ignored for edge detection
     - If a manifest is malformed, log the error and continue scanning other files
     - For monorepos, each sub-service is a separate entry in `sub_services`
   - Output cap: "Your JSON output must be valid. If the repo has many edges, include all of them — completeness matters for synthesis."
   - Context self-monitoring: "If you reach 50%+ context utilization, report what you have so far. Include a `partial: true` field in your JSON output and list unscanned files in `scan_metadata.errors`."

**Commit:** `feat: add tier 1 analyzer prompt template for pathfinder`

---

### Task 3: Create Tier 2 Analyzer Prompt Template

Write the subagent dispatch template for Phase 2 Tier 2 — deep code scanning for additional edges in a single pre-cloned repo.

- **Files:** `skills/pathfinder/tier2-analyzer-prompt.md` (1 file)
- **Complexity:** High
- **Dependencies:** None

**Steps:**

1. Write `skills/pathfinder/tier2-analyzer-prompt.md` with:
   - Dispatch block header: `Agent tool (subagent_type: Explore, model: sonnet):`
   - Description placeholder: `"Tier 2 deep scan for [org/repo]"`
   - Agent identity: "You are a Tier 2 repo analyzer. Your job is to scan source code in a single repository to discover inter-service edges that manifest and config scanning missed. You look for HTTP client calls, message queue interactions, gRPC channels, and shared infrastructure usage in actual code."
   - Input sections (placeholders for orchestrator to fill):
     - `[PASTE: Org name and repo name — qualified as org/repo]`
     - `[PASTE: Repo path on disk]`
     - `[PASTE: Tier 1 findings JSON for this repo — so you know what edges were already found]`
     - `[PASTE: All repo names and service names in this scan — for hostname matching]`
     - `[PASTE: Org names being scanned]`
   - Process:
     1. **Identify source files** to scan: `src/**/*.{ts,js,py,go,java,rb,cs}`
        - **Per-repo limits:** Max 200 source files. Prioritize recently modified files (use filesystem timestamps).
        - **Exclusions:** Skip `**/test/**`, `**/spec/**`, `**/mock/**`, `**/__tests__/**`, `**/node_modules/**`, `**/vendor/**`
     2. **Grep for edge patterns** by type:
        - **HTTP clients:** `requests.get`, `requests.post`, `fetch(`, `axios.`, `http.Get`, `http.Post`, `HttpClient`, `urllib`, `got(`, `ky(`
        - **Kafka:** `producer.send`, `consumer.subscribe`, `KafkaProducer`, `KafkaConsumer`, topic name strings in producer/consumer context
        - **gRPC:** `NewServiceClient(`, `ServiceStub(`, `grpc.secure_channel`, `grpc.insecure_channel`, `@GrpcClient`
        - **Redis:** `redis.StrictRedis`, `RedisClient`, `ioredis`, `createClient`, Redis connection patterns
        - **Elasticsearch:** `Elasticsearch(`, `ElasticsearchClient`, `@elastic/elasticsearch`
        - **S3:** `s3.get_object`, `s3.putObject`, `s3.getObject`, `S3Client`, bucket name strings
     3. **For each match**, extract context:
        - What hostname/topic/resource is referenced?
        - Can the hostname/topic be matched to a known repo or service name?
        - Is this a producer or consumer pattern?
     4. **False positive mitigation:**
        - Exclude commented-out lines (lines starting with `//`, `#`, `*`, `<!--`)
        - Rank by frequency: single reference = MEDIUM confidence, 3+ references = HIGH
        - HTTP calls to well-known external APIs (googleapis.com, api.stripe.com, etc.) are not inter-service edges
     5. **Max 50 grep matches retained** — if more matches found, keep the 50 most diverse (different targets, different edge types)
   - Edge output format — same as Tier 1 but edges have `tier: 2` marker:
     ```json
     {
       "new_edges": [
         {
           "source": "org/repo",
           "target": "org/other-repo",
           "type": "HTTP",
           "direction": "unidirectional",
           "confidence": "MEDIUM",
           "label": "auth-service:8080/api/v1/validate",
           "evidence": [
             { "file": "src/middleware/auth.ts", "line": 42, "match": "await fetch('http://auth-service:8080/api/v1/validate')" }
           ],
           "tier": 2
         }
       ],
       "upgraded_edges": [
         {
           "original_label": "AUTH_SERVICE_URL",
           "new_evidence": [
             { "file": "src/middleware/auth.ts", "line": 42, "match": "code-level confirmation of env var usage" }
           ],
           "new_confidence": "HIGH"
         }
       ],
       "unresolved": [
         { "reference": "http://unknown-host:3000/api", "file": "src/client.ts", "line": 88, "reason": "Hostname does not match any scanned repo" }
       ],
       "scan_metadata": {
         "source_files_scanned": 142,
         "source_files_skipped": 58,
         "grep_matches_total": 87,
         "grep_matches_retained": 50,
         "errors": []
       }
     }
     ```
   - Rules:
     - Do NOT duplicate edges already found in Tier 1 — check the provided Tier 1 findings. If you find code evidence for a Tier 1 edge, put it in `upgraded_edges` to boost confidence.
     - Do NOT modify any files — read-only scan
     - Unresolvable references go in `unresolved`, not silently dropped
     - If a source file is too large to read (>500 lines), scan only the import section and first 200 lines
   - Context self-monitoring: "Report at 50% context usage. Include `partial: true` in your JSON and list unscanned directories in `scan_metadata.errors`."

**Commit:** `feat: add tier 2 analyzer prompt template for pathfinder`

---

### Task 4: Create Synthesis Prompt Template

Write the subagent dispatch template for Phase 3 — cross-references all per-repo findings, resolves edges, detects clusters, and generates all output artifacts.

- **Files:** `skills/pathfinder/synthesis-prompt.md` (1 file)
- **Complexity:** High
- **Dependencies:** None

**Steps:**

1. Write `skills/pathfinder/synthesis-prompt.md` with:
   - Dispatch block header: `Agent tool (subagent_type: general-purpose, model: opus):`
   - Description placeholder: `"Synthesize topology for [org names]"`
   - Agent identity: "You are a topology synthesis agent. Your job is to cross-reference per-repo analysis results, resolve dependency edges, detect service clusters, and generate the final topology artifacts: JSON, Mermaid diagrams, and a human-readable report."
   - Input sections (placeholders for orchestrator to fill):
     - `[PASTE: Org names being synthesized]`
     - `[PASTE: File paths to per-repo JSON results — e.g., /tmp/pathfinder/acme-platform/repos/orders-api.json]`
     - `[PASTE: Tier depth — 1 or 2, so you know whether Tier 2 data exists]`
     - `[PASTE: Output directory — e.g., docs/pathfinder/acme-platform/]`
     - `[PASTE: Persistence path — e.g., ~/.claude/memory/pathfinder/acme-platform/]`
     - `[PASTE: Existing topology.json if incremental run — or "No prior topology data."]`
   - Process:
     1. **Read all per-repo result files** from the provided paths
     2. **Build the service inventory** — unified list of all services with their classifications
     3. **Edge resolution — producer/consumer matching:**
        - For each edge, verify both source and target exist in the service inventory
        - Apply edge identity rule: two edges are the same if `source + target + type + label` match
        - On merge: confidence takes max, evidence is unioned, direction flagged if contradictory
        - Deduplicate: multiple evidence points for the same logical edge merge into one
     4. **Cluster detection** (algorithm from design doc):
        - Step 1: Monorepo clusters — services within the same monorepo always form a cluster, named after the repo
        - Step 2: Affinity clusters — services that share 2+ edges of any type form a candidate cluster. Use connected components on the subgraph of services with 2+ shared edges.
        - Step 3: Naming — clusters named after their most-connected service or shared resource
        - Step 4: Singletons — services with no cluster affinity appear as standalone nodes
        - Clusters are always recomputed from scratch on the full edge set
     5. **Incremental merge** (if existing topology provided):
        - New repos: add with `status: "active"`
        - Removed repos: set `status` to `"stale"`, keep for one more run, then remove
        - Existing repos: update classification and edges, confidence takes max of old/new
        - Edge merge: match by `source + target + type + label`, confidence max, evidence union, direction flag
        - Clusters: always recomputed from scratch on merged edge set
     6. **Generate output artifacts:**
   - Output artifacts — the synthesis agent writes all of the following:

     **File: `topology.json`** — Source of truth. Follow the exact schema from the design doc:
     ```json
     {
       "meta": {
         "orgs": ["org-name"],
         "scan_timestamp": "ISO 8601",
         "tier_depth": 1,
         "repo_count": N,
         "service_count": N,
         "edge_count": N,
         "service_coverage": { "high": N, "medium": N, "low": N },
         "edge_coverage": { "high": N, "medium": N, "low": N }
       },
       "services": [ ... ],
       "edges": [ ... ],
       "clusters": [ ... ]
     }
     ```
     Write to BOTH the output directory and the persistence path.

     **File: `topology.mermaid.md`** — Full org graph. Nodes shaped by type (rectangle for API, stadium for Worker, hexagon for Frontend, etc.). Edges labeled by communication type. Monorepo services grouped in `subgraph` blocks. Line style: solid = HIGH confidence, dashed = MEDIUM, dotted = LOW. For 30+ services: render at cluster level with per-cluster detail diagrams.

     **File: `clusters/<cluster-name>.mermaid.md`** — One Mermaid file per detected cluster. Focused view showing internal edges and external edges to/from the cluster.

     **File: `report.md`** — Human-readable summary with sections:
     - Service inventory table (name, type, language, org, confidence)
     - Dependency matrix (which service calls which)
     - Cluster descriptions with embedded Mermaid diagrams
     - Flagged items: LOW-confidence classifications, unresolved edges, scan errors
     - Recommendations for further investigation

     **File: `scan-log.json`** — Scan metadata: per-repo timing, errors, skipped repos, rate limit usage.

   - Rules:
     - Every service name must be qualified as `org/repo` to avoid cross-org collisions
     - Do NOT invent edges — only include edges with evidence from the per-repo results
     - Unresolved references from per-repo results should be collected into the report's "Flagged Items" section
     - Mermaid diagrams must render correctly — test by keeping syntax simple (no special characters in labels without quoting)
     - If the full Mermaid graph would exceed ~100 nodes, render at cluster level only and generate per-cluster detail diagrams
   - Context self-monitoring: "If you reach 50%+ context utilization with artifacts remaining, prioritize: topology.json first, then report.md, then Mermaid diagrams. Write each to disk as completed."

**Commit:** `feat: add synthesis prompt template for pathfinder`

---

### Task 5: Create Query Handler Prompt Template

Write the subagent dispatch template for query mode — traverses persisted topology data to answer upstream/downstream/blast-radius queries.

- **Files:** `skills/pathfinder/query-handler-prompt.md` (1 file)
- **Complexity:** Medium
- **Dependencies:** None

**Steps:**

1. Write `skills/pathfinder/query-handler-prompt.md` with:
   - Dispatch block header: `Task tool (general-purpose, model: sonnet):`
   - Description placeholder: `"Pathfinder query: [query type] [target]"`
   - Agent identity: "You are a topology query handler. Your job is to traverse a persisted service topology graph to answer questions about service dependencies, blast radius, and communication paths. You return structured results."
   - Input sections (placeholders for orchestrator to fill):
     - `[PASTE: Query type — one of: upstream, downstream, blast-radius, shared-infra, path]`
     - `[PASTE: Query target(s) — service name(s) or resource name]`
     - `[PASTE: Full topology.json contents]`
   - Process — by query type:
     1. **`upstream <service>`** — Find all services that have edges pointing TO the target service. Return direct callers/consumers with edge types.
     2. **`downstream <service>`** — Find all services that the target service has edges pointing TO. Return direct dependencies with edge types.
     3. **`blast-radius <service>`** — Transitive upstream traversal using BFS with a visited set. For each hop, record the path. Detect and report cycles: "Circular dependency detected: A -> B -> A." Return all transitively affected services grouped by hop distance.
     4. **`shared-infra <resource>`** — Find all services that share the named resource (matching by edge label). Resource types: shared-db, infrastructure.
     5. **`path <service-A> <service-B>`** — Find communication path(s) between two services. Use BFS from A to B, considering edge direction. Report direct or transitive paths with edge types at each hop. If no path exists, report "No communication path found between A and B."
   - Required output format:
     ```
     ## Query: [query type] [target]

     ### Results

     [Structured results depending on query type — table or list format]

     ### Details

     | Service | Edge Type | Direction | Confidence | Hop Distance |
     |---------|-----------|-----------|------------|--------------|
     | ... | ... | ... | ... | ... |

     ### Warnings
     [Cycles detected, stale services, low-confidence edges in the path]

     ### Raw Data
     [JSON array of relevant edges for programmatic consumption]
     ```
   - Rules:
     - Cycle detection is mandatory for blast-radius and path queries — use a visited set
     - Report stale services (status: "stale") separately — they are unreliable
     - LOW-confidence edges should be included but flagged with a warning
     - If the topology.json is empty or contains no services, return: "No topology data available. Run `crucible:pathfinder <org>` to perform a full scan."
     - Do NOT modify the topology data — read-only query
     - Keep output concise — for blast-radius queries with 20+ affected services, show the first 3 hops in detail and summarize deeper hops

**Commit:** `feat: add query handler prompt template for pathfinder`

---

### Task 6: Create Pathfinder SKILL.md

Write the main skill definition that orchestrates the full pathfinder flow — discovery, analysis (Tier 1 + optional Tier 2), synthesis, query mode, and compaction recovery. This is the core deliverable and the largest task.

- **Files:** `skills/pathfinder/SKILL.md` (1 file)
- **Complexity:** High
- **Dependencies:** Task 1, Task 2, Task 3, Task 4, Task 5

**Steps:**

1. Write `skills/pathfinder/SKILL.md` with the following structure:

   **Frontmatter:**
   ```yaml
   ---
   name: pathfinder
   description: "Map a GitHub organization's service topology — repos, dependencies, communication edges. Triggers on 'map services', 'service topology', 'what depends on X', 'blast radius', or any task requesting cross-repo dependency analysis."
   ---
   ```

   **Overview section:**
   - Maps an entire GitHub org's (or multiple orgs') service topology
   - Produces Mermaid diagrams, structured JSON, and a human-readable markdown report
   - Two modes: full scan (three-phase execution) and query mode (graph traversal on persisted data)
   - Invocation: `crucible:pathfinder <org1> [org2] [org3...]` for full scan, `crucible:pathfinder query <type> <target>` for queries
   - Announce at start: "Running pathfinder on [org names]."
   - Skill type: Rigid — follow exactly, no shortcuts

   **Model section:**
   - Orchestrator: Opus
   - Analysis agents (Phase 2): Sonnet via Agent tool (subagent_type: Explore)
   - Discovery classifier (Phase 1): Sonnet via Task tool
   - Synthesis agent (Phase 3): Opus via Task tool
   - Query handler: Sonnet via Task tool

   **Communication Requirement (Non-Negotiable) section:**
   - Between every agent dispatch and every agent completion, output a status update to the user
   - Status updates must include: current phase, what just completed, what's being dispatched next, progress counts (repos completed/remaining, edges found so far)
   - After compaction: re-read state file and current state before continuing
   - Examples of good narration (matching audit skill pattern)

   **Scratch and State section:**
   - State file: `/tmp/pathfinder-state.json` — written by orchestrator, updated after each repo completes
   - Per-repo results: `/tmp/pathfinder/<org>/repos/<repo-name>.json` — written on completion, survives compaction
   - Clone directory: `/tmp/pathfinder/<org>/<repo>/` for shallow clones
   - Output directory: `docs/pathfinder/<org-name>/` (single org) or `docs/pathfinder/<combined-name>/` (multi-org, alpha-sorted org names joined by `+`)
   - Persistence path: `~/.claude/memory/pathfinder/<org-name>/topology.json` (well-known absolute path, outside project-hash system)

   **Phase 1: Discovery section:**
   - **Pre-flight checks:**
     1. Verify `gh auth status` — stop with clear message if not authenticated
     2. Check rate limit budget via `gh api rate_limit` — estimate API calls needed (repo count / 30 pages + clone count). Warn if budget insufficient.
     3. Confirm org access for each provided org via `gh repo list <org> --limit 1`
   - **Repo enumeration:** `gh repo list <org> --json name,description,primaryLanguage,repositoryTopics,isArchived,diskUsage,pushedAt --limit 1000` for each provided org
   - **Classification dispatch:** Task tool (Sonnet) using `./discovery-classifier-prompt.md`. Pass repo metadata JSON. Receive classified repo list.
   - **User confirmation gate:** Present summary to user:
     > "Found 147 repos across 2 orgs. 68 look like services, 22 libraries, 12 infrastructure, 45 unknown. 8 archived (excluded). Proceed?"
   - Do NOT proceed without user confirmation. User may exclude specific repos or narrow scope.
   - **Exclusions:** Archived repos and empty repos (diskUsage = 0) excluded by default, listed in appendix of classification results.

   **Phase 2: Analysis section:**

   **Local Resolution sub-section:**
   - Before cloning, check `../` for existing clones matching repo names
   - Report to user: "Found 23 repos locally. Will shallow-clone the remaining 45 to /tmp/pathfinder/."
   - Local repos are used in-place — no copying

   **Orchestrator-Managed Cloning sub-section:**
   - The orchestrator performs all cloning sequentially using `gh repo clone <org>/<repo> /tmp/pathfinder/<org>/<repo>/ -- --depth=1`
   - Write progress to state file after each clone completes
   - Large repos (>1GB disk usage from metadata): manifest-only scan, skip clone — inform user
   - Clone failure: skip, log error to state file, continue with remaining repos

   **Tier 1 Analysis sub-section:**
   - Dispatch analysis agents in waves of max 10 concurrent via Agent tool (subagent_type: Explore, model: Sonnet) using `./tier1-analyzer-prompt.md`
   - Each agent receives: repo path (pre-cloned), classification, all repo names list, org names
   - Per-repo results written to `/tmp/pathfinder/<org>/repos/<repo-name>.json` immediately on completion
   - Update state file (repos_completed, repos_remaining) after each agent completes
   - For orgs with 50+ repos, batch into waves of 10 — complete one wave before starting next
   - Status update after each wave completes

   **Tier 1 Checkpoint sub-section:**
   - After all Tier 1 agents complete, present initial findings to user:
     > "Tier 1 complete. Found 68 services, 94 edges (79 HIGH, 15 MEDIUM). Here's the overview. Would you like me to run a deep code scan for additional edges?"
   - Include a summary table of edge types found and services with no detected edges
   - User options: proceed to Tier 2, skip to synthesis, abort

   **Tier 2 Analysis sub-section (opt-in):**
   - Dispatch deep scan agents in waves of max 10 via Agent tool (subagent_type: Explore, model: Sonnet) using `./tier2-analyzer-prompt.md`
   - Each agent receives: repo path, Tier 1 findings for that repo, all repo/service names, org names
   - Per-repo limits: max 200 source files scanned, max 50 grep matches retained. Prioritize recently modified files.
   - Agents report at 50% context usage
   - Tier 2 results merge with Tier 1: new edges added, existing edges upgraded if code evidence confirms config evidence
   - Update per-repo JSON files with merged results

   **Phase 3: Synthesis section:**
   - Dispatch single Opus agent via Agent tool (subagent_type: general-purpose, model: opus) using `./synthesis-prompt.md`
   - Agent receives: paths to all per-repo JSON files, tier depth, output directory, persistence path, existing topology.json (if incremental)
   - Agent produces all output artifacts: topology.json, topology.mermaid.md, clusters/, report.md, scan-log.json
   - Writes to both output directory (for committing) and persistence path (for query mode)
   - Orchestrator verifies output: topology.json exists and is valid JSON, report.md exists and is non-empty

   **Phase 4: Report section:**
   - Present results to user with key metrics: service count, edge count, cluster count
   - Show the full Mermaid graph (or cluster-level graph if 30+ services)
   - Highlight flagged items: LOW-confidence classifications, unresolved edges, scan errors
   - Offer to commit output to `docs/pathfinder/<org>/`

   **Query Mode section:**
   - Triggered by `crucible:pathfinder query <type> <target>`
   - Types: upstream, downstream, blast-radius, shared-infra, path
   - **Storage:** Read `~/.claude/memory/pathfinder/<org-name>/topology.json` — well-known path outside project-hash system. Multi-org stored under combined name (alpha-sorted, `+`-joined).
   - **Cold start:** If no topology.json exists, return empty results and suggest running a full scan. No errors, no blocking — graceful degradation.
   - Dispatch query handler via Task tool (Sonnet) using `./query-handler-prompt.md`
   - Pass: query type, target, full topology.json contents
   - Present structured results to user
   - **Cycle detection:** Mandatory for blast-radius and path queries. BFS with visited set. Report cycles explicitly.

   **Multi-Org Support section:**
   - All orgs enumerated and analyzed together
   - Dependency graph spans org boundaries — cross-org edges shown explicitly
   - Service names always qualified as `org/repo` to prevent name collisions
   - Output directory: `docs/pathfinder/<combined-name>/` where combined name is alpha-sorted org names joined by `+`

   **Monorepo Handling section:**
   - Detection signals from design doc (workspace configs, multiple Dockerfiles, multiple CI pipelines)
   - Sub-service enumeration: each Dockerfile or workspace member = separate service node
   - Naming: `<repo>/<subdir>` (e.g., `platform/services/auth`)
   - Monorepo services grouped in Mermaid `subgraph` blocks
   - Internal monorepo edges tracked but visually distinguished from cross-repo edges

   **Compaction Recovery section:**
   - State file: `/tmp/pathfinder-state.json` — read on compaction to determine current phase and progress
   - Schema from design doc: `{ orgs, phase, repos_total, repos_completed, repos_remaining, clone_paths }` — all repo names in these arrays must use qualified `org/repo` format for multi-org disambiguation
   - Per-repo results survive compaction (already written to disk)
   - Recovery logic:
     1. Read state file to determine current phase
     2. If Phase 2: skip completed repos, resume from remaining list
     3. If Phase 3: re-dispatch synthesis with all available per-repo results
     4. If query mode: no state needed — read topology.json and re-dispatch
   - Output status update to user after recovery before continuing

   **Error Handling section:**
   - `gh auth` failure → stop with clear message
   - Rate limit hit → pause, report remaining budget, offer to continue with reduced parallelism
   - Rate budget insufficient at pre-flight → warn user with estimate before starting
   - Clone failure (single repo) → skip, log to scan-log.json, continue with remaining repos
   - Unresolvable edge references → flag in report as "unresolved", don't silently drop
   - Large repos (>1GB disk usage) → manifest-only scan, skip clone
   - Org membership limitations → warn that only visible repos are scanned (private repos require org membership)
   - Service name collision across orgs → prevented by qualified `org/repo` identifiers

   **Persistence and Incremental Runs section:**
   - Each scan writes to both committed artifacts and queryable store
   - Merge rules from design doc: new repos added, removed repos marked stale, existing repos updated, edge merge by identity, clusters recomputed

   **Guardrails section:**

   Analysis agents must NOT:
   - Modify any code (pathfinder is read-only)
   - Clone repos (orchestrator handles all cloning)
   - Scan source code in Tier 1 (configs and manifests only)
   - Invent edges without evidence

   The orchestrator must NOT:
   - Proceed to Phase 2 without user confirmation of discovery results
   - Proceed to Tier 2 without explicit user opt-in at checkpoint
   - Run more than 10 concurrent analysis agents
   - Skip narration between agent dispatches
   - Clone repos larger than 1GB (use manifest-only scan)

   **Red Flags section:**
   - Cloning inside subagents instead of the orchestrator
   - Skipping the Tier 1 checkpoint before Tier 2
   - Silently dropping unresolved references
   - Running synthesis before all analysis agents complete
   - Exceeding 10 concurrent agents

   **Integration section:**
   - **Consults:** None (standalone initial scan)
   - **Consumed by:** `crucible:build` (blast-radius extends across repos), `crucible:design` (cross-service impact), `crucible:audit` (upstream/downstream neighbor scope)
   - **Query mode consumers:** Other skills read `topology.json` from well-known path
   - **Does NOT:** Modify any code, deploy anything, run tests
   - **Related skills:** `crucible:build`, `crucible:design`, `crucible:audit`

   **Subagent Dispatch Summary table:**
   | Agent | Model | Dispatch | Prompt Template |
   |-------|-------|----------|-----------------|
   | Discovery Classifier | Sonnet | Task tool (general-purpose) | `./discovery-classifier-prompt.md` |
   | Tier 1 Analyzer | Sonnet | Agent tool (Explore) | `./tier1-analyzer-prompt.md` |
   | Tier 2 Analyzer | Sonnet | Agent tool (Explore) | `./tier2-analyzer-prompt.md` |
   | Synthesis Agent | Opus | Agent tool (general-purpose) | `./synthesis-prompt.md` |
   | Query Handler | Sonnet | Task tool (general-purpose) | `./query-handler-prompt.md` |

   **Prompt Templates section:**
   - `./discovery-classifier-prompt.md` — Phase 1 repo classification from metadata
   - `./tier1-analyzer-prompt.md` — Phase 2 Tier 1 manifest and config scanning
   - `./tier2-analyzer-prompt.md` — Phase 2 Tier 2 deep code scanning
   - `./synthesis-prompt.md` — Phase 3 cross-reference, edge resolution, cluster detection, output generation
   - `./query-handler-prompt.md` — Query mode graph traversal and blast-radius computation

**Commit:** `feat: create pathfinder skill definition`

---

### Task 7: Integration Notes and README Update

Add pathfinder to the README skill table and document integration points for consuming skills.

- **Files:** `README.md` (1 file)
- **Complexity:** Low
- **Dependencies:** Task 6

**Steps:**

1. Read the current README.md to find the skill table location.

2. Add `pathfinder` to the skill table in the appropriate category (likely under a new "Discovery" or "Infrastructure" category, or alongside other mapping skills). New row:
   ```
   | **pathfinder** | Maps GitHub org service topology — enumerates repos, classifies services, detects inter-service dependencies. Produces Mermaid diagrams, JSON topology, and markdown reports. Query mode provides blast-radius analysis from persisted data. |
   ```

3. If there is a "How It Works" section, add a brief mention:
   ```
   The **pathfinder** skill maps service topology across GitHub organizations. Run `crucible:pathfinder <org>` to discover all services and their dependencies. Once scanned, other skills like build, design, and audit can query the persisted topology for cross-repo blast-radius analysis.
   ```

4. Verify no broken references — `skills/pathfinder/` directory should exist from Task 6 with all prompt templates from Tasks 1-5.

5. **Integration documentation** — the SKILL.md (Task 6) already documents integration points in its Integration section. No separate integration file is needed. The consuming skills (build, design, audit) should be updated in future PRs to add their pathfinder consultation logic — this is documented as RECOMMENDED (not required) per the design doc, meaning skills gracefully degrade when pathfinder data is absent.

**Commit:** `docs: add pathfinder to README skill table`

---

## Execution Order Summary

**Wave 1 (no dependencies, parallel-safe):**
- Task 1: Discovery classifier prompt (1 new file)
- Task 2: Tier 1 analyzer prompt (1 new file)
- Task 3: Tier 2 analyzer prompt (1 new file)
- Task 4: Synthesis prompt (1 new file)
- Task 5: Query handler prompt (1 new file)

**Wave 2 (depends on Wave 1):**
- Task 6: SKILL.md (depends on Tasks 1-5 — references all prompt templates)

**Wave 3 (depends on Wave 2):**
- Task 7: README update (depends on Task 6 — needs complete skill to describe)

---

## Verification Checklist

After all tasks complete, run these checks:

1. **Pathfinder SKILL.md validation:**
   - Has valid frontmatter (`name: pathfinder`, `description:`)
   - References all 5 prompt templates (files exist in same directory)
   - Contains: Pre-flight, Phase 1, Phase 2 (Tier 1 + Tier 2), Phase 3, Query Mode, Compaction Recovery, Error Handling sections
   - Communication Requirement section present with narration examples
   - Guardrails and Red Flags sections present

2. **Prompt template validation (all 5):**
   - Each has dispatch block header with correct subagent_type and model
   - Each has placeholder input sections for orchestrator to fill
   - Each has structured output format
   - Each has rules and context self-monitoring blocks
   - Tier 1 and Tier 2 analyzers produce JSON output matching the schema
   - Synthesis agent writes all 5 artifact types (topology.json, topology.mermaid.md, clusters/, report.md, scan-log.json)
   - Query handler supports all 5 query types (upstream, downstream, blast-radius, shared-infra, path)

3. **Edge model consistency:**
   - All templates use the same edge data model: source, target, type, direction, confidence, label, evidence
   - Edge identity rule consistent: `source + target + type + label`
   - Confidence levels consistent: HIGH, MEDIUM, LOW
   - Edge types consistent: HTTP, Kafka, gRPC, shared-db, shared-package, infrastructure

4. **Service classification consistency:**
   - Discovery classifier uses the same 8 types: API, Worker, Frontend, Serverless, Library, Infrastructure, Tool, Unknown
   - Classification signals match the design doc table
   - Confidence scoring consistent: HIGH/MEDIUM/LOW

5. **Output path consistency:**
   - Committed artifacts: `docs/pathfinder/<org-name>/` or `docs/pathfinder/<combined>/`
   - Persisted topology: `~/.claude/memory/pathfinder/<org-name>/topology.json`
   - Multi-org combined name: alpha-sorted, `+`-joined
   - Per-repo results: `/tmp/pathfinder/<org>/repos/<repo-name>.json`
   - State file: `/tmp/pathfinder-state.json`
   - Clone directory: `/tmp/pathfinder/<org>/<repo>/`

6. **Cross-reference resolution:**
   - `skills/pathfinder/discovery-classifier-prompt.md` exists
   - `skills/pathfinder/tier1-analyzer-prompt.md` exists
   - `skills/pathfinder/tier2-analyzer-prompt.md` exists
   - `skills/pathfinder/synthesis-prompt.md` exists
   - `skills/pathfinder/query-handler-prompt.md` exists
   - `skills/pathfinder/SKILL.md` exists
   - All `crucible:` references in new content point to existing skill directories

7. **README accuracy:**
   - `pathfinder` appears in the skill table
   - Description matches actual skill behavior
