# Contents

- Cost-Cap and Diminishing-Return Signals (#303) · Per-Round Ledger · Accepted · Deferred (v1.0 — empty in v0.1)
- Diminishing-Return Signal · Cost-Cap Prompt · Combined-Prompt Rule · Non-Interactive End-of-Gate Summary
- Non-Skippability · Architectural Concerns Exit · Fix Mechanism · No-Op Fix Detection
- Scope Anchoring for Fix Agents · Fix Memory · Round N Fix · Fix Verification

## Cost-Cap and Diminishing-Return Signals (#303)

Two advisory signals layered over existing escalation paths. Neither introduces a new termination path; both are advisory-only in v0.1 — they surface cost/diminishing-return information to the user but never change the gate's verdict or loop behavior.

### Per-Round Ledger

After each red-team round returns findings, the orchestrator writes `round-N-ledger.md` to the gate scratch directory. v0.1 enumerates every Fatal/Significant finding under `## Accepted`. The `## Deferred` section is present but always empty in v0.1 (no triage; deferral activates in v1.0 once corpus matures — see issue #305).

Emission is unconditional and independent of `cost_cap_threshold` / `dr_signal_findings`. Threshold-3 artifacts get the ledger but no prompts.

**Ledger format:**

```markdown
# Round N Ledger

Artifact-type: <code | design | plan | hypothesis>
Total findings: N (F: x, S: y, M: z)
New since round N-1: K   (on round 1, K = total findings — no prior round)
Accepted: P (all findings — v0.1)
Deferred: 0 (v0.1 — see issue #305 for v1.0)
DR signal: <fired | not fired>
Cost-cap signal: <fired | not fired>

## Accepted
- [Fatal] <finding-id>: <one-line summary>
- [Significant] <finding-id>: <one-line summary>

## Deferred (v1.0 — empty in v0.1)
(none)
```

### Diminishing-Return Signal

Fires when `dr_signal_findings != null` AND the count of **NEW** (delta-vs-prior-round) Fatal+Significant findings is ≤ `dr_signal_findings` AND LOCAL round ≥ 2. (`null` disables the signal entirely per INV-303-4.)

**Interactive** (`interactive: true`): emit prompt:

> "Quality gate round N surfaced only K NEW Fatal+Significant findings (≤ `dr_signal_findings` threshold). Diminishing returns reached. Continue or escalate?"

Choices: Continue / Escalate. No PASS exit from this prompt.

**Non-interactive** (`interactive: false`): log `DR signal: fired` in the round-N-ledger.md. No prompt. No behavior change. Loop continues per existing logic.

### Cost-Cap Prompt

Fires when LOCAL round ≥ `cost_cap_threshold` (default 3). Interactive only.

**Interactive:**

> "Quality gate round N (cost-cap threshold = T, cap exceeded). Score progression: [weighted scores list]. Continue or escalate?"

Choices: Continue / Escalate. No PASS-with-deferred exit in v0.1.

**Counter semantics (chunked-gate):** cost-cap uses the LOCAL (per-chunk) round counter. On a chunked gate, the cap fires once per chunk that reaches LOCAL round ≥ `cost_cap_threshold`. The cross-chunk integration round (where `suppression_threshold = 5`) fires cost-cap at its own LOCAL round ≥ 3. For builds with ≥3 chunks, consider passing `cost_cap_threshold: 5` or `null` to reduce prompt frequency.

**Non-interactive:** log `Cost-cap signal: fired` in the round-N-ledger.md. No prompt. No behavior change.

### Combined-Prompt Rule

When cost-cap and DR signals fire in the same round in interactive mode, emit a single combined prompt — not two sequential prompts:

> "Round N: cost-cap exceeded (threshold T) AND diminishing returns (K NEW findings ≤ S). Continue or escalate?"

### Non-Interactive End-of-Gate Summary

On gate termination (any verdict), the orchestrator emits structured summary lines in the
dispatch return to the parent skill. `Mode` is always `standard` or `full`; residual counts
are nonnegative integers from the terminal qualifying fresh review (or `0` when no
qualifying fresh review exists on an escalated run):

```
Mode: <standard | full>
ResidualSignificant: <int>
ResidualMinor: <int>
CostCapSignals: <DR-fire-count>+<cost-cap-fire-count>/<rounds>
```

Example: `CostCapSignals: 0+2/4` (zero DR fires, two cost-cap fires, four rounds). These
fields give parent skills (build, spec, debugging) a structured signal without changing
termination behavior. The same values appear in the verdict marker and convergence log
(see Verdict Marker spec below). Downstream consumers MUST inspect `Mode` before treating
PASS as strict: standard PASS may disclose residual Significant findings; full PASS may
not.

## Non-Skippability

**This gate cannot be bypassed without explicit user approval.** Task size, complexity, or scope is never a valid reason to skip. The invoking skill is responsible for always dispatching the gate AND letting it run to completion.

**The gate is not "done" until it completes with a mode-clean round** (`0 Fatal` on standard's required fresh reverify; `0 Fatal, 0 Significant` on full). Fixing findings and moving on without a verification round is a skip, not a pass. The iteration loop exists because fix agents introduce new issues or incompletely resolve old ones — fresh-eyes re-review catches what the fixer missed.

**The only valid skip** is an unambiguous user instruction specifically referencing the gate (e.g., "skip the quality gate"). General feedback like "looks good" or "move on" is not skip approval. Once a gate has run and presented findings to the user, the user's decision to proceed is authoritative.

## Architectural Concerns Exit

A fix agent may encounter a finding that cannot be resolved by editing within the declared change boundary — the artifact's structure itself is the problem. This is the only non-clean exit that bypasses suppression at any round.

**Declarant:** The fix agent only. Red-team and verifier agents may flag architectural concerns in their output, but those route through normal severity (Fatal/Significant) — only the fix agent can declare an architectural exit.

**Signal format:** The fix agent's return receipt includes a `VERDICT: ARCHITECTURAL_BLOCK` line and a mandatory `CLAIMS:` citation describing the structural barrier. Format:

```
VERDICT: ARCHITECTURAL_BLOCK
CLAIMS:
  - <Fatal/Significant finding id from the round's red-team findings>
  - <one-sentence explanation of why this cannot be fixed within the change boundary>
WITNESS:
  - kind: lint
  - expect-fail: "fixable-within-change-boundary"
NEXT: orchestrator-escalate-architectural
```

**Orchestrator action on ARCHITECTURAL_BLOCK:**
1. Verify the receipt parses per Tier 1 lint (see Receipt Linter).
2. Write `gate-verdict-<run-id>.md` with `Verdict: ARCHITECTURAL` and the standard fields.
3. Surface to the user: "Architectural concern declared at round N by fix agent. Citation: [CLAIMS]. The artifact requires structural changes beyond the current change boundary. Options: (a) expand change boundary and re-run gate, (b) escalate to the parent skill (design or planning), (c) accept findings as-is."
4. Do NOT loop further. ARCHITECTURAL is a terminal verdict.

**Carve-out from Non-Skippability.** Non-Skippability says "the gate is not done until 0 Fatal / 0 Significant on a fresh review." The ARCHITECTURAL exit is the documented exception: it acknowledges that some findings cannot be resolved without leaving the current artifact's scope. The exit is non-clean by design and routes the user to a parent-skill remediation rather than continued looping.

**Anti-rationalization.** ARCHITECTURAL is NOT an escape hatch for "this finding is hard" — the fix agent must articulate a structural reason in CLAIMS. Difficulty alone routes through normal Fatal/Significant fixing. The verdict is rare; in practice, expect 0-2 per pipeline.

## Fix Mechanism

The orchestrator coordinates the loop but does NOT fix artifacts directly. Fixes are dispatched to a **separate subagent** to maintain separation of concerns between coordination, review, and remediation.

| Artifact Type | Fix Agent |
|---|---|
| design | Plan Writer subagent revises the doc |
| plan | Plan Writer subagent revises the plan |
| code | Fix subagent (new, not the original implementer) |
| hypothesis | Debugging skill's hypothesis refinement (see below) |

**Before dispatching the fix agent (code artifacts only):** If crucible:checkpoint is available, create checkpoint with reason "pre-qg-fix-round-N". Non-code artifacts (design, plan, hypothesis) skip this step — they are fully captured by the existing artifact-N.md snapshots.

<!-- CANONICAL: shared/model-tier-policy.md -->
The fix agent (the design / plan / code rows above) is dispatched with `subagent_type: crucible-qg-fix`, which is **pinned to Sonnet** (`agents/crucible-qg-fix.md`) — the **main-loop** fix output is re-reviewed by the Opus red-team each round on single-model rounds — a weaker fix is *caught* on rounds that reach a subsequent red-team; the cost is **at least** an extra round and is not bounded above (#528 §1 measures fix-authored defects breeding across generations, and §4 shows the stagnation judge scores the catch as PROGRESS, so the extra rounds are not observable to the loop); see `shared/harness-adapter.md` Mapping 1b for the sites this bound does **not** cover; do not pass a call-level `model:`. (The `hypothesis` row is the one exception — it routes to the **debugging skill's own** hypothesis-refinement agent, not `crucible-qg-fix`; that agent is outside this skill's surface.) The fix agent receives: (a) the current artifact, (b) the red-team findings, (c) project context, and (d) the **fix journal** from prior rounds (see Fix Memory below). It returns the revised artifact. The orchestrator writes the revised artifact to the scratch directory and dispatches the next red-team round. If `subagent_type: crucible-qg-fix` fails to resolve (agent defs not installed — see `shared/harness-adapter.md` §8), the dispatch falls back to `general-purpose` on the orchestrator's inherited model and the Sonnet pin is **not** enforced; emit a one-time visible warning of its own ("agent type `crucible-qg-fix` not installed; the fix agent is running on the inherited/session model — the Sonnet pin is NOT enforced; install per harness-adapter §8") rather than degrading silently.

The orchestrator never applies fixes directly. Even trivial fixes go through a fix agent to maintain separation of concerns. The cost of dispatching for a small fix is negligible; the risk of the orchestrator conflating coordination with fixing is not.

### No-Op Fix Detection

A no-op fix is structural signal that the loop has zero forward momentum. The orchestrator detects no-op fixes via either of two conditions:

1. **Byte-identical artifact:** The fix agent's returned artifact is byte-for-byte identical to the input artifact. Detect by SHA-256 comparison.
2. **All-Unresolved verifier:** The fix verifier returns no Resolved findings (every targeted finding remains Unresolved).

When either condition is met:
- Record `no-op-fix: true` in `round-N-score.md`
- **Escalate immediately**, regardless of round number — this overrides pre-threshold suppression. Report: "No-op fix detected at round N: [byte-identical artifact | verifier marked all findings Unresolved]. The loop has zero forward momentum. Escalating."
- Verdict: `ESCALATED` (a no-op is not architectural — the fix agent declined to engage, not declared structurally unfixable). When the `architectural-candidates` list is empty (so no promotion re-dispatch fires), write `Reason: no-op-fix`. When the list is non-empty, the promotion path below governs the Reason token.

**Architectural-candidate promotion path.** If the no-op happened while the `architectural-candidates` list is non-empty (see Fix Verification), the orchestrator re-dispatches the fix agent ONE more time. The re-dispatch prompt enumerates ALL currently-set candidate finding-ids and instructs the fix agent to either (a) resolve any one of the contested Fatal findings, or (b) return `VERDICT: ARCHITECTURAL_BLOCK` with a CLAIMS citation describing the structural barrier — any one resolution path applies independently per candidate. This re-dispatch is executed as the **Pre-precedence resolution** step (see Exit Precedence) — it runs BEFORE precedence evaluation, ensuring the fix agent's second-chance declaration is never preempted by a higher-precedence co-firing exit. The re-dispatch round does NOT increment the gate's round counter (it is a remediation retry within the same no-op round). If the second dispatch produces a clean fix, the gate continues to the next red-team round normally. After the second fix dispatch (when it produced a clean fix, not another no-op or `ARCHITECTURAL_BLOCK`), the orchestrator runs the fix verifier on the second-fix artifact before the next red-team round. The verifier's output (including the `semantic-equivalence:` lines per Step 5) replaces the first-fix verification's output in `round-N-verification.md`. This ensures the architectural-candidates clearing rule has authoritative semantic-equivalence data even when a no-op was promoted to a clean fix mid-round. If the second dispatch returns `ARCHITECTURAL_BLOCK`, route to the ARCHITECTURAL exit (see Architectural Concerns Exit). If the second dispatch also produces a no-op, exit as `ESCALATED` with reason "no-op-with-architectural-candidate" and include both no-op receipts in the escalation output.

This rule is necessary because no-op rounds preserve the weighted score, which under pre-threshold suppression would otherwise loop without escalation. No-op detection is orthogonal to score trajectory.

## Scope Anchoring for Fix Agents

<!-- CANONICAL: shared/dispatch-convention.md (Scope Anchoring) — this section is the
     tier-1 reference implementation. The generalized two-tier pattern, and the tier-2
     semantic scope judge for dispatches whose file set cannot be pinned up front, live
     in the shared convention. -->

Fix agents are prone to drift — addressing findings by adding unrequested features, restructuring documents, or expanding scope beyond what was asked. This costs real time in re-anchoring and rework.

**Before dispatching each fix agent, the orchestrator MUST include in the fix prompt:**

1. **Scope statement:** "You are fixing ONLY the findings listed below. Do not add features, restructure the document, or make changes outside the scope of these findings."
2. **Change boundary:** List the specific sections/files the fix agent is allowed to modify. If a finding requires changes outside these boundaries, the fix agent must flag it rather than making the change.
3. **Drift detection:** After the fix agent completes, the orchestrator checks whether the fix touched files or sections not listed in the change boundary. If out-of-scope changes are detected: reject the entire fix round output, re-dispatch the fix agent with explicit instructions to omit the out-of-scope changes, and include the out-of-scope items as context for the next red-team round.

**Why this matters:** The #1 user friction with the quality gate is fix agents drifting from the original design by adding unrequested content. Scope anchoring turns "stop. skipping. steps." into a structural guardrail.

## Fix Memory

Anti-anchoring is a property of **review**, not **remediation**. Reviewers need fresh eyes to avoid confirmation bias. Fix agents need institutional memory to avoid repeating failed strategies.

The quality gate maintains a **fix journal** (`fix-journal.md` in the scratch directory — `chunk-N/fix-journal.md`, one per chunk, on a chunked gate) that accumulates across rounds. After each fix agent completes, the orchestrator appends a structured entry:

```
## Round N Fix
- **suppressed-signal:** none | regression | sustained-regression | stagnation-would-fire | diminishing-returns | oscillation
- **no-op-fix:** true | false
- **Findings addressed:** [list of Fatal/Significant findings from round N, summarized]
- **Approach taken:** [1-2 sentence description of fix strategy]
- **Files changed:** [list of files modified]
- **Reasoning:** [why this approach was chosen over alternatives]
```

The `suppressed-signal` and `no-op-fix` fields are copied from `round-N-score.md` after the fix completes; they are not authored by the fix agent. Forge consumes these to detect early-thrash patterns.

**On subsequent rounds, the fix agent receives the full fix journal.** This gives the fix agent critical context:
- What approaches were already tried (avoid repeating failed strategies)
- Which files were already modified (avoid unknowingly reverting prior fixes)
- The reasoning chain across rounds (understand the trajectory of remediation)

**Anti-anchoring is preserved.** The fix journal is NEVER passed to the red-team reviewer. Reviewers see only the clean artifact. The journal flows exclusively through the remediation path: fix agent writes it, next fix agent reads it, orchestrator maintains it.

**Round 1 fix agents** receive an empty journal (no prior rounds). This is the only round where the fix agent works without remediation history — on a **chunked** gate, read that per chunk: the journal is chunk-local (Chunked Gate Counter Semantics), so every chunk's LOCAL round 1 starts empty, not just the gate's first.

**Why this matters:** Without fix memory, the most common causes of stagnation and oscillation are fix agents repeating failed approaches or unknowingly reverting prior fixes while addressing new findings. Fix memory turns these escalation events into solvable problems -- the fix agent can see what was already tried and choose a genuinely different approach.

**Compaction recovery:** The fix journal is written to `fix-journal.md` alongside round scores and findings — in the scratch directory on a non-chunked gate, and in the same chunk subdirectory those files use on a chunked one. It is recovered automatically when the orchestrator reads that directory after compaction: the scratch directory on a non-chunked gate, and **the in-progress chunk's own directory** on a chunked one — the same descent Compaction Recovery step 6a already specifies for `round-N-flags.md`, and which the chunked gate's round-file layout requires for every per-round file it reads.

## Fix Verification

After each fix agent completes and before the next red-team round, dispatch a **Fix Verifier** — a dedicated Sonnet agent that checks whether each fix actually resolves its stated finding. No re-fix sub-loop; the verifier checks once, and its output feeds into the fix journal for the next round.

**Dispatch method:** Task tool, `subagent_type: crucible-qg-verifier` (the agent def pins **Sonnet** — `agents/crucible-qg-verifier.md`; do not pass a call-level `model:`), same pattern as the stagnation judge. The verifier needs no file access; the orchestrator includes all input in the dispatch file directly.
**If `subagent_type: crucible-qg-verifier` fails to resolve (agent defs not installed —
see `shared/harness-adapter.md` §8), the dispatch falls back to `general-purpose`
on the orchestrator's inherited model and the Sonnet pin is not enforced; emit a
one-time visible warning of its own ("agent type `crucible-qg-verifier` not
installed; the verifier is running on the inherited/session model — the Sonnet pin
is NOT enforced; install per harness-adapter §8") rather than degrading silently.**


**Input the orchestrator provides:**
1. Round N findings (the findings the fix agent was asked to address)
2. The current round's fix journal entry only — the `## Round N Fix` section just appended (not the full journal)
3. Prepared artifact:
   - Non-code (design docs, plans, hypotheses): post-fix version in full
   - Code: diff + full post-fix source of files touched by the diff. For large implementations (>2000 lines), dispatch one verifier call per finding if context exceeds limits.
4. The full content of `fix-verifier-prompt.md` as the agent's instructions

**Reading the verdict:** The verifier returns a per-finding Resolved/Unresolved table and an overall PASS/FAIL.

**Handling Unresolved findings:**
- **Fatal-severity Unresolved:** Flagged as "prior unresolved Fatal — must address" in the next round's fix dispatch. This is binding with one-round grace: if the fix agent addresses it and the next red-team round does NOT re-raise the finding, the binding expires. If the verifier marks the same Fatal as Unresolved again (persistent disagreement), the verdict downgrades to informational AND the orchestrator appends that finding-id to the `architectural-candidates` list for the next round's fix dispatch (see below). Sonnet should not permanently override Opus, but persistent verifier-red-team agreement that a Fatal cannot be fixed is structural signal — route it to the architectural exit rather than letting it churn silently.
- **Architectural-candidate flag (set on persistent-disagreement downgrade):** The next round's fix-agent prompt enumerates every finding-id currently in the `architectural-candidates` list, e.g.: "The prior two consecutive verifier rounds both marked Fatal `<id-1>`[, `<id-2>`, ...] Unresolved while the red-team has re-raised [it/them]. If you cannot resolve any of these within the change boundary on this round, return `VERDICT: ARCHITECTURAL_BLOCK` citing one or more of these findings (see Architectural Concerns Exit) instead of producing a no-op fix."
- **Significant-severity Unresolved:** Appended to the fix journal as informational context. The next round's fix agent may address, disagree with, or deprioritize.
- **All Resolved (PASS):** Proceed to next red-team round normally.
- **All Unresolved (verifier-PASS=false, no Resolved findings):** This is structural signal that the fix round did no work. The orchestrator records `no-op-fix: true` in `round-N-score.md` and applies the No-Op Fix Detector rule (see Fix Mechanism > No-Op Fix Detection).

**Fix journal integration:** The verifier's output is appended under a `### Verifier Assessment` heading in the fix journal, distinct from the `## Round N Fix` entry format. This keeps verifier assessments on the remediation path (fix agents see them) without contaminating the review path (red-team never sees them).

**Anti-anchoring preserved:** The verifier is on the remediation path — its output flows to fix agents only, never to the red-team reviewer. Same isolation as the fix journal itself.

**Round counter unchanged:** The verifier dispatch does not increment the round counter. It is part of the fix step, not a separate review round.

