---
ticket: "#65"
epic: "none"
title: "/migrate Skill for Autonomous Migration Planning and Execution"
date: "2026-03-23"
source: "spec"
---

# /migrate Skill -- Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use crucible:build to implement this plan task-by-task.

**Goal:** Create a new `/migrate` skill that takes a migration target and autonomously produces a phased migration plan with compatibility verification at each phase, then optionally executes it through build's refactor mode.

**Architecture:** New skill directory `skills/migrate/` containing a SKILL.md (~400 lines), 5 prompt templates, and 4-5 eval scenarios. The skill is an orchestrator that dispatches investigation and planning agents, produces a structured migration plan, and delegates execution to build's existing refactor mode. No new infrastructure -- uses existing subagent dispatch patterns, quality-gate, test-coverage, pathfinder query mode, and cartographer consult mode.

**Tech Stack:** Markdown skill documentation and prompt templates (no executable code)

---

### Task 1: Create SKILL.md Core Structure

- **Files:** `skills/migrate/SKILL.md` (1 file -- new)
- **Complexity:** High
- **Dependencies:** None

Create the main skill definition file with the following sections. This task covers the skill frontmatter, overview, invocation syntax, communication requirement, model allocation, scratch directory specification, and session tracking -- everything except the phase methodology and integration sections (Tasks 2-4).

**Step 1: Write the YAML frontmatter and overview**

```yaml
---
name: migrate
description: "Autonomous migration planning and execution. Takes a migration target (framework upgrade, API version bump, dependency major version, deprecation removal) and produces a phased migration plan with compatibility verification, then optionally executes via build's refactor mode. Triggers on /migrate, 'migration plan', 'upgrade X from Y to Z', 'remove deprecated', 'major version bump'."
---
```

The overview section must state:
- Purpose: bridge between prospector discovery and build execution for migration work
- Two modes: plan-only (produces plan) and full (plan + execute)
- Skill type: Rigid
- Announce text: "Running migrate on [migration target description]."

**Step 2: Write the invocation section**

Document four invocation patterns:
- Default: `/migrate "description"` (plan + execute)
- Plan only: `/migrate --plan-only "description"`
- Execute existing: `/migrate --execute <plan-file-path>`
- Cross-repo: `/migrate --orgs org1,org2 "description"` (enables pathfinder cross-repo query)

**Step 3: Write the communication requirement**

Follow the exact pattern from build (`skills/build/SKILL.md` lines 18-33) and prospector (`skills/prospector/SKILL.md` lines 30-49): mandatory status updates between every agent dispatch and completion, including current phase, what completed, what's next, and phase progress. Include compaction recovery instructions.

**Step 4: Write the pipeline status section**

Follow the shared pipeline status format from build (`skills/build/SKILL.md` lines 36-104). The skill-specific body should show:
- Phase progress (Analysis -> Blast Radius -> Decomposition -> Compatibility -> Waves -> Approval -> Execution)
- Per-phase status (pending/in-progress/complete/skipped)
- Consumer wave status (during execution)

Health state machine:
- GREEN: normal progress
- YELLOW: quality gate round 3+ on any phase, phase retry in progress
- RED: phase execution failure, test suite failure unresolved, stagnation in quality gate

**Step 5: Write the model allocation table**

| Agent | Model | Dispatch Method |
|-------|-------|-----------------|
| Orchestrator | Opus | -- |
| Migration Analyzer | Opus | Agent tool (Explore) |
| Blast Radius Mapper | Sonnet | Agent tool (general-purpose) |
| Phase Planner | Opus | Task tool |
| Compatibility Layer Designer | Opus | Task tool |
| Consumer Wave Grouper | Sonnet | Task tool |

**Step 6: Write the scratch directory specification**

Canonical path: `~/.claude/projects/<project-hash>/memory/migrate/scratch/<run-id>/`

