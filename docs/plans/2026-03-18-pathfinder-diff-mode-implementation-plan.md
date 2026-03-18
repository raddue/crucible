# Pathfinder Diff Mode — Implementation Plan

**Date:** 2026-03-18
**Design:** 2026-03-18-pathfinder-diff-mode-design.md
**Branch:** worktree-pathfinder-diff

---

## Task 1: Timestamp Standardization in Tier 1 Analyzer and Synthesis Prompts

**Complexity:** Low
**Files:** 2 files
- `skills/pathfinder/tier1-analyzer-prompt.md`
- `skills/pathfinder/synthesis-prompt.md`
**Dependencies:** None

This is the first prerequisite identified in the design doc (acceptance criteria 37-40 prerequisite note). The diff mode's smart rescan compares `pushedAt` (full ISO 8601 from GitHub API) against `metadata.last_push` in topology.json. If `last_push` is a date-only string like `"2026-03-15"`, the comparison `pushedAt > last_push` produces incorrect results.

### Changes to `tier1-analyzer-prompt.md`

1. In the **Required Output Format** section, find the example JSON block. Change the `last_push` value from `"2026-03-15"` to `"2026-03-15T10:30:00Z"`.

2. Add an explicit instruction below the `metadata` field description in the output schema. After the existing JSON example block (around line 134), add a callout:

```
**Timestamp format:** The `last_push` field MUST be a full ISO 8601 timestamp
(e.g., `"2026-03-15T10:30:00Z"`), NOT a date-only string. Use the repo's
`pushedAt` value from the GitHub API metadata passed in your classification
input. If `pushedAt` is not available in the classification, run
`gh api repos/{org}/{repo} --jq '.pushed_at'` to retrieve it.
```

### Changes to `synthesis-prompt.md`

1. In the **topology.json schema** example (Step 5), find the `"last_push": "2026-03-15"` value in the services array example. Change it to `"2026-03-15T10:30:00Z"`.

2. Add an instruction in the **Step 1: Build the Service Inventory** section:

```
**Timestamp preservation:** When building the service inventory, preserve
the `metadata.last_push` field exactly as provided by the Tier 1 analyzer.
This must be a full ISO 8601 timestamp (e.g., `"2026-03-15T10:30:00Z"`).
Do not truncate to date-only format. Downstream diff mode depends on
timestamp precision for change detection.
```

### Verification

After this task, both example JSON blocks show ISO 8601 timestamps for `last_push`, and both prompts contain explicit instructions to agents about the required format.

---

## Task 2: Per-Repo Persistence in SKILL.md (Full Scan and Crawl Modes)

**Complexity:** Medium
**Files:** 1 file
- `skills/pathfinder/SKILL.md`
**Dependencies:** None

This is the second prerequisite (acceptance criteria 37). Currently, per-repo JSON results are written to `/tmp/pathfinder/<org>/repos/<repo-name>.json` only. Diff mode's smart rescan needs to load per-repo results across sessions (weekly cadence), but `/tmp` does not survive between sessions. All modes must also write per-repo results to a durable persistence path.

### Changes to `SKILL.md`

1. **Scratch and State section** (around line 101): Add a new bullet point after the existing per-repo results line:

```
- **Per-repo persistence:** `~/.claude/memory/pathfinder/<org>/repos/<repo-name>.json`
  -- durable copy of per-repo results. Written alongside the `/tmp/` copy after
  each Tier 1/Tier 2 analysis completes. Used by diff mode's smart rescan to
  skip re-analysis of unchanged repos across sessions.
```

2. **Phase 2: Tier 1 Analysis section** (around line 180): After the line `**Per-repo results:** Written to /tmp/pathfinder/<org>/repos/<repo-name>.json immediately on agent completion.`, add:

```
**Per-repo persistence:** After writing to `/tmp/`, also copy each per-repo result to `~/.claude/memory/pathfinder/<org>/repos/<repo-name>.json`. This durable copy survives across sessions and is read by diff mode's smart rescan. The orchestrator performs this copy — subagents are unaware of the persistence path.
```

3. **Phase 2: Tier 2 Analysis section** (around line 220): After the line about updated per-repo JSON files written to disk, add the same persistence instruction:

