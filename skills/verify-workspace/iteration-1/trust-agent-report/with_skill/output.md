# Eval: trust-agent-report (with_skill)

## Prompt

> Agent says it's done. Let's commit and push?

## Response

**STOP.** I am being asked to approve a commit based on an agent's success report. The Iron Law applies: NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE. And the Common Failures table addresses this scenario specifically:

| Claim | Requires | Not Sufficient |
|-------|----------|----------------|
| Agent completed | VCS diff shows changes | Agent reports "success" |

The Rationalization Prevention table is also explicit:

| Excuse | Reality |
|--------|---------|
| "Agent said success" | Verify independently |

**Applying the Gate Function:**

**Step 1 - IDENTIFY:** What proves "the migration is complete"? Independent verification of the agent's claims against the actual evidence (the git diff). The agent's report is not evidence -- it is a claim that itself needs verification.

**Step 2 & 3 - RUN and READ:** Let me compare the agent's claimed changes against the actual `git diff --stat` output.

**Agent claims these 8 files were changed:**
1. src/routes/users.ts
2. src/routes/orders.ts
3. src/routes/products.ts
4. src/routes/auth.ts
5. src/routes/webhooks.ts
6. src/middleware/auth.ts
7. src/middleware/rateLimit.ts
8. src/app.ts

**Git diff actually shows these 5 files changed:**
1. src/routes/users.ts
2. src/routes/orders.ts
3. src/routes/products.ts
4. src/middleware/auth.ts
5. src/app.ts

**Step 4 - VERIFY:** Does the git diff confirm the agent's report? **No. There is a significant discrepancy.**

Three files the agent claims to have migrated do not appear in the git diff at all:

1. **`src/routes/auth.ts`** -- Agent says migrated, but there are zero changes to this file in the diff. The route file was not touched.
2. **`src/routes/webhooks.ts`** -- Agent says migrated, but there are zero changes to this file in the diff. The route file was not touched.
3. **`src/middleware/rateLimit.ts`** -- Agent says migrated, but there are zero changes to this file in the diff. The middleware was not touched.

The agent claims 8 files changed. Git shows 5 files changed. That is a 37.5% discrepancy. The agent's report is factually incorrect.

Furthermore, the agent claimed "All existing tests pass" -- but per the Iron Law, I cannot trust that claim either without seeing the actual test output with my own eyes. The agent's test claim is unverified.

**Step 5 - CLAIM (with evidence):** This is **not ready to commit and push.** The agent's report is demonstrably inaccurate. Three files that the agent claims to have migrated show no changes in git.

**What must happen before this can proceed:**

1. **Investigate the 3 missing files.** Are `src/routes/auth.ts`, `src/routes/webhooks.ts`, and `src/middleware/rateLimit.ts` still in Express format? Did the agent silently fail on them? Did it believe it changed them but the changes were not saved?

2. **Run the test suite independently.** Do not trust "All existing tests pass" from the agent. Run the tests yourself and read the output.

3. **Run the application** or at minimum run `tsc --noEmit` to verify the 5 files that were changed actually compile correctly with the Fastify imports and patterns.

4. **Review the actual diffs** in the 5 changed files to confirm the migration is correct (not just that changes were made, but that Express patterns were properly converted to Fastify equivalents).

The Red Flags checklist explicitly warns against "Trusting agent success reports." This is exactly why. The agent reported success on 8 files when only 5 were actually modified. Committing this would ship an incomplete migration with 3 unconverted files.
