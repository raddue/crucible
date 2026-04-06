# External Model Review Design

**Issue:** #144
**Branch:** feat/external-model-review
**Date:** 2026-04-06

## Overview

Add provider-agnostic external model review to Crucible's review pipeline. Any user with one or more external LLM API keys can get independent code review perspectives alongside their host model's review. Works with a single external provider (the common case) or many.

**Key distinction from #73 (consensus):** Consensus synthesizes N opinions into one verdict. External review presents independent opinions side-by-side. Different orchestration, same provider infrastructure.

**Invocation:** Automatic when external reviewers are configured. No explicit skill activation — the review skills detect configuration and dispatch external reviews in parallel with host reviews.

## Current State Analysis

### Existing Infrastructure

The `crucible-consensus` MCP server (`mcp-servers/crucible-consensus/`) provides:
- **Provider adapters:** `AnthropicProvider`, `GoogleProvider` — both fully implemented with async `query(prompt, context) -> ModelResponse`
- **Parallel dispatch:** `dispatch_all()` fires all providers concurrently with per-provider timeout
- **Configuration:** `.claude/consensus-config.yaml` with model list, API key env vars, timeout, temperature
- **MCP tool:** `consensus_query` with modes: review, verdict, investigate
- **Aggregation:** Mode-specific prompt templates that synthesize responses into consensus findings

### Existing Bugs to Fix

1. **Config parser/example mismatch:** `load_config()` reads flat YAML (`raw.get("models", [])`) but the example config nests everything under `consensus:`. The parser also expects `model_id` but the example uses `model`. These must be fixed as part of this work — the config parser needs to handle the nested structure AND we standardize on `model_id` in YAML (matching the code).

### What's Missing

1. **No "passthrough" mode** — every query goes through aggregation. External review needs raw per-model responses.
2. **No OpenAI-compatible provider** — only Anthropic and Google adapters exist.
3. **No integration in code-review, red-team, or inquisitor dispatches** — consensus only wires into quality-gate (rounds 1/4/7/10/13) and design (challenger).
4. **`min_models` defaults to 2** — blocks single-provider use. External review needs no minimum.
5. **Config is consensus-specific** — needs an `external_review` section.
6. **No `_external_providers` state** — `server.py` only initializes one provider list. External review needs its own providers built from its own config section.

## Design Decisions

### Decision 1: Extend Existing MCP Server vs. New Server

**Choice: Extend the existing `crucible-consensus` MCP server** with a new `external_review` tool.

**Rationale:** The provider infrastructure (adapters, dispatch, config loading, error handling, tests) is already built and tested. Building a separate server duplicates all of this. The two tools (`consensus_query` and `external_review`) share providers but differ in post-dispatch handling: consensus aggregates, external review passes through.

**Confidence: High.** The provider layer is cleanly separated from the aggregation layer. Adding a second tool that skips aggregation is architecturally natural.

### Decision 2: Configuration Location

**Choice: Extend `.claude/consensus-config.yaml` with an `external_review` section.** Also fix the existing config parser to handle the nested `consensus:` structure and standardize on `model_id` in YAML (matching the `ModelConfig` dataclass).

```yaml
consensus:
  enabled: true
  min_models: 2
  models:
    - provider: anthropic
      model_id: claude-sonnet-4-20250514
      api_key_env: ANTHROPIC_API_KEY
    - provider: google
      model_id: gemini-2.5-pro
      api_key_env: GOOGLE_API_KEY

external_review:
  enabled: true
  models:
    - provider: google
      model_id: gemini-2.5-pro
      api_key_env: GOOGLE_API_KEY
    - provider: openai
      model_id: o3
      api_key_env: OPENAI_API_KEY
      base_url_env: OPENAI_BASE_URL  # optional, for compatible endpoints
  timeout_seconds: 180
  temperature: 0.3
  skills:
    code_review: true
    quality_gate: true
    red_team: true
    inquisitor: false  # opt-in due to 5 * N cost (N = number of external models)
```

**Pre-requisite fix:** `load_config()` currently reads flat YAML (`raw.get("models")`) but the documented config nests under `consensus:`. The parser must be updated to read `raw.get("consensus", raw)` as a fallback chain (support both flat and nested). The example config must use `model_id` not `model`.

**Rationale:** A user may want different models for consensus (high-diversity, temperature 0.6) vs. external review (focused, temperature 0.3). Separate sections allow independent configuration while sharing the same config file and provider registry.

