---
name: migrate
description: "Autonomous migration planning and execution. Takes a migration target (framework upgrade, API version bump, dependency major version, deprecation removal) and produces a phased migration plan with compatibility verification, then optionally executes via build's refactor mode. Triggers on /migrate, 'migration plan', 'upgrade X from Y to Z', 'remove deprecated', 'major version bump'."
---

# Migrate

## Overview

Autonomous migration planning and execution: analyzes a migration target, maps blast radius, decomposes into safe phases with compatibility layers, groups consumers into waves, then executes through build's refactor/feature mode with verification at each phase boundary.

**Announce at start:** "Running migrate on [migration target description]."

**Skill type:** Rigid -- follow exactly, no shortcuts.

**Purpose:** Bridge between prospector discovery ("you should modernize X") and build execution ("here is the plan, execute it"). Today that bridge is manual. /migrate makes it autonomous.

**Two modes:**
- **Plan + Execute** (default) -- produces a phased migration plan, then executes each phase through build
- **Plan only** -- produces the plan and saves it without executing

## Invocation

```
/migrate "upgrade lodash from v3 to v4"                    # plan + execute
/migrate --plan-only "upgrade React Router v5 to v6"       # plan only, no execution
/migrate --execute docs/plans/2026-03-23-lodash-migration-plan.md  # execute existing plan
/migrate --orgs org1,org2 "upgrade shared-auth v2 to v3"   # cross-repo
```

## Communication Requirement (Non-Negotiable)

**Between every agent dispatch and every agent completion, output a status update to the user.** This is NOT optional -- the user cannot see agent activity without your narration.

Every status update must include:
1. **Current phase** -- Which pipeline phase you're in
2. **What just completed** -- What the last agent reported
3. **What's being dispatched next** -- What you're about to do and why
4. **Phase progress** -- Which phases are done, in progress, or pending

**After compaction:** If you just experienced context compaction, follow the Compaction Recovery procedure, re-read state from the scratch directory, and output current status before continuing. Do NOT proceed silently.

**Examples of GOOD narration:**
> "Phase 2 complete. Blast radius mapper found 14 direct consumers across 3 modules. Dispatching Phase Planner to decompose into migration phases."

> "Phase 7, Wave 2 complete. 8/14 consumers migrated. Build reported all tests passing after Phase 3b. Proceeding to Wave 3 (4 consumers)."

**This requirement exists because:** Migrations are long-running and high-stakes. The user needs visibility into progress, blast radius, and phase outcomes to decide whether to continue or intervene.

## Pipeline Status

Write a status file to `~/.claude/projects/<hash>/memory/pipeline-status.md` at every narration point. This file is overwritten (not appended) and provides ambient awareness for the user in a second terminal.

### Write Triggers

Write the status file at every point where the Communication Requirement mandates narration: before dispatch, after completion, phase transitions, health changes, escalations, and after compaction recovery.

### Status File Format

The status file uses this structure (overwritten in full each time):

```
# Pipeline Status
**Updated:** <current timestamp>
**Started:** <timestamp from first write -- persisted across compaction>
**Skill:** migrate
**Phase:** <current phase, e.g. "3 -- Decompose into Phases">
**Health:** <GREEN|YELLOW|RED>
**Suggested Action:** <omit when GREEN; concrete one-sentence action when YELLOW/RED>
**Elapsed:** <computed from Started>

## Recent Events
- [HH:MM] <most recent event>
- [HH:MM] <previous event>
(last 5 events, newest first)
```

### Skill-Specific Body

Append after the shared header:

```
## Migration Progress
| Phase | Description | Status |
|-------|-------------|--------|
| 0 | Pre-flight | DONE |
| 1 | Analyze target | DONE |
| 2 | Map blast radius | IN PROGRESS |
| 3 | Decompose phases | PENDING |
| 4 | Compatibility layer | PENDING |
| 5 | Plan waves | PENDING |
| G | User gate | PENDING |
| 6 | Rollback points | PENDING |
| 7 | Execute | PENDING |
| 8 | Cleanup | PENDING |

## Blast Radius
- Direct consumers: 14
- Cross-repo: 3 repos (if applicable)

## Execution (Phase 7)
- Wave 1: 4/4 consumers DONE
- Wave 2: 2/6 consumers IN PROGRESS
- Phase test suite: PASSING
```

### Health State Machine

Health transitions are one-directional within a phase: GREEN -> YELLOW -> RED. Phase boundaries reset to GREEN.

- **Phase boundaries** (reset to GREEN): each new phase
- **YELLOW:** quality gate round 3+ on any phase, phase retry in progress, medium-confidence decision
- **RED:** phase execution failure, test suite failure unresolved, stagnation in quality gate, compatibility layer test failure

