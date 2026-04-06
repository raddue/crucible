# External Model Review Implementation Plan

**Issue:** #144
**Branch:** feat/external-model-review
**Date:** 2026-04-06

## Task Overview

9 implementation tasks across 3 phases. Phase 1 builds the MCP infrastructure. Phase 2 integrates into review skills. Phase 3 updates documentation.

## Phase 1: MCP Server Infrastructure

### Task 0: Fix existing config parser and example

**Review-Tier:** 1

**Files:**
- `mcp-servers/crucible-consensus/config.py` (modify)
- `skills/consensus/consensus-config-example.yaml` (modify)
- `mcp-servers/crucible-consensus/tests/test_config.py` (modify)

**Approach:**
- Fix `load_config()` to handle nested `consensus:` key: `consensus_section = raw.get("consensus", raw)` then read fields from `consensus_section`
- Fix example config to use `model_id` instead of `model` (matching the `ModelConfig` dataclass field name)
- Update tests to verify both flat and nested YAML formats parse correctly
- This is a pre-existing bug, not new to #144, but must be fixed first

**Complexity:** Low
**Dependencies:** None

### Task 1: Add OpenAIProvider adapter

**Review-Tier:** 1

**Files:**
- `mcp-servers/crucible-consensus/providers.py` (modify)
- `mcp-servers/crucible-consensus/tests/test_providers.py` (modify)
- `mcp-servers/crucible-consensus/requirements.txt` (modify)

**Approach:**
- Add `OpenAIProvider` class following the `BaseProvider` protocol
- Constructor: reads API key from `os.environ.get(config.api_key_env)`. If `config.base_url_env` is set, reads base URL from `os.environ.get(config.base_url_env)` — `base_url_env` is an env var **name**, not a URL literal. If unset or env var empty, defaults to OpenAI's standard endpoint.
- Uses `openai.AsyncOpenAI(api_key=api_key, base_url=base_url)` client
- System message = context, user message = prompt
- `max_tokens=4096`, temperature from config
- Same error handling pattern as existing providers (catch exception, return in ModelResponse.error)
- Add to `PROVIDER_REGISTRY`: `"openai": OpenAIProvider`
- Add `openai>=1.0.0` to requirements.txt
- Tests: success path, API error path, base_url override via env var, factory creation via `create_provider()`

**Complexity:** Low
**Dependencies:** None (independent of Task 0 and Task 2)

### Task 2: Extend configuration for external_review

**Review-Tier:** 1

**Files:**
- `mcp-servers/crucible-consensus/config.py` (modify)
- `mcp-servers/crucible-consensus/tests/test_config.py` (modify)

**Approach:**
- Add `base_url_env: str | None = None` optional field to `ModelConfig` dataclass
- Add `ExternalReviewConfig` dataclass: `enabled: bool`, `models: list[ModelConfig]`, `timeout_seconds: int = 180`, `temperature: float = 0.3`, `skills: dict[str, bool]`
- Default skill toggles when `skills` key is absent from YAML: `{"code_review": True, "quality_gate": True, "red_team": True, "inquisitor": False}`
- Temperature precedence: per-model `ModelConfig.temperature` overrides section-level `ExternalReviewConfig.temperature`. Section-level is the default for models that don't specify their own.
- Add `load_external_review_config(project_dir) -> ExternalReviewConfig` function — reads the `external_review:` section from `.claude/consensus-config.yaml`. If the section is missing or the file doesn't exist, returns a disabled `ExternalReviewConfig(enabled=False, models=[])` — no error raised.
- Update `SUPPORTED_PROVIDERS` to include `"openai"`
- No `min_models` field — any number of configured models is valid (including 1)
- Validation: provider in supported set, API key env var set, base_url_env env var set if field is provided
- Tests: valid config with 1 model, valid config with 2 models, missing env var raises ConfigError, unknown provider raises ConfigError, disabled config, missing `external_review` section returns disabled config, missing config file returns disabled config, skill toggle defaults