**Confidence: High.** Single file, two sections, independent model lists.

### Decision 3: Provider-Agnostic via OpenAI-Compatible API

**Choice: Add `OpenAIProvider` that works with any OpenAI-compatible endpoint** (OpenAI, Azure OpenAI, Codex, local models via ollama/vllm, etc.)

```yaml
- provider: openai
  model_id: o3
  api_key_env: OPENAI_API_KEY
  base_url_env: OPENAI_BASE_URL  # optional, defaults to api.openai.com
```

**Rationale:** The OpenAI chat completions API is the de facto standard. Supporting it covers OpenAI, Azure, Codex CLI models, local inference servers, and any future provider that implements the same API. One adapter covers many providers.

**Confidence: High.** Industry-standard API, well-documented, widely adopted.

### Decision 4: Output Format — Raw Responses, Not Synthesized

**Choice: Return individual model responses as-is, formatted with provider attribution.**

The calling skill (code-review, quality-gate, etc.) formats each response into a labeled section:

```
## External Review — Gemini (2.5 Pro)
[Gemini's full review response]

## External Review — GPT (o3)
[GPT's full review response]
```

**Rationale:** The whole point of external review is independent perspectives. Synthesis collapses the value. The host model can optionally scan external reviews and call out overlapping findings, but the raw reviews are always shown.

**Confidence: High.** This is the explicit requirement from the issue.

### Decision 5: Integration Pattern — Sequential MCP Call Before Host Dispatch

**Choice: Skills call the `external_review` MCP tool first, then dispatch the host reviewer.** The MCP call is fast (fires async API requests, returns raw responses). The host reviewer dispatch follows. Both results are collected and formatted.

**Consensus bridge exception:** On consensus-eligible quality-gate rounds (1/4/7/10/13), external_review runs *before* consensus_query so its results can be injected via the `additional_responses` parameter. This creates a sequential dependency (external must complete before consensus dispatch). The latency tradeoff is accepted because cross-model synthesis on high-stakes rounds is more valuable than the 10-30s saved by parallelism. On non-consensus rounds, the standard parallel pattern applies. See INV-1 in the contract for the explicit carve-out.

**Why not parallel:** Claude Code's tool-use model executes tool calls within a turn. While multiple tool calls can be batched in a single response, an MCP tool call and an Agent/Task dispatch cannot truly race. The practical pattern is: call `external_review` MCP (which internally dispatches all providers in parallel via `asyncio.gather`), collect results, then dispatch host reviewer. The external API calls happen during the MCP tool execution, so total wall-clock overhead is `max(external_model_latencies)` — typically 10-30 seconds.

**Alternative:** If the orchestrator skill uses the Agent tool for host review, it could dispatch the host agent first (which runs in background), then call the MCP tool, then collect both. This gives effective parallelism. Skills should prefer this pattern where Agent Teams or background agents are available.

**Integration points (4 skills):**

| Skill | Where | How |
|-------|-------|-----|
| **code-review** | Before/alongside host reviewer dispatch | MCP call with same diff + review prompt |
| **quality-gate** | Red-team rounds (all rounds) | MCP call alongside red-team dispatch |
| **red-team** | Direct invocation mode | MCP call with same artifact + attack prompt |
| **inquisitor** | Per-dimension dispatch | MCP call per dimension with same diff (opt-in only) |

**Non-blocking guarantee:** If the MCP call fails or times out, the skill proceeds with host-only review. External review failure never blocks progress.

**Confidence: Medium.** The sequential overhead is real but bounded (10-30s). Background agent pattern can achieve true parallelism where supported.

### Decision 6: Review Prompt Adaptation

**Choice: Use a single `external-review-prompt.md` template** that is provider-agnostic. The prompt instructs the model to produce findings in a standardized severity format (Fatal/Significant/Minor with descriptions). The MCP server handles API format differences (system prompt support, message structure).

**Rationale:** Different models have different strengths, but asking them all to use the same output format makes findings comparable without synthesis. The prompt is the same; the API adapter handles the plumbing.

**Confidence: Medium.** Some models may not follow the severity format well.

### Decision 8: Bridge External Review into Consensus on Eligible Rounds

**Choice: On consensus-eligible quality-gate rounds (1/4/7/10/13), feed external review responses into `consensus_query` as additional model inputs** instead of running them as a disconnected sidebar.

