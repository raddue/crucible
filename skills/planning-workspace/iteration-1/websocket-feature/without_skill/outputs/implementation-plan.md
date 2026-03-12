# Implementation Plan: WebSocket Support for Real-Time Notifications

## 1. Overview

Add WebSocket support to the existing Express API so that authenticated clients can subscribe to granular, resource-level events (e.g., `order:123:status`) and receive real-time push notifications when those resources change. The solution must scale horizontally across multiple server instances using PostgreSQL LISTEN/NOTIFY as the pub/sub backbone.

---

## 2. Goals and Non-Goals

### Goals
- Clients can open a persistent WebSocket connection and subscribe to one or more topic strings (e.g., `order:123:status`, `user:456:messages`).
- When a relevant mutation occurs (via REST endpoint, background job, or database trigger), every subscribed client receives the event within milliseconds.
- The system works correctly when the API is scaled to multiple processes or containers.
- Connections are authenticated using the same auth mechanism as the REST API.
- Graceful handling of connection drops, reconnects, and back-pressure.

### Non-Goals
- Full-duplex RPC over WebSocket (this is notification-only; mutations stay on REST).
- Browser push notifications or SSE (may be added later).
- Message persistence / guaranteed delivery (first iteration is best-effort).

---

## 3. Technical Design

### 3.1 Library Choice

| Concern | Choice | Rationale |
|---------|--------|-----------|
| WebSocket server | **ws** (v8+) | Lightweight, production-proven, works directly with Node `http.Server`. No Socket.IO overhead needed since we are not targeting legacy browsers. |
| Pub/Sub backbone | **PostgreSQL LISTEN/NOTIFY** | Already in the stack; avoids adding Redis. Payloads up to 8 KB are sufficient for notification envelopes. |
| Schema validation | **zod** | Validate inbound subscribe/unsubscribe messages. |

### 3.2 Architecture Diagram

```
Client A ──ws──┐                        ┌── Process 1 (Express + WS)
Client B ──ws──┤  load balancer (sticky) │      ↕ pg LISTEN/NOTIFY
Client C ──ws──┘                        └── Process 2 (Express + WS)
                                               ↕
                                          PostgreSQL
```

Each API process:
1. Attaches a `ws.WebSocketServer` to the existing `http.Server`.
2. Maintains an in-memory map of `topic -> Set<WebSocket>`.
3. Opens a dedicated PostgreSQL connection that issues `LISTEN events` once.
4. On receiving a PG notification, fans out to locally-subscribed sockets.

### 3.3 Topic Format Convention

Topics follow the pattern `<resource>:<id>:<aspect>`:

```
order:123:status      -- status changes on order 123
order:123:*           -- all events on order 123
user:456:messages     -- new messages for user 456
```

Wildcard matching is handled in the fan-out logic using a simple prefix match (e.g., `order:123:*` matches any topic starting with `order:123:`).

### 3.4 Wire Protocol (Client <-> Server)

All messages are JSON over the WebSocket text frame.

**Client -> Server:**

```jsonc
// Subscribe
{ "type": "subscribe", "topics": ["order:123:status"] }

// Unsubscribe
{ "type": "unsubscribe", "topics": ["order:123:status"] }

// Ping (keepalive)
{ "type": "ping" }
```

**Server -> Client:**

```jsonc
// Event notification
{
  "type": "event",
  "topic": "order:123:status",
  "payload": { "status": "shipped", "updatedAt": "2026-03-11T10:00:00Z" },
  "timestamp": "2026-03-11T10:00:00.123Z"
}

// Subscription acknowledgement
{ "type": "subscribed", "topics": ["order:123:status"] }

// Error
{ "type": "error", "message": "Invalid topic format" }

// Pong
{ "type": "pong" }
```

### 3.5 Authentication

WebSocket connections are authenticated during the HTTP upgrade handshake, before the connection is promoted:

1. Extract the JWT from the `Authorization` header or the `token` query parameter.
2. Verify the token using the same middleware/logic used by the REST routes.
3. Reject the upgrade with HTTP 401 if authentication fails.
4. Attach the decoded user context to the socket instance for later authorization checks.

### 3.6 Authorization

When a client subscribes to a topic, the server checks whether the authenticated user has read access to the referenced resource. For example, subscribing to `order:123:status` requires that the user owns order 123 or has an admin role. This reuses the existing authorization logic in the route layer.

### 3.7 PostgreSQL LISTEN/NOTIFY Integration

**Dedicated listener connection:**
A single long-lived PG connection per process listens on a channel called `events`. This connection is separate from the query pool to avoid blocking or being recycled.

**Publishing events (NOTIFY):**
Mutations that should trigger notifications call a helper function that issues:

```sql
SELECT pg_notify('events', '{"topic":"order:123:status","payload":{"status":"shipped"}}');
```

