---
ticket: "#97"
title: "Subagent Prompt Echo Suppression via Disk-Mediated Dispatch"
date: "2026-04-05"
source: "design"
---

# Disk-Mediated Dispatch

## Problem

When orchestrator skills dispatch subagents via the Agent tool, the full expanded prompt (template + injected context like diffs, cartographer data, findings) fossilizes in the orchestrator's conversation history. Over 52-93 dispatches in a full build pipeline, that's **73-131K tokens of dead weight**.

Worse: autocompact **actively protects tool call bodies** from compression because they look like structured interaction records. This is the only accumulation vector that resists the model's built-in compression heuristics.

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

Introduce a single indirection layer between orchestrator skills and subagent dispatch. Instead of composing a full prompt inline in the Agent tool call, the orchestrator:

1. Reads the dispatch template file
2. Fills in template variables with task-specific context (diffs, cartographer data, findings, etc.)
3. Writes the expanded result to `/tmp/crucible-dispatch-<session-id>/<N>-<template-name>.md`
4. Sends a ~50-token pointer prompt via the Agent tool
5. Subagent reads the dispatch file, executes as normal

**Per-dispatch savings:** ~95% reduction (from ~1,500 avg tokens to ~50-100 tokens in orchestrator history).

**Pipeline savings:** ~73-131K tokens recovered — the hardest-to-shed kind (tool call bodies that autocompact protects).

## Architecture

### Dispatch File Structure

The dispatch file is the fully expanded template — identical to what currently goes into the Agent tool prompt. No new format:

```markdown
# Dispatch: <template-name>
**Pipeline:** <skill-name> | **Phase:** <phase> | **Task:** <N>
**Timestamp:** <ISO-8601>

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

The pointer prompt is what goes into the Agent tool `prompt` parameter and fossilizes in orchestrator history:

```
You are a [role] for [task summary].
Read your full instructions and context at [dispatch file path].
Begin by reading that file.
```

**Rules:**
- Role must be specific enough for error reporting ("code implementer for Task 3: Auth middleware", not just "implementer")
- Task summary is one clause, not a paragraph
- No file lists, no context, no instructions beyond "read the file"
- Maximum 80 tokens

**Examples:**

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

### File Naming Convention

**Directory:** `/tmp/crucible-dispatch-<session-id>/`

Session ID matches the pipeline's existing session identifier (timestamp-based). Provides isolation across concurrent sessions.

**Files:** `<N>-<template-name>.md`

Counter increments per dispatch within the session. Template name makes files self-documenting:
- `1-plan-writer.md`
- `2-plan-reviewer.md`
- `3-build-implementer.md`
- `4-build-reviewer.md`
- `5-cleanup.md`

On compaction recovery: orchestrator counts existing files in the directory to recover the counter.

### Failure Handling

If the subagent cannot read the dispatch file: abort and report "Could not read dispatch file at [path]."

The orchestrator verifies the file exists and re-writes if missing, then re-dispatches. No inline fallback, no redundant writes. If /tmp is broken, the pipeline has bigger problems.

### Cleanup Strategy

- **On successful pipeline completion:** delete the dispatch directory
- **On failure or escalation:** preserve for inspection
- Pipeline completion steps (build Phase 4, debugging Phase 5, etc.) each include cleanup

## Convention Propagation

### Canonical Source

`skills/shared/dispatch-convention.md` — defines the full pattern (~50-80 lines): when to use, file naming, pointer format, cleanup rules, failure handling.

### Per-Skill Changes (16 orchestrator skills)

Each gets:
1. A reference comment: `<!-- CANONICAL: shared/dispatch-convention.md -->`
2. One sentence at the top of their dispatch section: "All subagent dispatches use disk-mediated dispatch (see shared/dispatch-convention.md)."
3. Removal of any "paste X into prompt" language

**Skills requiring changes:** build, debugging, quality-gate, spec, migrate, audit, siege, prospector, recon, project-init, inquisitor, code-review, finish, test-coverage, adversarial-tester, design.

### Per-Template Changes (75 dispatch templates)

Each gets a 3-line comment header:
```markdown
<!-- DISPATCH: disk-mediated | This template is written to a dispatch file,
     not pasted into the Agent tool prompt. See shared/dispatch-convention.md -->
