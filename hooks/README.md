# Crucible Hooks

Hook scripts for Claude Code's lifecycle events.

## Session Activity Index

The session activity index continuously logs high-value session events (file edits, git operations, test runs, errors) to a persistent JSONL file on disk. This index survives context compaction and powers the `/recall` skill.

### Setup

Add the following to your `.claude/settings.json` (project-level) or `~/.claude/settings.json` (user-level):

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "command": "bash hooks/session-index.sh",
        "timeout": 500
      }
    ]
  }
}
```

### Verification

After enabling the hook, perform a file edit or git commit. Then check for the session index:

```bash
ls ~/.claude/projects/*/memory/session-index/*/events.jsonl
```

If the file exists and contains JSON entries, the hook is working.

### How It Works

1. **PostToolUse hook** (`session-index.sh`) fires after every tool use
2. Classifies the event: file edits, file creates, git commits, git checkouts, test runs, errors
3. Skips read-only operations (Read, Glob, Grep, cat, ls, etc.) to avoid noise
4. Appends a structured JSONL entry to `events.jsonl`
5. Every 20 events (or on phase changes), triggers the summary writer

The **summary writer** (`session-summary.sh`) reads `events.jsonl` and produces a rolling `summary.md` capped at ~2000 tokens. Pipeline skills read this summary during compaction recovery.

### Storage Location

```
~/.claude/projects/<project-hash>/memory/session-index/<session-id>/
  events.jsonl      # append-only event log
  summary.md        # rolling narrative summary
  outbox.jsonl      # temporary: semantic events from skills (drained by hook)
```

- **Project hash:** SHA-256 of the project directory, truncated to 16 chars (matches checkpoint convention)
- **Session ID:** `$CLAUDE_SESSION_ID` env var, or the most recent session directory, or a new epoch-based ID
- **Retention:** Session directories older than 7 days are cleaned up automatically

### Semantic Events (Outbox Pattern)

Pipeline skills can emit semantic events (decisions, phase changes) by writing to `outbox.jsonl` in the session index directory. The hook drains the outbox into `events.jsonl` on its next invocation. See `skills/shared/session-index-convention.md` for the event schema and examples.

### Disabling

Remove the `PostToolUse` entry from your `settings.json`. Existing session index data remains on disk and can be queried with `/recall` until it ages out (7-day retention).

### Dependencies

- `jq` must be installed and on the PATH
- `sha256sum` (standard on Linux, available via coreutils on macOS)