Files:
- `invocation.md` -- migration target, mode (plan-only/full), orgs scope
- `migration-analysis.md` -- Phase 1 output (API delta, breaking changes, complexity)
- `blast-radius.md` -- Phase 2 output (impact manifest + consumer registry)
- `phase-plan.md` -- Phase 3 output (ordered phases with safe stopping points)
- `compatibility-spec.md` -- Phase 4 output (shim/adapter design)
- `wave-plan.md` -- Phase 5 output (consumer wave assignments)
- `migration-plan.md` -- consolidated plan (presented at user gate)
- `rollback-points.md` -- Phase 6 output (per-phase rollback definitions)
- `execution-status.json` -- Phase 7 tracking (per-phase execution status)
- `phase-N/` -- per-phase build execution scratch (delegated to build's scratch)

Stale cleanup: delete scratch directories older than 48 hours (migrations run longer than most skills). Preserve directories where `execution-status.json` shows any phase in `executing` or `failed` status.

**Step 7: Write the context management section**

Follow spec's context budget management pattern (`skills/spec/SKILL.md` lines 202-231):
- Preemptive context checkpoint between phases
- Per-phase context lifecycle (load only current phase's inputs)
- Compaction recovery reads state from scratch directory
- Complex migrations (10+ phases) use aggressive summarization of completed phases

**Step 8: Write the compaction recovery section**

Recovery procedure:
1. Read `invocation.md` -- recover migration target, mode, scope
2. Read `execution-status.json` -- determine which phases are complete/in-progress/pending
3. Read `migration-plan.md` -- recover the approved plan
4. For any phase in `executing` status: restart that phase from the beginning (safe because build's refactor mode has its own rollback)
5. Resume processing from the next pending phase

**Verification:** The SKILL.md file exists, contains all listed sections, and follows the structural conventions of existing rigid skills (build, prospector, quality-gate).

---

### Task 2: Write SKILL.md Phase Methodology (Phases 1-5: Planning)

- **Files:** `skills/migrate/SKILL.md` (1 file -- continued from Task 1)
- **Complexity:** High
- **Dependencies:** Task 1

Add the planning phases to SKILL.md. This task covers Phase 0 through Phase 5 (everything before execution).

**Step 1: Write Phase 0 -- Pre-flight**

Before any agent dispatch:
1. Consult cartographer (consult mode) -- load known module boundaries, following prospector's pattern (`skills/prospector/SKILL.md` lines 137-141)
2. Consult forge (feed-forward) -- check past lessons
3. If `--orgs` specified, check pathfinder topology existence at `~/.claude/memory/pathfinder/<org>/topology.json`. If missing, warn: "No pathfinder topology found for [org]. Run crucible:pathfinder first for cross-repo migration planning."
4. If `--execute` specified, read the existing plan file and skip to Phase 7

**Step 2: Write Phase 1 -- Analyze Migration Target**

Dispatch the Migration Analyzer (Opus, Agent tool, Explore subagent) using `./migration-analyzer-prompt.md`.

Input: migration description, cartographer data (if available), framework context (read from dependency manifests following prospector's Phase 0.5 pattern at `skills/prospector/SKILL.md` lines 104-134).

The analyzer investigates:
- Changelog / migration guide (reads from repo if present, e.g., CHANGELOG.md, MIGRATION.md, UPGRADING.md)
- API diff between versions (compares old vs new type definitions, function signatures, endpoint contracts)
- Breaking changes (backward-incompatible removals or signature changes)
- Deprecation notices (what the new version removes that the old version warned about)
- New capabilities (additions consumers may want to adopt during migration)

Output: structured migration analysis written to `scratch/<run-id>/migration-analysis.md`.

Estimated complexity classification:
- **Low:** <5 breaking changes, <10 consumers, no behavioral changes (pure API rename/reorganization)
- **Medium:** 5-20 breaking changes, 10-50 consumers, some behavioral changes
- **High:** 20+ breaking changes, 50+ consumers, significant behavioral changes, cross-repo scope

**Step 3: Write Phase 2 -- Map Blast Radius**

Dispatch the Blast Radius Mapper (Sonnet, Agent tool, general-purpose).

Input: migration analysis from Phase 1, cartographer module data (if available).

Intra-repo mapping (follows build refactor mode's blast radius analysis pattern, `skills/build/SKILL.md` lines 214-247):
- Direct consumers: code that imports/calls/references the migration target
- Indirect dependents: code that depends on direct consumers (transitive)
- Test coverage: which tests exercise the target behavior
- Configuration/wiring: config files, DI registrations, build scripts referencing the target

Cross-repo mapping (when pathfinder data available):
- Query pathfinder: `crucible:pathfinder query downstream <package-name>`
- For each downstream repo: estimate migration complexity (simple/complex based on usage pattern depth)

Output: impact manifest + consumer registry written to `scratch/<run-id>/blast-radius.md`.

Consumer registry entry format:
```
- consumer: <file path or org/repo>
  usage_pattern: "calls TargetClass.method(args)"
  migration_complexity: low|medium|high
  independent: true|false
  reason_if_dependent: "shares state with <other consumer>"
```

**Step 4: Write Phase 3 -- Decompose into Phases**

Dispatch the Phase Planner (Opus, Task tool).

Input: migration analysis + blast radius + consumer registry.

The planner produces an ordered list of migration phases. Each phase must satisfy the **safe stopping point invariant**: after completing the phase, the codebase compiles, all tests pass, and both old and new code paths function correctly.

Standard phase template (adapted by planner based on migration type):

| Phase | Description | Build Mode | Typical Content |
|-------|-------------|------------|-----------------|
| 1 | Introduce new version | Feature | Add new dependency alongside old |
| 2 | Add compatibility layer | Feature | Create shims/adapters |
| 3a-3N | Migrate consumer waves | Refactor | Update consumers wave-by-wave |
| 4 | Remove compatibility layer | Refactor | Delete shims once all consumers migrated |
| 5 | Remove old version | Refactor | Delete old dependency |

Each phase entry includes:
- Phase number and description
- Affected files/repos
- Build mode (feature or refactor)
- Estimated effort (Low/Medium/High)
- Safe stopping point verification criteria
- Dependencies on prior phases

Write-on-complete: `scratch/<run-id>/phase-plan.md`

**Step 5: Write Phase 4 -- Design Compatibility Layer**

Dispatch the Compatibility Layer Designer (Opus, Task tool) using `./compatibility-designer-prompt.md`.

Input: migration analysis (API delta) + phase plan (which phases need coexistence).

Skip condition: If Phase 3 determined no coexistence period is needed (e.g., simple in-place rename with no external consumers), skip this phase entirely. Write "Compatibility layer: SKIPPED (no coexistence period required)" to scratch.

Output: compatibility specification written to `scratch/<run-id>/compatibility-spec.md`:
- Shim inventory: list of adapters/facades with their interfaces
- Mapping: old API call -> shim -> new API call (for each shim)
- Direction: strangler fig (old-to-new) or facade (new-to-old)
- Tests: what tests the shim needs (bidirectional correctness)
- Removal criteria: when each shim can be safely deleted

**Step 6: Write Phase 5 -- Plan Consumer Waves**

Dispatch the Consumer Wave Grouper (Sonnet, Task tool).

Input: consumer registry from Phase 2 + phase plan from Phase 3.

Algorithm:
1. Build dependency graph among consumers (consumer A depends on consumer B if A imports/calls B)
2. Topological sort: consumers with no dependencies on other consumers go in Wave 1
3. Consumers depending only on Wave 1 consumers go in Wave 2
4. Continue until all consumers assigned
5. Within each wave, verify independence (no consumer in the wave depends on another in the same wave)

Output: wave assignments written to `scratch/<run-id>/wave-plan.md`.

For cross-repo migrations: each wave entry includes repo name, estimated effort per repo, and CI pipeline considerations.

**Step 7: Write the User Gate section**

After Phase 5, the orchestrator consolidates all outputs into `scratch/<run-id>/migration-plan.md` and presents the complete plan:

```
### Migration Plan: [target description]

**Complexity:** [Low/Medium/High]
**Phases:** N
**Consumer waves:** M
**Estimated total effort:** [estimate]
**Cross-repo scope:** [yes/no, N repos]

#### Phase Summary
[table of phases with descriptions, affected files, effort, build mode]

#### Compatibility Layer
[shim inventory or "not required"]

#### Consumer Waves
[wave assignments with independence verification]

#### Rollback Strategy
[per-phase rollback approach]
```

User may: approve, modify phases, reorder waves, exclude consumers, add consumers, or abort.

Save the plan to `docs/plans/YYYY-MM-DD-<topic>-migration-plan.md` after approval.

**Verification:** Phases 0-5 are fully documented with agent dispatch specifications, input/output formats, and skip conditions. Each phase references its prompt template.

---

### Task 3: Write SKILL.md Phase Methodology (Phases 6-8: Execution and Cleanup)

- **Files:** `skills/migrate/SKILL.md` (1 file -- continued from Task 2)
- **Complexity:** Medium
- **Dependencies:** Task 2

Add the execution and cleanup phases to SKILL.md.

**Step 1: Write Phase 6 -- Define Rollback Points**

Orchestrator-local work (no agent dispatch):

For each phase in the approved plan, define:
- Rollback trigger: what failure condition causes rollback
- Rollback scope: which commits to revert
- Post-rollback verification: which tests to run
- Impact on other phases: does rolling back phase N invalidate phase N+1?

Rollback principles:
- Each phase is independently revertible (reverting phase N does not require reverting phases 1 through N-1)
- The compatibility layer MUST remain in place until the cleanup phase -- this is what makes intermediate rollback safe
- Cross-repo rollback: if repo A's migration fails in wave M, only repo A's wave M changes are reverted; other repos in wave M are unaffected if they migrated independently

Write to `scratch/<run-id>/rollback-points.md`.

**Step 2: Write Phase 7 -- Execute via Build**

Sequential phase execution:

```
For each phase in approved plan:
  1. Update execution-status.json: phase -> "executing"
  2. Determine build mode (feature or refactor) from phase plan
  3. Dispatch build with:
     - Mode: feature or refactor (from phase plan)
     - Design doc: phase description + affected files + compatibility spec (if applicable)
     - Scope: phase's file list
  4. Build executes its full pipeline (design -> plan -> execute -> complete)
  5. After build completes:
     - Run migration-specific verification:
       a. Both old and new API paths respond correctly (if coexistence phase)
       b. Compatibility layer tests pass (if shim exists)
       c. Consumer tests pass for migrated consumers
     - If verification passes: update execution-status.json: phase -> "complete"
     - If verification fails: update execution-status.json: phase -> "failed"
       - Execute rollback procedure from Phase 6
       - Escalate to user with failure context
  6. Quality-gate the phase output (artifact type: code)
  7. Test-coverage audit on the phase's changes
  8. Proceed to next phase
```

Between-phase gate: full test suite must pass before proceeding to the next phase. This is stricter than build's intra-task tiered test strategy (`skills/build/SKILL.md` lines 548-553) because migration phases have higher blast radius than individual refactoring tasks.

**Step 3: Write Phase 8 -- Cleanup**

After all consumer waves complete:

1. Remove compatibility layer (dispatch build refactor mode targeting shim files)
2. Remove old version dependency (update dependency manifests)
3. Run full test suite
4. Quality-gate the cleanup changes
5. Final migration-specific verification: only new API paths respond (old paths should fail gracefully or not exist)

Cleanup is a distinct phase because premature shim removal is the most common migration failure mode. Keeping it separate ensures the user explicitly approves shim removal.

**Step 4: Write the escalation triggers section**

Follow build's pattern (`skills/build/SKILL.md` lines 666-675):
- Phase execution failure after rollback
- Quality gate stagnation on any phase
- Test suite failures not obviously related to the migration
- Cross-repo migration coordination failure (one repo fails while others succeed)
- Compatibility layer tests fail (the shim is incorrect)
- User-requested abort at any point

**Step 5: Write the red flags section**

- Skipping the user gate before execution
- Removing compatibility layer before all consumers are migrated
- Executing phases out of order
- Proceeding to next phase when current phase tests are failing
- Attempting cross-repo migration without pathfinder data (should warn, not block)
- Allowing build to modify files outside the current phase's scope

**Verification:** Phases 6-8 are fully documented. Execution flow correctly delegates to build's refactor/feature mode. Rollback policy is defined for each phase. Escalation triggers cover migration-specific failure modes.

---

### Task 4: Write SKILL.md Integration and Prompt Template References

- **Files:** `skills/migrate/SKILL.md` (1 file -- continued from Task 3)
- **Complexity:** Low
- **Dependencies:** Task 3

Add the integration section, prompt template list, and quality gate orchestration section.

**Step 1: Write the integration section**

Document all skill integrations:

| Skill | How Used | When |
|-------|----------|------|
| `crucible:cartographer` | Consult mode | Phase 0 (module boundaries for blast radius) |
| `crucible:cartographer` | Record mode | Phase 8 (record migration discoveries) |
| `crucible:forge` | Feed-forward | Phase 0 (past migration lessons) |
| `crucible:forge` | Retrospective | Phase 8 (capture migration outcome) |
| `crucible:pathfinder` | Query mode | Phase 2 (cross-repo consumer discovery) |
| `crucible:build` | Refactor mode | Phase 7 (per-phase execution for restructuring phases) |
| `crucible:build` | Feature mode | Phase 7 (per-phase execution for additive phases) |
| `crucible:quality-gate` | Per-phase gate | Phase 7 (artifact type: code, per phase) |
| `crucible:quality-gate` | Plan gate | After Phase 5 (artifact type: plan, on migration plan) |
| `crucible:test-coverage` | Per-phase audit | Phase 7 (test alignment after each phase) |
| `crucible:prospector` | Upstream | Prospector discovers "modernize X"; migrate plans the transition |

**Step 2: Write the prompt template list**

- `./migration-analyzer-prompt.md` -- Phase 1 migration target analysis
- `./blast-radius-mapper-prompt.md` -- Phase 2 consumer and dependency mapping
- `./phase-planner-prompt.md` -- Phase 3 phase decomposition
- `./compatibility-designer-prompt.md` -- Phase 4 shim/adapter design
- `./wave-grouper-prompt.md` -- Phase 5 consumer wave assignment

**Step 3: Write the quality gate orchestration section**

Follow build's pattern (`skills/build/SKILL.md` lines 714-724):

| Pipeline Stage | Artifact Type | Purpose |
|---------------|---------------|---------|
| After Phase 5 (plan consolidation) | plan | Verify migration plan completeness, phase boundary safety |
| Phase 7 (per-phase, after build completes) | code | Verify phase implementation correctness |
| Phase 8 (after cleanup) | code | Verify clean removal of compatibility layer |

**Step 4: Write the "what the orchestrator should NOT do" section**

Following build's pattern (`skills/build/SKILL.md` lines 677-683):
- Implement migration code directly (dispatch build)
- Skip compatibility layer for "simple" migrations without analysis
- Execute phases in parallel (phases are strictly sequential -- coexistence depends on prior phase)
- Remove compatibility layer before user-approved cleanup phase
- Modify pathfinder topology data (read-only consumer)

**Verification:** Integration table covers all referenced skills. Prompt template list matches all agent dispatch points in Phases 1-5. Quality gate orchestration defines all gate points. Red flags are migration-specific.

---

### Task 5: Create Migration Analyzer Prompt Template

- **Files:** `skills/migrate/migration-analyzer-prompt.md` (1 file -- new)
- **Complexity:** Medium
- **Dependencies:** Task 2

Create the prompt template for the Phase 1 Migration Analyzer agent.

**Step 1: Write the template**

Follow the structural pattern of prospector's explorer prompt (`skills/prospector/explorer-prompt.md`) and build's implementer prompt (`skills/build/build-implementer-prompt.md`):

```markdown
# Migration Analyzer Prompt Template

Use this template when dispatching the Migration Analyzer agent in Phase 1.

```
Agent tool (subagent_type: Explore, model: opus):
  description: "Analyze migration target: [MIGRATION_DESCRIPTION]"
  prompt: |
    You are analyzing a migration target to understand what is changing,
    what will break, and how complex the migration will be.

    ## Migration Target

    [MIGRATION_DESCRIPTION]

    ## Framework Context

    [FRAMEWORK_CONTEXT from dependency manifest reads]

    ## Cartographer Context

    [CARTOGRAPHER_MODULE_MAP if available, or "No cartographer data available"]

    ## Your Job

    Investigate the migration target thoroughly:

    1. **Find the migration source material:**
       - Look for CHANGELOG.md, MIGRATION.md, UPGRADING.md in the repo
       - Look for the dependency's own migration guide (if it's a published package,
         check node_modules/<package>/CHANGELOG.md or equivalent)
       - Read the old version's API surface (type definitions, exports, public methods)
       - Read the new version's API surface (if available locally or documented)

    2. **Catalog the API delta:**
       - Removed APIs (breaking: consumers will fail)
       - Renamed APIs (breaking but mechanical: find-and-replace)
       - Changed signatures (breaking: consumers need logic changes)
       - Changed behavior (breaking: same API, different semantics)
       - New APIs (non-breaking: consumers may want to adopt)
       - Deprecated APIs (warning: will break in future versions)

    3. **Assess complexity:**
       - Count breaking changes
       - Categorize each: mechanical (rename/reorganize) vs behavioral (logic change)
       - Note any breaking changes that require design decisions (not just find-and-replace)

    4. **Output format:**

       ## Migration Analysis: [target description]

       ### API Delta Summary
       - Breaking changes: N (M mechanical, K behavioral)
       - Deprecations: N
       - New APIs: N

       ### Breaking Changes (detailed)
       For each breaking change:
       - **[old API] -> [new API]**: [description of change]
       - **Migration type:** mechanical | behavioral | design-required
       - **Affected pattern:** [how consumers typically use this API]

       ### Behavioral Changes
       For each behavioral change (same API, different semantics):
       - **[API name]**: [old behavior] -> [new behavior]
       - **Risk:** [what could go wrong if a consumer assumes old behavior]

       ### Migration Guides Found
       - [file path]: [summary of what the guide covers]

       ### Complexity Assessment
       - **Overall:** Low | Medium | High
       - **Reasoning:** [why this complexity level]
```
```

**Verification:** The prompt template exists, contains placeholder sections for all required inputs, and produces structured output that Phase 2 can consume.

---

### Task 6: Create Blast Radius Mapper Prompt Template

- **Files:** `skills/migrate/blast-radius-mapper-prompt.md` (1 file -- new)
- **Complexity:** Medium
- **Dependencies:** Task 2

Create the prompt template for the Phase 2 Blast Radius Mapper agent.

**Step 1: Write the template**

The mapper receives the migration analysis from Phase 1 and produces an impact manifest + consumer registry. Follow the blast radius analysis pattern from build's refactor mode (`skills/build/SKILL.md` lines 214-247).

The template must instruct the agent to:
1. Search for all imports/references to the migration target's old API surface
2. For each consumer, record: file path, usage pattern (how it calls the old API), whether the usage involves a breaking change or just a rename
3. Classify consumer migration complexity: low (mechanical replacement), medium (some logic changes), high (design decisions required)
4. Determine consumer independence: can this consumer be migrated without affecting other consumers?
5. Build a dependency graph among consumers (does migrating consumer A require migrating consumer B first?)
6. If pathfinder data available: query for cross-repo consumers and add to registry

Output format: impact manifest (matching build's refactor mode format) + consumer registry with per-consumer entries.

**Verification:** The prompt template exists, instructs the agent to produce both the impact manifest and consumer registry, and handles the pathfinder-available and pathfinder-unavailable cases.

---

### Task 7: Create Phase Planner Prompt Template

- **Files:** `skills/migrate/phase-planner-prompt.md` (1 file -- new)
- **Complexity:** Medium
- **Dependencies:** Task 2

Create the prompt template for the Phase 3 Phase Planner.

**Step 1: Write the template**

The planner receives: migration analysis + blast radius + consumer registry. It produces an ordered list of migration phases.

The template must enforce:
1. Each phase satisfies the safe stopping point invariant (compiles, tests pass, old + new coexist)
2. Each phase specifies its build mode (feature for additive, refactor for restructuring)
3. Consumer migration is broken into waves (not one monolithic phase)
4. Compatibility layer introduction happens before consumer migration
5. Compatibility layer removal happens after all consumers are migrated
6. Each phase lists affected files, estimated effort, and dependencies on prior phases

The template must include examples of phase decomposition for common migration types:
- Dependency major version upgrade (add new -> shim -> migrate waves -> remove shim -> remove old)
- API deprecation removal (identify callers -> update callers -> remove deprecated API)
- Framework upgrade (add compatibility layer -> migrate subsystems -> remove compatibility)

**Verification:** The prompt template exists, enforces the safe stopping point invariant, and produces output that the Compatibility Layer Designer and Consumer Wave Grouper can consume.

---

### Task 8: Create Compatibility Designer Prompt Template

- **Files:** `skills/migrate/compatibility-designer-prompt.md` (1 file -- new)
- **Complexity:** Medium
- **Dependencies:** Task 2

Create the prompt template for the Phase 4 Compatibility Layer Designer.

**Step 1: Write the template**

The designer receives: migration analysis (API delta) + phase plan (which phases need coexistence).

The template must instruct the agent to:
1. For each breaking change that requires a coexistence period, design a shim/adapter
2. Specify the shim interface (what old consumers call) and mapping (how it delegates to new implementation)
3. Choose the coexistence pattern: strangler fig (old interface wrapping new implementation), facade (new interface with old fallback), or dual registration (both old and new registered simultaneously)
4. Define shim tests: what must be tested to verify bidirectional correctness
5. Define shim removal criteria: when can each shim be safely deleted (all consumers migrated + tests passing without shim)

Output format: compatibility specification with per-shim entries.

**Verification:** The prompt template exists, covers the three coexistence patterns, and produces output that maps directly to build feature-mode tasks (adding shims) and build refactor-mode tasks (removing shims).

---

### Task 9: Create Wave Grouper Prompt Template

- **Files:** `skills/migrate/wave-grouper-prompt.md` (1 file -- new)
- **Complexity:** Low
- **Dependencies:** Task 2

Create the prompt template for the Phase 5 Consumer Wave Grouper.

**Step 1: Write the template**

The grouper receives: consumer registry + phase plan. It assigns consumers to waves.

The template must instruct the agent to:
1. Build a dependency graph among consumers
2. Topological sort: leaf consumers (no dependencies on other consumers) in Wave 1
3. Each subsequent wave contains consumers whose dependencies are all in prior waves
4. Within each wave, verify independence (no intra-wave dependencies)
5. For cross-repo migrations: group by repo, then by intra-repo independence
6. Estimate effort per wave (sum of consumer migration complexities)
7. Flag any circular dependencies (escalate to orchestrator -- cannot auto-resolve)

Output format: wave assignment list with per-wave consumer entries and independence verification.

**Verification:** The prompt template exists, handles both single-repo and cross-repo cases, and correctly defines the topological sort requirement.

---

### Task 10: Create Eval Scenarios

- **Files:** `skills/build/evals/migrate/` (4-5 files -- new directory and eval files)
- **Complexity:** Medium
- **Dependencies:** Tasks 1-4

Create eval scenarios that test the skill's core behaviors.

**Step 1: Create eval directory structure**

```
skills/build/evals/migrate/
  eval-1-single-repo-dependency-upgrade.md
  eval-2-cross-repo-shared-package.md
  eval-3-deprecation-removal.md
  eval-4-plan-only-mode.md
  eval-5-execute-existing-plan.md
```

**Step 2: Write eval-1 -- Single-repo dependency upgrade**

Scenario: "Upgrade lodash from v3 to v4 in a Node.js project"
- Expected: 3-5 phases (add v4, update imports for renamed methods, remove v3)
- Verify: phase decomposition respects safe stopping points, no compatibility layer needed (in-place mechanical replacement)

**Step 3: Write eval-2 -- Cross-repo shared package migration**

Scenario: "Upgrade shared-auth from v2 to v3 across 4 consumer repos"
- Expected: 5+ phases including compatibility layer, 2+ consumer waves
- Verify: pathfinder query mode is invoked, consumer waves respect inter-repo dependencies, compatibility layer persists until cleanup phase

**Step 4: Write eval-3 -- Deprecation removal**

Scenario: "Remove deprecated PaymentProcessor.legacy_charge method"
- Expected: 2-3 phases (update callers, remove method)
- Verify: blast radius identifies all callers, no compatibility layer needed

**Step 5: Write eval-4 -- Plan-only mode**

Scenario: "Plan migration of React Router v5 to v6 without executing"
- Expected: complete plan produced, no build invocations, plan saved to docs/plans/
- Verify: `--plan-only` flag prevents execution, plan file is valid

**Step 6: Write eval-5 -- Execute existing plan**

Scenario: Given an existing migration plan file, execute its phases
- Expected: phases execute sequentially through build, verification between phases
- Verify: `--execute` flag reads existing plan, skips Phases 1-6, proceeds directly to Phase 7

**Verification:** 4-5 eval files exist covering: single-repo, cross-repo, deprecation removal, plan-only mode, and execute-existing-plan mode. Each eval has expected outcomes and verification criteria.
