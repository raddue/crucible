---
ticket: "#63"
epic: "none"
title: "Decision Archaeology Log in Cartographer"
date: "2026-03-23"
source: "spec"
---

# Decision Archaeology Log in Cartographer

## Current State Analysis

### Where Decisions Are Generated

The system produces decision knowledge in three distinct locations, none of which persist beyond their immediate session:

1. **Spec scratch directory** (`~/.claude/projects/<hash>/memory/spec/scratch/<run-id>/decisions.md`, line 152 of `skills/spec/SKILL.md`): Each spec run produces a rich append-only decision log. Per-ticket decision files (`tickets/<ticket-number>/decisions.md`, line 169) capture choice, alternatives, confidence, and reasoning. The spec-writer-prompt.md (line 174) mandates a structured format with decision ID, choice, confidence level, alternatives considered, and project-specific reasoning. This is the highest-quality decision source in the system, but it lives in scratch directories subject to 24-hour stale cleanup (line 194-196 of `skills/spec/SKILL.md`).

2. **Build decision journal** (`/tmp/crucible-decisions-<session-id>.log`, line 653 of `skills/build/SKILL.md`): Captures routing decisions (reviewer model selection, gate rounds, escalations, task grouping, cleanup removal) in a single-line structured format. These are operational decisions, not design decisions. The journal lives in `/tmp/` and is consumed by forge retrospectives (line 36 of `skills/forge-skill/retrospective-prompt.md`) but is not persisted afterward.

3. **Design doc prose**: During build Phase 1, the design skill produces design documents with rationale embedded in prose sections (Key Decisions section). These are committed to `docs/plans/` and do survive, but the reasoning is buried in prose rather than structured for machine consumption.

### Where Decisions Are Consumed

- **Forge retrospective** (line 34-45 of `skills/forge-skill/retrospective-prompt.md`): Reads the build decision journal to cross-reference decisions against outcomes. Produces process-level lessons (deviation types, calibration insights) but does not extract or persist the substantive design decisions themselves.

- **Contract ambiguity_resolutions** (line 641-648 of `skills/spec/SKILL.md`): The contract schema includes an `ambiguity_resolutions` section that captures decisions with confidence, alternatives, and reasoning. These survive in `docs/plans/` as YAML, but only for spec-generated tickets. Build-originated decisions have no equivalent persistence path.

- **Cartographer map.md** (line 212 of `skills/cartographer-skill/SKILL.md`): The `## Key Architectural Decisions` section in map.md exists but captures only top-level structural observations (e.g., "monorepo with shared types"). It does not capture per-module design decisions or link them to evidence.

### The Gap

No path exists from decision generation to persistent, module-scoped, structured storage. The system generates rich decision data during /spec and /build, but:

- Spec decisions are deleted after 24 hours (scratch cleanup).
- Build decisions live in `/tmp/` and vanish with the session.
- Design doc rationale is prose-only and not indexed by module.
- Cartographer module files (`skills/cartographer-skill/SKILL.md`, lines 97-129) have Contracts and Gotchas sections but no section for "why was this decision made."

This causes re-litigation: a new session proposes reversing a decision made 10 sessions ago because no structured record of the prior decision's reasoning is accessible during cartographer consult or load modes.

## Target State

### Module-Scoped Decision Records

Each cartographer module file gains a `## Key Decisions` section between `## Contracts` and `## Gotchas`:

```markdown
## Key Decisions

- **REST over gRPC for lender API** (2026-03-15, #45): Downstream consumer cannot handle streaming. Alternatives: gRPC (rejected: streaming incompatible), GraphQL (rejected: team unfamiliar, no subscription need). Evidence: lender SDK docs specify REST-only.
- **Redis for session store** (2026-03-20, #52, medium confidence): Sub-millisecond lookups needed for auth middleware. Alternatives: Postgres (rejected: 5ms p99 too slow), DynamoDB (rejected: cost at scale). Evidence: load test showed 0.2ms p99 with Redis.
```

Each entry is a single compact record: decision name, date, source ticket, confidence (if non-high), alternatives with rejection reasons, and the evidence that drove the choice.

### Cross-Cutting Decision Overflow

Module files have a 100-line cap. Decisions that span multiple modules or are architectural in nature overflow to `cartographer/decisions.md` (new file, 200-line cap):

