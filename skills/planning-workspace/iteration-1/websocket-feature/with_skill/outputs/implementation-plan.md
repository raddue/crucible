# WebSocket Real-Time Notifications Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use crucible:build to implement this plan task-by-task.

**Goal:** Add WebSocket support to the Express API so clients can subscribe to resource-specific event channels (e.g., `order:123:status`) and receive real-time push notifications when those resources change.

**Architecture:** The Express HTTP server is upgraded to support WebSocket connections via the `ws` library, sharing the same underlying HTTP server. A `SubscriptionManager` singleton tracks which clients are subscribed to which channels. When application code needs to broadcast a change, it calls `notifyChannel(channel, payload)`, which fans out to all subscribers. PostgreSQL `LISTEN/NOTIFY` is used as the pub/sub backbone so notifications work across multiple server instances (horizontal scaling).

**Tech Stack:** TypeScript, Express, `ws` (WebSocket library), `pg` (PostgreSQL client for LISTEN/NOTIFY), Jest (testing), `ws` client (for integration tests)

---

### Task 1: Install Dependencies

**Files:**
- Modify: `package.json`

**Step 1: Install ws and its types**

```bash
npm install ws
npm install --save-dev @types/ws
```

**Step 2: Verify installation**

Run: `npm ls ws`
Expected: `ws@x.x.x` appears in the output with no errors.

**Step 3: Commit**

```bash
git add package.json package-lock.json
git commit -m "chore: add ws dependency for WebSocket support"
```

---

### Task 2: WebSocket Channel Types and Interfaces

**Files:**
- Create: `src/websocket/types.ts`
- Test: `tests/websocket/types.test.ts`

**Step 1: Write the failing test**

```typescript
// tests/websocket/types.test.ts
import { parseChannel, isValidChannel, type ClientMessage, type ServerMessage } from '../src/websocket/types';

describe('parseChannel', () => {
  it('parses a valid channel string into parts', () => {
    const result = parseChannel('order:123:status');
    expect(result).toEqual({ resource: 'order', id: '123', event: 'status' });
  });

  it('returns null for an invalid channel string', () => {
    expect(parseChannel('')).toBeNull();
    expect(parseChannel('order')).toBeNull();
    expect(parseChannel('order:123')).toBeNull();
    expect(parseChannel('order::status')).toBeNull();
  });
});

describe('isValidChannel', () => {
  it('returns true for valid channels', () => {
    expect(isValidChannel('order:123:status')).toBe(true);
    expect(isValidChannel('user:abc-def:profile')).toBe(true);
  });

  it('returns false for invalid channels', () => {
    expect(isValidChannel('')).toBe(false);
    expect(isValidChannel('order')).toBe(false);
    expect(isValidChannel('order:123')).toBe(false);
  });
});
```

**Step 2: Run test to verify it fails**

Run: `npx jest tests/websocket/types.test.ts --verbose`
Expected: FAIL with "Cannot find module '../src/websocket/types'"

**Step 3: Write minimal implementation**

```typescript
// src/websocket/types.ts

/** Shape of a parsed channel: resource:id:event */
export interface ChannelParts {
  resource: string;
  id: string;
  event: string;
}

/** Messages the client sends to the server */
export type ClientMessage =
  | { type: 'subscribe'; channel: string }
  | { type: 'unsubscribe'; channel: string }
  | { type: 'ping' };

/** Messages the server sends to the client */
export type ServerMessage =
  | { type: 'subscribed'; channel: string }
  | { type: 'unsubscribed'; channel: string }
  | { type: 'notification'; channel: string; payload: unknown }
  | { type: 'error'; message: string }
  | { type: 'pong' };

const CHANNEL_REGEX = /^[a-zA-Z0-9_-]+:[a-zA-Z0-9_-]+:[a-zA-Z0-9_-]+$/;

/**
 * Parse a channel string like 'order:123:status' into its parts.
 * Returns null if the string is invalid.
 */
export function parseChannel(channel: string): ChannelParts | null {
  if (!CHANNEL_REGEX.test(channel)) {
    return null;
  }
  const [resource, id, event] = channel.split(':');
  return { resource, id, event };
}

/**
 * Returns true if the channel string is well-formed.
 */
export function isValidChannel(channel: string): boolean {
  return parseChannel(channel) !== null;
}
```

**Step 4: Run test to verify it passes**

Run: `npx jest tests/websocket/types.test.ts --verbose`
Expected: PASS (all 4 tests)

**Step 5: Commit**

```bash
git add src/websocket/types.ts tests/websocket/types.test.ts
git commit -m "feat: add WebSocket channel types and parsing utilities"
```

---

### Task 3: SubscriptionManager

**Files:**
- Create: `src/websocket/subscription-manager.ts`
- Test: `tests/websocket/subscription-manager.test.ts`

**Step 1: Write the failing test**

