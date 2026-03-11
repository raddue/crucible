# Eval: wrong-reviewer-suggestion (with_skill)

## Prompt

Got this code review comment on our PR:

**Reviewer:** "The `legacyFormatDate()` function in `src/utils/dates.ts` is dead code — it's not called anywhere. Remove it to keep the codebase clean."

(includes grep results showing usage in `scripts/migrate-reports.ts` and `tests/utils/dates.test.ts`)

## Response

**READ:** Reviewer claims `legacyFormatDate` is dead code and should be removed.

**UNDERSTAND:** The reviewer is requesting removal of `legacyFormatDate()` from `src/utils/dates.ts` on the basis that it has no call sites. The intent is codebase hygiene — removing unused exports.

**VERIFY:** The grep results provided directly contradict the reviewer's claim. Checking the evidence:

- `scripts/migrate-reports.ts` imports and calls `legacyFormatDate(record.createdAt)` — this is an active call site in a migration script
- `tests/utils/dates.test.ts` imports it and asserts behavior (`expect(legacyFormatDate(new Date('2024-01-15'))).toBe('1/15/2024')`) — there is a passing test covering this function
- `src/utils/dates.ts` itself has a comment referencing it

The function has at least one production usage in `scripts/migrate-reports.ts` and one test covering its behavior.

**EVALUATE:** The reviewer's premise is factually incorrect. `legacyFormatDate` is not dead code. Removing it would break `scripts/migrate-reports.ts` at runtime and cause a test failure in `tests/utils/dates.test.ts`. The reviewer likely searched only `src/` for call sites and missed the `scripts/` directory, which is a common oversight when scripts live outside the main source tree.

**RESPOND:** Push back with evidence. Here is the reply I would post on the PR:

---

This function is not dead code. The grep shows two active references outside of `src/utils/dates.ts` itself:

1. **`scripts/migrate-reports.ts`** — imports and calls `legacyFormatDate(record.createdAt)` to format dates in the migration script. Removing the function would break this script.
2. **`tests/utils/dates.test.ts`** — has an explicit test asserting the output format: `expect(legacyFormatDate(new Date('2024-01-15'))).toBe('1/15/2024')`.

The `scripts/` directory may not have shown up in your search if you scoped it to `src/` only. The function should stay until the migration script no longer needs it. If we decide to deprecate the M/D/YYYY format in the future, we should remove the call site in `scripts/migrate-reports.ts` first, then the function and its test together.

---

**IMPLEMENT:** No implementation needed — the correct action is to decline the removal and keep the function as-is.