```markdown
# Cross-Cutting Decisions

- **Event-driven over polling for inter-service communication** (2026-03-10, #30): All three consumer modules (auth, funding, events) benefit from push semantics. Alternatives: polling (rejected: 3x load increase at 5s intervals), WebSocket (rejected: no server-to-server library in stack). Evidence: message bus already deployed for logging.

## Last Updated

2026-03-23
```

### Decision Injection During Consult and Load

- **Consult mode**: No change. Orchestrator reads `map.md` which already has `## Key Architectural Decisions`. Module-level decisions are not loaded here (same principle: orchestrator stays thin).
- **Load mode**: Module files are already pasted into subagent dispatch prompts. The new `## Key Decisions` section is included automatically because the entire module file is injected. No code change needed for load — the section is simply present in the file that already gets loaded.
- **Cross-cutting `decisions.md`**: Loaded alongside `conventions.md` for implementer subagents and alongside `landmines.md` for reviewer/red-team subagents. This provides feed-forward substantive ammunition.

### Decision Extraction Points

Two new extraction hooks, both piggybacking on existing dispatch mechanisms:

1. **After /spec completes** (before scratch cleanup): The spec orchestrator extracts decisions from the scratch `decisions.md` and per-ticket `decisions.md` files, maps them to cartographer modules by file path, and dispatches a cartographer recorder to persist them. This happens after the final wave completes and before the orchestrator considers the run done.

2. **During forge retrospective** (combined with existing cartographer recorder dispatch): The forge retrospective already dispatches a diagnostic extraction subagent for debugging sessions (line 74 of `skills/forge-skill/SKILL.md`). For build sessions, the retrospective dispatch includes the build decision journal content. The cartographer recorder is extended to extract substantive design decisions (not operational routing decisions) from this content and write them to the relevant module files.

## Key Decisions

### DEC-1: New section in existing module files vs. separate per-module decision files

**Choice:** New `## Key Decisions` section within existing module files.

**Alternatives considered:**
- Separate `modules/<name>.decisions.md` files: Rejected because it doubles the file count, requires changes to the load-mode dispatch logic (line 337-338 of `skills/cartographer-skill/SKILL.md`), and means decisions are not co-located with the module context they explain.
- Append to `## Gotchas` section: Rejected because gotchas are surprises (what IS unexpected), while decisions are justifications (why it IS this way). Conflating them weakens both signals.

**Reasoning:** Module files are already loaded in their entirety during load mode. Adding a section requires zero dispatch-logic changes. The 100-line cap is sufficient: a module with 5 components, 3 dependencies, 4 contracts, 3 gotchas, and 5 decisions fits comfortably. If a module needs more than 5 persistent decisions, the oldest low-value ones should be compressed or pruned.

### DEC-2: Cross-cutting decisions in a new file vs. expanding map.md

**Choice:** New `cartographer/decisions.md` file with 200-line cap.

**Alternatives considered:**
- Expand `map.md` Key Architectural Decisions section: Rejected because map.md is loaded by the orchestrator on every consult (line 65-66 of `skills/cartographer-skill/SKILL.md`). Architectural decisions are fine there (brief, top-level), but detailed cross-cutting decisions with alternatives and evidence would bloat the orchestrator's context.
- Put all cross-cutting decisions in `conventions.md`: Rejected because conventions describe patterns (how things are done), not justifications (why things are done this way). Mixing them dilutes the signal of both files.

**Reasoning:** A dedicated file keeps the orchestrator thin (it only reads `map.md`) while giving subagents access to cross-cutting rationale when needed. The 200-line cap matches the existing convention for top-level cartographer files.

### DEC-3: Extraction via existing recorder dispatch vs. new dedicated subagent

**Choice:** Extend the existing cartographer recorder prompt to handle decision extraction as an additional input type.

**Alternatives considered:**
- New dedicated "Decision Archaeologist" subagent: Rejected because it adds a new subagent type, increasing dispatch complexity and context cost. The recorder already handles module updates, conventions, landmines, and defect signatures.
- Direct writes by the orchestrator (no subagent): Rejected because decision extraction requires judgment (which decisions are module-scoped vs. cross-cutting, which are significant enough to persist, how to compress). This is exactly what the Sonnet recorder subagent is designed for.

**Reasoning:** The recorder prompt (`skills/cartographer-skill/recorder-prompt.md`) already has a precedent for handling different input types (standard exploration vs. defect signature recording, line 152-250). Adding a decision extraction mode follows the same pattern: a new section in the prompt with input format, rules, and output format.

