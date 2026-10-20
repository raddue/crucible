---
name: build
description: "Use when starting any feature development, building new functionality, implementing a design, going from idea to working code, or planning and executing a migration (framework upgrade, API version bump, dependency major version, deprecation removal). Triggers on \"build\", \"implement\", \"add feature\", any task requiring design-through-execution, \"migration plan\", \"upgrade X from Y to Z\", \"remove deprecated\", \"major version bump\"."
---

# Build

## Overview

<!-- CANONICAL: shared/dispatch-convention.md -->
All subagent dispatches use disk-mediated dispatch. See `shared/dispatch-convention.md` for the full protocol.

<!-- CANONICAL: shared/return-convention.md -->
All subagent returns use the Ledger Return Protocol. Every subagent returns exactly one Evidence Receipt per `shared/return-convention.md`; the orchestrator applies the two-tier receipt linter (Tier 1 structural + Tier 2 witness verification — full grammar in the shared convention) to every Task return before acting on the declared VERDICT. The linter is a deterministic runtime tool: orchestrators MUST run the installed write-boundary wrapper `/usr/local/libexec/crucible/rcpt-verify` (never a bare PATH lookup) when it is present — identical flags, and the wrapper's absence is never a failure (opt-in hardening, AC-25) — else the direct `python3 scripts/rcpt_verify.py --tier2 --strict --root <dispatch-root> --ledger <dispatch-root>/receipt-ledger.jsonl <receipt>` on every received receipt before acting on its VERDICT, and apply the shared convention's in-context pseudocode ONLY as the fallback when the tool is unavailable (`--root` is repeatable, but build passes exactly one — the dispatch root; a sha256 mismatch on any resolved artifact hard-FAILs with or without `--strict`, `--strict` additionally hard-FAILs a path-shaped name that neither the dispatch root nor its git toplevel holds, and under a single root the cross-root ambiguity hard-FAIL cannot arise at all — an unresolvable bare basename is UNVERIFIABLE, never a false FAIL). A lint failure is treated as structurally `BLOCKED`.

<!-- CANONICAL: shared/cairn-convention.md -->
The orchestrator maintains a per-run Invariant Cairn at `~/.claude/projects/<project-hash>/memory/cairn/cairn-<run-id>.md` per `shared/cairn-convention.md`. See the `## Cairn (Layer 3)` section in `references/runtime-protocols.md` for build-specific phase definitions, terminal condition, and mandatory-invariant categories.

End-to-end development pipeline: interactive design, autonomous planning with adversarial review, team-based execution with per-task code and test review. One command, idea to completion.

**Announce at start:** "I'm using the build skill to run the full development pipeline."

**Models:** Build dispatches request model-agnostic profiles. Implementers, plan writers, and gate-critical reviewers generally request `high`; bounded mechanical work and some reviewers may request `standard` under the existing complexity heuristics. Prompt templates show current Claude Code reference aliases; other harnesses map supported profiles or omit unsupported model fields per `shared/model-tier-policy.md`.

**Session index event:** At startup, if session indexing is active (session index path discoverable via glob), emit a `skill_start` event to the outbox: `{"ts":"<now>","seq":0,"type":"skill_start","summary":"Starting /build for <user goal>","detail":{"skill":"build","goal":"<user goal>"}}`. See `skills/shared/session-index-convention.md` for the outbox pattern.

**Guiding principle:** Quality over velocity. This pipeline produces correct, well-integrated, maintainable output — even if slower. Parallel execution is available for independent work, but sequential with quality gates is the default.

<!-- Trust framework: see [skills/getting-started/trust-hierarchy.md](../getting-started/trust-hierarchy.md). -->

## Contents and reference map

This body is the entry point and table of contents. Phase detail lives in flat reference files one level below; read each one at the moment its phase or protocol starts — do not skip a referenced file:

