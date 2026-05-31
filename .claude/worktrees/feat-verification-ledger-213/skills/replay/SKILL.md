---
name: replay
description: "Resume interrupted pipelines from dispatch manifests, or replay historical pipelines with template mutations for A/B experimentation. Triggers on /replay, 'resume pipeline', 'replay build', 'A/B test templates'."
---

# Pipeline Replay

## Overview

<!-- CANONICAL: shared/dispatch-convention.md -->
All subagent dispatches use disk-mediated dispatch. See `shared/dispatch-convention.md` for the full protocol.

Resume interrupted pipelines from their last successful phase boundary, or replay historical pipelines with mutated dispatch templates for A/B experimentation. Reads dispatch manifests, correlates with shadow git checkpoints, reconstructs orchestrator state from disk, and re-dispatches from the resume point.

**Announce at start:** "Using replay to [resume interrupted pipeline / replay pipeline with template mutations]."

**Skill type:** Orchestrator -- dispatches subagents via existing dispatch convention. Does NOT re-implement pipeline phases -- restores state and delegates to the original skill's phase logic.

**Key insight:** The dispatch convention was explicitly designed for this. Manifests, dispatch files, and checkpoints are all on disk. Replay is the orchestration layer that reads them and re-dispatches.

## Invocation

```
/replay <scratch-dir-or-manifest-path> [options]
```

**Options:**
- `--from-phase <N>` -- Resume from phase N boundary (overrides auto-detection)
- `--from-seq <N>` -- Resume from dispatch sequence N (finds enclosing phase boundary)
- `--mutate <original>=<replacement>` -- Swap dispatch template (repeatable for multi-template experiments)
- `--diff` -- Compare replayed vs original outcomes after completion
- `--dry-run` -- Show what would be re-dispatched without executing
- `--template-ref <sha>` -- Pin templates to a git ref (for controlled A/B experiments)

**Path resolution:**
- If path ends in `manifest.jsonl`: use directly
- If path is a directory: look for `manifest.jsonl` in that directory, then in `<path>/dispatch-*/manifest.jsonl`
- If path matches a scratch directory: read `.pipeline-active` to find the dispatch directory, then read its manifest

## Modes

### Resume Mode (default)

Active when no `--mutate` flag is present. Restores checkpoint, reconstructs state, and re-dispatches from the last verified phase boundary.

- Appends to existing `manifest.jsonl` with normal status lifecycle (`dispatched` -> `completed`)
- New entries carry `replay_of` back-referencing the original `seq` and `replay_session` identifying this run
- Uses current templates (not pinned -- you want the latest fixes)

### A/B Mode (`--mutate`)

Same as resume but with template substitutions at dispatch time. Produces structured diff output when combined with `--diff`.

- Templates are swapped at dispatch file write time
- Original manifest entries are never modified
- Mutated dispatches are marked with `mutation: "original.md -> replacement.md"` in manifest
- Warns if any dispatched template's modification time is newer than the original manifest timestamp

### Dry-Run Mode (`--dry-run`)

Analyzes the manifest, identifies the resume point, and lists what would be re-dispatched. No state changes, no dispatches, no checkpoint restores.

Output format:
```
# Replay Plan (dry-run)

**Source:** <manifest path>
**Original pipeline:** <skill> | Session: <id> | Started: <timestamp>
**Crashed at:** Phase <N>, <context>
**Resume point:** Phase <M> boundary (<checkpoint reason>)
**Work preserved:** <time estimate> (phases 1 through M-1)

## Dispatches to skip (verified complete)
| Seq | Role | Phase | Summary |
|-----|------|-------|---------|
| ... | ...  | ...   | ...     |

## Dispatches to re-execute
| Seq | Role | Phase | Original Status | Template |
|-----|------|-------|-----------------|----------|
| ... | ...  | ...   | ...             | ...      |

## Template Mutations (if --mutate specified)
- <original> -> <replacement>
```

## Step 1: Read and Parse Manifest

Read the manifest from the provided path. Handle errors gracefully:

1. **Read line-by-line.** For each line, attempt JSON parse. On parse error, log a warning with the line number and skip the line. This handles truncated manifests from mid-write crashes.
2. **Deduplicate by seq.** Multiple entries per `seq` is normal (dispatched -> completed). The last entry for each `seq` is authoritative.
3. **Build phase map.** Group entries by `phase` field. Within each phase, track the set of dispatches and their final statuses.
4. **If zero valid entries:** Report "Manifest is empty or entirely corrupted. Cannot resume." and exit.

