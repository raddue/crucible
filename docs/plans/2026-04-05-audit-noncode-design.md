---
ticket: "#102"
title: "Mature /audit to support non-code artifacts"
date: "2026-04-05"
source: "spec"
---

# Mature /audit to Support Non-Code Artifacts

## Current State Analysis

The `/audit` skill (`skills/audit/SKILL.md`, 424 lines) implements a 4-lens parallel dispatch architecture designed exclusively for code subsystems:

- **Phase 1 (Scoping):** Identifies subsystem files via cartographer or Explore agent (`audit-scoping-prompt.md`). Produces a file manifest with role descriptions.
- **Phase 2 (Analysis):** Dispatches 4 parallel lenses — Correctness, Robustness, Consistency (dual-agent), Architecture — each receiving Tier 1 overview + Tier 2 source partitions under a 1500-line hard cap.
- **Phase 2.5 (Blind-spots):** A fresh agent hunts gaps between lenses using a coverage map of which files were examined by which lenses.
- **Phase 3 (Synthesis):** Deduplication, compounding risk analysis, severity ranking, thematic grouping into structured report.
- **Phase 4 (Cross-reference):** Matches findings against existing issue tracker entries.

The problem: all 6 prompt templates (`audit-correctness-prompt.md`, `audit-robustness-prompt.md`, `audit-consistency-prompt.md`, `audit-architecture-prompt.md`, `audit-blindspots-prompt.md`, `audit-scoping-prompt.md`) assume file-level code analysis. When audit is invoked on a design doc, strategic plan, or product concept, it falls back to improvised analysis — losing the parallel dispatch, blind-spots, compounding risk, and structured reporting.

### Existing Precedent

Quality-gate (`skills/quality-gate/SKILL.md`) already handles multiple artifact types (design, plan, code, hypothesis, mockup, translation) by:
1. Declaring supported types in a table
2. Adapting context preparation per type
3. Selecting fix agents per type
4. Using type-specific framing for hypothesis artifacts

This is the pattern to follow.

## Target State

Audit supports 4 artifact types with per-type lens configurations:

| Artifact Type | Lens 1 | Lens 2 | Lens 3 | Lens 4 |
|---|---|---|---|---|
| `code` | Correctness | Robustness | Consistency | Architecture |
| `design` | Technical Soundness | Integration Impact | Edge Cases | Scope Clarity |
| `plan` | Feasibility | Risk & Dependencies | Completeness | Assumptions |
| `concept` | Problem-Solution Fit | Feasibility & Cost | Stakeholder Alignment | Blind Assumptions |

The `code` path is **completely unchanged** — existing prompt templates, Tier 1/Tier 2 context management, and dual-agent Consistency lens all remain as-is.

Non-code artifact types use:
- A single parameterized prompt template (`audit-noncode-lens-prompt.md`) with lens-specific instruction blocks injected by the orchestrator
- A dedicated non-code blind-spots template (`audit-noncode-blindspots-prompt.md`)
- Simplified scoping (the artifact IS the scope — no subsystem boundary identification)
- Full artifact content passed to each lens (no Tier 1/Tier 2 — non-code artifacts are small enough)

## Key Decisions

### DEC-1: Artifact Type Detection (High Confidence)

**Decision:** Explicit `artifact_type` parameter with auto-detection fallback.

**Alternatives considered:**
- Always require explicit type (rejected: adds friction for the common case)
- Content-based auto-detection only (rejected: unreliable, especially for concept vs plan)

**How it works:**
1. User can pass `artifact_type: design | plan | concept | code`
2. If omitted, auto-detect using this priority chain:
   - Directory or subsystem name → `code` (existing behavior)
   - File with code extension (`.py`, `.ts`, `.go`, etc.) → `code`
   - YAML frontmatter contains `source: "design"` or `source: "spec"` → `design`
   - YAML frontmatter contains `source: "plan"` or title contains "implementation plan" → `plan`
   - No file path (freeform text input) → `concept`
   - Ambiguous → ask user: "I detected a markdown document but can't determine its type. Is this a design doc, plan, or concept?"
3. `code` is the default when pointing at a directory or subsystem name (existing behavior)

**Auto-detection limitations:** The frontmatter-based detection relies on Crucible's `source` field convention. Repos without this convention will hit the "ambiguous → ask user" fallback more often. The explicit `artifact_type` parameter is the reliable path for any repo.

