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
aggregates entries into `docs/plans/<date>-<ticket-slug>-noticed.md` (with
`pipeline_id` recorded in the file's frontmatter for attribution), and a
contract test that detects the notice-AND-modify anti-pattern.

## Tiering

Tier 2 (multi-file prompt-template change with fixture test). Not Tier 3
because no new infrastructure, no cross-skill orchestration refactor.

## Canonical Constants

Copy these verbatim across T1, T2, T4, T5. If any drift, the grep
invariants in the contract will flag it.

**Filename regex (INV-6):**

```
^docs/plans/\d{4}-\d{2}-\d{2}-[a-z0-9-]+-noticed\.md$
```

**Frontmatter + heading template (T2 writer must emit exactly this shape):**

```markdown
---
pipeline_id: "<build-YYYYMMDD-HHMMSS>"
date: "YYYY-MM-DD"
ticket: "#NNN"
---

# Noticed But Not Touching — <ticket-slug>

- **file:** `path:L<start>-L<end>`
  **noticed:** <desc>
  **why it matters:** <risk/opportunity>
  **suggested follow-up:** <optional>
```

**Dedupe key:**

```
sha256( normalize(file_path) + "|" + line_range + "|" + noticed[:40] )
```

where `normalize(file_path)` = repo-relative POSIX path, lowercased.

**Contract tag strings (T4, T6 must use verbatim):**

- `contract:integration:inv-4` (T4 mechanical)
- `contract:scope-discipline:inv-3` (T6 behavioral)

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
5. If any entries remain, write
   `docs/plans/<YYYY-MM-DD>-<ticket-slug>-noticed.md` matching the
   Canonical Constants filename regex. Use the date embedded in the
   sibling plan filename (not wall-clock date) so all four sibling
   artifacts share a date; slug matches the ticket being built.
   Frontmatter + body follow the Canonical Constants template exactly.
6. **Idempotent overwrite:** if the target file already exists (rare:
   same-ticket re-run on same date), merge its existing entries with the
   newly collected entries, run full dedupe (same key as Canonical
   Constants), sort, and overwrite the file in one write. No append-mode;
   the on-disk file is always the full deduped set for that
   date+ticket.
7. Stage the file for the PR commit.

### T3 — Scope-discipline guidance in build SKILL.md
**Parallelizable with:** T1, T5
**File:** `skills/build/SKILL.md`
**Change:** Update the scope-discipline / YAGNI section to reference the
Noticed pattern explicitly: "Notice, do not act. If you see an
out-of-scope issue during implementation, log it under
`### Noticed But Not Touching` in your report. Acting on noticed items in
the same task is a scope-discipline failure."

### T4 — Mechanical contract test for report-format + reconciliation (INV-4)
**Depends on:** T2
**Location:** `skills/build/tests/` (create if absent) or colocated with
existing build tests.
**Scope note:** T4 is the **mechanical** contract test (INV-4): it feeds
two synthetic implementer reports into the reconciliation step and checks
parsing, dedup, and file emission. It does **not** try to verify that a
live agent refrains from acting on a noticed file — that is T6's job (see
DEC-6 enforcement layers). Stubbing the implementer for T4 is intentional
and scoped to the parsing contract.

**Test:** Construct two synthetic implementer report strings, each
containing a `### Noticed But Not Touching` section. Report A contains
one entry pointing at `out_of_scope.ts:L10-L20`. Report B contains one
duplicate entry (same file+range, same `noticed` prefix) and one unique
entry at `other.ts:L5-L7`. Invoke the reconciliation function. Assert:

1. Aggregated file is written at
   `docs/plans/<today>-<ticket-slug>-noticed.md`.
2. File contains exactly 2 entries (duplicate collapsed).
3. Entries are sorted by file path then line range.
4. Frontmatter includes `pipeline_id`, `date`, `ticket`.

5. Re-invoke with the same two reports (simulating same-date re-run);
   assert the resulting file is byte-identical to the first run (proves
   idempotent overwrite).

Tag: `contract:integration:inv-4` (verbatim from Canonical Constants).

### T5 — /finish references noticed.md
**Parallelizable with:** T1, T3
**File:** `skills/finish/SKILL.md`
**Change:** Add a step: "Check for `docs/plans/*-noticed.md` matching the
current pipeline. If entries exist, prompt the user: 'Found N
noticed-but-not-touching entries. Convert any to GitHub issues?' On
confirmation, offer a numbered list; create issues via `gh issue create`
for selected entries."

### T6 — Behavioral eval for INV-3 (live implementer)
**Depends on:** T1–T5
**Location:** `skills/build/evals/` (rides on the existing selection-eval
harness pattern — see `skills/build/evals/` precedent from #174 T5b).
**Test:** Dispatch a **real** implementer agent (not a stub) with a task
plan describing an in-scope change in `in_scope.ts` and a fixture
repository that also contains a clearly out-of-scope code smell in
`out_of_scope.ts`. Record `sha256(out_of_scope.ts)` pre-run. Verify:

1. The implementer report contains a `### Noticed But Not Touching`
   section with an entry referencing `out_of_scope.ts`.
2. `sha256(out_of_scope.ts)` post-run equals the pre-run hash (file
   unchanged in diff).
3. The aggregated
   `docs/plans/<date>-<ticket-slug>-noticed.md` is produced at pipeline
   completion and contains the entry.

Tag: `contract:scope-discipline:inv-3` (verbatim from Canonical Constants).

Rationale: T4 (stubbed) cannot prove the agent refrains from acting —
only a live dispatch can. This is INV-3's behavioral clause.

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
| Agent does not act on noticed items during current pipeline | T3, T6 (INV-3 behavioral) |
| Reconciliation dedupes and emits correctly structured file | T2, T4 (INV-4 mechanical) |
