---
version: 1
---

# Change-Bundling Convention

> Canonical reference for deterministic changed-file selection + bundling across
> all orchestrator/review dispatch. `warden` and `orchestrator` reference this
> file via `<!-- CANONICAL: shared/change-bundling-convention.md -->`.
>
> **This is a shared skill reference, not a CLAUDE.md directive.** CLAUDE.md
> must not duplicate the bundling rules.

## Problem

On a large changeset, a reviewer instructed (in natural language) to "review
the diff" reliably **cuts corners** — it reviews the files the prompt happens to
emphasize and silently skips the rest. Coverage is whatever the prompt produced:
purely prompt-driven, non-deterministic, unverifiable. alibaba/open-code-review
solved this with *deterministic engineering* — a code step that decides **which
files are reviewed** before any agent runs, so the language model never decides
the review set. This convention ports that shape to Crucible dispatch.

## The deterministic step

Before any review worker is dispatched over a many-file diff, the orchestrator
runs **one** deterministic selection + bundling pass (the contract below is
executed by `scripts/change_bundling.py`, the single source of truth; its
contract is pinned by `scripts/test_change_bundling.py`). The step's output —
the bundle list + per-file coverage report — is the **only** input to worker
dispatch. No reviewer re-derives the changed-file set from the prompt.

### Enumerate

List every changed path in the diff scope (`git diff --name-status <base..head>`
for a range, or the forge's changed-files call for a PR). This is **the full
changed-file set** — nothing is filtered by prompt preference.

### Select

Split the enumerated set into **selected** (reviewable) vs **explicitly
excluded**:

| Excluded | Reason token | Why |
|---|---|---|
| Deleted (status `D`) | `deleted` | no new content to review — the removal is still *named*, never silent |
| Binary / non-reviewable extension | `binary` | no textual content for a reviewer to read |

Everything else is selected. The exclusion list is **part of the report** — an
explicit skip is not a silent skip.

### Bundle

Group the selected files into bundles:

1. **Locale siblings first** — files in one directory whose names differ only by
   a trailing locale token (`message_en.properties` / `message_zh.properties` /
   `message_de.properties`) share one bundle, because a change to one almost
   always implies the same change to the others.
2. **Directory affinity** — remaining single files in the same directory bundle
   together.
3. **Size cap** — any bundle over `MAX_FILES_PER_BUNDLE` (10) splits into
   deterministic alphabetical chunks, so a single directory bulk-change fans out
   instead of overloading one worker.

**Determinism:** same input changed-file set → same bundles, regardless of input
order, run, or reviewer. Order-independence is the point: the bundle partition is
a pure function of the changed paths, so two orchestrators (or two runs) never
disagree on who covers what.

### Cover-report (the no-silent-skip guarantee)

Every changed file gets **exactly one** review assignment, verified by the
coverage report:

- **bundled** — the file is in exactly one bundle and one review worker covers
  that bundle;
- **skipped** — the file is explicitly excluded (`deleted` / `binary`) and its
  skip reason is in the report;
- **neither** — the engine raises. A changed file with no bundle and no explicit
  skip is a defect, not a soft warning. **This is the machine-enforced
  guarantee that a many-file review produces per-file coverage with no silent
  skips.**

## Dispatch protocol

1. Run the deterministic step (enumeration → selection → bundling → coverage
   report). Keep the report.
2. Dispatch **one review worker per bundle**, each worker's dispatch context
   naming its **exact file list** (the bundle it owns). Workers never receive
   "the diff, review it" — they receive one bundle.
3. Dispatch all bundles **concurrently** where the harness allows (each bundle is
   an isolated context, so fan-out scales with bundle count).
4. **Reconciled on completion:** the union of every dispatched bundle's coverage
   markers **must equal** the coverage report's `bundled` set, and the report's
   `skipped` set is acknowledged explicitly. A bundle that dies (crashes /
   timeouts / returns no parseable receipt) is **fail-closed**: the failed
   bundle's files are surfaced, never merged as though covered. Mirrors
   `warden`'s dead-leg rule — an unrun gate is not a pass.

## Behavior on small diffs

The deterministic step costs nothing on a small diff — a 1–3 file change bundles
into one bundle and dispatches one worker, exactly as today. The step only
*changes* behavior when the diff is large enough that prompt-driven review would
have risked skips; there it guarantees coverage that prompt-following cannot.

## Consumers

- **warden** — the standalone pre-push gate (:acceptance on a many-file diff →
  fan review legs per bundle, so every changed file is covered exactly once).
- **orchestrator** — Herdr team-boss dispatch (:bundle review work per
  `change-bundling` bundle, one worker per bundle, concurrent).

Each consumer's SKILL.md carries the same canonical link and the dispatch
protocol above; neither re-implements the bundling rules — they call
`scripts/change_bundling.py`.