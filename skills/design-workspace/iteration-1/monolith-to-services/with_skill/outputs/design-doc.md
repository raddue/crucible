# E-Commerce Monolith to Services Migration — Design

**Date:** 2026-03-11
**Status:** Draft
**Current Stack:** Rails monolith, single PostgreSQL database
**Team:** 6 backend engineers
**Constraints:** 50,000 DAU, zero downtime tolerance
**Scope:** User accounts, product catalog, inventory, orders, payments (Stripe), shipping, email notifications, recommendation engine

---

## Phase 1: Context Gathering

### Understanding the Current State

The Rails monolith handles eight major functional areas sharing a single PostgreSQL database. With 50,000 daily active users and zero downtime tolerance, this migration must be incremental — no big-bang rewrite. The team of 6 engineers must continue delivering features during the migration.

Key complexity drivers:
- **Shared database** — all domains read/write the same PostgreSQL instance; tables have foreign keys across domain boundaries
- **Zero downtime** — every migration step must be backward-compatible and reversible
- **Team capacity** — 6 engineers cannot extract all services simultaneously; must sequence carefully
- **Cross-domain transactions** — e.g., placing an order involves inventory, payments, shipping, and notifications in one request

---

## Phase 2: Investigated Questions

### Design Dimension 1: Bounded Context Identification

**Hypothesis:** I expect the natural bounded contexts to be: (1) Identity (user accounts + auth), (2) Catalog (products + search), (3) Inventory, (4) Orders + Payments (tightly coupled — separating them creates a distributed transaction problem), (5) Fulfillment (shipping), (6) Notifications (email), (7) Recommendations. I expect Inventory to be more coupled to Orders than to Catalog, which will be a key design tension.

#### Investigation (Deep Dive)

**Codebase Scout:**
This is a conceptual design (no actual Rails codebase to inspect). However, typical Rails e-commerce monoliths have these coupling patterns:
- `Order` model has `belongs_to :user`, `has_many :order_items`, `has_many :payments`
- `OrderItem` references both `Product` and `Inventory` (through SKU)
- `Payment` is tightly coupled to `Order` — always 1:1 or 1:N per order
- `ShippingLabel` is generated after payment confirmation, references order + address
- `Notification` (email) is triggered by state changes across all domains
- `Recommendation` reads product views, purchase history, and catalog data (read-heavy, write-light)

**Domain Researcher:**
Bounded context analysis using Domain-Driven Design principles:

**Context Mapping:**

| Context | Core Entities | External Dependencies | Coupling Strength |
|---------|--------------|----------------------|-------------------|
| **Identity** | User, Address, Auth | None | Low — consumed by all |
| **Catalog** | Product, Category, ProductImage | None (reads from Inventory for stock status) | Low |
| **Inventory** | StockLevel, Warehouse, SKU | Catalog (SKU references Product) | Medium |
| **Order Management** | Order, OrderItem, Cart | Identity (user), Catalog (product info), Inventory (stock check), Payment (charge) | Very High |
| **Payments** | Payment, Refund, StripeCustomer | Order (what's being paid for), Identity (who's paying) | High |
| **Fulfillment** | ShippingLabel, Shipment, Tracking | Order (what to ship), Identity (where to ship) | Medium |
| **Notifications** | EmailTemplate, NotificationLog | All (triggered by events everywhere) | Low (event-driven) |
| **Recommendations** | UserBehavior, ProductSimilarity | Catalog (products), Identity (user history) | Low (read-only) |

**Key insight:** Orders and Payments are tightly coupled but should still be separate contexts. The coupling is managed through an anti-corruption layer, not by merging them. Why: Payments have their own lifecycle (refunds, disputes, chargebacks) independent of order status, and Stripe integration is complex enough to warrant isolation.

**Counter-argument to merging Orders + Payments:** If merged, a Stripe API change forces redeploying the entire order processing system. Separate services allow the payments team to iterate on Stripe integration independently.

**Recommendation:** Eight bounded contexts as listed above. Orders and Payments are separate but tightly coordinated via synchronous calls (payment is part of the order placement flow) and events (refund triggers order status update).

