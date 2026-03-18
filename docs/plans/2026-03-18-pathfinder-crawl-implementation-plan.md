# Pathfinder Crawl Mode — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use crucible:build to implement this plan task-by-task.

**Goal:** Add crawl mode to the existing pathfinder skill — a third mode that starts from a seed repo and discovers connected services by tracing dependencies bidirectionally (forward fan-out + reverse fan-in). Handles large orgs where full enumeration is impractical.

**Architecture:** Markdown-only changes across 4 files (1 new, 3 modified). No application code. The implementation adds crawl mode sections to SKILL.md, creates a reverse-search-prompt.md template, extends tier1-analyzer-prompt.md with identity_signals output, and augments synthesis-prompt.md with crawl metadata handling. 5 tasks across 3 waves.

**Design doc:** `docs/plans/2026-03-18-pathfinder-crawl-mode-design.md`

**Acceptance tests:** `tests/pathfinder/crawl-mode.test.ts` (26 of 30 currently failing)

---

## Dependency Graph

```
Task 1 (reverse-search-prompt.md) ── no deps ─────────────┐
Task 2 (tier1-analyzer-prompt.md) ── no deps ──────────────┤
Task 3 (synthesis-prompt.md) ── no deps ───────────────────┤
Task 4 (SKILL.md — crawl mode section) ── depends on 1, 2, 3 ──┤
Task 5 (SKILL.md — existing section updates) ── depends on 4 ──┘
```

---

### Task 1: Create Reverse Search Prompt Template

Write the new subagent dispatch template for crawl mode's reverse (fan-in) search — searches across orgs for repos that reference a given repo's identity signals.

- **Files:** `skills/pathfinder/reverse-search-prompt.md` (1 file)
- **Complexity:** Medium
- **Dependencies:** None

**Steps:**

1. Create `skills/pathfinder/reverse-search-prompt.md` with:

   - Dispatch block header: `Agent tool (subagent_type: general-purpose, model: sonnet):`
   - Description placeholder: `"Reverse search for [org/repo] across [org list]"`

   - Agent identity: "You are a Reverse Searcher. Your job is to search across specified GitHub organizations for repos that reference a target repo, using that repo's identity signals. You discover fan-in dependencies — repos that call or depend on the target that forward analysis alone would miss."

   - Input sections (placeholders for orchestrator to fill):
     - `[PASTE: Target repo — qualified as org/repo]`
     - `[PASTE: Identity signals — JSON array from Tier 1 analyzer's identity_signals output]`
     - `[PASTE: Orgs to search — list of org names to search across]`
     - `[PASTE: Already-discovered repos — list of org/repo already in the crawl's discovered set, to avoid re-reporting]`

   - Process:
     1. **Progressive signal search** — search identity signals in priority order:
        - **HIGH priority (always search):** Repo name, package names, Docker image names
        - **MEDIUM priority (search if budget allows):** Proto service names, Kafka topic names
        - **LOW priority (search only on user opt-in):** API base paths, code-level string patterns
     2. **For each signal**, execute GitHub code search:
        ```bash
        gh api search/code -X GET -f q="<signal> org:<org>" --paginate
        ```
     3. **Compound queries** — where possible, batch 2-3 short signals per query using OR syntax to reduce API call count:
        ```bash
        gh api search/code -f q="payments-service OR @acme/payments-client org:acme"
        ```
        Max query length ~256 chars. Batch only short signals.
     4. **False positive filtering:**
        - Exclude archived repos
        - Exclude the target repo itself (self-references)
        - Exclude results from test/mock/example directories
        - Require 2+ distinct references in a repo to count as a real edge (single mention = LOW confidence, noted but not auto-followed)
        - Exclude well-known external service names (e.g., a repo named `redis` should not match every Redis client config)
     5. **Rate limit awareness:** Budget of 15 searches per target repo. If rate limit is hit, report partial results and note which signals were not searched.

   - Required output format — JSON:
     ```json
     {
       "target": "org/repo",
       "reverse_refs": [
         {
           "repo": "org/other-repo",
           "signal_type": "package_name",
           "signal_value": "@acme/payments-client",
           "match_count": 4,
           "confidence": "HIGH",
           "evidence": [
             { "file": "package.json", "match": "\"@acme/payments-client\": \"^2.1.0\"" }
           ]
         }
       ],
       "signals_searched": ["repo_name", "package_name", "docker_image"],
       "signals_skipped": ["api_base_path"],
       "search_metadata": {
         "api_calls_made": 8,
         "orgs_searched": ["acme", "acme-infra"],
         "errors": []
       }
     }
     ```

   - Rules:
     - Do NOT clone any repos — search only via GitHub code search API
     - Do NOT modify any files — read-only search
     - Single-mention matches go in `reverse_refs` with `confidence: "LOW"` — do not silently drop
     - If code search returns 1000+ results for a signal, skip it as "too broad" and log in errors
     - If code search returns 403/422 for an org, log the error and continue with other orgs
     - Report all API calls made for rate budget tracking

   - Context self-monitoring: "If you reach 50%+ context utilization, report what you have so far. Include a `partial: true` field in your JSON output and list unsearched signals in `signals_skipped`."

