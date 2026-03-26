"""Tests for the MCP server entry point."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from config import ConsensusConfig, ModelConfig
from providers import ModelResponse
from aggregator import ConsensusResult

import server as server_mod
from server import call_tool, list_tools


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
        "status": "consensus",
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
    server_mod._config = _make_config()
    server_mod._providers = [("mock_provider", "mock_config")]
    server_mod._project_dir = "/tmp/test-project"

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
    assert parsed["status"] == "consensus"
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
    server_mod._config = _make_config(enabled=False)
    server_mod._providers = []
    server_mod._project_dir = "/tmp/test-project"

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
    server_mod._config = _make_config()
    server_mod._providers = []
    server_mod._project_dir = "/tmp/test-project"

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
    server_mod._config = _make_config(modes={
        "review": False,
        "verdict": True,
        "investigate": True,
    })
    server_mod._providers = []
    server_mod._project_dir = "/tmp/test-project"

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
    """list_tools returns exactly one tool named 'consensus_query' with correct schema."""
    tools = await list_tools()

    assert len(tools) == 1
    tool = tools[0]
    assert tool.name == "consensus_query"
    assert "prompt" in tool.inputSchema["properties"]
    assert "context" in tool.inputSchema["properties"]
    assert "mode" in tool.inputSchema["properties"]
    assert "prompt" in tool.inputSchema["required"]
    assert "context" in tool.inputSchema["required"]
    assert "mode" in tool.inputSchema["required"]