Add an optional `additional_responses` parameter to the `consensus_query` MCP tool. When present, these responses are appended to the dispatch results before aggregation. The aggregator's `build_aggregation_input()` already iterates over a `list[ModelResponse]` — concat the lists. External models become first-class consensus participants on high-stakes rounds.

On non-consensus rounds, external review runs independently as raw per-model output (no change).

**Rationale:** Without this, consensus-eligible rounds produce two disconnected outputs: a synthesized consensus verdict (blind to external models) and raw external reviews (blind to consensus synthesis). This is architectural waste — the same artifact reviewed twice with no cross-pollination. Bridging gives:
- Deduplication of overlapping findings across all models
- Cross-model disagreements surfaced explicitly (e.g., Gemini vs Claude on severity)
- External unique findings get proper confidence tagging via the aggregator
- Zero changes to `aggregator.py` — it already handles N models

**Cost:** One optional parameter on `consensus_query` schema, ~10 lines in `server.py`, ~5 lines per skill integration on consensus-eligible rounds.

**Confidence: High.** The aggregator is provably model-count-agnostic. This is additive (optional parameter, backward compatible). Mitigation: the prompt includes explicit examples, and the calling skill treats external reviews as "best effort" — malformed output is shown as-is with a warning rather than discarded.

### Decision 7: Single Provider is First-Class

**Choice: No minimum model count for external review.** One configured external model triggers the feature. Zero configured = today's behavior.

```yaml
external_review:
  enabled: true
  models:
    - provider: google
      model_id: gemini-2.5-pro
      api_key_env: GOOGLE_API_KEY
```

This is sufficient. No `min_models` field in the `external_review` section — it's always "use whatever is configured."

**Confidence: High.** Explicit requirement from the issue.

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────┐
│  Calling Skill (code-review, quality-gate,  │
│  red-team, inquisitor)                       │
├─────────────────────────────────────────────┤
│  1. Dispatch host review (Task/Agent tool)   │
│  2. In parallel: call external_review MCP    │
│  3. Collect both, format output              │
└────────────┬───────────────┬────────────────┘
             │               │
     Host review      MCP: external_review
     (normal flow)          │
                    ┌───────▼────────┐
                    │ crucible-       │
                    │ consensus MCP   │
                    │ server          │
                    ├────────────────┤
                    │ dispatch_all() │
                    │ (parallel)     │
                    └──┬──────┬──┬──┘
                       │      │  │
                    Gemini  GPT  ...
                       │      │  │
                    ┌──▼──────▼──▼──┐
                    │ Raw responses  │
                    │ (no aggregation)│
                    └────────────────┘
```

### New MCP Tool: `external_review`

Added to `server.py` alongside existing `consensus_query`:

```python
# Tool: external_review
# Input:
#   prompt: str       — Review prompt (same as host reviewer gets)
#   context: str      — Supporting context (diff, requirements, etc.)
#   metadata: dict    — Traceability (skill, round, phase)
# Output:
#   status: "available" | "partial" | "unavailable"
#   models_queried: int
#   models_responded: int
#   reviews: [
#     { provider, model_id, content, latency_ms, error }
#   ]
```

Key difference from `consensus_query`: no aggregation step. Raw `ModelResponse` objects serialized directly.

**Server initialization changes:** `initialize()` must build two separate provider lists:
- `_providers` — from `consensus.models` (existing)
- `_external_providers` — from `external_review.models` (new)

Each list is constructed independently from its config section. A model can appear in both lists (e.g., Gemini used for both consensus and external review). The `external_review` tool uses `_external_providers`; `consensus_query` uses `_providers`. Provider config changes require server restart (same as today).

### Provider Adapter: OpenAIProvider

Follows the same `BaseProvider` protocol:

```python
class OpenAIProvider:
    async def query(self, prompt: str, context: str) -> ModelResponse:
        # Uses openai.AsyncOpenAI client
        # Sends context as system message, prompt as user message
        # Supports base_url override for compatible endpoints
