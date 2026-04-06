---
ticket: "#121"
title: "Assay Skill — Recon-Informed Approach Evaluator"
date: "2026-04-05"
source: "spec"
---

# Assay Skill — Design Document

**Goal:** Extract the "evaluate competing approaches and recommend" pattern from 4 skills (design, debugging, migrate, prospector) into a standalone `/assay` skill. Reusable, evidence-grounded, decision-type-adaptive. Consumes recon briefs or caller-provided context. Returns structured Assay Reports that downstream skills parse programmatically.

**Name origin:** In metallurgy, an assay tests raw material to determine its quality and composition before committing it to the forge.

## 1. Current State Analysis

The "evaluate approaches" pattern is currently embedded in 4 skills:

| Skill | Current Pattern | Problem |
|---|---|---|
| `/design` | Domain Researcher produces comparison table, orchestrator synthesizes into options | Operates in vacuum — no codebase grounding |
| `/debugging` | Synthesis agent ranks hypotheses by evidence strength | No structured output — orchestrator does ad-hoc selection |
| `/migrate` | Migration analyzer assesses complexity | Single-path analysis, doesn't compare competing strategies |
| `/prospector` | 3 design agents with hardcoded constraints | Constraint mapping is rigid, can't adapt to novel friction types |

All four follow the same flow: **investigate → synthesize competing approaches → select/recommend → present**. Each reimplements the evaluation logic locally. The evaluation quality varies — design uses multi-agent investigation, debugging does it inline, prospector hardcodes constraints.

## 2. Target State

A standalone `/assay` skill that:
1. Accepts a decision/question + context (recon brief or caller-provided evidence)
2. Adapts evaluation criteria based on decision type (architecture, strategy, diagnosis, optimization)
3. Scores each approach against known constraints from the context
4. Returns a structured Assay Report with recommendation, alternatives with kill criteria, and confidence scoring

**Dispatch convention:** All subagent dispatches follow `skills/shared/dispatch-convention.md` — disk-mediated dispatch with dispatch files written to `/tmp/crucible-dispatch-<session-id>/`, manifest logging, and pointer prompts. Prompt template: `skills/assay/assay-evaluator-prompt.md`.

## 3. Architecture

### Single-Agent Design

Assay dispatches **one Opus agent** per invocation. The evaluator receives:
- The decision/question
- Context (recon brief, cascading decisions, caller evidence)
- Decision type hint (or auto-detects from the question)
- Approaches to evaluate (caller-provided, or the evaluator generates candidates)

The evaluator returns a structured Assay Report.

**Why one agent, not multiple?** The evaluation is synthesis — weighing trade-offs, not discovering facts. Discovery is recon's job. Assay operates on already-gathered evidence. Multi-agent evaluation would produce competing recommendations that need meta-synthesis, adding complexity without value.

### Decision Type Adaptation

The evaluator adapts its scoring weights based on decision type:

| Type | Primary Weight | Secondary Weight | Example |
|---|---|---|---|
| `architecture` | Reversibility, constraint fit | Long-term cost, extensibility | "How should components communicate?" |
| `strategy` | Risk, phasing | Blast radius, team capacity | "What migration approach?" |
| `diagnosis` | Evidence strength, testability | Explanation coverage, simplicity | "What's the root cause?" |
| `optimization` | Measurable improvement | Disruption cost, reversibility | "Which redesign reduces friction?" |

If no type hint is provided, the evaluator infers from the question. If ambiguous, defaults to `architecture` (the most general).

### Input Schema

```
/assay
  question: "How should the auth middleware handle token refresh?"
  context: { ... }           # recon brief, cascading decisions, or caller evidence
  decision_type: "architecture"  # optional — architecture | strategy | diagnosis | optimization
  approaches: [              # optional — evaluator generates if omitted
    { name: "Approach A", description: "..." },
    { name: "Approach B", description: "..." }
  ]
  cascading_decisions: [     # optional — prior decisions as hard constraints
    { decision: "Using Redis for session store", reasoning: "..." }
  ]
```

**When approaches are omitted:** The evaluator generates 2-4 candidate approaches based on the question and context. This is the common case when called from `/design` (the dimension is identified, approaches are discovered).

**When approaches are provided:** The evaluator scores them as given. This is the case when called from `/prospector` (competing redesigns already generated) or `/debugging` (hypotheses already identified).

### Output: Assay Report

```json
{
  "decision_type": "architecture",
  "confidence": "high",
  "missing_information": [],
  "recommended": {
    "name": "Event-driven via message bus",
    "rationale": "Aligns with existing src/events/bus.ts pattern...",
    "evidence": ["src/events/bus.ts:14 — existing event dispatch", "src/api/routes/users.ts:7 — already subscribes to events"],
    "risks": ["Adds async complexity to currently synchronous flow"],
    "kill_criteria": "Switch away if latency requirements exceed 50ms p99 (event bus adds ~20ms)"
  },
  "alternatives": [
    {
      "name": "Direct service calls",
      "pros": ["Simpler mental model", "Synchronous — easy to debug"],
      "cons": ["Tight coupling between auth and user services", "Requires shared deployment"],
      "would_recommend_if": "Team prefers simplicity over decoupling, or latency is critical"
    }
  ],
  "constraint_fit": {
    "pattern_alignment": "high",
    "scope_fit": "high",
    "reversibility": "two-way door",
    "integration_risk": "low"
  },
  "prior_decision_conflicts": []
}
```

### Confidence Scoring

