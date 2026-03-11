# Design: E-Commerce Monolith to Services Migration

## Overview

This document outlines a plan to migrate an e-commerce Rails monolith into a services architecture. The monolith currently handles user accounts, product catalog, inventory, orders, payments (Stripe), shipping label generation, email notifications, and a recommendation engine. It runs on a single PostgreSQL database with 50,000 daily active users and a zero-downtime requirement. The team has 6 backend engineers.

## Current State Assessment

The monolith is a Rails application where all eight domains share one PostgreSQL database. The key pain points that drive this migration are likely:

- Deployment coupling: a change to the recommendation engine requires deploying the entire app.
- Scaling limitations: the recommendation engine and product catalog have very different load profiles but share the same resources.
- Development velocity: 6 engineers stepping on each other in the same codebase.
- Database bottleneck: one PostgreSQL instance serving all workloads.

## Bounded Context Identification

Rather than creating a service per database table, we group related functionality into bounded contexts based on business capabilities and data ownership.

### Proposed Bounded Contexts

| Bounded Context | Functionality | Notes |
|---|---|---|
| **Identity** | User accounts, authentication, profiles | Stable, low-change domain |
| **Catalog** | Product catalog, search, categories | Read-heavy, benefits from caching |
| **Inventory** | Stock levels, reservations, warehouse tracking | Tightly coupled to orders during checkout |
| **Order Management** | Orders, payments (Stripe), refunds | Orders and payments are a single transaction — splitting them would add dangerous distributed transaction complexity |
| **Fulfillment** | Shipping label generation, tracking, delivery status | Naturally async, external API dependent (carrier APIs) |
| **Notifications** | Email, push notifications, SMS | Pure side-effect service, event-driven |
| **Recommendations** | Recommendation engine, user behavior tracking | Compute-heavy, independent of transactional systems |

**Key grouping decisions:**

- **Orders + Payments together:** An order isn't complete without payment. Splitting them into separate services would require distributed transactions (sagas) for the most critical business flow — checkout. The complexity isn't worth it at this scale. They share a transaction boundary.
- **Inventory separate from Orders:** Inventory has its own lifecycle (warehouse receiving, stock adjustments) and needs to be queried independently (product pages showing availability). It interacts with orders at checkout but through a well-defined interface (reserve/release).
- **Notifications as its own service:** It has no domain logic — it just reacts to events from other services and sends messages. It's the simplest service to extract.

## Phased Migration Plan

With 6 engineers and zero-downtime tolerance, we cannot extract all services at once. The migration is phased over approximately 9-12 months.

### Phase 1: Notifications Service (Months 1-2)

**Why first:**
- It's the lowest-risk extraction. Notifications are fire-and-forget side effects.
- No other service depends on notifications — it only consumes events.
- It establishes the event infrastructure (message broker) that later phases need.
- Quick win to build team confidence with the services approach.

**What happens:**
1. Set up RabbitMQ (or Amazon SQS) as the message broker.
2. Identify all notification triggers in the monolith (order confirmation, shipping update, password reset, etc.).
3. Publish events from the monolith at each trigger point.
4. Build a standalone Node.js or Rails service that consumes events and sends emails/notifications.
5. Run both old (inline) and new (event-driven) notification paths simultaneously for 2 weeks, comparing output.
6. Remove inline notification code from the monolith.

**Team allocation:** 2 engineers.

### Phase 2: Recommendations Service (Months 2-4)

**Why second:**
- The recommendation engine is compute-heavy and has a completely different scaling profile from the transactional system.
- It reads product and user data but doesn't write to core transactional tables.
- Extracting it frees up significant database resources for the core app.

**What happens:**
1. Extract recommendation logic into a Python service (better ML ecosystem if needed).
2. It gets its own database for recommendation models, user behavior data, and precomputed results.
3. The monolith calls the recommendation service via REST API for product page recommendations.
4. User behavior events (page views, purchases) are published to the message broker for the recommendation service to consume.

**Team allocation:** 2 engineers.

### Phase 3: Catalog Service (Months 4-6)

**Why third:**
- The product catalog is read-heavy and benefits enormously from its own caching layer and potentially Elasticsearch for search.
- It's a natural boundary — products are read by many services but written by few (admin operations).

**What happens:**
1. Extract catalog into its own service with its own PostgreSQL database.
2. Add Elasticsearch for product search (if not already present).
3. Product data is the "source of truth" in the catalog service. Other services (orders, recommendations) reference product IDs but query the catalog service for details.
4. Use the Strangler Fig pattern: new API endpoints go to the catalog service, old endpoints are proxied through and gradually retired.

