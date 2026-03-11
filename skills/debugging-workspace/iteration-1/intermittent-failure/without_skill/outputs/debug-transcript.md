# Debug Transcript: Intermittent CI Integration Test Failure

## User's Problem
CI pipeline fails ~30% of the time on `test_concurrent_order_processing`. The test expects all orders to have status `fulfilled` but sometimes finds `processing` instead. Started failing ~2 weeks ago with no code changes to order processing.

## Investigation

Let me trace through the test and application code:

**The test flow:**
1. Create 3 orders concurrently
2. Call `processOrder` on each concurrently
3. `sleep(2000)` -- wait 2 seconds for async processing
4. Check all orders have status `fulfilled`

**What `processOrder` does:**
1. Sets order status to `processing` in the DB
2. Queues a `fulfill` job to the job queue
3. Returns `{ queued: true }`

**What the fulfillment worker does:**
1. Picks up the job from the queue
2. Runs fulfillment logic (takes **500ms-3000ms** depending on inventory checks)
3. Sets order status to `fulfilled`

**The critical timing issue:**

The test waits exactly 2000ms for all fulfillment jobs to complete. But the fulfillment worker takes between 500ms and 3000ms per job. If any of the 3 jobs takes longer than 2 seconds, the test fails.

Even on a fast machine, a job could take up to 3000ms. But on a slow machine, the issue is worse because:
- The job queue itself takes time to dispatch and pick up jobs
- The worker competes for CPU with the test process, the database, and Redis
- Multiple jobs running concurrently compete for resources

**The timeline of changes confirms this:**

| Event | When | Impact |
|-------|------|--------|
| CI runner downgraded from 4-core to 2-core | 2 weeks ago | Less CPU = slower job processing |
| Test started failing intermittently | 2 weeks ago | Exact match |
| Node bumped from 18.17 to 18.19 | 1 week ago | No relevant changes |

The failure onset matches the CI runner downgrade perfectly. On 4-core machines, the fulfillment worker, job queue, database, and test runner all had dedicated cores. On 2-core machines, they're contending for CPU, making fulfillment consistently slower and pushing more jobs past the 2-second window.

The ~30% failure rate makes sense: if fulfillment time is roughly uniformly distributed between 500ms-3000ms, on a 2-core machine with overhead, there's a meaningful probability that at least one of the 3 concurrent jobs exceeds 2 seconds total (including queue overhead).

## Root Cause

This is **not an application code bug**. The order processing logic is correct. This is a **test infrastructure issue**: the test uses a fixed `sleep(2000)` to wait for asynchronous job completion, but the actual fulfillment time can be up to 3000ms (or more under resource contention). The CI runner downgrade from 4-core to 2-core machines increased resource contention and pushed fulfillment times past the hardcoded sleep threshold.

The `sleep(2000)` is a fragile timing assumption that breaks under slower environments.

## Fix

Replace the fixed sleep with **condition-based polling** -- repeatedly check if the orders are fulfilled, with a reasonable timeout:

```javascript
// Helper: poll a condition until it's true or timeout
async function waitForCondition(conditionFn, { timeout = 15000, interval = 250 } = {}) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    if (await conditionFn()) return true;
    await sleep(interval);
  }
  throw new Error(`Condition not met within ${timeout}ms`);
}

test('test_concurrent_order_processing', async () => {
  const orders = await Promise.all([
    createOrder({ item: 'widget', qty: 1 }),
    createOrder({ item: 'gadget', qty: 2 }),
    createOrder({ item: 'doohickey', qty: 1 }),
  ]);

  // Process all orders concurrently
  await Promise.all(orders.map(o => processOrder(o.id)));

  // Wait for all orders to be fulfilled (with timeout instead of fixed sleep)
  await waitForCondition(async () => {
    const statuses = await Promise.all(
      orders.map(async (o) => {
        const updated = await getOrder(o.id);
        return updated.status;
      })
    );
    return statuses.every(s => s === 'fulfilled');
  }, { timeout: 15000, interval: 500 });

  // Verify all orders are fulfilled
  for (const order of orders) {
    const updated = await getOrder(order.id);
    expect(updated.status).toBe('fulfilled');
  }
});
```

**Key properties of this fix:**

1. **No fixed sleep**: Instead of sleeping a hardcoded duration, it polls the actual condition (all orders fulfilled).
2. **Generous timeout**: 15 seconds is enough for even the slowest CI environment, but the test completes as soon as the condition is met (often in 1-3 seconds).
3. **Polling interval**: 500ms is frequent enough to be responsive but not so frequent that it hammers the database.
4. **Clear failure mode**: If something is genuinely broken (not just slow), the timeout ensures the test fails with a clear message rather than hanging forever.

## Additional Recommendations

1. **Audit other tests**: Search for `sleep` calls in the integration test suite. Any test that uses a fixed sleep to wait for async work is vulnerable to the same issue.
2. **Extract the helper**: Put `waitForCondition` in a shared test utilities module so all integration tests can use it consistently.
3. **Consider test timeouts**: Set a per-test timeout (e.g., `jest.setTimeout(30000)`) for integration tests that involve async job processing.
4. **Don't revert the CI runner change**: The 2-core machines exposed a pre-existing fragility. Going back to 4-core would mask the problem, and it would resurface any time the environment gets slightly slower.