**Manifest location priority:**
1. Scratch directory copy (`<scratch>/crucible-dispatch-<session-id>/manifest.jsonl`) -- durable, survives `/tmp` loss
2. Original dispatch directory (`/tmp/crucible-dispatch-<session-id>/manifest.jsonl`) -- may not survive reboot
3. If neither exists: report "Manifest not found. Cannot resume." and exit

## Step 2: Identify Phase Boundaries

Partition the manifest into completed and incomplete phases:

1. **For each phase in order:** Check whether ALL dispatches in that phase have `status: "completed"`. A phase is complete if and only if every dispatch within it reached completion.
2. **Handle in-flight dispatches:** Entries with `status: "dispatched"` (no completion entry) indicate a dispatch that was in flight when the crash occurred. The enclosing phase is incomplete.
3. **Identify the resume point:** The latest phase boundary where all prior phases are complete. This is where replay will restore and re-dispatch.

**Phase boundary mapping for build pipelines:**

| Phase Boundary | Checkpoint Reason | When |
|---------------|-------------------|------|
| Pre-Phase 2 | `pre-design-gate` | After design approval, before planning |
| Late Phase 2 | `pre-plan-gate` | After plan approval, before execution |
| Pre-Phase 3 | `pre-wave-1` | After plan approval, before first execution wave |
| Mid-Phase 3 (wave N) | `pre-wave-N` | After wave N-1 completion |
| Pre-Phase 4 | `pre-code-review` | After all execution waves complete |
| Mid-Phase 4 | `pre-inquisitor` | After code review, before inquisitor |
| Late Phase 4 | `pre-impl-gate` | After inquisitor, before quality gate |

**`--from-phase` override:** If the user specified a phase, use that boundary instead of auto-detection. Warn if the specified phase is earlier than the auto-detected resume point (the user is choosing to redo verified work).

**`--from-seq` resolution:** Find the phase containing the specified seq number. Resume from the start of that phase (not mid-phase).

## Step 3: Verify Artifacts

Before committing to a resume point, verify that completed dispatches actually produced their expected artifacts:

1. **For each `completed` dispatch before the resume point:**
   a. **Mutating agents (implementers):** Check `git log --oneline` for commits that match the dispatch's time window and task description patterns. If no matching commits found but manifest says completed, the manifest may be stale -- fall back to earlier boundary.
   b. **Output-producing agents (reviewers, red-team):** Check that dispatch output files exist in the dispatch directory or scratch copy.
   c. **Non-artifact agents (quality-gate rounds):** No verification needed -- these produce conversation output only.

2. **Verification failure:** If any expected artifact is missing for a completed dispatch:
   a. Log which dispatch failed verification and why
   b. Fall back to the previous phase boundary
   c. If fallback also fails verification, continue falling back until a verified boundary is found or no boundaries remain
   d. If no verified boundary exists: report the situation and offer "resume with current disk state" or "start fresh"

3. **Partial commit detection:** For implementer dispatches near the crash point:
   a. Check git log for commits attributed to the dispatch (timestamp matching, commit message patterns)
   b. If partial commits found: the checkpoint restore in Step 4 will revert them (checkpoints predate the partial work)
   c. If no commits found: safe to re-dispatch from the phase boundary

## Step 4: Checkpoint Correlation and Restore

Map the verified resume point to a shadow git checkpoint:

### Checkpoint Lookup

1. **Read `checkpoint-manifest.md`** from `~/.claude/projects/<hash>/checkpoints/<dir-hash>/`
2. **Match checkpoint reason** to the resume point's phase boundary. Use string prefix matching:
   - Pre-Phase 2 boundary -> checkpoint reason starts with `pre-design-gate`
   - Late Phase 2 boundary -> checkpoint reason starts with `pre-plan-gate`
   - Phase 3 boundary -> checkpoint reason starts with `pre-wave-1`
   - Phase 3 wave N -> checkpoint reason starts with `pre-wave-N`
   - Phase 4 boundary -> checkpoint reason starts with `pre-code-review`
   - Phase 4 mid -> checkpoint reason starts with `pre-inquisitor`
   - Phase 4 late -> checkpoint reason starts with `pre-impl-gate`
