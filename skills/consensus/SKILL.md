---
name: consensus
description: Multi-model consensus for high-stakes quality decisions. Opt-in MCP-based system that dispatches prompts to multiple LLM providers in parallel and synthesizes their responses. Used by quality-gate (stagnation judge, periodic red-team) and design (Challenger).
---

## Overview

Multi-model consensus dispatches high-stakes decision prompts to multiple LLM providers in parallel via an MCP server, then synthesizes the responses. It surfaces blind spots that single-model review misses. Entirely opt-in — without configuration, all skills behave exactly as before.

The consensus system is not a replacement for existing skill logic. It is an amplifier applied at specific, high-leverage decision points where the cost of a missed defect or a wrong judgment is disproportionately high. Skills that integrate consensus call it at defined moments (e.g., the stagnation judge in quality-gate, the Challenger in design review) and treat its output as additional signal, not as an override.

## Tool Interface

### `consensus_query` (MCP tool)

Dispatches a prompt to all configured models in parallel, collects responses, and returns a synthesized result.

#### Parameters

| Parameter  | Type   | Required | Description |
|------------|--------|----------|-------------|
| `prompt`   | string | Yes      | The decision prompt to send to each model. Should be self-contained and unambiguous. |
| `context`  | string | Yes      | Supporting context (artifact content, conversation history, prior findings). Sent verbatim to each model alongside the prompt. |
| `mode`     | enum   | Yes      | One of `"review"`, `"verdict"`, or `"investigate"`. Controls how responses are aggregated. |
| `metadata` | object | No       | Optional metadata for traceability. Fields: `artifact_type` (string), `round_number` (int), `score_progression` (list of ints). |

#### Return Value

| Field              | Type   | Description |
|--------------------|--------|-------------|
| `status`           | enum   | `"consensus"` (all models responded), `"partial"` (some models responded, count >= min_models), `"unavailable"` (fewer than min_models responded or tool not configured). |
| `models_queried`   | int    | Number of models the query was dispatched to. |
| `models_responded` | int    | Number of models that returned a valid response within the timeout. |
| `synthesis`        | string | Aggregated result text, formatted according to the selected mode. |
| `agreements`       | list   | Findings or verdicts where 2+ models converged. |
| `disagreements`    | list   | Findings or verdicts where models explicitly contradicted each other. |
| `unique_findings`  | list   | Findings raised by exactly one model, with provenance. |
| `per_model`        | list   | Per-model detail. Each entry: `{ provider: string, model_id: string, content: string, responded: boolean }`. |

When `status` is `"unavailable"`, all list fields are empty and `synthesis` contains a short explanation (e.g., "Consensus unavailable: no models configured"). The caller should fall back to single-model behavior.

## Consensus Modes

### review

For adversarial review of artifacts (red-team rounds, design review, code review).

- Each model receives the prompt and context independently and reviews the artifact.
- The aggregator merges findings and deduplicates by semantic similarity (same root cause = one finding).
- **Confidence levels:**
  - **High** — 3 or more models independently identify the same finding.
  - **Medium** — 2 models independently identify the same finding.
  - **Low** — A single model identifies a finding with no corroboration.
- **Severity** uses Crucible's standard taxonomy: Fatal, Significant, Minor.
- Every finding carries **per-finding provenance** — the list of model IDs that surfaced it.
- Deduplicated findings are ordered by severity (Fatal first), then by confidence (High first).

### verdict

For binary or ternary decisions (stagnation judge, fix verification, pass/fail gates).

- Each model renders a verdict (e.g., `STAGNATION` or `PROGRESS`) along with structured reasoning.
- The aggregator reports the **verdict distribution** (e.g., `"STAGNATION: 3, PROGRESS: 1"`).
- **Confidence levels:**
  - **Unanimous** — All responding models agree.
  - **Supermajority** — 75%+ of responding models agree.
  - **Split** — No supermajority exists.
- Split decisions are flagged with `"requires_human_judgment": true` in the synthesis.
- The majority verdict is reported as the recommendation, but the caller decides how to act on splits.

