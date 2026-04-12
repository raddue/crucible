"""Tests for aggregation logic and multi-model synthesis."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from config import ConsensusConfig, ModelConfig
from providers import ModelResponse
from aggregator import (
    AggregationError,
    ConsensusResult,
    aggregate,
    build_aggregation_input,
    load_aggregation_prompt,
    parse_aggregation_output,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(
    provider: str = "anthropic",
    model_id: str = "claude-sonnet-4-20250514",
    content: str = "test response",
    latency_ms: int = 100,
    error: str | None = None,
) -> ModelResponse:
    return ModelResponse(
        provider=provider,
        model_id=model_id,
        content=content,
        latency_ms=latency_ms,
        error=error,
    )


def _make_config(min_models: int = 2) -> ConsensusConfig:
    return ConsensusConfig(
        enabled=True,
        min_models=min_models,
        timeout_seconds=120,
        models=[
            ModelConfig(
                provider="anthropic",
                model_id="claude-sonnet-4-20250514",
                api_key_env="TEST_ANTHROPIC_KEY",
            ),
            ModelConfig(
                provider="google",
                model_id="gemini-2.5-pro",
                api_key_env="TEST_GOOGLE_KEY",
            ),
        ],
    )


def _make_mock_aggregator(response_content: str) -> MagicMock:
    """Create a mock aggregator provider that returns a successful response."""
    mock = MagicMock()
    mock.query = AsyncMock(return_value=ModelResponse(
        provider="anthropic",
        model_id="claude-sonnet-4-20250514",
        content=response_content,
        latency_ms=200,
    ))
    return mock


VALID_AGG_JSON = json.dumps({
    "synthesis": "Models agree on key issues.",
    "agreements": [{"finding": "Missing error handling", "severity": "Significant"}],
    "disagreements": [],
    "unique_findings": [{"finding": "Potential race condition", "model": "google:gemini-2.5-pro"}],
})


# ---------------------------------------------------------------------------
# test_aggregate_all_success_returns_consensus
# ---------------------------------------------------------------------------


async def test_aggregate_all_success_returns_consensus(tmp_path, monkeypatch):
    """2 successful responses -> status='consensus', correct counts."""
    monkeypatch.setenv("TEST_ANTHROPIC_KEY", "key")
    monkeypatch.setenv("TEST_GOOGLE_KEY", "key")

    # Write a prompt template
    prompt_file = tmp_path / "aggregation-review-prompt.md"
    prompt_file.write_text("Template [MODEL_RESPONSES] and [ORIGINAL_CONTEXT]")

    responses = [
        _make_response(provider="anthropic", content="review from claude"),
        _make_response(provider="google", model_id="gemini-2.5-pro", content="review from gemini"),
    ]

    mock_agg = _make_mock_aggregator(VALID_AGG_JSON)
    config = _make_config(min_models=2)

    result = await aggregate(
        responses=responses,
        prompt="Review this code",
        context="def foo(): pass",
        mode="review",
        config=config,
        prompts_dir=str(tmp_path),
        aggregator_provider=mock_agg,
    )

    assert result.status == "complete"
    assert result.models_queried == 2
    assert result.models_responded == 2
    assert result.synthesis == "Models agree on key issues."
    assert len(result.agreements) == 1
    assert len(result.unique_findings) == 1
    assert len(result.per_model) == 2


# ---------------------------------------------------------------------------
# test_aggregate_below_min_models_returns_unavailable
# ---------------------------------------------------------------------------


async def test_aggregate_below_min_models_returns_unavailable(tmp_path, monkeypatch):
    """1 success + 1 failure with min_models=2 -> status='unavailable'."""
    monkeypatch.setenv("TEST_ANTHROPIC_KEY", "key")
    monkeypatch.setenv("TEST_GOOGLE_KEY", "key")

    prompt_file = tmp_path / "aggregation-review-prompt.md"
    prompt_file.write_text("Template [MODEL_RESPONSES] and [ORIGINAL_CONTEXT]")

    responses = [
        _make_response(provider="anthropic", content="review from claude"),
        _make_response(provider="google", model_id="gemini-2.5-pro", error="timeout"),
    ]

    config = _make_config(min_models=2)

    result = await aggregate(
        responses=responses,
        prompt="Review this code",
        context="def foo(): pass",
        mode="review",
        config=config,
        prompts_dir=str(tmp_path),
    )

    assert result.status == "unavailable"
    assert result.models_queried == 2
    assert result.models_responded == 1
    assert len(result.per_model) == 2
    assert result.per_model[0]["responded"] is True
    assert result.per_model[1]["responded"] is False


# ---------------------------------------------------------------------------
# test_aggregate_partial_returns_partial
# ---------------------------------------------------------------------------


async def test_aggregate_partial_returns_partial(tmp_path, monkeypatch):
    """2 success + 1 failure with min_models=2 -> status='partial'."""
    monkeypatch.setenv("TEST_ANTHROPIC_KEY", "key")
    monkeypatch.setenv("TEST_GOOGLE_KEY", "key")

    prompt_file = tmp_path / "aggregation-review-prompt.md"
    prompt_file.write_text("Template [MODEL_RESPONSES] and [ORIGINAL_CONTEXT]")

    responses = [
        _make_response(provider="anthropic", content="review from claude"),
        _make_response(provider="google", model_id="gemini-2.5-pro", content="review from gemini"),
        _make_response(provider="anthropic", model_id="claude-haiku", error="rate_limit"),
    ]

    mock_agg = _make_mock_aggregator(VALID_AGG_JSON)
    config = _make_config(min_models=2)

    result = await aggregate(
        responses=responses,
        prompt="Review this code",
        context="def foo(): pass",
        mode="review",
        config=config,
        prompts_dir=str(tmp_path),
        aggregator_provider=mock_agg,
    )

    assert result.status == "partial"
    assert result.models_queried == 3
    assert result.models_responded == 2
    assert len(result.per_model) == 3


# ---------------------------------------------------------------------------
# test_build_aggregation_input_formats_xml
# ---------------------------------------------------------------------------


def test_build_aggregation_input_formats_xml():
    """Verify XML tag format with provider/model_id attributes; failed responses excluded."""
    responses = [
        _make_response(provider="anthropic", model_id="claude-sonnet-4-20250514", content="Good code"),
        _make_response(provider="google", model_id="gemini-2.5-pro", content="Needs work"),
        _make_response(provider="anthropic", model_id="claude-haiku", error="timeout"),
    ]

    result = build_aggregation_input(responses, "prompt", "context")

    # Should include the two successful responses (with source attribute)
    assert '<model provider="anthropic" model_id="claude-sonnet-4-20250514" source="provider">' in result
    assert "Good code" in result
    assert '<model provider="google" model_id="gemini-2.5-pro" source="provider">' in result
    assert "Needs work" in result

    # Should NOT include the failed response
    assert "claude-haiku" not in result
    assert "timeout" not in result

    # Verify closing tags
    assert result.count("</model>") == 2


# ---------------------------------------------------------------------------
# test_parse_aggregation_output_valid_json
# ---------------------------------------------------------------------------


def test_parse_aggregation_output_valid_json():
    """Raw string containing valid JSON -> extracted correctly."""
    raw = json.dumps({
        "synthesis": "Everything looks good.",
        "agreements": [{"finding": "Clean code"}],
        "disagreements": [],
        "unique_findings": [],
    })

    result = parse_aggregation_output(raw)

    assert result["synthesis"] == "Everything looks good."
    assert len(result["agreements"]) == 1
    assert result["agreements"][0]["finding"] == "Clean code"
    assert result["disagreements"] == []
    assert result["unique_findings"] == []


# ---------------------------------------------------------------------------
# test_parse_aggregation_output_json_in_code_block
# ---------------------------------------------------------------------------


def test_parse_aggregation_output_json_in_code_block():
    """JSON wrapped in ```json ... ``` -> extracted correctly."""
    inner_json = {
        "synthesis": "Synthesized review.",
        "agreements": [],
        "disagreements": [{"aspect": "error handling"}],
        "unique_findings": [],
    }
    raw = f"Here is the analysis:\n\n```json\n{json.dumps(inner_json)}\n```\n\nDone."

    result = parse_aggregation_output(raw)

    assert result["synthesis"] == "Synthesized review."
    assert len(result["disagreements"]) == 1
    assert result["disagreements"][0]["aspect"] == "error handling"


# ---------------------------------------------------------------------------
# test_parse_aggregation_output_fallback
# ---------------------------------------------------------------------------


def test_parse_aggregation_output_fallback():
    """Non-JSON text -> fallback to synthesis=raw."""
    raw = "This is just plain text with no JSON structure at all."

    result = parse_aggregation_output(raw)

    assert result["synthesis"] == raw
    assert result["agreements"] == []
    assert result["disagreements"] == []
    assert result["unique_findings"] == []


# ---------------------------------------------------------------------------
# test_load_aggregation_prompt_missing_raises
# ---------------------------------------------------------------------------


def test_load_aggregation_prompt_missing_raises(tmp_path):
    """Nonexistent prompt file -> AggregationError."""
    with pytest.raises(AggregationError, match="Aggregation prompt not found"):
        load_aggregation_prompt("nonexistent", str(tmp_path))


# ---------------------------------------------------------------------------
# test_aggregator_call_failure_returns_unavailable
# ---------------------------------------------------------------------------


async def test_aggregator_call_failure_returns_unavailable(tmp_path, monkeypatch):
    """Aggregation provider raises exception -> status='unavailable', per_model populated."""
    monkeypatch.setenv("TEST_ANTHROPIC_KEY", "key")
    monkeypatch.setenv("TEST_GOOGLE_KEY", "key")

    prompt_file = tmp_path / "aggregation-review-prompt.md"
    prompt_file.write_text("Template [MODEL_RESPONSES] and [ORIGINAL_CONTEXT]")

    responses = [
        _make_response(provider="anthropic", content="review from claude"),
        _make_response(provider="google", model_id="gemini-2.5-pro", content="review from gemini"),
    ]

    # Mock aggregator that raises an exception
    mock_agg = MagicMock()
    mock_agg.query = AsyncMock(side_effect=RuntimeError("Aggregation API failure"))

    config = _make_config(min_models=2)

    result = await aggregate(
        responses=responses,
        prompt="Review this code",
        context="def foo(): pass",
        mode="review",
        config=config,
        prompts_dir=str(tmp_path),
        aggregator_provider=mock_agg,
    )

    assert result.status == "unavailable"
    assert result.models_queried == 2
    assert result.models_responded == 2
    assert len(result.per_model) == 2
    assert result.per_model[0]["responded"] is True
    assert result.per_model[1]["responded"] is True


# ---------------------------------------------------------------------------
# test_parse_aggregation_output_multiple_json_objects
# ---------------------------------------------------------------------------


def test_parse_aggregation_output_multiple_json_objects():
    """Multiple JSON objects in text — first valid one with expected keys wins."""
    preamble_json = json.dumps({"unrelated": "data", "count": 42})
    target_json = json.dumps({
        "synthesis": "Correct object.",
        "agreements": [{"finding": "Match"}],
        "disagreements": [],
        "unique_findings": [],
    })
    raw = f"Here is some data: {preamble_json} and the real result: {target_json} end."

    result = parse_aggregation_output(raw)

    assert result["synthesis"] == "Correct object."
    assert len(result["agreements"]) == 1


# ---------------------------------------------------------------------------
# test_consensus_result_error_field
# ---------------------------------------------------------------------------


def test_consensus_result_error_field_in_to_dict():
    """ConsensusResult.error is included in to_dict() when set."""
    result = ConsensusResult(status="unavailable", error="Test error message")
    d = result.to_dict()
    assert d["error"] == "Test error message"


def test_consensus_result_no_error_in_to_dict():
    """ConsensusResult.error is omitted from to_dict() when None."""
    result = ConsensusResult(status="complete")
    d = result.to_dict()
    assert "error" not in d


# ---------------------------------------------------------------------------
# test_aggregate_error_populated_on_failure
# ---------------------------------------------------------------------------


async def test_aggregate_error_populated_on_too_few_models(tmp_path, monkeypatch):
    """When too few models respond, error field explains why."""
    monkeypatch.setenv("TEST_ANTHROPIC_KEY", "key")
    monkeypatch.setenv("TEST_GOOGLE_KEY", "key")

    responses = [
        _make_response(provider="anthropic", content="review from claude"),
        _make_response(provider="google", model_id="gemini-2.5-pro", error="timeout"),
    ]

    config = _make_config(min_models=2)

    result = await aggregate(
        responses=responses,
        prompt="Review this code",
        context="def foo(): pass",
        mode="review",
        config=config,
        prompts_dir=str(tmp_path),
    )

    assert result.status == "unavailable"
    assert result.error is not None
    assert "Too few models responded" in result.error
