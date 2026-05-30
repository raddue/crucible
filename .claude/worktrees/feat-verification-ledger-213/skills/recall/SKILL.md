---
name: recall
description: Query session history from the persistent activity index. Returns event logs, summaries, and filtered views that survive context compaction.
origin: crucible
---

# Recall

Query the session activity index for event history, file change logs, decisions, and errors. The session index is written continuously by the PostToolUse hook and persists across compaction events.

**Skill type:** Rigid -- follow exactly, no shortcuts.

**Execution model:** Direct execution by the orchestrator. No subagent dispatch. No Agent/Task tool needed.

**Announce at start:** Output `[recall] Querying session activity index...` before any processing.

## Session Index Discovery

The session index lives at:
```
~/.claude/projects/<project-hash>/memory/session-index/<session-id>/
  events.jsonl      # append-only event log
  summary.md        # rolling narrative summary
```

**Discover the index path:**

1. Compute project hash: `echo -n "<absolute project dir>" | sha256sum | cut -c1-16`
2. Glob for `~/.claude/projects/<hash>/memory/session-index/*/events.jsonl`
3. Pick the most recently modified `events.jsonl` — its parent directory is the active session index
4. If no session index exists, return:
   > No session index found. Enable session indexing by adding the PostToolUse hook — see `hooks/README.md`.

**Tool constraint:** Use Read and Glob tools for session-index access. Do not use Bash to access `~/.claude/` paths (safety hooks block this).

## Query Modes

### No Arguments: `/recall`

Return the full contents of `summary.md`. If `summary.md` does not exist but `events.jsonl` does, read the last 20 entries from `events.jsonl` and format them as a table.

### Keyword Search: `/recall what files did I edit`

1. Read `events.jsonl` using the Read tool
2. Search all entries for lines containing any of the query keywords (case-insensitive match on the `summary` and `detail` fields)
3. Return up to 20 most recent matching entries, formatted as a table

### Type Filter: `/recall errors`, `/recall decisions`, `/recall edits`

Map common words to event types:

| Query Word | Event Type(s) |
|-----------|---------------|
| errors | error |
| decisions | decision |
| edits, files | file_edit, file_create |
| commits | git_commit |
| tests | test_run |
| phases | phase_change |

Filter `events.jsonl` to matching types. Return up to 20 most recent entries.

### Time Range: `/recall last 30 minutes`, `/recall last hour`

Parse the time expression:
- "last N minutes" -> filter events with `ts` within the last N minutes
- "last N hours" / "last hour" -> filter events within the last N hours
- "today" -> filter events from today (UTC)

Return up to 20 most recent matching entries.

## Output Format

For summary mode (no arguments), return the raw `summary.md` content.

For filtered/search results, format as:

```markdown
## Recall: [query description]
**Showing:** [N] events from [time range or filter description]

| Time | Type | Summary |
|------|------|---------|
| 14:30 | file_edit | Modified src/auth/middleware.ts: added rate limiting |
| 14:32 | file_create | Created docs/plans/auth-rate-limit.md |
| ... | ... | ... |
```

Cap output at 20 entries. If more entries match, note the total: `*(showing 20 of 47 matching events)*`.

## Event Schema Reference

Each line in `events.jsonl` follows this schema (see `skills/shared/session-index-convention.md` for full details):

```json
{
  "ts": "2026-04-07T14:30:00Z",
  "seq": 1,
  "type": "file_edit | file_create | git_commit | git_checkout | test_run | error | decision | phase_change | skill_start | skill_end",
  "summary": "One-line human-readable summary, max 120 chars",
  "detail": { "type-specific payload" }
}
```

## Integration with Pipeline Skills

Pipeline skills can invoke `/recall` internally after compaction to supplement CSB-based recovery:

1. **Existing recovery:** Read CSB / pipeline-status.md / handoff manifest
2. **Supplementary:** Read `summary.md` from the session index for narrative context
3. **Targeted:** Query specific events via `/recall` for focused context (e.g., `/recall errors` to recover error history)

This is additive -- it does not replace existing recovery mechanisms.

## Red Flags

- Using Bash to access `~/.claude/` paths (use Read/Glob tools instead)
- Treating session index as authoritative over CSB state (session index is supplementary narrative, CSB is authoritative state)
- Returning more than 20 events in a single recall (wastes context budget)
- Failing silently when the session index is missing (must return a helpful message pointing to hook setup)
