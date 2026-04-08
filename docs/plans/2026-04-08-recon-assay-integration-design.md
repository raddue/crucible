---
ticket: "#147"
title: "Integrate /recon and /assay into consuming skills"
date: "2026-04-08"
source: "spec"
---

# Integrate /recon and /assay into Consuming Skills

## Problem Statement

`/recon` and `/assay` are fully defined skills with well-specified APIs, output schemas, and depth modules tailored to specific consumers. However, no consuming skill actually dispatches them. Their "Called by" lists are aspirational documentation, not reality.

The result is duplicated investigation logic: `/design` reimplements codebase investigation inline with custom agents (Codebase Scout, Domain Researcher, Impact Analyst), `/spec` copies that pattern, and decision evaluation is done ad-hoc across multiple skills. This duplication means improvements to `/recon` or `/assay` (better scout prompts, cartographer integration, session caching) never reach the skills that would benefit from them.

## The Central Tradeoff

**Generic recon vs. custom investigation.** `/recon` provides a standardized investigation pipeline (Structure Scout + Pattern Scout + optional depth modules) with cartographer integration, session caching, overflow handling, and compaction recovery. Custom inline investigation (as `/design` currently does) allows per-dimension agents tailored to the specific question being asked.

The tradeoff is not abstract -- it differs per consumer:

- **Design** asks dimension-specific questions ("how should auth work?") and dispatches agents per dimension. Recon asks task-level questions ("what does the codebase look like for this task?"). These are different granularities.
- **Debugging** has a highly specialized investigation pipeline (Error Analysis, Change Analysis, Evidence Gathering, Reproduction agents) that maps poorly to recon's Structure/Pattern Scout model.
- **Audit** already has a scoping exploration agent that serves a different purpose than recon (finding subsystem boundaries, not general investigation).
- **Prospector** has an organic explorer that is fundamentally different from recon's structured scouts -- it navigates like a developer, not like a mapper.

The right answer is not "dispatch recon everywhere" -- it is "dispatch recon where it adds value, keep custom logic where it is more specific, and update documentation to match reality."

## Per-Consumer Analysis

### 1. /design -- PARTIAL INTEGRATION (recon for context, keep custom for dimensions)

**Current state:** Phase 1 consults cartographer and forge. Phase 2 dispatches per-dimension investigation agents (Codebase Scout, Domain Researcher, Impact Analyst) inline. The Codebase Scout overlaps heavily with recon's scouts; the Domain Researcher and Impact Analyst do not.

**What recon offers:** A one-time upfront investigation at the start of the design session that produces structural context, existing patterns, scope boundaries, and prior art. This is exactly the kind of context that design's per-dimension agents currently rediscover from scratch for each dimension.

**Recommendation: Dispatch recon once at the start of Phase 2** (before any dimension loop iterations) with `modules: ["impact-analysis"]`. Use the Investigation Brief as the structural context for all subsequent dimension investigations. **Delete the Codebase Scout** from investigation-prompts.md -- recon's Structure Scout and Pattern Scout already cover what the Codebase Scout does (existing patterns, constraints, touchpoints, precedents). Keep the Domain Researcher and Impact Analyst as dimension-specific agents -- they serve different purposes than recon's scouts.

**What gets removed:**
- The Codebase Scout template in `design/investigation-prompts.md` -- replaced by recon's brief
- The "Quick scan" path (Step 3) that dispatches "only the Codebase Scout" -- replaced by reading the relevant sections of the already-available recon brief
- References to the Codebase Scout in Steps 4-5

