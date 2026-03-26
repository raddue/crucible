"""Tests for provider adapters and parallel dispatch."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from config import ModelConfig
from providers import (
    AnthropicProvider,
    GoogleProvider,
    ModelResponse,
    create_provider,
    dispatch_all,
)


# ---------------------------------------------------------------------------
# Anthropic provider tests
# ---------------------------------------------------------------------------


async def test_anthropic_provider_success(anthropic_config):
    """AnthropicProvider returns a valid ModelResponse on success."""
    # Build a mock response matching the Anthropic SDK shape
    mock_text_block = MagicMock()
    mock_text_block.text = "Claude says hello"
    mock_response = MagicMock()
    mock_response.content = [mock_text_block]

    mock_messages = MagicMock()
    mock_messages.create = AsyncMock(return_value=mock_response)

    # Construct provider (uses mocked anthropic module from conftest)
    provider = AnthropicProvider(anthropic_config)
    # Replace the client's messages interface with our mock
    provider.client.messages = mock_messages

    result = await provider.query("test prompt", "test context")

    assert isinstance(result, ModelResponse)
    assert result.provider == "anthropic"
    assert result.model_id == "claude-sonnet-4-20250514"
    assert result.content == "Claude says hello"
    assert result.error is None
    assert result.latency_ms >= 0

    # Verify the SDK was called with the right arguments
    mock_messages.create.assert_awaited_once_with(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        temperature=0.6,
        system="test context",
        messages=[{"role": "user", "content": "test prompt"}],
    )


async def test_anthropic_provider_error(anthropic_config):
    """AnthropicProvider captures exceptions into ModelResponse.error."""
    mock_messages = MagicMock()
    mock_messages.create = AsyncMock(side_effect=RuntimeError("API failure"))

    provider = AnthropicProvider(anthropic_config)
    provider.client.messages = mock_messages

    result = await provider.query("test prompt", "test context")

    assert isinstance(result, ModelResponse)
    assert result.provider == "anthropic"
    assert result.content == ""
    assert result.error == "API failure"
    assert result.latency_ms >= 0


# ---------------------------------------------------------------------------
# Google provider tests
# ---------------------------------------------------------------------------


async def test_google_provider_success(google_config):
    """GoogleProvider returns a valid ModelResponse on success."""
    mock_response = MagicMock()
    mock_response.text = "Gemini says hello"

    mock_generate = AsyncMock(return_value=mock_response)
    mock_models = MagicMock()
    mock_models.generate_content = mock_generate

    mock_aio = MagicMock()
    mock_aio.models = mock_models

    provider = GoogleProvider(google_config)
    # Replace the client's aio interface with our mock
    provider.client.aio = mock_aio

    result = await provider.query("test prompt", "test context")

    assert isinstance(result, ModelResponse)
    assert result.provider == "google"
    assert result.model_id == "gemini-2.5-pro"
    assert result.content == "Gemini says hello"
    assert result.error is None
    assert result.latency_ms >= 0

    # Verify the SDK was called with the right arguments
    mock_generate.assert_awaited_once_with(
        model="gemini-2.5-pro",
        contents="test context\n\n---\n\ntest prompt",
        config={
            "temperature": 0.6,
            "max_output_tokens": 4096,
        },
    )


async def test_google_provider_error(google_config):
    """GoogleProvider captures exceptions into ModelResponse.error."""
    mock_generate = AsyncMock(side_effect=RuntimeError("Gemini API failure"))
    mock_models = MagicMock()
    mock_models.generate_content = mock_generate

    mock_aio = MagicMock()
    mock_aio.models = mock_models

    provider = GoogleProvider(google_config)
    provider.client.aio = mock_aio

    result = await provider.query("test prompt", "test context")

    assert isinstance(result, ModelResponse)
    assert result.provider == "google"
    assert result.content == ""
    assert result.error == "Gemini API failure"
    assert result.latency_ms >= 0


# ---------------------------------------------------------------------------
# dispatch_all tests
# ---------------------------------------------------------------------------


async def test_dispatch_all_parallel(anthropic_config, google_config):
    """dispatch_all returns results from all providers in parallel."""
    mock_provider_a = MagicMock()
    mock_provider_a.query = AsyncMock(return_value=ModelResponse(
        provider="anthropic",
        model_id="claude-sonnet-4-20250514",
        content="response A",
        latency_ms=100,
    ))

    mock_provider_b = MagicMock()
    mock_provider_b.query = AsyncMock(return_value=ModelResponse(
        provider="google",
        model_id="gemini-2.5-pro",
        content="response B",
        latency_ms=200,
    ))

    providers = [
        (mock_provider_a, anthropic_config),
        (mock_provider_b, google_config),
    ]
    results = await dispatch_all(providers, "prompt", "context", timeout_seconds=30)

    assert len(results) == 2
    assert results[0].content == "response A"
    assert results[0].error is None
    assert results[1].content == "response B"
    assert results[1].error is None

    mock_provider_a.query.assert_awaited_once_with("prompt", "context")
    mock_provider_b.query.assert_awaited_once_with("prompt", "context")


async def test_dispatch_all_timeout(anthropic_config, google_config):
    """dispatch_all returns a timeout error for slow providers without blocking others."""

    async def slow_query(prompt, context):
        await asyncio.sleep(10)  # Way longer than timeout
        return ModelResponse(
            provider="anthropic",
            model_id="claude-sonnet-4-20250514",
            content="should not arrive",
            latency_ms=10000,
        )

    mock_slow = MagicMock()
    mock_slow.query = slow_query

    mock_fast = MagicMock()
    mock_fast.query = AsyncMock(return_value=ModelResponse(
        provider="google",
        model_id="gemini-2.5-pro",
        content="fast response",
        latency_ms=50,
    ))

    providers = [
        (mock_slow, anthropic_config),
        (mock_fast, google_config),
    ]
    # Use a very short timeout so the test runs quickly
    results = await dispatch_all(providers, "prompt", "context", timeout_seconds=1)

    assert len(results) == 2

    # Order matches input: slow first, fast second
    timeout_result = results[0]
    fast_result = results[1]

    assert timeout_result.error == "timeout"
    assert timeout_result.content == ""
    assert timeout_result.provider == "anthropic"
    assert timeout_result.latency_ms == 1000

    assert fast_result.error is None
    assert fast_result.content == "fast response"


# ---------------------------------------------------------------------------
# create_provider tests
# ---------------------------------------------------------------------------


def test_create_provider_anthropic(anthropic_config):
    """create_provider returns an AnthropicProvider for 'anthropic' config."""
    provider = create_provider(anthropic_config)
    assert isinstance(provider, AnthropicProvider)


def test_create_provider_google(google_config):
    """create_provider returns a GoogleProvider for 'google' config."""
    provider = create_provider(google_config)
    assert isinstance(provider, GoogleProvider)


def test_create_provider_unknown():
    """create_provider raises ValueError for an unknown provider."""
    config = ModelConfig(
        provider="openai",
        model_id="gpt-4o",
        api_key_env="OPENAI_API_KEY",
        temperature=0.6,
    )
    with pytest.raises(ValueError, match="Unknown provider: openai"):
        create_provider(config)
