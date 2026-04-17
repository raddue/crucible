---
ticket: "#179"
epic: "#179"
title: "'Noticed but not touching' scope discipline pattern"
date: "2026-04-16"
source: "spec"
---

# Design: 'Noticed But Not Touching' Scope Discipline Pattern

## Problem

Crucible's `/build` pipeline has strong scope-discipline principles (YAGNI,
self-review checklist asking "No unrelated changes snuck in?"), but lacks a
**structured mechanism for surfacing scope-adjacent observations without
acting on them.** Today, when an implementer notices a bug, smell, or
opportunity outside the current task's scope, they must choose between two
bad options:

1. **Silently ignore it** — the signal is lost. The next agent (or the next
   human) must rediscover it.
2. **Act on it** — scope creep. The diff grows, review gets harder, and the
   original task's semantic boundary is blurred.

Inspired by [addyosmani/agent-skills]'s `incremental-implementation` skill,
this ticket introduces a formal **"Noticed But Not Touching"** output format
so implementers can **notice-and-log** without acting.

## Goals

- Give implementers a structured place to record out-of-scope observations.
- Persist those observations across the pipeline so they survive context
  compression and session boundaries.
- Commit the aggregated observations alongside the PR that discovered them,
  so context travels with code.
- Make scope discipline *checkable*: "did you notice AND modify?" is a
  detectable failure mode.

## Non-Goals

- Automatic GitHub issue creation (kept manual — human judgment in the loop).
- Modifying `quality-gate` to evaluate noticed items.
- Cross-pipeline aggregation of noticed.md files (each pipeline stands alone).
- Replacing existing scope-discipline guardrails (self-review checklist,
  YAGNI reminders) — this **augments** them.

## Key Decisions

### DEC-1 (high): Storage location — per-pipeline file

**Decision:** Write aggregated observations to
`docs/plans/<YYYY-MM-DD>-<ticket-slug>-noticed.md`, committed with the PR.
The date and ticket slug match the convention used by sibling design /
plan / contract artifacts (e.g. `2026-04-16-noticed-but-not-touching-*.md`),
so noticed files sort alongside their originating pipeline's other docs.
The pipeline's `pipeline_id` (session-ID-based, per
`skills/build/SKILL.md` lines 467–469) is recorded **inside** the file's
frontmatter for attribution, not in the filename — raw session IDs are
long opaque hashes and would break `ls`-sort alignment with date-prefixed
siblings.

**Alternatives considered:**

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Date+slug file (`docs/plans/<date>-<slug>-noticed.md`, pipeline_id in frontmatter) | Sorts with sibling plan artifacts; human-readable; bounded scope; attribution preserved | Requires orchestrator to know the ticket slug (already known — design/plan files use it) | **chosen** |
| Raw pipeline-id file (`docs/plans/<pipeline-id>-noticed.md`) | Collision-proof across parallel builds on same date | Ugly opaque filenames; breaks docs/plans sort order | rejected |
| Cross-pipeline `docs/plans/noticed.md` | Single dashboard view | Unbounded growth; no pipeline attribution; merge conflicts across parallel builds | rejected |
| Dispatch-only artifact (never committed) | Zero repo noise | Observations die with the pipeline — defeats the purpose | rejected |
| GitHub issues (auto-created) | Durable, actionable | Loses per-pipeline grouping; explicitly out-of-scope per ticket | rejected |

### DEC-2 (high): Output format — structured markdown list

**Decision:** Each observation is a markdown list entry with four fields:

```markdown
- **file:** `path/to/file.ts:L123-L140`
  **noticed:** short description of what was observed
  **why it matters:** 1–2 lines on the risk or opportunity
  **suggested follow-up:** optional 1-line suggestion
```

Rationale: markdown is grep-friendly, diff-friendly, reviewable by humans in
the PR, and mechanically parseable by future tooling (e.g. `/finish`
offering to convert to issues). The `file:line-range` prefix lets readers
jump to the observation with any editor.

### DEC-3 (high): Where in the pipeline — scratch then reconcile

**Decision:** Implementer agents append observations to
`<scratch>/noticed.md` during their work. They **never** write to the
committed `docs/plans/*-noticed.md` file directly. After all implementers
complete, the orchestrator reads all implementer reports, collects their
`### Noticed But Not Touching` sections, dedupes, and writes the aggregated
file.