### DEC-2: Single Parameterized Non-Code Template (High Confidence)

**Decision:** One `audit-noncode-lens-prompt.md` template with `{{LENS_NAME}}`, `{{LENS_QUESTION}}`, `{{LENS_FOCUS_AREAS}}`, and `{{LENS_EXCLUSIONS}}` placeholders, rather than 12 separate prompt files (3 non-code types × 4 lenses each).

**Alternatives considered:**
- 12 separate prompt files (rejected: massive duplication — the prompt structure is identical across lenses, only the instructions differ)
- Per-type template files, 3 per type (rejected: still 9 new files with heavy duplication)

**Rationale:** Non-code lens prompts share identical structure: role introduction → lens instructions → artifact content → output format. Only the "what to look for" section varies. Defining lens configs in SKILL.md and injecting them is DRY and maintainable. Code lenses remain as separate files because they have genuinely different structures (dual-agent Consistency, different Tier 2 partitioning strategies).

### DEC-3: Non-Code Scoping Is Trivial (High Confidence)

**Decision:** For non-code artifacts, Phase 1 reduces to artifact validation and type detection. No scoping agent needed.

**Rationale:** A design doc or strategic plan IS the scope — there's no subsystem boundary to identify. The orchestrator:
1. Validates the artifact exists and is readable
2. Detects or confirms artifact type
3. Optionally gathers context (referenced docs, related files mentioned in the artifact)
4. Presents a brief scope summary at the user gate

### DEC-4: Non-Code Context Replaces Tier 1/Tier 2 (High Confidence)

**Decision:** Non-code lenses receive the full artifact content (no tiering). If the artifact references other documents, those are gathered as "supporting context" with a soft cap of 2000 lines total.

**Rationale:** Non-code artifacts are typically 100-500 lines. Even with supporting context, they're well under the 1500-line per-agent cap. Tiering adds complexity for no benefit.

### DEC-5: Adapted Blind-Spots for Non-Code (Medium Confidence)

**Decision:** A separate `audit-noncode-blindspots-prompt.md` template that hunts for document-level gaps rather than code-level gaps.

