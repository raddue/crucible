---
name: quality-gate
description: Iterative red-teaming of any artifact (design docs, plans, code, hypotheses, mockups). Loops until clean or stagnation. Invoked by artifact-producing skills or their parent orchestrator.
origin: crucible
---

# Quality Gate

<!-- CANONICAL: shared/dispatch-convention.md -->
All subagent dispatches use disk-mediated dispatch. See `shared/dispatch-convention.md` for the full protocol.

<!-- CANONICAL: shared/return-convention.md -->
All subagent returns (red-team agents, judges, fix agents) use the Ledger Return Protocol. Every subagent returns exactly one Evidence Receipt per `shared/return-convention.md`; the orchestrator applies the two-tier receipt linter (see the "Receipt Linter (Ledger Return Protocol)" section below) to every Task return before acting on the declared VERDICT.

<!-- CANONICAL: shared/cairn-convention.md -->
The gate maintains an Invariant Cairn per `shared/cairn-convention.md`. Each gate round is a cairn phase. See `## Cairn (Layer 3)` below.

Shared iterative red-teaming mechanism invoked at the end of artifact-producing skills. Provides rigorous adversarial review as the core quality mechanism.

**Announce at start:** "Running quality gate on [artifact type]."

**Skill type:** Rigid -- follow exactly, no shortcuts.

**Execution model:** When this skill is running, YOU are the orchestrator. You drive the loop, dispatch fix agents and reviewers as subagents, track scores, and make escalation decisions. All references to "the orchestrator" in this document refer to you.

## Receipt Linter (Ledger Return Protocol)

Apply Tier 1 (structural) and Tier 2 (witness verification) lint per `shared/return-convention.md` to every Task return before acting on the declared VERDICT. The canonical grammar (CLAIM citations, WITNESS rules, verb-binding, byte-range limits, lint-failure handling) lives in that document. Build, siege, and audit apply the same linter.

**Quality-gate-specific obligations:** Receipts from red-team, fix, judge, verifier, and dependency-audit subagents are all linted before their VERDICT is consumed. A lint failure is treated as structurally `BLOCKED` regardless of declared VERDICT — see "Lint failure handling" in the shared convention.

## Cairn (Layer 3)

Per `shared/cairn-convention.md`. Quality-gate-specific bindings:

- **Phase mapping.** One cairn phase per gate round: `round/1`, `round/2`, …. A round begins at red-team dispatch, ends at judge verdict (either PASS/escalate or loop-again with score delta recorded).
- **Phase transitions.** At each round-exit, append a LEDGER line `round/N | dispatches=<red-team+judge+fix> receipts=<same> verdict=<PASS|FAIL|MIXED> | <score delta + key finding>`. Advance PHASE to the next round on loop; advance to `terminal/N` on PASS or escalation.
- **Terminal phase.** When the gate returns PASS to its caller, OR when it escalates (stagnation / 15-round limit / architectural concern). Delete `active-run.md` on terminal; keep `cairn-<run-id>.md`.
- **Mandatory-invariant categories.** Each round-exit MUST capture any finding that survived into the fix journal with severity ≥ Significant and a note on why — these are the load-bearing constraints for any later round's red-team. Also capture the score trajectory (`score-delta: -2`) for stagnation-detection audit.
- **Reconciliation.** Full 5-rule pass. Rule 4 (invariant-receipt liveness) drives the orchestrator to retire invariants whose originating finding was fixed by the fix-agent (via Layer 2 `SUPERSEDED_BY`) — keeping the invariants list from ballooning across long gates.

## Tripwire Manifest Sweep (Layer 2)

Starting with convention **v1.1**, every QG subagent (red-team, judge, fix-agent) returns a receipt carrying `TRIPWIRE:`, `SUPERSEDES:`, and (when applicable) `TRIPWIRE-CHILD:` lines. Full grammar in `shared/return-convention.md`.

**Manifest:** After each Task return (post-lint), append:

```
<rcpt-sha256-prefix-12>  <skill>/<dispatch-id>  <verdict>  TRIPWIRE: <predicates>  [SUPERSEDED_BY=<prefix>]  [keys=quality-gate:<k>:<v>,…]  [files=<path>:<h6>,…]
```

Namespace CLAIM-key discriminators as `quality-gate:<key>` (e.g. `quality-gate:severity-max:minor`) — prevents collision with `build`/`siege` keys.

**Sweep (dispatch-loop clause):** The orchestrator MAY NOT dispatch the next round until it has: (1) linted; (2) appended; (3) processed SUPERSEDES; (4) evaluated self-checks; (5) evaluated forward-checks against every active prior entry (TRIPWIRE ∪ TRIPWIRE-CHILD); (6) Read each firing M's full receipt and narrated the re-read; (7) then dispatch.

**Fix-agent supersession.** A QG fix-agent supersedes the prior FAIL red-team receipt. `SUPERSEDES: <fail-prefix>` + cited CLAIM + `exec`/`grep` witness with `ran=TRACE#N`. Tier-2 re-runs the witness against the fix — only survives if clean.

**Stagnation-judge tripwires.** A stagnation judge's receipt declaring `TRIPWIRE: peer-dispatch-disagrees(count)` lets a later round's divergent issue-count fire a re-read, surfacing judge-vs-judge disagreement without a separate escalation channel.

**Mandatory-work declarations for quality-gate subagent types:**

