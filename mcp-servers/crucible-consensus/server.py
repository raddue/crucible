"""Crucible Consensus MCP Server — multi-model consensus for high-stakes decisions."""

import json
import os
import sys
import logging
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from config import load_config, ConfigError, ConsensusConfig
from providers import create_provider, dispatch_all
from aggregator import aggregate, ConsensusResult

logger = logging.getLogger("crucible-consensus")
logging.basicConfig(stream=sys.stderr, level=logging.INFO)

server = Server("crucible-consensus")

# Global state initialized on startup
_config: ConsensusConfig | None = None
_providers: list = []
_project_dir: str = ""


def initialize():
    """Load config and create providers on startup."""
    global _config, _providers, _project_dir
    _project_dir = os.environ.get("PROJECT_DIR", os.getcwd())
    _config = load_config(_project_dir)

    if not _config.enabled:
        logger.info("Consensus is disabled in config")
        return

    _providers = []
    for model_config in _config.models:
        try:
            provider = create_provider(model_config)
            _providers.append((provider, model_config))
            logger.info(f"Initialized {model_config.provider}/{model_config.model_id}")
        except Exception as e:
            logger.warning(f"Failed to initialize {model_config.provider}/{model_config.model_id}: {e}")

    logger.info(f"Consensus server ready: {len(_providers)} providers, min_models={_config.min_models}")


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
                },
                "required": ["prompt", "context", "mode"],
            },
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name != "consensus_query":
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

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


async def main():
    initialize()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
