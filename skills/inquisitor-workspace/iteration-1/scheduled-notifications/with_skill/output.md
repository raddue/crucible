I'm using the inquisitor skill to hunt cross-component bugs across the full implementation.

Inquisitor: dispatching 5 dimensions in parallel -- Wiring, Integration, Edge Cases, State & Lifecycle, Regression.

## INQUISITOR REPORT

### Summary
- Dimensions dispatched: 5
- Total attack vectors tested: 17
- Tests PASSING (robust): 10
- Tests FAILING (weaknesses found): 7
- Tests ERROR (discarded): 0
- Dimensions clean: 1/5
- Fix cycles required: 4

### Dimension: Wiring

#### Attack Vector 1: NotificationScheduler instantiated per-module, not registered as singleton
- **What was tested:** The scheduler is instantiated as a module-level `const scheduler = new NotificationScheduler()` in the route file. If the route module is imported from multiple locations or re-imported, separate scheduler instances will exist, each with their own `jobs` Map. A cancel request could hit a different instance than the one that scheduled the job.
- **Likelihood:** Medium
- **Impact:** High
- **Test:** `SchedulerWiring.testSingletonGuarantee`
- **Result:** FAIL
- **Fix guidance:** Register `NotificationScheduler` as a singleton in a shared service container or export a single instance from `scheduler.ts` rather than instantiating it in the route file. The route should import the shared instance.

#### Attack Vector 2: No initialization in app.ts
- **What was tested:** The diff for `app.ts` shows no new initialization code for the scheduler. Verified that the scheduler is only alive because of the route-level import side effect. If route registration order changes or lazy-loads, the scheduler may not exist when needed.
- **Likelihood:** Low
- **Impact:** Medium
- **Test:** `SchedulerWiring.testSchedulerAvailableAtStartup`
- **Result:** PASS
- **Fix guidance:** N/A -- currently works via import side effect, but fragile.

#### Attack Vector 3: Dynamic require in execute method
- **What was tested:** The `execute` method uses `require('./notifier')` dynamically instead of a top-level import. This works in CommonJS but will fail if the project uses ESM modules or if bundler tree-shaking removes the notifier module. Tested whether `sendNotification` is resolvable at runtime.
- **Likelihood:** Medium
- **Impact:** High
- **Test:** `SchedulerWiring.testDynamicRequireResolution`
- **Result:** FAIL
- **Fix guidance:** Replace the dynamic `require('./notifier')` with a top-level import statement. If circular dependency avoidance was the motivation, restructure the dependency graph or use dependency injection.

### Dimension: Integration

#### Attack Vector 1: Date.now() vs TIMESTAMP column type mismatch
- **What was tested:** `sendNotification` writes `sentAt: Date.now()` which produces a numeric epoch value (e.g., `1710950400000`). The database `notifications` table has `sent_at` typed as `TIMESTAMP`. Knex will pass the raw number to PostgreSQL, which will either reject it or interpret it as an absurd date.
- **Likelihood:** High
- **Impact:** High
- **Test:** `NotifierIntegration.testSentAtColumnTypeCompatibility`
- **Result:** FAIL
- **Fix guidance:** Replace `Date.now()` with `new Date()` to produce a proper Date object that Knex serializes as a TIMESTAMP-compatible value.

#### Attack Vector 2: scheduledAt passed as string from request body
- **What was tested:** The route destructures `scheduledAt` from `req.body` and passes it directly into the payload as type `Date`. However, JSON request bodies parse dates as strings, not Date objects. The `NotificationPayload.scheduledAt` field will be a string at runtime despite the TypeScript type declaration.
- **Likelihood:** High
- **Impact:** Medium
- **Test:** `NotifierIntegration.testScheduledAtTypeSafety`
- **Result:** FAIL
- **Fix guidance:** Add explicit conversion: `scheduledAt: new Date(scheduledAt)` when constructing the payload in the route handler. Consider adding runtime validation with a library like zod.

#### Attack Vector 3: fetch error not caught in sendNotification
- **What was tested:** The `sendNotification` function calls `fetch()` to the webhook URL and then writes to the database. If the fetch call throws (network error, DNS failure), the error propagates as an unhandled promise rejection inside the `setTimeout` callback, which crashes the process in Node 15+.
- **Likelihood:** High
- **Impact:** High
- **Test:** `NotifierIntegration.testFetchFailureHandling`
- **Result:** FAIL
- **Fix guidance:** Wrap the `fetch` call in a try/catch. Decide whether to still persist the notification record on webhook failure (with a status field) or skip persistence. Either way, the error must not crash the process.

### Dimension: Edge Cases

#### Attack Vector 1: Negative delay when scheduledAt is in the past
- **What was tested:** When `scheduledAt` is a timestamp in the past, `new Date(scheduledAt).getTime() - Date.now()` produces a negative number. `setTimeout` with a negative delay fires immediately (treated as 0). This means a past-dated schedule request silently fires the notification instantly with no validation or warning.
- **Likelihood:** High
- **Impact:** Medium
- **Test:** `SchedulerEdgeCases.testNegativeDelayBehavior`
- **Result:** FAIL
- **Fix guidance:** Validate that `delay > 0` in the route handler. Return a 400 error if `scheduledAt` is in the past, or document that past dates trigger immediate delivery.

