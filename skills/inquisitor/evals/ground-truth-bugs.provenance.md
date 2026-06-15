<!-- AUDIT ARTIFACT (#424, S4). The EXACT text fed to the blind ground-truth
authoring subagent: the diff blocks + factual existing-codebase context extracted
from each fixture's `prompt` field, with the skill-naming opener ("Run the
inquisitor against...") neutralized. The evals.json `expected_output` and
`expectations` fields were WITHHELD from the subagent — they live in separate JSON
fields and appear nowhere below. scripts/check_ground_truth_provenance.py asserts
this file contains NONE of those expectation strings, proving the blind boundary
held. Do not edit by hand to match the bug list; this records what was actually fed. -->

# Ground-truth blind-authoring provenance (#424)

This is the verbatim input handed to the blind subagent that authored
`ground-truth-bugs.json`. Expectation prose was never shown to it.


## Fixture 1 — blind input

Feature under review: a new 'Scheduled Notifications' feature. The feature adds scheduled notification support to our Express/PostgreSQL app.

```diff
// NEW FILE: src/services/scheduler.ts
+import { NotificationPayload } from './types';
+
+export class NotificationScheduler {
+  private jobs: Map<string, NodeJS.Timeout> = new Map();
+
+  schedule(id: string, payload: NotificationPayload, delayMs: number): void {
+    const timer = setTimeout(async () => {
+      await this.execute(payload);
+      this.jobs.delete(id);
+    }, delayMs);
+    this.jobs.set(id, timer);
+  }
+
+  cancel(id: string): boolean {
+    const timer = this.jobs.get(id);
+    if (timer) {
+      clearTimeout(timer);
+      this.jobs.delete(id);
+      return true;
+    }
+    return false;
+  }
+
+  private async execute(payload: NotificationPayload): Promise<void> {
+    const { sendNotification } = require('./notifier');
+    await sendNotification(payload);
+  }
+}
```

```diff
// NEW FILE: src/services/notifier.ts
+import { db } from '../db';
+import { NotificationPayload } from './types';
+
+export async function sendNotification(payload: NotificationPayload): Promise<void> {
+  const user = await db.users.findById(payload.userId);
+  if (!user) return; // silently skip
+
+  await fetch(payload.webhookUrl, {
+    method: 'POST',
+    headers: { 'Content-Type': 'application/json' },
+    body: JSON.stringify({ message: payload.message, recipient: user.email }),
+  });
+
+  await db.notifications.create({
+    userId: payload.userId,
+    message: payload.message,
+    sentAt: Date.now(),  // returns number (epoch ms)
+  });
+}
```

```diff
// NEW FILE: src/services/types.ts
+export interface NotificationPayload {
+  userId: string;
+  message: string;
+  webhookUrl: string;
+  scheduledAt: Date;
+}
```

```diff
// MODIFIED: src/routes/notifications.ts
+import { NotificationScheduler } from '../services/scheduler';
+
+const scheduler = new NotificationScheduler();
+
+router.post('/notifications/schedule', async (req, res) => {
+  const { userId, message, webhookUrl, scheduledAt } = req.body;
+  const delay = new Date(scheduledAt).getTime() - Date.now();
+  const id = crypto.randomUUID();
+  scheduler.schedule(id, { userId, message, webhookUrl, scheduledAt }, delay);
+  res.status(201).json({ id, scheduledAt });
+});
+
+router.delete('/notifications/schedule/:id', async (req, res) => {
+  const cancelled = scheduler.cancel(req.params.id);
+  res.json({ cancelled });
+});
```

```diff
// MODIFIED: src/app.ts
 import notificationRoutes from './routes/notifications';
 // ... existing setup ...
 // No new initialization code for NotificationScheduler
```

The existing codebase has:
- `src/db.ts` — Knex-based database module, `notifications` table has `sent_at` column of type `TIMESTAMP`
- `src/services/` — existing notification services
- `src/routes/notifications.ts` — existing CRUD routes for notifications


## Fixture 2 — blind input

Feature under review: adding Role-Based Access Control (RBAC) to our Express API.

```diff
// NEW FILE: src/middleware/rbac.ts
+import { Request, Response, NextFunction } from 'express';
+import { db } from '../db';
+
+export function requireRole(...roles: string[]) {
+  return async (req: Request, res: Response, next: NextFunction) => {
+    const userId = req.user?.id;  // set by auth middleware
+    if (!userId) return res.status(401).json({ error: 'Not authenticated' });
+
+    const userRole = await db.users.findById(userId).select('role');
+    if (!userRole || !roles.includes(userRole.role)) {
+      return res.status(403).json({ error: 'Insufficient permissions' });
+    }
+    req.userRole = userRole.role;
+    next();
+  };
+}
```

```diff
// MODIFIED: src/routes/admin.ts
+import { requireRole } from '../middleware/rbac';
+
-router.get('/admin/users', authMiddleware, async (req, res) => {
+router.get('/admin/users', authMiddleware, requireRole('admin'), async (req, res) => {
   const users = await db.users.findAll();
   res.json(users);
 });

-router.delete('/admin/users/:id', authMiddleware, async (req, res) => {
+router.delete('/admin/users/:id', authMiddleware, requireRole('admin'), async (req, res) => {
   await db.users.deleteById(req.params.id);
   res.json({ deleted: true });
 });
```

```diff
// MODIFIED: src/routes/content.ts
+import { requireRole } from '../middleware/rbac';
+
 router.get('/articles', authMiddleware, async (req, res) => {
   const articles = await db.articles.findAll();
   res.json(articles);
 });

-router.post('/articles', authMiddleware, async (req, res) => {
+router.post('/articles', authMiddleware, requireRole('admin', 'editor'), async (req, res) => {
   const article = await db.articles.create(req.body);
   res.json(article);
 });

-router.put('/articles/:id', authMiddleware, async (req, res) => {
+router.put('/articles/:id', authMiddleware, requireRole('admin', 'editor'), async (req, res) => {
   const article = await db.articles.update(req.params.id, req.body);
   res.json(article);
 });

-router.delete('/articles/:id', authMiddleware, async (req, res) => {
+router.delete('/articles/:id', authMiddleware, requireRole('admin'), async (req, res) => {
   await db.articles.deleteById(req.params.id);
   res.json({ deleted: true });
 });
```

```diff
// MODIFIED: src/db/migrations/20240320_add_roles.sql
+ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'viewer';
```

Existing codebase context:
- Auth middleware at `src/middleware/auth.ts` sets `req.user` from JWT
- `req.user` type is `{ id: string; email: string }` — does NOT include a `role` field
- No `req.userRole` property exists on the Express Request type
- The `users` table currently has no `role` column (that's what the migration adds)
- Existing tests in `tests/routes/admin.test.ts` and `tests/routes/content.test.ts` mock `authMiddleware` to set `req.user`


## Fixture 3 — blind input

Feature under review: adding cursor-based pagination to our API.

```diff
// NEW FILE: src/utils/paginate.ts
+import { Knex } from 'knex';
+
+interface PaginationParams {
+  cursor?: string;
+  limit: number;
+}
+
+interface PaginatedResult<T> {
+  data: T[];
+  nextCursor: string | null;
+}
+
+export function parsePaginationParams(query: Record<string, unknown>): PaginationParams {
+  const limit = Math.min(Math.max(parseInt(String(query.limit)) || 20, 1), 100);
+  const cursor = query.cursor ? String(query.cursor) : undefined;
+  return { cursor, limit };
+}
+
+export async function paginate<T extends { id: number }>(
+  queryBuilder: Knex.QueryBuilder,
+  params: PaginationParams
+): Promise<PaginatedResult<T>> {
+  let query = queryBuilder.orderBy('id', 'asc').limit(params.limit + 1);
+  if (params.cursor) {
+    query = query.where('id', '>', parseInt(params.cursor));
+  }
+  const rows = await query;
+  const hasMore = rows.length > params.limit;
+  const data = hasMore ? rows.slice(0, params.limit) : rows;
+  const nextCursor = hasMore ? String(data[data.length - 1].id) : null;
+  return { data, nextCursor };
+}
```

```diff
// MODIFIED: src/routes/users.ts
+import { parsePaginationParams, paginate } from '../utils/paginate';
+
-router.get('/users', authMiddleware, async (req, res) => {
-  const users = await db.users.findAll();
-  res.json(users);
+router.get('/users', authMiddleware, async (req, res) => {
+  const params = parsePaginationParams(req.query);
+  const result = await paginate(db('users'), params);
+  res.json(result);
 });
```

```diff
// MODIFIED: src/routes/orders.ts
+import { parsePaginationParams, paginate } from '../utils/paginate';
+
-router.get('/orders', authMiddleware, async (req, res) => {
-  const orders = await db.orders.findAll({ userId: req.user.id });
-  res.json(orders);
+router.get('/orders', authMiddleware, async (req, res) => {
+  const params = parsePaginationParams(req.query);
+  const query = db('orders').where('user_id', req.user.id);
+  const result = await paginate(query, params);
+  res.json(result);
 });
```

```diff
// NEW FILE: tests/utils/paginate.test.ts
+import { parsePaginationParams, paginate } from '../../src/utils/paginate';
+// ... tests using in-memory SQLite
```

Existing codebase context:
- Knex with PostgreSQL
- The `orders` table has a UUID `id` column (not integer)
- The `users` table has auto-incrementing integer `id`
- Frontend currently calls GET /users and GET /orders expecting a flat array response
- There are existing integration tests that assert `res.body` is an array
