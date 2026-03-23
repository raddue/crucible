---
ticket: "#65"
epic: "none"
title: "/migrate Skill for Autonomous Migration Planning and Execution"
date: "2026-03-23"
source: "spec"
---

# /migrate Skill -- Design Document

## Current State Analysis

### The Migration Gap in the Pipeline

Crucible's skill ecosystem covers discovery-through-execution for new features and refactoring, but migration -- the phased transition of an entire dependency, framework version, or API surface -- sits in an uncovered gap between existing skills:

1. **Prospector** (`skills/prospector/SKILL.md`) discovers friction and proposes competing redesigns. It can surface "you should modernize X" but does not plan phased transitions. Its output is a problem frame and design candidates (Phase 5-6), not a sequenced migration plan with compatibility shims.

2. **Build's refactor mode** (`skills/build/SKILL.md`, lines 108-596) executes structural changes with GREEN-GREEN discipline, blast radius analysis, contract tests, and coordinated-atomic steps. But it requires a pre-written plan and treats the refactoring as a single atomic project. It does not understand multi-phase transitions where old and new versions coexist, nor does it generate compatibility layers.

3. **Pathfinder** (`skills/pathfinder/SKILL.md`) maps cross-repo service topology -- repos, dependencies, communication edges. It can answer "what depends on shared-auth v2?" but it does not plan migration waves or generate shims.

4. **Cartographer** (`skills/cartographer-skill/SKILL.md`) provides intra-repo structural knowledge -- module boundaries, dependencies, conventions. It does not reason about version transitions.

5. **Quality-gate** (`skills/quality-gate/SKILL.md`) provides iterative red-teaming on artifacts. It can verify each migration phase's output but has no migration-specific review criteria.

6. **Test-coverage** (`skills/test-coverage/SKILL.md`) audits test alignment after code changes. It can verify tests adapt to new API surfaces but does not drive the migration itself.

**The missing piece:** No skill knows how to decompose "upgrade React Router from v5 to v6" or "migrate shared-auth from v2 to v3" into safe atomic phases with compatibility shims at boundaries, consumer wave grouping, and rollback points. Today, a human must manually bridge prospector's "you should modernize X" output into a build-ready plan. `/migrate` closes this gap.

### How Migrations Currently Work Without This Skill

Without `/migrate`, a migration requires:

1. Manual investigation of what changed between versions (reading changelogs, migration guides, API diffs)
2. Manual blast radius analysis (which consumers use the old API, which patterns need updating)
3. Manual decomposition into safe phases (figuring out which changes can coexist)
4. Manual compatibility layer design (writing shims, adapters, facade patterns)
5. Manual consumer grouping (which repos/modules can migrate independently)
6. Handing each phase to `/build` refactor mode as a separate, disconnected invocation

This is error-prone because the human must hold the entire migration graph in their head, and each `/build` invocation has no awareness of the broader migration context.

## Target State

### Skill Purpose

`/migrate` is a migration orchestrator that takes a migration target (framework upgrade, API version bump, dependency major version, deprecation removal) and autonomously produces a phased migration plan with:

- **Phase decomposition** -- each phase is a safe stopping point where the codebase compiles, tests pass, and old + new code coexist
- **Compatibility layer generation** -- shims/adapters that allow gradual consumer migration
- **Consumer wave grouping** -- independent consumers migrate in parallel waves
- **Rollback points** -- each phase can be independently reverted
- **Execution handoff** -- phases execute through build's refactor mode, or output the plan for manual execution

### Invocation

```
/migrate "upgrade shared-auth from v2 to v3"
/migrate "remove deprecated PaymentProcessor.legacy_charge method"
/migrate "upgrade React Router from v5 to v6"
/migrate --plan-only "upgrade Django from 4.2 to 5.0"   # plan without executing
/migrate --execute docs/plans/2026-03-23-shared-auth-migration-plan.md  # execute existing plan
```

### Execution Model

The skill operates in two modes:

1. **Plan mode** (default with `--plan-only`, or first half of full mode): Investigate, analyze, decompose, and produce a phased migration plan
2. **Execute mode** (default second half, or `--execute` with an existing plan): Hand each phase to build's refactor mode sequentially, verifying phase gates between handoffs

### Skill Type

**Rigid** -- follow exactly, no shortcuts. Migrations are high-blast-radius operations where skipping steps causes cascading failures.

### Model Allocation

