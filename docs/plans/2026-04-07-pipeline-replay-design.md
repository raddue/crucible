# Pipeline Replay Design

**Issue:** #143
**Branch:** feat/pipeline-replay
**Date:** 2026-04-07

## Overview

Pipeline Replay wires together three existing systems -- dispatch manifests, dispatch files, and shadow git checkpoints -- to enable crash recovery and A/B experimentation for long-running pipelines. A build that crashes at Phase 4 after 90 minutes currently requires a full restart. With replay, it costs approximately 10 minutes to resume from the last successful phase boundary.

**Key insight:** The dispatch convention was explicitly designed for this. `dispatch-convention.md` line 141 notes "Pipeline resume (future) -- skip completed dispatches, restart from first failure." The manifests, dispatch files, and checkpoints are all on disk. The missing piece is purely the orchestration layer that reads them and re-dispatches.

**Two capabilities, one mechanism:**
1. **Crash recovery** -- detect interrupted pipeline, resume from last good state
2. **A/B experimentation** -- replay a historical pipeline with mutated dispatch templates, compare outcomes

## Current State Analysis

### What Exists Today

1. **Dispatch manifests** (`manifest.jsonl`) -- JSONL trace of every subagent dispatch. Fields: `seq`, `file`, `role`, `phase`, `status`, `duration_s`, `summary`. Append-only; last entry per `seq` is authoritative. Preserved to scratch directory on failure (dispatch-convention.md cleanup rules).

2. **Dispatch files** (`<N>-<template-name>.md`) -- Self-contained subagent instructions on disk. Include audit header with pipeline/phase/task metadata and `Dispatch-Dir` path. Preserved alongside manifest on failure.

3. **Shadow git checkpoints** -- Working directory snapshots in `~/.claude/projects/<hash>/checkpoints/<dir-hash>/`. Tagged with reason (`pre-design-gate`, `pre-wave-N`, etc.), source skill, and timestamp. Manifest at `checkpoint-manifest.md`. Persist across sessions.

4. **Compression State Blocks (CSBs)** -- Structured context blocks emitted at checkpoint boundaries. Contain goal, phase, progress, key decisions, active constraints, files modified, scratch state, and next steps. Persisted to `pipeline-status.md` and handoff manifests.

5. **Phase Handoff Manifests** -- Written at phase boundaries (1->2, 2->3, 3->4). Define exactly what the next phase needs. Stored in scratch directory as `handoff-N-to-M.md`.

6. **Compaction recovery** -- `.dispatch-active-<session-id>` marker files, mode files (`/tmp/crucible-build-mode.md`), pipeline-status.md Compression State section. Already handle within-session recovery after context compaction.

### What's Missing

1. **Cross-session resume orchestrator** -- compaction recovery works within a session; nothing handles session crash (process killed, rate limit, timeout).
2. **Pipeline-active marker** -- `.dispatch-active-*` tracks dispatch directory, not pipeline liveness. No way to detect an interrupted pipeline vs. a completed one.
3. **Replay dispatch logic** -- no code to partition manifest into completed/incomplete, restore checkpoint, and re-dispatch from a specific point.
4. **Prompt mutation for A/B** -- no mechanism to swap templates on replay.
5. **Structured diff output** -- no way to compare two manifest runs.

## Design Decisions

### Decision 1: Resume Is Both Automatic and Explicit

**Choice:** Automatic detection on `/build` start (marker file check) AND explicit `/replay` invocation. Both use the same underlying replay engine.

**Rationale:** Automatic catches the common case (crash during build, user restarts build). Explicit enables the advanced case (replay old pipeline, A/B experiments, cross-session resume with mutation). Making automatic opt-out (user can say "start fresh") avoids surprise behavior while preventing silent 90-minute rework.

**Confidence: High.** The automatic path is a 30-line marker file check at build start. The explicit path is the full replay skill. No conflict between the two.

### Decision 2: Resume Granularity Is Phase Boundaries

**Choice:** Resume at phase boundaries (7 points in build: pre-design-gate, pre-plan-gate, pre-wave-1 through pre-wave-N, pre-code-review, pre-inquisitor, pre-impl-gate). Not per-dispatch.

**Rationale:** Phase boundaries align with existing checkpoint infrastructure. Every boundary has a shadow git snapshot, a CSB or handoff manifest, and a clean pipeline state. Per-dispatch resume would require reconstructing mid-phase orchestrator state (task lists, review loop counters, wave progress), which is fragile and error-prone. Phase boundaries are natural consistency points where all in-flight work has completed.

