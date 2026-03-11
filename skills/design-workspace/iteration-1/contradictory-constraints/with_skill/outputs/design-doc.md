# Real-Time Collaborative Document Editor — Design

**Date:** 2026-03-11
**Status:** Draft
**Tech Stack:** TypeScript (frontend + backend)
**Team:** 2 engineers, 3 months
**Requirements:** Real-time collaboration (sub-100ms latency), offline support, 500-page documents, complete version history

---

## Phase 1: Context Gathering

### Understanding the Tension

This project has a fundamental tension between scope and constraints that must be surfaced immediately:

**Scope:** Real-time collaboration (Google Docs-level) + offline editing + 500-page document support + complete version history. Each of these is individually a significant engineering challenge. Combined, they represent years of engineering effort by large teams (Google Docs: 100+ engineers, Notion: 50+ engineers on their editor alone).

**Constraints:** 2 engineers, 3 months.

This design must confront this tension honestly rather than hand-wave it. The investigated questions below will reveal where to cut scope and what to phase.

---

## Phase 2: Investigated Questions

### Design Dimension 1: Scope Assessment — What Can 2 Engineers Build in 3 Months?

**Hypothesis:** I expect that real-time collaboration + offline + 500-page docs + version history is approximately 10-20x more work than 2 engineers can deliver in 3 months. The design should recommend aggressive scope reduction: focus on real-time collaboration for the first release, defer offline support and version history to later phases. 500-page support depends on the editor architecture choice.

#### Investigation (Deep Dive)

**Codebase Scout:**
No existing codebase — greenfield TypeScript project. No constraints from prior work.

**Domain Researcher:**
Complexity assessment of each requirement:

**Real-time collaboration:**
- Requires: collaboration algorithm (OT or CRDT), WebSocket server, cursor/presence awareness, conflict resolution
- Estimated effort with an existing library (Yjs, Automerge): 4-6 weeks for 2 engineers
- Estimated effort from scratch: 6-12 months (this is a PhD-thesis-level problem)
- Verdict: **Achievable in 3 months ONLY if using an existing CRDT/OT library**

**Offline editing with re-merge:**
- Requires: local persistence, change tracking, merge protocol for divergent document states, conflict UI
- Complication: offline edits can diverge arbitrarily from the online document — merging a day's worth of offline edits is fundamentally harder than merging real-time keystrokes
- Estimated effort: 3-4 weeks if CRDT-based (CRDTs handle offline merge natively), 6-8 weeks if OT-based (OT requires server-side transformation, offline breaks this)
- Verdict: **Achievable in 3 months only if using CRDTs (which handle offline natively)**

**500-page documents:**
- Requires: virtualized rendering (only render visible pages), lazy loading, efficient data structures for large documents
- Rich text editor performance degrades significantly above ~50 pages without virtualization
- Estimated effort: 2-3 weeks for basic virtualization, ongoing optimization
- Verdict: **Partially achievable — basic virtualization is feasible, but 500 pages with real-time collaboration will have performance issues**

**Complete version history:**
- Requires: snapshot strategy (full snapshots vs. operation log), version browsing UI, diff visualization, restore capability
- If CRDT-based: operation log is the source of truth — versions can be reconstructed by replaying operations up to a timestamp
- Storage concern: 500-page document with full operation history will be massive
- Estimated effort: 2-3 weeks for basic version list + restore, 6-8 weeks for full diff visualization and efficient storage
- Verdict: **Basic version history is feasible, full diff visualization is not in 3 months**

**Total estimated effort (using CRDT library, all features):** 11-16 weeks for 2 engineers = 22-32 engineer-weeks. With a 3-month window (26 engineer-weeks), this is theoretically possible but leaves zero margin for bugs, testing, deployment, or the inevitable "CRDT edge cases."

**Recommendation:** Apply YAGNI aggressively. Ship a v1 that does real-time collaboration well, with basic offline support (CRDT provides this "for free"), basic version history (operation log with timestamps), and document size handling up to ~100 pages. Defer 500-page optimization and rich version diff UI to v2.

**Impact Analyst:**
- Reduced scope affects product promises — stakeholders must agree to the phased approach
- CRDTs provide offline merge as a byproduct, so "basic offline" is almost free — good news
- 500-page optimization is an independent workstream that can be tackled in v2 without re-architecting
- Version history based on operation log means the data is captured from day 1 — the UI can come later

