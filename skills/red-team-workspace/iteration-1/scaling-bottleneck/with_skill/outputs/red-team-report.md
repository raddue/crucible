I'm using the red-team skill to adversarially review this artifact.

---

# Red Team Report: Notification Service Design

## Artifact Under Review

A design document for an event-driven notification system that fans out user notifications (email, push, SMS) via a single `NotificationRouter` service consuming from Kafka. Expected growth from ~10k events/day to ~1M events/day within 6 months.

---

## Fatal Challenges

### F1. Single Kafka Partition + Single Consumer Instance Cannot Scale to 1M Events/Day

**What breaks:** The design specifies "a single instance consuming from a single Kafka partition." Kafka's unit of parallelism is the partition — a single partition can only be consumed by one consumer in a consumer group. This means:

- **At 10k events/day** (~0.12 events/second): trivially handled.
- **At 1M events/day** (~11.6 events/second): still manageable as raw event ingestion, BUT each event triggers up to 3 synchronous external API calls (SES, Firebase, Twilio). At ~200-500ms per API call, processing one event takes 600-1500ms. A single-threaded, single-instance processor handles ~0.7-1.7 events/second of actual throughput. **The system falls behind at roughly 60k-150k events/day** — well short of the 1M target.

The design's scaling strategy is to "scale up the instance" (vertical scaling). This does not help because:
1. The bottleneck is I/O wait on external API calls, not CPU or memory.
2. A single Kafka partition cannot be split across consumers.
3. Vertical scaling has a hard ceiling and doesn't address the fundamental architectural constraint.

**Evidence:** From the design: "The NotificationRouter runs as a single instance consuming from a single Kafka partition. If load increases, we plan to 'scale up' the instance."

**Impact:** The notification system will fall behind within weeks of reaching moderate load, creating an ever-growing backlog. Users will receive notifications hours or days late, or not at all.

**Proposed fix:** Use multiple Kafka partitions (e.g., 12-24) with a consumer group:

- Partition the `events` topic by `user_id` to ensure per-user ordering.
- Run multiple NotificationRouter instances in a consumer group, with each instance consuming from one or more partitions.
- This allows horizontal scaling: add instances as load grows.
- At 12 partitions with 12 consumers, throughput scales to ~12x a single instance.

### F2. No Retry Mechanism or Dead-Letter Queue for Failed Notifications

**What breaks:** The design states: "If a channel fails, we log the error and move on to the next event. No retries." This means:

- A transient SES outage (which AWS documents as expected) permanently drops all email notifications during the outage window.
- A Twilio rate limit response (HTTP 429) drops the SMS and never re-attempts.
- A Firebase token rotation that causes a brief authentication failure drops all push notifications.

At 1M events/day with ~3 channels per event, even a 0.1% transient failure rate means ~3,000 lost notifications per day. During a provider outage lasting minutes, thousands of notifications are permanently lost.

There is no dead-letter queue (DLQ), so failed notifications cannot be reprocessed, audited, or alerted on. The only record is a log line, which is not actionable at scale.

**Evidence:** From the design: "If a channel fails, we log the error and move on to the next event. No retries."

**Impact:** Users silently miss critical notifications. There is no recovery mechanism. At scale, this will be a constant source of data loss.

**Proposed fix:**
1. Add per-channel retry with exponential backoff (3 attempts, 1s/2s/4s).
2. After max retries, publish the failed notification to a dead-letter topic (`notifications-dlq`).
3. Build a DLQ consumer that alerts on failures and supports manual or automated reprocessing.
4. Track delivery status in the `notifications_sent` table (pending/delivered/failed/retrying).

---

## Significant Challenges

### S1. Synchronous Fan-Out Within a Single Process Creates Cascading Failure Risk

**What the risk is:** Each channel handler (SES, Firebase, Twilio) is "a function call within the NotificationRouter process." This means:

1. **Serial execution per event:** If the user has all three channels enabled, the system calls SES, waits for response, calls Firebase, waits, calls Twilio, waits. Total time per event: sum of all three latencies (~600-1500ms).
2. **Cascading failure:** If Twilio's API slows down (e.g., 10-second response times), it blocks the entire pipeline — email and push notifications back up behind slow SMS calls, even though SES and Firebase are healthy.
3. **No isolation:** A crash in one channel handler (e.g., an unhandled exception from the Firebase SDK) can crash the entire NotificationRouter process, halting all notification delivery.