**Tradeoff:** A crash mid-wave in Phase 3 loses that wave's work (max ~30 minutes for a complex wave). This is acceptable given that the alternative is losing the entire pipeline run. Per-dispatch granularity can be added later as a refinement without changing the phase-boundary architecture.

**Confidence: High.**

### Decision 3: Replayed Manifests Are Continuations, Not Separate Files

**Choice:** Append to the original `manifest.jsonl` with `status: "replayed"` entries that back-reference the original `seq`.

**Rationale:** A single manifest is the complete execution history. Separate files require cross-referencing. The append-only protocol already handles multiple entries per `seq` -- the last entry is authoritative. Replay entries use a new `replay_of` field to link back.

**Confidence: Medium.** Separate files would be cleaner for A/B comparison. But the manifest already supports multiple entries per seq, and a single file is simpler for tooling. The `replay_of` field preserves the link. Revisit if A/B comparison tooling finds this awkward.

### Decision 4: Partial Commit Handling Uses Conservative Verification

**Choice:** Before resuming from a phase boundary, verify that all dispatches marked `completed` before that boundary actually produced their expected artifacts (commits exist, output files exist). If verification fails, fall back to the previous good boundary.

**Rationale:** A crash can occur between a subagent completing work and the manifest being updated. The manifest might show `status: "dispatched"` for an agent that actually committed code. Or it might show `status: "completed"` for an agent whose commit was partial. Verification catches both cases.

**Confidence: High.** Verification is cheap (git log checks, file existence) and the cost of false negatives (resuming too early) is only the cost of re-executing one phase.

### Decision 5: A/B Mutation Is Template-Level, Not Manifest-Level

**Choice:** Mutations specify template replacements: "use `quality-gate-v2-prompt.md` instead of `quality-gate-prompt.md`". The manifest itself is never modified -- mutations are applied at dispatch time.

**Rationale:** Manifests are historical records. Mutating them corrupts the execution trace. Template-level mutation is the natural unit of experimentation (you want to test "does this new template produce better results?"). The dispatch file on disk is the template output -- mutations produce new dispatch files with new seq numbers.

**Confidence: High.**

### Decision 6: Replay Generates Chronicle-Compatible Signals

**Choice:** Replay runs generate the same chronicle signals as normal runs, plus a `replay_source` field linking to the original manifest. Replay diffs (original vs. replayed outcomes) are also emitted as structured signals.

**Rationale:** Replay runs are real pipeline executions with real outcomes. They should feed the same data pipelines. The `replay_source` field lets chronicle distinguish organic from replay runs. Replay diffs are especially valuable -- they are structured input/output pairs from real pipelines, exactly what skill-creator needs for eval generation.

**Confidence: Medium.** Chronicle is not yet live. Design for compatibility now; wire up when chronicle ships.

## Architecture

### Pipeline-Active Marker

```
<scratch>/.pipeline-active
```

Format (4 lines):
```
pipeline: build
session-id: 1775430161
started: 2026-04-07T14:30:00Z
dispatch-dir: /tmp/crucible-dispatch-1775430161/
```

**Lifecycle:**
1. Written at pipeline start (build Phase 1, before first dispatch)
2. Deleted on successful pipeline completion (build Phase 4 cleanup)
3. Left in place on crash (the marker IS the crash signal)

**Detection:** At `/build` start, check for `.pipeline-active` in the scratch directory. If present and the session-id does not match the current session, the previous pipeline crashed.

### Resume Flow (Automatic -- `/build` Start)

```
1. Check <scratch>/.pipeline-active
   |
   |- Not found → normal pipeline start
   |
   |- Found, same session → compaction recovery (existing behavior)
   |
   |- Found, different session → RESUME PATH:
      |
      2. Read manifest.jsonl from dispatch-dir (or scratch copy)
      3. Partition entries into completed/incomplete by phase boundary
      4. Find latest phase boundary where all prior dispatches are verified complete
      5. Present resume option to user:
         "Previous build crashed at Phase 3, Wave 2. Resume from Phase 3 start
          (checkpoint: pre-wave-1, 45 min of work preserved)? [y/n/fresh]"
      6a. User says yes → restore checkpoint, reconstruct state, re-dispatch
      6b. User says no/fresh → delete marker, start fresh
```

### Resume Flow (Explicit -- `/replay`)

```
/replay <scratch-dir-or-manifest-path> [options]

Options:
  --from-phase <N>       Resume from phase N boundary
  --from-seq <N>         Resume from dispatch sequence N
  --mutate <original>=<replacement>  Swap dispatch template
  --diff                 Compare replayed vs original outcomes
  --dry-run              Show what would be re-dispatched without executing
```

