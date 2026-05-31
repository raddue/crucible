---
name: innovate
description: Use when a design doc or implementation plan is finalized and you want a divergent creativity injection before adversarial review. Proposes the single most impactful addition.
---

# Innovate

## Overview

<!-- CANONICAL: shared/dispatch-convention.md -->
All subagent dispatches use disk-mediated dispatch. See `shared/dispatch-convention.md` for the full protocol.

<!-- CANONICAL: shared/cairn-convention.md -->
Sweep-mode runs (multiple innovate invocations against the same target) maintain an Invariant Cairn per `shared/cairn-convention.md`. Single-run invocations do NOT — they're too short. See `## Cairn (Layer 3)` below.

Divergent creativity injection. Dispatches an Innovation subagent to propose the single most impactful addition to an artifact. One shot, not iterative — the red-team that follows is the quality gate.

**Core principle:** The best ideas often come from asking "what's missing?" after you think you're done.

**Announce at start:** "I'm using the innovate skill to explore potential improvements."

## Cairn (Layer 3)

Per `shared/cairn-convention.md`. Innovate-specific bindings:

- **Applies to sweep mode only.** A single-invocation innovate run is one dispatch and doesn't need a cairn. Sweep mode (≥ 3 invocations against the same target, per the `sweep-id` context key) does.
- **Phase mapping.** One cairn phase per sweep run: `run/1`, `run/2`, …. Each sweep run's `scratch/<run-id>/` directory already exists from the innovate convention; the cairn adds the cross-run continuity layer.
- **Terminal phase.** The last sweep run seals its `ranked.md` view.
- **Mandatory-invariant categories.** Each sweep run-exit MUST capture the run's proposal as an invariant (≤240 chars distillation) with `[ref: <innovate-run-id-as-receipt-prefix>]` — so later sweep runs can distinguish "already proposed" from "not yet" without re-reading every prior `proposal.md`.
- **Reconciliation.** Full 5-rule pass. Rule 4 (invariant-receipt liveness) applies only to invariants that carry `[ref: <receipt-prefix-12>]`. Innovate doesn't produce Layer 2 receipts (the orchestrator writes `proposal.md`/`alternatives.md` directly), so sweep-run invariants should use a phase/counter-based `[ref:]` of the form documented in the cairn convention's explicit-discharge path, OR omit `[ref:]` entirely (which forfeits the shedding license for those invariants — acceptable since innovate runs are not context-constrained the way /build is).

## When to Use

- After a design doc is approved by the user (before red-teaming)
- After an implementation plan passes review (before red-teaming)
- Anytime you want a creative enhancement pass on a finalized artifact
- When the build pipeline calls for innovation

## The Process

1. Generate a `<run-id>` and write `invocation.md` to scratch
2. Dispatch an Innovation subagent (Opus) with the artifact and context
3. Subagent proposes the single most impactful addition plus a "Why This Over Alternatives" narrative
4. Write the subagent's output to scratch: `proposal.md` + `alternatives.md`
5. Incorporate the proposal into the artifact (Plan Writer or equivalent)
6. If part of a sweep, update the sweep's `ranked.md` view
7. Proceed to red-teaming — the red team is the YAGNI gate

**Not iterative.** One shot per artifact. The red-team loop handles quality from there.

## Scratch Directory

**Canonical path:** `~/.claude/projects/<project-hash>/memory/innovate/scratch/<run-id>/`

The `<run-id>` is a timestamp generated at invocation start with millisecond precision: `YYYY-MM-DDTHH-mm-ss-<ms>` (e.g., `2026-04-19T10-30-00-427`), where `<ms>` is zero-padded milliseconds. Dashes are used as the time separator (not colons) so the path is filesystem-safe — this is a deliberate deviation from literal ISO-8601. If the target directory already exists on disk (rare), append `-2`, `-3`, etc. until a fresh path is found.

Files (written by the orchestrator, not the subagent):

- `invocation.md` — Written before dispatch. Strict YAML frontmatter followed by a markdown body. The frontmatter MUST be valid YAML, parseable by any standard YAML parser. The `sweep-id` field MUST be present: either a **double-quoted string** matching the sweep-id regex when in sweep mode (quoting is mandatory to avoid YAML type coercion — sweep-id values that would otherwise be parsed as booleans, numbers, or null must still be treated as strings), or the literal YAML value `null` (unquoted, not missing, not empty string) when in single-run mode. `run-id` and `target` fields must also be double-quoted. This makes parsing unambiguous across all edge cases. The `## Project Context` and `## Kill-Criteria` markdown headers in the body are informational (for human readers and `/recall` queries) — NOT structured fields that any orchestrator programmatically parses. Only the YAML frontmatter is parsed.

  ```
  ---
  run-id: "<run-id>"
  sweep-id: "<sweep-id>"  # or: null  (unquoted, for single-run mode)
  target: "<one-line artifact reference, e.g. filename or URL>"
  ---

  ## Project Context

  <one-paragraph summary>

  ## Kill-Criteria

  <if provided by caller; else: "None provided.">
  ```
