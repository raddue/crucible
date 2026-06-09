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

**Excluded skills:** `skill-creator` is a meta-tool, not a production pipeline orchestrator (its dispatches are A/B eval test-runs, not pipeline work). `stocktake`'s only subagent use is a single read-only Explore evaluation agent — not a disk-mediated pipeline dispatch. (`parallel` is a production dispatcher and is NOT excluded: it follows this convention and links it as canonical.)

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

## Pipeline-Active Marker

**Purpose:** Detect interrupted (crashed) pipelines across sessions. The dispatch-active marker (below, in Compaction Recovery) handles within-session compaction recovery. The pipeline-active marker handles cross-session crash detection.

**Path:** `<scratch>/.pipeline-active`

**Format (JSON):**
```json
{
  "pipeline_id": "<session-id>",
  "skill": "<skill-name>",
  "phase": "<current-phase>",
  "start_time": "<ISO-8601>",
  "scratch_dir": "<scratch directory path>",
  "dispatch_dir": "/tmp/crucible-dispatch-<session-id>/",
  "branch": "<git branch at pipeline start>",
  "baseline_sha": "<HEAD SHA at pipeline start>"
}
```

**Lifecycle:**
1. **Write** at pipeline start -- before the first dispatch, after the dispatch directory is created
2. **Update** at phase boundaries -- update the `phase` field to track progress
3. **Delete** on successful pipeline completion -- the final cleanup step removes the marker
4. **Leave in place on crash** -- the marker's presence with a non-current session ID IS the crash signal

**Detection (at pipeline start):**
1. Check `<scratch>/.pipeline-active`
2. Not found -> write marker (include `branch` from `git branch --show-current` and `baseline_sha` from `git rev-parse HEAD`), proceed normally
3. Found, same `pipeline_id` as current session -> compaction recovery (within-session, existing behavior)
4. Found, different `pipeline_id` -> previous pipeline crashed. Check `branch` field against current `git branch --show-current`:
   - **Branch matches:** offer resume per the skill's resume logic (see `crucible:replay` for full orchestration, or per-skill detection-only for secondary skills)
   - **Branch mismatch:** warn the user: *"Previous [skill] on branch [marker.branch] crashed at Phase [phase]. You are currently on [current-branch]. Switch to [marker.branch] before resuming? [switch+resume / start fresh / abort]"*. Do NOT proceed with resume on the wrong branch — checkpoint restore would contaminate the current branch.

**Where `<scratch>` is:** The pipeline's persistent scratch directory (`~/.claude/projects/<hash>/memory/`).

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

**Session index integration (supplementary):** When session indexing is active (PostToolUse hook configured), include the session index path in the CSB Scratch State section:
```
Session Index: ~/.claude/projects/<hash>/memory/session-index/<session-id>/
```
After compaction, skills can read `summary.md` from this path for narrative context that supplements the CSB's authoritative state. If the session-id is lost, glob `~/.claude/projects/<hash>/memory/session-index/*/events.jsonl` and pick the most recently modified directory. See `skills/shared/session-index-convention.md` for details.

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
- `replay_of` — seq number of the original dispatch being replayed (null or absent for non-replay entries)
- `replay_session` — session ID of the replay run (null or absent for non-replay entries)
- `mutation` — template mutation applied during replay, e.g. `"original.md -> replacement.md"` (null or absent for non-replay or faithful replay entries)

**Backward compatibility:** Entries without efficiency fields (`input_chars`, `output_chars`, `model_tier`, `tool_calls`) or replay fields (`replay_of`, `replay_session`, `mutation`) are valid. Consumers must handle missing/null values gracefully.

### Re-dispatch Safety

Read-only agents (reviewers, red-team) can be re-dispatched safely — second runs overwrite the same outputs.

**Mutating agents (implementers):** Before re-dispatching after compaction, verify:
1. Dispatch file creation timestamp is recent (within current session)
2. Check for evidence of prior completion (commits, test results, output files)

**Cross-session re-dispatch (replay):** The `crucible:replay` skill performs artifact verification before any cross-session re-dispatch -- checking git log for expected commits and verifying output files exist. This is the canonical pre-dispatch check for resume scenarios. See replay skill for details.

### What the Manifest Enables

1. **Failure replay** — debugging skill reads manifest, re-runs failing dispatch from preserved file
2. **Forge execution data** — machine-readable trace of template failure rates, phase durations, iteration counts
3. **Pipeline replay** — resume from crash or replay with template mutations (see `crucible:replay`)

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

These aggregates feed into the chronicle signal's `efficiency` sub-object (see forge/SKILL.md Step 8.5).

## Receipt Ledger