**Commit:** `feat: add reverse search prompt template for pathfinder crawl mode`

---

### Task 2: Extend Tier 1 Analyzer with Identity Signals

Add an `identity_signals` output field to the existing Tier 1 analyzer prompt so it captures signals needed for reverse search during crawl mode. This is a surgical addition — the existing prompt structure and output format are preserved.

- **Files:** `skills/pathfinder/tier1-analyzer-prompt.md` (1 file)
- **Complexity:** Low
- **Dependencies:** None

**Steps:**

1. Read `skills/pathfinder/tier1-analyzer-prompt.md` to confirm the current structure.

2. In the **Process** section, after step 4 (Infrastructure) and before step 5 (Monorepo Sub-Services), add a new step numbered **5** (shifting the old step 5 to become step 6):

   ```markdown
   ### 5. Identity Signals (for Crawl Mode Reverse Search)

   Extract identity signals that other repos might use to reference this repo. These are used by crawl mode's reverse search to find fan-in dependencies. Collect ALL of the following that are present:

   1. **Repo name** — the repo's short name (always present)
   2. **Package names** — from package.json `name` field, go.mod `module` path, pyproject.toml `[project] name`, Cargo.toml `[package] name`
   3. **Proto service names** — from `service` declarations in `.proto` files
   4. **Docker image names** — from Dockerfile metadata, docker-compose service names, or CI/CD build configs
   5. **Kafka topics produced** — topic names where this repo is a producer (from infrastructure scan above)
   6. **API base paths** — from OpenAPI/Swagger specs (e.g., `/api/v1/payments`)

   Each signal should include a `type` and `value` field.
   ```

3. Renumber old step 5 (Monorepo Sub-Services) to step 6. Update its internal reference from "Run the above scans (steps 1-4)" to "Run the above scans (steps 1-5) per sub-service directory".

4. In the **Required Output Format** section, add `identity_signals` to the JSON schema, as a new top-level field alongside `service`, `edges`, `unresolved`, and `scan_metadata`:

   ```json
   "identity_signals": [
     { "type": "repo_name", "value": "payments-service" },
     { "type": "package_name", "value": "@acme/payments-client" },
     { "type": "docker_image", "value": "acme/payments-service" },
     { "type": "proto_service", "value": "acme.payments.v1.PaymentsService" },
     { "type": "kafka_topic", "value": "payment-events" },
     { "type": "api_base_path", "value": "/api/v1/payments" }
   ]
   ```

5. In the **Rules** section, add: "The `identity_signals` array must always contain at least the repo name. If no other signals are found, that is acceptable — the repo name alone is the minimum."

