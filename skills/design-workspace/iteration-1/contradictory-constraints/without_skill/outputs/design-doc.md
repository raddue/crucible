# Design: Real-Time Collaborative Document Editor

## Overview

This document outlines the design for a real-time collaborative document editor (similar to Google Docs) with offline support, 500-page document handling, and complete version history. The target is sub-100ms keystroke propagation between collaborators. The team is 2 engineers with a 3-month timeline. Both frontend and backend use TypeScript.

## Honest Assessment: Scope vs. Constraints

Before diving into architecture, we need to confront the reality of what's being asked.

**Google Docs** is built by hundreds of engineers over 15+ years. The combination of requirements here — real-time collaboration, offline editing, 500-page documents, complete version history, and sub-100ms latency — represents several PhD-level problems packed into a 3-month timeline for 2 engineers.

Let me be specific about the tensions:

| Requirement | Engineering Effort (Estimated) | Conflict |
|---|---|---|
| Real-time collaboration (OT/CRDT) | 8-12 engineer-months alone | Core feature, can't skip |
| Offline editing + merge back | 4-6 engineer-months | Requires solving the same problems as real-time collab, plus additional sync logic |
| 500-page document support | 2-3 engineer-months | Requires chunking, lazy loading, virtual rendering — conflicts with naive CRDT implementations that hold full doc in memory |
| Complete version history | 2-4 engineer-months | Naive approach (full snapshots) explodes storage with 500-page docs. Efficient approach (operation log + periodic snapshots) is complex |
| Sub-100ms latency | Ongoing optimization | Constrains architecture choices throughout |

**Total estimated effort: 16-25 engineer-months. Available: 6 engineer-months.**

We must scope down. Here's what I recommend.

## Recommended Phased Approach

### Phase 1 (Months 1-3): Ship a viable product

- Real-time collaboration for documents up to ~50 pages
- Basic version history (operation log, no sophisticated snapshotting yet)
- No offline support (defer to Phase 2)
- Sub-100ms latency for same-region collaborators

### Phase 2 (Months 4-6, if applicable): Extend

- Offline editing with conflict merge
- Document size scaling toward 500 pages
- Efficient version history with snapshots

### What's Cut and Why

- **Offline editing (deferred):** Real-time collaboration and offline editing are both hard, and building offline merge on top of a not-yet-stable collaboration engine creates compounding bugs. Get real-time right first.
- **500-page support (reduced to 50 initially):** CRDT memory and performance tuning for massive documents is a separate engineering effort. 50 pages covers 90%+ of real-world collaborative editing use cases.
- **Complete version history (simplified):** Store the operation log. Build time-travel UI later. Don't build snapshot infrastructure yet.

## Real-Time Collaboration Algorithm

### Choice: CRDT over OT

**Recommendation: Use a CRDT (Conflict-free Replicated Data Type), specifically Yjs.**

| Factor | OT (Operational Transform) | CRDT (Yjs) |
|---|---|---|
| Server requirement | Requires central server to transform operations in order | Works peer-to-peer, server optional |
| Offline support | Very difficult — ops must be transformed against missed ops on reconnect | Natural — CRDTs merge by design |
| Implementation complexity | Must implement transform functions for every operation pair | Use Yjs library — battle-tested |
| Performance at scale | Good with small docs | Yjs handles millions of operations efficiently |
| Future offline support | Would require rewriting the sync layer | Already built into the data model |

**Why Yjs specifically:**
- Open-source TypeScript CRDT library with a large community.
- Used in production by Notion, JupyterLab, and others.
- Has provider libraries for WebSocket transport (`y-websocket`), persistence (`y-indexeddb`), and rich text (`y-prosemirror`, `y-tiptap`).
- Its internal encoding is compact — a document with millions of edits can be stored in kilobytes.
- Choosing Yjs dramatically reduces engineering effort from "build a CRDT from scratch" (months) to "integrate a library" (weeks).

### Why Not OT

OT would require a central server to serialize all operations — this adds latency and makes offline support (if we add it later) extremely difficult. OT also requires implementing correct transformation functions for every pair of operation types, which is a notorious source of bugs. Google's OT implementation (used in Google Docs) took years to stabilize.

## Architecture

```
Client (React + TipTap + Yjs)
  |-- y-prosemirror (editor binding)
  |-- y-websocket (WebSocket provider)
  |-- y-indexeddb (local persistence, for Phase 2 offline)
  |
  WebSocket
  |
Server (Node.js + Hocuspocus)
  |-- Hocuspocus (Yjs WebSocket server)
  |-- Document persistence (PostgreSQL + S3)
  |-- Auth middleware (JWT)
  |
PostgreSQL
  |-- Document metadata
  |-- Operation log (for version history)
  |-- User data
```

### Key Technology Choices

