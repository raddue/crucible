---
ticket: "#158"
epic: "#158"
title: "Consensus code quality fixes from audit"
date: "2026-04-11"
source: "spec"
---

# Consensus Code Quality Fixes — Design Doc

## Current State Analysis

The `mcp-servers/crucible-consensus/` module implements multi-model consensus dispatch for high-stakes decisions. A repo-wide `/audit` run on 2026-04-10 surfaced 7 non-security code quality issues. Security issues from the same audit were already fixed in PR #112.

### Files in scope

| File | Lines | Role |
|------|-------|------|
| `aggregator.py` | 266 | Response aggregation, JSON parsing, consensus synthesis |
| `server.py` | 266 | MCP server, tool handlers, global state |
| `config.py` | 199 | Configuration loading/validation for consensus + external review |
| `providers.py` | 210 | Provider adapters (Anthropic, Google, OpenAI), parallel dispatch |

### Test coverage

4 test files exist with good coverage of aggregation, config loading, provider dispatch, and server tool handlers. Tests use `pytest` with `asyncio` mode.

## Target State

All 7 audit findings resolved with minimal API surface changes. Existing test assertions updated where status values change; new tests added for new validation logic and refactored interfaces.

## Key Decisions

### DEC-1: Greedy regex JSON parsing (aggregator.py:131)

**Finding:** `re.search(r"\{.*\}", raw, re.DOTALL)` matches from the first `{` to the last `}` in the entire string. This works when there's exactly one JSON object but will silently produce garbage if there's surrounding text with braces.

