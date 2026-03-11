I'm using the innovate skill to explore potential improvements.

I've reviewed the Batch Invoice Processing design doc in its entirety. The architecture is solid for the core happy path: CSV upload, validation, persistence, nightly Stripe batch. But there is a meaningful operational gap that will bite this team hard once they're in production with 200 invoices/day.

## The Single Best Addition

**Add an idempotency layer to the InvoiceBatcher using a `batch_run_id` and per-invoice `payment_idempotency_key` derived from a deterministic hash of `(po_number, amount, vendor_email, due_date)`.**

Before the nightly cron sends each invoice to Stripe, it should check the `payment_results` table for a matching idempotency key from a previous run. Stripe payment intents should also receive this key via Stripe's built-in `idempotencyKey` parameter. The `batch_run_id` (a UUID generated at the start of each nightly run) gets stamped on every `payment_results` row, enabling operators to reason about which invoices were processed in which run.

This is not generic "error handling." It is a specific, concrete mechanism: a deterministic hash that flows from your CSV data through to Stripe's API, making the entire pipeline safely re-runnable.

## Why This Over Alternatives

**Runner-up: Real-time webhook processing instead of nightly batch.** Webhooks would give faster feedback but would require a publicly reachable endpoint, webhook signature verification, and a state machine for payment intent lifecycle. That blows past the 6-week/2-person constraint. The idempotency layer keeps the existing batch architecture and adds safety without architectural disruption.

**Runner-up: A dead-letter queue for failed invoices.** Useful, but it only addresses post-failure triage. The idempotency layer prevents the most damaging failure mode (duplicate payments) from occurring at all, which is strictly higher priority.

## Impact

Without this, a crashed nightly job that restarts (or a manual re-run after a partial failure) will send duplicate payment intents to Stripe for invoices that already succeeded. With 200 invoices/day and real money flowing, even one duplicate payment erodes trust with vendors and creates accounting reconciliation nightmares. This addition makes the batch job safely re-runnable, which means operators can confidently retry after failures, partial runs are resumable, and the system is correct by construction rather than by hope.

## Cost

Approximately 1-2 days of additional work. The implementation involves adding a `payment_idempotency_key` column to the `invoices` table (computed at CSV parse time), a `batch_run_id` column to `payment_results`, a pre-send check in `InvoiceBatcher`, and passing the key to Stripe's API (which already supports it natively). No new infrastructure, no new dependencies. The main complexity is writing tests that simulate partial batch failures and verify no duplicates on retry.
