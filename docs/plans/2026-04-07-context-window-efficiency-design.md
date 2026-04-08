---
ticket: "#108"
title: "Context window efficiency: session activity index and compaction recovery"
date: "2026-04-07"
source: "spec"
---

# Context Window Efficiency: Session Activity Index and Compaction Recovery

## Overview

Two-pillar enhancement to Crucible's resilience across conversation compactions:

1. **Session Activity Index** -- hook-based logging of key session events into a persistent, searchable index on disk. Provides durable session history that survives any compaction layer.
2. **Compaction Recovery Enhancement** -- a `/recall` skill that queries the session index on demand, plus improvements to how skills recover state after auto-compaction.

**What is NOT in scope:** Output sandboxing. Claude Code's native microcompaction already handles this (offloads bulky tool outputs to disk with a hot tail of recent results). See `skills/shared/claude-code-internals.md` for details.

## Problem Statement

### What Gets Lost Today

Crucible's pipeline skills (build, debugging, spec, siege, quality-gate) persist critical state to disk via CSBs, handoff manifests, pipeline-status.md, and skill-specific scratch directories. This works well for **pipeline state recovery** -- the orchestrator can reconstruct what phase it's in, what tasks are pending, and what decisions were made.

What it does NOT recover:

1. **Session-wide event history.** A build run creates dozens of events (file edits, git commits, test runs, errors, decisions) that are useful context for later reasoning. After compaction, only the 5-entry Recent Events buffer in pipeline-status.md survives. The full event stream is gone.
2. **Cross-skill continuity.** If a user runs `/build`, then `/debugging`, then asks "what did I change today?", there is no unified view. Each skill's scratch directory is isolated.
3. **Ad-hoc recall.** A user mid-session who asks "what error did I get earlier?" or "which files did I edit in the first wave?" has no retrieval mechanism. The model must either remember (pre-compaction) or guess (post-compaction).

### Why Hooks

Claude Code fires hooks at well-defined points in its lifecycle. The relevant hook events for this design:

- **PreToolUse / PostToolUse** -- fires before/after every tool invocation. This is where we observe file edits, bash commands, git operations.
- **PreCompact / PostCompact** -- fires before/after manual `/compact`. Auto-compaction does NOT fire these hooks (it fires internally without hook integration). This limits hook-based compaction interception to manual compaction only.

The hook mechanism is configured in `.claude/settings.json` (project-level) or `~/.claude/settings.json` (user-level). Hooks are shell commands that receive event data on stdin as JSON and can return JSON on stdout to modify behavior.

### Constraint: Auto-Compaction Has No Hooks

Auto-compaction (the reactive compaction that fires when context fills) does NOT fire PreCompact/PostCompact hooks. Only manual `/compact` does. This is a critical constraint:

- We cannot intercept auto-compaction with hooks.
- We must design recovery to work WITHOUT a pre-compaction hook firing.
- The Session Activity Index must be written continuously (not just at compaction time), because we won't get a warning before auto-compaction.

This means the Session Activity Index is the primary recovery mechanism, not hooks. Hooks are a bonus for manual compaction scenarios.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Claude Code Session                     │
│                                                          │
│  PostToolUse hook ──→ Session Activity Index (disk)      │
│       │                     │                            │
│       │                     ▼                            │
│       │            ~/.claude/projects/<hash>/             │
│       │              memory/session-index/                │
│       │                <session-id>/                      │
│       │                  events.jsonl                     │
│       │                  summary.md                       │
│       │                                                  │
│  /recall skill ──→ reads events.jsonl ──→ returns        │
│                    relevant history to context            │
│                                                          │
│  CSB emission ──→ includes session-index path            │
│                   in Scratch State section                │
│                                                          │
│  Post-compaction ──→ skill reads summary.md              │
│    recovery          + recent events.jsonl               │
└─────────────────────────────────────────────────────────┘
```

### Components

1. **PostToolUse Hook** (`hooks/session-index.sh`): Shell script invoked after every tool use. Filters for significant events, appends structured entries to `events.jsonl`.
2. **Session Activity Index**: JSONL file at a persistent path. Each entry is a structured event with timestamp, event type, and payload.
3. **Summary Writer**: Periodic summarization of the event stream into `summary.md` -- a rolling narrative that skills can inject post-compaction.
4. **`/recall` Skill**: User-facing skill that queries the index by keyword, time range, or event type. Returns relevant history formatted for context injection.
5. **CSB Integration**: Existing CSB Scratch State section includes the session index path so post-compaction recovery can find it.

## Session Activity Index Design

### Storage Location

```
~/.claude/projects/<project-hash>/memory/session-index/<session-id>/
  events.jsonl      # append-only event log
  summary.md        # rolling narrative summary (overwritten)
