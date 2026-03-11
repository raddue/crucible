# Design Review: Notification Service

## Overall Impression

The design covers the basic requirements — event consumption, preference lookup, multi-channel dispatch, and audit logging. However, there are several concerns about how this will scale from 10k to 1M events/day, and some gaps in reliability.

## Concerns

### Scaling: Single Instance / Single Partition Won't Scale

The design specifies a single `NotificationRouter` instance consuming from a single Kafka partition. Kafka's parallelism model is based on partitions — one consumer per partition. With a single partition, you cannot add more consumers to share the load. You're limited to vertical scaling ("scale up"), which has hard limits and is expensive.

At 1M events/day (~12 events/second average, but likely bursty), you'll probably be fine initially, but you're designing yourself into a corner. You should use multiple partitions from the start (e.g., partition by user_id) and run multiple consumer instances in a consumer group. This is how Kafka is meant to be used.

### No Retries or Dead-Letter Queue

If a channel fails (SES is down, Twilio returns an error), you log the error and move on. The notification is permanently lost. This is a poor user experience — a user who should have received an SMS about a critical event simply never gets it.

You need at minimum:
- Retry with exponential backoff for transient failures
- A dead-letter queue or table for messages that fail after all retries
- Alerting on dead-letter queue growth

### Synchronous Fan-Out

All three channel handlers (email, push, SMS) run as function calls within the same NotificationRouter process. This means:
- If Twilio has high latency, it blocks email and push processing for subsequent events
- A crash in any handler could bring down the entire service
- You can't scale channels independently

Consider dispatching to separate channel-specific queues or workers. This also lets you apply channel-specific rate limiting and retry policies.

### Rate Limiting for External Providers

SES, Firebase, and Twilio all have rate limits. At 1M events/day, if even a fraction of users have all three channels enabled, you could hit provider throttling. The design doesn't mention any rate limiting or backpressure mechanism.

You should add rate limiting per provider and handle throttling responses (HTTP 429) with appropriate backoff.

### Data Model Gaps

- The `notifications_sent` table doesn't track delivery status — just that it was sent. You won't know if notifications actually reached users.
- No index mentioned on `notifications_sent` for querying by user_id or event_type, which will matter at scale.
- `user_preferences` is simple boolean flags — no way to set quiet hours, frequency caps, or per-event-type preferences. This may be fine for v1 but will likely need to evolve quickly.

### Missing Idempotency

If the consumer crashes after sending a notification but before committing the Kafka offset, the event will be reprocessed and the user will receive duplicate notifications. You need idempotency keys (e.g., based on event ID + channel) to deduplicate.

## Summary

The core architecture is reasonable for a quick v1 at 10k events/day, but the design has fundamental scaling and reliability issues that need to be addressed before you can grow to 1M events/day. The single-partition/single-instance constraint and the lack of retries are the most pressing concerns. I'd recommend redesigning with multiple partitions, independent channel workers, retry logic, and rate limiting before building this out.