3. **If multiple checkpoints match** (e.g., multiple `pre-wave-2` entries from retries): use the most recent by timestamp.

### Fallback Chain

If the desired checkpoint is missing (evicted, shadow repo reinitialized, pre-checkpoint-era pipeline):

1. Fall back to the nearest earlier checkpoint
2. Adjust the resume point to match the available checkpoint (replay resumes from checkpoint state, not from a state that no longer exists on disk)
3. Warn the user: "Desired checkpoint [reason] not found. Falling back to [earlier checkpoint]. Replaying from Phase [M] instead of Phase [N]."
4. If NO checkpoints exist: warn that filesystem state cannot be guaranteed. Offer:
   a. "Resume with current disk state" -- risky but may work if disk state is close to a clean boundary
   b. "Start fresh" -- safe, loses all prior work

### Restore

**Branch guard (mandatory):** Before offering restore, check the `.pipeline-active` marker's `branch` field against the current `git branch --show-current`. If they differ, abort with:

> "Pipeline was running on branch [marker.branch] but you are on [current-branch]. Switch to [marker.branch] before resuming — restoring a checkpoint from a different branch would contaminate your working directory."

Do NOT proceed with restore on the wrong branch. This is a data-safety invariant.

**Before any restore, require explicit user confirmation:**

> "About to restore working directory to checkpoint [reason] (taken at [timestamp], branch [marker.branch]). This will reset uncommitted changes. Proceed? [yes / no]"

On confirmation:
1. Use the shadow git repo to restore the working directory to the checkpoint state
2. Verify the restore succeeded (check key files exist, git status is clean)

## Step 5: State Reconstruction

Reconstruct the orchestrator's internal state from disk sources. This seeds the new context window with enough information to continue the pipeline mid-flight.

**Sources, in priority order:**

1. **Phase Handoff Manifests** (`handoff-N-to-M.md` in scratch directory)
   - If resuming at a phase boundary and the handoff manifest exists, this is the primary state source
   - Contains: Goal, Mode, Inputs for next phase, Decisions Carried Forward, Active Constraints, Shed Receipt
   - This is the richest state source -- prefer it over all others when available

2. **Pipeline-status.md Compression State** (`~/.claude/projects/<hash>/memory/pipeline-status.md`)
   - Read the `## Compression State` section for: Goal, Key Decisions, Active Constraints, Next Steps
   - Fallback when handoff manifest is missing

3. **Manifest entries** (from Step 1)
   - seq/role/phase/status/summary for all prior dispatches
   - Reconstructs what happened: which agents ran, what they produced, how long they took

4. **Dispatch files on disk** (in dispatch directory or scratch copy)
   - Full subagent instructions for any dispatch that needs re-execution
   - If missing, regenerate from template + manifest metadata (role, phase, task are all recorded)

5. **Shadow git checkpoint** (from Step 4)
   - Filesystem state at the resume point
   - The foundation -- all code, test, and config files at the exact state they were when the checkpoint was taken

6. **Build mode file** (`/tmp/crucible-build-mode.md`)
   - Mode (feature/refactor) and baseline commit SHA
   - If missing (ephemeral /tmp lost): default to feature mode and warn

### Emit Synthetic CSB

From the combined state, construct and emit a Compression State Block:

```
===COMPRESSION_STATE===
Goal: [from handoff manifest or pipeline-status.md]
Skill: [from .pipeline-active marker]
Phase: [resume phase]
Health: GREEN (reset on resume)

Progress:
- Phases 1 through [N-1] completed in prior session
- Resuming from [checkpoint reason] via replay
- [key milestones from manifest summaries]

Key Decisions (prior session):
- [decisions from handoff manifest or pipeline-status.md]

Active Constraints:
- [constraints from handoff manifest or pipeline-status.md]
- Replay session -- prior work verified through Phase [N-1]

Files Modified:
- [recovered from checkpoint diff if available, or "see git log"]

Scratch State:
- Location: [scratch directory path]
- Recovery: pipeline-status.md, handoff manifests, manifest.jsonl

Next Steps:
1. [first action for the resumed phase]
2. [subsequent actions from handoff manifest or manifest analysis]
===END_COMPRESSION_STATE===
```