```typescript
// tests/websocket/subscription-manager.test.ts
import { SubscriptionManager } from '../src/websocket/subscription-manager';

describe('SubscriptionManager', () => {
  let manager: SubscriptionManager;

  beforeEach(() => {
    manager = new SubscriptionManager();
  });

  describe('subscribe', () => {
    it('adds a client to a channel', () => {
      const clientId = 'client-1';
      manager.subscribe(clientId, 'order:123:status');
      expect(manager.getSubscribers('order:123:status')).toEqual(new Set(['client-1']));
    });

    it('allows multiple clients on the same channel', () => {
      manager.subscribe('client-1', 'order:123:status');
      manager.subscribe('client-2', 'order:123:status');
      expect(manager.getSubscribers('order:123:status')).toEqual(new Set(['client-1', 'client-2']));
    });

    it('is idempotent for the same client+channel', () => {
      manager.subscribe('client-1', 'order:123:status');
      manager.subscribe('client-1', 'order:123:status');
      expect(manager.getSubscribers('order:123:status').size).toBe(1);
    });
  });

  describe('unsubscribe', () => {
    it('removes a client from a channel', () => {
      manager.subscribe('client-1', 'order:123:status');
      manager.unsubscribe('client-1', 'order:123:status');
      expect(manager.getSubscribers('order:123:status').size).toBe(0);
    });

    it('does nothing if the client was not subscribed', () => {
      expect(() => manager.unsubscribe('client-1', 'order:123:status')).not.toThrow();
    });
  });

  describe('removeClient', () => {
    it('removes a client from all channels', () => {
      manager.subscribe('client-1', 'order:123:status');
      manager.subscribe('client-1', 'user:456:profile');
      manager.removeClient('client-1');
      expect(manager.getSubscribers('order:123:status').size).toBe(0);
      expect(manager.getSubscribers('user:456:profile').size).toBe(0);
    });
  });

  describe('getChannelsForClient', () => {
    it('returns all channels a client is subscribed to', () => {
      manager.subscribe('client-1', 'order:123:status');
      manager.subscribe('client-1', 'user:456:profile');
      const channels = manager.getChannelsForClient('client-1');
      expect(channels).toEqual(new Set(['order:123:status', 'user:456:profile']));
    });

    it('returns an empty set for an unknown client', () => {
      expect(manager.getChannelsForClient('unknown').size).toBe(0);
    });
  });
});
```

**Step 2: Run test to verify it fails**

Run: `npx jest tests/websocket/subscription-manager.test.ts --verbose`
Expected: FAIL with "Cannot find module '../src/websocket/subscription-manager'"

**Step 3: Write minimal implementation**

```typescript
// src/websocket/subscription-manager.ts

/**
 * Tracks which client IDs are subscribed to which channels.
 * Two-way mapping for efficient lookup in both directions.
 */
export class SubscriptionManager {
  /** channel -> Set of clientIds */
  private channelToClients = new Map<string, Set<string>>();
  /** clientId -> Set of channels */
  private clientToChannels = new Map<string, Set<string>>();

  subscribe(clientId: string, channel: string): void {
    if (!this.channelToClients.has(channel)) {
      this.channelToClients.set(channel, new Set());
    }
    this.channelToClients.get(channel)!.add(clientId);

    if (!this.clientToChannels.has(clientId)) {
      this.clientToChannels.set(clientId, new Set());
    }
    this.clientToChannels.get(clientId)!.add(channel);
  }

  unsubscribe(clientId: string, channel: string): void {
    this.channelToClients.get(channel)?.delete(clientId);
    this.clientToChannels.get(clientId)?.delete(channel);
  }

  removeClient(clientId: string): void {
    const channels = this.clientToChannels.get(clientId);
    if (channels) {
      for (const channel of channels) {
        this.channelToClients.get(channel)?.delete(clientId);
      }
      this.clientToChannels.delete(clientId);
    }
  }

  getSubscribers(channel: string): Set<string> {
    return this.channelToClients.get(channel) ?? new Set();
  }

  getChannelsForClient(clientId: string): Set<string> {
    return this.clientToChannels.get(clientId) ?? new Set();
  }
}
```

**Step 4: Run test to verify it passes**

Run: `npx jest tests/websocket/subscription-manager.test.ts --verbose`
Expected: PASS (all 7 tests)

**Step 5: Commit**

```bash
git add src/websocket/subscription-manager.ts tests/websocket/subscription-manager.test.ts
git commit -m "feat: add SubscriptionManager for tracking WebSocket channel subscriptions"
```

---

### Task 4: WebSocket Message Handler

**Files:**
- Create: `src/websocket/message-handler.ts`
- Test: `tests/websocket/message-handler.test.ts`

**Step 1: Write the failing test**