**Commit:** `feat: extend tier 1 analyzer with identity signals for crawl mode`

---

### Task 3: Augment Synthesis Prompt with Crawl Metadata

Add crawl-mode-specific instructions to the synthesis prompt template. The orchestrator appends crawl metadata when dispatching in crawl mode; the synthesis agent needs instructions on how to use it. This is additive — the existing synthesis flow for full scan mode is unchanged.

- **Files:** `skills/pathfinder/synthesis-prompt.md` (1 file)
- **Complexity:** Medium
- **Dependencies:** None

**Steps:**

1. Read `skills/pathfinder/synthesis-prompt.md` to confirm the current structure. **Important:** The entire prompt content is wrapped inside a code fence (opening triple backtick at line 5, closing at the end). All insertions must go INSIDE this code fence, not after it.

2. After the existing `## Existing Topology (Incremental Run)` input section (inside the code fence), add a new input section:

   ```markdown
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
   ```

3. In the **Step 4: Incremental Merge** section, add a crawl-specific merge rule after the existing merge rules:

   ```markdown
   **Crawl-mode merge exception:** When the mode is "crawl", do NOT mark repos
   absent from the crawl results as "stale". Crawl results are intentionally
   partial (only discovered repos). Stale-marking only applies when mode is
   "full-scan" (which is comprehensive). Crawl provenance is preserved as a
   `crawl_metadata` section in topology.json that coexists with full scan data.
   ```

4. In the **Step 5: Generate Output Artifacts** section, within the `report.md` description, add crawl-specific report sections:

   ```markdown
   **Crawl mode additions to report.md (only when mode is "crawl"):**
   - **Discovery Path** — a tree visualization showing: seed -> depth 1 repos -> depth 2 repos, with the discovery signal that led to each repo (e.g., "found via forward:env_var:PAYMENTS_SERVICE_URL")
   - **Importance Heatmap** — repos listed by importance score, used to weight cluster detection and size Mermaid nodes proportionally
   - **Reverse Search Coverage** — which orgs were searched, which had code search available, how many signals were searched per repo
   ```

5. In the **topology.json schema** section, add `crawl_metadata` as an optional top-level field:

   ```markdown
   **Crawl mode addition to topology.json (only when crawl_metadata is provided):**
   Add a `"crawl_metadata"` top-level field to topology.json preserving the seed, depth, found_via, importance, and signal_sources for each discovered repo. This section is additive and does not conflict with full scan data.
   ```

**Commit:** `feat: augment synthesis prompt with crawl metadata support`

---

### Task 4: Add Crawl Mode Section to SKILL.md

Add the new Crawl Mode top-level section to SKILL.md. This section goes after Phase 4 (Report) and before Query Mode. It contains all crawl-specific subsections.

- **Files:** `skills/pathfinder/SKILL.md` (1 file)
- **Complexity:** High
- **Dependencies:** Task 1, Task 2, Task 3

**Steps:**

1. Read `skills/pathfinder/SKILL.md` to confirm the current structure and identify the exact insertion point between Phase 4 (Report) and Query Mode.

