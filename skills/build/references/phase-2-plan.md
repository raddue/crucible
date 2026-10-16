# Build — Phase 2: Plan

## Contents

- [Phase 2: Plan (Autonomous)](#phase-2-plan-autonomous)
  - [Step 1: Write the Plan](#step-1-write-the-plan)
  - [Step 2: Review the Plan](#step-2-review-the-plan)
  - [Step 3: Innovate and Red-Team the Plan](#step-3-innovate-and-red-team-the-plan)
  - [Phase Handoff: 2 → 3](#phase-handoff-2--3)

## Phase 2: Plan (Autonomous)

> **Eval-gate pointer (Mock Dispatch Mode):** when `CRUCIBLE_BUILD_EVAL_MOCK_DIR` is set, the Plan Writer, Plan Reviewer, design innovation pass, and quality-gate dispatches in this phase use the mock-dir substitution rule defined in the `## Mock Dispatch Mode (eval-gate)` section. The substitution does not change Phase 2's structure or the gate-ledger writes.

### Step 1: Write the Plan

Dispatch a **Plan Writer** subagent (Opus):

- Read the design doc produced in Phase 1 and the acceptance tests from Step 3
- Write an implementation plan following the `crucible:planning` format
- If acceptance tests couldn't compile (typed language), Task 1 should create the interfaces/stubs needed for them to compile and fail correctly
- Include per-task metadata: Files (with count), Complexity (Low/Medium/High), Dependencies
- Save to `docs/plans/YYYY-MM-DD-<topic>-implementation-plan.md`
- Plan tasks should be scoped to 2-3 per subagent, ~10 files max (context budget awareness)

Use `./plan-writer-prompt.md` template for the dispatch prompt.

### Step 2: Review the Plan

Dispatch a **Plan Reviewer** subagent:

Reviewer model selection:
- Plan touches **4+ systems** or has **10+ tasks** → Opus
- Plan touches **1-3 systems** with **<10 tasks** → Sonnet
- When in doubt → Opus

Review protocol (iterative):
- Dispatch Plan Reviewer to check plan against design doc
- If issues found: record issue count, dispatch Plan Writer to revise
- Dispatch NEW fresh Plan Reviewer on revised plan (no anchoring)
- Compare issue count to prior round:
  - Strictly fewer issues → progress, loop again
  - Same or more issues → stagnation, **escalate to user** with findings from both rounds
- Loop until plan passes with no issues
- **Architectural concerns bypass the loop** — immediate escalation regardless of round

Use `./plan-reviewer-prompt.md` template for the dispatch prompt.

### Step 3: Innovate and Red-Team the Plan

**After the plan passes review:**

**RECOMMENDED SUB-SKILL:** Use crucible:checkpoint — create checkpoint with reason "pre-plan-gate" before dispatching design's innovation pass and quality-gate on the plan.

1. **Write Phase 2 IN_PROGRESS** to the gate ledger.
2. **Innovation:** Run `crucible:design` in innovation-pass mode (`design/innovation.md`) on the approved plan. Plan Writer incorporates the proposal into the plan.
3. **REQUIRED SUB-SKILL:** Use crucible:quality-gate on the (potentially updated) plan with artifact type "plan" and explicit `mode: standard` (unless caller explicitly requests `full`). Include in the dispatch context: `Phase: plan`, `PipelineID: <current PipelineID>`, and the immutable mode. Persist selected QG mode in the phase handoff/cairn state and reuse it on retries, compaction recovery, and resume; never infer or downgrade it. Provides the plan and design doc as context. **(Non-negotiable — see Quality Gate Requirement.)**
4. **Verify verdict marker and write Phase 2 PASS** to the gate ledger (see Verdict Marker Verification). Delete the verdict marker after writing the ledger entry.

The quality gate handles the iterative red-team loop — fresh review each round, weighted stagnation detection, 15-round safety limit, escalation. See `crucible:quality-gate` for details.

### Phase Handoff: 2 → 3

Before creating the team and task list, write a handoff manifest. Step 3.4 above already verified the verdict marker, wrote PASS to the ledger, and deleted the marker. The handoff manifest is written AFTER the ledger PASS — this sequencing ensures compaction recovery finds a consistent state (ledger shows PASS, handoff exists).

Write a handoff manifest:

1. Write `<build-scratch>/handoff-2-to-3.md` with:
   - **Goal:** original user request, verbatim
   - **Mode:** feature or refactor
   - **Inputs for Phase 3:** plan path, design doc path, acceptance test paths (or contract tests), contract YAML path (if exists), baseline SHA (current HEAD), cartographer context paths (module files, conventions.md, landmines.md)
   - **Decisions Carried Forward:** accumulated decisions from Phases 1-2
   - **Active Constraints:** constraints affecting execution
   - **Shed Receipt:** plan review iterations, innovation proposals, quality gate round history → plan on disk captures the outcome
2. Emit shed statement: "Phase 2 context shed. Plan, design doc, and acceptance tests are on disk. Plan review rounds, innovation proposals, and gate details are not carried forward."
3. Update `## Compression State` in `<build-scratch>/pipeline-status.md` with manifest contents.
4. Do NOT emit a Compression State Block.
5. **Session index event:** Emit a `phase_change` event to the outbox: `{"ts":"<now>","seq":0,"type":"phase_change","summary":"Build: Phase 2 -> Phase 3 (Execute)","detail":{"skill":"build","from":"2","to":"3"}}`.