**Challenge:**
The scope assessment is accurate. One additional concern: the "3 months" timeline should account for learning curve. If neither engineer has worked with CRDTs before, budget 1-2 weeks for ramp-up. The effective timeline is more like 10 weeks of productive development.

Also: "basic offline support" needs clear definition. Does "offline" mean "app stays open, network drops temporarily" (simple — CRDT handles this) or "user deliberately works offline for hours, then comes back" (harder — needs local persistence, queue management, large merge)? The first is almost free with CRDTs; the second is a significant feature.

**Surprises:** The distinction between "network resilience" (free with CRDTs) and "deliberate offline mode" (significant work) is important. My hypothesis lumped these together. We should scope offline to "network resilience" for v1 and "deliberate offline mode" for v2.

#### Decision: Aggressive Scope Reduction with Phased Delivery

**v1 (3 months — the deliverable):**
- Real-time collaborative editing with cursor presence (core feature)
- Network resilience: if connection drops, local edits continue and merge when reconnected (CRDT handles this)
- Document size: optimized for up to 100 pages, functional up to 500 (without virtualization — may be slow)
- Basic version history: timestamp-based operation log, "restore to this version" capability, no diff view
- Sub-100ms latency for keystroke propagation (within same region)

**v2 (future — explicitly deferred):**
- Deliberate offline mode with local persistence
- 500-page document virtualization for smooth editing
- Rich version history with diff visualization
- Comments and suggestions
- Access control and sharing permissions

**Stakeholder conversation required:** This phased approach must be agreed upon before development starts. The prompt's requirements cannot all be delivered at production quality by 2 engineers in 3 months.

**Cascading context:** v1 focuses on real-time collaboration + network resilience. CRDTs are the likely algorithm choice (offline merge benefit). 500-page optimization and deliberate offline mode deferred.

---

### Design Dimension 2: Collaboration Algorithm — OT vs. CRDT

**Hypothesis:** Given our decision to use CRDTs' offline merge as a "free" feature and the 2-engineer team, I expect CRDTs (specifically Yjs) to be the clear winner over Operational Transforms. OT requires a centralized server for transformation, which breaks under network partitions. CRDTs are peer-to-peer compatible and handle offline natively.

#### Investigation (Deep Dive)

**Codebase Scout:**
Greenfield TypeScript project. The algorithm choice affects the entire architecture — this is the most consequential decision.

**Domain Researcher:**

