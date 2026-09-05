import assert from 'node:assert/strict';
import test from 'node:test';

import { ProtocolMessageValidator } from '../../src/protocol/protocol-message-validator.ts';
import {
  APPLICATION_CLOSE_CODES,
  JlcEdaProtocolClient,
  type ProtocolClientDiagnostics,
  type ProtocolClientScheduler,
} from '../../src/transport/protocol-client.ts';
import type {
  TransportConnectedHandler,
  TransportMessageHandler,
  WebSocketTransport,
} from '../../src/transport/websocket-transport.ts';


const SECRET = new Uint8Array(Array.from({ length: 32 }, (_, index) => index));

class ManualScheduler implements ProtocolClientScheduler {
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

  advance(milliseconds: number): void {
    const target = this.#now + milliseconds;
    while (true) {
      const next = [...this.#tasks.entries()]
        .filter(([, task]) => task.due <= target)
        .sort((left, right) => left[1].due - right[1].due || left[0] - right[0])[0];
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

class ReliabilityTransport implements WebSocketTransport {
  readonly sent: string[] = [];
  readonly closeCalls: Array<{ code?: number; reason?: string }> = [];
  registerCount = 0;
  sendFailure = false;
  registerFailure = false;
  closeFailure = false;
  #onMessage?: TransportMessageHandler;
  #onConnected?: TransportConnectedHandler;

  register(
    _connectionId: string,
    _serviceUri: string,
    onMessage: TransportMessageHandler,
    onConnected: TransportConnectedHandler,
  ): void {
    this.registerCount += 1;
    if (this.registerFailure) throw new Error('backend unavailable');
    this.#onMessage = onMessage;
    this.#onConnected = onConnected;
  }

  send(_connectionId: string, data: string): void {
    if (this.sendFailure) throw new Error('WebSocket is already in CLOSING or CLOSED state');
    this.sent.push(data);
  }

  close(_connectionId: string, code?: number, reason?: string): void {
    this.closeCalls.push({ code, reason });
    if (this.closeFailure) throw new DOMException('invalid close code', 'InvalidAccessError');
  }

  async connect(): Promise<void> { await this.#onConnected?.(); }
  async receive(message: unknown): Promise<void> {
    await this.#onMessage?.(JSON.stringify(message));
  }
}

test('backend disappearance stops heartbeat without closing a socket proven dead', async () => {
  const scheduler = new ManualScheduler();
  const transport = new ReliabilityTransport();
  const client = newClient(transport, scheduler, { reconnectDelaysMs: [] });
  const oldSession = await authenticate(client, transport);
  assert.equal(client.sessionId, oldSession);

  transport.sendFailure = true;
  assert.doesNotThrow(() => client.sendHeartbeat());
  assert.equal(client.state, 'reconnect_exhausted');
  assert.equal(client.sessionId, null);
  assert.equal(transport.closeCalls.length, 0);
  const sendsAfterDisconnect = transport.sent.length;
  assert.doesNotThrow(() => client.sendHeartbeat());
  scheduler.advance(60_000);
  assert.equal(transport.sent.length, sendsAfterDisconnect);
  assert.equal(transport.closeCalls.length, 0);
});

test('duplicate disconnect triggers are idempotent', async () => {
  const scheduler = new ManualScheduler();
  const transport = new ReliabilityTransport();
  const client = newClient(transport, scheduler, { reconnectDelaysMs: [] });
  await authenticate(client, transport);
  transport.sendFailure = true;

  client.sendHeartbeat();
  await transport.receive({ kind: 'invalid-after-disconnect' });
  client.sendHeartbeat();

  assert.equal(transport.closeCalls.length, 0);
  assert.equal(client.sessionId, null);
  assert.equal(scheduler.pendingCount, 0);
});

test('transport close failure cannot block cleanup or reconnect scheduling', async () => {
  const scheduler = new ManualScheduler();
  const transport = new ReliabilityTransport();
  const diagnostics: ProtocolClientDiagnostics[] = [];
  const client = newClient(transport, scheduler, {
    reconnectDelaysMs: [500],
    onDiagnostics: (event) => diagnostics.push(event),
  });
  await authenticate(client, transport);
  transport.closeFailure = true;

  client.sendHeartbeat();
  const ping = JSON.parse(transport.sent.at(-1)!) as Record<string, unknown>;
  await transport.receive({
    ...base(),
    kind: 'pong',
    session_id: crypto.randomUUID(),
    reply_to_message_id: ping.message_id,
    nonce: ping.nonce,
  });
  assert.equal(client.state, 'retry_wait');
  assert.equal(client.sessionId, null);
  assert.equal(scheduler.pendingCount, 1);
  assert.equal(transport.closeCalls.length, 1);
  assert.equal(transport.closeCalls[0]!.code, APPLICATION_CLOSE_CODES.sessionInvalid);
  assert.equal(
    diagnostics.some((event) => event.event === 'transport_warning'),
    true,
  );

  transport.closeFailure = false;
  scheduler.advance(500);
  assert.equal(transport.registerCount, 2);
  assert.equal(client.state, 'connecting');
});

test('backend recovery within retry window creates a fresh authenticated session', async () => {
  const scheduler = new ManualScheduler();
  const transport = new ReliabilityTransport();
  const client = newClient(transport, scheduler);
  const oldSession = await authenticate(client, transport);

  transport.sendFailure = true;
  client.sendHeartbeat();
  assert.equal(client.state, 'retry_wait');
  transport.sendFailure = false;
  scheduler.advance(500);
  await transport.connect();
  const newSession = await completeHandshakeAfterInit(client, transport);

  assert.equal(client.state, 'authenticated');
  assert.notEqual(newSession, oldSession);
  assert.equal(client.sessionId, newSession);
  assert.equal(
    scheduler.pendingCount,
    1,
    'only the new heartbeat timer should remain after authentication',
  );
});

test('bounded reconnect emits exhausted state after 0.5s 1s 2s 5s retries', async () => {
  const scheduler = new ManualScheduler();
  const transport = new ReliabilityTransport();
  const diagnostics: ProtocolClientDiagnostics[] = [];
  const client = newClient(transport, scheduler, {
    onDiagnostics: (event) => diagnostics.push(event),
  });
  await authenticate(client, transport);
  transport.sendFailure = true;
  transport.registerFailure = true;
  client.sendHeartbeat();

  for (const delay of [500, 1000, 2000, 5000]) scheduler.advance(delay);

  assert.equal(client.state, 'reconnect_exhausted');
  assert.equal(transport.registerCount, 5);
  assert.equal(scheduler.pendingCount, 0);
  assert.equal(
    diagnostics.some((event) => event.event === 'reconnect_exhausted'),
    true,
  );
});

function newClient(
  transport: ReliabilityTransport,
  scheduler: ManualScheduler,
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
  transport: ReliabilityTransport,
): Promise<string> {
  await transport.connect();
  return completeHandshakeAfterInit(client, transport);
}

async function completeHandshakeAfterInit(
  client: JlcEdaProtocolClient,
  transport: ReliabilityTransport,
): Promise<string> {
  const init = JSON.parse(transport.sent.at(-1)!) as Record<string, unknown>;
  await transport.receive({
    ...base(), kind: 'hello_ack', phase: 'challenge',
    reply_to_message_id: init.message_id,
    challenge_id: crypto.randomUUID(), client_nonce: init.client_nonce,
    server_nonce: nonce(), expires_at: new Date(Date.now() + 10_000).toISOString(),
  });
  const prove = JSON.parse(transport.sent.at(-1)!) as Record<string, unknown>;
  const sessionId = crypto.randomUUID();
  await transport.receive({
    ...base(), kind: 'hello_ack', phase: 'accepted',
    reply_to_message_id: prove.message_id, session_id: sessionId,
    heartbeat_interval_ms: 5000, heartbeat_timeout_ms: 15000,
  });
  return sessionId;
}

function base(): Record<string, unknown> {
  return {
    protocol: 'aia-jlceda', protocol_version: '1.0',
    message_id: crypto.randomUUID(), sent_at: new Date().toISOString(),
    trace_id: crypto.randomUUID(),
  };
}

function nonce(): string {
  const bytes = new Uint8Array(32).fill(11);
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');
}