```

**Session ID**: The session-id from the Claude Code conversation (available in the environment or derivable from the conversation). If unavailable, use a timestamp-based ID (Unix epoch seconds) matching the dispatch convention's session ID pattern.

**Cleanup**: At session start, delete session-index directories older than 7 days. This prevents unbounded growth. Active sessions are never cleaned (identified by modification time within the last 24 hours).

### Event Schema

Each line in `events.jsonl`:

```json
{
  "ts": "2026-04-07T14:30:00Z",
  "seq": 1,
  "type": "file_edit",
  "summary": "Modified src/auth/middleware.ts: added rate limiting",
  "detail": {
    "file": "src/auth/middleware.ts",
    "tool": "Edit"
  }
}
```

**Fields:**
- `ts` -- ISO-8601 timestamp
- `seq` -- monotonically increasing sequence number within the session
- `type` -- event type enum (see below)
- `summary` -- one-line human-readable summary, max 120 chars
- `detail` -- type-specific payload, max 500 chars total

### Event Types

Events are categorized by signal-to-noise value. Only high-value events are indexed:

| Type | Source | What It Captures |
|------|--------|------------------|
| `file_edit` | PostToolUse (Edit, Write) | File path + one-line description of change |
| `file_create` | PostToolUse (Write) | New file path + purpose |
| `git_commit` | PostToolUse (Bash containing `git commit`) | Commit SHA + message |
| `git_checkout` | PostToolUse (Bash containing `git checkout/switch`) | Branch change |
| `test_run` | PostToolUse (Bash containing test runner patterns) | Pass/fail + count |
| `error` | PostToolUse (Bash with non-zero exit) | Command + error summary |
| `decision` | Explicit skill emission | Decision ID + choice + reasoning |
| `phase_change` | Explicit skill emission | Skill + old phase + new phase |
| `skill_start` | Skill invocation detection | Skill name + goal |
| `skill_end` | Skill completion detection | Skill name + outcome |

**Noise filtering**: The hook does NOT index:
- Read-only tool uses (Read, Glob, Grep) -- too frequent, low signal
- Bash commands that are pure reads (cat, ls, find, echo)
- Tool uses that produce no meaningful state change

### PostToolUse Hook Implementation

The hook is a shell script that:

1. Reads JSON from stdin (Claude Code provides tool name, arguments, and result)
2. Classifies the event type based on tool name and arguments
3. If the event is indexable, formats a JSONL entry and appends to `events.jsonl`
4. Exits with code 0 (hooks must not block or fail the tool use)

```bash
#!/usr/bin/env bash
# hooks/session-index.sh
# PostToolUse hook for session activity indexing
# Receives: {"tool": "Edit", "args": {...}, "result": {...}} on stdin
# Must exit 0 -- never block tool execution

set -euo pipefail

# Read input
INPUT=$(cat)

# ... classify and append to events.jsonl ...
```

The hook must be fast (<100ms). It must never fail in a way that blocks tool execution. All errors are swallowed (logged to a debug file if needed, but never surfaced to the user or model).

**Configuration** (in `.claude/settings.json`):
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

### Summary Writer

The summary is a condensed narrative written to `summary.md`. It provides a quick-read overview that skills can inject into context after compaction.

**When to write**: After every 20 events appended to `events.jsonl`, OR when a `phase_change` or `skill_end` event is logged. The hook itself triggers the summary write by checking the event count.

**Format**:
```markdown
# Session Summary
**Session:** <session-id>
**Started:** <first event timestamp>
**Last Updated:** <latest event timestamp>
**Events:** <total count>