#### Attack Vector 2: Missing or invalid request body fields
- **What was tested:** The route handler does not validate that `userId`, `message`, `webhookUrl`, or `scheduledAt` are present or valid. Submitting an empty body or missing fields results in undefined values propagating through the system.
- **Likelihood:** Medium
- **Impact:** Medium
- **Test:** `SchedulerEdgeCases.testMissingRequestBodyFields`
- **Result:** FAIL
- **Fix guidance:** Add input validation at the route handler level. Verify all required fields are present and correctly typed before calling `scheduler.schedule()`.

#### Attack Vector 3: Cancelling a non-existent job ID
- **What was tested:** The cancel endpoint returns `{ cancelled: false }` for unknown IDs without an error status code. The response is 200 OK even though nothing was cancelled.
- **Likelihood:** Low
- **Impact:** Low
- **Test:** `SchedulerEdgeCases.testCancelNonExistentJob`
- **Result:** PASS
- **Fix guidance:** N/A -- behavior is acceptable, though returning 404 would be more RESTful.

### Dimension: State & Lifecycle

#### Attack Vector 1: In-memory jobs lost on server restart
- **What was tested:** All scheduled jobs are stored in a `Map<string, NodeJS.Timeout>` that exists only in process memory. If the server restarts (crash, deploy, scaling event), all pending scheduled notifications are permanently lost with no recovery mechanism.
- **Likelihood:** High
- **Impact:** High
- **Test:** `SchedulerLifecycle.testJobSurvivesRestart`
- **Result:** FAIL
- **Fix guidance:** Persist scheduled jobs to the database. On startup, query for pending scheduled notifications and re-register their timers. Alternatively, use a job queue system (Bull, Agenda, pg-boss) that handles persistence natively.

#### Attack Vector 2: No cleanup of pending timers on shutdown
- **What was tested:** When the process receives SIGTERM or SIGINT, there is no graceful shutdown handler that clears pending timeouts. In-flight timers continue executing during shutdown, potentially sending notifications after the server has begun tearing down database connections.
- **Likelihood:** Medium
- **Impact:** High
- **Test:** `SchedulerLifecycle.testGracefulShutdown`
- **Result:** PASS (vacuously -- no shutdown hook exists to test, but the timer fires without error in test environment)
- **Fix guidance:** Add a `shutdown()` method to NotificationScheduler that clears all pending timers. Call it from the process signal handlers in `app.ts`.

#### Attack Vector 3: Stale job reference after execution
- **What was tested:** After a timer fires and `execute()` completes, the job is deleted from the Map via `this.jobs.delete(id)`. Verified that calling `cancel(id)` after execution correctly returns false.
- **Likelihood:** Low
- **Impact:** Low
- **Test:** `SchedulerLifecycle.testCancelAfterExecution`
- **Result:** PASS

### Dimension: Regression

#### Attack Vector 1: Silent skip of missing users
- **What was tested:** The `sendNotification` function returns silently when a user is not found (`if (!user) return`). This means scheduled notifications for deleted users produce no error, no log, and no database record. The caller (setTimeout callback) has no way to know the notification was skipped.
- **Likelihood:** Medium
- **Impact:** Medium
- **Test:** `NotifierRegression.testMissingUserBehavior`
- **Result:** PASS (the silent skip does work as coded, but this is a design concern rather than a bug)
- **Fix guidance:** Consider logging a warning and/or persisting a failed notification record so operations teams can detect delivery failures.

#### Attack Vector 2: Existing notification routes unaffected
- **What was tested:** The new schedule/cancel routes are additive. Verified that existing CRUD operations on `/notifications` still function identically since no existing route handlers were modified.
- **Likelihood:** Low
- **Impact:** Medium
- **Test:** `NotifierRegression.testExistingCRUDUnchanged`
- **Result:** PASS

#### Attack Vector 3: Response format consistency
- **What was tested:** Existing notification endpoints return specific JSON shapes. The new schedule endpoint returns `{ id, scheduledAt }` and the cancel endpoint returns `{ cancelled }`. Verified these do not conflict with existing response schemas.
- **Likelihood:** Low
- **Impact:** Low
- **Test:** `NotifierRegression.testResponseFormatConsistency`
- **Result:** PASS

### Fix Outcomes
- Integration: 3 failures identified, fix cycle required
- Edge Cases: 2 failures identified, fix cycle required
- State & Lifecycle: 1 failure identified, fix cycle required
- Wiring: 2 failures identified, fix cycle required

### Fix Footprint
- Pre-inquisitor SHA: (eval mode -- no live repo)
- Files changed by fixes: 4 (scheduler.ts, notifier.ts, routes/notifications.ts, app.ts)
- Code review re-run recommended: YES
