# Quality Gate Review: Redis Caching Layer for REST API

## Design Under Review

Adding a caching layer to a REST API using Redis for: session data, query caches, rate limiting counters, and as the primary data store for user preferences. Architecture: single Redis instance, no replication. Cache invalidation strategy: clear everything on deploy.

---

## Round 1: Architectural Risk Assessment

### Finding 1.1 — CRITICAL: Redis as Primary Data Store for User Preferences

**Severity: Critical**

The design proposes using Redis as the *primary* data store for user preferences. Redis is an in-memory data store. By default, if the Redis process crashes or the host reboots, data can be lost depending on persistence configuration (RDB snapshots have gaps; AOF has trade-offs with performance). Using Redis as a primary store without a durable backing store means user preferences are at risk of permanent data loss.

**Recommendation:** User preferences must be persisted in a durable data store (e.g., PostgreSQL, MySQL, DynamoDB). Redis can serve as a read-through cache in front of that store, but it must not be the system of record for data users expect to be permanent.

---

### Finding 1.2 — CRITICAL: Single Instance with No Replication

**Severity: Critical**

A single Redis instance with no replication is a single point of failure (SPOF). If that instance goes down:
- All sessions are lost (users are logged out).
- Rate limiting stops working (potential abuse window, or — if the app hard-fails on Redis unavailability — full outage).
- Query caches disappear (sudden load spike on the database, risking cascading failure / "thundering herd").
- User preferences are inaccessible or lost (see Finding 1.1).

This architecture has zero fault tolerance. Any maintenance window, crash, or network partition takes out four distinct subsystems simultaneously.

**Recommendation:** At minimum, deploy a Redis replica (Redis Sentinel or Redis Cluster) for automatic failover. For the use cases described, a primary + replica + sentinel setup is the baseline. For production systems, consider Redis Cluster for horizontal scaling.

---

### Finding 1.3 — HIGH: "Clear Everything on Deploy" Invalidation Strategy

**Severity: High**

Flushing all caches on every deploy has multiple serious consequences:

1. **Session destruction:** Every deploy logs out every user. This is unacceptable for user experience in most applications.
2. **Thundering herd on the database:** Immediately after deploy, every request will be a cache miss. If the application has meaningful traffic, this can overwhelm the backing database, causing latency spikes or outages.
3. **Rate limiting reset:** All rate-limiting counters reset on deploy, meaning rate-limited or abusive clients get a fresh allowance on every deploy. If deploys happen frequently (CI/CD), rate limiting is effectively broken.
4. **Loss of user preferences:** Combined with Finding 1.1, every deploy permanently destroys user preferences.

**Recommendation:** Implement granular invalidation strategies per data type:
- **Sessions:** Do not invalidate on deploy. Use TTL-based expiry.
- **Query caches:** Use key-versioning (e.g., prefix keys with a schema version or content hash) or event-driven invalidation when underlying data changes.
- **Rate limiting counters:** Use TTL-based sliding windows; never bulk-clear.
- **User preferences:** Should not be in Redis as primary store (see 1.1), but if cached, invalidate individual keys on write.

---

### Finding 1.4 — HIGH: Mixing Disparate Workloads on a Single Redis Instance

**Severity: High**

The design co-locates four fundamentally different workloads on a single Redis instance:

| Workload | Access Pattern | Durability Need | Eviction Tolerance |
|---|---|---|---|
| Session data | Read-heavy, key-value | Medium (loss = logout) | Low |
| Query caches | Read-heavy, variable size | Low (rebuildable) | High |
| Rate limiting | Write-heavy, counters | Low (but resets enable abuse) | Low |
| User preferences | Read-heavy, key-value | **High** (user data) | **None** |

These workloads have conflicting requirements. For example:
- If Redis hits its `maxmemory` limit, the eviction policy (e.g., `allkeys-lru`) cannot distinguish between an expendable query cache entry and a critical user-preference record or an active session.
- Write-heavy rate-limiting counter updates can cause latency spikes for session reads during high-traffic periods.
- Large query cache values can crowd out small but critical session tokens.

**Recommendation:** Separate at minimum into two logical Redis instances:
1. **Ephemeral cache** (query caches) — with aggressive eviction (`allkeys-lru`), OK to lose.
2. **Stateful store** (sessions, rate limiting) — with `noeviction` or `volatile-lru`, sized appropriately.
User preferences should not be in Redis at all as a primary store.

---

## Round 2: Operational and Production Readiness

### Finding 2.1 — MEDIUM: No Memory Planning or Eviction Policy Specified

**Severity: Medium**

The design does not mention `maxmemory` configuration or eviction policy. Without explicit memory limits, Redis will consume memory until the host runs out, at which point the OOM killer may terminate it (see Finding 1.2 — no replication means this is an outage). Without an eviction policy, behavior at memory pressure is undefined from the application's perspective.

