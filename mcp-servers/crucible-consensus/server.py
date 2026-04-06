"""Crucible Consensus MCP Server — multi-model consensus for high-stakes decisions."""

import json
import os
import sys
import logging
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from config import load_config, ConfigError, ConsensusConfig, ExternalReviewConfig, load_external_review_config
from providers import create_provider, dispatch_all, ModelResponse
from aggregator import aggregate, ConsensusResult

logger = logging.getLogger("crucible-consensus")
logging.basicConfig(stream=sys.stderr, level=logging.INFO)

server = Server("crucible-consensus")

# Global state initialized on startup
_config: ConsensusConfig | None = None
_providers: list = []
_project_dir: str = ""
_external_config: ExternalReviewConfig | None = None
_external_providers: list = []


def initialize():
    """Load config and create providers on startup."""
    global _config, _providers, _project_dir, _external_config, _external_providers
    _project_dir = os.environ.get("PROJECT_DIR", os.getcwd())

    # Load consensus config (optional — don't crash if missing)
    try:
        _config = load_config(_project_dir)
    except ConfigError as e:
        _config = None
        logger.warning(f"Consensus config not loaded: {e}")

    if _config is not None and not _config.enabled:
        logger.info("Consensus is disabled in config")

    if _config is not None and _config.enabled:
        _providers = []
        for model_config in _config.models:
            try:
                provider = create_provider(model_config)
                _providers.append((provider, model_config))
                logger.info(f"Initialized {model_config.provider}/{model_config.model_id}")
            except Exception as e:
                logger.warning(f"Failed to initialize {model_config.provider}/{model_config.model_id}: {e}")

        logger.info(f"Consensus server ready: {len(_providers)} providers, min_models={_config.min_models}")

    # Load external review config (may raise ConfigError on malformed config)
    try:
        _external_config = load_external_review_config(_project_dir)
    except ConfigError as e:
        _external_config = ExternalReviewConfig()
        logger.warning(f"External review config not loaded: {e}")
    _external_providers = []
    if _external_config.enabled and _external_config.models:
        for model_config in _external_config.models:
            try:
                provider = create_provider(model_config)
                _external_providers.append((provider, model_config))
                logger.info(f"External review: initialized {model_config.provider}/{model_config.model_id}")
            except Exception as e:
                logger.warning(f"External review: failed to initialize {model_config.provider}/{model_config.model_id}: {e}")
        logger.info(f"External review ready: {len(_external_providers)} providers")


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
    if _config is None:
        return [TextContent(type="text", text='{"status": "unavailable", "synthesis": "Consensus not configured"}')]

    if not _config.enabled:
        result = ConsensusResult(status="unavailable")
        return [TextContent(type="text", text=json.dumps(result.to_dict()))]

    prompt = arguments["prompt"]
    context = arguments["context"]
    mode = arguments["mode"]

    if mode not in ("review", "verdict", "investigate"):
        return [TextContent(type="text", text=f'{{"status": "unavailable", "synthesis": "Invalid mode: {mode}"}}')]

    # Check if this mode is enabled
    if not _config.modes.get(mode, True):
        result = ConsensusResult(status="unavailable")
        return [TextContent(type="text", text=json.dumps(result.to_dict()))]

    logger.info(f"Consensus query: mode={mode}, providers={len(_providers)}")

    # Dispatch to all providers in parallel
    responses = await dispatch_all(_providers, prompt, context, _config.timeout_seconds)

    # Inject additional external review responses if provided
    additional_responses = arguments.get("additional_responses")
    if additional_responses:
        for ar in additional_responses:
            try:
                responses.append(ModelResponse(
                    provider=ar["provider"],
                    model_id=ar["model_id"],
                    content=ar["content"],
                    latency_ms=ar["latency_ms"],
                ))
            except (KeyError, TypeError) as e:
                logger.warning(f"Skipping malformed additional_response: {e}")

    # Aggregate responses
    prompts_dir = str(Path(_project_dir) / "skills" / "consensus")
    result = await aggregate(
        responses=responses,
        prompt=prompt,
        context=context,
        mode=mode,
        config=_config,
        prompts_dir=prompts_dir,
    )

    logger.info(f"Consensus result: status={result.status}, responded={result.models_responded}/{result.models_queried}")

    return [TextContent(type="text", text=json.dumps(result.to_dict()))]


async def _handle_external_review(arguments: dict) -> list[TextContent]:
    if _external_config is None or not _external_config.enabled:
        return [TextContent(type="text", text=json.dumps({"status": "unavailable"}))]

    if not _external_providers:
        return [TextContent(type="text", text=json.dumps({"status": "unavailable"}))]

    # Per-skill toggle: if caller declares a skill, check whether it's enabled
    # Normalize hyphenated names to underscored to match config keys
    skill = (arguments.get("skill") or "").replace("-", "_") or None
    if skill and not _external_config.skills.get(skill, True):
        return [TextContent(type="text", text=json.dumps({"status": "unavailable", "reason": f"external review disabled for skill '{skill}'"}))]

    prompt = arguments["prompt"]
    context = arguments["context"]

    responses = await dispatch_all(_external_providers, prompt, context, _external_config.timeout_seconds)

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
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