**Complexity:** Low
**Dependencies:** None (independent of Task 0 and Task 1 — `load_external_review_config` is a new function reading a different YAML section, not modifying `load_config`)

### Task 3: Add `external_review` MCP tool

**Review-Tier:** 2

**Files:**
- `mcp-servers/crucible-consensus/server.py` (modify)
- `mcp-servers/crucible-consensus/tests/test_server.py` (modify)

**Approach:**
- Add `_external_config: ExternalReviewConfig | None` and `_external_providers: list` global state alongside existing `_config`/`_providers`
- Extend `initialize()`:
  - Wrap existing `load_config()` call in try/except ConfigError — if consensus config fails, set `_config = None` and log warning (don't crash). This allows external review to work even if consensus is not configured.
  - After consensus init, call `load_external_review_config()` for `_external_config` and build `_external_providers` list. This never raises — returns disabled config on missing file/section.
- Extend `consensus_query` schema: add optional `additional_responses` parameter (array of `{provider, model_id, content, latency_ms}`). When present, deserialize into `ModelResponse` objects and append to dispatch results before calling `aggregate()`. This lets external review responses feed into consensus synthesis on eligible rounds.
- Add `external_review` to `list_tools()` with schema: `prompt` (string, required), `context` (string, required), `metadata` (object, optional)
- Restructure `call_tool()` routing: replace `if name != "consensus_query": error` with if/elif/else routing for `consensus_query`, `external_review`, and unknown tools
- Add `external_review` handler:
  1. Early-exit if `_external_config` is None or disabled → return `{"status": "unavailable"}`
  2. Call `dispatch_all()` with `_external_providers` and `_external_config.timeout_seconds`
  3. Build response: `{ "status": ..., "models_queried": N, "models_responded": M, "reviews": [{ "provider": ..., "model_id": ..., "content": ..., "latency_ms": ..., "error": ... }] }`
  4. Status: all responded = "available", some responded = "partial", none = "unavailable"
  5. No aggregation — raw ModelResponse fields serialized directly
- Update `test_list_tools` to expect 2 tools (was asserting `len(tools) == 1`)
- Tests: success with 1 model, success with 2 models, disabled config returns unavailable, timeout returns partial, consensus config missing but external works, missing external_review section returns unavailable

**Complexity:** Medium
**Dependencies:** Task 1 (OpenAI provider in registry), Task 2 (ExternalReviewConfig + loader)

## Phase 2: Skill Integration

### Task 7a: Create external review prompt template

**Review-Tier:** 1

**Files:**
- `skills/shared/external-review-prompt.md` (new)

**Approach:**
- Provider-agnostic review instructions designed to work as a single user-message prompt (no system prompt dependency)
- Severity definitions matching Crucible's scale: Fatal (will break), Significant (real cost), Minor (style/preference)
- Structured output format with examples of well-formed findings
- Includes: role framing (independent code reviewer), what to review (code diff provided in context), how to report (structured findings with severity + description + location), severity calibration examples
- Works across all provider APIs (no special tokens, no tool-use assumptions)

**Complexity:** Low
**Dependencies:** None (can run in parallel with Phase 1 tasks)

### Task 4: Integrate external review into code-review skill

**Review-Tier:** 1

**Files:**
- `skills/code-review/SKILL.md` (modify)

**Approach:**
- Add section: "External Model Review (Optional)" after the existing review dispatch instructions
- Dispatch pattern: dispatch host code-reviewer as a background Agent first, then call `external_review` MCP tool with the same diff context and `external-review-prompt.md` content, then collect host results. This gives effective parallelism where background agents are available.
- If `external_review` tool is not available (MCP server not running), skip silently
- If external review returns "unavailable" (no config or disabled), skip silently
- Format output: host review section first, then each external review in its own `## External Review — {provider} ({model})` section
- Respect per-skill toggle: check `skills.code_review` in external review config

**Complexity:** Low
**Dependencies:** Task 3, Task 7a

### Task 5: Integrate external review into quality-gate skill

**Review-Tier:** 2

**Files:**
- `skills/quality-gate/SKILL.md` (modify)

**Approach:**
- Add section: "External Model Review (Optional)" — insert after the red-team dispatch instruction in the round loop, before the scoring calculation
- During red-team dispatch (every round), call `external_review` MCP tool with the same artifact context and `external-review-prompt.md`
- External findings are appended to round output for visibility
- External findings are added to the fix journal context (so fix agent sees them as additional perspective)
- **Critical invariant (INV-2):** External findings do NOT affect the scoring algorithm. The weighted score (Fatal=3, Significant=1) is computed from host red-team findings ONLY. External findings are informational context, not scoring inputs.
- **Consensus bridge (innovative addition):** On consensus-eligible rounds (1/4/7/10/13), run `external_review` first, then pass the external responses as `additional_responses` to `consensus_query`. The aggregator deduplicates findings across all models (consensus + external), surfaces cross-model disagreements, and tags external unique findings with proper confidence. On non-consensus rounds, external review runs independently as raw output.
- Respect per-skill toggle: check `skills.quality_gate` in external review config

**Complexity:** Medium (must preserve scoring invariant)
**Dependencies:** Task 3, Task 7a

### Task 6: Integrate external review into red-team and inquisitor skills

**Review-Tier:** 1

**Files:**
- `skills/red-team/SKILL.md` (modify)
- `skills/inquisitor/SKILL.md` (modify)

**Approach:**

**Red-team (direct mode only):**
- Add section: "External Model Review (Optional)" after the host red-team dispatch
- Call `external_review` MCP with same artifact + `external-review-prompt.md`
- Append external perspectives after host findings
- Only active in direct invocation mode. Detection: the red-team SKILL.md already has a dual-mode check ("When called by quality-gate: single-pass only"). The external review section specifies: "Skip this section when operating in single-pass mode (invoked by quality-gate)." Quality-gate handles its own external review integration (Task 5).
- Respect per-skill toggle: check `skills.red_team`

**Inquisitor:**
- Add section: "External Model Review (Optional)" per-dimension
- Per-dimension: after dispatching the host Opus agent, call `external_review` MCP with same diff + dimension-specific context
- Append external perspective per dimension
- Default: disabled in config (`inquisitor: false`) due to cost: `5 dimensions * N external models` API calls per run
- Respect per-skill toggle: check `skills.inquisitor`

**Complexity:** Low
**Dependencies:** Task 3, Task 7a

## Phase 3: Documentation

### Task 7b: Update config example and README

**Review-Tier:** 1

**Files:**
- `skills/consensus/consensus-config-example.yaml` (modify)
- `README.md` (modify)

**Approach:**

**Config example:**
- Add `external_review:` section with two examples: single-provider (Gemini only) and multi-provider (Gemini + OpenAI)
- Use `model_id` (not `model`) matching the fixed config parser
- Document per-skill toggles with defaults
- Document `base_url_env` for OpenAI-compatible endpoints
- Include inline comments explaining each field

**README:**
- Add "External Model Review" section under the skill catalog or features section
- Document: what it does, how to configure, relationship to consensus (#73), cost implications
- Note: works with 1 provider, works with any OpenAI-compatible endpoint

**Complexity:** Low
**Dependencies:** Tasks 4-6 (integration complete before documenting)

## Dependency Graph

```
Task 0 (Fix config parser)  ─┐
Task 1 (OpenAI provider)     ├──→ Task 3 (MCP tool)
Task 2 (Config extension)   ─┘        │
Task 7a (Prompt template)  ────────────┤
                                       ↓
                              Task 4 (code-review)
                              Task 5 (quality-gate)
                              Task 6 (red-team + inquisitor)
                                       │
                                       ↓
                              Task 7b (docs + config example)
```

**Wave 1:** Tasks 0, 1, 2, 7a (all independent — run in parallel)
**Wave 2:** Task 3 (depends on 0, 1, 2)
**Wave 3:** Tasks 4, 5, 6 (depend on 3 + 7a, run in parallel)
**Wave 4:** Task 7b (depends on 4, 5, 6)
