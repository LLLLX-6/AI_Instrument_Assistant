import assert from 'node:assert/strict';
import test from 'node:test';

import { ProtocolMessageValidator } from '../../src/protocol/protocol-message-validator.ts';
import {
  JlcEdaProtocolClient,
  type ProtocolClientScheduler,
} from '../../src/transport/protocol-client.ts';
import type {
  TransportConnectedHandler,
  TransportMessageHandler,
  WebSocketTransport,
} from '../../src/transport/websocket-transport.ts';


const SECRET = new Uint8Array(Array.from({ length: 32 }, (_, index) => index));

class QueuedScheduler implements ProtocolClientScheduler {
  readonly #tasks = new Map<number, { due: number; callback: () => void }>();
  #now = 0;
  #nextId = 1;

  setTimeout(callback: () => void, delayMs: number): number {
    const id = this.#nextId++;
    this.#tasks.set(id, { due: this.#now + delayMs, callback });
    return id;
  }

  clearTimeout(handle: unknown): void {
    if (typeof handle === 'number') this.#tasks.delete(handle);
  }

  captureNextCallback(): () => void {
    const next = [...this.#tasks.values()].sort((a, b) => a.due - b.due)[0];
    assert.ok(next, 'expected a queued callback');
    return next.callback;
  }

  advance(milliseconds: number): void {
    const target = this.#now + milliseconds;
    while (true) {
      const next = [...this.#tasks.entries()]
        .filter(([, task]) => task.due <= target)
        .sort((a, b) => a[1].due - b[1].due || a[0] - b[0])[0];
      if (next === undefined) break;
      const [id, task] = next;
      this.#tasks.delete(id);
      this.#now = task.due;
      task.callback();
    }
    this.#now = target;
  }

  get pendingCount(): number { return this.#tasks.size; }
}

interface Registration {
  readonly id: string;
  readonly uri: string;
  readonly onMessage: TransportMessageHandler;
  readonly onConnected: TransportConnectedHandler;
}

class HostProbeTransport implements WebSocketTransport {
  readonly registrations: Registration[] = [];
  readonly sent: Array<{ id: string; data: string }> = [];
  readonly closes: Array<{ id: string; code?: number }> = [];
  sendFailure = false;
  registerFailure = false;

  register(
    id: string,
    uri: string,
    onMessage: TransportMessageHandler,
    onConnected: TransportConnectedHandler,
  ): void {
    if (this.registerFailure) throw new Error('connection registration failed');
    this.registrations.push({ id, uri, onMessage, onConnected });
  }

  send(id: string, data: string): void {
    if (this.sendFailure) throw new Error('socket dead');
    this.sent.push({ id, data });
  }

  close(id: string, code?: number): void {
    this.closes.push({ id, code });
  }

  fireConnected(attempt: number): void | Promise<void> {
    return this.registrations[attempt]!.onConnected();
  }

  fireMessage(attempt: number, message: unknown): void | Promise<void> {
    return this.registrations[attempt]!.onMessage(JSON.stringify(message));
  }
}

test('connect attempt timeout never pretends socket opened and never closes unopened socket', () => {
  const scheduler = new QueuedScheduler();
  const transport = new HostProbeTransport();
  const client = createClient(transport, scheduler, {
    connectTimeoutMs: 100,
    reconnectDelaysMs: [500],
  });

  assert.equal(client.state, 'connecting');
  assert.equal(transport.sent.length, 0);
  scheduler.advance(100);

  assert.equal(client.state, 'retry_wait');
  assert.equal(transport.sent.length, 0);
  assert.equal(transport.closes.length, 0);
});

test('registration failure before connected callback never closes an unopened socket', () => {
  const scheduler = new QueuedScheduler();
  const transport = new HostProbeTransport();
  transport.registerFailure = true;
  const client = createClient(transport, scheduler, { reconnectDelaysMs: [500] });

  assert.equal(client.state, 'retry_wait');
  assert.equal(transport.sent.length, 0);
  assert.equal(transport.closes.length, 0);
  assert.equal(scheduler.pendingCount, 1);
});

test('each logical reconnect uses isolated physical WebSocket attempt id on same endpoint', () => {
  const scheduler = new QueuedScheduler();
  const transport = new HostProbeTransport();
  createClient(transport, scheduler, { connectTimeoutMs: 100 });

  scheduler.advance(100);
  scheduler.advance(500);

  assert.equal(transport.registrations.length, 2);
  assert.notEqual(transport.registrations[0]!.id, transport.registrations[1]!.id);
  assert.equal(transport.registrations[0]!.uri, 'ws://127.0.0.1:49624');
  assert.equal(transport.registrations[1]!.uri, 'ws://127.0.0.1:49624');
});

test('late connected callback from stale generation is a no-op', () => {
  const scheduler = new QueuedScheduler();
  const transport = new HostProbeTransport();
  const client = createClient(transport, scheduler, { connectTimeoutMs: 100 });
  scheduler.advance(100);
  scheduler.advance(500);
  const before = transport.sent.length;

  const returned = transport.fireConnected(0);

  assert.equal(returned, undefined);
  assert.equal(transport.sent.length, before);
  assert.equal(client.state, 'connecting');
});

test('late message callback from stale generation is a no-op', async () => {
  const scheduler = new QueuedScheduler();
  const transport = new HostProbeTransport();
  const client = createClient(transport, scheduler, { connectTimeoutMs: 100 });
  scheduler.advance(100);
  scheduler.advance(500);

  await transport.fireMessage(0, { invalid: true });

  assert.equal(client.state, 'connecting');
  assert.equal(transport.closes.length, 0);
});

test('queued old heartbeat cannot send after transport loss begins', async () => {
  const scheduler = new QueuedScheduler();
  const transport = new HostProbeTransport();
  const client = createClient(transport, scheduler, { reconnectDelaysMs: [] });
  await authenticate(client, transport, 0);
  const queuedHeartbeat = scheduler.captureNextCallback();
  transport.sendFailure = true;
  client.sendHeartbeat();
  const sendCount = transport.sent.length;

  queuedHeartbeat();

  assert.equal(client.state, 'reconnect_exhausted');
  assert.equal(transport.sent.length, sendCount);
  assert.equal(transport.closes.length, 0, 'send failure proves socket dead');
});

test('one physical attempt can be closed at most once by duplicate local failures', async () => {
  const scheduler = new QueuedScheduler();
  const transport = new HostProbeTransport();
  const client = createClient(transport, scheduler);
  await authenticate(client, transport, 0);
  client.sendHeartbeat();
  const ping = JSON.parse(transport.sent.at(-1)!.data) as Record<string, unknown>;
  const invalidPong = {
    ...base(), kind: 'pong', session_id: crypto.randomUUID(),
    reply_to_message_id: ping.message_id, nonce: ping.nonce,
  };

  await transport.fireMessage(0, invalidPong);
  await transport.fireMessage(0, invalidPong);

  assert.equal(transport.closes.length, 1);
  assert.equal(client.state, 'retry_wait');
});

test('successful backend restart reconnects on same configured endpoint with fresh session', async () => {
  const scheduler = new QueuedScheduler();
  const transport = new HostProbeTransport();
  const client = createClient(transport, scheduler, { connectTimeoutMs: 100 });
  await authenticate(client, transport, 0);
  const oldSession = client.sessionId;
  transport.sendFailure = true;
  client.sendHeartbeat();
  transport.sendFailure = false;
  scheduler.advance(500);
  const currentAttempt = transport.registrations.length - 1;
  await authenticate(client, transport, currentAttempt);

  assert.equal(client.state, 'authenticated');
  assert.notEqual(client.sessionId, oldSession);
  assert.equal(transport.registrations[currentAttempt]!.uri, 'ws://127.0.0.1:49624');
  assert.equal(scheduler.pendingCount, 1);
});

test('repeated reconnect cycles do not accumulate heartbeat or retry timers', async () => {
  const scheduler = new QueuedScheduler();
  const transport = new HostProbeTransport();
  const client = createClient(transport, scheduler);
  await authenticate(client, transport, 0);

  for (const attempt of [1, 2]) {
    transport.sendFailure = true;
    client.sendHeartbeat();
    assert.equal(scheduler.pendingCount, 1, 'only one retry timer may remain');
    transport.sendFailure = false;
    scheduler.advance(500);
    await authenticate(client, transport, attempt);
    assert.equal(scheduler.pendingCount, 1, 'only one heartbeat timer may remain');
  }

  assert.equal(transport.registrations.length, 3);
  assert.equal(client.state, 'authenticated');
});

function createClient(
  transport: HostProbeTransport,
  scheduler: QueuedScheduler,
  overrides: Partial<ConstructorParameters<typeof JlcEdaProtocolClient>[0]> = {},
): JlcEdaProtocolClient {
  const client = new JlcEdaProtocolClient({
    transport,
    validator: new ProtocolMessageValidator(),
    serviceUri: 'ws://127.0.0.1:49624',
    secret: SECRET,
    scheduler,
    connectTimeoutMs: 60_000,
    ...overrides,
  });
  client.start();
  return client;
}

async function authenticate(
  client: JlcEdaProtocolClient,
  transport: HostProbeTransport,
  attempt: number,
): Promise<void> {
  assert.equal(transport.fireConnected(attempt), undefined);
  const init = JSON.parse(transport.sent.at(-1)!.data) as Record<string, unknown>;
  assert.equal(init.phase, 'init');
  await transport.fireMessage(attempt, {
    ...base(), kind: 'hello_ack', phase: 'challenge',
    reply_to_message_id: init.message_id,
    challenge_id: crypto.randomUUID(), client_nonce: init.client_nonce,
    server_nonce: nonce(), expires_at: new Date(Date.now() + 10_000).toISOString(),
  });
  const prove = JSON.parse(transport.sent.at(-1)!.data) as Record<string, unknown>;
  await transport.fireMessage(attempt, {
    ...base(), kind: 'hello_ack', phase: 'accepted',
    reply_to_message_id: prove.message_id, session_id: crypto.randomUUID(),
    heartbeat_interval_ms: 5000, heartbeat_timeout_ms: 15000,
  });
  assert.equal(client.state, 'authenticated');
}

function base(): Record<string, unknown> {
  return {
    protocol: 'aia-jlceda', protocol_version: '1.0',
    message_id: crypto.randomUUID(), sent_at: new Date().toISOString(),
    trace_id: crypto.randomUUID(),
  };
}

function nonce(): string {
  const bytes = new Uint8Array(32).fill(13);
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');
}