This can be called:
- Inline within route handlers after a successful mutation.
- Inside a PostgreSQL trigger/function for database-level changes.
- From background job workers.

**Receiving events:**
The listener connection receives the notification, parses the JSON payload, and fans out to all locally-subscribed WebSocket clients whose topic list matches.

### 3.8 Connection Lifecycle and Health

| Concern | Strategy |
|---------|----------|
| Keepalive | Server sends WebSocket ping frames every 30 seconds. Clients that do not respond with pong within 10 seconds are terminated. |
| Reconnection | Client-side responsibility. Server is stateless; clients re-subscribe on reconnect. |
| Back-pressure | If a socket's `bufferedAmount` exceeds a threshold (e.g., 1 MB), the server closes that socket to protect the process. |
| Max subscriptions | Each connection is limited to 50 active topic subscriptions to prevent abuse. |
| Max connections per user | Configurable limit (default: 5) enforced during upgrade. |

### 3.9 Scaling Considerations

- **PostgreSQL LISTEN/NOTIFY** delivers to every listening connection across all processes, so horizontal scaling works without additional infrastructure.
- **Payload size limit:** PG NOTIFY payloads are limited to ~8 KB. For larger payloads, the notification contains only the topic and resource ID; the client fetches full data via REST.
- **If PG pub/sub becomes a bottleneck** (thousands of notifications/sec), the design can be swapped to Redis pub/sub by changing only the `PubSubAdapter` layer (see file structure below).

---

## 4. File Structure and Changes

### 4.1 New Files

```
src/
  websocket/
    index.ts                  -- Public API: attachWebSocketServer()
    WebSocketManager.ts       -- Core class: upgrade handling, subscription map, fan-out
    pgListener.ts             -- Dedicated PG LISTEN connection management
    pubsubAdapter.ts          -- Interface abstracting pub/sub (PG impl now, Redis later)
    messageSchema.ts          -- Zod schemas for inbound/outbound messages
    authorize.ts              -- Per-topic authorization checks
    constants.ts              -- Config: ping interval, max subscriptions, etc.
    __tests__/
      WebSocketManager.test.ts
      pgListener.test.ts
      messageSchema.test.ts
      integration.test.ts     -- End-to-end with real PG + WS client
```

### 4.2 Modified Files

| File | Change |
|------|--------|
| `src/server.ts` | Import `attachWebSocketServer` and call it with the `http.Server` instance after Express setup. |
| `src/routes/*.ts` (mutation routes) | After successful mutations, call `publishEvent(topic, payload)` to issue PG NOTIFY. |
| `package.json` | Add `ws` and `@types/ws` dependencies. Add `zod` if not already present. |
| Database migrations | Add a helper SQL function `notify_event(topic, payload)` for optional use in triggers. |

### 4.3 Database Migration

```sql
-- migrations/XXXX_add_notify_event_function.sql

CREATE OR REPLACE FUNCTION notify_event(topic TEXT, payload JSONB)
RETURNS VOID AS $$
BEGIN
  PERFORM pg_notify('events', json_build_object(
    'topic', topic,
    'payload', payload
  )::text);
END;
$$ LANGUAGE plpgsql;
```

---

## 5. Implementation Steps

### Phase 1: Core WebSocket Infrastructure (Estimated: 1-2 days)

1. **Install dependencies:** `ws`, `@types/ws`, and `zod` (if missing).
2. **Create `src/websocket/messageSchema.ts`:** Define Zod schemas for subscribe, unsubscribe, ping messages and the outbound event/error/subscribed/pong messages.
3. **Create `src/websocket/constants.ts`:** Ping interval, pong timeout, max subscriptions per connection, max connections per user, max buffered amount.
4. **Create `src/websocket/WebSocketManager.ts`:**
   - Accept an `http.Server` and attach a `ws.WebSocketServer` with `noServer: true`.
   - Handle the `upgrade` event: authenticate the request, then complete the upgrade.
   - On new connection: set up ping/pong, message parsing, subscription tracking.
   - Maintain `Map<string, Set<WebSocket>>` for topic-to-clients mapping.
   - Implement `broadcast(topic, payload)` that iterates matching subscriptions and sends.
   - Implement wildcard matching for topics ending in `:*`.
5. **Create `src/websocket/index.ts`:** Export `attachWebSocketServer(server, options)` as the public entry point.
6. **Modify `src/server.ts`:** Call `attachWebSocketServer` after creating the HTTP server.
7. **Write unit tests** for `WebSocketManager` (mock `ws` and PG).

### Phase 2: PostgreSQL Pub/Sub (Estimated: 1 day)

8. **Create `src/websocket/pubsubAdapter.ts`:** Define a `PubSubAdapter` interface with `publish(topic, payload)` and `subscribe(callback)` methods. Implement `PgPubSubAdapter`.
9. **Create `src/websocket/pgListener.ts`:**
   - Open a dedicated PG connection (not from the pool).
   - Issue `LISTEN events`.
   - On notification, parse JSON and invoke the callback registered by `WebSocketManager`.
   - Handle disconnection with exponential-backoff reconnect.
