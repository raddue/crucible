# Role-Based Access Control (RBAC) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use crucible:build to implement this plan task-by-task.

**Goal:** Add role-based access control (admin, editor, viewer) to the existing API so that endpoints enforce permission checks based on the authenticated user's role.

**Architecture:** Extend the existing JWT auth middleware at `src/middleware/auth.ts` with a role-authorization layer. Each user row in PostgreSQL gains a `role` column (enum: `admin`, `editor`, `viewer`). A new `authorize` middleware factory checks the decoded JWT's role against the required permission for each route. Permissions follow a simple hierarchy: admin > editor > viewer, where higher roles inherit all lower-role permissions.

**Tech Stack:** TypeScript, Express, PostgreSQL, JWT (jsonwebtoken), Jest, supertest

---

### Task 1: Add the `role` Column to the Users Table

**Files:**
- Create: `src/db/migrations/XXXXXX_add_role_to_users.ts`
- Test: `tests/db/migrations/add_role_to_users.test.ts`

**Step 1: Write the failing test**

```typescript
// tests/db/migrations/add_role_to_users.test.ts
import { Pool } from "pg";
import { up, down } from "../../src/db/migrations/XXXXXX_add_role_to_users";

describe("add_role_to_users migration", () => {
  let pool: Pool;

  beforeAll(() => {
    pool = new Pool({ connectionString: process.env.TEST_DATABASE_URL });
  });

  afterAll(async () => {
    await pool.end();
  });

  it("adds a role column with default 'viewer'", async () => {
    await up(pool);

    const result = await pool.query(`
      SELECT column_name, column_default, data_type
      FROM information_schema.columns
      WHERE table_name = 'users' AND column_name = 'role'
    `);

    expect(result.rows).toHaveLength(1);
    expect(result.rows[0].column_default).toContain("viewer");
  });

  it("rolls back cleanly", async () => {
    await up(pool);
    await down(pool);

    const result = await pool.query(`
      SELECT column_name
      FROM information_schema.columns
      WHERE table_name = 'users' AND column_name = 'role'
    `);

    expect(result.rows).toHaveLength(0);
  });
});
```

**Step 2: Run test to verify it fails**

Run: `npx jest tests/db/migrations/add_role_to_users.test.ts --verbose`
Expected: FAIL with "Cannot find module" because the migration file does not exist yet.

**Step 3: Write minimal implementation**

```typescript
// src/db/migrations/XXXXXX_add_role_to_users.ts
import { Pool } from "pg";

export async function up(pool: Pool): Promise<void> {
  await pool.query(`
    DO $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role') THEN
        CREATE TYPE user_role AS ENUM ('admin', 'editor', 'viewer');
      END IF;
    END $$;
  `);

  await pool.query(`
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS role user_role NOT NULL DEFAULT 'viewer'
  `);
}

export async function down(pool: Pool): Promise<void> {
  await pool.query(`ALTER TABLE users DROP COLUMN IF EXISTS role`);
  await pool.query(`DROP TYPE IF EXISTS user_role`);
}
```

**Step 4: Run test to verify it passes**

Run: `npx jest tests/db/migrations/add_role_to_users.test.ts --verbose`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add src/db/migrations/XXXXXX_add_role_to_users.ts tests/db/migrations/add_role_to_users.test.ts
git commit -m "feat: add role column migration to users table"
```

---

### Task 2: Define the Role Types and Permission Map

**Files:**
- Create: `src/auth/roles.ts`
- Test: `tests/auth/roles.test.ts`

**Step 1: Write the failing test**

```typescript
// tests/auth/roles.test.ts
import { Role, ROLE_HIERARCHY, canPerform, Action } from "../../src/auth/roles";

