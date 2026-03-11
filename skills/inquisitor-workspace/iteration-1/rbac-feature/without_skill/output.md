Here is my review of the RBAC feature diff.

**TypeScript type issue with `req.userRole`**

The `requireRole` middleware sets `req.userRole = userRole.role`, but looking at the existing codebase context, the Express `Request` type only includes `{ id: string; email: string }` for `req.user`. There is no `userRole` property defined on the Request type. This will cause TypeScript compilation errors in strict mode. You need to augment the Express Request type to include `userRole?: string`, typically done in a declaration file or at the top of the middleware module.

**Existing tests will break**

The existing tests in `tests/routes/admin.test.ts` and `tests/routes/content.test.ts` mock `authMiddleware` to set `req.user`, but they do not account for the new `requireRole` middleware. Since `requireRole` makes its own database query (`db.users.findById(userId).select('role')`), any test that only mocks the auth middleware will now fail when the RBAC middleware tries to hit the database. These tests need to be updated to either mock the database call or seed a test user with an appropriate role.

**N+1 query problem**

Every request to a role-protected endpoint now makes an additional database round-trip. The auth middleware already validates the user (presumably by looking them up or verifying a JWT), and then `requireRole` queries the database again just to get the role. On high-traffic routes, this doubles the per-request query count. A better approach would be to include the role in the JWT token, or fetch it once during authentication and attach it to `req.user`.

**Potential issue with `findById().select('role')` return value**

The code does `const userRole = await db.users.findById(userId).select('role')` and then accesses `userRole.role`. The exact shape of this return value depends on how `findById` is implemented. If it is a Knex chain, `.select('role')` on a single row typically returns an object like `{ role: 'admin' }`. But if `findById` is a custom method that returns a model instance, chaining `.select()` might not work as expected. This should be tested to ensure `userRole.role` actually contains the expected string.

**Missing role check on GET /articles**

Looking at the permission model, POST, PUT, and DELETE on `/articles` all have role requirements, but GET `/articles` only requires authentication. If this is intentional (all authenticated users can read articles), that is fine. But it is worth explicitly documenting, because it creates an asymmetry where a `viewer` role can read articles but not create them, and there is no route-level indication that this was a deliberate choice vs. an oversight.

**Role strings are hardcoded magic values**

The roles `'admin'`, `'editor'`, and `'viewer'` appear as string literals scattered across multiple files. There is no shared constant or enum. A typo in any route definition (e.g., `'Admin'` instead of `'admin'`) would silently lock out all users from that route. Define a shared roles constant and use it everywhere.

**Migration consideration**

The migration adds `role VARCHAR(20) DEFAULT 'viewer'`. In PostgreSQL 11+, adding a column with a DEFAULT value does backfill existing rows, so this should be fine. However, if you need to support older PostgreSQL versions, you would need a separate UPDATE statement. Worth verifying your target PostgreSQL version.

**Admin self-deletion**

The DELETE `/admin/users/:id` route allows an admin to delete any user, including themselves. After self-deletion, the admin's JWT remains valid, but subsequent requests will fail at the RBAC middleware because the user no longer exists in the database. Consider adding a guard that prevents admins from deleting their own account.

The overall structure of the RBAC middleware is clean and the approach is reasonable. The most urgent items to address are the test breakage (which will block CI immediately), the TypeScript type issue, and the N+1 query performance concern.