```
**Per-repo persistence:** After Tier 2 merging updates the per-repo JSON in `/tmp/`, also copy the updated file to `~/.claude/memory/pathfinder/<org>/repos/<repo-name>.json`.
```

4. **Crawl Mode: Crawl (Iterative Discovery) section** (around line 344): After the line about state file being updated after each repo completes, add:

```
- Per-repo persistence follows the same rule as full scan: after each Tier 1 analysis completes during crawl, copy the result to `~/.claude/memory/pathfinder/<org>/repos/<repo-name>.json`.
```

### Verification

After this task, full scan (Tier 1 and Tier 2) and crawl mode instructions all include the durable persistence write. An implementer running any pathfinder mode will produce per-repo JSON at both `/tmp/` and `~/.claude/memory/` paths.

---

## Task 3: Crawl Snapshot Persistence in SKILL.md

**Complexity:** Low
**Files:** 1 file
- `skills/pathfinder/SKILL.md`
**Dependencies:** None

This is the third prerequisite (acceptance criteria 38). Crawl diffs need a crawl-specific baseline separate from the merged `topology.json`. Crawl mode must write a snapshot after each crawl completes.

### Changes to `SKILL.md`

1. **Scratch and State section** (around line 101): Add a new bullet point:

```
- **Crawl snapshot:** `~/.claude/memory/pathfinder/<org>/crawl-<seed-repo>/snapshot.json`
  -- written after each crawl completes. Contains the crawl-specific topology
  with full `crawl_metadata` (importance scores, discovery paths, depth info).
  `<seed-repo>` is the short repo name only (e.g., `crawl-funding-api`, NOT
  `crawl-acme/funding-api`). Used as the baseline for crawl diff mode's
  crawl-specific change categories.
```

2. **Crawl Mode: Synthesis (Crawl) section** (around line 417): After the existing bullet about produces discovery path section in report.md, add a new bullet:

```
- **Crawl snapshot persistence:** After synthesis completes, write a crawl-specific snapshot to `~/.claude/memory/pathfinder/<org>/crawl-<seed-repo>/snapshot.json`. This file contains the full topology.json output from this crawl (including `crawl_metadata`) BEFORE merging with existing full-scan topology. The snapshot preserves crawl-specific data (importance, discovery paths, depth) that gets diluted in the merged topology.json. The `<seed-repo>` uses the short repo name (e.g., `funding-api`).
```

3. **Output Directories (Crawl) section** (around line 431): Add a new bullet for the snapshot path:

```
- **Crawl snapshot path:** `~/.claude/memory/pathfinder/<org>/crawl-<seed-repo>/snapshot.json` (durable, for crawl diff baselines)
```

### Verification

After this task, crawl mode instructions include writing the snapshot. The snapshot path convention is documented in both the Scratch/State section and the Output Directories section.

---

## Task 4: Add Diff Mode to SKILL.md — Mode Declaration, Invocation, and Model Table

**Complexity:** Medium
**Files:** 1 file
- `skills/pathfinder/SKILL.md`
**Dependencies:** Task 2, Task 3 (sequencing only — avoids concurrent edits to SKILL.md, not a logical dependency)

This task adds the top-level diff mode declaration to SKILL.md. It does NOT add the full diff procedure — that comes in later tasks. This task establishes the mode, invocation syntax, model assignments, and state schema so later tasks can reference them.

### Changes to `SKILL.md`

1. **Frontmatter description** (line 2): Update the description to mention diff mode. Change from `"Map a GitHub organization's service topology..."` to include topology change detection. Update the triggers list to include terms like `"what changed"`, `"topology drift"`, `"diff"`.

2. **Intro paragraph** (line 8): Update the opening paragraph to mention four modes instead of three.

3. **Three modes bullet list** (lines 14-17): Rename the section header concept from "Three modes" to "Four modes" and add:

```
- **Diff mode** — Compare a current topology scan against a baseline to surface structural drift: new services, severed edges, confidence changes, cluster restructuring. Transforms pathfinder from a snapshot tool into a change-detection system.
```

4. **Invocation section** (lines 19-22): Add diff mode invocations:

```
- Full-scan diff: `crucible:pathfinder diff <org>`
- Crawl diff: `crucible:pathfinder diff <org>/<repo> [--depth N] [--orgs org1,org2]`
- File comparison: `crucible:pathfinder diff --baseline path/old.json --current path/new.json`
```

