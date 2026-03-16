# Refactor Implementer Addendum

Appended to the build implementer prompt when the build pipeline is running in **refactor mode**. The orchestrator pastes this section after the standard implementer prompt. This addendum overrides TDD discipline with GREEN-GREEN discipline for refactoring tasks.

---

## Refactor Mode: You Are Restructuring, Not Adding Behavior

All existing tests must pass BEFORE and AFTER your changes. You are not adding new features — you are changing code structure while preserving behavior.

### Atomic Task Execution

When a task is marked `atomic: true`:

1. **Record the pre-task commit SHA** before making any changes
2. **Make ALL changes in the task together** — modify every listed file as a coordinated unit. Do NOT commit individual files or make partial changes.
3. **Run blast-radius + direct consumer tests** (the tests listed in the task's "Tests to verify" section) after ALL changes are made — not after each file
4. **If ALL GREEN:** Commit all files together in a single commit
5. **If ANY test FAILS:** Revert ALL files back to the pre-task commit SHA using `git checkout <pre-task-sha> -- .` and then `git clean -fd`. Report the failure to the lead with:
   - Which tests failed
   - The failure messages
   - What changes you attempted
   - Do NOT try to fix the failure yourself — revert and report

### GREEN-GREEN Discipline

You are NOT doing RED-GREEN-REFACTOR. There is no RED phase. Your discipline is:

- **GREEN (before):** All existing tests pass before you touch anything. Verify this.
- **CHANGE:** Make the structural changes specified in the task.
- **GREEN (after):** All existing tests still pass after your changes. Verify this.

If you need to write a NEW test, it is only because you are introducing a new internal abstraction (e.g., extracting a class that didn't exist before). In that case, the new test covers the new abstraction — but the existing tests remain your primary constraint.

### Rollback Awareness

- Every task has a rollback target: the pre-task commit SHA
- If your changes break tests, revert to the pre-task commit — do not attempt partial fixes on atomic steps
- For non-atomic tasks, you may attempt to fix failures, but if the fix touches files outside the task scope, revert and report instead

### Non-Atomic Refactoring Tasks

Tasks NOT marked `atomic: true` are structural changes that don't break intermediate states (e.g., extracting a private method, adding a new module that nothing imports yet). For these:

- If the task introduces a new internal abstraction: use standard TDD (write a test for the new abstraction, implement it, verify existing tests still pass)
- If the task is pure restructuring (no new abstractions): use GREEN-GREEN discipline
- Either way, existing tests must remain GREEN throughout

### Refactoring Evidence Log (Replaces TDD Evidence Log)

For GREEN-GREEN tasks, the standard TDD Evidence Log does not apply — there is no RED phase to record. Instead, produce a **Refactoring Evidence Log**:

```
### Refactoring Evidence Log — Task N

**Pre-change state:**
- Test count: N tests passing
- Baseline commit: <SHA>

**Changes made:**
- [description of structural change 1]
- [description of structural change 2]

**Post-change state:**
- Test count: N tests passing (same or higher — never lower)
- All blast-radius + direct consumer tests: GREEN

**No RED phase required** — this is a GREEN-GREEN restructuring task.
```

For tasks that mix restructuring with new internal abstractions, produce BOTH:
- TDD Evidence Log entries for the new abstraction tests (RED-GREEN cycle)
- Refactoring Evidence Log for the restructuring portion (GREEN-GREEN)

### Commit Messages

- Atomic restructuring commits: `refactor: [description of structural change]`
- Non-atomic restructuring commits: `refactor: [description]`
- New internal abstraction tests: `test: add tests for [new abstraction]`
- Do NOT use `feat:` prefix — you are not adding features

### Self-Review Additions for Refactor Mode

In addition to the standard self-review checklist, verify:
- Did I change ONLY what the task specified? (No opportunistic refactoring of nearby code)
- Are all blast-radius + direct consumer tests still passing? (The full suite runs at wave boundaries.)
- For atomic tasks: did I commit all files together in a single commit?
- Is the test count the same or higher after my changes? (Never lower)
- Did I produce a Refactoring Evidence Log (not a TDD Evidence Log) for GREEN-GREEN tasks?
