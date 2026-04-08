---
ticket: "#108"
title: "Context window efficiency: implementation plan"
date: "2026-04-07"
source: "spec"
---

# Context Window Efficiency: Implementation Plan

**Issue:** #108
**Date:** 2026-04-07

## Task Overview

8 implementation tasks across 3 waves. Wave 1 builds the session indexing infrastructure. Wave 2 creates the /recall skill and integrates with existing recovery. Wave 3 updates pipeline skills to consume the session index.

## Wave 1: Session Activity Index Infrastructure

### Task 1: Create PostToolUse hook script

**Complexity:** M

**Files:**
- `hooks/session-index.sh` (create)

**Approach:**
- Shell script that reads PostToolUse JSON from stdin
- Classifies events by tool name: Edit/Write -> file_edit/file_create, Bash with git patterns -> git_commit/git_checkout/test_run/error
- Computes session index path: `~/.claude/projects/<project-hash>/memory/session-index/<session-id>/`
- Project hash: derive from `$PWD` using `echo -n "$PWD" | sha256sum | cut -c1-16` (matches checkpoint convention)
- Session ID: use `$CLAUDE_SESSION_ID` env var if available, fall back to reading the most recent directory in the session-index folder, fall back to creating a new one from epoch seconds
- Appends JSONL entry to `events.jsonl` with: ts, seq (derived from line count), type, summary, detail
- Summary extraction: for Edit, use the file path; for Bash git commit, extract commit message; for Bash errors, capture first line of stderr
- Must complete in <100ms. No network calls. All errors swallowed (exit 0 always)
- Creates session directory on first event if it doesn't exist
- Stale cleanup: on first invocation per session, remove session-index directories with mtime >7 days

**Done when:**
- Hook script exists, is executable, and processes Edit/Write/Bash tool events
- events.jsonl entries are valid JSON, one per line
- Hook never blocks or errors (exit 0 on malformed input, missing dirs, etc.)
- Manual test: invoke hook with sample PostToolUse JSON, verify JSONL output

**Dependencies:** None

### Task 2: Create summary writer

**Complexity:** M

**Files:**
- `hooks/session-summary.sh` (create)

**Approach:**
- Called by session-index.sh after every 20th event or after phase_change/skill_end events
- Reads events.jsonl and produces summary.md
- Summary sections: Session metadata, Activity Timeline (last 30 events, one line each), Files Modified (deduplicated), Key Decisions (from decision-type events), Errors Encountered (from error-type events)
- Token budget enforcement: count characters (rough proxy: 4 chars/token). If summary exceeds 8000 chars (~2000 tokens), truncate Activity Timeline from the oldest end, keeping Files Modified and Key Decisions intact
- Overwrites summary.md each time (not append)

**Done when:**
- summary.md is generated from events.jsonl with all specified sections
- Token budget is respected (summary stays under ~8000 chars)
- Summary is valid markdown, human-readable
- Manual test: generate 50 events, verify summary captures all file edits and decisions

**Dependencies:** Task 1 (reads events.jsonl format)

### Task 3: Hook configuration

**Complexity:** S

**Files:**
- `hooks/README.md` (create) -- documents hook setup for users
- Update project README or CLAUDE.md if needed to reference hooks

**Approach:**
- Document the settings.json configuration needed to enable the hook:
  ```json
  {
    "hooks": {
      "PostToolUse": [
        {
          "command": "bash $PROJECT_DIR/hooks/session-index.sh",
          "timeout": 500
        }
      ]
    }
  }
  ```
- Document how to verify the hook is working (check for events.jsonl creation)
- Document how to disable the hook (remove the settings.json entry)
- Note: this is opt-in. The hook is not auto-installed. Users add it to their settings.json.

**Done when:**
- README documents setup, verification, and disable procedures
- A user following the README can enable session indexing in <2 minutes

**Dependencies:** Task 1

## Wave 2: /recall Skill and Recovery Integration

### Task 4: Create /recall skill

**Complexity:** M

**Files:**
- `skills/recall/SKILL.md` (create)

**Approach:**
- Skill type: Rigid -- follow exactly, no subagent dispatch
- Execution model: Direct execution by the orchestrator (like checkpoint). No Agent/Task tool dispatch.
- Input parsing: detect query type from user input
  - No arguments: return full summary.md content
  - Keywords present: grep events.jsonl for matching entries
  - "errors" / "decisions" / "edits": filter by event type
  - Time expressions ("last 30 minutes", "last hour"): parse into timestamp filter
- Output: formatted markdown table of matching events, capped at 20 entries
- Session index discovery: glob `~/.claude/projects/<hash>/memory/session-index/*/events.jsonl`, pick most recently modified
- If no session index exists: return "No session index found. Enable session indexing by adding the PostToolUse hook -- see hooks/README.md."
- Tool constraint: use Read and Glob tools for session-index access (safety hooks block Bash on .claude/ paths)

**Done when:**
- SKILL.md covers all query modes (summary, keyword, type filter, time range)
- Graceful handling when no index exists
- Output is formatted, concise, and useful for context recovery
- Skill follows crucible conventions (frontmatter, announce at start, red flags)

**Dependencies:** Tasks 1-2 (session index must exist to query)

### Task 5: Explicit event emission API for skills

**Complexity:** S

**Files:**
- `skills/shared/session-index-convention.md` (create)

