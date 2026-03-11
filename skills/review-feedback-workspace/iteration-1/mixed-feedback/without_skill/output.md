# Eval: mixed-feedback (without_skill)

## Prompt

PR review with 5 items on `src/services/notification.ts`. Items include changing findById to findUnique (Prisma convention, but we use Knex), PII leak in error messages, return type annotation, transaction question, and an outstanding clarification question on item 4.

## Response

Great set of review feedback! Let me help you work through each item:

**Item 1 — Change `findById` to `findUnique`:**
Thanks for the suggestion! However, I should note that our project uses Knex, not Prisma. `findUnique` is a Prisma-specific method, so it wouldn't work with our data access layer. Our `findById` method is the appropriate way to query by ID in our Knex-based setup, so I think we should keep it as-is. You might want to gently let the reviewer know about the ORM difference.

**Item 2 — PII leak in error messages:**
Great catch! This is a valid concern. Including the `userId` directly in the error message means it could show up in logs, error tracking tools, or even be exposed to end users if error messages aren't properly sanitized. I'd recommend changing it to something generic:

```typescript
if (!user) throw new Error('User not found');
```

If you need the userId for debugging purposes, you could log it separately before throwing:

```typescript
if (!user) {
  console.error(`Failed to find user for notification`, { userId });
  throw new Error('User not found');
}
```

**Item 3 — Return type annotation:**
Good suggestion! Adding an explicit return type is a nice improvement for code readability and maintainability:

```typescript
export async function notifyUser(userId: string, message: string): Promise<void> {
```

This makes it immediately clear what the function returns and helps catch unintended return value changes.

**Item 4 — Transaction for email + db write:**
This is an interesting point! The reviewer raises a valid concern about what happens if `sendEmail` succeeds but `db.notifications.create` fails — you'd have sent an email but have no record of it.

**Item 5 — Your clarification question:**
Your clarification question is really smart! You're right that email sends can't be rolled back, so wrapping everything in a database transaction doesn't fully solve the problem. Since you're waiting for the reviewer to respond to your question, I'd hold off on implementing anything for item 4 until you get clarity.

Some possible approaches once you get clarification:
- Reverse the order: write the notification record first, then send the email (if the email fails, you can delete the record or mark it as unsent)
- Use a try/catch around the db write and add compensating logic
- Accept eventual consistency for this use case

**Summary:**
I'd go ahead and implement items 2 and 3 now since they're straightforward improvements. Item 1 can be declined with the Knex explanation. And items 4/5 should wait until you hear back from the reviewer. Nice work asking for clarification before jumping into implementation!
