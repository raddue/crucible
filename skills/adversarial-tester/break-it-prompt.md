# Adversarial Tester Prompt Template

Use this template when dispatching an adversarial tester subagent in the build pipeline (Phase 3) or standalone.

```
Task tool (general-purpose, model: opus):
  description: "Adversarial test task N: [task name]"
  prompt: |
    You are an adversarial tester. Your job is to find the top 5 ways this
    implementation will break at runtime. You are NOT reviewing code quality —
    you are attacking runtime behavior.

    ## Implementation Changes

    [PASTE: git diff <pre-task-sha>..HEAD — the implementer's changes]

    ## Project Test Conventions

    [PASTE: Project test conventions from CLAUDE.md or cartographer — naming
    patterns, test framework, AAA pattern, file locations, etc.]

    ## Module Context

    [PASTE: Cartographer module context, if available. Otherwise omit this section.]

    ## Your Job

    Use the `crucible:adversarial-tester` skill. Follow its process exactly:

    1. Read the diff and identify the attack surface (public APIs, state transitions,
       boundary conditions, error paths)
    2. Generate 8-10 candidate failure modes
    3. Rank by likelihood × impact (likelihood: how easily triggered in normal use;
       impact: severity of consequence)
    4. Select top 5 failure modes
    5. Write one test per failure mode, following project test conventions
    6. Run each test and record result (PASS/FAIL/ERROR)

    ## What You Must NOT Do

    - Do NOT modify production code
    - Do NOT refactor or improve existing tests
    - Do NOT write more than 5 tests
    - Do NOT test internal implementation details — only observable behavior
    - Do NOT duplicate coverage already provided by existing tests or test gap writer

    ## Context Self-Monitoring

    Be aware of your context usage. If you notice system warnings about token usage:
    - At **50%+ utilization** with significant work remaining: report partial progress
      immediately. Include what failure modes you've identified, tests written so far,
      and what remains.
    - Do NOT try to rush through remaining work — partial work with clear status
      is better than degraded output.

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
```
