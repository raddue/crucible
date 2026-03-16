# Contract Test Writer Prompt Template

Use this template when dispatching a contract test writer subagent in refactor-mode Phase 1. These tests lock existing behavior before refactoring begins — the build pipeline starts GREEN and must stay GREEN throughout.

This is NOT a variant of `acceptance-test-writer-prompt.md`. It has different inputs (impact manifest + blast radius file list) and a different goal (lock current behavior, not define new behavior).

```
Task tool (general-purpose, model: opus):
  description: "Write contract tests for [target] refactoring"
  prompt: |
    You are writing contract tests to lock existing behavior BEFORE a
    refactoring begins. These tests capture what the code does NOW, so
    that any refactoring step that breaks existing behavior is caught
    immediately.

    ## Impact Manifest

    [FULL TEXT of the impact manifest from blast radius analysis — paste it here]

    ## Blast Radius File List

    [FULL LIST of files in the blast radius — paste file paths here]

    ## Project Conventions

    [Test framework, test location, naming conventions, DI framework, etc.]

    ## Your Job

    Perform three steps in order:

    ### Step 1: Map Existing Tests to Behavioral Seams

    Read the test files that already exist for the target and its consumers.
    For each behavioral seam in the blast radius, identify whether an existing
    test already covers it. A "behavioral seam" is any point where the target
    code's behavior is observable by a consumer — method calls, return values,
    side effects, error conditions, event emissions, state transitions.

    Output a mapping:
    - Seam: [description] → Covered by: [test name] or UNCOVERED

    ### Step 2: Identify Untested Seams (Gaps)

    From the mapping above, list every UNCOVERED seam. These are the gaps
    where refactoring could silently break behavior.

    For each gap, note:
    - What behavior the seam exercises
    - Which consumers depend on this behavior
    - Why it matters for the refactoring (what could break)

    ### Step 3: Write Contract Tests for Gaps

    For each identified gap, write a contract test that locks the CURRENT
    behavior. Critical rules:

    **Lock current behavior, not desired behavior:**
    - If the code returns null on invalid input, your test asserts null — even
      if that seems like a bug. You are locking what EXISTS, not what SHOULD exist.
    - If the code silently swallows an exception, your test asserts no exception —
      even if that seems wrong.

    **Do not write tests for already-covered seams:**
    - If Step 1 shows a seam is already tested, skip it. Do not duplicate coverage.

    **Test naming convention:**
    - Name tests to indicate they are contract tests:
      `ContractTest_[Target]_[Seam]_[ExpectedBehavior]`

    **Test quality:**
    - Use real components where possible, not mocks
    - Each test should be independent and deterministic
    - Follow project test conventions
    - Test at the behavioral boundary (consumer-facing), not internal implementation

    ### Running the Tests

    After writing all contract tests:
    1. Run them ALL
    2. Every contract test MUST pass GREEN — you are locking existing behavior
    3. If a contract test FAILS, investigate:
       - **Test defect** (wrong assertion, bad setup, misunderstood seam):
         Fix the test and re-run.
       - **Latent codebase bug** (the existing code genuinely doesn't match
         expected behavior): Report to the user with three options:
         (a) Fix the bug first before proceeding with the refactoring
         (b) Exclude this seam from contract test coverage and accept the risk
         (c) Abort the refactoring entirely
       - NEVER silently drop a failing contract test or adjust its assertion
         to match unexpected behavior without reporting to the user.

    ### Proportionality Check

    Before writing tests, count the gaps. If any of the following are true,
    STOP and report to the orchestrator before writing tests:
    - More than 15 contract tests would be needed
    - The number of contract tests would exceed the number of planned
      refactoring tasks
    - You are approaching context limits
    - Estimated total contract test LOC exceeds ~2x the estimated
      refactoring scope LOC

    The orchestrator will present the gap list to the user for prioritization.

    ## Output

    - Seam mapping (Step 1 results)
    - Gap list (Step 2 results)
    - Contract test file(s) with all new tests
    - Per-test run results (test name: PASS or FAIL with details)
    - Summary: N seams found, M already covered, K contract tests written,
      all GREEN / X failures reported
    - Commit with message: `test: add contract tests for [target] refactoring (GREEN — locking existing behavior)`
```
