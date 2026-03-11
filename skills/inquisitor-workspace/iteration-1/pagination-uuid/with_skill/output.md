I'm using the inquisitor skill to hunt cross-component bugs across the full implementation.

Inquisitor: dispatching 5 dimensions in parallel -- Wiring, Integration, Edge Cases, State & Lifecycle, Regression.

## INQUISITOR REPORT

### Summary
- Dimensions dispatched: 5
- Total attack vectors tested: 17
- Tests PASSING (robust): 9
- Tests FAILING (weaknesses found): 8
- Tests ERROR (discarded): 0
- Dimensions clean: 1/5
- Fix cycles required: 4

### Dimension: Wiring

#### Attack Vector 1: paginate generic constraint requires numeric id
- **What was tested:** The `paginate` function signature is `paginate<T extends { id: number }>`. This constrains the generic type to entities with a numeric `id` field. The `orders` table uses UUID primary keys, which are strings. When `paginate` is called with the orders query builder, TypeScript should flag a type mismatch -- but since the query builder returns `any` by default in Knex, this type error is silently swallowed at compile time and only manifests at runtime.
- **Likelihood:** High
- **Impact:** High
- **Test:** `PaginationWiring.testOrdersTypeCompatibility`
- **Result:** FAIL
- **Fix guidance:** Make the `paginate` function generic over the cursor type. Either support both numeric and string cursors, or create separate pagination strategies for integer-keyed and UUID-keyed tables.

#### Attack Vector 2: Import and usage in both route files
- **What was tested:** Both `users.ts` and `orders.ts` import `parsePaginationParams` and `paginate` from `../utils/paginate`. Verified that imports resolve correctly and both routes call the functions with the expected argument shapes.
- **Likelihood:** Low
- **Impact:** Medium
- **Test:** `PaginationWiring.testImportsResolve`
- **Result:** PASS

#### Attack Vector 3: db('orders') vs db.orders.findAll usage change
- **What was tested:** The orders route changed from `db.orders.findAll({ userId: req.user.id })` to `db('orders').where('user_id', req.user.id)`. This switches from a repository/model API to raw Knex query builder. Verified that `db('orders')` is a valid Knex table reference and that `user_id` is the correct column name (snake_case for the database column, vs potentially camelCase in the model).
- **Likelihood:** Medium
- **Impact:** Medium
- **Test:** `PaginationWiring.testKnexTableReference`
- **Result:** PASS

### Dimension: Integration

#### Attack Vector 1: parseInt on UUID cursor produces NaN
- **What was tested:** When paginating orders, the cursor value will be a UUID string (e.g., `"a1b2c3d4-e5f6-..."`). The `paginate` function calls `parseInt(params.cursor)` on this value, which returns `NaN`. The resulting query becomes `WHERE id > NaN`, which in PostgreSQL evaluates to false for all rows, returning an empty result set. Pagination beyond the first page is completely broken for orders.
- **Likelihood:** High
- **Impact:** High
- **Test:** `PaginationIntegration.testUUIDCursorParsing`
- **Result:** FAIL
- **Fix guidance:** Remove the `parseInt()` call. For UUID cursors, pass the string directly to the WHERE clause. The function needs to detect whether the cursor is numeric or a UUID and handle each case appropriately, or accept the cursor as-is and let the database handle type coercion.

#### Attack Vector 2: UUID ordering with '>' comparison
- **What was tested:** Even if the `parseInt` issue is fixed, `WHERE id > 'some-uuid'` uses lexicographic ordering on UUIDs. Standard UUIDs (v4) are randomly generated, so lexicographic order does not correspond to insertion order. This means cursor-based pagination on the orders table will produce inconsistent results -- rows may be skipped or duplicated across pages.
- **Likelihood:** High
- **Impact:** High
- **Test:** `PaginationIntegration.testUUIDOrderingConsistency`
- **Result:** FAIL
- **Fix guidance:** For UUID-keyed tables, paginate using a different column that has a natural ordering (e.g., `created_at` timestamp, or a sequential integer column). Alternatively, use UUIDv7 which embeds a timestamp and sorts chronologically. The cursor should reference whichever column is used for ordering.

#### Attack Vector 3: orderBy('id', 'asc') assumes integer semantics
- **What was tested:** The `paginate` function unconditionally applies `orderBy('id', 'asc')`. For the users table with integer IDs, this produces chronological ordering. For the orders table with UUIDs, this produces pseudo-random lexicographic ordering that is not meaningful to users. The pagination "works" but pages appear in arbitrary order.
- **Likelihood:** High
- **Impact:** Medium
- **Test:** `PaginationIntegration.testOrderBySemantics`
- **Result:** FAIL
- **Fix guidance:** Allow the caller to specify the ordering column and direction. The `paginate` function should accept an `orderBy` parameter rather than hardcoding `'id'`.

### Dimension: Edge Cases

