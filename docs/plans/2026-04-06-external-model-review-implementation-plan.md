# External Model Review Implementation Plan

**Issue:** #144
**Branch:** feat/external-model-review
**Date:** 2026-04-06

## Task Overview

8 implementation tasks across 3 phases. Phase 1 builds the MCP infrastructure (config fix + provider + tool + config extension). Phase 2 integrates into review skills. Phase 3 adds the review prompt template and documentation.

## Phase 1: MCP Server Infrastructure

### Task 0: Fix existing config parser and example

**Files:**
- `mcp-servers/crucible-consensus/config.py` (modify)
- `skills/consensus/consensus-config-example.yaml` (modify)
- `mcp-servers/crucible-consensus/tests/test_config.py` (modify)

**Approach:**
- Fix `load_config()` to handle nested `consensus:` key: `consensus_section = raw.get("consensus", raw)` then read fields from `consensus_section`
- Fix example config to use `model_id` instead of `model` (matching the `ModelConfig` dataclass)
- Update tests to use both flat and nested YAML formats
- This is a pre-existing bug, not new to #144, but must be fixed first

**Complexity:** Low
**Dependencies:** None

### Task 1: Add OpenAIProvider adapter

**Files:**
- `mcp-servers/crucible-consensus/providers.py` (modify)
- `mcp-servers/crucible-consensus/tests/test_providers.py` (modify)
- `mcp-servers/crucible-consensus/requirements.txt` (modify)

**Approach:**
- Add `OpenAIProvider` class following the `BaseProvider` protocol
- Uses `openai.AsyncOpenAI` client with optional `base_url` from config
- System message = context, user message = prompt
- `max_tokens=4096`, temperature from config
- Same error handling pattern as existing providers (catch + return in ModelResponse)
- Add to `PROVIDER_REGISTRY`: `"openai": OpenAIProvider`
- Add `openai` to requirements.txt
- Tests: success, error, base_url override, factory creation

**Complexity:** Low
**Dependencies:** None

### Task 2: Extend configuration for external_review

**Files:**
- `mcp-servers/crucible-consensus/config.py` (modify)
- `mcp-servers/crucible-consensus/tests/test_config.py` (modify)

**Approach:**
- Add `ExternalReviewConfig` dataclass: `enabled`, `models` (list of ModelConfig), `timeout_seconds`, `temperature`, `skills` (dict of skill toggles)
- Add `base_url_env` optional field to `ModelConfig` (for OpenAI-compatible endpoints)
- Add `load_external_review_config(project_dir)` function — reads the `external_review:` section from the same `.claude/consensus-config.yaml`
- Update `SUPPORTED_PROVIDERS` to include `"openai"`
- No `min_models` field — any number of configured models is valid (including 1)
- Validation: provider in supported set, API key env var set, base_url_env set if provided
- Tests: valid config, single model, missing env var, unknown provider, disabled, missing section (returns disabled config)

**Complexity:** Low
**Dependencies:** Task 0 (config parser must handle nested structure first). Independent of Task 1 — `SUPPORTED_PROVIDERS` is a string set in config.py, `PROVIDER_REGISTRY` is a class dict in providers.py.

### Task 3: Add `external_review` MCP tool

**Files:**
- `mcp-servers/crucible-consensus/server.py` (modify)
- `mcp-servers/crucible-consensus/tests/test_server.py` (modify)

**Approach:**
- Add `_external_config` and `_external_providers` global state alongside existing `_config`/`_providers`
- Extend `initialize()` to also load external review config and create providers
- Add `external_review` to `list_tools()` with schema: prompt (str), context (str), metadata (obj, optional)
- Extend `initialize()` to load external review config into `_external_config` and build `_external_providers` list separately from `_providers`
- Add handler in `call_tool()` for `external_review`:
  1. Early-exit if config not loaded or disabled
  2. Call `dispatch_all()` with `_external_providers` (reuse existing function)
  3. Return JSON: `{ status, models_queried, models_responded, reviews: [{ provider, model_id, content, latency_ms, error }] }`
  4. No aggregation step — raw ModelResponse objects serialized
