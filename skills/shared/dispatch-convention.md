---
version: 1
---

# Dispatch Convention

> Canonical reference for disk-mediated subagent dispatch across all orchestrator skills.
> Each orchestrator SKILL.md references this file via `<!-- CANONICAL: shared/dispatch-convention.md -->`.
>
> **This is a shared skill reference, not a CLAUDE.md directive.** CLAUDE.md must not duplicate dispatch rules.

## When to Use

**Disk-mediated dispatch (default):** All Agent tool and Task tool subagent dispatches.

**Paste-only exemption:** If a future template is under 500 tokens total payload, uses the Task tool, and needs no file access, it may skip disk-mediation. No current templates qualify — all were promoted to disk-mediated after validation.

**Excluded skills:** `skill-creator` is a meta-tool, not a production pipeline orchestrator. `stocktake` and `parallel` do not dispatch subagents.

## Dispatch Directory

**Path:** `/tmp/crucible-dispatch-<session-id>/`

**Session ID:** Reuse the pipeline's existing session identifier (timestamp-based ID generated at pipeline start). Skills invoked standalone that lack an existing session ID must generate one: Unix epoch seconds.

**Sub-skill inheritance:** Sub-skills (quality-gate, red-team, innovate, etc.) use the **parent orchestrator's dispatch directory and seq counter**. Two passing mechanisms:

1. **Subagent dispatches** (Agent/Task tool): The `Dispatch-Dir:` header field in the dispatch file carries the path. Subagents extract it and use it for their own dispatches.
2. **Skill invocations** (crucible:quality-gate, crucible:red-team, etc.): The parent orchestrator passes the dispatch directory path as part of the invocation context — e.g., "Dispatch directory: /tmp/crucible-dispatch-1775430161/" in the quality-gate/red-team input.

Sub-skills append to the existing `manifest.jsonl`. The parent is responsible for cleanup. The seq counter MUST be recovered from the manifest (last `seq` + 1) immediately before each dispatch — do not cache across dispatches. Nested sub-skills (e.g., quality-gate calling red-team) append entries to the shared manifest, so a cached counter goes stale.

**Fallback for missing path:** If a sub-skill receives no dispatch directory path (e.g., standalone invocation), create a new dispatch directory with a timestamp-based session ID. Do not glob for other sessions' directories — this would break session isolation under concurrent pipelines.

## File Naming

**Pattern:** `<N>-<template-name>.md`

The counter `N` increments per dispatch within the session. Template name makes files self-documenting. **Concurrent dispatches:** When dispatching multiple teammates in parallel, the parent orchestrator pre-allocates seq numbers before dispatch (e.g., assign seq 3, 4, 5 to three parallel implementers). This avoids counter collisions without shared state.

Examples:
- `1-plan-writer.md`
- `2-plan-reviewer.md`
- `3-build-implementer.md`
- `4-build-reviewer.md`

## Dispatch File Header

Every dispatch file begins with a 4-line audit header:

```markdown
# Dispatch: <template-name>
**Pipeline:** <skill-name> | **Phase:** <phase> | **Task:** <N>
**Timestamp:** <ISO-8601>
**Dispatch-Dir:** <dispatch directory path>

---
```

The `Dispatch-Dir` field enables sub-skill inheritance — when a sub-skill reads its dispatch file, it extracts this path and uses it for its own dispatches. The subagent reads from below the `---` onward. The header provides execution trace context.

## Pointer Prompt Format

The pointer prompt is what goes into the Agent tool `prompt` parameter (or Task tool `prompt:` field) and fossilizes in orchestrator history:

```
You are a [role] for [task summary].
Read your full instructions and context at [dispatch file path].
Begin by reading that file.
```

**Rules:**
- Role must be specific enough for error reporting (e.g., "code implementer for Task 3: Auth middleware", not just "implementer")
- Task summary is one clause, not a paragraph
- No file lists, no context, no instructions beyond "read the file"
- **Target:** 80 tokens. **Hard ceiling:** 120 tokens (full disk-mediated) or 300 tokens (hybrid mode)
- Pointer prompts between 80-120 tokens must justify the extra length with a role description that cannot be shortened without losing error-diagnostic specificity
- Token limits apply to the `prompt` parameter/field only, not to structured Task tool fields (`team_name`, `name`, `description`, `subagent_type`)
- "Begin by reading that file" establishes the first action, not the only action
- For teammate dispatches: mailbox/communication protocol instructions go in the dispatch file, not the pointer prompt

## Compaction Recovery

