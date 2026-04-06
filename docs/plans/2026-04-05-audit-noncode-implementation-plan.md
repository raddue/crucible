---
ticket: "#102"
title: "Mature /audit — Implementation Plan"
date: "2026-04-05"
source: "spec"
---

# Mature /audit — Implementation Plan

## Task Overview

7 tasks across 2 waves. All deliverables are prompt templates and SKILL.md updates — no compiled code, no runtime dependencies.

## Wave 1: Core Infrastructure

### Task 1: Add artifact type detection and routing to SKILL.md

**Files:** `skills/audit/SKILL.md`
**Complexity:** High
**Dependencies:** None

Update SKILL.md to add:

1. **Artifact type declaration** — Add a new section after the Overview defining the 4 supported types (`code`, `design`, `plan`, `concept`) with their lens configurations.

2. **Invocation API update** — Add `artifact_type` parameter (optional, auto-detected if omitted). Document auto-detection logic:
   - Directory or subsystem name → `code`
   - File with code extension → `code`
   - `docs/plans/*-design.md` or frontmatter `source: design/spec` → `design`
   - `docs/plans/*-implementation-plan.md` or `*-prd.md` → `plan`
   - Freeform text (no file path) → `concept`
   - Ambiguous → ask user

3. **Phase 1 bifurcation** — Add non-code scoping path: validate artifact → detect type → gather supporting context → user gate. Code path unchanged.

4. **Phase 2 bifurcation** — Add non-code dispatch path: 4 parallel lenses using `audit-noncode-lens-prompt.md` with lens-specific instructions. Document the lens configuration tables for all 3 non-code types (design, plan, concept). Code path unchanged.

5. **Phase 2.5 bifurcation** — Add non-code blind-spots dispatch using `audit-noncode-blindspots-prompt.md`. No coverage map for non-code (all lenses see full artifact). Code path unchanged.

6. **Finding format adaptation** — Document `section` field replacing `file` + `line_range` for non-code findings. Document lens-specific `concern` field replacing code-specific fields (`scenario`, `failure_scenario`, `convention_violated`, `impact`).

7. **Lens configuration reference tables** — Full per-type lens configs with core question, focus areas, and exclusions for each of the 12 non-code lenses (4 types × ... wait, 3 non-code types × 4 lenses = 12 lens configs).

### Task 2: Create non-code lens prompt template

**Files:** `skills/audit/audit-noncode-lens-prompt.md`
**Complexity:** Medium
**Dependencies:** Task 1

Create a single parameterized dispatch template with:
- `<!-- DISPATCH: disk-mediated -->` header
- Role: "You are an auditor reviewing a non-code artifact through a specific analytical lens."
- Template placeholders:
  - `{{LENS_NAME}}` — e.g., "Technical Soundness"
  - `{{LENS_QUESTION}}` — e.g., "Are the technical decisions well-reasoned?"
  - `{{LENS_FOCUS_AREAS}}` — bullet list of what to look for
  - `{{LENS_EXCLUSIONS}}` — what NOT to look for (other lenses handle it)
  - `{{ARTIFACT_TYPE}}` — design/plan/concept
  - `{{ARTIFACT_CONTENT}}` — the full artifact text
  - `{{SUPPORTING_CONTEXT}}` — referenced docs, if any
- Output format matching code lens format but with `section` instead of `file` + `line_range`, and `concern` as the lens-specific field
- 5-finding cap with justification override
- Context self-monitoring section
- Evidence grounding rules: every finding must quote specific text from the artifact
- "Do NOT suggest fixes" and "Do NOT speculate" guardrails

### Task 3: Create non-code blind-spots prompt template

**Files:** `skills/audit/audit-noncode-blindspots-prompt.md`
**Complexity:** Medium
**Dependencies:** Task 1

Create dispatch template with:
- `<!-- DISPATCH: disk-mediated -->` header
- Role: "You are a second-opinion auditor. Four specialist reviewers have already examined this artifact through separate analytical lenses. Your job is to find what they MISSED."
- Input: full artifact content + lens summary (which lenses ran and what they focused on)
- Gap categories specific to documents:
  - Internal contradictions
  - Unstated assumptions
  - Missing stakeholder perspectives
  - Scope boundary gaps
  - Silent dependencies
  - Logical leaps (conclusions not supported by the argument)
- 8-finding cap
- Same output format as code blind-spots but with `section` instead of `file` + `line_range`

## Wave 2: Integration and Documentation

### Task 4: Update Phase 1 scoping for non-code artifacts

**Files:** `skills/audit/SKILL.md`
**Complexity:** Low
**Dependencies:** Task 1

Add detailed non-code scoping procedure to Phase 1:
1. If input is a file path: read file, check frontmatter, detect type
2. If input is freeform text: set type to `concept`, use text as artifact content
3. Gather supporting context: scan artifact for references to other docs (e.g., "see design doc at...", "#NNN", file paths). Read referenced docs up to 2000-line soft cap.
4. Present user gate: "Auditing [name] as [type]. Supporting context: [list]. Proceed?"
5. Write `gate-approved.md` for compaction recovery (same as code path)

### Task 5: Update Phase 2.5 for non-code artifacts

**Files:** `skills/audit/SKILL.md`
**Complexity:** Low
**Dependencies:** Task 1, Task 3

Document non-code blind-spots dispatch:
1. No coverage map construction (all lenses see full artifact)
2. Instead, build a lens summary: which 4 lenses ran, their core questions, and finding counts
3. Dispatch `audit-noncode-blindspots-prompt.md` with artifact + lens summary
4. No follow-up dispatch for non-code (the artifact is fully visible to blind-spots agent)

### Task 6: Update communication and status sections

**Files:** `skills/audit/SKILL.md`
**Complexity:** Low
**Dependencies:** Task 1

Update narration examples and pipeline status format to include artifact type:
- Status line: "Auditing [name] as [type]. Phase 2: [lens status]."
- Lens names in status reflect the current artifact type (e.g., "Technical Soundness: DONE (3 findings)" not "Correctness: DONE")
- Pipeline status file `## Lenses` section uses type-appropriate lens names

### Task 7: Update README

**Files:** `README.md`
**Complexity:** Low
**Dependencies:** Task 1

Update the audit entry in the README to reflect multi-artifact support. Change description from code-only subsystem review to artifact-aware subsystem/document review. One sentence, not a paragraph.

## Dependency Graph

```
Task 1 (SKILL.md core) ← Task 2 (noncode lens template)
                       ← Task 3 (noncode blindspots template)
                       ← Task 4 (Phase 1 scoping detail)
                       ← Task 5 (Phase 2.5 detail)
                       ← Task 6 (communication updates)
                       ← Task 7 (README)
```

Task 1 is the foundation. Tasks 2-7 are independent of each other.

## Implementation Notes

- **This is a prompt-only skill update.** No Python scripts, no shell commands. SKILL.md + 2 new prompt templates.
- **Code path is untouched.** The 6 existing prompt templates (`audit-correctness-prompt.md`, `audit-robustness-prompt.md`, `audit-consistency-prompt.md`, `audit-architecture-prompt.md`, `audit-blindspots-prompt.md`, `audit-scoping-prompt.md`) are not modified.
- **Disk-mediated dispatch.** Both new templates use the shared dispatch convention.
- **Testing strategy.** Acceptance: invoke `/audit` on a design doc, verify 4 type-appropriate lenses dispatch. Invoke on a plan, verify different lenses. Invoke on code subsystem, verify existing behavior unchanged.
