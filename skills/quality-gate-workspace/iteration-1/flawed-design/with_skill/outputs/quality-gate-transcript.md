# Quality Gate Transcript: Redis Caching Layer Design Doc

**Artifact type:** design
**Artifact:** Design doc for adding a Redis caching layer to a REST API

**Original design:**
- Redis for session data, query caches, rate limiting counters, and as the primary data store for user preferences
- Single Redis instance with no replication
- Cache invalidation strategy: "clear everything on deploy"

---

## Round 1 — Fresh Devil's Advocate Review

### Fatal Challenges

**F1. Redis as primary data store for user preferences with no persistence guarantees or replication.**
Redis is an in-memory store. Using it as the *primary* data store (not a cache backed by a persistent database) for user preferences means any Redis crash, restart, or OOM event results in permanent data loss. A single instance with no replication means there is zero fault tolerance. If Redis goes down, user preferences are gone forever.
**Severity:** Fatal
**Fix:** User preferences must have a durable primary store (e.g., PostgreSQL). Redis can serve as a read-through cache in front of it.

**F2. Single Redis instance is a single point of failure for all critical subsystems.**
Sessions, rate limiting, query caches, and user preferences all depend on one Redis instance. If that instance fails: users are logged out (sessions lost), rate limiting stops working (potential abuse), and user preferences vanish. There is no failover.
**Severity:** Fatal
**Fix:** At minimum, deploy Redis Sentinel or a Redis Cluster with at least one replica. Separate concerns so session store and rate limiter are independent of user preferences store.

**F3. "Clear everything on deploy" invalidation destroys sessions, rate limits, and user preferences.**
Every deploy wipes all sessions (all users forcibly logged out), resets all rate limiting counters (allowing burst abuse immediately post-deploy), and destroys user preferences (since Redis is the primary store). In a continuous deployment environment, this is catastrophic.
**Severity:** Fatal
**Fix:** Implement per-key TTL-based expiration for query caches, preserve sessions and rate limiting state across deploys, and never destroy the primary data store on deploy.

### Significant Challenges

**S1. No separation of concerns — mixing volatile caches with stateful data in one instance.**
Query caches are ephemeral and can be evicted freely. Sessions and rate limiting counters are semi-durable state. User preferences are permanent state. Mixing all three in one Redis instance means eviction policies (e.g., `allkeys-lru`) will conflict: evicting a query cache entry is fine, evicting a user's preferences is data loss.
**Severity:** Significant
**Fix:** Use separate Redis databases or instances for volatile vs. stateful vs. persistent data, or move persistent data out of Redis entirely.

**S2. No cache invalidation strategy beyond "nuke from orbit."**
No mechanism for targeted cache invalidation when underlying data changes. Stale query cache results will be served until the next deploy.
**Severity:** Significant
**Fix:** Implement event-driven or write-through invalidation. At minimum, use TTLs on query cache keys.

**S3. No eviction policy specified.**
Without a configured `maxmemory-policy`, the default (`noeviction`) will cause write errors when memory is full, crashing rate limiting, session creation, and user preference writes simultaneously.
**Severity:** Significant
**Fix:** Define explicit eviction policy per data type. At minimum, configure `volatile-lru` with TTLs on cache keys.

**S4. Rate limiting counters reset on deploy.**
Creates a security vulnerability window after every deployment. Attackers can time attacks to deploy schedules.
**Severity:** Significant
**Fix:** Rate limiting state should persist across deploys.

### Minor Observations

- M1. No mention of Redis authentication or network security (binding, TLS, AUTH).
- M2. No mention of monitoring, alerting, or capacity planning.

### Round 1 Score

| Severity | Count | Weight | Subtotal |
|----------|-------|--------|----------|
| Fatal | 3 | 3 | 9 |
| Significant | 4 | 1 | 4 |
| **Total** | | | **13** |

### Fixes Applied After Round 1

1. User preferences moved to PostgreSQL as primary store; Redis used only as read-through cache.
2. Redis Sentinel deployed with at least one replica for high availability.
3. Cache invalidation revised: query caches use per-key TTLs (default 5 min). Sessions and rate limiting state preserved across deploys. Only query cache namespace flushed on deploy if needed.
4. Separated Redis logical databases: db0 for query caches (allkeys-lru), db1 for sessions (volatile-ttl), db2 for rate limiting (noeviction).
5. Eviction policy explicitly configured per logical database.
6. Rate limiting counters persist across deploys.
7. Write-through invalidation: on data mutation, corresponding cache keys invalidated.

---

## Round 2 — Fresh Devil's Advocate Review

### Fatal Challenges

None.

### Significant Challenges

**S1. Redis logical databases (SELECT) are not true isolation.**
Logical databases share the same memory pool, CPU, and persistence config. A memory spike in query caches (db0) can starve sessions (db1) and rate limiting (db2). `maxmemory-policy` is global, not per-database.
**Severity:** Significant
**Fix:** Use separate Redis instances for truly isolated failure domains, or accept the shared-resource risk with careful memory budgeting and monitoring at 70% capacity.