- Red-team agent: `read-artifact`, `emit-findings`.
- Judge agent: `read-findings`, `emit-scores`.
- Fix agent: `read-findings`, `apply-edits`, `run-tests` (if tests exist for the artifact's subtree).

**On lint failure:** treat as structurally `BLOCKED` regardless of declared VERDICT. Re-dispatch with lint errors appended to the brief, or escalate.

## Consensus Detection

At the start of the quality gate, check whether the `consensus_query` MCP tool
is available in the current environment:

1. If the tool is available: consensus-eligible rounds will use multi-model
   dispatch (see Multi-Model Red-Team Review and Multi-Model Consensus in
   Stagnation Detection below).
2. If the tool is not available: all rounds use standard single-model dispatch.
   No degradation, no warnings — the gate behaves exactly as it did before
   consensus was introduced.

**Do NOT:**
- Prompt the user to set up consensus if it is unavailable
- Log warnings about missing consensus configuration
- Change any scoring, stagnation, or escalation logic based on consensus availability

Consensus is a transparent enhancement. Its presence improves coverage;
its absence changes nothing.

## External Model Review (Optional)

At the start of the quality gate, check whether the `external_review` MCP tool
is available in the current environment AND `skills.quality_gate` is enabled in
the external review config. If either check fails, skip all external review
steps silently — no warnings, no prompts.

### When It Runs

Every red-team round, alongside the host red-team dispatch. Call
`external_review` with:
- `prompt`: contents of `skills/shared/external-review-prompt.md`
- `context`: the same artifact context given to the red-team subagent
- `skill`: `"quality_gate"` (top-level argument for per-skill toggle enforcement)
- `metadata`: `{"skill": "quality_gate", "round": N}` (traceability)

### Consensus Bridge (rounds 1, 4, 7, 10, 13)

On consensus-eligible rounds where both `consensus_query` and `external_review`
are available:

1. Run `external_review` FIRST, before calling `consensus_query`
2. Only bridge reviews where `error` is null. Skip errored reviews — their
   empty content would corrupt the consensus signal.
3. Pass the non-errored external review responses as the `additional_responses`
   parameter to `consensus_query`
4. The aggregator deduplicates findings across all models (consensus + external),
   surfaces cross-model disagreements, and tags external-unique findings with
   confidence levels
5. On non-consensus rounds, external review runs independently — its findings
   are appended to round output but not routed through the aggregator

### Scoring Invariant (INV-2)

**CRITICAL: External findings do NOT affect the scoring algorithm.**

- The weighted score (Fatal=3, Significant=1) is computed from **host red-team
  findings ONLY**
- External findings are appended to round output for visibility
- External findings are added to the fix journal context (so the fix agent sees
  them as additional perspective)
- External findings are NEVER inputs to the stagnation detection scoring

This invariant is load-bearing. The quality gate's convergence guarantees depend
on a single, consistent scoring source. Mixing external signal into scoring
would create non-deterministic stagnation behavior.

### Graceful Degradation

- `external_review` tool not available (MCP server not running): skip silently.
- Response `status` is `"unavailable"` (no config or disabled): skip silently.
- Response `status` is `"error"` (all models failed): skip silently, note
  failure in round output. Distinct from "unavailable" — means the feature is
  configured but every model errored.
- Response `status` is `"partial"` (some models failed): include available
  reviews, note which models failed in round output.
- External review timeout or failure never blocks or delays the host red-team
  round.

## Anti-Rationalization Table — quality-gate

| Rationalization | Rebuttal | Rule |
|---|---|---|
| "This finding is minor, I'll just fix it inline instead of dispatching a fix agent." | Orchestrator-applied fixes break separation of concerns and corrupt the fix journal. Fix-agent overhead for trivial fixes is negligible; the risk of conflation is not. | All fixes route through the fix agent — no exceptions, no matter how small. |
| "Round N fixed everything, I can return PASS without another red-team round." | Fixing is not passing. A fresh red-team round is the verification step. Skipping it is a skip disguised as a pass. | The gate is only PASS after a fresh red-team round returns 0 Fatal, 0 Significant. |
| "The red-team finding is wrong / overblown, I'll mark it resolved without a fix." | Rationalizing away findings defeats the point of adversarial review. If a finding is wrong, the fix agent explicitly justifies dismissal in the fix journal — the orchestrator does not dismiss findings unilaterally. | Every Fatal/Significant finding is either fixed or documented as dismissed by the fix agent with reasoning. |
| "The score went up but I can tell it's close, skip the stagnation judge." | Stagnation detection uses weighted score, not orchestrator intuition. Score-based inline judgment is the exact failure the judge exists to catch. | Dispatch the stagnation judge whenever score is not strictly lower than the prior round. |
| "Round 15 hit — I'll squeeze in one more round, surely the next will pass." | The 15-round limit is a circuit breaker, not a suggestion. Exceeding it silently is how runaway loops happen. | At round 15, escalate to the user with full round history — never silently continue. |
| "Score went up at round 4 — that's a regression, I should escalate now." | Pre-threshold suppression is deliberate: most artifacts converge within a few rounds and early escalation interrupts that. Record the regression in `round-N-score.md` and keep looping. Exception: if score increased at BOTH round 3→4 AND round 4→5, that's sustained regression — escalate. | Single-round regressions before `suppression_threshold` are suppressed; sustained regressions (2 consecutive strict increases) escalate at any round. |
| "Round 6 scored higher than round 5, and round 5 scored higher than round 4 — but suppression should still apply, right?" | No. The sustained-regression hard exit overrides suppression. Two strict score increases running is a structural signal that further looping will not help. | At round 3+, check `score(N) > score(N-1) > score(N-2)` every round; if true, escalate immediately regardless of suppression. |
| "We're at round 8 and stuck — the user would want to know." | The suppression rule exists precisely because intuition about "stuck" is often wrong before the threshold. Trust the rule; the loop continues unless one of the structural exits (sustained-regression, no-op-fix, architectural-block) fires. | Pre-threshold escalations require a structural exit or explicit user interrupt — orchestrator judgment does not qualify. |
| "This is a hypothesis artifact and we're at round 4 — but pre-round-10 suppression should apply." | No. Hypothesis artifacts default to `suppression_threshold: 3`. At round 4 the threshold has already been crossed; normal escalation applies. Always read the threshold from skill arguments, not from memory of the default for code. | Always read `suppression_threshold` from the current invocation's arguments, never assume 10. |
| "The user said 'move on', that's approval to skip the gate." | General feedback is never skip approval. Skip requires an unambiguous instruction specifically referencing the gate. | Only an explicit, gate-referencing instruction counts as skip approval. |

## Skill Arguments

| Argument | Type | Default | Effect |
|---|---|---|---|
| `suppression_threshold` | int | (artifact-type lookup, see below) | The round number at which suppressed escalations (single-round stagnation, single-round regression, diminishing returns) become live. Below this round, only sustained-regression, no-op-fix, architectural-block, and user-interrupt can exit pre-clean. Above it, all escalation logic applies. |
| `interactive` | bool | `true` if invoked from a standalone session, `false` if invoked by a parent orchestrator (build, debugging, spec) | When true, the orchestrator emits a between-rounds check-in at round `ceil(suppression_threshold/2)` offering the user options: continue, escalate-now, or skip. Non-interactive contexts skip this prompt. |

**Artifact-type-aware default for `suppression_threshold`:**

| Artifact Type | Default Threshold | Rationale |
|---|---|---|
| `code` | 10 | Build-pipeline economics; large diffs benefit from sustained iteration |
| `design` | 10 | Iterative refinement on complex documents |
| `plan` | 10 | Same as design |
| `hypothesis` | 3 | 1-2 sentence artifacts; 10 rounds is wildly disproportionate |
| `mockup` | 3 | Visual artifact; convergence is fast |
| `translation` | 3 | Mock-to-Unity translation; fast iteration loop |

The threshold can be overridden per invocation. Build typically uses the defaults; debugging's Phase 3.5 hypothesis review uses the hypothesis default (3); a user running `/design` directly inherits the design default (10) unless they pass `--suppression-threshold N`.

**Interactive check-in (when `interactive: true`):** After round `ceil(suppression_threshold/2)` (e.g., round 5 for threshold=10, round 2 for threshold=3) completes without clean pass, emit:

> "Quality gate round N (suppression active until round T). Score progression: [list]. Continue, escalate now, or skip gate?"

The user's response routes to: continue (loop with suppression intact), escalate now (treat the next round's stagnation/regression signal as live regardless of suppression), or skip (terminate with `Verdict: ESCALATED`, reason "user-skipped"). One check-in per gate run; not repeated.

## How It Works

1. Receives: artifact content, artifact type, project context
2. **Pre-flight dependency audit (delegated).** As of 2026-05-16, dependency-vulnerability scanning is `crucible:dependency-audit`, invoked by the parent orchestrator in parallel with quality-gate. Quality-gate itself no longer runs this step. If invoked standalone on a code artifact and the user expects dependency scanning, point them to `/dependency-audit`.
3. Prepares the artifact for review (see Artifact Preparation below)
4. Invokes `crucible:red-team` as a **single-pass reviewer** (one dispatch = one review round). Quality-gate owns the iteration loop; red-team produces findings for one round and returns. Red-team does NOT run its own stagnation loop when invoked by quality-gate.
5. If red-team finds **zero Fatal and zero Significant issues:** artifact approved. Write final artifact to scratch directory, output consolidated Minor observations from all rounds (see Minor Issue Handling), surface pre-flight audit results (if any) alongside gate results, clean up, and return.
6. If red-team finds Fatal or Significant issues:
   a. Dispatch a **separate fix agent** (see Fix Mechanism below) — receive revised artifact, append to fix journal
   b. Dispatch **Fix Verifier** (see Fix Verification below) — one Sonnet check per fix round
   c. Append verifier output to fix journal under `### Verifier Assessment` heading; write verdict summary to `round-N-verification.md`
   d. If Fatal-severity Unresolved: flag as "prior unresolved Fatal — must address" in next round's fix dispatch (binding, one-round grace)
   e. If Significant-severity Unresolved: appended to fix journal as informational context
   f. Invoke a FRESH red-team on the revised artifact (no anchoring)