**Approach:**
- Define how pipeline skills emit semantic events (decision, phase_change, skill_start, skill_end) that the hook cannot infer from raw tool data
- Convention: skills write a JSONL entry directly to events.jsonl using the Write tool (append mode not available -- read, append in memory, write back. OR: use Bash with `echo '...' >> events.jsonl` but this hits the .claude/ path safety hook)
- Alternative: skills emit events by writing to a well-known "outbox" file that the hook picks up. The hook checks for `~/.claude/projects/<hash>/memory/session-index/<session-id>/outbox.jsonl` on each invocation, moves entries to events.jsonl, and deletes outbox.jsonl.
- Decision: use the outbox pattern. Skills write to outbox.jsonl (which is a project-memory path, accessible via Write tool). The next PostToolUse hook invocation drains the outbox into events.jsonl. This avoids the Bash/.claude safety hook conflict.
- Document the outbox entry format (same schema as events.jsonl)
- Provide examples for each semantic event type

**Done when:**
- Convention document covers outbox pattern, event schema, and examples
- Skills can emit semantic events without Bash (using Write tool to outbox.jsonl)
- Hook drains outbox on each invocation

**Dependencies:** Task 1 (hook must support outbox drain)

### Task 6: CSB integration -- add session index path

**Complexity:** S

**Files:**
- `skills/shared/dispatch-convention.md` (modify -- add session index to compaction recovery section)
- `skills/build/SKILL.md` (modify -- add session index path to CSB Scratch State)
- `skills/debugging/SKILL.md` (modify -- same)
- `skills/spec/SKILL.md` (modify -- same)

**Approach:**
- In each skill's CSB template, add to the Scratch State section:
  ```
  Scratch State:
  - Location: [skill-specific scratch path]
  - Session Index: ~/.claude/projects/<hash>/memory/session-index/<session-id>/
  - Recovery: [existing recovery instructions]
  ```
- In dispatch-convention.md's Compaction Recovery section, add a note that the session index path should be included in CSBs when session indexing is active
- This is a minimal, non-breaking change to existing CSB format

**Done when:**
- CSB templates in build, debugging, and spec include session index path
- dispatch-convention.md references session index in compaction recovery
- No functional change to CSB emission triggers or frequency

**Dependencies:** Task 1 (session index path convention must be defined)

## Wave 3: Pipeline Skill Integration

### Task 7: Enhance build/debugging/spec compaction recovery

**Complexity:** M

**Files:**
- `skills/build/SKILL.md` (modify -- compaction recovery section)
- `skills/debugging/SKILL.md` (modify -- compaction recovery section)
- `skills/spec/SKILL.md` (modify -- compaction recovery section)

**Approach:**
- Add step 4.5 to each skill's compaction recovery procedure:
  ```
  4.5. Read session index summary: If the session index path is available
       (from CSB Scratch State or from globbing session-index/), read
       summary.md. Include the Activity Timeline and Key Decisions in
       the post-compaction narration. This supplements (does not replace)
       the CSB and pipeline-status.md recovery.
  ```
- The step is conditional -- if no session index exists, skip silently. This maintains backward compatibility with sessions that don't have the hook enabled.
- Add to each skill's Red Flags section: "Treating session index summary as authoritative over CSB state (session index is supplementary narrative, CSB is authoritative state)"

**Done when:**
- Build, debugging, and spec compaction recovery sections include session index read step
- Recovery is additive (no existing steps removed or modified)
- Skills degrade gracefully when session index is absent
- Red flags updated

**Dependencies:** Tasks 4-6

### Task 8: Skill-emitted events in build skill

**Complexity:** S

**Files:**
- `skills/build/SKILL.md` (modify)

**Approach:**
- Add outbox writes at key pipeline moments:
  - Phase transitions: write `phase_change` event to outbox
  - Quality gate results: write `decision` event with gate outcome
  - Task completion: write `skill_end`-like event with task summary
  - Skill start/end: write `skill_start` and `skill_end` events
- This is the reference implementation. Other skills (debugging, spec, siege) can adopt the pattern in future tickets.
- Keep it minimal: 4-6 outbox write instructions added to existing pipeline steps. Do not restructure the skill.

**Done when:**
- Build skill writes 4-6 semantic events to outbox at key moments
- Events follow the schema from session-index-convention.md
- No change to build's execution flow or timing
- Other skills are not modified in this task (future work)

**Dependencies:** Task 5 (outbox convention must be defined)

## Summary

| Task | Wave | Complexity | Creates | Modifies |
|------|------|-----------|---------|----------|
| 1. PostToolUse hook | 1 | M | hooks/session-index.sh | -- |
| 2. Summary writer | 1 | M | hooks/session-summary.sh | -- |
| 3. Hook configuration docs | 1 | S | hooks/README.md | -- |
| 4. /recall skill | 2 | M | skills/recall/SKILL.md | -- |
| 5. Event emission convention | 2 | S | skills/shared/session-index-convention.md | hooks/session-index.sh |
| 6. CSB integration | 2 | S | -- | dispatch-convention.md, build/debugging/spec SKILL.md |
| 7. Compaction recovery enhancement | 3 | M | -- | build/debugging/spec SKILL.md |
| 8. Build skill semantic events | 3 | S | -- | build/SKILL.md |

**Total complexity:** 3M + 3S + 2M = 5M + 3S
**Estimated effort:** ~4-6 hours of focused implementation

## What "Done" Looks Like

1. A PostToolUse hook captures file edits, git operations, test runs, and errors into a persistent JSONL index
2. A rolling summary is maintained and kept under 2000 tokens
3. `/recall` lets users (and skills) query session history by keyword, type, or time range
4. Pipeline skills read the session index summary during compaction recovery, supplementing existing CSB-based recovery
5. The build skill emits semantic events (phase changes, decisions) to the session index
6. Everything is opt-in (hook must be configured), backward-compatible (skills work without it), and zero-infrastructure (no daemons, no databases, no external services)
