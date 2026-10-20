# Build — Pipeline Status and Compaction

## Contents

- [Pipeline Status](#pipeline-status)
  - [Write Triggers](#write-triggers)
  - [Status File Format](#status-file-format)
  - [Skill-Specific Body](#skill-specific-body)
  - [Health State Machine](#health-state-machine)
  - [Inline CLI Format](#inline-cli-format)
  - [Compaction Recovery](#compaction-recovery)
  - [Compression State Block](#compression-state-block)
  - [Checkpoint Timing](#checkpoint-timing)
  - [Phase Handoff Manifest](#phase-handoff-manifest)

## Pipeline Status

<!-- CANONICAL: shared/pipeline-status-convention.md (shared header, health state machine, events buffer, inline CLI, compaction recovery; build keeps only its skill-specific body + YELLOW/RED triggers) -->
**Runtime tool (preferred — the format below is the skill-specific reference).** Compose the shared header/health/events with `python3 scripts/pipeline_status.py write --path <build-scratch>/pipeline-status.md --skill build --phase … --health … [--event …] --body-file <skill-body.md>` (see `shared/pipeline-status-convention.md`); hand-compose only build's skill-specific body (`## Task Progress`, `## Quality Gates`, `## Checkpoints`, `## Compression State`).

Write `<build-scratch>/pipeline-status.md` at every narration point. This file is overwritten (not appended) and provides ambient awareness for the user in a second terminal.

### Write Triggers

Write the status file at every point where the Communication Requirement mandates narration: before dispatch, after completion, phase transitions, health changes, escalations, and after compaction recovery.

### Status File Format

The status file uses this structure (overwritten in full each time):

```
# Pipeline Status
**Updated:** <current timestamp>
**Started:** <timestamp from first write — persisted across compaction>
**Skill:** build
**Phase:** <current phase, e.g. "3 — Execute (Autonomous)">
**Health:** <GREEN|YELLOW|RED>
**Suggested Action:** <omit when GREEN; concrete one-sentence action when YELLOW/RED>
**Elapsed:** <computed from Started>

## Recent Events
- [HH:MM] <most recent event>
- [HH:MM] <previous event>
(last 5 events, newest first)
```

### Skill-Specific Body

Append after the shared header:

```
## Task Progress
| # | Task | Tier | Status | Duration |
|---|------|------|--------|----------|
| 1 | Auth middleware | T3 | DONE | 12m |
| 2 | Route handlers | T2 | IN REVIEW (code, pass 1) | 18m+ |
| 3 | Database layer | T1 | PENDING | — |

## Quality Gates
- Design: PASSED (2 rounds)
- Plan: PASSED (1 round)
- Task tiers: 1x T1, 1x T2, 1x T3
- Code: not yet reached
- QG-leg model assurance: <verified | configured | unknown> (the recorded `QGModelAssurance` claim, copied from the marker and not re-proved here — the quality-gate leg only, never a build-wide or Warden-wide claim; `caller_allowed` is the only proof)

## Checkpoints
- Last checkpoint: pre-wave-3 (12:45:30)
- Total checkpoints: 7
- Shadow repo: healthy

## Compression State
Goal: [original user request]
Key Decisions:
- [accumulated decisions, max 10]
Active Constraints:
- [constraints affecting remaining work]
Next Steps:
1. [immediate next action]
2. [subsequent actions]
```

The Compression State section is a semantic subset of the full Compression State Block emitted into the conversation. It omits Files Modified (recoverable from git) and Scratch State (fixed per skill). It is the first section read during compaction recovery.

### Health State Machine

Health transitions are one-directional within a phase: GREEN -> YELLOW -> RED. Phase boundaries reset to GREEN.

- **Phase boundaries** (reset to GREEN): Phase 1->2, 2->3, 3->4
- **YELLOW:** review loop round 3+, quality gate round 5+, retry in progress
- **RED:** escalation pending, stagnation detected, test suite failure unresolved

When health is YELLOW or RED, include `**Suggested Action:**` with a concrete, context-specific sentence (e.g., "Code review looping on Task 4. Check recent events for recurring patterns.").

### Inline CLI Format

Output concise inline status alongside the status file write:
- **Minor transitions** (dispatch, completion): one-liner, e.g. `Phase 3 [4/8] Task 4 IN REVIEW (pass 1) | GREEN | 1h 12m`
- **Phase changes and escalations**: expanded block with `---` separators
- **Health transitions**: always expanded with old -> new health

### Compaction Recovery

After compaction, before re-writing the status file:
0. Read the `## Compression State` section from `<build-scratch>/pipeline-status.md` — recover Goal, Key Decisions, Active Constraints, and Next Steps. If the section is absent (pre-update pipeline), skip to step 1.
<!-- TRUST: dispatch manifest is L2 — produced by prior pipeline stage; prefer most recent if conflicting. -->
0.5. Check for handoff manifests (`handoff-*-to-*.md`) in `<build-scratch>`. If the most recent manifest exists, use its Inputs, Decisions, and Constraints to reconstruct state for the current phase — this supersedes the Compression State section for phase-boundary recovery. If no manifest exists, continue with CSB-based recovery.
1. Read the rest of `<build-scratch>/pipeline-status.md` to recover `Started` timestamp and `Recent Events` buffer
2. Reconstruct phase, health, and skill-specific body from internal state files
3. If crucible:checkpoint was used: verify checkpoint availability by checking for the shadow repo at the computed path. Log available checkpoint count. Do not restore — just confirm checkpoints are recoverable.
4. Emit a Compression State Block into the conversation to seed the new context window with recovered state
4.5. **Read session index summary (supplementary):** If the CSB Scratch State contains a `Session Index:` path, or if globbing `~/.claude/projects/<hash>/memory/session-index/*/summary.md` finds a recent file, read `summary.md`. Include the Activity Timeline, Files Modified, and Key Decisions sections in the post-compaction narration. If no session index exists, skip silently — this step is purely additive. If `summary.md` lacks detail for a specific event type (e.g., errors, decisions, file changes), use the recall reference (`/getting-started recall <query>`, `getting-started/recall.md`) to query `events.jsonl` with filters for targeted recovery.
5. Write the updated status file
6. Output inline status to CLI

### Compression State Block

At checkpoint boundaries (see Checkpoint Timing below), emit the following structured block into the conversation. This block signals to the auto-compactor which state is critical to preserve. Also persist the semantic subset (Goal, Key Decisions, Active Constraints, Next Steps) to the `## Compression State` section of `<build-scratch>/pipeline-status.md`.

```
===COMPRESSION_STATE===
Goal: [original user request, one sentence]
Skill: [skill name]
Phase: [current phase identifier]
Health: [GREEN|YELLOW|RED]
Mode: [skill-specific mode if applicable, omit otherwise]

Progress:
- [completed milestone 1]
- [completed milestone 2]
- [current work in progress]

Key Decisions (this session):
- [DEC-1] [decision]: [reasoning, one line]
- [DEC-2] [decision]: [reasoning, one line]

Active Constraints:
- [constraint that affects remaining work]
- [constraint from prior phase that still applies]

Files Modified:
- [file path]: [what changed, one line]

Scratch State:
- Location: [scratch directory path]
- Session Index: [~/.claude/projects/<hash>/memory/session-index/<session-id>/ if active, omit if not]
- Recovery: [which files to read first, in order]

Next Steps:
1. [immediate next action]
2. [action after that]
3. [remaining work summary]
===END_COMPRESSION_STATE===
```

**Rules:**
- Key Decisions list is capped at 10. When adding an 11th, compress the oldest low-impact decision into a single-line Progress entry annotated "[compressed from decisions]".
- Each Compression State Block includes the FULL accumulated decision list, not just new decisions since the last block. Decisions accumulate across compressions.
- Progress entries are cumulative — include all completed milestones, not just since the last block.
- Files Modified lists only files changed since the last block emission. On first block of a session, list all files changed so far.
- Goal must be the original user request verbatim or a faithful one-sentence paraphrase. Do not let it drift across compressions.

### Checkpoint Timing

Emit a Compression State Block into the conversation AND update the `## Compression State` section in `<build-scratch>/pipeline-status.md` at these points:

- **Phase transitions:** 1→2, 2→3, 3→4 — emit a **Phase Handoff Manifest** (see below) instead of a Compression State Block at these points
- **Phase 3 progress:** After every 3 task completions
- **Quality gate entry/exit:** Before first quality gate round dispatch and after gate completes (pass or escalation)
- **Escalations:** Before any escalation to user
- **Health transitions:** On any GREEN->YELLOW or YELLOW->RED transition

These triggers are a superset of the existing `<build-scratch>/pipeline-status.md` write triggers. The Compression State Block is emitted alongside (not instead of) the normal narration and status file write.

### Phase Handoff Manifest

At phase boundaries (1→2, 2→3, 3→4), write a **handoff manifest** to `<build-scratch>` instead of emitting a Compression State Block. The manifest defines exactly what the next phase needs — an allowlist, not a denylist. Everything not on the manifest is shed.

**Format:**

```markdown
# Phase Handoff: N → M
**Timestamp:** ISO-8601
**Goal:** [original user request, verbatim]
**Mode:** feature | refactor
**RequiredModelAssurance:** qg-verified   <!-- only when the ledger persists qg-verified; omit the line for none/absent (#746) -->

## Inputs for Phase M
- **[Input name]:** [disk path or inline value]

## Decisions Carried Forward
- [DEC-N] [decision]: [reasoning, one line]

## Active Constraints
- [constraint affecting remaining work]

## Shed Receipt
- [what was shed] → [where it lives on disk]
```

**Rules:**
- When the gate ledger persists `RequiredModelAssurance: qg-verified`, every handoff manifest carries the `**RequiredModelAssurance:** qg-verified` header line (the only opt-in signal ledger reconstruction reads); for `none` or absent the line is omitted.
- After writing the manifest, emit an explicit **shed statement**: list what context is no longer needed, where it lives on disk, and that the orchestrator operates from manifest inputs only going forward.
- After writing the manifest, update the `## Compression State` section in `<build-scratch>/pipeline-status.md` with the manifest contents (Goal, Decisions, Constraints, and the Inputs as Next Steps). This ensures compaction recovery can reconstruct state even if the manifest is lost.
- CSBs continue at all non-boundary checkpoint triggers (intra-phase progress, quality gate entry/exit, escalations, health transitions).
- **Backward compatibility:** If a handoff manifest does not exist at a recovery point, fall back to CSB-based recovery (existing behavior).
