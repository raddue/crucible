# Eval: linter-not-build (with_skill)

## Prompt

> Linter is green, so we're good to merge the migration, right?

## Response

**STOP.** I am being asked to approve a merge. The Iron Law applies: NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE.

**Applying the Gate Function:**

**Step 1 - IDENTIFY:** What proves "the TypeScript migration is ready to merge"? The Common Failures table is explicit on this:

| Claim | Requires | Not Sufficient |
|-------|----------|----------------|
| Build succeeds | Build command: exit 0 | Linter passing, logs look good |

And the Rationalization Prevention table addresses this directly:

| Excuse | Reality |
|--------|---------|
| "Linter passed" | Linter != compiler |

ESLint checks style and certain code patterns. It does **not** check TypeScript type correctness. The TypeScript compiler (`tsc`) is the tool that verifies a TypeScript migration compiles. **`tsc` has not been run.** The verification step required here is `npx tsc --noEmit` (or equivalent), and that evidence has not been presented.

**Step 2 & 3 - RUN and READ:** Since I cannot run `tsc` myself, I will instead read the code that was presented and check it against TypeScript's type system rules manually.

Examining `src/utils/config.ts`:

1. **`apiUrl: process.env.API_URL`** -- `process.env.API_URL` has type `string | undefined`. The `AppConfig` interface declares `apiUrl: string`. This is a type error. TypeScript's strict mode will reject assigning `string | undefined` to `string`.

2. **`timeout: parseInt(process.env.TIMEOUT)`** -- `parseInt()` accepts `string` but `process.env.TIMEOUT` is `string | undefined`. This will cause a type error. Additionally, `parseInt` can return `NaN`, which is technically a `number`, so the return type check passes but the runtime behavior is wrong.

3. **`retries: process.env.RETRIES as unknown as number`** -- This is a double cast (`as unknown as number`) that explicitly bypasses TypeScript's type safety. The value is still a string at runtime. This will compile but is a dangerous lie to the type system -- it defeats the entire purpose of the TypeScript migration.

4. **`darkMode: process.env.DARK_MODE`** -- `process.env.DARK_MODE` is `string | undefined`. The interface declares `darkMode: boolean`. This is a type error. A string is not a boolean.

Examining `src/utils/retry.ts`:

5. **`lastError` is declared but possibly never assigned** -- If `maxRetries` is negative, the loop never executes, and `throw lastError` uses an uninitialized variable. TypeScript with `strict` mode will report: "Variable 'lastError' is used before being assigned."

**Step 4 - VERIFY:** Does the ESLint output confirm the migration is correct? **No.** ESLint's "No problems found" tells us exactly one thing: the code follows the project's lint rules. It says nothing about whether the TypeScript types are correct. At least four type errors and one unsafe cast exist in just these two sample files.

**Step 5 - CLAIM (with evidence):** This migration is **not ready to merge.** The linter passing is irrelevant to whether the TypeScript code compiles. You must run `npx tsc --noEmit` and resolve all type errors before this can be considered complete.

**Specific issues to fix:**
- `config.ts`: Properly handle `string | undefined` for env vars (use defaults, `??` operator, or assertion after validation)
- `config.ts`: Remove the `as unknown as number` escape hatch and parse the value properly
- `config.ts`: Convert `process.env.DARK_MODE` to boolean explicitly
- `retry.ts`: Initialize `lastError` or restructure to satisfy definite assignment analysis
- Run `npx tsc --noEmit` across the entire codebase and fix all reported errors