### investigate

For design exploration (Challenger mode, architectural analysis).

- Each model investigates the prompt independently, surfacing risks, alternatives, or concerns.
- The aggregator merges findings and deduplicates by semantic similarity.
- Findings unique to a single model are marked with **provenance** and highlighted as potential blind-spot discoveries.
- Contradictory findings (where two models reach opposing conclusions about the same aspect) are flagged explicitly in the `disagreements` list with both positions and their reasoning.
- The synthesis groups results into: shared concerns, unique discoveries, and contradictions.

## Configuration

Consensus is configured via `.claude/consensus-config.yaml` in the project root. If this file is absent or `consensus.enabled` is `false`, all consensus calls return `status: "unavailable"` and skills fall back to single-model behavior with zero overhead.

### Schema

```yaml
consensus:
  enabled: true                # Master switch. Default: false.
  min_models: 2                # Minimum models that must respond for a valid result. Default: 2.
  timeout_seconds: 120         # Per-query timeout. Models that haven't responded are marked responded: false. Default: 120.
  models:
    - provider: anthropic      # Provider identifier. Shipped: "anthropic", "google". Planned: "openai", "deepseek".
      model: claude-sonnet-4-20250514  # Model identifier within the provider.
      api_key_env: ANTHROPIC_API_KEY   # Environment variable name holding the API key. NEVER a raw key.
      temperature: 0.6         # Sampling temperature for this model. Default: 0.6. Range: 0.0-1.0.
    - provider: google
      model: gemini-2.5-pro
      api_key_env: GOOGLE_API_KEY
      temperature: 0.6
  modes:
    review: true               # Enable consensus for review-mode calls. Default: true.
    verdict: true              # Enable consensus for verdict-mode calls. Default: true.
    investigate: true          # Enable consensus for investigate-mode calls. Default: true.
```

### Field Reference

| Field                       | Type    | Default | Description |
|-----------------------------|---------|---------|-------------|
| `consensus.enabled`         | boolean | `false` | Master switch. When false, all `consensus_query` calls immediately return `status: "unavailable"`. |
| `consensus.min_models`      | int     | `2`     | Minimum number of models that must respond for the result to be `"consensus"` or `"partial"`. If fewer respond, status is `"unavailable"`. Must be >= 2. |
| `consensus.timeout_seconds` | int     | `120`   | Maximum time (seconds) to wait for all models to respond. Models exceeding this are marked `responded: false`. Must be >= 10 and <= 600. |
| `consensus.models`          | list    | `[]`    | List of model configurations. At least `min_models` entries required. |
| `consensus.models[].provider`    | string | —  | Provider identifier. Must be one of the shipped providers (`anthropic`, `google`) or a planned provider once available. |
| `consensus.models[].model`       | string | —  | Model identifier recognized by the provider's API. |
| `consensus.models[].api_key_env` | string | —  | Name of the environment variable containing the API key. The MCP server reads the key from the environment at runtime. Keys are NEVER stored in config files. |
| `consensus.models[].temperature` | float  | `0.6` | Sampling temperature. Lower values produce more deterministic responses. |
| `consensus.modes.review`     | boolean | `true`  | Whether `review` mode calls are dispatched to consensus. When false, review-mode calls return `"unavailable"`. |
| `consensus.modes.verdict`    | boolean | `true`  | Whether `verdict` mode calls are dispatched to consensus. |
| `consensus.modes.investigate`| boolean | `true`  | Whether `investigate` mode calls are dispatched to consensus. |

### Validation Rules

- If `consensus.enabled` is `true` but `consensus.models` has fewer entries than `min_models`, the MCP server logs a warning and treats consensus as unavailable.
- If a referenced `api_key_env` variable is not set in the environment, that model is skipped. If the remaining count drops below `min_models`, status is `"unavailable"`.
- Duplicate provider+model combinations are rejected at config load time.
- The `temperature` field is clamped to [0.0, 1.0].

## Graceful Degradation