describe("Role definitions", () => {
  describe("ROLE_HIERARCHY", () => {
    it("ranks admin highest", () => {
      expect(ROLE_HIERARCHY.admin).toBeGreaterThan(ROLE_HIERARCHY.editor);
      expect(ROLE_HIERARCHY.admin).toBeGreaterThan(ROLE_HIERARCHY.viewer);
    });

    it("ranks editor above viewer", () => {
      expect(ROLE_HIERARCHY.editor).toBeGreaterThan(ROLE_HIERARCHY.viewer);
    });
  });

  describe("canPerform", () => {
    it("allows admin to delete", () => {
      expect(canPerform("admin", "delete")).toBe(true);
    });

    it("allows admin to create", () => {
      expect(canPerform("admin", "create")).toBe(true);
    });

    it("allows admin to read", () => {
      expect(canPerform("admin", "read")).toBe(true);
    });

    it("allows editor to create", () => {
      expect(canPerform("editor", "create")).toBe(true);
    });

    it("allows editor to update", () => {
      expect(canPerform("editor", "update")).toBe(true);
    });

    it("denies editor delete", () => {
      expect(canPerform("editor", "delete")).toBe(false);
    });

    it("allows viewer to read", () => {
      expect(canPerform("viewer", "read")).toBe(true);
    });

    it("denies viewer create", () => {
      expect(canPerform("viewer", "create")).toBe(false);
    });

    it("denies viewer update", () => {
      expect(canPerform("viewer", "update")).toBe(false);
    });

    it("denies viewer delete", () => {
      expect(canPerform("viewer", "delete")).toBe(false);
    });
  });
});
```

**Step 2: Run test to verify it fails**

Run: `npx jest tests/auth/roles.test.ts --verbose`
Expected: FAIL with "Cannot find module" because `src/auth/roles.ts` does not exist.

**Step 3: Write minimal implementation**

```typescript
// src/auth/roles.ts

export type Role = "admin" | "editor" | "viewer";

export type Action = "create" | "read" | "update" | "delete";

export const ROLE_HIERARCHY: Record<Role, number> = {
  admin: 3,
  editor: 2,
  viewer: 1,
};

const ROLE_PERMISSIONS: Record<Role, Set<Action>> = {
  admin: new Set(["create", "read", "update", "delete"]),
  editor: new Set(["create", "read", "update"]),
  viewer: new Set(["read"]),
};

export function canPerform(role: Role, action: Action): boolean {
  const permissions = ROLE_PERMISSIONS[role];
  if (!permissions) {
    return false;
  }
  return permissions.has(action);
}
```

**Step 4: Run test to verify it passes**

Run: `npx jest tests/auth/roles.test.ts --verbose`
Expected: PASS (10 tests)

**Step 5: Commit**

```bash
git add src/auth/roles.ts tests/auth/roles.test.ts
git commit -m "feat: define RBAC role types and permission map"
```

---

### Task 3: Extend the JWT Payload Type to Include `role`

**Files:**
- Modify: `src/middleware/auth.ts`
- Test: `tests/middleware/auth.test.ts`

**Step 1: Write the failing test**

Add a test to the existing auth middleware test file (or create it if it does not exist). This test verifies the decoded JWT now carries a `role` field that gets attached to `req.user`.

```typescript
// tests/middleware/auth.test.ts
// Add to existing test file or create new:
import { Request, Response, NextFunction } from "express";
import jwt from "jsonwebtoken";
import { authenticate } from "../../src/middleware/auth";

const JWT_SECRET = process.env.JWT_SECRET || "test-secret";

function mockReqResNext(token?: string) {
  const req = {
    headers: { authorization: token ? `Bearer ${token}` : undefined },
    user: undefined,
  } as unknown as Request & { user?: any };
  const res = {
    status: jest.fn().mockReturnThis(),
    json: jest.fn().mockReturnThis(),
  } as unknown as Response;
  const next = jest.fn() as NextFunction;
  return { req, res, next };
}

describe("authenticate middleware", () => {
  it("attaches user with role to req.user on valid token", () => {
    const token = jwt.sign(
      { userId: "u1", role: "editor" },
      JWT_SECRET
    );
    const { req, res, next } = mockReqResNext(token);

    authenticate(req, res, next);

    expect(next).toHaveBeenCalled();
    expect((req as any).user).toMatchObject({
      userId: "u1",
      role: "editor",
    });
  });

  it("defaults role to viewer when token has no role claim", () => {
    const token = jwt.sign({ userId: "u2" }, JWT_SECRET);
    const { req, res, next } = mockReqResNext(token);

    authenticate(req, res, next);

    expect(next).toHaveBeenCalled();
    expect((req as any).user.role).toBe("viewer");
  });
});
```

**Step 2: Run test to verify it fails**

Run: `npx jest tests/middleware/auth.test.ts --verbose`
Expected: FAIL -- the `role` field is not yet handled; `req.user.role` is `undefined`.

**Step 3: Write minimal implementation**

Modify `src/middleware/auth.ts`. Find the section where the JWT is decoded and `req.user` is set. Add `role` to the payload interface and default it to `"viewer"` if absent.

```typescript
// src/middleware/auth.ts
// --- Add/update these parts (keep existing logic intact) ---