- **TipTap:** Rich text editor built on ProseMirror with first-class Yjs integration via `y-prosemirror`. Provides the editing UI, toolbar, formatting, etc.
- **Hocuspocus:** Open-source Yjs WebSocket backend for Node.js. Handles document loading, client connections, awareness (cursor positions), and persistence hooks. Saves us from building the WebSocket server from scratch.
- **PostgreSQL:** Stores document metadata, user data, and the operation log for version history. The Yjs document state itself is stored as a binary blob (Yjs encodes efficiently).

## Sub-100ms Latency

### How It's Achieved

1. **WebSocket transport:** No HTTP overhead. Persistent connection. Operations are sent as soon as they happen.
2. **Yjs delta encoding:** Only the changed bytes are sent, not the full document. A single keystroke is ~30-50 bytes on the wire.
3. **No server transformation required:** Unlike OT, the server doesn't need to transform operations. It receives a delta, broadcasts it to other clients, and persists it. The critical path is: receive bytes -> broadcast bytes. This is sub-millisecond on the server.
4. **Server proximity:** Deploy in the region closest to users. For multi-region, use a WebSocket server per region with Yjs sync between regions (Yjs supports this natively).

### Latency Budget

| Step | Time |
|---|---|
| Client encodes edit | < 1ms |
| Network to server | 10-40ms (same region) |
| Server broadcast | < 1ms |
| Network to other client | 10-40ms (same region) |
| Client applies edit | < 1ms |
| **Total** | **~20-80ms** |

This meets the sub-100ms target for same-region collaborators. Cross-region will be 100-200ms depending on distance — acceptable for most use cases.

## Document Model

### Yjs Document Structure

```typescript
import * as Y from 'yjs';

interface CollaborativeDocument {
  // The Yjs document
  ydoc: Y.Doc;

  // Rich text content (bound to TipTap)
  content: Y.XmlFragment;  // ydoc.getXmlFragment('content')

  // Document metadata (title, etc.)
  meta: Y.Map<any>;  // ydoc.getMap('meta')

  // Comments / annotations
  comments: Y.Array<any>;  // ydoc.getArray('comments')
}
```

### Persistence

Yjs documents are persisted in two forms:

1. **Full document state:** The Yjs binary encoding of the current document state. Stored in PostgreSQL as a `bytea` column (or S3 for very large docs). Updated on every save (debounced, e.g., every 5 seconds of inactivity or every 30 seconds).

2. **Operation log:** Individual updates (deltas) are appended to a log table for version history.

```sql
CREATE TABLE documents (
  id UUID PRIMARY KEY,
  title VARCHAR(500),
  owner_id UUID REFERENCES users(id),
  yjs_state BYTEA,  -- current full Yjs state
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE document_updates (
  id BIGSERIAL PRIMARY KEY,
  document_id UUID REFERENCES documents(id),
  yjs_update BYTEA,  -- individual Yjs update (delta)
  user_id UUID REFERENCES users(id),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_doc_updates_doc_time
  ON document_updates(document_id, created_at);

CREATE TABLE document_snapshots (
  id BIGSERIAL PRIMARY KEY,
  document_id UUID REFERENCES documents(id),
  yjs_state BYTEA,
  snapshot_at TIMESTAMPTZ DEFAULT NOW(),
  update_id BIGINT REFERENCES document_updates(id)  -- the update this snapshot was taken at
);
```

## Version History

### Strategy: Operation Log + Periodic Snapshots

Storing full document snapshots for every edit of a 500-page document would be enormously wasteful. Instead:

1. **Every edit is logged** as a Yjs update (delta) in `document_updates`. These are tiny (bytes to kilobytes).
2. **Periodic snapshots** are taken of the full document state (e.g., every 100 updates or every hour). Stored in `document_snapshots`.
3. **To reconstruct any point in time:** Find the nearest snapshot before the target time, then replay updates forward to the exact point.

This is conceptually similar to how databases use WAL (write-ahead logs) + checkpoints.

### Version History UI

- Show a timeline of edits with timestamps and author attribution.
- Allow jumping to any point in time by replaying from the nearest snapshot.
- For Phase 1, this is a read-only "time travel" view. Full restore/branching is Phase 2.

## Scaling for Large Documents (Future: 500 Pages)

For Phase 1 (50-page target), the naive approach works: load the entire Yjs document into memory on the server and client.

For Phase 2 (500 pages), we'd need:

1. **Chunked loading on the client:** Only load the visible portion of the document into the editor. Use virtualized rendering (similar to how VS Code handles large files).
2. **Sub-documents in Yjs:** Yjs supports sub-documents (`Y.Doc` inside `Y.Doc`). Each "chunk" (e.g., 10 pages) could be a sub-document, loaded on demand.
3. **Server-side:** Hocuspocus can be configured to load sub-documents independently, so the server doesn't hold entire 500-page documents in memory for every connection.

This is explicitly deferred because it requires significant work to get the chunking boundaries right (what happens when a user types at the boundary between two chunks?).

