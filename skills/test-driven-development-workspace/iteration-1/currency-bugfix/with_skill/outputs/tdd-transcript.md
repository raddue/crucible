# TDD Bug Fix Transcript: formatCurrency decimal separator bug

## Bug Report

`formatCurrency(1)` returns `'$1,00'` instead of `'$1.00'`. The decimal separator is a comma instead of a period.

## Investigation

Read the source file at `src/utils/format.ts`:

```typescript
/**
 * Formats a number as a US currency string.
 * Example: 1234.5 -> "$1,234.50"
 */
export function formatCurrency(amount: number): string {
  const fixed = amount.toFixed(2);
  const [whole, decimal] = fixed.split(".");
  const withCommas = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `$${withCommas},${decimal}`;
}
```

**Root cause identified:** Line 9 uses a comma (`,`) to join the whole-number part and the decimal part in the template literal. It should use a period (`.`).

Existing test file at `src/utils/__tests__/format.test.ts` has 6 tests covering various inputs, all expecting period-separated decimals.

---

## TDD Cycle

### RED -- Write a failing test that reproduces the bug

Added a targeted regression test to `src/utils/__tests__/format.test.ts`:

```typescript
it("uses a period (not comma) as the decimal separator", () => {
  const result = formatCurrency(1);
  expect(result).toBe("$1.00");
  expect(result).not.toContain(",");
});
```

This test is specific to the reported bug: it checks that the decimal separator is a period, and explicitly asserts no comma is present (for a simple input like `1` that should have no thousands-separator commas).

### Verify RED -- Watch it fail

```
$ npx vitest run src/utils/__tests__/format.test.ts -t "uses a period"

 ❯ src/utils/__tests__/format.test.ts (7 tests | 1 failed | 6 skipped)
     × uses a period (not comma) as the decimal separator

 FAIL  src/utils/__tests__/format.test.ts > formatCurrency > uses a period (not comma) as the decimal separator
 AssertionError: expected '$1,00' to be '$1.00' // Object.is equality

 Expected: "$1.00"
 Received: "$1,00"

 Test Files  1 failed (1)
      Tests  1 failed | 6 skipped (7)
```

**Confirmed:** The test fails for the expected reason -- the function returns `$1,00` (comma) instead of `$1.00` (period). This is the bug, not a typo or test error.

All 6 pre-existing tests also fail for the same root cause (comma instead of period in the decimal separator).

### GREEN -- Minimal code to pass

Changed one character on line 9 of `src/utils/format.ts`:

```diff
-  return `$${withCommas},${decimal}`;
+  return `$${withCommas}.${decimal}`;
```

This is the simplest possible fix -- replace the comma with a period in the template literal that joins the whole-number and decimal parts.

### Verify GREEN -- Watch all tests pass

```
$ npx vitest run src/utils/__tests__/format.test.ts

 ✓ src/utils/__tests__/format.test.ts (7 tests)

 Test Files  1 passed (1)
      Tests  7 passed (7)
   Duration  1.66s
```

**Confirmed:** All 7 tests pass. Output is pristine -- no errors, no warnings.

### REFACTOR

No refactoring needed. The fix was a single-character change. The code is clean and readable. The test suite is well-organized with clear names.

---

## Final State

### `src/utils/format.ts` (fixed)

```typescript
/**
 * Formats a number as a US currency string.
 * Example: 1234.5 -> "$1,234.50"
 */
export function formatCurrency(amount: number): string {
  const fixed = amount.toFixed(2);
  const [whole, decimal] = fixed.split(".");
  const withCommas = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `$${withCommas}.${decimal}`;
}
```

### `src/utils/__tests__/format.test.ts` (with regression test)

```typescript
import { describe, it, expect } from "vitest";
import { formatCurrency } from "../format";

describe("formatCurrency", () => {
  it("should format 1 as $1.00", () => {
    expect(formatCurrency(1)).toBe("$1.00");
  });

  it("should format 0 as $0.00", () => {
    expect(formatCurrency(0)).toBe("$0.00");
  });

  it("should format 1234.5 as $1,234.50", () => {
    expect(formatCurrency(1234.5)).toBe("$1,234.50");
  });

  it("should format 1000000 as $1,000,000.00", () => {
    expect(formatCurrency(1000000)).toBe("$1,000,000.00");
  });

  it("should format 99.99 as $99.99", () => {
    expect(formatCurrency(99.99)).toBe("$99.99");
  });

  it("should format 0.5 as $0.50", () => {
    expect(formatCurrency(0.5)).toBe("$0.50");
  });

  it("uses a period (not comma) as the decimal separator", () => {
    const result = formatCurrency(1);
    expect(result).toBe("$1.00");
    expect(result).not.toContain(",");
  });
});
```

---

## Verification Checklist

- [x] Every new function/method has a test
- [x] Watched the test fail before implementing the fix
- [x] Test failed for expected reason (comma instead of period, not a typo)
- [x] Wrote minimal code to pass the test (single character change)
- [x] All tests pass (7/7)
- [x] Output pristine (no errors, warnings)
- [x] Tests use real code (no mocks)
- [x] Edge cases covered (whole numbers, decimals, zero, large numbers)
- [x] Test level matches the behavior (unit test for isolated formatting logic)
