<!-- DISPATCH: disk-mediated | This template is written to a dispatch file,
     not pasted into the Agent tool prompt. See shared/dispatch-convention.md -->
# Acceptance Test Writer Prompt Template

Use this template when dispatching an acceptance test writer subagent in Phase 1, Step 3. These tests define "done" at the feature level — the build pipeline starts RED and ends GREEN.

```
Task tool (general-purpose, model: opus):
  description: "Write acceptance tests for [feature]"
  prompt: |
    You are writing acceptance tests for a feature BEFORE it is implemented.
    These tests define what "done" looks like. They will fail now (the feature
    doesn't exist) and pass when the build pipeline finishes.

    ## Design Document

    [FULL TEXT of the finalized design doc — paste it here]

    ## Project Conventions

    [Test framework, test location, naming conventions, DI framework, etc.]

    ## Your Job

    Write integration-level tests that verify the feature works end-to-end.
    These are NOT unit tests — they test feature BEHAVIOR from the outside.

    **What to test:**
    - Each acceptance criterion from the design doc becomes one or more tests
    - Multi-system interactions (the seams between components)
    - User-facing behavior (what the user would observe)
    - Key failure modes mentioned in the design

    **What NOT to test:**
    - Internal implementation details (those get unit-tested during implementation)
    - How the code is structured (that's an implementation decision)
    - Every edge case (unit tests handle those — acceptance tests verify the feature)

    **Test quality:**
    - Test names describe the feature behavior, not the implementation
      - Good: `Player_UsesStealthTalent_BecomesUntargetable`
      - Bad: `StealthManager_SetStealthFlag_UpdatesTargetingList`
    - Use real components where possible, not mocks
    - Each test should be independent and deterministic
    - Follow project test conventions

    **For typed languages (C#, Java, Go, etc.):**
    - Tests may not compile because the types don't exist yet — this is expected
    - Write them as if the interfaces exist, using the names from the design doc
    - The plan's first task will create stubs so these tests compile and fail
    - Include a comment at the top: "// These tests will not compile until [types] are created"

    ## Output

    - Test file(s) with all acceptance tests
    - Brief summary: what each test verifies and which acceptance criterion it maps to
    - Note any acceptance criteria that can't be tested automatically (need manual verification)
```