**Team allocation:** 2-3 engineers.

### Phase 4: Fulfillment Service (Months 6-8)

**Why fourth:**
- Shipping label generation involves external carrier APIs and is naturally asynchronous.
- It has a clear interface: receives order + shipping address, produces labels and tracking numbers.

**What happens:**
1. Extract shipping logic into its own service.
2. It consumes `order.placed` events from the message broker.
3. Interacts with carrier APIs (FedEx, UPS, USPS) to generate labels.
4. Publishes `shipment.created` and `shipment.delivered` events.

**Team allocation:** 1-2 engineers.

### Phase 5: Inventory Service (Months 7-9)

**Why fifth (not earlier):**
- Inventory is tightly coupled to orders at checkout. It needs careful work to define the reservation interface.
- By this phase, the event infrastructure is mature and the team has experience.

**What happens:**
1. Extract inventory into its own service with its own database.
2. Define a synchronous API for checkout flow: `POST /inventory/reserve` and `POST /inventory/release`.
3. Stock level queries for product pages go through a cached read API.
4. Inventory adjustments (warehouse receiving) are handled within the service.

**Team allocation:** 2 engineers.

### Phase 6: Order Management Service (Months 9-12)

**Why last:**
- This is the most critical and complex service. It handles the core business flow (checkout + payment).
- By extracting it last, all surrounding services are already in place, reducing the surface area of the extraction.
- The team has maximum experience with service extraction at this point.

**What happens:**
1. Extract orders + payments into a service with its own database.
2. The checkout flow: Order Service calls Inventory Service (reserve) -> processes Stripe payment -> confirms order -> publishes `order.placed` event.
3. Identity Service remains as the last piece in the (now much smaller) monolith, or is extracted as a final cleanup.

**Team allocation:** 3 engineers (most critical extraction).

## Data Ownership Strategy

### During Transition: Shared Database with Schema Separation

During the migration, we can't switch to separate databases overnight. The approach:

1. **Schema namespacing:** Within the shared PostgreSQL database, create schemas per bounded context (`notifications`, `recommendations`, `catalog`, etc.).
2. **Access boundaries:** Each service only accesses tables within its own schema via its own database user with restricted permissions. Cross-schema access is forbidden in code review.
3. **Data replication for reads:** Services that need to read another service's data get a read-only replicated view or subscribe to events.

### After Transition: Database per Service

Each extracted service eventually gets its own PostgreSQL database:

1. Use logical replication or change data capture (Debezium) to migrate data while both old and new databases are active.
2. The monolith's tables for that domain are made read-only, then deprecated.
3. Foreign key constraints across service boundaries are replaced with application-level references (storing IDs, validating via API calls).

### Handling Cross-Service References

- **Product references in orders:** The order stores a `product_id` and a snapshot of the product data at time of purchase (name, price, image URL). It does not query the catalog service for historical orders.
- **User references everywhere:** Services store `user_id` and call the Identity service (or use JWT claims) when they need user details.

## Inter-Service Communication

### Synchronous (REST/HTTP)

Used for:
- **Checkout flow:** Order Service -> Inventory Service (reserve stock). This must be synchronous because the user is waiting.
- **Product page:** Frontend -> Catalog Service (get product) + Inventory Service (check availability). Parallel calls.
- **User authentication:** All services validate JWTs independently (shared public key), but call Identity service for user details when needed.

### Asynchronous (Message Broker / RabbitMQ)

Used for:
- **Notifications:** All services publish domain events; Notification Service consumes them.
- **Recommendations:** Behavior events (views, purchases) are published for async consumption.
- **Fulfillment:** `order.placed` triggers shipping label generation.
- **Inventory updates:** `shipment.delivered` triggers stock adjustments.

### Decision Rationale

- Synchronous for operations where the user is actively waiting and needs an immediate response.
- Asynchronous for everything else — it decouples services temporally and allows them to fail independently.
- We use RabbitMQ over Kafka because our event volume (50K DAU) doesn't require Kafka's throughput, and RabbitMQ is simpler to operate for a small team.

## Zero-Downtime Migration Strategies

### Strangler Fig Pattern

Each service extraction follows the Strangler Fig approach:

1. **Build the new service** alongside the monolith.
2. **Route new traffic** to the new service via an API gateway / reverse proxy (e.g., NGINX or Kong).
3. **Migrate gradually:** Start with read endpoints, then write endpoints.
4. **Run in parallel:** Both old and new code paths are active. Compare results (shadow mode) before cutting over.
5. **Remove old code** from the monolith once the new service is stable.

