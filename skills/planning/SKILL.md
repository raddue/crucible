---
name: planning
description: Use when you have a spec or requirements for a multi-step task, before touching code
---

# Writing Plans

## Overview

Write comprehensive implementation plans assuming the engineer has zero context for our codebase and questionable taste. Document everything they need to know: which files to touch for each task, code, testing, docs they might need to check, how to test it. Give them the whole plan as bite-sized tasks. DRY. YAGNI. TDD. Frequent commits.

Assume they are a skilled developer, but know almost nothing about our toolset or problem domain. Assume they don't know good test design very well.

**Announce at start:** "I'm using the planning skill to create the implementation plan."

**Context:** This should be run in a dedicated worktree (created by design skill).

**Save plans to:** `docs/plans/YYYY-MM-DD-<feature-name>.md`

## Bite-Sized Task Granularity

**Each step is one action (2-5 minutes):**
- "Write the failing test" - step
- "Run it to make sure it fails" - step
- "Implement the minimal code to make the test pass" - step
- "Run the tests and make sure they pass" - step
- "Commit" - step

## Plan Document Header

**Every plan MUST start with this header:**

```markdown
# [Feature Name] Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use crucible:build to implement this plan task-by-task.

**Goal:** [One sentence describing what this builds]

**Architecture:** [2-3 sentences about approach]

**Tech Stack:** [Key technologies/libraries]

---
```

## Task Structure

```markdown
### Task N: [Component Name]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py:123-145`
- Test: `tests/exact/path/to/test.py`

**Step 1: Write the failing test**

```python
def test_specific_behavior():
    result = function(input)
    assert result == expected
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/path/test.py::test_name -v`
Expected: FAIL with "function not defined"

**Step 3: Write minimal implementation**

```python
def function(input):
    return expected
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/path/test.py::test_name -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/path/test.py src/path/file.py
git commit -m "feat: add specific feature"
```
```

## Refactoring Task Format

When the build orchestrator indicates **refactor mode**, tasks carry additional metadata and constraints. These extend the standard task structure above — all standard requirements (file paths, complete content, per-step detail) still apply.

### Preserve-Behavior Constraint

Every refactoring task carries an implicit constraint: **existing tests must stay green.** Make this explicit:

- Each task specifies which existing tests exercise the code being changed (in a "Tests to verify" field)
- The "expected output" for each step is "all existing tests still pass" (not "new test passes")
- Tasks that intentionally change an interface specify which tests will need updating and why

### Atomic Step Metadata

When a task modifies a public interface (method signature, class name, module export, type definition), the planner:

1. Traces all consumers of that interface (from the blast radius analysis)
2. Bundles the interface change + all consumer updates into a single task marked `atomic: true`
3. Independent consumers that don't interact with each other can be split into parallel atomic tasks

**Refactoring task metadata format:**

```markdown
### Task N: [Description]
- **Files:** file1.py, file2.py, file3.py (N files)
- **Complexity:** Low | Medium | High
- **Dependencies:** Task X, Task Y (or "None")
- **Atomic:** true | false — [reason if true, e.g., "intermediate state breaks imports"]
- **Restructuring-only:** true | false — true if no signature/control-flow changes
- **Safe-partial:** true | false — true if codebase is shippable after this task
- **Rollback:** git revert to pre-task commit
- **Tests to verify:** test_file1.py, test_file2.py (blast-radius + consumer tests)
```

### Consumer Migration Fan-Out

When an interface changes and consumers are independent, create parallel tasks:

```
Task 3: Update auth module consumers (atomic)
Task 4: Update API module consumers (atomic)    <- parallel with Task 3
Task 5: Update middleware consumers (atomic)     <- parallel with Task 3 & 4
```

Explicitly declare dependencies between consumer migrations. Independent consumers get parallel tasks. Consumers that depend on each other get sequential tasks.

### Bite-Sized Step Exception for Atomic Tasks

Atomic tasks are an exception to the bite-sized step rule. An atomic task's entire coordinated change is one commit-unit — the interface change plus all consumer updates land in a single commit. Internal steps within an atomic task (e.g., "Step 1: rename class", "Step 2: run tests", "Step 3: commit") are execution guidance, not separate commit points. Do NOT split an atomic task into multiple bite-sized tasks.

### Restructuring-Only Annotation Heuristic

A task is `restructuring-only: true` if it changes no method signatures, no parameter types, no return types, and no control flow:
- **True:** Renames where all call sites are mechanically updated, file moves with updated paths, extract-method where the extracted method is private and preserves the original call signature
- **False:** Extract-class where callers must change call targets, splitting a module where consumers must update imports, any change where the consumer-facing API surface shifts

When in doubt, default to `false` — unnecessary adversarial testing (false positive) is cheap; skipping it (false negative) risks silent breakage.

## Quality Gate

This skill produces **implementation plans**. When used standalone, invoke `crucible:quality-gate` after the plan is saved. When used as a sub-skill of build, the parent orchestrator handles gating.

**Standalone invocation:**
1. Plan is saved
2. Invoke `crucible:quality-gate` with artifact type "plan"
3. Address any findings, revise plan
4. Quality gate iterates until clean or stagnation is detected

## Remember
- Exact file paths always
- Complete code in plan (not "add validation")
- Exact commands with expected output
- Reference relevant skills with @ syntax
- DRY, YAGNI, TDD, frequent commits

## Integration

**Related skills:** crucible:design, crucible:build, crucible:worktree, crucible:quality-gate
