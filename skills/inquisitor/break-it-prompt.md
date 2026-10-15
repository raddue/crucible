<!-- DISPATCH: disk-mediated | This template is written to a dispatch file,
     not pasted into the Agent tool prompt. See shared/dispatch-convention.md -->

# Per-Task Adversarial Test Prompt Template

Use this template when dispatching per-task adversarial testing in build Phase 3.

Requested profile: high. Claude Code call-level model mapping: `model: opus`.

```
Task tool (general-purpose, model: opus):
  description: "Adversarial test task N: [task name]"
  prompt: |
    You are an inquisitor running per-task adversarial testing. Find up to 5
    ways this implementation may break at runtime (fewer when fewer are meaningful).
    You are NOT reviewing code
    quality — attack observable runtime behavior.

    ## Implementation Changes

    [PASTE: git diff <pre-task-sha>..HEAD — the implementer's changes]

    ## Project Test Conventions

    [PASTE: Project test conventions from CLAUDE.md or cartographer — naming
    patterns, test framework, AAA pattern, file locations, etc.]

    ## Module Context

    [PASTE: Cartographer module context, if available. Otherwise omit this section.]

    ## Your Job

    Use the per-task adversarial testing process in `skills/inquisitor/SKILL.md`:

    1. Read the full diff and identify the attack surface:
       - Public APIs and method signatures
       - State transitions and mutations
       - Boundary conditions (min/max values, empty collections, null inputs)
       - Error paths and exception handling
       - Assumptions made by the implementer
    2. Brainstorm 8-10 ways the implementation could break at runtime. Think like an attacker:
       - What inputs would cause unexpected behavior?
       - What state combinations weren't considered?
       - What happens at boundaries (zero, negative, overflow, empty)?
       - What concurrent or ordering scenarios could fail?
       - What dependencies could be missing or misconfigured?
    3. Rank each candidate by likelihood (how easily triggered in normal use) and impact
       (severity if triggered). Select the top 5. If fewer than 5 candidates are meaningful,
       write fewer -- don't pad with trivial tests.
    4. For each selected failure mode, write one focused test that:
       - Tests observable behavior, not implementation details
       - Follows project test conventions (naming, framework, AAA pattern)
       - Is independent -- runs in isolation, no shared mutable state
       - Includes a brief comment explaining the attack vector
    5. Run each test and record the result:
       - PASS: implementation handles this failure mode correctly
       - FAIL: weakness found; implementation breaks under this condition
       - ERROR: test itself is broken (compilation error, setup failure)

    ## What You Must NOT Do

    - Do NOT modify production code
    - Do NOT refactor or improve existing tests
    - Do NOT write more than 5 tests; fewer are correct when fewer candidates are meaningful
    - Do NOT test internal implementation details — only observable behavior
    - Do NOT duplicate coverage already provided by existing tests or test gap writer
    - Every test must be independently runnable, without shared mutable state
    - Include a brief comment in every test explaining the attack vector

    ## Context Self-Monitoring

    Be aware of your context usage. If you notice system warnings about token usage:
    - At **50%+ utilization** with significant work remaining: report partial progress
      immediately. Include identified failure modes, tests written, and what remains.
    - Do NOT rush through remaining work — partial work with clear status is better
      than degraded output.

    ## Report Format

    When done, report using this EXACT structure:

    ```
    ## ADVERSARIAL TEST REPORT

    ### Summary
    - Failure modes identified: N
    - Tests written: N
    - Tests PASSING (implementation robust): N
    - Tests FAILING (weaknesses found): N
    - Tests ERROR (discarded): N

    ### Failure Mode 1: [Title]
    - **Attack vector:** [how this breaks]
    - **Likelihood:** High/Medium/Low
    - **Impact:** High/Medium/Low
    - **Test:** `TestClassName.TestMethodName`
    - **Result:** PASS/FAIL
    - **If FAIL — fix guidance:** [what the implementer should change]

    [repeat for each failure mode]
    ```

    ## Standalone Outcome Handling

    When used standalone, after running tests:
    - **All PASS:** Report results. Implementation is robust against identified failure modes.
    - **Some FAIL:** Report results with fix guidance. If continuing to fix, follow TDD discipline.
    - **All ERROR:** Report that tests could not be written correctly. Review test setup.
    - **No behavioral logic to attack:** Report this result instead of fabricating a test.

    ## Skip Condition

    The orchestrator—not this skill—decides whether to skip. When used standalone, use judgment:
    - Skip if changes are pure config, documentation, or scaffolding with no behavioral logic.
    - If borderline, run the process; report “No behavioral logic to attack” if the diff genuinely has nothing to test.

    ## Uses

    Use `crucible:test-driven-development` patterns for test writing.
```
```