## Step 6: Re-Dispatch

After checkpoint restore and state reconstruction, hand off to the original skill's phase logic:

### Build Pipeline Resume

1. **Resuming at Phase 2 (plan):** Invoke build's Phase 2 flow with the design doc from the handoff manifest inputs.
2. **Resuming at Phase 3 (execute):** Invoke build's Phase 3 flow. If resuming mid-Phase 3 (wave N), start from wave N -- prior waves are verified complete.
3. **Resuming at Phase 4 (completion):** Invoke build's Phase 4 flow with HEAD SHA from the checkpoint.

### Manifest Continuation

New dispatches during replay append to the original `manifest.jsonl`:

- **Seq numbering:** Continue from the last `seq` in the manifest + 1
- **Status field:** Use normal status lifecycle (`"dispatched"` -> `"completed"`, etc.) for all dispatches during replay. Replay provenance is tracked via `replay_of` and `replay_session`, not via the status field. This ensures existing manifest readers (compaction recovery, forge, debugging) handle replay entries correctly.
- **`replay_of` field:** Set to the original `seq` number when re-dispatching a previously attempted dispatch. Set to `null` for new dispatches that have no original counterpart.
- **`replay_session` field:** Set to the current session ID for all entries written during a replay run.
- **`mutation` field:** Set to `"original.md -> replacement.md"` if a template mutation was applied. `null` otherwise.

### Delegation

The replay skill does NOT re-implement build phases. After emitting the synthetic CSB and setting up the manifest continuation, replay delegates to the build skill's existing phase logic. The build skill continues as if it had just crossed a phase boundary -- the CSB seeds its context, the manifest is ready for new entries, and the working directory is at the checkpoint state.

**For non-build skills (future):** The same pattern applies -- replay restores state and delegates to the original skill. The phase structure and checkpoint reasons are skill-specific, but the restore/reconstruct/delegate pattern is universal.

## Step 7: Template Mutation (A/B Mode)

Active only when `--mutate` is specified. This step modifies dispatch behavior during re-execution.

### Mutation Parsing

Parse each `--mutate` argument:
- Format: `<original-template>=<replacement-path>`
- `original-template` is a filename (e.g., `quality-gate-prompt.md`)
- `replacement-path` is a path to the replacement template file
- Multiple `--mutate` flags are allowed for multi-template experiments
- Validate that replacement files exist before starting replay

### Dispatch-Time Substitution

When writing a dispatch file during re-execution:

1. Check if the dispatch's template filename matches any mutation's `original-template`
2. If matched: read the replacement template instead of the original. Write the dispatch file with the replacement template content but the same audit header (pipeline, phase, task metadata) and the same context injections (cartographer data, defect signatures, etc.)
3. Record the mutation in the manifest entry: `"mutation": "original.md -> replacement.md"`
4. If not matched: dispatch normally (no mutation)

### Template Staleness Warning

In A/B mode, check each dispatched template's modification time against the original manifest's first entry timestamp. If any template is newer:

> "Warning: Template [name] was modified after the original pipeline run. A/B comparison may be confounded by template changes unrelated to the mutation."

### Template Pinning (`--template-ref`)

When `--template-ref <sha>` is specified:
1. Check out the skill templates from the specified git ref into a temporary directory
2. Use those templates for all dispatches (overrides current templates)
3. Apply mutations on top of the pinned templates
4. This ensures the only variable in the A/B experiment is the explicit mutation

## Step 8: Structured Diff Output (A/B Mode + `--diff`)

Active when both `--mutate` and `--diff` are specified. Produces a comparison report after the replay completes.

### Data Collection

1. Read the full manifest (now containing both original and replayed entries)
2. Match replayed entries to originals via the `replay_of` field
3. Collect metrics:
   - Total dispatch count (original vs replayed)
   - Per-phase dispatch count
   - Quality gate round counts (count entries with `role: "red-team"` or `role: "quality-gate"` per phase)
   - Total wall clock time (from first to last entry timestamps)
   - Per-dispatch durations
   - Acceptance test outcomes (from manifest summaries of test-running dispatches)

### Diff Output (Markdown)