## Activity Timeline
- [14:30] Started /build for auth rate limiting feature
- [14:32] Created design doc at docs/plans/auth-rate-limit.md
- [14:45] Phase 1 complete, 3 files modified
- [14:52] Test suite: 42 passed, 0 failed
- [15:10] Compaction occurred, recovered from session index
...

## Files Modified
- src/auth/middleware.ts (rate limiting logic)
- src/auth/middleware.test.ts (rate limiting tests)
- docs/plans/auth-rate-limit.md (design doc)

## Key Decisions
- DEC-1: Chose token bucket over sliding window (lower memory footprint)
- DEC-2: 100 req/min default, configurable via env var

## Errors Encountered
- [14:48] Test failure: middleware.test.ts line 42 — fixed in next edit
```

The summary is capped at 2000 tokens. When it exceeds this, older timeline entries are compressed (keeping files modified and key decisions intact).

## /recall Skill Design

### Purpose

User-facing skill for querying session history. Also usable by other skills for programmatic retrieval.

**Invocation:**
```
/recall                          # show recent activity summary
/recall what files did I edit    # keyword search
/recall errors                   # filter by event type
/recall last 30 minutes          # time-range filter
```

### Behavior

1. **No arguments**: Return the full `summary.md` content
2. **Keyword search**: Grep `events.jsonl` for matching entries, return up to 20 most recent matches with context
3. **Type filter**: Filter by event type (file_edit, error, decision, etc.)
4. **Time range**: Filter events within a time window

### Output Format

```markdown
## Recall: [query description]
**Showing:** [N] events from [time range]

| Time | Type | Summary |
|------|------|---------|
| 14:30 | file_edit | Modified src/auth/middleware.ts: added rate limiting |
| 14:32 | file_create | Created docs/plans/auth-rate-limit.md |
| ... | ... | ... |
```

### Skill File Structure

```
skills/recall/
  SKILL.md           # Skill definition
```

The skill is a simple orchestrator that reads the session index and formats output. No subagent dispatch. No dispatch convention needed.

### Integration with Pipeline Skills

Pipeline skills (build, debugging, etc.) can invoke `/recall` internally after compaction to supplement their CSB-based recovery:

1. Read CSB / pipeline-status.md / handoff manifest (existing recovery)
2. Read `summary.md` from the session index (new -- provides narrative context the CSB lacks)
3. Optionally query specific events via `/recall` for targeted context

This is additive -- it does not replace existing recovery mechanisms.

## Compaction Recovery Enhancement

### Current Recovery Flow (Unchanged)

Skills today recover via:
1. Read `## Compression State` from `pipeline-status.md`
2. Check for handoff manifests in scratch directory
3. Read skill-specific state files (task lists, hypothesis logs, etc.)
4. Emit a new CSB into the conversation

### Enhanced Recovery Flow (New)

After the existing recovery steps, add:

4.5. **Read session index summary**: Read `summary.md` from `~/.claude/projects/<hash>/memory/session-index/<session-id>/summary.md`. If it exists, include the Activity Timeline, Files Modified, and Key Decisions sections in the post-compaction narration.

4.6. **Include session index path in CSB**: The Scratch State section of every CSB now includes the session index path:
```
Scratch State:
- Location: [skill-specific scratch path]
- Session Index: ~/.claude/projects/<hash>/memory/session-index/<session-id>/
- Recovery: [existing recovery instructions]
```

This ensures that even if the session-id is lost from context, the CSB carries the path to the index.

### Session ID Recovery

After compaction, the session-id might be lost from context. Recovery strategy:

1. **From CSB**: The Scratch State section includes the session index path (new).
2. **From pipeline-status.md**: Could include session-id in the status file header.
3. **From filesystem**: List `~/.claude/projects/<hash>/memory/session-index/` and pick the most recently modified directory.

Option 3 is the fallback -- it always works but may pick the wrong session if multiple are active (unlikely for a single user).

## Integration with Existing CSB Patterns

### No CSB Format Changes

The CSB format (`===COMPRESSION_STATE=== ... ===END_COMPRESSION_STATE===`) is not modified. The only addition is including the session index path in the Scratch State section, which is already a free-form field.

