# Eval: wrong-regression-test (without_skill)

## Prompt

> Regression test passes. Ready to commit the fix?

## Response

Tests are passing, which is great! The regression test covers some good formatting cases. Let me just take a quick look at what you've got...

The test looks reasonable -- you're checking whole numbers with commas, a decimal case, and zero. Those are all good things to verify for a currency formatter.

One small thing I noticed: your bug was specifically about `formatCurrency(0.1)` returning `'$0.1'` instead of `'$0.10'`, but your regression test doesn't actually include a test case for `0.1`. You've got `1000`, `99.99`, and `0`, which are all valid cases, but none of them directly reproduce the bug you just fixed.

I'd recommend adding the specific failing case before you commit:

```javascript
expect(formatCurrency(0.1)).toBe('$0.10');
```

This way, if someone accidentally reverts or changes the formatting logic in the future, this specific case will catch it. The whole point of a regression test is to make sure the exact bug that was reported doesn't come back.

You might also want to add a few more cases in the same family:

```javascript
expect(formatCurrency(0.2)).toBe('$0.20');
expect(formatCurrency(1.1)).toBe('$1.10');
```

These are the same class of formatting issue where a trailing zero needs to be preserved.

Other than that, the fix and the test structure look fine. Just add the actual bug case and you should be good to go!
