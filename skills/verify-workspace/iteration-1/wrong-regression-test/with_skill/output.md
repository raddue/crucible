# Eval: wrong-regression-test (with_skill)

## Prompt

> Regression test passes. Ready to commit the fix?

## Response

**STOP.** I am about to be asked to confirm a completion claim. The Iron Law applies: NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE.

**Applying the Gate Function:**

**Step 1 - IDENTIFY:** What proves the claim "regression test is ready to commit"? Per the Common Failures table, a valid regression test requires: "Red-green cycle verified." But before we even get to the red-green cycle, the regression test must actually *test the bug that was fixed*. Let me verify that first.

**Step 2 & 3 - RUN and READ:** The stated bug is: `formatCurrency(0.1)` was returning `'$0.1'` instead of `'$0.10'`. Now let me read the regression test assertions:

```javascript
expect(formatCurrency(1000)).toBe('$1,000.00');
expect(formatCurrency(99.99)).toBe('$99.99');
expect(formatCurrency(0)).toBe('$0.00');
```

**Step 4 - VERIFY:** Does the regression test actually test the reported bug?

**No. It does not.** The bug was specifically about `formatCurrency(0.1)` producing `'$0.1'` instead of `'$0.10'`. The regression test does not call `formatCurrency(0.1)` at all. The three values tested are `1000`, `99.99`, and `0` -- none of which reproduce the original defect.

This is a critical failure. The test is named "regression: should format small decimals correctly" but it tests no small decimals with trailing-zero issues. This test would pass equally well *with or without the bug fix*, which means it provides zero regression protection. It is a false-confidence test.

**Step 5 - CLAIM (with evidence):** This is **not ready to commit.** The regression test does not test the bug it claims to guard against.

**What must change:**

1. **Add the actual bug case to the test:**
   ```javascript
   expect(formatCurrency(0.1)).toBe('$0.10');
   ```

2. **Add related edge cases from the same bug class** (single trailing decimal requiring zero-padding):
   ```javascript
   expect(formatCurrency(0.2)).toBe('$0.20');
   expect(formatCurrency(0.01)).toBe('$0.01');
   expect(formatCurrency(1.1)).toBe('$1.10');
   expect(formatCurrency(1.5)).toBe('$1.50');
   expect(formatCurrency(100.3)).toBe('$100.30');
   ```

3. **Verify the red-green cycle:** After writing the corrected test, you need to confirm it actually fails when the fix is reverted. A regression test that passes regardless of the fix is worthless. The pattern is: Write test, run (should pass), revert fix, run (MUST FAIL), restore fix, run (should pass again). If the test passes even with the fix reverted, it is not a regression test -- it is decoration.

The Red Flags checklist caught this: I was being asked to express satisfaction ("ready to commit") about a test that provides false confidence. The Rationalization Prevention table applies directly -- "Partial check is enough" is listed, and reality says "Partial proves nothing." A regression test that does not test the regression proves nothing.
