<!-- DISPATCH: disk-mediated | This template is written to a dispatch file,
     not pasted into the Agent tool prompt. See shared/dispatch-convention.md -->

# Per-Task Adversarial Test Prompt Template

Use this template when dispatching per-task adversarial testing in build Phase 3.

Requested profile: high. Claude Code call-level model mapping: `model: opus`.

```
Task tool (general-purpose, model: opus):
  description: "Adversarial test task N: [task name]"
  prompt: |
    You are an inquisitor running per-task adversarial testing. Find the top 5
    ways this implementation may break at runtime. You are NOT reviewing code
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

    1. Read the diff and identify the attack surface (public APIs, state transitions,
       boundary conditions, error paths)
    2. Generate 8-10 candidate failure modes
    3. Rank by likelihood × impact (likelihood: how easily triggered in normal use;
       impact: severity of consequence)
    4. Select up to 5 meaningful failure modes; do not pad
    5. Write one focused test per failure mode, following project conventions
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
```