When health is YELLOW or RED, include `**Suggested Action:**` with a concrete, context-specific sentence.

### Inline CLI Format

Output concise inline status alongside the status file write:
- **Minor transitions** (dispatch, completion): one-liner, e.g. `Phase 2 [blast radius] 14 consumers found | GREEN | 12m`
- **Phase changes and escalations**: expanded block with `---` separators
- **Health transitions**: always expanded with old -> new health

### Compaction Recovery

After compaction, before re-writing the status file:
1. Read the existing `pipeline-status.md` to recover `Started` timestamp and `Recent Events` buffer
2. Reconstruct phase, health, and skill-specific body from scratch directory state files
3. Write the updated status file
4. Output inline status to CLI

## Model Allocation

| Agent | Model | Dispatch Method |
|-------|-------|-----------------|
| Orchestrator | Opus | -- |
| Migration Analyzer | Opus | Agent tool (Explore) |
| Blast Radius Mapper | Sonnet | Agent tool (general-purpose) |
| Phase Planner | Opus | Task tool |
| Compatibility Layer Designer | Opus | Task tool |
| Consumer Wave Grouper | Sonnet | Task tool |

## Scratch Directory

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

**Stale cleanup:** Delete scratch directories older than 48 hours (migrations run longer than most skills). Preserve directories where `execution-status.json` shows any phase in `executing` or `failed` status.

## Context Management

Follow spec's context budget management pattern:
- **Preemptive context checkpoint between phases:** Before starting a new phase, write current state to scratch directory so compaction recovery can resume
- **Per-phase context lifecycle:** Load only current phase's inputs. Do not carry forward raw outputs from completed phases -- use the structured scratch files instead
- **Complex migrations (10+ phases):** Use aggressive summarization of completed phases. Carry forward only the phase-plan.md and execution-status.json, not individual phase outputs

## Compaction Recovery

