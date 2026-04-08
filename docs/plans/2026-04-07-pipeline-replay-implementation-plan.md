# Pipeline Replay Implementation Plan

**Issue:** #143
**Branch:** feat/pipeline-replay
**Date:** 2026-04-07

## Task Overview

8 implementation tasks across 3 waves. Wave 1 builds the replay engine core. Wave 2 integrates into existing skills. Wave 3 adds A/B experimentation and diff output.

## Wave 1: Replay Engine Core

### Task 1: Pipeline-active marker lifecycle

**Review-Tier:** 1
**Complexity:** S

**Files:**
- `skills/build/SKILL.md` (modify -- add Step -1 resume detection, marker write at start, marker delete at cleanup)
- `skills/shared/dispatch-convention.md` (modify -- add `.pipeline-active` marker spec to the Compaction Recovery section)

**Approach:**
- Add a `## Pipeline-Active Marker` section to `dispatch-convention.md` defining the marker format (pipeline, session-id, started, dispatch-dir) and lifecycle (write at start, delete on success, leave on crash)
- Add Step -1 to build Phase 1 that checks for `.pipeline-active` in the scratch directory
- Add marker write immediately after Step -1 (before design dispatch)
- Add marker delete to Phase 4 completion (after finish skill, before final report)
- Marker is written to `<scratch>/.pipeline-active` where `<scratch>` is the pipeline's persistent scratch directory (`~/.claude/projects/<hash>/memory/`)

**Done when:**
- dispatch-convention.md documents marker format and lifecycle
- build SKILL.md writes marker at pipeline start
- build SKILL.md deletes marker at successful completion
- build SKILL.md checks marker at start and branches on same-session vs different-session

**Dependencies:** None

### Task 2: Manifest partition and verification engine

**Review-Tier:** 2
**Complexity:** M

**Files:**
- `skills/replay/SKILL.md` (create -- core replay skill)

**Approach:**
- Create the replay skill file with metadata (name, description, origin)
- Implement manifest reading: line-by-line JSONL parse with per-line error handling, last-entry-per-seq deduplication
- Implement phase boundary detection: group entries by phase, identify boundaries where all dispatches in the prior phase are `completed`
- Implement artifact verification: for each `completed` entry before the resume point, verify expected artifacts exist (git commits via `git log --oneline --since`, output files from dispatch metadata)
- Implement resume point selection: find latest verified phase boundary, present to user with context (phase name, checkpoint reason, elapsed time preserved)
- Define the three modes: resume (default), A/B (--mutate), dry-run (--dry-run)
- Dry-run mode: parse manifest, identify resume point, list what would be re-dispatched, exit without changes

**Done when:**
- Replay skill can read any valid manifest.jsonl and identify phase boundaries
- Truncated/corrupted manifests degrade gracefully (skip bad lines, warn)
- Artifact verification catches missing commits and output files
- Dry-run mode produces accurate report of resume plan
- Unit-testable via synthetic manifest files

**Dependencies:** None (can proceed in parallel with Task 1)

### Task 3: Checkpoint-manifest correlation and state reconstruction

**Review-Tier:** 2
**Complexity:** M

**Files:**
- `skills/replay/SKILL.md` (modify -- add checkpoint correlation and state reconstruction sections)

**Approach:**
- Implement checkpoint lookup: given a phase boundary, find the matching checkpoint in `checkpoint-manifest.md` by matching reason strings to phase identifiers (see design doc correlation table)
- Implement fallback chain: missing checkpoint -> earlier checkpoint -> no checkpoint (warn, offer current-state resume)
- Implement state reconstruction from disk sources (priority order): handoff manifests, pipeline-status.md Compression State, manifest entries, dispatch files, build mode file
- Emit synthetic CSB from reconstructed state to seed the new context window
- Handle the cross-session case: shadow repo path is deterministic from working directory, so a new session can find checkpoints from a prior session

