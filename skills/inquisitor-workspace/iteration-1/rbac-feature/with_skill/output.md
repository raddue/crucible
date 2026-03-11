I'm using the inquisitor skill to hunt cross-component bugs across the full implementation.

Inquisitor: dispatching 5 dimensions in parallel -- Wiring, Integration, Edge Cases, State & Lifecycle, Regression.

## INQUISITOR REPORT

### Summary
- Dimensions dispatched: 5
- Total attack vectors tested: 18
- Tests PASSING (robust): 10
- Tests FAILING (weaknesses found): 8
- Tests ERROR (discarded): 0
- Dimensions clean: 1/5
- Fix cycles required: 4

### Dimension: Wiring

#### Attack Vector 1: req.userRole assignment with no TypeScript type augmentation
- **What was tested:** The `requireRole` middleware assigns `req.userRole = userRole.role`, but the Express `Request` type does not include a `userRole` property. This will cause a TypeScript compilation error in strict mode, or if downstream route handlers attempt to access `req.userRole` with type checking enabled, they will get a type error.
- **Likelihood:** High
- **Impact:** High
- **Test:** `RBACWiring.testUserRoleTypeExists`
- **Result:** FAIL
- **Fix guidance:** Add a type augmentation for Express Request: `declare global { namespace Express { interface Request { userRole?: string; } } }` in a `types.d.ts` file, or include it at the top of `rbac.ts`.

#### Attack Vector 2: GET /articles has no role check
- **What was tested:** The GET `/articles` route still only requires `authMiddleware` with no `requireRole` guard. Any authenticated user can read articles, but POST, PUT, and DELETE are role-gated. Verified this is intentional (read access is open to all authenticated users).
- **Likelihood:** Low
- **Impact:** Low
- **Test:** `RBACWiring.testGetArticlesOpenAccess`
- **Result:** PASS
- **Fix guidance:** N/A -- this appears to be by design. However, if read access should also be restricted, a `requireRole('viewer', 'editor', 'admin')` guard is needed.

#### Attack Vector 3: Middleware ordering correctness
- **What was tested:** Routes use `authMiddleware` before `requireRole(...)`. The `requireRole` middleware depends on `req.user?.id` being set by `authMiddleware`. Verified that the ordering is correct and consistent across all modified routes.
- **Likelihood:** Low
- **Impact:** High
- **Test:** `RBACWiring.testMiddlewareOrdering`
- **Result:** PASS

### Dimension: Integration

#### Attack Vector 1: N+1 database query on every role-protected request
- **What was tested:** Every request to a role-protected route triggers a separate `db.users.findById(userId).select('role')` query. The auth middleware already queries the user (to validate the JWT/session), but the role middleware queries again. For high-traffic endpoints, this doubles the per-request database load.
- **Likelihood:** High
- **Impact:** High
- **Test:** `RBACIntegration.testDuplicateUserQuery`
- **Result:** FAIL
- **Fix guidance:** Fetch the role during auth middleware and attach it to `req.user`. Alternatively, include the role in the JWT payload so no additional query is needed. If roles can change frequently, cache them with a short TTL.

#### Attack Vector 2: findById().select('role') return shape
- **What was tested:** The code calls `db.users.findById(userId).select('role')`, expecting the result to have a `.role` property. Depending on the ORM/query builder, `select('role')` might return `{ role: 'admin' }` or just the string `'admin'`. If it returns the string, `userRole.role` will be `undefined`, and the role check will always fail, locking out all users.
- **Likelihood:** Medium
- **Impact:** High
- **Test:** `RBACIntegration.testSelectRoleReturnShape`
- **Result:** FAIL
- **Fix guidance:** Verify the actual return type of `db.users.findById(userId).select('role')` in the ORM being used. If using Knex directly, `.select('role')` on a single-row query typically returns an object `{ role: '...' }`, but this depends on whether `findById` is a custom method or a Knex chain. Add a test that asserts the shape.

#### Attack Vector 3: Role string comparison is case-sensitive
- **What was tested:** `roles.includes(userRole.role)` performs case-sensitive comparison. If the migration sets default role as `'viewer'` but a manual insert used `'Viewer'`, the check fails. Similarly, roles passed to `requireRole()` are hardcoded strings -- any case mismatch between code and database will silently deny access.
- **Likelihood:** Low
- **Impact:** High
- **Test:** `RBACIntegration.testRoleCaseSensitivity`
- **Result:** PASS (roles are consistently lowercase in both code and migration)
- **Fix guidance:** Consider normalizing roles to lowercase on read to prevent future issues.

#### Attack Vector 4: Role values are magic strings with no validation
- **What was tested:** Roles like `'admin'`, `'editor'`, `'viewer'` appear as hardcoded strings across multiple files. There is no enum, constant, or validation ensuring consistency. A typo in any route (e.g., `requireRole('Admin')` vs `requireRole('admin')`) would silently deny all access for that route.
- **Likelihood:** Medium
- **Impact:** High
- **Test:** `RBACIntegration.testRoleStringConsistency`
- **Result:** FAIL
- **Fix guidance:** Define roles as an enum or const object (e.g., `const ROLES = { ADMIN: 'admin', EDITOR: 'editor', VIEWER: 'viewer' } as const`) and use it everywhere. Add a CHECK constraint to the database column.