**On-disk marker (primary mechanism):** At dispatch-directory creation time, the orchestrator writes a marker to the pipeline's persistent scratch directory:

```
<scratch>/.dispatch-active-<session-id>
```

Format (two lines):
```
dispatch-dir: /tmp/crucible-dispatch-<session-id>/
seq: <current counter>
```

**After compaction:**
1. Glob for `.dispatch-active-*` in the pipeline's persistent scratch directory
2. Read `manifest.jsonl` to find the last entry's `seq` value + 1 as the next counter
3. Resume dispatching

This works for all 22 orchestrator skills regardless of whether they have Compression State Block support. CSB inclusion of the dispatch directory path is a secondary nice-to-have.

## Dispatch Manifest

Every dispatch directory includes `manifest.jsonl` — a structured execution trace. Manifest entries must remain under 4096 bytes (POSIX PIPE_BUF) to ensure atomic appends under concurrent access.

### Protocol: Write Before Dispatch

1. **Before dispatching:** Append entry with `status: "dispatched"`
2. **After dispatch returns:** Append a new entry with the same `seq` and updated status/duration/summary. The last entry for a given `seq` is authoritative (append-only, no in-place rewrite — this preserves crash safety).
3. **After compaction:** If the last entry for a `seq` still shows `"dispatched"`, treat as needs-re-dispatch (conservative default)

### Entry Format

```jsonl
{"seq":1,"file":"1-plan-writer.md","role":"plan-writer","phase":"2","task":null,"status":"completed","duration_s":83,"summary":"Plan written: 8 tasks, 3 waves"}
```

**Fields:**
- `seq` — dispatch sequence number (matches file counter)
- `file` — dispatch file name
- `role` — subagent role (implementer, reviewer, red-team, etc.)
- `phase` — pipeline phase
- `task` — task number (null for non-task dispatches)
- `status` — dispatched | completed | failed | skipped | error
- `duration_s` — wall clock seconds (null while dispatched)
- `summary` — one-line result from subagent output

### Re-dispatch Safety

Read-only agents (reviewers, red-team) can be re-dispatched safely — second runs overwrite the same outputs.

**Mutating agents (implementers):** Before re-dispatching after compaction, verify:
1. Dispatch file creation timestamp is recent (within current session)
2. Check for evidence of prior completion (commits, test results, output files)

### What the Manifest Enables

1. **Failure replay** — debugging skill reads manifest, re-runs failing dispatch from preserved file
2. **Forge execution data** — machine-readable trace of template failure rates, phase durations, iteration counts
3. **Pipeline resume (future)** — skip completed dispatches, restart from first failure

### Chronicle Compatibility

The manifest schema is designed to be chronicle-compatible. When the chronicle system is live, the cleanup step should transform completed manifest entries into chronicle signals (per-dispatch granularity). This wiring is deferred to chronicle implementation — this note documents the intent so the schema doesn't drift.

## Cleanup

**On successful pipeline completion:**
1. Copy `manifest.jsonl` to the pipeline's persistent scratch directory (for forge retrospectives)
2. Delete the dispatch directory

**On failure or escalation:**
1. Copy the full dispatch directory to the pipeline's persistent scratch directory (durable record for inspection and replay)
2. Leave the `/tmp` copy in place as well (`/tmp` is ephemeral; scratch copy is durable)

Pipeline completion steps (build Phase 4, debugging Phase 5, etc.) each include cleanup.

## Failure Handling

If a subagent cannot read its dispatch file, it must **abort immediately** and report the missing file path. No inline fallback — the subagent must not attempt to proceed without its instructions.

**Orchestrator responsibility:** Before dispatching, verify the dispatch file exists on disk. If the file is missing (e.g., after compaction or filesystem error), re-write the dispatch file from the template and re-dispatch. Never fall back to pasting instructions inline.

## Template Comment Header

Every dispatch template file gets this comment:

```markdown
<!-- DISPATCH: disk-mediated | This template is written to a dispatch file,
     not pasted into the Agent tool prompt. See shared/dispatch-convention.md -->
```

Files with multiple dispatch prompts (e.g., `investigation-prompts.md`) get the header on each distinct prompt section. A file-level header is sufficient when all prompts in the file share the same dispatch mode.

Template expansion follows the existing bracket-placeholder pattern (`{{variable}}`). Disk-mediated dispatch changes delivery, not composition.

**Note:** Existing `[PASTE: ...]` placeholders in templates are expansion markers, not delivery instructions. They indicate what content the orchestrator substitutes before writing the dispatch file. This syntax coexists with the `{{variable}}` pattern and is exempt from AC #7 (no paste-into-prompt language).