**Done when:**
- Given a phase boundary, replay can find and verify the corresponding checkpoint
- Missing checkpoints fall back gracefully with user-facing warnings
- State reconstruction produces a valid CSB from disk-only sources
- The reconstructed CSB contains goal, phase, progress, key decisions, active constraints, and next steps

**Dependencies:** Task 2 (needs manifest partition to know which phase boundary to correlate)

### Task 4: Re-dispatch engine

**Review-Tier:** 2
**Complexity:** L

**Files:**
- `skills/replay/SKILL.md` (modify -- add re-dispatch orchestration)

**Approach:**
- After checkpoint restore and state reconstruction, replay enters the normal pipeline flow at the identified phase
- For build resume: hand off to the appropriate build phase (Phase 2/3/4) with reconstructed state
- The replay skill does NOT re-implement build phases -- it reconstructs state and then delegates to build's existing phase logic
- Manifest extension: new dispatches use the next available seq number (from manifest), write entries with `status: "replayed"`, `replay_of` back-referencing original seq, `replay_session` with current session ID
- Handle the "resume from Phase 3 mid-wave" case: restore to pre-wave-N checkpoint, re-execute from wave N start (not mid-wave)
- Re-dispatch safety: for mutating agents (implementers), verify via git log that no partial commits from the crashed dispatch pollute the restored state (checkpoint restore handles this, but verify)

**Done when:**
- Replay can restore a checkpoint and hand off to build Phase 2, 3, or 4
- New manifest entries carry replay metadata (replay_of, replay_session)
- Build phases work correctly when entered mid-pipeline via replay (state is correctly reconstructed)
- Mutating agent re-dispatch is safe (no duplicate commits, no partial state)

**Dependencies:** Task 2, Task 3

## Wave 2: Skill Integration

### Task 5: Build skill resume integration

**Review-Tier:** 2
**Complexity:** M

**Files:**
- `skills/build/SKILL.md` (modify -- add resume flow to Step -1, add Phase 4 marker cleanup)

**Approach:**
- Flesh out Step -1 with the full resume detection flow:
  1. Check `.pipeline-active` -- not found -> write marker, proceed
  2. Found, same session -> compaction recovery (existing)
  3. Found, different session -> read manifest, identify resume point, present option to user
  4. User accepts -> invoke `crucible:replay` in resume mode, passing scratch dir
  5. User declines -> delete marker, write fresh marker, proceed normally
- Add marker deletion to Phase 4 step 11 (after finish, before final report)
- Add communication: the resume prompt must explain what work is preserved, what will be re-executed, and the estimated time savings
- Ensure the pipeline-status.md is updated correctly on resume (Started timestamp from original run, events buffer reset with resume note)

**Done when:**
- `/build` automatically detects crashed pipelines and offers resume
- Resume invocation delegates to replay skill correctly
- User can decline resume and start fresh without artifacts from the old run interfering
- Pipeline-status.md shows correct timeline on resume

**Dependencies:** Task 1, Task 4

### Task 6: Dispatch convention manifest extensions

**Review-Tier:** 1
**Complexity:** S

**Files:**
- `skills/shared/dispatch-convention.md` (modify -- extend entry format with replay fields)

**Approach:**
- Add `replay_of`, `replay_session`, and `mutation` fields to the Entry Format section
- Document them as optional (null or absent for non-replay entries)
- Add a note to "What the Manifest Enables" section: "4. Pipeline replay -- resume from crash or replay with template mutations (see crucible:replay)"
- Add backward compatibility note: existing manifest readers must ignore unknown fields
- Update the "Re-dispatch Safety" section to reference replay's artifact verification as the canonical pre-dispatch check

**Done when:**
- dispatch-convention.md documents the three new manifest fields
- Backward compatibility is explicitly stated
- The "Pipeline resume (future)" note is updated to reference the live implementation

**Dependencies:** None (can run in parallel with any task, but logically follows Task 2)

### Task 7: Secondary skill resume markers (debugging, spec, migrate)

**Review-Tier:** 1
**Complexity:** S

