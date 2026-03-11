# Event Ticketing Platform — REST API Design

**Date:** 2026-03-11
**Status:** Draft
**Tech Stack:** Node.js + Express, PostgreSQL, serving web + mobile clients
**Constraint:** Up to 10,000 concurrent users during popular on-sales

---

## Phase 1: Context Gathering

### Understanding the Domain

The platform manages events (concerts, conferences, sports), venues with seating maps, ticket purchasing with seat selection, and waitlists. The API serves both web and mobile clients and must handle extreme concurrency during popular event on-sales (up to 10,000 concurrent users).

Key complexity drivers:
- **Seat selection is a contention hotspot** — many users competing for the same seats simultaneously
- **Venues and seating maps** are relatively static but complex (sections, rows, seats)
- **Waitlists** introduce asynchronous state transitions (waitlisted → offered → purchased/expired)
- **Two client types** (web + mobile) need consistent API contract

---

## Phase 2: Investigated Questions

### Design Dimension 1: Resource Modeling & URL Structure

**Hypothesis:** I expect a straightforward RESTful resource hierarchy: `/events`, `/venues`, `/tickets`, `/orders`, with nested resources for venue seating (`/venues/:id/sections/:id/seats`). Ticket purchasing will need a transactional resource (e.g., `/orders`) rather than a simple `POST /tickets`.

#### Investigation

**Codebase Scout:**
This is a greenfield API design — no existing codebase patterns to follow. The crucible project itself is a skill toolkit, not a ticketing application. We have full freedom in resource design.

**Domain Researcher:**
Three viable approaches for ticket-purchasing resource modeling:

1. **Cart-based model:** `/carts` → add items → `/orders` (checkout). Common in e-commerce. Adds complexity but supports multi-ticket purchases naturally.
2. **Reservation-based model:** `POST /reservations` (hold seats) → `POST /orders` (confirm + pay). Two-step process that separates seat-holding from payment. Industry standard for ticketing.
3. **Direct purchase model:** `POST /orders` with seat IDs in the body. Simplest, but conflates seat locking with payment in one request.

**Recommendation:** Reservation-based model. Ticketing platforms universally separate seat selection (hold) from purchase (payment). This matches user expectations (timer-based holds), reduces payment contention, and enables graceful timeout/release.

**Impact Analyst:**
- Reservation-based model requires a background job to expire stale reservations
- Adds a state machine: `held → confirmed → expired`
- More database writes per purchase flow, but reduces contention on the payment step

**Challenge:**
Solid recommendation. One blind spot: the reservation timeout mechanism needs careful design — if the expiry job is delayed, seats could be double-sold. Consider database-level TTL or `CHECK` constraints rather than relying solely on application-level cron.

**Surprises:** None — reservation model is standard. The challenger's point about timeout reliability is worth addressing in the concurrency section.

#### Decision: Reservation-Based Resource Model

**Core Resources:**

| Resource | URL | Description |
|----------|-----|-------------|
| Events | `/events` | Concerts, conferences, sports events |
| Venues | `/venues` | Physical locations with seating maps |
| Sections | `/venues/:venueId/sections` | Seating sections within a venue |
| Seats | `/venues/:venueId/sections/:sectionId/seats` | Individual seats |
| Reservations | `/events/:eventId/reservations` | Temporary seat holds (time-limited) |
| Orders | `/orders` | Confirmed purchases with payment |
| Tickets | `/orders/:orderId/tickets` | Issued tickets for an order |
| Waitlists | `/events/:eventId/waitlist` | Queue for sold-out events |

---

### Design Dimension 2: Concurrency Control for Seat Selection

**Hypothesis:** I expect optimistic locking with version columns will be insufficient at 10,000 concurrent users — the retry storm would be brutal. I suspect we need either PostgreSQL advisory locks or a queue-based approach where seat selection requests are serialized per event.

#### Investigation (Deep Dive)

**Codebase Scout:**
No existing concurrency patterns to reference (greenfield). PostgreSQL supports `SELECT ... FOR UPDATE SKIP LOCKED`, advisory locks, and serializable isolation — all viable primitives.

**Domain Researcher:**
Four approaches for preventing double-booking:

1. **Optimistic locking (version column):** Read seat version, attempt update with `WHERE version = X`. Fails on conflict, client retries. Simple but degrades under high contention — at 10,000 users competing for popular seats, retry storms can cascade.

2. **Pessimistic locking (`SELECT FOR UPDATE`):** Lock the seat row during the reservation transaction. Guarantees consistency but serializes all requests for the same seat — creates blocking under load.

3. **`SELECT FOR UPDATE SKIP LOCKED` with reservation table:** Attempt to insert into a `reservations` table with a unique constraint on `(event_id, seat_id)`. Failed inserts mean the seat is taken — no blocking, instant feedback. Combined with `SKIP LOCKED` for batch seat queries, this avoids lock contention entirely.

4. **Queue-based (Redis + worker):** Enqueue seat selection requests, process serially per event. Guarantees ordering but adds latency (queue delay) and infrastructure complexity (Redis).

| Approach | Throughput | Latency | Complexity | Data Integrity |
|----------|-----------|---------|-----------|---------------|
| Optimistic locking | Poor under contention | Variable (retries) | Low | Strong |
| `SELECT FOR UPDATE` | Moderate | High (blocking) | Low | Strong |
| Unique constraint + `SKIP LOCKED` | High | Low | Medium | Strong |
| Redis queue | High | Medium (queue delay) | High | Strong (with care) |

**Recommendation:** Unique constraint on `reservations(event_id, seat_id)` + `SKIP LOCKED` for availability queries. This is the sweet spot: PostgreSQL enforces uniqueness at the database level (impossible to double-book), `SKIP LOCKED` lets availability queries skip already-held seats without blocking, and no external infrastructure is needed.

**Impact Analyst:**
- Unique constraint approach requires careful handling of expired reservations — must `DELETE` expired holds before they block new reservations
- Background job or PostgreSQL `pg_cron` extension can handle expiration
- No impact on other systems since this is greenfield
- Reversibility: high — can switch to queue-based later if needed

**Challenge:**
The recommendation is solid for the reservation step. Blind spot: what about the "browse available seats" query? At 10,000 concurrent users, repeatedly querying seat availability could hammer the database. Consider caching the availability map with short TTL (1-2 seconds) or using a materialized view. The unique constraint handles writes, but reads need their own strategy.

**Surprises:** The challenger raised a good point about read pressure. I expected write contention to be the main concern, but at 10,000 users, the `GET /events/:id/seats?status=available` endpoint will be hit far more than the reservation endpoint. Reads need a caching layer.

#### Decision: Unique Constraint + SKIP LOCKED + Redis Read Cache

- **Write path:** `INSERT INTO reservations (event_id, seat_id, user_id, expires_at)` with `UNIQUE(event_id, seat_id)`. Conflict = seat taken. No locking needed.
- **Read path:** Cache seat availability in Redis with 1-2 second TTL. The map is a bitmap or sorted set per event. Cache miss → query with `SKIP LOCKED`.
- **Expiration:** `pg_cron` job every 30 seconds deletes reservations past `expires_at`. Application also checks expiry on read.
- **Reservation TTL:** 10 minutes (configurable per event).

---

### Design Dimension 3: Pagination Strategy

**Hypothesis:** For event listings, cursor-based pagination is likely better than offset-based because events are frequently added and the list changes. For venue seats, offset-based might be fine since seating maps are static.

#### Investigation (Quick Scan)

**Codebase Scout:**
No existing pagination patterns. Both approaches are viable with PostgreSQL.

**Domain Researcher:**

| Strategy | Best For | Drawback |
|----------|---------|----------|
| **Offset-based** (`?page=2&per_page=20`) | Static data, simple UIs, admin dashboards | Skips/duplicates when data changes between pages |
| **Cursor-based** (`?after=abc123&limit=20`) | Feeds, dynamic lists, infinite scroll | Can't jump to page N, slightly more complex |
| **Keyset** (`?after_date=2026-03-01&limit=20`) | Time-ordered data | Requires stable sort column |

**Recommendation:** Use cursor-based for dynamic lists (events, orders, waitlists) and offset-based for static/admin views (venue seats, sections). This hybrid approach matches the data characteristics of each endpoint.

**Surprises:** None — hypothesis confirmed. Hybrid approach is standard practice.

