# Build — Gate Ledger Protocol

## Contents

- [Gate Ledger Protocol](#gate-ledger-protocol)
  - [PipelineID Generation](#pipelineid-generation)
  - [Ledger Format](#ledger-format)
  - [Ledger Initialization](#ledger-initialization)
  - [Run Isolation](#run-isolation)
  - [Verdict Marker Isolation](#verdict-marker-isolation)
  - [Timestamps and File Operations](#timestamps-and-file-operations)
  - [Enforcement Rules](#enforcement-rules)
  - [Verdict Marker Verification](#verdict-marker-verification)
  - [Skip Escape Hatch](#skip-escape-hatch)
  - [State Machine](#state-machine)
  - [Compaction Recovery (Ledger)](#compaction-recovery-ledger)

## Gate Ledger Protocol

Tamper-evident audit trail for phase transitions and gate verdicts. This is defense-in-depth — it raises the cost of gate-skipping from zero to nonzero by requiring structured state to be maintained and verified. An external enforcement hook (`gate-ledger-guard.sh`) provides mechanical enforcement by blocking unauthorized PASS writes.

**File location:** `<build-scratch>/build-gate-ledger.md`, where `<build-scratch>` is `~/.claude/projects/<project-hash>/memory/builds/<worktree-key>/`. Derive `<worktree-key>` as the full hex digest output by `printf '%s' "$(git rev-parse --show-toplevel)" | sha256sum | cut -d' ' -f1`. This keys state to the worktree path, including detached worktrees and branch switches.

**Relationship to pipeline-status.md:** `<build-scratch>/pipeline-status.md` is ambient user awareness (overwritten at every narration point). `<build-scratch>/build-gate-ledger.md` is the gate verdict audit trail (updated per phase as gates pass). Both are needed; neither replaces the other.

### PipelineID Generation

At pipeline start, generate a PipelineID via `date -u +build-%Y%m%d-%H%M%S`. This ID:
- Is persisted in the ledger header
- Is passed to quality-gate invocations as `pipeline_id`
- Is used by the enforcement hook to cross-check verdict markers
- Is unique per build run (timestamp-based)

### Ledger Format

```
# Build Gate Ledger
Run: <ISO-8601 timestamp>
PipelineID: <build-YYYYMMDD-HHMMSS>
Goal: <user request>
Mode: <feature | refactor>
QualityGateMode: <standard | full>
RequiredModelAssurance: <none | qg-verified>

## Phase 1: Design
Status: NOT_STARTED

## Phase 2: Plan
Status: NOT_STARTED

## Phase 3: Execute
Status: NOT_STARTED

## Phase 4: Completion
Status: NOT_STARTED
```

**Format constraints:**
- One key-value pair per line: `Key: value`
- Fixed key names: `Status`, `Gate`, `Artifact`, `Tasks`, `Reason`, `Acknowledged`, `PipelineID`, `RequiredModelAssurance`, `QGModelAssurance`, `QGProofTuple`
- Status values: `NOT_STARTED`, `IN_PROGRESS`, `PASS`, `COMPLETE`, `FAIL`, `SKIPPED`, `INFERRED`
- Phase headers are `## Phase N: Name` — always 4 phases, always in order
- No prose, no paragraphs, no nested structure

**Model-assurance opt-in (#746).** The header field `RequiredModelAssurance` persists the caller's explicit opt-in, immutable for the run: `none` (an absent field is legacy `none`) or `qg-verified`. Build never writes `warden-verified`; if it is found in persisted state it blocks only the opted-in action pending explicit user resolution (no Warden-wide proof contract exists) and is never treated as `none`. When a phase's quality gate passes, record alongside `Status: PASS`, before the verdict marker is deleted:

```
QGModelAssurance: <verified | configured | unknown>
QGProofTuple: RunID=<id>; ArtifactHash=<sha256>; FinalArtifactHash=<sha256>; MarkerFinality=<final-integration>; Inventory=<path>; InventoryDigest=<sha256>; GatedFiles=<json-list>
```

sourced from the QG leg's `ModelAssurance`, `RunID`, `ArtifactHash`, `FinalArtifactHash`, `MarkerFinality`, `ModelAssuranceInventory`, and `Gated-Files` fields. For design and plan phases that is the phase's own quality-gate marker; for Phase 4 it is the QG leg's tuple that warden carries in the `QGLegModelAssurance`/`QGLegProofTuple` fields of its aggregate marker (warden/SKILL.md), since build never sees the leg's own marker. Build passes `RequiredModelAssurance` to warden in the dispatch context. Later opted-in checks rebuild the marker dict for `caller_allowed` from the ledger — `Verdict` from `Status: PASS`, `ModelAssurance` from `QGModelAssurance`, `ModelAssuranceInventory` as `<Inventory> sha256:<InventoryDigest>`, and `MarkerFinality`, `RunID`, `ArtifactHash`, `FinalArtifactHash`, `Gated-Files` from the tuple — never with a fabricated field. If the marker or warden's fields are absent (a `none` run, a warden aggregate marker without them, or a legacy marker), record `QGModelAssurance: unknown` and no tuple — never a reason to withhold or fail PASS. `Status: PASS` remains artifact closure only and never satisfies this separate opt-in predicate.

### Ledger Initialization

Runs during build startup, after mode detection but before Phase 1 begins:

1. Check for existing ledger at `<build-scratch>/build-gate-ledger.md`
2. If found: run Run Isolation checks (see below)
3. If not found (or user chose "start fresh"): write new ledger at `<build-scratch>/build-gate-ledger.md` including `Run`, `PipelineID`, `Goal`, `Mode`, and `QualityGateMode` header fields, then all four phases with `Status: NOT_STARTED`. `QualityGateMode` is `standard` unless the caller explicitly selected `full`; reject any other value before dispatch. `RequiredModelAssurance` persists the caller's explicit opt-in (absent = legacy `none`); recovery reuses the persisted policy and never silently defaults a persisted `qg-verified` to `none`.
4. The ledger MUST exist before Phase 1 transitions to `IN_PROGRESS`

After writing any ledger (fresh or reconstructed), immediately re-read the ledger header to extract the PipelineID and `QualityGateMode` into active in-memory state. This is a defensive consistency practice — ensures in-memory values always match persisted values. Every quality-gate retry, compaction recovery, and resume reuses that immutable `QualityGateMode`; never silently defaults an explicit `full` run to `standard`.

### Run Isolation

Stale detection prevents cross-run contamination:

1. **Compaction recovery (same run):** If `<build-scratch>/pipeline-status.md` `Started` timestamp matches the ledger's `Run` timestamp, this is the same build run recovering from compaction. Auto-resume without prompting.
2. **New session with existing ledger:** If the namespaced ledger exists but `<build-scratch>/pipeline-status.md` is missing or its `Started` timestamp doesn't match the ledger's `Run`, prompt: "Found existing ledger for '[goal]' (started [timestamp], Phase N [status]). Resume this run? [y/n]". On "no", archive it via Bash `mv` to `<build-scratch>/build-gate-ledger-<old-timestamp>.md`. If target filename exists, append a counter suffix (`-2`, `-3`, etc.).
3. **No existing ledger:** Create fresh at `<build-scratch>/build-gate-ledger.md`.

### Verdict Marker Isolation

The quality-gate verdict directory remains project-wide: `~/.claude/projects/<project-hash>/memory/quality-gate/`. Do NOT delete markers whose `PipelineID` differs from the active build. A different ID does not prove a marker is stale; it may belong to a live build in another worktree. Verification already filters by the active `PipelineID`, and normal ledger verification deletes this build's marker after use. Leave unconsumed markers untouched. (Project-wide verdict markers are not one of the three recovery singletons; the active marker and PipelineID checks prevent cross-run state deletion.)

### Timestamps and File Operations

- **Timestamps:** Obtained via Bash `date -u +%Y-%m-%dT%H:%M:%S` (Bash is allowed for `date` commands that don't reference `.claude/` paths)
- **Ledger archival (rename):** Uses Bash `mv` since Write/Read/Edit/Glob have no rename capability
- **All other ledger operations** (create, read, update): MUST use Write and Read tools, NOT Bash. This is a **tooling-discipline convention, not an enforced hook** — see `quality-gate/recovery.md` › Round History and Compaction Recovery › *Stated cause, corrected (#486)*, which retracts the "safety hooks block Bash commands referencing `.claude/` paths" justification this line used to carry. Follow it regardless (a deployment may add such a hook), but do not cite the hook as the reason.

### Enforcement Rules

Before each phase transition, read `<build-scratch>/build-gate-ledger.md` and check the previous phase's status:

- **Gate check:** If the previous phase's Status is NOT in {`PASS`, `COMPLETE` (Phase 3 only), `SKIPPED` with `Acknowledged: true`}, output:
  ```
  PHASE GATE BLOCKED: Cannot start Phase N — Phase N-1 gate has not passed.
  Current state: [status]
  Run the quality gate on Phase N-1's artifact before proceeding.
  ```
  This means `INFERRED`, `IN_PROGRESS`, `FAIL`, and `NOT_STARTED` all trigger BLOCKED.

- **Phase 1 exception:** Phase 1 (Design) has no predecessor gate — it always starts.
- **Phase 3 exception:** Phase 3 transitions to `COMPLETE` (not `PASS`) when all tasks are done and per-task code reviews pass. `COMPLETE` satisfies the gate requirement for Phase 4. No verdict marker is required for Phase 3.

**Assurance opt-in predicate (#746).** Before each next-phase transition, push handoff, and recovery-driven action, when the ledger persists `RequiredModelAssurance: qg-verified`, call the shared predicate (`caller_allowed` in `scripts/qg_model_assurance.py`) with the persisted QG-leg proof tuple, the retained inventory file, and a `FinalArtifactHash` recomputed by `gated_hash` (the sole computation, over the inventory's persisted gated path set, deletion set, and hash mode via `artifact_hash` — the caller passes no mode); it additionally takes the `evidence`, `allowlist`, `policy`, and `host_adapter` that the host adapter supplies from its own protected store — none of these is persisted in this ledger, because the inventory's per-row attestation digests (pinned by `InventoryDigest`) are what that evidence must match, and with no host adapter the predicate returns False. For code artifacts, recompute at the commit boundary and again before push from a clean working tree at the committed state in the same worktree root (the hash binds the root, so a different checkout fails closed and asks for fresh gating). The finality, complete chunk roster (terminal inventory), and exact run/artifact/inventory binding checks belong to this opt-in predicate only: missing or mismatched run, artifact, inventory path, digest, attestation evidence, or a non-final marker blocks only the opted-in action — `Status: PASS` and ordinary phase-gate semantics are unchanged — and asks for fresh gating or user resolution. A `gated_hash` failure at a boundary blocks the opted-in action and is never passed to the predicate as `None` (a `None` or absent digest, final hash, or marker `FinalArtifactHash` returns False). Every `qg-verified` call must also pass `expected_gated`, the caller's own list of the paths the action authorizes, and the predicate returns False when it is missing, `None`, empty, or has any path outside the inventory's `gated.paths`; `expected_gated` binds the tuple to the artifact being authorized, and the authenticated evidence names the gated set (`canonical_evidence` covers `gated` and `roster`), so a genuine tuple from another retained run cannot authorize a different artifact. Design and plan phase transitions pass, as a one-item list, the artifact path (repo-relative POSIX form, byte-for-byte as in `gated.paths`) taken from the phase sub-skill's linted Evidence Receipt or the orchestrator's in-context phase output, never re-read from this ledger (the ledger is the store a replay rewrites, so an `Artifact:` line read back from it anchors nothing); when that in-context anchor is unavailable (compaction or recovery) the opted-in action blocks and asks for fresh gating. The 3→4 transition has no QG tuple of its own and re-checks Phase 2's tuple with the Phase 2 plan path from the same in-context anchor. At each opted-in commit and push boundary (including warden's push handoff, whose caller builds `expected_gated` the same way) pass the output of `git diff --no-renames --name-only -z <base>..HEAD` split on NUL (the base the QG leg gated against; `--no-renames` keeps a rename's deleted source and `-z` stops path quoting), and enumerate a code gate's `gated.paths` and `gated.deleted` (deleted entries) from the same command, which makes the rule that every changed path is in the inventory's `gated.paths` executable; a changed path QG never gated (including one a later warden leg edited) is a gated-path mismatch that blocks only the opted-in action and asks for fresh gating. There is no run-id argument: the marker's `RunID` is already bound to the inventory. `action_allowed` itself checks that the marker's `Gated-Files` equals the inventory's gated set minus tombstones. `RequiredModelAssurance: none` or absent requires nothing.

### Verdict Marker Verification

After quality-gate returns with a verdict, verify the verdict marker before writing to the ledger:

1. Glob for verdict markers: `~/.claude/projects/<project-hash>/memory/quality-gate/gate-verdict-*.md` (project-wide directory; filter by active PipelineID, never delete other markers).
2. Filter by `PipelineID` match — only markers with the current build's PipelineID
3. Sort by the `Timestamp` field value inside the marker file (parsed as ISO-8601), take the most recent
4. Verify: marker exists, `Verdict` is `PASS`, `PipelineID` matches current build's PipelineID, and `MarkerFinality` is not `chunk-milestone` — an absent `MarkerFinality` (a warden aggregate marker, a legacy MarkerVersion-2 marker, or a non-chunked gate) reads as final, and only an explicit `chunk-milestone` is rejected; no inventory, roster, or assurance field is read here, so ordinary PASS is never blocked by assurance data
5. If verification passes: write `PASS` to the ledger with `Gate` timestamp and `Artifact` path, and record `QGModelAssurance` (the marker's `ModelAssurance`, itself `marker_assurance` output, never a row-label reading)/`QGProofTuple` from the marker's fields (Phase 4: warden's `QGLegModelAssurance`/`QGLegProofTuple`) before step 7 deletes it, when the marker carries them; otherwise record `QGModelAssurance: unknown` and no tuple — never a reason to withhold PASS
6. If verification fails:
   - **Normal flow** (marker missing/mismatched after a just-run gate): do NOT write PASS. Output warning and re-invoke warden on the same artifact (the full reviewer set — NOT bare `quality-gate`, else recovery downgrades to red-team-only and the I-W7 fail-open re-opens).
   - **INFERRED recovery** (PipelineID mismatch or missing marker on an INFERRED phase): prompt the user for the artifact path, then offer to run the gate or type SKIP GATE.
7. After writing the ledger entry, delete the verdict marker (it has served its purpose). This applies to all verdict outcomes — PASS, FAIL, STAGNATION, and ESCALATED markers are all deleted after the corresponding ledger entry is written. [PLAN ADDITION — extends the design doc's PASS-only deletion to all verdict outcomes for cleanliness.]

### Skip Escape Hatch

If the user explicitly wants to bypass a gate:

**Example of a SKIPPED phase in the ledger:**
```
## Phase 2: Plan
Status: SKIPPED
Gate: 2026-04-13T15:00:00
Reason: User requested skip
Acknowledged: true
```

**Confirmation protocol:** [Default: option (a) — separate-turn required, matching the design doc's two-step flow. User may override to option (b) before implementation.]

1. The orchestrator outputs: "Gate skip requested. Type `SKIP GATE` to confirm. This will be logged."
2. The orchestrator halts execution and waits. The user's NEXT message must contain exactly `SKIP GATE`. A `SKIP GATE` token in the same message as the skip request does NOT satisfy the confirmation requirement.
3. The orchestrator writes `Status: SKIPPED` with `Reason` field to the ledger.

**Per-phase acknowledgment:** SKIPPED requires one acknowledgment per phase, not per boundary. Before starting Phase N, the orchestrator checks all prior phases. Any prior phase with `Status: SKIPPED` that has not yet been `Acknowledged: true` triggers the BLOCKED message. The user types `SKIP GATE` once per skipped phase, and the ledger records `Acknowledged: true`. Subsequent boundaries do not re-prompt for already-acknowledged skips.

**Missing artifact handling:** If a phase was SKIPPED because no artifact was produced, retroactive gating requires the user to supply the artifact path: "To run the gate on Phase N, provide the artifact path." If no artifact exists, retroactive gating is not possible — the phase remains SKIPPED.

**Recovery from SKIPPED:** If the user later wants to properly gate a skipped phase, they can ask to "run the gate on Phase N." The orchestrator transitions `SKIPPED → IN_PROGRESS`, runs the quality gate on the phase's artifact, and writes the result normally.

**Phase 4 completion warning:** If ANY prior phase has `Status: SKIPPED`, Phase 4 outputs a prominent warning listing all skipped gates before presenting finish options.

### State Machine

```
Phase 1: Design
  NOT_STARTED → IN_PROGRESS (design skill starts)
  IN_PROGRESS → PASS (quality gate verdict marker verified)
  IN_PROGRESS → FAIL (quality gate escalates — stagnation/regression)
  FAIL → IN_PROGRESS (user directs re-work)
  * → SKIPPED (user types SKIP GATE — does NOT unlock next phase without acknowledgment)
  SKIPPED → IN_PROGRESS (user asks to run the gate retroactively)
  INFERRED → IN_PROGRESS (user runs gate after compaction recovery)
  INFERRED → SKIPPED (user types SKIP GATE after compaction recovery)

Phase 2: Plan
  NOT_STARTED → IN_PROGRESS (requires Phase 1 Status = PASS or SKIPPED+Acknowledged)
  [same transitions as Phase 1]

Phase 3: Execute (no quality gate — uses COMPLETE instead of PASS)
  NOT_STARTED → IN_PROGRESS (requires Phase 2 Status = PASS or SKIPPED+Acknowledged)
  IN_PROGRESS → COMPLETE (all tasks done, per-task reviews passed, verification gates green)
  IN_PROGRESS → FAIL (task failures, user escalation)
  FAIL → IN_PROGRESS (user directs re-work)
  * → SKIPPED (user types SKIP GATE)
  SKIPPED → IN_PROGRESS (user asks to run retroactively)
  Note: Phase 3 has no QG invocation. COMPLETE satisfies Phase 4's gate requirement.

Phase 4: Completion
  NOT_STARTED → IN_PROGRESS (requires Phase 3 Status = COMPLETE or SKIPPED+Acknowledged. PASS is unreachable for Phase 3.)
  IN_PROGRESS → PASS (quality gate verdict marker verified)
  IN_PROGRESS → FAIL (quality gate escalates)
  FAIL → IN_PROGRESS (user directs re-work)
  * → SKIPPED (user types SKIP GATE)
  SKIPPED → IN_PROGRESS (user asks to run retroactively)
  IN_PROGRESS includes: emit skip warnings if any prior phase SKIPPED
```

### Compaction Recovery (Ledger)

`<build-scratch>/build-gate-ledger.md` is on disk and survives compaction. Recovery precedence when state is partial:

- **Ledger exists, handoff manifest missing:** Use namespaced ledger to determine which phase to resume from. Prompt: "Gate ledger shows Phase N passed, but the phase handoff context was lost. Confirm resume from Phase N+1?" If PASS but no handoff, also prompt for Phase N inputs (design doc path, plan path, etc.) before proceeding.
- **Handoff manifest exists, ledger missing:** Reconstruct ledger from manifests in `<build-scratch>`. Mark the current phase as `INFERRED` (not `PASS`). Mark predecessor phases as `PASS` (handoff existence proves the boundary was crossed). Generate a new PipelineID and write it to the reconstructed ledger header. After writing, re-read the ledger header to extract the PipelineID into active state. INFERRED phases trigger the gate-blocked check — the orchestrator must run a fresh quality gate (with matching PipelineID) or the user must type SKIP GATE.
- **Both missing:** Fresh start in `<build-scratch>`. Prompt user.
- **Model assurance on recovery (#746):** A persisted `RequiredModelAssurance` survives reconstruction and is reused as-is; a ledger reconstructed from handoff manifests takes the requirement from the manifests' `**RequiredModelAssurance:** qg-verified` header line (written by the Phase Handoff Manifest rule in pipeline-status.md whenever the ledger persisted `qg-verified`): if any manifest carries that line, restore `qg-verified`; a manifest lacking the line while another carries it counts as disagreement, and on any disagreement block only the opted-in action pending user resolution rather than defaulting to `none`. A retained `model-assurance/<run-id>.json` inventory or a `QGProofTuple` is not an opt-in signal — every gated run produces them — so it never blocks reconstruction; with no manifest carrying the line, keep legacy `none` behavior and print a one-line notice that the opt-in could not be recovered. If the requirement persists but the QG-leg tuple, inventory file, or referenced evidence is missing or unknown, block only the opted-in action and request fresh gating or user resolution — never advance from `Status: PASS` alone, and no silent PASS-to-verified upgrade.
