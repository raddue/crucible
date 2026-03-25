# crucible-consensus

Multi-model consensus MCP server for Crucible. Dispatches prompts to multiple LLM providers in parallel and synthesizes their responses for high-stakes quality decisions.

## Prerequisites

- Python 3.10+
- API keys for at least 2 supported providers

## Supported Providers

| Provider | SDK | API Key Env Var |
|----------|-----|----------------|
| Anthropic (Claude) | `anthropic` | `ANTHROPIC_API_KEY` |
| Google (Gemini) | `google-genai` | `GOOGLE_API_KEY` |

OpenAI and DeepSeek support is planned.

## Installation

```bash
cd mcp-servers/crucible-consensus
pip install -r requirements.txt
```

## Configuration

Create `.claude/consensus-config.yaml` in your project root. See `skills/consensus/consensus-config-example.yaml` for an annotated example.

Minimal config:
```yaml
consensus:
  enabled: true
  min_models: 2
  models:
    - provider: anthropic
      model: claude-sonnet-4-20250514
      api_key_env: ANTHROPIC_API_KEY
    - provider: google
      model: gemini-2.5-pro
      api_key_env: GOOGLE_API_KEY
```

## Running

### With Claude Code

Add to your Claude Code MCP settings (`.claude/settings.json` or global):

```json
{
  "mcpServers": {
    "crucible-consensus": {
      "command": "python3",
      "args": ["mcp-servers/crucible-consensus/server.py"],
      "env": {
        "PROJECT_DIR": "/path/to/your/project"
      }
    }
  }
}
```

### Standalone (for testing)

```bash
export PROJECT_DIR=/path/to/your/project
export ANTHROPIC_API_KEY=your-key
export GOOGLE_API_KEY=your-key
python3 server.py
```

## Running Tests

```bash
cd mcp-servers/crucible-consensus
python3 -m pytest tests/ -v
```

All tests use mocked API responses — no live API keys needed.

## How It Works

1. On startup, reads config and initializes provider adapters
2. Exposes `consensus_query` tool via MCP protocol
3. On each call: dispatches to all providers in parallel, aggregates responses, returns structured synthesis
4. Graceful degradation: if providers fail, returns `status: "unavailable"` and skills fall back to single-model behavior

## Consensus Modes

- **review** — Adversarial review aggregation (used by quality-gate red-team)
- **verdict** — Binary/ternary decision aggregation (used by quality-gate stagnation judge)
- **investigate** — Exploratory analysis aggregation (used by design Challenger)

See `skills/consensus/SKILL.md` for full documentation.
