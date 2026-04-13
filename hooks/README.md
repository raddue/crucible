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

## Gate Ledger Guard

External enforcement hook for the build pipeline's gate ledger. Blocks unauthorized `Status: PASS` writes to `build-gate-ledger.md` when no matching quality-gate verdict marker exists. This is the mechanical enforcement layer — Claude cannot bypass it because it runs as an external process.

### Setup

Add the following to your `.claude/settings.json` (project-level) or `~/.claude/settings.json` (user-level):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write",
        "command": "bash hooks/gate-ledger-guard.sh",
        "timeout": 500
      }
    ]
  }
}
```

> **Note:** Verify that the `matcher` field is supported in your Claude Code version. If not, remove it — the hook itself checks the tool name from stdin JSON and exits 0 for non-Write operations.

### Verification

After enabling the hook, test it by attempting to write a PASS status to a gate ledger without a verdict marker. The hook should block with:

```
BLOCKED: Cannot write PASS to gate ledger — no matching verdict marker found.
```

### How It Works

1. **PreToolUse hook** (`gate-ledger-guard.sh`) fires before every Write tool call
2. Checks if the write target is `build-gate-ledger.md` — exits 0 (allows) for all other files
3. Compares incoming content against the existing file to detect new `Status: PASS` entries per phase
4. If a new PASS is detected, cross-checks against verdict markers in `~/.claude/projects/<hash>/memory/quality-gate/`:
   - PipelineID must match between the ledger content and the verdict marker
   - Verdict must be `PASS`
   - Phase field must match (Phase 1 = "design", Phase 2 = "plan", Phase 4 = "code")
5. Blocks Phase 3 PASS writes (Phase 3 uses COMPLETE, not PASS)
6. **Graceful degradation:** On any infrastructure failure (missing `jq`, missing directories, malformed JSON), exits 0 to avoid blocking legitimate work

### Testing

Run the test suite:

```bash
bash hooks/tests/test-gate-ledger-guard.sh
```

11 test cases covering: non-ledger writes, non-PASS writes, valid markers, missing markers, PipelineID mismatch, missing jq, missing directories, malformed JSON, COMPLETE writes, wrong-phase markers, and Phase 3 PASS blocking.

### Dependencies

- `jq` must be installed and on the PATH (gracefully degrades if missing)