import { Request, Response, NextFunction } from "express";
import jwt from "jsonwebtoken";
import { Role } from "../auth/roles";

const JWT_SECRET = process.env.JWT_SECRET || "test-secret";

export interface JwtPayload {
  userId: string;
  role: Role;
  iat?: number;
  exp?: number;
}

declare global {
  namespace Express {
    interface Request {
      user?: JwtPayload;
    }
  }
}

export function authenticate(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  const authHeader = req.headers.authorization;
  if (!authHeader || !authHeader.startsWith("Bearer ")) {
    res.status(401).json({ error: "Missing or invalid authorization header" });
    return;
  }

  const token = authHeader.split(" ")[1];

  try {
    const decoded = jwt.verify(token, JWT_SECRET) as Omit<JwtPayload, "role"> & { role?: Role };
    req.user = {
      userId: decoded.userId,
      role: decoded.role || "viewer",
      iat: decoded.iat,
      exp: decoded.exp,
    };
    next();
  } catch (err) {
    res.status(401).json({ error: "Invalid or expired token" });
  }
}
```

**Step 4: Run test to verify it passes**

Run: `npx jest tests/middleware/auth.test.ts --verbose`
Expected: PASS (2 tests, plus any pre-existing tests)

**Step 5: Commit**

```bash
git add src/middleware/auth.ts tests/middleware/auth.test.ts
git commit -m "feat: extend JWT payload and auth middleware with role field"
```

---

### Task 4: Create the `authorize` Middleware Factory

**Files:**
- Create: `src/middleware/authorize.ts`
- Test: `tests/middleware/authorize.test.ts`

**Step 1: Write the failing test**

```typescript
// tests/middleware/authorize.test.ts
import { Request, Response, NextFunction } from "express";
import { authorize } from "../../src/middleware/authorize";
import { JwtPayload } from "../../src/middleware/auth";

function mockReqResNext(user?: JwtPayload) {
  const req = { user } as Request & { user?: JwtPayload };
  const res = {
    status: jest.fn().mockReturnThis(),
    json: jest.fn().mockReturnThis(),
  } as unknown as Response;
  const next = jest.fn() as NextFunction;
  return { req, res, next };
}

describe("authorize middleware", () => {
  describe("authorize('read')", () => {
    const mw = authorize("read");

    it("allows admin", () => {
      const { req, res, next } = mockReqResNext({ userId: "u1", role: "admin" });
      mw(req, res, next);
      expect(next).toHaveBeenCalled();
    });

    it("allows editor", () => {
      const { req, res, next } = mockReqResNext({ userId: "u2", role: "editor" });
      mw(req, res, next);
      expect(next).toHaveBeenCalled();
    });

    it("allows viewer", () => {
      const { req, res, next } = mockReqResNext({ userId: "u3", role: "viewer" });
      mw(req, res, next);
      expect(next).toHaveBeenCalled();
    });
  });

  describe("authorize('create')", () => {
    const mw = authorize("create");

    it("allows admin", () => {
      const { req, res, next } = mockReqResNext({ userId: "u1", role: "admin" });
      mw(req, res, next);
      expect(next).toHaveBeenCalled();
    });

    it("allows editor", () => {
      const { req, res, next } = mockReqResNext({ userId: "u2", role: "editor" });
      mw(req, res, next);
      expect(next).toHaveBeenCalled();
    });

    it("denies viewer with 403", () => {
      const { req, res, next } = mockReqResNext({ userId: "u3", role: "viewer" });
      mw(req, res, next);
      expect(next).not.toHaveBeenCalled();
      expect(res.status).toHaveBeenCalledWith(403);
      expect(res.json).toHaveBeenCalledWith({
        error: "Forbidden: insufficient permissions",
      });
    });
  });

  describe("authorize('update')", () => {
    const mw = authorize("update");

    it("allows admin", () => {
      const { req, res, next } = mockReqResNext({ userId: "u1", role: "admin" });
      mw(req, res, next);
      expect(next).toHaveBeenCalled();
    });

    it("allows editor", () => {
      const { req, res, next } = mockReqResNext({ userId: "u2", role: "editor" });
      mw(req, res, next);
      expect(next).toHaveBeenCalled();
    });

    it("denies viewer with 403", () => {
      const { req, res, next } = mockReqResNext({ userId: "u3", role: "viewer" });
      mw(req, res, next);
      expect(next).not.toHaveBeenCalled();
      expect(res.status).toHaveBeenCalledWith(403);
    });
  });

  describe("authorize('delete')", () => {
    const mw = authorize("delete");

    it("allows admin", () => {
      const { req, res, next } = mockReqResNext({ userId: "u1", role: "admin" });
      mw(req, res, next);
      expect(next).toHaveBeenCalled();
    });

    it("denies editor with 403", () => {
      const { req, res, next } = mockReqResNext({ userId: "u2", role: "editor" });
      mw(req, res, next);
      expect(next).not.toHaveBeenCalled();
      expect(res.status).toHaveBeenCalledWith(403);
    });

    it("denies viewer with 403", () => {
      const { req, res, next } = mockReqResNext({ userId: "u3", role: "viewer" });
      mw(req, res, next);
      expect(next).not.toHaveBeenCalled();
      expect(res.status).toHaveBeenCalledWith(403);
    });
  });

  describe("edge cases", () => {
    it("returns 401 when req.user is undefined", () => {
      const mw = authorize("read");
      const { req, res, next } = mockReqResNext(undefined);
      mw(req, res, next);
      expect(next).not.toHaveBeenCalled();
      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({
        error: "Authentication required",
      });
    });
  });
});
```

**Step 2: Run test to verify it fails**

Run: `npx jest tests/middleware/authorize.test.ts --verbose`
Expected: FAIL with "Cannot find module" because `src/middleware/authorize.ts` does not exist.

**Step 3: Write minimal implementation**

```typescript
// src/middleware/authorize.ts
import { Request, Response, NextFunction } from "express";
import { Action, canPerform } from "../auth/roles";

