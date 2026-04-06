---
ticket: "#97"
title: "Subagent Prompt Echo Suppression via Disk-Mediated Dispatch"
date: "2026-04-05"
source: "design"
---

# Disk-Mediated Dispatch

## Problem

When orchestrator skills dispatch subagents via the Agent tool or Task tool (teammate dispatches), the full expanded prompt (template + injected context like diffs, cartographer data, findings) fossilizes in the orchestrator's conversation history. Over 52-93 dispatches in a full build pipeline, that's **73-131K tokens of dead weight**.

Worse: autocompact is **empirically observed to resist compressing tool call bodies** — they appear to be treated as structured interaction records. This is the accumulation vector most resistant to the model's built-in compression heuristics. (Actual savings should be measured post-implementation via #106.)

This design addresses input echo (prompt parameters). Output echo (subagent return values) is a separate vector addressed by microcompaction and tracked under #106.

### Token Impact

| Dispatches | Count | Tokens each | Total |
|---|---|---|---|
| Phase 1 (Design) | 4-6 | ~1,000-2,000 | 4-12K |
| Phase 2 (Plan + gate) | 8-19 | ~1,000-3,000 | 8-57K |
| Phase 3 (per-task x8) | 32-48 | ~1,100-1,400 | 35-67K |
| Phase 4 (review + gate) | 8-20 | ~1,500-3,000 | 12-60K |
| **Total** | **52-93** | | **~73-131K** |

This represents **~20-40% of total accumulated pipeline context**.

## Solution: Disk-Mediated Dispatch

Introduce a single indirection layer between orchestrator skills and subagent dispatch. This applies to both Agent tool and Task tool (teammate) dispatches. Instead of composing a full prompt inline in the tool call, the orchestrator:

1. Reads the dispatch template file
2. Fills in template variables with task-specific context (diffs, cartographer data, findings, etc.)
3. Writes the expanded result to `/tmp/crucible-dispatch-<session-id>/<N>-<template-name>.md`
4. Sends a ~50-token pointer prompt via the Agent tool
5. Subagent reads the dispatch file, executes as normal

**Per-dispatch savings:** ~95% reduction (from ~1,500 avg tokens to ~50-100 tokens in orchestrator history).

**Pipeline savings:** ~73-131K tokens recovered — the hardest-to-shed kind (tool call bodies that autocompact empirically resists compressing). **Reversibility note:** If future autocompact improvements begin compressing tool call bodies effectively, the dispatch indirection can be removed while preserving the manifest — the convention is additive and each skill change is a one-line reference swap.

## Architecture

### Dispatch File Structure

The dispatch file is the fully expanded template — identical to what currently goes into the Agent tool prompt. No new format:

```markdown
# Dispatch: <template-name>
**Pipeline:** <skill-name> | **Phase:** <phase> | **Task:** <N>
**Timestamp:** <ISO-8601>
**Dispatch-Dir:** <dispatch directory path>

---

## Role
You are a [role] for [task description].

## Context
[Expanded context sections — task description, file paths,
cartographer data, defect signatures, prior findings, etc.]

## Instructions
[What to do, constraints, self-review requirements]

## Output Format
[Required report sections and structure]
```

The 4-line header provides audit trail (which pipeline, phase, and task produced the dispatch). The subagent reads from `## Role` onward, same as today.

### Pointer Prompt Format

The pointer prompt is what goes into the Agent tool `prompt` parameter (or Task tool `prompt:` field for teammate dispatches) and fossilizes in orchestrator history:

```
You are a [role] for [task summary].
Read your full instructions and context at [dispatch file path].
Begin by reading that file.
```

**Rules:**
- Role must be specific enough for error reporting ("code implementer for Task 3: Auth middleware", not just "implementer")
- Task summary is one clause, not a paragraph
- No file lists, no context, no instructions beyond "read the file"
- Target 80 tokens; hard ceiling 120 tokens (full disk-mediated mode) or 300 tokens (hybrid mode). Pointer prompts above 80 tokens must justify the extra length with a role description that cannot be shortened without losing error-diagnostic specificity. This limit applies to the `prompt` parameter/field only — not to structured Task tool fields (`team_name`, `name`, `description`, `subagent_type`), which are metadata, not conversation content.
- "Begin by reading that file" does not preclude subsequent actions (e.g., mailbox checks); it establishes the first action, not the only action.
- For teammate dispatches: the dispatch file itself must include any teammate communication protocol instructions (e.g., mailbox check conventions). The pointer prompt stays minimal — do not duplicate mailbox instructions in the pointer.

