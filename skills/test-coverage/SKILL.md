---
name: test-coverage
description: "Audit existing tests for staleness, needed updates, or removal after code changes. Use after any code modification to verify test suite alignment. Triggers on 'audit tests', 'check test alignment', 'stale tests', 'test health', or any task verifying tests match changed code. Technology-agnostic — works with any language and test framework."
---

# Test Alignment Audit

Audits whether existing tests need updating, removal, or modification after code changes. Distinct from test-gap-writer (which adds NEW tests for missing coverage) — this skill reviews the EXISTING test suite's alignment with changed code.

**Announce at start:** "Running test alignment audit on [scope description]."

**Skill type:** Rigid -- follow exactly, no shortcuts.

**Execution model:** When this skill is running, YOU are the orchestrator. You dispatch the audit and fix agents, handle conditional logic, and return results to the caller. All references to "the orchestrator" in this document refer to you.

**Technology-agnostic:** This skill works with any programming language and test framework. Examples use generic patterns. The audit agent adapts its checks to whatever language and testing conventions are present in the project.

## Why This Exists

Code changes create three categories of test debt that pass silently:

1. **Tests to update** — assertions, descriptions, or setup that are now wrong or misleading given the change. This includes tests that assert on pre-change behavior (stale assertions), tests with outdated descriptions, and tests whose helpers/utilities reference changed interfaces. Severity ranges from "assertion expects wrong value" to "test description is misleading but assertion is technically correct."
2. **Tests to delete** — test code paths that were removed. They may still pass (testing dead code that wasn't cleaned up) or may have been silently skipped.
3. **Coincidence tests** — test setup exercises the changed code, but assertions check something unrelated to the change. The test provides false confidence. These are flagged for human judgment, not auto-fixed.

Test-gap-writer handles a fourth category (missing tests for new behavior). This skill handles categories 1-3 (existing tests misaligned with changed behavior).

## When to Use

- **After debugging fixes** (debugging Phase 5 Step 2.5)
- **After build task implementation** (potential replacement for build Phase 3 Pass 2 staleness checks)
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
2. Dispatch a **Test Audit Agent** (Opus) using `./test-audit-prompt.md`
3. The agent reads the diff and affected test files, then produces a structured report
4. If findings in categories 1-2 exist (tests to update or delete): dispatch **Test Fix Agent(s)** (Opus) using `./test-fix-prompt.md`. If the audit was split (step 1), dispatch one fix agent per audit batch **sequentially** (not in parallel) to isolate revert scope. Sequential execution prevents file clobber when multiple batches have findings in shared test utilities (helpers, fixtures, conftest). Each fix agent checks `git status` before starting to confirm the tree is in the expected state. A failure in one batch does not discard successful fixes from other batches.
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

**On failure:** Reverts its own changes using `git checkout` + `git clean` (see `test-fix-prompt.md`), then verifies clean working tree with `git status`. Reports: "Attempted fix for [finding], reverted because [test failure details]. Manual intervention needed." This prevents broken test modifications from polluting the working tree. The caller decides next steps per its own protocol.

**Precondition:** The working tree must be clean when this skill starts. The caller should commit before invoking test-coverage (debugging's commit strategy handles this). In multi-batch mode, the orchestrator commits each successful batch before dispatching the next, maintaining the clean-tree invariant throughout. If uncommitted changes are detected, the fix agent reports this and does not proceed.

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
Invoke crucible:test-coverage with:
- Code diff: git diff <pre-debug-sha>..HEAD
- Affected test files: test files in subsystem identified during investigation
- Context: "Debugging fix for [hypothesis summary]"
```

### From build (Phase 3 — potential future integration)

```
Invoke crucible:test-coverage with:
- Code diff: git diff <pre-task-sha>..HEAD
- Affected test files: test files touched or related to task
- Context: "Build task N: [task description]"
```

Build's reviewer Pass 2 currently checks test health inline. A future integration could replace the staleness-detection portion of Pass 2 with this skill, letting the reviewer focus on test quality (independence, determinism, edge cases). This integration is not yet wired — the build skill would need to be updated to dispatch this skill.

### Standalone

```
Invoke crucible:test-coverage with:
- Code diff: git diff <base>..HEAD
- Context: [description of changes]
```

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

- `./test-audit-prompt.md` — Test audit agent dispatch
- `./test-fix-prompt.md` — Test fix agent dispatch (revert-on-failure, source file access)

## Integration

- **Called by:** `crucible:debugging` (Phase 5 Step 2.5), `crucible:build` (Phase 3, after test quality review), `crucible:finish` (Step 2.5, pre-merge audit), standalone invocation
- **Distinct from:** `crucible:test-driven-development` (writes tests during implementation), test-gap-writer (adds missing coverage for new behavior)
- **Does NOT use:** `crucible:quality-gate` (this is a single-pass audit, not an iterative loop)