- [references/runtime-protocols.md](references/runtime-protocols.md) — Mock Dispatch Mode (eval-gate), Cairn (Layer 3), Tripwire Manifest Sweep (Layer 2). Read at startup.
- [references/gate-ledger.md](references/gate-ledger.md) — Gate Ledger Protocol: PipelineID, ledger format, run isolation, Verdict Marker Verification, skip escape hatch, state machine, RequiredModelAssurance opt-in and the QG-leg assurance predicate, ledger compaction recovery. Read before Phase 1.
- [references/pipeline-status.md](references/pipeline-status.md) — Pipeline Status file, health state machine, Compaction Recovery, Compression State Block, Phase Handoff Manifest.
- [references/phase-1-design.md](references/phase-1-design.md) — Phase 1: Design (Step -1 resume detection and pipeline-active marker through Phase Handoff 1 → 2, including refactor-mode blast radius).
- [references/phase-2-plan.md](references/phase-2-plan.md) — Phase 2: Plan.
- [references/phase-3-execute.md](references/phase-3-execute.md) — Phase 3: Execute (team setup, per-task review cycle, refactor-mode Phase 3 changes, Noticed Reconciliation, Phase Handoff 3 → 4).
- [references/migration.md](references/migration.md) — Migration mode (absorbed `migrate` skill): phased migration plan, compatibility layer, consumer waves, rollback points, per-phase execution through this pipeline, kill criteria.

Phase 4 (Completion), escalation, quality-gate orchestration, red flags and integration stay in this file.

Shared conventions those references apply: [pipeline-status-convention.md](../shared/pipeline-status-convention.md) (status file) and [compass-protocol.md](../shared/compass-protocol.md) (Phase 1 arc-start emit).

## Communication Requirement (Non-Negotiable)

**Between every agent dispatch and every agent completion, output a status update to the user.** This is NOT optional — the user cannot see agent activity without your narration.

Every status update must include:
1. **Current phase** — Which pipeline phase you're in
2. **What just completed** — What the last agent reported
3. **What's being dispatched next** — What you're about to do and why
4. **Task checklist** — Current status of all tasks (pending/in-progress/complete)

**After compaction:** If you just experienced context compaction, re-read the task list from disk and output current status before continuing. Do NOT proceed silently.

**Examples of GOOD narration:**
> "Phase 3, Task 4 complete. Reviewer found 2 Important issues — dispatching implementer to fix. Tasks: [1] ✓ [2] ✓ [3] ✓ [4] fixing [5-8] pending"

> "Phase 2 complete. Plan passed review with 0 issues on round 2. Dispatching design's innovation pass on the plan."

**This requirement exists because:** Long-running autonomous pipelines can run for hours. Without narration, the user sees nothing but a spinner. They can't assess progress, can't decide whether to intervene, and can't learn from the pipeline's decisions.

## Pipeline Discipline (Non-Negotiable)

NEVER skip quality gate steps. Every artifact must pass its quality gate before proceeding to the next phase. No exceptions, no shortcuts.

**BLOCK semantics:** Phase transitions are gated. You CANNOT proceed from Phase 1→2, 2→3, or 3→4 without the gate for that phase passing. If a gate fails, fix the issues and re-run the gate. Do not silently skip a gate because "it looks fine" or "we already reviewed it."

**If you find yourself about to skip a gate:** STOP. Re-read this section. The gate exists because skipping it has caused real production incidents and hours of wasted time. Run the gate.

## Anti-Rationalization Table — build

| Rationalization | Rebuttal | Rule |
|---|---|---|
| "This task is small/simple/trivial, the quality gate would just find nits." | Small changes have the same bug density per line as large ones. QG has never run on a Crucible artifact without finding at least one real issue. | Run the quality gate on every phase artifact, regardless of size. |
| "Phase N looks fine, I can skip the gate and move on." | Self-assessment of artifact quality is exactly the bias the gate exists to counter. "Looks fine" is the failure mode, not a pass criterion. | Phase transitions are BLOCKED without a verified PASS verdict marker for the prior phase. |
| "The fix agent addressed the findings, so the gate is done." | Fixing is not passing. Fix rounds routinely introduce new issues or incompletely resolve old ones. A fresh verification round is required. | The gate is only complete after a mode-clean fresh reverify: `0 Fatal` in default `standard`, or `0 Fatal, 0 Significant` when the caller passes `mode: full`. A truly clean first round (`0 Fatal / 0 Significant`) may use normal candidate-clean handling; first-round `0 Fatal / >0 Significant` is actionable. Standard residual Significant/Minor findings must be disclosed. |
| "The user said 'looks good' / 'move on' — that's approval to skip the gate." | General feedback is not skip approval. Only an unambiguous instruction that explicitly references the gate counts. | Require literal `SKIP GATE` (or equivalent explicit phrase) before recording `Status: SKIPPED`. |
| "I can fix this one finding myself instead of dispatching a fix agent." | Orchestrator-applied fixes conflate coordination with remediation and bypass the fix journal. Every fix — even trivial — goes through a fix agent. | Orchestrator never edits the artifact directly; always dispatch the fix agent. |
| "Design's innovation pass/red-team seem redundant on top of the quality gate, I'll skip them." | They are not redundant. Innovation is divergent; red-team is adversarial; QG is iterative remediation. Skipping any one of them is a documented regression (`feedback_never_skip_gates`). | Run design's innovation pass and red-team on every artifact, every time. |
| "I'll just finish the task list and narrate at the end." | Long-running autonomous pipelines are invisible without narration. Silent runs prevent the user from intervening or learning. | Narrate before every dispatch and after every completion — non-negotiable. |