2. **Insert the Crawl Mode section** between Phase 4 (Report) and Query Mode. The section contains ALL of the following subsections:

   **`## Crawl Mode`**

   Opening paragraph: "Crawl mode starts from a seed repo and discovers connected services by tracing dependencies bidirectionally. Unlike full scan (which enumerates an entire org top-down), crawl mode follows dependency threads from a known starting point. Use for large orgs (100+ repos) where full enumeration is impractical."

   Named phases: Pre-flight → Seed → Crawl → Tier 2 (opt-in) → Synthesis → Report

   **`### Pre-flight`**

   - Same pre-flight checks as full scan: `gh auth status`, rate limit check, org access verification for seed org + all `--orgs`
   - Verify seed repo exists: `gh repo view <org>/<repo>`. If not found, stop with clear message: "Seed repo `<org>/<repo>` not found or inaccessible."
   - Code search availability check: For each org in `--orgs`, test code search with `gh api search/code -f q="test org:<org>" --jq '.total_count'`. If 403/422, warn: "Code search unavailable for `<org>`. Reverse search will not cover this org." Offer to continue with forward-only crawl.
   - Single-org notice: If `--orgs` is omitted, display: "Reverse search will only cover the `<seed-org>` org. To discover cross-org callers, add `--orgs org1,org2`. Continue with single-org reverse search?"
   - Reverse search time estimate: Based on org repo count and estimated signals per repo, display: "Estimated reverse search: ~N API calls across M orgs. At GitHub's code search rate (10 req/min), this may take ~X minutes."
   - Initialize state file at `/tmp/pathfinder-state.json` with `"mode": "crawl"`

   **`### Seed`**

   - Clone seed repo following full scan cloning rules (local resolution in `../`, large repo handling, clone to `/tmp/pathfinder/<org>/<repo>/`)
   - Run full Tier 1 analysis on seed using `./tier1-analyzer-prompt.md` — outputs both standard edge data AND identity signals
   - Seed with no manifests fallback: If Tier 1 returns zero outbound edges and no identity signals beyond the repo name, inform user: "Seed repo has no detectable dependencies or identity signals beyond its name. Reverse search will use repo name only. Results may be limited." Proceed with repo-name-only reverse search.

   **`### Cloning`**

   Crawl mode inherits all full scan cloning rules:
   - Local resolution: Check `../` for existing clones matching repo names before cloning
   - Large repos (>1GB disk usage): Skip clone, manifest-only scan. Inform user.
   - Clone path: `/tmp/pathfinder/<org>/<repo>/` — same convention as full scan
   - Clone persistence: Clones are NOT cleaned up between depth levels. The `clone_paths` map in the state file tracks all cloned repos. When a repo appears in the frontier that's already in `clone_paths`, skip cloning.
   - Clone failure: Skip repo, log error, continue with remaining repos. Report to user.

   **`### Crawl (Iterative Discovery)`**

   - Pseudocode showing the crawl loop: frontier processing, forward analysis (Tier 1), reverse search (via `./reverse-search-prompt.md`), reference resolution, importance scoring, adaptive depth
   - Each depth level is a wave — clone all new repos, analyze in parallel (max 10 concurrent)
   - User checkpoint after each depth level — user can stop, exclude repos, or continue
   - Forward analysis reuses existing Tier 1 analyzer agents
   - Reverse search dispatched via the Reverse Searcher agent inline during each iteration (not a separate phase)
   - State file updated after each repo completes

   **`### Bidirectional Analysis`**

   - Fan-out (forward): Analyze repo manifests/code to find what it calls — same as existing Tier 1/Tier 2 analysis
   - Fan-in (reverse): Search across specified orgs for repos that reference this repo — uses identity signals from Tier 1 output
   - Explain why bidirectional matters: if Service A calls Service B, but B has no reference back, forward-only crawl from B would never discover A

   **`### Reference Resolution`**

   Layered confidence strategy for mapping references to actual repos:

   | Strategy | Confidence |
   |----------|-----------|
   | Exact package match (go.mod, package.json) | HIGH |
   | Docker image match | HIGH |
   | Proto import match | HIGH |
   | Env var hostname = repo name | MEDIUM |
   | Env var hostname prefix match | LOW |
   | Code search string match | LOW |

   **`### Cross-Org Resolution`**

   When `--orgs` includes multiple orgs, resolution searches all of them. A reference to `payments-service` checks `org1/payments-service`, `org2/payments-service`, etc. If found in exactly one org, auto-resolve. If found in multiple, add to the ambiguous queue.

   **`### False Positive Mitigation for Reverse Search`**

   - Exclude archived repos
   - Exclude the repo being searched for (self-references)
   - Exclude test/mock/example directories
   - Require 2+ distinct references in a repo to count as a real edge (single mention = LOW confidence, noted but not auto-followed)
   - Exclude well-known external service names (e.g., a repo named `redis` shouldn't match every Redis client config)

   **`### Frontier Prioritization`**

   - Scoring function (orchestrator logic, no additional API calls):
     - Signal density: how many distinct signals point to this candidate (1=1pt, 2-3=3pts, 4+=5pts)
     - Signal diversity: discovered via multiple independent signal types (bonus 2pts) vs single type (0pts)
     - Cross-cluster bridging: candidate's referrers span different already-identified clusters (bonus 3pts)
   - Score ranges: minimum 1pt, maximum 10pts
   - LOW_THRESHOLD = 2 — a repo scoring 2 or below was discovered by a single signal with no diversity or bridging bonus
   - Frontier sorted by score — high-importance repos analyzed first within each wave
   - Score breakdown logged in state file and visible at checkpoints for transparency
   - Adaptive depth termination: if highest-scored candidate falls below LOW_THRESHOLD, recommend termination at checkpoint. Adaptive termination is always a recommendation, never automatic.

   **`### Ambiguous Reference Handling`**

   - When a reference cannot be auto-resolved or has LOW confidence, queue for user input
   - Batched at end of each depth level and presented together at checkpoint
   - User options per reference: skip, enter repo name, search orgs, pick from candidates
   - Resolution persistence: user decisions stored in state file's `unresolved` array with `resolution` field — survives compaction

   **`### Tier 2 (Opt-in)`**

   - Tier 2 deep code scanning offered after all crawl depth levels complete, before synthesis:
     > "Crawl complete. Discovered N repos across M depth levels with K edges. Would you like to run a deep code scan on all/selected repos for additional edges?"
   - User options: all repos, selected repos, or skip

   **`### Synthesis (Crawl)`**

   - Dispatch Opus synthesis agent using `./synthesis-prompt.md` with crawl-specific augmentation
   - Standard inputs same as full scan plus: `"mode": "crawl"`, `"seed": "<org>/<repo>"`, `crawl_metadata` map
   - **Per-repo JSON augmentation:** Before dispatching synthesis, the orchestrator annotates each per-repo JSON file with a `"crawl"` metadata block containing `depth`, `found_via`, `importance`, and `signal_sources` from the state file's discovered map. This keeps the Tier 1 analyzer unchanged — crawl metadata is added by the orchestrator after analysis.
   - Produces discovery path section in report.md, uses importance scores for cluster weighting and Mermaid node sizing

   **`### Merge Rules (Crawl)`**

   - Edge identity matching same as full scan: `source + target + type + label`, confidence takes max, evidence unions
   - No stale-marking for crawl merges — crawl results are intentionally partial. Stale-marking only applies to full scan mode.
   - Crawl provenance preserved in topology.json's `crawl_metadata` section
   - Reverse-search edges are new edge types that full scan doesn't produce; they merge normally

   **`### Output Directories (Crawl)`**

   - Single-org crawl: `docs/pathfinder/<org-name>/crawl-<seed-repo>/`
   - Multi-org crawl: `docs/pathfinder/<combined-orgs>/crawl-<seed-repo>/` (alpha-sorted, `+`-joined)
   - Persistence path: `~/.claude/memory/pathfinder/<org-name>/topology.json` (same as full scan — crawl results merge into unified topology)

**Commit:** `feat: add crawl mode section to pathfinder SKILL.md`

---

### Task 5: Update Existing SKILL.md Sections for Crawl Mode

Surgical updates to existing SKILL.md sections (mode count, model table, narration, state schema, compaction, error handling, dispatch table, guardrails). Separate from Task 4 to keep context manageable.

- **Files:** `skills/pathfinder/SKILL.md` (1 file)
- **Complexity:** Medium
- **Dependencies:** Task 4

**Steps:**

1. Read `skills/pathfinder/SKILL.md` to confirm the current structure after Task 4's additions.

2. **Update mode count and add crawl invocation** — In the overview section near the top of the file:

   - Change `**Two modes:**` to `**Three modes:**` (line 14)
   - After the existing two bullet points (Full scan, Query mode), add:
     ```markdown
     - **Crawl mode** — Seed-based bidirectional discovery: start from one repo, trace dependencies forward and reverse to discover connected services. For large orgs where full enumeration is impractical.
     ```
   - After the existing invocation lines, add:
     ```markdown
     - Crawl mode: `crucible:pathfinder crawl <org>/<repo> [--depth N] [--orgs org1,org2]`
     ```

3. **Add Reverse Searcher to the Model section** — After the existing model entries (line 28 area), add:
   ```markdown
   - **Reverse Searcher (Crawl mode):** Sonnet via Agent tool (subagent_type: general-purpose)
   ```

4. **Add crawl-specific narration examples** — In the Communication Requirement section, after the existing "Examples of GOOD narration" (around line 47), add:
   ```markdown
   > "Crawl (Seed): Seed analysis complete — TypeScript API, 5 outbound refs, 3 identity signals. Dispatching reverse search + depth 1 forward analysis."

   > "Crawl (Depth 2): Wave complete — discovered 8 new repos (total: 14), 31 edges. Top-scored: acme/event-bus (importance: 9). Presenting checkpoint."
   ```

5. **Update the Scratch and State section** — In the state file schema (around line 52-61):

   - Add `"mode"` field documentation BEFORE the existing JSON schema example. Insert a paragraph:
     ```markdown
     The state file uses a `"mode"` field to discriminate between full scan and crawl schemas:
     - `"mode": "full-scan"` — existing full scan schema (unchanged)
     - `"mode": "crawl"` — crawl mode schema (see Crawl Mode section below)
     ```
   - Add `"mode": "full-scan"` to the existing JSON schema example (as the first field inside the object)
   - AFTER the existing JSON schema, add the crawl mode state schema as a separate JSON block:
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

6. **Update the Compaction Recovery section** — Add crawl mode recovery logic after the existing full scan recovery steps:

   ```markdown
   **Crawl mode recovery:** The compaction recovery logic reads `/tmp/pathfinder-state.json` and branches on the `mode` field:
   - If `mode: "crawl"`: Read `current_phase` to determine resume point (seed, crawl, tier2, synthesis). Read `current_depth` and `frontier` for crawl progress. Skip repos with `status: "analyzed"` — resume from `status: "pending"`. Re-present only `unresolved` entries with `"resolution": "pending"`.
   - If `mode: "full-scan"`: Existing recovery logic (unchanged).
   ```

7. **Add crawl-specific error handling** — In the Error Handling table, add these rows:

   | Error | Response |
   |-------|----------|
   | Seed repo not found | Stop with clear message: "Seed repo `<org>/<repo>` not found or inaccessible." |
   | Seed repo has no manifests | Warn user, proceed with repo-name-only reverse search |
   | Code search unavailable (403/422) | Warn: "Code search unavailable for `<org>`. Reverse search will not cover this org." Offer forward-only crawl. |
   | Code search rate limit hit | Pause reverse search, present partial results, offer to continue with forward-only crawl |
   | Code search returns 1000+ results | Signal too generic — skip it, log as "too broad", continue with other signals |
   | No new repos discovered at depth level | Natural termination — proceed to synthesis |
   | All references at a depth level are ambiguous | Present full unresolved list to user, don't auto-follow any |

8. **Update the Subagent Dispatch Summary table** — Add the Reverse Searcher row:

   | Agent | Model | Dispatch | Prompt Template |
   |-------|-------|----------|-----------------|
   | Reverse Searcher | Sonnet | Agent tool (general-purpose) | `./reverse-search-prompt.md` |

9. **Update the Prompt Templates section** — Add:
    ```markdown
    - `./reverse-search-prompt.md` — Crawl mode reverse search across orgs for fan-in dependencies
    ```

10. **Add crawl guardrails** — In the Guardrails section, under "The orchestrator must NOT", add:
    ```markdown
    - Proceed past a crawl depth checkpoint without user confirmation
    - Auto-follow ambiguous references — always present to user at checkpoint
    - Mark non-crawled repos as stale when merging crawl results
    ```

11. **Add crawl red flags** — In the Red Flags section, add:
    ```markdown
    - Marking repos as stale during crawl mode merge (crawl is partial by design)
    - Skipping user checkpoints between crawl depth levels
    - Auto-resolving ambiguous references without user input
    ```

**Commit:** `feat: update existing SKILL.md sections for crawl mode`

---

## Execution Order Summary

**Wave 1 (no dependencies, parallel-safe):**
- Task 1: Reverse search prompt template (1 new file)
- Task 2: Tier 1 analyzer identity signals extension (1 modified file)
- Task 3: Synthesis prompt crawl metadata augmentation (1 modified file)

**Wave 2 (depends on Wave 1):**
- Task 4: SKILL.md crawl mode section (1 modified file — references all templates from Wave 1)

**Wave 3 (depends on Wave 2):**
- Task 5: SKILL.md existing section updates (1 modified file — must run after Task 4 to avoid merge conflicts)

---

## Verification Checklist

After all tasks complete, run the acceptance tests:

```bash
npx vitest run tests/pathfinder/crawl-mode.test.ts
```

All 30 tests should pass. The tests verify:

1. **SKILL.md structural checks:**
   - [ ] "three modes" text present (was "two modes")
   - [ ] `crucible:pathfinder crawl <org>/<repo>` invocation syntax documented
   - [ ] `--depth` and `--orgs` parameters documented
   - [ ] Fan-out (forward) analysis documented
   - [ ] Fan-in (reverse) search documented
   - [ ] Identity signals documented
   - [ ] Default depth 3 and max depth 10 documented
   - [ ] Natural termination when no new repos found documented
   - [ ] Checkpoint after each depth level documented
   - [ ] Unresolved/ambiguous reference handling documented
   - [ ] No stale-marking for crawl merges documented
   - [ ] `"mode": "crawl"` in state file schema
   - [ ] Compaction recovery for crawl mode documented
   - [ ] Resolution persistence (`resolution` field) documented
   - [ ] Importance scoring documented
   - [ ] Signal density, signal diversity, bridging scoring factors documented
   - [ ] LOW_THRESHOLD = 2 documented
   - [ ] Adaptive termination as recommendation, never automatic
   - [ ] "Reverse search will only cover" single-org notice documented
   - [ ] Tier 2 offered after crawl depth levels, before synthesis
   - [ ] Reverse Searcher agent in dispatch table
   - [ ] `crawl-<seed-repo>` output directory pattern documented
   - [ ] `~/.claude/memory/pathfinder` persistence path documented
   - [ ] Crawl-specific narration examples (`Crawl (Seed)`, `Crawl (Depth)`)
   - [ ] `crawl_metadata` or `discovery path` documented for synthesis
   - [ ] Seed repo not found error documented
   - [ ] Code search unavailable error documented
   - [ ] No manifests / no identity signals fallback documented

2. **Prompt template checks:**
   - [ ] `reverse-search-prompt.md` file exists
   - [ ] `tier1-analyzer-prompt.md` contains `identity_signals` (or `identity signals`)

3. **Cross-reference consistency:**
   - [ ] SKILL.md references `./reverse-search-prompt.md` and the file exists
   - [ ] SKILL.md references Reverse Searcher agent with correct dispatch method
   - [ ] Tier 1 analyzer output schema matches what crawl mode expects
   - [ ] Synthesis prompt crawl metadata schema matches what SKILL.md describes
   - [ ] State file crawl schema in SKILL.md matches the design doc schema
   - [ ] All error handling entries from design doc are present in SKILL.md