- `proposal.md` — Written after subagent completion. The Single Best Addition + Impact + Cost sections, copied verbatim from the subagent's return.
- `alternatives.md` — Written after subagent completion. The "Why This Over Alternatives" section, copied verbatim. If the subagent did not identify alternatives, write `*(none reported)*`.

### Active Run Marker

At the start of every invocation, after generating `<run-id>` but before writing `invocation.md`, write a marker file to `~/.claude/projects/<project-hash>/memory/innovate/active-run.md` (outside the scratch tree) containing a single line: `run-id: <run-id>`. Delete this marker when `proposal.md` and `alternatives.md` have both been written (the run is sealed).

After compaction, the post-compaction orchestrator reads `active-run.md` if present to identify which `<run-id>` directory was in flight. If `active-run.md` is absent or points to a directory that no longer needs recovery (all files sealed), no in-flight recovery is needed.

**Stale marker handling:** If a stale marker exists from a prior crashed run (the scratch directory it points to has no `proposal.md` and no `alternatives.md`), the orchestrator **deletes only the marker file** and leaves the scratch `<run-id>/` directory intact. The orphaned `invocation.md` remains on disk as a historical record of the failed invocation — this preserves the append-only retention guarantee even for crashed runs. A paused sweep run whose orchestrator returns after a long delay (e.g., human-in-the-loop gap >1 hour) can still locate its in-flight directory and either resume (if the marker is still present) or treat the directory as orphaned (if a fresh invocation has since cleared the marker) — in the latter case, the next invocation in the sweep writes a new `<run-id>/` and the orphaned one remains for /recall consumers.

**No general stale-scratch cleanup.** Unlike prospector's 24-hour scratch cleanup, innovate has NO general cleanup of `scratch/<run-id>/` directories. All scratch persists indefinitely per the append-only retention rule. Only the `active-run.md` marker is ever deleted.

### Retention (Append-Only)

**Scratch is append-only. Never delete or overwrite `proposal.md` or `alternatives.md` after write.** Each run produces its own `<run-id>/` directory; later runs create new directories, they do not touch earlier ones.

Rationale: today's #2 proposal is often tomorrow's #1 when context shifts. Ranking is ephemeral; the proposal itself is the durable unit. Downstream consumers (future audit skills, `/recall` queries, sweep rankings) require access to the complete historical set.

**No file inside `scratch/` is ever rewritten.** A sweep's `ranked.md` (see Sweep Mode below) is rewritten between runs, but it lives in a sibling `sweeps/<sweep-id>/` tree — not under `scratch/` — and is explicitly a view layer over persistent scratch, not authoritative content.

**Note on prospector parity:** Prospector uses second-precision run-ids (`2026-03-18T14-30-00`). Innovate uses millisecond precision because sweep mode can invoke multiple times per second; prospector's multi-phase, multi-gate structure inherently spaces invocations further apart. This is a justified divergence, not an inconsistency.

## Sweep Mode (Optional)

When `/innovate` is invoked as part of a sweep (multiple invocations against the same target, e.g. "run /innovate six times for missed features"), the caller passes a `sweep-id` in the invocation context. Sweep-id can be auto-derived (e.g. hash of target + date) or user-supplied.

### Channel

- Sweep-id is passed as a key in the dispatch context block the caller provides to the skill — alongside the artifact, project context, etc.
- The key name is literally `sweep-id`.
- Format: a string matching `^[a-z0-9-]{1,64}$` (lowercase alphanumeric + hyphens, max 64 chars). If the caller-supplied value does not match, the orchestrator rejects the invocation with a clear error (do NOT silently sanitize — silent sanitization could collide distinct sweep-ids).
- Build pipeline callers that do not set this key operate in single-run mode. This preserves existing behavior exactly.

### Divergence Awareness

Before dispatching the subagent, if `sweep-id` is set:

1. List prior runs in the sweep by scanning `~/.claude/projects/<project-hash>/memory/innovate/scratch/` for directories whose `invocation.md` is a member of this sweep — read the YAML frontmatter and check the `sweep-id` field for exact string match (case-sensitive) to the current sweep-id. A `null` or non-matching value means the directory is not part of this sweep. (This is an O(N) scan over all-time scratch directories, acceptable at realistic usage scales of dozens to hundreds of runs; future work may add a `sweeps/<sweep-id>/members.txt` index to avoid the scan.)
2. Read each prior run's `proposal.md`
3. Include the prior proposals in the subagent's dispatch context under a **"Prior Proposals in This Sweep (Diverge From These)"** section
4. Instruct the subagent explicitly: "The proposals above have already been made in this sweep. Your proposal must be materially distinct — a different angle, a different layer, or a different framing. Do not propose a near-duplicate of any prior entry."

### Ranked View

After writing `proposal.md` and `alternatives.md` for the current run, update the sweep's ranked view:

**Canonical path:** `~/.claude/projects/<project-hash>/memory/innovate/sweeps/<sweep-id>/ranked.md`

