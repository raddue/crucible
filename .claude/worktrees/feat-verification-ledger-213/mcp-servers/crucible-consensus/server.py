"""Crucible Consensus MCP Server — multi-model consensus for high-stakes decisions."""

import json
import os
import sys
import logging
from dataclasses import dataclass, field
from pathlib import Path

from mcp.server import Server, InitializationOptions, NotificationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from config import load_config, ConfigError, ConsensusConfig, ExternalReviewConfig, load_external_review_config
from providers import BaseProvider, create_provider, dispatch_all, ModelResponse
from aggregator import aggregate, ConsensusResult

logger = logging.getLogger("crucible-consensus")
logging.basicConfig(stream=sys.stderr, level=logging.INFO)

server = Server("crucible-consensus")


@dataclass
class ServerState:
    """Encapsulates all mutable server state."""
    config: ConsensusConfig | None = None
    providers: list[BaseProvider] = field(default_factory=list)
    project_dir: str = ""
    external_config: ExternalReviewConfig | None = None
    external_providers: list[BaseProvider] = field(default_factory=list)


_state: ServerState | None = None


def _get_state() -> ServerState | None:
    """Return current server state, or None if uninitialized."""
    return _state


def initialize():
    """Load config and create providers on startup."""
    global _state
    project_dir = os.environ.get("PROJECT_DIR", os.getcwd())

    state = ServerState(project_dir=project_dir)

    # Load consensus config (optional — don't crash if missing)
    try:
        state.config = load_config(project_dir)
    except ConfigError as e:
        state.config = None
        logger.warning(f"Consensus config not loaded: {e}")

    if state.config is not None and not state.config.enabled:
        logger.info("Consensus is disabled in config")

    if state.config is not None and state.config.enabled:
        for model_config in state.config.models:
            try:
                provider = create_provider(model_config)
                state.providers.append(provider)
                logger.info(f"Initialized {model_config.provider}/{model_config.model_id}")
            except Exception as e:
                logger.warning(f"Failed to initialize {model_config.provider}/{model_config.model_id}: {e}")

        logger.info(f"Consensus server ready: {len(state.providers)} providers, min_models={state.config.min_models}")

    # Load external review config (may raise ConfigError on malformed config)
    try:
        state.external_config = load_external_review_config(project_dir)
    except ConfigError as e:
        state.external_config = ExternalReviewConfig()
        logger.warning(f"External review config not loaded: {e}")
    if state.external_config.enabled and state.external_config.models:
        for model_config in state.external_config.models:
            try:
                provider = create_provider(model_config)
                state.external_providers.append(provider)
                logger.info(f"External review: initialized {model_config.provider}/{model_config.model_id}")
            except Exception as e:
                logger.warning(f"External review: failed to initialize {model_config.provider}/{model_config.model_id}: {e}")
        logger.info(f"External review ready: {len(state.external_providers)} providers")

    _state = state


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="consensus_query",
            description="Dispatch a prompt to multiple LLM providers and synthesize their responses.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "The question or review prompt"},
                    "context": {"type": "string", "description": "Supporting context (artifact content, etc.)"},
                    "mode": {"type": "string", "enum": ["review", "verdict", "investigate"], "description": "Consensus mode"},
                    "metadata": {"type": "object", "description": "Optional metadata (artifact_type, round_number, etc.)"},
                    "additional_responses": {
                        "type": "array",
                        "description": "External review responses to inject into consensus aggregation",
                        "items": {
                            "type": "object",
                            "properties": {
                                "provider": {"type": "string"},
                                "model_id": {"type": "string"},
                                "content": {"type": "string"},
                                "latency_ms": {"type": "integer"},
                            },
                            "required": ["provider", "model_id", "content", "latency_ms"],
                        },
                    },
                },
                "required": ["prompt", "context", "mode"],
            },
        ),
        Tool(
            name="external_review",
            description="Dispatch a review prompt to configured external models and return raw per-model responses.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Review prompt to send to external models"},
                    "context": {"type": "string", "description": "Code diff and supporting context"},
                    "metadata": {"type": "object", "description": "Traceability metadata"},
                    "skill": {"type": "string", "description": "Calling skill name (e.g. 'code_review', 'quality_gate'). If provided, checked against per-skill toggles in config."},
                },
                "required": ["prompt", "context"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "consensus_query":
        return await _handle_consensus_query(arguments)
    elif name == "external_review":
        return await _handle_external_review(arguments)
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def _handle_consensus_query(arguments: dict) -> list[TextContent]:
    state = _get_state()
    if state is None or state.config is None:
        return [TextContent(type="text", text='{"status": "unavailable", "synthesis": "Consensus not configured"}')]

    if not state.config.enabled:
        result = ConsensusResult(status="unavailable")
        return [TextContent(type="text", text=json.dumps(result.to_dict()))]

    prompt = arguments["prompt"]
    context = arguments["context"]
    mode = arguments["mode"]

    # Input size limits to prevent DoS / API credit burn
    MAX_INPUT_SIZE = 500_000  # 500KB
    MAX_ADDITIONAL_RESPONSES = 10
    if len(prompt) > MAX_INPUT_SIZE or len(context) > MAX_INPUT_SIZE:
        return [TextContent(type="text", text=json.dumps({"status": "unavailable", "synthesis": "Input exceeds size limit (500KB max)"}))]

    if mode not in ("review", "verdict", "investigate"):
        return [TextContent(type="text", text=json.dumps({"status": "unavailable", "synthesis": f"Invalid mode: {mode}"}))]

    # Check if this mode is enabled
    if not state.config.modes.get(mode, True):
        result = ConsensusResult(status="unavailable")
        return [TextContent(type="text", text=json.dumps(result.to_dict()))]

    logger.info(f"Consensus query: mode={mode}, providers={len(state.providers)}")

    # Dispatch to all providers in parallel
    responses = await dispatch_all(state.providers, prompt, context, state.config.timeout_seconds)

    # Inject additional external review responses if provided
    additional_responses = arguments.get("additional_responses")
    if additional_responses:
        if len(additional_responses) > MAX_ADDITIONAL_RESPONSES:
            additional_responses = additional_responses[:MAX_ADDITIONAL_RESPONSES]
            logger.warning(f"Truncated additional_responses to {MAX_ADDITIONAL_RESPONSES}")
        for ar in additional_responses:
            try:
                content = ar["content"]
                if len(content) > MAX_INPUT_SIZE:
                    logger.warning("Skipping oversized additional_response")
                    continue
                responses.append(ModelResponse(
                    provider=ar["provider"],
                    model_id=ar["model_id"],
                    content=content,
                    latency_ms=ar["latency_ms"],
                    source="external",  # Tag to distinguish from real provider responses
                ))
            except (KeyError, TypeError) as e:
                logger.warning(f"Skipping malformed additional_response: {e}")

    # Aggregate responses
    prompts_dir = str(Path(state.project_dir) / "skills" / "consensus")
    result = await aggregate(
        responses=responses,
        prompt=prompt,
        context=context,
        mode=mode,
        config=state.config,
        prompts_dir=prompts_dir,
    )

    logger.info(f"Consensus result: status={result.status}, responded={result.models_responded}/{result.models_queried}")

    return [TextContent(type="text", text=json.dumps(result.to_dict()))]


async def _handle_external_review(arguments: dict) -> list[TextContent]:
    state = _get_state()
    if state is None or state.external_config is None or not state.external_config.enabled:
        return [TextContent(type="text", text=json.dumps({"status": "unavailable"}))]

    if not state.external_providers:
        return [TextContent(type="text", text=json.dumps({"status": "unavailable"}))]

    # Per-skill toggle: if caller declares a skill, check whether it's enabled
    # Normalize hyphenated names to underscored to match config keys
    skill = (arguments.get("skill") or "").replace("-", "_") or None
    if skill and not state.external_config.skills.get(skill, True):
        return [TextContent(type="text", text=json.dumps({"status": "unavailable", "reason": f"external review disabled for skill '{skill}'"}))]

    prompt = arguments["prompt"]
    context = arguments["context"]

    # Input size limits to prevent DoS / API credit burn (matches consensus_query)
    MAX_INPUT_SIZE = 500_000  # 500KB
    if len(prompt) > MAX_INPUT_SIZE or len(context) > MAX_INPUT_SIZE:
        return [TextContent(type="text", text=json.dumps({"status": "unavailable", "reason": "Input exceeds size limit (500KB max)"}))]

    responses = await dispatch_all(state.external_providers, prompt, context, state.external_config.timeout_seconds)

    models_responded = sum(1 for r in responses if r.error is None)
    models_queried = len(responses)

    if models_responded == models_queried:
        status = "available"
    elif models_responded > 0:
        status = "partial"
    else:
        status = "error"

    result = {
        "status": status,
        "models_queried": models_queried,
        "models_responded": models_responded,
        "reviews": [
            {
                "provider": r.provider,
                "model_id": r.model_id,
                "content": r.content,
                "latency_ms": r.latency_ms,
                "error": r.error,
            }
            for r in responses
        ],
    }

    return [TextContent(type="text", text=json.dumps(result))]


async def main():
    initialize()
    init_options = InitializationOptions(
        server_name="crucible-consensus",
        server_version="1.0.0",
        capabilities=server.get_capabilities(
            notification_options=NotificationOptions(),
            experimental_capabilities=None,
        ),
    )
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, init_options)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