**Examples (Agent tool):**

```
You are a code implementer for Task 3: Auth middleware.
Read your full instructions and context at /tmp/crucible-dispatch-1775427090/3-build-implementer.md
Begin by reading that file.
```

```
You are a red-team reviewer for the implementation plan.
Read your full instructions and context at /tmp/crucible-dispatch-1775427090/7-red-team.md
Begin by reading that file.
```

```
You are an investigator (Breadth-First role) for bug: session timeout after OAuth redirect.
Read your full instructions and context at /tmp/crucible-dispatch-1775427090/2-investigator-breadth.md
Begin by reading that file.
```

**Example (Task tool):**

```json
{
  "team_name": "plan-review-team",
  "name": "Plan reviewer",
  "description": "Reviews implementation plan for gaps",
  "prompt": "You are a plan reviewer for the auth middleware plan.\nRead your full instructions and context at /tmp/crucible-dispatch-1775427090/2-plan-reviewer.md\nBegin by reading that file.",
  "subagent_type": "research"
}
```

Note: the 80-token target / 120-token ceiling applies to the `prompt` value only; `team_name`, `name`, `description`, and `subagent_type` are unconstrained.

### File Naming Convention

**Directory:** `/tmp/crucible-dispatch-<session-id>/`

Session ID reuses the pipeline's existing session identifier (the timestamp-based ID already generated by orchestrator skills at pipeline start). No new ID generation needed. Provides isolation across concurrent sessions. Skills that lack an existing session ID (e.g., standalone invocations) must generate a timestamp-based one at pipeline start (format: Unix epoch seconds).

**Files:** `<N>-<template-name>.md`

Counter increments per dispatch within the session. Template name makes files self-documenting.

**Sub-skill inheritance:** When an orchestrator invokes sub-skills (quality-gate, red-team, etc.), those sub-skills use the **parent orchestrator's dispatch directory and seq counter**, not their own. The parent is responsible for cleanup. Sub-skills receive the dispatch directory path as input and append to the existing `manifest.jsonl`. This prevents dispatch directory proliferation and keeps the execution trace unified.

**Fallback for missing dispatch directory path:** If a sub-skill receives no explicit dispatch directory path (e.g., invoked standalone or the parent omitted it), the sub-skill creates a new dispatch directory with a timestamp-based session ID. Do not glob for other sessions' directories — this would break session isolation under concurrent pipelines.

Example files:
- `1-plan-writer.md`
- `2-plan-reviewer.md`
- `3-build-implementer.md`
- `4-build-reviewer.md`
- `5-cleanup.md`

**Compaction Recovery (on-disk marker — primary mechanism):** At dispatch-directory creation time, the orchestrator writes a marker file to the pipeline's persistent scratch directory: `<scratch>/.dispatch-active-<session-id>`. The marker contains the dispatch directory path and the current seq counter. After compaction, the orchestrator globs for `.dispatch-active-*` in scratch to rediscover in-flight dispatch state, reads `manifest.jsonl` to find the last entry's `seq` value + 1 as the next counter, and resumes. All 22 orchestrator skills use this same marker pattern — it does not depend on per-skill CSB support. CSB inclusion of the dispatch directory path is a secondary nice-to-have for skills that already have Compression State Blocks (build, debugging, quality-gate, migrate).

### Failure Handling

If the subagent cannot read the dispatch file: abort and report "Could not read dispatch file at [path]."

The orchestrator verifies the file exists and re-writes if missing, then re-dispatches. No inline fallback, no redundant writes. If /tmp is broken, the pipeline has bigger problems.

### Dispatch Manifest

Every dispatch directory includes a `manifest.jsonl` file — a structured execution trace. The orchestrator writes a manifest entry **before** dispatching (with status `"dispatched"`), then updates the entry to `"completed"`, `"failed"`, etc. after the dispatch returns. On compaction recovery, any entry still showing `"dispatched"` status is treated as **needs re-dispatch** — the conservative default. There is no reliable way to distinguish "completed but status not yet written" from "truly interrupted mid-execution," so the orchestrator re-dispatches unconditionally. Duplicate work is acceptable for read-only agents (reviewers, red-team): the subagent's second run overwrites the same files and produces the same test results, making re-dispatch idempotent in practice. **Extra care for mutating agents (implementers):** Before re-dispatching an implementer after compaction recovery, verify: (1) the dispatch file's creation timestamp is recent (within the current session), and (2) check for evidence of prior completion — commits, test results, or output files — before re-dispatching. Re-running a completed implementer risks duplicate commits or conflicting file mutations.