### DEC-4: Decision entry format — structured YAML vs. compact markdown

**Choice:** Compact single-line-plus-expansion markdown entries within module files.

**Alternatives considered:**
- YAML blocks within markdown: Rejected because module files are markdown, and embedding YAML creates parsing complexity for the recorder and readers. The contract YAML schema works for `docs/plans/` files because those are standalone YAML, not sections within markdown.
- Full decision records (multi-paragraph): Rejected because module files have a 100-line cap. At 5-10 lines per decision, only 2-3 decisions would fit.

**Reasoning:** The compact format (`- **Decision title** (date, ticket, confidence): Reasoning. Alternatives: X (rejected: reason), Y (rejected: reason). Evidence: Z.`) packs maximum information into 2-3 lines per entry. This matches the density of the existing Contracts and Gotchas sections.

### DEC-5: Extraction timing — spec decisions before scratch cleanup vs. at scratch cleanup time

**Choice:** Extract immediately after the final wave completes, before the orchestrator considers the run finished.

**Alternatives considered:**
- Extract during scratch stale cleanup (24-hour mark): Rejected because cleanup is a destructive operation that runs at the start of the *next* run (line 194-196 of `skills/spec/SKILL.md`). If no next run happens within 24 hours, decisions are lost. If the next run is for a different epic, the cleanup context lacks the module-mapping awareness needed for extraction.
- Extract during forge retrospective only: Rejected because /spec runs do not always trigger a forge retrospective in the same session. The spec orchestrator completes and the session may end without a build or debugging task that would trigger forge.

**Reasoning:** Extracting at the end of the spec run guarantees decisions are captured while the full context (module mappings, ticket-to-file associations, dependency graph) is available. The extraction adds one Sonnet recorder dispatch — the same cost as a standard cartographer record operation.

### DEC-6: Which subagent types receive `decisions.md` during load mode

**Choice:** Implementers and reviewers/red-team get `decisions.md`; investigators and plan writers do not.

**Alternatives considered:**
- All subagent types: Rejected because investigators are exploring unknowns (decisions about known things may bias them), and plan writers are creating new plans (prior decisions about different work may anchor them).
- Implementers only: Rejected because reviewers need decision context to distinguish intentional constraints from accidental ones. A reviewer who does not know "we chose REST because the consumer cannot handle streaming" may flag the REST choice as a deficiency.

**Reasoning:** Implementers need decisions to avoid re-litigating during implementation. Reviewers need decisions to judge code in context. Red-team agents need decisions to test whether the chosen approach holds under adversarial conditions. This matches the existing pattern: implementers get `conventions.md`, reviewers get `landmines.md` (line 347-353 of `skills/cartographer-skill/SKILL.md`).

## Migration / Implementation Path

### Phase 1: Storage Format (no behavior changes)

Add `## Key Decisions` section template to the module file format in `skills/cartographer-skill/SKILL.md` (between `## Contracts` and `## Gotchas`). Add `cartographer/decisions.md` file format specification. Update file size caps table to include `decisions.md`. No existing data is affected — module files without the section continue to work.

### Phase 2: Recorder Prompt Extension

Add a "Decision Extraction" mode to `skills/cartographer-skill/recorder-prompt.md`, parallel to the existing "Defect Signature Recording" mode (line 152). Define input format (raw decisions from spec scratch or build journal), output format (structured entries for module files and/or `decisions.md`), and extraction rules (what qualifies as a persistent decision, how to map decisions to modules).

### Phase 3: Spec Extraction Hook

Add a post-completion step to the spec orchestration flow in `skills/spec/SKILL.md` (after the final wave completes, before the run is considered done). This step reads the scratch `decisions.md`, maps decisions to cartographer modules using file paths from the design docs, and dispatches a cartographer recorder with the decision extraction directive.

### Phase 4: Forge/Build Extraction Hook

Extend the forge retrospective in `skills/forge-skill/SKILL.md` to include substantive design decisions (not just routing decisions) in the cartographer recorder dispatch. This requires the retrospective to distinguish between routing decisions (reviewer model, gate rounds) and design decisions (technology choices, API designs, architecture) from the build decision journal.

### Phase 5: Load Mode Update