The consensus system is designed to never break existing workflows. Degradation follows a strict hierarchy:

1. **Consensus available** — All configured models respond within the timeout. `status: "consensus"`. Full multi-model synthesis is returned to the calling skill.

2. **Partially available** — Some models fail or time out, but the number of successful responses is >= `min_models`. `status: "partial"`. Aggregation proceeds with available responses. The `models_queried` and `models_responded` fields indicate the gap.

3. **Unavailable (configuration)** — No config file, `enabled: false`, no models configured, or no API keys in environment. `status: "unavailable"`. The calling skill receives an immediate response and proceeds with its existing single-model logic. Zero overhead, zero delay.

4. **MCP server not running** — The `consensus_query` tool is not present in the tool list. Skills that integrate consensus check for tool availability before attempting calls. If the tool is absent, the consensus step is skipped entirely. No errors, no retries.

In all cases, the calling skill's core logic is self-contained. Consensus is additive signal, never a gate.

## Cost Estimation

Consensus multiplies API costs by the number of models queried. The following table estimates cost multipliers relative to a single-model baseline, assuming prompts of roughly equal token count across models.

### Per-Query Cost Multiplier

| Models Configured | Multiplier |
|-------------------|------------|
| 2                 | 2x         |
| 3                 | 3x         |
| 4                 | 4x         |

### Estimated Impact on Quality Gate Runs

Quality gate integrates consensus at two points: the stagnation judge (verdict mode, every round) and periodic red-team review (review mode, periodic). The table below shows total additional API calls from consensus across different run lengths, assuming periodic red-team consensus fires on rounds 1, 4, 7, 10 (every 3rd round starting from round 1).

| Run Length | Stagnation Verdicts | Periodic Red-Team Reviews | Total Consensus Calls | With 2 Models | With 3 Models | With 4 Models |
|------------|---------------------|---------------------------|-----------------------|----------------|----------------|----------------|
| 5 rounds   | 5                   | 2 (rounds 1, 4)          | 7                     | 14 API calls   | 21 API calls   | 28 API calls   |
| 10 rounds  | 10                  | 4 (rounds 1, 4, 7, 10)   | 14                    | 28 API calls   | 42 API calls   | 56 API calls   |

Periodic application (rather than every-round) keeps cost manageable. A 10-round quality gate run with 2 models adds 28 API calls total — significant but bounded. Teams should start with 2 models and add more only after validating the signal-to-cost ratio.

### Cost Management Recommendations

- Start with 2 models to validate consensus value before scaling.
- Use mode-level toggles (`consensus.modes.verdict: false`) to disable consensus for lower-value decision points.
- Monitor `models_responded` in results to detect models that consistently time out (wasted cost).

## Red Flags

### Never

- **Use consensus on every red-team round.** Consensus is for periodic checkpoints (e.g., rounds 1, 4, 7), not every iteration. Every-round consensus is wasteful and slows feedback loops.
- **Treat single-model unique findings as less important than multi-model agreements.** Unique findings are often the most valuable — they represent blind spots. Confidence level indicates corroboration, not importance.
- **Pass consensus provenance to the next red-team reviewer.** This creates anchoring bias. The next reviewer must form independent judgments. Provenance is for the aggregator and the human operator, not for downstream reviewers.
- **Store API keys in config files.** Keys are referenced by environment variable name only. The `api_key_env` field holds the variable name, never the key itself.
- **Log prompt content or API keys.** The MCP server must not persist prompt text, context, or API credentials to disk or stdout. Structured metadata (model IDs, response times, token counts) may be logged.

### Always

- **Fall back gracefully when consensus is unavailable.** Every skill that calls `consensus_query` must have a code path that works without it. Consensus is additive, never required.
- **Include provenance metadata in consensus results.** Every finding and verdict must trace back to the model(s) that produced it. Provenance enables debugging, trust calibration, and cost attribution.
- **Check tool availability before attempting consensus calls.** Skills must verify that the `consensus_query` tool exists in the current tool list before calling it. If absent, skip the consensus step silently.