```

### Config Extension

`config.py` gains:
- `ExternalReviewConfig` dataclass (enabled, models, timeout_seconds, temperature)
- `load_external_review_config()` function
- `SUPPORTED_PROVIDERS` updated to include `"openai"`

### Review Prompt Template

`skills/shared/external-review-prompt.md` — a single provider-agnostic template used for all external review dispatches. Contains:
- Role framing (independent code reviewer)
- Severity definitions (Fatal/Significant/Minor — matching Crucible's existing scale)
- Output format instructions (structured findings)
- Examples of well-formed findings

This template is read by the calling skill and passed as the `prompt` parameter to the `external_review` MCP tool.

## Integration Detail Per Skill

### code-review

Current flow:
1. Dispatch code-reviewer subagent with diff + requirements
2. Collect findings, format output

New flow:
1. Dispatch code-reviewer subagent with diff + requirements
2. **In parallel:** Call `external_review` MCP tool with same diff + `external-review-prompt.md`
3. Collect host findings
4. Collect external reviews (if available, with timeout tolerance)
5. Format output: host review first, then each external review in its own section

**SKILL.md change:** ~15-20 lines added to the review dispatch section.

### quality-gate

Current flow (red-team rounds):
- Dispatch red-team subagent (or consensus_query on eligible rounds)
- Collect findings, score, iterate

New flow:
- Dispatch red-team subagent (or consensus on eligible rounds)
- **In parallel:** Call `external_review` MCP tool with same artifact
- Collect host findings (used for scoring as today)
- Append external findings to the round's output (informational — external findings do NOT affect the scoring algorithm, only the fix journal receives them for context)

**Rationale for not scoring external findings:** The quality gate's stagnation detection is calibrated to the host model's severity scale. Mixing in external model severities would destabilize the scoring. External findings inform the fix agent (via fix journal) but don't drive the loop.

### red-team (direct mode)

Current flow:
- Dispatch red-team subagent with artifact
- Collect steel-man-then-kill findings

New flow:
- Dispatch red-team subagent
- **In parallel:** Call `external_review` MCP tool
- Present both

### inquisitor

Current flow:
- 5 parallel dimension dispatches (all Opus)
- Each produces attack vectors + tests

New flow:
- 5 parallel dimension dispatches
- **In parallel with each dimension:** Call `external_review` MCP tool with same diff + dimension-specific framing
- Per-dimension output includes external perspective alongside host findings

**Note:** This is the highest-cost integration. Cost formula: `5 dimensions * N external models` API calls per inquisitor run. With 2 external models, that's 10 API calls. If quality-gate runs inquisitor across multiple rounds, costs compound further. Defaults to disabled via config:

```yaml
external_review:
  skills:
    code_review: true     # 1 * N calls per review
    quality_gate: true    # 1 * N calls per red-team round
    red_team: true        # 1 * N calls per invocation
    inquisitor: false     # 5 * N calls per run — opt-in only
```

## Risk Areas

1. **Prompt format incompatibility** — Some models handle system prompts differently (Gemini concatenates, OpenAI separates). The provider adapters handle this, but output quality may vary. Mitigation: the `external-review-prompt.md` template is designed to work as a single user-message prompt (no system prompt dependency).

2. **Output format inconsistency** — External models may not follow the severity format. Mitigation: treat external reviews as "best effort" — show raw output with provider attribution. Don't parse or score it.

3. **Cost surprise** — External reviews add API calls. Mitigation: per-skill toggle in config, clear documentation of cost implications.

4. **Latency** — External API calls may be slow. Mitigation: non-blocking parallel dispatch with configurable timeout. Host review is never delayed.

5. **API key management** — Environment variables only (never in config files). This matches the existing consensus config pattern.

6. **Input size** — Large diffs can exceed external model context windows. Mitigation: the review prompt template includes a note that the context may be truncated. The MCP server does not truncate (it can't know provider limits); the provider's API returns an error which is captured in `ModelResponse.error`. The calling skill sees the error and proceeds with host-only review.

7. **Temperature precedence** — Per-model `temperature` in the config overrides the section-level `temperature`. Section-level is the default for models that don't specify their own. This matches the existing `ModelConfig.temperature` default pattern.

## Acceptance Criteria

1. A user with a single Gemini API key can configure external review and see Gemini's code review alongside their host model's review
2. A user with zero external providers configured sees no change in behavior
3. External review failures (timeout, API error, malformed response) do not block or slow the host review
4. External reviews are presented with clear provider attribution
5. The `external_review` MCP tool returns raw per-model responses without aggregation
6. OpenAI-compatible endpoints are supported (OpenAI, Azure, local inference)
7. Per-skill toggles allow disabling external review for cost-sensitive skills (e.g., inquisitor)
8. Config validation rejects unknown providers and missing API key env vars
