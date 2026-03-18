# Synthesis Subagent Prompt Template

Use this template when dispatching the Phase 3 synthesis agent. The orchestrator fills in the bracketed sections with paths to per-repo JSON results, tier depth, output directories, and any existing topology data for incremental merging.

```
Agent tool (subagent_type: general-purpose, model: opus):
  description: "Synthesize topology for [org names]"
  prompt: |
    You are a topology synthesis agent. Your job is to cross-reference
    per-repo analysis results, resolve dependency edges, detect service
    clusters, and generate the final topology artifacts: JSON, Mermaid
    diagrams, and a human-readable report.

    ## Org Names

    [PASTE: Org names being synthesized]

    ## Per-Repo Result Files

    [PASTE: File paths to per-repo JSON results — e.g., /tmp/pathfinder/acme-platform/repos/orders-api.json]

    ## Tier Depth

    [PASTE: Tier depth — 1 or 2, so you know whether Tier 2 data exists]

    ## Output Directory

    [PASTE: Output directory — e.g., docs/pathfinder/acme-platform/]

    ## Persistence Path

    [PASTE: Persistence path — e.g., ~/.claude/memory/pathfinder/acme-platform/]

    ## Existing Topology (Incremental Run)

    [PASTE: Existing topology.json if incremental run — or "No prior topology data."]

    ## Crawl Metadata (Crawl Mode Only)

    [PASTE: If mode is "crawl", paste the following. If mode is "full-scan", paste "N/A — full scan mode."]

    - `"mode": "crawl"` — indicates this synthesis is for crawl mode results
    - `"seed": "<org>/<repo>"` — the starting repo for the crawl
    - `"crawl_metadata"` — a JSON map of `repo -> {depth, found_via, importance, signal_sources}` extracted from the state file's discovered map. Example:
      ```json
      {
        "acme/funding-api": { "depth": 0, "found_via": "seed", "importance": 10, "signal_sources": [] },
        "acme/payments-service": { "depth": 1, "found_via": "forward:env_var:PAYMENTS_SERVICE_URL", "importance": 8, "signal_sources": [{"type": "env_var", "source_repo": "acme/funding-api"}] }
      }
      ```

    ## Your Job

    Read all per-repo result files from the provided paths, then execute
    the following steps in order.

    ### Step 1: Build the Service Inventory

    Create a unified list of all services across all orgs with their
    classifications. Every service name must be qualified as `org/repo`
    to avoid cross-org collisions.

    **Timestamp preservation:** When building the service inventory, preserve
    the `metadata.last_push` field exactly as provided by the Tier 1 analyzer.
    This must be a full ISO 8601 timestamp (e.g., `"2026-03-15T10:30:00Z"`).
    Do not truncate to date-only format. Downstream diff mode depends on
    timestamp precision for change detection.

    ### Step 2: Edge Resolution — Producer/Consumer Matching

    For each edge found in the per-repo results:

    1. **Verify both endpoints exist.** Both `source` and `target` must
       be present in the service inventory. Drop edges with missing
       endpoints into the unresolved list with a reason.

    2. **Apply the edge identity rule.** Two edges are the same if they
       share the same `source + target + type + label`. When merging
       duplicate edges:
       - Confidence takes the max of the duplicates
       - Evidence arrays are unioned (no duplicate evidence entries)
       - Direction is flagged if contradictory across duplicates

    3. **Deduplicate.** Multiple evidence points for the same logical
       edge merge into one edge with accumulated evidence.

    ### Step 3: Cluster Detection

    Detect service clusters using this algorithm:

    1. **Monorepo clusters** — Services within the same monorepo always
       form a cluster, named after the repo.

    2. **Affinity clusters** — Services that share 2+ edges of any type
       form a candidate cluster. Use connected components on the subgraph
       of services with 2+ shared edges.

    3. **Naming** — Clusters are named after their most-connected service
       or shared resource (e.g., "orders-cluster" if `orders-api` has the
       most edges).

    4. **Singletons** — Services with no cluster affinity appear as
       standalone nodes.

    Clusters are always recomputed from scratch on the full edge set.

    **Crawl mode cluster weighting (only when crawl_metadata is provided):**
    When importance scores are available from crawl_metadata, use them to
    influence cluster detection: high-importance repos (score 7+) that share
    even a single edge should be considered for clustering (lower the 2-edge
    threshold to 1 for high-importance pairs). Name clusters after the
    highest-importance service rather than most-connected, since importance
    reflects structural significance in the discovered subgraph.

    **Crawl mode Mermaid styling (only when crawl_metadata is provided):**
    In the Mermaid diagram, indicate importance visually: high-importance
    repos (score 7+) get bold node borders using `style` directives,
    medium-importance (3-6) get normal borders, and low-importance (1-2)
    get dashed borders. Include the depth level in node labels (e.g.,
    `orders-api [d1]` for depth 1).

    ### Step 4: Incremental Merge (if existing topology provided)

    If existing topology data was provided above, merge as follows:

    - **New repos:** Add with `status: "active"`
    - **Removed repos:** Set `status` to `"stale"`, keep for one more
      run, then remove
    - **Existing repos:** Update classification and edges; confidence
      takes the max of old/new
    - **Edge merge:** Match by `source + target + type + label`;
      confidence takes max, evidence is unioned, direction flagged if
      contradictory
    - **Clusters:** Always recomputed from scratch on the merged edge set

    **Crawl-mode merge exception:** When the mode is "crawl", do NOT mark repos
    absent from the crawl results as "stale". Crawl results are intentionally
    partial (only discovered repos). Stale-marking only applies when mode is
    "full-scan" (which is comprehensive). Crawl provenance is preserved as a
    `crawl_metadata` section in topology.json that coexists with full scan data.

    If the existing topology field says "No prior topology data.", skip
    this step entirely.

    ### Step 5: Generate Output Artifacts

    Write ALL of the following files. Use the output directory provided
    above.

    #### File: `topology.json` — Source of Truth

    Follow this exact schema:

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
      "services": [
        {
          "name": "org/repo",
          "repo": "org/repo",
          "org": "org-name",
          "type": "API",
          "language": "TypeScript",
          "framework": "Express",
          "confidence": "HIGH",
          "status": "active",
          "metadata": { "topics": [], "last_push": "2026-03-15T10:30:00Z" }
        }
      ],
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
      "clusters": [
        {
          "name": "orders-cluster",
          "services": ["org/orders-api", "org/orders-worker", "org/orders-common"],
          "description": "Core order processing pipeline"
        }
      ]
    }
    ```

    **Crawl mode addition to topology.json (only when crawl_metadata is provided):**
    Add a `"crawl_metadata"` top-level field to topology.json preserving the seed, depth, found_via, importance, and signal_sources for each discovered repo. This section is additive and does not conflict with full scan data.

    Write topology.json to BOTH the output directory AND the persistence
    path.

    #### File: `topology.mermaid.md` — Full Org Graph

    Generate a Mermaid diagram with these conventions:

    - **Node shapes by service type:**
      - API: rectangle `[name]`
      - Worker: stadium `([name])`
      - Frontend: hexagon `{{name}}`
      - Serverless: subroutine `[[name]]`
      - Library: circle `((name))`
      - Infrastructure: cylinder `[(name)]`
      - Tool: trapezoid `[/name/]`
      - Unknown: default rectangle `[name]`

    - **Edge styles by confidence:**
      - HIGH confidence: solid line `-->`
      - MEDIUM confidence: dashed line `-.->`
      - LOW confidence: dotted line `....>`

    - **Edge labels:** Communication type (HTTP, Kafka, gRPC, etc.)

    - **Monorepo services:** Grouped in `subgraph` blocks named after
      the repo

    - **For 30+ services:** Render at cluster level with one node per
      cluster and edges between clusters showing multiplicity. Generate
      per-cluster detail diagrams separately.

    #### File: `clusters/<cluster-name>.mermaid.md` — Per-Cluster Diagrams

    One Mermaid file per detected cluster. Each shows:
    - All services within the cluster with typed node shapes
    - Internal edges between cluster members
    - External edges to/from services outside the cluster

    #### File: `report.md` — Human-Readable Summary

    Include these sections:

    - **Service Inventory** — Table with columns: Name, Type, Language,
      Org, Confidence
    - **Dependency Matrix** — Which service calls which, by edge type
    - **Cluster Descriptions** — Each cluster with its services, purpose,
      and embedded Mermaid diagram
    - **Flagged Items** — LOW-confidence classifications, unresolved
      edges from per-repo results, scan errors
    - **Recommendations** — Suggestions for further investigation
      (unknown services, low-confidence edges, unresolved references)

    **Crawl mode additions to report.md (only when mode is "crawl"):**
    - **Discovery Path** — a tree visualization showing: seed -> depth 1 repos -> depth 2 repos, with the discovery signal that led to each repo (e.g., "found via forward:env_var:PAYMENTS_SERVICE_URL")
    - **Importance Heatmap** — repos listed by importance score, used to weight cluster detection and size Mermaid nodes proportionally
    - **Reverse Search Coverage** — which orgs were searched, which had code search available, how many signals were searched per repo

    #### File: `scan-log.json` — Scan Metadata

    Include: per-repo timing, errors encountered, skipped repos, rate
    limit usage during the scan.

    ## Rules

    - Every service name must be qualified as `org/repo` to avoid
      cross-org collisions
    - Do NOT invent edges — only include edges with evidence from the
      per-repo results
    - Unresolved references from per-repo results should be collected
      into the report's "Flagged Items" section
    - Mermaid diagrams must render correctly — keep syntax simple, quote
      labels that contain special characters
    - If the full Mermaid graph would exceed ~100 nodes, render at
      cluster level only and generate per-cluster detail diagrams

    ## Context Self-Monitoring

    If you reach 50%+ context utilization with artifacts remaining,
    prioritize output in this order:

    1. `topology.json` first (source of truth — most critical)
    2. `report.md` second (human-readable findings)
    3. Mermaid diagrams last (visual aids)

    Write each artifact to disk as soon as it is completed. Do not
    buffer all artifacts in memory — write incrementally so that
    partial results survive if context is exhausted.
```
