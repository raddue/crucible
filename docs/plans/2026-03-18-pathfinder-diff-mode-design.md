# Pathfinder Diff Mode — Topology Change Detection

**Date:** 2026-03-18
**Status:** Design approved
**Branch:** worktree-pathfinder-diff

## Overview

Adds a fourth mode to the pathfinder skill — **diff mode** — which compares a current topology scan against a baseline to surface structural drift: new services, severed edges, confidence changes, cluster restructuring. Transforms pathfinder from a snapshot tool into a change-detection system.

**Primary use case:** Weekly drift check — "What changed in our service graph since last scan?" Answerable in minutes against orgs with 1000+ repos.

**Three invocation forms:**

```
# Full-scan diff: rescan org, compare against persisted topology
crucible:pathfinder diff <org>

# Crawl diff: re-crawl from seed, compare against persisted crawl topology
crucible:pathfinder diff <org>/<repo> [--depth N] [--orgs org1,org2]

# File comparison: compare any two topology files (no rescanning)
crucible:pathfinder diff --baseline path/old.json --current path/new.json
```

The distinction between full-scan diff and crawl diff is natural: org name only = full-scan, org/repo (seed) = crawl. File comparison uses explicit flags.

**Common options:**
- `--tier 2` — run deep code scan during rescan (default: Tier 1 only)

## Smart Rescan Strategy

Diff mode's rescan is optimized for speed — it doesn't re-analyze the entire org from scratch.

### Full-Scan Diff Rescan

1. **Discovery:** `gh repo list <org>` to get current repo metadata including `pushedAt` timestamps
2. **Delta detection:** Compare `pushedAt` against baseline topology's `metadata.last_push` per service. Repos unchanged since last scan skip Tier 1 — reuse cached per-repo JSON from `/tmp/pathfinder/<org>/repos/`.
3. **Selective Tier 1:** Only re-analyze repos that were pushed since the baseline scan, plus any newly discovered repos. Clone only new/changed repos.
4. **Synthesis:** Merge reused + fresh per-repo results into a new topology.
5. **Diff:** Compare new topology against baseline.

### Crawl Diff Rescan

