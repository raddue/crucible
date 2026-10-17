---
name: verify
description: Use before claiming work is complete, fixed, or passing, committing, or creating PRs: run verification commands and confirm output; evidence before assertions. Also use after code changes to audit existing tests for stale assertions, misleading descriptions, removed code paths, and coincidence tests that pass by luck; trigger on 'audit tests', 'check test alignment', 'stale tests', or 'test health'. Technology-agnostic.
---

# Verification Before Completion

Verify work before claiming completion, fix, or passing status. Its test-alignment mode also audits existing tests after code changes.

## Contents

- [Core verification](#overview)
- [Test-alignment mode](#test-alignment-mode)
  - [Alignment protocol](#alignment-protocol)
- [Calibration ledger](#calibration-ledger-emit-tier-b-stub--standalone-only)

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

## The Bottom Line

**No shortcuts for verification.**

Run the command. Read the output. THEN claim the result.

This is non-negotiable.

## Test-alignment mode

Use this mode after code changes to audit existing tests. It is distinct from test-gap writing, which adds new tests for missing coverage.

**Triggers:** "audit tests", "check test alignment", "stale tests", "test health", or any request to verify existing tests match changed code.

### Alignment protocol

<!-- CANONICAL: shared/dispatch-convention.md -->
All subagent dispatches use disk-mediated dispatch. See `shared/dispatch-convention.md` for the full protocol.

Audits whether existing tests need updating, removal, or modification after code changes. Distinct from test-gap-writer (which adds NEW tests for missing coverage) — this skill reviews the EXISTING test suite's alignment with changed code.

**Announce at start:** "Running test alignment audit on [scope description]."

**Skill type:** Rigid -- follow exactly, no shortcuts.

**Execution model:** When this skill is running, YOU are the orchestrator. You dispatch the audit and fix agents, handle conditional logic, and return results to the caller. All references to "the orchestrator" in this document refer to you.

**Technology-agnostic:** This skill works with any programming language and test framework. Examples use generic patterns. The audit agent adapts its checks to whatever language and testing conventions are present in the project.

**Models:** Test audit and fix agents request `high`. The Claude Code examples use the current reference alias `model: opus`; other harnesses map supported profiles or omit unsupported model fields per `shared/model-tier-policy.md`.

## Why This Exists

Code changes create three categories of test debt that pass silently:

1. **Tests to update** — assertions, descriptions, or setup that are now wrong or misleading given the change. This includes tests that assert on pre-change behavior (stale assertions), tests with outdated descriptions, and tests whose helpers/utilities reference changed interfaces. Severity ranges from "assertion expects wrong value" to "test description is misleading but assertion is technically correct."
2. **Tests to delete** — test code paths that were removed. They may still pass (testing dead code that wasn't cleaned up) or may have been silently skipped.
3. **Coincidence tests** — test setup exercises the changed code, but assertions check something unrelated to the change. The test provides false confidence. These are flagged for human judgment, not auto-fixed.

Test-gap-writer handles a fourth category (missing tests for new behavior). This skill handles categories 1-3 (existing tests misaligned with changed behavior).

## When to Use

- **After debugging fixes** (debugging Phase 5 Step 2.5)
- **After build task implementation** (build Phase 3 delegates staleness checks here)
- **After any code modification** where test suite health matters
- **Before merging** as a final test alignment check
- Anytime you want to verify tests still accurately document behavior

## Inputs

The skill receives from the caller:

1. **Code diff** — the changes to audit against (`git diff <base-sha>..<head-sha>` or equivalent)
2. **Affected test files** — test files in the same subsystem or that import changed modules. The caller identifies these, or the orchestrator discovers them by checking imports and directory proximity.
3. **Context** (optional) — what the change was for (bug fix hypothesis, feature description, refactoring goal). Helps the auditor understand intent.

## How It Works

1. **Size check:** If the combined diff + test file content exceeds 2,000 lines, split the audit into multiple dispatches by test file grouping. Each dispatch gets the full diff but a subset of test files. When merging, check each dispatch's "Audit Coverage" line — if any dispatch reports unaudited files (context exhaustion), re-dispatch those files in a new batch.
2. Dispatch a **Test Audit Agent** (requested profile `high`) using `./references/test-audit-prompt.md`
3. The agent reads the diff and affected test files, then produces a structured report
4. If findings in categories 1-2 exist (tests to update or delete): dispatch **Test Fix Agent(s)** (requested profile `high`) using `./references/test-fix-prompt.md`. If the audit was split (step 1), dispatch one fix agent per audit batch **sequentially** (not in parallel) to isolate revert scope. Sequential execution prevents file clobber when multiple batches have findings in shared test utilities (helpers, fixtures, conftest). Each fix agent checks `git status` before starting to confirm the tree is in the expected state. A failure in one batch does not discard successful fixes from other batches.
5. Each fix agent reads the current source files (not just the diff) to determine correct new behavior, makes test changes, and runs affected tests
6. If modified tests fail: the fix agent reverts its own batch's changes and reports the failure
7. If modified tests pass: the orchestrator commits the batch's changes (`test: batch N alignment fixes`) before dispatching the next batch. This ensures clean revert targets for subsequent batches and prevents revert clobber of prior successes. The caller may squash these commits per its own protocol.
8. Return the combined report (audit findings + fix actions across all batches) to the caller

### Test Audit Agent

Dispatch: `Agent tool (subagent_type: "general-purpose", model: opus)`

The audit agent receives the code diff, affected test files (full source), and optional context. It checks three categories:

**Category 1 — Tests to Update:**
- Assertions that expect values the code no longer produces
- Test descriptions/names that document behavior that was changed
- Setup/arrange sections that create scenarios the code no longer supports
- Test helpers or utilities that reference changed interfaces or signatures
- Mock setups that no longer match the real implementation
- Severity: **wrong** (assertion will produce incorrect documentation of behavior) vs **misleading** (technically passes but describes old intent)

**Category 2 — Tests to Delete:**
- Tests for deleted functions, methods, or classes
- Tests for removed code branches (e.g., a removed error path)
- Tests for deprecated behavior that was cleaned up in this change
- Test files whose entire corresponding source file was deleted

**Category 3 — Coincidence Tests (flag only, do not fix):**
- Tests whose setup calls into the changed code path but whose assertions verify something unrelated to the change
- Tests where the assertion checks a property that was NOT modified by the diff, even though the test exercises code that WAS modified
- These are structurally detectable: does the test's assertion reference any value or behavior that appears in the diff? If not, and the test's setup exercises diff-affected code, it's a coincidence test.

**Evidence requirement:** Every finding must reference specific test file, test name, and the line(s) in the diff that make the test problematic. No speculation.

### Test Fix Agent

If the audit agent reports findings in categories 1-2, dispatch a fix agent (Opus) that receives:
- The audit report
- The affected test files (full source)
- The code diff

The fix agent has tool access to **read current source files** — it needs the actual current behavior (not just the diff) to write correct updated assertions.

The fix agent:
1. Updates stale assertions to match new behavior
2. Updates misleading test names/descriptions
3. Deletes tests for removed code paths
4. Does NOT modify coincidence tests (category 3) — those are flagged for the caller
5. Runs all modified test files to verify changes don't break anything

**On success:** Reports changes made (tests updated, tests deleted, all passing).

**On failure:** Reverts its own changes using `git checkout` + `git clean` (see `./references/test-fix-prompt.md`), then verifies clean working tree with `git status`. Reports: "Attempted fix for [finding], reverted because [test failure details]. Manual intervention needed." This prevents broken test modifications from polluting the working tree. The caller decides next steps per its own protocol.

**Precondition:** The working tree must be clean when this skill starts. The caller should commit before invoking verify in test-alignment mode (debugging's commit strategy handles this). In multi-batch mode, the orchestrator commits each successful batch before dispatching the next, maintaining the clean-tree invariant throughout. If uncommitted changes are detected, the fix agent reports this and does not proceed.

### Output Format

The skill returns a structured report to the caller:

```
## Test Alignment Audit Report

### Summary
- Tests audited: N
- Tests updated: N
- Tests deleted: N
- Coincidence tests flagged: N (require caller judgment)
- All modified tests passing: yes/no
- Fix agent reverts: N (if any fixes failed)

### Findings

#### Tests Updated
- `test_file::test_name` — assertion on line N expected OLD_VALUE, updated to NEW_VALUE. Diff ref: [changed line]
[repeat]

#### Tests Deleted
- `test_file::test_name` — tested removed code path [description]. Diff ref: [removed lines]
[repeat]

#### Coincidence Tests (flagged, not modified)
- `test_file::test_name` — exercises changed code but asserts on [unrelated property]. Consider updating assertion to verify [changed behavior].
[repeat]

#### Fix Failures (reverted)
- `test_file::test_name` — attempted [change], reverted because [failure reason]. Manual intervention needed.
[repeat]

### Test Run Results
- [PASS/FAIL] per modified test file
```

## Caller Integration

### From debugging (Phase 5 Step 2.5)

```
Invoke `crucible:verify` in test-alignment mode with:
- Code diff: git diff <pre-debug-sha>..HEAD
- Affected test files: test files in subsystem identified during investigation
- Context: "Debugging fix for [hypothesis summary]"
```

### From build (Phase 3, after test quality review)

```
Invoke `crucible:verify` in test-alignment mode with:
- Code diff: git diff <pre-task-sha>..HEAD
- Affected test files: test files touched or related to task
- Context: "Build task N: [task description]"
```

Build's reviewer Pass 2 focuses on test quality (independence, determinism, edge cases, test level). Staleness detection is delegated to this skill, dispatched after the implementer addresses Pass 2 findings.

### From finish (Step 2.5, pre-merge audit)

```
Invoke `crucible:verify` in test-alignment mode with:
- Code diff: git diff <base-branch>..HEAD
- Affected test files: test files in the diff or test files that import changed modules
- Context: "Finish pre-merge audit for [branch description]"
```

When finish is called by build, build tells finish to skip Step 2.5 (verify's test-alignment mode already ran per-task in Phase 3). This step only runs when finish is invoked standalone.

### Standalone

```
Invoke `crucible:verify` in test-alignment mode with:
- Code diff: git diff <base>..HEAD
- Context: [description of changes]
```

- **Host-pipeline dispatch:** When build Phase 3, debugging Phase 5, or finish Step 2.5 invokes test-alignment mode inline, do not emit a ledger row; the host owns its row. Only standalone `/verify` invocation emits, using the UUID, schema, null-field, and failure-handling mechanics above.
- **Test-alignment verdict mapping:** At the audit's single terminal emit point for standalone invocation, map to `PASS` when all affected tests pass after alignment with no coincidence flags or fix failures; map to `ESCALATED` when coincidence tests or fix failures require caller judgment. Keep `skill: "verify"`, `artifact_type: "code"`, and `gated_files` set to the audited test files.

## Guardrails

**The audit agent must NOT:**
- Write new tests (that's test-gap-writer's job)
- Modify source code (only audit test files)
- Flag style or naming issues unrelated to the change
- Speculate about test health without evidence from the diff
- Use counterfactual reasoning ("would this test pass if reverted?") — use structural checks instead

**The fix agent must NOT:**
- Modify coincidence tests (flag them, don't guess what they should assert)
- Delete tests that still test valid behavior (even if the test name is slightly misleading)
- Add new test cases (scope is updating/removing existing tests only)
- Leave failed modifications in the working tree (revert on failure)

## Red Flags

- Auditing tests without reading the code diff (can't assess staleness without knowing what changed)
- Deleting tests "to be safe" without evidence they test removed behavior
- Updating assertions to make tests pass without understanding WHY they should pass
- Confusing "test passes" with "test is correct" — a passing test can still be stale

## Prompt Templates

- `./references/test-audit-prompt.md` — Test audit agent dispatch
- `./references/test-fix-prompt.md` — Test fix agent dispatch (revert-on-failure, source file access)

## Integration

- **Called by:** `crucible:debugging` (Phase 5 Step 2.5), `crucible:build` (Phase 3, after test quality review), `crucible:finish` (Step 2.5, pre-merge audit), standalone invocation
- **Distinct from:** `crucible:test-driven-development` (writes tests during implementation), test-gap-writer (adds missing coverage for new behavior)
- **Does NOT use:** `crucible:quality-gate` (this is a single-pass audit, not an iterative loop)