**Likelihood:** High. External API latency spikes are routine. Provider-specific outages are common (multiple times per year for each provider).

**Impact:** A single slow or failing provider degrades or halts all notification delivery across all channels.

**Proposed fix:** Decouple channels into separate consumers or async workers:

- Use separate Kafka topics per channel: `notifications-email`, `notifications-push`, `notifications-sms`.
- The NotificationRouter becomes a pure fan-out service: it reads from `events`, looks up preferences, and publishes to the appropriate channel topics.
- Each channel has its own consumer(s) with independent scaling, retries, and circuit breakers.
- This isolates failures: a Twilio outage only affects SMS, not email or push.

### S2. No Rate Limiting or Backpressure for External Provider APIs

**What the risk is:** At 1M events/day (~11.6 events/second), with up to 3 channels per event, the system may generate ~35 API calls/second to external providers. Each provider has rate limits:

- **AWS SES:** 14 emails/second default (can be increased but requires approval).
- **Twilio SMS:** Varies by number type; standard long codes support 1 SMS/second per number.
- **Firebase Cloud Messaging:** 500 messages/second (generous, but batch-sending is recommended).

Without rate limiting, the system will exceed provider limits, triggering throttling (HTTP 429), temporary bans, or dropped messages. Combined with the "no retries" policy, throttled messages are permanently lost.

**Likelihood:** Near-certain at 1M events/day.

**Impact:** Provider throttling leads to silent message loss at scale.

**Proposed fix:**
- Implement per-provider rate limiters (token bucket or sliding window) in front of each channel handler.
- Use the provider's batch APIs where available (SES `SendBulkEmail`, FCM batch send).
- Implement backpressure: when a rate limit is hit, slow the consumer's commit offset rather than dropping messages.

### S3. `notifications_sent` Audit Table Will Become a Write Bottleneck

**What the risk is:** At 1M events/day with ~2-3 notifications per event, the `notifications_sent` table will receive ~2-3 million inserts per day. The table has no mentioned indexes beyond the implicit PK, no partitioning strategy, and no archival plan.

Within months, the table will contain hundreds of millions of rows. Queries for auditing (e.g., "show me all notifications for user X in the last 30 days") will degrade. The write volume (~35 inserts/second sustained) will compete with the preference lookups on the same PostgreSQL instance.

**Likelihood:** Medium-high, depending on PostgreSQL instance sizing.

**Impact:** Database performance degradation affecting both notification delivery (preference lookups) and audit queries.

**Proposed fix:**
- Partition the `notifications_sent` table by date (e.g., monthly range partitions).
- Add an index on `(user_id, sent_at)` for audit queries.
- Consider writing audit logs asynchronously (publish to a separate topic and have a dedicated consumer write to the audit table) to decouple audit writes from the notification delivery hot path.
- Plan for archival: drop or move partitions older than the retention period.

---

## Minor Observations

- **No mention of idempotency.** If the consumer crashes after sending a notification but before committing the Kafka offset, the event will be reprocessed. Without idempotency keys, users may receive duplicate notifications. Non-blocking but worth noting.
- **User preference lookups are not cached.** At 1M events/day, that is ~11.6 PostgreSQL queries/second just for preference lookups. A simple in-memory cache with short TTL (e.g., 60 seconds) would reduce database load significantly.
- **No mention of notification content templates or localization.** The design only covers routing, not what is sent. This is presumably out of scope but should be documented.
- **The `user_preferences` table only supports boolean per-channel preferences.** There's no support for notification type filtering (e.g., "email me about billing but not marketing"), quiet hours, or frequency caps. This may be intentional for v1 but will be needed soon.

---

## Overall Assessment

- **Verdict:** Has fundamental issues that must be addressed before implementation
- **Confidence:** High. The single-partition bottleneck is a hard architectural constraint, not a theoretical concern — the math shows it fails at the stated growth target. The no-retry policy guarantees message loss at any meaningful scale. These are verified against the design's own stated requirements and growth projections.
- **Summary:** The design has a sound conceptual model (event-driven, fan-out to channels, audit trail), but its scaling architecture is fundamentally inadequate for the stated growth from 10k to 1M events/day. The single-partition/single-instance approach hits a hard wall at roughly 60k-150k events/day. Combined with no retries, no dead-letter queue, synchronous fan-out, and no rate limiting, this system will lose notifications silently and fall further behind as load grows. The core fan-out concept is right; the implementation architecture needs to be redesigned around horizontal scaling, channel isolation, and resilient delivery.