Rationale: this mirrors the existing `/build` scratch-and-reconcile
pattern (handoff manifests at phase boundaries, pipeline-active marker in
scratch). Implementers never race on a shared committed file.

### DEC-4 (medium): Trigger — mandatory report section, can be empty

**Decision:** Every implementer's report format gains a required
`### Noticed But Not Touching` section. If the implementer has nothing to
note, they write the literal string `*(none)*` — **not** omit the section.
This makes "noticed-and-logged" the zero-cost path and omission detectable.

### DEC-5 (medium): Conversion to issues — documented extension via /finish

**Decision:** Out of scope for this ticket, but `/finish` will be taught to
detect `docs/plans/*-noticed.md` and prompt the user:
"Found N noticed-but-not-touching entries from this pipeline. Convert any
to GitHub issues?" Conversion remains a human-confirmed action.

### DEC-6 (high): Anti-pattern guardrail — notice-AND-modify is a failure

**Decision:** If an implementer writes a Noticed entry pointing at `foo.ts`
**and** modifies `foo.ts` in the same task, that is a scope-discipline
failure.

Enforcement has two layers:

1. **Static (INV-3 grep-style contract check):** the implementer prompt
   template contains the Self-Review Checklist question "Did I notice
   anything out-of-scope? If yes, is it in the Noticed section and NOT in
   my diff?". INV-1/INV-2 grep-verify the prompt text.
2. **Behavioral (INV-3 selection eval, covered by T6):** dispatch a real
   implementer agent against a fixture with a visible out-of-scope bug and
   assert (a) a Noticed entry references the out-of-scope file, and
   (b) the out-of-scope file's hash is unchanged pre/post. A stubbed
   implementer cannot verify this invariant — only a live agent run can.

T4 is the **narrow mechanical contract test** (report-format parsing +
aggregation), T6 is the **behavioral invariant test**. Both are required
because a stubbed implementer can be made to emit any report, so INV-3's
"does the agent actually refrain from acting" clause must ride on a live
dispatch.

This closes the loophole where an agent might claim "I noticed it" as
cover for fixing it anyway.

## Architecture

```
Implementer 1 ──► report with ### Noticed But Not Touching
Implementer 2 ──► report with ### Noticed But Not Touching  ──► Orchestrator
Implementer N ──► report with ### Noticed But Not Touching         │
                                                                   ▼
                                                      Dedupe + sort by file path
                                                                   │
                                                                   ▼
                                 docs/plans/<date>-<ticket-slug>-noticed.md
                                       (pipeline_id in frontmatter)
                                                       │
                                                       ▼
                                                 committed with PR
                                                       │
                                                       ▼
                                       /finish offers issue conversion
```

## Failure Modes

| Failure | Detection | Mitigation |
|---|---|---|
| Implementer notices AND modifies out-of-scope file | INV-3 contract test | Fail the task; surface in code review |
| Implementer omits Noticed section entirely | Orchestrator parse check | Require `*(none)*` literal; reject reports missing the header |
| Two implementers notice the same thing | Orchestrator dedupes by `file:line-range` + `noticed` prefix | Dedupe during reconcile |
| Noticed file bloats the PR | Per-pipeline file bounds growth; empty pipelines produce empty file (or skip) | Skip write if zero entries across all implementers |
| Scope creep justified as "noticed" | Code review catches via diff vs noticed.md cross-check | Reviewer prompt reminds to spot-check |

## Integration Points

- **#176 (anti-rationalization tables):** also modifies `skills/build/SKILL.md`.
  Soft coordination — section placement should not collide.
- **#180 (context-trust hierarchy):** also modifies `skills/build/SKILL.md`.
  Soft coordination — same file, different sections.
- **`/finish` skill:** downstream consumer of the aggregated file. Changes to
  filename pattern (`*-noticed.md`) must be reflected in `/finish`.
- **`simplify` skill:** surfaces scope-adjacent concerns during review.
  Simplify runs *after* implementation and can legitimately propose changes;
  Noticed is implementer-level during work and must not act. The two are
  complementary, not overlapping.

## Open Questions

None — all resolved in DEC-1 through DEC-6.
