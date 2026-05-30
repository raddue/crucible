---
version: 1
---

# Cairn Convention (Invariant Cairn — Layer 3)

> Canonical reference for the orchestrator's per-run cairn file — the authoritative
> substitute for the orchestrator's own context trail.
>
> **This is a shared skill reference, not a CLAUDE.md directive.** Long-running
> orchestrator skills (`/build`, `/quality-gate`, `/siege`, `/forge`, `/innovate`)
> reference this file via `<!-- CANONICAL: shared/cairn-convention.md -->`.
> Skill bodies do not duplicate the schema — they link here.

## Purpose

Orchestrators running for hours accumulate an opaque in-context trail (tool-use traces, reasoning steps, intermediate state, reloaded skill definitions, user turns, branch decisions). Claude Code's auto-compaction is opaque: the orchestrator cannot pick what it loses, often cannot tell it was compacted until it acts on a stale assumption, and has no deterministic recovery path.

The cairn is a per-run markdown file with a rigid four-section schema that the orchestrator reads at every phase entry and whenever uncertain about its own state. Load-bearing facts pin into the cairn as append-only `I-NN` invariants. Once pinned, the orchestrator is licensed to let the underlying reasoning fall out of context — the safety net is explicit and verifiable.

Layered composition: Layer 1 (`return-convention.md`, v1.0) defined the subagent→orchestrator channel. Layer 2 (same file, v1.1) defined cross-receipt recall. Layer 3 (this file) defines orchestrator-internal continuity.

## File Layout

**Canonical path:** `~/.claude/projects/<project-hash>/memory/cairn/cairn-<run-id>.md`

- `<project-hash>` is the standard Crucible project memory root.
- `<run-id>` is second-precision: `YYYY-MM-DDTHH-mm-ss` (dashes, filesystem-safe). A run that resumes after auto-compaction keeps the same `<run-id>` — the marker file survives compaction.

**Active-run marker:** `~/.claude/projects/<project-hash>/memory/cairn/active-run.md` — one line `run-id: <run-id>`. Written when the cairn is first created, deleted when the run sealingly terminates (phase 4 or skill-specific terminal phase).

## Schema (rigid, four sections)

The cairn is a markdown file with exactly four top-level headers, in this order, no other prose. Anything else is a Phase Entry Check failure.

```
# Cairn — <run-id>

## PHASE
phase: <phase-name> / <monotonic-counter>
started-at: <ISO-8601 timestamp>
parent-skill: <top-level skill name, e.g. "build">

## INVARIANTS
I-01: <≤240 char fact>  [ref: <receipt-prefix-12>]
I-02: <≤240 char fact>  [ref: <receipt-prefix-12>]
I-12 supersedes I-07: <≤240 char replacement fact>  [ref: <receipt-prefix-12>]
...

## OPEN_OBLIGATIONS
- [ ] <≤240 char obligation>  [ref: <receipt-prefix-12>]
- [x] <≤240 char obligation>  [ref: <receipt-prefix-12>] [closed-by: <later-prefix-12>]
- [x] <≤240 char obligation>  [closed-by: SUPERSEDED_BY=<later-prefix-12>]
- [x] <≤240 char obligation>  [closed-by: phase/counter] [reason: <≤80 chars>]
...

## LEDGER
<phase>/<counter> | dispatches=<N> receipts=<N> verdict=<PASS|FAIL|MIXED> | <≤80 char summary>
<phase>/<low>-<high> | dispatches=<N> receipts=<N> verdict=MIXED | <summary-of-summaries>   (range-compacted)
...
```

### Section bodies

- **PHASE** — exactly three lines: `phase:`, `started-at:`, `parent-skill:`, in that order. No other keys.
- **INVARIANTS** — append-only, ordinal `I-NN` (zero-padded, monotonic, never reused). Each line ≤ 240 chars. Supersession form: `I-12 supersedes I-07: <replacement>`.
- **OPEN_OBLIGATIONS** — mutable checklist. `- [ ]` or `- [x]`. Each line ≤ 240 chars. Closing an obligation flips the checkbox and appends a `[closed-by: …]` trailer; the original text is preserved.
- **LEDGER** — append-only, one line per completed phase. The only section permitted to compact on budget pressure (see Budget below).