**Impact Analyst:**
- Separating Inventory from Catalog breaks the common `Product.in_stock?` pattern in Rails views. The Catalog service will need to call Inventory or cache stock status.
- Notifications as a separate service is the easiest extraction — it's already event-driven in most Rails apps (Action Mailer callbacks).
- Recommendations is read-heavy and rarely changes — ideal for early extraction as it reduces load on the monolith.

**Challenge:**
The 8-context proposal is sound, but consider: with 6 engineers, having 8 services means less than 1 engineer per service. The team will need to own multiple services each, and cognitive overhead matters. Recommendation: extract into 8 bounded contexts, but consider deploying some as separate modules within a modular monolith first (e.g., Catalog + Inventory stay as separate modules in one deployment unit until the team grows). This gives domain isolation without the operational burden of 8 separate deployments.

**Surprises:** The challenger's point about team capacity vs. service count is sharp. 8 services for 6 engineers means significant operational overhead. However, the extraction order (next decision) means we won't have 8 services running simultaneously early on — it'll be gradual. The modular monolith intermediate step for tightly coupled domains is worth considering.

#### Decision: 8 Bounded Contexts, Phased Extraction

Bounded contexts:
1. **Identity** — User accounts, authentication, addresses
2. **Catalog** — Products, categories, search
3. **Inventory** — Stock levels, warehouses, SKU management
4. **Order Management** — Orders, order items, carts
5. **Payments** — Stripe integration, charges, refunds, disputes
6. **Fulfillment** — Shipping labels, shipment tracking
7. **Notifications** — Email templates, delivery, notification log
8. **Recommendations** — User behavior tracking, similarity engine

Catalog and Inventory may share a deployment unit initially (modular monolith pattern) and split later when the team is ready for the operational overhead.

**Cascading context:** 8 bounded contexts identified. Orders and Payments are separate but coordinated. Team has 6 engineers across 8 eventual services.

---

### Design Dimension 2: Extraction Order (Phased Migration Plan)

**Hypothesis:** I expect the right order to be: (1) Notifications first (lowest coupling, easiest win, builds extraction muscle), (2) Recommendations (read-only, no write contention), (3) Identity (consumed by all — extracting early lets other services depend on it), (4-5) Catalog + Inventory together, (6-7) Payments then Orders (highest coupling, extract last). Fulfillment fits between Inventory and Payments.

#### Investigation (Deep Dive)