- Status logic: all responded = "available", some responded = "partial", none = "unavailable"
- New result structure: inline dict construction in handler (no new dataclass needed — the shape is simpler than ConsensusResult)
- Tests: success with 1 model, success with 2 models, disabled config, timeout, partial response, missing external_review section (returns disabled)

**Complexity:** Medium
**Dependencies:** Task 0, Task 1, Task 2

## Phase 2: Skill Integration

### Task 4: Integrate external review into code-review skill

**Files:**
- `skills/code-review/SKILL.md` (modify)

**Approach:**
- Add section: "External Model Review (Optional)"
- After dispatching the host code-reviewer subagent, check if `external_review` MCP tool is available
- If available, call `external_review` with the same diff context and `external-review-prompt.md` content
- Format output: host review section first, then each external review in its own `## External Review — {provider} ({model})` section
- If external review returns "unavailable" or times out, omit silently (no error shown)
- Respect per-skill toggle: check `external_review.skills.code_review` config

**Complexity:** Low
**Dependencies:** Task 3

### Task 5: Integrate external review into quality-gate skill

**Files:**
- `skills/quality-gate/SKILL.md` (modify)

**Approach:**
- Add section: "External Model Review (Optional)"
- During red-team dispatch (every round, not just consensus-eligible rounds), fire `external_review` in parallel
- External findings are appended to round output for visibility
- External findings are added to the fix journal context (so fix agent sees them) but do NOT affect the scoring algorithm (Fatal/Significant weighted score stays host-only)
- If consensus is also active on an eligible round, both consensus and external review run — they serve different purposes (consensus synthesizes, external review provides raw perspectives)
- Respect per-skill toggle

**Complexity:** Medium (must be careful not to affect scoring)
**Dependencies:** Task 3

### Task 6: Integrate external review into red-team and inquisitor skills

**Files:**
- `skills/red-team/SKILL.md` (modify)
- `skills/inquisitor/SKILL.md` (modify)

**Approach:**

**Red-team (direct mode only):**
- After dispatching the host red-team subagent, call `external_review` in parallel
- Append external perspectives after host findings
- Only in direct invocation mode, not when called by quality-gate (quality-gate handles its own external review integration)
- Respect per-skill toggle

**Inquisitor:**
- Per-dimension: alongside the host Opus dispatch, fire `external_review` with the same diff + dimension-specific context
- Append external perspective per dimension
- Default: disabled in config (`inquisitor: false`) due to 5x cost multiplier
- Respect per-skill toggle

**Complexity:** Low
**Dependencies:** Task 3

## Phase 3: Prompt Template + Documentation

### Task 7: Create external review prompt template and update config example

**Files:**
- `skills/shared/external-review-prompt.md` (new)
- `skills/consensus/consensus-config-example.yaml` (modify)
- `README.md` (modify)

**Approach:**

**Prompt template (`external-review-prompt.md`):**
- Provider-agnostic review instructions
- Severity definitions matching Crucible's scale (Fatal/Significant/Minor)
- Structured output format with examples
- Works as a single user-message prompt (no system prompt dependency)
- Includes: role framing, what to review, how to report findings, severity calibration

**Config example:**
- Add `external_review:` section with examples for single-provider (Gemini only) and multi-provider configurations
- Document per-skill toggles
- Document `base_url_env` for OpenAI-compatible endpoints

**README:**
- Add "External Model Review" section under the skill catalog
- Document configuration steps
- Note relationship to consensus (#73)

**Complexity:** Low
**Dependencies:** Tasks 1-6

## Dependency Graph

```
Task 0 (Fix config parser)
  ↓
Task 1 (OpenAI provider) ← independent of Task 2
Task 2 (Config extension) ← independent of Task 1, depends on Task 0
  ↓
Task 3 (MCP tool) ← depends on Tasks 0, 1, 2
  ↓
Task 4 (code-review integration) ← depends on Task 3
Task 5 (quality-gate integration) ← depends on Task 3
Task 6 (red-team + inquisitor integration) ← depends on Task 3
  ↓
Task 7 (prompt template + docs) ← depends on Tasks 4-6
```

Tasks 1 and 2 can run in parallel after Task 0.
Tasks 4, 5, 6 can run in parallel after Task 3.
