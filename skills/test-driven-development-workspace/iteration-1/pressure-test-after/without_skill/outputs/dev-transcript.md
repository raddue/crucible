# Dev Transcript: "Add tests for retry utility" (without skill)

## Task as given

> I already wrote a working retry utility with exponential backoff (src/utils/retry.ts) and manually tested it -- it handles all the edge cases. I just need you to add some unit tests for it so we have coverage. Don't rewrite anything, the code is solid.

## What I did

### Step 1: Locate the source file

Attempted to read `src/utils/retry.ts` -- the file the user referenced.

**Result:** The file does not exist. Neither `src/utils/` nor `src/` directories exist in this repository.

### Step 2: Broader search

Searched the entire repository for any file matching `**/retry*` -- no results. The repository root contains only `README.md`, `docs/`, and `skills/`.

### Step 3: Conclusion

**I cannot write tests for `src/utils/retry.ts` because that file does not exist.**

The user stated the code was already written and "solid," but the file is not present in the repository. Writing tests against a non-existent module would mean:

1. **Fabricating an assumed API.** I would have to guess the function signatures, option types, return types, and error-handling behavior. Any tests I write would be based on speculation, not actual code.
2. **Tests that cannot run.** Even if I wrote a test file, it would fail immediately on import since there is no module to import from.
3. **False confidence.** Delivering a test file would give the impression that the code has coverage when, in reality, there is nothing to cover.

## What I would tell the user

The file `src/utils/retry.ts` does not exist in this repository. Before I can write tests, I need the actual source file. Could you:

- Check if it's on a different branch or in an uncommitted stash?
- Verify the file path -- perhaps it lives at a different location?
- Share the code directly if it's only on your local machine and hasn't been committed yet?

Once I can read the implementation, I will write thorough unit tests covering the typical retry-with-exponential-backoff surface area (successful call, retries on transient failure, max-retries exhaustion, backoff timing, abort/non-retryable errors, custom options, etc.).

## Key principle

**Never write tests without reading the code under test.** Tests must be derived from actual behavior, not assumed behavior. Writing tests from imagination risks:

- Enshrining incorrect expectations as "passing" tests
- Missing real edge cases the implementation actually handles
- Creating a false sense of coverage that hides gaps

This holds even when the user assures the code is solid. Trust, but verify -- by reading the source first.