```typescript
// tests/websocket/message-handler.test.ts
import { handleClientMessage } from '../src/websocket/message-handler';
import { SubscriptionManager } from '../src/websocket/subscription-manager';
import type { ServerMessage } from '../src/websocket/types';

describe('handleClientMessage', () => {
  let manager: SubscriptionManager;
  let responses: ServerMessage[];
  const send = (msg: ServerMessage) => { responses.push(msg); };
  const clientId = 'client-1';

  beforeEach(() => {
    manager = new SubscriptionManager();
    responses = [];
  });

  it('handles a subscribe message for a valid channel', () => {
    handleClientMessage(clientId, '{"type":"subscribe","channel":"order:123:status"}', manager, send);
    expect(responses).toEqual([{ type: 'subscribed', channel: 'order:123:status' }]);
    expect(manager.getSubscribers('order:123:status').has(clientId)).toBe(true);
  });

  it('handles an unsubscribe message', () => {
    manager.subscribe(clientId, 'order:123:status');
    handleClientMessage(clientId, '{"type":"unsubscribe","channel":"order:123:status"}', manager, send);
    expect(responses).toEqual([{ type: 'unsubscribed', channel: 'order:123:status' }]);
    expect(manager.getSubscribers('order:123:status').has(clientId)).toBe(false);
  });

  it('handles a ping message', () => {
    handleClientMessage(clientId, '{"type":"ping"}', manager, send);
    expect(responses).toEqual([{ type: 'pong' }]);
  });

  it('returns an error for invalid JSON', () => {
    handleClientMessage(clientId, 'not json', manager, send);
    expect(responses).toEqual([{ type: 'error', message: 'Invalid JSON' }]);
  });

  it('returns an error for an invalid channel', () => {
    handleClientMessage(clientId, '{"type":"subscribe","channel":"bad"}', manager, send);
    expect(responses).toEqual([{ type: 'error', message: 'Invalid channel format. Expected resource:id:event' }]);
  });

  it('returns an error for an unknown message type', () => {
    handleClientMessage(clientId, '{"type":"unknown"}', manager, send);
    expect(responses).toEqual([{ type: 'error', message: 'Unknown message type: unknown' }]);
  });
});
```

**Step 2: Run test to verify it fails**

Run: `npx jest tests/websocket/message-handler.test.ts --verbose`
Expected: FAIL with "Cannot find module '../src/websocket/message-handler'"

**Step 3: Write minimal implementation**

```typescript
// src/websocket/message-handler.ts
import { SubscriptionManager } from './subscription-manager';
import { isValidChannel, type ServerMessage } from './types';

/**
 * Parses a raw WebSocket text message from a client and performs the
 * appropriate action (subscribe, unsubscribe, ping). Sends responses
 * via the provided `send` callback.
 */
export function handleClientMessage(
  clientId: string,
  raw: string,
  manager: SubscriptionManager,
  send: (msg: ServerMessage) => void,
): void {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    send({ type: 'error', message: 'Invalid JSON' });
    return;
  }

  const msg = parsed as Record<string, unknown>;

  switch (msg.type) {
    case 'subscribe': {
      const channel = msg.channel as string;
      if (!isValidChannel(channel)) {
        send({ type: 'error', message: 'Invalid channel format. Expected resource:id:event' });
        return;
      }
      manager.subscribe(clientId, channel);
      send({ type: 'subscribed', channel });
      break;
    }
    case 'unsubscribe': {
      const channel = msg.channel as string;
      manager.unsubscribe(clientId, channel);
      send({ type: 'unsubscribed', channel });
      break;
    }
    case 'ping': {
      send({ type: 'pong' });
      break;
    }
    default: {
      send({ type: 'error', message: `Unknown message type: ${msg.type}` });
    }
  }
}
```

**Step 4: Run test to verify it passes**

Run: `npx jest tests/websocket/message-handler.test.ts --verbose`
Expected: PASS (all 6 tests)

**Step 5: Commit**

```bash
git add src/websocket/message-handler.ts tests/websocket/message-handler.test.ts
git commit -m "feat: add WebSocket client message handler with subscribe/unsubscribe/ping"
```

---

### Task 5: PostgreSQL NOTIFY Bridge

**Files:**
- Create: `src/websocket/pg-notify-bridge.ts`
- Test: `tests/websocket/pg-notify-bridge.test.ts`

**Step 1: Write the failing test**

```typescript
// tests/websocket/pg-notify-bridge.test.ts
import { PgNotifyBridge } from '../src/websocket/pg-notify-bridge';
import { SubscriptionManager } from '../src/websocket/subscription-manager';
import type { Client as PgClient } from 'pg';
import { EventEmitter } from 'events';

/** Minimal mock of pg.Client that emits 'notification' events */
function createMockPgClient(): PgClient & EventEmitter {
  const emitter = new EventEmitter();
  return Object.assign(emitter, {
    connect: jest.fn().mockResolvedValue(undefined),
    query: jest.fn().mockResolvedValue({ rows: [] }),
    end: jest.fn().mockResolvedValue(undefined),
  }) as unknown as PgClient & EventEmitter;
}

describe('PgNotifyBridge', () => {
  let pgClient: ReturnType<typeof createMockPgClient>;
  let manager: SubscriptionManager;
  let sentMessages: Array<{ clientId: string; payload: unknown }>;
  let bridge: PgNotifyBridge;

  beforeEach(async () => {
    pgClient = createMockPgClient();
    manager = new SubscriptionManager();
    sentMessages = [];

    const sendToClient = (clientId: string, payload: unknown) => {
      sentMessages.push({ clientId, payload });
    };

    bridge = new PgNotifyBridge(pgClient as unknown as PgClient, manager, sendToClient);
    await bridge.start();
  });

  afterEach(async () => {
    await bridge.stop();
  });

  it('calls LISTEN on the pg_channel on start', () => {
    expect(pgClient.query).toHaveBeenCalledWith('LISTEN ws_events');
  });

  it('fans out a pg notification to subscribed clients', () => {
    manager.subscribe('client-1', 'order:123:status');
    manager.subscribe('client-2', 'order:123:status');

    pgClient.emit('notification', {
      channel: 'ws_events',
      payload: JSON.stringify({ channel: 'order:123:status', data: { status: 'shipped' } }),
    });

    expect(sentMessages).toEqual([
      { clientId: 'client-1', payload: { type: 'notification', channel: 'order:123:status', payload: { status: 'shipped' } } },
      { clientId: 'client-2', payload: { type: 'notification', channel: 'order:123:status', payload: { status: 'shipped' } } },
    ]);
  });

  it('does not send to clients not subscribed to the channel', () => {
    manager.subscribe('client-1', 'order:999:status');

    pgClient.emit('notification', {
      channel: 'ws_events',
      payload: JSON.stringify({ channel: 'order:123:status', data: { status: 'shipped' } }),
    });

    expect(sentMessages).toEqual([]);
  });

  it('handles malformed notification payloads gracefully', () => {
    pgClient.emit('notification', {
      channel: 'ws_events',
      payload: 'not json',
    });

    // Should not throw, should not send anything
    expect(sentMessages).toEqual([]);
  });
});
```

