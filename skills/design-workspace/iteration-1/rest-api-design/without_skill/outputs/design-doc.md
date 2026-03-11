# REST API Design: Event Ticketing Platform

## Overview

This document describes the design for a REST API powering an event ticketing platform. The platform handles concerts, conferences, and sports events with venue seating maps, ticket purchasing with seat selection, and waitlists. The API serves both a web frontend and a mobile app, built with Node.js/Express and PostgreSQL, targeting up to 10,000 concurrent users during popular on-sales.

## Resource Modeling

The API is organized around the following core resources:

### Events
- `GET /api/v1/events` — List events (with filtering, sorting, pagination)
- `GET /api/v1/events/:id` — Get event details
- `POST /api/v1/events` — Create an event (admin)
- `PUT /api/v1/events/:id` — Update an event (admin)
- `DELETE /api/v1/events/:id` — Cancel/remove an event (admin)

### Venues
- `GET /api/v1/venues` — List venues
- `GET /api/v1/venues/:id` — Get venue details including seating map
- `POST /api/v1/venues` — Create a venue (admin)
- `PUT /api/v1/venues/:id` — Update a venue (admin)

### Seating Maps
- `GET /api/v1/events/:eventId/seating` — Get seating availability for an event
- `GET /api/v1/venues/:venueId/sections` — Get sections/zones of a venue
- `GET /api/v1/venues/:venueId/sections/:sectionId/seats` — Get individual seats in a section

### Tickets
- `POST /api/v1/events/:eventId/tickets` — Purchase tickets (creates order)
- `GET /api/v1/tickets/:id` — Get ticket details
- `GET /api/v1/users/:userId/tickets` — Get user's tickets
- `DELETE /api/v1/tickets/:id` — Cancel/refund a ticket

### Reservations (temporary seat holds)
- `POST /api/v1/events/:eventId/reservations` — Reserve seats temporarily
- `GET /api/v1/reservations/:id` — Check reservation status
- `DELETE /api/v1/reservations/:id` — Release reservation

### Waitlists
- `POST /api/v1/events/:eventId/waitlist` — Join the waitlist
- `GET /api/v1/events/:eventId/waitlist/position` — Check position (authenticated user)
- `DELETE /api/v1/events/:eventId/waitlist` — Leave the waitlist

### Orders
- `POST /api/v1/orders` — Create an order from reservations
- `GET /api/v1/orders/:id` — Get order details
- `GET /api/v1/users/:userId/orders` — List user's orders

### Users
- `POST /api/v1/auth/register` — Register
- `POST /api/v1/auth/login` — Login (returns JWT)
- `GET /api/v1/users/me` — Get current user profile
- `PUT /api/v1/users/me` — Update profile

## Pagination

For list endpoints, we'll use **cursor-based pagination**. This is better than offset-based for our use case because:

1. Events and tickets are frequently added/removed, making offset unreliable (items shift between pages).
2. Cursor-based pagination performs better at scale since it avoids `OFFSET` which forces the database to scan and discard rows.
3. It works well for infinite-scroll UIs on mobile.

**Request:**
```
GET /api/v1/events?cursor=eyJpZCI6MTIzfQ&limit=20&sort=date_asc
```

**Response:**
```json
{
  "data": [...],
  "pagination": {
    "next_cursor": "eyJpZCI6MTQ0fQ",
    "has_more": true,
    "limit": 20
  }
}
```

The cursor is a base64-encoded representation of the last item's sort key. The `limit` parameter defaults to 20, max 100.

For endpoints where total count matters (admin dashboards), we support an optional `include_count=true` query parameter that adds a `total_count` field but with a performance caveat noted in the docs.

## Error Response Format

All errors follow a consistent structure:

```json
{
  "error": {
    "code": "SEAT_ALREADY_RESERVED",
    "message": "The selected seat is no longer available.",
    "details": [
      {
        "field": "seat_id",
        "issue": "Seat A12 in Section 101 was reserved by another user."
      }
    ],
    "request_id": "req_abc123"
  }
}
```

