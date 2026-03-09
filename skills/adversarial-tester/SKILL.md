---
name: adversarial-tester
description: "Use after completing implementation to find unknown failure modes. Reads implementation diff and writes up to 5 tests designed to make it break. Triggers on 'break it', 'adversarial test', 'stress test implementation', 'find weaknesses', or any task seeking to expose unknown failure modes."
---

# Adversarial Tester

Read completed implementation and write up to 5 tests designed to make it break. Targets edge cases, boundary conditions, and failure modes the implementer didn't anticipate.

**Announce at start:** "I'm using the adversarial-tester skill to find weaknesses in this implementation."

**Skill type:** Rigid -- follow exactly, no shortcuts.

**Model:** Opus (adversarial reasoning about failure modes requires creative analytical thinking)

## Distinction from Related Skills

| Agent | Question | Output | Scope |
|-------|----------|--------|-------|
| Red-team | "What's wrong with this artifact?" | Written findings (Fatal/Significant/Minor) | Attacks designs, plans, code quality |
| Test Gap Writer | "What known gaps need filling?" | Executable tests (expected to PASS) | Fills reviewer-identified holes |
| Adversarial Tester | "What runtime behavior will break?" | Executable tests (may PASS or FAIL) | Finds unknown weaknesses in behavior |

## Process

### Step 1: Read the Implementation

Read the full diff of the implementation changes. Identify:
- Public APIs and method signatures
- State transitions and mutations
- Boundary conditions (min/max values, empty collections, null inputs)
- Error paths and exception handling
- Assumptions made by the implementer

### Step 2: Generate Candidate Failure Modes

Brainstorm 8-10 ways the implementation could break at runtime. Think like an attacker:
- What inputs would cause unexpected behavior?
- What state combinations weren't considered?
- What happens at boundaries (zero, negative, overflow, empty)?
- What concurrent or ordering scenarios could fail?
- What dependencies could be missing or misconfigured?

### Step 3: Rank and Select

Rank each candidate by:
- **Likelihood:** How easily triggered in normal use (High/Medium/Low)
- **Impact:** Severity of consequence if triggered (High/Medium/Low)

Select the top 5. If fewer than 5 candidates are meaningful, write fewer -- don't pad with trivial tests.

### Step 4: Write Tests

For each selected failure mode, write one focused test that:
- Tests observable behavior, not implementation details
- Follows project test conventions (naming, framework, AAA pattern)
- Is independent -- runs in isolation, no shared mutable state
- Includes a brief comment explaining the attack vector

### Step 5: Run and Record

Run each test and record the result:
- **PASS** -- Implementation handles this failure mode correctly
- **FAIL** -- Weakness found; the implementation breaks under this condition
- **ERROR** -- Test itself is broken (compilation error, setup failure)

### Step 6: Report

Output the ADVERSARIAL TEST REPORT (see Report Format below).

## Report Format

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
- **If FAIL -- fix guidance:** [what the implementer should change]

[repeat for each failure mode]
```

## Guardrails

**Must NOT do:**
- Modify production code
- Write more than 5 tests
- Refactor or "improve" existing tests
- Test implementation details (only test observable behavior)
- Duplicate coverage already provided by existing tests

## Outcome Handling

When used standalone, after running the tests:
- **All PASS:** Report results. Implementation is robust against identified failure modes.
- **Some FAIL:** Report results with fix guidance. If continuing to fix, follow TDD discipline.
- **All ERROR:** Report that tests couldn't be written correctly. Review test setup.

When used within the build pipeline, the orchestrator handles outcome routing (see build skill Phase 3).

## Skip Condition

The **orchestrator** (not this skill) decides whether to skip. When used standalone, use your judgment:
- Skip if the changes are pure config, documentation, or scaffolding with no behavioral logic
- If borderline, run the process -- you can report "No behavioral logic to attack" if the diff genuinely has nothing to test

## Build Pipeline Integration

When dispatched by the build pipeline:

**Fix loop mechanics:**
- All tests PASS -> log and proceed to task complete
- Some tests FAIL -> implementer fixes, re-run all tests (including adversarial). If pass -> done. If fail -> one more attempt, then escalate
- Tests ERROR -> discard broken tests, log, proceed to task complete
- Quality bypass prevention: if implementer's fix touches 3+ files -> lightweight code review before completing

**Orchestrator skip conditions:**
- Task diff contains no behavioral source files (only `.md`, `.json`, `.yaml`, `.uss`, `.uxml`)
- No tests were written during implementation (pure scaffolding)

## Quality Gate

This skill produces **adversarial tests**. When used standalone, the tests themselves are the quality mechanism -- no additional quality gate needed. When used within the build pipeline, the orchestrator handles outcome routing.

## Integration

- **Called by:** `crucible:build` (Phase 3, after test gap writer)
- **Uses:** `crucible:test-driven-development` patterns for test writing
- **Pairs with:** `crucible:code-review` (lightweight review if fix touches 3+ files)
- **Prompt template:** `break-it-prompt.md` (for subagent dispatch)