### Line-shape grammars (Phase Entry Check enforces these)

Blank lines and HTML comments (`<!-- … -->`) are permitted between section headers and are not counted as prose. Every non-blank body line must match its section's grammar:

- PHASE body: `^(phase|started-at|parent-skill): .+$`, three lines, in that order.
- INVARIANTS body: `^I-\d{2}(?: supersedes I-\d{2})?: .+$`, total length ≤ 240.
- OPEN_OBLIGATIONS body: `^- \[[ x]\] .+$`, total length ≤ 240.
- LEDGER body: `^[a-z][a-z0-9-]*/\d+(?:-\d+)?\s*\|\s*dispatches=\d+\s+receipts=\d+\s+verdict=(?:PASS|FAIL|MIXED)\s*\|\s*.+$`, summary clause ≤ 80 chars.

Any non-blank body line that does not match is "prose outside a section body" and fails the Phase Entry Check.

## Write Rules (Non-Negotiable)

1. **Phase-exit invariants are mandatory.** Before entering phase N+1, the orchestrator writes any phase-N invariants that are correctness-critical for later phases. Missing invariants are caught at the next phase-entry check.
2. **PHASE is the only section overwritten.** INVARIANTS and LEDGER are append-only. OPEN_OBLIGATIONS is mutable-in-place per the checkbox-flip rule.
3. **INVARIANT ordinals are never reused.** Even superseded slots (`I-07`) stay occupied forever.
3a. **Shedding license requires `[ref:]`.** An invariant is eligible for the shedding license (the orchestrator letting the reasoning trail that produced the fact fall out of context) **only if it carries a `[ref: <receipt-prefix-12>]` trailer** — exactly 12 hex chars, matching Layer 2's hash-prefix-12 format, pointing at the receipt in `receipt-ledger.jsonl` that produced or validated the fact. Invariants without `[ref:]` are pinned but NOT shedding-licensed — the orchestrator retains the surrounding reasoning until amended, superseded, or discharged. No retroactive shedding.
4. **Atomicity.** Phase transitions write the cairn in one `Write` call. A partial cairn surviving auto-compaction is a failure mode Rule 5 of Reconciliation catches.
5. **No prose outside sections.** Enforced by the grammars above.

## Read Rules

1. **Mandatory phase-entry read.** At the start of every phase (including the first), the orchestrator reads the full cairn.
2. **Uncertainty re-read.** Whenever unsure of current state, re-read the cairn first.
3. **No partial reads.** The file is short by construction; always read whole.

## Shedding License

Once a fact is recorded as `I-NN` with a `[ref:]` trailer (per Rule 3a) and the current phase has re-read the cairn, the orchestrator is licensed to let the original reasoning trail that produced the fact fall out of context. Reason in terms of the short ID (`per I-07, token rotation must be preserved`) rather than re-quoting the fact. The orchestrator's own chain-of-thought compresses naturally.

## Phase Entry Check

Before doing any phase-N+1 work, after re-reading the cairn from disk:

```
parse cairn file
fail if any of the 4 section headers missing or out of order
fail if prose appears outside section bodies (use the line-shape grammars)
fail if PHASE section's `phase:` value does not match the phase the orchestrator
  is about to start (or if the monotonic counter has not incremented)
fail if any I-NN ordinal is missing/duplicated/out of order
fail if any I-NN line exceeds 240 chars or contains the literal "TODO" as the
  entire fact (common failure mode: "TODO fill this in")
fail if any OPEN_OBLIGATIONS line exceeds 240 chars
```

Lint failure at phase entry aborts the transition. The orchestrator narrates the failure and either repairs (rewrite phase-exit with the missing invariants) or escalates.

## Reconciliation Pass

After the structural Phase Entry Check passes but before phase-N+1 work begins, the orchestrator runs the **reconciliation pass** — a closed set of rules that compare the cairn's claims against ground truth on disk and in-context. This turns the cairn from an *asserted* recall substrate into a *verified* one.

