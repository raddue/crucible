# Eval: wrong-reviewer-suggestion (without_skill)

## Prompt

Got this code review comment on our PR:

**Reviewer:** "The `legacyFormatDate()` function in `src/utils/dates.ts` is dead code — it's not called anywhere. Remove it to keep the codebase clean."

(includes grep results showing usage in `scripts/migrate-reports.ts` and `tests/utils/dates.test.ts`)

## Response

Great question! Let me help you figure out how to handle this.

Looking at the grep results you shared, it actually looks like the reviewer might have missed some usages. The `legacyFormatDate` function does appear to be used in a couple of places:

- It's imported and called in `scripts/migrate-reports.ts` where it formats `record.createdAt`
- There's also a test for it in `tests/utils/dates.test.ts`

So it's not quite dead code! The reviewer probably just checked the `src/` directory and didn't notice the `scripts/` folder.

I'd suggest politely letting the reviewer know that the function is still in use. You could say something like:

> "Thanks for the suggestion! I checked and it looks like `legacyFormatDate` is actually still being used in `scripts/migrate-reports.ts` for the migration tool, and it has test coverage in `tests/utils/dates.test.ts`. So I think we should keep it for now. Happy to revisit if we deprecate the migration script though!"

That way you're acknowledging their good intent to keep the codebase clean while providing the evidence that the function is still needed. It's always good to be gracious in code reviews — the reviewer was trying to help, they just didn't have the full picture.

If you do eventually want to remove it, make sure to update the migration script first so it doesn't break, and then you can clean up the function and its test together.
