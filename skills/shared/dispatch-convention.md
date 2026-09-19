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

## Scope Anchoring (opt-in)

> Dispatched subagents drift: they fix an adjacent defect, generalize past the
> request, or record bookkeeping about work nobody asked for. Scope anchoring is the
> two-tier checkpoint any orchestrator can opt into. **Tier 1 is the default; tier 2 is
> for dispatches whose file set cannot be pinned up front, or whose file set is pinnable
> but whose intra-file work is not mechanically constrained.** Skills that adopt either tier
> link this section — do not re-specify it per skill (except quality-gate's tier-1
> reference implementation, retained deliberately; de-duplicating it is tracked
> separately).
>
> Prior art and reference implementation of tier 1: `skills/quality-gate/SKILL.md`
> ("Scope Anchoring for Fix Agents"). Measured evidence for tier 2: `#562` spike,
> `docs/research/2026-09-06-scope-judge-spike.md`.

Every scope-anchored dispatch carries a **scope statement** in its dispatch file: one
sentence naming what the subagent is fixing, and an explicit "do not add features,
restructure, or make changes outside these findings" clause.

### Tier 1 — mechanical change boundary (cheap; default)

Use when the orchestrator can name the allowed files/sections **before** dispatch.

1. **Change boundary.** The dispatch file lists the specific files or sections the
   subagent may modify. A finding that cannot be resolved inside the boundary must be
   flagged in the receipt, not fixed.
2. **Drift detection.** After the subagent returns, the orchestrator diffs the actual
   changed-path set against the boundary — and, where sections were named, checks by
   inspection whether the change also stayed inside the named sections. Any path outside
   the boundary, or a change outside a named section within an allowed file, → reject the
   round's output, re-dispatch with the out-of-scope items named explicitly, and carry
   those items forward as context for the next review round.

