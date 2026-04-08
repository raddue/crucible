---
version: 1
---

# Session Index Convention

> Defines how pipeline skills emit semantic events to the session activity index.
> The PostToolUse hook captures tool-level events (file edits, git ops, errors) automatically.
> This convention covers **semantic events** that only the skill can provide: decisions, phase changes, skill lifecycle.

## Outbox Pattern

Skills cannot write directly to `events.jsonl` (it lives under `~/.claude/` which safety hooks block from Bash access). Instead, skills write to an **outbox file** that the PostToolUse hook drains on its next invocation.

### How It Works

1. **Skill computes the outbox path:**
   ```
   ~/.claude/projects/<project-hash>/memory/session-index/<session-id>/outbox.jsonl
   ```
   - Project hash: `echo -n "$PWD" | sha256sum | cut -c1-16` (matches checkpoint convention)
   - Session ID: from the CSB Scratch State `Session Index:` field, or glob for the most recent session directory

2. **Skill appends an entry** to `outbox.jsonl` using the Write tool (read existing content, append new line, write back). If the file does not exist, create it with the single entry.

3. **On next PostToolUse hook invocation**, the hook reads `outbox.jsonl`, appends all entries to `events.jsonl`, and deletes `outbox.jsonl`.

### Latency

Outbox entries appear in `events.jsonl` within one tool use (the next PostToolUse hook fires after whatever tool the skill uses next). This latency is acceptable -- semantic events are retrospective context, not real-time signals.

## Event Schema

Every entry (in both `events.jsonl` and `outbox.jsonl`) follows this schema:

```json
{
  "ts": "2026-04-07T14:30:00Z",
  "seq": 0,
  "type": "<event-type>",
  "summary": "One-line human-readable summary, max 120 chars",
  "detail": { "<type-specific payload, max 500 chars serialized>" }
}
```

**Note on `seq`:** Outbox entries should set `seq` to `0`. The hook assigns the correct sequence number when draining. Skills do not need to track the sequence counter.

## Event Types

### Tool-Level Events (captured automatically by hook)

| Type | Source | What It Captures |
|------|--------|------------------|
| `file_edit` | PostToolUse (Edit, Write) | File path + tool name |
| `file_create` | PostToolUse (Write, new file) | New file path + tool name |
| `git_commit` | PostToolUse (Bash + `git commit`) | Commit SHA + message |
| `git_checkout` | PostToolUse (Bash + `git checkout/switch`) | Branch name |
| `test_run` | PostToolUse (Bash + test runner) | Command + result summary |
| `error` | PostToolUse (Bash, non-zero exit) | Command + error message |

### Semantic Events (emitted by skills via outbox)

| Type | When to Emit | Detail Fields |
|------|-------------|---------------|
| `decision` | When the skill makes a significant choice | `{id: "DEC-N", choice: "...", reasoning: "..."}` |
| `phase_change` | At phase transitions | `{skill: "build", from: "2", to: "3"}` |
| `skill_start` | At the beginning of a skill invocation | `{skill: "build", goal: "..."}` |
| `skill_end` | At the end of a skill invocation | `{skill: "build", outcome: "success|failure|escalated"}` |

## Examples

### Emitting a decision event

After making a significant design or implementation choice, write to the outbox:

```json
{"ts":"2026-04-07T14:30:00Z","seq":0,"type":"decision","summary":"DEC-1: Chose token bucket over sliding window","detail":{"id":"DEC-1","choice":"token bucket","reasoning":"Lower memory footprint for per-user tracking"}}
```

### Emitting a phase change event

At phase transitions (e.g., build Phase 2 -> Phase 3):

```json
{"ts":"2026-04-07T15:00:00Z","seq":0,"type":"phase_change","summary":"Build: Phase 2 -> Phase 3 (Execute)","detail":{"skill":"build","from":"2","to":"3"}}
```

### Emitting skill lifecycle events

At the start and end of a skill invocation:

```json
{"ts":"2026-04-07T14:00:00Z","seq":0,"type":"skill_start","summary":"Starting /build for auth rate limiting","detail":{"skill":"build","goal":"Implement auth rate limiting middleware"}}
```

```json
{"ts":"2026-04-07T16:00:00Z","seq":0,"type":"skill_end","summary":"/build complete: auth rate limiting shipped","detail":{"skill":"build","outcome":"success"}}
```

## Session Index Path Discovery

Skills discover the session index path via:

1. **CSB Scratch State** (preferred): The `Session Index:` field in the Compression State Block carries the full path.
2. **Filesystem glob** (fallback): Glob `~/.claude/projects/*/memory/session-index/*/events.jsonl` and pick the most recently modified.

## Integration with Summary Writer

The summary writer (`hooks/session-summary.sh`) is triggered automatically by the hook after every 20th event or after `phase_change` / `skill_end` events. Skills do not need to invoke the summary writer directly.

## Backward Compatibility

Session indexing is opt-in. If the PostToolUse hook is not configured:
- No `events.jsonl` or `summary.md` will exist
- The outbox will never be drained (entries accumulate harmlessly)
- Skills that attempt to read the session index should degrade gracefully (skip the session index step, continue with CSB-based recovery)