**Non-code blind-spot categories:**
- Internal contradictions (artifact says X in one section, Y in another)
- Unstated assumptions (decisions that depend on conditions not documented)
- Missing stakeholder perspectives (who would disagree with this?)
- Scope boundary gaps (what's just outside scope that could cause problems?)
- Silent dependencies (what external factors does this assume will remain true?)
- Logical leaps (conclusions not supported by the preceding argument)

**Alternative considered:** Reuse code blind-spots template with parameterization (rejected: code blind-spots are deeply tied to coverage maps, file partitions, and code-specific categories like security/performance/concurrency — the document-level gaps are fundamentally different).

### DEC-6: Phase 3 Synthesis Unchanged (High Confidence)

**Decision:** The synthesis process (dedup, compounding risk, severity ranking, thematic grouping, report output) is artifact-type-agnostic. Finding format uses the same structure with a type-adapted specific field.

**Code finding format:** severity, file, line_range, evidence, description + lens-specific field (scenario, failure_scenario, convention_violated, impact)

**Non-code finding format:** severity, section, evidence, description + lens-specific field (concern)

The `section` field replaces `file` + `line_range` for non-code artifacts. Format: the nearest markdown heading that contains the issue, e.g., `## Key Decisions > DEC-3`. For artifacts without markdown headings, use a brief quoted phrase from the opening of the relevant paragraph (e.g., `"The orchestrator validates..."`). This pinned format ensures Phase 3 dedup can match findings from different lenses that reference the same section.

### DEC-7: Finding Cap Unchanged (High Confidence)

**Decision:** 5 findings per lens (8 for blind-spots) regardless of artifact type.

## Artifact Type Lens Configurations

### `design` — Design Documents

| Lens | Core Question | Focus Areas |
|---|---|---|
| Technical Soundness | "Are the technical decisions well-reasoned?" | Trade-off analysis quality, constraint identification, decision-evidence alignment, alternative exploration depth |
| Integration Impact | "How does this design interact with existing systems?" | Breaking changes identified, migration path, dependency awareness, blast radius assessment |
| Edge Cases | "What happens at the boundaries?" | Failure modes addressed, boundary conditions, concurrent usage, data edge cases, degraded-mode behavior |
| Scope Clarity | "Is the scope well-defined and appropriate?" | Non-goals stated, scope-to-problem fit, YAGNI compliance, acceptance criteria testability |

### `plan` — Strategic Plans, Implementation Plans, PRDs

| Lens | Core Question | Focus Areas |
|---|---|---|
| Feasibility | "Can this actually be executed as described?" | Resource requirements vs availability, timeline realism, skill/capability assumptions, tooling prerequisites |
| Risk & Dependencies | "What could derail execution?" | External dependency risks, sequencing risks, single points of failure, rollback provisions, blast radius of partial failure |
| Completeness | "What's missing from this plan?" | Phases covered, milestones defined, success criteria measurable, testing strategy present, communication plan |
| Assumptions | "What's being taken for granted?" | Environmental assumptions, team capacity assumptions, technical assumptions, timeline assumptions, stakeholder alignment assumptions |

### `concept` — Product Concepts, Proposals, Early-Stage Ideas

The concept type is for artifacts that haven't yet been refined into a design or plan. Where `design` assumes technical decisions have been made and `plan` assumes execution steps are defined, `concept` evaluates whether the idea itself is worth pursuing.

| Lens | Core Question | Focus Areas |
|---|---|---|
| Problem-Solution Fit | "Does this concept solve a real problem?" | Problem definition clarity, target audience identified, value proposition specificity, differentiation from existing solutions |
| Feasibility & Cost | "Is this achievable and worth the investment?" | Build vs buy analysis, resource requirements, timeline expectations, opportunity cost, maintenance burden |
| Stakeholder Alignment | "Who needs to agree and will they?" | Decision-makers identified, conflicting incentives surfaced, adoption path realistic, organizational readiness |
| Blind Assumptions | "What is this concept taking for granted?" | Market assumptions, user behavior assumptions, technical assumptions, competitive landscape assumptions, sustainability assumptions |

## Phase Adaptations for Non-Code

### Phase 1: Scoping

**Code (unchanged):** Cartographer → scoping agent → subsystem manifest → user gate.

**Non-code:** Orchestrator validates artifact → detects type → gathers referenced context → presents scope summary → user gate.

**Supporting context gathering procedure:**
1. Parse the artifact for references: markdown links (`[text](path)`), file paths (`path/to/file.ext`), issue references (`#NNN`), and explicit "see also" references
2. For each referenced file that exists locally: read it and include as supporting context
3. For issue references: fetch the issue title and body via `gh issue view`
4. **Soft cap: 2000 lines total** for all supporting context. If exceeded: prioritize files referenced in decision-critical sections (Key Decisions, Risk Areas) over background references. Truncate with a note: "[truncated — 2000-line context cap reached]"
5. If no references found: proceed with artifact-only context (no supporting context)

The user gate is still non-negotiable. For non-code, the gate confirms: "Auditing [artifact name] as a [type]. Supporting context: [list of referenced docs, if any]. Proceed?"

### Phase 2: Lens Dispatch

**Code (unchanged):** 4 parallel lenses with Tier 1/Tier 2 context, dual-agent Consistency.

**Non-code:** 4 parallel lenses using `audit-noncode-lens-prompt.md`, each receiving full artifact content + supporting context. All single-agent (no dual-agent equivalent needed — non-code doesn't have the consistency lens's triage-then-deep-inspect pattern).

### Phase 2.5: Blind-Spots

**Code (unchanged):** Coverage map → blind-spots agent → gap hunting.

**Non-code:** No coverage map needed (all lenses see the full artifact). The `audit-noncode-blindspots-prompt.md` receives the artifact and a **lens summary** with this format:

```
## Lens Summary
- **[Lens Name]** — [Core Question]. Findings: N (Fatal: N, Significant: N, Minor: N). Focus areas: [brief list].
[repeat for each lens]
```

The blind-spots agent uses this summary to understand which analytical angles were already covered and hunts for document-level gaps: contradictions, unstated assumptions, missing perspectives, scope boundary gaps, silent dependencies, and logical leaps.

### Phase 3: Synthesis

**Unchanged for both code and non-code.** The finding format is consistent enough that the same dedup/compounding/ranking logic applies. The `section` field in non-code findings replaces `file` + `line_range`.

### Phase 4: Cross-Reference

**Unchanged.** Works on findings regardless of artifact type.

### Compaction Recovery

The existing compaction recovery logic checks for code-specific scratch files (`manifest.md`, `<lens>-partition.md`, `consistency-a-findings.md`, `consistency-b-findings.md`). Non-code audits need adapted recovery.

**Non-code scratch file naming convention:**
- `artifact-type.md` — contains the detected artifact type, written at Phase 1 completion
- `<lens-name-kebab>-findings.md` — e.g., `technical-soundness-findings.md`, `feasibility-findings.md`
- `noncode-blindspots-findings.md` — blind-spots findings
- No partition files (non-code lenses receive full artifact, no partitioning)
- `gate-approved.md` — same as code path

**Recovery procedure:** On compaction recovery, read `artifact-type.md` first. If present and not `code`, follow non-code recovery:
1. Read `artifact-type.md` to recover type
2. Look for `<lens-name>-findings.md` files matching the type's lens names
3. Look for `noncode-blindspots-findings.md`
4. Resume from the latest completed phase

If `artifact-type.md` is absent, fall back to existing code recovery.

### SKILL.md Metadata Updates

The SKILL.md frontmatter `description` and trigger phrases must be updated to include non-code artifacts:

**Current:** `"Review existing subsystems for bugs, robustness gaps, inconsistencies, and architecture issues. Triggers on 'audit', 'review subsystem', 'check the save system', 'examine the UI code', or any task requesting adversarial review of existing (not newly written) code."`

**Updated:** `"Adversarial review of code subsystems or non-code artifacts (design docs, plans, concepts) through parallel analytical lenses. Triggers on 'audit', 'review subsystem', 'audit this design', 'review this plan', 'check the save system', or any task requesting adversarial review of existing artifacts."`

The "Distinction from Related Skills" table must also be updated: audit reviews "existing code subsystems or non-code artifacts" (not just "existing code in a subsystem").

### Phase 4: Cartographer Recording

For non-code audits, skip cartographer recording (Mode 1). The recorder expects a subsystem manifest with file paths and role descriptions — non-code audits do not produce this. Recording a single-file "manifest" adds noise to the cartographer map without structural value.

## Invocation Examples

**Design doc audit:**
```
/audit docs/plans/2026-04-01-auth-redesign-design.md
```
Auto-detects `design` from path and frontmatter. Dispatches Technical Soundness, Integration Impact, Edge Cases, Scope Clarity lenses.

**Plan audit with explicit type:**
```
/audit docs/plans/2026-04-01-migration-plan.md artifact_type: plan
```
Dispatches Feasibility, Risk & Dependencies, Completeness, Assumptions lenses.

**Concept audit from freeform input:**
```
/audit "We should build a CLI tool that converts design docs into interactive decision trees..."
```
Auto-detects `concept` (no file path, freeform text). Dispatches Viability, Technical Feasibility, User Impact, Gaps lenses.

**Code audit (unchanged):**
```
/audit save/load
```
Existing behavior. No changes to code audit path.

## Risk Areas

1. **Lens quality for non-code:** The parameterized template approach means lens-specific instructions must be precise enough to produce useful findings. Risk mitigated by defining detailed focus areas in SKILL.md.

2. **Auto-detection ambiguity:** A markdown file could be a design doc, a plan, or a concept. Mitigation: check for frontmatter `source` field first, then path patterns, then ask.

3. **Blind-spots template quality:** Document-level gap hunting is less well-defined than code-level gap hunting. The non-code blind-spots categories (contradictions, unstated assumptions, missing perspectives) are broader. Risk: findings may be more subjective. Mitigation: evidence grounding rules still apply — every finding must quote specific text from the artifact.

## Acceptance Criteria

1. `/audit` on a design doc dispatches 4 design-specific lenses in parallel and produces a structured report
2. `/audit` on a plan dispatches 4 plan-specific lenses and produces a structured report
3. `/audit` on freeform text dispatches 4 concept-specific lenses and produces a structured report
4. Code audit path is completely unchanged — all existing prompt templates untouched
5. Non-code findings use `section` instead of `file` + `line_range`
6. User gate still fires for non-code artifacts before Phase 2
7. Blind-spots agent runs for non-code artifacts with document-level gap categories
8. SKILL.md frontmatter description and trigger phrases updated to include non-code artifacts
9. Compaction recovery works for non-code audits (reads `artifact-type.md`, recovers non-code lens findings)
10. Pipeline status lens names reflect the current artifact type (e.g., "Technical Soundness" not "Correctness" for design audits)