**Codebase Scout:**
Typical Rails monolith extraction patterns suggest starting with services that have:
- Few inbound dependencies (nothing else calls them synchronously)
- Clear boundaries (little shared state)
- Low risk (failure doesn't break checkout)

**Domain Researcher:**
Extraction ordering frameworks:

**Criteria for sequencing:**
1. **Coupling** — lower coupling = easier to extract
2. **Risk** — failure impact on revenue (checkout path = highest risk)
3. **Team learning** — early extractions build muscle for harder ones
4. **Value** — some extractions unlock independent scaling or deployment

**Analysis per context:**

| Context | Coupling | Revenue Risk | Learning Value | Scaling Value | Recommended Phase |
|---------|---------|-------------|----------------|---------------|-------------------|
| Notifications | Very Low | None | High (first extraction) | Low | Phase 1 |
| Recommendations | Low | Low | Medium | High (CPU-intensive) | Phase 1 |
| Identity | Medium | High (auth breaks everything) | Medium | Medium | Phase 2 |
| Catalog | Medium | Medium | Medium | High (read-heavy) | Phase 3 |
| Inventory | Medium-High | High (stock accuracy) | Medium | Medium | Phase 3 |
| Fulfillment | Medium | Low | Low | Low | Phase 4 |
| Payments | High | Very High | Low | Medium | Phase 5 |
| Order Management | Very High | Very High | N/A (last) | High | Phase 5 |

**Recommendation:**
- **Phase 1 (Month 1-2):** Notifications + Recommendations — low risk, high learning value
- **Phase 2 (Month 3-4):** Identity — establishes the auth foundation all services need
- **Phase 3 (Month 5-7):** Catalog + Inventory — extract together, split deployment later
- **Phase 4 (Month 8-9):** Fulfillment — medium coupling, moderate risk
- **Phase 5 (Month 10-14):** Payments + Order Management — highest risk, requires saga pattern, extract with extreme care

**Important:** Phases are sequential but overlapping. A phase starts when the previous phase's service is stable in production, not when it's just deployed. Budget 2-4 weeks of stabilization per phase.

**Impact Analyst:**
- Total timeline: ~14 months with 6 engineers
- At any point, the monolith continues to work — strangler fig pattern means old code paths remain active until the new service is proven
- Risk concentrates in Phase 5 — if the team is burned out by then, Orders + Payments extraction could stall
- Recommendation: budget a "consolidation sprint" between Phase 4 and Phase 5 to address tech debt and team fatigue

**Challenge:**
Timeline is realistic but ambitious. Key concern: extracting Identity in Phase 2 is risky. If the Identity service has an outage, the entire platform goes down. Consider: keep Identity in the monolith longer (it's not causing scaling pain) and extract it after the team has more experience (Phase 4, swap with Fulfillment). An authentication outage is worse than a shipping label outage.

Also: the 14-month timeline assumes no feature development pressure. In practice, the team will be split between migration and feature work. Realistic timeline: 18-24 months.

**Surprises:** The challenger's argument to delay Identity extraction is compelling. I assumed extracting it early would help other services, but the risk profile is wrong — authentication is the highest-impact failure mode. Deferring it until the team has battle-tested their extraction patterns makes more sense. Also, the realistic 18-24 month timeline is more honest.

#### Decision: Revised Extraction Order

**Phase 1 (Month 1-3): Build Extraction Muscle**
- Extract **Notifications** and **Recommendations**
- Team learns: service deployment, monitoring, inter-service communication
- Both are low-risk — failures degrade experience but don't break checkout
- **Team allocation:** 2 engineers on Notifications, 2 on Recommendations, 2 on feature work

**Phase 2 (Month 4-7): Scale-Sensitive Domains**
- Extract **Catalog** (read-heavy, benefits from caching layer and CDN)
- Begin **Inventory** extraction (tightly coupled to Catalog, extract together)
- **Team allocation:** 3 engineers on extraction, 3 on feature work

**Phase 3 (Month 8-10): Medium-Risk Domains**
- Extract **Fulfillment** (shipping labels, tracking)
- Extract **Identity** (team now has experience; implement with careful failover — monolith auth as fallback)
- **Team allocation:** 3 engineers on extraction, 3 on feature work

**Phase 4 (Month 11-12): Consolidation**
- No new extractions
- Stabilize existing services, improve monitoring, address tech debt
- Prepare for the hardest extraction (Orders + Payments)
- **Team allocation:** All 6 on stabilization and preparation

**Phase 5 (Month 13-18): Revenue-Critical Domains**
- Extract **Payments** (Stripe integration isolation)
- Extract **Order Management** (the final, hardest extraction)
- Implement saga pattern for distributed order placement
- **Team allocation:** 4 engineers on extraction, 2 on support/feature work

**Total realistic timeline: 18 months**

**Cascading context update:** 5-phase extraction plan over 18 months. Notifications and Recommendations first, Orders and Payments last. Identity deferred to Phase 3.

---

### Design Dimension 3: Data Ownership & Shared Database Strategy

**Hypothesis:** I expect the strangler fig pattern at the data layer — each extracted service gets its own schema/database, but during transition, both the monolith and the new service may need access to the same data. The transition pattern will be: (1) new service writes to its own DB, (2) sync layer keeps monolith DB updated, (3) monolith code gradually stops accessing that data, (4) sync layer removed.

#### Investigation (Deep Dive)

**Codebase Scout:**
In a typical Rails monolith with PostgreSQL, all models share one database. ActiveRecord models have direct foreign key relationships across domains (e.g., `orders.user_id` references `users.id`). Breaking these FK constraints is a prerequisite for extraction.

**Domain Researcher:**
Three strategies for data ownership transition:

1. **Schema separation first (Database-per-service later):**
   - Move tables to service-specific schemas within the same PostgreSQL instance: `identity.users`, `catalog.products`, `orders.orders`
   - Service accesses only its schema, monolith still sees all schemas during transition
   - Later, move schemas to separate databases
   - Advantage: No cross-database sync needed during transition; foreign keys can be relaxed gradually
   - Disadvantage: Still one PostgreSQL instance — no independent scaling

2. **Database-per-service immediately:**
   - Each extracted service gets its own PostgreSQL instance from day one
   - Dual-write during transition: service writes to its DB, sync job writes to monolith DB
   - Advantage: Clean separation from the start; independent scaling
   - Disadvantage: Dual-write consistency is hard; sync lag can cause data discrepancies

3. **Change Data Capture (CDC) with Debezium:**
   - Extract service writes to its own DB
   - Debezium streams changes from the new DB back to the monolith DB (and vice versa during transition)
   - Advantage: No application-level dual-write; CDC is reliable and battle-tested
   - Disadvantage: Adds infrastructure (Kafka + Debezium); latency on data propagation

| Approach | Complexity | Consistency | Scaling | Zero-Downtime Safety |
|----------|-----------|-------------|---------|---------------------|
| Schema separation | Low | Strong (same DB) | Poor | Excellent |
| DB-per-service + dual-write | High | Weak (sync lag) | Excellent | Moderate |
| CDC (Debezium) | Medium-High | Good (near real-time) | Excellent | Good |

**Recommendation:** Schema separation first, then CDC for the final migration to separate databases. This two-step approach matches our phased extraction: early phases use schema separation (simple, safe), later phases use CDC when the team has more experience and the operational infrastructure is in place.

**Impact Analyst:**
- Schema separation requires: create new schemas, move tables with `ALTER TABLE SET SCHEMA`, update Rails models to specify schema
- Foreign keys across schemas still work in PostgreSQL — they break only when moving to separate databases
- CDC (Phase 5) requires Kafka cluster + Debezium connectors — significant infrastructure investment
- The monolith's ActiveRecord queries that join across domains will break when tables move to separate schemas — must be refactored to API calls first

**Challenge:**
Good two-step approach. Blind spot: the "refactor joins to API calls" step is the hardest part and it's mentioned almost in passing. In a mature Rails app, cross-domain joins are everywhere — reporting queries, admin dashboards, search. Each one must be identified and replaced before schema separation. Recommendation: before any extraction, run a query audit to find all cross-schema joins. This is Phase 0 work.

Also: CDC via Debezium requires Kafka. If the team doesn't already run Kafka, that's a massive operational burden. Consider: use PostgreSQL logical replication instead of CDC for the early extractions (same technology the team already knows), reserve CDC for the complex Order/Payment extraction.

**Surprises:** Two important findings: (1) The join audit is prerequisite work I didn't account for — it's a "Phase 0" that must happen before any extraction. (2) PostgreSQL logical replication as a simpler alternative to CDC for early phases is smart — it avoids introducing Kafka until we actually need it.

#### Decision: Three-Step Data Strategy

**Step 1 — Phase 0 (Before any extraction): Join Audit & Refactoring**
- Audit all ActiveRecord queries that join across domain boundaries
- Catalog every cross-domain join: `User JOIN Order`, `Product JOIN Inventory`, `Order JOIN Payment`, etc.
- Refactor joins into two-step queries (fetch from one domain, then the other) or precomputed materialized views
- This work starts immediately and continues in parallel with Phase 1 extractions

**Step 2 — Phases 1-3: Schema Separation**
- Move each extracted domain's tables to its own PostgreSQL schema
- Remove cross-schema foreign key constraints (replace with application-level validation)
- The monolith and new services share the same PostgreSQL instance but access different schemas
- Services access ONLY their own schema; any cross-schema data needs go through APIs

**Step 3 — Phases 4-5: Separate Databases with PostgreSQL Logical Replication**
- Provision separate PostgreSQL instances for Payments and Order Management
- Use PostgreSQL logical replication to keep the monolith's copy in sync during transition
- Once the monolith no longer reads from the migrated tables, stop replication
- Consider CDC (Debezium + Kafka) only if logical replication proves insufficient for the Order/Payment complexity

**Cascading context update:** Three-step data strategy: join audit (Phase 0), schema separation (Phases 1-3), separate databases with logical replication (Phases 4-5). Cross-domain joins must be eliminated before extraction.

---

### Design Dimension 4: Inter-Service Communication Patterns

**Hypothesis:** I expect a mix of synchronous (REST/gRPC) for request-response interactions (e.g., "check inventory before placing order") and asynchronous events for fire-and-forget notifications (e.g., "order placed" → triggers email, updates recommendations). The order placement flow will need a saga pattern for the distributed transaction across Inventory, Payments, and Orders.

#### Investigation (Deep Dive)

**Codebase Scout:**
Rails monolith currently handles everything in synchronous request-response within a single process. Background jobs (Sidekiq/Resque) handle async work like email sending. The extraction needs to replicate this with inter-service communication.

**Domain Researcher:**
Communication patterns for e-commerce microservices:

**Synchronous (REST/gRPC):**
- Use when: the caller NEEDS the response to continue its work
- Examples: Catalog → Inventory (check stock), Order → Payments (charge card), Identity → auth verification
- Trade-offs: simpler to reason about, but creates runtime coupling (if downstream is down, upstream fails)

**Asynchronous (Events via message broker):**
- Use when: the caller doesn't need to wait for the result
- Examples: Order placed → Notifications (send email), Order placed → Recommendations (update model), Payment refunded → Order (update status)
- Trade-offs: decoupled (downstream outage doesn't block upstream), but harder to debug, eventual consistency

**Saga pattern (for distributed transactions):**
- Use when: a business operation spans multiple services and requires all-or-nothing semantics
- The order placement flow: Reserve inventory → Charge payment → Create order → Generate shipping label
- If any step fails, compensating actions roll back prior steps (release inventory, refund payment)
- Two styles: orchestration (central coordinator) vs. choreography (each service triggers the next)

| Interaction | Pattern | Rationale |
|-------------|---------|-----------|
| Check stock (Catalog → Inventory) | Sync REST | UI needs immediate stock status |
| Authenticate request | Sync REST/JWT validation | Must block on auth |
| Place order (Order → Inventory + Payments) | Saga (orchestrated) | Multi-service transaction |
| Order placed → Email | Async event | Fire-and-forget |
| Order placed → Recommendations | Async event | Background processing |
| Payment refunded → Order status | Async event | Eventually consistent |
| Generate shipping label | Async event + callback | External API (slow), callback when ready |

**Recommendation:** REST for synchronous calls (team knows REST, Rails background), RabbitMQ for async events (simpler than Kafka for event-driven patterns, no need for event replay at this scale). Orchestrated saga for order placement (explicit state machine, easier to debug than choreography).

**Impact Analyst:**
- RabbitMQ adds operational infrastructure (but simpler than Kafka)
- Saga orchestrator is a new service/component — consider hosting it within the Order Management service
- Circuit breakers needed for all synchronous calls (if Inventory service is down, don't let Order placement hang)
- Event schema versioning becomes important — services must handle old event formats

**Challenge:**
The REST + RabbitMQ combination is pragmatic. One concern: REST for synchronous calls between services adds latency (HTTP overhead). For high-frequency internal calls (auth verification on every request), consider JWT token validation locally (no service call needed — just verify the signature). Reserve synchronous REST calls for operations where the data might have changed since the token was issued (e.g., stock check).

Also: orchestrated saga vs. choreography is a correct call for this team size. Choreography requires understanding the full event flow across all services, which is harder with 6 people.

**Surprises:** The JWT local validation point is important — I was about to propose an auth service call on every request, which would be a massive bottleneck. JWT validation is stateless and can be done locally. The auth service is only called for token refresh and login.

#### Decision: REST + RabbitMQ + Orchestrated Saga

**Synchronous (REST):**
- Stock check: `GET /inventory/api/stock/{sku}` (Catalog calls Inventory)
- Product details: `GET /catalog/api/products/{id}` (Order calls Catalog for display)
- User profile: `GET /identity/api/users/{id}` (Order calls Identity for address)
- **NOT used for:** auth verification (JWT local validation), notifications, recommendations

**Authentication:**
- JWT tokens issued by Identity service, validated locally by all services (shared public key)
- Token refresh: `POST /identity/api/auth/refresh` (synchronous call to Identity service)
- No inter-service auth call on every request

**Asynchronous (RabbitMQ events):**
- `order.placed` → Notifications (send confirmation email), Recommendations (update model), Fulfillment (queue shipping)
- `payment.refunded` → Order Management (update status), Notifications (send refund email)
- `inventory.low_stock` → Notifications (alert admin)
- `shipment.delivered` → Order Management (mark delivered), Notifications (send delivery email)

**Event envelope:**
```json
{
  "event_type": "order.placed",
  "event_id": "uuid",
  "timestamp": "2026-03-11T10:00:00Z",
  "version": 1,
  "payload": { "order_id": "uuid", "user_id": "uuid", "total_cents": 5999 }
}
```

**Order Placement Saga (Orchestrated):**
```
1. Order Service: Create order (status: pending)
2. Order Service → Inventory Service: Reserve stock (sync REST)
   - Compensate: Release stock
3. Order Service → Payment Service: Charge card (sync REST)
   - Compensate: Refund payment
4. Order Service: Confirm order (status: confirmed)
5. Order Service → Event bus: publish "order.placed"
   - Fulfillment, Notifications, Recommendations react asynchronously
```

If step 2 fails: order marked as `failed`, user notified "out of stock."
If step 3 fails: inventory released (compensating action), order marked as `payment_failed`.

**Circuit breakers:** All synchronous REST calls wrapped with circuit breaker (e.g., `opossum` gem for Rails, or Istio if using service mesh). Fallback: degrade gracefully (e.g., show "stock status unavailable" instead of crashing).

**Cascading context update:** REST for sync calls, RabbitMQ for async events, orchestrated saga for order placement. JWT local validation for auth. Circuit breakers on all sync calls.

---

### Design Dimension 5: Zero-Downtime Migration Strategy

**Hypothesis:** Strangler fig pattern is the obvious choice — route traffic to the new service while keeping the monolith code active. Feature flags control which code path is active. Blue-green deployment for each service extraction.

#### Investigation (Quick Scan)

**Domain Researcher:**
Zero-downtime strategies for monolith-to-services migration:

1. **Strangler Fig:** New service handles new requests, monolith handles old. Traffic gradually shifted via reverse proxy/load balancer routing rules. Old code kept warm until new service is proven.

2. **Branch by Abstraction:** Introduce an abstraction layer in the monolith, implement both old and new behavior behind it, switch via feature flag. More code changes but safer — rollback is a flag flip.

3. **Parallel Running:** Both old and new code process every request. Results compared (shadow testing). When new service matches old service's output, switch over.

**Recommendation:** Combine Branch by Abstraction (within the monolith) with Strangler Fig (for routing). Feature flags control which implementation is active. Shadow testing validates the new service before cutover. This is belt-and-suspenders but appropriate given the zero-downtime requirement.

#### Decision: Strangler Fig + Branch by Abstraction + Shadow Testing

**For each extracted service:**

1. **Introduce abstraction in monolith:** Create an internal API boundary around the domain (e.g., `NotificationService.send_email(...)` instead of direct ActiveRecord calls)
2. **Build the new service:** Implement the same interface as a separate service
3. **Feature flag:** Toggle between monolith implementation and service call
4. **Shadow testing:** Run both in parallel, compare outputs, log discrepancies
5. **Gradual traffic shift:** 1% → 10% → 50% → 100% via feature flag percentage
6. **Decommission:** After 2 weeks at 100% with no issues, remove monolith code for that domain

**Rollback plan:** Feature flag flip (instant, no deployment needed). If new service is completely down, circuit breaker falls back to monolith implementation.

**Database migration safety:**
- All schema changes are backward-compatible (add columns, never remove)
- Column removal happens only after all code referencing it is deployed and stable
- Use `strong_migrations` gem in Rails to enforce safe migration practices

---

## Phase 3: Design Presentation

### Migration Architecture Overview

```
                    ┌──────────────┐
                    │ Load Balancer │
                    │ (nginx/ALB)  │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
     ┌────────▼───┐  ┌─────▼─────┐  ┌──▼──────────┐
     │  Rails     │  │ Extracted │  │  Extracted   │
     │  Monolith  │  │ Service A │  │  Service B   │
     │ (shrinking)│  │           │  │              │
     └────┬───────┘  └─────┬─────┘  └──────┬──────┘
          │                │               │
     ┌────▼───────┐  ┌─────▼─────┐  ┌──────▼──────┐
     │ PostgreSQL │  │ Schema A  │  │  Schema B   │
     │ (shared,   │  │ (same     │  │  (same      │
     │  shrinking)│  │  instance)│  │   instance) │
     └────────────┘  └───────────┘  └─────────────┘
              │            │               │
              └────────────┼───────────────┘
                           │
                    ┌──────▼───────┐
                    │  RabbitMQ    │
                    │  (events)    │
                    └──────────────┘
```

### Detailed Phase Plan

#### Phase 0: Foundation (Month 0-1, concurrent with Phase 1 prep)

**Work:**
- Audit all cross-domain ActiveRecord queries and joins
- Introduce internal API boundaries in the monolith for each domain
- Set up service deployment infrastructure (Docker, CI/CD, health checks)
- Set up RabbitMQ cluster
- Implement feature flag system (LaunchDarkly or Flipper gem)
- Set up centralized logging and distributed tracing (OpenTelemetry)

**Team:** 2 engineers on infrastructure, 4 on feature work

#### Phase 1: Low-Risk Extractions (Month 1-3)

**Notifications Service:**
- Rails → separate Ruby/Sidekiq service (or Node.js if team prefers)
- Consumes events from RabbitMQ: `order.placed`, `payment.refunded`, `shipment.delivered`, etc.
- Owns: email templates, notification preferences, delivery log
- Data migration: move `notifications`, `email_templates`, `notification_preferences` tables to `notifications` schema
- Shadow test: send emails from both monolith and new service, compare deliverability metrics

**Recommendations Service:**
- Extract recommendation engine into a Python service (if ML-based) or Ruby service
- Consumes events: `product.viewed`, `order.placed` (to build purchase history)
- Exposes: `GET /recommendations/api/users/{id}/recommended-products`
- Data: owns `user_behaviors`, `product_similarities` — low coupling, easy to extract
- This service can use a different database (e.g., Redis for fast lookups) without affecting the monolith

**Exit criteria for Phase 1:**
- Both services running at 100% traffic for 2+ weeks
- Monitoring dashboards showing equivalent or better performance than monolith
- On-call runbooks for both services

#### Phase 2: Scale-Sensitive Domains (Month 4-7)

**Catalog Service:**
- Extract product management, search, categories
- Read-heavy — benefits from dedicated caching (Redis/Varnish)
- Exposes: `GET /catalog/api/products`, `GET /catalog/api/products/{id}`, `GET /catalog/api/search`
- Challenge: product search may need Elasticsearch — extract search as a sub-component of Catalog
- Data: owns `products`, `categories`, `product_images`

**Inventory Service:**
- Extract stock management, warehouse tracking
- Tightly coupled to Order placement (stock reservation during checkout)
- Exposes: `GET /inventory/api/stock/{sku}`, `POST /inventory/api/reserve`, `POST /inventory/api/release`
- Data: owns `stock_levels`, `warehouses`, `stock_movements`
- Critical: stock reservation must be atomic — use database-level locking within Inventory service

**Exit criteria for Phase 2:**
- Catalog search performs as well as or better than monolith
- Inventory service handles peak checkout load (measured by load test)
- No increase in stock discrepancy rate

#### Phase 3: Medium-Risk Domains (Month 8-10)

**Fulfillment Service:**
- Extract shipping label generation, tracking
- Interacts with external shipping APIs (FedEx, UPS, USPS)
- Consumes: `order.placed` events (async — shipping isn't time-critical)
- Exposes: `GET /fulfillment/api/orders/{id}/shipment`
- Data: owns `shipping_labels`, `shipments`, `tracking_events`

**Identity Service:**
- Extract user management, authentication, authorization
- JWT token issuance and refresh
- All other services validate JWT locally (no synchronous dependency)
- Data: owns `users`, `addresses`, `auth_tokens`
- **Safety measure:** monolith retains a read-only copy of auth data for fallback. If Identity service is down, monolith can validate existing JWTs (but can't issue new ones)

#### Phase 4: Consolidation (Month 11-12)

- No new extractions
- Fix issues discovered during Phases 1-3
- Improve monitoring, alerting, runbooks
- Load test the distributed system under peak conditions
- Prepare saga orchestration for Order placement
- Team training on distributed debugging

#### Phase 5: Revenue-Critical Domains (Month 13-18)

**Payments Service:**
- Extract Stripe integration: charges, refunds, disputes, webhooks
- Exposes: `POST /payments/api/charge`, `POST /payments/api/refund`
- Data: owns `payments`, `refunds`, `stripe_customers`, `stripe_events`
- PCI compliance boundary — isolating payments in its own service reduces PCI scope for all other services
- Shadow test: process payments through both monolith and service, compare results (idempotency keys prevent double-charging)

**Order Management Service:**
- The final extraction — the core of the monolith
- Owns: orders, order items, carts, order state machine
- Implements the saga orchestrator for distributed order placement
- Data: owns `orders`, `order_items`, `carts`
- This is the riskiest extraction — extensive shadow testing and slow traffic rollout (1% → 5% → 10% → 25% → 50% → 100%)

### Cross-Service Data Consistency

**Problem:** Placing an order spans Inventory (reserve stock), Payments (charge card), Orders (create order), Fulfillment (queue shipping), and Notifications (send email).

**Solution: Orchestrated Saga with Compensation**

```
Order Service (Saga Orchestrator)
  │
  ├── Step 1: Create Order (status: pending)
  │   └── Compensate: Cancel order
  │
  ├── Step 2: Reserve Inventory (sync call)
  │   └── Compensate: Release inventory
  │
  ├── Step 3: Charge Payment (sync call)
  │   └── Compensate: Refund payment
  │
  ├── Step 4: Confirm Order (status: confirmed)
  │   └── No compensation needed (this is the commit point)
  │
  └── Step 5: Publish "order.placed" event
      └── Fulfillment + Notifications react asynchronously
```

**Saga state is persisted** in the Order database. If the Order service crashes mid-saga, it can resume from the last persisted step on restart.

**Idempotency:** Every step uses idempotency keys. Re-executing a step that already succeeded is a no-op.

### Monitoring & Observability

- **Distributed tracing:** OpenTelemetry across all services. Every request gets a trace ID that propagates through sync calls and async events.
- **Centralized logging:** ELK stack or Datadog. Structured JSON logs with trace ID, service name, request ID.
- **Health checks:** Each service exposes `/health` (liveness) and `/ready` (readiness). Kubernetes or load balancer uses these for routing.
- **SLO dashboard:** Per-service latency (p50, p95, p99), error rate, availability. Alert when SLOs are breached.
- **Saga monitoring:** Dashboard showing in-flight sagas, failed sagas pending compensation, compensation success rate.

---

## Gap Scan

- [x] **Acceptance criteria:**
  - Each phase has explicit exit criteria
  - Zero-downtime maintained via strangler fig + feature flags
  - 6-engineer team constraint respected (no more than 3 engineers on extraction at once)
  - Saga pattern specified for cross-service transactions
- [x] **Testing strategy:**
  - Shadow testing for each extraction (run old and new in parallel)
  - Load testing before each cutover (replicate production traffic)
  - Contract tests between services (consumer-driven contracts)
  - Chaos testing in Phase 4 (kill services, verify circuit breakers and fallbacks)
- [x] **Integration impact:**
  - RabbitMQ cluster is new infrastructure
  - Feature flag system is new infrastructure
  - Centralized logging/tracing is new infrastructure
  - All infrastructure should be set up in Phase 0
- [x] **Failure modes:**
  - Service down → circuit breaker → fallback to monolith code (during transition) or degraded response (post-transition)
  - RabbitMQ down → events queued in memory (limited), alert immediately, events replayed on recovery
  - Saga step fails → compensating actions execute, order marked failed, user notified
  - Database migration breaks backward compatibility → detected by strong_migrations gem, blocked before deploy
  - Network partition between services → circuit breakers open, monolith fallback (during transition)
- [x] **Edge cases:**
  - Feature flag rollback during active requests → in-flight requests complete on old path, new requests go to monolith
  - Partial saga compensation failure → saga enters "compensation_failed" state, manual intervention required, alert fires
  - Event ordering issues → events include version numbers, consumers handle out-of-order delivery (idempotent processing)
  - Clock skew between services → use event IDs (UUIDs) for deduplication, not timestamps
