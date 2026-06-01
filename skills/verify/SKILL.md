---
name: verify
description: Use when about to claim work is complete, fixed, or passing, before committing or creating PRs - requires running verification commands and confirming output before making any success claims; evidence before assertions always
---

# Verification Before Completion

## Overview

Claiming work is complete without verification is dishonesty, not efficiency.

**Core principle:** Evidence before claims, always.

**Violating the letter of this rule is violating the spirit of this rule.**

## The Iron Law

```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

If you haven't run the verification command in this message, you cannot claim it passes.

## The Gate Function

```
BEFORE claiming any status or expressing satisfaction:

1. IDENTIFY: What command proves this claim?
2. RUN: Execute the FULL command (fresh, complete)
3. READ: Full output, check exit code, count failures
4. VERIFY: Does output confirm the claim?
   - If NO: State actual status with evidence
   - If YES: State claim WITH evidence
5. ONLY THEN: Make the claim

Skip any step = lying, not verifying
```

## Common Failures

| Claim | Requires | Not Sufficient |
|-------|----------|----------------|
| Tests pass | Test command output: 0 failures | Previous run, "should pass" |
| Linter clean | Linter output: 0 errors | Partial check, extrapolation |
| Build succeeds | Build command: exit 0 | Linter passing, logs look good |
| Bug fixed | Test original symptom: passes | Code changed, assumed fixed |
| Regression test works | Red-green cycle verified | Test passes once |
| Agent completed | VCS diff shows changes | Agent reports "success" |
| Requirements met | Line-by-line checklist | Tests passing |

## Red Flags - STOP

- Using "should", "probably", "seems to"
- Expressing satisfaction before verification ("Great!", "Perfect!", "Done!", etc.)
- About to commit/push/PR without verification
- Trusting agent success reports
- Relying on partial verification
- Thinking "just this once"
- Tired and wanting work over
- **ANY wording implying success without having run verification**

## Rationalization Prevention

| Excuse | Reality |
|--------|---------|
| "Should work now" | RUN the verification |
| "I'm confident" | Confidence ≠ evidence |
| "Just this once" | No exceptions |
| "Linter passed" | Linter ≠ compiler |
| "Agent said success" | Verify independently |
| "I'm tired" | Exhaustion ≠ excuse |
| "Partial check is enough" | Partial proves nothing |
| "Different words so rule doesn't apply" | Spirit over letter |

## Key Patterns

**Tests:**
```
✅ [Run test command] [See: 34/34 pass] "All tests pass"
❌ "Should pass now" / "Looks correct"
```

**Regression tests (TDD Red-Green):**
```
✅ Write → Run (pass) → Revert fix → Run (MUST FAIL) → Restore → Run (pass)
❌ "I've written a regression test" (without red-green verification)
```

**Build:**
```
✅ [Run build] [See: exit 0] "Build passes"
❌ "Linter passed" (linter doesn't check compilation)
```

**Requirements:**
```
✅ Re-read plan → Create checklist → Verify each → Report gaps or completion
❌ "Tests pass, phase complete"
```

**Agent delegation:**
```
✅ Agent reports success → Check VCS diff → Verify changes → Report actual state
❌ Trust agent report
```

## Why This Matters

From 24 failure memories:
- your human partner said "I don't believe you" - trust broken
- Undefined functions shipped - would crash
- Missing requirements shipped - incomplete features
- Time wasted on false completion → redirect → rework
- Violates: "Honesty is a core value. If you lie, you'll be replaced."

## When To Apply

**ALWAYS before:**
- ANY variation of success/completion claims
- ANY expression of satisfaction
- ANY positive statement about work state
- Committing, PR creation, task completion
- Moving to next task
- Delegating to agents

**Rule applies to:**
- Exact phrases
- Paraphrases and synonyms
- Implications of success
- ANY communication suggesting completion/correctness

## Calibration ledger emit (Tier B stub — standalone only)

<!-- CANONICAL: shared/ledger-append.md -->

**Standalone top-level invocation ONLY.** Emit a ledger row IFF `verify` was invoked as its own top-level run (a user `/verify`, or an orchestrator dispatching it as a discrete step that owns a run). When this skill's discipline is applied **inline** before another skill's completion claim — the common case — emit **nothing**; that host skill owns its own ledger row. Verify has no run lifecycle of its own when applied inline, so there is no `run_id` to mint and nothing to emit. This precondition is non-negotiable: a naive per-application emit would flood the ledger.

When (and only when) running standalone, at the terminal verdict emit ONE **Tier B STUB** JSONL line to the **central ledger** (`~/.claude/crucible/ledger/runs.jsonl`) via the `emit` CLI per `skills/shared/ledger-append.md` — resolve `scripts/ledger_append.py` by absolute path from the plugin root and run `python3 <script> emit - '<json>'`.

- Mint exactly ONE UUIDv7 (`scripts/uuid7.py`) at the start of the standalone run and reuse it for the single emit at the terminal verdict (not mid-flow). `(run_id, skill="verify")` dedup (L-2) guarantees idempotency.
- The `emit` CLI owns the mechanics: graceful skip on `CRUCIBLE_CALIBRATION_DISABLED=1` (L-6), and auto-fill of `repo` + `schema_version`. If the script can't be resolved, warn to stderr and skip — a missing emit must **never block** the skill.
- Populate ONLY meaningful values: `schema_version: 2`, `run_id`, `skill: "verify"`, `tier: "B"`, `verdict` (claim verified by fresh evidence → `PASS`; claim falsified by evidence → `FAIL`; could not verify → `ESCALATED`), `timestamp` (ISO-8601 UTC), `gated_files` (what was verified, repo-relative), `artifact_type` (per what was verified; default `code`).
- Set ALL calibration fields EXPLICITLY null per "Tier-B null semantics": `severity_histogram`, `highest_finding`, `would_have_shipped_without_gate`, `findings_count`, `confidence`, `chunk_hash`, `rounds`, `predicted_falsifier` — all `null`. Also `gated_files_truncated: 0`, `comment: null`, `backfilled: false`, `falsified: null`, `falsified_by: null`.
- **No advisory wiring.** Verify produces no confidence-weighted verdict, so Brier is not viable and there is no `brier_advisory` read here by design.

## The Bottom Line

**No shortcuts for verification.**

Run the command. Read the output. THEN claim the result.

This is non-negotiable.
