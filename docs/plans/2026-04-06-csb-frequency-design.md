---
ticket: "#140"
title: "Reduce CSB emission frequency"
date: "2026-04-06"
source: "spec"
---

# Reduce CSB Emission Frequency

## Problem

CSBs (~150-250 tokens each) are emitted at 6+ trigger types in build and 5 trigger types in debugging. They stack in conversation history — autocompact can't selectively shed old ones. Each emission adds tokens that persist until compaction.

## Change

Remove low-value CSB triggers. Keep only triggers where the CSB serves a genuine recovery or communication purpose.

### Build Skill — Checkpoint Timing

**Current triggers (5):**
1. Phase transitions → handoff manifest (already not a CSB)
2. Phase 3 progress: after every 3 task completions
3. Quality gate entry/exit
4. Escalations
5. Health transitions

**Revised triggers (3):**
1. Phase transitions → handoff manifest (unchanged)
2. Escalations (keep — user needs full state)
3. Health transitions (keep — state change worth recording)

**Dropped:**
- Every-3-task progress CSBs → replace with pipeline-status.md write only (already happens). The status file provides ambient awareness without bloating conversation context.
- Quality gate entry/exit → the gate is a sub-operation within a phase, not a phase boundary. Pipeline-status.md captures gate progress.

### Debugging Skill — Checkpoint Timing

**Current triggers (5):**
1. Phase transitions → handoff manifests at major boundaries, CSBs at minor ones
2. Hypothesis cycles: after each hypothesis formed/invalidated
3. Fix attempts: after each Phase 4 attempt
4. Escalations
5. Health transitions

**Revised triggers (4):**
1. Phase transitions → handoff manifests at major boundaries, CSBs at minor ones (unchanged)
2. Fix attempts: after each Phase 4 attempt (keep — fix cycles are the core loop)
3. Escalations (keep)
4. Health transitions (keep)

**Dropped:**
- Hypothesis cycles → these fire frequently during Phase 2 (every hypothesis formed AND invalidated). Replace with pipeline-status.md write only.

## Acceptance Criteria

1. Build Checkpoint Timing section reduced from 5 to 3 triggers
2. Debugging Checkpoint Timing section reduced from 5 to 4 triggers
3. Pipeline-status.md writes still happen at all former CSB trigger points (ambient awareness preserved)
4. Existing handoff manifest behavior unchanged
