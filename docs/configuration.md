# Configuration (Claude Code)

These settings are specific to Claude Code. Other platforms have equivalent configuration — see [PLATFORMS.md](../PLATFORMS.md) for details.

## Run mode

**Auto mode** (recommended for autonomous pipelines) — Crucible is designed for long-running autonomous pipelines (build, debugging, spec, migrate) that complete complex development tasks without user intervention. Auto mode lets Claude execute tool calls without per-action prompts while still confirming destructive operations (deletes, force-pushes, shared-system writes). It supersedes earlier guidance that recommended `--dangerously-skip-permissions`. Pair auto mode with a safety hook or other failsafe if your environment warrants extra protection — see [Anthropic's hooks documentation](https://docs.anthropic.com/en/docs/claude-code/hooks) for setup guidance.

## Environment variables

**`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`** — Required for build's team-based parallel execution. Skills degrade gracefully without it — independent tasks run sequentially instead of in parallel. This applies to all platforms where parallel subagent dispatch is not available.

**`CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=50`** — Performance recommendation for long-running pipelines. Triggers compaction earlier to preserve context for complex multi-phase work. Pipeline skills emit structured Compression State Blocks at checkpoint boundaries to guide the compactor on what to preserve.

## Session Activity Index (hooks)

Crucible includes PostToolUse hooks (`hooks/session-index.sh`, `hooks/session-summary.sh`) that log session events for compaction recovery and the `/recall` skill. To enable, add to your `.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      { "command": "/path/to/crucible/hooks/session-index.sh" },
      { "command": "/path/to/crucible/hooks/session-summary.sh" }
    ]
  }
}
```

See `hooks/README.md` for details on storage layout, the outbox pattern, and hook dependencies.

## Build Routing Advisor (hooks)

Optional PreToolUse hook (`hooks/build-routing-advisor.sh`) that warns — without blocking — when a raw-agent dispatch looks like it should have gone through `/build`, `/spec`, `/debugging`, or `/migrate`. Warn-only and tier-aware (matches Claude Code's skill-trigger vocabulary). Enable via `.claude/settings.json` with a `PreToolUse` matcher on `Agent`. The post-merge reconciler (`hooks/tests/tools/build-routing-reconcile.sh`) provides a read-only audit of dispatches in recent session index data.

## External Model Review (MCP)

For independent code review from non-Anthropic models (Gemini, OpenAI, etc.), configure `.claude/consensus-config.yaml` using the example at [consensus-config-example.yaml](../skills/consensus/consensus-config-example.yaml) and register the MCP server in `.mcp.json`. See the consensus and external review skill descriptions in [skills.md](skills.md) for details.