Same `pushedAt` optimization applies. Re-crawl from seed, but skip Tier 1 for unchanged repos at each depth level. Reverse search always re-runs (org-wide code references may have changed even if the target repo didn't).

### User Gates (Streamlined)

- No discovery confirmation (you already know the org)
- No Tier 1 checkpoint (diff is meant to be quick)
- Confirm before cloning repos not seen in the baseline (genuinely new services)
- Crawl diff: checkpoint after each depth level (inherited from crawl mode)

The rescan updates the persisted `topology.json` as a side effect — running diff keeps your topology fresh. The diff artifacts are the delta between old and new.

## Diff Algorithm & Change Categories

The diff agent receives baseline and current topology JSON and produces a structured change report.

### Service Changes (matched by `name`)

| Change | Detection |
|--------|-----------|
| Added | In current, not in baseline |
| Removed | In baseline, not in current |
| Reclassified | Same name, different `type` |
| Confidence changed | Same name, different `confidence` |

### Edge Changes (matched by identity: `source + target + type + label`)

| Change | Detection |
|--------|-----------|
| Added | New edge not in baseline |
| Removed | Baseline edge not in current |
| Confidence upgraded | Same identity, confidence increased (e.g., MEDIUM -> HIGH) |
| Confidence degraded | Same identity, confidence decreased |
| Evidence changed | Same identity, evidence array differs (new files found, old files gone) |

### Cluster Changes (matched by `name`)

| Change | Detection |
|--------|-----------|
| New cluster | Didn't exist in baseline |
| Dissolved | Existed in baseline, gone now |
| Membership changed | Same cluster, different service set (with specific adds/removes) |

### Crawl-Specific Changes (additional, only for crawl diffs)

| Change | Detection |
|--------|-----------|
| Importance score changed | Same repo, different importance score |
| Discovery path changed | Same repo, different `found_via` signal |
| Depth changed | Same repo, discovered at different depth on re-crawl |
| Signal diversity changed | Same repo, different `signal_sources` array |

### Summary Metrics

- Net service/edge/cluster count deltas
- Coverage distribution shifts (HIGH/MEDIUM/LOW)
- Crawl diffs: total importance score shift, frontier expansion/contraction

## Output Artifacts

**Full-scan diff output:** `docs/pathfinder/<org>/diffs/YYYY-MM-DD/`

**Crawl diff output:** `docs/pathfinder/<org>/crawl-<seed-repo>/diffs/YYYY-MM-DD/`

**File comparison output:** `docs/pathfinder/manual-diffs/YYYY-MM-DD/`

### 1. `topology-diff.json` — Machine-Readable Structured Diff

```json
{
  "meta": {
    "baseline_timestamp": "2026-03-11T14:30:00Z",
    "current_timestamp": "2026-03-18T14:30:00Z",
    "mode": "full-scan",
    "org": "acme-platform",
    "repos_rescanned": 47,
    "repos_reused": 38,
    "repos_changed": 9
  },
  "services": {
    "added": [{ "name": "acme/new-gateway", "type": "API" }],
    "removed": [{ "name": "acme/old-proxy", "type": "API" }],
    "reclassified": [{ "name": "acme/jobs-runner", "old_type": "Unknown", "new_type": "Worker" }],
    "confidence_changed": [{ "name": "acme/alerts-api", "old": "MEDIUM", "new": "HIGH" }]
  },
  "edges": {
    "added": [{ "source": "...", "target": "...", "type": "HTTP" }],
    "removed": [],
    "confidence_upgraded": [{ "edge": {}, "old": "MEDIUM", "new": "HIGH" }],
    "confidence_degraded": [],
    "evidence_changed": []
  },
  "clusters": {
    "new": [],
    "dissolved": [],
    "membership_changed": [{ "name": "orders-cluster", "added": [], "removed": [] }]
  },
  "summary": {
    "services_delta": "+1 / -1 / 2 reclassified",
    "edges_delta": "+3 / -1 / 2 confidence changes",
    "clusters_delta": "+0 / -0 / 1 membership change"
  }
}
```

### 2. `diff-report.md` — Human-Readable with Mermaid

- Summary table of all changes
- Mermaid diagram with visual diff: added edges in green (`style` directives), removed edges in red (dashed + red), confidence changes in yellow
- Per-change detail with evidence (which file changed, what was the old/new value)
- Crawl diffs: discovery tree comparison showing which repos appeared/disappeared at each depth

### 3. `diff-log.json` — Scan Metadata

- Per-repo: rescanned vs reused, timing, errors
- Rate limit usage
- `pushedAt` deltas that triggered re-analysis

### Persistence

`~/.claude/memory/pathfinder/<org>/latest-diff.json` — overwritten each run with the `topology-diff.json` contents. Consuming skills check this file opportunistically.

## State Management & Compaction Recovery

**State file:** `/tmp/pathfinder-state.json` with `"mode": "diff"`

```json
{
  "mode": "diff",
  "diff_type": "full-scan",
  "org": "acme-platform",
  "phase": "rescan-tier1",
  "baseline_path": "~/.claude/memory/pathfinder/acme-platform/topology.json",
  "baseline_timestamp": "2026-03-11T14:30:00Z",
  "repos_total": 47,
  "repos_rescanned": ["acme/orders-api", "acme/new-gateway"],
  "repos_reused": ["acme/auth-service"],
  "repos_remaining": ["acme/payments-service"],
  "clone_paths": {}
}
```

Crawl diff state adds `seed`, `orgs`, `max_depth`, `current_depth`, `frontier` — same fields as crawl mode, nested under `"diff_type": "crawl"`.

**Phases:** `pre-flight` -> `discovery` -> `rescan-tier1` -> `rescan-tier2` (if opted in) -> `synthesis` -> `diff` -> `report`

**Compaction recovery:** Read state file, branch on `mode: "diff"`. Resume from current phase. Per-repo results on disk survive compaction. The baseline topology is always available at the persistence path (never modified mid-run — only updated after synthesis completes).

## Error Handling

| Error | Response |
|-------|----------|
| No baseline topology exists | Stop: "No topology data for `<org>`. Run `crucible:pathfinder <org>` first." |
| Baseline topology is corrupt/unparseable | Stop with clear message, suggest re-running full scan |
| `pushedAt` not available for a repo | Conservative: re-analyze that repo (don't skip) |
| All repos unchanged (zero delta) | Report "No structural changes detected since [baseline timestamp]." Still produce artifacts (empty diff). |
| Partial rescan failure (some repos error) | Skip errored repos, flag in diff-log.json, note in report: "N repos could not be rescanned — changes in those repos may be missed" |
| File comparison with mismatched orgs | Warn: "Baseline covers orgs [A, B], current covers [A, C]. Diff will only cover overlapping org [A]." |

## Integration with Consuming Skills

No mandatory changes to any existing skill. Integration is additive and opportunistic.

**New well-known path:** `~/.claude/memory/pathfinder/<org>/latest-diff.json`

**Consuming skill pattern (same for all three):**

```
If latest-diff.json exists AND its current_timestamp is within 7 days:
  Read and incorporate change awareness
Else:
  Proceed without diff data (existing behavior, no degradation)
```

- **Build skill:** Refactor mode blast radius gains cross-repo change awareness. "This refactoring also affects 3 services in other repos that recently changed their edges to this service."
- **Design skill:** Investigation agents get instant topology change context. "Services X and Y depend on this service. Edge to X was added recently — may be unstable."
- **Audit skill:** Subsystem scoping gains neighbor change awareness. "This subsystem gained 2 new consumers since last week. Consider widening audit scope."
- **Query mode:** Unchanged. Queries run against `topology.json` which is updated by the rescan.

Note: The actual skill file edits to build/design/audit are out of scope for this implementation — they're single-line additions that can be done later. This design documents the integration contract (`latest-diff.json` schema and path) so the door is open.

## Subagent Dispatch

Diff mode adds one new agent and reuses existing ones:

| Agent | Model | Dispatch | Prompt Template | Purpose |
|-------|-------|----------|-----------------|---------|
| Discovery Classifier | Sonnet | Task tool | `./discovery-classifier-prompt.md` (reused) | Re-enumerate repos during rescan |
| Tier 1 Analyzer | Sonnet | Agent tool (Explore) | `./tier1-analyzer-prompt.md` (reused) | Re-analyze changed repos |
| Reverse Searcher | Sonnet | Agent tool | `./reverse-search-prompt.md` (reused) | Crawl diff reverse search |
| Synthesis Agent | Opus | Agent tool | `./synthesis-prompt.md` (reused) | Produce new topology from merged results |
| **Diff Analyzer** | **Sonnet** | **Task tool** | **`./diff-analyzer-prompt.md` (NEW)** | Compare baseline vs current topology, produce structured diff |

The Diff Analyzer is lightweight — it receives two JSON objects and computes set differences. Sonnet is sufficient; no codebase exploration needed. Single dispatch, no parallelism.

**Execution order:** Pre-flight -> Discovery -> Selective Tier 1 (parallel waves) -> Synthesis -> Diff Analyzer -> Report

## Acceptance Criteria

(Numbered 23-34, continuing from crawl mode's 12-22)

23. Given an org with persisted topology data, `pathfinder diff <org>` produces a structured diff report showing services added, removed, and reclassified since the last scan
24. Given an org where only 10 of 100 repos have been pushed since the baseline, only those 10 repos are re-analyzed (smart rescan via `pushedAt`)
25. Given a crawl seed with persisted crawl topology, `pathfinder diff <org>/<repo>` re-crawls and produces a diff including crawl-specific changes (importance, discovery path, depth)
26. Given two topology files, `pathfinder diff --baseline A --current B` produces a diff without rescanning
27. Given an org with no prior topology data, diff mode stops with a clear message directing the user to run a full scan first
28. Given a rescan where no structural changes occurred, diff mode reports "No structural changes detected" and produces empty diff artifacts
29. Diff output Mermaid diagram visually distinguishes added (green), removed (red), and changed (yellow) edges
30. The rescan updates the persisted `topology.json` as a side effect, keeping the queryable store fresh
31. `latest-diff.json` is written to the well-known persistence path and is consumable by other skills
32. Diff state survives compaction and resumes correctly from the current phase
33. Crawl diffs respect depth checkpoints and do not stale-mark repos absent from the re-crawl
34. Timestamped output directories accumulate diff history across multiple runs

## Future Enhancements

- **Scheduled diffs:** Integration with a cron or CI system to run diffs automatically on a cadence
- **Diff-triggered alerts:** Configurable rules (e.g., "alert if a new shared-db edge appears") that flag high-impact changes
- **Multi-seed crawl diffs:** Diff across multiple crawl seeds simultaneously to detect cross-cluster drift
- **Trend analysis:** Aggregate diff history over time to show topology evolution (service count growth, edge churn rate)
