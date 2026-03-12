# Implementation Plan: Role-Based Access Control (RBAC)

## Overview

Add role-based access control to the existing API with three roles (admin, editor, viewer) by extending the current JWT authentication middleware at `src/middleware/auth.ts` and adding a PostgreSQL-backed role model.

## Assumptions

- PostgreSQL database is already provisioned and connected (e.g., via a pool/client in a `src/db` or similar module).
- JWT authentication middleware at `src/middleware/auth.ts` already verifies tokens and attaches a user object (or user ID) to the request.
- The API framework is Express (or Express-compatible such as Koa with adapters). Adjustments are minor if using Fastify or another framework.
- A `users` table already exists in PostgreSQL.

---

## Phase 1: Database Schema Changes

### 1.1 Add `role` column to `users` table

Create a migration that adds a `role` column with a constrained set of allowed values.

**Migration file:** `src/migrations/<timestamp>_add_role_to_users.sql`

```sql
-- Up
ALTER TABLE users
  ADD COLUMN role VARCHAR(16) NOT NULL DEFAULT 'viewer'
  CONSTRAINT valid_role CHECK (role IN ('admin', 'editor', 'viewer'));

-- Down
ALTER TABLE users DROP COLUMN role;
```

Key decisions:
- Default role is `viewer` (principle of least privilege).
- The constraint is enforced at the database level, not just application level.
- Using a `CHECK` constraint on a varchar column rather than a separate `roles` table. A separate table is warranted only if roles become dynamic or need metadata; for three fixed roles, a constrained column is simpler and faster.

### 1.2 Seed an initial admin user

Provide a seed script or migration that promotes an existing user to `admin` so the system is not locked out.

```sql
UPDATE users SET role = 'admin' WHERE email = '<bootstrap-admin-email>';
```

---

## Phase 2: Role Definition and Permission Mapping

### 2.1 Create role constants and permission map

**New file:** `src/auth/roles.ts`

Define the three roles as a TypeScript enum (or const object) and map each role to its allowed HTTP methods.

```ts
export const Role = {
  ADMIN: 'admin',
  EDITOR: 'editor',
  VIEWER: 'viewer',
} as const;

export type RoleName = (typeof Role)[keyof typeof Role];

// Maps each role to the HTTP methods it may use.
const ROLE_PERMISSIONS: Record<RoleName, Set<string>> = {
  admin:  new Set(['GET', 'POST', 'PUT', 'PATCH', 'DELETE']),
  editor: new Set(['GET', 'POST', 'PUT', 'PATCH']),
  viewer: new Set(['GET']),
};

export function roleCanPerform(role: RoleName, method: string): boolean {
  return ROLE_PERMISSIONS[role]?.has(method.toUpperCase()) ?? false;
}
```

This mapping encodes the requirement:
| Role   | GET | POST | PUT/PATCH | DELETE |
|--------|-----|------|-----------|--------|
| admin  | Y   | Y    | Y         | Y      |
| editor | Y   | Y    | Y         | N      |
| viewer | Y   | N    | N         | N      |

### 2.2 (Optional) Fine-grained resource permissions

If certain routes need exceptions to the method-based rules (e.g., editors can delete their own drafts), add a resource-level permission layer later. For the initial implementation the HTTP-method mapping above covers the stated requirements.

---

## Phase 3: Extend JWT Payload and Auth Middleware

### 3.1 Include `role` in JWT payload

When a user logs in (or a token is issued), include the role claim:

```ts
const token = jwt.sign(
  { sub: user.id, role: user.role },
  SECRET,
  { expiresIn: '8h' }
);
```

**File to modify:** wherever token signing happens (e.g., `src/auth/login.ts` or `src/controllers/auth.ts`).

### 3.2 Extend the request type

**File to modify:** `src/types/express.d.ts` (or equivalent)

Augment the Express `Request` to carry role information:

```ts
declare namespace Express {
  interface Request {
    user?: {
      id: string;
      role: 'admin' | 'editor' | 'viewer';
    };
  }
}
```

### 3.3 Update existing auth middleware to extract role

**File to modify:** `src/middleware/auth.ts`

After verifying the JWT and attaching `req.user`, ensure the decoded `role` claim is also set on `req.user.role`. No new middleware file is needed for this step; the existing middleware just needs to pass through the additional claim.

---

## Phase 4: Authorization Middleware

### 4.1 Create `authorize` middleware

**New file:** `src/middleware/authorize.ts`

This middleware runs *after* the existing `auth` middleware (which handles authentication) and enforces authorization.

```ts
import { Request, Response, NextFunction } from 'express';
import { RoleName, roleCanPerform } from '../auth/roles';

/**
 * Factory that returns middleware restricting access to the given roles.
 * If no roles are specified, falls back to method-based permission check.
 */
export function authorize(...allowedRoles: RoleName[]) {
  return (req: Request, res: Response, next: NextFunction) => {
    const userRole = req.user?.role;

    if (!userRole) {
      return res.status(401).json({ error: 'Not authenticated' });
    }

    // If specific roles were listed, check membership.
    if (allowedRoles.length > 0 && !allowedRoles.includes(userRole)) {
      return res.status(403).json({ error: 'Insufficient permissions' });
    }

    // Method-based check (covers the general create/edit/delete rules).
    if (!roleCanPerform(userRole, req.method)) {
      return res.status(403).json({ error: 'Insufficient permissions' });
    }

    next();
  };
}
```

