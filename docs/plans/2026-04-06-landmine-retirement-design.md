---
ticket: "#92"
title: "Landmines.md entry retirement policy"
date: "2026-04-06"
source: "spec"
---

# Landmines.md Entry Retirement Policy

## Current State

Cartographer's `landmines.md` has a 100-line cap. Current pruning rule (SKILL.md line 251): "Mark resolved landmines with strikethrough, prune after 10 sessions." Dead-end entries for approaches that failed are not "resolved" — they stay relevant while the module exists. When modules are deleted or restructured, their dead-end entries become obsolete but never age out.

As more sources write dead ends (debugging, QG via negative knowledge persistence), cap pressure increases. Without retirement, the cap-pressure skip path becomes steady state on long-lived projects, silently discarding fresh negative knowledge.

## Change

Add a retirement policy to SKILL.md's recorder rules and the recorder prompt:

1. **Path staleness check:** Before each recorder write, check if landmine entries reference file paths that no longer exist in the current tree. Entries whose ALL referenced paths are gone are candidates for retirement.

2. **Retirement action:** Move stale entries to `## Retired Landmines` section at the bottom of `landmines.md` (not a separate file — keeps everything in one place for grep-ability). Retired entries are not loaded into subagent dispatch files.

3. **Retirement format:** `- ~~[Short title]~~ — [Retired: paths no longer exist. Original module: X]`

4. **Cap accounting:** Retired entries do NOT count toward the 100-line cap. Only Active and Resolved entries count.

5. **Orchestrator responsibility:** The recorder agent handles retirement during its normal update pass. No separate retirement agent needed.

## Key Decisions

### DEC-1: Retire within landmines.md, not to a separate file (High Confidence)

A separate `resolved-landmines.md` fragments the knowledge. Keeping retired entries in the same file (but excluded from cap and subagent loading) preserves grep-ability while freeing cap budget.

### DEC-2: Path-based staleness, not session-count-based (High Confidence)

The issue proposed "entries older than N sessions without a path match." Session counting is fragile (sessions vary in length, different projects have different cadences). Path existence is objective and verifiable: if every file path in the entry is gone, the entry is stale.

## Acceptance Criteria

1. SKILL.md documents retirement policy (path staleness → retire)
2. Recorder prompt instructs agent to check path staleness and move entries
3. Retired entries excluded from 100-line cap
4. Retired entries not loaded into subagent dispatches
5. `## Retired Landmines` section format defined