**Step 2: Run test to verify it fails**

Run: `npx jest tests/websocket/pg-notify-bridge.test.ts --verbose`
Expected: FAIL with "Cannot find module '../src/websocket/pg-notify-bridge'"

**Step 3: Write minimal implementation**

```typescript
// src/websocket/pg-notify-bridge.ts
import type { Client as PgClient } from 'pg';
import type { Notification } from 'pg';
import { SubscriptionManager } from './subscription-manager';
import type { ServerMessage } from './types';

const PG_CHANNEL = 'ws_events';

/**
 * Listens on a PostgreSQL NOTIFY channel and fans out notifications
 * to WebSocket clients via the SubscriptionManager.
 *
 * This enables horizontal scaling: any server instance can NOTIFY,
 * and every server instance LISTENing will forward to its local clients.
 */
export class PgNotifyBridge {
  private handler: (msg: Notification) => void;

  constructor(
    private pgClient: PgClient,
    private manager: SubscriptionManager,
    private sendToClient: (clientId: string, message: ServerMessage) => void,
  ) {
    this.handler = this.onNotification.bind(this);
  }

  async start(): Promise<void> {
    this.pgClient.on('notification', this.handler);
    await this.pgClient.query(`LISTEN ${PG_CHANNEL}`);
  }

  async stop(): Promise<void> {
    this.pgClient.removeListener('notification', this.handler);
    await this.pgClient.query(`UNLISTEN ${PG_CHANNEL}`);
  }

  private onNotification(msg: Notification): void {
    if (msg.channel !== PG_CHANNEL) return;

    let parsed: { channel: string; data: unknown };
    try {
      parsed = JSON.parse(msg.payload ?? '');
    } catch {
      // Malformed payload — drop silently (logged in production)
      return;
    }

    const subscribers = this.manager.getSubscribers(parsed.channel);
    for (const clientId of subscribers) {
      this.sendToClient(clientId, {
        type: 'notification',
        channel: parsed.channel,
        payload: parsed.data,
      });
    }
  }
}

/**
 * Helper to send a notification into the PostgreSQL NOTIFY pipeline.
 * Call this from route handlers or services when a resource changes.
 *
 * Example:
 *   await emitNotification(pool, 'order:123:status', { status: 'shipped' });
 */
export async function emitNotification(
  pgClient: PgClient,
  channel: string,
  data: unknown,
): Promise<void> {
  const payload = JSON.stringify({ channel, data });
  await pgClient.query(`NOTIFY ${PG_CHANNEL}, $1`, [payload]);
}
```

**Step 4: Run test to verify it passes**

Run: `npx jest tests/websocket/pg-notify-bridge.test.ts --verbose`
Expected: PASS (all 4 tests)

**Step 5: Commit**

```bash
git add src/websocket/pg-notify-bridge.ts tests/websocket/pg-notify-bridge.test.ts
git commit -m "feat: add PgNotifyBridge for cross-instance WebSocket notification fan-out"
```

---

### Task 6: WebSocket Server Setup (attach to Express)

**Files:**
- Create: `src/websocket/ws-server.ts`
- Modify: `src/server.ts`
- Test: `tests/websocket/ws-server.test.ts`

**Step 1: Write the failing test**