The `git diff --name-only` check catches "touched a file it was never pointed at" for
free; section-level drift inside an allowed file is caught only by inspection (see
quality-gate's implementation), which is what tier 2 mechanizes — whether the file set
could not be pinned up front, or was pinned but its intra-file work is not mechanically
constrained.

### Tier 2 — semantic scope judge (for unpinnable scope)

Use when the right file set is not knowable in advance (a bug fix whose root cause is
still being located, an implementer working from a design), or when the dispatch's
allowed file set was pinnable but the work inside those files is not mechanically
constrained — i.e. intra-file expansion is a plausible failure mode that a named-section
inspection was not run against.

Dispatch **one** judge after the work completes — model tier **sonnet**, the same tier as
quality-gate's fix verifier — using `shared/scope-judge-prompt.md`. It receives **only**:

- (a) the original task / finding / hypothesis text, verbatim, and
- (b) the resulting diff.

Nothing else. No repo access, no fix journal, no reviewer narrative, no commit messages.
The isolation is the mechanism: a judge with the surrounding context reconstructs a
justification for almost any change, which is exactly the failure being checked for.
The judge's procedure requires hunk-level content to classify — a bare changed-file list
is not a valid substitute and was not measured; if a diff is too large to dispatch
whole, restrict it by path rather than passing a file list.

The judge labels every changed file — per hunk-group where a file is mixed — as
`in-scope`, `justified-adjacent` (must name what would break without it), or
`unrequested-expansion`, and returns `VERDICT: IN-SCOPE | SCOPE-EXPANSION` plus a flagged
path list and a self-reported confidence.

**Reading the verdict.** `SCOPE-EXPANSION` is a **signal, not a rejection** — unlike tier
1's boundary breach, it is a judgment call and the orchestrator owns the decision. On
`SCOPE-EXPANSION`, the orchestrator picks one of three responses: inspect the flagged
hunks itself and re-dispatch asking for the ones it independently agrees are untraceable
to be dropped; record the expansion as an accepted deviation with a one-line reason; or,
for an advisory-only adoption that does not act on the verdict at all, record it and
surface it for a later review phase to weigh (this is the shape debugging's Phase 4.4
uses). `CONFIDENCE: medium` is advisory only and must never auto-reject; `CONFIDENCE:
high` is a self-report that classification felt unambiguous, not a validated measure of
correctness, and must not auto-reject on its own either. **`CONFIDENCE: low` is not a
scope verdict at all** — per `shared/scope-judge-prompt.md`'s `## Confidence`, it reports
that the request text was unusable, which forces every group to `unrequested-expansion`
by construction; treat it exactly as an unparseable return: record why the verdict was
unusable, and proceed.

**If the judge's return is missing `VERDICT:`, missing `CONFIDENCE:`, carries
`CONFIDENCE: low`, the `VERDICT`/`FLAGGED` pair is internally inconsistent (e.g.
`SCOPE-EXPANSION` with `FLAGGED: none`, or `IN-SCOPE` with a non-empty `FLAGGED` list), or
either contradicts `CLASSIFICATION` — `VERDICT: IN-SCOPE` or `FLAGGED: none` while any
`CLASSIFICATION` group is labelled `unrequested-expansion`, or the `CLASSIFICATION`
section carries no groups at all, in either verdict direction, or a path with such a group
missing from a non-empty `FLAGGED` list — or, in the other direction, `VERDICT:
SCOPE-EXPANSION` or a non-empty `FLAGGED` list while **no** `CLASSIFICATION` group is
labelled `unrequested-expansion`, or a `FLAGGED` path none of whose `CLASSIFICATION`
groups is so labelled — or otherwise unparseable:** record why the
verdict was unusable, and proceed. Do not
re-dispatch the judge — it is a one-shot check by design.

**Known divergence from `shared/return-convention.md`.** The tier-2 judge
(`shared/scope-judge-prompt.md`) returns plain structured text (`VERDICT:`/`FLAGGED:`/
`CLASSIFICATION:`/`CONFIDENCE:`), not an Evidence Receipt. An orchestrator that has
adopted the receipt convention — "every subagent it dispatches ... MUST return exactly
one Evidence Receipt" — has an unresolved conflict the moment it adopts tier 2: giving
the judge a receipt shape is a prerequisite for that adoption and has not been done.
Debugging's Phase 4.4 prototype does not carry the `return-convention.md` marker, so it
does not hit this conflict today; a future adopter that does carry the marker must
resolve it before dispatching the judge as specified here.

**When NOT to run tier 2.** The judge's cost is dominated by a fixed per-dispatch
overhead, so it is only worth paying against work that is itself substantial. Skip it
when:

1. the dispatch's allowed file set was fully pinnable up front AND the work inside those
   files is mechanically constrained (a rename, a config value) — i.e. intra-file
   expansion is not a plausible failure mode;
2. the diff is trivially small (single-hunk fixes); or
3. the dispatch is *deliberately* exploratory or expansive — a blast-radius scan that
   fixes sibling occurrences by design will be flagged as expansion by a judge that was
   only shown the original bug.

Conditions (1) and (3) are categorical: where either holds, do not run tier 2, whatever
an adopting skill's size threshold says — (3) in particular cannot be expressed as a
threshold, and a large deliberately-expansive diff is the case a size rule gets wrong.
Condition (2) is deliberately imprecise; an adopting skill's own mechanical size
threshold (e.g. debugging's Phase 4.4: `>1 non-test file OR >40 changed lines in
non-test files`) is the operative rule wherever it and "trivially small" could disagree
on a specific diff.

**Cost (measured, #562):** these figures and the threshold above assume a Sonnet judge;
no agent def binds that tier today (`harness-adapter.md` Mapping 1b — prose model words
are descriptive, not binding), so an orchestrator running on a larger model pays
proportionally more and the threshold is correspondingly miscalibrated. All six run-1
dispatches now have a retained token/wall
figure — P1/P2/N1/N2 captured at run time, P3/N3 recovered from the session transcript's
per-dispatch `<usage>` records and cross-validated (that field matches the four
run-time-recorded figures exactly, 4/4, so it is the same measurement — see the write-up's
Provenance section). A fixed per-dispatch floor of **~50.3k tokens** dominates: the two
smallest diffs cost 50,439 and 50,325 tokens, close to that floor. Across the full
six-point corpus the spread is 50,325-60,119 tokens — under 20% between the cheapest and
most expensive case, while diff size varies 4.7x. Diff-size dependence beyond the floor is
**not characterized**, and the full corpus sharpens the non-monotonicity: N3's diff is
about half the size of P1's yet costs more tokens and over 3x the wall time (58,678
tokens/81.7s vs. 56,422 tokens/23.9s) — confirming, on all six points rather than four,
that a fixed floor dominates and diff-size dependence past it is not characterized. One
sonnet dispatch per case; the one-turn/one-tool-call characterization was observed at
spike time but is not itself a retained, citable figure (see the write-up's Cost
section). 14-82s wall across the six cases, fully parallelizable against other post-work
checks. Run 2's cost (P3 = 58,513 tokens/58.4s, N3 = 58,422 tokens/78.7s) was also
recovered post-hoc from the transcript, the same route and caveat as run 1's P3/N3
figures — cost is post-hoc for run 2 and for run 1's P3/N3; run 1's P1/P2/N1/N2 cost was
captured at run time (see the write-up).

On the #562 corpus the judge scored 3/3 on diffs containing a real unrequested expansion
and 3/3 on clean diffs whose only extra touches were legitimate side-effects (dead-import
removal, `.gitignore`, prose restated to match a changed spelling) — case-level verdicts
against pre-registered ground truth: four cases (P1, P2, N1, N2) single-run, two cases
(P3, N3) whose retained run-1 verdict was recovered post-hoc from the session transcript
and then confirmed by a live-captured second run — two of the six cases were re-run, n=6,
one model (see the write-up's Provenance for the run-1/run-2 provenance asymmetry).
Hunk-level labels were **not** stable under replication: run 1 P3 had 3 of 9
hunk-classification groups differ from ground truth, 2 of them crossing the expansion
line (one root judgment error, propagated to its test) and a third that does not (a
justified-adjacent-vs-in-scope mismatch), that run 2's different 7-group partition
matched ground truth on, while reproducing the case-level verdict, flagged set, and
confidence exactly (see the write-up), so the 3/3 rates above are case-level results, not
a variance-measured false-positive rate at the hunk level.
The prompt was also amended after measurement (a `## Confidence` rubric and injection
hardening were added), so these numbers are evidence for the approach, not for the
shipped `shared/scope-judge-prompt.md` text as written.

## Graphify Consult

A `graphify-out/graph.json` call graph (AST-derived, built by graphify) is a
second, machine-checkable structural-knowledge source alongside cartographer's
curated prose map. When composing a dispatch file for a target repo, check
whether that repo carries a graph and whether it is fresh enough to trust; if
both hold, include a pointer clause directing the receiving agent to query the
graph FIRST for structural questions before falling back to grep/Explore.

The staleness check is `check-graph-staleness.sh [--json] [repo_dir]` (shipped
in ai-rack's hooks; generic over any repo). Its human line carries the stable
prefix `graphify-staleness:`; `--json` emits the same facts as an object
(`{"state":"stale","commits_behind":N,...}`). The `no-graph` ("never built") and
`stale:N` ("built N commits behind") states are deliberately distinct and never
collapsed.

The script itself may simply be **not present in the target repo** — today that
is every repo except `ai-rack`. This is a distinct case from any state the
script reports, since an absent script cannot be invoked to report anything.
Before consulting staleness, check the script exists in the target repo; if it
does not, skip the pointer clause entirely and fall back to grep/Explore +
cartographer, same as the `no-graph` row below — do not invent a state or try
to reconstruct one by other means.

Trust tiers — the dispatch author decides the pointer from the staleness state:

| State | Dispatch action |
|---|---|
| `fresh` | Point at the graph; instruct query-first as authoritative for structure. |
| `stale:N`, N ≤ 5 | Point at the graph with a cross-check caveat: verify any answer whose reachable files fall in `git diff <built>..HEAD`. |
| `stale:N`, N > 5 / `diverged` / `unknown` / `no-graph` / `no-commit` / `no-git` | Do NOT pre-point; instruct the agent to rebuild (`/graphify`) or fall back to grep/Explore + cartographer. |

The ≤ 5 bound is a structural-freshness call, not an accuracy guarantee: the
graph answers structure questions, and structure changes only on renames,
refactors, and dependency edits — ordinary logic commits leave the call graph
intact. Five commits is one worker session's worth of change; beyond that,
cross-checking every answer costs more than re-deriving the structure.

The pointer clause, when included:

> A graphify call graph exists at `graphify-out/graph.json` (staleness: <state>).
> For structural questions — what calls/imports X, blast radius, shortest path,
> architectural hubs — query it first: `graphify explain <node>`,
> `graphify affected <node>`, `graphify path A B`, `graphify query "<question>"`.
> Fall back to grep/Explore only where the graph does not cover the area.

Enforcement stance — **recommended, not enforced**. This is a default-on
knowledge accelerator, not a hard gate. Including the pointer is the default
whenever a trust tier says so; omitting it is a deviation the orchestrator
should note, because the whole point is to stop re-deriving structure the graph
already knows. It is never a reason to block a dispatch: when the graph is
absent, stale, or does not cover the area, proceed with grep/Explore and
cartographer. This matches the staleness script's own posture (an announcement,
never a gate — it always exits 0) and cartographer's (RECOMMENDED, not
REQUIRED).

This convention adds a pointer, not a new store. Graphify is the derived call
graph; cartographer is the curated prose map — see cartographer-skill's "With
Graphify" note for the division of labor. Do not fold one into the other.

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

**Runtime tool (preferred — the steps below are the spec + fallback).** Use `python3 scripts/dispatch.py` for the mechanical bookkeeping: `seq --dir <D>` (crash-safe next seq = last manifest `seq` + 1), `before --dir <D> --seq N --file <dispatch-file> --role <r> [--phase P] [--task K] --model-tier <t>` (measures `input_chars` and appends the `dispatched` entry), `after --dir <D> --seq N --status <completed|failed|error|skipped> [--summary …] [--output-chars C] [--tool-calls K] [--duration S]` (appends the authoritative completion entry, copying the dispatched entry's context fields), and `cleanup --dir <D> --scratch <s> [--failed]` (## Cleanup). Token/rework aggregation stays in forge's Step 8.5 (single owner — no third copy). The steps below remain the canonical spec.

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