Update the subagent loading table in `skills/cartographer-skill/SKILL.md` (line 347-353) to add `decisions.md` to the implementer and reviewer/red-team columns. No code changes needed for module-level decisions (they are already in the module files that get loaded).

## Risk Areas

### Module File Line Cap Pressure

Adding a `## Key Decisions` section to module files reduces the space available for other sections. A module file at 95 lines today would need pruning to accommodate decisions.

**Mitigation:** The recorder prompt already requires compression when files approach the 100-line cap (line 107-108 of `skills/cartographer-skill/recorder-prompt.md`). Decision entries use a compact format (2-3 lines each). If a module has more decisions than fit, the recorder should move the oldest or lowest-confidence ones to the cross-cutting `decisions.md` with a module tag, or compress them into a single summary line.

### Decision Staleness

Decisions extracted 20 sessions ago may reference APIs or constraints that no longer exist.

**Mitigation:** Decision entries include a date and source ticket. The recorder's existing merge rule ("contradictions: flag to user", line 221 of `skills/cartographer-skill/SKILL.md`) applies. When a recorder observes that a decision's constraint no longer holds (e.g., the downstream consumer now supports streaming), it flags the contradiction and updates or removes the entry.

### Extraction Quality — Signal vs. Noise

Not every decision in a spec scratch `decisions.md` deserves permanent persistence. High-confidence, single-ticket, implementation-detail decisions (e.g., "use a for-loop over a map") add noise.

**Mitigation:** The recorder prompt defines extraction criteria: persist decisions where (a) confidence is medium or low, OR (b) the decision affects module-level architecture or cross-ticket interfaces, OR (c) the decision records why an alternative was rejected (the "why not" is the most valuable part). High-confidence implementation details are filtered out by the recorder.

### Dual-Write During Spec — Ordering Risk

The spec orchestrator writes to `docs/plans/` (design docs, contracts) and then dispatches cartographer recording. If the session is interrupted between these two steps, decisions are generated but not persisted to cartographer.

**Mitigation:** Decisions are already persisted in the committed design docs and contract `ambiguity_resolutions`. The cartographer extraction is a secondary persistence path for indexed, module-scoped access. Loss of this step is recoverable — a future session can re-extract from the design docs in `docs/plans/`.

## Acceptance Criteria

1. **Module file format updated**: `skills/cartographer-skill/SKILL.md` module file template (around line 97-129) includes a `## Key Decisions` section between `## Contracts` and `## Gotchas`, with format specification and examples.

2. **Cross-cutting decisions file specified**: `skills/cartographer-skill/SKILL.md` storage section (around line 42-59) includes `decisions.md` in the file listing with a 200-line cap, and the file size caps table (around line 63-71) includes a row for `decisions.md`.

3. **Recorder prompt extended**: `skills/cartographer-skill/recorder-prompt.md` includes a "Decision Extraction" mode with defined input format, output format, extraction criteria, and module-mapping rules, comparable in structure to the existing "Defect Signature Recording" mode (line 152-250).

4. **Spec extraction hook added**: `skills/spec/SKILL.md` orchestration flow includes a step after the final wave completes that dispatches a cartographer recorder with decision extraction input derived from the scratch `decisions.md`.

5. **Forge extraction hook added**: `skills/forge-skill/SKILL.md` retrospective mode includes substantive design decision extraction alongside the existing diagnostic extraction dispatch (line 74), with filtering to exclude operational routing decisions.

6. **Load mode table updated**: The subagent loading table in `skills/cartographer-skill/SKILL.md` (line 347-353) includes `decisions.md` in the context provided to implementer and reviewer/red-team subagent types.

7. **Line cap enforcement**: Module files with `## Key Decisions` remain under the 100-line cap. `decisions.md` remains under the 200-line cap. Recorder prompt includes compression/overflow rules.

8. **No new skills, modes, or subagent types**: The implementation uses existing cartographer recorder dispatch, existing forge retrospective hook, and existing spec orchestration flow. No new skill files are created.

9. **Backward compatibility**: Module files without a `## Key Decisions` section continue to function. The recorder creates the section on first decision extraction. Existing consult and load modes are unaffected when the section is absent.

10. **Re-litigation prevention verifiable**: After a decision is persisted to a module file, a subsequent cartographer load for that module includes the decision text in the subagent prompt. A subagent receiving "REST chosen because downstream cannot handle streaming" has the information needed to avoid proposing gRPC for that module.