#### Decision: Hybrid Pagination

- **Cursor-based:** `/events`, `/orders`, `/waitlist` — data changes frequently, mobile apps use infinite scroll
- **Offset-based:** `/venues/:id/sections/:sectionId/seats` — seating maps are static, UIs need to show the full grid
- **Response envelope:**
```json
{
  "data": [...],
  "pagination": {
    "next_cursor": "eyJpZCI6MTAwfQ==",
    "has_more": true,
    "total": 5000
  }
}
```
- `total` is included for offset endpoints, omitted for cursor endpoints (expensive COUNT on large tables)

---

### Design Dimension 4: Error Response Format

**Hypothesis:** A consistent JSON error envelope with HTTP status code, application error code, human-readable message, and optional field-level validation errors. This is well-established practice with no real alternatives.

#### Investigation — Auto-Resolved

Only one viable path exists: consistent error response format with machine-readable codes. The debate is only about the exact shape. Since we're serving both web and mobile, the format needs to support field-level validation errors (for forms) and general errors.

**Decision:**

```json
{
  "error": {
    "code": "SEAT_ALREADY_RESERVED",
    "message": "Seat A-14 is no longer available. Please select a different seat.",
    "status": 409,
    "details": [
      {
        "field": "seat_id",
        "code": "CONFLICT",
        "message": "This seat was reserved by another user."
      }
    ],
    "request_id": "req_abc123"
  }
}
```

**HTTP Status Code Mapping:**

| Status | Usage |
|--------|-------|
| 200 | Success |
| 201 | Resource created (reservation, order) |
| 400 | Validation errors |
| 401 | Authentication required |
| 403 | Insufficient permissions |
| 404 | Resource not found |
| 409 | Conflict (seat taken, duplicate reservation) |
| 422 | Unprocessable (valid format but business rule violation) |
| 429 | Rate limited |
| 500 | Internal server error |

*Speak up if you disagree.*

---

### Design Dimension 5: High-Concurrency Strategy (10,000 Users)

**Hypothesis:** We'll need connection pooling (PgBouncer), Redis caching for hot data, rate limiting on the reservation endpoint, and possibly a queue for payment processing. The seat reservation unique-constraint approach (decided above) handles write contention, but the overall system needs broader scaling.

#### Investigation (Deep Dive)

**Codebase Scout:**
Greenfield — no existing scaling infrastructure. Node.js with Express is single-threaded per process but non-blocking, which suits I/O-heavy API workloads well. PM2 or cluster mode can utilize multiple cores.

**Domain Researcher:**
Key scaling strategies for a Node.js + PostgreSQL ticketing API:

1. **Connection pooling:** PostgreSQL default `max_connections = 100`. At 10,000 users, even with Node's non-blocking I/O, direct connections will exhaust the pool. PgBouncer in transaction mode is essential.

2. **Application-level caching (Redis):**
   - Event details (cache for 60s — events change rarely)
   - Seat availability maps (cache for 1-2s — changes frequently during on-sale)
   - Venue/section data (cache for hours — essentially static)

3. **Rate limiting:**
   - Global: 100 requests/second per user
   - Reservation endpoint: 5 requests/minute per user (prevent bot sniping)
   - Use Redis-backed sliding window rate limiter

4. **Queue-based payment processing:**
   - After reservation, payment can be processed asynchronously via Bull/BullMQ (Redis-backed)
   - User sees "processing payment..." rather than waiting for Stripe round-trip in the request
   - Webhook confirms payment, finalizes order

5. **Horizontal scaling:**
   - Node.js processes behind a load balancer (stateless API)
   - Redis for session/state coordination
   - Read replicas for PostgreSQL (event browsing hits replica, reservations hit primary)

**Impact Analyst:**
- PgBouncer: adds infrastructure but no application code changes
- Redis: new dependency, need Redis connection management in Express middleware
- Queue: adds BullMQ dependency, requires worker processes, monitoring dashboard
- Read replicas: requires connection routing logic in the data access layer

**Challenge:**
The combination is solid but may be over-engineered for launch. 10,000 concurrent users is significant but not extreme for a properly tuned Node.js + PostgreSQL setup. Consider: PgBouncer + Redis caching are essential. Rate limiting is essential. But the async payment queue and read replicas might be premature — start with synchronous payment, add the queue when latency data justifies it. YAGNI.