10. **Wire `PgPubSubAdapter` into `WebSocketManager`:** On `broadcast`, call the adapter's publish. On adapter notification, call local fan-out.
11. **Create database migration** for the `notify_event` helper function.
12. **Write unit tests** for `pgListener` (mock `pg` client).

### Phase 3: Authorization and Route Integration (Estimated: 1-2 days)

13. **Create `src/websocket/authorize.ts`:**
    - Given a user context and a topic string, determine if the user has read access.
    - Reuse existing service-layer authorization logic (e.g., `OrderService.canView(userId, orderId)`).
    - Return a boolean or throw an authorization error.
14. **Integrate authorization into `WebSocketManager`:** Before adding a subscription, call `authorize`. Send an error frame if denied.
15. **Modify mutation routes** (e.g., `src/routes/orders.ts`):
    - After a successful status update, call `publishEvent('order:123:status', { status: newStatus })`.
    - Keep this lightweight -- a single function call, fire-and-forget.
16. **Write tests** for authorization logic and route-level event publishing.

### Phase 4: Testing and Hardening (Estimated: 1 day)

17. **Write integration test (`integration.test.ts`):**
    - Start a real Express server with WebSocket support and a test PG database.
    - Connect a WS client, authenticate, subscribe to a topic.
    - Trigger a mutation via REST.
    - Assert the WS client receives the expected event.
    - Test cross-process delivery (two WS server instances, one PG database).
18. **Load test:** Use a tool like `ws-benchmark` or `artillery` to validate behavior under connection volume (target: 1,000 concurrent connections per process).
19. **Add graceful shutdown:** On `SIGTERM`, close all WebSocket connections with code 1001 (Going Away) and close the PG listener connection.
20. **Add monitoring:** Log connection count, subscription count, and notification throughput to existing logging/metrics infrastructure.

---

## 6. Key API Surface

### `attachWebSocketServer(server: http.Server, options: WebSocketOptions): WebSocketManager`

Called once in `src/server.ts`. Returns the manager instance for use in route handlers.

### `WebSocketManager.publish(topic: string, payload: object): Promise<void>`

Called from route handlers or services to broadcast an event. Internally issues `pg_notify`.

### Example Route Integration

```typescript
// In src/routes/orders.ts
router.patch('/:id/status', auth, async (req, res) => {
  const order = await orderService.updateStatus(req.params.id, req.body.status);

  // Fire-and-forget notification
  wsManager.publish(`order:${order.id}:status`, {
    status: order.status,
    updatedAt: order.updatedAt,
  });

  res.json(order);
});
```

---

## 7. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| PG NOTIFY 8 KB payload limit exceeded | Medium | Notification silently dropped | Validate payload size before NOTIFY; for large payloads, send only topic + ID and let client fetch via REST. |
| PG listener connection drops silently | Low | Notifications stop for one process | Implement health-check pings on the listener connection; reconnect with exponential backoff; alert on prolonged disconnection. |
| Memory pressure from many connections | Medium | Process OOM | Enforce per-user connection limits; monitor `process.memoryUsage()`; set `maxPayload` on ws server. |
| Topic subscription abuse (fan-out amplification) | Low | CPU spike on broadcast | Cap subscriptions per connection; rate-limit subscribe messages; monitor fan-out ratio. |
| Sticky sessions not configured on load balancer | Medium | Frequent disconnects | Document LB requirements; alternatively, support long-polling fallback via Socket.IO adapter (future). |

---

## 8. Future Enhancements (Out of Scope)

- **Message persistence and replay:** Store events in a PG table; on reconnect, client sends `lastEventId` and receives missed events.
- **Redis pub/sub adapter:** Swap in when PG NOTIFY throughput becomes a bottleneck.
- **Server-Sent Events (SSE) fallback:** For environments where WebSocket is blocked.
- **Fine-grained rate limiting:** Per-topic publish rate limits.
- **Admin dashboard:** Real-time view of connected clients and active subscriptions.

---

## 9. Definition of Done

- [ ] WebSocket connections are authenticated during HTTP upgrade using existing JWT auth.
- [ ] Clients can subscribe/unsubscribe to topics and receive JSON event frames.
- [ ] Wildcard subscriptions (`resource:id:*`) work correctly.
- [ ] Authorization prevents users from subscribing to resources they cannot access.
- [ ] Events published from any API process are delivered to all matching subscribers across all processes.
- [ ] Unit tests cover message parsing, subscription management, authorization, and PG listener reconnection.
- [ ] Integration test demonstrates end-to-end flow: REST mutation triggers WS notification.
- [ ] Graceful shutdown closes all connections cleanly.
- [ ] No degradation to existing REST API performance.
