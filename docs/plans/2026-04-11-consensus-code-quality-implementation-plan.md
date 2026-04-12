---
ticket: "#158"
epic: "#158"
title: "Consensus code quality fixes from audit"
date: "2026-04-11"
source: "spec"
---

# Consensus Code Quality Fixes — Implementation Plan

## Task Order

Tasks are ordered by dependency. Tasks 1-3 are independent leaf changes. Task 4 depends on Task 3 (dispatch_all refactor feeds into ServerState). Tasks 5-7 are independent test/cleanup tasks.

## Tasks

### Task 1: Robust JSON parsing in aggregator

**Files:** `aggregator.py`
**Complexity:** Low
**Dependencies:** None

Replace the greedy `\{.*\}` regex fallback in `parse_aggregation_output()` with `json.JSONDecoder().raw_decode()`. Walk the string for `{` characters and try `raw_decode` at each position. Accept the first parse that contains the expected keys (`synthesis`, `agreements`, `disagreements`, `unique_findings`).

Keep the code-block regex path as the primary (it's already correct). Only change the raw-JSON fallback path.

### Task 2: Rename "consensus" status to "complete"

**Files:** `aggregator.py`, `tests/test_aggregator.py`, `tests/test_server.py`, `skills/consensus/SKILL.md`, `skills/quality-gate/SKILL.md`
**Complexity:** Low
**Dependencies:** None

- In `aggregate()`, change `status = "consensus"` to `status = "complete"`.
- Update the `ConsensusResult` docstring to reflect the three values: `"complete"` / `"partial"` / `"unavailable"`.
- Update test assertions in `tests/test_aggregator.py` that check `status == "consensus"`.
- Update `tests/test_server.py`: change `_make_consensus_result` default status from `"consensus"` to `"complete"` (line 44), and assertions at lines 87 and 408.
- Update `skills/consensus/SKILL.md`: lines 34 (status enum), 115 (min_models description), 137 (operational flow).
- Update `skills/quality-gate/SKILL.md`: line 245 (status check in stagnation judge).

### Task 3: Refactor dispatch_all signature

**Files:** `providers.py`, `server.py`
**Complexity:** Medium
**Dependencies:** None

- Add `config: ModelConfig` to `BaseProvider` protocol (all three concrete classes already have `self.config`, so they satisfy it — no changes to concrete classes needed).
- Change `dispatch_all` to accept `list[BaseProvider]` instead of `list[tuple[BaseProvider, ModelConfig]]`.
- Change `_query_with_timeout` signature from `(provider, config)` to just `(provider)`. Access `provider.config.provider` and `provider.config.model_id` for the timeout error path.
- Update task list construction in line 208: from `[_query_with_timeout(p, c) for p, c in providers]` to `[_query_with_timeout(p) for p in providers]`.
- Update `server.py`: change `_providers` and `_external_providers` from `list[tuple]` to `list[BaseProvider]`. Update `_providers.append((provider, model_config))` → `_providers.append(provider)`. Update all `dispatch_all(...)` calls.

### Task 4: Encapsulate global state in ServerState

**Files:** `server.py`
**Complexity:** Medium
**Dependencies:** Task 3 (new provider list types)

- Define `@dataclass class ServerState` with fields: `config: ConsensusConfig | None`, `providers: list[BaseProvider]`, `project_dir: str`, `external_config: ExternalReviewConfig | None`, `external_providers: list[BaseProvider]`.
- Replace the 5 module-level globals with a single `_state: ServerState | None = None`.
- `initialize()` creates a new `ServerState` and assigns it to `_state`.
- Add `_get_state() -> ServerState | None` helper that returns `None` (NOT raises) — current code gracefully returns "unavailable" when config is None, preserve this pattern.
- Update `_handle_consensus_query` and `_handle_external_review`: call `state = _get_state()`, check `if state is None`, then access `state.config`, `state.providers`, etc.
- Note: `tests/test_server.py` has ~15 functions that directly set module globals (`server_mod._config = ...`, etc.). These all need to change to `server_mod._state = ServerState(...)`. This is covered in Task 7.

### Task 5: Provider-agnostic aggregator fallback + aggregator_error field

**Files:** `aggregator.py`
**Complexity:** Low
**Dependencies:** None

- In `aggregate()`, replace the Anthropic-specific model search with: take the first model from `config.models` (any provider).
- Use `create_provider()` from `providers.py` to instantiate it.
- Update imports: add `create_provider`, remove `AnthropicProvider` (now dead).
- Add optional `error: str | None = None` field to `ConsensusResult` dataclass. Include in `to_dict()`.
- Populate `error` in all three "return unavailable" paths: (1) no models configured, (2) prompt template missing, (3) aggregator call failure.
- Log the selected fallback provider at INFO level when creating one.

### Task 6: Timeout validation + dead field removal in config

**Files:** `config.py`
**Complexity:** Low
**Dependencies:** None

- In `load_config()`, after building `ConsensusConfig`, validate `1 <= timeout_seconds <= 600`. Raise `ConfigError` if out of range.
- In `load_external_review_config()`, validate the same range for `timeout_seconds`.
- Remove `temperature: float = 0.3` field from `ExternalReviewConfig` dataclass.
- In `load_external_review_config()`, stop passing `temperature=section_temperature` to the `ExternalReviewConfig` constructor.
- Note: removing the field will break two tests — `test_external_review_one_model` (asserts `config.temperature == 0.4`) and `test_external_review_temperature_precedence` (asserts `config.temperature == 0.5`). These test updates are in Task 7.

### Task 7: Update and add tests

**Files:** `tests/test_aggregator.py`, `tests/test_config.py`, `tests/test_providers.py`, `tests/test_server.py`
**Complexity:** Medium
**Dependencies:** Tasks 1-6

**Status rename updates (`"consensus"` → `"complete"`):**
- `tests/test_aggregator.py`: update `test_aggregate_all_success_returns_consensus` assertion (line 113)
- `tests/test_server.py`: update `_make_consensus_result` default status (line 44), `test_call_tool_success` assertion (line 87), `test_consensus_with_additional_responses` assertion (line 408)

**Temperature field removal:**
- `tests/test_config.py`: remove `assert config.temperature == 0.4` in `test_external_review_one_model` (line 274)
- `tests/test_config.py`: remove `assert config.temperature == 0.5` in `test_external_review_temperature_precedence` (line 415). Keep per-model temperature assertions (`config.models[N].temperature`) — those still work.

**dispatch_all signature change:**
- `tests/test_providers.py`: update `test_dispatch_all_parallel` and `test_dispatch_all_timeout` — construct `providers` as `list[BaseProvider]` instead of `list[tuple]`

**ServerState migration (~15 test functions):**
- `tests/test_server.py`: all test functions that set `server_mod._config`, `server_mod._providers`, `server_mod._project_dir`, `server_mod._external_config`, `server_mod._external_providers` must change to set `server_mod._state = ServerState(...)`. Create a helper fixture for constructing `ServerState` with defaults to reduce boilerplate.

**New tests:**
- Add test for `parse_aggregation_output` with multiple JSON objects in raw text (greedy regex would have matched wrong object)
- Add tests for `timeout_seconds` validation (boundary: 0, 1, 600, 601) in both `load_config` and `load_external_review_config`
- Add test confirming `ExternalReviewConfig` no longer has `temperature` attribute
- Add test that `ConsensusResult.error` field is populated in failure paths and included in `to_dict()`