**Surprises:** The challenger's YAGNI call on async payment processing is fair. Stripe's API typically responds in 1-3 seconds — acceptable for a checkout flow. Queue adds operational complexity (dead letter handling, retry logic, webhook reconciliation). Start synchronous, add queue when data shows it's needed.

#### Decision: Tiered Scaling Strategy

**Launch (Day 1):**
- PgBouncer in transaction mode (pool size: 50)
- Redis for seat availability caching (1-2s TTL) and event data caching (60s TTL)
- Rate limiting via `express-rate-limit` with Redis store
- PM2 cluster mode (utilize all CPU cores)
- Synchronous Stripe payment in the order confirmation flow

**Phase 2 (when data justifies it):**
- BullMQ for async payment processing
- PostgreSQL read replica for browsing endpoints
- CDN for venue seating map SVGs/images

---

## Phase 3: Design Presentation

### API Endpoint Specification

#### Events

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/events` | List events (filterable by type, date, venue; cursor-paginated) |
| GET | `/events/:id` | Get event details including venue info |
| POST | `/events` | Create event (admin) |
| PATCH | `/events/:id` | Update event (admin) |
| DELETE | `/events/:id` | Cancel event (admin, soft-delete) |
| GET | `/events/:id/seats` | Get seat availability map for event |

#### Venues

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/venues` | List venues |
| GET | `/venues/:id` | Get venue details with section summary |
| POST | `/venues` | Create venue (admin) |
| GET | `/venues/:id/sections` | List sections with seat counts |
| GET | `/venues/:id/sections/:sectionId/seats` | List seats in section (offset-paginated) |

#### Reservations

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/events/:eventId/reservations` | Reserve seats (body: `{ seat_ids: [...] }`) |
| GET | `/reservations/:id` | Get reservation status + expiry time |
| DELETE | `/reservations/:id` | Release reservation (user cancels) |

**Reservation flow:**
1. `POST /events/:eventId/reservations` — attempts to hold seats. Returns `201` with reservation ID and expiry timestamp, or `409` if any seat is taken.
2. Client shows countdown timer based on `expires_at`.
3. User proceeds to payment → `POST /orders`.
4. If timer expires, background job deletes reservation, seats become available.

#### Orders

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/orders` | Create order from reservation (body: `{ reservation_id, payment_method_id }`) |
| GET | `/orders/:id` | Get order details with tickets |
| GET | `/orders` | List user's orders (cursor-paginated) |
| GET | `/orders/:id/tickets` | List tickets for order |
| GET | `/orders/:id/tickets/:ticketId` | Get individual ticket (with QR code data) |

#### Waitlist

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/events/:eventId/waitlist` | Join waitlist |
| GET | `/events/:eventId/waitlist/position` | Get user's position |
| DELETE | `/events/:eventId/waitlist` | Leave waitlist |

**Waitlist flow:**
1. When event sells out, `POST /events/:eventId/reservations` returns `410 Gone` with `waitlist_available: true`.
2. User joins waitlist via `POST /events/:eventId/waitlist`.
3. When seats are released (reservation expiry, order cancellation), waitlist entries are notified in FIFO order.
4. Notified user gets a time-limited reservation automatically created.

### Data Model (PostgreSQL)

```sql
-- Core tables
CREATE TABLE venues (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    address JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE sections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    venue_id UUID REFERENCES venues(id),
    name TEXT NOT NULL,  -- e.g., "Orchestra", "Balcony A"
    capacity INTEGER NOT NULL
);

CREATE TABLE seats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    section_id UUID REFERENCES sections(id),
    row_label TEXT NOT NULL,     -- e.g., "A", "B"
    seat_number INTEGER NOT NULL,
    seat_type TEXT DEFAULT 'standard',  -- standard, premium, accessible
    UNIQUE(section_id, row_label, seat_number)
);

CREATE TABLE events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    venue_id UUID REFERENCES venues(id),
    title TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('concert', 'conference', 'sports')),
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ,
    on_sale_at TIMESTAMPTZ NOT NULL,
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'on_sale', 'sold_out', 'cancelled', 'completed')),
    reservation_ttl_minutes INTEGER DEFAULT 10,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Reservation system (concurrency-safe)