### HTTP Status Code Usage
- `200` — Success
- `201` — Resource created
- `204` — Deleted, no content
- `400` — Bad request (validation errors)
- `401` — Not authenticated
- `403` — Forbidden
- `404` — Resource not found
- `409` — Conflict (e.g., seat already taken, double booking)
- `422` — Unprocessable entity (business rule violation)
- `429` — Rate limited
- `500` — Internal server error

Application-specific error codes (like `SEAT_ALREADY_RESERVED`, `EVENT_SOLD_OUT`, `RESERVATION_EXPIRED`) are included in the `code` field for programmatic handling by clients.

## Concurrency Control for Seat Selection

This is the most critical design challenge. During popular on-sales, thousands of users will try to select the same seats simultaneously. We use a **two-phase approach: temporary reservation + optimistic locking**.

### Phase 1: Seat Reservation (Temporary Hold)

When a user selects seats:

```
POST /api/v1/events/:eventId/reservations
{
  "seat_ids": ["A12", "A13"],
  "section_id": "101"
}
```

This creates a temporary hold (5 minutes) on those seats. The reservation is stored in both PostgreSQL (for durability) and Redis (for fast availability checks).

**Implementation:**
- Use a PostgreSQL `SELECT ... FOR UPDATE SKIP LOCKED` query to atomically lock seats.
- If any requested seat is already locked/sold, the entire request fails with a `409 Conflict`.
- A background job (using Bull queue) expires reservations after 5 minutes.
- Redis stores a seat availability bitmap per event for fast read checks without hitting PostgreSQL on every seating map load.

### Phase 2: Purchase (Optimistic Locking)

When the user proceeds to checkout:

```
POST /api/v1/orders
{
  "reservation_id": "res_xyz",
  "payment_method_id": "pm_abc"
}
```

The order creation:
1. Validates the reservation is still active and belongs to the user.
2. Processes payment.
3. Converts reserved seats to sold tickets within a database transaction.
4. Uses a `version` column on the reservation row for optimistic locking to prevent race conditions between the expiry worker and purchase flow.

### Why This Approach

- **Not pure optimistic locking:** Users would fill out payment info only to learn seats were taken. Bad UX.
- **Not distributed locks (e.g., Redlock):** Adds infrastructure complexity and Redis becomes a single point of failure for correctness.
- **Temporary reservations:** Give users a fair window to complete purchase while preventing double-booking at the database level.

## Handling 10,000 Concurrent Users

### Connection Pooling
- Use `pg-pool` with a pool size of 20-30 connections (PostgreSQL handles ~100 connections well; leave room for background jobs and admin tools).
- For read-heavy endpoints (event listing, seating map), use a read replica.

### Caching Strategy
- **Redis caching** for event details, venue data, and seating availability.
- Event listings: cached for 30 seconds with cache invalidation on event updates.
- Seating availability: cached in Redis as a bitmap, updated on every reservation/purchase via pub/sub.
- Use `Cache-Control` headers for client-side caching of static resources (venue images, seating map layouts).

### Queue-Based Ticket Purchasing
For extremely popular events (on-sale spikes), enable a **virtual queue**:

1. When concurrent purchase requests exceed a threshold, incoming users are placed in a queue.
2. `POST /api/v1/events/:eventId/queue/join` returns a position and estimated wait time.
3. Users poll `GET /api/v1/events/:eventId/queue/status` (or use WebSocket for real-time updates).
4. When their turn arrives, they get a time-limited token to access the reservation endpoint.

This prevents the system from being overwhelmed during flash sales.

### Rate Limiting
- Per-user rate limits: 100 requests/minute for general endpoints, 10 requests/minute for purchase endpoints.
- Implemented with Redis using a sliding window algorithm.
- Return `429 Too Many Requests` with a `Retry-After` header.