## Offline Support (Phase 2)

When we add offline in Phase 2, the architecture is ready because we chose CRDTs:

1. **y-indexeddb** persists the Yjs document to the browser's IndexedDB.
2. Edits made offline are applied to the local Yjs document.
3. When the user comes back online, the Yjs WebSocket provider reconnects and automatically syncs — the CRDT merge handles conflicts by design.
4. No special conflict resolution logic needed. Two users can type in the same paragraph simultaneously (online or offline), and the CRDT guarantees convergence.

The main challenge is UX: showing the user clearly that they're offline, what's unsynced, and resolving any *semantic* conflicts (e.g., two users rewrote the same paragraph with different intent — the CRDT merges the characters, but the meaning might be garbled). This requires human review and is a UX problem, not a data problem.

## Authentication & Authorization

- **JWT-based auth** with short-lived tokens.
- Document-level permissions: `owner`, `editor`, `viewer`.
- The WebSocket connection authenticates via a token in the initial handshake.
- Hocuspocus has built-in auth hooks for this.

```typescript
// Hocuspocus auth hook
const server = new Hocuspocus({
  async onAuthenticate({ token, documentName }) {
    const user = verifyJWT(token);
    const permission = await getPermission(user.id, documentName);
    if (!permission || permission === 'viewer') {
      throw new Error('Not authorized to edit');
    }
    return { user };
  }
});
```

## Project Plan for 2 Engineers (3 Months)

### Month 1: Foundation
- **Engineer 1:** Set up TipTap + Yjs integration. Build the editor UI with basic formatting (bold, italic, headings, lists, images). Get real-time collaboration working locally.
- **Engineer 2:** Set up Hocuspocus server with PostgreSQL persistence. Auth system (JWT). Document CRUD API. WebSocket infrastructure.
- **End of month:** Two users can open the same document and see each other's edits in real time.

### Month 2: Features & Polish
- **Engineer 1:** Cursor awareness (show other users' cursor positions and selections). Version history UI (timeline view). Document sharing UI.
- **Engineer 2:** Operation logging for version history. Snapshot generation. Performance testing and optimization. Document listing and search.
- **End of month:** Feature-complete for Phase 1 scope.

### Month 3: Hardening
- **Both engineers:** Load testing, bug fixing, edge cases (network disconnection handling, reconnection, stale state). Security review. Deployment. Documentation.
- **End of month:** Production-ready for Phase 1.

### What This Delivers

A collaborative editor where:
- Multiple users edit documents in real time with sub-100ms latency (same region).
- Documents up to ~50 pages work smoothly.
- Basic version history with time-travel view.
- Document sharing with permissions.
- Solid reconnection handling (if you lose connection briefly, you don't lose work).

### What This Doesn't Deliver (Deferred)

- True offline editing (requires Phase 2).
- 500-page document support (requires Phase 2).
- Full version history with branching/restore (simplified version only).
- Comments and suggestions (could be Month 2 stretch goal).

## Technology Stack Summary

| Component | Technology |
|---|---|
| Editor | TipTap (ProseMirror-based) |
| Real-time collaboration | Yjs (CRDT) |
| Editor-CRDT binding | y-prosemirror |
| WebSocket server | Hocuspocus |
| Backend framework | Express or Fastify (Node.js) |
| Database | PostgreSQL |
| Future offline storage | IndexedDB via y-indexeddb |
| Language | TypeScript throughout |
| Deployment | Docker + any cloud provider |

## Risks

1. **Yjs performance with large documents:** We're betting on Yjs handling our scale. If we hit performance walls before 50 pages, we'll need to investigate sub-document chunking earlier than planned. Mitigation: performance testing in Month 2.

2. **Hocuspocus stability:** It's open source with a smaller community than Yjs itself. If we hit bugs, we may need to fork or patch. Mitigation: review source code early, evaluate alternatives (build custom WebSocket server using y-websocket directly).

3. **Scope creep:** The user's requirements already exceed what 2 engineers can deliver in 3 months. The phased approach only works if Phase 1 is genuinely accepted as the initial deliverable. Mitigation: align on Phase 1 scope with stakeholders before starting.

## Summary

Key design decisions:

1. **Scope reduction is mandatory** — the full requirements represent 16-25 engineer-months of work for a 6 engineer-month budget. Phase 1 delivers real-time collaboration for reasonable document sizes; offline and large doc support are Phase 2.
2. **Yjs (CRDT) over OT** — better fit for eventual offline support, no central server bottleneck, and the Yjs library eliminates months of from-scratch implementation.
3. **TipTap + Hocuspocus** — leverages the Yjs ecosystem with production-ready editor and server components.
4. **Operation log + periodic snapshots** for version history — avoids the storage explosion of full-document snapshots for large documents.
5. **Sub-100ms latency achieved** through WebSocket transport, delta-only updates, and no server-side transformation requirement.