**Operational Transforms (OT):**
- How it works: Operations (insert, delete) are transformed against concurrent operations by a central server. The server is the single source of truth.
- Used by: Google Docs (custom OT), Firepad (deprecated)
- Advantages: Well-understood algorithm (30+ years of research), server has authoritative document state, smaller memory footprint
- Disadvantages: Requires centralized server for transformation (offline breaks this model), transformation functions are notoriously hard to get right (Google's OT has known edge cases even after years), server becomes a bottleneck and single point of failure
- TypeScript libraries: ShareDB (mature, Node.js-based OT server)
- Offline story: Poor — OT fundamentally assumes a central server for ordering. Offline requires buffering operations and replaying on reconnect, which can produce surprising merges.

**CRDTs (Conflict-Free Replicated Data Types):**
- How it works: Data structure designed so concurrent edits always converge to the same state, regardless of operation order. No central server needed for conflict resolution.
- Used by: Figma (custom CRDT), Notion (CRDT-inspired), Apple Notes (CRDT-based)
- Advantages: Offline support is inherent (peers merge without server), no single point of failure, peer-to-peer architectures possible
- Disadvantages: Higher memory overhead (each character has a unique ID), more complex data structures, fewer "off-the-shelf" rich text CRDTs with good UIs
- TypeScript libraries: **Yjs** (mature, excellent, has rich text CRDT via `y-prosemirror`), Automerge (more academic, heavier)
- Offline story: Excellent — CRDTs are designed for exactly this use case

**Yjs specifically:**
- Most popular CRDT implementation for collaborative editing
- Bindings for ProseMirror, TipTap, Monaco, CodeMirror, Quill
- `y-websocket` for real-time sync, `y-indexeddb` for local persistence
- Active maintenance, large community, used in production by many companies
- Handles text, rich text, and arbitrary JSON structures
- Memory overhead: ~50 bytes per character for metadata (manageable for documents up to hundreds of pages)

| Criterion | OT (ShareDB) | CRDT (Yjs) |
|-----------|-------------|-----------|
| Offline support | Poor | Excellent |
| Implementation complexity | High (transform functions) | Medium (library handles it) |
| TypeScript support | Good | Excellent |
| Rich text editing | ShareDB + Quill | Yjs + TipTap/ProseMirror |
| Memory overhead | Low | Medium (~50B/char) |
| Server dependency | Required (single point of failure) | Optional (peer-to-peer possible) |
| Learning curve | High | Medium |
| 500-page documents | Good (lower memory) | Manageable (with lazy loading) |
| Production readiness | Mature | Mature |

**Recommendation:** Yjs (CRDT). For a 2-engineer team with 3 months, Yjs is the clear winner:
1. Offline merge is free — don't have to build it
2. No complex transformation server to implement
3. Excellent TypeScript ecosystem with TipTap integration
4. Active community and maintenance
5. The 50B/char overhead is acceptable for our scope (100 pages optimized, 500 functional)

**Impact Analyst:**
- Yjs determines the entire architecture: WebSocket-based sync, Y.Doc as the central data structure, operation log as the version history source
- Editor choice is constrained to Yjs-compatible editors: TipTap (recommended — built on ProseMirror, extensible), ProseMirror (lower-level), Quill (simpler but less extensible)
- Server-side: `y-websocket` handles sync, but we need persistence (Yjs operations must be stored, not just relayed)
- The memory overhead at 500 pages: ~250,000 characters × 50 bytes = ~12.5 MB of CRDT metadata. Significant but manageable in a modern browser.

**Challenge:**
Solid recommendation. CRDTs are the right call for this team and scope. One nuance: Yjs' "offline for free" means operations are applied locally and merged when reconnected. But for long offline periods, the merge can produce surprising results (e.g., two users restructure the same section differently). For v1's "network resilience" scope, this isn't a problem — short disconnections produce small, intuitive merges. For v2's deliberate offline mode, the merge quality for large divergences needs attention.

No change to the recommendation needed — just flag for v2 planning.

**Surprises:** None — hypothesis confirmed. Yjs is the dominant choice for a TypeScript collaborative editor in 2026.

#### Decision: Yjs (CRDT) with TipTap Editor

- **CRDT library:** Yjs (`yjs` npm package)
- **Rich text editor:** TipTap v2 (built on ProseMirror, excellent Yjs integration via `@tiptap/extension-collaboration`)
- **Sync transport:** `y-websocket` for WebSocket-based real-time sync
- **Local persistence:** `y-indexeddb` for browser persistence (survives page reload, provides network resilience)
- **Document model:** `Y.Doc` containing a `Y.XmlFragment` for rich text content

**Cascading context update:** Yjs + TipTap is the core stack. WebSocket sync, IndexedDB persistence. This constrains the server architecture and version history approach.

---

### Design Dimension 3: Architecture for Sub-100ms Latency

**Hypothesis:** I initially framed this as "how to achieve sub-100ms latency" but investigation may reveal that with Yjs + WebSocket, the question is actually about what could PREVENT sub-100ms latency — the defaults should be fast enough.

#### Investigation — Question Redirected

**Was going to ask:** "What architecture choices are needed for sub-100ms keystroke propagation?"

**Investigation revealed the real question is:** "What could break the sub-100ms latency that Yjs + WebSocket already provides, and how do we avoid those pitfalls?"

**Why the redirect:** Yjs operations are tiny (a few bytes per keystroke). WebSocket is persistent connection with no HTTP overhead. In the same AWS region, round-trip latency is 1-5ms. Yjs sync protocol is already optimized for minimal wire format. The latency target is achievable by default — the question is what to avoid.

**Latency budget:**
| Step | Typical Latency |
|------|----------------|
| Client: Yjs operation creation | <1ms |
| Client: serialize + send via WebSocket | <1ms |
| Network: client → server (same region) | 1-5ms |
| Server: process + broadcast | <1ms |
| Network: server → other clients | 1-5ms |
| Client: apply Yjs operation | <1ms |
| Client: TipTap re-render | 5-20ms |
| **Total** | **8-33ms** |

**What could break this:**
1. **Server persistence on the sync path:** If the server writes every operation to a database synchronously before broadcasting, it adds 5-20ms. Solution: broadcast first, persist asynchronously.
2. **Large document initial load:** 500-page document sync on connect could take seconds. Solution: lazy loading — load visible portion first, sync rest in background.
3. **Cross-region collaboration:** Latency between US East and Europe is ~80ms one-way, making round-trip ~160ms. Solution: for v1, deploy in one region. Cross-region collaboration is a v2 concern.
4. **TipTap rendering bottleneck:** Large documents with complex formatting can cause slow re-renders. Solution: virtualize rendering (only render visible portion) — deferred to v2 but design for it.

#### Decision — Auto-Resolved: Default Architecture is Sufficient

The Yjs + WebSocket architecture meets the sub-100ms target by default for same-region collaboration. Key architectural rules:

1. **Broadcast before persist:** Server relays Yjs operations to other clients immediately, persists to database asynchronously
2. **Single-region deployment for v1:** Deploy server in one AWS region. Document this limitation.
3. **Lazy initial sync:** On connect, send document snapshot for visible portion, sync full document in background
4. **No synchronous middleware on the WebSocket path:** Auth happens on connection establishment, not per message

*Speak up if you disagree.*

**Cascading context update:** Sub-100ms latency achieved by default with Yjs + WebSocket in same region. Server uses broadcast-first-persist-later pattern.

---

### Design Dimension 4: Version History Storage Strategy

**Hypothesis:** With Yjs, the operation log IS the version history. But storing every keystroke for a 500-page document is enormous. I expect we need a hybrid: periodic snapshots + operation log segments. Version restore = load nearest snapshot + replay operations.

#### Investigation (Deep Dive)

**Codebase Scout:**
Yjs has built-in support for document state encoding (`Y.encodeStateAsUpdate`) and state vectors for incremental sync. The operation log is a compact binary format.

**Domain Researcher:**
Three approaches for version history with Yjs:

1. **Full operation log (append-only):**
   - Store every Yjs update in order. Reconstruct any version by replaying from start.
   - Advantage: Complete fidelity, no information loss
   - Disadvantage: Grows unboundedly. A 500-page document with heavy editing could generate gigabytes of operations over months. Reconstruction time grows linearly — loading version from 3 months ago requires replaying millions of operations.

2. **Periodic snapshots only:**
   - Take full document snapshots at intervals (every N minutes or N operations)
   - Advantage: O(1) version loading, predictable storage
   - Disadvantage: Granularity limited to snapshot interval. Can't see the exact state at 2:47pm — only the nearest snapshot. Losing operations between snapshots means some edits are invisible in history.

3. **Hybrid: Snapshots + Operation Log Segments:**
   - Take a full snapshot every N operations (e.g., every 1,000 operations or every 5 minutes)
   - Store operation log segments between snapshots
   - To reconstruct version at time T: load nearest snapshot before T, replay operations up to T
   - Advantage: Bounded reconstruction time (max 1,000 operations to replay), full fidelity preserved, manageable storage
   - Disadvantage: Slightly more complex than either approach alone

| Approach | Storage Growth | Reconstruction Time | Fidelity | Complexity |
|----------|---------------|--------------------|-----------| -----------|
| Full op log | Unbounded | O(n) operations | Perfect | Low |
| Snapshots only | Linear, predictable | O(1) | Lossy | Low |
| Hybrid | Linear, predictable | O(snapshot_interval) | Perfect | Medium |

**Recommendation:** Hybrid approach. Snapshot every 1,000 operations or 5 minutes (whichever comes first). Store operation log segments between snapshots. Garbage collect old operation segments after 90 days (keep snapshots forever for point-in-time restore at snapshot granularity).

**Impact Analyst:**
- Yjs provides `Y.encodeStateAsUpdate(doc)` for snapshots — binary format, typically 2-5x the text size
- 500-page document (~250,000 characters) = ~500KB-1.25MB per snapshot
- With snapshots every 5 minutes and 8 hours of active editing: ~96 snapshots = ~50-120MB per document per day
- For v1's 100-page target: ~20-50MB per document per day — very manageable
- Storage: PostgreSQL for metadata + S3 for binary snapshot/operation data
- Compression: Yjs binary format compresses well — gzip reduces by 60-80%

**Challenge:**
The snapshot interval needs tuning. 5 minutes is good for active editing, but snapshots during idle periods waste storage. Better approach: snapshot after 1,000 operations (effort-based, not time-based). Also: the 90-day garbage collection of operation segments needs stakeholder approval — "complete version history" may mean "forever" to the product team. Clarify requirements.

**Surprises:** The challenger's point about effort-based vs. time-based snapshots is smart — avoids wasting storage during idle periods. And the "complete version history" requirement likely needs clarification. For v1, implement operation-based snapshots with no garbage collection (defer the storage optimization to when it's actually a problem — YAGNI).

