"""Tests for the MCP server entry point."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from config import ConsensusConfig, ExternalReviewConfig, ModelConfig
from providers import ModelResponse
from aggregator import ConsensusResult

import server as server_mod
from server import call_tool, list_tools, ServerState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(enabled: bool = True, modes: dict | None = None) -> ConsensusConfig:
    return ConsensusConfig(
        enabled=enabled,
        min_models=2,
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
        modes=modes or {"review": True, "verdict": True, "investigate": True},
    )


def _make_consensus_result(**kwargs) -> ConsensusResult:
    defaults = {
        "status": "complete",
        "models_queried": 2,
        "models_responded": 2,
        "synthesis": "All models agree.",
        "agreements": [{"finding": "Clean code"}],
        "disagreements": [],
        "unique_findings": [],
        "per_model": [
            {"provider": "anthropic", "model_id": "claude-sonnet-4-20250514", "responded": True, "latency_ms": 100},
            {"provider": "google", "model_id": "gemini-2.5-pro", "responded": True, "latency_ms": 150},
        ],
    }
    defaults.update(kwargs)
    return ConsensusResult(**defaults)


# ---------------------------------------------------------------------------
# test_call_tool_success
# ---------------------------------------------------------------------------


@patch("server.aggregate", new_callable=AsyncMock)
@patch("server.dispatch_all", new_callable=AsyncMock)
async def test_call_tool_success(mock_dispatch, mock_aggregate):
    """Valid consensus_query returns JSON with correct status and fields."""
    server_mod._state = ServerState(
        config=_make_config(),
        providers=["mock_provider"],
        project_dir="/tmp/test-project",
    )

    mock_dispatch.return_value = [
        ModelResponse(provider="anthropic", model_id="claude-sonnet-4-20250514", content="good", latency_ms=100),
        ModelResponse(provider="google", model_id="gemini-2.5-pro", content="also good", latency_ms=150),
    ]
    mock_aggregate.return_value = _make_consensus_result()

    result = await call_tool("consensus_query", {
        "prompt": "Review this code",
        "context": "def foo(): pass",
        "mode": "review",
    })

    assert len(result) == 1
    parsed = json.loads(result[0].text)
    assert parsed["status"] == "complete"
    assert parsed["models_queried"] == 2
    assert parsed["models_responded"] == 2
    assert parsed["synthesis"] == "All models agree."
    assert len(parsed["agreements"]) == 1
    assert len(parsed["per_model"]) == 2

    mock_dispatch.assert_called_once()
    mock_aggregate.assert_called_once()


# ---------------------------------------------------------------------------
# test_call_tool_disabled
# ---------------------------------------------------------------------------


async def test_call_tool_disabled():
    """When config.enabled is False, returns status='unavailable'."""
    server_mod._state = ServerState(
        config=_make_config(enabled=False),
        project_dir="/tmp/test-project",
    )

    result = await call_tool("consensus_query", {
        "prompt": "Review this",
        "context": "some context",
        "mode": "review",
    })

    assert len(result) == 1
    parsed = json.loads(result[0].text)
    assert parsed["status"] == "unavailable"


# ---------------------------------------------------------------------------
# test_call_tool_invalid_mode
# ---------------------------------------------------------------------------


async def test_call_tool_invalid_mode():
    """Invalid mode returns error response with status='unavailable'."""
    server_mod._state = ServerState(
        config=_make_config(),
        project_dir="/tmp/test-project",
    )

    result = await call_tool("consensus_query", {
        "prompt": "Review this",
        "context": "some context",
        "mode": "invalid",
    })

    assert len(result) == 1
    parsed = json.loads(result[0].text)
    assert parsed["status"] == "unavailable"
    assert "Invalid mode" in parsed["synthesis"]


# ---------------------------------------------------------------------------
# test_call_tool_mode_disabled
# ---------------------------------------------------------------------------


async def test_call_tool_mode_disabled():
    """When a specific mode is disabled in config, returns status='unavailable'."""
    server_mod._state = ServerState(
        config=_make_config(modes={
            "review": False,
            "verdict": True,
            "investigate": True,
        }),
        project_dir="/tmp/test-project",
    )

    result = await call_tool("consensus_query", {
        "prompt": "Review this",
        "context": "some context",
        "mode": "review",
    })

    assert len(result) == 1
    parsed = json.loads(result[0].text)
    assert parsed["status"] == "unavailable"


# ---------------------------------------------------------------------------
# test_call_tool_unknown_tool
# ---------------------------------------------------------------------------


async def test_call_tool_unknown_tool():
    """Calling an unknown tool name returns an error message."""
    result = await call_tool("unknown_tool", {})

    assert len(result) == 1
    assert "Unknown tool" in result[0].text
    assert "unknown_tool" in result[0].text


# ---------------------------------------------------------------------------
# test_list_tools_returns_consensus_query
# ---------------------------------------------------------------------------


async def test_list_tools_returns_consensus_query():
    """list_tools returns two tools: consensus_query and external_review."""
    tools = await list_tools()

    assert len(tools) == 2
    tool_names = {t.name for t in tools}
    assert tool_names == {"consensus_query", "external_review"}

    consensus_tool = next(t for t in tools if t.name == "consensus_query")
    assert "prompt" in consensus_tool.inputSchema["properties"]
    assert "context" in consensus_tool.inputSchema["properties"]
    assert "mode" in consensus_tool.inputSchema["properties"]
    assert "additional_responses" in consensus_tool.inputSchema["properties"]
    assert "prompt" in consensus_tool.inputSchema["required"]
    assert "context" in consensus_tool.inputSchema["required"]
    assert "mode" in consensus_tool.inputSchema["required"]

    external_tool = next(t for t in tools if t.name == "external_review")
    assert "prompt" in external_tool.inputSchema["properties"]
    assert "context" in external_tool.inputSchema["properties"]
    assert "metadata" in external_tool.inputSchema["properties"]
    assert "skill" in external_tool.inputSchema["properties"]
    assert "prompt" in external_tool.inputSchema["required"]
    assert "context" in external_tool.inputSchema["required"]


# ---------------------------------------------------------------------------
# External review tests
# ---------------------------------------------------------------------------


def _make_external_config(enabled: bool = True) -> ExternalReviewConfig:
    return ExternalReviewConfig(
        enabled=enabled,
        models=[
            ModelConfig(
                provider="openai",
                model_id="gpt-4o",
                api_key_env="TEST_OPENAI_KEY",
            ),
        ],
        timeout_seconds=180,
    )


@patch("server.dispatch_all", new_callable=AsyncMock)
async def test_external_review_success_one_model(mock_dispatch):
    """Single external model responds successfully."""
    server_mod._state = ServerState(
        external_config=_make_external_config(),
        external_providers=["mock_provider"],
    )

    mock_dispatch.return_value = [
        ModelResponse(provider="openai", model_id="gpt-4o", content="Looks good", latency_ms=200),
    ]

    result = await call_tool("external_review", {
        "prompt": "Review this code",
        "context": "def foo(): pass",
    })

    assert len(result) == 1
    parsed = json.loads(result[0].text)
    assert parsed["status"] == "available"
    assert parsed["models_queried"] == 1
    assert parsed["models_responded"] == 1
    assert len(parsed["reviews"]) == 1
    assert parsed["reviews"][0]["provider"] == "openai"
    assert parsed["reviews"][0]["content"] == "Looks good"
    assert parsed["reviews"][0]["error"] is None


@patch("server.dispatch_all", new_callable=AsyncMock)
async def test_external_review_success_two_models(mock_dispatch):
    """Two external models both respond successfully."""
    ext_config = ExternalReviewConfig(
        enabled=True,
        models=[
            ModelConfig(provider="openai", model_id="gpt-4o", api_key_env="TEST_OPENAI_KEY"),
            ModelConfig(provider="anthropic", model_id="claude-sonnet-4-20250514", api_key_env="TEST_ANTHROPIC_KEY"),
        ],
        timeout_seconds=180,
    )
    server_mod._state = ServerState(
        external_config=ext_config,
        external_providers=["mock1", "mock2"],
    )

    mock_dispatch.return_value = [
        ModelResponse(provider="openai", model_id="gpt-4o", content="Review A", latency_ms=150),
        ModelResponse(provider="anthropic", model_id="claude-sonnet-4-20250514", content="Review B", latency_ms=250),
    ]

    result = await call_tool("external_review", {
        "prompt": "Review this",
        "context": "some code",
    })

    parsed = json.loads(result[0].text)
    assert parsed["status"] == "available"
    assert parsed["models_queried"] == 2
    assert parsed["models_responded"] == 2
    assert len(parsed["reviews"]) == 2


async def test_external_review_disabled():
    """When external review is disabled, returns unavailable."""
    server_mod._state = ServerState(
        external_config=_make_external_config(enabled=False),
    )

    result = await call_tool("external_review", {
        "prompt": "Review this",
        "context": "some code",
    })

    parsed = json.loads(result[0].text)
    assert parsed["status"] == "unavailable"


@patch("server.dispatch_all", new_callable=AsyncMock)
async def test_external_review_timeout_partial(mock_dispatch):
    """One provider times out, status is partial."""
    ext_config = ExternalReviewConfig(
        enabled=True,
        models=[
            ModelConfig(provider="openai", model_id="gpt-4o", api_key_env="TEST_OPENAI_KEY"),
            ModelConfig(provider="anthropic", model_id="claude-sonnet-4-20250514", api_key_env="TEST_ANTHROPIC_KEY"),
        ],
        timeout_seconds=180,
    )
    server_mod._state = ServerState(
        external_config=ext_config,
        external_providers=["mock1", "mock2"],
    )

    mock_dispatch.return_value = [
        ModelResponse(provider="openai", model_id="gpt-4o", content="Review OK", latency_ms=150),
        ModelResponse(provider="anthropic", model_id="claude-sonnet-4-20250514", content="", latency_ms=180000, error="timeout"),
    ]

    result = await call_tool("external_review", {
        "prompt": "Review this",
        "context": "some code",
    })

    parsed = json.loads(result[0].text)
    assert parsed["status"] == "partial"
    assert parsed["models_queried"] == 2
    assert parsed["models_responded"] == 1
    assert parsed["reviews"][1]["error"] == "timeout"


@patch("server.dispatch_all", new_callable=AsyncMock)
async def test_external_review_all_errored_returns_error_status(mock_dispatch):
    """When ALL models error, status is 'error' (not 'unavailable')."""
    ext_config = ExternalReviewConfig(
        enabled=True,
        models=[
            ModelConfig(provider="openai", model_id="gpt-4o", api_key_env="TEST_OPENAI_KEY"),
            ModelConfig(provider="anthropic", model_id="claude-sonnet-4-20250514", api_key_env="TEST_ANTHROPIC_KEY"),
        ],
        timeout_seconds=180,
    )
    server_mod._state = ServerState(
        external_config=ext_config,
        external_providers=["mock1", "mock2"],
    )

    mock_dispatch.return_value = [
        ModelResponse(provider="openai", model_id="gpt-4o", content="", latency_ms=180000, error="timeout"),
        ModelResponse(provider="anthropic", model_id="claude-sonnet-4-20250514", content="", latency_ms=180000, error="timeout"),
    ]

    result = await call_tool("external_review", {
        "prompt": "Review this",
        "context": "some code",
    })

    parsed = json.loads(result[0].text)
    assert parsed["status"] == "error"
    assert parsed["models_queried"] == 2
    assert parsed["models_responded"] == 0


async def test_external_review_no_config():
    """When _external_config is None, returns unavailable."""
    server_mod._state = ServerState(
        external_config=None,
    )

    result = await call_tool("external_review", {
        "prompt": "Review this",
        "context": "some code",
    })

    parsed = json.loads(result[0].text)
    assert parsed["status"] == "unavailable"


@patch("server.aggregate", new_callable=AsyncMock)
@patch("server.dispatch_all", new_callable=AsyncMock)
async def test_consensus_with_additional_responses(mock_dispatch, mock_aggregate):
    """additional_responses are appended before aggregation."""
    server_mod._state = ServerState(
        config=_make_config(),
        providers=["mock_provider"],
        project_dir="/tmp/test-project",
    )

    mock_dispatch.return_value = [
        ModelResponse(provider="anthropic", model_id="claude-sonnet-4-20250514", content="good", latency_ms=100),
    ]
    mock_aggregate.return_value = _make_consensus_result(models_queried=2, models_responded=2)

    result = await call_tool("consensus_query", {
        "prompt": "Review this code",
        "context": "def foo(): pass",
        "mode": "review",
        "additional_responses": [
            {
                "provider": "openai",
                "model_id": "gpt-4o",
                "content": "external review content",
                "latency_ms": 300,
            }
        ],
    })

    assert len(result) == 1
    parsed = json.loads(result[0].text)
    assert parsed["status"] == "complete"

    # Verify aggregate was called with the combined responses
    call_args = mock_aggregate.call_args
    responses_passed = call_args.kwargs["responses"]
    assert len(responses_passed) == 2
    assert responses_passed[1].provider == "openai"
    assert responses_passed[1].model_id == "gpt-4o"
    assert responses_passed[1].content == "external review content"


# ---------------------------------------------------------------------------
# Skill toggle tests (S4)
# ---------------------------------------------------------------------------


async def test_external_review_skill_disabled():
    """When a skill is disabled in config, external_review returns unavailable."""
    ext_config = ExternalReviewConfig(
        enabled=True,
        models=[
            ModelConfig(provider="openai", model_id="gpt-4o", api_key_env="TEST_OPENAI_KEY"),
        ],
        timeout_seconds=180,
        skills={"inquisitor": False, "code_review": True},
    )
    server_mod._state = ServerState(
        external_config=ext_config,
        external_providers=["mock_provider"],
    )

    result = await call_tool("external_review", {
        "prompt": "Review this",
        "context": "some code",
        "skill": "inquisitor",
    })

    parsed = json.loads(result[0].text)
    assert parsed["status"] == "unavailable"
    assert "inquisitor" in parsed.get("reason", "")


@patch("server.dispatch_all", new_callable=AsyncMock)
async def test_external_review_skill_enabled(mock_dispatch):
    """When a skill is enabled in config, external_review proceeds normally."""
    ext_config = ExternalReviewConfig(
        enabled=True,
        models=[
            ModelConfig(provider="openai", model_id="gpt-4o", api_key_env="TEST_OPENAI_KEY"),
        ],
        timeout_seconds=180,
        skills={"code_review": True},
    )
    server_mod._state = ServerState(
        external_config=ext_config,
        external_providers=["mock_provider"],
    )

    mock_dispatch.return_value = [
        ModelResponse(provider="openai", model_id="gpt-4o", content="Looks good", latency_ms=200),
    ]

    result = await call_tool("external_review", {
        "prompt": "Review this",
        "context": "some code",
        "skill": "code_review",
    })

    parsed = json.loads(result[0].text)
    assert parsed["status"] == "available"
    assert parsed["models_responded"] == 1


@patch("server.dispatch_all", new_callable=AsyncMock)
async def test_external_review_unknown_skill_defaults_enabled(mock_dispatch):
    """An unknown skill name defaults to enabled (True)."""
    ext_config = ExternalReviewConfig(
        enabled=True,
        models=[
            ModelConfig(provider="openai", model_id="gpt-4o", api_key_env="TEST_OPENAI_KEY"),
        ],
        timeout_seconds=180,
        skills={"code_review": True},
    )
    server_mod._state = ServerState(
        external_config=ext_config,
        external_providers=["mock_provider"],
    )

    mock_dispatch.return_value = [
        ModelResponse(provider="openai", model_id="gpt-4o", content="OK", latency_ms=100),
    ]

    result = await call_tool("external_review", {
        "prompt": "Review this",
        "context": "some code",
        "skill": "some_future_skill",
    })

    parsed = json.loads(result[0].text)
    assert parsed["status"] == "available"
