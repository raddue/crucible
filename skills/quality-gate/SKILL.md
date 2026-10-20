---
name: quality-gate
description: Runs iterative adversarial review and remediation of artifacts until clean or stagnation. Applies when asked for a quality gate, to red-team this design, plan, code, PR, or documentation, invoke multi-model consensus or a stagnation judge, audit dependencies, scan vulnerabilities, or check CVEs. Includes standalone red-team and dependency-audit modes.
origin: crucible
---

# Quality Gate

<!-- CANONICAL: shared/dispatch-convention.md -->
All subagent dispatches use disk-mediated dispatch. See `shared/dispatch-convention.md` for the full protocol.

<!-- CANONICAL: shared/return-convention.md -->
All subagent returns (red-team agents, judges, fix agents) use the Ledger Return Protocol. Every subagent returns exactly one Evidence Receipt per `shared/return-convention.md`; the orchestrator applies the two-tier receipt linter (see `receipt-consensus.md` › Receipt Linter) to every Task return before acting on the declared VERDICT.

<!-- CANONICAL: shared/cairn-convention.md -->
The gate maintains an Invariant Cairn per `shared/cairn-convention.md`. Each gate round is a cairn phase. See `receipt-consensus.md` › Cairn (Layer 3).

Shared iterative red-teaming mechanism invoked at the end of artifact-producing skills. Provides rigorous adversarial review as the core quality mechanism.

**Announce at start:** "Running quality gate on [artifact type]." For direct red-team and dependency-audit modes use their preserved mode-specific announcements instead.

**Skill type:** Rigid -- follow exactly, no shortcuts.

**Execution model:** When this skill is running, YOU are the orchestrator. You drive the loop, dispatch fix agents and reviewers as subagents, track scores, and make escalation decisions. All references to "the orchestrator" in this document refer to you.

**Runtime:** Size any coordinator deadline to artifact scope and expected review/fix rounds; large or uncertain gates need hours, not a blanket 15-minute cap. Let async completion events drive waits. If a child is still active, check its status about every 15 minutes only when a supported scheduled-wake facility is available; otherwise wait for its completion event without polling or shell sleep. Before coordinator-budget expiry, save durable evidence and handoff as available. If a hard deadline interrupts the run, mark it incomplete/blocked, never PASS; resume only on an explicit later invocation through existing recovery. Keep child-level transport timeouts separate from the coordinator budget.

## Runbook — read before dispatch

Choose mode from the invocation: a full-gate caller uses the single-pass reviewer inside its gate; a direct "red-team this" request uses the standalone red-team loop; a dependency/CVE request uses only the audit lane. **Full gate** owns the multi-round review and fix loop; **red-team mode** preserves the standalone full-loop and single-pass caller semantics in `red-team-mode.md`. **Dependency-audit mode** produces an independent supply-chain result from `dependency-audit.md`; the parent invokes it in parallel with the full gate for code artifacts, and it never changes the weighted adversarial score. Consensus is optional; see `consensus-mechanism.md` and `receipt-consensus.md` when enabled.

Read these flat references in order for a full gate. They preserve the original runbook text and CONTRACT anchors; do not skip a referenced phase:

1. `receipt-consensus.md` — receipt lint, cairn/tripwire, consensus bridge.
2. `loop.md` — arguments, closure modes, review rounds, scoring, red-team dispatch.
3. `cost-fix.md` — cost signals, fixes and verification.
4. `stagnation.md` — stagnation judge, persistence and fix-generated defect tracking.
5. `artifact-preflight.md` — artifact preparation, dependency-audit lane, siege and anti-anchoring.
6. `recovery.md` — round history and compaction recovery.
7. `verdict.md` — verdict marker and exit precedence.
8. `telemetry-invariants.md` — convergence telemetry, invocation, invariants and integrations.

Standalone red-team: read `red-team-mode.md` and `red-team-prompt.md`. Consensus: read `consensus-mechanism.md` and its `aggregation-*-prompt.md` files as needed. Dependency audit: read `dependency-audit.md`. These are direct references, not nested workflows.

Checklist: select mode and artifact → load its reference(s) → run preflight and dispatch → lint returns → score and fix or escalate → re-review with fresh eyes → verify terminal verdict. If verification fails, return to the affected round; never declare PASS from an unverified receipt. Announce the selected mode at start.