- **Orchestrator:** Opus
- **Migration Analyzer** (Phase 1): Opus via Agent tool (subagent_type: Explore) -- needs deep investigation of changelogs, API diffs, breaking changes
- **Blast Radius Mapper** (Phase 2): Sonnet via Agent tool (subagent_type: general-purpose) -- structural search, does not require creative reasoning
- **Phase Planner** (Phase 3): Opus via Task tool -- needs architectural judgment about safe decomposition
- **Compatibility Layer Designer** (Phase 4): Opus via Task tool -- needs API design judgment
- **Consumer Wave Grouper** (Phase 5): Sonnet via Task tool -- graph traversal, no creative reasoning required
- **Build handoff** (Phase 7): Existing build refactor mode pipeline

## Key Decisions

### Decision 1: Phased migration plan as the core artifact

**Choice:** The primary output is a structured migration plan document with phases, not a single monolithic refactoring plan.

**Reasoning:** Migrations differ from refactoring in a critical way: they must support long-lived coexistence of old and new versions. A single-phase refactoring plan (what build's refactor mode expects) works when you can atomically swap old for new. Migrations often cannot -- consumers migrate over days or weeks, and the compatibility layer must work throughout. The phased plan captures this temporal dimension that a flat task list cannot.

**Alternatives rejected:**
- Extending build's refactor mode with multi-phase awareness. Rejected because it would bloat build's already complex orchestration (700+ lines) and conflate two distinct concerns: structural refactoring (same version, change shape) vs. migration (old version to new version, coexistence period).
- Producing a series of independent build plans. Rejected because they would lack awareness of each other -- phase 3 would not know about the compatibility layer introduced in phase 2.

### Decision 2: Compatibility layer as explicit phase output, not implicit

**Choice:** Phase 4 (Compatibility Layer Design) produces an explicit adapter/shim specification that becomes part of the plan. The shim is a first-class artifact, not hidden implementation detail.

**Reasoning:** Compatibility shims are the highest-risk part of any migration. They are temporary code that must be correct in both directions (old consumers calling through the shim to new implementation, and new consumers calling the new API directly). Making them explicit allows quality-gate to review the shim design before any code is written, and allows the shim removal to be planned as a distinct phase.

### Decision 3: Build's refactor mode for execution, not a new execution engine

**Choice:** `/migrate` delegates execution to build's refactor mode (per-phase), rather than implementing its own execution pipeline.

**Reasoning:** Build's refactor mode already handles blast radius analysis (`skills/build/SKILL.md` lines 214-248), contract test writing (lines 251-274), coordinated-atomic execution (lines 556-567), tiered test strategy (lines 548-553), and rollback policy (lines 577-596). Reimplementing these would be duplication. Each migration phase maps to a single refactor-mode invocation with the phase's scope as the "target."

**Constraint:** This means each migration phase must be expressible as a refactor-mode task. The migrate skill's phase planner must ensure this. Phases that require non-refactoring work (e.g., "add v3 as peer dependency alongside v2") use build's feature mode instead.

### Decision 4: Cross-repo awareness via pathfinder, not reimplemented

**Choice:** When the migration target is a shared dependency consumed across repos (detected by pathfinder topology data), the migrate skill uses pathfinder's query mode for cross-repo blast radius and consumer discovery.

**Reasoning:** Pathfinder already maps inter-repo dependencies (`skills/pathfinder/SKILL.md` lines 1-27). Its query mode can answer "what repos depend on shared-auth?" without a full rescan. Reimplementing cross-repo discovery would duplicate pathfinder's logic and miss edges that pathfinder already knows about.

**Limitation:** If pathfinder has not been run against the relevant orgs, cross-repo awareness degrades gracefully to single-repo mode. The skill warns the user: "No pathfinder topology found for [org]. Cross-repo consumers will not be discovered. Run `crucible:pathfinder` first for cross-repo migration planning."

### Decision 5: User gate between planning and execution

**Choice:** The skill presents the complete phased plan for user approval before executing any phase.

**Reasoning:** Migrations are high-stakes, high-blast-radius operations. Unlike a single-feature build where the design phase provides the user gate, a migration plan involves judgment calls about phase boundaries, compatibility layer design, and consumer wave grouping that the user must validate. Autonomous execution without plan approval would be reckless for work that teams typically defer for years.

### Decision 6: Separate scratch directory, not reusing build's

**Choice:** `/migrate` maintains its own scratch directory at `~/.claude/projects/<project-hash>/memory/migrate/scratch/<run-id>/` with migration-specific state.

**Reasoning:** The migration has state that does not map to build's state model: phase progression, compatibility layer specs, consumer wave assignments, cross-repo status. Sharing build's scratch directory would create coupling between the migration orchestrator and the build execution engine. Each build invocation (one per phase) manages its own build scratch directory independently.

## Migration/Implementation Path

### Phase Structure

The skill follows a 7-phase methodology:

```
Phase 1: Analyze Migration Target
  |
Phase 2: Map Blast Radius
  |
Phase 3: Decompose into Phases
  |
Phase 4: Design Compatibility Layer
  |
Phase 5: Plan Consumer Waves
  |
  +-- USER GATE: Approve migration plan
  |
Phase 6: Define Rollback Points
  |
Phase 7: Execute via Build (per-phase, sequential)
  |
Phase 8: Cleanup (remove compatibility layers, old version)
```

### Phase 1: Analyze Migration Target

The Migration Analyzer agent investigates the migration target:

- **Input:** User-provided migration description (e.g., "upgrade shared-auth from v2 to v3")
- **Investigation:** Reads changelogs, migration guides (if available in repo or accessible via web), API diffs between versions, breaking change lists, deprecation notices
- **Output:** Structured migration analysis:
  - What is changing (API surface delta)
  - What is breaking (backward-incompatible changes)
  - What is deprecated (removals in new version)
  - What is new (additions that consumers may want to adopt)
  - Estimated migration complexity (Low/Medium/High based on number of breaking changes x number of consumers)

The orchestrator consults cartographer (consult mode) and forge (feed-forward) before dispatching the analyzer, following the pattern established by prospector (`skills/prospector/SKILL.md` lines 137-141) and build (`skills/build/SKILL.md` lines 163-166).

### Phase 2: Map Blast Radius

The Blast Radius Mapper identifies all affected code:

- **Intra-repo:** Uses cartographer module data (if available) or falls back to language-aware symbol search, following build's refactor mode pattern (`skills/build/SKILL.md` lines 214-247)
- **Cross-repo:** Queries pathfinder topology (if available) for inter-repo consumers of the migration target
- **Output:** Impact manifest (same format as build's refactor mode) plus a consumer registry listing every consumer with:
  - Consumer location (file path or repo name)
  - Usage pattern (how it calls the old API)
  - Migration complexity per consumer (simple mechanical update vs. complex behavioral change)
  - Independence flag (can this consumer migrate independently of others?)

### Phase 3: Decompose into Phases

The Phase Planner takes the migration analysis and blast radius, then decomposes into ordered phases. Each phase must satisfy the **safe stopping point invariant**: after completing any phase, the codebase compiles, all tests pass, and both old and new code paths work.

Standard phase template (adapted per migration type):

1. **Introduce new version** -- add new dependency/API alongside old, no consumers changed
2. **Add compatibility layer** -- shims that expose new API through old interface (or vice versa)
3. **Migrate consumers (waves)** -- grouped by independence, each wave is a separate sub-phase
4. **Remove compatibility layer** -- delete shims once all consumers are migrated
5. **Remove old version** -- delete old dependency/API

The planner may collapse or expand phases based on migration complexity. A simple single-consumer deprecation removal may need only 2 phases (remove + update consumer). A cross-repo framework upgrade may need 10+ phases.

### Phase 4: Design Compatibility Layer

The Compatibility Layer Designer produces:

- **Shim specification:** What adapters/facades are needed, their interface, their mapping from old to new
- **Coexistence strategy:** How old and new code run simultaneously (dual dependency, feature flag, interface adapter)
- **Migration direction:** Whether consumers call old-interface-to-new-implementation (strangler fig) or new-interface-with-old-fallback

This phase is skipped for migrations that do not require coexistence (e.g., a simple in-place API rename with no external consumers).

### Phase 5: Plan Consumer Waves

The Consumer Wave Grouper takes the consumer registry from Phase 2 and the independence flags to produce wave assignments:

- **Wave 1:** Consumers with no dependencies on other consumers (leaf nodes)
- **Wave 2:** Consumers that depend only on Wave 1 consumers
- **Wave N:** Consumers that depend on Wave N-1 consumers
- **Within each wave:** Independent consumers can migrate in parallel

For cross-repo migrations, each wave maps to a set of repos that can be migrated simultaneously.

### USER GATE: Plan Approval

The complete migration plan is presented to the user:

- Phase list with descriptions, affected files/repos, estimated effort per phase
- Compatibility layer design
- Consumer wave assignments
- Rollback strategy per phase
- Total estimated effort

The user may: approve, modify phases, reorder waves, exclude consumers, or abort.

### Phase 6: Define Rollback Points

For each phase, the skill defines:

- **Pre-phase commit SHA** (recorded at execution time)
- **Rollback procedure** (what to revert, what to keep)
- **Rollback test** (which tests to run after rollback to verify clean state)

This integrates with build's refactor mode rollback policy (`skills/build/SKILL.md` lines 577-596), extending it to the multi-phase case where rolling back phase N must not break phases 1 through N-1.

### Phase 7: Execute via Build

Each phase is dispatched to build's refactor mode as a self-contained refactoring task:

- Phases that restructure code use build refactor mode
- Phases that add new code (e.g., adding new dependency, creating shim) use build feature mode
- Between phases, the migrate orchestrator runs the full test suite + any migration-specific verification (e.g., "both v2 and v3 endpoints respond correctly")
- Quality-gate runs on each phase's output (artifact type: code)
- Test-coverage audits test alignment after each phase

### Phase 8: Cleanup

After all consumers are migrated:

1. Remove compatibility layer (shims, adapters, facades)
2. Remove old version dependency
3. Run full test suite to verify clean removal
4. Quality-gate the cleanup changes

## Risk Areas

### Risk 1: Phase boundary correctness

**Risk:** A phase decomposition that looks safe on paper may not actually satisfy the safe-stopping-point invariant (codebase compiles, tests pass, old + new coexist).

**Mitigation:** Each phase boundary is verified by running the full test suite before proceeding to the next phase. Build's refactor mode already enforces this with its pre-execution coverage check and tiered test strategy. The quality gate on each phase's output catches correctness issues. The Phase Planner receives explicit instructions to verify coexistence at each boundary.

### Risk 2: Compatibility layer incorrectness

**Risk:** The shim/adapter translates incorrectly between old and new APIs, causing subtle behavioral differences that pass tests but break production.

**Mitigation:** The compatibility layer design is quality-gated before execution. Contract tests (from build's refactor mode) lock existing behavior before the shim is introduced. The shim itself gets dedicated tests verifying bidirectional correctness. Adversarial tester from build's pipeline stress-tests the shim boundary.

### Risk 3: Cross-repo coordination failures

**Risk:** For cross-repo migrations, repo A migrates successfully but repo B's migration fails, leaving the system in a split state.

**Mitigation:** Each repo migration is a self-contained phase with its own rollback point. The compatibility layer persists until ALL repos have migrated -- it is not removed in the same phase as the last consumer migration. The wave structure ensures that repos migrate in dependency order, so a failure in wave N does not affect already-migrated wave N-1 repos.

### Risk 4: Pathfinder topology staleness

**Risk:** Pathfinder data may be stale -- new consumers may have been added since the last scan, or removed consumers may still appear.

**Mitigation:** The blast radius mapping phase explicitly notes when pathfinder data was last updated. If the topology is older than 7 days, the skill recommends running a pathfinder diff before proceeding. The user gate allows manual addition of consumers not in the topology.

### Risk 5: Context exhaustion for large migrations

**Risk:** A migration touching 50+ consumers across 10+ repos will exhaust the orchestrator's context window.

**Mitigation:** Follow the context management patterns established by spec (`skills/spec/SKILL.md` lines 202-231): preemptive context checkpoints between phases, per-phase context lifecycle, state persisted to scratch directory. The orchestrator holds only the current phase's context, not the full migration history. Compaction recovery reads state from disk.

## Acceptance Criteria

1. **AC-1:** Given a migration target description, the skill produces a phased migration plan with at least 2 phases, where each phase has: description, affected files, estimated effort, and a defined rollback point.

2. **AC-2:** The phased plan satisfies the safe-stopping-point invariant: a quality-gate reviewer confirms that each phase boundary allows the codebase to compile, pass tests, and have both old and new code coexist.

3. **AC-3:** For migrations requiring coexistence, the skill produces an explicit compatibility layer specification (shim/adapter design) that is quality-gated before execution begins.

4. **AC-4:** Consumer wave grouping correctly identifies independent consumers (no shared dependencies between consumers in the same wave), verified by checking that no consumer in wave N depends on another consumer in wave N.

5. **AC-5:** When pathfinder topology data is available, the skill discovers cross-repo consumers of the migration target and includes them in the blast radius and wave plan.

6. **AC-6:** When pathfinder topology data is unavailable, the skill degrades gracefully to single-repo mode with a clear warning to the user.

7. **AC-7:** Each migration phase executes successfully through build's refactor mode (or feature mode for additive phases), with test suite verification between phases.

8. **AC-8:** The `--plan-only` flag produces the complete plan without executing any phases. The `--execute` flag accepts an existing plan file and executes its phases.

9. **AC-9:** The user is presented with the complete migration plan for approval before any execution begins. The user can modify, reorder, exclude, or abort.

10. **AC-10:** The skill persists all state to a scratch directory and recovers correctly after context compaction, resuming from the last completed phase.

11. **AC-11:** The skill integrates with cartographer (consult mode at start), forge (feed-forward at start), pathfinder (query mode for cross-repo), quality-gate (per-phase verification), and test-coverage (per-phase test alignment audit).
