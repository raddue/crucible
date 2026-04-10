"""Provider adapters for multi-model consensus dispatch."""

import asyncio
import re
import time
from dataclasses import dataclass
from typing import Protocol

from config import ModelConfig


def _sanitize_error(e: Exception) -> str:
    """Sanitize exception message to prevent API key leakage."""
    msg = str(e)
    # Redact anything that looks like an API key
    msg = re.sub(r'(sk-|key-|AIza)[A-Za-z0-9_-]{10,}', '[REDACTED]', msg)
    # Truncate to prevent excessive detail
    if len(msg) > 200:
        msg = msg[:200] + "..."
    return f"{type(e).__name__}: {msg}"


@dataclass
class ModelResponse:
    """Response from a single model provider."""
    provider: str
    model_id: str
    content: str
    latency_ms: int
    error: str | None = None
    source: str = "provider"  # "provider" for real responses, "external" for injected


class BaseProvider(Protocol):
    """Protocol for model provider adapters."""
    async def query(self, prompt: str, context: str) -> ModelResponse: ...


class AnthropicProvider:
    """Provider adapter for Anthropic (Claude) models."""

    def __init__(self, config: ModelConfig):
        import anthropic
        import os
        self.config = config
        self.client = anthropic.AsyncAnthropic(
            api_key=os.environ[config.api_key_env]
        )

    async def query(self, prompt: str, context: str) -> ModelResponse:
        start = time.monotonic()
        try:
            response = await self.client.messages.create(
                model=self.config.model_id,
                max_tokens=4096,
                temperature=self.config.temperature,
                system=context,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.content[0].text
            latency = int((time.monotonic() - start) * 1000)
            return ModelResponse(
                provider=self.config.provider,
                model_id=self.config.model_id,
                content=content,
                latency_ms=latency,
            )
        except Exception as e:
            latency = int((time.monotonic() - start) * 1000)
            return ModelResponse(
                provider=self.config.provider,
                model_id=self.config.model_id,
                content="",
                latency_ms=latency,
                error=_sanitize_error(e),
            )


class GoogleProvider:
    """Provider adapter for Google (Gemini) models."""

    def __init__(self, config: ModelConfig):
        from google import genai
        import os
        self.config = config
        self.client = genai.Client(
            api_key=os.environ[config.api_key_env]
        )

    async def query(self, prompt: str, context: str) -> ModelResponse:
        start = time.monotonic()
        try:
            full_prompt = f"{context}\n\n---\n\n{prompt}"
            response = await self.client.aio.models.generate_content(
                model=self.config.model_id,
                contents=full_prompt,
                config={
                    "temperature": self.config.temperature,
                    "max_output_tokens": 4096,
                },
            )
            content = response.text or ""
            latency = int((time.monotonic() - start) * 1000)
            return ModelResponse(
                provider=self.config.provider,
                model_id=self.config.model_id,
                content=content,
                latency_ms=latency,
            )
        except Exception as e:
            latency = int((time.monotonic() - start) * 1000)
            return ModelResponse(
                provider=self.config.provider,
                model_id=self.config.model_id,
                content="",
                latency_ms=latency,
                error=_sanitize_error(e),
            )


class OpenAIProvider:
    """Provider adapter for OpenAI-compatible models."""

    def __init__(self, config: ModelConfig):
        import openai
        import os
        self.config = config
        api_key = os.environ.get(config.api_key_env)
        base_url = None
        if config.base_url_env:
            base_url = os.environ.get(config.base_url_env) or None
        self.client = openai.AsyncOpenAI(
            api_key=api_key,
            **({"base_url": base_url} if base_url else {}),
        )

    async def query(self, prompt: str, context: str) -> ModelResponse:
        start = time.monotonic()
        try:
            response = await self.client.chat.completions.create(
                model=self.config.model_id,
                messages=[
                    {"role": "system", "content": context},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=4096,
                temperature=self.config.temperature,
            )
            content = response.choices[0].message.content or ""
            latency = int((time.monotonic() - start) * 1000)
            return ModelResponse(
                provider=self.config.provider,
                model_id=self.config.model_id,
                content=content,
                latency_ms=latency,
            )
        except Exception as e:
            latency = int((time.monotonic() - start) * 1000)
            return ModelResponse(
                provider=self.config.provider,
                model_id=self.config.model_id,
                content="",
                latency_ms=latency,
                error=_sanitize_error(e),
            )


PROVIDER_REGISTRY: dict[str, type] = {
    "anthropic": AnthropicProvider,
    "google": GoogleProvider,
    "openai": OpenAIProvider,
}


def create_provider(config: ModelConfig) -> BaseProvider:
    """Create a provider adapter from a model config."""
    cls = PROVIDER_REGISTRY.get(config.provider)
    if cls is None:
        raise ValueError(f"Unknown provider: {config.provider}")
    return cls(config)


async def dispatch_all(
    providers: list[tuple[BaseProvider, ModelConfig]],
    prompt: str,
    context: str,
    timeout_seconds: int,
) -> list[ModelResponse]:
    """Dispatch prompt to all providers in parallel with per-provider timeout."""

    async def _query_with_timeout(
        provider: BaseProvider, config: ModelConfig
    ) -> ModelResponse:
        try:
            return await asyncio.wait_for(
                provider.query(prompt, context),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            return ModelResponse(
                provider=config.provider,
                model_id=config.model_id,
                content="",
                latency_ms=timeout_seconds * 1000,
                error="timeout",
            )

    tasks = [_query_with_timeout(p, c) for p, c in providers]
    return list(await asyncio.gather(*tasks))