Every dispatch directory also contains `receipt-ledger.jsonl` — the **Layer 1 receipt ledger**, a sibling of `manifest.jsonl`, written by the orchestrator per the Parent-Child Receipt Binding rule in `shared/return-convention.md`. **This is the canonical location for the receipt ledger.** It is a session-scoped file inside the per-session dispatch directory, NOT a shared project-memory file — co-locating it here keeps concurrent pipelines isolated (a shared ledger would interleave entries across runs and break the per-phase reconciliation count).

Each line is an append-only JSON object `{dispatch-id, phase, rcpt-sha256, verdict}`. The literal on-disk JSON keys the writer emits are snake_case — **`{"dispatch_id": …, "phase": …, "rcpt_sha256": …, "verdict": …}`** — matching `manifest.jsonl`'s key convention and JSON idiom; these are the exact keys the part-3 `rcpt_verify.py --ledger` verifier and the cairn reconciler read. The hyphenated forms used in prose (`dispatch-id`, `rcpt-sha256`) are the conceptual names for the same fields. (The eval fixture's `hash_prefix` and `witness_ran` are eval-only stand-ins — for `rcpt_sha256`'s 12-char prefix and the receipt's WITNESS disposition respectively — NOT production keys. `witness_ran` in particular is the fixture stand-in for the closing receipt's `ran=` disposition that the orchestrator observes **from the receipt in-hand at obligation-close time** (cairn Rule 2); production never persists it as a ledger key.)
- `dispatch-id` — the dispatch-file basename `<N>-<template-name>` (the same `<dispatch-id>` carried in the receipt header). Phase-less by design.
- `phase` — the orchestrator's current phase label, **skill-qualified** as `<skill>:<phase>/<counter>` (e.g. `"phase": "quality-gate:round/1"`), where `<skill>` is the recording skill's name (the cairn's `parent-skill`, or its own skill name when no cairn is active). The skill prefix makes the phase globally unique across sibling cairns that share one dispatch directory, so two sub-skills that both use `round/N` (e.g. `siege` and `quality-gate`) never collide on the same `round/1`. Layer 3 (`shared/cairn-convention.md`, Reconciliation Rule 1) counts entries by this field for per-phase dispatch-count consistency.
- `rcpt-sha256` — `sha256(normalize(receipt_text))` (normalize per `shared/return-convention.md`).
- `verdict` — the child receipt's verdict (`PASS`/`FAIL`/`BLOCKED`).

Layer 3 reconciliation and compaction recovery resolve the ledger via the run's dispatch-directory path, carried in the `.pipeline-active` marker's `dispatch_dir` field (see Pipeline-Active Marker above). After the run terminates and the dispatch directory is deleted (see Cleanup), post-terminal consumers (forge retrospectives, the receipt-binding audit) resolve the ledger from the durable, **session-namespaced** scratch copy `<scratch>/crucible-dispatch-<session-id>/receipt-ledger.jsonl` (the `<session-id>` from the `.pipeline-active` / `.dispatch-active-<session-id>` marker), NOT the deleted `/tmp` dispatch-dir path nor an un-namespaced flat path — the session-namespace keeps concurrent pipelines' durable copies isolated (same rationale as the live ledger above, and consistent with `replay`'s `<scratch>/crucible-dispatch-<session-id>/…` pattern). Both cleanup dispositions land the ledger at that path (see Cleanup).

The ledger's `phase` field (`<skill>:<phase>/<counter>`) is intentionally distinct from `manifest.jsonl`'s per-entry `phase` (a bare string like `"2"`): the manifest tracks the pipeline phase for execution-trace purposes, while the ledger's skill-qualified `<skill>:<phase>/<counter>` is authoritative for cairn Reconciliation Rule 1's per-phase dispatch count.

## Cleanup

**On successful pipeline completion:**
1. Copy `manifest.jsonl` **and `receipt-ledger.jsonl`** to the session-namespaced subdirectory `<scratch>/crucible-dispatch-<session-id>/` of the pipeline's persistent scratch directory — so both land at `<scratch>/crucible-dispatch-<session-id>/…` (for forge retrospectives and post-hoc receipt-binding audit; the dispatch directory itself — and its `/tmp` ledger copy — is deleted in step 2)
2. Delete the dispatch directory

**On failure or escalation:**
1. Copy the dispatch directory itself — directory-into-directory, its basename `crucible-dispatch-<session-id>` preserved (the directory lands as a subdirectory of `<scratch>/`, NOT its contents flattened) — to the pipeline's persistent scratch directory (durable record for inspection and replay). Because the basename is preserved, this copy lands `receipt-ledger.jsonl` at the canonical session-namespaced path `<scratch>/crucible-dispatch-<session-id>/receipt-ledger.jsonl` — the same path the success disposition produces; flattening the contents would instead land it at the un-namespaced flat `<scratch>/receipt-ledger.jsonl` that L241 forbids consumers from reading. No separate flat copy is made.
2. Leave the original `/tmp` dispatch directory in place as well (`/tmp` is ephemeral; the scratch copy is the durable artifact)

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