```

Comment is invisible to the subagent reading the expanded file, visible to orchestrators and humans reading the template source. No behavioral changes to templates — variable placeholders, instructions, output formats all unchanged.

## Testing Strategy: Primacy Eval

### Risk: Prompt Primacy

The core risk is not mechanical (file I/O works). The risk is **prompt primacy** — whether the model treats context read via the Read tool with the same weight as context received in its initial prompt.

If subagents give less attention to injected context (cartographer data, defect signatures, prior findings) when it arrives via file read instead of inline, output quality degrades silently.

### Phase 1: Primacy Eval (before any skill changes)

Eval uses issue #126 (Embed scope absorption test in /design dimension analysis) as the test fixture — a small, well-scoped enhancement to a single skill.

**Templates to test** (highest injected-context-to-static ratio):
- `build-reviewer` (50% injected — implementer report + task spec)
- `investigator` (71% injected — bug context + hypothesis log + cartographer)
- `red-team` (82% injected — full design doc + implementation plan)

**Per-template test:**
1. Expand template with realistic fixture data from #126
2. **Control:** dispatch subagent with full expanded prompt inline (current behavior)
3. **Test:** write expanded prompt to dispatch file, dispatch with pointer prompt
4. Run each 2-3 times to account for model variance
5. Compare outputs: structure, thoroughness, context utilization

**Eval criteria:**
- **Pass:** test runs produce findings of comparable depth and all injected context sections are referenced
- **Degraded:** test runs produce shallower findings or skip injected context — triggers hybrid investigation
- **Fail:** subagent ignores dispatch file or produces structurally wrong output

### Phase 2: Hybrid Fallback (only if Phase 1 shows degradation)

If prompt primacy effects are observed:
- Keep role + key constraints + instruction summary inline (~200-300 tokens)
- Move only heavy context (diffs, findings, cartographer data) to disk
- Re-run eval to verify hybrid recovers quality
- Hybrid still saves ~80% of tokens (heavy context is ~70-85% of dispatch size)

### Phase 3: Rollout (after eval passes)

Apply convention to all 16 skills and 75 templates.

## Acceptance Criteria

1. Primacy eval passes on all 3 test templates (or hybrid fallback validated)
2. All 16 orchestrator skills use disk-mediated dispatch for every subagent call
3. No Agent tool prompt exceeds 80 tokens (pointer only)
4. Dispatch files written before dispatch and readable by subagents
5. Dispatch directory cleaned up on success, preserved on failure
6. No "paste X into prompt" language remains in any SKILL.md or template file
7. Every dispatch template has the `<!-- DISPATCH: disk-mediated -->` comment
8. `shared/dispatch-convention.md` exists and referenced by all 16 skills

## Invariants

### Checkable (by inspection)

- No Agent tool prompt in any orchestrator exceeds 80 tokens
- No SKILL.md contains "paste into prompt" or "paste relevant" language for subagent dispatch
- Every dispatch template has the `<!-- DISPATCH: disk-mediated -->` comment
- `shared/dispatch-convention.md` exists and is referenced by all 16 orchestrator skills
- Dispatch files follow naming: `<counter>-<template-name>.md`

### Testable (requires eval)

- Subagent output quality unchanged between inline and disk-mediated dispatch
- Subagents reference injected context at same rate in both modes
- Dispatch files readable by subagents (no path or permission errors)

## Scope

### In scope
- Shared dispatch convention document
- SKILL.md edits for 16 orchestrator skills
- Comment headers for 75 dispatch templates
- Primacy eval on 3 templates using #126 as fixture
- Hybrid fallback design (if needed)

### Out of scope
- Modifying Claude Code's Agent tool
- Token counting/measurement (#106)
- Template content restructuring (templates unchanged)
- Runtime code or hooks