7. Track weighted score between rounds (Fatal=3, Significant=1):
   - **Strictly lower score** → progress, loop again
   - **Same or higher score** → dispatch the Stagnation Judge (see Stagnation Detection below)
8. Read the judge's verdict and act on it (see Stagnation Detection below)
9. **Progress notification.** After round 5 and every 3 rounds thereafter (rounds 5, 8, 11, 14), emit: "Quality gate round [N]: score progression [list]." If the judge was dispatched, append recurring/new counts. Informational only — no pause.
10. **Pre-threshold escalation suppression.** Before round `suppression_threshold` (default 10 for code/design/plan; 3 for hypothesis/mockup/translation — see Skill Arguments), the gate does NOT escalate to the user for stagnation, diminishing returns, or single-round regression. These signals are suppressed in favor of continued iteration — most artifacts converge to 0 Fatal / 0 Significant within a few rounds, and early escalation interrupts the user before that convergence has a chance to happen. The stagnation judge is NOT dispatched on rounds 1 through `suppression_threshold - 4` (i.e., rounds 1-6 for threshold 10). On rounds `suppression_threshold - 3` through `suppression_threshold - 1` (rounds 7-9 for threshold 10), the judge runs in silent mode to seed comparison history (see Stagnation Detection > Judge Dispatch). Regression detection is recorded in the round notes but does not escalate on a single round.

    **Sustained-regression hard exit (convergence guarantee).** Pre-round-10 suppression does NOT extend to a regression that persists across two consecutive rounds. If `score(N) > score(N-1)` AND `score(N-1) > score(N-2)` (i.e., weighted score has strictly increased two rounds running), the gate escalates immediately regardless of round number. Report: "Sustained regression detected: scores [N-2: X, N-1: Y, N: Z] strictly increasing. Fix cycle is actively worsening the artifact. Escalating." This rule guarantees loop termination even under suppression — without it, an oscillating fix agent (score 4 ↔ 5 ↔ 4) could burn rounds 1-9 with zero progress. Two consecutive strict increases is a structural signal that no further looping will help; one increase remains suppressed because single-round noise is expected during convergence.

    The only pre-threshold exits are: clean pass (0 Fatal, 0 Significant); architectural concerns declared via the fix agent's `VERDICT: ARCHITECTURAL_BLOCK` receipt (see Architectural Concerns Exit); sustained-regression hard exit (defined above); no-op fix detection (see Fix Mechanism > No-Op Fix Detection); or explicit user interrupt (including the interactive check-in's "escalate now" response, see Skill Arguments). Beginning at round `suppression_threshold`, normal escalation logic applies (stagnation judge, single-round regression escalation, diminishing returns).
11. **Global safety limit: 15 rounds.** This is a runaway protection circuit-breaker. If you hit 15, escalate to user with full round history. This limit applies regardless of the round-10 suppression rule.

### Multi-Model Red-Team Review (when available)

**Applies to:** Round 1 and every 3rd round thereafter (rounds 1, 4, 7, 10, 13).
**Intermediate rounds:** Standard single-model red-team dispatch (no change).

On consensus-eligible rounds:
1. Instead of dispatching a single red-team subagent, call `consensus_query(mode: "review")` with the red-team prompt and artifact content
2. The consensus response provides merged findings with per-finding severity (Fatal/Significant/Minor), confidence (High/Medium/Low based on model agreement), provenance (which models raised it), and unique findings flagged as "potentially novel"
3. The orchestrator processes these findings exactly as single-model findings: compute weighted score, compare to prior round, dispatch fix agent if needed
4. Findings from consensus rounds include provenance metadata in `round-N-findings.md`

**Cost control:** The consensus dispatch replaces (not supplements) the single-model dispatch on eligible rounds.
**Fallback:** If consensus is unavailable on an eligible round, dispatch standard single-model red-team review.

### Pre-Threshold Consensus Carve-Out

