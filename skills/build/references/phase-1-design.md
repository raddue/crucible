# Build — Phase 1: Design

## Contents

- [Phase 1: Design (Interactive)](#phase-1-design-interactive)
  - [Step -1: Resume Detection and Pipeline-Active Marker](#step--1-resume-detection-and-pipeline-active-marker)
  - [Step 0: Pre-Existing Doc Detection](#step-0-pre-existing-doc-detection)
  - [Step 2: Innovate and Red-Team the Design](#step-2-innovate-and-red-team-the-design)
  - [Step 3: Generate Acceptance Tests (RED)](#step-3-generate-acceptance-tests-red)
  - [Refactor Mode: Phase 1 Changes](#refactor-mode-phase-1-changes)
  - [Phase Handoff: 1 → 2](#phase-handoff-1--2)

## Phase 1: Design (Interactive)

### Step -1: Resume Detection and Pipeline-Active Marker

Before any design or dispatch work, derive `<build-scratch>` as `~/.claude/projects/<project-hash>/memory/builds/<worktree-key>/`, where `<worktree-key>` is the full hex digest output by `printf '%s' "$(git rev-parse --show-toplevel)" | sha256sum | cut -d' ' -f1`. Store this build's recovery files under `<build-scratch>`: `.pipeline-active`, `build-gate-ledger.md`, `pipeline-status.md`, `build-mode.md`, and phase handoff manifests. The worktree path, not branch, defines identity.

**First-run handling for legacy shared state:** If `<build-scratch>` has no state yet, inspect the old shared files at `~/.claude/projects/<project-hash>/memory/{.pipeline-active,build-gate-ledger.md,pipeline-status.md}`. If any exist, tell the user which exist and offer (a) copy existing files into `<build-scratch>` and continue normal recovery, or (b) start fresh in `<build-scratch>`. Never silently ignore or auto-adopt the old state. Adoption copies only files that exist and does not overwrite namespaced files; preserve the originals in place. Before adopting `.pipeline-active`, compare its `worktree_root` with current `git rev-parse --show-toplevel`: if present and different, treat it and the shared state set as foreign; do not adopt any of them, offer only fresh namespaced state, and leave originals untouched. If `worktree_root` is absent, state that ownership cannot be verified and adopt only after explicit user confirmation. Before adopting a present ledger/status with the marker, verify status `Started` matches ledger `Run`; if either is missing or differs, do not adopt the shared state set. Worktree ownership is checked independently using the marker's `worktree_root`. When copying an owned `.pipeline-active`, update only its `scratch_dir` field to `<build-scratch>` and preserve `dispatch_dir` and other fields. Starting fresh leaves all legacy files untouched. This is a one-time decision: once namespaced state exists, do not consult or mutate the shared legacy paths again.

1. **Check `<build-scratch>/.pipeline-active`**
2. **Not found:** If adopting legacy state, run the resume checks on the adopted files before proceeding. Otherwise create new ledger and status under `<build-scratch>` and never read or write legacy singleton paths again. Write the pipeline-active marker (JSON with `pipeline_id` set to current session ID, `skill` set to `"build"`, `phase` set to `"1"`, `start_time` set to current ISO-8601 timestamp, `scratch_dir` set to `<build-scratch>`, `dispatch_dir` set to the dispatch directory path, `branch` from `git branch --show-current`, `worktree_root` from `git rev-parse --show-toplevel`, `baseline_sha` from `git rev-parse HEAD`). Proceed to Step 0.
3. **Found, same `pipeline_id` as current session:** This is a compaction recovery scenario. Follow existing compaction recovery procedures. Do not re-write the marker.
4. **Found, different `pipeline_id`:**
   a. **Branch guard:** Compare marker's `branch` field against current `git branch --show-current`. If they differ, warn: *"Previous build on branch [marker.branch] crashed at Phase [phase]. You are currently on [current-branch]. Switch to [marker.branch] before resuming? [switch+resume / start fresh / abort]"*. Do NOT offer resume on the wrong branch.
   b. Read `manifest.jsonl` from the marker's `dispatch_dir`; if `/tmp` was lost, read the durable copy at `<build-scratch>/crucible-dispatch-<marker.pipeline_id>/manifest.jsonl` (the same session-scoped copy used by the dispatch convention).
   c. Identify the last successful phase boundary by scanning manifest entries grouped by phase. A phase boundary is verified when all dispatches in that phase have `status: "completed"`.
   d. Present resume option to the user:
      > "Previous build on branch [marker.branch] crashed at Phase [N], [context]. Resume from [last good boundary] ([checkpoint reason], [estimated time preserved] of work preserved)? [yes / no / fresh]"
   e. **User accepts:** Invoke `crucible:replay` in resume mode, passing the dispatch directory as its positional path — `<marker.dispatch_dir>`, or `<build-scratch>/crucible-dispatch-<marker.pipeline_id>/` when `/tmp` was lost — and provide `<build-scratch>` as the build state path. The replay skill handles checkpoint restore, state reconstruction, and re-dispatch. The build pipeline does not continue -- replay takes over.
   f. **User declines (fresh):** Delete only `<build-scratch>/.pipeline-active`. Write a fresh marker with the current session. Proceed to Step 0 as a new pipeline run.

**Marker updates during pipeline:** Update the `phase` field in `<build-scratch>/.pipeline-active` at each phase boundary (1->2, 2->3, 3->4) to track progress for crash detection.

**Marker cleanup:** Delete `<build-scratch>/.pipeline-active` at Phase 4 step 12 (after finish skill completes).

**Gate Ledger Initialization:** After the pipeline-active marker is written (or recovered) and mode detection is complete, run the Gate Ledger Initialization and Verdict Marker Isolation steps. The ledger must exist before Phase 1 transitions to IN_PROGRESS.

**Compass Arc Emit (build orchestrator only — D14):**
<!-- CANONICAL: shared/compass-protocol.md -->

After Gate Ledger Initialization completes AND the resume decision at Step -1 has resolved, emit the current arc to `docs/compass.md` — but ONLY on a fresh-start or fresh-restart path. Skip this emit if the user accepted the resume path (Step -1e: replay took over), because the prior arc's `current_arc` is already correct. Do NOT place this emit inside crash-recovery branches (Step -1, items 3 or 4e), as those fire mid-resume-detection and can clobber `current_arc` before replay restores the prior arc.

`RESUME_DECISION` is set by Step -1 to one of `fresh` / `resume` / `fresh-restart`. Default `fresh` if unset.

```bash
if [ "${RESUME_DECISION:-fresh}" != "resume" ]; then
  python scripts/compass.py update --field current_arc --value "#<ticket>: <user-goal-one-liner>" \
    || echo '[compass] emit failed at arc start; continuing build' >&2
fi
```

Replace `<ticket>` with the GitHub issue number (e.g. `273`) and `<user-goal-one-liner>` with a short, precise description of the task at hand (e.g. `Compass arc-state skill`). The leading `#` is required — `compass update` raises `ValueError` on values missing the `#NNN:` prefix.

**Error policy (best-effort):** Compass is an optimization, not a correctness layer. A failed emit MUST NOT fail the build pipeline — log to stderr and continue. Never tighten this error handling.

**D14 invariant:** Sub-agents spawned inside build do NOT emit compass updates. This emit fires from the build orchestrator only, exactly once per fresh pipeline start.

### Step 0: Pre-Existing Doc Detection

Before running interactive design, check whether `/spec` (or a prior `/build` run) already produced design artifacts for this ticket.

1. **Scan for pre-existing spec docs:** Search `docs/plans/` for design docs (`*-design.md`) with a matching `ticket` field in YAML frontmatter. Also check for corresponding `*-implementation-plan.md` and `*-contract.yaml` files with the same ticket field.

2. **Conflict detection:** If multiple design docs match the same `ticket` field, escalate to user: "Found multiple design docs for ticket #NNN: [list files]. Which should I use?" Do not proceed until the user resolves the conflict.

3. **Full match (design doc + implementation plan + contract all present):**
   - Skip interactive design (the Phase 1 design sub-skill below) — design doc already exists
   - **Security review check:** If the contract contains `security_review` field, note it in the Phase 1→2 handoff manifest under Active Constraints: "Contract requires security review (`security_review.status: [required|recommended]`) — siege will be evaluated in Phase 4 Step 5.5." This ensures the directive survives phase handoffs and compaction recovery.
   - Quality-gate the existing design doc with staleness context: "This design doc is pre-existing from /spec and may be stale — verify against current codebase state before proceeding"
   - **Staleness rejection:** If the quality gate finds that the design doc references files, interfaces, or modules that no longer exist in the codebase, reject the doc as fundamentally stale. Fall back to running Phase 1 interactively. Inform user: "Pre-existing design doc for #NNN is fundamentally stale (references [specific items] that no longer exist). Running interactive design instead."
   - If quality gate passes: Run Phase 2 on the pre-existing implementation plan — skip Plan Writer (plan already exists), but run Plan Reviewer + design's innovation pass + quality-gate on the existing plan. This ensures the plan gets the same review rigor as a freshly written plan.
   - If quality gate fails (non-staleness issues): fix or escalate
   - Proceed to Phase 3 when the plan passes review

4. **Partial match (design doc present but implementation plan or contract missing):**
   - Use the existing design doc (quality-gate it as above, including staleness rejection)
   - Run the missing phases normally: if no implementation plan, run Plan Writer in Phase 2; if no contract, proceed without contract awareness for this ticket
   - Inform user which artifacts were found and which are being generated fresh: "Found pre-existing design doc for #NNN. Implementation plan is missing — will generate in Phase 2." (or similar)

5. **Not found:** Proceed with normal Phase 1 (interactive design below).

---

- **Model:** Opus (creative/architectural work needs the best model)
- **Mode:** Interactive with the user
- **RECOMMENDED SUB-SKILL:** Use crucible:getting-started (`forge.md`, feed-forward mode) — consult past lessons before starting
- **RECOMMENDED SUB-SKILL:** Use crucible:cartographer-skill (consult mode) — review codebase map for structural awareness
- **REQUIRED SUB-SKILL:** Use crucible:design
- Follow design skill for design refinement, section-by-section validation, and saving the design doc
- **OVERRIDE:** When design completes and the design doc is saved, do NOT follow design's "Implementation" section (do not chain into planning or worktree from there). Return control to this build skill — Phase 2 handles planning with its own subagent-based approach.
- Phase ends when user approves the design (says "go", "looks good", "proceed", etc.)
- **Everything after this point is autonomous** — tell the user: "Design approved. Starting autonomous pipeline — I'll only interrupt for escalations."

> **Eval-gate pointer (Mock Dispatch Mode):** when `CRUCIBLE_BUILD_EVAL_MOCK_DIR` is set, all `Use crucible:<skill>` and `Dispatch a <kind> subagent` invocations in Phase 1 (design, design's innovation pass, quality-gate, acceptance test writer, contract test writer) substitute a disk-read from the mock dir for the Task tool invocation. Each substitution follows the substitution rule in the `## Mock Dispatch Mode (eval-gate)` section. AskUserQuestion calls in Phase 1 use `CRUCIBLE_BUILD_EVAL_USER_INPUT_DIR` per that same section.

### Step 2: Innovate and Red-Team the Design

After the user approves the design and before starting Phase 2:

**RECOMMENDED SUB-SKILL:** Use crucible:checkpoint — create checkpoint with reason "pre-design-gate" before dispatching design's innovation pass and quality-gate on the design doc.

1. **Innovation:** Dispatch `crucible:design` in innovation-pass mode (`design/innovation.md`) on the design doc. Plan Writer incorporates the proposal. If it changes the API Surface, Invariants, or integration points, re-extract the contract from the revised design and obtain user approval of the changed contract before the quality gate and handoff.
2. **Write Phase 1 IN_PROGRESS** to the gate ledger (after ledger initialization).
3. **REQUIRED SUB-SKILL:** Use crucible:quality-gate on the (potentially updated) design doc with artifact type "design" and explicit `mode: standard` (unless caller explicitly requests `full`). Include in the dispatch context: `Phase: design`, `PipelineID: <current PipelineID>`, and the immutable mode. Persist selected QG mode in the phase handoff/cairn state and reuse it on retries, compaction recovery, and resume; never infer or downgrade it. Iterate until clean or stagnation. **(Non-negotiable — see Quality Gate Requirement.)**
4. If the quality gate requires changes, the Plan Writer updates the design doc and re-commits.
5. **Verify verdict marker and write Phase 1 PASS** to the gate ledger (see Verdict Marker Verification). Delete the verdict marker after writing the ledger entry.
6. Design doc is now finalized — proceed to acceptance tests.

### Step 3: Generate Acceptance Tests (RED)

Before planning, define "done" with executable tests:

1. Dispatch an **Acceptance Test Writer** subagent (Opus) using `./acceptance-test-writer-prompt.md`
   - Input: finalized design doc (especially acceptance criteria)
   - Output: integration-level test file(s) that verify feature behavior end-to-end
2. Run the acceptance tests — verify they **FAIL** (the feature doesn't exist yet)
   - If tests pass: something is wrong — investigate before proceeding
   - If tests error (won't compile): this is expected in typed languages — note which tests exist and what they verify. They become the first implementation task.
3. Commit: `test: add acceptance tests for [feature] (RED)`

These tests define the feature-level RED-GREEN cycle that wraps the entire pipeline. The pipeline is done when these tests pass.

### Refactor Mode: Phase 1 Changes

When in refactor mode, Phase 1 shifts from "what should we build?" to "what are we changing and what could break?"

#### Blast Radius Analysis

After the user describes the refactoring intent, the design phase:

1. **Identify the target** — What code is being restructured? (module, interface, data representation, file organization, etc.)
2. **Trace the blast radius** using cartographer (if available) or fallback exploration:
   - **Direct consumers** — code that imports/calls/references the target
   - **Indirect dependents** — code that depends on consumers (transitive)
   - **Test coverage** — which tests exercise the target behavior
   - **Configuration/wiring** — DI registrations, config files, build scripts that reference the target
   - **Fallback when cartographer is unavailable:** Use language-aware symbol search via agent exploration. Grep for symbol references (imports, type annotations, function calls) using language-specific patterns. The impact manifest's confidence field reflects reduced precision.
3. **Present an impact manifest** to the user:

```
### Impact Manifest

**Target:** [what's being restructured]
**Structural goal:** [what the code should look like after]

**Direct consumers:** N files
- path/to/consumer1.py (calls TargetClass.method)
- path/to/consumer2.py (imports TargetClass)

**Indirect dependents:** N files
- path/to/dependent.py (depends on consumer1)

**Test coverage:**
- N tests directly exercise target behavior
- N tests exercise consumers
- Gap: no tests cover [specific seam]

**Risk assessment:** [Low/Medium/High] based on consumer count and coverage gaps
**Confidence:** [High/Medium/Low] — High if cartographer used, Medium/Low if fallback
```

**When confidence is Low**, require explicit user confirmation before proceeding. The user must review the impact manifest and confirm the blast radius is complete.

4. **Design the structural goal** — what should the code look like after the refactoring? User validates the target state.

#### Acceptance Tests (Refactor Mode)

Instead of writing NEW acceptance tests (Step 3 above), the pipeline:

1. **Dispatch the contract test writer** using `./contract-test-writer-prompt.md` — a single agent handles gap identification AND gap filling. Input: impact manifest + blast radius file list. The agent maps existing tests to behavioral seams, identifies untested seams, and writes contract tests for each gap.
2. **Run all contract tests GREEN** — contract tests must pass before any refactoring begins.
3. **If a contract test FAILS:** The contract test writer investigates:
   - **Test defect** (wrong assertion, bad setup) — fix the test and re-run
   - **Latent codebase bug** — report to user with options: (a) fix the bug first, (b) exclude this seam and accept the risk, (c) abort the refactoring. Never silently drop a failing contract test.
4. **Commit:** `test: add contract tests for [target] refactoring (GREEN — locking existing behavior)`

#### Proportionality Escape Valve

Contract test writing must remain proportional to the refactoring scope. Trigger a scope check when **any** of these thresholds are hit:

- **Count threshold:** More than 15 contract tests needed
- **Effort threshold:** Contract test writer reports context pressure, or estimated total contract test LOC exceeds ~2x the estimated refactoring scope LOC

When triggered:
1. Present the full gap list to the user with estimated effort per gap
2. User selects which gaps to fill and which to accept as uncovered risk
3. Proceed with only user-selected contract tests

The impact manifest records which gaps the user chose to leave uncovered.

### Phase Handoff: 1 → 2

Before dispatching the Plan Writer, verify the gate ledger and write a handoff manifest:

0. **Gate ledger check:** Read `<build-scratch>/build-gate-ledger.md` and verify Phase 1 Status is `PASS`. If not, follow Enforcement Rules.
1. Write `<build-scratch>/handoff-1-to-2.md` with:
   - **Goal:** original user request, verbatim
   - **Mode:** feature or refactor
   - **Inputs for Phase 2:** design doc path, acceptance test paths (or contract tests in refactor mode), conventions path (from cartographer, if loaded)
   - **Decisions Carried Forward:** accumulated decisions from Phase 1
   - **Active Constraints:** constraints affecting planning
   - **Shed Receipt:** design iteration history, innovation proposals, quality gate round details → design doc on disk captures the outcome
2. Emit shed statement: "Phase 1 context shed. Design doc and acceptance tests are on disk. Design iteration history, innovation proposals, and gate round details are not carried forward."
3. Update `## Compression State` in `<build-scratch>/pipeline-status.md` with manifest contents.
4. Do NOT emit a Compression State Block (manifest replaces it at this boundary).
5. **Session index event:** Emit a `phase_change` event to the outbox: `{"ts":"<now>","seq":0,"type":"phase_change","summary":"Build: Phase 1 -> Phase 2 (Plan)","detail":{"skill":"build","from":"1","to":"2"}}`.
