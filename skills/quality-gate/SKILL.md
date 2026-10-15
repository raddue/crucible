---
name: quality-gate
description: Iterative adversarial review and remediation of artifacts until clean or stagnation. Use for quality gate, red-team this design/plan/code/PR/documentation, adversarial review, multi-model consensus or stagnation judge, audit dependencies, scan vulnerabilities, and check CVEs; includes standalone red-team mode and dependency-audit preflight lane.
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

## Runbook — read before dispatch

Choose mode from the invocation. **Full gate** owns the multi-round review and fix loop; **red-team mode** preserves the standalone full-loop and single-pass caller semantics in `red-team-mode.md`. **Dependency-audit mode** produces an independent supply-chain result from `dependency-audit.md`; it never changes the weighted adversarial score. Consensus is optional; see `consensus-mechanism.md` and `receipt-consensus.md` when enabled.

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