### 4.2 Apply middleware to routes

There are two strategies; choose one based on the API's route structure.

**Strategy A -- Global (recommended for uniform APIs):**

Mount `authorize()` (with no role arguments) globally after `auth`. Every route then gets method-based protection automatically.

```ts
app.use(auth);        // existing JWT verification
app.use(authorize()); // new: method-based RBAC
```

**Strategy B -- Per-route (for mixed-access APIs):**

Apply `authorize` selectively:

```ts
router.get('/articles',       auth, authorize(),                  listArticles);
router.post('/articles',      auth, authorize('admin', 'editor'), createArticle);
router.delete('/articles/:id', auth, authorize('admin'),          deleteArticle);
```

### 4.3 Admin-only routes

Certain routes (user management, role assignment) should be restricted to admins:

```ts
router.put('/users/:id/role', auth, authorize('admin'), updateUserRole);
```

---

## Phase 5: Admin Endpoint for Role Management

### 5.1 Create role-update endpoint

**New file:** `src/controllers/userRole.ts` (or add to existing user controller)

```ts
// PATCH /users/:id/role
// Body: { "role": "editor" }
// Restricted to admin only.
```

Validation:
- Confirm the target user exists.
- Confirm the new role is one of the three valid values.
- Prevent the last admin from demoting themselves (optional safeguard).

### 5.2 Add route

Wire the controller into the router with `authorize('admin')`.

---

## Phase 6: Testing

### 6.1 Unit tests

**New file:** `tests/auth/roles.test.ts`

- `roleCanPerform('viewer', 'GET')` returns `true`.
- `roleCanPerform('viewer', 'POST')` returns `false`.
- `roleCanPerform('editor', 'DELETE')` returns `false`.
- `roleCanPerform('admin', 'DELETE')` returns `true`.
- Unknown role returns `false`.

### 6.2 Middleware integration tests

**New file:** `tests/middleware/authorize.test.ts`

- Request with no token returns 401.
- Viewer making a GET request returns 200.
- Viewer making a POST request returns 403.
- Editor making a POST request returns 200.
- Editor making a DELETE request returns 403.
- Admin making a DELETE request returns 200.
- Explicit role-list check: non-admin hitting an `authorize('admin')` route returns 403.

### 6.3 End-to-end / API tests

- Create three test users (one per role).
- Run the full request lifecycle (login, get token, hit protected endpoint) for each role against representative routes.
- Verify that role changes via the admin endpoint take effect on next request.

---

## Phase 7: Token Refresh and Role Sync

### 7.1 Handle role changes mid-session

When an admin changes a user's role, existing JWTs still carry the old role. Two mitigation options:

**Option A -- Short-lived tokens (recommended):** Set JWT expiry to a short window (e.g., 15 minutes) with a refresh-token flow. Role is re-read from the database at refresh time.

**Option B -- Database check on sensitive operations:** For DELETE and role-management routes, re-query the database for the user's current role instead of trusting the JWT claim alone. This adds one query per sensitive request but guarantees real-time accuracy.

---

## File Change Summary

| File | Action | Description |
|------|--------|-------------|
| `src/migrations/<ts>_add_role_to_users.sql` | Create | Add `role` column to `users` table |
| `src/auth/roles.ts` | Create | Role constants and permission-check function |
| `src/middleware/auth.ts` | Modify | Pass `role` from decoded JWT onto `req.user` |
| `src/middleware/authorize.ts` | Create | Authorization middleware (role + method check) |
| `src/types/express.d.ts` | Modify | Augment `Request` type with `role` field |
| Token-signing code (e.g., `src/auth/login.ts`) | Modify | Include `role` in JWT payload |
| `src/controllers/userRole.ts` | Create | Admin endpoint to change a user's role |
| Route definitions | Modify | Apply `authorize` middleware to routes |
| `tests/auth/roles.test.ts` | Create | Unit tests for permission map |
| `tests/middleware/authorize.test.ts` | Create | Integration tests for authorization middleware |

## Implementation Order

1. **Database migration** -- add the `role` column, seed the admin.
2. **`src/auth/roles.ts`** -- define roles and permission logic (can be unit-tested immediately).
3. **Modify `src/middleware/auth.ts`** -- extract and attach `role` from JWT.
4. **Create `src/middleware/authorize.ts`** -- the core authorization middleware.
5. **Update token signing** -- include `role` in JWT payload.
6. **Wire middleware into routes** -- global or per-route.
7. **Build admin role-management endpoint**.
8. **Write and run tests** (unit, integration, e2e).
9. **Evaluate token-refresh strategy** and implement if needed.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Existing users have no role after migration | Users locked out or over-privileged | Default to `viewer` in migration; seed at least one admin |
| Stale JWT carries old role after admin changes it | User retains revoked permissions | Short-lived tokens + refresh flow, or DB re-check on sensitive ops |
| New middleware breaks existing routes | API downtime | Deploy behind a feature flag; run full test suite before enabling |
| Editor needs to delete specific owned resources later | Feature gap | Plan for resource-level ownership checks as a follow-up phase |