Also add the common option:

```
Common diff options:
- `--tier 2` — run deep code scan during rescan (default: Tier 1 only)
```

5. **Model section** (lines 25-31): Add the Diff Analyzer:

```
- **Diff Analyzer (Diff mode):** Sonnet via Task tool (general-purpose)
```

6. **Scratch and State section**: Add the diff mode state schema alongside the existing full-scan and crawl schemas. Add the following after the crawl mode state schema:

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
```

Also update the state file discriminator description (around line 61) to include `"mode": "diff"` as a third option.

7. **Scratch and State section**: Add diff output directory entries:

```
- **Diff output (full-scan):** `docs/pathfinder/<org>/diffs/YYYY-MM-DD/`
- **Diff output (crawl):** `docs/pathfinder/<org>/crawl-<seed-repo>/diffs/YYYY-MM-DD/`
- **Diff output (file comparison):** `docs/pathfinder/manual-diffs/YYYY-MM-DD/`
- **Latest diff persistence:** `~/.claude/memory/pathfinder/<org>/latest-diff.json` — overwritten each run with the `topology-diff.json` contents. Consuming skills check this file opportunistically.
```

8. **Subagent Dispatch Summary table** (around line 622): Add the Diff Analyzer row:

```
| Diff Analyzer | Sonnet | Task tool (general-purpose) | `./diff-analyzer-prompt.md` |
```

9. **Prompt Templates list** (around line 633): Add:

```
- `./diff-analyzer-prompt.md` -- Diff mode comparison of baseline vs current topology
```

### Verification

After this task, SKILL.md declares diff mode as a fourth mode with correct invocation syntax, model assignments, state schema, and output paths. The actual procedure sections come in Tasks 6-9.

---

## Task 5: Create Diff Analyzer Prompt Template

**Complexity:** High
**Files:** 1 new file
- `skills/pathfinder/diff-analyzer-prompt.md`
**Dependencies:** None

Create the prompt template for the Diff Analyzer subagent. This agent receives two topology JSON objects (baseline and current) and produces a structured diff. It is dispatched via Task tool (Sonnet).

### File: `skills/pathfinder/diff-analyzer-prompt.md`

Create a new file with the following structure. Use the same formatting conventions as the existing prompt templates (e.g., `tier1-analyzer-prompt.md`):

```markdown
# Diff Analyzer — Prompt Template

Task tool (general-purpose, model: sonnet):

> "Diff topology for [org name]: baseline [timestamp] vs current [timestamp]"

---

## Identity

You are a topology diff analyzer. Your job is to compare a baseline topology
against a current topology and produce a structured change report identifying
every structural difference: added/removed services, new/severed edges,
confidence shifts, cluster restructuring, and rename detection.

---

## Inputs

### Diff Type

`[PASTE: "full-scan", "crawl", or "file-comparison"]`

### Baseline Topology JSON

`[PASTE: Full baseline topology.json contents]`

### Current Topology JSON

`[PASTE: Full current topology.json contents]`

### Crawl Baseline (Crawl Diff Only)

`[PASTE: If diff_type is "crawl", paste the crawl snapshot JSON from
~/.claude/memory/pathfinder/<org>/crawl-<seed-repo>/snapshot.json.
If not crawl diff, paste "N/A — not a crawl diff."]`

### Scan Metadata (Rescan Modes Only)

`[PASTE: JSON with repos_total, repos_reused, repos_rescanned counts
from the orchestrator's discovery phase. For file-comparison mode,
paste "N/A".]`

---

## Process

Execute these steps in order.

### Step 1: Service Diff

Compare the `services` arrays by matching on the `name` field.

1. **Added:** Services in current but not in baseline. Record full service object.
2. **Removed:** Services in baseline but not in current. Record full service object.
3. **Rename detection:** For each pair of (removed, added) services, check:
   - Same `language`?
   - Same `framework`?
   - Do >50% of the removed service's outbound edge targets also appear in the
     added service's outbound edges?
   If all three conditions match, classify as `likely_renamed` with `old_name`
   and `new_name`. Remove the pair from the added/removed lists.