**Files:**
- `skills/debugging/SKILL.md` (modify -- add pipeline-active marker write/check/delete)
- `skills/spec/SKILL.md` (modify -- add pipeline-active marker write/check/delete)
- `skills/migrate/SKILL.md` (modify -- add pipeline-active marker write/check/delete)

**Approach:**
- Each skill gets the same pattern as build: write `.pipeline-active` at start, delete at successful completion, check at start for prior crash
- The marker format includes the skill name in the `pipeline` field, so replay knows which skill to resume
- For now, detection only -- present the user with "Previous [skill] run crashed. Start fresh?" and delete the stale marker. Full replay support for these skills is deferred until their phase structure is documented at the same granularity as build.
- This is a minimal change per skill (~10-15 lines each): marker write, marker check, marker delete

**Done when:**
- debugging, spec, and migrate skills write and clean up pipeline-active markers
- Stale markers from prior crashed runs are detected and reported to user
- No full replay orchestration for these skills yet (detection + cleanup only)

**Dependencies:** Task 1 (marker format must be defined first)

## Wave 3: A/B Experimentation

### Task 8: Template mutation and structured diff

**Review-Tier:** 2
**Complexity:** L

**Files:**
- `skills/replay/SKILL.md` (modify -- add A/B mode and diff output)

**Approach:**
- Implement `--mutate <original>=<replacement>` flag parsing
  - `original` is a template filename (e.g., `quality-gate-prompt.md`)
  - `replacement` is a path to the replacement template
  - Multiple `--mutate` flags allowed for multi-template experiments
- At dispatch time, check if the current dispatch's template matches any mutation. If so, write the dispatch file using the replacement template content but the same audit header and context
- Mark mutated dispatch entries with `mutation: "original.md -> replacement.md"` in manifest
- Implement `--template-ref <sha>` for pinning templates to a git ref (for controlled experiments)
- Implement structured diff output:
  - Read original manifest entries and replayed entries (matched by `replay_of`)
  - Compare: dispatch count, durations, quality gate rounds, acceptance test outcomes, final git diff
  - Output as markdown table (human-readable) and as JSONL (machine-readable, for chronicle/eval)
- Template staleness warning: on A/B mode, check if any dispatched template's mtime is newer than the original manifest timestamp. Warn but do not block.

**Done when:**
- `/replay --mutate` correctly substitutes templates at dispatch time
- Mutated dispatches are marked in manifest
- `--diff` produces a structured comparison of original vs replayed outcomes
- Diff output is both human-readable (markdown) and machine-readable (JSONL)
- Template staleness is detected and warned about

**Dependencies:** Task 4 (needs working re-dispatch engine)

## Summary

| Wave | Task | Description | Complexity | Dependencies |
|------|------|-------------|------------|--------------|
| 1 | 1 | Pipeline-active marker lifecycle | S | None |
| 1 | 2 | Manifest partition and verification | M | None |
| 1 | 3 | Checkpoint-manifest correlation | M | Task 2 |
| 1 | 4 | Re-dispatch engine | L | Task 2, 3 |
| 2 | 5 | Build skill resume integration | M | Task 1, 4 |
| 2 | 6 | Dispatch convention manifest extensions | S | None |
| 2 | 7 | Secondary skill resume markers | S | Task 1 |
| 3 | 8 | Template mutation and structured diff | L | Task 4 |

**Total estimated complexity:** 2S + 3M + 2L (Wave 1 is the critical path)

**What "done" looks like for the whole feature:**
1. A `/build` run that crashes mid-Phase 3 can be resumed from the last wave boundary by re-running `/build` in the same scratch directory
2. `/replay <scratch-dir> --dry-run` accurately reports what would be re-dispatched
3. `/replay <scratch-dir> --from-phase 3` resumes from a specific phase boundary
4. `/replay <scratch-dir> --mutate qg-prompt.md=qg-v2-prompt.md --diff` replays with a template swap and produces a structured comparison
5. All existing pipelines work identically when no crash marker is present (zero behavioral change for the happy path)
