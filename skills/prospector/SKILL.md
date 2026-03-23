---
name: prospector
description: "Explore a codebase for architectural friction and propose competing redesigns. Triggers on 'prospector', 'find improvements', 'architecture friction', 'what should I refactor', 'where are the structural problems', or any task requesting discovery of codebase improvement opportunities."
---

# Prospector

Explores a codebase organically, surfaces architectural friction, and proposes competing redesigns for the user to choose from.

**Announce at start:** "Running prospector on [codebase/directory name]."

**Skill type:** Rigid -- follow exactly, no shortcuts.

**Purpose:** Discover structural improvement opportunities in a codebase. Distinct from audit (which finds bugs in a specific subsystem) -- prospector finds what could be better across the entire codebase. Audit finds what's broken. Prospector finds what could be better.

**Model:** Opus (orchestrator, organic explorer, competing design agents). Sonnet (genealogists, structured analysis). If the orchestrator session is not running Opus, warn: "Prospector requires Opus-level reasoning for exploration and design phases. Results may be degraded."

## Invocation

```
crucible:prospector                        # default — explore for all friction types
crucible:prospector --focus testability     # narrow: where is testing painful?
crucible:prospector --focus coupling        # narrow: where does change ripple?
crucible:prospector --focus complexity      # narrow: where are things over-engineered?
crucible:prospector --focus depth           # narrow: Ousterhout deep modules lens
```

Default mode uses the full friction example set. A `--focus` flag swaps in a targeted subset of guiding questions. The explorer is still organic — it can report friction outside its focus — but the focus tells it where to start looking.

## Communication Requirement (Non-Negotiable)

**Between every agent dispatch and every agent completion, output a status update to the user.** This is NOT optional -- the user cannot see agent activity without your narration.

Every status update must include:
1. **Current phase** -- Which phase you're in
2. **What just completed** -- What the last agent reported
3. **What's being dispatched next** -- What you're about to do and why
4. **Agent status** -- During parallel phases (1.5+2, 3, 6): which agents have reported vs. still in flight, finding counts so far

**After compaction:** Re-read the scratch directory and current state before continuing. See Compaction Recovery below.

**Examples of GOOD narration:**
> "Phase 1 complete. Explorer found 6 friction points (3 High, 2 Medium, 1 Low). Presenting for your review before committing genealogy + root cause dispatches."

> "Phase 1.5+2: Genealogy 4/6 complete, Root cause 2/3 complete. 3 Incomplete Migrations, 1 Accretion so far. 4 agents still running."

> "Phase 2.5: Convergence found 2 clusters (friction points #2+#5, #3+#7). Presenting draft for confirmation."

> "Phase 6: All 3 competing designs complete. Presenting sequentially with comparison including 'Do Nothing' option."

## Agent Budget

**Total budget: ~24 agents.** Worst case with 8 friction points (typically 3-4 High-severity):
- 1 explorer (Opus)
- 8 genealogists (Sonnet) — enhanced with change metrics
- 3-4 root cause agents (Sonnet) — NEW, parallel with genealogists, High-severity findings only
- 8 analysis agents (Sonnet) — enhanced, 2000-line hard cap
- 3 design agents (Opus) — enhanced with root cause integration
- 0-1 just-in-time root cause agent (Sonnet) — dispatched only if user selects a Limited candidate

**Concurrency:** Maximum 5 concurrent agents. Genealogy and root cause agents share this budget during their parallel execution window. The orchestrator dispatches them in round-robin fashion (e.g., 3 genealogy + 2 root cause, then backfill as each completes). Once both tracks complete, analysis agents use the full concurrency budget.

The explorer's output cap of 8 friction points enforces the overall budget. If the user requests exploration of a second candidate after completing the first, the budget resets for the new design cycle (Phases 5-8 only), reusing existing exploration and analysis results.

## Scratch Directory

**Canonical path:** `~/.claude/projects/<project-hash>/memory/prospector/scratch/<run-id>/`

The `<run-id>` is a timestamp generated at the start of Phase 1 (e.g., `2026-03-18T14-30-00`). This same identifier is used for all scratch files and session logs throughout the run.

Files:
- `invocation.md` — Written at run start. Contains focus mode ("default", "testability", "coupling", "complexity", "depth") and any user-specified directory scope. Compaction recovery reads this first.
- `explorer-findings.md` — Phase 1 organic explorer output
- `exploration-approved.md` — Phase 1 user gate confirmation
- `genealogy-<n>.md` — Phase 1.5 genealogy per friction point
- `root-cause-<n>.md` — Phase 2 root cause output per High-severity friction point
- `convergence-draft.md` — Phase 2.5 proposed groupings with confidence ratings (checkpoint before user confirmation)
- `convergence.md` — Phase 2.5 root cause convergence output after user confirmation (clusters + standalones)
- `analysis-<n>.md` — Phase 2 structured analysis per friction point
- `candidates.md` — Synthesized candidate list (after analysis)
- `problem-frame.md` — Phase 4 problem space framing
- `design-<n>.md` — Phase 5 competing design outputs
- `decision.md` — Phase 6 user's design choice

