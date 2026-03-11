# Eval: mixed-feedback (with_skill)

## Prompt

PR review with 5 items on `src/services/notification.ts`. Items include changing findById to findUnique (Prisma convention, but we use Knex), PII leak in error messages, return type annotation, transaction question, and an outstanding clarification question on item 4.

## Response

**READ:** Five feedback items. Item 1 is an API change suggestion. Items 2 and 3 are code quality improvements. Item 4 raises a failure-mode concern about atomicity. Item 5 is my own clarifying question back to the reviewer on item 4 — still unanswered.

**UNDERSTAND:**

- Item 1: Replace `findById` with `findUnique` because it is the "Prisma convention."
- Item 2: The error message `User ${userId} not found` embeds the userId, which could surface as PII in logs.
- Item 3: Add an explicit return type annotation to `notifyUser`.
- Item 4: Concern about partial failure — if `sendEmail` succeeds but `db.notifications.create` fails, we have an inconsistent state.
- Item 5: My clarification question asking whether the transaction should wrap both the email send and the DB write, or only DB operations. Unanswered.

**VERIFY:**

- Item 1: This project uses Knex, not Prisma. `findUnique` is a Prisma Client method. Our `db.users.findById` is a Knex-based query method — it is the correct API for this codebase. The reviewer appears to be applying conventions from a different ORM.
- Item 2: Valid concern. If this error propagates to an error-reporting service or is logged, the userId would be visible. Depending on what userId contains (email, UUID, etc.), this could be a PII exposure. Replacing with a generic message or logging the userId separately at a controlled log level is the right fix.
- Item 3: The function currently has an inferred return type of `Promise<void>`. Adding an explicit `Promise<void>` annotation improves readability and catches accidental return-type drift. Straightforward improvement.
- Items 4 and 5: There is an open question about the scope of the transaction. Email sends are side effects that cannot be rolled back — wrapping them in a DB transaction does not help. But the reviewer might be suggesting something different: perhaps reordering operations, or only wrapping multiple DB writes. I have already asked for clarification and have not received a response.

**EVALUATE:**

- Item 1: Reject. Wrong ORM. `findById` is correct for our Knex-based data layer.
- Item 2: Accept. Legitimate security concern. Fix the error message.
- Item 3: Accept. Low-cost improvement to type safety.
- Items 4+5: Block. Cannot implement without clarification. The implementation differs significantly depending on the answer: wrapping only DB operations in a transaction vs. reordering to write the notification record before sending email vs. adding a compensation/retry mechanism. Implementing the wrong approach would create unnecessary churn.

**RESPOND:**

---

Working through each item:

**Item 1 — `findById` to `findUnique`:** Declining. This project uses Knex, not Prisma. `findUnique` is a Prisma Client method and does not exist in our data access layer. `db.users.findById` is the correct method for our codebase.

**Item 2 — PII in error message:** Fixing. Changing the error to a generic message: `throw new Error('User not found')`. The userId will not appear in the error string. If we need it for debugging, we can log it separately at an appropriate level before throwing.

**Item 3 — Return type annotation:** Adding `Promise<void>` as the explicit return type for `notifyUser`.

**Items 4+5 — Transaction scope:** Not implementing yet. I have an outstanding clarification question (item 5) asking whether the intent is to wrap both the email send and the DB write in a transaction, or only the DB operations. These have very different implementations, and email sends cannot be rolled back regardless. Waiting for the response before proceeding.

---

**IMPLEMENT:** Proceeding with items 2 and 3 now. Item 1 rejected. Items 4/5 on hold pending clarification.

For item 2:
```typescript
if (!user) throw new Error('User not found');
```

For item 3:
```typescript
export async function notifyUser(userId: string, message: string): Promise<void> {
```