**Decision:** Replace with iterative `json.loads` attempts. Walk the string for `{` characters, attempt `json.loads` from each position. First successful parse with the expected keys wins. This is more robust than balanced-brace counting (which doesn't handle strings containing braces) and avoids pulling in a dependency.

**Confidence:** High. The code-block regex path already handles the most common case; this fallback path just needs to be less greedy.

**Alternatives considered:**
- Balanced-brace counter: fragile with braces inside JSON strings
- `json.JSONDecoder.raw_decode()`: cleaner API, handles the exact case. **Actually, use this** — it's stdlib, parses the first valid JSON object from a position, and returns how far it consumed. Better than manual walking.

**Revised decision:** Use `json.JSONDecoder().raw_decode()` to find the first valid JSON object. Scan for `{` positions and try `raw_decode` at each.

### DEC-2: Misleading "consensus" status (aggregator.py:191-192)

**Finding:** `status = "consensus"` means "all models responded", not "models agreed on findings". This is semantically misleading — consumers may interpret it as agreement.

**Decision:** Rename to `"complete"`. The three statuses become `"complete"` / `"partial"` / `"unavailable"`. This is a breaking change to the MCP tool response schema, but this server is internal to crucible with no external consumers.

**Confidence:** High. `ConsensusResult.status` field comment already documents the three values — just needs updating.

**Impact:** Test assertions checking `status == "consensus"` must change to `status == "complete"`. The `ConsensusResult` dataclass docstring must be updated.

### DEC-3: Anthropic-only aggregator fallback (aggregator.py:221-233)

**Finding:** If no `aggregator_provider` is passed, `aggregate()` searches for the first Anthropic model in config. If none exists, aggregation silently returns "unavailable". This hard-codes Anthropic as the only viable aggregator.

**Decision:** Use `create_provider()` from `providers.py` (which already has the `PROVIDER_REGISTRY`) to create an aggregator from the first available model in config, regardless of provider. Any configured model can serve as aggregator. Fall back to the first model, period — not the first Anthropic model.

**Confidence:** High. All three providers (Anthropic, Google, OpenAI) support the same `query(prompt, context)` interface. The aggregation prompt is provider-agnostic.

### DEC-4: Global mutable state (server.py:23-28)

**Finding:** Five module-level globals (`_config`, `_providers`, `_project_dir`, `_external_config`, `_external_providers`) with no cleanup on re-init. Calling `initialize()` twice leaks the old providers.

**Decision:** Wrap in a `ServerState` dataclass. Single module-level `_state: ServerState | None` variable. `initialize()` creates a fresh `ServerState` instance, replacing any prior one. Add `_get_state() -> ServerState | None` helper that returns `None` if uninitialized (NOT raises — current code gracefully returns "unavailable" responses when config is None, and this behavior must be preserved). Tool handlers call `_get_state()` and check for `None`.

**Confidence:** High. Straightforward encapsulation. No behavioral change — just structural.

### DEC-5: Unbounded timeout_seconds (config.py)

**Finding:** No validation that `timeout_seconds` is within a reasonable range. A config typo like `timeout_seconds: 99999` would cause requests to hang for 28 hours.

**Decision:** Validate `timeout_seconds` is between 1 and 600 (10 minutes) in both `load_config()` and `load_external_review_config()`. Raise `ConfigError` if out of range. The 600s upper bound matches typical LLM API timeout ceilings.

**Confidence:** High. Purely additive validation.

### DEC-6: Unused ModelConfig in dispatch_all tuple (providers.py:183)

**Finding:** `dispatch_all` takes `list[tuple[BaseProvider, ModelConfig]]` but only uses `ModelConfig` in the timeout error path to populate `provider` and `model_id` fields. Every provider already stores its config as `self.config`.

**Decision:** Change `dispatch_all` to take `list[BaseProvider]`. In the timeout error path, access `provider.config.provider` and `provider.config.model_id`. This requires adding a `config` attribute to the `BaseProvider` protocol.

**Confidence:** High. Clean abstraction fix. All three providers already have `self.config`.

**Impact:** All callers of `dispatch_all` (in `server.py`) must change from passing tuples to passing just providers. The `_providers` / `_external_providers` lists change type from `list[tuple]` to `list[BaseProvider]`.

### DEC-7: Dead ExternalReviewConfig.temperature (config.py:28-29)

**Finding:** `ExternalReviewConfig.temperature` is stored as a field but never read after construction. During `load_external_review_config()`, the local variable `section_temperature` is used as the per-model default, then stored into the field — but nothing ever reads `config.temperature` back.

**Decision:** Remove the `temperature` field from `ExternalReviewConfig`. The local `section_temperature` variable in `load_external_review_config()` serves its purpose during construction and doesn't need to persist.

**Confidence:** High. No production code reads `_external_config.temperature` after construction. Two tests assert on it (`test_external_review_one_model:274`, `test_external_review_temperature_precedence:415`) — these must be updated: remove the `config.temperature` assertions since the field no longer exists. The per-model temperature assertions (`config.models[N].temperature`) still work and verify the parsing logic.

### DEC-8: Add aggregator_error field to ConsensusResult (from innovate)

**Finding (innovate):** The `aggregate()` function has three distinct failure paths that all return `status="unavailable"` with no indication of *why*: no models configured, prompt template missing, and aggregator call failure. When DEC-3 changes the fallback to use any provider (not just Anthropic), new failure modes appear (e.g., aggregation prompt exceeds a provider's context window). Without distinguishing these, debugging silent aggregation failures becomes a guessing game.

**Decision:** Add an optional `error: str | None = None` field to `ConsensusResult`. Populate it in each of the three "return unavailable" paths in `aggregate()` with a specific reason. Also log the selected fallback provider at INFO level.

**Confidence:** High. One dataclass field, three string assignments, one log line. No behavioral change for consumers that don't read the field.

## Risk Areas

1. **DEC-2 (status rename)** is a breaking schema change. Confirmed consumers: `skills/quality-gate/SKILL.md` (line 245 checks `status: "consensus"`), `skills/consensus/SKILL.md` (lines 34, 115, 137 document the status). These must be updated or the quality-gate stagnation judge will fall through to single-model fallback.
2. **DEC-6 (dispatch_all signature)** touches the provider protocol, which affects all three provider classes and both call sites in `server.py`.
3. **DEC-4 (ServerState)** is the most invasive refactor — every tool handler touches global state. The `_get_state()` helper must NOT raise on uninitialized state — current code gracefully returns `"unavailable"` responses when `_config is None`. The helper should return `None` and callers should preserve the existing graceful degradation pattern.
4. **DEC-7 (temperature removal)** — two tests read `config.temperature`: `test_external_review_one_model` (line 274) and `test_external_review_temperature_precedence` (line 415). These must be updated/removed, not just the field.

## Acceptance Criteria

- [ ] `parse_aggregation_output` handles multi-object responses without false matches
- [ ] `ConsensusResult.status` uses `"complete"` / `"partial"` / `"unavailable"`
- [ ] `skills/quality-gate/SKILL.md` (line 245) updated from `"consensus"` to `"complete"`
- [ ] `skills/consensus/SKILL.md` (lines 34, 115, 137) updated from `"consensus"` to `"complete"`
- [ ] Aggregator fallback uses first available model, not first Anthropic model
- [ ] `ConsensusResult` has optional `error` field populated in all three failure paths
- [ ] Server state is encapsulated in a `ServerState` dataclass with graceful None-returning accessor
- [ ] `timeout_seconds` validated to [1, 600] range in both config loaders
- [ ] `dispatch_all` takes `list[BaseProvider]`, not `list[tuple[BaseProvider, ModelConfig]]`
- [ ] `ExternalReviewConfig.temperature` field removed
- [ ] `AnthropicProvider` import removed from `aggregator.py` (replaced by `create_provider`)
- [ ] All existing tests pass (updated for status rename, dispatch_all signature, ServerState, temperature removal)
- [ ] `tests/test_server.py` updated: `_make_consensus_result` default status, lines 87 and 408 assertions
- [ ] `tests/test_config.py` updated: `test_external_review_one_model` and `test_external_review_temperature_precedence` temperature assertions removed
- [ ] New tests cover timeout validation, robust JSON parsing, and aggregator_error field
