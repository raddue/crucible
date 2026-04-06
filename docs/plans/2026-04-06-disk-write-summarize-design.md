---
ticket: "#141"
title: "Disk-write-then-summarize convention"
date: "2026-04-06"
source: "spec"
---

# Disk-Write-Then-Summarize Convention

## Problem

Orchestrators write state to disk (scratch files, findings, fix journals) but the full content also stays in conversation history via tool call results. The disk copy is authoritative — the conversation copy is dead weight. This doubles storage for every state write.

Disk-mediated dispatch (#97) solved this for subagent prompts. This extends the pattern to orchestrator state.

## Change

Add a convention to the three orchestrator skills (build, debugging, quality-gate): after writing structured state to disk, the orchestrator emits a 2-3 line summary referencing the disk path instead of relying on the full content remaining in conversation.

### The Convention

**After any Write tool call that persists orchestrator state to a scratch directory, emit a brief summary:**

```
[State type] written to [path]. [1-line summary of contents].
```

**Examples:**
- "Fix journal round 4 written to scratch/fix-journal.md. 3 findings addressed via extracted helper pattern."
- "Round 3 findings written to scratch/round-3-findings.md. Score: 4 (1 Fatal, 1 Significant). Down from 7."
- "Task 5 completion written to task-list. 2 files changed, review clean on pass 1."

**The orchestrator should not re-read the full content from its own conversation history after writing to disk.** If it needs the content later (e.g., to pass to a subagent), it reads from disk via the Read tool.

### Where to Apply

**Quality-gate:** After writing `round-N-findings.md`, `round-N-score.md`, `fix-journal.md` entries, `artifact-N.md` snapshots. These are the highest-volume writes (one per round, multiple files per round).

**Build Phase 3:** After writing task completion status, review findings summaries, and wave verification results to scratch/task files.

**Debugging:** After writing `hypothesis-log.md` updates, `phase-state.md` updates, and investigation findings to scratch.

### Implementation

Add a short section to each orchestrator skill's scratch directory documentation:

**"Disk-Write-Then-Summarize Convention"** (~5-8 lines per skill):
> After writing structured state to the scratch directory, emit a 1-2 line summary referencing the file path. Do not rely on the full content persisting in conversation — if you need it later, re-read from disk. This keeps conversation context lean while disk remains the source of truth.

## Key Decisions

### DEC-1: Convention in orchestrator skills, not in shared dispatch convention (High Confidence)

The shared dispatch convention covers subagent dispatch files. This covers orchestrator-to-disk writes, which are a different pattern. Keeping them separate avoids overloading `shared/dispatch-convention.md`.

### DEC-2: No enforcement mechanism — just clear instructions (High Confidence)

Like disk-mediated dispatch, this is an instruction the model follows, not compiled code. The pattern is simple enough (write, then summarize) that LLM compliance is high. The existing dispatch convention proves this pattern works.

## Acceptance Criteria

1. Quality-gate SKILL.md includes the convention in its scratch directory section
2. Build SKILL.md includes the convention in its context management section
3. Debugging SKILL.md includes the convention in its scratch directory section
4. Convention text is ~5-8 lines per skill (not a major SKILL.md addition)