CREATE TABLE reservations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID REFERENCES events(id),
    seat_id UUID REFERENCES seats(id),
    user_id UUID NOT NULL,
    status TEXT DEFAULT 'held' CHECK (status IN ('held', 'confirmed', 'expired')),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(event_id, seat_id)  -- Database-enforced uniqueness prevents double-booking
);

CREATE INDEX idx_reservations_expires ON reservations(expires_at) WHERE status = 'held';

CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    reservation_id UUID REFERENCES reservations(id),
    stripe_payment_intent_id TEXT,
    total_cents INTEGER NOT NULL,
    currency TEXT DEFAULT 'USD',
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'paid', 'refunded', 'failed')),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE tickets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID REFERENCES orders(id),
    event_id UUID REFERENCES events(id),
    seat_id UUID REFERENCES seats(id),
    qr_code_data TEXT NOT NULL,
    status TEXT DEFAULT 'valid' CHECK (status IN ('valid', 'used', 'cancelled')),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE waitlist_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID REFERENCES events(id),
    user_id UUID NOT NULL,
    position INTEGER NOT NULL,
    status TEXT DEFAULT 'waiting' CHECK (status IN ('waiting', 'offered', 'expired')),
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(event_id, user_id)
);
```

### Authentication & Authorization

- JWT-based authentication (access token + refresh token)
- Access token in `Authorization: Bearer <token>` header
- Role-based access: `user` (purchase tickets), `admin` (manage events/venues), `scanner` (validate tickets at door)
- Admin endpoints require `admin` role
- Users can only access their own orders, reservations, waitlist entries

### Request/Response Conventions

**Request headers:**
- `Authorization: Bearer <jwt>`
- `Content-Type: application/json`
- `X-Request-ID: <client-generated UUID>` (for idempotency and tracing)
- `Accept-Language: en-US` (for localized error messages)

**Success response envelope:**
```json
{
  "data": { ... },
  "meta": {
    "request_id": "req_abc123",
    "timestamp": "2026-03-11T10:00:00Z"
  }
}
```

**List response envelope:**
```json
{
  "data": [...],
  "pagination": {
    "next_cursor": "eyJpZCI6MTAwfQ==",
    "has_more": true
  },
  "meta": {
    "request_id": "req_abc123",
    "timestamp": "2026-03-11T10:00:00Z"
  }
}
```

**Idempotency:**
- `POST` endpoints accept `X-Idempotency-Key` header
- Critical for payment operations — prevents double-charging on network retries
- Server stores idempotency key → response mapping in Redis with 24h TTL

---

## Gap Scan

- [x] **Acceptance criteria** — API endpoints are fully specified with HTTP verbs, URLs, request/response shapes. Concurrency mechanism is concrete (unique constraint + SKIP LOCKED). Pagination strategy is defined per endpoint type.
- [x] **Testing strategy** — Unit tests for reservation logic (expiry, conflict handling). Integration tests for the full reservation → order flow. Load tests with k6 simulating 10,000 concurrent seat selection attempts. Contract tests for the API response shapes (web + mobile clients).
- [x] **Integration impact** — Stripe integration for payments (webhook for async confirmation). Redis for caching and rate limiting. PgBouncer for connection pooling.
- [x] **Failure modes:**
  - Stripe payment fails after reservation → reservation remains, user can retry within TTL
  - Redis cache unavailable → fall through to PostgreSQL (degraded performance, not failure)
  - PgBouncer pool exhaustion → 503 with retry-after header
  - Reservation expiry job delayed → stale reservations block seats temporarily, but unique constraint prevents double-booking
- [x] **Edge cases:**
  - User selects seats, another user reserves them before first user submits → `409 Conflict`
  - User's reservation expires during payment form fill → `410 Gone`, must re-reserve
  - Event cancelled with existing orders → batch refund process, tickets marked cancelled
  - Waitlist user doesn't claim offered seats → auto-expire, offer to next in queue
  - Concurrent waitlist offers when multiple seats release → FIFO ordering with `SELECT FOR UPDATE SKIP LOCKED` on waitlist entries