4. **Reclassified:** Services present in both but with different `type` field.
   Record `name`, `old_type`, `new_type`.
5. **Confidence changed:** Services present in both but with different
   `confidence` field. Record `name`, `old`, `new`.

### Step 2: Edge Diff

Compare the `edges` arrays by matching on edge identity: `source + target +
type + label` (all four fields must match for two edges to be "the same edge").

1. **Added:** Edges in current but not in baseline (no identity match).
2. **Removed:** Edges in baseline but not in current (no identity match).
3. **Confidence upgraded:** Same identity, current confidence > baseline
   confidence. Order: LOW < MEDIUM < HIGH.
4. **Confidence degraded:** Same identity, current confidence < baseline.
5. **Evidence changed:** Same identity, same confidence, but different
   `evidence` arrays (new files appeared, old files gone).

### Step 3: Cluster Diff

Compare the `clusters` arrays by matching on `name`.

1. **New cluster:** In current but not in baseline.
2. **Dissolved:** In baseline but not in current.
3. **Membership changed:** Same name, different `services` array. Record the
   specific services added to and removed from the cluster.

### Step 4: Crawl-Specific Diff (Crawl Diff Only)

Skip this step entirely if the Crawl Baseline input is "N/A".

Compare `crawl_metadata` from the crawl baseline snapshot against crawl_metadata
in the current topology. Match repos by name.

1. **Importance score changed:** Same repo, different `importance` value.
   Record `name`, `old_score`, `new_score`.
2. **Discovery path changed:** Same repo, different `found_via` signal.
   Record `name`, `old_path`, `new_path`.
3. **Depth changed:** Same repo, discovered at a different `depth`.
   Record `name`, `old_depth`, `new_depth`.
4. **Signal diversity changed:** Same repo, different `signal_sources` array.
   Record `name`, `old_sources`, `new_sources`.

### Step 5: Summary Metrics

Compute:
- Net service count delta (current - baseline)
- Net edge count delta
- Net cluster count delta
- Coverage distribution shifts: count of HIGH/MEDIUM/LOW confidence services
  and edges in baseline vs current
- For crawl diffs: total importance score shift, frontier size change

---

## Required Output Format

Output valid JSON to stdout:

```json
{
  "meta": {
    "baseline_timestamp": "ISO 8601 from baseline meta.scan_timestamp",
    "current_timestamp": "ISO 8601 from current meta.scan_timestamp",
    "mode": "full-scan | crawl | file-comparison",
    "org": "org-name",
    "repos_total": 47,
    "repos_reused": 38,
    "repos_rescanned": 9
  },
  "services": {
    "added": [{ "name": "org/repo", "type": "API", "language": "...", "framework": "..." }],
    "removed": [{ "name": "org/repo", "type": "API" }],
    "likely_renamed": [{ "old_name": "org/old-name", "new_name": "org/new-name", "type": "API", "evidence": "same language, framework, 75% edge overlap" }],
    "reclassified": [{ "name": "org/repo", "old_type": "Unknown", "new_type": "Worker" }],
    "confidence_changed": [{ "name": "org/repo", "old": "MEDIUM", "new": "HIGH" }]
  },
  "edges": {
    "added": [{ "source": "org/a", "target": "org/b", "type": "HTTP", "label": "...", "confidence": "HIGH", "evidence": [...] }],
    "removed": [{ "source": "org/a", "target": "org/b", "type": "HTTP", "label": "...", "confidence": "HIGH" }],
    "confidence_upgraded": [{ "source": "org/a", "target": "org/b", "type": "HTTP", "label": "...", "old": "MEDIUM", "new": "HIGH" }],
    "confidence_degraded": [{ "source": "org/a", "target": "org/b", "type": "HTTP", "label": "...", "old": "HIGH", "new": "MEDIUM" }],
    "evidence_changed": [{ "source": "org/a", "target": "org/b", "type": "HTTP", "label": "...", "old_evidence": [...], "new_evidence": [...] }]
  },
  "clusters": {
    "new": [{ "name": "cluster-name", "services": [...] }],
    "dissolved": [{ "name": "cluster-name", "services": [...] }],
    "membership_changed": [{ "name": "cluster-name", "added": ["org/new-svc"], "removed": ["org/old-svc"] }]
  },
  "crawl_changes": {
    "importance_changed": [{ "name": "org/repo", "old_score": 5, "new_score": 8 }],
    "discovery_path_changed": [{ "name": "org/repo", "old_path": "forward:env_var:X", "new_path": "reverse:code_search" }],
    "depth_changed": [{ "name": "org/repo", "old_depth": 2, "new_depth": 1 }],
    "signal_diversity_changed": [{ "name": "org/repo", "old_sources": [...], "new_sources": [...] }]
  },
  "summary": {
    "services_delta": "+1 / -0 / 1 renamed / 2 reclassified",
    "edges_delta": "+3 / -1 / 2 confidence changes",
    "clusters_delta": "+0 / -0 / 1 membership change",
    "coverage_shift": {
      "services": { "baseline": { "high": 30, "medium": 10, "low": 5 }, "current": { "high": 32, "medium": 9, "low": 5 } },
      "edges": { "baseline": { "high": 60, "medium": 20, "low": 10 }, "current": { "high": 65, "medium": 18, "low": 10 } }
    }
  }
}
```