```jsonl
{"seq":1,"file":"1-plan-writer.md","role":"plan-writer","phase":"2","task":null,"status":"completed","duration_s":83,"summary":"Plan written: 8 tasks, 3 waves"}
{"seq":2,"file":"2-plan-reviewer.md","role":"plan-reviewer","phase":"2","task":null,"status":"completed","duration_s":45,"summary":"2 issues found: dependency gap, missing edge case"}
{"seq":3,"file":"3-build-implementer.md","role":"implementer","phase":"3","task":1,"status":"completed","duration_s":120,"summary":"Auth middleware implemented, 4 tests green"}
{"seq":4,"file":"4-build-reviewer.md","role":"reviewer","phase":"3","task":1,"status":"dispatched","duration_s":null,"summary":null}
```

**Fields:**
- `seq` — dispatch sequence number (matches file counter)
- `file` — dispatch file name
- `role` — subagent role (implementer, reviewer, red-team, etc.)
- `phase` — pipeline phase
- `task` — task number (null for non-task dispatches)
- `status` — dispatched, completed, failed, skipped, error
- `duration_s` — wall clock seconds (optional; null while status is `"dispatched"`)
- `summary` — one-line result extracted from subagent output

**What this enables:**
1. **Zero-cost failure replay** — debugging skill reads manifest, identifies failing dispatch, re-runs from preserved file with identical context. No reconstruction.
2. **Forge execution data** — machine-readable trace of template failure rates, phase durations, iteration counts. Direct feed into forge retrospectives.
3. **Pipeline resume (future)** — skip completed dispatches, restart from first failure. 10x harder to add later without the manifest.

**Cost:** ~3-5 lines per orchestrator skill to append after each dispatch. One Bash append call per entry.

### Exclusions (Paste-Only Dispatches)

Some subagent dispatches receive all input directly in the Agent/Task tool prompt and need no file access. These are exempt from disk-mediated dispatch:

- ~~**QG stagnation judge**~~ — promoted to disk-mediated; template exceeds 500 tokens static (~1000 tokens)
- ~~**Fix verifier**~~ — promoted to disk-mediated; template exceeds 500 tokens static (~900 tokens)
- ~~**Prospector analysis agents**~~ — promoted to disk-mediated; template exceeds 500 tokens with 8 expansion sections. (Original note: "Validate that prospector analysis payloads actually stay under the 500-token exclusion threshold in practice." Validated — they don't.)

**Bright-line rule:** Dispatches with <500 tokens total payload AND that use the Task tool without file access are exempt from disk-mediated dispatch. These dispatches are small (typically <200 tokens of injected context) and their prompts compress normally under autocompact. Disk-mediating them would add file I/O overhead for negligible savings.

Acceptance criteria and invariant checks (e.g., "no Agent tool prompt exceeds N tokens") exclude paste-only dispatches listed here.

### Cleanup Strategy

- **On successful pipeline completion:**
  1. Copy `manifest.jsonl` to the pipeline's persistent scratch directory (for forge retrospectives)
  2. Delete the dispatch directory
- **On failure or escalation:** copy the full dispatch directory (not just `manifest.jsonl`) to the pipeline's persistent scratch directory, then leave the `/tmp` copy in place as well. `/tmp` is ephemeral and may be cleared by the OS; the scratch copy is the durable record for inspection and replay.
- Pipeline completion steps (build Phase 4, debugging Phase 5, etc.) each include cleanup

## Phase 0: Baseline Token Measurement (Hard Prerequisite)

**Do not begin convention propagation, primacy eval design, or any skill edits until Phase 0 results confirm savings exceed 20K tokens.**

Before any other implementation work, validate the savings claim with direct observation:

1. Run one real pipeline (e.g., `/build` on issue #126) with token observation enabled via `#106` instrumentation
2. Dump context window contents at key points: after Phase 2 dispatches, after Phase 3 dispatches, at pipeline end
3. Record: (a) total tokens consumed by Agent/Task tool call bodies, (b) how much autocompact actually reduces those bodies between phases
4. Confirm that prompt parameters persist at the claimed scale (~1,000-3,000 tokens per dispatch) and that autocompact does not already handle them

**Decision gate:** If measured savings from disk-mediated dispatch would be under 20K tokens across a full pipeline (i.e., autocompact or microcompaction already handles most tool call body weight), descope the effort to manifest-only — implement `manifest.jsonl` for execution tracing without the dispatch file indirection.

## Convention Propagation

### Canonical Source

`skills/shared/dispatch-convention.md` — defines the full pattern (~50-80 lines): when to use, file naming, pointer format, cleanup rules, failure handling. The convention doc must include `version: 1` as the first field. **CLAUDE.md note:** The convention doc should mention its relationship to CLAUDE.md — specifically that dispatch-convention.md is a shared skill reference, not a CLAUDE.md directive, and that CLAUDE.md should not duplicate dispatch rules. **Stocktake integration:** Stocktake should flag paste-only dispatches exceeding 500 tokens.

### Per-Skill Changes (22 orchestrator skills)

Each gets:
1. A reference comment: `<!-- CANONICAL: shared/dispatch-convention.md -->`
2. One sentence at the top of their dispatch section: "All subagent dispatches use disk-mediated dispatch (see shared/dispatch-convention.md)."
3. Removal of any "paste X into prompt" language

**Skills requiring changes:** build, debugging, quality-gate, spec, migrate, audit, siege, prospector, recon, project-init, inquisitor, code-review, finish, test-coverage, adversarial-tester, design, red-team, forge-skill, innovate, cartographer-skill, consensus, prd.

### Per-Template Changes (~73 dispatch templates)

Each gets a 3-line comment header:
```markdown
<!-- DISPATCH: disk-mediated | This template is written to a dispatch file,
     not pasted into the Agent tool prompt. See shared/dispatch-convention.md -->
```

Comment is invisible to the subagent reading the expanded file, visible to orchestrators and humans reading the template source. No behavioral changes to templates — variable placeholders, instructions, output formats all unchanged.

**Template expansion:** Disk-mediated dispatch changes the *delivery* mechanism (file read vs. inline paste), not template *composition*. Expansion follows the existing bracket-placeholder pattern (`{{variable}}`): orchestrators read the template, substitute placeholders with task-specific values, and write the fully expanded result to the dispatch file. No new placeholder syntax or expansion rules are introduced.

**Note:** Some files contain multiple dispatch prompts (e.g., `investigation-prompts.md`). Each distinct prompt section within such files gets the comment header. The ~73 count refers to distinct template files; effective dispatch-point count is higher.

## Testing Strategy: Primacy Eval

### Risk: Prompt Primacy

The core risk is not mechanical (file I/O works). The risk is **prompt primacy** — whether the model treats context read via the Read tool with the same weight as context received in its initial prompt.

If subagents give less attention to injected context (cartographer data, defect signatures, prior findings) when it arrives via file read instead of inline, output quality degrades silently.

### Phase 1: Primacy Eval (after Phase 0 passes — before any skill changes)

Eval uses issue #126 (Embed scope absorption test in /design dimension analysis) as the test fixture — a small, well-scoped enhancement to a single skill.

**Templates to test** (highest injected-context-to-static ratio):
- `build-reviewer` (50% injected — implementer report + task spec) — Agent tool dispatch
- `investigator` (71% injected — bug context + hypothesis log + cartographer) — Agent tool dispatch
- `red-team` (82% injected — full design doc + implementation plan) — Agent tool dispatch
- `plan-reviewer` — Task tool teammate dispatch (validates pointer prompt works in `prompt:` field)

**Fixtures:**
- **Primary:** issue #126 (Embed scope absorption test in /design dimension analysis) — small, well-scoped
- **Large context:** one fixture with a complex multi-file diff (8+ files) and cartographer data for 3+ modules, to stress-test whether large payloads read from disk degrade attention

**Per-template test:**
1. Expand template with realistic fixture data
2. **Control:** dispatch subagent with full expanded prompt inline (current behavior)
3. **Test:** write expanded prompt to dispatch file, dispatch with pointer prompt
4. Run each **8-10 times** to account for model variance (minimum 8 runs per template; 4-5 reps is insufficient to detect a 15% effect)
5. Compare outputs: structure, thoroughness, context utilization

**Eval criteria:**
- **Pass:** test runs produce findings of comparable depth, all injected context sections are referenced, **output must reference at least N specific named entities from injected context** (where N = number of distinct modules/files/defects injected, verified by string match), **test mean must be within 1 standard deviation of control mean on both entity reference count and specific code reference count**, and **each canary fact is correctly referenced** (see canary protocol below)
- **Degraded:** test runs produce shallower findings or skip injected context — triggers hybrid investigation
- **Fail:** subagent ignores dispatch file or produces structurally wrong output

**Eval cost note:** Expect 64-80 subagent runs at Opus pricing (4 templates x 2 modes x 8-10 reps).

**Canary Fact Protocol:** Each test template fixture includes one "canary fact" — a unique, fabricated detail injected into the context (e.g., a fake function name like `_xq7_verifyOAuthNonce`, a specific fabricated line number like "line 4217 of auth.ts"). The canary is placed within the injected context section, not the static template. The subagent's output MUST reference the canary for that run to pass. Canary evaluation is binary pass/fail per run — if the canary is absent from the output, the run fails regardless of other metrics. This detects attention degradation that entity counts alone might miss.

### Phase 2: Hybrid Fallback (only if Phase 1 shows degradation)

If prompt primacy effects are observed:
- Keep role + key constraints + instruction summary inline (~200-300 tokens)
- Move only heavy context (diffs, findings, cartographer data) to disk
- Re-run eval to verify hybrid recovers quality
- Hybrid still saves ~80% of tokens (heavy context is ~70-85% of dispatch size)

### Phase 2.5: Pointer Prompt Length Validation (before rollout)

Write sample pointer prompts for all ~73 dispatch templates and validate the 80-token target / 120-token ceiling holds. For each template, compose the pointer prompt using realistic role descriptions and file paths. Report the top 10 longest pointer prompts as examples. If any exceed 80 tokens, confirm the role description cannot be shortened without losing error-diagnostic specificity. If any exceed 120 tokens, shorten the role description. This catches templates with naturally verbose roles (e.g., "adversarial red-team reviewer for cross-component integration surface") before rollout creates a constraint violation.

### Phase 3: Rollout (after eval passes)

Apply convention to all 22 skills and ~73 templates.

## Acceptance Criteria

1. Primacy eval passes on all 4 test templates (or hybrid fallback validated)
2. All 22 orchestrator skills use disk-mediated dispatch for every Agent tool and Task tool subagent call (excluding paste-only dispatches)
3. No Agent/Task tool prompt exceeds 120 tokens (hard ceiling) for full disk-mediated dispatch, with 80-token target, or 300 tokens for hybrid mode (excluding paste-only dispatches)
4. Dispatch files written before dispatch and readable by subagents
5. Dispatch directory cleaned up on success, preserved on failure
6. Dispatch manifest (`manifest.jsonl`) written before every dispatch (status `"dispatched"`) and updated after completion with final status, duration, and summary
7. No "paste X into prompt" language remains in any SKILL.md or template file
8. Every dispatch template has the `<!-- DISPATCH: disk-mediated -->` comment
9. `shared/dispatch-convention.md` exists and referenced by all 22 skills

## Invariants

### Checkable (by inspection)

- No Agent/Task tool prompt in any orchestrator exceeds 120 tokens hard ceiling (80-token target; 80-120 range requires justification) for full disk-mediated mode, or 300 tokens for hybrid mode, excluding paste-only dispatches
- No SKILL.md contains "paste into prompt" or "paste relevant" language for subagent dispatch
- Every dispatch template has the `<!-- DISPATCH: disk-mediated -->` comment
- `shared/dispatch-convention.md` exists and is referenced by all 21 orchestrator skills
- Dispatch files follow naming: `<counter>-<template-name>.md`
- `manifest.jsonl` exists in dispatch directory with one entry per dispatch (entry written before dispatch, updated after)

### Testable (requires eval)

- Subagent output quality unchanged between inline and disk-mediated dispatch
- Subagents reference injected context at same rate in both modes
- Dispatch files readable by subagents (no path or permission errors)

## Scope

### In scope
- Shared dispatch convention document
- Dispatch manifest (manifest.jsonl) — structured execution trace
- SKILL.md edits for all 21 orchestrator skills
- Comment headers for ~73 dispatch templates
- Phase 0 baseline token measurement (go/no-go gate for full implementation)
- Primacy eval on 4 templates (3 Agent tool + 1 Task tool) using #126 as fixture plus one large-context fixture
- Pointer prompt length validation across all ~73 templates
- Hybrid fallback design (if needed)

### Prior Art

The `/project-init` skill already uses a similar pattern: it writes structured context to disk and dispatches subagents that read from those files rather than receiving everything inline. This design generalizes that approach across all orchestrator skills. Note: `project-init`'s existing output temp directory is separate from the dispatch input directory introduced here; the two coexist without conflict.

### Out of scope
- Modifying Claude Code's Agent tool
- Token counting/measurement (#106)
- Template content restructuring (templates unchanged)
- Runtime code or hooks