## Quality Gate Requirement (Non-Negotiable)

**Every quality gate in this pipeline MUST run to completion.** This is NOT optional — you may NOT self-assess whether a quality gate is "needed" based on task size, complexity, or scope.

Quality gates are unconditional at all three gate points:
1. **Phase 1, Step 2** — Design doc gate
2. **Phase 2, Step 3** — Plan gate
3. **Phase 4, Step 6** — Implementation gate

**Common rationalizations that are NEVER valid reasons to skip:**
- "This is a small change"
- "This is trivial / simple / straightforward"
- "This is just a config change / documentation update / one-liner"
- "The quality gate won't find anything on something this simple"
- "I fixed the findings, so the gate is done" — **fixing findings is NOT the same as passing the gate.** The iteration loop must complete with a mode-clean fresh reverify (`0 Fatal` in default `standard`; `0 Fatal, 0 Significant` with `mode: full`). Standard residual Significant/Minor findings must be disclosed. Fix agents introduce new issues or incompletely resolve old ones — that is why fresh-eyes re-review exists.

**This requirement exists because:** Quality gates consistently find issues the pipeline misses regardless of task size. There is no category of task that is immune. In observed runs, tasks self-assessed as "trivial" had the same defect rate as complex tasks. The only way to skip a quality gate is with explicit user approval — an unambiguous instruction specifically referencing the gate, not general feedback like "looks good" or "move on."

## Mode Detection

Before dispatching the design skill, determine whether this build is:

- **Feature mode** (default) — adding new capability. Success = new acceptance tests pass.
- **Refactor mode** — restructuring existing code. Success = existing behavior preserved + structural goals met.
- **Migration mode** — planning and executing a migration (framework upgrade, API version bump, dependency major version, deprecation removal; entered as `/build <migration request>`, e.g. "migration plan", "upgrade X from Y to Z", "remove deprecated", "major version bump"; `--plan-only`, `--execute <migration-plan>` and `--orgs` are migration-mode options and imply migration mode). Success = every migration phase reaches its safe stopping point and the old version is removed. Migration mode is an invocable subflow that wraps this pipeline: follow [references/migration.md](references/migration.md) end to end; it dispatches this pipeline once per migration phase in feature or refactor mode. Build's own phase flow (Phases 1–4) is unchanged.

**Detection:** If the user's intent is ambiguous, ask directly before proceeding:

> "Is this adding new behavior, or restructuring existing code without changing what it does, or migrating a framework/dependency/API version?"

The user's answer sets the mode for the entire pipeline. No special syntax needed.

> **Eval-gate pointer (Mock Dispatch Mode):** if `CRUCIBLE_BUILD_EVAL_MODE` is set, use its value (`feature` or `refactor`) as the mode-detection answer and skip the AskUserQuestion call. The substitution rule lives in the `## Mock Dispatch Mode (eval-gate)` section of `references/runtime-protocols.md`.

### Mode Propagation

Propagate refactor mode to subagents through:

1. **New refactor-specific prompt templates** — `contract-test-writer-prompt.md` and `refactor-implementer-addendum.md` are standalone files used only in refactor mode. Select these instead of (or in addition to) the feature-mode equivalents.
2. **Appended context blocks** — For existing prompts that serve both modes (`plan-writer-prompt.md`, `build-implementer-prompt.md`), append a "Refactor Mode Context" section when composing the dispatch file. The templates remain flat markdown — the orchestrator decides what to include.
3. **Scratch file for compaction recovery** — Persist current mode in `<build-scratch>/build-mode.md` containing `mode: refactor` or `mode: feature` plus baseline commit SHA. The worktree namespace prevents concurrent builds from overwriting it.

### Compaction Recovery

Build's existing compaction step must read the Compression State FIRST (step 0 from Pipeline Status Compaction Recovery in `references/pipeline-status.md`), then the mode file, before re-reading the task list or any other state. On resumption after compaction:

0. **Read `## Compression State` from `<build-scratch>/pipeline-status.md`** — recover goal, decisions, constraints, next steps.
0.5. **Check for handoff manifests** (`handoff-*-to-*.md`, format in `references/pipeline-status.md` § Phase Handoff Manifest) in `<build-scratch>`. If the most recent manifest exists, use its Inputs and Mode to bootstrap recovery — this supersedes the mode file for phase-boundary state.
1. **Read `<build-scratch>/build-mode.md`** — recover mode and baseline commit SHA.
2. **If file is missing:** Default to feature mode and warn.
3. **If mode is `refactor`:** Verify baseline commit SHA exists.
4. **Read `<build-scratch>/build-gate-ledger.md`** — if it exists, apply Gate Ledger Compaction Recovery (see Compaction Recovery (Ledger) in `references/gate-ledger.md`). Use the ledger's phase statuses to determine the resume point. If the ledger is missing but handoff manifests exist, reconstruct with INFERRED status.
5. **After mode and ledger are recovered:** Proceed with general state reconstruction (task list, phase, health).

## Phase 4: Completion

> **Eval-gate pointer (Mock Dispatch Mode):** when `CRUCIBLE_BUILD_EVAL_MOCK_DIR` is set, the temper, inquisitor, optional siege, quality-gate, forge, cartographer, and finish dispatches in this phase use the mock-dir substitution rule defined in the `## Mock Dispatch Mode (eval-gate)` section in `references/runtime-protocols.md`. Local test-suite execution (`pytest`, etc.) runs normally — substitution applies only to subagent dispatches.

After all tasks complete:

0. **Write Phase 4 IN_PROGRESS** to the gate ledger (after Phase 3 COMPLETE verification).

1. **Feature mode:** Run acceptance tests from Phase 1 Step 3 — verify they **PASS** (GREEN). **Refactor mode:** Run all contract tests from Phase 1 — verify they **PASS** (GREEN).
   - If any fail: implementation is incomplete. Identify what's missing, dispatch implementer to fix, re-run.
   - If all pass: feature is verifiably done. Proceed.
2. Run full test suite (unit + integration)
2.5. **Guarantee a fully-clean working tree before the review gate.** The Step-1/Step-2 test runs sit between the Phase-3 commit and the review gate and can leave residue — not only tracked modifications but also untracked artifacts. Run `git status --porcelain` and drive the tree to **fully empty** (tracked **and** untracked) by **producing** that clean state, not merely checking for one. `docs/memory.md` is the sole exception: it is committed only at end-of-session and excluded from this mid-session check. Because `git status --porcelain` never lists `.gitignore`d paths, properly-ignored caches/coverage never appear, so the residual to classify is small and author-actionable:
   - **Tracked modifications** (a passing test regenerated a golden file or updated a snapshot) → **commit** them: `git add -A && git commit -m "chore(build): commit test-regenerated artifacts before gate"`. This is normal output — committed, not flagged.
   - **Non-ignored new untracked files** → classify each: a legitimately-generated file that belongs in the repo (a golden/fixture) → **commit** it (fold into the same commit); an incidental artifact that should never be tracked (coverage output, a cache) → **gitignore** it (a test-hygiene fix) so it stops appearing.
   - There is **NO bare "assert-clean" branch.** An assert-clean would spuriously halt a *healthy* build whenever a passing test regenerates a golden file, and untracked test residue would make the review gate REFUSE inside a healthy build. build must **produce** the clean tree, not merely check for one.
   - A tree that is **still** dirty or untracked *after* the commit/gitignore step is a **surfaced build/test defect** — surface it (error out) and stop; do NOT silently sweep it into the gate's first commit. End state: `git status --porcelain` empty (tracked **and** untracked), identical to the review gate's entry precondition.