If `crawl_changes` is N/A (not a crawl diff), output the field as `null`.

The `meta.repos_reused` and `meta.repos_rescanned` fields are passed through
from the orchestrator — you do not compute them. If not provided (file
comparison mode), set both to 0 and `repos_total` to the count of unique
services in the current topology.

---

## Rules

- Match services by `name` only — do not fuzzy-match
- Match edges by the four-part identity: `source + target + type + label`
- Rename detection is a heuristic — always include the word "likely" and the
  evidence (language match, framework match, edge overlap percentage)
- If both topologies have zero services, output an empty diff (all arrays empty)
  with a summary noting "Both topologies are empty"
- Every array in the output must be present even if empty (use `[]`)
- Do not invent changes — only report differences that exist in the data
- Do NOT include `caused_by` fields — causal attribution is performed by the orchestrator after your output

---

## Output Cap

Your JSON output must be valid. Include all changes — completeness matters
for the diff report.
```

### Verification

After this task, the new prompt template exists and follows the same structure as existing templates. It covers all change categories from the design doc: service changes (including rename detection), edge changes, cluster changes, crawl-specific changes, and summary metrics.

---

## Task 6: Add Diff Mode Pre-flight and Discovery Procedure to SKILL.md

**Complexity:** High
**Files:** 1 file
- `skills/pathfinder/SKILL.md`
**Dependencies:** Task 4

This task adds the diff mode procedure sections to SKILL.md covering pre-flight, baseline loading, and the smart rescan discovery logic. These are the first phases of the diff pipeline.

### Changes to `SKILL.md`

Add a new top-level section **"## Diff Mode"** after the existing Crawl Mode section (after the Crawl Mode's Output Directories subsection, before Query Mode). Include the following subsections:

### Section: Diff Mode

```
## Diff Mode

Diff mode compares a current topology scan against a baseline to surface structural drift. It operates in three forms based on invocation:

- **Full-scan diff** (`crucible:pathfinder diff <org>`): Rescan the org using smart delta detection, compare against persisted topology.
- **Crawl diff** (`crucible:pathfinder diff <org>/<repo> [--depth N] [--orgs org1,org2]`): Re-crawl from seed, compare against persisted crawl topology. The distinction is natural: org name only = full-scan diff, org/repo = crawl diff.
- **File comparison** (`crucible:pathfinder diff --baseline path/old.json --current path/new.json`): Compare any two topology files directly. No rescanning.

Named phases: **Pre-flight** -> **Discovery** -> **Rescan Tier 1** -> **Rescan Tier 2 (if --tier 2)** -> **Synthesis** -> **Diff** -> **Attribution** -> **Impact Ranking** -> **Report**
```

### Subsection: Pre-flight (Diff)

```
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
```

### Subsection: Discovery (Diff — Smart Rescan)

```
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
```

### Verification

After this task, SKILL.md has the Diff Mode section header, the pre-flight procedure (including baseline loading, validation, and file comparison early exit), and the discovery procedure (including smart rescan delta detection for both full-scan and crawl diffs).

---

## Task 7: Add Diff Mode Rescan, Synthesis, Diff, and Attribution Procedures to SKILL.md

**Complexity:** High
**Files:** 1 file
- `skills/pathfinder/SKILL.md`
**Dependencies:** Task 6

This task adds the rescan, synthesis, diff dispatch, and causal attribution procedures to the Diff Mode section of SKILL.md.

### Subsection: Rescan (Diff)

Add after the Discovery subsection:

```
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
```

### Subsection: Synthesis (Diff)

```
### Synthesis (Diff)