**Recommendation:** Define `maxmemory` based on expected dataset size with headroom. Choose an eviction policy that matches the workload (which reinforces the need to separate workloads per Finding 1.4).

---

### Finding 2.2 — MEDIUM: No TTL Strategy Defined

**Severity: Medium**

The design does not mention TTLs for any of the cached data types. Without TTLs:
- Sessions live forever (security risk — stale sessions never expire).
- Query caches grow unboundedly until eviction or flush.
- Rate limiting counters have no defined window (are they per-minute? per-hour? per-day?).

**Recommendation:** Define explicit TTLs for each data type:
- Sessions: e.g., 30 minutes sliding, 24 hours absolute max.
- Query caches: seconds to minutes depending on data freshness requirements.
- Rate limiting: must match the rate-limit window (e.g., 60 seconds for a per-minute limit).

---

### Finding 2.3 — MEDIUM: No Monitoring or Alerting Mentioned

**Severity: Medium**

Given that a single Redis instance underpins four critical subsystems, there is no mention of monitoring (memory usage, connection count, latency percentiles, eviction rate, persistence lag) or alerting (instance down, memory above threshold, replication lag if replication is added).

**Recommendation:** Instrument Redis with monitoring (Redis INFO metrics exported to Prometheus/Datadog/CloudWatch) and set alerts for: instance availability, memory usage > 80%, eviction rate spikes, and command latency p99.

---

### Finding 2.4 — LOW: No Consideration of Connection Pooling or Client Configuration

**Severity: Low**

The design does not discuss how the API servers connect to Redis — connection pooling, timeout configuration, retry policies, or circuit-breaker patterns. Under the single-instance design, a Redis outage without circuit breakers will cause all API requests to hang on Redis connection timeouts, amplifying the outage.

**Recommendation:** Use a connection pool with sensible limits. Implement circuit breakers so that Redis unavailability degrades gracefully (e.g., sessions fall back to stateless JWTs, query caches are bypassed, rate limiting is relaxed or handled at the load balancer).

---

## Round 3: Security and Compliance Considerations

### Finding 3.1 — MEDIUM: Session Data in Redis Without Security Posture

**Severity: Medium**

Storing session data in Redis requires consideration of:
- **Encryption in transit:** Is TLS enabled between the API servers and Redis? By default, Redis does not use TLS.
- **Encryption at rest:** If Redis persistence is enabled (RDB/AOF), session tokens are written to disk in plaintext.
- **Access control:** Is `requirepass` or ACL configured? A default Redis installation has no authentication.
- **Network segmentation:** Is Redis on a private network, or exposed?

**Recommendation:** Enable TLS for Redis connections. Configure authentication (Redis 6+ ACLs preferred). Ensure Redis is not accessible from the public internet. Evaluate whether session data at rest requires encryption based on compliance requirements.

---

### Finding 3.2 — LOW: Rate Limiting Resilience to Manipulation

**Severity: Low**

If rate limiting is solely implemented via Redis counters and Redis goes down (or is flushed on deploy), there is no fallback. An attacker aware of the deploy schedule could time attacks to coincide with deployments when rate limits reset.

**Recommendation:** Implement a secondary rate-limiting mechanism at the infrastructure layer (e.g., load balancer or API gateway rate limiting) that does not depend on Redis.

---

## Summary of Findings

| # | Finding | Severity | Category |
|---|---|---|---|
| 1.1 | Redis as primary store for user preferences — data loss risk | Critical | Architecture |
| 1.2 | Single instance, no replication — single point of failure | Critical | Architecture |
| 1.3 | "Clear everything on deploy" — destroys sessions, enables abuse, thundering herd | High | Architecture |
| 1.4 | Mixed workloads with conflicting requirements on one instance | High | Architecture |
| 2.1 | No memory planning or eviction policy | Medium | Operations |
| 2.2 | No TTL strategy | Medium | Operations |
| 2.3 | No monitoring or alerting | Medium | Operations |
| 2.4 | No connection pooling or graceful degradation | Low | Operations |
| 3.1 | No security posture for session data in Redis | Medium | Security |
| 3.2 | Rate limiting has no fallback | Low | Security |

## Verdict: FAIL

This design has **2 critical** and **2 high-severity** issues that must be resolved before implementation. The core problems are:

1. **Using Redis as a primary data store** for data that must be durable (user preferences).
2. **Single point of failure** architecture with no redundancy.
3. **Destructive cache invalidation** strategy that breaks sessions, rate limiting, and could cause cascading database failures.
4. **Workload mixing** that prevents correct eviction and resource management.

The design needs significant revision across architecture, operations, and security before it is ready for implementation.