3. **REQUIRED REVIEW AND SUPPLY-CHAIN SIGNALS:** Use crucible:warden on the full implementation and dispatch `crucible:quality-gate` **dependency-audit mode** (`dependency-audit.md`, `scope_root` = project root) in parallel. They consume the same code artifact but not each other's findings. Pass warden `reviewer-set: full`, `Phase: code`, `PipelineID: <current PipelineID>`, and the ledger's `RequiredModelAssurance`; warden runs temper + delve + red-team[quality-gate leg] + siege[conditional] + inquisitor[unconditional in full], drives and commits its fixes, and emits the aggregate review marker. The dependency-audit mode writes its separate `audit-results.md` signal; it does not enter the red-team loop and is not part of warden's weighted score. Await both. On either warden `BLOCKED` or audit `Result: BLOCKED`, halt Phase 4 (fail-closed); surface audit FINDINGS/INCONCLUSIVE/FAILED separately, never as a clean audit. Do NOT separately invoke other reviewer legs or another full quality-gate; warden remains the sole code-review gate-driver (I-W4).
6b. **Verify warden's aggregate verdict marker and integrate the independent dependency-audit result before writing Phase 4 PASS** to the gate ledger (see Verdict Marker Verification in `references/gate-ledger.md`). The marker to verify is now **warden's** build-`PipelineID` aggregate verdict marker — warden owns it (it is no longer a temper or quality-gate marker). The READ mechanism (marker present + `Verdict: PASS` + PipelineID match) is unchanged apart from rejecting an explicit `MarkerFinality: chunk-milestone` (absent reads as final, so warden's marker needs no new finality field; its advisory `QGLegModelAssurance`/`QGLegProofTuple` fields are the Phase 4 source for the QG-leg tuple and are never required for PASS); only the marker's owner/name changed. Delete the verdict marker after writing the ledger entry.
7. **RECOMMENDED SUB-SKILL:** Use crucible:getting-started (`forge.md`, retrospective mode) — capture what happened vs what was planned
7.5. **Chronicle signal fallback:** If forge retrospective was skipped (user declined, session ending),
   append a minimal chronicle signal directly:
   - Read the metrics log at `/tmp/crucible-metrics-<session-id>.log` for duration and subagent counts
   - Construct signal: `v=1`, `ts=now`, `skill="build"`, `outcome` from acceptance test results,
     `duration_m` from metrics log, `branch` from git, `files_touched` from `git diff <base-sha>..HEAD --name-only`,
     `metrics={mode, tasks count, tasks_passed count from task list, stagnation=false}`
   - Append as a single JSON line to `~/.claude/projects/<hash>/memory/chronicle/signals.jsonl`
   - If forge retrospective DID run, skip this step (forge Step 8.5 already emitted the signal)
8. **RECOMMENDED SUB-SKILL:** Use crucible:recon (persistent-map mode) (record mode) — persist any new codebase knowledge discovered during build
9. Compile summary: what was built, acceptance tests passing, review findings addressed, inquisitor findings, concerns
10. Report to user
10.5. **Session index event:** Emit a `skill_end` event to the outbox: `{"ts":"<now>","seq":0,"type":"skill_end","summary":"/build complete: <outcome summary>","detail":{"skill":"build","outcome":"success|failure|escalated"}}`.
11. **REQUIRED SUB-SKILL:** Use crucible:finish — **skip finish's warden call** (warden already ran in build Phase 4 at step 3 — this is the structural double-temper kill), **AND skip finish's Step 2.5 (verify test-alignment audit)** since the audit ran per-task in Phase 3. Tell finish to skip both.
12. **Delete pipeline-active marker:** Remove `<build-scratch>/.pipeline-active`. This signals that the pipeline completed successfully. If deletion fails (permissions, missing file), log a warning but do not fail the pipeline.

### Session Metrics

Throughout the pipeline, the orchestrator appends timestamped entries to `/tmp/crucible-metrics-<session-id>.log` on each subagent dispatch and completion.

**Dispatch measurement protocol:** On every subagent dispatch, the orchestrator follows the enriched manifest protocol from `shared/dispatch-convention.md`:
- **Before dispatching:** Measure the dispatch file size in characters. Record `input_chars` and `model_tier` in the manifest entry.
- **After dispatch returns:** Measure the subagent response length in characters. Record `output_chars` and `tool_calls` (if available) in the manifest completion entry.

At completion (before reporting to user, i.e. step 9), read the metrics log and manifest, then compute:

```
-- Pipeline Complete ----------------------------------------
  Subagents dispatched:  23 (14 Opus, 7 Sonnet, 2 Haiku)
  Active work time:      2h 47m
  Wall clock time:       11h 13m
  Quality gate rounds:   4 (design: 2, plan: 1, impl: 1)
  Siege:                 dispatched (3 agents, 2 rounds, 0 Critical, 0 High) | skipped (0 signals) | skipped (1 signal: auth)
  Task tiers:           3 Tier 1, 3 Tier 2, 2 Tier 3
  Subagent savings:     ~21 dispatches skipped vs all-Tier-3
  Est. input tokens:    ~32,100 (128,400 chars)
  Est. output tokens:   ~20,500 (82,000 chars)
  Token estimate note:  Based on dispatch file sizes (chars/4). Actual consumption may vary +/-30%.
-------------------------------------------------------------
```

**Metrics tracked:**
- Total subagents dispatched (by type and model tier: Opus/Sonnet/Haiku)
- Active work time (merge overlapping parallel intervals — NOT naive sum)
- Wall clock time (first dispatch to final completion)
- Quality gate rounds (per gate: design, plan, implementation)
- Siege status (dispatched with agent count, rounds, and final severity counts — or skipped with signal count and reason)
- Estimated input tokens (sum of `input_chars` from manifest / 4)
- Estimated output tokens (sum of `output_chars` from manifest / 4)

**Efficiency summary computation:** Read `manifest.jsonl` from the dispatch directory. Sum `input_chars` and `output_chars` across all completed entries (skip nulls). Divide each by 4 for token estimates. Count comparable dispatches grouped by `model_profile`; report raw `model_tier` separately when useful. Include these in the pipeline completion report alongside existing metrics.

**Gate tracking verification:** Before compiling the pipeline summary (Phase 4 Step 9), verify that all three gate categories (design, plan, implementation) show round count >= 1 with clean final rounds (0 Fatal, 0 Significant). If any gate was skipped with explicit user approval, record it as `USER_SKIP` in the metrics. A zero without user approval indicates a gate was dropped — report this in the summary.

### Pipeline Decision Journal

Alongside the metrics log, maintain a decision journal at `/tmp/crucible-decisions-<session-id>.log`. Append a structured entry for every non-trivial routing decision:

```
[timestamp] DECISION: <type> | choice=<what> | reason=<why> | alternatives=<rejected>
```

Decision types to capture:
- `reviewer-model` — why Opus vs Sonnet for this reviewer
- `review-tier` -- tier assignment read from plan, runtime escalation reason if applicable
- `gate-round` — issue count, severity shifts, progress/stagnation per round
- `escalation` — why the orchestrator escalated to user (and user's decision)
- `task-grouping` — parallelism decisions for wave execution
- `cleanup-removal` — what de-sloppify removed and accept/reject decision

## Escalation Triggers (Any Phase)

**STOP and ask the user when:**
- Architectural concerns in plan or code review
- Review loop stagnation (same or more issues after fixes — any phase)
- Test suite failures not obviously fixable
- Multiple teammates fail on different tasks
- Teammate reports context pressure at 50%+ with significant work remaining
- When escalating for regression or stagnation AND a checkpoint exists for the current phase boundary: include "A checkpoint from [reason] is available. Restore to pre-regression state?" in the escalation message.

**Minor issues:** Log, work around, include in final report.

## What the Lead Should NOT Do

- Implement code (dispatch implementers)
- Read large files (spawn Haiku researcher)
- Debug failing tests (dispatch implementer)
- Make architectural decisions (escalate to user)

## Context Management

- **One task per agent** — always spawn a fresh implementer for each task. Never send a second task to a running agent via SendMessage. Reusing agents accumulates context and causes exhaustion.
- "2-3 per subagent, ~10 files max" refers to **plan design** — group small steps into one task at planning time, not sequential dispatch to a running agent
- Lead stays thin — coordination only
- All important state on disk (plan files, task list)
- Teammates report at 50%+ context usage
- Lead compaction acceptable — task list is source of truth
- **Agent teams unavailable:** If agent teams are not enabled, the lead dispatches tasks sequentially via Agent tool. Task tracking still uses TaskCreate/TaskUpdate. The pipeline is slower but functionally identical.

## Prompt Templates

- `./acceptance-test-writer-prompt.md` — Phase 1 acceptance test generation
- `./plan-writer-prompt.md` — Phase 2 plan writer dispatch
- `./plan-reviewer-prompt.md` — Phase 2 plan reviewer dispatch
- `./build-implementer-prompt.md` — Phase 3 implementer dispatch
- `./build-reviewer-prompt.md` — Phase 3 reviewer dispatch
- `./cleanup-prompt.md` — Phase 3 de-sloppify cleanup dispatch
- `./test-gap-writer-prompt.md` — Phase 3 test gap writer dispatch
- `./architecture-reviewer-prompt.md` — Mid-plan checkpoint
- `./contract-test-writer-prompt.md` — Phase 1 refactor-mode contract test generation
- `./refactor-implementer-addendum.md` — Phase 3 refactor-mode implementer addendum (appended to build-implementer-prompt)
- `./migration-analyzer-prompt.md` — Migration mode Phase 1 migration target analysis
- `./blast-radius-mapper-prompt.md` — Migration mode Phase 2 consumer and dependency mapping
- `./phase-planner-prompt.md` — Migration mode Phase 3 phase decomposition
- `./compatibility-designer-prompt.md` — Migration mode Phase 4 shim/adapter design
- `./wave-grouper-prompt.md` — Migration mode Phase 5 consumer wave assignment

Red-team, design innovation, and inquisitor prompts live in their respective skills:
- `crucible:quality-gate (red-team mode)` — `skills/quality-gate/red-team-prompt.md`
- `crucible:design` innovation pass — `skills/design/innovation-prompt.md`
- `crucible:inquisitor` per-task mode — `skills/inquisitor/break-it-prompt.md`
- `crucible:inquisitor` full-feature mode — `skills/inquisitor/inquisitor-prompt.md`

## Quality Gate Orchestration

Build is the outermost orchestrator. The **design and plan** gates route via `crucible:quality-gate`; the **code** gate routes via `crucible:warden` (which drives the quality-gate red-team leg exactly once). Do NOT invoke red-team (or temper/inquisitor/siege) separately at these points.

**Gate points in the pipeline:**

| Pipeline Stage | Artifact Type | Replaces |
|---------------|---------------|----------|
| Phase 1, Step 2 (after design) | design | Existing `crucible:quality-gate` on design (preserved red-team review) |
| Phase 2, Step 3 (after plan review) | plan | Existing `crucible:quality-gate` on plan (preserved red-team review) |
| Phase 4 (single warden gate) | code | `crucible:warden` — runs the red-team leg (+ temper/delve/inquisitor/siege) |

For the **code leg**, code review (`crucible:temper`), inquisitor (`crucible:inquisitor`), and the quality-gate red-team leg are now consolidated inside `crucible:warden` — temper does structured quality checks, inquisitor writes cross-component adversarial tests, and the red-team leg does adversarial artifact review (plus delve and a conditional siege run). The three purposes still stand, but warden drives them as one disjunction-of-native-gates rather than as separate steps.

### Contract-Aware Quality Gate

When a contract YAML exists for the current ticket, the quality gate adds contract verification to its checks. This applies at all gate points (design, plan, and code), though most contract checks are only meaningful at the code gate (Phase 4, Step 6).

1. **Version check:** Before processing a contract, verify the `version` field is `"1.0"`. If the version is missing or unrecognized, reject the contract with a clear error: "Contract version [X] is not supported. Expected version 1.0." Do not proceed with contract-aware checks — fall back to standard quality gate behavior without contract awareness.

2. **Checkable invariant verification:** For each `checkable` invariant in the contract, verify satisfaction using the declared `check_method`:
   - `grep` — pattern match (or absence) in production code. Run the grep and confirm the result matches the invariant's `verification` description.
   - `code-inspection` — read and reason about the relevant code to confirm the invariant holds (e.g., idempotency, no side effects).
   - `file-structure` — check that file existence, location, or organization matches the constraint.

3. **Testable invariant verification:** For each `testable` invariant in the contract:
   - Verify that a test tagged with the declared `test_tag` (pattern: `contract:<category>:<id>`) exists in the test suite.
   - Verify that the tagged test passes when run.
   - A missing or failing tagged test is a contract violation.

4. **Contract violations are blocking issues.** Contract violations are NOT warnings — they have the same severity as architectural concerns and must be resolved before the gate passes. The quality gate's iterative fix loop applies: dispatch fixes, re-check, track progress/stagnation as normal.

## Red Flags

- Skipping Compression State Block emission at checkpoint boundaries
- Emitting a Compression State Block at a phase boundary (1→2, 2→3, 3→4) instead of writing a handoff manifest
- Skipping the shed statement after a manifest write
- Emitting a Compression State Block with stale or missing Key Decisions (decisions must be cumulative across all prior blocks)
- Allowing the Goal field to drift across successive Compression State Blocks (must match original user request)
- Exceeding 10 entries in the Key Decisions list without overflow-compressing the oldest
- Skipping a REQUIRED quality gate because the task seems "small", "simple", or "trivial"
- Self-assessing that a quality gate is unnecessary based on perceived task complexity
- Rationalizing that quality-gate findings would be "minor" as justification to skip
- Declaring a quality gate "done" after fixing findings without a clean verification round (fixing is not passing)
- Short-circuiting the quality-gate iteration loop by assuming fixes are self-evidently correct
- Interpreting general user feedback as approval to skip a quality gate that has not yet run — once a gate has run and presented findings to the user, the user's decision to proceed is authoritative. Pre-gate skip approval must be an unambiguous instruction specifically referencing the gate.
- Treating session index summary as authoritative over CSB state (session index is supplementary narrative, CSB is authoritative state)

## Integration

**Required sub-skills:**
- **crucible:design** — Phase 1
- **crucible:finish** — Phase 4
- **crucible:quality-gate** — Iterative red-teaming at each quality gate point
- **crucible:quality-gate (red-team mode)** — Adversarial review engine (invoked by quality-gate)
- **crucible:design** innovation pass — Creative enhancement before quality gates
- **crucible:inquisitor** — Per-task adversarial testing (Phase 3) and full-feature cross-component testing (Phase 4, inside the warden gate)
- **crucible:warden** — Consolidated pre-push code-review gate (Phase 4): temper + delve + quality-gate red-team leg + conditional siege + inquisitor as one disjunction-of-native-gates.

**Recommended sub-skills:**
- **crucible:getting-started** (`forge.md`) — Feed-forward at Phase 1 start, retrospective at Phase 4 completion
- **crucible:recon (persistent-map mode)** — Consult at Phase 1 start, load at Phase 3 dispatches, record at Phase 4
- **crucible:checkpoint** — Shadow git checkpoints at pipeline boundaries (pre-design-gate, pre-plan-gate, pre-wave-N, pre-cleanup-task-N)

**Recon/approach-evaluation context:** Inherits recon/approach-evaluation context through /design (Phase 1). No direct dispatch. When design integrates recon, build benefits automatically. See #147 for rationale.

**Phase 3 sub-skills (dispatched per-task):**
- **crucible:verify** — Test-alignment mode audits existing tests after each task's test quality review (staleness, dead tests, coincidence tests)

**Implementer sub-skills:**
- **crucible:test-driven-development** — TDD within each task
- **crucible:source-driven-development** — Detect → Fetch → Implement → Cite loop for non-trivial external API usage (≥ 5 LOC touching a detected framework); invoked by the implementer prompt's Source Consultation block. Recommended — skipped for pure internal refactors or trivial edits.

**Contract consumption:**
- **crucible:spec** — Consumes contract YAML files produced by `/spec` (schema version 1.0). Contracts are read from `docs/plans/*-contract.yaml` and feed into pre-existing doc detection (Phase 1 Step 0), implementer dispatch (Phase 3), reviewer checks (Phase 3), and quality gate verification (all gate points). See [`crucible:spec/contract-schema.md`](../spec/contract-schema.md) for field definitions.
