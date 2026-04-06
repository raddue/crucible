---
ticket: "#121"
title: "Assay Skill — Implementation Plan"
date: "2026-04-05"
source: "spec"
---

# Assay Skill — Implementation Plan

## Task Overview

4 tasks in a single wave. All deliverables are prompt templates and SKILL.md — no compiled code, no runtime dependencies.

## Wave 1: Full Implementation

### Task 1: Create SKILL.md

**Files:** `skills/assay/SKILL.md`
**Complexity:** Medium
**Dependencies:** None

Create the skill definition with:
- YAML frontmatter (`name: assay`, description with trigger words)
- Overview with `<!-- CANONICAL: shared/dispatch-convention.md -->` reference
- Announce text: "I'm using the assay skill to evaluate competing approaches."
- Invocation API: input schema (question, context, decision_type, approaches, cascading_decisions)
- Execution flow: receive input → detect decision type → dispatch evaluator → validate output → return report
- Decision type adaptation table (scoring weights per type)
- Confidence scoring rules (high/medium/low)
- Evidence grounding requirements
- Kill criteria and `would_recommend_if` requirements
- Output schema (full Assay Report JSON)
- Error handling: invalid input, evaluator timeout, malformed output (retry once, return error on second failure)
- Integration section documenting all 4 consumer skills

### Task 2: Create evaluator prompt template

**Files:** `skills/assay/assay-evaluator-prompt.md`
**Complexity:** High
**Dependencies:** Task 1

Create the dispatch template with `<!-- DISPATCH: disk-mediated -->` header.

The evaluator prompt must include:
- Role definition: "You are an approach evaluator. You receive a decision question, context, and optionally a set of candidate approaches..."
- Decision type adaptation instructions (scoring weight tables)
- Approach generation instructions (when `approaches` is not provided): "Generate 2-4 candidate approaches based on the question and context"
- Evaluation procedure: for each approach, score against constraint_fit dimensions (pattern_alignment, scope_fit, reversibility, integration_risk)
- Evidence grounding rules: cite specific file:line from context, not generic best practices
- Confidence scoring: criteria for high/medium/low, `missing_information` when low
- Kill criteria requirement: every recommended approach must have a kill_criteria, every alternative must have would_recommend_if
- Cascading decision handling: treat as immutable constraints, flag conflicts in prior_decision_conflicts
- Exact JSON output schema with example
- Placeholder sections: `{{QUESTION}}`, `{{CONTEXT}}`, `{{DECISION_TYPE}}`, `{{APPROACHES}}`, `{{CASCADING_DECISIONS}}`

### Task 3: Document consumer integration patterns

**Files:** `skills/assay/SKILL.md` (integration section)
**Complexity:** Low
**Dependencies:** Task 1

Add detailed integration documentation for each of the 4 consumers:
- `/design`: dispatch pattern, what replaces the Domain Researcher, how Challenger interacts with assay output
- `/debugging`: dispatch pattern with hypotheses as approaches, evidence-from-investigation as context
- `/migrate`: dispatch pattern with recon brief as context, strategy as decision_type
- `/prospector`: dispatch pattern with competing redesigns as approaches, optimization as decision_type

Include example dispatch calls for each consumer showing the exact parameters they'd pass.

### Task 4: Add assay to README

**Files:** `README.md`
**Complexity:** Low  
**Dependencies:** Task 1

Add assay to the README's Core Pipeline section (it's a reusable primitive, not a domain-specific utility). One-row table entry describing the skill's purpose and consumer pattern.

## Dependency Graph

```
Task 1 (SKILL.md) ← Task 2 (evaluator prompt)
                  ← Task 3 (consumer integration docs)
                  ← Task 4 (README)
```

All tasks depend on Task 1 (the skeleton), but Tasks 2-4 are independent of each other.

## Implementation Notes

- **This is a prompt-only skill.** No Python scripts, no shell commands. The skill dispatches one Opus agent and returns its structured output.
- **Disk-mediated dispatch.** The evaluator prompt template uses the shared dispatch convention.
- **Consumer migration is NOT in scope.** This ticket creates the assay skill. Migrating `/design` to use assay (shedding its Domain Researcher) is a separate ticket. Same for `/debugging`, `/migrate`, `/prospector`.
- **JSON output validation.** The SKILL.md should instruct the orchestrator to validate the evaluator's output against the Assay Report schema. If validation fails, retry once with the validation errors as feedback.
