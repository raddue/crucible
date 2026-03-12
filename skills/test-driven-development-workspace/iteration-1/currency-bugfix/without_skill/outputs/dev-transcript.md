# Currency Bug Fix -- Development Transcript

## Task

Fix `formatCurrency` in `src/utils/format.ts` which returns `$1,00` instead of `$1.00` for input `1`.

---

## Step 1: Identify the Bug

Read the source file `src/utils/format.ts`:

```ts
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

**Root cause:** Line 9 uses a comma (`,`) as the decimal separator in the template literal `` `$${withCommas},${decimal}` `` instead of a period (`.`). This means every output has its decimal portion joined with a comma rather than a period.

For input `1`:
- `amount.toFixed(2)` produces `"1.00"`
- `split(".")` produces `["1", "00"]`
- The comma regex is a no-op for single-digit numbers, so `withCommas` = `"1"`
- The return value is `` `$1,00` `` -- the bug

---

## Step 2: Write Tests (Red Phase)

Created `src/utils/__tests__/format.test.ts`:

```ts
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
});
```

**Command run:**

```bash
npx vitest run src/utils/__tests__/format.test.ts
```

**Result: 6 failed** -- all tests confirm the bug. Example output:

```
AssertionError: expected '$1,00' to be '$1.00' // Object.is equality

Expected: "$1.00"
Received: "$1,00"
```

---

## Step 3: Fix the Bug (Green Phase)

**The fix:** Change the comma to a period on line 9.

**Before:**
```ts
  return `$${withCommas},${decimal}`;
```

**After:**
```ts
  return `$${withCommas}.${decimal}`;
```

**Command run:**

The edit was a single-character change: `,` to `.` in the template literal on line 9 of `src/utils/format.ts`.

---

## Step 4: Verify the Fix

**Command run:**

```bash
npx vitest run src/utils/__tests__/format.test.ts
```

**Result: 6 passed**

```
 ✓ src/utils/__tests__/format.test.ts (6 tests) 2ms

 Test Files  1 passed (1)
      Tests  6 passed (6)
```

---

## Step 5: Final State of Fixed File

`src/utils/format.ts`:

```ts
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

---

## Summary

| Phase | Action | Result |
|-------|--------|--------|
| Identify | Read `src/utils/format.ts` | Found comma used as decimal separator on line 9 |
| Red | Wrote 6 test cases covering integers, decimals, large numbers, zero | All 6 tests failed, confirming the bug |
| Green | Changed `,` to `.` in template literal on line 9 | All 6 tests passed |

**One-character fix.** The comma (`,`) joining `withCommas` and `decimal` in the template literal was replaced with a period (`.`).

**Files modified:**
- `src/utils/format.ts` (bug fix)

**Files created:**
- `src/utils/__tests__/format.test.ts` (regression tests)
