# Debug Transcript: Double Charges on Checkout

## User's Problem
Checkout process sometimes charges customers twice (~1 in 50 orders). User believes adding `redis.del(orderKey)` after payment writes will fix stale cache reads.

## Investigation

Before implementing the suggested fix, let me examine the evidence more closely.

**The log entries are the key clue:**

```
[2024-03-14 10:23:01] processPayment called orderId=12345 status=pending -> charge created ch_abc123
[2024-03-14 10:23:06] processPayment called orderId=12345 status=pending -> charge created ch_def456
```

Two things jump out:

1. **The 5-second gap matches the frontend retry timeout exactly.** The frontend retries on network timeout (5s). So the first call was made, 5 seconds passed without a response, the frontend retimed out and retried.

2. **Both calls saw `status=pending`.** This is critical. The second call checked the order status and it was still `pending` -- meaning the first call hadn't completed yet.

**Now let me trace through what actually happens:**

1. User clicks checkout. Frontend sends POST to `/checkout/:orderId`.
2. `processPayment` is called. It reads the order -- status is `pending`. Good.
3. It calls `stripe.charges.create()`. This is a network call to Stripe that usually takes <5s but sometimes takes longer.
4. **While waiting for Stripe to respond**, 5 seconds elapse. The frontend times out.
5. The frontend retries, sending another POST to `/checkout/:orderId`.
6. `processPayment` is called again. It reads the order -- **status is STILL `pending`** because the first call hasn't returned from Stripe yet to update the DB.
7. The `if (order.status === 'pending')` check passes. A second charge is created.
8. Eventually both Stripe calls return successfully. Two charges exist.

**This is a race condition, not a caching issue.**

## Why Cache Invalidation Won't Fix This

The user's suggested fix (`redis.del(orderKey)` after payment) would not help because:

- The cache is **correct**. When the retry arrives, the order status genuinely IS `pending` in both the cache AND the database. The first Stripe call hasn't returned yet, so no status update has occurred anywhere.
- Even if you deleted the cache and forced a DB read, the DB also shows `pending` because the first `processPayment` hasn't reached the `UPDATE orders SET status = 'paid'` line yet.
- Cache invalidation addresses stale data. This isn't stale data -- it's a race condition where two concurrent requests both see a legitimately `pending` status.

## Root Cause

The `processPayment` function has a classic **check-then-act race condition**:

1. Check: `if (order.status === 'pending')` -- not atomic with the act
2. Act: `stripe.charges.create(...)` -- slow external call
3. Update: `UPDATE orders SET status = 'paid'` -- only happens after Stripe returns

Between steps 1 and 3, any concurrent call will also pass the check. The 1-in-50 rate correlates with how often Stripe responses take longer than 5 seconds, triggering the frontend retry.

## Fix

There are several approaches, and they can be combined:

### Option 1: Stripe Idempotency Keys (Recommended - Primary Fix)

Stripe natively supports idempotency keys. Pass the orderId as the idempotency key so that duplicate charge requests for the same order are deduplicated by Stripe:

```javascript
async function processPayment(orderId, amount) {
  const order = await getOrder(orderId);
  if (order.status === 'pending') {
    const charge = await stripe.charges.create(
      { amount, currency: 'usd' },
      { idempotencyKey: `order_${orderId}` }  // Stripe deduplicates on this key
    );
    await db.query('UPDATE orders SET status = $1, charge_id = $2 WHERE id = $3',
      ['paid', charge.id, orderId]);
    await updateOrderCache(orderId);
    return { success: true, chargeId: charge.id };
  }
  return { success: false, reason: 'Order not in pending state' };
}
```

With this, even if two identical charge requests reach Stripe, the second one returns the same result as the first without creating a new charge.

### Option 2: Optimistic Locking on Order Status (Recommended - Secondary Fix)

Change the status to an intermediate state BEFORE calling Stripe, using an atomic DB update:

```javascript
async function processPayment(orderId, amount) {
  // Atomically claim this order for processing
  const result = await db.query(
    'UPDATE orders SET status = $1 WHERE id = $2 AND status = $3 RETURNING id',
    ['charging', orderId, 'pending']
  );

  if (result.rowCount === 0) {
    // Another request already claimed this order
    return { success: false, reason: 'Order not in pending state or already being processed' };
  }

  try {
    const charge = await stripe.charges.create(
      { amount, currency: 'usd' },
      { idempotencyKey: `order_${orderId}` }
    );
    await db.query('UPDATE orders SET status = $1, charge_id = $2 WHERE id = $3',
      ['paid', charge.id, orderId]);
    await updateOrderCache(orderId);
    return { success: true, chargeId: charge.id };
  } catch (err) {
    // Revert status if Stripe fails
    await db.query('UPDATE orders SET status = $1 WHERE id = $2', ['pending', orderId]);
    throw err;
  }
}
```

This uses the database as a lock. The `UPDATE ... WHERE status = 'pending'` is atomic -- only one concurrent request can succeed in changing the status from `pending` to `charging`. The second request will see `rowCount === 0` and bail out.

### Option 3: Increase Frontend Timeout or Add Response Status Polling

The 5-second frontend timeout is aggressive for a flow that includes an external payment API call. Consider:
- Increasing the timeout to 30s for payment endpoints
- Instead of retrying the payment, poll a `/checkout/:orderId/status` endpoint to check if the original request completed

## Recommended Approach

Use Options 1 + 2 together (belt and suspenders for payment processing):
- Idempotency keys protect against duplicate charges at the Stripe level
- Optimistic locking prevents the race condition at the application level
- Together they provide defense in depth for a critical financial operation

Option 3 is a good supplementary improvement but shouldn't be the sole fix.