```typescript
// tests/websocket/ws-server.test.ts
import http from 'http';
import express from 'express';
import WebSocket from 'ws';
import { createWebSocketServer } from '../src/websocket/ws-server';
import { SubscriptionManager } from '../src/websocket/subscription-manager';

describe('WebSocket server', () => {
  let httpServer: http.Server;
  let manager: SubscriptionManager;
  let port: number;

  beforeEach((done) => {
    const app = express();
    httpServer = http.createServer(app);
    manager = new SubscriptionManager();

    createWebSocketServer(httpServer, manager);

    httpServer.listen(0, () => {
      port = (httpServer.address() as { port: number }).port;
      done();
    });
  });

  afterEach((done) => {
    httpServer.close(done);
  });

  it('accepts a WebSocket connection and responds to ping', (done) => {
    const ws = new WebSocket(`ws://localhost:${port}`);

    ws.on('open', () => {
      ws.send(JSON.stringify({ type: 'ping' }));
    });

    ws.on('message', (data) => {
      const msg = JSON.parse(data.toString());
      expect(msg).toEqual({ type: 'pong' });
      ws.close();
      done();
    });
  });

  it('allows subscribing to a channel', (done) => {
    const ws = new WebSocket(`ws://localhost:${port}`);

    ws.on('open', () => {
      ws.send(JSON.stringify({ type: 'subscribe', channel: 'order:123:status' }));
    });

    ws.on('message', (data) => {
      const msg = JSON.parse(data.toString());
      expect(msg).toEqual({ type: 'subscribed', channel: 'order:123:status' });
      // Verify the subscription was registered
      expect(manager.getSubscribers('order:123:status').size).toBe(1);
      ws.close();
      done();
    });
  });

  it('cleans up subscriptions when a client disconnects', (done) => {
    const ws = new WebSocket(`ws://localhost:${port}`);

    ws.on('open', () => {
      ws.send(JSON.stringify({ type: 'subscribe', channel: 'order:123:status' }));
    });

    ws.on('message', () => {
      ws.close();
    });

    ws.on('close', () => {
      // Allow a tick for the server-side 'close' handler to fire
      setTimeout(() => {
        expect(manager.getSubscribers('order:123:status').size).toBe(0);
        done();
      }, 50);
    });
  });
});
```

**Step 2: Run test to verify it fails**

Run: `npx jest tests/websocket/ws-server.test.ts --verbose`
Expected: FAIL with "Cannot find module '../src/websocket/ws-server'"

**Step 3: Write minimal implementation**

```typescript
// src/websocket/ws-server.ts
import http from 'http';
import { WebSocketServer, WebSocket } from 'ws';
import { randomUUID } from 'crypto';
import { SubscriptionManager } from './subscription-manager';
import { handleClientMessage } from './message-handler';
import type { ServerMessage } from './types';

/**
 * Attaches a WebSocket server to an existing HTTP server.
 * Returns the WSS instance (useful for testing or manual broadcast).
 */
export function createWebSocketServer(
  server: http.Server,
  manager: SubscriptionManager,
): WebSocketServer {
  const wss = new WebSocketServer({ server });

  /** Map clientId -> WebSocket, for sending messages by clientId */
  const clients = new Map<string, WebSocket>();

  wss.on('connection', (ws: WebSocket) => {
    const clientId = randomUUID();
    clients.set(clientId, ws);

    const send = (msg: ServerMessage) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(msg));
      }
    };

    ws.on('message', (data: Buffer) => {
      handleClientMessage(clientId, data.toString(), manager, send);
    });

    ws.on('close', () => {
      manager.removeClient(clientId);
      clients.delete(clientId);
    });

    ws.on('error', () => {
      manager.removeClient(clientId);
      clients.delete(clientId);
    });
  });

  return wss;
}

/**
 * Creates a function that sends a ServerMessage to a specific client by ID.
 * Used by PgNotifyBridge to push notifications to the right socket.
 */
export function createClientSender(
  clients: Map<string, WebSocket>,
): (clientId: string, message: ServerMessage) => void {
  return (clientId, message) => {
    const ws = clients.get(clientId);
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(message));
    }
  };
}
```

**Step 4: Run test to verify it passes**

Run: `npx jest tests/websocket/ws-server.test.ts --verbose`
Expected: PASS (all 3 tests)

**Step 5: Commit**

```bash
git add src/websocket/ws-server.ts tests/websocket/ws-server.test.ts
git commit -m "feat: add WebSocket server that attaches to Express HTTP server"
```

---

### Task 7: Barrel Export

**Files:**
- Create: `src/websocket/index.ts`

**Step 1: Create the barrel export file**

```typescript
// src/websocket/index.ts
export { SubscriptionManager } from './subscription-manager';
export { createWebSocketServer, createClientSender } from './ws-server';
export { PgNotifyBridge, emitNotification } from './pg-notify-bridge';
export { parseChannel, isValidChannel } from './types';
export type { ChannelParts, ClientMessage, ServerMessage } from './types';
```

**Step 2: Verify TypeScript compiles**

Run: `npx tsc --noEmit`
Expected: No errors.

**Step 3: Commit**

```bash
git add src/websocket/index.ts
git commit -m "chore: add barrel export for websocket module"
```

---

### Task 8: Integrate into src/server.ts

**Files:**
- Modify: `src/server.ts`

**Step 1: Review the current server.ts**

Read `src/server.ts` end-to-end to understand the current structure. Identify:
- Where `app.listen()` is called (this needs to change to `http.createServer(app)` + `server.listen()`)
- Where the PostgreSQL pool/client is created
- The export pattern

**Step 2: Modify src/server.ts**

Add the following imports at the top of `src/server.ts`:

```typescript
import http from 'http';
import { Client as PgClient } from 'pg';
import {
  SubscriptionManager,
  createWebSocketServer,
  PgNotifyBridge,
} from './websocket';
```

Replace the `app.listen(...)` call with the WebSocket-enabled version. For example, if the current code looks like:

```typescript
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
```

Replace it with:

```typescript
// Create HTTP server wrapping Express so ws can share the port
const httpServer = http.createServer(app);

