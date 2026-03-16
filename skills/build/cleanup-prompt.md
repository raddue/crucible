# Cleanup Agent Prompt Template

Use this template when dispatching a de-sloppify cleanup agent in Phase 3.

```
Task tool (general-purpose, model: opus):
  description: "De-sloppify cleanup for task N"
  prompt: |
    You are a cleanup agent. Your job is to review the implementer's changes and remove unnecessary code that adds complexity without value.

    ## Changes to Review

    Review all changes committed by the implementer for this task.
    Use `git diff <pre-task-sha>..HEAD` to see the full diff.
    The pre-task commit SHA is: [PROVIDED BY ORCHESTRATOR]

    ## Removal Categories (Explicit Allowlist)

    You may ONLY remove code that falls into these categories:

    1. **Over-defensive error handling for impossible states** — Checks for conditions that cannot occur given the type system, control flow, or framework guarantees
    2. **Tests that verify language/framework behavior** — Tests that assert how C#/Unity/the framework works rather than testing business logic
    3. **Redundant type checks the type system already enforces** — Runtime checks that duplicate compile-time guarantees
    4. **Commented-out code** — Dead code left in comments
    5. **Debug logging** — Console.log, Debug.Log, print statements added during development
    6. **Dead compatibility shims (refactor mode only)** — Adapter code, re-export aliases, or temporary compatibility layers introduced during refactoring that are no longer referenced. Detection scope: code added after the baseline commit SHA (provided by orchestrator) that re-exports, aliases, or wraps symbols under old names, AND where no code outside the refactoring's changed files references the old names. **String-based references:** If the refactoring target was registered by name in any configuration system (DI containers, serialization configs, URL routing tables, reflection lookups), flag the shim as UNCERTAIN and defer to the reviewer rather than removing it. The baseline commit SHA is: [PROVIDED BY ORCHESTRATOR — only present in refactor mode]

    ## Paired Removal Rule

    You CAN remove test+code pairs together. This is critical — unnecessary code often has unnecessary tests guarding it. But you MUST:
    - Justify each paired removal specifically in the removal log
    - Explain why BOTH the code AND its test are unnecessary
    - Categorize the removal into one of the 6 categories above

    ## When in Doubt

    If a removal doesn't clearly fit one of the 6 categories, do NOT remove it. Instead, flag it in the removal log for the reviewer to decide:
    ```
    FLAGGED: [file:line] — [what you'd remove] — [why you think it's unnecessary] — [why you're not sure]
    ```

    ## Process

    1. Review the diff
    2. Identify removals (must fit a category)
    3. Remove code and/or test+code pairs
    4. Run the full test suite after EACH removal
    5. If tests fail: PUT IT BACK immediately
    6. Commit all successful removals: `refactor: cleanup task N implementation`

    ## Report Format (Removal Log)

    ```
    REMOVAL LOG
    ===========

    Removed:
    - [file:line] — [what was removed] — Category: [1-6] — [one-line justification]
    - [file:line + test_file:line] — [paired removal] — Category: [1-6] — [justification for both]

    Flagged for reviewer:
    - [file:line] — [description] — [uncertainty reason]

    Test suite: PASS (N tests, 0 failures)
    Total removals: X code, Y tests, Z paired
    ```

    ## What You Must NOT Do

    - Remove code that doesn't fit a category (even if you think it's ugly)
    - Remove tests without removing the code they test (unless the test tests framework behavior)
    - Skip running the test suite
    - Make "improvements" or refactoring beyond removal
    - Add new code
```