| Level | Criteria |
|---|---|
| `high` | One approach clearly dominates on all weighted dimensions |
| `medium` | Two viable options with trade-offs that depend on priority |
| `low` | Need more information before recommending (specify what's missing) |

When confidence is `low`, the `missing_information` array lists specific questions that would resolve the uncertainty. The caller decides whether to gather more context or proceed with the recommendation.

### Kill Criteria

For each non-recommended approach, `would_recommend_if` states the condition that would flip the recommendation. For the recommended approach, `kill_criteria` states when to switch away. This makes decisions revisitable without re-running the full analysis.

### Evidence Grounding

Every recommendation must cite **specific evidence** from the context:
- File:line references from recon briefs
- Specific pattern names from the codebase
- Concrete constraint violations or alignments

"This is the industry standard approach" is NOT evidence. "This aligns with how `src/api/routes/users.ts` already handles it" IS evidence.

When no recon brief is provided, evidence cites the caller's context. Confidence scores skew lower without codebase grounding — the evaluator acknowledges the reduced evidence quality.

## 4. Consumer Integration

### With `/design` (replaces Domain Researcher)

```
/design identifies design dimension
  → dispatch /recon with dimension context (if deep dive)
  → dispatch /assay with:
      question: the design dimension
      context: recon brief + cascading decisions
      decision_type: "architecture"
  → /assay returns Assay Report
  → /design synthesizes report with Challenger findings, presents to user
```

`/design` sheds its Domain Researcher agent. The Codebase Scout and Impact Analyst remain (they discover facts; assay evaluates options).

### With `/debugging` (replaces synthesis convergence)

```
/debugging narrows to candidate root causes
  → dispatch /assay with:
      question: "Which hypothesis best explains the observed symptoms?"
      context: investigation findings (not a full /recon — debugger already has deep context)
      decision_type: "diagnosis"
      approaches: [hypothesis A, hypothesis B, ...]
  → /assay evaluates evidence strength for each
  → /debugging pursues highest-confidence hypothesis
```

### With `/migrate` (replaces migration-analyzer)

```
/migrate identifies migration target
  → dispatch /recon (blast-radius analysis)
  → dispatch /assay with:
      question: "What migration strategy minimizes risk?"
      context: recon brief + migration target details
      decision_type: "strategy"
  → /assay evaluates strategies
  → /migrate proceeds with recommended approach
```

### With `/prospector` (replaces hardcoded constraint mapping)

```
/prospector identifies friction + competing redesigns
  → dispatch /assay with:
      question: "Which redesign offers the best improvement-to-disruption ratio?"
      context: friction analysis + recon brief
      decision_type: "optimization"
      approaches: [redesign A, redesign B, redesign C]
  → /assay evaluates each against codebase constraints
  → /prospector presents ranked options to user
```

## 5. Key Design Decisions

### DEC-1: Single Opus agent, not multi-agent (High confidence)

**Decision:** One evaluator agent per invocation.

**Alternatives considered:**
- Multiple evaluators with meta-synthesis: adds a synthesis layer that assay IS the synthesis layer
- Per-approach agents: generates competitive advocacy rather than balanced evaluation

**Reasoning:** Evaluation is synthesis of already-gathered evidence. Multi-agent adds complexity without discovery value. The caller provides the evidence (via recon or direct context); assay weighs it.

### DEC-2: Structured JSON output, not prose (High confidence)

**Decision:** Assay Report is structured JSON, not a narrative comparison table.

**Alternatives considered:**
- Prose comparison table: human-readable but downstream skills can't parse it programmatically
- Markdown with headers: semi-structured but fragile to parse

**Reasoning:** 4 skills consume assay output. They need to extract `recommended.name`, `confidence`, `kill_criteria` programmatically. JSON is unambiguous. The caller can render it as prose if needed for human presentation.

### DEC-3: Evaluator generates approaches when not provided (Medium confidence)

**Decision:** When `approaches` is omitted, the evaluator generates 2-4 candidates.

**Alternatives considered:**
- Always require approaches: simpler but shifts work to every caller
- Always generate regardless of input: wastes effort when caller already has candidates

**Reasoning:** `/design` identifies dimensions but doesn't enumerate approaches — that's currently the Domain Researcher's job. Assay needs to handle both modes. The `approaches` field being optional makes assay flexible for all 4 consumers.

### DEC-4: No cascading decision modification (High confidence)

**Decision:** Cascading decisions are hard constraints, not suggestions. The evaluator cannot modify or challenge prior decisions.

**Reasoning:** Cascading decisions come from `/design`'s user-approved choices. Assay must respect them as immutable context. Challenging prior decisions is the Challenger agent's job (separate from assay).

## 6. Risk Areas

| Risk | Severity | Mitigation |
|---|---|---|
| JSON output format fragile to LLM variation | Medium | Evaluator prompt includes exact schema + example. Caller validates structure. |
| Without recon brief, recommendations are weak | Low | Confidence score reflects evidence quality. `missing_information` guides the caller. |
| Decision type auto-detection unreliable | Low | Default to `architecture` when ambiguous. Callers that know their type should specify it. |
| Approach generation without recon produces generic options | Medium | Warn in output when evidence is thin. Callers should provide recon for important decisions. |

## 7. Acceptance Criteria

1. Skill definition at `skills/assay/SKILL.md` with invocation API, evaluation flow, and integration docs
2. Evaluator prompt template at `skills/assay/assay-evaluator-prompt.md`
3. Decision type adaptation: different scoring weights for architecture/strategy/diagnosis/optimization
4. Structured JSON Assay Report output with all fields from the schema
5. Confidence scoring (high/medium/low) with `missing_information` when low
6. Kill criteria on recommended approach and `would_recommend_if` on alternatives
7. Evidence grounding: recommendations cite specific file:line or context references
8. Works with recon brief (preferred) or caller-provided context (fallback)
9. Approaches field optional — evaluator generates candidates when omitted
10. Cascading decisions treated as hard constraints
11. Disk-mediated dispatch per `skills/shared/dispatch-convention.md`
