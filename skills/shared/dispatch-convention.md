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

1. **Before dispatching:** Measure the dispatch file size in characters (e.g., read the file, count characters). Append entry with `status: "dispatched"` and `input_chars` set to the measured character count. Include `model_tier` based on the dispatch decision (opus/sonnet/haiku). Set `output_chars` and `tool_calls` to null (not yet available).
2. **After dispatch returns:** Measure the subagent response length in characters. Append a new entry with the same `seq` and updated status/duration/summary. Set `output_chars` to the measured response length. Set `tool_calls` to the count of tool invocations if available from the response metadata, otherwise null. The last entry for a given `seq` is authoritative (append-only, no in-place rewrite — this preserves crash safety).
3. **After compaction:** If the last entry for a `seq` still shows `"dispatched"`, treat as needs-re-dispatch (conservative default)

**Measurement failure handling:** If the dispatch file is unreadable at measurement time (race condition, permission error), set `input_chars` to null for that entry. If the subagent response length is unavailable (agent crashed, timeout), set `output_chars` to null. Measurement failure must never block pipeline execution — the pipeline proceeds normally with null efficiency fields.

### Entry Format

```jsonl
{"seq":1,"file":"1-plan-writer.md","role":"plan-writer","phase":"2","task":null,"status":"completed","duration_s":83,"summary":"Plan written: 8 tasks, 3 waves","input_chars":12840,"output_chars":8200,"model_tier":"opus","tool_calls":5}
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
- `input_chars` — dispatch file size in characters, measured before dispatch (null for pre-enrichment entries or measurement failure)
- `output_chars` — subagent response length in characters, measured after completion (null for pre-enrichment entries, in-flight dispatches, or crashed subagents)
- `model_tier` — "opus", "sonnet", or "haiku" (null for pre-enrichment entries)
- `tool_calls` — count of tool invocations by the subagent (null if unavailable)

**Backward compatibility:** Entries without `input_chars`, `output_chars`, `model_tier`, or `tool_calls` (from pre-enrichment runs) are valid. Consumers must handle missing/null values gracefully.

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

### Token Estimation

The manifest's `input_chars` and `output_chars` fields enable token estimation using a character-to-token ratio.

**Methodology:** `estimated_tokens = chars / 4`. This uses the well-established approximation that 1 token ~= 4 characters for English text. For code-heavy content, 1 token ~= 3.5 characters, but `chars / 4` is used uniformly for simplicity and consistency.

**Accuracy:** +/-30% overall (+/-20% for pure prose, +/-25% for code, worse for mixed content with extended thinking or system prompt overhead). Estimates are directionally correct and suitable for relative comparison across runs. They are NOT suitable for billing or exact cost calculation.

**Known blind spots:**
- **Extended thinking tokens** — Opus subagents may use extended thinking, which consumes tokens not captured in the dispatch file or response. This causes underestimation of total token consumption for Opus dispatches.
- **Prompt cache effects** — Subagents share prompt caches. Cache-warm dispatches consume fewer actual tokens than estimated. This causes overestimation of cost for cache-warm subagents.
- **Context carry-forward** — Orchestrator context grows across dispatches. The orchestrator's own token consumption is not captured per-dispatch.
- **System prompt overhead** — Each subagent has a system prompt (~2000 tokens Opus, ~1500 Sonnet, ~800 Haiku) not reflected in `input_chars`.

**Aggregation:** At pipeline completion, compute totals from the manifest:
- `total_input_chars = sum(input_chars)` across all entries (skip nulls)
- `total_output_chars = sum(output_chars)` across all entries (skip nulls)
- `est_input_tokens = total_input_chars / 4` (rounded)
- `est_output_tokens = total_output_chars / 4` (rounded)
- `dispatches_by_tier = count of entries grouped by model_tier` (skip nulls)

**Rework analysis:** For any `seq` with multiple manifest entries where an earlier entry has `status: "failed"` or `status: "error"`, the subsequent retry's `input_chars + output_chars` count as rework. Compute separately:
- `rework_input_chars = sum(input_chars)` for retry entries only
- `rework_output_chars = sum(output_chars)` for retry entries only
- `est_rework_tokens = (rework_input_chars + rework_output_chars) / 4`
- `rework_pct = est_rework_tokens / (est_input_tokens + est_output_tokens) * 100`

These aggregates feed into the chronicle signal's `efficiency` sub-object (see forge-skill/SKILL.md Step 8.5).

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