### Manifest Entry Extensions

New fields for replay entries (backward-compatible -- existing manifests lack these fields and that is fine):

```jsonl
{"seq":15,"file":"15-build-implementer.md","role":"implementer","phase":"3","task":2,"status":"replayed","duration_s":45,"summary":"Task 2 re-implemented","replay_of":8,"replay_session":"1775430200","mutation":null}
```

- `replay_of` -- seq number of the original dispatch being replayed (null for non-replay)
- `replay_session` -- session ID of the replay run (null for non-replay)
- `mutation` -- template mutation applied, if any (null for faithful replay)

### Checkpoint-Manifest Correlation

The replay engine maps phase boundaries to checkpoints by matching checkpoint reasons to phase identifiers:

| Phase Boundary | Checkpoint Reason | What It Captures |
|---------------|-------------------|------------------|
| Pre-Phase 2 | `pre-design-gate` or `pre-plan-gate` | State after design approval |
| Pre-Phase 3 | `pre-wave-1` | State after plan approval, before execution |
| Mid-Phase 3 | `pre-wave-N` | State after wave N-1 completion |
| Pre-Phase 4 | `pre-code-review` | State after all execution waves complete |

The correlation is string-matching on checkpoint reason prefixes. If a checkpoint is missing (disabled, evicted, or pre-checkpoint-era pipeline), the replay engine falls back to the earliest available checkpoint and warns.

### State Reconstruction

At resume, the orchestrator needs to reconstruct its internal state without the original conversation context. Sources, in priority order:

1. **Phase Handoff Manifests** (`handoff-N-to-M.md`) -- define exactly what the next phase needs. If resuming at a phase boundary and the handoff manifest exists, this is the primary state source.
2. **Pipeline-status.md Compression State** -- goal, key decisions, active constraints, next steps. Semantic subset of the full CSB.
3. **Manifest entries** -- seq/role/phase/status/summary for all prior dispatches. Reconstructs what happened.
4. **Dispatch files on disk** -- full subagent instructions for any dispatch that needs re-execution.
5. **Shadow git checkpoint** -- filesystem state at the resume point.
6. **Build mode file** (`/tmp/crucible-build-mode.md`) -- mode and baseline commit SHA.

The replay engine reads these in order, constructs a synthetic CSB from the combined state, and emits it to seed the new context window. This follows the same pattern as compaction recovery but from disk state rather than in-conversation state.

### A/B Experimentation

```
/replay /path/to/scratch-dir --mutate quality-gate-prompt.md=quality-gate-v2-prompt.md --diff
```

**Flow:**
1. Read original manifest, identify all dispatches using the mutated template
2. Restore checkpoint to the point before the first affected dispatch
3. Re-execute from that point, substituting the new template at dispatch time
4. New dispatch files are written with the mutated template content but follow the same naming/seq convention (with `replay_of` back-reference)
5. After completion, run structured diff

**Structured Diff Output:**

```markdown
# Replay Diff: <original-session> vs <replay-session>

## Template Mutations
- quality-gate-prompt.md → quality-gate-v2-prompt.md

## Outcome Comparison
| Metric | Original | Replayed | Delta |
|--------|----------|----------|-------|
| Total dispatches | 23 | 21 | -2 |
| Quality gate rounds | 4 | 2 | -2 |
| Wall clock time | 2h 47m | 1h 53m | -54m |
| Acceptance tests | PASS | PASS | = |

## Per-Dispatch Comparison
| Seq | Role | Original Status | Replayed Status | Summary Delta |
|-----|------|----------------|-----------------|---------------|
| 14 | red-team | completed | replayed | 3 findings → 1 finding |
| 15 | implementer | completed | replayed | Fixed 3 issues → fixed 1 issue |

## Artifact Diff
- git diff <original-final-sha>..<replayed-final-sha>
  N files changed, +X/-Y lines
```

This output is machine-readable for eval generation and human-readable for decision-making.

## The `/replay` Skill

### Skill Metadata

```yaml
name: replay
description: "Resume interrupted pipelines from dispatch manifests, or replay historical pipelines with template mutations for A/B experimentation."
origin: crucible
```

### Execution Model

- **Skill type:** Orchestrator -- dispatches subagents via existing dispatch convention
- **Subagent dispatch:** Reuses the parent pipeline's dispatch templates and convention
- **No new dispatch templates** -- replay re-dispatches using existing templates (or mutated versions)

### Modes