Rewrite `ranked.md` to aggregate all sweep runs. Format: a numbered list of proposals sorted by the orchestrator's best-effort judgment of impact (using the subagent's stated impact and cost), with each entry linking back to its source `scratch/<run-id>/proposal.md`. This file is a **view**, not a source of truth — it lives outside `scratch/` and is rewritten between runs. Ranking is non-deterministic by design: a later re-rank may reorder earlier entries as context shifts, and the ranked.md view is explicitly non-authoritative per the Retention guarantee — consumers who need deterministic ordering must read source `proposal.md` files and apply their own criteria.

Per the retention guarantee above: if two proposals from different sweep runs look similar, the view may note the overlap, but **neither source `proposal.md` is ever modified or removed**.

## Compaction Recovery

If compaction hits between `invocation.md` being written and `proposal.md` being written, the post-compaction orchestrator reads `scratch/<run-id>/` and:

0. Read `active-run.md` if present to identify the in-flight `<run-id>`. If absent, no in-flight recovery is needed — proceed as a fresh invocation.
1. If `proposal.md` and `alternatives.md` exist → dispatch already completed; proceed to step 4 (incorporate) or step 5 (update sweep view) depending on `sweep-id` presence.
2. If `proposal.md` exists but `alternatives.md` does not → compaction hit mid-write between the two file writes. The subagent's full return (which contained both sections) is no longer in memory, so `alternatives.md` cannot be reconstructed. Re-dispatch with the same `invocation.md` and discard the stale `proposal.md`. **This is the ONE permitted overwrite of `proposal.md`, narrowly scoped to the atomic partial-write recovery window** — it is a documented exception to the append-only retention rule, permissible only when `alternatives.md` is absent in the same `<run-id>/` directory.
3. If only `invocation.md` exists → dispatch was in flight or never completed. Re-dispatch with the same `invocation.md` context. The orchestrator MUST NOT write a new `invocation.md` in a new `<run-id>/` directory for this retry — reuse the existing directory. Append-only retention does NOT apply to the in-flight directory until `proposal.md` lands; after that, the directory is sealed.
4. If neither exists → treat as fresh invocation.

## How to Use

### 1. Write invocation.md

Generate `<run-id>` per the format specified in Scratch Directory above. Write `scratch/<run-id>/invocation.md` containing the YAML frontmatter and markdown body defined in Scratch Directory.

### 2. Dispatch Innovation subagent

Use the `innovate-prompt.md` template in this directory. Provide:
- The full artifact content
- Project context (existing systems, constraints, tech stack)
- What the artifact is trying to accomplish
- If `sweep-id` is set: the "Prior Proposals in This Sweep" section (see Sweep Mode above)

Model: **Opus** (creative/architectural work needs the best model)

### 3. Persist and process the proposal

The subagent returns:
- **The Single Best Addition** — what to add and why
- **Why This Over Alternatives** — brief comparison to runners-up
- **Impact** — what it enables
- **Cost** — what it adds to scope/complexity

Immediately after completion, write to scratch:
- `proposal.md` — The Single Best Addition + Impact + Cost sections, verbatim
- `alternatives.md` — The Why This Over Alternatives section, verbatim

Do NOT paraphrase or summarize — copy verbatim so future audits see exactly what the subagent produced.

### 4. Incorporate and move on

Have the Plan Writer (or equivalent) incorporate the proposal into the artifact. Then proceed to red-teaming — if the addition is YAGNI, the red team will kill it.

### 5. Update sweep view (if applicable)

If `sweep-id` was set, rewrite `sweeps/<sweep-id>/ranked.md` per the Sweep Mode section. Scratch `proposal.md` files are never touched.

## What the Innovator is NOT

- A scope expander — one carefully chosen addition, not a feature wishlist
- A reviewer — they don't check quality or find bugs
- Iterative — one shot, move on

## Red Flags

- Writing `proposal.md` before the subagent dispatch completes
- Overwriting or deleting a `proposal.md` from a prior run (including during dedup — dedup is display-only)
- Skipping `invocation.md` on single-run invocations (persistence applies to all invocations, not just sweeps)
- Generating a sweep's `ranked.md` without linking each entry back to its source `scratch/<run-id>/proposal.md`
- Silently sanitizing a malformed `sweep-id` instead of rejecting with an error (silent sanitization can collide distinct sweep-ids)
- Passing the HTML-commented sweep instructions in `innovate-prompt.md` as prompt text to the subagent (comments are orchestrator-only)
- Treating a scratch directory with `proposal.md` but no `alternatives.md` as a complete run — this is a mid-write crash state, not a sealed directory
- Failing to write `active-run.md` at invocation start, or failing to delete it on completion

## Integration

**Called by:**
- **crucible:build** — Phase 1 (after design), Phase 2 (after plan review)
- **User or future sweep orchestrator** — standalone invocations and multi-run sweeps are supported via the `sweep-id` dispatch context key (see Sweep Mode above)

**Pairs with:**
- **crucible:quality-gate** — always runs after innovate to validate the addition

See prompt template: `innovate/innovate-prompt.md`
