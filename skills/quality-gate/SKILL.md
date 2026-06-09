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

The linter is a deterministic runtime tool: orchestrators MUST run `python3 scripts/rcpt_verify.py --tier2 --strict --root <dispatch-root> --ledger <dispatch-root>/receipt-ledger.jsonl <receipt>` on every received receipt before acting on its VERDICT, and apply the shared convention's in-context pseudocode ONLY as the fallback when the tool is unavailable. `--strict` hard-FAILs only resolvable path-shaped artifacts on a sha256/witness mismatch; an unresolvable bare basename stays UNVERIFIABLE (never a false FAIL); always pass `--root <dispatch-root>` explicitly. The obligation to lint every return is unchanged — only the mechanism moves to the tool.

**Quality-gate-specific obligations:** Receipts from red-team, fix, judge, verifier (the fix-verification dispatch; the persistence-checker JSON output is consumed directly, not receipt-linted — see Persistence Check), and dependency-audit subagents are all linted before their VERDICT is consumed. A lint failure is treated as structurally `BLOCKED` regardless of declared VERDICT — see "Lint failure handling" in the shared convention.

**Red-team receipts lint clean (#366).** Red-team returns a structured `RCPT v1.1` receipt (not prose), so its receipt passes Tier-1/Tier-2 normally — it does **not** lint-to-`BLOCKED`. The red-team **findings** themselves come from the **cited artifact** the receipt pins (`round-N-findings.md`, an `[FINDINGS_OUTPUT_PATH]` the orchestrator supplies — see the score step and writer-inversion below), which the orchestrator reads directly; the receipt's VERDICT is the witness-verified PASS/FAIL boundary plus the supersession/tripwire anchor, not the findings channel. This makes the `:44`/`:56`/`:62` couplings operational (red-team genuinely emits a receipt).

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

**Fix-agent superseding-witness by artifact class (#366).** Because the red-team FAIL receipt is now a real supersession anchor, the convention's witness-evidence requirement (a FAIL / `SUSPICION ≥ 0.30` predecessor demands the superseding `WITNESS` be `kind ∈ {exec, grep}` + `ran=TRACE#N`) is live on the fix-agent's superseding receipt:

- **Test-less artifacts (test-less design / plan / doc gates — the dominant QG case):** the fix-agent's superseding receipt carries a **`grep` witness against the revised artifact** proving the superseded red-team **finding-anchor** text **no longer appears** (`kind=grep`, `ran=TRACE#N`), **plus** the justification CLAIM citing the FAIL receipt's prefix (`from=<fail-prefix>#…`, per the SUPERSEDES Tier-1 justification requirement in `return-convention.md`). This is what makes the supersession survive Tier-2 — the original concern demonstrably no longer reproduces.
- **Artifacts WITH tests:** the existing `run-tests` exec witness applies (the `run-tests` mandatory-work declaration above).

**Clean-PASS TRIPWIRE predicate (#366, SP2).** Per the convention's TRIPWIRE-none rule at `return-convention.md` (the Tripwire Manifest section, ~`:427`), `TRIPWIRE: none` is permitted **only** on a PASS receipt with `SUSPICION=0.00`; a FAIL red-team receipt carries `TRIPWIRE: verdict=FAIL`. This is a pointer to the canonical rule, not a redeclaration of the grammar (per CLAUDE.md "link, never copy").

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

Consensus is a near-transparent enhancement. Its presence improves coverage;
its absence preserves all standard exit paths. The one documented asymmetry:
consensus presence enables one additional pre-threshold escalation path — see
Pre-Threshold Consensus Carve-Out. This is the only place where consensus
availability changes the gate's exit set.

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

### Consensus Bridge (Round 1, then every `max(1, suppression_threshold // 3)` rounds, up to round 15)

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
| "This is a hypothesis artifact and we're at round 4 — but pre-threshold suppression should apply." | No. Hypothesis artifacts default to `suppression_threshold: 3`. At round 4 the threshold has already been crossed; normal escalation applies. Always read the threshold from skill arguments, not from memory of the default for code. | Always read `suppression_threshold` from the current invocation's arguments, never assume 10. |
| "This is a small auth fix, siege is overkill — skip it." | Detection exists because intuition about "small" security changes is unreliable. The cost of one siege dispatch is ~6 Opus agents; the cost of missing a regression in a security PR is unbounded. | Never skip siege when detection fires unless `skip_siege: true` is explicitly set with documented reason. |
| "Detection fired on keywords in a design doc, but the doc isn't really about security." | The confidence threshold (≥2 categories OR keyword + dedicated `## Security` section) already filters single-word noise. If detection still fires, the doc has real security content. | Trust the confidence threshold. To override, set `skip_siege: true` with reason in the gate-verdict marker. |
| "The user said 'move on', that's approval to skip the gate." | General feedback is never skip approval. Skip requires an unambiguous instruction specifically referencing the gate. | Only an explicit, gate-referencing instruction counts as skip approval. |
| "Skip look-harder on this clean round — it converged fast and the artifact is obviously fine." | Speed of convergence is not signal of correctness; the entire premise of look-harder is that a single-pass clean round can hide Significants under standard rubric. The skip conditions are MECHANICAL (`circuit-breaker` at round 15, `tail-rubric-already-applied` when the round ran with the addendum already in-band), not judgment-based. | Look-harder fires on every first-clean round of a chunk; only the documented skip conditions short-circuit it. No "this one feels safe" exceptions. |
| "Skip the persistence checker — round N's fix verifier already confirmed which findings were unresolved, so running the checker on round N+1 is redundant." | The verifier checks whether *this specific fix attempt* resolved the targeted findings (single-channel, fix-side). The persistence checker checks whether round-(N+1)'s red-team independently raises the same complaint (single-channel, review-side). Two single channels do not equal two-channel corroboration. | Run the persistence checker whenever the trigger fires (round N+1 non-clean AND ≥1 round-N Unresolved verdict). The verifier and persistence checker are independent corroboration channels by design. |
| "Tail-rubric is too aggressive on round 6 of this threshold-10 gate — the standard rubric is fine, let the round stand without the addendum." | The tail-rubric trigger is mechanical (`suppression_threshold ≥ 5` AND LOCAL round ≥ `ceil(suppression_threshold * 0.6)`), NOT a judgment call. Late-round inflation is the failure mode the addendum exists to suppress; declining to apply it at the trigger round is exactly when it's most needed. | Apply `tail_rubric: true` mechanically. The addendum's anti-undergrade clause preserves real Fatals; the demotion is targeted at speculative Significants only. |

## Skill Arguments

| Argument | Type | Default | Effect |
|---|---|---|---|
| `suppression_threshold` | int | (artifact-type lookup, see below) | The round number at which suppressed escalations (single-round stagnation, single-round regression, diminishing returns) become live. Below this round, only sustained-regression, no-op-fix, architectural-block, and user-interrupt can exit pre-clean. Above it, all escalation logic applies. |
| `interactive` | bool | `true` if invoked from a standalone session, `false` if invoked by a parent orchestrator (build, debugging, spec). **Detection:** The orchestrator infers `interactive` from the presence of the `Context from invoking orchestrator` block in its dispatch context: BOTH `Phase` AND `PipelineID` present → treated as sub-skill invocation (`interactive: false`). Either field alone or both absent → standalone (`interactive: true`). Sub-skill parents (debugging, spec) MUST follow the build pattern; any parent that fails to pass Phase+PipelineID will cause QG to default to `interactive: true` and emit between-rounds check-ins, which will hang non-interactive pipelines. Parent skills can also explicitly pass `interactive: false` to override detection if they do not have a natural Phase/PipelineID to provide. Explicit `interactive:` argument overrides detection in either direction. | When true, the orchestrator emits a between-rounds check-in at round `ceil(suppression_threshold/2)` offering the user options: continue, escalate-now, or skip. Non-interactive contexts skip this prompt. |
| `force_siege` | bool | `false` | When true, always dispatch `crucible:siege` in parallel with the first red-team round regardless of security-surface detection. Use for: explicit security PRs, scheduled security audits, post-incident review. |
| `skip_siege` | bool | `false` | When true, never dispatch siege even if security-surface detection fires. Use for: artifacts the user already siege-tested separately, or repeated re-runs after siege already passed. Mutually exclusive with `force_siege` — passing both is an error. |
| `cost_cap_threshold` | int \| null | `3` if `suppression_threshold > 3` else `null` (auto-null on hypothesis/mockup/translation) | LOCAL round at which the cost-cap prompt fires (interactive only). Set to `null` to disable. Auto-null when `suppression_threshold ≤ 3` to avoid collision with the existing `DIMINISHING_RETURNS` judge verdict at the same round. See `## Cost-Cap and Diminishing-Return Signals` for behavior. (Added by #303.) |
| `dr_signal_findings` | int \| null | `2` if `suppression_threshold > 3` else `null` | Count of NEW (delta-vs-prior-round) Fatal+Significant findings at or below which the DR signal fires (interactive only). Same auto-null rule as `cost_cap_threshold`. (Added by #303.) |

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

**No new public arguments for #265 mechanisms.** Look-harder verification, tail-rubric, and the persistence checker are mechanically derived from existing `suppression_threshold` + artifact type + LOCAL round number. There is no `--look-harder` / `--tail-rubric` / `--persistence-check` argument — callers do not opt in or out. The mechanisms fire on their structural triggers; the only externally observable change is new fields in the verdict marker and convergence-log.

**Interactive check-in (when `interactive: true`):** After round `ceil(suppression_threshold/2)` (e.g., round 5 for threshold=10, round 2 for threshold=3) completes without clean pass, emit:

> "Quality gate round N (suppression active until round T). Score progression: [list]. Continue, escalate now, or skip gate?"

The user's response routes to: continue (loop with suppression intact), escalate now (treat the next round's stagnation/regression signal as live regardless of suppression), or skip (terminate with `Verdict: ESCALATED`, reason "user-skipped"). One check-in per gate run; not repeated.

## How It Works

1. Receives: artifact content, artifact type, project context
1.5. **Calibration advisory (print-only, at gate entry).** Resolve `scripts/brier_advisory.py` by absolute path from the plugin root (same resolution as the ledger emit below) and run `python3 <script> advisory quality-gate`. If it prints a line, surface that line to the user verbatim before the first red-team round; if it prints nothing, say nothing. The script reads the central store (`~/.claude/crucible/ledger/brier-rolling.json` + `falsification.jsonl`, override `CRUCIBLE_LEDGER_DIR`) and is silent unless this skill has ≥5 falsifiable verdicts with a Brier > 0.25 over trustworthy (≤30-day-old) reconciliation data. It honors `CRUCIBLE_CALIBRATION_DISABLED=1` as a graceful skip. If the script can't be resolved, skip silently — a missing advisory must never block the gate. No behavior change; this is an advisory print only.
2. **Pre-flight dependency audit (delegated).** As of 2026-05-16, dependency-vulnerability scanning is `crucible:dependency-audit`, invoked by the parent orchestrator in parallel with quality-gate. Quality-gate itself no longer runs this step. If invoked standalone on a code artifact and the user expects dependency scanning, point them to `/dependency-audit`.
2.5. **Security surface detection and siege dispatch.** Run the detection heuristic (see Security Surface Detection and Siege Dispatch). If `security_surface: detected` AND `skip_siege: false`, OR if `force_siege: true`, dispatch `crucible:siege` in parallel with the first red-team round. The two skills proceed independently. The orchestrator awaits both before terminal verdict.
3. Prepares the artifact for review (see Artifact Preparation below)
4. Invokes `crucible:red-team` as a **single-pass reviewer** (one dispatch = one review round) via `subagent_type: crucible-red-team`, which pins this **single-model** red-team dispatch to **Opus** regardless of the orchestrator's own model (`agents/crucible-red-team.md`; the prose model line in `red-team/SKILL.md` is now descriptive only). On consensus-eligible rounds (Multi-Model Red-Team Review), the single-model dispatch is replaced by `consensus_query(mode: "review")`, whose model membership is resolved by the operator's `consensus_query` configuration — NOT by this pin. Quality-gate owns the iteration loop; red-team produces findings for one round and returns. Red-team does NOT run its own stagnation loop when invoked by quality-gate. If the harness reports that `subagent_type: crucible-red-team` fails to resolve (the agent defs are not installed on this machine — see `shared/harness-adapter.md` §8), the dispatch falls back to `general-purpose` on the orchestrator's inherited model and the Opus recall guarantee is **not** enforced; in that case the orchestrator emits a one-time visible warning ("agent type `crucible-red-team` not installed; the red-team is running on the inherited/session model — recall guarantee NOT enforced; install per harness-adapter §8") rather than degrading silently. The trigger is the observable type-resolution failure, not a transcript or metadata read.
5. If red-team finds **zero Fatal and zero Significant issues:** artifact is a *candidate* PASS — the round is candidate-clean, but the terminal verdict is deferred until look-harder verification completes. Order of operations on a candidate-clean round (0 Fatal, 0 Significant) — see `## Security Surface Detection and Siege Dispatch > Decision and Dispatch > Awaiting siege` for cross-reference:
   1. Await siege completion (if dispatched and still running) — see `## Security Surface Detection and Siege Dispatch > Decision and Dispatch > Awaiting siege`.
   2. If `SiegeVerdict != PASS`: skip look-harder + Minor Issue Handling, write verdict marker with `Verdict: ESCALATED, Reason: siege-blocked`, surface siege findings, and exit. Look-harder is SKIPPED entirely — the round was never going to be PASS.
   3. **Look-harder precedence gate.** Before invoking look-harder, evaluate Exit Precedence slots #3 (sustained-regression) and #4 (no-op-fix) per existing logic. (**This is a distinct mechanism from Exit Precedence's "Pre-precedence resolution" step at `## Escalation > Exit Precedence`** — that step is specifically the no-op → architectural re-dispatch path, run before precedence evaluation on rounds with active architectural candidates. The "Look-harder precedence gate" here is a much narrower check: it inspects whether a non-Clean-Pass slot would have won precedence on this candidate-clean round, and short-circuits look-harder if so.) A 0F/0S round cannot logically co-fire with sustained-regression (the weighted score on 0F/0S is 0, so `score(N) > score(N-1) > score(N-2)` cannot hold), but no-op-fix CAN co-fire (the fix agent may have returned a byte-identical artifact that the red-team also finds clean). If either slot fires, look-harder is SKIPPED ENTIRELY — the round was never going to be PASS. Look-harder is reached only when Clean Pass (slot #1) would otherwise win precedence.
   4. **Look-harder verification (Component 1 / #265).** Re-dispatch of red-team (`subagent_type: crucible-red-team`, the same enforced **Opus** pin as every red-team round — "same model" here means the pinned red-team model, NOT the orchestrator's) with the shared tightened-rubric addendum (`skills/quality-gate/tightened-rubric-addendum.md`) concatenated to `red-team-prompt.md` body by the orchestrator. The re-dispatch is the same model, same artifact, fresh dispatch — only the rubric is tightened; no prior-round context leaks (anti-anchoring preserved). Look-harder is SKIPPED on the following conditions; the orchestrator records `LookHarderSkippedReason` in the verdict marker and proceeds to sub-step 5:
      - **`circuit-breaker`** — global round 15 (runaway protection takes precedence; this matches the pre-precedence architectural re-dispatch behavior of the 15-round limit).
      - **`tail-rubric-already-applied`** — the candidate-clean round's red-team dispatch already carried `tail_rubric: true` (i.e., LOCAL round ≥ `ceil(suppression_threshold * 0.6)` on a `suppression_threshold ≥ 5` gate). The same-model re-dispatch with the identical addendum adds no signal beyond sampling variance.
      - **Already fired this chunk** — `look-harder-fired-on-round` is non-null in any prior `round-N-flags.md` of the in-progress chunk per the all-files recovery scan (see Compaction Recovery). Skip silently; no `LookHarderSkippedReason` recorded (the field is for circuit-breaker / tail-rubric-already-applied only).
      - **Co-fire precedence:** when BOTH `circuit-breaker` AND `tail-rubric-already-applied` apply simultaneously, `circuit-breaker` wins and is the recorded reason. (Note: co-fire is reachable on threshold-5 / threshold-6 gates where LOCAL round 15 is also a tail-rubric round; the precedence rule disambiguates regardless of frequency.)

      If look-harder is NOT skipped, dispatch as a fresh Task (same disk-mediated dispatch convention as every red-team round). Output is persisted to `round-N-look-harder.md`. Phase 2 of the write-ordering protocol (see below) updates `round-N-flags.md` with `look-harder-fired-on-round: <LOCAL N>` AFTER look-harder resolves.

      - If look-harder returns **0F/0S**: confirms the candidate-clean round. Execute Phase 2 of the write-ordering protocol (re-open `round-N-flags.md` and set `look-harder-fired-on-round: <LOCAL N>`, full-file replacement). Then proceed to sub-step 5 (Minor Issue Handling). `LookHarderFiredCount` is incremented; `LookHarderRounds` is NOT appended (only non-clean fires are listed).
      - If look-harder returns **Fatal/Significant**: the candidate-clean round is DEMOTED. The orchestrator MUST execute the following three writes **in strict order, with no other dispatches interleaved** (this ordering is load-bearing for recovery — see the Demotion crash-window rule below):
        1. Persist `round-N-look-harder.md` with the demoting findings.
        2. Overwrite `round-N-findings.md` with the look-harder findings (INV-A17) — the original 0F/0S findings file is replaced.
        3. Execute Phase 2 of the write-ordering protocol: re-open `round-N-flags.md` and set `look-harder-fired-on-round: <LOCAL N>` (full-file replacement).

        After step 3, the round becomes a normal non-clean round and proceeds to the fix loop (step 6 below). Do NOT re-dispatch siege — siege's prior verdict carries forward; the existing siege-await ordering applies on the next candidate-clean round without a fresh siege dispatch. The terminal sentinel `round-N-complete.md` is NOT written (round became non-terminal). `LookHarderFiredCount` is incremented and the round's LOCAL number is appended to `LookHarderRounds`. `round-N-look-harder.md` is retained as a separate telemetry artifact.

        **Stale-pin inertness (#366) — no supersession needed.** The candidate-clean PASS red-team receipt pinned the pre-overwrite `round-N-findings.md` sha256 in its `ARTIFACTS`; the INV-A17 overwrite makes that pinned hash **stale**. This stale pin is **inert** and needs **no `SUPERSEDES:`**: (a) the candidate-clean PASS receipt's Tier-2 ran **once at insertion** against the then-current file (pre-overwrite) and passed, and (b) no manifest-sweep step re-hashes a prior entry's pinned `ARTIFACTS` against disk after insertion (see the SP3 negative invariant in the invariant table) — so nothing ever reads the stale pin again. The demotion is recorded by the existing INV-A17 mechanism (the overwrite + the Phase-2 flags write), **not** by supersession: a demotion ("the prior clean verdict was wrong", whose witness MUST fire) is the opposite of supersession's semantics ("the prior concern no longer reproduces", whose witness must NOT fire), so `SUPERSEDES:` is the wrong primitive for a demotion. The look-harder FAIL receipt is therefore a normal fresh manifest entry, not a superseding one.

      Look-harder does NOT increment the gate's round counter (INV-A2). It is a verification step within slot #1; if it confirms, slot #1 stands; if it demotes, slot #1 is invalidated.

   5. Proceed to **Minor Issue Handling** (quick-fix pass on consolidated minors). Minor Issue Handling does not re-trigger siege — it operates on a known-passed artifact.
   6. After Minor Issue Handling: write final artifact to scratch directory, write verdict marker with `Verdict: PASS, Reason: clean-pass`, output consolidated Minor observations from all rounds (see Minor Issue Handling), surface pre-flight audit results (if any) alongside gate results, clean up, and return.

   **Write-ordering protocol (two-phase) for `round-N-flags.md` on candidate-clean rounds where look-harder fires:**

   1. **Phase 1 (end of red-team round, before look-harder dispatch).** Existing semantics. Write `architectural-candidates: [...]` per the Compaction Recovery section. Add the new key `look-harder-fired-on-round: null` to the same file in the same write.
   2. **Phase 2 (after look-harder dispatch resolves, immediately after `round-N-look-harder.md` is persisted).** Re-open `round-N-flags.md` via the Write tool, set `look-harder-fired-on-round: <LOCAL N>` (the LOCAL round number within the current chunk), and write back as a **full-file replacement** (same pattern as the convergence-log update — not append).

   On **non-candidate-clean rounds** (the round had Fatal/Significant), look-harder is not dispatched and Phase 2 is skipped; the key remains `null`. On **skipped look-harder** (circuit-breaker / tail-rubric-already-applied), Phase 2 is also skipped and the key remains `null`. Recovery interprets `null` as "look-harder not yet fired in this chunk, eligible to fire" and a populated value as "look-harder already fired in this chunk, skip per INV-T8."

   **Crash-window analysis.** If the orchestrator crashes between Phase 1 and Phase 2 (look-harder dispatch in flight), recovery scans all `round-N-flags.md` files in the in-progress chunk's directory and sees `null` for the in-flight round. Recovery re-dispatches look-harder. Look-harder is protocol-safe to re-run (same model, same artifact, fresh framing) because no fix dispatch has yet consumed the first dispatch's findings — the second dispatch's findings are authoritative. `round-N-look-harder.md` is overwritten by the re-dispatch; this is the documented exception to the "no overwrites" convention for round-N artifacts.

   **Demotion crash-window rule.** The strict write order (1: persist look-harder findings, 2: overwrite findings, 3: Phase 2 flags) collapses the demotion crash window onto Phase 2: if Phase 2 ran to completion, the findings overwrite is guaranteed to have happened before it. Recovery therefore treats `look-harder-fired-on-round: <N>` (Phase 2 populated) as authoritative evidence that the demotion's findings-overwrite (INV-A17) also completed; no separate consistency check is required. If recovery instead observes `round-N-look-harder.md` present AND Phase 2 still `null`, the crash landed between step 1 and step 3, and recovery step 6b's "re-dispatch look-harder" path applies — which transparently re-runs steps 1-3 in order. **Out-of-order writes are forbidden**: an orchestrator MUST NOT, for example, write Phase 2 before overwriting findings, or skip step 2 entirely. The recovery semantics depend on step ordering being honored.
6. If red-team finds Fatal or Significant issues:
   a. Dispatch a **separate fix agent** (see Fix Mechanism below) — receive revised artifact, append to fix journal
   b. Dispatch **Fix Verifier** (see Fix Verification below) — one Sonnet check per fix round
   c. Append verifier output to fix journal under `### Verifier Assessment` heading; write verdict summary to `round-N-verification.md`
   d. If Fatal-severity Unresolved: flag as "prior unresolved Fatal — must address" in next round's fix dispatch (binding, one-round grace)
   e. If Significant-severity Unresolved: appended to fix journal as informational context
   f. Invoke a FRESH red-team on the revised artifact (no anchoring)
7. Track weighted score between rounds (Fatal=3, Significant=1):

   **Score source (#366).** The weighted score is computed by the **orchestrator counting the cited findings file's `### Fatal Challenges` / `### Significant Challenges` sections** (the entries under each heading) — **not** from the receipt's CLAIMS. The receipt's `SEVERITY-COUNTS:` line and CLAIMS `*-count=` values are **reviewer-declared cross-checks**: on disagreement with the orchestrator's own section count, the orchestrator **trusts its own count for scoring and flags the discrepancy** in the narration log. This keeps the score un-spoofable — a fabricated declared count cannot move it. The receipt's role is narrower than the score: trust-check VERDICT boundary, supersession anchor (`:56`), tripwire participation (`:44`), and hash-pinned findings artifact.

   **Findings path & writer-inversion (#366).** The `[FINDINGS_OUTPUT_PATH]` is **orchestrator-supplied**: the orchestrator supplies it = the round's `round-N-findings.md` path when it composes the red-team dispatch (it already owns that path). The red-team reviewer is now the **initial writer** of `round-N-findings.md` (it `WROTE`s the file; the receipt's TRACE carries that write) — QG no longer transcribes the reviewer's prose return into that file; it only **reads** the cited artifact (for fix-agent context, the stagnation judge, and look-harder/persistence diffs). The prepended `SEVERITY-COUNTS:` first line is benign for the persistence-checker (it matches findings by title/root-cause, not line number) and tolerated by the look-harder format.

   - **Strictly lower score** → progress, loop again
   - **Same or higher score** → dispatch the Stagnation Judge (see Stagnation Detection below)
8. Read the judge's verdict and act on it (see Stagnation Detection below). See `## Stagnation Detection > Persistence Check` for the orchestrator step that runs BEFORE judge dispatch (Component 4 / #265), and `## Stagnation Detection > Verdict-Level Promotion` for the post-judge promotion step that may convert a `PROGRESS` verdict to `STAGNATION, Reason: persistent-finding-corroborated`.
9. **Progress notification.** After round `ceil(suppression_threshold / 2)` and every `max(1, suppression_threshold // 3)` rounds thereafter (rounds 5, 8, 11, 14 for threshold 10; rounds 2, 3, 4, ... for threshold 3), emit: "Quality gate round [N]: score progression [list]." If the judge was dispatched, append recurring/new counts. Informational only — no pause. (Start round uses `ceil` — rounds up — so the first notification lands no earlier than the midpoint; cadence uses `max(1, // 3)` — floors with a 1-minimum — so worked examples match: threshold 10 yields cadence 3, threshold 3 yields cadence 1.)
10. **Pre-threshold escalation suppression.** Before round `suppression_threshold` (default 10 for code/design/plan; 3 for hypothesis/mockup/translation — see Skill Arguments), the gate does NOT escalate to the user for stagnation, diminishing returns, or single-round regression. These signals are suppressed in favor of continued iteration — most artifacts converge to 0 Fatal / 0 Significant within a few rounds, and early escalation interrupts the user before that convergence has a chance to happen. The stagnation judge is NOT dispatched on rounds 1 through `suppression_threshold - 4` (i.e., rounds 1-6 for threshold 10). On rounds `max(1, suppression_threshold - 3)` through `suppression_threshold - 1` (rounds 7-9 for threshold 10), **and only when `suppression_threshold ≥ 6`**, the judge runs in silent mode to seed comparison history (see Stagnation Detection > Judge Dispatch). For thresholds < 6 (hypothesis, mockup, translation defaults), there are no silent-seed rounds — the judge dispatches only at round ≥ `suppression_threshold` in normal mode. Regression detection is recorded in the round notes but does not escalate on a single round.

    **Sustained-regression hard exit (convergence guarantee).** Pre-threshold suppression does NOT extend to a regression that persists across two consecutive rounds. If `score(N) > score(N-1)` AND `score(N-1) > score(N-2)` (i.e., weighted score has strictly increased two rounds running), the gate escalates immediately regardless of round number. Report: "Sustained regression detected: scores [N-2: X, N-1: Y, N: Z] strictly increasing. Fix cycle is actively worsening the artifact. Escalating." This rule guarantees loop termination even under suppression — without it, an oscillating fix agent (score 4 ↔ 5 ↔ 4) could burn rounds 1-9 with zero progress. Two consecutive strict increases is a structural signal that no further looping will help; one increase remains suppressed because single-round noise is expected during convergence.

    The only pre-threshold exits are: clean pass (0 Fatal, 0 Significant); architectural concerns declared via the fix agent's `VERDICT: ARCHITECTURAL_BLOCK` receipt (see Architectural Concerns Exit); sustained-regression hard exit (defined above); no-op fix detection (see Fix Mechanism > No-Op Fix Detection); consensus-stagnation pre-threshold escalation (ONLY when `consensus_query` is available; see Pre-Threshold Consensus Carve-Out); or explicit user interrupt (including the interactive check-in's "escalate now" response, see Skill Arguments). Beginning at round `suppression_threshold`, normal escalation logic applies (stagnation judge, single-round regression escalation, diminishing returns). When two or more exits would fire on the same round, apply the precedence rules in Escalation > Exit Precedence (first match wins).
11. **Global safety limit: 15 rounds.** This is a runaway protection circuit-breaker. If you hit 15, escalate to user with full round history. This limit applies regardless of the `suppression_threshold` rule.

### Tail-Rubric Flag (Component 2 / #265)

**Trigger.** The orchestrator computes `tail_rubric: true` for a red-team dispatch IFF:

- `suppression_threshold ≥ 5`, AND
- the current LOCAL round number ≥ `ceil(suppression_threshold * 0.6)`.

For default thresholds in the enabled range:

- `suppression_threshold = 10` (code/design/plan) → trigger at LOCAL round 6.
- `suppression_threshold = 6` → trigger at LOCAL round 4.
- `suppression_threshold = 5` (cross-chunk integration round) → trigger at LOCAL round 3 (`ceil(5*0.6) = 3`).
- `suppression_threshold ∈ {3, 4}` → tail-rubric DISABLED. The flag is **never** set on these gates regardless of round number (INV-T3).

**Counter selection.** The tail-rubric uses the LOCAL (per-chunk) round number, consistent with `suppression_threshold`, consensus cadence, look-harder, and silent-seed. Late chunks do NOT automatically have tail-rubric active from round 1 — each chunk's local counter governs.

**Action.** When `tail_rubric: true`, the quality-gate orchestrator **concatenates `skills/quality-gate/tightened-rubric-addendum.md` to the `red-team-prompt.md` body BEFORE Task dispatch**. This is the SAME addendum file used by look-harder (Component 1); one source of truth, two trigger paths. `red-team-prompt.md` itself is **not modified** — the orchestrator is the sole appender (INV-A4). Standalone red-team invocation (i.e., red-team called outside of quality-gate) does NOT use the addendum.

The dispatch file written by the orchestrator records `tail_rubric: true` so the candidate-clean-round look-harder skip condition (`tail-rubric-already-applied`) can read it from disk after the round completes.

**Cross-chunk integration coverage.** The cross-chunk integration round runs with `suppression_threshold = 5` (see Chunked Gate Counter Semantics). The tail-rubric trigger at threshold 5 (LOCAL round 3+) ensures the integration surface — which carries cumulative residual risk from all chunks — benefits from late-round rubric tightening.

**Interaction with the existing inflation check.** The `red-team-prompt.md` body already has an inflation check on its severity rubric. The tail-rubric addendum **tightens** that check round-conditionally; it does not replace it. Early rounds use the existing rubric unchanged; tail rounds layer the shared addendum on top.

### Multi-Model Red-Team Review (when available)

**Applies to:** Round 1, and every `max(1, suppression_threshold // 3)` rounds thereafter, up to round 15. For the default `suppression_threshold` of 10, this yields cadence 3 → rounds 1, 4, 7, 10, 13. For `suppression_threshold` of 3 (hypothesis/mockup/translation), this yields cadence 1 → rounds 1, 2, 3 (effectively every pre-threshold round — short-threshold artifacts have less room to converge, so multi-model coverage on every round is justified). The `max(1, ...)` floor handles thresholds 1-2 (rare) by collapsing to cadence 1.
**Intermediate rounds:** Standard single-model red-team dispatch (no change).
**Tail-rubric and consensus rounds:** When `tail_rubric: true` AND the round is consensus-eligible, the orchestrator concatenates the tightened-rubric addendum to the prompt body passed to `consensus_query(mode: "review")` the same way it does for single-model dispatch. Consensus participants see the tightened rubric uniformly; per-model variance applies to the tightening, not its presence.

On consensus-eligible rounds:
1. Instead of dispatching a single red-team subagent, call `consensus_query(mode: "review")` with the red-team prompt and artifact content
2. The consensus response provides merged findings with per-finding severity (Fatal/Significant/Minor), confidence (High/Medium/Low based on model agreement), provenance (which models raised it), and unique findings flagged as "potentially novel"
3. The orchestrator processes these findings exactly as single-model findings: compute weighted score, compare to prior round, dispatch fix agent if needed
4. Findings from consensus rounds include provenance metadata in `round-N-findings.md`

**Cost control:** The consensus dispatch replaces (not supplements) the single-model dispatch on eligible rounds.
**Fallback:** If consensus is unavailable on an eligible round, dispatch standard single-model red-team review.

**At-threshold consensus (when consensus round == `suppression_threshold`):** Consensus dispatches normally and produces findings; the orchestrator computes the weighted score from those findings; the standard Multi-Model Consensus path in Stagnation Detection (single-judge dispatch replaced by `consensus_query(mode: 'verdict')`) consumes those findings for the stagnation judgment. The Pre-Threshold Consensus Carve-Out does NOT apply at-or-above threshold — `agreement_level` becomes informational metadata only at that point.

### Pre-Threshold Consensus Carve-Out

Consensus-eligible rounds inside the suppression window (i.e., consensus-eligible rounds < `suppression_threshold`) — for the default threshold of 10, these are rounds 4 and 7 — fall inside the suppression window. The red-team consensus dispatch still runs on these rounds and produces findings — but normally the stagnation signal it implies (e.g., score didn't improve) is suppressed.

**Carve-out:** When a consensus-mode red-team dispatch on a pre-threshold round returns findings whose Fatal+Significant count is identical to the prior round's AND the weighted score did not strictly decrease AND the consensus aggregator reports `agreement_level >= 0.75` (75% of responding models converged on the same finding set), the orchestrator escalates immediately with verdict `ESCALATED`, reason "consensus-stagnation-pre-threshold". Report:

> "Multi-model consensus at round N shows persistent findings with high model agreement (75%+). Suppression overridden — unanimity is stronger signal than the threshold heuristic. Escalating."

This preserves the value of the pre-threshold consensus investment without giving every consensus call escape-hatch power. Without the carve-out, those rounds pay full consensus cost for signal the loop is contractually deaf to.

**Fallback:** If `agreement_level` is unavailable in the consensus response, treat as < 0.75 (do not escalate).

**Round-1 exclusion.** The carve-out requires at least one prior round of findings for the "identical to the prior round's" comparison. It does NOT fire on Round 1, regardless of `suppression_threshold`. For `suppression_threshold ≤ 3`, this means the earliest carve-out is Round 2 (consensus rounds 1, 2, 3; pre-threshold rounds 1 and 2; round 1 excluded by this rule); for `suppression_threshold = 10`, the earliest carve-out is Round 4 (consensus rounds 1, 4, 7, 10; round 1 excluded). In all cases Round 1 is structurally ineligible because no prior-round comparison exists.

## Cost-Cap and Diminishing-Return Signals (#303)

Two advisory signals layered over existing escalation paths. Neither introduces a new termination path; both are advisory-only in v0.1 — they surface cost/diminishing-return information to the user but never change the gate's verdict or loop behavior.

### Per-Round Ledger

After each red-team round returns findings, the orchestrator writes `round-N-ledger.md` to the gate scratch directory. v0.1 enumerates every Fatal/Significant finding under `## Accepted`. The `## Deferred` section is present but always empty in v0.1 (no triage; deferral activates in v1.0 once corpus matures — see issue #305).

Emission is unconditional and independent of `cost_cap_threshold` / `dr_signal_findings`. Threshold-3 artifacts get the ledger but no prompts.

**Ledger format:**

```markdown
# Round N Ledger

Artifact-type: <code | hypothesis | mockup | translation>
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

On gate termination (any verdict), the orchestrator emits a single summary line in the dispatch return to the parent skill:

```
CostCapSignals: <DR-fire-count>+<cost-cap-fire-count>/<rounds>
```

Example: `CostCapSignals: 0+2/4` (zero DR fires, two cost-cap fires, four rounds). This gives the parent skill (build, spec, debugging) a structured signal without changing termination behavior. The same value appears as a verdict-marker field (see Verdict Marker spec below).

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

The fix agent (the design / plan / code / mockup / translation rows above) is dispatched with `subagent_type: crucible-qg-fix`, which **inherits the session model** (`agents/crucible-qg-fix.md`) — the fix output is re-reviewed by the now-Opus red-team each round, so a weaker fixer costs at most an extra round, never a missed bug; do not pass a call-level `model:`. (The `hypothesis` row is the one exception — it routes to the **debugging skill's own** hypothesis-refinement agent, not `crucible-qg-fix`; that agent is outside this skill's surface.) The fix agent receives: (a) the current artifact, (b) the red-team findings, (c) project context, and (d) the **fix journal** from prior rounds (see Fix Memory below). It returns the revised artifact. The orchestrator writes the revised artifact to the scratch directory and dispatches the next red-team round.

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

**Dispatch method:** Task tool, `subagent_type: crucible-qg-verifier` (the agent def pins **Sonnet** — `agents/crucible-qg-verifier.md`; do not pass a call-level `model:`), same pattern as the stagnation judge. The verifier needs no file access; the orchestrator includes all input in the dispatch file directly.

**Input the orchestrator provides:**
1. Round N findings (the findings the fix agent was asked to address)
2. The current round's fix journal entry only — the `## Round N Fix` section just appended (not the full journal)
3. Prepared artifact:
   - Non-code (design docs, plans, hypotheses, mockups, translations): post-fix version in full
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

## Stagnation Detection

A single stagnation pipeline with three optional model tiers, all gated by `suppression_threshold`:

1. **Orchestrator first-pass (always runs)** — local arithmetic check on weighted score and Fatal count. Cheapest; deterministic; runs every round but only escalates at round ≥ threshold (with sustained-regression and no-op-fix as the at-any-round exceptions).
2. **Sonnet stagnation judge (runs at round ≥ threshold - 4, silent until threshold)** — semantic comparison of finding sets across rounds. Verdict: PROGRESS / STAGNATION / DIMINISHING_RETURNS. Silent dispatches seed comparison history (see Judge Dispatch).
3. **Multi-model consensus (runs on Round 1 and every `max(1, suppression_threshold // 3)` rounds thereafter up to round 15, when consensus_query available)** — cross-model verdict on the same comparison inputs. Higher confidence; carries pre-threshold escalation power via the consensus carve-out (see Pre-Threshold Consensus Carve-Out).

The three tiers share the same trigger (same-or-higher weighted score, no Fatal improvement) but produce distinct signals at different cost points. The orchestrator first-pass is the always-on rail; the judge adds semantic recurring/new classification; consensus adds cross-model unanimity weighting. Each tier's verdict is reflected in `round-N-score.md` and `round-N-comparison.md` regardless of whether it escalates.

### First-Pass Check (orchestrator — runs every round)

Stagnation uses **weighted scoring** (Fatal=3, Significant=1) AND **Fatal count tracking**.

**Progress requires EITHER:**
- Weighted score strictly lower than prior round, OR
- Fatal count strictly lower AND weighted score same-or-lower

If either condition is met → progress, loop again. No judge needed.

**Pre-threshold gating.** Before round `suppression_threshold`, the single-round regression and stagnation paths below do NOT escalate. Record the signal in `round-N-score.md` for audit purposes and continue looping. The single-round-regression check below applies only at round `suppression_threshold` and later. (See Skill Arguments for threshold defaults and overrides.)

**Sustained-regression hard exit (applies at every round, including pre-threshold).** If `score(N) > score(N-1)` AND `score(N-1) > score(N-2)` — two consecutive strict score increases — escalate immediately as a sustained regression. This rule overrides pre-threshold suppression and guarantees loop termination. Requires at least 3 rounds of history (skip on rounds 1 and 2). See How It Works step 10 for rationale.

**Oscillation detection (round ≥ `suppression_threshold`):** If the weighted score *increases* (not just stays the same) for a single round, escalate immediately as a **regression**. Report: "Round N score (X) is higher than Round N-1 score (Y). The fix cycle introduced new issues. Escalating." No judge needed.

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

1. Instead of dispatching a single judge via Task tool (`subagent_type: crucible-qg-judge`), call
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
     - Fall back to the single-judge dispatch (`subagent_type: crucible-qg-judge`, see
       **Judge Dispatch → Dispatch method**)

3. The comparison file (`round-N-comparison.md`) includes the consensus
   metadata: models queried, models responded, agreement level, and any
   dissenting verdicts.

### Persistence Check (Component 4 / #265)

The orchestrator dispatches a **persistence checker** between a non-clean red-team round's receipt and the stagnation judge's dispatch, **conditional on cross-channel corroboration triggers**. The stagnation judge itself is UNCHANGED — its 4-data-input set (plus the prompt itself) and procedure are preserved verbatim. The persistence signal is applied as an orchestrator-layer verdict-level promotion AFTER the judge returns (see Verdict-Level Promotion below).

**Counter selection.** For chunked gates, "round N" and "round N+1" in this section refer to LOCAL round numbers within the in-progress chunk (consistent with `suppression_threshold`, look-harder, tail-rubric, consensus cadence, and the stagnation judge). Cross-chunk persistence checking is NOT performed — each chunk's persistence-checker fires only against the prior LOCAL round of the same chunk. The marker / convergence-log encoding for persistence rounds uses the canonical `<chunk_id>:<local_round>` grammar per INV-A15.

**Trigger (INV-A10).** The persistence checker fires on every non-clean red-team round N+1 where ALL of:

- Round N's fix-journal entry's `### Verifier Assessment` sub-section contains **≥1 finding with verdict `Unresolved`** (the verifier's per-finding vocabulary is exactly `Resolved` | `Unresolved` per `fix-verifier-prompt.md`). Partial-Unresolved (some Resolved, some Unresolved) fires it; full-Resolved SKIPS it (symmetric leverage — converging runs bypass the mechanism entirely); full-Unresolved fires it.
- Both `round-N-findings.md` AND `round-(N+1)-findings.md` exist on disk.

**Verifier-error rounds** (where the round-N fix-verifier dispatch failed or its `### Verifier Assessment` sub-section is malformed/absent) implicitly skip the persistence checker per fail-open semantics — the `≥1 Unresolved` gate is vacuous, so the trigger does not fire. The F1 promotion is also skipped (vacuous gating on condition (d) below).

**Dispatch.** When the trigger fires, dispatch the persistence checker as a fresh Task with `subagent_type: crucible-qg-verifier` (reused — both the fix verifier and the persistence checker are Sonnet mechanical structural checks; the agent def pins **Sonnet**, `agents/crucible-qg-verifier.md`; do not pass a call-level `model:`) and `persistence-checker-prompt.md` as the prompt. The persistence checker emits a JSON correspondence object, not an Evidence Receipt — the shared `crucible-qg-verifier` def is deliberately return-format-neutral so it does not conflict with that (the persistence checker is not a receipt-bearing role — its JSON is consumed directly by the orchestrator, written to `round-(N+1)-persistence.md` per the flow below, and is NOT run through the receipt linter; this is a pre-existing exemption that #352 does not change). Inputs supplied verbatim by the orchestrator:

1. `round-N-findings.md` (prior round's findings)
2. `round-(N+1)-findings.md` (current round's findings)
3. The round-N fix-journal entry — **full entry**, including both the `## Round N Fix` agent-authored sub-section AND the `### Verifier Assessment` verifier-authored sub-section. Both sub-sections live in the remediation path and never leak to the red-team.

The persistence checker performs a **structural diff** — not an adversarial review. It produces only correspondence judgments between round-(N+1) findings and the round-N `Unresolved` set. Output is a JSON object (see `persistence-checker-prompt.md` for schema) written to `round-(N+1)-persistence.md` BEFORE the stagnation judge dispatches on round N+1.

**Failure modes (fail-open).** If the persistence checker fails (Task error, malformed output): record `status: error` in `round-(N+1)-persistence.md`, treat `persistent_finding_count: 0`, and proceed to standard stagnation judge dispatch. The orchestrator does NOT retry a failed persistence-checker dispatch within the same round. Error dispatches DO count toward `PersistentCheckCount` (the dispatch happened); only the resulting `persistent_finding_count` is treated as 0.

**Data flow guarantees (anti-anchoring preservation, INV-A11).** Persistence-checker output flows ONLY to the orchestrator (read path between judge dispatch and verdict marker write). It NEVER flows back into the red-team prompt on subsequent rounds. It NEVER flows into the stagnation judge's input set. The persistence checker itself sees only the three inputs above; it never receives prior-round content beyond round N, the orchestrator's state machine, or the artifact bytes.

### Judge Dispatch (silent-seed at round ≥ `max(1, suppression_threshold - 3)` when `suppression_threshold ≥ 6`; normal escalation at round ≥ `suppression_threshold`)

**Rounds `1` through `max(0, suppression_threshold - 4)`:** Skip judge dispatch entirely. Loop again regardless of score trajectory. The `max(0, ...)` clamp handles short thresholds: for `suppression_threshold ≤ 4` the upper bound clamps to 0 (no rounds are skipped — judge dispatches normally starting at the threshold). For threshold 10: rounds 1-6 skipped. For threshold 3: no rounds skipped; judge runs from round 3 onward.

**Seed rounds (rounds `max(1, suppression_threshold - 3)` through `suppression_threshold - 1`, only when `suppression_threshold ≥ 6`):** When the first-pass check would trigger stagnation (same-or-higher score AND no Fatal count improvement), dispatch the judge in **silent mode**. For `suppression_threshold ≤ 5` there are no seed rounds. For threshold 10 this is rounds 7-9. Silent mode is identical to normal dispatch except:
- The judge's verdict (PROGRESS/STAGNATION/DIMINISHING_RETURNS) is logged to `round-N-comparison.md` but does NOT route to the user
- A `silent-mode: true` line is appended to the comparison file
- The orchestrator loops again regardless of verdict
- The judge's `suppressed-signal` reading is mirrored into `round-N-score.md` (e.g., `suppressed-signal: stagnation-would-fire`)

Silent dispatch seeds the consecutive-round comparison history that the judge's prompt expects. Without seeding, the at-threshold judge runs with no prior comparison files and the consecutive-round semantics never engage until two rounds later — leaving few escalation-eligible rounds before the 15-round limit.

**Dispatch boundaries by threshold:**

| `suppression_threshold` | Skip range | Seed range (silent) | First normal dispatch |
| --- | --- | --- | --- |
| 3 | none (clamped to 0) | none | round 3 |
| 4 | none (clamped to 0) | none | round 4 |
| 5 | round 1 only | none | round 5 |
| 6 | rounds 1-2 | rounds 3-5 | round 6 |
| 10 | rounds 1-6 | rounds 7-9 | round 10 |

For thresholds 3-5 the short window means no silent-seed pass is feasible; the judge dispatches at the threshold with whatever comparison state exists. For threshold ≥ 6 the full skip-then-seed-then-normal pattern applies.

**Short-threshold behavior note (thresholds 4 and 5):** The silent-seed window only opens at `suppression_threshold ≥ 6`. For thresholds 4 and 5, the at-threshold judge dispatches without any prior `round-*-comparison.md` history. The judge's "recurring-Significant for 2 consecutive rounds" rule requires comparison history; with none, the judge's fail-open default classifies findings as PROGRESS or New rather than recurring, making STAGNATION effectively unreachable on the first at-threshold round. By round `threshold+1`, one comparison file exists and the judge can detect stuck patterns normally. This is an intentional trade-off: short-threshold artifacts (hypothesis/mockup/translation in particular) prioritize fast convergence over early stagnation detection.

**At round `suppression_threshold` and later, if neither progress condition is met AND the score did not increase** (i.e., same score, no Fatal count improvement), dispatch the **Stagnation Judge** — a dedicated Sonnet agent that performs semantic comparison of findings across rounds. If the `consensus_query` tool is not available in the environment, this step uses the standard single-Sonnet dispatch described below.

**Dispatch method:** Task tool, `subagent_type: crucible-qg-judge` (the agent def pins **Sonnet** — `agents/crucible-qg-judge.md`; do not pass a call-level `model:`). The judge needs no file access; the orchestrator includes all input in the dispatch file directly.

**Input the orchestrator provides:**
1. The content of `round-N-findings.md` (current round)
2. The content of `round-(N-1)-findings.md` (prior round)
3. The latest fix journal entry only — extract the last `## Round N Fix` section from `fix-journal.md` (not the full journal)
4. The content of any prior `round-*-comparison.md` files (for consecutive-round state tracking)
5. The full content of `stagnation-judge-prompt.md` as the agent's instructions

**Reading the verdict:** The judge returns a structured verdict: **PROGRESS**, **STAGNATION**, or **DIMINISHING_RETURNS**. The orchestrator **parses the judge's `DR-Cause:` line the same way it parses the `Verdict:` line**, writes the resolved value into `round-N-comparison.md`, and uses it for (a) selecting the DIMINISHING_RETURNS user-facing message below and (b) the convergence-log `dr_cause` field (`none → null` on write — see Convergence Telemetry).
- **PROGRESS** → loop again
- **STAGNATION** → escalate: "Stagnation detected: Round N has [X] recurring issues from round N-1 and [Y] new issues. Recurring: [list from judge]. Escalating."
- **DIMINISHING_RETURNS** → escalate, with the message **keyed off `DR-Cause`** (the judge emits which cause fired; the orchestrator — not the judge — composes the matching user-facing message). `minor-accumulation` is the only special arm; everything else routes to the default message so every DR exit has a defined message:
  - When `DR-Cause = minor-accumulation` → "Quality gate: Minors are accumulating at a flat score while Fatal/Significant findings still churn without converging. Recurring Minors: [list from judge]. This is user-judgment, not a forced fix loop (Minors never trigger fix rounds). Presenting for user judgment."
  - Otherwise (`structural-saturation`, `consensus`, or absent/unattributable) → "Quality gate has resolved all prior issues. Round N found [X] new findings, all Structural (require design-level decisions). Remaining findings: [list from judge]. Presenting for user judgment."

**The judge also writes:** a `round-N-comparison.md` file. The orchestrator saves the judge's full output as `round-N-comparison.md` in the scratch directory. This file is used by future judge dispatches for consecutive-round tracking.

### Verdict-Level Promotion (Persistent Finding Corroboration, Component 4 / #265)

After the stagnation judge returns its verdict (PROGRESS / STAGNATION / DIMINISHING_RETURNS), **and after the existing Pre-precedence resolution step** (no-op → architectural re-dispatch), the orchestrator applies one promotion step that consumes the persistence-checker output:

**Promotion condition (F1 / INV-A10 / INV-T14).** If ALL of:

a. `persistent_finding_count ≥ 1` (read from `round-(N+1)-persistence.md`); AND
b. current round ≥ `suppression_threshold`; AND
c. the judge's verdict is `PROGRESS`; AND
d. round N's verifier had **≥1 `Resolved` finding** (NOT fully no-op — i.e., the fix attempted real work and still left a persistent finding);

then promote to `Verdict: STAGNATION, Reason: persistent-finding-corroborated`. The promoted STAGNATION verdict is then consumed at **precedence slot #7** (the standard stagnation-judge consumption slot — see Exit Precedence).

**Threshold rationale (persistent_finding_count ≥ 1).** The single-match threshold is deliberate but rests on the checker's documented conservativeness, not on the orchestrator side alone. The asymmetry is: a false-positive `high` correspondence promotes PROGRESS to STAGNATION, costing the user a real escalation; a false-negative `high` correspondence simply means the promotion fires on a later round when the same root cause persists. The checker's prompt mandates "when in doubt between `high` and `medium`, choose `medium`" and `medium` does NOT count toward `persistent_finding_count`, so a single `high` is by construction a high-confidence structural match against a verifier-`Unresolved` round-N finding. The orchestrator does NOT add a second independent verification of the correspondence — the prompt's conservativeness is the upstream guard. If empirical data (after ≥30 marker_version=2 entries; see Open Questions) shows false-positive `high` correspondences driving incorrect F1 promotions, the threshold should be raised to `≥ 2` or a second-channel corroboration check added; this is the canonical revisit trigger.

**Mutex with no-op exit (anti-double-counting).** Condition (d) prevents mechanical over-firing on no-op rounds. When round N's verifier marked ALL findings `Unresolved` (i.e., a no-op fix per Fix Mechanism → No-Op Fix Detection), the no-op exit (precedence slot #4) is the authoritative cause — F1 promotion would mechanically over-fire because the persistence checker is GUARANTEED to find correspondences when the fix didn't change anything. F1 fires only when the fix attempted real work and still left a persistent finding.

**Precedence interaction.** Precedence slots #2-#6 (ARCHITECTURAL_BLOCK, SUSTAINED_REGRESSION, no-op fix, consensus-stagnation pre-threshold, 15-round circuit-breaker) continue to outrank a promoted STAGNATION when they co-fire on the same round — `persistent-finding-corroborated` is recorded under `CoFiredExits` in those cases. See Exit Precedence for the full ordering and `CoFiredExits` semantics.

**Rationale.** Surface/Structural is a per-finding class that the judge tags only in its **All-new** branch. Persistent findings are by construction Recurring (they match prior-round findings whose verifier verdict was `Unresolved`), so the judge enters its All-recurring or Mixed branch — where Surface/Structural is never tagged — and a classification-level override would have nothing to apply. The persistence signal is therefore promoted at the orchestrator layer, not via classification override.

The stagnation judge's own output is unchanged in both fire and no-fire cases (the judge still wrote `PROGRESS`); the promotion happens entirely in orchestrator post-processing.

## Artifact Preparation

### Small artifacts (design docs, plans, hypotheses, mockups, translations)

Pass the full artifact content to the red-team subagent. No preparation needed.

### Code artifacts

Code artifacts vary in size. The orchestrator prepares the artifact based on scope:

- **Small implementations (<500 lines diff):** Pass the full diff + any new files in full.
- **Medium implementations (500-2000 lines):** Pass full source of high-risk files (new files, files with complex logic changes) + summaries of routine changes (imports, wiring, boilerplate). Include a change manifest listing all files with 1-line descriptions.
- **Large implementations (>2000 lines):** Split into logical chunks (by subsystem, module, or feature boundary). Run a quality gate on each chunk, then a final cross-chunk round reviewing the integration points. Present the chunking plan to the user before proceeding. See Chunked Gate Counter Semantics below for how round numbering, consensus cadence, and the suppression threshold apply across chunks. **Chunked compaction recovery:** Use a parent run-id for the entire chunked gate. Write `chunk-manifest.md` (lists all chunks with gated/pending status) to the parent scratch directory. Per-chunk round files go in `chunk-N/` subdirectories. Only delete the parent scratch directory after the final cross-chunk round completes. The `active-run.md` marker references the parent run-id throughout.

**Grudge pre-flight (regression-oracle, #271).** On round 1, query the **Book of Grudges** for the gated files and include any matches in the red-team dispatch context as known prior regressions to check against — a reviewer should weight a past grudge on a touched file heavily. Resolve the helper by absolute path from the plugin root — `plugin_root="$(realpath "<this-skill-base-dir>/../..")"` — and run `python3 "$plugin_root/scripts/grudge_query.py" <gated files…> --with-signatures`. Best-effort: if unresolved, emit a one-line stderr warning and continue — a missing pre-flight must NEVER block the gate. See `skills/grudge/SKILL.md`.

### Chunked Gate Counter Semantics

A chunked gate has two independent round counters: a **local** counter per chunk (resets to 1 at each chunk start) and a **global** counter (monotonic across all chunks). These counters drive different mechanisms; the spec made them collide before this section was added.

| Mechanism | Counter | Rationale |
|---|---|---|
| `suppression_threshold` | **local** (per chunk) | Each chunk is conceptually its own artifact converging from scratch; the convergence economics that justify a 10-round trust window apply per chunk, not globally. |
| Consensus cadence (every `max(1, suppression_threshold // 3)` rounds, starting at 1) | **local** (per chunk) | Each chunk's round 1 deserves multi-model review; otherwise chunks 2+ never get consensus coverage. |
| Stagnation judge dispatch | **local** (per chunk) | The judge's "consecutive-round comparison" semantics are about within-chunk convergence, not cross-chunk drift. |
| Silent-seed judge dispatches (rounds threshold-3 to threshold-1) | **local** (per chunk) | Same reason — comparison history is per-chunk. |
| 15-round safety limit | **global** (across all chunks) | This is runaway-protection circuit-breaker. If a 3-chunk gate is on round 16 globally, something is wrong; force escalation. |
| `Rounds` field in verdict marker | **global** | Downstream consumers need total cost signal. |
| `ScoreTrajectory` field | **global, with chunk boundary markers** | Format: `6,4,3,|,5,3,1,0,|,4,2,1` (pipes mark chunk boundaries). Lets forge analyze per-chunk and cross-chunk trajectory. |

**Cross-chunk round:** After all chunks complete, the final integration round increments the global counter but is conceptually its own "mini-chunk" with `suppression_threshold` = 5 (lower, because integration issues should escalate faster than within-chunk issues). Consensus is mandatory for the cross-chunk round (single-model review is too narrow for integration-surface bugs).

**Siege on chunked gates:** siege dispatches **once on the full artifact**, not per-chunk (see Security Surface Detection → Dispatch timing → Chunked-gate siege scope for the rationale and the chunk-local tradeoff).

**Canonical `chunk_id` grammar (INV-A15 / #265).** Chunk identifiers used in marker fields (`LookHarderRounds`, `PersistentFindingRounds`), convergence-log entries (`look_harder_rounds`, `persistent_finding_rounds`), and scratch directory names are restricted to TWO forms:

- `chunk-<N>` where `<N>` is a positive integer matching the chunk's directory name (`chunk-1`, `chunk-2`, ...). Used for author-defined chunks.
- `cross-chunk` — reserved string for the synthetic cross-chunk integration round.

**Gate-start validation.** At chunked-gate start, the orchestrator MUST refuse to begin if any author-chunk directory name does not match the regex `^chunk-[1-9][0-9]*$`. The reserved `cross-chunk` token explicitly avoids collision with user-chosen subsystem names (e.g., `integration` would be a valid directory name in some authors' systems but would collide with the integration round's semantic).

**Chunked-gate list-element encoding for new telemetry fields (INV-A15 / S6).** `LookHarderRounds` and `PersistentFindingRounds` are run-level lists in marker output; their elements differ between chunked and non-chunked gates:

- **Non-chunked gates:** bare integers — e.g., `LookHarderRounds: 3, 6`. The convergence-log uses bare integers in the JSON list.
- **Chunked gates:** `<chunk_id>:<local_round>` pairs (colon-separated) in the marker — e.g., `LookHarderRounds: chunk-1:3, chunk-2:5, cross-chunk:2`. The convergence-log encodes elements as JSON objects: `[{"chunk":"chunk-1","local_round":3},{"chunk":"chunk-2","local_round":5},{"chunk":"cross-chunk","local_round":2}]`.

Two chunks could each contribute a "round 3"; without chunk-coordinate qualification a flat integer list would be ambiguous. The same encoding applies to `PersistentFindingRounds` / `persistent_finding_rounds`.

**ArtifactHash and ChunkHash semantics on chunked gates.** `ArtifactHash` is the sha256 hex of the FULL pre-chunking artifact's bytes, computed once at gate start. Every per-chunk verdict marker AND the cross-chunk integration round's marker carry the **same** `ArtifactHash` — it identifies the artifact bytes across all chunks of a single gate run AND across multiple gate runs on the same content (regardless of chunking strategy). Forge consumers group markers by `ArtifactHash` for cross-run comparison, including the `tail-rubric-already-applied` revisit trigger.

`ChunkHash` is the sha256 hex of the specific chunk's bytes. It is present **only** on per-chunk markers in chunked gates; it is **omitted** from non-chunked-gate markers and from the cross-chunk integration round's marker. `ChunkHash` is internal-only for per-chunk recovery scenarios; `ArtifactHash` is the canonical cross-run identifier.

**Recovery semantics:** On compaction mid-chunked-gate, read `chunk-manifest.md` to recover chunk status. The local counter for the in-progress chunk is recovered by reading the highest N in `chunk-K/round-N-score.md`. The global counter is reconstructed by summing rounds across all completed chunks plus the in-progress chunk's local rounds. The look-harder all-files scan (see Compaction Recovery step 6a) operates strictly within the in-progress chunk's directory — never globs across chunks.

The red-team subagent receives the **prepared artifact**, not raw diff. This mirrors audit's Tier 1/Tier 2 context management approach.

### Hypothesis artifacts

Hypotheses are 1-2 sentence statements, not plans or designs. The red-team prompt template is plan-centric and does not map well to hypothesis testing. For hypothesis artifacts, the orchestrator frames the red-team dispatch with hypothesis-specific attack vectors:

- Does this hypothesis explain ALL observed symptoms?
- What evidence would disprove it?
- Are there simpler alternative explanations?
- What assumptions does this hypothesis make that could be wrong?

Include these in the dispatch prompt alongside the standard red-team template. The debugging skill's Phase 3.5 defines these questions -- the quality-gate orchestrator should use them.

## Minor Issue Handling

Minor issues still **do not enter the weighted score and never trigger fix rounds**, but the **stagnation judge may weigh sustained Minor accumulation** at round ≥ threshold (per D1 — see the Step 3 Mixed-branch Minor-accumulation rule in `stagnation-judge-prompt.md`). They accumulate across rounds and contain useful information. Do not silently discard them.

**After the gate completes** (artifact approved or stagnation escalated):

1. **Consolidate:** Collect all Minor observations from all rounds, deduplicate.
2. **Quick-fix pass:** Dispatch a fix subagent (`subagent_type: crucible-qg-fix`, same fix type as the main loop, so it inherits the session model — `agents/crucible-qg-fix.md`; do not pass a call-level `model:`) with the consolidated minors and the final artifact. The fix agent addresses easy wins only — changes that are simple, low-risk, and unambiguous (typos, naming inconsistencies, missing edge-case guards, trivial cleanup). It skips anything requiring judgment or design decisions.
3. **Present remainder:** Output any minors the fix agent skipped as "Remaining minor observations" so the user can decide whether to address them. No further red-team round on the quick fixes — the gate is already complete. (Because this post-pass quick-fix is **not** re-reviewed, its edits ship on the inherited model unverified — a bounded residual accepted in the #352 plan: blast radius is consolidated Minors on an already-passed artifact, and routing through `crucible-qg-fix` keeps it from becoming a silent escapee if the fix tier ever moves off `inherit`.)

## Pre-Flight Dependency Audit

**Extracted to `crucible:dependency-audit` (2026-05-16).** The dependency-vulnerability scanning logic formerly inlined here is now its own skill, invoked in parallel with quality-gate by the parent orchestrator (build, debugging, user session). It produces an independent supply-chain signal that is surfaced alongside quality-gate's verdict but does not feed into quality-gate's weighted score (preserves INV-2 — host red-team findings only).

**Migration note:** The `skip_blocking` and `min_blocking_severity` arguments no longer live on quality-gate; they belong to `crucible:dependency-audit`. Build dispatches both skills with their own arguments. Direct user invocations of `/quality-gate` no longer trigger pre-flight; users wanting both should invoke `/dependency-audit` separately or use `/build`.

**Anti-anchoring preserved:** As before, dependency-audit findings are NOT passed to red-team dispatch. The two skills share an artifact but produce independent signals.

See `skills/dependency-audit/SKILL.md` for the full audit specification (manifest scanning, ecosystem detection, severity normalization, output schema, recovery semantics).

## Security Surface Detection and Siege Dispatch

Some artifacts touch security-relevant surface and deserve a dedicated security audit pass alongside (not in place of) the red-team loop. Quality-gate inspects each artifact at gate start; when security signal is detected, it dispatches `crucible:siege` in parallel with the first red-team round. Siege runs its own attacker-perspective loop independently. The gate awaits both before declaring PASS.

This mirrors the dependency-audit pattern: siege is a sibling parallel skill, not a quality-gate phase. Findings flow back as an independent signal that blocks PASS but does not feed the weighted score (preserves INV-2).

### Detection Heuristic

Set `security_surface: detected` if ANY of the following signals fires:

**File path / project structure:**
- Path components matching: `auth/`, `crypto/`, `secrets/`, `tokens/`, `permissions/`, `sanitiz`, `validat`, `escape`, `csrf`, `xss`, `sqli`
- Test paths matching the same patterns (test files that exercise security code are themselves security-relevant)

**Code patterns (code artifacts):**
- Regex compiled from user input
- Shell exec with string interpolation (any of: `os.system`, `subprocess.*shell=True`, backticks, `eval`, `exec`)
- Deserialization without schema (pickle.loads, yaml.load without SafeLoader, JSON.parse-then-trust)
- SQL with string concatenation or f-string interpolation against user-controlled values
- File path joins where a path component is user-controlled (`os.path.join(base, user_input)` without sanitization)
- Password / token comparisons not using constant-time (`==` against secret material)
- Cryptographic primitives invoked directly (use of `hashlib`, `cryptography`, `crypto` libraries)

**Design / plan / hypothesis keywords:**
- Single-word match in artifact body: `authentication`, `authorization`, `cryptographic`, `cryptography`, `session token`, `API key`, `permission boundary`, `trust boundary`, `sandbox`, `privilege`, `RBAC`, `OAuth`, `SAML`, `JWT`, `CSRF`, `XSS`, `SQL injection`, `RCE`, `deserialization`, `path traversal`
- Two-word phrases: `user-supplied input`, `untrusted input`, `external input`, `attack surface`, `threat model`

**Dependency-audit signal:** If dependency-audit (running in parallel) flags Critical/High vulnerabilities in security-critical packages (auth libraries, crypto libraries, web frameworks), promote to `security_surface: detected` even if no other signal fired.

**Standalone invocation note:** Standalone `/quality-gate` does not run `crucible:dependency-audit` (extracted to the parent orchestrator). Therefore the dependency-audit-promotes-security-surface path does NOT fire in standalone mode. Users wanting this signal should either: (a) invoke `/dependency-audit` first and pass `force_siege: true` to `/quality-gate` if it reports findings, or (b) use `/build`, which dispatches both skills.

**Confidence threshold:** Keyword matches in design/plan/hypothesis artifacts are noisy. Require either ≥2 distinct keyword categories OR 1 keyword + an explicit "## Security" section. A single mention of "authentication" in passing does not trigger detection.

### Decision and Dispatch

After detection runs:
- If `force_siege: true` → dispatch siege unconditionally (skip detection, log as "force-dispatched")
- Else if `skip_siege: true` → never dispatch (log as "skip-requested")
- Else if `security_surface: detected` → dispatch siege
- Else → no siege dispatch (log as "no-security-surface")

**Dispatch timing:** Immediately before the first red-team round, in parallel. Quality-gate's loop proceeds independently; siege runs on its own scratch directory and its own counters.

**Chunked-gate siege scope:** When a *chunked* gate detects a security surface, dispatch `/siege` **once on the full artifact**, NOT per-chunk. Rationale: siege is expensive (~6 Opus agents) and security surfaces are typically cross-cutting (auth / data-flow span chunk boundaries), so per-chunk dispatch both multiplies cost *and* misses cross-chunk interactions. **Acknowledged tradeoff (R1 M2):** once-on-full-artifact can under-weight a chunk-*local* sink that only a per-chunk view would surface; this is accepted because (a) siege itself reasons over the full artifact and (b) the per-chunk red-team loop runs on each chunk and would independently flag a local injection sink.

**Awaiting siege (all exit paths):** Before writing any terminal verdict marker, the orchestrator verifies siege has completed. This applies to ALL exits — PASS, ARCHITECTURAL, SUSTAINED_REGRESSION, STAGNATION, ESCALATED. If siege is still running:

- **For PASS / clean exit:** Wait for siege unconditionally. Siege's Critical/High findings demote PASS to `ESCALATED` with reason "siege-blocked" — fix the security issue and re-run. If siege itself escalates (its own ESCALATED/STAGNATION verdict), include those findings in the gate's escalation summary. **Ordering on clean red-team round** (cross-reference How It Works step 5): (1) await siege; (2) if `SiegeVerdict != PASS`, skip Minor Issue Handling and write `Verdict: ESCALATED, Reason: siege-blocked`; (3) if siege PASSes or was not dispatched, run Minor Issue Handling on the known-passed artifact (Minor Issue Handling does NOT re-trigger siege); (4) write `Verdict: PASS, Reason: clean-pass` and cleanup.
- **For any escalation exit (ARCHITECTURAL, SUSTAINED_REGRESSION, STAGNATION, ESCALATED):** Wait for siege if it has been running ≤ 5 minutes; otherwise cancel siege via `crucible:siege`'s interrupt mechanism and write `SiegeVerdict: UNAVAILABLE` with `SiegeReason: cancelled-by-host-exit`. The 5-minute cap prevents an in-flight siege from blocking an already-decided escalation indefinitely.

Quality-gate's verdict is always determined by the local exit condition (see Escalation > Exit Precedence); siege results are integrated into the verdict marker after the local verdict is determined. Siege's Critical/High findings BLOCK quality-gate PASS the same way a Fatal red-team finding does, but they do NOT override a higher-precedence escalation verdict — they are recorded alongside it.

### Result Integration

Verdict marker fields (extend the existing set):

```
SiegeDispatched: true | false
SiegeReason: detected | force | skip-requested | no-security-surface
SiegeVerdict: PASS | ESCALATED | STAGNATION | UNAVAILABLE (only when SiegeDispatched=true)
SiegeFindings: <count of Critical+High findings, 0 if none or N/A>
```

**Verdict mapping:** If `SiegeDispatched: true AND SiegeVerdict != PASS`, quality-gate's verdict cannot be `PASS` — emit `Verdict: ESCALATED` with reason "siege-blocked".

**Independent of weighted score (INV-2):** Siege findings are not summed into Fatal/Significant counts. They appear in the gate output as a separate "Security Findings" section. The red-team never sees siege output (anti-anchoring preserved).

### Standalone Siege Invocations

Siege can still be invoked directly by the user. Quality-gate's siege dispatch is additive — it ensures siege runs when surfaced needs are detected, not exclusive. A user running `/siege` directly followed by `/quality-gate` will see siege run twice unless they pass `skip_siege: true` to the gate.

## Anti-Anchoring Rules

The iterative loop relies on **no contextual anchoring** between rounds — each reviewer receives the artifact and prompt as if reviewing for the first time. This is a structural property the orchestrator controls (what is passed to the reviewer), not a claim about reviewer independence. Two dispatches of the same LLM on the same artifact may produce correlated findings; that correlation is acceptable as long as the orchestrator does not amplify it by leaking prior-round context.

The convergence argument is therefore: *fix-agent edits change what is on the page; the next reviewer reads what is on the page; correlated findings on the same page imply real issues, not anchoring*. No claim about reviewer-to-reviewer statistical independence is made. (See `evals/anti-anchoring/` if it exists for empirical measurement; otherwise this property is asserted as a design boundary, not measured.)

To prevent context leaking between rounds:

1. **Clean artifact only.** The artifact passed to each round's reviewer must be the current version with no revision marks, "Fixed:" annotations, or comments about prior reviews. If the fix agent left review-response comments in the artifact, strip them before the next round.
2. **Standardized framing.** The orchestrator's dispatch prompt must use the **same framing** for every round. Do not mention that prior review rounds occurred, what was fixed, or how many rounds have run. The reviewer sees the artifact as if it is the first review.
3. **No findings forwarding.** Never pass prior round findings to the next reviewer. This is already specified in `crucible:red-team` but is restated here because the quality-gate orchestrator is the most likely point of accidental leakage.

## Round History and Compaction Recovery

Quality gate writes round state to disk for compaction recovery.

**Scratch directory:** `~/.claude/projects/<project-hash>/memory/quality-gate/scratch/<run-id>/` where `<run-id>` is a timestamp generated at the start of the gate. This path is persistent and discoverable (matching the audit skill's pattern), so it survives compaction even if the run-id is lost from context — the orchestrator can list the directory to find active runs.

**Tool constraint:** All scratch directory operations (create, read, list, delete) must use Write, Read, and Glob tools — NOT Bash. Safety hooks block Bash commands referencing `.claude/` paths.

**Active run marker:** At the start of the gate, write `~/.claude/projects/<project-hash>/memory/quality-gate/active-run-<run-id>.md` containing the run-id and scratch directory path. Delete only your own marker when the gate completes. After compaction, glob for `active-run-*.md` files to locate active runs — recover the one whose run-id matches context, or the most recent if context is lost.

**Stale cleanup:** At the start of each gate, delete scratch directories whose timestamps are older than 2 hours AND that are NOT referenced by any `active-run-*.md` marker. Also delete any `fix-journal-*.md` handoff files and `defer-ledger-*/` handoff directories in the `memory/quality-gate/` directory whose mtime is older than 24 hours (the longer window accommodates overnight breaks between QG and forge/finish sessions).

**After each round, write:**
- `round-N-score.md`: weighted score, Fatal count, Significant count, Minor count, plus the following suppression-audit fields:
  - `delta-vs-prior`: integer (weighted score - prior weighted score; positive = regression, negative = progress)
  - `fatal-delta`: integer (Fatal count delta vs prior round)
  - `suppressed-signal`: one of `none | regression | sustained-regression | stagnation-would-fire | diminishing-returns | oscillation` (records what would have escalated had suppression not been in effect; `none` if no escalation signal would have fired; `sustained-regression` is itself an exit and cannot appear as suppressed)
  - `no-op-fix`: boolean (true if round N's fix agent returned a byte-identical artifact, or the verifier returned all findings Unresolved)
- `round-N-findings.md`: the red-team findings for this round
- `artifact-N.md`: the artifact snapshot after fixes (input to round N+1)
- `fix-journal.md`: cumulative fix journal (appended after each fix agent completes; see Fix Memory above)
- `round-N-comparison.md`: stagnation judge output (only exists for rounds where the judge was dispatched — absence on clean-progress rounds is expected, not an error). When multi-model consensus was used, this file also contains consensus metadata: models queried, models responded, agreement level, and any dissenting verdicts. Silent-seed dispatches (rounds threshold-3 through threshold-1) include a `silent-mode: true` line.
- `round-N-verification.md`: fix verifier verdict summary (written after every fix round — unlike comparison files, these exist for every round that had fixes). MUST include an `architectural-candidates: [<finding-id-1>, ...] | []` field recording the list of Fatal findings flagged as architectural-candidate as of this round. This field is now informational-only and mirrors the authoritative state in `round-N-flags.md` (see below). A finding-id is added when a Fatal is marked Unresolved for the second consecutive round (per Fix Verification).
- `round-N-flags.md`: derived flag state in key-value form, written at the END of each round (after the red-team round completes, regardless of whether a fix was dispatched). This file exists for EVERY round, including clean-PASS rounds with no fix dispatch AND candidate-clean rounds that exit early (siege-blocked or no-op-fix co-fire), so every round has a defined writer for flag state. **Phase 2 behavior on candidate-clean rounds:**
  - **Look-harder confirms clean** → Phase 2 RUNS, setting `look-harder-fired-on-round: <LOCAL N>`. (This populates the at-most-once-per-chunk flag and, more importantly, prevents recovery step 6b from spuriously re-dispatching look-harder after a crash that landed post-confirmation.)
  - **Look-harder demotes the round** → Phase 2 RUNS (per the three-step Demotion crash-window rule in How It Works step 5), setting `look-harder-fired-on-round: <LOCAL N>`.
  - **Look-harder skipped (circuit-breaker, tail-rubric-already-applied, or already-fired-this-chunk)** → Phase 2 is SKIPPED; the key remains `null`. The chunk-scoped at-most-once invariant is enforced by either the chunk having ended (the skip occurred on a terminal PASS round) or by a prior round's flag carrying the populated value (the already-fired skip).
  - **Siege-blocked exit** → Phase 2 is SKIPPED; the key remains `null`. The round is terminal (`Verdict: ESCALATED, Reason: siege-blocked`); the chunk does not continue, so no subsequent round will mis-interpret the `null`.

  Contents:
  ```
  architectural-candidates: [<finding-id-1>, <finding-id-2>, ...] | []
  look-harder-fired-on-round: <LOCAL round number> | null
  ledger-emitted: <true | false>
  ```

  `ledger-emitted` defaults to `true` (set every round); `false` only if the ledger write failed.
  A list of currently-set architectural-candidate findings, in the order they were marked. Empty list `[]` means no candidates. A finding-id is added to the list when the fix verifier downgrades that Fatal to informational (per Fix Verification). Multiple candidates can coexist. This is the authoritative store for flag state; `round-N-verification.md`'s `architectural-candidate:` field mirrors it for human readability but is not consulted by recovery.

  The `look-harder-fired-on-round` key records the LOCAL round number (per-chunk) on which look-harder fired in the current chunk, or `null` if look-harder has not fired in this chunk as of round N. The key is set to `null` on every round's Phase 1 write; the firing round's Phase 2 re-write updates it to the LOCAL round number. **Recovery uses the all-files scan rule below — NOT the latest-file value alone — because later non-clean rounds write `null` (Phase 1 only) and the latest-file's `null` does NOT mean look-harder has never fired in the chunk.**

- `round-N-look-harder.md`: per-round artifact persisting the look-harder dispatch's findings (Component 1 / #265). Written ONLY on rounds where look-harder fired (clean confirmation or non-clean demotion). Absence is the canonical "look-harder did not fire this round" signal. Format mirrors `round-N-findings.md` — the red-team output of the look-harder dispatch.
- `round-N-persistence.md`: per-round artifact persisting the persistence-checker output (Component 4 / #265). Written ONLY on rounds where the persistence checker fired (i.e., round N+1's check against round N's `Unresolved` set; the file is named for round N+1, the current round). Format is the JSON object emitted by `persistence-checker-prompt.md` — either a populated correspondence list or a `status: error` fail-open entry.

  **Clear condition for `architectural-candidates`:** A finding-id `<X>` is removed from the list (set difference) on round N if BOTH conditions hold:
  1. The round-N red-team findings do not include `<X>` by literal id, AND
  2. The round-N fix verifier (if dispatched — i.e., round N had Fatal/Significant findings) does NOT classify any new round-N finding as semantically equivalent to `<X>` under the stagnation judge's Attempted-Exposed-Deeper rule (per `stagnation-judge-prompt.md`).

  If round N is a clean PASS with no fix verifier dispatched, condition (2) is trivially satisfied — the architectural concern is genuinely gone. If round N has a verifier and the verifier flags an Attempted-Exposed-Deeper relationship to `<X>`, the candidate is NOT cleared; instead the new finding's id replaces `<X>` in the list (preserving the architectural-candidate state under the new identity).

  The fix verifier MUST scan round-N red-team findings against any active architectural-candidate id from `round-(N-1)-flags.md` and report semantic-equivalence determinations in its verdict, so the orchestrator can apply this clear rule deterministically.
- `round-N-complete.md`: per-round completion sentinel. Written LAST for the round, with one of two trigger conditions:
  - **Non-terminal round:** Written after all other round-N files are flushed AND the next round's red-team dispatch has been queued. Contents: `complete: <ISO-8601 timestamp>` and `next-round-dispatched: true`.
  - **Terminal round** (the round on which the gate exits — clean PASS, ARCHITECTURAL, ESCALATED, SUSTAINED_REGRESSION, STAGNATION): Written after all other round-N files are flushed, BEFORE the verdict marker. Contents: `complete: <ISO-8601 timestamp>` and `terminal: <verdict>`. No next-round dispatch is queued.

  The sentinel's presence guarantees round N is fully recoverable; its absence means the round is incomplete and must be discarded on recovery. The `terminal:` field tells recovery the gate had exited and the verdict marker should be the source of truth, not a continuation.

**Compaction recovery:**
0. Read `## Compression State` from `pipeline-status.md` — recover Goal, Key Decisions (including parent skill decisions that affect the gate), Active Constraints, and Next Steps. If absent, skip to step 1. Note: quality-gate is invoked by a parent skill (build, debugging, spec), so the Compression State reflects the parent's context. The quality-gate orchestrator inherits this context.
1. Glob for `active-run-*.md` markers to locate the scratch directory.
1b. **Pre-flight recovery (code artifacts only):** Check for `preflight-audit.md` in the scratch directory. If absent, restart from manifest scan. If present, read it to recover the manifest list. Then check `audit-results.md` for completed ecosystem sections (those ending with `status: complete` sentinel). Sections without the sentinel are discarded as incomplete. Resume from the first manifest not yet present as a complete section. Recovery re-invokes the audit tool for incomplete manifests — no raw output is cached between compaction events. After all manifests complete, regenerate the Summary section of `audit-results.md`.
2. Read scratch directory to determine current round. The current round is the highest N with a corresponding `round-N-complete.md` sentinel. If `round-(N+1)-score.md` exists but `round-(N+1)-complete.md` does not, round (N+1) was in progress when the crash occurred — discard `round-(N+1)-*.md` files (they may be partial) and resume from round N+1's fix dispatch. If `round-N-complete.md` includes `terminal: <verdict>`, the gate had completed — proceed to verify the verdict marker exists; if so, no recovery needed (treat as completed run). If the marker is missing or partial, replay only the verdict-marker write step.
2a. **Suppression-boundary recovery rule:** If recovery resumes at a round where the local round count ≥ `suppression_threshold`, the suppression window is over — all subsequent rounds use normal escalation logic. Crash-induced delay does not extend the trust window.
3. Read the latest `artifact-N.md` as the current artifact state.
4. Read all `round-N-score.md` files to reconstruct the score progression.
5. Read all `round-N-comparison.md` files to reconstruct consecutive-round state for the stagnation judge. Absence of comparison files is expected on clean-progress rounds.
6. Read all `round-N-verification.md` files to recover fix verifier state. If any Fatal-severity Unresolved verdicts exist in the latest verification file, carry them forward as binding context for the next fix dispatch. Then read the latest `round-N-flags.md` (authoritative store for flag state — exists for every round, including clean-PASS rounds): if its `architectural-candidates:` list is non-empty, restore every finding-id in the list to the next fix dispatch's prompt. Without this restoration, a crash between flag-set and the next no-op round would silently drop the candidates, breaking the no-op→architectural promotion path.

6a. **Look-harder fired-flag recovery (all-files scan, not latest-file).** Read ALL `round-N-flags.md` files in the in-progress chunk's directory (per the chunk-scoped grammar — non-chunked gates scan the flat scratch dir; chunked gates scan only `chunk-K/round-N-flags.md` for the in-progress chunk K — **no cross-chunk globbing**, completed chunks' flag files are never consulted). Treat look-harder as already fired in this chunk iff ANY file has a non-null `look-harder-fired-on-round` value. The chunk's effective fired-round is the maximum LOCAL round number across all non-null entries. Subsequent candidate-clean rounds in this chunk SKIP look-harder silently per INV-A1. This rule is load-bearing: later non-clean rounds wrote `look-harder-fired-on-round: null` (Phase 1 only; Phase 2 skipped on non-clean), so reading the latest flag file alone would lose the earlier "fired" state and re-fire look-harder on the next candidate-clean round.

6b. **`round-N-look-harder.md` recovery.** If `round-N-look-harder.md` exists but the corresponding `round-N-flags.md`'s `look-harder-fired-on-round` is `null`, the orchestrator crashed in the Phase-1 / Phase-2 window. Re-dispatch look-harder for round N; the re-dispatch overwrites `round-N-look-harder.md` and writes Phase 2 of `round-N-flags.md` per the write-ordering protocol. This is protocol-safe per the crash-window analysis (no fix dispatch has consumed the prior findings; sampling-variance differences are acceptable).

6c. **`round-N-persistence.md` recovery.** Three sub-cases:
   - **File ABSENT and trigger conditions met** (round N+1 was non-clean AND round N's `### Verifier Assessment` contains ≥1 `Unresolved` AND both findings files exist): the orchestrator crashed BEFORE the persistence checker dispatched. Dispatch the persistence checker now, before the judge, per the normal flow. This case is NOT fail-open — the gate must run the checker if the trigger fires, and an absent file means "never dispatched", not "errored". (Without this clause, an F1 verdict-level promotion would silently fail to fire on recovery and a real persistence pattern would be missed.)
   - **File EXISTS with `status: error`**: the state stands — do NOT re-dispatch the persistence checker. `persistent_finding_count: 0` (fail-open) carries forward, and the verdict-level promotion does not fire on this round even after recovery.
   - **File EXISTS with a populated correspondence list**: the state stands as-is; the orchestrator reads it after judge dispatch as if the gate had never crashed.
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


**Defer-ledger handoff (#303):** After Minor Issue Handling and before cleanup, preserve the per-round ledgers so `crucible:finish` can seed the v1.0 calibration corpus *after* this scratch directory is deleted. Copy every `round-N-ledger.md` from the scratch directory — including those in `chunk-*/` subdirectories for chunked gates — into a durable per-run directory `~/.claude/projects/<project-hash>/memory/quality-gate/defer-ledger-<run-id>/`. Flatten chunked ledgers with a chunk prefix (`chunk-<K>-round-<N>-ledger.md`) so names cannot collide with the non-chunked `round-<N>-ledger.md` form. Written on ALL exit paths (PASS, ESCALATED, STAGNATION, ARCHITECTURAL) because a ledger exists for every round per INV-303-1. Use Write/Read/Glob, NOT Bash (the `.claude/` Bash constraint above applies). This mirrors the `fix-journal-<run-id>.md` handoff: a transient artifact consumed by a later skill, not part of the gate's verdict. The consuming skill (`crucible:finish`) deletes the directory after seeding; the stale-cleanup pass (above, 24h) reclaims any handoff that is never consumed.

**Cleanup:** Delete scratch directory and your `active-run-<run-id>.md` marker after the gate completes (pass or stagnation). Do NOT delete verdict marker files (`gate-verdict-<run-id>.md`) — the build orchestrator is responsible for their lifecycle.

**Checkpoint cleanup (code artifacts only):** On terminal exit paths:
- **Clean PASS:** Delete all `pre-qg-fix-round-*` checkpoints from this gate run via the checkpoint skill. They served their purpose; retaining them clutters the shadow git log.
- **Any escalation (ESCALATED, STAGNATION, SUSTAINED_REGRESSION, ARCHITECTURAL):** Retain all `pre-qg-fix-round-*` checkpoints until the user resolves the escalation. The user may invoke "restore to checkpoint" on any of them. After the user accepts the escalation (continues, restores, or kills the gate), cleanup is the responsibility of the parent orchestrator or the next gate run's stale-cleanup pass (2-hour TTL).
- **Crash / abandoned run:** The 2-hour stale-cleanup pass at gate start handles abandoned checkpoint sets via mtime check.

## Verdict Marker

After Minor Issue Handling completes and before cleanup begins, write a verdict marker file to a stable location outside the scratch directory. This marker survives scratch cleanup and serves as a cross-skill consistency signal for the build orchestrator's gate ledger.

**When:** After Minor Issue Handling (the quick-fix pass on consolidated minors) and before cleanup. Written on ALL exit paths — PASS, FAIL, STAGNATION, and ESCALATED. The Verdict field reflects the actual outcome.

**Path:** `~/.claude/projects/<project-hash>/memory/quality-gate/gate-verdict-<run-id>.md`

**Format:** Key-value pairs, one per line. `MarkerVersion: 2` MUST be the FIRST line, `ArtifactHash` the SECOND. Field ordering below is canonical for writers:

```
MarkerVersion: 2
ArtifactHash: <sha256-hex of FULL pre-chunking artifact bytes, computed once at gate start>
ChunkHash: <sha256-hex of this chunk's bytes>   # chunked gates only, per-chunk markers only; omit on non-chunked markers and on the cross-chunk integration marker
Verdict: PASS | FAIL | STAGNATION | ESCALATED | ARCHITECTURAL | SUSTAINED_REGRESSION
Reason: clean-pass | siege-blocked | consensus-stagnation-pre-threshold | sustained-regression | no-op-fix | no-op-with-architectural-candidate | user-skipped | 15-round-circuit-breaker | stagnation-judge | single-round-regression | diminishing-returns | architectural-block-from-fix-agent | persistent-finding-corroborated | caller-detected-failure
Phase: <phase name from invoking orchestrator, omit if standalone>
PipelineID: <pipeline-id from invoking orchestrator, omit if standalone>
Rounds: <total round count>
FinalScore: <weighted score from last round>
MaxScore: <highest weighted score observed across all rounds>
ScoreTrajectory: <comma-separated per-round weighted scores; on chunked gates, chunk boundaries are marked with `|` between two commas (e.g., `6,4,3,|,5,3,1,0,|,4,2,1`); parsers must split on `,` and treat `|` tokens as chunk separators rather than integers, e.g., 6,4,5,4,3,0>
SuppressedRegressions: <count of pre-threshold rounds with suppressed-signal != none>
NoOpFixes: <count of rounds with no-op-fix = true>
CoFiredExits: <comma-separated list of suppressed co-firing exits, omit if none>
ConsensusAvailable: true | false
ConsensusRoundsRun: <int — count of rounds where consensus_query returned status in {complete, partial}>
LookHarderRounds: <comma-separated list of LOCAL round numbers where look-harder fired NON-CLEAN; on chunked gates, elements are `<chunk_id>:<local_round>` per the canonical grammar — see Chunked Gate section; OMIT this field entirely when empty (omit-when-empty, parallel to CoFiredExits)>
LookHarderFiredCount: <int — count of look-harder dispatches (clean + non-clean, NOT skipped); always present, defaults to 0; invariant: len(LookHarderRounds) ≤ LookHarderFiredCount>
LookHarderSkippedReason: circuit-breaker | tail-rubric-already-applied   # OMIT unless look-harder was skipped on a candidate-clean round; per-run, first reason recorded if multiple skips occur; circuit-breaker wins over tail-rubric-already-applied on co-fire
PersistentFindingRounds: <comma-separated list of LOCAL round numbers where persistent_finding_count ≥ 1; on chunked gates, elements are `<chunk_id>:<local_round>`; OMIT this field entirely when empty (parallel to LookHarderRounds)>
PersistentCheckCount: <int — count of persistence-checker dispatches (error dispatches DO count); always present, defaults to 0; invariant: len(PersistentFindingRounds) ≤ PersistentCheckCount>
SiegeDispatched: true | false
SiegeReason: detected | force | skip-requested | no-security-surface
SiegeVerdict: PASS | ESCALATED | STAGNATION | UNAVAILABLE (omit if SiegeDispatched=false)
SiegeFindings: <count of Critical+High siege findings, omit if SiegeDispatched=false>
CostCapSignals: <DR-fire-count>+<cost-cap-fire-count>/<rounds>
Timestamp: <ISO-8601>
RunID: <quality-gate run-id>
Severity-Histogram: <json — e.g., {"fatal":0,"significant":0,"minor":0,"nit":0}>
Gated-Files: <json-list — e.g., ["src/foo.py","src/bar.py"]>
Highest-Finding: "<one-line quote of the most severe finding, or empty string if none>"
```

<!-- CANONICAL: shared/ledger-append.md -->

**Ledger emit at verdict-emit.** When emitting your terminal verdict, also emit one JSONL line to the **central ledger** (`~/.claude/crucible/ledger/runs.jsonl`, override `CRUCIBLE_LEDGER_DIR`) via the `emit` CLI per the canonical protocol at `skills/shared/ledger-append.md` — resolve `scripts/ledger_append.py` by absolute path from the plugin root and run `python3 <script> emit - '<json>'` (`-` = central default). The `emit` CLI owns the mechanics: it honors `CRUCIBLE_CALIBRATION_DISABLED=1` as a graceful skip, dedups by `(run_id, skill)` (L-2), and auto-fills `repo` + `schema_version` — so you only construct the entry. If the script can't be resolved, warn to stderr and skip; a missing emit must never block the gate.

**`predicted_falsifier` (Phase 7 prediction market).** When constructing the entry, set `predicted_falsifier` to a pre-registered, machine-checkable predicate ONLY when `verdict ∈ {PASS, FAIL}` AND `artifact_type == "code"`; otherwise `null` (all escalation verdicts — STAGNATION/ESCALATED/ARCHITECTURAL/SUSTAINED_REGRESSION — and all non-code artifact types). In one sentence, describe the future evidence that would prove this verdict wrong, using the canonical grammar where possible: `{verb} touching {file-or-glob[,file-or-glob,...]} within {N}d` (e.g., `fix touching src/auth/token.ts within 30d`). Free-form prose is permitted but counts as "unparseable" for auto-checking. Max 256 chars. Full grammar (three forms, verbs, glob/hash/token variants) is the canonical `predicted_falsifier` protocol in `skills/shared/ledger-append.md`. Do NOT write the retired `"<DEFERRED:pre-phase-7>"` sentinel.

**MarkerVersion semantics:** Every verdict marker written by this version of the gate or later carries `MarkerVersion: 2` as its first line. Consumers gate version-aware parsing on this stamp:

- `MarkerVersion: 1` or absent ⇒ legacy marker. Consumers MUST treat any missing field as `null` (unknown), NOT as `false`/`0`/`[]`.
- `MarkerVersion: 2` ⇒ this version's marker. Missing fields are semantically empty per the **omit-when-empty** convention enumerated above (e.g., absent `LookHarderRounds` means "no non-clean look-harder rounds"; absent `LookHarderSkippedReason` means "look-harder was not skipped").

The convergence-log mirrors this stamp via `marker_version` (see Convergence Telemetry).

**ArtifactHash semantics:** `ArtifactHash` is the sha256 hex of the FULL pre-chunking artifact's bytes, computed once at gate start. For non-chunked gates this is the single artifact's hash. For chunked gates, every per-chunk verdict marker AND the cross-chunk integration round's marker carry the **same** `ArtifactHash` — it identifies the artifact across all chunks of a single gate run AND across multiple gate runs on the same byte content (regardless of chunking strategy). Forge consumers use `ArtifactHash` for same-artifact cross-run comparison, including the revisit trigger for the `tail-rubric-already-applied` skip.

`ChunkHash` (chunked gates only): sha256 hex of the specific chunk's bytes. Present on per-chunk markers in chunked gates only. **Omitted from non-chunked-gate markers and from the cross-chunk integration round's marker.** `ArtifactHash` is the canonical cross-run identifier; `ChunkHash` is internal-only for per-chunk recovery scenarios.

**Verdict enum semantics:**
- `PASS`: gate exited cleanly (0 Fatal, 0 Significant on a fresh red-team round)
- `FAIL`: caller-detected gate failure outside the normal exit paths (reserved for build's gate ledger). Quality-gate itself never writes `Verdict: FAIL`. The FAIL value exists in the enum for callers (build's gate ledger) that need to record a downstream-detected failure of the gate's output; such callers write `Reason: caller-detected-failure` alongside it.
- `STAGNATION`: stagnation judge declared STAGNATION at round ≥ `suppression_threshold`
- `ESCALATED`: any other escalation routed to the user (15-round limit, diminishing returns, single-round regression at round ≥ `suppression_threshold`)
- `ARCHITECTURAL`: fix-agent flagged architectural concern (any round); see Architectural Concerns Exit
- `SUSTAINED_REGRESSION`: `score(N) > score(N-1) > score(N-2)` triggered the hard exit (any round)

**Reason token mapping (which exit-path writes which token):**
- `clean-pass` — Verdict: PASS. The only valid Reason for PASS.
- `siege-blocked` — Verdict: ESCALATED, from the Siege verdict-mapping rule (`SiegeDispatched: true AND SiegeVerdict != PASS`).
- `consensus-stagnation-pre-threshold` — Verdict: ESCALATED, from the Pre-Threshold Consensus Carve-Out.
- `sustained-regression` — Verdict: SUSTAINED_REGRESSION, from the sustained-regression hard exit.
- `no-op-fix` — Verdict `ESCALATED`. The fix agent returned a byte-identical artifact, OR the verifier marked every targeted finding Unresolved, AND no architectural-candidate flag was set from a prior round. Distinct from `no-op-with-architectural-candidate`, which applies when the architectural-candidates list is non-empty.
- `no-op-with-architectural-candidate` — Verdict: ESCALATED, from the no-op→architectural promotion path when the re-dispatch also returns a no-op.
- `user-skipped` — Verdict: ESCALATED, from the interactive check-in's escalate-now/skip response or an out-of-band user interrupt.
- `15-round-circuit-breaker` — Verdict: ESCALATED, from the 15-round global safety limit.
- `stagnation-judge` — Verdict: STAGNATION, from the stagnation judge declaring STAGNATION at round ≥ `suppression_threshold`.
- `single-round-regression` — Verdict: ESCALATED, from a single-round score increase at round ≥ `suppression_threshold`.
- `diminishing-returns` — Verdict: ESCALATED, from the judge's DIMINISHING_RETURNS verdict.
- `architectural-block-from-fix-agent` — Verdict: ARCHITECTURAL, from the fix agent's `VERDICT: ARCHITECTURAL_BLOCK` declaration.
- `persistent-finding-corroborated` — Verdict: STAGNATION, from the orchestrator's post-judge verdict-level promotion rule (Component 4). Recorded when the stagnation judge returned PROGRESS but `persistent_finding_count ≥ 1` AND round ≥ `suppression_threshold` AND round N's verifier had ≥1 `Resolved` finding (NOT fully no-op). See `## Stagnation Detection > Persistence Check` for the promotion logic.
- `caller-detected-failure` — Verdict: FAIL. Valid ONLY when `Verdict: FAIL`; written by callers (e.g., build's gate ledger) recording a downstream-detected failure of the gate's output. Quality-gate itself never writes this combination.

**Fragile-pass detection:** Downstream consumers (build's gate ledger, forge retrospectives, future telemetry) detect a fragile pass via `Verdict: PASS AND (SuppressedRegressions > 0 OR MaxScore > FinalScore + max(2, ceil(suppression_threshold / 3)) OR NoOpFixes > 0 OR ConsensusAvailable: false)`. The `max(2, ceil(threshold/3))` term scales the score-swing tolerance to the convergence window: a code/design/plan gate (threshold 10) tolerates a 4-point swing; a hypothesis/mockup/translation gate (threshold 3) tolerates 2 points. (Note: fragile-pass detection intentionally uses `ceil` — slightly more permissive tolerance — while the consensus/notification *cadence* uses `max(1, // 3)` floor for a precise per-round schedule. The two formulas serve different purposes and are not expected to match.) The rationale is that longer convergence windows naturally produce larger transient scores, and a flat `+2` would over-flag normal convergence on artifacts allowed more rounds. A fragile pass is still a PASS — these fields are advisory signal for human review or telemetry filtering, not for failing the gate.

**Fragile-pass disjunct partitioning (advisory).** Consumers SHOULD partition `ConsensusAvailable: false` from the other disjuncts (SuppressedRegressions, MaxScore drift, NoOpFixes) when reporting fragility rates. The consensus disjunct reflects a **cross-model coverage gap** — the gate ran against a single model family and correlated blind spots are possible. The other disjuncts reflect **within-loop convergence instability**. Each consumer may choose to display them as separate metrics rather than a single fragility boolean; collapsing the two onto one axis obscures the underlying cause of the fragility flag.

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
{"marker_version":2,"artifact_hash":"<sha256-hex>","chunk_hash":"<sha256-hex>","run_id":"2026-05-16T14-30-00","artifact_type":"code","threshold":10,"rounds":4,"verdict":"PASS","final_score":0,"max_score":6,"score_trajectory":[6,4,3,0],"suppressed_regressions":1,"no_op_fixes":0,"consensus_available":false,"consensus_rounds_run":0,"look_harder_rounds":[],"look_harder_fired_count":0,"look_harder_skipped_reason":null,"persistent_finding_rounds":[],"persistent_check_count":0,"siege_dispatched":false,"timestamp":"2026-05-16T14:38:21Z"}
```

Fields mirror the verdict marker plus `threshold` (the active `suppression_threshold` for this run). One line per gate run, regardless of verdict.

**Field semantics for the new entries:**

- `marker_version`: integer matching the verdict marker's `MarkerVersion`. New entries written by this version carry `2`.
- `artifact_hash`: sha256 hex of the FULL pre-chunking artifact's bytes (mirrors `ArtifactHash` in the verdict marker).
- `chunk_hash`: sha256 hex of the specific chunk's bytes. Present on chunked-gate per-chunk entries only; OMITTED (key absent) on non-chunked entries and on the cross-chunk integration entry.
- `consensus_available`: `true` iff `consensus_query` returned `status in {complete, partial}` on ≥1 consensus-eligible round across the run.
- `consensus_rounds_run`: integer count of rounds where `consensus_query` returned `status in {complete, partial}`.
- `look_harder_rounds`: JSON list. **Non-chunked gates:** bare integers (e.g., `[3, 6]`). **Chunked gates:** objects `{"chunk": "chunk-<N>" | "cross-chunk", "local_round": <int>}` (e.g., `[{"chunk":"chunk-1","local_round":3},{"chunk":"chunk-2","local_round":5}]`). Empty list `[]` when no non-clean look-harder rounds occurred (JSON has no omit-vs-empty ambiguity, so empty list is canonical rather than absent key).
- `look_harder_fired_count`: integer count of look-harder dispatches in the gate run (clean + non-clean, NOT skipped). Defaults to 0. Invariant: `len(look_harder_rounds) ≤ look_harder_fired_count`.
- `look_harder_skipped_reason`: enum value `"circuit-breaker"` | `"tail-rubric-already-applied"` recorded on a per-run basis. First reason recorded if multiple skips occur. `null` when no skip occurred.
- `persistent_finding_rounds`: JSON list, same element grammar as `look_harder_rounds`. Empty list `[]` when no rounds produced `persistent_finding_count ≥ 1`.
- `persistent_check_count`: integer count of persistence-checker dispatches (error dispatches DO count). Defaults to 0. Invariant: `len(persistent_finding_rounds) ≤ persistent_check_count`.
- `dr_cause`: convergence-log JSON **only** (there is **no verdict-marker `dr_cause` field** and **no `marker_version` bump** — key presence resolves the null ambiguity). Value set: `"minor-accumulation" | "structural-saturation" | "consensus" | null`.
  Populated from the judge's `DR-Cause:` discriminator when the resolved reason is `diminishing-returns`, else `null`. The orchestrator **translates `none → null`** when writing — it must NOT write the literal string `"none"`.
  On a **consensus-resolved** DR exit (no single-judge discriminator line to read), set the sentinel `"consensus"`; a `"consensus"` value **cannot attribute** minor-accumulation vs. structural-saturation, since consensus synthesis collapses the cause.
  Key-presence semantics: every **post-D5** entry carries the `dr_cause` key (value in `{minor-accumulation, structural-saturation, consensus, null}`); every **pre-D5** entry lacks it entirely. A present-but-`null` value means "this DR-eligible run did not exit on diminishing-returns," not "unknown vintage."

**Version-aware backward compatibility (canonical):** Existing convergence-log entries written before this version was deployed lack `marker_version`, `artifact_hash`, and the new telemetry fields. Consumers MUST treat any missing field on a legacy entry as `null` (unknown), NOT as `false` / `0` / `[]`. **Legacy entries are explicitly excluded from any rate-denominator computation** — clean-confirmation rates, non-clean rates, persistence-checker correlation rates, and the recurrence-rate measurements in Open Questions are computed only over entries with `marker_version: 2`. Forge consumers analyzing pre-design entries treat all new fields as `null` and skip those entries when computing rates. **`dr_cause` firing-rate denominators filter on `dr_cause` key-presence** (post-D5 entries always carry the key), **not on `marker_version` alone** — so a pre-D5 (`marker_version:2`-but-no-`dr_cause`) entry is not pulled into a `dr_cause` denominator.

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

### When Used as a Sub-Skill of Build, Debugging, or Spec

Build is the outermost orchestrator and controls all quality gates:

- **Phase 1 (after design):** Quality gate on design doc (artifact type: design)
- **Phase 2 (after plan review):** Quality gate on plan (artifact type: plan)
- **Phase 4 (after implementation):** Quality gate on full implementation (artifact type: code)

**Context from invoking orchestrator:** When a parent orchestrator (build, debugging, or spec) invokes quality-gate, it MUST include a "Context from invoking orchestrator" block in the dispatch prompt containing `Phase` (the parent's logical phase name) and `PipelineID` (the parent's unique pipeline identifier). For build, `Phase` is one of `design | plan | code` and `PipelineID` is `build-YYYYMMDD-HHMMSS`. For debugging, `Phase` is `hypothesis` or `code` (Phase 3.5 vs Phase 5) and `PipelineID` is `debug-YYYYMMDD-HHMMSS`. For spec, `Phase` is `spec` and `PipelineID` is `spec-<ticket-id>`. Quality-gate uses these to set `interactive: false` and to populate the verdict marker.

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
- **Diminishing returns** (round ≥ threshold) → escalate to user, message **keyed off the judge's `DR-Cause`** (Verdict: `ESCALATED` in every case). `minor-accumulation` is the only special arm; everything else routes to the default message so every DR exit has a defined message. When `DR-Cause = minor-accumulation`: "Quality gate: Minors are accumulating at a flat score while Fatal/Significant findings still churn without converging. Recurring Minors: [list]. Presenting for user judgment (Minors never trigger fix rounds — this is a judgment call, not a forced fix)." Otherwise (`structural-saturation`, `consensus`, or absent/unattributable): "Quality gate has resolved all prior issues. Round N found [X] new findings, all Structural (require design-level decisions). Remaining findings: [list]. Presenting for user judgment."
- **Single-round regression** (round ≥ `suppression_threshold`) → escalate immediately, no judge needed: "Round N score (X) is higher than Round N-1 score (Y). The fix cycle introduced new issues. Escalating." Verdict: `ESCALATED`.
- **Global safety limit reached (15 rounds)** → escalate to user with full round history. Applies regardless of `suppression_threshold`. Verdict: `ESCALATED`.
- **Architectural concerns** → fix agent returns `VERDICT: ARCHITECTURAL_BLOCK` (see Architectural Concerns Exit). Escalate immediately, terminal verdict `ARCHITECTURAL`. Applies at any round.
- **User interrupt** — either between-rounds interactive check-in's "escalate now"/"skip" response (see Skill Arguments) or an out-of-band interrupt. Verdict: `ESCALATED`, reason "user-skipped".

### Exit Precedence

A single round can satisfy more than one exit condition (e.g., sustained-regression AND no-op AND consensus-stagnation can co-fire). The orchestrator MUST select the verdict deterministically using this precedence list. Evaluate top-to-bottom; the first match wins; remaining conditions are recorded in the verdict marker for telemetry but do not change the verdict.

**Pre-precedence resolution.** Before evaluating precedence, the orchestrator MUST run the no-op→architectural promotion re-dispatch if both conditions are true: (a) no-op fix detected this round, (b) the `architectural-candidates` list from a prior round is non-empty. The re-dispatch's outcome (ARCHITECTURAL_BLOCK, clean fix, or persistent no-op) then participates in normal precedence evaluation. This ensures the fix agent always gets its second chance to declare ARCHITECTURAL, even when other exits (15-round limit, consensus-stagnation, etc.) would co-fire and otherwise win precedence. Exception: if the current round is at the 15-round circuit breaker (`current_round == 15`), the pre-precedence re-dispatch is skipped and the orchestrator proceeds directly to circuit-breaker escalation. The 15-round cap is absolute — runaway protection takes precedence over architectural second-chance.

**Persistent-finding verdict promotion (Component 4 / #265).** AFTER the Pre-precedence resolution step above AND AFTER the stagnation judge returns its verdict (per `## Stagnation Detection > Verdict-Level Promotion`), the orchestrator applies the persistent-finding promotion: if `persistent_finding_count ≥ 1` AND round ≥ `suppression_threshold` AND judge verdict is `PROGRESS` AND round N's verifier had ≥1 `Resolved` finding (NOT fully no-op), the verdict is promoted to `STAGNATION, Reason: persistent-finding-corroborated`. The promoted STAGNATION is consumed at **slot #7** (the standard stagnation-judge consumption slot below). Precedence slots #2-#6 outrank a promoted STAGNATION when they co-fire on the same round; in those cases `persistent-finding-corroborated` is recorded under `CoFiredExits` and does NOT alter the higher-precedence verdict.

1. **Clean pass** (0 Fatal, 0 Significant on a fresh red-team round) — overrides every other entry in this list, but is subject to post-precedence siege demotion (see below). A fresh-eyes clean review means the artifact is done.
2. **ARCHITECTURAL_BLOCK** — the fix agent declared `VERDICT: ARCHITECTURAL_BLOCK` (see Architectural Concerns Exit). The only exit declared by the fix agent itself; honor it. Verdict: `ARCHITECTURAL`.
3. **SUSTAINED_REGRESSION** — three rounds of strictly-increasing scores (see First-Pass Check). Structural signal of active worsening; bypass everything else. Verdict: `SUSTAINED_REGRESSION`.
4. **No-op fix ESCALATED** — byte-identical artifact OR all-Unresolved verifier (see No-Op Fix Detection). Pre-precedence resolution has already attempted the architectural-promotion re-dispatch if the `architectural-candidates` list was non-empty; by this point in evaluation, the outcome is one of: (a) re-dispatch produced a clean fix → no-op condition no longer fires; (b) re-dispatch returned ARCHITECTURAL_BLOCK → already won at precedence #2; (c) re-dispatch produced another no-op AND the architectural-candidates list was non-empty → verdict `ESCALATED` with Reason `no-op-with-architectural-candidate`; OR no-op detected with empty list (no re-dispatch fired) → verdict `ESCALATED` with Reason `no-op-fix`.
5. **Consensus-stagnation pre-threshold ESCALATED** — ONLY when `consensus_query` is available (see Pre-Threshold Consensus Carve-Out). Verdict: `ESCALATED`, reason "consensus-stagnation-pre-threshold".
6. **15-round circuit-breaker ESCALATED** — global safety limit. Verdict: `ESCALATED`.
7. **At round ≥ `suppression_threshold`:** stagnation / regression / diminishing-returns ESCALATED, per the Stagnation Detection and Escalation rules above. Verdict: `STAGNATION` or `ESCALATED` as documented per exit.
8. **User interrupt ESCALATED** — interactive check-in or out-of-band interrupt. Verdict: `ESCALATED`, reason "user-skipped".

**Post-precedence siege demotion.** After the precedence list selects a local verdict, the orchestrator applies one post-processing step: if `SiegeDispatched: true` AND `SiegeVerdict != PASS` AND the local verdict is `PASS` (precedence #1), demote to `Verdict: ESCALATED` with `Reason: siege-blocked` and record the original would-be-PASS in `CoFiredExits: clean-pass-demoted-by-siege`. Siege demotion does NOT override any non-PASS local verdict (ARCHITECTURAL, SUSTAINED_REGRESSION, STAGNATION, ESCALATED) — those stand, with siege findings recorded in the dedicated `SiegeVerdict` / `SiegeFindings` marker fields. This demotion is the ONLY post-precedence verdict modification.

How It Works step 10's enumeration of pre-threshold exits and the bullet list above reference this precedence; co-firing conditions resolve here. If a co-firing condition is suppressed by precedence, record it under a `CoFiredExits:` line in the verdict marker (informational only).

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

- Using consensus on every red-team round (periodic only: Round 1 and every `max(1, suppression_threshold // 3)` rounds thereafter, up to round 15)
- Treating single-model unique findings from consensus as less important than multi-model agreements (the prompt explicitly elevates "potentially novel" findings)
- Blocking the host red-team round on external review availability or timeout

### Look-harder, tail-rubric, and persistence (#265)

- Self-overwriting `round-N-findings.md` on the same candidate-clean round where look-harder ran AND returned 0F/0S. The overwrite happens ONLY on look-harder demotion (look-harder returned Fatal/Significant). Confirming a clean round does NOT overwrite the findings file.
- Forwarding persistence-checker output to the red-team prompt or the stagnation judge's input set. The output flows ONLY to the orchestrator (read path between judge dispatch and verdict marker write). Leaking it to either consumer breaks anti-anchoring (red-team) or the judge's input-set invariant.
- Computing `tail_rubric: true` against the GLOBAL round number on chunked gates. The trigger is LOCAL (per-chunk) — chunk 2 of a chunked gate does NOT inherit tail-rubric from chunk 1's late rounds. Each chunk's local counter governs.

**Retired (covered structurally):** Self-fixing instead of dispatching a fix agent, rationalizing away findings, skipping the gate without approval, declaring "complete" without a clean round, exceeding 15-round limit, escalating pre-threshold for single-round signals, dispatching the judge pre-threshold, looping past sustained regression, allowing fix-agent scope drift, skipping the fix verifier — all of these are now caught by the Anti-Rationalization Table or by structural invariants (Non-Skippability, Receipt Linter mandatory-work, Architectural Concerns Exit). They do not need separate red-flag entries.

## Implementation Invariants

The invariants below govern the look-harder verification (Component 1), the tail-rubric (Component 2), the telemetry-expansion fields (Component 3), and the persistence-checker / verdict-level promotion (Component 4) introduced by #265. These are spec-inspection invariants: in a spec-only repo, the verification mechanism is targeted grep against the orchestrator state-machine in this SKILL.md plus the two new prompt files (`tightened-rubric-addendum.md`, `persistence-checker-prompt.md`). The canonical statements live in the design doc (`docs/plans/2026-05-17-qg-tail-hardening-design.md`, local-only) and the machine-readable contract (`docs/plans/2026-05-17-qg-tail-hardening-contract.yaml`). This table is the navigational index.

### Checkable (INV-A1 — INV-A17)

| ID | Summary |
|---|---|
| INV-A1 | Look-harder fires at-most-once per chunk per gate run, on the first non-skip-condition clean round (LOCAL counter) |
| INV-A2 | Look-harder does NOT increment the gate's round counter |
| INV-A3 | `tail_rubric: true` iff `suppression_threshold ≥ 5` AND LOCAL round ≥ `ceil(suppression_threshold * 0.6)` |
| INV-A4 | Shared addendum is concatenated to `red-team-prompt.md` body by the orchestrator iff look-harder is firing OR `tail_rubric: true`; orchestrator is sole appender |
| INV-A5 | `ConsensusAvailable` present on every marker; canonical run-total semantics (any chunk OR cross-chunk integration); legacy markers treat absence as `null` |
| INV-A6 | `ConsensusRoundsRun` is run-total count of consensus-eligible rounds with `status in {complete, partial}` |
| INV-A7 | `look-harder-fired-on-round` persists per-chunk; recovery scans ALL flags files in the chunk dir; effective fired-round = max non-null |
| INV-A8 | Two-phase write protocol for `round-N-flags.md` (Phase 1: null at end of round; Phase 2: LOCAL round after look-harder resolves) |
| INV-A9 | `LookHarderFiredCount` always present; counts clean confirmations + non-clean demotions, NOT skipped |
| INV-A10 | Persistence checker fires iff round N+1 non-clean AND round N's `### Verifier Assessment` has ≥1 `Unresolved`; F1 promotion requires `persistent_finding_count ≥ 1` AND round ≥ threshold AND judge `PROGRESS` AND ≥1 `Resolved` |
| INV-A11 | Persistence checker inputs limited to round-N/N+1 findings + round-N fix-journal; output flows only to orchestrator (not red-team, not judge); promotion runs post-judge, post-pre-precedence; consumed at slot #7 |
| INV-A12 | `PersistentCheckCount` always present; error dispatches count; invariant `len(PersistentFindingRounds) ≤ PersistentCheckCount` |
| INV-A13 | `MarkerVersion: 2` is FIRST line of every marker by this design |
| INV-A14 | `ArtifactHash` is SECOND line; per-run identifier covering all per-chunk and cross-chunk markers in a chunked gate |
| INV-A15 | `chunk_id` grammar restricted to `chunk-<N>` (positive integer) | `cross-chunk`; gate refuses to start on non-conforming chunk dirs |
| INV-A16 | `ChunkHash` on per-chunk markers only; omitted on non-chunked markers and on cross-chunk integration marker |
| INV-A17 | On a look-harder-demoted round, `round-N-findings.md` is overwritten with look-harder findings before fix dispatch; `round-N-look-harder.md` is retained |
| INV-A18 | No manifest-sweep step re-hashes a prior manifest entry's pinned `ARTIFACTS` against disk after insertion (the sweep only re-reads a receipt's text on a tripwire fire) — this is the load-bearing fact making a look-harder-demoted candidate-clean receipt's now-stale pinned hash inert (#366, SP3) |

### Testable (INV-T1 — INV-T16, with T2b/T2c/T5b suffix variants)

| ID | Summary |
|---|---|
| INV-T1 | Round-counter integrity — 4-standard-round gate emits `Rounds: 4`, not 5 |
| INV-T2 | Tail-rubric trigger (threshold 10) — LOCAL rounds 1-5 lack `tail_rubric: true`; LOCAL 6+ have it |
| INV-T2b | Tail-rubric trigger (threshold 6) — LOCAL rounds 1-3 lack it; LOCAL 4+ have it |
| INV-T2c | Tail-rubric trigger (threshold 5) — LOCAL rounds 1-2 lack it; LOCAL 3+ have it (cross-chunk integration round) |
| INV-T3 | Tail-rubric DISABLED for threshold 3 / 4 — flag never set at any LOCAL round number |
| INV-T4 | Look-harder no-second-fire per-chunk — across a clean→fix→non-clean→fix→clean chunk, look-harder fires only on the first clean LOCAL round |
| INV-T5 | Consensus-unavailable run emits `ConsensusAvailable: false, ConsensusRoundsRun: 0` |
| INV-T5b | Partial-consensus (one `partial`, one `unavailable`) emits `ConsensusAvailable: true, ConsensusRoundsRun: 1` |
| INV-T6 | Convergence-log version-aware backward compat — consumers treat legacy missing fields as `null`, not `false`/`0`/`[]` |
| INV-T7 | Fragile-pass disjunct extension — `PASS, ConsensusAvailable: false` is flagged fragile |
| INV-T8 | Look-harder crash safety — chunk with fired round 1 + null round 2 recovers as "fired" via all-files scan |
| INV-T9 | Chunked-gate look-harder isolation — chunk-1's firing does NOT prevent chunk-2's first firing |
| INV-T10 | Two-phase write ordering — recovery between phases sees null and re-dispatches (protocol-safe) |
| INV-T11 | `LookHarderFiredCount` accounting — counts dispatches (clean + non-clean), NOT skipped |
| INV-T12 | `tail-rubric-already-applied` skip — first-clean at LOCAL 6 on threshold-10 emits skip reason; first-clean at LOCAL 5 fires look-harder normally |
| INV-T13 | Persistence-trigger gating uses round-N verifier status (Resolved=skip, partial-Unresolved=fire, all-Unresolved=fire); LOCAL counter for chunked gates |
| INV-T14 | F1 promotion fires on PROGRESS+`persistent_finding_count≥1`+round≥threshold+≥1 Resolved; SKIPS on fully no-op (slot #4 authoritative) |
| INV-T15 | Persistence checker error → `status: error` + `persistent_finding_count = 0` (fail-open); no re-dispatch |
| INV-T16 | Fix-input contract — `round-N-findings.md` overwritten with 2 Significants on look-harder demotion; `round-N-look-harder.md` retained as separate artifact; fix agent for round N+1 reads `round-N-findings.md` per existing convention |

### #303 Cost-Cap (INV-303-1 — INV-303-7)

| ID | Summary |
|---|---|
| INV-303-1 | Every QG round produces exactly one `round-N-ledger.md` file in the scratch dir |
| INV-303-2 | Existing scoring/stagnation/escalation algorithms receive the same inputs as before. The ledger is a NEW output channel only. v0.1 introduces no new termination paths. |
| INV-303-3 | `interactive: false` invocations never block on cost-cap or DR prompts |
| INV-303-4 | `cost_cap_threshold: null` and `dr_signal_findings: null` disable their respective prompts entirely |
| INV-303-5 | For artifacts with `suppression_threshold ≤ 3`, both `cost_cap_threshold` and `dr_signal_findings` default to `null` |
| INV-303-6 | v0.1 ledger Deferred section is empty for every round (Accept-all) |
| INV-303-7 | Every verdict marker has `CostCapSignals` field, regardless of interactive mode |
| INV-303-8 | Every round's ledger is copied to a durable `defer-ledger-<run-id>/` handoff dir before scratch cleanup, on all exit paths, so corpus seeding survives scratch deletion |

## Integration

- **crucible:red-team** — The engine that performs each review round. **Loop ownership:** Quality-gate uses red-team as a single-pass reviewer only (one dispatch = one review round, findings returned). Quality-gate owns the iteration loop, stagnation detection, and round tracking. Red-team does NOT run its own stagnation loop when invoked by quality-gate. Red-team's stagnation rules apply only when red-team is invoked directly (e.g., by `crucible:finish`).
- **crucible:design** — Produces design docs (gateable artifact)
- **crucible:planning** — Produces plans (gateable artifact)
- **crucible:debugging** — Produces hypotheses and fixes (gateable artifacts). **Note:** Debugging's Phase 5 must invoke `crucible:quality-gate` for fix review, not `crucible:red-team` directly. This ensures fixes get iteration tracking, compaction recovery, and user checkpoints.
- **crucible:mockup-builder** — Produces mockups (gateable artifact)
- **crucible:mock-to-unity** — Produces translation maps and implementations (gateable artifacts)
- **crucible:build** — Outermost orchestrator, controls all gates in pipeline
- **crucible:checkpoint** — Shadow git checkpoints before code-artifact fix rounds (recommended). Provides rollback target when fix rounds introduce regressions.