// WebSocket setup
const subscriptionManager = new SubscriptionManager();
createWebSocketServer(httpServer, subscriptionManager);

// PostgreSQL NOTIFY bridge for cross-instance fan-out
const pgNotifyClient = new PgClient({
  connectionString: process.env.DATABASE_URL,
});

const pgBridge = new PgNotifyBridge(pgNotifyClient, subscriptionManager, (clientId, message) => {
  // sendToClient is handled internally by ws-server; we need to wire it up
  // See Task 9 for the final wiring
});

(async () => {
  await pgNotifyClient.connect();
  await pgBridge.start();
})();

httpServer.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});

// Graceful shutdown
process.on('SIGTERM', async () => {
  await pgBridge.stop();
  await pgNotifyClient.end();
  httpServer.close();
});
```

**Step 3: Verify TypeScript compiles**

Run: `npx tsc --noEmit`
Expected: No errors.

**Step 4: Verify the existing test suite still passes**

Run: `npx jest --verbose`
Expected: All existing tests PASS; no regressions.

**Step 5: Commit**

```bash
git add src/server.ts
git commit -m "feat: integrate WebSocket server and PgNotifyBridge into Express server"
```

---

### Task 9: Wire PgNotifyBridge to WebSocket Clients

The `createWebSocketServer` function currently manages its own internal `clients` map. We need to expose the `sendToClient` callback so `PgNotifyBridge` can push messages to WebSocket clients.

**Files:**
- Modify: `src/websocket/ws-server.ts`
- Modify: `src/server.ts`
- Test: `tests/websocket/ws-server-bridge.test.ts`

**Step 1: Write the failing test**

```typescript
// tests/websocket/ws-server-bridge.test.ts
import http from 'http';
import express from 'express';
import WebSocket from 'ws';
import { createWebSocketServer } from '../src/websocket/ws-server';
import { SubscriptionManager } from '../src/websocket/subscription-manager';

describe('WebSocket server bridge integration', () => {
  let httpServer: http.Server;
  let manager: SubscriptionManager;
  let port: number;
  let sendToClient: (clientId: string, message: unknown) => void;

  beforeEach((done) => {
    const app = express();
    httpServer = http.createServer(app);
    manager = new SubscriptionManager();

    const result = createWebSocketServer(httpServer, manager);
    sendToClient = result.sendToClient;

    httpServer.listen(0, () => {
      port = (httpServer.address() as { port: number }).port;
      done();
    });
  });

  afterEach((done) => {
    httpServer.close(done);
  });

  it('can push a notification to a subscribed client via sendToClient', (done) => {
    const ws = new WebSocket(`ws://localhost:${port}`);

    ws.on('open', () => {
      ws.send(JSON.stringify({ type: 'subscribe', channel: 'order:123:status' }));
    });

    let messageCount = 0;
    ws.on('message', (data) => {
      messageCount++;
      const msg = JSON.parse(data.toString());

      if (messageCount === 1) {
        // First message is the subscribe confirmation
        expect(msg.type).toBe('subscribed');

        // Now push a notification from the server side
        const subscribers = manager.getSubscribers('order:123:status');
        for (const clientId of subscribers) {
          sendToClient(clientId, {
            type: 'notification',
            channel: 'order:123:status',
            payload: { status: 'shipped' },
          });
        }
      }

      if (messageCount === 2) {
        // Second message is the notification
        expect(msg).toEqual({
          type: 'notification',
          channel: 'order:123:status',
          payload: { status: 'shipped' },
        });
        ws.close();
        done();
      }
    });
  });
});
```

**Step 2: Run test to verify it fails**

Run: `npx jest tests/websocket/ws-server-bridge.test.ts --verbose`
Expected: FAIL because `createWebSocketServer` currently returns a `WebSocketServer`, not an object with `sendToClient`.

**Step 3: Update createWebSocketServer to return sendToClient**

Modify `src/websocket/ws-server.ts` so the return type changes:

```typescript
// src/websocket/ws-server.ts
import http from 'http';
import { WebSocketServer, WebSocket } from 'ws';
import { randomUUID } from 'crypto';
import { SubscriptionManager } from './subscription-manager';
import { handleClientMessage } from './message-handler';
import type { ServerMessage } from './types';

export interface WsServerResult {
  wss: WebSocketServer;
  sendToClient: (clientId: string, message: ServerMessage) => void;
}

/**
 * Attaches a WebSocket server to an existing HTTP server.
 * Returns the WSS instance and a sendToClient function for pushing
 * server-initiated messages to specific clients.
 */
