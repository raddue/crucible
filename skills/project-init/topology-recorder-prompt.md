<!-- DISPATCH: disk-mediated | This template is written to a dispatch file,
     not pasted into the Agent tool prompt. See shared/dispatch-convention.md -->

# Topology Recorder — Dispatch Template

Dispatch a Sonnet subagent during Tier 2 fan-in to synthesize neighbor scan results into a cross-repo topology map.

```
Task tool (general-purpose, model: sonnet):
  description: "Topology recording — synthesizing [N] neighbor scans"
  prompt: |
    You are a topology recorder. Your job is to synthesize neighbor scan
    results into a cross-repo topology map. You produce a summary with
    dependency graph and per-neighbor detail files for meaningfully
    connected repos.

    ## Neighbor Scan Results

    [PASTE: File paths to neighbor scan results on disk — e.g.,
     /tmp/crucible-project-init/neighbors/auth-service.md]

    ## Current Repository

    [PASTE: Current repo name, ecosystem, purpose]

    ## Relevance Scores

    [PASTE: Relevance scores from orchestrator — per neighbor:
     high/medium/low with reason]

    ## Existing Topology Data

    [PASTE: Existing topology data, if any. Say "No prior topology
     data." if first run]

    ## Output Directory

    [PASTE: Output directory for topology files — e.g., memory/topology/]

    ## Your Job

    1. Read each neighbor scan result from the provided file paths
    2. Filter by relevance: include high and medium neighbors in the
       summary table; exclude low (note them in Unmapped section)
    3. Build the dependency digraph from connection data — label each
       edge with connection type (gRPC, REST, file import, shared DB,
       docker-compose, etc.)
    4. Extract contracts — explicit or implicit agreements between repos
       (API versions, auth mechanisms, shared schema constraints).
       Contracts are things that would break if changed unilaterally —
       not features, not descriptions
    5. Produce topology.md and per-neighbor detail files (high/medium
       neighbors only)

    If no neighbors have high or medium relevance, produce a minimal
    topology.md noting "No meaningfully connected neighbors detected."

    ## Output Format

    ### File: topology.md

    Hard cap: 200 lines.

    ```markdown
    <!-- project-init:structural -->
    # Topology

    ## Current Repository
    [name], [ecosystem], [purpose — 1 line]

    ## Neighbors

    | Repo | Ecosystem | Purpose | Connection | Location |
    |------|-----------|---------|------------|----------|
    | ... | ... | ... | ... | ... |

    ## Dependency Graph

    ```dot
    digraph { current -> neighbor [label="connection type"]; ... }
    ```

    ## Contracts
    - [explicit or implicit agreements between repos]

    ## Unmapped
    - [low-relevance neighbors with reason]
    - [inaccessible repos with reason]

    ## Last Updated
    [today's date]
    ```

    ### File: <name>.md (one per high/medium neighbor)

    Hard cap: 100 lines each. Do NOT create detail files for
    low-relevance neighbors.

    ```markdown
    <!-- project-init:structural -->
    # [Repo Name]

    **Path:** [relative path]
    **Ecosystem:** [language/framework]
    **Purpose:** [one sentence]
    **Connection Strength:** high | medium

    ## Exposed Interfaces
    - [from neighbor scan]

    ## Connection Details
    - [how it connects, what contracts exist]

    ## Shared Dependencies
    - [common libraries, shared schemas]

    ## Last Updated
    [today's date]
    ```

    ## Re-invocation Merge Rules

    When topology data already exists from a prior run:

    - **Structural-tagged content** (`<!-- project-init:structural -->`):
      overwrite with fresh data
    - **Task-verified content** (if any): preserve — do not overwrite
      content that has been verified by a task agent
    - **New neighbors:** add with structural tag
    - **Missing neighbors** (present in prior data but absent from
      current scan): flag with `[STALE?]`, do not remove

    ## Rules

    - Relevance filtering is critical — do NOT include low-relevance
      neighbors in the summary table or create detail files for them
    - Contracts section should capture things that would break if
      changed unilaterally — not features, not descriptions
    - Digraph edges must be labeled with connection type (gRPC, REST,
      file import, shared DB, docker-compose, etc.)
    - Record OBSERVED FACTS from the neighbor scans. Not speculation,
      not "this might connect to..."
    - Target 70% of line caps — leave room for task-verified additions.
      topology.md: target 140 lines, hard cap 200. Detail files: target
      70 lines, hard cap 100
    - If exceeding limits, compress entries — do not split files
    - Include "Last Updated" with today's date on every file you produce

    ## Context Self-Monitoring

    If you reach 50%+ context utilization with scan results remaining,
    write what you have to disk and report which neighbors still need
    processing.
```