### Horizontal Scaling
- The Express API is stateless (JWT auth, no server-side sessions), so it can be load-balanced across multiple instances.
- Use PM2 cluster mode or Kubernetes for auto-scaling.

## Database Schema (Key Tables)

```sql
CREATE TABLE events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title VARCHAR(255) NOT NULL,
  description TEXT,
  venue_id UUID REFERENCES venues(id),
  event_date TIMESTAMPTZ NOT NULL,
  on_sale_date TIMESTAMPTZ,
  status VARCHAR(20) DEFAULT 'draft', -- draft, published, sold_out, cancelled
  total_capacity INT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE seats (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  venue_id UUID REFERENCES venues(id),
  section_id UUID REFERENCES sections(id),
  row_label VARCHAR(10),
  seat_number VARCHAR(10),
  seat_type VARCHAR(20) DEFAULT 'standard' -- standard, premium, accessible
);

CREATE TABLE reservations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id UUID REFERENCES events(id),
  user_id UUID REFERENCES users(id),
  status VARCHAR(20) DEFAULT 'active', -- active, expired, converted
  expires_at TIMESTAMPTZ NOT NULL,
  version INT DEFAULT 1,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE reservation_seats (
  reservation_id UUID REFERENCES reservations(id),
  seat_id UUID REFERENCES seats(id),
  event_id UUID REFERENCES events(id),
  PRIMARY KEY (reservation_id, seat_id),
  UNIQUE (event_id, seat_id) -- prevents double-booking at DB level
);

CREATE TABLE tickets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id UUID REFERENCES events(id),
  seat_id UUID REFERENCES seats(id),
  order_id UUID REFERENCES orders(id),
  user_id UUID REFERENCES users(id),
  status VARCHAR(20) DEFAULT 'active', -- active, cancelled, refunded
  price_cents INT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (event_id, seat_id) -- hard constraint against double-booking
);

CREATE TABLE waitlist_entries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id UUID REFERENCES events(id),
  user_id UUID REFERENCES users(id),
  position INT NOT NULL,
  status VARCHAR(20) DEFAULT 'waiting', -- waiting, notified, expired, converted
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (event_id, user_id)
);
```

## Authentication & Authorization

- **JWT-based authentication** with short-lived access tokens (15 min) and refresh tokens (7 days).
- Tokens include user role (`customer`, `organizer`, `admin`).
- Admin endpoints (`POST /events`, `PUT /events/:id`, etc.) require `organizer` or `admin` role.
- Users can only access their own tickets, orders, and reservations.

## API Versioning

URL-based versioning (`/api/v1/`) for simplicity. When breaking changes are needed, a new version is introduced while the old one is maintained for a deprecation period.

## Waitlist Flow

1. When an event sells out, its status changes to `sold_out`.
2. Purchase endpoints return `422` with error code `EVENT_SOLD_OUT` and a flag `waitlist_available: true`.
3. Users can join via `POST /api/v1/events/:eventId/waitlist`.
4. When tickets become available (cancellation/refund), waitlist entries are processed in FIFO order.
5. The next user in line gets a notification (push notification + email) and a 15-minute window to purchase.
6. If they don't purchase in time, the offer moves to the next person.

## Mobile & Web Considerations

- All responses use JSON.
- Support `Accept-Language` header for i18n.
- Provide `ETag` headers for conditional requests (`If-None-Match`) to reduce bandwidth on mobile.
- Image URLs for events/venues use a CDN with responsive sizing via query parameters (`?w=400&h=300`).
- WebSocket endpoint at `/ws` for real-time seat availability updates during active on-sales.

## Summary

The key design decisions are:

1. **Cursor-based pagination** for reliable, performant list endpoints.
2. **Two-phase reservation system** with `SELECT FOR UPDATE SKIP LOCKED` for safe concurrent seat selection.
3. **Redis caching + read replicas** for handling read-heavy load at scale.
4. **Virtual queue system** for flash-sale scenarios exceeding normal capacity.
5. **Consistent error format** with application-specific error codes for client handling.
