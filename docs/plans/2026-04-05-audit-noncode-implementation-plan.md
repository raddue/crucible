---
ticket: "#102"
title: "Mature /audit — Implementation Plan"
date: "2026-04-05"
source: "spec"
---

# Mature /audit — Implementation Plan

## Task Overview

6 tasks in a flat fan from Task 1. All deliverables are prompt templates and SKILL.md updates — no compiled code, no runtime dependencies.

### Task 1: Add artifact type system, routing, and phase adaptations to SKILL.md

**Files:** `skills/audit/SKILL.md`
**Complexity:** High
**Dependencies:** None

This is the single large task that modifies SKILL.md. All non-code logic lives here — no subsequent tasks re-edit SKILL.md to "add detail."

Updates:

1. **Frontmatter and triggers** — Update `description` to include non-code artifacts. Add trigger phrases: "audit this design", "review this plan", "audit concept."

2. **Artifact type declaration** — New section after Overview defining 4 types (`code`, `design`, `plan`, `concept`) with summary table and auto-detection logic (frontmatter `source` field → path patterns → ask user). Include auto-detection limitations note for non-Crucible repos.

3. **Invocation API** — Add `artifact_type` parameter (optional, auto-detected if omitted).

4. **Lens configuration tables** — Full per-type configs for all 12 non-code lenses (3 types × 4 lenses). Each entry: lens name, core question, focus areas, exclusions. Design: Technical Soundness, Integration Impact, Edge Cases, Scope Clarity. Plan: Feasibility, Risk & Dependencies, Completeness, Assumptions. Concept: Problem-Solution Fit, Feasibility & Cost, Stakeholder Alignment, Blind Assumptions.

5. **Phase 1 (non-code scoping)** — Full procedure: validate artifact → detect type → gather supporting context (parse markdown links, file paths, issue refs; read referenced files up to 2000-line soft cap with prioritization rules) → present user gate → write `gate-approved.md` and `artifact-type.md` to scratch.

6. **Phase 2 (non-code lens dispatch)** — 4 parallel lenses using `audit-noncode-lens-prompt.md` with lens-specific instruction injection. All single-agent, no dual-agent pattern. Full artifact + supporting context to each lens.

7. **Phase 2.5 (non-code blind-spots)** — Build lens summary (format: lens name, core question, finding counts, focus areas). Dispatch `audit-noncode-blindspots-prompt.md` with artifact + lens summary. No coverage map, no follow-up dispatch.

8. **Finding format** — Document `section` field (nearest markdown heading, e.g., `## Key Decisions > DEC-3`) replacing `file` + `line_range`. Document `concern` field replacing lens-specific code fields.

9. **Compaction recovery** — Write `artifact-type.md` at Phase 1 completion. Non-code recovery: read type file → look for `<lens-name-kebab>-findings.md` → look for `noncode-blindspots-findings.md` → resume from latest phase. Fall back to code recovery if `artifact-type.md` absent.

10. **Communication updates** — Status narration uses type-appropriate lens names. Pipeline status `## Lenses` section reflects current artifact type.

11. **Cartographer recording** — Skip for non-code (no subsystem manifest to record).

12. **Distinction table** — Update to "existing code subsystems or non-code artifacts."

### Task 2: Create non-code lens prompt template

**Files:** `skills/audit/audit-noncode-lens-prompt.md`
**Complexity:** Medium
**Dependencies:** Task 1

Create a single parameterized dispatch template with:
- `<!-- DISPATCH: disk-mediated -->` header
- Role: "You are an auditor reviewing a non-code artifact through a specific analytical lens."
- Template placeholders: `{{LENS_NAME}}`, `{{LENS_QUESTION}}`, `{{LENS_FOCUS_AREAS}}`, `{{LENS_EXCLUSIONS}}`, `{{ARTIFACT_TYPE}}`, `{{ARTIFACT_CONTENT}}`, `{{SUPPORTING_CONTEXT}}`
- Output format: section (nearest markdown heading), evidence (quoted text), concern (lens-specific), description, severity
- 5-finding cap with justification override
- Context self-monitoring section
- Evidence grounding: every finding must quote specific text from the artifact
- Guardrails: "Do NOT suggest fixes", "Do NOT speculate"

### Task 3: Create non-code blind-spots prompt template

**Files:** `skills/audit/audit-noncode-blindspots-prompt.md`
**Complexity:** Medium
**Dependencies:** Task 1

Create dispatch template with:
- `<!-- DISPATCH: disk-mediated -->` header
- Role: "You are a second-opinion auditor. Four specialist reviewers have already examined this artifact through separate analytical lenses. Your job is to find what they MISSED."
- Input: full artifact content + lens summary (structured format: lens name, core question, finding counts, focus areas per lens)
- Gap categories: internal contradictions, unstated assumptions, missing stakeholder perspectives, scope boundary gaps, silent dependencies, logical leaps
- 8-finding cap
- Same output format as non-code lens (section, evidence, concern, description, severity)

### Task 4: Update README

**Files:** `README.md`
**Complexity:** Low
**Dependencies:** Task 1

Update the audit entry in the README to reflect multi-artifact support. Change description from code-only subsystem review to artifact-aware subsystem/document review.

### Task 5: Update contract

**Files:** `docs/plans/2026-04-05-audit-noncode-contract.yaml`
**Complexity:** Low
**Dependencies:** Task 1

Update the contract to reflect any changes from QG (concept lens names changed, new acceptance criteria added).

### Task 6: Verify code path unchanged

**Files:** None (verification only)
**Complexity:** Low
**Dependencies:** Tasks 1-3

Verify that all 6 existing code prompt templates are unmodified (`git diff` shows no changes to `audit-correctness-prompt.md`, `audit-robustness-prompt.md`, `audit-consistency-prompt.md`, `audit-architecture-prompt.md`, `audit-blindspots-prompt.md`, `audit-scoping-prompt.md`).

## Dependency Graph

```
Task 1 (SKILL.md — all non-code logic) ← Task 2 (noncode lens template)
                                        ← Task 3 (noncode blindspots template)
                                        ← Task 4 (README)
                                        ← Task 5 (contract update)
                                        ← Task 6 (code path verification)
```

Task 1 is the foundation. Tasks 2-6 are independent of each other.

## Implementation Notes

- **This is a prompt-only skill update.** No Python scripts, no shell commands. SKILL.md + 2 new prompt templates.
- **Code path is untouched.** The 6 existing prompt templates are not modified. Task 6 explicitly verifies this.
- **Disk-mediated dispatch.** Both new templates use the shared dispatch convention.
- **Single SKILL.md edit task.** Task 1 is large but coherent — it writes all non-code logic to SKILL.md in one pass, avoiding ambiguous boundaries between "stub" and "detail" tasks.
- **Testing strategy.** Invoke `/audit` on a design doc → verify 4 design-specific lenses dispatch. Invoke on a plan → verify 4 plan-specific lenses. Invoke on code subsystem → verify existing behavior unchanged. Invoke after compaction → verify non-code recovery works.