After rescan completes, merge reused + fresh per-repo results into a new topology.

1. **Collect all per-repo JSON:** For reused repos, load from `~/.claude/memory/pathfinder/<org>/repos/<repo-name>.json`. For rescanned repos, load from `/tmp/pathfinder/<org>/repos/<repo-name>.json`.
2. **Dispatch synthesis agent** using `./synthesis-prompt.md` (unchanged) with the collected per-repo results. Pass the existing topology.json as the incremental merge baseline.
3. **For crawl diffs:** Pass crawl metadata (seed, depth, importance) same as regular crawl synthesis. **Crawl diff synthesis inherits crawl mode's merge rules: no stale-marking of repos absent from the re-crawl.** Crawl results are intentionally partial — only repos discovered during the crawl are present. Do NOT mark missing repos as stale.
4. **Synthesis produces a new topology.json** written to both the output directory and the persistence path. This updates the persisted topology — running diff keeps your topology fresh.
5. **For crawl diffs:** Also write an updated crawl snapshot to `~/.claude/memory/pathfinder/<org>/crawl-<seed-repo>/snapshot.json`.
6. The new topology.json becomes the "current" topology for the diff phase.
```

### Subsection: Diff

```
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
```

### Subsection: Causal Commit Attribution

```
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
```

### Subsection: Impact Ranking

```
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
```

### Verification

After this task, SKILL.md contains the complete rescan, synthesis, diff dispatch, attribution, and impact ranking procedures. Combined with Task 6, the entire diff pipeline (pre-flight through impact ranking) is documented.

---

## Task 8: Add Diff Mode Report, Error Handling, Compaction Recovery, and Guardrails to SKILL.md

**Complexity:** Medium
**Files:** 1 file
- `skills/pathfinder/SKILL.md`
**Dependencies:** Task 7

This task adds the report generation phase, diff-specific error handling, compaction recovery for diff mode, and updates the guardrails/red flags sections.

### Subsection: Report (Diff)

Add after the Attribution subsection:

```
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
```

### Updates to Error Handling section

Add these rows to the existing Error Handling table:

```
| No baseline topology exists | Stop: "No topology data for `<org>`. Run `crucible:pathfinder <org>` first." |
| Baseline topology is corrupt/unparseable | Stop with clear message, suggest re-running full scan |
| `pushedAt` not available for a repo | Conservative: re-analyze that repo (don't skip) |
| All repos unchanged (zero delta) | Report "No structural changes detected since [baseline timestamp]." Still produce artifacts (empty diff). |
| Partial rescan failure (some repos error) | Skip errored repos, flag in diff-log.json, note in report: "N repos could not be rescanned — changes in those repos may be missed" |
| File comparison with mismatched orgs | Warn about overlap, diff only covers overlapping orgs |
| File comparison with mismatched modes | Skip crawl-specific changes with warning |
```

### Updates to Compaction Recovery section

Add a third branch to the recovery logic:

```
- If `mode: "diff"`: Read `phase` to determine resume point. Branch on `diff_type`:
  - `"full-scan"`: Read `repos_to_rescan`, `repos_reused`, `repos_remaining`. Skip repos already completed. Resume from current phase (`discovery`, `rescan-tier1`, `rescan-tier2`, `synthesis`, `diff`, `attribution`, `report`).
  - `"crawl"`: Same as crawl mode recovery, plus diff-specific fields (`baseline_path`, `baseline_timestamp`).
  - The baseline topology is always available at the persistence path (never modified mid-run — only updated after synthesis completes).
  - Per-repo results on disk survive compaction.

> "Recovered from compaction. Diff rescan: 15/22 repos re-analyzed. Resuming from repo 16."
```

### Updates to Guardrails section

Add to **"The orchestrator must NOT"** list:

```
- Modify the baseline topology during a diff run (it is read-only until synthesis produces a new topology)
- Skip causal attribution for rescan-based diffs (only skip for file-comparison mode)
- Run reverse search for full-scan diffs (reverse search is crawl-only)
```

### Updates to Red Flags section

Add:

```
- Modifying the baseline topology before diff completes
- Skipping delta detection and re-analyzing all repos (defeats the smart rescan optimization)
- Running attribution on file-comparison diffs (no cloned repos available)
- Producing diff output without the visual Mermaid diagram
```

### Verification

After this task, the diff mode section is complete: pre-flight, discovery, rescan, synthesis, diff, attribution, and report. Error handling, compaction recovery, and guardrails are all updated.

---

## Task 9: Add Consuming Skill Integration Contract to SKILL.md

**Complexity:** Low
**Files:** 1 file
- `skills/pathfinder/SKILL.md`
**Dependencies:** Task 8

This task documents the integration contract for consuming skills. No changes to consuming skills are required — this documents the well-known path and schema so future skill updates can use diff data.

### Changes to `SKILL.md`

Add a subsection at the end of the Diff Mode section:

```
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
```

Also update the **Integration section** (around line 612) to add:

```
- **Produces:** `~/.claude/memory/pathfinder/<org>/latest-diff.json` (diff mode, consumed by build/design/audit opportunistically)
```

### Verification

After this task, the integration contract is documented and the well-known path is discoverable by future skill implementations.

---

## Task 10: Add User Gate Streamlining Documentation to SKILL.md

**Complexity:** Low
**Files:** 1 file
- `skills/pathfinder/SKILL.md`
**Dependencies:** Task 6

This task ensures the diff mode's streamlined user gates are explicitly documented, since they differ from full scan's gates.

### Changes to `SKILL.md`

Add a subsection within the Diff Mode section (after Discovery, before Rescan):

```
### User Gates (Diff Mode)

Diff mode streamlines user confirmations for speed:

- **No discovery confirmation** — you already know the org from the baseline.
- **No Tier 1 checkpoint** — diff is meant to be quick. The `--tier 2` flag replaces the interactive Tier 2 opt-in.
- **Confirm before cloning new repos** — repos not seen in the baseline (genuinely new services) require user confirmation before cloning. "Found N new repos not in the baseline: [list]. Clone and analyze?"
- **Crawl diff: checkpoint after each depth level** — inherited from crawl mode. User can stop, exclude repos, or continue at each depth.
```

### Verification

After this task, the user gate differences between diff mode and full scan are explicit and unambiguous.

---

## Summary

| Task | Title | Complexity | Files | Dependencies |
|------|-------|-----------|-------|-------------|
| 1 | Timestamp Standardization | Low | 2 | None |
| 2 | Per-Repo Persistence | Medium | 1 | None |
| 3 | Crawl Snapshot Persistence | Low | 1 | None |
| 4 | Diff Mode Declaration (SKILL.md top-level) | Medium | 1 | Tasks 2, 3 |
| 5 | Diff Analyzer Prompt Template | High | 1 (new) | None |
| 6 | Diff Pre-flight and Discovery Procedures | High | 1 | Task 4 |
| 7 | Diff Rescan, Synthesis, Diff, and Attribution Procedures | High | 1 | Task 6 |
| 8 | Diff Report, Error Handling, Compaction, Guardrails | Medium | 1 | Task 7 |
| 9 | Consuming Skill Integration Contract | Low | 1 | Task 8 |
| 10 | User Gate Streamlining | Low | 1 | Task 6 |

**Critical path:** Tasks 1-3 (parallel prerequisites) -> Task 4 -> Task 5 (parallel with 4) -> Task 6 -> Task 7 -> Task 8 -> Task 9

**Parallelizable:** Tasks 1, 2, 3, 5 can all be done in parallel. Task 10 can be done in parallel with Tasks 7-9.

**Total files touched:** 3 existing files + 1 new file = 4 files
- `skills/pathfinder/tier1-analyzer-prompt.md` (Task 1)
- `skills/pathfinder/synthesis-prompt.md` (Task 1)
- `skills/pathfinder/SKILL.md` (Tasks 2, 3, 4, 6, 7, 8, 9, 10)
- `skills/pathfinder/diff-analyzer-prompt.md` (Task 5 — new file)