export function authorize(action: Action) {
  return (req: Request, res: Response, next: NextFunction): void => {
    const user = req.user;

    if (!user) {
      res.status(401).json({ error: "Authentication required" });
      return;
    }

    if (!canPerform(user.role, action)) {
      res.status(403).json({ error: "Forbidden: insufficient permissions" });
      return;
    }

    next();
  };
}
```

**Step 4: Run test to verify it passes**

Run: `npx jest tests/middleware/authorize.test.ts --verbose`
Expected: PASS (13 tests)

**Step 5: Commit**

```bash
git add src/middleware/authorize.ts tests/middleware/authorize.test.ts
git commit -m "feat: add authorize middleware factory for RBAC"
```

---

### Task 5: Wire Authorization into API Routes

**Files:**
- Modify: `src/routes/index.ts` (or wherever your route definitions live -- check for `src/routes/*.ts`)
- Test: `tests/routes/rbac.integration.test.ts`

**Step 1: Write the failing integration test**

This test boots a minimal Express app with real middleware to verify end-to-end RBAC enforcement on representative routes.

```typescript
// tests/routes/rbac.integration.test.ts
import express from "express";
import request from "supertest";
import jwt from "jsonwebtoken";
import { authenticate } from "../../src/middleware/auth";
import { authorize } from "../../src/middleware/authorize";

const JWT_SECRET = process.env.JWT_SECRET || "test-secret";

function makeToken(role: string): string {
  return jwt.sign({ userId: "test-user", role }, JWT_SECRET);
}

function buildApp() {
  const app = express();
  app.use(express.json());

  // Sample resource routes with RBAC
  app.get("/api/items", authenticate, authorize("read"), (_req, res) => {
    res.json({ items: [] });
  });

  app.post("/api/items", authenticate, authorize("create"), (_req, res) => {
    res.status(201).json({ id: "new" });
  });

  app.put("/api/items/:id", authenticate, authorize("update"), (_req, res) => {
    res.json({ updated: true });
  });

  app.delete("/api/items/:id", authenticate, authorize("delete"), (_req, res) => {
    res.status(204).send();
  });

  return app;
}

describe("RBAC integration", () => {
  const app = buildApp();

  describe("GET /api/items (read)", () => {
    it("allows viewer", async () => {
      const res = await request(app)
        .get("/api/items")
        .set("Authorization", `Bearer ${makeToken("viewer")}`);
      expect(res.status).toBe(200);
    });

    it("allows editor", async () => {
      const res = await request(app)
        .get("/api/items")
        .set("Authorization", `Bearer ${makeToken("editor")}`);
      expect(res.status).toBe(200);
    });

    it("allows admin", async () => {
      const res = await request(app)
        .get("/api/items")
        .set("Authorization", `Bearer ${makeToken("admin")}`);
      expect(res.status).toBe(200);
    });

    it("rejects unauthenticated with 401", async () => {
      const res = await request(app).get("/api/items");
      expect(res.status).toBe(401);
    });
  });

  describe("POST /api/items (create)", () => {
    it("allows editor", async () => {
      const res = await request(app)
        .post("/api/items")
        .set("Authorization", `Bearer ${makeToken("editor")}`)
        .send({ name: "test" });
      expect(res.status).toBe(201);
    });

    it("allows admin", async () => {
      const res = await request(app)
        .post("/api/items")
        .set("Authorization", `Bearer ${makeToken("admin")}`)
        .send({ name: "test" });
      expect(res.status).toBe(201);
    });

    it("denies viewer with 403", async () => {
      const res = await request(app)
        .post("/api/items")
        .set("Authorization", `Bearer ${makeToken("viewer")}`)
        .send({ name: "test" });
      expect(res.status).toBe(403);
    });
  });

  describe("PUT /api/items/:id (update)", () => {
    it("allows editor", async () => {
      const res = await request(app)
        .put("/api/items/1")
        .set("Authorization", `Bearer ${makeToken("editor")}`)
        .send({ name: "updated" });
      expect(res.status).toBe(200);
    });

    it("allows admin", async () => {
      const res = await request(app)
        .put("/api/items/1")
        .set("Authorization", `Bearer ${makeToken("admin")}`)
        .send({ name: "updated" });
      expect(res.status).toBe(200);
    });

    it("denies viewer with 403", async () => {
      const res = await request(app)
        .put("/api/items/1")
        .set("Authorization", `Bearer ${makeToken("viewer")}`)
        .send({ name: "updated" });
      expect(res.status).toBe(403);
    });
  });

  describe("DELETE /api/items/:id (delete)", () => {
    it("allows admin", async () => {
      const res = await request(app)
        .delete("/api/items/1")
        .set("Authorization", `Bearer ${makeToken("admin")}`);
      expect(res.status).toBe(204);
    });

    it("denies editor with 403", async () => {
      const res = await request(app)
        .delete("/api/items/1")
        .set("Authorization", `Bearer ${makeToken("editor")}`);
      expect(res.status).toBe(403);
    });

    it("denies viewer with 403", async () => {
      const res = await request(app)
        .delete("/api/items/1")
        .set("Authorization", `Bearer ${makeToken("viewer")}`);
      expect(res.status).toBe(403);
    });
  });
});
```

**Step 2: Run test to verify it fails**

Run: `npx jest tests/routes/rbac.integration.test.ts --verbose`
Expected: FAIL initially if route files are not yet wired. Once the test app above is self-contained, it should actually pass because it wires middleware directly. This test validates the full stack works end-to-end.

If tests pass immediately, that confirms the middleware chain is correct. Proceed to wiring real routes.

**Step 3: Wire middleware into actual route files**

Find your existing route files (check `src/routes/` directory). For each resource router, add `authenticate` and `authorize` middleware. Example for a typical resource router:

```typescript
// src/routes/items.ts (or whatever your resource routes are)
// --- Modify existing route definitions ---

import { Router } from "express";
import { authenticate } from "../middleware/auth";
import { authorize } from "../middleware/authorize";

const router = Router();

// Read operations - all authenticated users
router.get("/", authenticate, authorize("read"), itemController.list);
router.get("/:id", authenticate, authorize("read"), itemController.getById);

// Create/Update operations - editors and admins
router.post("/", authenticate, authorize("create"), itemController.create);
router.put("/:id", authenticate, authorize("update"), itemController.update);
router.patch("/:id", authenticate, authorize("update"), itemController.update);

// Delete operations - admins only
router.delete("/:id", authenticate, authorize("delete"), itemController.remove);

export default router;
```

Repeat this pattern for every resource router in `src/routes/`. The key mapping is:
- `GET` routes use `authorize("read")`
- `POST` routes use `authorize("create")`
- `PUT`/`PATCH` routes use `authorize("update")`
- `DELETE` routes use `authorize("delete")`

**Step 4: Run test to verify it passes**

Run: `npx jest tests/routes/rbac.integration.test.ts --verbose`
Expected: PASS (12 tests)

Also run the full test suite to verify nothing is broken:

Run: `npx jest --verbose`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/routes/ tests/routes/rbac.integration.test.ts
git commit -m "feat: wire RBAC authorize middleware into API routes"
```

---

### Task 6: Add Role to JWT Token Generation (Sign-Up / Login)

**Files:**
- Modify: `src/auth/token.ts` (or wherever tokens are generated -- check for `jwt.sign` calls)
- Test: `tests/auth/token.test.ts`

**Step 1: Write the failing test**

```typescript
// tests/auth/token.test.ts
import jwt from "jsonwebtoken";
import { generateToken } from "../../src/auth/token";

const JWT_SECRET = process.env.JWT_SECRET || "test-secret";

describe("generateToken", () => {
  it("includes role in the JWT payload", () => {
    const token = generateToken({ userId: "u1", role: "editor" });
    const decoded = jwt.verify(token, JWT_SECRET) as any;
    expect(decoded.userId).toBe("u1");
    expect(decoded.role).toBe("editor");
  });

  it("defaults to viewer role when none is specified", () => {
    const token = generateToken({ userId: "u2" });
    const decoded = jwt.verify(token, JWT_SECRET) as any;
    expect(decoded.role).toBe("viewer");
  });

  it("includes admin role when specified", () => {
    const token = generateToken({ userId: "u3", role: "admin" });
    const decoded = jwt.verify(token, JWT_SECRET) as any;
    expect(decoded.role).toBe("admin");
  });
});
```

**Step 2: Run test to verify it fails**

Run: `npx jest tests/auth/token.test.ts --verbose`
Expected: FAIL -- either the function does not exist or it does not include `role` in the payload.

**Step 3: Write minimal implementation**

```typescript
// src/auth/token.ts
import jwt from "jsonwebtoken";
import { Role } from "./roles";

const JWT_SECRET = process.env.JWT_SECRET || "test-secret";
const TOKEN_EXPIRY = process.env.TOKEN_EXPIRY || "24h";

interface TokenInput {
  userId: string;
  role?: Role;
}

export function generateToken(input: TokenInput): string {
  return jwt.sign(
    {
      userId: input.userId,
      role: input.role || "viewer",
    },
    JWT_SECRET,
    { expiresIn: TOKEN_EXPIRY }
  );
}
```

**Step 4: Run test to verify it passes**

Run: `npx jest tests/auth/token.test.ts --verbose`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add src/auth/token.ts tests/auth/token.test.ts
git commit -m "feat: include role in JWT token generation"
```

---

### Task 7: Add an Admin Endpoint for Changing User Roles

**Files:**
- Create: `src/routes/admin.ts`
- Test: `tests/routes/admin.test.ts`

**Step 1: Write the failing test**

```typescript
// tests/routes/admin.test.ts
import express from "express";
import request from "supertest";
import jwt from "jsonwebtoken";
import { authenticate } from "../../src/middleware/auth";
import { adminRouter } from "../../src/routes/admin";

const JWT_SECRET = process.env.JWT_SECRET || "test-secret";

// Mock the database query function
jest.mock("../../src/db/pool", () => ({
  query: jest.fn(),
}));

import { query } from "../../src/db/pool";
const mockQuery = query as jest.MockedFunction<typeof query>;

function makeToken(userId: string, role: string): string {
  return jwt.sign({ userId, role }, JWT_SECRET);
}

function buildApp() {
  const app = express();
  app.use(express.json());
  app.use("/admin", authenticate, adminRouter);
  return app;
}

describe("PATCH /admin/users/:id/role", () => {
  const app = buildApp();

  it("allows admin to change a user role", async () => {
    mockQuery.mockResolvedValueOnce({
      rows: [{ id: "target-user", role: "editor" }],
      rowCount: 1,
    } as any);

    const res = await request(app)
      .patch("/admin/users/target-user/role")
      .set("Authorization", `Bearer ${makeToken("admin-user", "admin")}`)
      .send({ role: "editor" });

    expect(res.status).toBe(200);
    expect(res.body.role).toBe("editor");
  });

  it("rejects editor with 403", async () => {
    const res = await request(app)
      .patch("/admin/users/target-user/role")
      .set("Authorization", `Bearer ${makeToken("editor-user", "editor")}`)
      .send({ role: "admin" });

    expect(res.status).toBe(403);
  });

  it("rejects viewer with 403", async () => {
    const res = await request(app)
      .patch("/admin/users/target-user/role")
      .set("Authorization", `Bearer ${makeToken("viewer-user", "viewer")}`)
      .send({ role: "editor" });

    expect(res.status).toBe(403);
  });

  it("rejects invalid role value with 400", async () => {
    const res = await request(app)
      .patch("/admin/users/target-user/role")
      .set("Authorization", `Bearer ${makeToken("admin-user", "admin")}`)
      .send({ role: "superadmin" });

    expect(res.status).toBe(400);
    expect(res.body.error).toContain("Invalid role");
  });

  it("returns 404 when user does not exist", async () => {
    mockQuery.mockResolvedValueOnce({
      rows: [],
      rowCount: 0,
    } as any);

    const res = await request(app)
      .patch("/admin/users/nonexistent/role")
      .set("Authorization", `Bearer ${makeToken("admin-user", "admin")}`)
      .send({ role: "editor" });

    expect(res.status).toBe(404);
  });
});
```

**Step 2: Run test to verify it fails**

Run: `npx jest tests/routes/admin.test.ts --verbose`
Expected: FAIL with "Cannot find module" because `src/routes/admin.ts` does not exist.

**Step 3: Write minimal implementation**

```typescript
// src/routes/admin.ts
import { Router, Request, Response } from "express";
import { authorize } from "../middleware/authorize";
import { Role } from "../auth/roles";
import { query } from "../db/pool";

const VALID_ROLES: Set<string> = new Set(["admin", "editor", "viewer"]);

export const adminRouter = Router();

// All admin routes require the "delete" action (admin-only)
adminRouter.use(authorize("delete"));

adminRouter.patch(
  "/users/:id/role",
  async (req: Request, res: Response): Promise<void> => {
    const { id } = req.params;
    const { role } = req.body;

    if (!role || !VALID_ROLES.has(role)) {
      res.status(400).json({
        error: `Invalid role. Must be one of: ${[...VALID_ROLES].join(", ")}`,
      });
      return;
    }

    const result = await query(
      "UPDATE users SET role = $1 WHERE id = $2 RETURNING id, role",
      [role, id]
    );

    if (result.rowCount === 0) {
      res.status(404).json({ error: "User not found" });
      return;
    }

    res.json(result.rows[0]);
  }
);
```

**Step 4: Run test to verify it passes**

Run: `npx jest tests/routes/admin.test.ts --verbose`
Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add src/routes/admin.ts tests/routes/admin.test.ts
git commit -m "feat: add admin endpoint for changing user roles"
```

---

### Task 8: Run Full Test Suite and Verify

**Files:** No new files.

**Step 1: Run all tests**

Run: `npx jest --verbose --coverage`
Expected: All tests PASS. Review coverage output to confirm auth and middleware files are well covered.

**Step 2: Run TypeScript compiler check**

Run: `npx tsc --noEmit`
Expected: No type errors.

**Step 3: Final commit (if any linting or type fixes were needed)**

```bash
git add -A
git commit -m "chore: fix any linting or type issues from RBAC implementation"
```

If there are no changes, skip this commit.

---

## Summary of Files Created/Modified

| File | Action |
|------|--------|
| `src/db/migrations/XXXXXX_add_role_to_users.ts` | Create |
| `src/auth/roles.ts` | Create |
| `src/auth/token.ts` | Create or Modify |
| `src/middleware/auth.ts` | Modify |
| `src/middleware/authorize.ts` | Create |
| `src/routes/admin.ts` | Create |
| `src/routes/*.ts` (existing resource routes) | Modify |
| `tests/db/migrations/add_role_to_users.test.ts` | Create |
| `tests/auth/roles.test.ts` | Create |
| `tests/auth/token.test.ts` | Create |
| `tests/middleware/auth.test.ts` | Create or Modify |
| `tests/middleware/authorize.test.ts` | Create |
| `tests/routes/rbac.integration.test.ts` | Create |
| `tests/routes/admin.test.ts` | Create |

## Permission Matrix

| Action | Admin | Editor | Viewer |
|--------|-------|--------|--------|
| `read` | Yes | Yes | Yes |
| `create` | Yes | Yes | No |
| `update` | Yes | Yes | No |
| `delete` | Yes | No | No |