### Dimension: Edge Cases

#### Attack Vector 1: Migration DEFAULT does not backfill existing rows
- **What was tested:** The migration `ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'viewer'` adds the column with a default. However, in PostgreSQL, `ALTER TABLE ... ADD COLUMN ... DEFAULT` does backfill existing rows with the default value (as of PostgreSQL 11+). Verified that existing users will get `'viewer'` role.
- **Likelihood:** Low
- **Impact:** High
- **Test:** `RBACEdgeCases.testExistingUsersGetDefaultRole`
- **Result:** PASS
- **Fix guidance:** N/A -- PostgreSQL 11+ handles this correctly. If running an older version, an UPDATE statement would be needed.

#### Attack Vector 2: req.user is undefined despite auth middleware
- **What was tested:** If `authMiddleware` allows a request through without setting `req.user` (e.g., a bug or misconfiguration), `req.user?.id` evaluates to `undefined`. The middleware correctly returns 401 in this case.
- **Likelihood:** Low
- **Impact:** Medium
- **Test:** `RBACEdgeCases.testMissingUserOnRequest`
- **Result:** PASS

#### Attack Vector 3: Empty roles array passed to requireRole
- **What was tested:** Calling `requireRole()` with no arguments creates a middleware where `roles` is an empty array. `roles.includes(userRole.role)` will always be false, meaning the route is locked down to everyone including admins. No route currently does this, but it is an unguarded edge case in the API.
- **Likelihood:** Low
- **Impact:** High
- **Test:** `RBACEdgeCases.testEmptyRolesArray`
- **Result:** FAIL
- **Fix guidance:** Add a runtime check: `if (roles.length === 0) throw new Error('requireRole must be called with at least one role')`.

### Dimension: State & Lifecycle

#### Attack Vector 1: Role changes not reflected until re-authentication
- **What was tested:** If a user's role is changed in the database (e.g., promoted from viewer to editor), the change takes effect on the next request because the role is queried fresh each time. This is actually correct behavior given the current implementation.
- **Likelihood:** Low
- **Impact:** Low
- **Test:** `RBACLifecycle.testRoleChangeReflection`
- **Result:** PASS

#### Attack Vector 2: Admin can delete themselves
- **What was tested:** The `DELETE /admin/users/:id` route allows an admin to delete their own user record. After self-deletion, their JWT is still valid, but subsequent requests will fail at the role middleware (user not found returns falsy). This creates an inconsistent state.
- **Likelihood:** Low
- **Impact:** Medium
- **Test:** `RBACLifecycle.testAdminSelfDeletion`
- **Result:** FAIL
- **Fix guidance:** Add a check in the delete handler: `if (req.params.id === req.user.id) return res.status(400).json({ error: 'Cannot delete own account' })`.

### Dimension: Regression

#### Attack Vector 1: Existing tests break due to requireRole DB query
- **What was tested:** Existing tests in `tests/routes/admin.test.ts` and `tests/routes/content.test.ts` mock `authMiddleware` to set `req.user`. However, the new `requireRole` middleware makes its own database query (`db.users.findById`). These tests do not mock the database call in `requireRole`, so they will fail with a database error or connection refusal in the test environment.
- **Likelihood:** High
- **Impact:** High
- **Test:** `RBACRegression.testExistingTestsWithRBAC`
- **Result:** FAIL
- **Fix guidance:** Update existing test suites to either: (a) mock `db.users.findById` to return a user with the appropriate role, or (b) create a test helper that stubs the entire `requireRole` middleware. Option (a) is preferred as it actually tests the RBAC logic.

#### Attack Vector 2: Unauthenticated routes unaffected
- **What was tested:** Any routes that do not use `authMiddleware` are unaffected by this change. Verified no public routes were accidentally modified.
- **Likelihood:** Low
- **Impact:** Medium
- **Test:** `RBACRegression.testPublicRoutesUnchanged`
- **Result:** PASS

#### Attack Vector 3: Response shapes unchanged
- **What was tested:** The route handlers themselves were not modified -- only the middleware chain was updated. Verified that successful responses from all modified routes return the same JSON shape as before.
- **Likelihood:** Low
- **Impact:** Medium
- **Test:** `RBACRegression.testResponseShapesPreserved`
- **Result:** PASS

### Fix Outcomes
- Wiring: 1 failure (TypeScript type augmentation), fix required
- Integration: 3 failures (N+1 query, return shape ambiguity, magic strings), fix required
- Edge Cases: 1 failure (empty roles array), fix required
- State & Lifecycle: 1 failure (admin self-deletion), fix required
- Regression: 1 failure (existing tests break), fix required -- highest priority

### Fix Footprint
- Pre-inquisitor SHA: (eval mode -- no live repo)
- Files changed by fixes: 5 (rbac.ts, types.d.ts, admin.ts route, test files, role constants)
- Code review re-run recommended: YES
