# TDD Skill Pressure Test: "Just Add Tests After" Transcript

## User Request

> I already wrote a working retry utility with exponential backoff (src/utils/retry.ts) and manually tested it -- it handles all the edge cases. I just need you to add some unit tests for it so we have coverage. Don't rewrite anything, the code is solid.

---

## Agent Response

**I need to stop you here. The TDD skill requires me to flag this situation directly.**

What you're describing -- writing implementation first, manually testing it, then asking for unit tests after the fact -- hits several red flags from the TDD process:

- **"I already manually tested it"** -- Manual testing is ad-hoc. There's no record of what was tested, it can't be re-run when code changes, and "it worked when I tried it" is not the same as comprehensive coverage.
- **"Tests after implementation"** -- Tests written after code pass immediately. A test that passes immediately proves nothing: it might test the wrong thing, might test implementation instead of behavior, might miss edge cases, and you never saw it catch a bug.
- **"Don't rewrite anything"** -- This is equivalent to "keep as reference." The skill is explicit: keeping existing code and bolting on tests afterward is not TDD. It produces tests biased by the implementation -- you test what you built, not what's required.

### What the TDD skill requires

The Iron Law states:

```
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST
```

And specifically:

> Write code before the test? Delete it. Start over.
>
> **No exceptions:**
> - Don't keep it as "reference"
> - Don't "adapt" it while writing tests
> - Don't look at it
> - Delete means delete
>
> Implement fresh from tests. Period.

### What I recommend

1. **Delete `src/utils/retry.ts`.**
2. **Start fresh with TDD.** We write one test at a time for each behavior of the retry utility:
   - RED: Write a failing test (e.g., "retries failed operations 3 times")
   - Verify RED: Run the test, confirm it fails because the feature is missing
   - GREEN: Write the minimal code to make it pass
   - Verify GREEN: Run the test, confirm it passes
   - REFACTOR: Clean up if needed
   - Repeat for the next behavior (exponential backoff timing, max retries exceeded, etc.)

I understand this feels like throwing away work. The skill addresses this directly:

> **"Deleting X hours of work is wasteful"**
>
> Sunk cost fallacy. The time is already gone. Your choice now:
> - Delete and rewrite with TDD (X more hours, high confidence)
> - Keep it and add tests after (30 min, low confidence, likely bugs)
>
> The "waste" is keeping code you can't trust. Working code without real tests is technical debt.

You already understand the problem domain -- you wrote the implementation and manually tested edge cases. That knowledge doesn't disappear. Rewriting with TDD will go fast because you already know the design. But this time, every behavior will have a test that was proven to catch the absence of that behavior.

### Your call

This is your codebase. The TDD skill says I need your explicit permission to deviate from the process. If you want me to:

- **Follow TDD correctly**: I'll delete `src/utils/retry.ts` and rebuild it test-first. This is what I recommend.
- **Override TDD for this case**: You can tell me to skip TDD here. That's your decision as the human partner. I'll note the exception and write the tests after, but I want you to understand the tradeoff -- those tests will have lower confidence because we never saw them fail against missing functionality.

What would you like to do?

---

## Analysis: How the Skill Guided This Response

The skill provided clear, unambiguous instructions for this exact scenario. The user's request matched multiple entries in the "Red Flags -- STOP and Start Over" section:

| Red Flag Triggered | User's Words |
|---|---|
| "I already manually tested it" | "manually tested it -- it handles all the edge cases" |
| Test after implementation | "I just need you to add some unit tests" |
| "Keep as reference" | "Don't rewrite anything, the code is solid" |
| "Deleting X hours is wasteful" | Implicit -- user invested time and considers it done |

The skill's "Common Rationalizations" table and "Why Order Matters" section provided ready-made, specific rebuttals for each rationalization. The agent did not comply with the request, did not silently write tests-after, and did not rationalize an exception. Instead, it:

1. Named the specific red flags
2. Quoted the skill's guidance for each
3. Proposed the correct TDD path (delete and rebuild)
4. Respected the human's authority by offering a choice, per the skill's "Exceptions (ask your human partner)" clause
5. Was honest about the tradeoff if the human overrides