export function createWebSocketServer(
  server: http.Server,
  manager: SubscriptionManager,
): WsServerResult {
  const wss = new WebSocketServer({ server });
  const clients = new Map<string, WebSocket>();

  const sendToClient = (clientId: string, message: ServerMessage) => {
    const ws = clients.get(clientId);
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(message));
    }
  };

  wss.on('connection', (ws: WebSocket) => {
    const clientId = randomUUID();
    clients.set(clientId, ws);

    const send = (msg: ServerMessage) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(msg));
      }
    };

    ws.on('message', (data: Buffer) => {
      handleClientMessage(clientId, data.toString(), manager, send);
    });

    ws.on('close', () => {
      manager.removeClient(clientId);
      clients.delete(clientId);
    });

    ws.on('error', () => {
      manager.removeClient(clientId);
      clients.delete(clientId);
    });
  });

  return { wss, sendToClient };
}
```

Also update `src/websocket/index.ts` to export `WsServerResult`:

```typescript
export { createWebSocketServer, type WsServerResult } from './ws-server';
```

Remove the now-unused `createClientSender` export from both files.

**Step 4: Update src/server.ts integration to use the new return value**

Wire `sendToClient` from the `createWebSocketServer` result into the `PgNotifyBridge` constructor:

```typescript
const subscriptionManager = new SubscriptionManager();
const { sendToClient } = createWebSocketServer(httpServer, subscriptionManager);

const pgBridge = new PgNotifyBridge(pgNotifyClient, subscriptionManager, sendToClient);
```

**Step 5: Run all tests to verify everything passes**

Run: `npx jest --verbose`
Expected: ALL tests PASS.

**Step 6: Commit**

```bash
git add src/websocket/ws-server.ts src/websocket/index.ts src/server.ts tests/websocket/ws-server-bridge.test.ts
git commit -m "feat: expose sendToClient from WS server and wire into PgNotifyBridge"
```

---

### Task 10: Notification Helper for Route Handlers

**Files:**
- Create: `src/websocket/notify.ts`
- Test: `tests/websocket/notify.test.ts`

**Step 1: Write the failing test**

```typescript
// tests/websocket/notify.test.ts
import { buildNotifyQuery } from '../src/websocket/notify';

describe('buildNotifyQuery', () => {
  it('builds a NOTIFY query with a JSON payload', () => {
    const { text, values } = buildNotifyQuery('order:123:status', { status: 'shipped' });
    expect(text).toBe('SELECT pg_notify($1, $2)');
    expect(values[0]).toBe('ws_events');
    expect(JSON.parse(values[1] as string)).toEqual({
      channel: 'order:123:status',
      data: { status: 'shipped' },
    });
  });
});
```

**Step 2: Run test to verify it fails**

Run: `npx jest tests/websocket/notify.test.ts --verbose`
Expected: FAIL with "Cannot find module '../src/websocket/notify'"

**Step 3: Write minimal implementation**

```typescript
// src/websocket/notify.ts

const PG_CHANNEL = 'ws_events';

export interface NotifyQuery {
  text: string;
  values: [string, string];
}

/**
 * Builds a parameterized query that sends a NOTIFY on the shared
 * WebSocket events channel. Use this in route handlers:
 *
 *   const query = buildNotifyQuery('order:123:status', { status: 'shipped' });
 *   await pool.query(query.text, query.values);
 *
 * This can be included inside a transaction so the notification is
 * only sent if the transaction commits.
 */
export function buildNotifyQuery(channel: string, data: unknown): NotifyQuery {
  const payload = JSON.stringify({ channel, data });
  return {
    text: 'SELECT pg_notify($1, $2)',
    values: [PG_CHANNEL, payload],
  };
}
```

**Step 4: Run test to verify it passes**

Run: `npx jest tests/websocket/notify.test.ts --verbose`
Expected: PASS

**Step 5: Add export to barrel file**

Add to `src/websocket/index.ts`:

```typescript
export { buildNotifyQuery, type NotifyQuery } from './notify';
```

**Step 6: Commit**

```bash
git add src/websocket/notify.ts tests/websocket/notify.test.ts src/websocket/index.ts
git commit -m "feat: add buildNotifyQuery helper for emitting notifications from route handlers"
```

---

### Task 11: Example Usage in a Route Handler

**Files:**
- Modify: `src/routes/orders.ts` (or whichever route file manages orders)

**Step 1: Review the existing orders route file**

Read `src/routes/orders.ts` to find the handler that updates an order's status (e.g., `PATCH /orders/:id/status` or `PUT /orders/:id`).

**Step 2: Add the notification call**

After the database UPDATE query succeeds (and inside the same transaction if one is used), add:

```typescript
import { buildNotifyQuery } from '../websocket';

// Inside the route handler, after the UPDATE:
const notify = buildNotifyQuery(`order:${req.params.id}:status`, { status: newStatus });
await pool.query(notify.text, notify.values);
```

If the route uses a transaction:

```typescript
await client.query('BEGIN');
await client.query('UPDATE orders SET status = $1 WHERE id = $2', [newStatus, orderId]);
const notify = buildNotifyQuery(`order:${orderId}:status`, { status: newStatus });
await client.query(notify.text, notify.values);
await client.query('COMMIT');
```

**Step 3: Verify TypeScript compiles**

Run: `npx tsc --noEmit`
Expected: No errors.

**Step 4: Verify existing route tests still pass**

Run: `npx jest tests/routes/orders.test.ts --verbose`
Expected: PASS (no regressions).

**Step 5: Commit**

```bash
git add src/routes/orders.ts
git commit -m "feat: emit WebSocket notification on order status change"
```

---

### Task 12: End-to-End Integration Test

**Files:**
- Create: `tests/websocket/e2e.test.ts`

**Step 1: Write the end-to-end test**

```typescript
// tests/websocket/e2e.test.ts
import http from 'http';
import express from 'express';
import WebSocket from 'ws';
import { EventEmitter } from 'events';
import { SubscriptionManager } from '../src/websocket/subscription-manager';
import { createWebSocketServer } from '../src/websocket/ws-server';
import { PgNotifyBridge } from '../src/websocket/pg-notify-bridge';
import type { Client as PgClient } from 'pg';

