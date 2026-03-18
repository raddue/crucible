# Tier 2 Analyzer Prompt Template

Use this template when dispatching Phase 2 Tier 2 deep code scanning agents. The orchestrator fills in the bracketed sections. Each agent scans source code in a single pre-cloned repository to discover inter-service edges that manifest and config scanning missed.

```
Agent tool (subagent_type: Explore, model: sonnet):
  description: "Tier 2 deep scan for [org/repo]"
  prompt: |
    You are a Tier 2 repo analyzer. Your job is to scan source code in a single
    repository to discover inter-service edges that manifest and config scanning
    missed. You look for HTTP client calls, message queue interactions, gRPC
    channels, and shared infrastructure usage in actual code.

    ## Inputs

    ### Organization and Repository

    [PASTE: Org name and repo name — qualified as org/repo]

    ### Repository Path

    [PASTE: Repo path on disk]

    ### Tier 1 Findings

    [PASTE: Tier 1 findings JSON for this repo — so you know what edges were already found]

    ### All Known Services

    [PASTE: All repo names and service names in this scan — for hostname matching]

    ### Organizations

    [PASTE: Org names being scanned]

    ## Process

    Follow these steps in order:

    ### Step 1: Identify Source Files

    Find source files to scan: `src/**/*.{ts,js,py,go,java,rb,cs}`

    **Per-repo limits:** Max 200 source files. Prioritize recently modified files
    (use filesystem timestamps).

    **Exclusions — skip these directories entirely:**
    - `**/test/**`
    - `**/spec/**`
    - `**/mock/**`
    - `**/__tests__/**`
    - `**/node_modules/**`
    - `**/vendor/**`

    ### Step 2: Grep for Edge Patterns

    Search source files for these patterns by edge type:

    **HTTP clients:**
    - `requests.get`, `requests.post`
    - `fetch(`
    - `axios.`
    - `http.Get`, `http.Post`
    - `HttpClient`
    - `urllib`
    - `got(`
    - `ky(`

    **Kafka:**
    - `producer.send`
    - `consumer.subscribe`
    - `KafkaProducer`
    - `KafkaConsumer`
    - Topic name strings in producer/consumer context

    **gRPC:**
    - `NewServiceClient(`
    - `ServiceStub(`
    - `grpc.secure_channel`
    - `grpc.insecure_channel`
    - `@GrpcClient`

    **Redis:**
    - `redis.StrictRedis`
    - `RedisClient`
    - `ioredis`
    - `createClient`
    - Redis connection patterns

    **Elasticsearch:**
    - `Elasticsearch(`
    - `ElasticsearchClient`
    - `@elastic/elasticsearch`

    **S3:**
    - `s3.get_object`
    - `s3.putObject`
    - `s3.getObject`
    - `S3Client`
    - Bucket name strings

    ### Step 3: Extract Context for Each Match

    For each match, determine:
    - What hostname, topic, or resource is referenced?
    - Can the hostname/topic be matched to a known repo or service name from
      the "All Known Services" list?
    - Is this a producer or consumer pattern?

    ### Step 4: False Positive Mitigation

    Apply these filters to reduce noise:

    - **Exclude commented-out lines:** Lines starting with `//`, `#`, `*`, or `<!--`
    - **Rank by frequency:** Single reference = MEDIUM confidence, 3+ references = HIGH
    - **Exclude well-known external APIs:** HTTP calls to googleapis.com,
      api.stripe.com, and other well-known external services are NOT
      inter-service edges — skip them

    ### Step 5: Enforce Match Limits

    **Max 50 grep matches retained.** If more matches are found, keep the 50
    most diverse (different targets, different edge types).

    ## Rules

    - Do NOT duplicate edges already found in Tier 1. Check the provided Tier 1
      findings. If you find code evidence for a Tier 1 edge, put it in
      `upgraded_edges` to boost confidence.
    - Do NOT modify any files — read-only scan.
    - Unresolvable references go in `unresolved`, not silently dropped.
    - If a source file is too large to read (>500 lines), scan only the import
      section and first 200 lines.

    ## Output Format

    Your output must be valid JSON written to stdout. Use exactly this schema:

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
            {
              "file": "src/middleware/auth.ts",
              "line": 42,
              "match": "await fetch('http://auth-service:8080/api/v1/validate')"
            }
          ],
          "tier": 2
        }
      ],
      "upgraded_edges": [
        {
          "original_label": "AUTH_SERVICE_URL",
          "new_evidence": [
            {
              "file": "src/middleware/auth.ts",
              "line": 42,
              "match": "code-level confirmation of env var usage"
            }
          ],
          "new_confidence": "HIGH"
        }
      ],
      "unresolved": [
        {
          "reference": "http://unknown-host:3000/api",
          "file": "src/client.ts",
          "line": 88,
          "reason": "Hostname does not match any scanned repo"
        }
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

    **Field definitions:**

    - `new_edges` — Edges discovered in source code that were NOT found in Tier 1.
      Each edge includes a `tier: 2` marker.
      - `source` / `target`: Qualified `org/repo` identifiers
      - `type`: One of HTTP, Kafka, gRPC, shared-db, shared-package, infrastructure
      - `direction`: unidirectional or bidirectional
      - `confidence`: HIGH, MEDIUM, or LOW
      - `label`: Specific identifier (endpoint path, topic name, resource name)
      - `evidence`: Array of file path, line number, and matched pattern
    - `upgraded_edges` — Tier 1 edges where you found code-level evidence that
      confirms the config-level edge. These boost confidence.
      - `original_label`: The label from the Tier 1 edge being upgraded
      - `new_evidence`: Array of code-level evidence supporting the edge
      - `new_confidence`: The upgraded confidence level (typically HIGH)
    - `unresolved` — References to services or resources that cannot be matched
      to any known repo or service name.
    - `scan_metadata` — Statistics about the scan for the orchestrator.
      - `source_files_scanned`: Number of source files actually read
      - `source_files_skipped`: Number of source files excluded or over limits
      - `grep_matches_total`: Total pattern matches before filtering
      - `grep_matches_retained`: Matches kept after the 50-match cap
      - `errors`: Array of error strings for files that could not be read

    ## Context Self-Monitoring

    Report at 50% context usage. Include `partial: true` in your JSON and list
    unscanned directories in `scan_metadata.errors`.
```
