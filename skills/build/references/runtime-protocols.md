# Build — Runtime Protocols

## Contents

- [Mock Dispatch Mode (eval-gate)](#mock-dispatch-mode-eval-gate)
- [Cairn (Layer 3)](#cairn-layer-3)
- [Tripwire Manifest Sweep (Layer 2)](#tripwire-manifest-sweep-layer-2)

## Mock Dispatch Mode (eval-gate)

This mode exists for the private `raddue/crucible-eval` `skills/build/evals/` eval-gate harness. It is enabled **iff** `CRUCIBLE_BUILD_EVAL_MOCK_DIR` is set in the environment. Production runs MUST leave this variable unset, in which case this mode is a no-op and the orchestrator behaves exactly as if this section were not present.

**Env-var contract.** Three variables, all consumed only when `CRUCIBLE_BUILD_EVAL_MOCK_DIR` is set:

- `CRUCIBLE_BUILD_EVAL_MOCK_DIR=<path>` — directory of canned subagent return receipts. Filenames follow `<seq>-<template-name>.md` with fallback `<template-name>.md` (e.g. `1-plan-writer.md`, then `plan-writer.md`). Missing mock → halt immediately with a clear error; no silent fallthrough.
- `CRUCIBLE_BUILD_EVAL_MODE=feature|refactor` — pre-set answer to the Mode Detection prompt. When present, the orchestrator skips the AskUserQuestion call in Mode Detection and uses this value.
- `CRUCIBLE_BUILD_EVAL_USER_INPUT_DIR=<path>` — directory of canned user-input turns, named `turn-<N>.md`. Each AskUserQuestion call (other than Mode Detection, which uses `CRUCIBLE_BUILD_EVAL_MODE`) consumes the next sequential turn. If the next turn-file is missing, halt before proceeding — this is the b4 fixture's design: build correctly stops when it needs input it does not have.

**Substitution rule (defined ONCE here; referenced from intercept sites below):** at every dispatch site, the dispatch file is STILL written to the normal dispatch dir (trace integrity preserved). Only the Task/Agent tool invocation is replaced — instead of invoking the tool, read `$CRUCIBLE_BUILD_EVAL_MOCK_DIR/<seq>-<template-name>.md` (or `<template-name>.md`) and treat its contents as the subagent's return receipt. Apply the normal receipt linter and manifest sweep as if the receipt had come from a live agent.

**Boundary behavior.** `MockNotFound` / `MockUserInputMissing` errors raised by the mock loader halt the build run with a clear stderr message. They do not silently fall through. The eval-gate harness detects these halts via on-disk artifacts (absent phase-handoff manifests, pipeline-active marker still at the original phase) — the harness does NOT catch these exceptions across the build-runtime boundary.

**Pointer reminders.** Sections that reference these env vars (Mode Detection, Phase 1 Step 2 / 3, Phase 2 Step 1 / 2, Phase 3 Step 3) contain short inline pointers back to this section. The substitution rule is defined here only; the pointers exist so a reader scanning a dispatch site doesn't need to re-derive the contract.

**See also:** `raddue/crucible-eval/skills/build/evals/README.md` for harness usage; `skills/shared/dispatch-convention.md` for the dispatch-file protocol the substitution rule preserves.

## Cairn (Layer 3)

The orchestrator maintains an Invariant Cairn per `shared/cairn-convention.md`. Build-specific bindings:

- **Phase mapping.** The build pipeline's four phases (1 Design, 2 Plan, 3 Execute, 4 Completion) map 1:1 to cairn phases. Mid-phase sub-stages (e.g. Phase 3 Wave N, Phase 4 gate rounds) do NOT get their own cairn phase counter — they are internal to the owning phase and contribute a single LEDGER line when the owning phase completes.
- **Phase transitions.** At every 1→2, 2→3, 3→4 transition, the orchestrator: (a) writes any correctness-critical phase-N invariants, (b) appends the phase-N LEDGER line with `dispatches=/receipts=/verdict=`, (c) single atomic Write advancing PHASE to phase N+1. Uses the phase handoff manifest (`<build-scratch>/handoff-N-to-M.md`) as input evidence for the invariants.
- **Terminal phase.** Phase 4 sealing — after finish-skill completes and the pipeline-active marker is deleted. At terminal sealing, delete `active-run.md`; leave `cairn-<run-id>.md` in place.
- **Mandatory-invariant categories for build.** Each phase-exit MUST capture:
  - **Design exit:** the one-sentence architectural commitment, plus any RED-flag constraint surfaced by red-team that later phases must preserve.
  - **Plan exit:** the task list's load-bearing dependencies (e.g. "Task 3 unblocks Tasks 5-7; T2 review tier"); any non-obvious refactoring risk.
  - **Execute exit:** every `noticed-not-touching` entry that is correctness-critical for a future task or for post-merge review; every test-gap finding that the run chose to leave uncovered.
  - **Completion exit:** acceptance-test outcome; siege dispatch decision + outcome; any skipped gate with `Acknowledged: true`.
- **Reconciliation on phase entry.** Runs the full Reconciliation Pass (5 rules) against `receipt-ledger.jsonl` and the in-context Tripwire Manifest. Rule 1 local-repair is authorized for trailing-receipts-in-current-phase LEDGER under-count only.
- **Composition with Phase Handoff Manifest.** The cairn and the existing Phase Handoff Manifest overlap in intent but not in scope: the handoff manifest is a per-transition snapshot of inputs for the next phase; the cairn is the cumulative load-bearing state across the whole run. Both are maintained; neither replaces the other. On Recovery Protocol invocation, the orchestrator reads the cairn first (authoritative for load-bearing state) then the most recent handoff manifest (authoritative for current-phase inputs).

## Tripwire Manifest Sweep (Layer 2)

Starting with convention **v1.1**, every subagent returns a receipt carrying `TRIPWIRE:`, `SUPERSEDES:`, and (if the subagent dispatched children) `TRIPWIRE-CHILD:` lines. The full grammar and predicate vocabulary live in `shared/return-convention.md`. This section defines how the orchestrator uses them.

**Manifest:** After each Task return (post-lint), append one line to the in-context manifest:

```
<rcpt-sha256-prefix-12>  <skill>/<dispatch-id>  <verdict>  TRIPWIRE: <predicates>  [SUPERSEDED_BY=<prefix>]  [keys=<skill>:<k>:<v>,…]  [files=<path>:<h6>,…]
```

Extract `keys=` and `files=` discriminators at insertion time (severity-max, `*-count` CLAIM keys namespaced by skill; EDIT/WROTE paths with first 6 hex of post-edit hash). Truncate each list at 8; overflow becomes `more=<N>` and forces mandatory fire on `peer-dispatch-disagrees`.

**Sweep (the dispatch-loop clause):** The orchestrator MAY NOT dispatch the next subagent until it has:

1. Applied Layer 1 two-tier linter to the just-returned receipt. Lint failure → re-dispatch, DO NOT sweep.
2. Appended the manifest entry.
3. Processed `SUPERSEDES:` — marked each cited predecessor `SUPERSEDED_BY=<new-prefix>`.
4. Evaluated self-checks (verdict=FAIL, exec-exit!=0, suspicion>=N-self) on the new receipt — no Read needed.
5. Evaluated forward-checks against every active (not `SUPERSEDED_BY=*`) prior manifest entry, over the union of that entry's `TRIPWIRE` and `TRIPWIRE-CHILD` predicate sets:
   - `claims-touch(glob)` / `wrote(glob)` / `read(glob)` — path-glob match against the new receipt's TRACE or CLAIMS citations.
   - `suspicion>=N` — new receipt's SUSPICION ≥ N.
   - `peer-dispatch-disagrees(<dim>)` — same-skill, same-target, discriminator mismatch (evaluated via manifest `keys=`/`files=`; `more=` overflow → mandatory fire).
   - `always` — fires unconditionally.
6. For each firing predicate on manifest entry M, `Read` M's full receipt from disk and narrate the re-read: *"tripwire `<predicate>` on <M-prefix> fired from <new-prefix>; re-read M."*
7. Only then dispatch the next subagent.

<!-- CANONICAL: shared/return-convention.md -->
**Supersession fix-flow.** A fix-agent dispatched after a FAIL receipt normally supersedes that FAIL. Its receipt MUST cite the FAIL's hash-prefix in `SUPERSEDES:` and in at least one CLAIM `from=<prefix>#…`, AND its WITNESS must be `kind ∈ {exec, grep}` with `ran=TRACE#N` (not SKIPPED/UNRUNNABLE). Tier-2 then verifies the witness — supersession only survives if the original failure no longer reproduces. On a `BLOCKED` verdict this hard-FAILs unconditionally instead; see `shared/return-convention.md` › the SUPERSEDES witness-evidence requirement for the full rule and the BLOCKED-verdict consequence.

**Mandatory-work declarations for build's subagent types** (add to each dispatch template's `## Return Format` section):

- Implementer (feature): `run-tests`, `apply-edits`.
- Implementer (refactor, atomic): `run-blast-radius-tests`, `apply-edits`.
- Reviewer (code / test): `read-artifact`, `emit-findings`.
- Cleanup agent: `read-diff`, `emit-recommendation`.
- Plan writer / plan reviewer: `read-design`, `emit-artifact`.
- Acceptance-test writer / test-gap writer / Inquisitor per-task mode: `run-tests`, `emit-tests`.