Consensus-eligible rounds 4 and 7 fall inside the suppression window for the default `suppression_threshold` of 10. The red-team consensus dispatch still runs on these rounds and produces findings — but normally the stagnation signal it implies (e.g., score didn't improve) is suppressed.

**Carve-out:** When a consensus-mode red-team dispatch on a pre-threshold round returns findings whose Fatal+Significant count is identical to the prior round's AND the weighted score did not strictly decrease AND the consensus aggregator reports `agreement_level >= 0.75` (75% of responding models converged on the same finding set), the orchestrator escalates immediately with verdict `ESCALATED`, reason "consensus-stagnation-pre-threshold". Report:

> "Multi-model consensus at round N shows persistent findings with high model agreement (75%+). Suppression overridden — unanimity is stronger signal than the threshold heuristic. Escalating."

This preserves the value of the rounds-4/7 consensus investment without giving every consensus call escape-hatch power. Without the carve-out, those rounds pay full consensus cost for signal the loop is contractually deaf to.

**Fallback:** If `agreement_level` is unavailable in the consensus response, treat as < 0.75 (do not escalate).

## Non-Skippability

**This gate cannot be bypassed without explicit user approval.** Task size, complexity, or scope is never a valid reason to skip. The invoking skill is responsible for always dispatching the gate AND letting it run to completion.

**The gate is not "done" until it completes with a clean round** (0 Fatal, 0 Significant on a fresh review). Fixing findings and moving on without a verification round is a skip, not a pass. The iteration loop exists because fix agents introduce new issues or incompletely resolve old ones — fresh-eyes re-review catches what the fixer missed.

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
| mockup | Fix subagent |
| translation | Fix subagent revises the translation map |

**Before dispatching the fix agent (code artifacts only):** If crucible:checkpoint is available, create checkpoint with reason "pre-qg-fix-round-N". Non-code artifacts (design, plan, hypothesis, mockup, translation) skip this step — they are fully captured by the existing artifact-N.md snapshots.

The fix agent receives: (a) the current artifact, (b) the red-team findings, (c) project context, and (d) the **fix journal** from prior rounds (see Fix Memory below). It returns the revised artifact. The orchestrator writes the revised artifact to the scratch directory and dispatches the next red-team round.

The orchestrator never applies fixes directly. Even trivial fixes go through a fix agent to maintain separation of concerns. The cost of dispatching for a small fix is negligible; the risk of the orchestrator conflating coordination with fixing is not.

### No-Op Fix Detection

A no-op fix is structural signal that the loop has zero forward momentum. The orchestrator detects no-op fixes via either of two conditions:

1. **Byte-identical artifact:** The fix agent's returned artifact is byte-for-byte identical to the input artifact. Detect by SHA-256 comparison.
2. **All-Unresolved verifier:** The fix verifier returns no Resolved findings (every targeted finding remains Unresolved).

When either condition is met:
- Record `no-op-fix: true` in `round-N-score.md`
- **Escalate immediately**, regardless of round number — this overrides pre-round-10 suppression. Report: "No-op fix detected at round N: [byte-identical artifact | verifier marked all findings Unresolved]. The loop has zero forward momentum. Escalating."
- Verdict: `ESCALATED` (a no-op is not architectural — the fix agent declined to engage, not declared structurally unfixable). If the no-op happened after the architectural-candidate flag was set (see Fix Verification), prefer the architectural exit instead.

This rule is necessary because no-op rounds preserve the weighted score, which under pre-round-10 suppression would otherwise loop without escalation. No-op detection is orthogonal to score trajectory.

## Scope Anchoring for Fix Agents

Fix agents are prone to drift — addressing findings by adding unrequested features, restructuring documents, or expanding scope beyond what was asked. This costs real time in re-anchoring and rework.

**Before dispatching each fix agent, the orchestrator MUST include in the fix prompt:**

1. **Scope statement:** "You are fixing ONLY the findings listed below. Do not add features, restructure the document, or make changes outside the scope of these findings."
2. **Change boundary:** List the specific sections/files the fix agent is allowed to modify. If a finding requires changes outside these boundaries, the fix agent must flag it rather than making the change.
3. **Drift detection:** After the fix agent completes, the orchestrator checks whether the fix touched files or sections not listed in the change boundary. If out-of-scope changes are detected: reject the entire fix round output, re-dispatch the fix agent with explicit instructions to omit the out-of-scope changes, and include the out-of-scope items as context for the next red-team round.

**Why this matters:** The #1 user friction with the quality gate is fix agents drifting from the original design by adding unrequested content. Scope anchoring turns "stop. skipping. steps." into a structural guardrail.

## Fix Memory

Anti-anchoring is a property of **review**, not **remediation**. Reviewers need fresh eyes to avoid confirmation bias. Fix agents need institutional memory to avoid repeating failed strategies.

The quality gate maintains a **fix journal** (`fix-journal.md` in the scratch directory) that accumulates across rounds. After each fix agent completes, the orchestrator appends a structured entry:

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

**Round 1 fix agents** receive an empty journal (no prior rounds). This is the only round where the fix agent works without remediation history.

**Why this matters:** Without fix memory, the most common causes of stagnation and oscillation are fix agents repeating failed approaches or unknowingly reverting prior fixes while addressing new findings. Fix memory turns these escalation events into solvable problems -- the fix agent can see what was already tried and choose a genuinely different approach.

**Compaction recovery:** The fix journal is written to `fix-journal.md` in the scratch directory alongside round scores and findings. It is recovered automatically when the orchestrator reads the scratch directory after compaction.

## Fix Verification

After each fix agent completes and before the next red-team round, dispatch a **Fix Verifier** — a dedicated Sonnet agent that checks whether each fix actually resolves its stated finding. No re-fix sub-loop; the verifier checks once, and its output feeds into the fix journal for the next round.

**Dispatch method:** Task tool (model: Sonnet), same pattern as the stagnation judge. The verifier needs no file access; the orchestrator includes all input in the dispatch file directly.

**Input the orchestrator provides:**
1. Round N findings (the findings the fix agent was asked to address)
2. The current round's fix journal entry only — the `## Round N Fix` section just appended (not the full journal)
3. Prepared artifact:
   - Non-code (design docs, plans, hypotheses, mockups, translations): post-fix version in full
   - Code: diff + full post-fix source of files touched by the diff. For large implementations (>2000 lines), dispatch one verifier call per finding if context exceeds limits.
4. The full content of `fix-verifier-prompt.md` as the agent's instructions

**Reading the verdict:** The verifier returns a per-finding Resolved/Unresolved table and an overall PASS/FAIL.

**Handling Unresolved findings:**
- **Fatal-severity Unresolved:** Flagged as "prior unresolved Fatal — must address" in the next round's fix dispatch. This is binding with one-round grace: if the fix agent addresses it and the next red-team round does NOT re-raise the finding, the binding expires. If the verifier marks the same Fatal as Unresolved again (persistent disagreement), the verdict downgrades to informational AND the orchestrator marks the next round's fix dispatch as architectural-candidate (see below). Sonnet should not permanently override Opus, but persistent verifier-red-team agreement that a Fatal cannot be fixed is structural signal — route it to the architectural exit rather than letting it churn silently.
- **Architectural-candidate flag (set on persistent-disagreement downgrade):** The next round's fix-agent prompt includes: "Round (N-2) and (N-1) verifier both marked Fatal `<id>` Unresolved while red-team has re-raised it. If you cannot resolve `<id>` within the change boundary on this round, return `VERDICT: ARCHITECTURAL_BLOCK` citing this finding (see Architectural Concerns Exit) instead of producing a no-op fix."
- **Significant-severity Unresolved:** Appended to the fix journal as informational context. The next round's fix agent may address, disagree with, or deprioritize.
- **All Resolved (PASS):** Proceed to next red-team round normally.
- **All Unresolved (verifier-PASS=false, no Resolved findings):** This is structural signal that the fix round did no work. The orchestrator records `no-op-fix: true` in `round-N-score.md` and applies the No-Op Fix Detector rule (see Fix Mechanism > No-Op Fix Detection).

**Fix journal integration:** The verifier's output is appended under a `### Verifier Assessment` heading in the fix journal, distinct from the `## Round N Fix` entry format. This keeps verifier assessments on the remediation path (fix agents see them) without contaminating the review path (red-team never sees them).

**Anti-anchoring preserved:** The verifier is on the remediation path — its output flows to fix agents only, never to the red-team reviewer. Same isolation as the fix journal itself.

**Round counter unchanged:** The verifier dispatch does not increment the round counter. It is part of the fix step, not a separate review round.

## Stagnation Detection

A single stagnation pipeline with three optional model tiers, all gated by `suppression_threshold`:

1. **Orchestrator first-pass (always runs)** — local arithmetic check on weighted score and Fatal count. Cheapest; deterministic; runs every round but only escalates at round ≥ threshold (with sustained-regression and no-op-fix as the at-any-round exceptions).
2. **Sonnet stagnation judge (runs at round ≥ threshold - 4, silent until threshold)** — semantic comparison of finding sets across rounds. Verdict: PROGRESS / STAGNATION / DIMINISHING_RETURNS. Silent dispatches seed comparison history (see Judge Dispatch).
3. **Multi-model consensus (runs on rounds 1, 4, 7, 10, 13 when consensus_query available)** — cross-model verdict on the same comparison inputs. Higher confidence; carries pre-threshold escalation power via the consensus carve-out (see Pre-Threshold Consensus Carve-Out).

The three tiers share the same trigger (same-or-higher weighted score, no Fatal improvement) but produce distinct signals at different cost points. The orchestrator first-pass is the always-on rail; the judge adds semantic recurring/new classification; consensus adds cross-model unanimity weighting. Each tier's verdict is reflected in `round-N-score.md` and `round-N-comparison.md` regardless of whether it escalates.

### First-Pass Check (orchestrator — runs every round)

Stagnation uses **weighted scoring** (Fatal=3, Significant=1) AND **Fatal count tracking**.

**Progress requires EITHER:**
- Weighted score strictly lower than prior round, OR
- Fatal count strictly lower AND weighted score same-or-lower

If either condition is met → progress, loop again. No judge needed.

**Pre-threshold gating.** Before round `suppression_threshold`, the single-round regression and stagnation paths below do NOT escalate. Record the signal in `round-N-score.md` for audit purposes and continue looping. The single-round-regression check below applies only at round `suppression_threshold` and later. (See Skill Arguments for threshold defaults and overrides.)

**Sustained-regression hard exit (applies at every round, including pre-round-10).** If `score(N) > score(N-1)` AND `score(N-1) > score(N-2)` — two consecutive strict score increases — escalate immediately as a sustained regression. This rule overrides pre-round-10 suppression and guarantees loop termination. Requires at least 3 rounds of history (skip on rounds 1 and 2). See How It Works step 10 for rationale.

**Oscillation detection (round 10+):** If the weighted score *increases* (not just stays the same) for a single round, escalate immediately as a **regression**. Report: "Round N score (X) is higher than Round N-1 score (Y). The fix cycle introduced new issues. Escalating." No judge needed.

**Regression with checkpoint (any escalation path on code artifacts):** When the gate escalates with `Verdict: ESCALATED | STAGNATION | SUSTAINED_REGRESSION | ARCHITECTURAL`, glob for all `pre-qg-fix-round-*` checkpoints in the checkpoint skill's store. Surface the full list in escalation output:

```
Pre-fix checkpoints from this gate run (most-recent first):
  - round 9: <hash> (score 4, before round-9 fix)
  - round 8: <hash> (score 3, before round-8 fix)
  - round 7: <hash> (score 5, before round-7 fix)
  ...
```

The user can identify the inflection point (e.g., round-3 fix made things worse) by score trajectory and choose any checkpoint to restore. Options offered: (a) restore to a chosen checkpoint and retry with different fix strategy, (b) continue with current state, (c) escalate to parent orchestrator.

If no checkpoints exist (checkpoint skill unavailable), escalate without the restore option.

### Multi-Model Consensus (when available)

When the `consensus_query` MCP tool is available and consensus mode `verdict` is enabled:

1. Instead of dispatching a single Sonnet judge via Task tool, call
   `consensus_query(mode: "verdict")` with:
   - prompt: the stagnation judge prompt from `stagnation-judge-prompt.md`
   - context: round N findings, round N-1 findings, latest fix journal entry,
     prior comparison files (same inputs as the single-model judge)
   - metadata: { artifact_type, round_number, score_progression }

2. Read the consensus response:
   - If `status: "complete"` or `status: "partial"`:
     - Use the `synthesis` verdict (PROGRESS/STAGNATION/DIMINISHING_RETURNS)
     - If the verdict is STAGNATION or DIMINISHING_RETURNS and disagreements
       exist, include the dissent summary in the escalation message:
       "Stagnation detected (consensus: N/M models agree, dissent: [summary])."
   - If `status: "unavailable"`:
     - Fall back to single-Sonnet judge dispatch (existing behavior)

3. The comparison file (`round-N-comparison.md`) includes the consensus
   metadata: models queried, models responded, agreement level, and any
   dissenting verdicts.

### Judge Dispatch (only when first-pass check would trigger stagnation, round ≥ suppression_threshold)

**Rounds 1 through `suppression_threshold - 4`:** Skip judge dispatch entirely. Loop again regardless of score trajectory. (For threshold 10: rounds 1-6. For threshold 3: judge runs from round 3 onward; no seed rounds because the 3-round window is too short to seed.)

**Seed rounds (rounds `suppression_threshold - 3` through `suppression_threshold - 1`, only when `suppression_threshold ≥ 6`):** When the first-pass check would trigger stagnation (same-or-higher score AND no Fatal count improvement), dispatch the judge in **silent mode**. For threshold 10 this is rounds 7-9; for threshold 3 there are no seed rounds. Silent mode is identical to normal dispatch except:
- The judge's verdict (PROGRESS/STAGNATION/DIMINISHING_RETURNS) is logged to `round-N-comparison.md` but does NOT route to the user
- A `silent-mode: true` line is appended to the comparison file
- The orchestrator loops again regardless of verdict
- The judge's `suppressed-signal` reading is mirrored into `round-N-score.md` (e.g., `suppressed-signal: stagnation-would-fire`)

Silent dispatch seeds the consecutive-round comparison history that the judge's prompt expects. Without seeding, the round-10 judge runs with no prior comparison files and the consecutive-round semantics never engage until round 12+ — leaving only 3-4 escalation-eligible rounds before the 15-round limit.

**At round 10 and later, if neither progress condition is met AND the score did not increase** (i.e., same score, no Fatal count improvement), dispatch the **Stagnation Judge** — a dedicated Sonnet agent that performs semantic comparison of findings across rounds. If the `consensus_query` tool is not available in the environment, this step uses the standard single-Sonnet dispatch described below.

**Dispatch method:** Task tool (model: Sonnet). The judge needs no file access; the orchestrator includes all input in the dispatch file directly.

**Input the orchestrator provides:**
1. The content of `round-N-findings.md` (current round)
2. The content of `round-(N-1)-findings.md` (prior round)
3. The latest fix journal entry only — extract the last `## Round N Fix` section from `fix-journal.md` (not the full journal)
4. The content of any prior `round-*-comparison.md` files (for consecutive-round state tracking)
5. The full content of `stagnation-judge-prompt.md` as the agent's instructions

**Reading the verdict:** The judge returns a structured verdict: **PROGRESS**, **STAGNATION**, or **DIMINISHING_RETURNS**.
- **PROGRESS** → loop again
- **STAGNATION** → escalate: "Stagnation detected: Round N has [X] recurring issues from round N-1 and [Y] new issues. Recurring: [list from judge]. Escalating."
- **DIMINISHING_RETURNS** → escalate: "Quality gate has resolved all prior issues. Round N found [X] new findings, all Structural (require design-level decisions). Remaining findings: [list from judge]. Presenting for user judgment."

**The judge also writes:** a `round-N-comparison.md` file. The orchestrator saves the judge's full output as `round-N-comparison.md` in the scratch directory. This file is used by future judge dispatches for consecutive-round tracking.

## Artifact Preparation

### Small artifacts (design docs, plans, hypotheses, mockups, translations)

Pass the full artifact content to the red-team subagent. No preparation needed.

### Code artifacts

Code artifacts vary in size. The orchestrator prepares the artifact based on scope:

- **Small implementations (<500 lines diff):** Pass the full diff + any new files in full.
- **Medium implementations (500-2000 lines):** Pass full source of high-risk files (new files, files with complex logic changes) + summaries of routine changes (imports, wiring, boilerplate). Include a change manifest listing all files with 1-line descriptions.
- **Large implementations (>2000 lines):** Split into logical chunks (by subsystem, module, or feature boundary). Run a quality gate on each chunk, then a final cross-chunk round reviewing the integration points. Present the chunking plan to the user before proceeding. Normal stagnation detection, progress notifications, and round 15 safety limit apply to **total rounds across all chunks**, not per chunk. **Chunked compaction recovery:** Use a parent run-id for the entire chunked gate. Write `chunk-manifest.md` (lists all chunks with gated/pending status) to the parent scratch directory. Per-chunk round files go in `chunk-N/` subdirectories. Only delete the parent scratch directory after the final cross-chunk round completes. The `active-run.md` marker references the parent run-id throughout.

The red-team subagent receives the **prepared artifact**, not raw diff. This mirrors audit's Tier 1/Tier 2 context management approach.

### Hypothesis artifacts

Hypotheses are 1-2 sentence statements, not plans or designs. The red-team prompt template is plan-centric and does not map well to hypothesis testing. For hypothesis artifacts, the orchestrator frames the red-team dispatch with hypothesis-specific attack vectors:

- Does this hypothesis explain ALL observed symptoms?
- What evidence would disprove it?
- Are there simpler alternative explanations?
- What assumptions does this hypothesis make that could be wrong?

Include these in the dispatch prompt alongside the standard red-team template. The debugging skill's Phase 3.5 defines these questions -- the quality-gate orchestrator should use them.

## Minor Issue Handling

Minor issues do not trigger fix rounds and do not count toward stagnation. However, they accumulate across rounds and contain useful information. Do not silently discard them.

**After the gate completes** (artifact approved or stagnation escalated):

1. **Consolidate:** Collect all Minor observations from all rounds, deduplicate.
2. **Quick-fix pass:** Dispatch a fix subagent with the consolidated minors and the final artifact. The fix agent addresses easy wins only — changes that are simple, low-risk, and unambiguous (typos, naming inconsistencies, missing edge-case guards, trivial cleanup). It skips anything requiring judgment or design decisions.
3. **Present remainder:** Output any minors the fix agent skipped as "Remaining minor observations" so the user can decide whether to address them. No further red-team round on the quick fixes — the gate is already complete.

## Pre-Flight Dependency Audit

**Extracted to `crucible:dependency-audit` (2026-05-16).** The dependency-vulnerability scanning logic formerly inlined here is now its own skill, invoked in parallel with quality-gate by the parent orchestrator (build, debugging, user session). It produces an independent supply-chain signal that is surfaced alongside quality-gate's verdict but does not feed into quality-gate's weighted score (preserves INV-2 — host red-team findings only).

**Migration note:** The `skip_blocking` and `min_blocking_severity` arguments no longer live on quality-gate; they belong to `crucible:dependency-audit`. Build dispatches both skills with their own arguments. Direct user invocations of `/quality-gate` no longer trigger pre-flight; users wanting both should invoke `/dependency-audit` separately or use `/build`.

**Anti-anchoring preserved:** As before, dependency-audit findings are NOT passed to red-team dispatch. The two skills share an artifact but produce independent signals.

See `skills/dependency-audit/SKILL.md` for the full audit specification (manifest scanning, ecosystem detection, severity normalization, output schema, recovery semantics).


## Anti-Anchoring Rules

The iterative loop's value depends on each reviewer seeing the artifact with fresh eyes. To prevent information leaking between rounds:

1. **Clean artifact only.** The artifact passed to each round's reviewer must be the current version with no revision marks, "Fixed:" annotations, or comments about prior reviews. If the fix agent left review-response comments in the artifact, strip them before the next round.
2. **Standardized framing.** The orchestrator's dispatch prompt must use the **same framing** for every round. Do not mention that prior review rounds occurred, what was fixed, or how many rounds have run. The reviewer sees the artifact as if it is the first review.
3. **No findings forwarding.** Never pass prior round findings to the next reviewer. This is already specified in `crucible:red-team` but is restated here because the quality-gate orchestrator is the most likely point of accidental leakage.

## Round History and Compaction Recovery

Quality gate writes round state to disk for compaction recovery.

**Scratch directory:** `~/.claude/projects/<project-hash>/memory/quality-gate/scratch/<run-id>/` where `<run-id>` is a timestamp generated at the start of the gate. This path is persistent and discoverable (matching the audit skill's pattern), so it survives compaction even if the run-id is lost from context — the orchestrator can list the directory to find active runs.

**Tool constraint:** All scratch directory operations (create, read, list, delete) must use Write, Read, and Glob tools — NOT Bash. Safety hooks block Bash commands referencing `.claude/` paths.

**Active run marker:** At the start of the gate, write `~/.claude/projects/<project-hash>/memory/quality-gate/active-run-<run-id>.md` containing the run-id and scratch directory path. Delete only your own marker when the gate completes. After compaction, glob for `active-run-*.md` files to locate active runs — recover the one whose run-id matches context, or the most recent if context is lost.

**Stale cleanup:** At the start of each gate, delete scratch directories whose timestamps are older than 2 hours AND that are NOT referenced by any `active-run-*.md` marker. Also delete any `fix-journal-*.md` handoff files in the `memory/quality-gate/` directory whose mtime is older than 24 hours (the longer window accommodates overnight breaks between QG and forge sessions).

**After each round, write:**
- `round-N-score.md`: weighted score, Fatal count, Significant count, Minor count, plus the following suppression-audit fields:
  - `delta-vs-prior`: integer (weighted score - prior weighted score; positive = regression, negative = progress)
  - `fatal-delta`: integer (Fatal count delta vs prior round)
  - `suppressed-signal`: one of `none | regression | sustained-regression | stagnation-would-fire | diminishing-returns | oscillation` (records what would have escalated had suppression not been in effect; `none` if no escalation signal would have fired; `sustained-regression` is itself an exit and cannot appear as suppressed)
  - `no-op-fix`: boolean (true if round N's fix agent returned a byte-identical artifact, or the verifier returned all findings Unresolved)
- `round-N-findings.md`: the red-team findings for this round
- `artifact-N.md`: the artifact snapshot after fixes (input to round N+1)
- `fix-journal.md`: cumulative fix journal (appended after each fix agent completes; see Fix Memory above)
- `round-N-comparison.md`: stagnation judge output (only exists for rounds where the judge was dispatched — absence on clean-progress rounds is expected, not an error). When multi-model consensus was used, this file also contains consensus metadata: models queried, models responded, agreement level, and any dissenting verdicts.
- `round-N-verification.md`: fix verifier verdict summary (written after every fix round — unlike comparison files, these exist for every round that had fixes)

**Compaction recovery:**
0. Read `## Compression State` from `pipeline-status.md` — recover Goal, Key Decisions (including parent skill decisions that affect the gate), Active Constraints, and Next Steps. If absent, skip to step 1. Note: quality-gate is invoked by a parent skill (build, debugging, spec), so the Compression State reflects the parent's context. The quality-gate orchestrator inherits this context.
1. Glob for `active-run-*.md` markers to locate the scratch directory.
1b. **Pre-flight recovery (code artifacts only):** Check for `preflight-audit.md` in the scratch directory. If absent, restart from manifest scan. If present, read it to recover the manifest list. Then check `audit-results.md` for completed ecosystem sections (those ending with `status: complete` sentinel). Sections without the sentinel are discarded as incomplete. Resume from the first manifest not yet present as a complete section. Recovery re-invokes the audit tool for incomplete manifests — no raw output is cached between compaction events. After all manifests complete, regenerate the Summary section of `audit-results.md`.
2. Read scratch directory to determine current round (highest N in `round-N-score.md` files).
3. Read the latest `artifact-N.md` as the current artifact state.
4. Read all `round-N-score.md` files to reconstruct the score progression.
5. Read all `round-N-comparison.md` files to reconstruct consecutive-round state for the stagnation judge. Absence of comparison files is expected on clean-progress rounds.
6. Read all `round-N-verification.md` files to recover fix verifier state. If any Fatal-severity Unresolved verdicts exist in the latest verification file, carry them forward as binding context for the next fix dispatch.
7. Output status to user: "Quality gate recovered after compaction. Round N complete, score progression: [list]. Continuing."
8. Emit a Compression State Block into the conversation with gate-specific state: current round, score progression, artifact type under review. Inherit Goal and Key Decisions from the parent skill's last Compression State if available.
8b. Check whether `consensus_query` MCP tool is available (consensus
    availability may have changed across compaction boundary). Use current
    availability for subsequent rounds regardless of what was used pre-compaction.
9. Dispatch the next red-team round.

### Checkpoint Timing

Emit a Compression State Block at:
- **Every 3 rounds:** After rounds 3, 6, 9, 12
- **Before stagnation judge dispatch:** When the first-pass check would trigger stagnation
- **Gate completion:** When the gate passes or escalates (before returning to parent skill)
- **Health transitions:** On any GREEN->YELLOW or YELLOW->RED transition

**Forge handoff (code artifacts only):** After Minor Issue Handling and before cleanup, if `fix-journal.md` exists in the scratch directory and contains 2+ round entries (i.e., at least one round had fixes to journal), copy its contents to the quality-gate memory directory as `fix-journal-<run-id>.md` (using the gate's run-id). This is a **transient handoff artifact** for the next forge retrospective.

Write the handoff on ALL exit paths with ≥2 rounds:
- **Clean PASS at round ≥2:** write handoff so forge can detect early-thrash patterns even on successful exits ("converged but tried strategy X three times first")
- **Any escalation:** write handoff — stagnated sessions produce the highest-value dead-end data
- **Clean PASS at round 1:** skip the handoff (single-round successes have no remediation history worth recording)

**Suppressed-signal tagging:** Each `## Round N Fix` entry in the journal includes a `suppressed-signal:` line copied from `round-N-score.md`. Forge uses this to distinguish "thrashed early, recovered" (multiple non-`none` suppressed signals followed by clean pass) from "stagnated late" (clean rounds early, stagnation near threshold). Example:

```
## Round 4 Fix
- suppressed-signal: regression
- no-op-fix: false
- Findings addressed: ...
```


**Cleanup:** Delete scratch directory and your `active-run-<run-id>.md` marker after the gate completes (pass or stagnation). Do NOT delete verdict marker files (`gate-verdict-<run-id>.md`) — the build orchestrator is responsible for their lifecycle.

**Checkpoint cleanup (code artifacts only):** On terminal exit paths:
- **Clean PASS:** Delete all `pre-qg-fix-round-*` checkpoints from this gate run via the checkpoint skill. They served their purpose; retaining them clutters the shadow git log.
- **Any escalation (ESCALATED, STAGNATION, SUSTAINED_REGRESSION, ARCHITECTURAL):** Retain all `pre-qg-fix-round-*` checkpoints until the user resolves the escalation. The user may invoke "restore to checkpoint" on any of them. After the user accepts the escalation (continues, restores, or kills the gate), cleanup is the responsibility of the parent orchestrator or the next gate run's stale-cleanup pass (2-hour TTL).
- **Crash / abandoned run:** The 2-hour stale-cleanup pass at gate start handles abandoned checkpoint sets via mtime check.

## Verdict Marker

After Minor Issue Handling completes and before cleanup begins, write a verdict marker file to a stable location outside the scratch directory. This marker survives scratch cleanup and serves as a cross-skill consistency signal for the build orchestrator's gate ledger.

**When:** After Minor Issue Handling (the quick-fix pass on consolidated minors) and before cleanup. Written on ALL exit paths — PASS, FAIL, STAGNATION, and ESCALATED. The Verdict field reflects the actual outcome.

**Path:** `~/.claude/projects/<project-hash>/memory/quality-gate/gate-verdict-<run-id>.md`

**Format:** Key-value pairs, one per line:

```
Verdict: PASS | FAIL | STAGNATION | ESCALATED | ARCHITECTURAL | SUSTAINED_REGRESSION
Phase: <phase name from invoking orchestrator, omit if standalone>
PipelineID: <pipeline-id from invoking orchestrator, omit if standalone>
Rounds: <total round count>
FinalScore: <weighted score from last round>
MaxScore: <highest weighted score observed across all rounds>
ScoreTrajectory: <comma-separated per-round weighted scores, e.g., 6,4,5,4,3,0>
SuppressedRegressions: <count of pre-round-10 rounds with suppressed-signal != none>
NoOpFixes: <count of rounds with no-op-fix = true>
Timestamp: <ISO-8601>
RunID: <quality-gate run-id>
```

**Verdict enum semantics:**
- `PASS`: gate exited cleanly (0 Fatal, 0 Significant on a fresh red-team round)
- `FAIL`: caller-detected gate failure outside the normal exit paths (reserved for build's gate ledger)
- `STAGNATION`: stagnation judge declared STAGNATION at round 10+
- `ESCALATED`: any other escalation routed to the user (15-round limit, diminishing returns, single-round regression at round 10+)
- `ARCHITECTURAL`: fix-agent flagged architectural concern (any round); see Architectural Concerns Exit
- `SUSTAINED_REGRESSION`: `score(N) > score(N-1) > score(N-2)` triggered the hard exit (any round)

**Fragile-pass detection:** Downstream consumers (build's gate ledger, forge retrospectives, future telemetry) detect a fragile pass via `Verdict: PASS AND (SuppressedRegressions > 0 OR MaxScore > FinalScore + 2 OR NoOpFixes > 0)`. A fragile pass is still a PASS — these fields are advisory signal for human review or telemetry filtering, not for failing the gate.

**Tool:** Write tool (not Bash) since the path is under `.claude/`.

**Standalone invocations:** When quality-gate is invoked directly (not by build), the `Phase` and `PipelineID` fields are omitted. The marker is still written — it serves as a completion record even without pipeline context.

**Stale cleanup exclusion:** Verdict markers are NOT subject to the 2-hour stale cleanup that applies to scratch directories. They are deleted by the build orchestrator after writing the corresponding gate ledger entry. Orphaned markers (from crashed runs) are cleaned up during the build skill's ledger initialization.

## Convergence Telemetry

The pre-threshold suppression rule rests on a quantitative claim: "most artifacts converge to 0 Fatal / 0 Significant within a few rounds." Without measurement, the choice of threshold (default 10 for code, 3 for hypothesis) cannot be tuned or falsified. This section defines a persistent per-run convergence record that survives scratch cleanup and enables threshold calibration over time.

**Path:** `convergence-log.jsonl` under the quality-gate memory directory (sibling to `gate-verdict-*.md`, NOT under `scratch/<run-id>/` which is deleted on terminal exit).

**When written:** Once per gate run, immediately after the verdict marker is written and before scratch cleanup.

**Tool:** Write tool (not Bash, since the path is under `.claude/`). Append-only — read existing file, append one line, write back.

**Format:** One JSON object per line:

```json
{"run_id":"2026-05-16T14-30-00","artifact_type":"code","threshold":10,"rounds":4,"verdict":"PASS","final_score":0,"max_score":6,"score_trajectory":[6,4,3,0],"suppressed_regressions":1,"no_op_fixes":0,"siege_dispatched":false,"timestamp":"2026-05-16T14:38:21Z"}
```

Fields mirror the verdict marker plus `threshold` (the active `suppression_threshold` for this run). One line per gate run, regardless of verdict.

**Size management:** The log is append-only. Rotate via mtime check: if the file exceeds 10,000 lines, the next gate run renames it to `convergence-log-<YYYY-MM>.jsonl` (archive) and starts a fresh log. Archives are never deleted by quality-gate — the user manages retention.

**Acceptance criterion for the suppression rule:** Across the most recent 100 entries with matching `artifact_type`, ≥80% should have `rounds < threshold` AND `verdict == PASS`. If the ratio drops below 70% for a given artifact type across 50+ entries, the threshold default for that type is mistuned and should be revisited.

**Sunset trigger:** If a single rolling 30-day window shows the acceptance criterion failing for any artifact type, the next gate run emits a warning at start: "Convergence telemetry shows suppression threshold for `<artifact_type>` may be mistuned: <ratio>% of recent runs PASSed under threshold. Consider overriding `suppression_threshold` for this invocation, or raising the issue for threshold review."

**Privacy:** The log contains no artifact contents, no findings, no file paths from the project being gated. Run IDs are timestamps. Safe to commit, share with collaborators, or aggregate across projects.

**Why not in the scratch directory:** Scratch is deleted on terminal exit. A telemetry log that survives only until the gate ends is useless for tuning. The convergence-log lives in the persistent quality-gate memory directory.

## Invocation Convention

Quality gate is invoked by the **outermost orchestrator only** — not self-invoked by child skills. This avoids double-gating.

**Rule: Skills NEVER self-invoke quality-gate.** They only document that their output is gateable. The outermost orchestrator (build, the user session, or another pipeline) always handles gating. This eliminates the ambiguity of skills trying to detect whether they are running standalone or as a sub-skill.

### When Used Standalone (user invokes directly)

The user's session is the outermost orchestrator. When a user runs `/design` directly, the design skill produces the doc and documents it as gateable. The user's session (following the design skill's instructions) invokes quality-gate.

### When Used as a Sub-Skill of Build

Build is the outermost orchestrator and controls all quality gates:

- **Phase 1 (after design):** Quality gate on design doc (artifact type: design)
- **Phase 2 (after plan review):** Quality gate on plan (artifact type: plan)
- **Phase 4 (after implementation):** Quality gate on full implementation (artifact type: code)

**Context from invoking orchestrator:** When build invokes quality-gate, it includes a "Context from invoking orchestrator" block in the dispatch prompt containing:
- `Phase: <phase name>` — "design", "plan", or "code"
- `PipelineID: <pipeline-id>` — the build's PipelineID (format: `build-YYYYMMDD-HHMMSS`)

Quality-gate reads these values from its dispatch context and includes them in the verdict marker. These are dispatch context values, not tool arguments — quality-gate is a skill, not an API.

### Artifact Types

| Type | Produced By | Gate Trigger |
|------|-------------|-------------|
| design | `crucible:design` | After design doc is saved |
| plan | `crucible:planning` | After plan passes review |
| hypothesis | `crucible:debugging` | Phase 3.5, before implementation |
| code | `crucible:debugging`, build | After implementation/fix |
| mockup | `crucible:mockup-builder` | After mockup is created |
| translation | `crucible:mock-to-unity` | After self-verification |

### Documentation Convention

Each artifact-producing skill's SKILL.md documents:

> "This skill produces **[artifact type]**. The outermost orchestrator invokes `crucible:quality-gate` after [trigger]."

## Escalation

Exit modes beyond clean approval. **Single-round stagnation, single-round regression, and diminishing-returns exits are suppressed before round `suppression_threshold`** — see the pre-threshold suppression rule under How It Works step 10. The sustained-regression, no-op-fix, and architectural-concerns exits apply at every round.

- **Sustained regression** (any round) → escalate immediately: "Sustained regression detected: scores [N-2: X, N-1: Y, N: Z] strictly increasing. Fix cycle is actively worsening the artifact. Escalating." Verdict: `SUSTAINED_REGRESSION`. Applies pre-threshold too — guarantees loop termination under suppression.
- **No-op fix** (any round) → escalate immediately on byte-identical artifact OR all-Unresolved verifier (see Fix Mechanism > No-Op Fix Detection). Verdict: `ESCALATED`. Applies pre-threshold too.
- **Stagnation** (round ≥ threshold) → escalate to user with recurring/new classification from the judge: "Stagnation detected: Round N has [X] recurring issues from round N-1 and [Y] new issues. Recurring: [list]. Escalating." Verdict: `STAGNATION`.
- **Diminishing returns** (round ≥ threshold) → escalate to user with structural findings from the judge: "Quality gate has resolved all prior issues. Round N found [X] new findings, all Structural (require design-level decisions). Remaining findings: [list]. Presenting for user judgment." Verdict: `ESCALATED`.
- **Single-round regression** (round ≥ threshold) → escalate immediately, no judge needed: "Round N score (X) is higher than Round N-1 score (Y). The fix cycle introduced new issues. Escalating." Verdict: `ESCALATED`.
- **Global safety limit reached (15 rounds)** → escalate to user with full round history. Applies regardless of `suppression_threshold`. Verdict: `ESCALATED`.
- **Architectural concerns** → fix agent returns `VERDICT: ARCHITECTURAL_BLOCK` (see Architectural Concerns Exit). Escalate immediately, terminal verdict `ARCHITECTURAL`. Applies at any round.
- **User interrupt** — either between-rounds interactive check-in's "escalate now"/"skip" response (see Skill Arguments) or an out-of-band interrupt. Verdict: `ESCALATED`, reason "user-skipped".

## Red Flags

**Inclusion rule:** A red flag belongs here only if it describes a runtime mistake the orchestrator could make at gate time. Failure modes that the Anti-Rationalization Table, Non-Skippability, or a structural invariant (Receipt Linter, Cairn, Tripwire Manifest) already prevents do NOT appear in this list — they are mechanically impossible, not vigilance items. Any new red flag added here must come with a one-line justification of why no upstream mechanism catches it.

### Loop ownership

- Using the same red-team agent across rounds (always dispatch fresh — `crucible:red-team` is single-pass when invoked by quality-gate)
- Re-dispatching the fix agent based on verifier results (no re-fix sub-loop — verifier checks once, output feeds into next round's fix dispatch)
- Orchestrator performing semantic comparison inline instead of dispatching the stagnation judge at round ≥ threshold

### Anti-anchoring

- Passing revision context, prior findings, round history, or fix journal to the red-team reviewer (fix journal is for fix agents ONLY; verifier output is for fix agents only)
- Leaving review-response artifacts (comments, annotations) in the artifact between rounds
- Dispatching a fix agent without the fix journal on round 2+ (fix agents need remediation history)
- Passing consensus provenance metadata to the fix agent's red-team framing (provenance is for the fix journal and orchestrator, not for biasing the next reviewer)

### Scoring & verdicts (INV-2 hygiene)

- Declaring stagnation on raw issue count without using weighted score (Fatal=3, Significant=1)
- Including external review findings in the weighted score calculation (INV-2: host red-team findings ONLY)
- Using external findings as inputs to stagnation detection scoring
- Passing `crucible:dependency-audit` output to red-team dispatch — dependency-audit is an independent parallel signal, not red-team input
- Dispatching the judge when the score is strictly improving (waste — score alone is sufficient)

### State & recovery

- Forgetting to save the judge's output as `round-N-comparison.md` (breaks consecutive-round tracking and silent-seed history)
- Skipping Compression State Block emission at checkpoint boundaries
- Emitting a Compression State Block with stale or missing Key Decisions, or letting the Goal field drift across blocks
- Exceeding 10 entries in the Key Decisions list without overflow-compressing the oldest

### Multi-model & external

- Using consensus on every red-team round (periodic only: rounds 1, 4, 7, 10, 13)
- Treating single-model unique findings from consensus as less important than multi-model agreements (the prompt explicitly elevates "potentially novel" findings)
- Blocking the host red-team round on external review availability or timeout

**Retired (covered structurally):** Self-fixing instead of dispatching a fix agent, rationalizing away findings, skipping the gate without approval, declaring "complete" without a clean round, exceeding 15-round limit, escalating pre-threshold for single-round signals, dispatching the judge pre-threshold, looping past sustained regression, allowing fix-agent scope drift, skipping the fix verifier — all of these are now caught by the Anti-Rationalization Table or by structural invariants (Non-Skippability, Receipt Linter mandatory-work, Architectural Concerns Exit). They do not need separate red-flag entries.

## Integration

- **crucible:red-team** — The engine that performs each review round. **Loop ownership:** Quality-gate uses red-team as a single-pass reviewer only (one dispatch = one review round, findings returned). Quality-gate owns the iteration loop, stagnation detection, and round tracking. Red-team does NOT run its own stagnation loop when invoked by quality-gate. Red-team's stagnation rules apply only when red-team is invoked directly (e.g., by `crucible:finish`).
- **crucible:design** — Produces design docs (gateable artifact)
- **crucible:planning** — Produces plans (gateable artifact)
- **crucible:debugging** — Produces hypotheses and fixes (gateable artifacts). **Note:** Debugging's Phase 5 must invoke `crucible:quality-gate` for fix review, not `crucible:red-team` directly. This ensures fixes get iteration tracking, compaction recovery, and user checkpoints.
- **crucible:mockup-builder** — Produces mockups (gateable artifact)
- **crucible:mock-to-unity** — Produces translation maps and implementations (gateable artifacts)
- **crucible:build** — Outermost orchestrator, controls all gates in pipeline
- **crucible:checkpoint** — Shadow git checkpoints before code-artifact fix rounds (recommended). Provides rollback target when fix rounds introduce regressions.