Inputs:
- `~/.claude/projects/<project-hash>/memory/receipt-ledger.jsonl` (Layer 1)
- The in-context Tripwire Manifest (Layer 2)
- `active-run.md` (this layer)

### Rules

1. **LEDGER dispatch count consistency.** For each `LEDGER` line `<phase>/<counter> | dispatches=N receipts=N …`, `receipt-ledger.jsonl` must contain exactly N entries whose `dispatch-id` begins with `<phase>/<counter>-`.
   - **Local repair (append-only, narrow scope):** permitted ONLY when PHASE and LEDGER-tail agree on the current phase AND the only discrepancy is trailing receipts for the in-progress phase. Append missing receipts via a single atomic Write. Any other section mismatch is NOT locally repairable.
   - **Escalate** in all other cases, including any INVARIANTS or OPEN_OBLIGATIONS drift.

2. **OPEN_OBLIGATIONS closure evidence.** For every `[x]` obligation, the `[closed-by: …]` trailer must be one of:
   - `[closed-by: <receipt-prefix-12>]` — direct close. Cited receipt must resolve to a `receipt-ledger.jsonl` entry with `verdict=PASS`. If the obligation was promoted from a Layer 2 `ran=SKIPPED` witness (obligation carries a `[ref: <receipt-prefix-12>]`), the closing receipt's WITNESS MUST have `ran=TRACE#N` (not SKIPPED/UNRUNNABLE).
   - `[closed-by: SUPERSEDED_BY=<later-prefix-12>]` — peer-supersession close. Layer 2 manifest must show `<orig-prefix> SUPERSEDED_BY=<later-prefix>` and the later receipt must have `verdict=PASS`. Layer 2's witness-evidence rule already gated the supersession; no additional re-run check here.
   - `[closed-by: phase/counter] [reason: <≤80 chars>]` — explicit discharge by orchestrator judgment (Rule 4 option-(b) discharges land here).
   - Any other form, or a cited receipt failing the checks, is a reconciliation failure → escalate.

3. **Active-run singleton (detection-only).** `active-run.md` must exist (unless the run is terminally sealed) AND its `run-id` must match the cairn filename's `<run-id>`. Mismatch → escalate. **Detection, not prevention** — two orchestrators racing to create the marker will both succeed (Write is not CAS). The rule surfaces the race at the next phase entry so the user resolves it; filesystem-lock semantics are out of scope for a convention-only v1.

4. **Invariant-receipt liveness (orchestrator decision point).** For every invariant carrying `[ref: <receipt-prefix-12>]`:
   - The cited receipt must be present in `receipt-ledger.jsonl`. Absence → escalate.
   - If the Layer 2 Tripwire Manifest marks the receipt `SUPERSEDED_BY=<later-prefix>`, the orchestrator **must make an explicit recorded decision**: either (a) record a superseding invariant `I-NN supersedes I-OO: <≤240 char fact reflecting the resolution>`, or (b) append to OPEN_OBLIGATIONS a single closed entry `- [x] I-OO reviewed against supersession <later-prefix>; no update needed [closed-by: phase/counter] [reason: <≤80 chars>]`. One of the two must happen before the orchestrator proceeds; skipping both is a reconciliation failure. The rule is a decision point — not a mechanical semantic proof — because Layer 2's grounds-binding limitation propagates here. The recorded artifact is the falsifiable evidence.

5. **Phase-transition atomicity witness.** On every Recovery Protocol invocation, the PHASE section's `phase: <name>/<counter>` must be consistent with the LEDGER tail:
   - If LEDGER's last entry is `<prev>/<prev-counter>`, PHASE's counter must be exactly `<prev-counter> + 1`.
   - If LEDGER has no entry for the current `phase:` (still in progress), that is fine.
   - If PHASE claims counter ≥ 2 but LEDGER has no entries, auto-compaction hit between the phase-transition Write and the orchestrator acknowledging success. Recovery MUST escalate.
   - If PHASE counter > (LEDGER tail counter + 1), one or more phase-completion lines were skipped. Recovery MUST escalate.