function createMockPgClient(): PgClient & EventEmitter {
  const emitter = new EventEmitter();
  return Object.assign(emitter, {
    connect: jest.fn().mockResolvedValue(undefined),
    query: jest.fn().mockResolvedValue({ rows: [] }),
    end: jest.fn().mockResolvedValue(undefined),
  }) as unknown as PgClient & EventEmitter;
}

describe('E2E: WebSocket subscription + PG notification', () => {
  let httpServer: http.Server;
  let manager: SubscriptionManager;
  let pgClient: ReturnType<typeof createMockPgClient>;
  let bridge: PgNotifyBridge;
  let port: number;

  beforeEach(async () => {
    const app = express();
    httpServer = http.createServer(app);
    manager = new SubscriptionManager();
    pgClient = createMockPgClient();

    const { sendToClient } = createWebSocketServer(httpServer, manager);
    bridge = new PgNotifyBridge(pgClient as unknown as PgClient, manager, sendToClient);
    await bridge.start();

    await new Promise<void>((resolve) => {
      httpServer.listen(0, resolve);
    });
    port = (httpServer.address() as { port: number }).port;
  });

  afterEach(async () => {
    await bridge.stop();
    await new Promise<void>((resolve) => httpServer.close(() => resolve()));
  });

  it('delivers a PG notification to a subscribed WebSocket client', (done) => {
    const ws = new WebSocket(`ws://localhost:${port}`);

    ws.on('open', () => {
      ws.send(JSON.stringify({ type: 'subscribe', channel: 'order:123:status' }));
    });

    let messageCount = 0;
    ws.on('message', (data) => {
      messageCount++;
      const msg = JSON.parse(data.toString());

      if (messageCount === 1) {
        expect(msg.type).toBe('subscribed');

        // Simulate a PostgreSQL NOTIFY arriving
        pgClient.emit('notification', {
          channel: 'ws_events',
          payload: JSON.stringify({
            channel: 'order:123:status',
            data: { status: 'delivered' },
          }),
        });
      }

      if (messageCount === 2) {
        expect(msg).toEqual({
          type: 'notification',
          channel: 'order:123:status',
          payload: { status: 'delivered' },
        });
        ws.close();
        done();
      }
    });
  });

  it('does not deliver notifications for channels the client is not subscribed to', (done) => {
    const ws = new WebSocket(`ws://localhost:${port}`);

    ws.on('open', () => {
      ws.send(JSON.stringify({ type: 'subscribe', channel: 'order:123:status' }));
    });

    ws.on('message', (data) => {
      const msg = JSON.parse(data.toString());

      if (msg.type === 'subscribed') {
        // Emit a notification for a DIFFERENT channel
        pgClient.emit('notification', {
          channel: 'ws_events',
          payload: JSON.stringify({
            channel: 'order:999:status',
            data: { status: 'cancelled' },
          }),
        });

        // Give it time — if nothing arrives in 200ms, the test passes
        setTimeout(() => {
          ws.close();
          done();
        }, 200);
      }

      if (msg.type === 'notification') {
        done(new Error('Should not have received a notification for order:999'));
      }
    });
  });
});
```

**Step 2: Run the test**

Run: `npx jest tests/websocket/e2e.test.ts --verbose`
Expected: PASS (all 2 tests)

**Step 3: Run the full test suite**

Run: `npx jest --verbose`
Expected: ALL tests PASS.

**Step 4: Commit**

```bash
git add tests/websocket/e2e.test.ts
git commit -m "test: add end-to-end integration test for WebSocket notification pipeline"
```

---

## Summary of Files

| Action | Path |
|--------|------|
| Create | `src/websocket/types.ts` |
| Create | `src/websocket/subscription-manager.ts` |
| Create | `src/websocket/message-handler.ts` |
| Create | `src/websocket/pg-notify-bridge.ts` |
| Create | `src/websocket/ws-server.ts` |
| Create | `src/websocket/notify.ts` |
| Create | `src/websocket/index.ts` |
| Modify | `src/server.ts` |
| Modify | `src/routes/orders.ts` |
| Create | `tests/websocket/types.test.ts` |
| Create | `tests/websocket/subscription-manager.test.ts` |
| Create | `tests/websocket/message-handler.test.ts` |
| Create | `tests/websocket/pg-notify-bridge.test.ts` |
| Create | `tests/websocket/ws-server.test.ts` |
| Create | `tests/websocket/ws-server-bridge.test.ts` |
| Create | `tests/websocket/notify.test.ts` |
| Create | `tests/websocket/e2e.test.ts` |
| Modify | `package.json` (new dependency: `ws`, `@types/ws`) |
