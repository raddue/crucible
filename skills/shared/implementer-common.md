# Implementer Common -- Canonical Reference

> This file is the single source of truth for shared implementer sections.
> Prompt templates that use these sections keep inline copies marked with
> `<!-- CANONICAL: shared/implementer-common.md#section-name -->` comments.
> When updating, change this file first, then propagate to templates.
>
> **Used by:** `skills/build/build-implementer-prompt.md`, `skills/debugging/implementer-prompt.md`

## TDD Discipline

**REQUIRED SUB-SKILL:** Use `crucible:test-driven-development`

For each behavior you need to implement, follow this cycle:

1. **RED:** Write ONE failing test. Run it. Confirm it FAILS for the right reason (missing feature, not typo/error). Record the failure message.
2. **GREEN:** Write MINIMAL code to make the test pass. Run it. Confirm ALL tests pass.
3. **COMMIT:** `test: add failing test for X` is optional, but `feat: implement X` after green is required.
4. **REFACTOR:** Clean up if needed. Run tests. Confirm still green.
5. Repeat for the next behavior.

Do NOT batch -- write one test, see it fail, implement, see it pass. Then next test.

## Self-Review Checklist

Before reporting, review your work:

**Completeness:**
- Did I implement everything in the task spec?
- Did I miss any requirements?
- Are there edge cases I didn't handle?

**Quality:**
- Is this my best work?
- Are names clear and accurate?
- Is the code clean and maintainable?

**Discipline:**
- Did I avoid overbuilding (YAGNI)?
- Did I only build what was requested?
- Did I follow existing patterns in the codebase?
- Are my changes limited to the minimum necessary files?
- No unrelated changes snuck in?

**Testing (TDD Evidence):**
- For each test: can I name the failure message I saw during RED? If not, I skipped RED.
- Did I run tests between EVERY red-green step, or did I batch?
- Do tests verify behavior (not just mock interactions)?
- Are tests comprehensive?
- Did I test at the right level? (unit for isolated logic, integration for multi-component behavior)
- Am I over-mocking to avoid writing an integration test?
- Would my tests catch a regression if someone reintroduced the bug?

If you find issues during self-review, fix them (within scope) before reporting.

## Context Self-Monitoring

Be aware of your context usage. If you notice system warnings about token usage:
- At **50%+ utilization** with significant work remaining: report partial progress immediately.
  Include what you've completed, what remains, and whether work is in a safe state (tests passing or not).
- Do NOT try to rush through remaining work -- partial work with clear status
  is better than degraded output.

## Report Format

### TDD Evidence Log

The TDD Evidence Log is REQUIRED. For each test you wrote, you MUST record:
- The test name
- The exact failure message you saw during RED
- Whether there were test errors (setup issues) before the correct failure
- Confirmation of GREEN after implementing the fix

If you cannot produce a TDD log entry for a test, it means you skipped the
RED step -- go back and do it properly.

Example entries:
```
TDD Evidence Log:
- DamageCalculator_CriticalHit_DoublesDamage -- RED: "Assert.AreEqual failed. Expected: 20, Got: 0" -> GREEN: pass
- DamageCalculator_ZeroDamage_ReturnsZero -- RED: "NullReferenceException" (test error, not failure -- fixed setup, re-ran) -> RED: "Assert.AreEqual failed. Expected: 0, Got: 10" -> GREEN: pass
```