Recovery procedure:
1. Read `invocation.md` -- recover migration target, mode, scope
2. Read `execution-status.json` -- determine which phases are complete/in-progress/pending
3. Read `migration-plan.md` -- recover the approved plan
4. For any phase in `executing` status: restart that phase from the beginning (safe because build's refactor mode has its own rollback)
5. Resume processing from the next pending phase

---

## Phase 0: Pre-flight

Before any agent dispatch:

1. **Consult cartographer** (consult mode) -- load known module boundaries for blast radius mapping
2. **Consult forge** (feed-forward) -- check past lessons, especially prior migration outcomes
3. **Handle `--execute`** -- if specified, read the existing plan file, validate it has the expected structure (phases, consumer registry, rollback points), and skip to Phase 7.
5. **Write invocation.md** to scratch directory with migration target, mode, and scope.

---

## Phase 1: Analyze Migration Target

Dispatch the **Migration Analyzer** (Opus, Agent tool, Explore subagent) using `./migration-analyzer-prompt.md`.

**Input:**
- Migration description from user
- Cartographer data (if available)
- Framework context from dependency manifests (following prospector's Phase 0.5 pattern: read package.json, *.csproj, requirements.txt, go.mod, Cargo.toml, etc.)

**The analyzer investigates:**
- Changelog / migration guide (CHANGELOG.md, MIGRATION.md, UPGRADING.md in repo or dependency)
- API diff between versions (old vs new type definitions, function signatures, endpoint contracts)
- Breaking changes (backward-incompatible removals or signature changes)
- Deprecation notices (what the new version removes that the old warned about)
- New capabilities (additions consumers may want to adopt during migration)

**Output:** Structured migration analysis written to `scratch/<run-id>/migration-analysis.md`.

**Complexity classification:**
- **Low:** <5 breaking changes, <10 consumers, no behavioral changes (pure API rename/reorganization)
- **Medium:** 5-20 breaking changes, 10-50 consumers, some behavioral changes
- **High:** 20+ breaking changes, 50+ consumers, significant behavioral changes, cross-repo scope

---

## Phase 2: Map Blast Radius

Dispatch the **Blast Radius Mapper** (Sonnet, Agent tool, general-purpose) using `./blast-radius-mapper-prompt.md`.

**Input:** Migration analysis from Phase 1, cartographer module data (if available).

**Intra-repo mapping** (follows build refactor mode's blast radius analysis pattern):
- **Direct consumers** -- code that imports/calls/references the migration target
- **Indirect dependents** -- code that depends on direct consumers (transitive)
- **Test coverage** -- which tests exercise the target behavior
- **Configuration/wiring** -- config files, DI registrations, build scripts referencing the target

**Output:** Impact manifest + consumer registry written to `scratch/<run-id>/blast-radius.md`.

**Consumer registry entry format:**
```
- consumer: <file path or org/repo>
  usage_pattern: "calls TargetClass.method(args)"
  migration_complexity: low|medium|high
  independent: true|false
  reason_if_dependent: "shares state with <other consumer>"
```

---

## Phase 3: Decompose into Phases

Dispatch the **Phase Planner** (Opus, Task tool) using `./phase-planner-prompt.md`.

**Input:** Migration analysis + blast radius + consumer registry.

The planner produces an ordered list of migration phases. Each phase must satisfy the **safe stopping point invariant**: after completing the phase, the codebase compiles, all tests pass, and both old and new code paths function correctly.

**Standard phase template** (adapted by planner based on migration type):

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

**Output:** `scratch/<run-id>/phase-plan.md`

---

## Phase 4: Design Compatibility Layer

Dispatch the **Compatibility Layer Designer** (Opus, Task tool) using `./compatibility-designer-prompt.md`.

**Input:** Migration analysis (API delta) + phase plan (which phases need coexistence).

**Skip condition:** If Phase 3 determined no coexistence period is needed (e.g., simple in-place rename with no external consumers), skip this phase. Write "Compatibility layer: SKIPPED (no coexistence period required)" to scratch.

**Output:** Compatibility specification written to `scratch/<run-id>/compatibility-spec.md`:
- **Shim inventory** -- list of adapters/facades with their interfaces
- **Mapping** -- old API call -> shim -> new API call (for each shim)
- **Direction** -- strangler fig (old-to-new) or facade (new-to-old)
- **Tests** -- what tests the shim needs (bidirectional correctness)
- **Removal criteria** -- when each shim can be safely deleted

---

## Phase 5: Plan Consumer Waves

Dispatch the **Consumer Wave Grouper** (Sonnet, Task tool) using `./wave-grouper-prompt.md`.

**Input:** Consumer registry from Phase 2 + phase plan from Phase 3.

**Algorithm:**
1. Build dependency graph among consumers (consumer A depends on consumer B if A imports/calls B)
2. Topological sort: consumers with no dependencies on other consumers go in Wave 1
3. Consumers depending only on Wave 1 consumers go in Wave 2
4. Continue until all consumers assigned
5. Within each wave, verify independence (no consumer in the wave depends on another in the same wave)

**Output:** Wave assignments written to `scratch/<run-id>/wave-plan.md`.

For cross-repo migrations: each wave entry includes repo name, estimated effort per repo, and CI pipeline considerations.

---

## User Gate

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

**User may:** approve, modify phases, reorder waves, exclude consumers, add consumers, or abort.

**On approval:** Save the plan to `docs/plans/YYYY-MM-DD-<topic>-migration-plan.md`. If `--plan-only` mode: stop here, report success.

**REQUIRED SUB-SKILL:** Use crucible:quality-gate on the migration plan with artifact type "plan". Iterate until clean or stagnation. **(Non-negotiable — see Quality Gate Requirement.)**

---

## Phase 6: Define Rollback Points

Orchestrator-local work (no agent dispatch).

For each phase in the approved plan, define:
- **Rollback trigger** -- what failure condition causes rollback
- **Rollback scope** -- which commits to revert
- **Post-rollback verification** -- which tests to run
- **Impact on other phases** -- does rolling back phase N invalidate phase N+1?

**Rollback principles:**
- Each phase is independently revertible (reverting phase N does not require reverting phases 1 through N-1)
- The compatibility layer MUST remain in place until the cleanup phase -- this is what makes intermediate rollback safe
- Cross-repo rollback: if repo A's migration fails in wave M, only repo A's wave M changes are reverted; other repos in wave M are unaffected if they migrated independently

Write to `scratch/<run-id>/rollback-points.md`.

---

## Phase 7: Execute via Build

Sequential phase execution. Phases are strictly sequential -- coexistence correctness depends on prior phase completion.

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

**Between-phase gate:** Full test suite must pass before proceeding to the next phase. This is stricter than build's intra-task review because migration phases have higher blast radius than individual refactoring tasks.

---

## Phase 8: Cleanup

After all consumer waves complete:

1. Remove compatibility layer (dispatch build refactor mode targeting shim files)
2. Remove old version dependency (update dependency manifests)
3. Run full test suite
4. Quality-gate the cleanup changes
5. Final migration-specific verification: only new API paths respond (old paths should fail gracefully or not exist)

Cleanup is a distinct phase because premature shim removal is the most common migration failure mode. Keeping it separate ensures the user explicitly approves shim removal.

**Post-cleanup:**
- Dispatch `crucible:cartographer` (record mode) -- record migration discoveries
- Dispatch `crucible:forge` (retrospective) -- capture migration outcome and lessons

---

## Escalation Triggers

Escalate to the user when:
- Phase execution failure after rollback
- Quality gate stagnation on any phase
- Test suite failures not obviously related to the migration
- Cross-repo migration coordination failure (one repo fails while others succeed in the same wave)
- Compatibility layer tests fail (the shim is incorrect -- this is a design problem, not an execution problem)
- User-requested abort at any point

---

## What the Orchestrator Must NOT Do

- **Implement migration code directly** -- dispatch build for all code changes
- **Skip compatibility layer for "simple" migrations** without analysis confirming it's unnecessary
- **Execute phases in parallel** -- phases are strictly sequential; coexistence depends on prior phase
- **Remove compatibility layer before user-approved cleanup phase**
- **Proceed past the user gate without explicit approval**

---

## Integration

| Skill | How Used | When |
|-------|----------|------|
| `crucible:cartographer` | Consult mode | Phase 0 (module boundaries for blast radius) |
| `crucible:cartographer` | Record mode | Phase 8 (record migration discoveries) |
| `crucible:forge` | Feed-forward | Phase 0 (past migration lessons) |
| `crucible:forge` | Retrospective | Phase 8 (capture migration outcome) |
| `crucible:build` | Refactor mode | Phase 7 (per-phase execution for restructuring phases) |
| `crucible:build` | Feature mode | Phase 7 (per-phase execution for additive phases) |
| `crucible:quality-gate` | Per-phase gate | Phase 7 (artifact type: code, per phase) |
| `crucible:quality-gate` | Plan gate | After Phase 5 (artifact type: plan, on migration plan) |
| `crucible:test-coverage` | Per-phase audit | Phase 7 (test alignment after each phase) |
| `crucible:prospector` | Upstream | Prospector discovers "modernize X"; migrate plans the transition |

## Prompt Templates

- `./migration-analyzer-prompt.md` -- Phase 1 migration target analysis
- `./blast-radius-mapper-prompt.md` -- Phase 2 consumer and dependency mapping
- `./phase-planner-prompt.md` -- Phase 3 phase decomposition
- `./compatibility-designer-prompt.md` -- Phase 4 shim/adapter design
- `./wave-grouper-prompt.md` -- Phase 5 consumer wave assignment

## Quality Gate Requirement (Non-Negotiable)

**Every quality gate in this pipeline MUST run to completion.** This is NOT optional — you may NOT self-assess whether a quality gate is "needed" based on migration step size, complexity, or perceived mechanical nature.

Migration work is especially vulnerable to "this is mechanical/boilerplate" rationalization. Mechanical changes still introduce bugs — mismatched imports, forgotten call sites, subtle behavioral differences in new APIs. Quality gates catch these regardless of how "simple" the migration step appears.

**Fixing findings is NOT the same as passing the gate.** The iteration loop must complete with a clean verification round (0 Fatal, 0 Significant on a fresh review).

**The only valid skip** is an unambiguous user instruction specifically referencing the gate. General feedback is not skip approval.

**Gate tracking:** Before compiling the migration summary, verify gate round counts by category: `plan` (Phase 5), `code-per-phase` (Phase 7, one entry per executed phase), `cleanup` (Phase 8). Each must show round count >= 1 with clean final rounds. If any gate was skipped with explicit user approval, record it as `USER_SKIP`. A zero without user approval indicates a gate was dropped — report this in the summary.

## Quality Gate Orchestration

| Pipeline Stage | Artifact Type | Purpose |
|---------------|---------------|---------|
| After Phase 5 (plan consolidation) | plan | Verify migration plan completeness, phase boundary safety |
| Phase 7 (per-phase, after build completes) | code | Verify phase implementation correctness |
| Phase 8 (after cleanup) | code | Verify clean removal of compatibility layer |

## Red Flags

**Quality gate violations:**
- Skipping a quality gate because the migration step is "mechanical" or "boilerplate"
- Self-assessing that a quality gate is unnecessary based on perceived migration step simplicity
- Declaring a quality gate "done" after fixing findings without a clean verification round (fixing is not passing)
- Short-circuiting the quality-gate iteration loop by assuming fixes are self-evidently correct
- Interpreting general user feedback as approval to skip a quality gate that has not yet run

**Compression State violations:**
- Skipping Compression State Block emission at checkpoint boundaries
- Emitting a Compression State Block with stale or missing Key Decisions (decisions must be cumulative across all prior blocks)
- Allowing the Goal field to drift across successive Compression State Blocks (must match original user request)
- Exceeding 10 entries in the Key Decisions list without overflow-compressing the oldest