**S2. Redis Sentinel provides failover but not horizontal scaling.**
If query cache volume grows, a single-primary Sentinel setup becomes a bottleneck. No load spike strategy documented.
**Severity:** Significant
**Fix:** Document capacity limits. Specify migration path to Redis Cluster if throughput exceeds single-instance capacity. Add read replicas for cache reads.

**S3. Write-through invalidation mechanism unspecified.**
The design says cache keys are invalidated on mutation but doesn't specify synchronous vs. asynchronous. Async risks stale data; synchronous adds latency and coupling.
**Severity:** Significant
**Fix:** Specify the mechanism. For strong consistency: invalidate within the same transaction. For eventual consistency: use CDC with documented staleness bounds.

### Minor Observations

- M1. PostgreSQL connection pool configuration for user preferences not mentioned. Cache-miss path could exhaust DB connections under load.
- M2. No cache warming strategy after cold start or failover — thundering herd risk on database.

### Round 2 Score

| Severity | Count | Weight | Subtotal |
|----------|-------|--------|----------|
| Fatal | 0 | 3 | 0 |
| Significant | 3 | 1 | 3 |
| **Total** | | | **3** |

**Score comparison: 13 -> 3. Strictly lower. Progress — continuing.**

### Fixes Applied After Round 2

1. Separate Redis instances instead of logical databases: one for query caches (LRU eviction), one for sessions/rate-limiting.
2. Capacity limits documented: single-primary Sentinel for now, migration path to Redis Cluster at >50k ops/sec.
3. Cache invalidation mechanism specified: synchronous invalidation for user preferences via transactional outbox pattern. TTL-based expiration for query caches with optional explicit invalidation via application events.
4. Read replicas added for query cache reads.

---

## Round 3 — Fresh Devil's Advocate Review

### Fatal Challenges

None.

### Significant Challenges

**S1. Transactional outbox pattern adds complexity without specifying the outbox consumer.**
What processes the outbox? Polling worker? CDC connector? If the consumer falls behind or crashes, cache staleness grows unbounded.
**Severity:** Significant
**Fix:** Specify the outbox consumer implementation (e.g., Debezium CDC or polling worker with SLA alerting on lag) and define maximum acceptable staleness.

### Minor Observations

- M1. Separate Redis instances increase operational overhead (monitoring, upgrades, config). Acceptable trade-off for isolation; document in operational runbooks.
- M2. No mention of connection pooling to Redis instances from the application layer.

### Round 3 Score

| Severity | Count | Weight | Subtotal |
|----------|-------|--------|----------|
| Fatal | 0 | 3 | 0 |
| Significant | 1 | 1 | 1 |
| **Total** | | | **1** |

**Score comparison: 3 -> 1. Strictly lower. Progress — continuing.**

### Fixes Applied After Round 3

1. Outbox consumer specified: dedicated polling worker running every 500ms, reads pending invalidation events from outbox table, issues Redis DEL commands, marks events as processed.
2. Alerting configured if outbox lag exceeds 5 seconds.
3. Maximum acceptable staleness documented as 5 seconds.

---

## Round 4 — Fresh Devil's Advocate Review

### Fatal Challenges

None.

### Significant Challenges

None.

### Minor Observations

- M1. 500ms polling interval means ~250ms average invalidation latency. Acceptable for most REST API use cases; document as known trade-off.
- M2. Outbox worker should have idempotent processing on crash/restart. Redis DEL is naturally idempotent, so this is satisfied — worth explicitly stating.

### Round 4 Score

| Severity | Count | Weight | Subtotal |
|----------|-------|--------|----------|
| Fatal | 0 | 3 | 0 |
| Significant | 0 | 1 | 0 |
| **Total** | | | **0** |

**Score comparison: 1 -> 0. Strictly lower. No Fatal or Significant issues remain.**

---

## Final Disposition

**PASSED** — Quality gate approved after 4 rounds.

### Score Progression

| Round | Fatal | Significant | Weighted Score | Delta | Status |
|-------|-------|-------------|----------------|-------|--------|
| 1 | 3 | 4 | 13 | — | Issues found |
| 2 | 0 | 3 | 3 | -10 | Progress |
| 3 | 0 | 1 | 1 | -2 | Progress |
| 4 | 0 | 0 | 0 | -1 | Clean |

### Summary

The original design had three fatal flaws: using Redis as a primary data store without durability, running a single instance with no replication, and destroying all state on every deploy. Through four rounds of adversarial review and iterative revision, all issues were resolved. The final design uses PostgreSQL for durable user preferences, separate Redis instances for isolation, Redis Sentinel for high availability, TTL-based and event-driven cache invalidation, and a well-specified transactional outbox pattern for consistency.

Stagnation was never detected — each round showed strictly decreasing weighted scores.