**What stays:**
- Domain Researcher (explores approaches for a specific dimension -- recon does not do this)
- Impact Analyst (assesses what existing systems a specific decision affects -- overlaps with recon's impact-analysis module, but operates at dimension granularity, not task granularity)
- Challenger agent (Step 6 -- attacks assumptions, not approach evaluation)

**What this changes:**
- Phase 2 gains a new Step 0: Dispatch `/recon` with the task description and `session_id`
- "Quick scan" triage tier becomes "read recon brief" (no agent dispatch needed)
- "Deep dive" triage tier dispatches 2 agents (Domain Researcher + Impact Analyst) instead of 3
- Structure Scout results are cached across dimensions via `session_id`

**Why not full replacement of all three agents:** The Domain Researcher explores approaches and trade-offs for a specific design dimension -- it is creative/advisory work, not codebase investigation. The per-dimension Impact Analyst operates at decision granularity ("what breaks if we choose X?"), not task granularity ("what does the codebase look like?"). These are genuinely different from what recon provides.

**Assay integration:** Dispatch `/assay` during Step 5 (Synthesize) for Deep Dive dimensions when the orchestrator has 2-3 informed options with a recommendation. Assay provides structured evaluation with constraint_fit scoring, kill criteria, and evidence grounding -- currently done informally by the orchestrator. **This replaces the informal option-comparison prose** in Step 5 with structured JSON output.

**What assay replaces:** The ad-hoc "Synthesize into 2-3 informed options with a recommended choice" step. The orchestrator currently does this judgment inline -- assay externalizes it to a dedicated Opus evaluator with a structured output schema. The Challenger agent (Step 6) remains separate -- it attacks assumptions, which is different from evaluating approaches.

### 2. /spec -- PARTIAL INTEGRATION (mirrors design's approach)

**Current state:** Per-ticket investigation uses "same depth as /design Phase 2" with Codebase Scout, Domain Researcher, Impact Analyst + Challenger. Runs fully autonomous.

**Recommendation: Mirror design's integration.** Each ticket investigation starts with a `/recon` dispatch (with `session_id` shared across the entire spec run for structure cache reuse), then runs dimension-specific agents with the brief as context. **Delete the Codebase Scout** from spec's investigation -- same reasoning as design. Keep Domain Researcher and Impact Analyst. Assay dispatched for architectural decisions.

**What gets removed:**
- The Codebase Scout dispatch within the per-ticket spec writer (currently described as "same depth as /design Phase 2")
- The "Quick scan" path -- replaced by reading the recon brief

**Key difference from design:** Spec is autonomous. Assay results are consumed directly by the spec writer (no user gate). The spec writer uses assay's `confidence` field to decide whether to flag the decision as a terminal alert (low confidence) or proceed autonomously (high/medium confidence).

**What this changes:**
- spec-writer-prompt.md gains recon dispatch at investigation start and loses Codebase Scout
- session_id is set once per epic run and reused across all tickets (significant cost savings)
- "Quick scan" tier becomes "read recon brief" (no agent dispatch)
- "Deep dive" tier dispatches 2 agents instead of 3
- Architectural dimension decisions dispatch assay; the spec writer consumes the JSON report
- Low-confidence assay results trigger terminal alerts

### 3. /build -- RECON DISPATCH (Phase 1 inherits from design)

**Current state:** Phase 1 dispatches `/design` as a sub-skill. Build itself does no investigation -- it delegates to design.

**Recommendation: No direct recon/assay integration in build.** Build's investigation happens through design (Phase 1). When design integrates recon, build inherits the benefit automatically. Build's Phase 2 (planning) and Phase 3 (execution) do not perform investigation.

**Documentation update only:** Update build's integration table to note that recon/assay are consumed indirectly through design.

### 4. /debugging -- DOCUMENTATION ONLY (custom pipeline is superior)

**Current state:** Phase 1 dispatches 3-6 parallel investigation agents (Error Analysis, Change Analysis, Evidence Gathering, Reproduction, Deep Dive). These are highly specialized for debugging: they trace call chains, analyze diffs, reproduce intermittent bugs. Phase 3 forms hypotheses from synthesis.

**Why recon is a poor fit:** Recon's Structure Scout and Pattern Scout investigate codebase structure and conventions. Debugging needs error-chain-specific investigation: "what changed recently?", "what does the stack trace tell us?", "can we reproduce this?" These are categorically different from structural investigation.

**Why assay is a poor fit:** Debugging's hypothesis evaluation (Phase 3 + Phase 3.5 quality-gate) is already well-structured: form hypothesis, define falsification criteria, red-team the hypothesis. Assay evaluates competing approaches against codebase constraints -- it is designed for architecture/strategy decisions, not hypothesis testing. The `diagnosis` decision type exists in assay but maps poorly to debugging's existing hypothesis formation + red-team pipeline.

**Recommendation: Documentation only.** Update recon's and assay's "Called by" lists to remove `/debugging`. Update debugging's integration section to note that it uses specialized investigation agents rather than generic recon.

**Depth module opportunity:** Recon's `diagnostic-context` depth module could be useful as a lightweight pre-investigation step (gathering context before the main debugging pipeline). However, this is a "nice to have" that does not justify the integration complexity. Defer to a future iteration.

### 5. /migrate -- FULL INTEGRATION (recon + assay)

**Current state:** Phase 1 dispatches a Migration Analyzer (Opus Explore agent). Phase 2 dispatches a Blast Radius Mapper. Neither uses recon, though Phase 3's planner mentions recon in passing ("if `/recon` with `consumer-registry` was run").

**What recon offers:** The `consumer-registry` depth module is literally designed for migrate. It maps consumers of a migration target, their usage patterns, and migration complexity. This directly feeds Phase 2 (Blast Radius Mapping) and Phase 5 (Consumer Wave Grouping).

**Recommendation: Dispatch recon in Phase 0** with `modules: ["consumer-registry"]` and `context: { target: migration_target }`. The Investigation Brief provides structural context for the Migration Analyzer, and the consumer registry provides the consumer discovery that the Blast Radius Mapper currently rediscovers from scratch.

**What gets removed / reduced:**
- The Blast Radius Mapper's consumer discovery work is significantly reduced -- it receives recon's consumer registry as input instead of discovering consumers from scratch. The Blast Radius Mapper still does transitive dependency analysis and test coverage mapping (which recon's consumer-registry does not do), but its direct consumer discovery is replaced.
- The `blast-radius-mapper-prompt.md` gains a `[CONSUMER_REGISTRY]` input section and loses its "Direct consumers" discovery instructions

**What stays:**
- Migration Analyzer (Phase 1) -- analyzes API diffs, breaking changes, deprecations. Recon does not do this.
- Blast Radius Mapper's transitive dependency and test coverage analysis -- recon's consumer-registry only maps direct consumers
- All phases 3-8: unchanged

**Assay integration:** Dispatch assay at the User Gate (after Phase 5) with `decision_type: "strategy"` to evaluate the overall migration approach. The recon brief plus migration analysis becomes assay's context. **This replaces the unstructured plan presentation** with a structured evaluation that includes kill criteria and confidence scoring. The user still approves/modifies/rejects the plan -- assay's output enriches the presentation, it does not replace the user gate.

**What this changes:**
- Phase 0 gains recon dispatch before Migration Analyzer
- Blast Radius Mapper receives consumer-registry data, skips direct consumer discovery
- User Gate presentation includes assay's structured strategy evaluation
- Phase 3 planner's mention of recon becomes a real dependency

### 6. /audit -- RECON DISPATCH (code path only)

**Current state:** Phase 1 dispatches a Sonnet Explore agent for scoping (identifying subsystem boundaries). This overlaps with recon's Structure Scout but serves a narrower purpose: finding which files belong to a named subsystem.

**What recon offers:** The `subsystem-manifest` depth module produces exactly what audit's Phase 1 needs -- a structured manifest of a subsystem's files, responsibilities, and interfaces. Recon's cartographer integration means the manifest benefits from accumulated structural knowledge.

**Recommendation: Dispatch recon for code audits** with `scope: <subsystem path>` and `modules: ["subsystem-manifest"]`. **Delete the scoping exploration agent** (`audit-scoping-prompt.md` dispatch) from Phase 1's code path -- recon's subsystem manifest provides a superset of what the scoping agent produces. For non-code audits (design, plan, concept), recon is not applicable -- the artifact IS the scope.

**What gets removed:**
- The `audit-scoping-prompt.md` Sonnet Explore dispatch in Phase 1 code path
- The manual subsystem boundary discovery logic

**What stays:**
- The USER GATE presenting the manifest for user confirmation (now presenting recon's subsystem manifest instead of the scoping agent's output)
- Non-code path: entirely unchanged
- Phase 2 analysis: unchanged (receives better input from recon)

**What this changes:**
- Phase 1 code path: recon dispatch replaces the scoping exploration agent entirely
- The subsystem manifest feeds directly into Phase 2's context management (Tier 1 overview)
- Cartographer integration comes for free (recon consults cartographer, the scoping agent did not)

### 7. /prospector -- DOCUMENTATION ONLY (organic exploration is the point)

**Current state:** Phase 1 dispatches an Organic Explorer (Opus) that navigates the codebase like a developer joining for the first time. This is fundamentally different from recon's structured scouts -- the organic explorer follows threads of friction, not structural mapping.

**Why recon is a poor fit:** Prospector's value is in organic, unstructured discovery. Recon produces structured, repeatable investigation. Replacing the organic explorer with recon would produce a different (and worse) output -- structural maps instead of friction discovery. Recon's `friction-scan` depth module exists but is designed to be dispatched BY prospector's flow, not to replace its organic exploration.

**What about assay for competing designs?** Prospector Phase 6 dispatches 3 competing design agents (Opus). The competing designs are then presented to the user. Assay could evaluate the competing designs, but the evaluation is already well-structured: constraint-based scoring with the REFERENCE.md mapping. Assay would add overhead without adding quality.

**Recommendation: Documentation only.** Update recon's "Called by" to note `/prospector (supplementary)` is deferred. If prospector wants structural context, it consults cartographer directly (Phase 1 already does this). Assay integration is not recommended -- prospector's competing design evaluation is already more sophisticated than what assay provides for this use case.

### 8. /project-init -- DOCUMENTATION ONLY (different purpose)

**Current state:** Tier 1 dispatches Partition Explorers to map the codebase, then an Init Recorder to merge findings into cartographer format. This is a one-time structural bootstrapping operation.

**Why recon is a poor fit:** Project-init and recon serve different purposes. Project-init produces persistent cartographer data (module map, conventions, landmines). Recon produces ephemeral Investigation Briefs for task-specific investigation. Project-init already does what recon would do, but with the explicit goal of persisting the results -- and with a more thorough approach (partition-by-partition fan-out, validation gates, size caps).

**Recommendation: Documentation only.** Update recon's "Called by" to remove `/project-init`. Project-init bootstraps the cartographer data that recon consults -- they are complementary, not overlapping.

## Integration Architecture

### Dispatch Model

All integrations use **subagent dispatch** via the existing disk-mediated dispatch convention. Recon and assay are dispatched as sub-skills, not inlined.

**Why subagent dispatch, not inline methodology:**
1. **Single source of truth.** Improvements to recon's scouts, overflow handling, or cartographer integration propagate to all consumers automatically.
2. **Session caching.** Recon's Structure Scout caching across invocations (via `session_id`) only works when recon manages its own scratch directory.
3. **Compaction safety.** Recon writes its own pipeline-status.md and scratch artifacts. Inlining recon's methodology into consumer skills would create compaction recovery conflicts.
4. **Cost control.** Recon's layered model (core is cheap, depth modules are opt-in) gives consumers cost control that would be lost if investigation were inlined.

### Invocation Patterns

**Design/Spec (context enrichment):**
```
/recon
  task: "Design dimension context: [user's feature request]"
  session_id: "<design-session-id>"
  modules: ["impact-analysis"]
```
The brief is passed as context to per-dimension agents. Not a replacement for dimension-specific investigation.

**Migrate (consumer discovery):**
```
/recon
  task: "Map consumers and structure for migration: [migration target]"
  context: { target: "<migration-target-symbol>" }
  modules: ["consumer-registry"]
```
Consumer registry feeds directly into Blast Radius Mapper.

**Audit (subsystem scoping):**
```
/recon
  task: "Subsystem manifest for audit: [subsystem name]"
  scope: "<subsystem-path>"
  modules: ["subsystem-manifest"]
```
Subsystem manifest replaces the scoping exploration agent.

**Assay (decision evaluation):**
```
/assay
  question: "<design dimension question>"
  context: { <recon brief + cascading decisions> }
  decision_type: "architecture"
  cascading_decisions: [<prior decisions>]
```
Called during design/spec synthesis steps. Migrate calls with `decision_type: "strategy"`.

### Consumer-Side Changes

Each consumer that integrates recon/assay needs:
1. **Dispatch code** in the orchestrator section of their SKILL.md
2. **Brief consumption** -- instructions for how the consumer's downstream agents receive the brief
3. **Error handling** -- what to do if recon/assay fails (always: fall back to existing behavior)
4. **Integration table update** -- add recon/assay to the skill's Integration section

### Error Handling (All Consumers)

If recon fails (timeout, both scouts fail, etc.):
- The consuming skill **falls back to its existing investigation behavior**
- Narrate: "Recon failed: [reason]. Falling back to inline investigation."
- The consumer's quality is not degraded -- it just misses the acceleration that recon provides

If assay fails (evaluator timeout, invalid JSON after retry):
- The consuming skill **proceeds with its existing decision-making approach**
- Narrate: "Assay evaluation failed: [reason]. Proceeding with manual synthesis."
- The consumer presents options without assay's structured scoring

This means integration can never make a consumer worse -- at worst, it adds one failed agent dispatch and falls back to the status quo.

## Migration Path

### Phase 1: Update recon/assay documentation and APIs (if needed)

Before consumers can dispatch recon/assay, verify that the invocation APIs match what consumers need. Current analysis shows no API changes are needed -- recon's existing parameters (`task`, `context`, `session_id`, `modules`, `scope`) and assay's parameters (`question`, `context`, `decision_type`, `approaches`, `cascading_decisions`) already cover all identified use cases.

### Phase 2: Update consumers (highest-value first)

1. **Design** -- highest impact because spec and build inherit the benefit
2. **Spec** -- mirrors design, shares session caching
3. **Migrate** -- consumer-registry depth module is uniquely valuable
4. **Audit** -- subsystem-manifest replaces existing scoping agent

### Phase 3: Update documentation for non-integrated consumers

5. **Debugging, Prospector, Project-init, Build** -- update "Called by" lists and integration docs

## Decision Log

| ID | Decision | Rationale |
|---|---|---|
| DEC-1 | Recon replaces design/spec's Codebase Scout but keeps Domain Researcher and Impact Analyst | The Codebase Scout does the same thing as recon's scouts (find patterns, constraints, touchpoints). Domain Researcher and Impact Analyst operate at dimension granularity with different goals. Consolidation means ripping out the duplicate, not layering. |
| DEC-2 | Debugging gets documentation-only, no recon/assay integration | Debugging's investigation pipeline (Error Analysis, Change Analysis, etc.) is categorically different from structural investigation. Forcing recon would degrade quality. |
| DEC-3 | Prospector gets documentation-only, no recon/assay integration | Organic exploration is prospector's core value. Recon's structured scouts would produce different (worse) output. Assay adds overhead without quality improvement over existing competing-design evaluation. |
| DEC-4 | Project-init gets documentation-only | Project-init bootstraps the cartographer data that recon consults. They serve complementary purposes, not overlapping ones. |
| DEC-5 | Build gets documentation-only (inherits from design) | Build delegates investigation to design. When design integrates recon, build benefits automatically. |
| DEC-6 | All integrations include fallback to existing behavior on failure | Integration must never degrade consumer quality. Failed recon/assay dispatch falls back to the status quo. |
| DEC-7 | Assay replaces ad-hoc option synthesis in design Step 5, not the Challenger | Assay evaluates approaches. The Challenger attacks assumptions. These are complementary, not redundant. |
| DEC-8 | Migrate dispatches recon with consumer-registry in Phase 0 | The consumer-registry depth module is specifically designed for migrate. It feeds directly into Blast Radius Mapping. |
| DEC-9 | Audit dispatches recon with subsystem-manifest for code path only | Non-code audits scope to the artifact itself. Recon is only useful for code audits where subsystem boundary discovery is needed. |
| DEC-10 | Consolidation, not layering -- delete replaced inline code | When recon/assay replaces inline investigation logic, the old code is deleted, not left alongside. Dead inline code alongside a dispatch creates confusion about which path runs. If recon is not good enough to replace something, it should not be dispatched for that purpose. |
| DEC-11 | Audit scoping agent is deleted, not supplemented | Recon's subsystem-manifest produces a superset of what the scoping agent discovers, with cartographer integration the scoping agent lacks. The scoping agent dispatch and prompt template become dead code. |
| DEC-12 | Migrate's Blast Radius Mapper loses direct consumer discovery but keeps transitive analysis | Consumer-registry maps direct consumers. The Blast Radius Mapper still does transitive dependency tracing and test coverage mapping. The prompt template is modified, not deleted. |