1. **Resume mode** (default when `.pipeline-active` detected or `--from-phase`/`--from-seq` given without `--mutate`)
   - Restores checkpoint, reconstructs state, re-dispatches from resume point
   - Appends to existing manifest with `status: "replayed"`

2. **A/B mode** (`--mutate` flag)
   - Same as resume but with template substitutions
   - Produces structured diff output after completion

3. **Dry-run mode** (`--dry-run` flag)
   - Analyzes manifest, identifies resume point, lists what would be re-dispatched
   - No state changes, no dispatches

### Integration with `/build`

The `/build` skill gains a ~30-50 line resume check at the very start of Phase 1, before any design work:

```
Step -1: Resume Detection

1. Check <scratch>/.pipeline-active
2. If not found: write marker, proceed normally
3. If found with current session ID: compaction recovery (existing behavior)
4. If found with different session ID:
   a. Read manifest from dispatch-dir or scratch copy
   b. Identify last successful phase boundary
   c. Present resume option to user
   d. If user accepts: invoke crucible:replay in resume mode
   e. If user declines: delete marker, proceed fresh
```

The marker file is also written at pipeline start and deleted at successful completion (Phase 4 cleanup step 11, after finish).

## Edge Cases

### Corrupted or Truncated Manifest

The manifest uses append-only JSONL. Truncation mid-line produces an invalid final line. The replay engine:
1. Reads line-by-line, catching JSON parse errors per line
2. Drops unparseable lines with a warning
3. Uses the last valid entry per `seq` as authoritative
4. If zero valid entries: treat as missing manifest, cannot resume

### Missing Checkpoint

If the desired checkpoint was evicted (>50 entries) or the shadow repo was reinitialized:
1. Fall back to the nearest earlier checkpoint
2. If no checkpoints exist: warn that filesystem state cannot be guaranteed, offer "resume with current disk state" or "start fresh"
3. The user makes the call -- replay never auto-restores without confirmation

### Missing Dispatch Files

Dispatch files should be preserved in the scratch directory on failure (per dispatch-convention.md cleanup rules). If missing:
1. Re-generate from template + manifest metadata (role, phase, task are all recorded)
2. If the template itself is unavailable (skill files changed between sessions): warn that faithful replay is impossible, offer to proceed with current templates or abort

### Partially Committed Mutating Agent

A crash can occur after an implementer commits 2 of 3 files. The manifest shows `status: "dispatched"` (no completion entry). At resume:
1. Check git log for commits attributed to the dispatch (match by timestamp, commit message patterns, or dispatch-file references)
2. If partial commits found: revert to the phase boundary checkpoint (which predates the partial work) and re-dispatch the entire wave
3. If no commits found: safe to re-dispatch from the same point

### Dispatch Directory in `/tmp` Lost

`/tmp` is ephemeral. If the machine rebooted, the dispatch directory is gone. But:
1. The cleanup rules copy the full dispatch directory to the scratch directory on failure
2. Resume reads from the scratch copy preferentially
3. If both are missing: the manifest survives (also copied to scratch), but dispatch files must be regenerated from templates

### Stale Templates Between Sessions

Between crash and resume, someone may have modified skill templates. This is fine for resume (you want current-best templates). For A/B experimentation, it is a confound. The replay engine:
1. On A/B mode: warns if any dispatched template's modification time is newer than the original manifest
2. For faithful comparison: user can pin templates via git ref (`--template-ref <sha>`)

## Interaction with Other Systems

### Forge Chronicle

Replay runs generate chronicle signals with `replay_source` field. Replay diffs are separate signal type (`skill: "replay-diff"`). When chronicle ships, the wiring is:
- Normal replay signals: append to `signals.jsonl` as usual
- Replay diff signals: new signal format, same file

### Quality Gates

Quality gates during replay follow the same rules as normal runs. The quality gate cannot be skipped just because the original run passed -- the replay may use different templates, different model versions, or different codebase state.

### Dispatch Convention

No changes to the core dispatch protocol. Replay appends to existing manifests and writes dispatch files following the same naming convention. The new `replay_of`, `replay_session`, and `mutation` fields are additive and backward-compatible (existing manifest readers ignore unknown fields).

## Security Considerations

- **Replay does not escalate permissions** -- replayed dispatches run with the same tool access as normal dispatches
- **Template mutation is user-initiated** -- no automatic template swapping; all mutations are explicit CLI arguments
- **Checkpoint restore is user-confirmed** -- the resume prompt requires explicit user acceptance before any filesystem changes
- **A/B mode does not modify the original manifest** -- original entries are preserved; replay entries are appended with clear `replay_of` linkage
