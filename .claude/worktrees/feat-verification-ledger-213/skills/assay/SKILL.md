---
name: assay
description: "Recon-informed approach evaluator. Weighs competing options against codebase constraints and returns structured recommendations with confidence scoring, kill criteria, and evidence grounding. Consumes recon briefs or caller context. Used by design, spec, migrate. Triggers on /assay, 'evaluate approaches', 'which option', 'compare alternatives'."
---

# Assay

## Overview

<!-- CANONICAL: shared/dispatch-convention.md -->
All subagent dispatches use disk-mediated dispatch. See `shared/dispatch-convention.md` for the full protocol.

Evaluate competing approaches against codebase constraints. Returns a structured Assay Report with a recommendation, alternatives with kill criteria, and confidence scoring. Evidence-grounded — recommendations cite specific file:line references, not generic best practices.

**Skill type:** Rigid — follow exactly, no shortcuts.

**Models:**
- Evaluator agent: Opus (synthesis/judgment work needs the best model)
- Orchestrator: runs on whatever model the session uses

**Announce at start:** "I'm using the assay skill to evaluate competing approaches."

**Name origin:** In metallurgy, an assay tests raw material to determine its quality and composition before committing it to the forge.

## Invocation API

```
/assay
  question: "How should the auth middleware handle token refresh?"
  context: { ... }
  decision_type: "architecture"
  approaches: [...]
  cascading_decisions: [...]
```

### Parameters

**`question`** (required) — The decision or question to evaluate. One clear sentence.

**`context`** (required) — Evidence for the evaluator to reason against. Accepts different shapes depending on the caller:

| Caller | Context Shape | Key Fields |
|---|---|---|
| `/design` | Recon brief + agent findings | `project_structure`, `existing_patterns`, `scope_boundaries`, `prior_art` |
| `/spec` | Recon brief + agent findings (autonomous) | `project_structure`, `existing_patterns`, `scope_boundaries`, `prior_art` |
| `/migrate` | Recon brief + migration analysis | `project_structure`, `migration_target`, `breaking_changes`, `blast_radius` |
| Generic caller | Freeform evidence | `description` (string) — unstructured context, lower confidence |

When context contains unrecognized keys, the evaluator treats them as additional evidence. When context is a bare string, treat as `{ "description": context }`.

**`decision_type`** (optional) — `architecture` | `strategy` | `diagnosis` | `optimization`. Auto-detected from the question if omitted. Defaults to `architecture` when ambiguous.

**`approaches`** (optional) — Array of `{ name, description }` candidates to evaluate. When omitted, the evaluator generates 2-4 candidates from the question and context.

**`cascading_decisions`** (optional) — Array of `{ decision, reasoning }` representing prior decisions. Treated as **hard constraints** — the evaluator cannot modify or challenge them. Conflicts are reported in `prior_decision_conflicts`.

## The Process

### Phase 1: Input Validation

1. Verify `question` is present and non-empty
2. Verify `context` is present (object or string)
3. If `decision_type` is provided, validate it's one of the 4 recognized values
4. If `approaches` is provided, verify it's an array with at least 2 entries, each having `name` and `description`

### Phase 2: Dispatch Evaluator

Dispatch a single Opus agent using `skills/assay/assay-evaluator-prompt.md`.

Fill template placeholders before writing the dispatch file:
- `{{QUESTION}}` — the decision question
- `{{CONTEXT}}` — the full context object/string
- `{{DECISION_TYPE}}` — the decision type (provided or "auto-detect")
- `{{APPROACHES}}` — the approaches array (or "Generate 2-4 candidates")
- `{{CASCADING_DECISIONS}}` — cascading decisions array (or "None")

### Phase 3: Validate Output

Parse the evaluator's response as JSON. Validate:
1. All required fields present: `decision_type`, `confidence`, `missing_information`, `recommended`, `alternatives`, `prior_decision_conflicts`
2. `recommended` has: `name`, `rationale`, `evidence`, `risks`, `kill_criteria`, `constraint_fit`
3. Each alternative has: `name`, `constraint_fit`, `pros`, `cons`, `would_recommend_if`
4. `constraint_fit` objects have: `pattern_alignment`, `scope_fit`, `reversibility`, `integration_risk`
5. `confidence` is one of: `high`, `medium`, `low`

**On validation failure:** Retry once with the validation errors as feedback. On second failure, return:
```json
{ "error": "Evaluator produced invalid output after retry", "raw_output": "..." }
```

### Phase 4: Return Report

Return the validated Assay Report to the caller.

## Decision Type Adaptation

The evaluator adapts scoring weights based on decision type:

| Type | Primary Weight | Secondary Weight |
|---|---|---|
| `architecture` | Reversibility, constraint fit | Long-term cost, extensibility |
| `strategy` | Risk, phasing | Blast radius, team capacity |
| `diagnosis` | Evidence strength, testability | Explanation coverage, simplicity |
| `optimization` | Measurable improvement | Disruption cost, reversibility |

## Output: Assay Report

```json
{
  "decision_type": "architecture",
  "confidence": "high",
  "missing_information": [],
  "recommended": {
    "name": "Event-driven via message bus",
    "rationale": "Aligns with existing src/events/bus.ts pattern...",
    "evidence": ["src/events/bus.ts:14 — existing event dispatch"],
    "risks": ["Adds async complexity to currently synchronous flow"],
    "kill_criteria": "Switch away if latency requirements exceed 50ms p99",
    "constraint_fit": {
      "pattern_alignment": "high",
      "scope_fit": "high",
      "reversibility": "two-way door",
      "integration_risk": "low"
    }
  },
  "alternatives": [
    {
      "name": "Direct service calls",
      "constraint_fit": {
        "pattern_alignment": "medium",
        "scope_fit": "high",
        "reversibility": "one-way door",
        "integration_risk": "medium"
      },
      "pros": ["Simpler mental model", "Synchronous"],
      "cons": ["Tight coupling", "Requires shared deployment"],
      "would_recommend_if": "Latency is critical or team prefers simplicity"
    }
  ],
  "prior_decision_conflicts": []
}
```

### Confidence Scoring

| Level | Criteria |
|---|---|
| `high` | One approach clearly dominates on all weighted dimensions |
| `medium` | Two viable options with trade-offs that depend on priority |
| `low` | Need more information — `missing_information` lists what would help |

### Evidence Grounding

Every recommendation must cite **specific evidence** from the context:
- File:line references from recon briefs
- Specific pattern names from the codebase
- Concrete constraint violations or alignments

"This is the industry standard approach" is NOT evidence. "This aligns with how `src/api/routes/users.ts` already handles it" IS evidence.

Without a recon brief, evidence cites the caller's context. Confidence scores skew lower.

### Kill Criteria

- **`kill_criteria`** on recommended approach: condition that would flip the recommendation
- **`would_recommend_if`** on each alternative: condition that would make it the recommendation

These make decisions revisitable without re-running the full analysis.

## Error Handling

| Failure | Behavior |
|---|---|
| Missing `question` or `context` | Return error immediately — no dispatch |
| Evaluator returns invalid JSON | Retry once with validation errors. Second failure returns `{ "error": ... }` |
| Evaluator timeout | Return `{ "error": "Evaluator timed out" }` |
| Invalid `decision_type` | Warn and default to `architecture` |
| `approaches` has fewer than 2 entries | Ignore provided approaches, let evaluator generate candidates |

## Integration

### Called by

| Skill | Decision Type | Context Source | Approaches |
|---|---|---|---|
| `/design` | `architecture` | Recon brief + cascading decisions | Evaluator generates |
| `/spec` | `architecture` | Recon brief + cascading decisions (autonomous — confidence routing) | Evaluator generates |
| `/migrate` | `strategy` | Recon brief + migration analysis | Evaluator generates |

**Not called by (investigated, not a fit):** `/debugging` (hypothesis evaluation uses quality-gate, not assay), `/prospector` (competing design evaluation is more sophisticated than assay for this use case). See #147 for rationale.

### Consumer Dispatch Examples

**From `/design`:**
```
/assay
  question: "How should components communicate in the new auth module?"
  context: { recon brief with project_structure, existing_patterns }
  decision_type: "architecture"
  cascading_decisions: [{ decision: "Using Redis for session store", reasoning: "..." }]
```

**From `/spec`:**
```
/assay
  question: "How should the auth middleware handle token refresh?"
  context: { recon brief + investigation findings }
  decision_type: "architecture"
  cascading_decisions: [{ decision: "Using Redis for session store", reasoning: "..." }]
```
Spec consumes assay output autonomously: high confidence = accept, medium = terminal alert, low = block alert.

**From `/migrate`:**
```
/assay
  question: "What migration strategy minimizes risk for the React 18→19 upgrade?"
  context: { recon brief + migration_target: "React 19", breaking_changes: [...] }
  decision_type: "strategy"
```

### Standalone Usage

```
/assay question: "Should we use PostgreSQL or SQLite for this project?"
  context: "Small team, <10K users, read-heavy workload, deployed on single server"
```

### Dispatches

- Evaluator agent (Opus) via `skills/assay/assay-evaluator-prompt.md`

### Does NOT

- Investigate the codebase (that's `/recon`)
- Challenge prior decisions (that's `/design`'s Challenger agent)
- Make the decision for the user (it recommends; the caller decides)
- Iterate or loop (one dispatch, one report)