**Rule-precedence note.** Rule 5 takes precedence over Rule 1. If a recovery encounters both a LEDGER under-count AND a PHASE-vs-LEDGER gap, the state is too corrupted for local repair — escalate.

## Budget

Hard limit: **200 lines**. Beyond 120 lines, begin precautionary compaction.

Compaction rules (apply in order):

1. `LEDGER` entries for phases older than the last 5 completed phases may be compressed into a single range line (`<phase>/<low>-<high> | dispatches=<sum> receipts=<sum> verdict=MIXED | summary-of-summaries`).
2. Closed `[x]` OPEN_OBLIGATIONS older than the last 20 closures may be removed. Their `closed-by` references are preserved in a trailing comment on the LEDGER line for the phase that closed them.
3. **INVARIANTS are never compacted.** If the file still exceeds 200 lines after (1) and (2), record a new invariant `I-NN: cairn at budget-limit; further context-shedding must go through user [ref: …]` and escalate.

## Recovery Protocol

Whenever the orchestrator might be post-auto-compaction (unfamiliar context, mid-phase with no clear recollection, tool result doesn't match expectations):

1. Read `~/.claude/projects/<project-hash>/memory/cairn/active-run.md`. If absent → no active run; begin fresh.
2. Read the corresponding `cairn-<run-id>.md` in full.
3. Run the Phase Entry Check. On failure → narrate and escalate; do not proceed.
4. Run the Reconciliation Pass. On failure → narrate the specific rule and escalate (or local-repair per Rule 1's narrow scope).
5. Set internal phase state to PHASE's `phase:` value. Re-read INVARIANTS, OPEN_OBLIGATIONS, LEDGER fully into working context.
6. Continue the run from where the cairn says we are. No retroactive re-dispatch — Layer 1's `receipt-ledger.jsonl` and Layer 2's manifest are authoritative for what happened; the cairn is authoritative for what's **load-bearing**.

**Termination.** At the run's terminal phase sealing, delete `active-run.md` and leave `cairn-<run-id>.md` in place (append-only retention — same rationale as innovate scratch). "Terminal phase" is skill-specific; each pilot skill's `## Cairn (Layer 3)` section declares what terminal means for it.

## Composition with Layers 1 and 2

- **Layer 1 (#202).** LEDGER lines reference Layer 1 receipt-prefixes for each phase's dispatches. An invariant may cite a receipt: `I-07: red-team found auth bypass in v3 [ref: <receipt-prefix-12>]`.
- **Layer 2 (#203).** Receipts with `WITNESS ... ran=SKIPPED:<reason>` or `ran=UNRUNNABLE:<reason>` promote into OPEN_OBLIGATIONS as concrete runnable tails: `- [ ] <witness payload verbatim> [ref: <receipt-prefix-12>]`. Layer 2's `SUPERSEDED_BY` drives cairn's Rule 4 decision point and Rule 2's peer-supersession close path.

## Integration Checklist for Pilot Skills

Each long-running orchestrator skill (`/build`, `/quality-gate`, `/siege`, `/forge`, `/innovate`) must:

1. Add `<!-- CANONICAL: shared/cairn-convention.md -->` near the top of its SKILL.md.
2. Add a `## Cairn (Layer 3)` section declaring:
   - What constitutes a phase for this skill (so phase-transitions map deterministically).
   - What "terminal phase" means for this skill.
   - Any mandatory-invariant categories this skill's phase-exit step must write.
3. At phase entries: read the cairn, run the Phase Entry Check, run the Reconciliation Pass.
4. At phase exits: write any correctness-critical phase-N invariants, append the LEDGER line, single atomic Write advancing PHASE.

## Version History

- **v1** (2026-04-20) — Initial Invariant Cairn convention. Pilot in `/build`, `/quality-gate`, `/siege`, `/forge`, `/innovate`. Bulk rollout across other long-running skills is a follow-up.