#### Decision: Operation-Based Snapshots + Retained Operation Log

**v1 implementation:**
- Snapshot after every 1,000 Yjs operations (not time-based)
- Retain all snapshots and operation segments (no garbage collection in v1)
- Store snapshots and operation segments in S3 (compressed with gzip)
- Store metadata (snapshot timestamps, operation counts, S3 keys) in PostgreSQL
- Version history UI: list snapshots with timestamps, allow restore to any snapshot
- Diff view: deferred to v2

**Storage model:**
```typescript
interface DocumentVersion {
  id: string;
  documentId: string;
  snapshotKey: string;     // S3 key for the Yjs state snapshot
  operationLogKey: string; // S3 key for operations since last snapshot
  operationCount: number;  // Operations in this segment
  createdAt: Date;
  createdBy: string;       // User who triggered the snapshot threshold
}
```

**Restore flow:**
1. User selects version from history list
2. Load snapshot from S3
3. If user wants exact point between snapshots, replay operations from log segment
4. Create new Yjs document from the restored state
5. New document state becomes a new version (append-only — no destructive restore)

**Cascading context update:** Version history uses operation-based snapshots stored in S3. All data retained (no GC in v1). Restore is non-destructive (creates new version).

---

### Design Dimension 5: System Architecture & Technology Choices