### Feature Flags

- Use feature flags (LaunchDarkly, Flipper gem, or simple env vars) to control which code path handles each request.
- Roll out per-endpoint: 1% -> 10% -> 50% -> 100%.
- Instant rollback by flipping the flag.

### Database Migration

- Use logical replication to keep old and new databases in sync during migration.
- Writes go to the new database first, replicated back to the old for services still reading from it.
- Only cut over reads when the new service is fully stable.

### Blue-Green for Service Deployments

- Each new service is deployed using blue-green deployment.
- Health checks confirm the new version is responding correctly before routing traffic.

## Cross-Service Data Consistency

For operations spanning multiple services (e.g., checkout involves Inventory + Orders + Payments):

### Saga Pattern

The checkout saga:

1. **Order Service** creates order in `pending` status.
2. **Order Service** calls **Inventory Service** to reserve stock.
   - If fail -> cancel order, return error to user.
3. **Order Service** calls Stripe to process payment.
   - If fail -> call Inventory Service to release stock, cancel order, return error.
4. **Order Service** confirms order, publishes `order.placed` event.
   - Fulfillment Service picks up the event.
   - Notification Service sends confirmation email.

This is a **choreography-less orchestrated saga** where the Order Service is the coordinator. We chose orchestration over choreography because:

- The checkout flow has a clear linear sequence.
- Orchestration makes the flow explicit and debuggable.
- With choreography, the flow is scattered across multiple services' event handlers — harder to understand and troubleshoot.

### Compensation

If step 3 (payment) fails after step 2 (inventory reserved):
- The Order Service explicitly calls `POST /inventory/release` with the reservation ID.
- If that call also fails, a background reconciliation job detects orphaned reservations and releases them after a timeout (15 minutes).

### Eventual Consistency

Services that consume events (Notifications, Recommendations, Fulfillment) are eventually consistent. This is acceptable because:
- A 2-second delay in sending a confirmation email is fine.
- Recommendation data can be minutes behind without user impact.
- Shipping labels can be generated within minutes of order placement.

## Team Capacity Considerations

With 6 engineers:

- **Never more than 2 active extractions at once.** Each extraction needs at least 2 engineers for code review, on-call, and knowledge sharing.
- **Phases overlap slightly** where possible (Phase 2 starts before Phase 1 is fully complete, since different engineers are involved).
- **Dedicated infrastructure engineer:** One engineer (rotating) focuses on shared infrastructure — message broker, API gateway, CI/CD pipelines for new services, monitoring/observability.
- **Knowledge sharing:** Weekly architecture sync to ensure all 6 engineers understand the overall design, not just their current service.

### Realistic Timeline

| Phase | Months | Engineers | Risk |
|---|---|---|---|
| Notifications | 1-2 | 2 | Low |
| Recommendations | 2-4 | 2 | Low-Medium |
| Catalog | 4-6 | 2-3 | Medium |
| Fulfillment | 6-8 | 1-2 | Low |
| Inventory | 7-9 | 2 | Medium-High |
| Orders + Payments | 9-12 | 3 | High |

The total timeline is 9-12 months. This is realistic for a team of 6, assuming no major surprises and continued feature development happening in parallel (at reduced velocity during active extraction phases).

## Observability

As services are extracted, observability becomes critical:

- **Distributed tracing:** Use OpenTelemetry with Jaeger to trace requests across services.
- **Centralized logging:** All services log to a centralized system (ELK stack or Datadog).
- **Health checks:** Every service exposes `/health` endpoints.
- **Circuit breakers:** Use a circuit breaker pattern (e.g., via `opossum` library) for synchronous inter-service calls to prevent cascading failures.

## Summary

Key design decisions:

1. **7 bounded contexts** based on business capabilities, with Orders + Payments kept together to avoid distributed transaction complexity.
2. **Phased 9-12 month migration** starting with lowest-risk services (Notifications, Recommendations) and ending with the most critical (Orders + Payments).
3. **Strangler Fig pattern** with feature flags for zero-downtime migration.
4. **Schema separation during transition**, eventual database-per-service.
5. **Orchestrated sagas** for cross-service transactions (checkout flow) with explicit compensation.
6. **REST for synchronous** (user-facing flows) and **RabbitMQ for async** (events, side effects).
7. **Team-aware planning** — never more than 2 concurrent extractions for 6 engineers.