**Stale cleanup:** Delete scratch directories older than 24 hours at run start. Prospector runs include unbounded user interaction gaps, so do not delete directories that lack a `decision.md` file and are less than 24 hours old — they may be paused runs.

## Session Tracking

- **Metrics:** `/tmp/crucible-prospector-metrics-<run-id>.log` — agent dispatches, completion times
- **Decision journal:** `/tmp/crucible-prospector-decisions-<run-id>.log` — constraint selection rationale, candidate ranking decisions

## Preferences Storage

Stored in `~/.claude/projects/<project-hash>/memory/prospector/preferences.md`:

```markdown
## Issue Tracker
- Tracker: [github|jira|linear|...]
- Project: [identifier]
```

First run: ask if user wants to file issues and which tracker. Persist for future runs.

## Phase 0.5: Framework Detection

Framework detection is a deterministic orchestrator step that runs BEFORE explorer dispatch. The orchestrator reads dependency manifests directly — this is orchestrator-local work requiring 1-3 file reads, not an agent dispatch.

Phase 0.5 identifies **which frameworks are declared** (name + version). It does NOT determine which framework patterns are used, unused, or available — that requires code-level investigation and is handled by root cause agents in Phase 2 and analysis agents in Phase 3.

### Dependency Manifests Checked

The orchestrator reads whichever of the following exist in the repository root (or known locations):
- `package.json` (Node.js / JavaScript / TypeScript)
- `*.csproj` (C# / .NET)
- `Cargo.toml` (Rust)
- `go.mod` (Go)
- `requirements.txt`, `pyproject.toml`, `setup.cfg` (Python)
- `build.gradle`, `pom.xml` (Java / Kotlin)
- `Gemfile` (Ruby)
- `composer.json` (PHP)

### Output

A "Framework context" block (~5-10 lines) containing:
- Language and runtime version
- DI framework name and version (if any)
- Test framework name and version
- UI/web framework name and version
- Any other domain-relevant frameworks (ORM, messaging, etc.) with versions

This block is a hint for downstream agents, not a definitive reference. Pattern-level investigation (which patterns are available and whether they are used or unused) is the responsibility of root cause agents (Phase 2) who have file access to the actual code.

This block is passed to the explorer agent, all root cause agents, all analysis agents, and all design agents.

## Phase 1: Explore (Organic Discovery)

### Pre-Exploration Context

- **RECOMMENDED:** Consult `crucible:cartographer` (consult mode) — load known module boundaries, conventions, landmines
- **RECOMMENDED:** Consult `crucible:forge` (feed-forward mode) — check past retrospectives for known pain points

### Write Invocation State

At run start, write `scratch/<run-id>/invocation.md` containing:
- Focus mode: "default" | "testability" | "coupling" | "complexity" | "depth"
- Directory scope: user-specified scope or "Entire codebase"

### The Organic Explorer

Dispatch: `Agent tool (subagent_type: Explore, model: Opus)` using `./explorer-prompt.md`

The explorer receives:
- Cartographer data (if available) — module map, conventions, landmines
- Forge signals (if available) — known pain points from past work
- Framework context block (from Phase 0.5) — language, framework names and versions
- The guiding friction examples (full set or focus-specific subset)
- Instruction: "You're a senior developer joining this codebase for the first time. Navigate it naturally. Note where you experience friction."

**Guiding friction examples (default mode):**
- Understanding one concept requires bouncing between many small files
- A module's interface is nearly as complex as its implementation
- Testing requires elaborate mock setups that mirror internal structure
- Changing one behavior requires edits across many unrelated files
- An abstraction exists but doesn't actually simplify anything
- Pure functions extracted for testability, but the real bugs hide in how they're called
- Tightly-coupled modules create integration risk in the seams between them
- Domain concepts scattered across layers with no clear owner
- Code that's hard to navigate — you keep getting lost or losing context

**Focus mode subsets:**

| Focus | Guiding Examples |
|-------|-----------------|
| `testability` | Mock complexity, test-implementation coupling, untestable seams, pure-function extraction that misses real bugs |
| `coupling` | Shotgun surgery, ripple effects, shared mutable state, co-change patterns, circular dependencies |
| `complexity` | Over-abstraction, unnecessary indirection, configuration that exceeds the problem, premature generalization |
| `depth` | Shallow modules (Ousterhout), interface-to-implementation ratio, information hiding gaps, too many small files per concept |

The explorer outputs a structured list of friction points (capped at **top 8**, ranked by severity x frequency), each with:
- **Location:** Files/modules involved
- **Friction description:** What was confusing or resistant
- **Severity:** How much this friction would slow down a developer working in this area (High/Medium/Low)
- **Frequency estimate:** How often a developer would hit this friction (daily, weekly, rarely)

**Write-on-complete:** The orchestrator writes the explorer's output to `scratch/<run-id>/explorer-findings.md` immediately upon agent completion. Do not hold results in context memory only — always persist to disk.

### Explorer Context Budget

The explorer should target 50% of its context window for exploration, reserving the remainder for output generation. For large codebases:
- Start with high-level structure (directory layout, key entry points)
- Drill into areas where friction signals appear
- Report at 50% context usage if significant friction already found
- Do NOT attempt to read every file — organic exploration means following threads, not enumerating
- Maximum ~30 files read at full source depth; use directory listings and interface scanning for breadth

### Large Codebase Scoping

For codebases with 20+ top-level modules or directories:
1. Perform a breadth-first pass first — read top-level directory structure, key entry points, existing architectural docs
2. Produce a directory-level heat map indicating which areas look most promising for friction discovery
3. Present the heat map to the user as part of the exploration review gate

If the explorer produces fewer than 3 friction points, report to the user and offer to re-run with: (a) a different starting area, (b) a `--focus` mode, or (c) user-specified directory scope.

### User Gate: Exploration Review

**USER GATE:** Present the explorer's friction points to the user before committing genealogy and analysis agent dispatches (~16 agents). The user may:
- **Prune:** Remove friction points that aren't interesting or are already known
- **Reorder:** Adjust priority ranking
- **Adjust severity:** Upgrade a finding to High (triggers root cause analysis in Phase 2) or downgrade a High finding (skips root cause analysis)
- **Refocus:** Ask the explorer to re-run with a different `--focus` or in a different area
- **Proceed:** Approve the friction points for genealogy and analysis

Write `scratch/<run-id>/exploration-approved.md` when user confirms.

## Phase 1.5: Friction Genealogy

After user approves exploration results, trace the causal origin of each approved friction point using git archaeology. Root cause analysis agents (Phase 2) run in parallel with genealogy — both investigate the same friction points independently.

### Genealogist Agents

Dispatch: One agent per approved friction point, parallel (max 5), via `Agent tool (subagent_type: general-purpose, model: Sonnet)` using `./genealogist-prompt.md`. Note: `general-purpose` (not `Explore`) because genealogists run git commands (`git log`, `git blame`, `git show`) which require Bash tool access.

### Enhanced Output: Change Metrics

In addition to the standard genealogy data (origin classification, key commits, narrative), the genealogist agent's output now includes two structured numeric fields per friction point file:

- **Change frequency:** Number of commits touching this file in the last 6 months, with rate classification (monthly/weekly/daily)
- **Bug-fix commit count:** Number of commits with bug-fix indicators (e.g., "fix", "bug", "hotfix" in message) touching this file in the last 6 months

The genealogist already runs `git log` and `git blame` on friction point files. These metrics are derived from the same data — no additional tool access is needed.

### Git Metrics Aggregation

When a friction point spans multiple files, the genealogist reports per-file metrics for each file. The orchestrator aggregates these into the analysis agent's prompt as follows:

- **Headline metric:** The hottest file's change frequency and bug-fix commit count are reported as the headline values (e.g., "Change frequency: 14 commits/6mo (weekly) -- `src/services/PaymentProcessor.ts`").
- **Range summary:** A one-line range summary follows: "Range across N files: [lowest]-[highest] commits/6mo, [lowest]-[highest] bug-fix commits."
- **Inaction rules key on the hottest file.** A single hot file within a friction point's scope makes inaction indefensible — the cost is being paid regardless of whether other files are stable.

Each agent classifies the friction's origin:

| Origin Type | Description | Effort Implication |
|-------------|-------------|-------------------|
| **Incomplete Migration** | A refactoring or migration started but never finished | Lower — finish the existing migration path |
| **Accretion** | No single commit caused this; small additions over time | Medium — needs new boundaries |
| **Forced Marriage** | Two unrelated concerns coupled in a single commit | Medium — separation path is clear |
| **Vestigial Structure** | Old architecture replaced but scaffolding remains | Lower — fix may be deletion |
| **Original Sin** | Friction present in initial implementation | Higher — no prior art |
| **Indeterminate** | Git history insufficient (shallow clone, squash-only) | No adjustment |

**Graceful degradation:** Genealogy enriches when available but is never required. If git history is too shallow or all results are Indeterminate, downstream phases proceed without genealogy data.

**Write-on-complete:** The orchestrator writes each genealogist's output to `scratch/<run-id>/genealogy-<n>.md` immediately upon agent completion.

## Phase 2: Root Cause Analysis

Root cause analysis runs in parallel with genealogy. Root cause looks at code structure ("why is this designed this way?"), genealogy traces git history ("how did it get this way?"). Both feed into Phase 2.5 convergence, then Phase 3.

### Dispatch Criteria

Root cause agents are dispatched only for **High-severity** friction points. In a typical run with 8 friction points, 3-4 are High-severity.

- **High-severity findings:** Full root cause analysis via competing causal hypotheses (agent dispatch).
- **Medium/Low-severity findings:** No dedicated root cause agent. These findings receive a lightweight root cause signal: if a neighboring High-severity finding's surviving hypothesis covers the same code area or pattern, the orchestrator extracts a one-line root cause note from it. Otherwise, the finding proceeds with "Root cause not analyzed -- severity below threshold."

### Agent Spec

Dispatch: One agent per approved High-severity friction point, parallel with genealogy (shares max-5 concurrency budget with genealogists, dispatched in round-robin fashion), via `Agent tool (subagent_type: general-purpose, model: Sonnet)` using `./root-cause-prompt.md`.

Each agent receives:
- Friction point description and file locations
- Framework context block (from Phase 0.5, as a hint — agent investigates which patterns are actually used)
- Genealogy data (if available; otherwise runs without it)

Each agent uses the competing causal hypotheses method: generates 2-3 plausible causal hypotheses, defines a falsification criterion for each, tests the criteria against the code, and reports which hypotheses survived.

### Root Cause Types

| Type | Description |
|---|---|
| **Missing or underused pattern** | A known pattern exists in the ecosystem that would solve this, but the code uses a manual approach |
| **Wrong abstraction** | An abstraction exists but it models the wrong concept |
| **Absent boundary** | No module boundary exists where one should |
| **Misaligned ownership** | The boundary exists but the wrong module owns the concept |
| **Other / Constraint-driven** | Root cause is an external constraint, not an internal design flaw |

### Scope and Termination

- **File read budget:** Maximum 15 file reads per agent. Maximum 100 lines per targeted read. After reading 10 files, begin synthesizing regardless of investigation state.
- **Read strategy:** Prefer targeted reads (specific functions/classes, 100-line windows) over full-file reads for large files.
- **Codebase boundary:** If hypothesis testing leads outside the codebase (into framework internals, language runtime, or third-party library code), stop at the codebase boundary. Record the external dependency as the terminal cause.
- **Hypothesis count:** 2-3 hypotheses per friction point. Stop when one hypothesis survives falsification, or when all hypotheses have been tested.

**Write-on-complete:** The orchestrator writes each root cause agent's output to `scratch/<run-id>/root-cause-<n>.md` immediately upon agent completion.

## Phase 2.5: Root Cause Convergence

After all root cause agents and genealogy agents complete, the orchestrator checks whether multiple friction points share the same root cause. When they do, it collapses them into a single "friction cluster" with a unified remediation scope. This prevents producing interfering partial fixes for what is really a single architectural problem.

**No agent dispatch** — this is orchestrator-local work (Opus reads N root-cause files, groups them, writes one file).

### How It Works

1. Read all `root-cause-<n>.md` outputs
2. Group by: same root cause type AND surviving hypothesis root cause statements describe the same architectural decision (semantic match, not string equality)
3. **Merge threshold:** Two friction points merge only when they share the same root cause type AND their root cause statements describe the same underlying architectural decision or missing pattern. Overlapping symptoms or co-located files alone are not sufficient.
4. **Split criterion:** Before merging, ask: "Would a single design change plausibly fix BOTH friction points?" If no, do not merge even if root cause type and statement match.

### Merge Confidence

- **High confidence:** Same root cause type, same architectural decision, AND a single design change would plausibly fix both. High-confidence merges auto-approve (no user confirmation needed).
- **Low confidence:** Same root cause type and similar statements, but unclear whether a single design change covers both (e.g., similar root causes in different subsystems). Low-confidence merges require explicit user confirmation.

### Medium/Low Finding Overlap Check

Before writing the draft, the orchestrator also checks whether any Medium/Low-severity finding (which did not receive a root cause agent) has symptom descriptions and file locations that overlap with a High-severity finding's root cause scope. Overlaps are flagged as Low-confidence potential merges for user confirmation.

### Two-Step Convergence (Compaction-Safe)

1. **Draft step:** Write proposed groupings to `scratch/<run-id>/convergence-draft.md`. Each proposed merge includes its confidence rating (High/Low) and the split criterion assessment. This is a checkpoint — if compaction occurs, the draft survives.
2. **Confirmation step:** Present the draft to the user. High-confidence merges auto-approve; the user decides on Low-confidence merges (approve or split). The user may also split any auto-approved merge or force-merge missed connections. After confirmation, write the final `scratch/<run-id>/convergence.md`.

### Downstream Impact

- Analysis agents (Phase 3) receive merged clusters instead of individual findings
- Candidate list (Phase 4) shows clusters as single candidates with combined leverage scores
- Agent budget is reduced in practice — fewer analysis agents and design cycles for merged clusters

## Phase 3: Structured Analysis (Enhanced)

The orchestrator reads explorer findings, genealogy results, root cause outputs, and convergence data from disk, then dispatches **Structured Analysis Agents** via `Task tool (general-purpose, model: Sonnet)` using `./analysis-prompt.md`. One agent per friction point or convergence cluster, dispatched in parallel (max 5 concurrent).

Each analysis agent receives:
- The friction point description and file locations (or cluster of merged friction points with combined scope)
- Genealogy classification and key commits (if available)
- Root cause summary (max 10 lines, mechanically extracted — see below)
- Framework context block (from Phase 0.5)
- Change metrics from genealogy (change frequency and bug-fix commit counts, aggregated per Git Metrics Aggregation rules)
- Relevant source files (subject to 2000-line hard cap — increased from 1500 to accommodate four new output sections)
- The relevant REFERENCE.md section for the friction type being analyzed

### Root Cause Summary Extraction

The orchestrator produces the root cause summary by extracting four fields **verbatim** from the root cause agent's output — no summarization, no paraphrasing:

1. **Root cause type** (1 line) — copied verbatim from "Type:" field
2. **Root cause statement** (1 line) — copied verbatim from "Root cause statement:" field
3. **Pattern-level fix** (1-2 lines) — copied verbatim from "Pattern-level fix:" field
4. **Framework-native solution** (1-2 lines) — copied verbatim from "Framework-native solution:" field

For convergence clusters, append: "Cluster scope: merged from friction points #X, #Y, #Z — addresses shared root cause as a unit."

For Medium/Low-severity findings without a dedicated root cause agent: use either a one-line note from a neighboring High-severity finding (if applicable) or "Root cause not analyzed -- severity below threshold."

### Source Prioritization for Convergence Clusters

When an analysis agent processes a convergence cluster:
1. **Full source** for the highest-severity constituent finding's files
2. **Interface-only excerpts** (function signatures, class declarations, public API surfaces) for other constituent findings' files
3. If the cluster still exceeds the 2000-line cap after prioritization, the orchestrator **splits the cluster** into sub-clusters that each fit. The orchestrator warns the user: "Cluster [X] exceeds context budget and was split into sub-clusters. This partially reduces the convergence benefit." The decision journal logs the split and rationale. Sub-cluster analysis results are re-merged in the Phase 4 candidate presentation.

Each analysis agent outputs:
- **Friction type classification** — which category from the reference doc
- **Applicable philosophy/framework** — which architectural philosophy best explains this friction
- **Causal origin** — from genealogy (if available), factored into effort estimate
- **Cluster:** Which modules/concepts are involved
- **Why they're coupled:** Shared types, call patterns, co-ownership
- **Dependency category:** In-process, local-substitutable, remote-but-owned, or true external
- **Estimated improvement impact:** High/Medium/Low
- **Estimated effort:** High/Medium/Low — refined by genealogy
- **Friction dimensions** — comprehension friction (High/Medium/Low), modification friction (High/Medium/Low), primary dimension
- **ROI assessment** — leverage score with justification, change frequency, bug correlation
- **Framework check** — framework patterns available, pattern evidence source, applicability
- **Cost of inaction** — change frequency (hottest file + range), bug origin rate, blocking planned work, inaction assessment
- **Interface surface summary** — current public API
- **Top caller patterns** — 3-5 most common usage patterns
- **Structural summary** — module boundaries, data flow direction, dependency graph fragment

The last three fields form the **design brief** consumed by Phase 5 competing design agents.

**Write-on-complete:** The orchestrator writes each analysis agent's output to `scratch/<run-id>/analysis-<n>.md` immediately upon agent completion. (Analysis agents are Task tool dispatches — they return text to the orchestrator, who persists it.)

The orchestrator reads all analysis results from disk and synthesizes into a ranked candidate list using the formula `leverage_score x modification_friction_score` (High=3, Medium=2, Low=1). Ties are broken by comprehension friction score. Effort is shown separately as a cost indicator, not included in the ranking formula. Candidates where inaction is defensible are demoted to a "Track Only" section. Writes to `scratch/<run-id>/candidates.md`.

**USER GATE: Candidate Selection** — Present candidates to the user. Do not proceed until user picks one:

```
### Prospector Candidates

#### Active Candidates (ranked by leverage x modification_friction)

1. **[Score: 9] [Effort: Medium] [Full analysis] Payment processing cluster**
   - Friction: Understanding payment flow requires reading 8 files across 3 directories
   - Root cause: Missing or underused pattern -- no aggregate module, each concern handled individually
   - Origin: Incomplete Migration (commit abc123)
   - Comprehension: High | Modification: High | Leverage: High
   - Framework check: None identified
   - Cost of inaction: Modified weekly, 4 bug-fix commits in 6 months. Not defensible.

2. **[Score: 6] [Effort: Low] [Limited -- no root cause] Auth middleware duplication**
   - Friction: Auth checks duplicated across 4 route handlers
   - Root cause: Root cause not analyzed -- severity below threshold
   - Origin: Organic Growth (no single commit)
   - Comprehension: Medium | Modification: High | Leverage: Medium
   - Framework check: Express middleware pattern (framework hint only -- pattern usage not verified)
   - Cost of inaction: Modified weekly, 2 bug-fix commits in 6 months. Not defensible.

---

#### Track Only (inaction defensible -- low modification friction or low leverage)

3. **[Score: 3] [Effort: Low] [Limited -- no root cause] GameBootstrap god-class**
   - Friction: Hard to read (2,393 lines) but modification pattern is clear (~5 lines per change)
   - Root cause: Missing or underused pattern -- no self-registration, but modification cost is low
   - Comprehension: High | Modification: Low | Leverage: Low
   - Framework check: VContainer IInitializable would solve this (framework hint only -- pattern usage not verified)
   - Cost of inaction: Modified monthly, 0 bug-fix commits. Defensible -- rarely modified, clear patterns.
```

### Data Quality Indicators

Each candidate is tagged with:
- **`[Full analysis]`** — High-severity finding that received a dedicated root cause agent. Framework check is based on code-level investigation.
- **`[Limited -- no root cause]`** — Medium/Low-severity finding that did not receive a root cause agent. Framework check is based on Phase 0.5 hint only.

### Constraint-Driven Root Cause Warning

When a candidate's root cause type is "Other / Constraint-driven," the candidate presentation includes a warning: "Root cause is an external constraint -- designs address symptoms, not the underlying cause." The orchestrator does NOT auto-demote these.

### Just-in-Time Root Cause for Limited Candidates

If the user selects a `[Limited -- no root cause]` candidate for design, the orchestrator dispatches a just-in-time root cause agent for that finding before proceeding to design agent dispatch. This single Sonnet dispatch is cheap compared to dispatching three Opus design agents without root cause data.

After the JIT root cause agent completes, the orchestrator compares its output against existing root-cause files and convergence clusters. If the JIT root cause matches an existing cluster's shared root cause, the orchestrator warns the user: "This finding appears to share a root cause with [cluster X]. Continue separately, merge into cluster X, or skip?" The user decides before design agents are dispatched.

User selects by number. Orchestrator proceeds to problem framing for that candidate.

## Phase 5: Frame the Problem Space

Before spawning competing design agents, write a user-facing explanation:

- **The constraints** any new interface would need to satisfy
- **The dependencies** it would need to rely on
- **The dependency category** and what that means for testing strategy
- **A rough illustrative code sketch** — NOT a proposal, just grounding for the constraints

Write to `scratch/<run-id>/problem-frame.md`.

**USER GATE:** Present the problem framing to the user and wait for confirmation before dispatching design agents. The framing directly determines the constraint selection in Phase 5 — dispatching 3 Opus agents with wrong inputs is expensive. User may adjust constraints, dependencies, or dependency category before proceeding.

## Phase 6: Competing Designs (Contextual Constraints)

### Constraint Selection

The orchestrator selects 3 design constraints from a deterministic mapping in [REFERENCE.md](REFERENCE.md). The mapping is keyed by friction type classification (from Phase 2 analysis). Each friction type has exactly 3 associated constraints — the orchestrator looks up the friction type and uses its constraints. This is a **routing decision, not a creative one.**

**Friction-type-to-constraint mapping (canonical, in REFERENCE.md):**

| Friction Type | Constraint 1 | Constraint 2 | Constraint 3 |
|--------------|--------------|--------------|--------------|
| Shallow modules | Minimize interface (1-3 entry points) | Optimize for most common caller | Hide maximum implementation detail |
| Coupling/shotgun surgery | Consolidate into single module | Introduce facade pattern | Extract shared abstraction with clean boundary |
| Leaky abstraction | Seal the abstraction (hide all internals) | Replace with simpler direct approach | Ports & adapters (injectable boundary) |
| Testability barrier | Boundary-test-friendly interface | Dependency-injectable design | Pure-function extraction with integration wrapper |
| Scattered domain | Aggregate into domain module | Event-driven decoupling | Layered with clear ownership per layer |

If a friction point doesn't match any defined type, the orchestrator falls back to a generic set: "Minimize interface," "Maximize flexibility," "Optimize for most common caller." The decision journal must log which constraint set was selected and why.

### Dynamic Constraint Overrides

The constraint table above is the default. The following overrides apply when root cause analysis provides additional signal:

#### Root-Cause-Aware Framework Override

When the root cause type is "Missing or underused pattern" AND a framework-native solution was identified in Phase 3:
- **Slot 1:** "Adopt framework-native pattern: [specific pattern from Phase 3 framework check]"
- **Slot 2:** From friction-type mapping (custom approach)
- **Slot 3:** From friction-type mapping (custom approach)

#### Root-Cause-Type-Derived Override

When the root cause type suggests a specific design direction:
- **"Wrong abstraction":** One slot becomes "Replace abstraction with correct domain model: [domain concept from surviving hypothesis]"
- **"Absent boundary":** One slot becomes "Introduce boundary at [identified seam from surviving hypothesis]"

These overrides apply to Slot 3. If a framework-native override already occupies Slot 1, the root-cause-type override replaces Slot 3 — both can coexist. Root cause types "Misaligned ownership" and "Other / Constraint-driven" do not trigger this override.

#### Standard Framework-Native Slot

When Phase 3 identified a framework-native solution BUT root cause type is NOT "Missing or underused pattern":
- **Slot 1:** From friction-type mapping
- **Slot 2:** From friction-type mapping
- **Slot 3:** "Framework-native solution" — design agent's constraint is to use only existing framework/language features

When no framework-native solution was identified: all 3 slots from friction-type mapping (unchanged).

The decision journal must log which constraint set was selected and which overrides applied.

### Design Agent Dispatch

Spawn 3 agents in parallel via `Agent tool (subagent_type: general-purpose, model: Opus)` using `./design-competitor-prompt.md`.

Each agent receives (subject to 2000-line hard cap):
- Technical brief from the analysis output (interface surface, caller patterns, structural summary)
- Genealogy context: causal origin classification and key commits (if available)
- Full competing hypotheses output from Phase 2 root cause analysis (all hypotheses with verdicts, surviving hypothesis, root cause classification, framework investigation, remediation direction)
- Framework context block (from Phase 0.5)
- Its assigned design constraint
- The applicable architectural philosophy and why it applies

**Write-on-complete:** The orchestrator writes each design agent's output to `scratch/<run-id>/design-<n>.md` immediately upon agent completion.

Each agent outputs:
1. **Interface signature** — types, methods, params
2. **Usage example** — how callers use the new interface
3. **What complexity it hides** internally
4. **Dependency strategy** — how deps are handled (mapped to the dependency category)
5. **Testing strategy** — what tests look like at the new boundary
6. **Trade-offs** — what you gain and what you give up
7. **Root cause coverage** — Does this design address the root cause? Yes/Partially/No, with explanation

Design agents are instructed: "Your proposal must address the surviving root cause hypothesis, not just the symptom identified by the explorer. Review the falsified hypotheses to understand what the root cause is NOT."

### Presentation

Present designs sequentially, then compare in prose. Give an opinionated recommendation: which design is strongest and why. If elements from different designs combine well, propose a hybrid. The user wants a strong read, not just a menu.

### "Do Nothing" Comparison

After all designs are presented, include a mandatory comparison table with a "Do Nothing" column:

```
| Dimension | Design A | Design B | Design C | Do Nothing |
|---|---|---|---|---|
| Root cause addressed? | Yes | Partially | Yes | No |
| Effort | Medium | Low | High | None |
| Leverage | High | Medium | High | N/A |
| Risk | Medium | Low | High | None |
| Lines changed (est.) | ~200 | ~80 | ~500 | 0 |
| Cost of inaction | -- | -- | -- | [from analysis] |
```

The orchestrator still gives an opinionated recommendation, but "do nothing" is explicitly on the table.

## Phase 7: User Picks a Design

User selects a design, accepts the recommendation, or requests a hybrid. Orchestrator records the decision to `scratch/<run-id>/decision.md`.

## Phase 8: Output

### Design Doc

Write a design doc to `docs/plans/YYYY-MM-DD-prospector-<topic>-design.md` where `<topic>` is a kebab-case slug derived from the selected candidate's name, truncated to 40 characters. If the file already exists, append a numeric suffix (`-2`, `-3`). The doc contains:

- **Friction analysis** — what was found and why it matters
- **Friction genealogy** — causal origin, key commits, how the friction developed (if genealogy data available)
- **Chosen design** — interface, usage, hidden complexity, dependency strategy, testing strategy
- **Competing designs summary** — what was considered and why the winner was chosen
- **Implementation recommendations** — durable architectural guidance not coupled to current file paths

### User Choice

After saving the design doc, ask the user:

> "Design doc saved. Would you like to:
> (a) File this as an issue in your tracker
> (b) Kick off build in refactor mode to implement it
> (c) Just keep the design doc for now
> (d) Explore another candidate from the list"

**Option (a):** File as an issue using whatever tools are available in the environment. Tracker-agnostic — no hardcoded assumption about GitHub, Jira, Linear, or anything else. If tracker preference isn't stored, ask the user. Persist preference.

**Option (b):** Invoke `crucible:build` in refactor mode. The user provides the prospector design doc as context for build's interactive design phase. Build runs its own Phase 1 normally (including blast radius analysis, impact manifest, contract tests).

**Option (c):** Done. Design doc is committed and available for future reference.

**Option (d):** Return to Phase 3 (candidate selection). Reuse existing exploration and analysis results from disk — no re-exploration needed. Budget resets for Phases 4-6 only (3 Opus design agents). New candidate's design doc saved alongside the first.

### End-of-Run Cleanup

Delete `scratch/<run-id>/` after all Phase 7 actions are complete (design doc saved, issue filed if requested, or build handoff initiated).

### Cartographer Recording

After Phase 7, dispatch `crucible:cartographer` (record mode) with the user-approved friction points from the exploration review gate. Record only friction point locations and classifications — not raw explorer observations or unconfirmed speculation.

## Dependency Categories

Classification system for the target code's dependencies:

### 1. In-Process
Pure computation, in-memory state, no I/O. Always improvable — merge modules and test directly.

### 2. Local-Substitutable
Dependencies with local test stand-ins (e.g., SQLite for Postgres, in-memory filesystem). Improvable if the stand-in exists.

### 3. Remote but Owned (Ports & Adapters)
Your own services across a network boundary. Define a port at the module boundary; inject transport. Tests use an in-memory adapter.

### 4. True External (Mock)
Third-party services you don't control (Stripe, Twilio, etc.). Mock at the boundary via injected port.

## Compaction Recovery

After context compaction:
1. Read `scratch/<run-id>/invocation.md` first — recover focus mode and directory scope before any other state
2. Read remaining `scratch/<run-id>/` files to determine current state
3. `explorer-findings.md` exists → Phase 1 exploration complete
4. `exploration-approved.md` exists → user gate passed. If missing but `explorer-findings.md` exists, re-present friction points for confirmation.
5. Check completion state of BOTH parallel tracks before advancing:
   a. Read `explorer-findings.md` to determine expected count N (total) and H (High-severity count)
   b. Count existing `genealogy-<n>.md` files. If fewer than N, dispatch remaining genealogy agents
   c. Count existing `root-cause-<n>.md` files. If fewer than H, dispatch remaining root cause agents (High-severity findings only)
   d. Wait for ALL dispatched agents from BOTH tracks to complete before proceeding
6. `convergence-draft.md` exists but `convergence.md` does not → re-read draft and present to user for confirmation (skip grouping analysis)
7. `convergence.md` exists → Phase 2.5 complete. If neither convergence file exists but all root-cause and genealogy files are complete, re-run convergence from scratch (orchestrator-local, cheap).
8. `candidates.md` exists → Phase 3 complete, re-present to user if no selection recorded
9. `problem-frame.md` exists → Phase 5 complete
10. `design-*.md` files → count competing designs, dispatch remaining if incomplete
11. `decision.md` exists → Phase 7 complete, proceed to output
12. Output status update before continuing

## Guardrails

**The explorer must NOT:**
- Modify any code (prospector is read-only until output phase)
- Follow rigid heuristics — explore organically
- Report friction without specific file/location evidence

**Analysis agents must NOT:**
- Exceed 2000 lines of total prompt content
- Classify friction without evidence from the source code provided in their prompt (analysis agents are Task tool dispatches — they receive pasted source, not file access)
- Speculate about problems they can't point to evidence for

**Design agents must NOT:**
- Produce identical designs with different names — designs must be radically different
- Ignore the assigned constraint
- Propose changes without showing the caller-side impact

**The orchestrator must NOT:**
- Proceed past any user gate without confirmation
- Select design constraints before the analysis phase classifies the friction
- File issues without user approval
- Skip narration between dispatches

## Red Flags

- Explorer producing a checklist instead of organic friction observations
- All three competing designs converging on the same solution (constraints weren't different enough)
- Design agents ignoring dependency category in their testing strategy
- Orchestrator hardcoding tracker-specific commands
- Skipping the problem-framing step (Phase 4)
- Root cause agent restating the symptom instead of identifying an architectural cause
- Convergence merging friction points that share a root cause type but describe different architectural decisions
- All three competing designs ignoring the surviving root cause hypothesis
- Inaction assessment missing when change metrics show weekly+ modification frequency

## Integration

- **Consults:** `crucible:cartographer` (consult mode), `crucible:forge` (feed-forward mode)
- **Records to:** `crucible:cartographer` (record mode) — user-approved friction point locations and classifications only
- **Hands off to:** `crucible:build` (refactor mode) — design doc becomes context for build's design phase
- **Complementary to:** `crucible:audit` — audit finds bugs, prospector finds structural improvements. Run prospector before audit when both are planned.
- **Called by:** Standalone only (user invokes directly)
- **Does NOT use:** `crucible:quality-gate` (prospector is advisory, not a fix loop), `crucible:red-team`

## Subagent Dispatch Summary

| Agent | Model | Dispatch | Prompt Template |
|-------|-------|----------|-----------------|
| Organic Explorer | Opus | Agent tool (Explore) | `./explorer-prompt.md` |
| Genealogist (per friction point) | Sonnet | Agent tool (general-purpose) | `./genealogist-prompt.md` |
| Root Cause (per High-severity friction point) | Sonnet | Agent tool (general-purpose) | `./root-cause-prompt.md` |
| Structured Analysis (per friction point or cluster) | Sonnet | Task tool (general-purpose) | `./analysis-prompt.md` |
| Competing Design Agents (x3) | Opus | Agent tool (general-purpose) | `./design-competitor-prompt.md` |

## Prompt Templates

- `./explorer-prompt.md` — Phase 1 organic exploration dispatch
- `./genealogist-prompt.md` — Phase 1.5 git archaeology, causal origin classification, and change metrics
- `./root-cause-prompt.md` — Phase 2 competing causal hypotheses agent dispatch
- `./analysis-prompt.md` — Phase 3 structured friction analysis dispatch (enhanced with ROI, friction dimensions, framework check, cost of inaction)
- `./design-competitor-prompt.md` — Phase 6 competing design agent dispatch (enhanced with root cause integration)
- `./REFERENCE.md` — Friction taxonomy, philosophy mappings, constraint menu, dependency categories, origin type definitions, root cause type taxonomy, ROI scoring, framework check guidance, cost-of-inaction criteria