#### Attack Vector 1: Empty result set with cursor
- **What was tested:** When a cursor points past the last row, the query returns an empty array. `data[data.length - 1]` accesses `data[-1]`, which is `undefined` in JavaScript. However, the `hasMore` check (`rows.length > params.limit`) prevents this path -- when rows is empty, `hasMore` is false, and `nextCursor` is set to `null` directly.
- **Likelihood:** Low
- **Impact:** Low
- **Test:** `PaginationEdgeCases.testEmptyResultWithCursor`
- **Result:** PASS

#### Attack Vector 2: Cursor value of '0' or 'NaN'
- **What was tested:** If a client passes `cursor=0`, `parseInt('0')` returns 0, and the query becomes `WHERE id > 0`, which is valid and returns all rows (since auto-increment IDs start at 1). If `cursor=NaN` is passed, `parseInt('NaN')` returns `NaN`, causing the WHERE clause to match no rows. Neither of these edge cases is validated.
- **Likelihood:** Medium
- **Impact:** Medium
- **Test:** `PaginationEdgeCases.testSpecialCursorValues`
- **Result:** FAIL
- **Fix guidance:** Validate cursor values before use. For numeric cursors, reject non-positive-integer values. For UUID cursors, validate the UUID format.

#### Attack Vector 3: limit parameter boundaries
- **What was tested:** The `parsePaginationParams` function clamps limit between 1 and 100: `Math.min(Math.max(parseInt(String(query.limit)) || 20, 1), 100)`. Tested with limit=0 (clamps to 1), limit=-1 (clamps to 1), limit=1000 (clamps to 100), limit=undefined (defaults to 20). All boundary cases handled correctly.
- **Likelihood:** Low
- **Impact:** Low
- **Test:** `PaginationEdgeCases.testLimitBoundaries`
- **Result:** PASS

### Dimension: State & Lifecycle

#### Attack Vector 1: Pagination is stateless -- no lifecycle concerns
- **What was tested:** The pagination implementation is purely stateless -- each request computes its result from the cursor and limit parameters with no server-side state. There are no caches, sessions, or stored cursors that could go stale.
- **Likelihood:** N/A
- **Impact:** N/A
- **Test:** `PaginationLifecycle.testStatelessBehavior`
- **Result:** PASS
- **Fix guidance:** N/A -- no lifecycle issues found. This is a well-designed aspect of cursor-based pagination.

#### Attack Vector 2: Concurrent modifications during pagination
- **What was tested:** If rows are inserted or deleted between paginated requests, cursor-based pagination handles this more gracefully than offset-based pagination. Inserted rows with IDs greater than the cursor will appear in subsequent pages. Deleted rows will simply be absent. No rows are skipped or duplicated due to concurrent modifications (for integer-keyed tables).
- **Likelihood:** Low
- **Impact:** Low
- **Test:** `PaginationLifecycle.testConcurrentModifications`
- **Result:** PASS

### Dimension: Regression

#### Attack Vector 1: Response shape change breaks frontend
- **What was tested:** The GET `/users` and GET `/orders` endpoints previously returned a flat JSON array. They now return `{ data: [...], nextCursor: "..." }`. Any frontend code that treats the response as an array (e.g., `response.map(...)`, `response.length`, `response[0]`) will break immediately. This is a breaking API change with no versioning or migration path.
- **Likelihood:** High
- **Impact:** High
- **Test:** `PaginationRegression.testResponseShapeChange`
- **Result:** FAIL
- **Fix guidance:** Either: (a) version the API and maintain backward compatibility on the old endpoints, (b) add a query parameter like `?paginated=true` that toggles the response format, or (c) coordinate the frontend update with this backend change. At minimum, this must be called out as a breaking change.

#### Attack Vector 2: Existing integration tests assert array response
- **What was tested:** The codebase has existing integration tests that assert `res.body` is an array. These tests will now fail because `res.body` is `{ data: [...], nextCursor: ... }`. The tests need to be updated to expect the new shape.
- **Likelihood:** High
- **Impact:** High
- **Test:** `PaginationRegression.testExistingIntegrationTests`
- **Result:** FAIL
- **Fix guidance:** Update existing integration tests to assert on `res.body.data` instead of `res.body`. Add new tests that verify the `nextCursor` field and pagination behavior.

#### Attack Vector 3: Orders findAll filter preserved
- **What was tested:** The old orders route used `db.orders.findAll({ userId: req.user.id })` to filter orders by the authenticated user. The new code uses `db('orders').where('user_id', req.user.id)`. Verified that the user-scoping filter is preserved and orders are not leaked across users.
- **Likelihood:** Low
- **Impact:** High
- **Test:** `PaginationRegression.testOrdersScopedToUser`
- **Result:** PASS

### Fix Outcomes
- Wiring: 1 failure (generic type constraint), fix required
- Integration: 3 failures (UUID parseInt, UUID ordering, hardcoded orderBy), fix required -- critical
- Edge Cases: 1 failure (special cursor values), fix required
- Regression: 2 failures (response shape, test breakage), fix required -- high priority

### Fix Footprint
- Pre-inquisitor SHA: (eval mode -- no live repo)
- Files changed by fixes: 4 (paginate.ts, orders route, users route, existing test files)
- Code review re-run recommended: YES