```markdown
# Replay Diff: <original-session> vs <replay-session>

## Template Mutations
- <original.md> -> <replacement.md>

## Outcome Comparison
| Metric | Original | Replayed | Delta |
|--------|----------|----------|-------|
| Total dispatches | N | M | +/-X |
| Quality gate rounds | N | M | +/-X |
| Wall clock time | Xh Ym | Xh Ym | +/-Zm |
| Acceptance tests | PASS/FAIL | PASS/FAIL | =/changed |

## Per-Dispatch Comparison
| Seq | Role | Original Status | Replayed Status | Summary Delta |
|-----|------|----------------|-----------------|---------------|
| N | role | status | status | brief comparison |

## Artifact Diff
- git diff <original-final-sha>..<replayed-final-sha>
  N files changed, +X/-Y lines
```

### Diff Output (JSONL -- machine-readable)

Append a structured signal to the manifest directory:

```jsonl
{"type":"replay-diff","original_session":"...","replay_session":"...","mutations":["original.md -> replacement.md"],"metrics":{"original_dispatches":N,"replayed_dispatches":M,"original_gate_rounds":N,"replayed_gate_rounds":M,"original_duration_m":N,"replayed_duration_m":M},"outcome":{"original":"PASS","replayed":"PASS"},"artifact_diff":{"files_changed":N,"insertions":X,"deletions":Y}}
```

This output is designed to be:
- **Human-readable** (markdown tables) for decision-making
- **Machine-readable** (JSONL) for future chronicle/eval integration
- **Eval-compatible** -- structured input/output pairs from real pipelines, suitable for skill-creator eval generation

## Edge Cases

### Corrupted or Truncated Manifest

Handled in Step 1: per-line JSON parse with error handling. The last valid entry per seq is authoritative. Zero valid entries = cannot resume.

### Missing Checkpoint

Handled in Step 4 fallback chain: earlier checkpoint -> no checkpoint with user choice.

### Missing Dispatch Files

If dispatch files are missing from both the dispatch directory and scratch copy:
1. Regenerate from template + manifest metadata (role, phase, task are recorded in the manifest)
2. If the template itself is unavailable (skill files changed between sessions): warn that faithful replay is impossible. Offer to proceed with current templates or abort.

### Dispatch Directory in `/tmp` Lost

`/tmp` is ephemeral. If the machine rebooted, the dispatch directory is gone. But:
1. The cleanup rules copy the full dispatch directory to the scratch directory on failure
2. Resume reads from the scratch copy preferentially (Step 1 manifest location priority)
3. If both are missing: the manifest survives in scratch, but dispatch files must be regenerated

### Stale Templates Between Sessions

Between crash and resume, templates may have been modified. For resume mode this is fine (you want current-best templates). For A/B mode it is a confound -- the staleness warning in Step 7 catches this.

### Partially Committed Mutating Agent

A crash can occur after an implementer commits 2 of 3 files. At resume:
1. Check git log for commits attributed to the dispatch (timestamp + commit message patterns)
2. If partial commits found: the checkpoint restore (Step 4) reverts to the phase boundary state, which predates the partial work. The entire wave is re-dispatched.
3. If no commits found: safe to re-dispatch from the same point

## Interaction with Other Systems

### Quality Gates

Quality gates during replay follow the same rules as normal runs. A replayed pipeline may have different model versions, different codebase state, or mutated templates -- the quality gate must verify independently.

### Dispatch Convention

No changes to the core dispatch protocol. Replay appends to existing manifests and writes dispatch files following the same naming convention. The `replay_of`, `replay_session`, and `mutation` fields are additive and backward-compatible.

### Forge Chronicle

Replay runs generate chronicle signals with `replay_source` field linking to the original manifest. Replay diffs are a separate signal type (`skill: "replay-diff"`). Chronicle integration is deferred to chronicle implementation -- the schema is forward-compatible.

### Checkpoint System

Replay consumes checkpoints (reads and restores) but does not modify the checkpoint system. New checkpoints are created during the resumed pipeline execution by the normal checkpoint triggers in the delegated skill.

## Security

- **Replay does not escalate permissions** -- replayed dispatches run with the same tool access as normal dispatches
- **Template mutation is user-initiated** -- all mutations are explicit CLI arguments, no automatic template swapping
- **Checkpoint restore is user-confirmed** -- the resume prompt requires explicit acceptance before filesystem changes
- **A/B mode does not modify the original manifest** -- original entries are preserved, replay entries are appended with clear `replay_of` linkage