**Hypothesis:** Full-stack TypeScript: React frontend with TipTap, Node.js backend with WebSocket server, PostgreSQL for metadata, S3 for document data. The backend is relatively thin — Yjs does the heavy lifting.

#### Investigation (Quick Scan)

**Domain Researcher:**
With Yjs + TipTap decided and the constraint of TypeScript everywhere, the architecture is largely determined:

**Frontend:**
- React + TipTap v2 + Yjs extensions
- `@tiptap/extension-collaboration` for Yjs integration
- `@tiptap/extension-collaboration-cursor` for cursor presence
- `y-indexeddb` for local persistence (network resilience)
- `y-websocket` client for WebSocket sync

**Backend:**
- Node.js with Express (HTTP endpoints) + `ws` (WebSocket server)
- `y-websocket` server adapter handles Yjs sync protocol
- Custom persistence: hook into Yjs server to write updates to S3
- PostgreSQL for: user accounts, document metadata, version history metadata, access control
- S3 for: Yjs snapshots, operation log segments

**Infrastructure:**
- Single server for v1 (WebSocket connections are stateful — load balancing WebSockets requires sticky sessions or a pub/sub layer)
- Redis for presence awareness (who's online, cursor positions) — lightweight pub/sub

This is well-established and doesn't warrant a deep dive.

#### Decision — Auto-Resolved: Standard Yjs Architecture

```
┌──────────────────────────────────────────────┐
│               React Frontend                  │
│                                              │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │  TipTap  │  │   Yjs    │  │ IndexedDB │  │
│  │  Editor  │  │  Y.Doc   │  │ (offline) │  │
│  └────┬─────┘  └────┬─────┘  └─────┬─────┘  │
│       └──────────────┼──────────────┘        │
│                      │ WebSocket             │
└──────────────────────┼───────────────────────┘
                       │
┌──────────────────────┼───────────────────────┐
│            Node.js Backend                    │
│                      │                        │
│  ┌───────────────────┼────────────────────┐  │
│  │     y-websocket server                 │  │
│  │  (sync protocol + broadcast)           │  │
│  └────────┬──────────────────┬────────────┘  │
│           │                  │                │
│  ┌────────▼──────┐  ┌───────▼───────────┐   │
│  │  PostgreSQL   │  │       S3          │   │
│  │  - users      │  │  - snapshots      │   │
│  │  - doc meta   │  │  - operation logs │   │
│  │  - versions   │  │                   │   │
│  │  - access     │  │                   │   │
│  └───────────────┘  └───────────────────┘   │
│           │                                   │
│  ┌────────▼──────┐                           │
│  │    Redis      │                           │
│  │  - presence   │                           │
│  │  - cursors    │                           │
│  └───────────────┘                           │
└──────────────────────────────────────────────┘
```

*Speak up if you disagree.*

---

## Phase 3: Design Presentation

### What Gets Built in 3 Months

#### Week 1-2: Foundation
- Project scaffolding (React + Node.js + TypeScript monorepo)
- TipTap + Yjs integration (local editing works)
- Basic WebSocket server with `y-websocket`
- Two browsers can edit the same document in real-time
- Authentication (simple JWT — don't over-engineer)

#### Week 3-4: Core Collaboration
- Cursor presence (see other users' cursors and selections)
- User awareness (who's in the document, online/offline indicators)
- IndexedDB persistence (page reload doesn't lose work)
- Network resilience (edits during brief disconnections merge on reconnect)

#### Week 5-7: Document Management
- Document CRUD (create, list, open, delete)
- PostgreSQL schema for document metadata
- S3 persistence for Yjs document state
- Version history: snapshot system (every 1,000 ops)
- Version history UI: list versions, restore to any version

#### Week 8-9: Rich Text Features
- Essential formatting: headings, bold, italic, lists, links, images
- Paste handling (paste from Word, Google Docs, web)
- Keyboard shortcuts

#### Week 10-11: Polish & Performance
- Performance optimization for documents up to 100 pages
- Basic 500-page handling (functional but not optimized)
- Error handling (reconnection, stale document detection)
- Loading states and UX polish

#### Week 12: Testing & Deployment
- End-to-end testing of collaboration scenarios
- Load testing (concurrent editors)
- Deployment to production
- Monitoring and alerting setup

### What Does NOT Get Built

To be explicit about what's cut (YAGNI):
- **Deliberate offline mode** with prolonged disconnection — deferred to v2
- **Document virtualization** for smooth 500-page editing — deferred to v2
- **Version diff view** — deferred to v2
- **Comments and suggestions** — deferred to v2
- **Access control and sharing** (beyond basic auth) — deferred to v2
- **Cross-region low-latency** — v1 is single-region
- **Mobile-specific optimizations** — web only for v1
- **Import/export** (Word, PDF) — deferred to v2
- **Search within documents** — basic browser find works; custom search deferred

### Key Technical Decisions Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Collaboration algorithm | CRDT (Yjs) | Offline merge for free, no central transform server, mature TypeScript library |
| Rich text editor | TipTap v2 | Built on ProseMirror, native Yjs integration, extensible |
| Transport | WebSocket (`y-websocket`) | Persistent connection, sub-ms message delivery |
| Local persistence | IndexedDB (`y-indexeddb`) | Browser-native, survives reload, provides network resilience |
| Version history | Operation-based snapshots in S3 | Bounded reconstruction time, complete fidelity, manageable storage |
| Database | PostgreSQL | Metadata, users, document records |
| Object storage | S3 | Document snapshots and operation logs |
| Presence | Redis pub/sub | Lightweight, ephemeral cursor/user data |
| Deployment | Single region | Sub-100ms latency achievable; cross-region is v2 |

### Data Model

```typescript
// PostgreSQL tables
interface User {
  id: string;          // UUID
  email: string;
  name: string;
  passwordHash: string;
  createdAt: Date;
}

interface Document {
  id: string;          // UUID
  title: string;
  ownerId: string;     // FK to User
  currentSnapshotKey: string;  // S3 key for latest Yjs state
  operationCount: number;      // Total operations since creation
  lastEditedAt: Date;
  lastEditedBy: string;        // FK to User
  createdAt: Date;
}

interface DocumentVersion {
  id: string;          // UUID
  documentId: string;  // FK to Document
  snapshotS3Key: string;
  opsSegmentS3Key: string;
  operationCount: number;  // Ops in this segment
  triggerType: string;     // 'threshold' | 'manual' | 'restore'
  createdBy: string;       // FK to User
  createdAt: Date;
}

interface ActiveSession {
  // Redis — ephemeral
  documentId: string;
  userId: string;
  cursorPosition: number;
  selectionRange: { from: number; to: number } | null;
  lastSeen: Date;
}
```

### Server WebSocket Handler

```typescript
// Conceptual — not production code, but shows the architecture
import { WebSocketServer } from 'ws';
import { setupWSConnection } from 'y-websocket/bin/utils';
import { S3Client, PutObjectCommand } from '@aws-sdk/client-s3';
import { createClient } from 'redis';

const wss = new WebSocketServer({ server: httpServer });
const redis = createClient();
const s3 = new S3Client({ region: 'us-east-1' });

// Track operation counts per document for snapshot decisions
const opCounts = new Map<string, number>();
const SNAPSHOT_THRESHOLD = 1000;

wss.on('connection', (ws, req) => {
  // Authenticate on connection (not per message)
  const token = extractToken(req);
  const user = verifyJWT(token);
  if (!user) { ws.close(4001, 'Unauthorized'); return; }

  const docId = extractDocId(req.url);

  // y-websocket handles the Yjs sync protocol
  setupWSConnection(ws, req, {
    docName: docId,
    gc: true, // garbage collect deleted content
  });

  // Hook: after each update, check if snapshot is needed
  // (broadcast happens automatically by y-websocket — persist is async)
  ws.on('message', async (message) => {
    const count = (opCounts.get(docId) || 0) + 1;
    opCounts.set(docId, count);

    if (count >= SNAPSHOT_THRESHOLD) {
      opCounts.set(docId, 0);
      await createSnapshot(docId, user.id);
    }
  });

  // Publish presence to Redis
  redis.hSet(`doc:${docId}:presence`, user.id, JSON.stringify({
    name: user.name,
    cursor: null,
    lastSeen: new Date().toISOString()
  }));

  ws.on('close', () => {
    redis.hDel(`doc:${docId}:presence`, user.id);
  });
});
```

---

## Gap Scan

- [x] **Acceptance criteria:**
  - Real-time collaboration: two users edit simultaneously with sub-100ms keystroke propagation (same region) — measurable via WebSocket round-trip monitoring
  - Network resilience: disconnect Wi-Fi for 30 seconds, reconnect, edits merge correctly
  - Version history: can see list of versions, restore to a previous version
  - 100 pages: editor remains responsive (>30fps) with 100-page document with 2 concurrent editors
- [x] **Testing strategy:**
  - Unit tests: Yjs document operations, snapshot/restore logic, auth middleware
  - Integration tests: WebSocket connection lifecycle, document persistence to S3, version history CRUD
  - E2E tests: Two-browser collaboration test (Playwright with two browser contexts), disconnect/reconnect test
  - Performance tests: latency measurement (client-side timestamp in operation → time to appear on other client), document size stress test (50, 100, 200, 500 pages)
  - Manual testing: edit on slow connection (throttled to 3G), edit with packet loss
- [x] **Integration impact:**
  - S3 bucket for document storage
  - Redis instance for presence
  - PostgreSQL for metadata
  - WebSocket requires sticky sessions or single-server deployment for v1
- [x] **Failure modes:**
  - WebSocket server crashes → clients detect disconnect, continue editing locally (IndexedDB), reconnect with exponential backoff, Yjs merges on reconnect
  - S3 write fails → retry with exponential backoff; document state preserved in server memory and client IndexedDB; alert on repeated failure
  - Redis down → cursor presence unavailable (degraded UX, not broken functionality)
  - PostgreSQL down → can't create new documents or view version history, but existing open documents continue working (Yjs operates in memory)
  - Browser crashes → IndexedDB has latest state; reopen browser, document loads from IndexedDB
- [x] **Edge cases:**
  - Two users type in the exact same position simultaneously → CRDT guarantees deterministic ordering (user with lower client ID wins position — both edits preserved)
  - User restores old version while another user is editing → restoration creates a new version; actively editing user sees the document change (Yjs operation, not page reload)
  - Document exceeds 500 pages → no hard limit; performance degradation is gradual. v1 warning at 200 pages: "Large document — performance may be reduced"
  - Snapshot creation fails → operation log continues accumulating; next snapshot will capture all operations. Alert on failure so it doesn't accumulate indefinitely
  - Clock skew between clients → not an issue — Yjs uses logical clocks (Lamport timestamps), not wall clocks
