"""Tests for provider adapters and parallel dispatch."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from config import ModelConfig
from providers import (
    AnthropicProvider,
    GoogleProvider,
    OpenAIProvider,
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
    assert "API failure" in result.error
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
    assert "Gemini API failure" in result.error
    assert result.latency_ms >= 0


# ---------------------------------------------------------------------------
# OpenAI provider tests
# ---------------------------------------------------------------------------


async def test_openai_provider_success(openai_config):
    """OpenAIProvider returns a valid ModelResponse on success."""
    mock_message = MagicMock()
    mock_message.content = "GPT says hello"

    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_completions = MagicMock()
    mock_completions.create = AsyncMock(return_value=mock_response)

    mock_chat = MagicMock()
    mock_chat.completions = mock_completions

    provider = OpenAIProvider(openai_config)
    provider.client.chat = mock_chat

    result = await provider.query("test prompt", "test context")

    assert isinstance(result, ModelResponse)
    assert result.provider == "openai"
    assert result.model_id == "gpt-4o"
    assert result.content == "GPT says hello"
    assert result.error is None
    assert result.latency_ms >= 0

    mock_completions.create.assert_awaited_once_with(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "test context"},
            {"role": "user", "content": "test prompt"},
        ],
        max_tokens=4096,
        temperature=0.6,
    )


async def test_openai_provider_error(openai_config):
    """OpenAIProvider captures exceptions into ModelResponse.error."""
    mock_completions = MagicMock()
    mock_completions.create = AsyncMock(side_effect=RuntimeError("OpenAI API failure"))

    mock_chat = MagicMock()
    mock_chat.completions = mock_completions

    provider = OpenAIProvider(openai_config)
    provider.client.chat = mock_chat

    result = await provider.query("test prompt", "test context")

    assert isinstance(result, ModelResponse)
    assert result.provider == "openai"
    assert result.content == ""
    assert "OpenAI API failure" in result.error
    assert result.latency_ms >= 0


async def test_openai_provider_base_url_override(monkeypatch):
    """OpenAIProvider reads base_url from env when base_url_env is set."""
    monkeypatch.setenv("TEST_OPENAI_KEY", "test-key-789")
    monkeypatch.setenv("TEST_OPENAI_BASE_URL", "https://custom.api.example.com/v1")

    config = ModelConfig(
        provider="openai",
        model_id="gpt-4o",
        api_key_env="TEST_OPENAI_KEY",
        temperature=0.6,
    )
    # Attach base_url_env dynamically (Task 2 adds the field formally)
    config.base_url_env = "TEST_OPENAI_BASE_URL"

    provider = OpenAIProvider(config)

    # The mock AsyncOpenAI constructor should have been called with base_url
    import openai
    openai.AsyncOpenAI.assert_called_with(
        api_key="test-key-789",
        base_url="https://custom.api.example.com/v1",
    )


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

    providers = [mock_provider_a, mock_provider_b]
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
    mock_slow.config = anthropic_config

    mock_fast = MagicMock()
    mock_fast.query = AsyncMock(return_value=ModelResponse(
        provider="google",
        model_id="gemini-2.5-pro",
        content="fast response",
        latency_ms=50,
    ))
    mock_fast.config = google_config

    providers = [mock_slow, mock_fast]
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


def test_create_provider_openai(openai_config):
    """create_provider returns an OpenAIProvider for 'openai' config."""
    provider = create_provider(openai_config)
    assert isinstance(provider, OpenAIProvider)


def test_create_provider_unknown():
    """create_provider raises ValueError for an unknown provider."""
    config = ModelConfig(
        provider="cohere",
        model_id="command-r-plus",
        api_key_env="COHERE_API_KEY",
        temperature=0.6,
    )
    with pytest.raises(ValueError, match="Unknown provider: cohere"):
        create_provider(config)
