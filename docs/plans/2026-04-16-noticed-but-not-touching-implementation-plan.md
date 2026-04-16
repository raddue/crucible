---
ticket: "#179"
epic: "#179"
title: "'Noticed but not touching' scope discipline pattern"
date: "2026-04-16"
source: "spec"
---

# Implementation Plan: 'Noticed But Not Touching' Scope Discipline Pattern

## Summary

Add a structured `### Noticed But Not Touching` section to the build
implementer report format, an orchestrator reconciliation step that
aggregates entries into `docs/plans/<pipeline-id>-noticed.md`, and a
contract test that detects the notice-AND-modify anti-pattern.

## Tiering

Tier 2 (multi-file prompt-template change with fixture test). Not Tier 3
because no new infrastructure, no cross-skill orchestration refactor.

## Tasks

### T1 — Add Noticed section to implementer report format
**Parallelizable with:** T3, T5
**File:** `skills/build/build-implementer-prompt.md`
**Change:** Append to the "Report Format" / "TDD Evidence Log" block:

```markdown
### Noticed But Not Touching

Out-of-scope observations surfaced during this task. Do NOT act on these;
log and move on. If nothing noticed, write `*(none)*`.

Format (one entry per observation):

- **file:** `path:L<start>-L<end>`
  **noticed:** <what you observed>
  **why it matters:** <risk or opportunity, 1–2 lines>
  **suggested follow-up:** <optional 1-line suggestion>
```

Also add to the Self-Review Checklist under **Discipline:**
"Did I notice anything out-of-scope? If yes, is it in the Noticed section
and NOT in my diff?"

### T2 — Document reconciliation in build SKILL.md
**Depends on:** T1
**File:** `skills/build/SKILL.md`
**Change:** In the Phase 3 (implementation) or Phase 4 (verification)
section, add a "Noticed Reconciliation" subsection. After all implementers
report:

1. Collect each implementer's `### Noticed But Not Touching` section.
2. Skip entries marked `*(none)*`.
3. Dedupe by normalized (file path + line range + first 40 chars of
   `noticed`).
4. Sort by file path, then line range.
5. If any entries remain, write `docs/plans/<pipeline-id>-noticed.md` with
   frontmatter (`pipeline_id`, `date`, `ticket`) and the deduped list.
6. Stage the file for the PR commit.

### T3 — Scope-discipline guidance in build SKILL.md
**Parallelizable with:** T1, T5
**File:** `skills/build/SKILL.md`
**Change:** Update the scope-discipline / YAGNI section to reference the
Noticed pattern explicitly: "Notice, do not act. If you see an
out-of-scope issue during implementation, log it under
`### Noticed But Not Touching` in your report. Acting on noticed items in
the same task is a scope-discipline failure."

### T4 — Fixture test for scope-discipline invariant (INV-3)
**Depends on:** T2
**Location:** `skills/build/tests/` (create if absent) or colocated with
existing build tests.
**Test:** Stub implementer dispatch with a plan that mentions an in-scope
change to `in_scope.ts` and a fixture that also contains a clearly
out-of-scope code smell in `out_of_scope.ts`. Assert:

1. Implementer's report contains a Noticed entry referencing
   `out_of_scope.ts`.
2. `out_of_scope.ts` is unchanged in the implementer's diff (hash match
   pre/post).
3. Aggregated `docs/plans/<pipeline-id>-noticed.md` contains the entry.

Tag: `contract:scope-discipline:inv-3`.

### T5 — /finish references noticed.md
**Parallelizable with:** T1, T3
**File:** `skills/finish/SKILL.md`
**Change:** Add a step: "Check for `docs/plans/*-noticed.md` matching the
current pipeline. If entries exist, prompt the user: 'Found N
noticed-but-not-touching entries. Convert any to GitHub issues?' On
confirmation, offer a numbered list; create issues via `gh issue create`
for selected entries."

### T6 — Selection eval
**Depends on:** T1–T5
**Location:** `skills/build/evals/` or the selection-eval harness.
**Test:** Prompt the agent with a task plan + a fixture containing both
in-scope work and a visible out-of-scope bug. Verify:

1. The Noticed section appears in the implementer report.
2. The out-of-scope file is not modified.
3. The aggregated file is produced at pipeline completion.

## Parallelization Plan

```
Wave 1:  T1  T3  T5   (all SKILL/prompt edits, different sections/files)
Wave 2:  T2            (depends on T1 for the report-format contract)
Wave 3:  T4            (depends on T2's reconciliation contract)
Wave 4:  T6            (end-to-end selection eval)
```

## Rollback

All changes are prompt-template / SKILL.md edits plus one fixture test.
Rollback = revert the PR commit. No data migrations, no API contracts, no
runtime state.

## Risks

- **Prompt-template churn:** three tickets (#176, #179, #180) all edit
  `skills/build/SKILL.md`. Mitigation: target distinct sections;
  coordinate merge order if parallel.
- **Empty noticed files cluttering `docs/plans/`:** T2 skips the write if
  zero entries remain after dedupe.
- **False positives (implementer notices normal refactor targets):** the
  Self-Review Checklist question in T1 nudges toward minimal noticing;
  reviewers can flag excessive entries in code review.

## Acceptance Criteria Mapping

| Ticket AC | Tasks |
|---|---|
| Build pipeline produces structured observations | T1, T2 |
| Observations persisted, not just logged to conversation | T2 |
| Format includes enough context to be actionable later | T1 (DEC-2 schema) |
| Agent does not act on noticed items during current pipeline | T3, T4 (INV-3), T6 |