### No New CSB Triggers

Per the recent CSB frequency reduction (#140), we do NOT add new CSB emission triggers. The session index is a passive system -- it writes to disk continuously and is read on demand. It does not emit anything into the conversation context.

### Relationship to Pipeline Status

`pipeline-status.md` remains the primary recovery artifact for pipeline skills. The session index is a supplementary source of narrative context. Skills that don't use pipeline-status.md (standalone tools, one-off commands) benefit from the session index without needing any pipeline infrastructure.

## Decision Log

### D1: Continuous Logging vs. Pre-Compaction Snapshot

**Decision:** Continuous logging via PostToolUse hook.

**Alternatives considered:**
- Pre-compaction snapshot (write everything at compaction time)

**Rationale:** Auto-compaction does NOT fire hooks. If we only wrote state at compaction time, we'd miss all auto-compaction events -- which are the most common compaction type in long-running pipelines. Continuous logging ensures the index is always up-to-date regardless of which compaction layer fires.

**Confidence:** High. This is a hard constraint from Claude Code's architecture.

### D2: JSONL vs. SQLite vs. Flat Markdown

**Decision:** JSONL for events, Markdown for summary.

**Alternatives considered:**
- SQLite database (richer queries, but requires sqlite3 binary and is harder to inspect)
- Flat markdown log (human-readable but hard to parse programmatically)

**Rationale:** JSONL is append-only (crash-safe), grep-searchable, parseable by shell scripts and Python, and human-inspectable. It matches the manifest.jsonl pattern already used in dispatch convention. SQLite adds a dependency and complicates debugging. Markdown is hard to filter programmatically.

**Confidence:** High.

### D3: Hook-Based vs. Skill-Embedded Logging

**Decision:** Hook-based logging via PostToolUse.

**Alternatives considered:**
- Each skill explicitly emits log entries at interesting points

**Rationale:** Hook-based logging captures events from ALL tool uses, including those outside skill pipelines (ad-hoc user commands, one-off edits). Skill-embedded logging only captures events within pipeline skills, missing the majority of session activity. Hooks also ensure logging happens even if a skill forgets to emit.

**Downside:** Hooks see raw tool data, not semantic skill data. The `decision` and `phase_change` event types require explicit emission from skills (the hook cannot infer these). This is a hybrid approach: hooks capture tool-level events automatically, skills emit semantic events explicitly.

**Confidence:** High.

### D4: /recall as Separate Skill vs. Integrated into Existing Skills

**Decision:** Separate `/recall` skill.

**Alternatives considered:**
- Integrate recall into each pipeline skill's compaction recovery

**Rationale:** A standalone skill is usable outside pipelines (user asks "what did I do today?"). Pipeline skills can invoke it internally when they need supplementary context. Separation of concerns: the session index is infrastructure, not pipeline-specific.

**Confidence:** High.

### D5: Summary Token Budget

**Decision:** 2000-token cap on summary.md.

**Alternatives considered:**
- Uncapped (risk bloating post-compaction context injection)
- 500 tokens (too compressed to be useful)

**Rationale:** Post-compaction context injection needs to be small enough to not waste recovered context headroom, but large enough to carry meaningful narrative. 2000 tokens is approximately 1 page of structured text -- enough for a timeline, file list, and decision list. The CSB itself is ~150-250 tokens, so the combined recovery payload is ~2200 tokens, well within the typical post-compaction headroom.

**Confidence:** Medium. May need tuning based on real-world usage. The cap is easy to adjust.

### D6: Event Noise Filtering Strategy

**Decision:** Allowlist of high-value event types, everything else dropped.

**Alternatives considered:**
- Log everything, filter at query time
- Log everything with severity levels

**Rationale:** A long session can produce thousands of tool uses. Logging all of them would create a large JSONL file that's slow to search and wasteful to summarize. The allowlist (file_edit, git_commit, test_run, error, decision, phase_change, skill_start, skill_end) captures the events that are actually useful for session recall. Read-only operations (Grep, Read, Glob) are too frequent and too low-signal to index.

**Confidence:** Medium. The allowlist may need expansion based on usage. Adding a new event type is a one-line change in the hook.
