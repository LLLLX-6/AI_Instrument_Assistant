import assert from 'node:assert/strict';
import test from 'node:test';

import { ProtocolMessageValidator } from '../../src/protocol/protocol-message-validator.ts';
import {
  JlcEdaProtocolClient,
  type ProtocolClientDiagnostics,
} from '../../src/transport/protocol-client.ts';
import type {
  TransportConnectedHandler,
  TransportMessageHandler,
  WebSocketTransport,
} from '../../src/transport/websocket-transport.ts';
import { computeProof } from '../../src/transport/hmac.ts';


const SECRET = new Uint8Array(Array.from({ length: 32 }, (_, index) => index));

class FakeTransport implements WebSocketTransport {
  readonly sent: string[] = [];
  readonly registrations: string[] = [];
  closeCount = 0;
  #onMessage?: TransportMessageHandler;
  #onConnected?: TransportConnectedHandler;

  register(
    connectionId: string,
    serviceUri: string,
    onMessage: TransportMessageHandler,
    onConnected: TransportConnectedHandler,
  ): void {
    this.registrations.push(`${connectionId}:${serviceUri}`);
    this.#onMessage = onMessage;
    this.#onConnected = onConnected;
  }

  send(_connectionId: string, data: string): void {
    this.sent.push(data);
  }

  close(): void {
    this.closeCount += 1;
  }

  async connect(): Promise<void> {
    await this.#onConnected?.();
  }

  async receive(message: unknown): Promise<void> {
    await this.#onMessage?.(JSON.stringify(message));
  }
}

test('client completes challenge-response and establishes a session', async () => {
  const transport = new FakeTransport();
  const diagnostics: ProtocolClientDiagnostics[] = [];
  const client = new JlcEdaProtocolClient({
    transport,
    validator: new ProtocolMessageValidator(),
    serviceUri: 'ws://127.0.0.1:49624',
    secret: SECRET,
    onDiagnostics: (event) => diagnostics.push(event),
    autoHeartbeat: false,
    connectTimeoutMs: 60_000,
  });

  client.start();
  await transport.connect();
  const init = JSON.parse(transport.sent.at(-1)!) as Record<string, unknown>;
  assert.equal(init.phase, 'init');
  assert.equal('session_id' in init, false);

  const challenge = base() as Record<string, unknown>;
  Object.assign(challenge, {
    kind: 'hello_ack',
    phase: 'challenge',
    reply_to_message_id: init.message_id,
    challenge_id: crypto.randomUUID(),
    client_nonce: init.client_nonce,
    server_nonce: nonce(7),
    expires_at: new Date(Date.now() + 10_000).toISOString(),
  });
  await transport.receive(challenge);
  const prove = JSON.parse(transport.sent.at(-1)!) as Record<string, unknown>;
  assert.equal(prove.phase, 'prove');
  assert.match(String(prove.proof), /^[A-Za-z0-9_-]{43}$/);

  await transport.receive({
    ...base(),
    kind: 'hello_ack',
    phase: 'accepted',
    reply_to_message_id: prove.message_id,
    session_id: crypto.randomUUID(),
    heartbeat_interval_ms: 5000,
    heartbeat_timeout_ms: 15000,
  });
  assert.equal(client.state, 'authenticated');
  assert.ok(client.sessionId);
  assert.equal(diagnostics.some((event) => event.event === 'authenticated'), true);
  client.stop();
});

test('malformed server message is rejected before handshake dispatch', async () => {
  const transport = new FakeTransport();
  const client = new JlcEdaProtocolClient({
    transport,
    validator: new ProtocolMessageValidator(),
    serviceUri: 'ws://127.0.0.1:49624',
    secret: SECRET,
    autoHeartbeat: false,
    connectTimeoutMs: 60_000,
  });
  client.start();
  await transport.connect();
  await transport.receive({ kind: 'hello_ack', phase: 'challenge' });
  assert.equal(client.state, 'disconnected');
  assert.equal(transport.closeCount, 1);
  client.stop();
});

test('authenticated heartbeat uses session and verifies pong correlation', async () => {
  const transport = new FakeTransport();
  const client = new JlcEdaProtocolClient({
    transport,
    validator: new ProtocolMessageValidator(),
    serviceUri: 'ws://127.0.0.1:49624',
    secret: SECRET,
    autoHeartbeat: false,
    connectTimeoutMs: 60_000,
  });
  client.start();
  await transport.connect();
  const init = JSON.parse(transport.sent.at(-1)!) as Record<string, unknown>;
  const challenge = {
    ...base(), kind: 'hello_ack', phase: 'challenge',
    reply_to_message_id: init.message_id,
    challenge_id: crypto.randomUUID(), client_nonce: init.client_nonce,
    server_nonce: nonce(8), expires_at: new Date(Date.now() + 10_000).toISOString(),
  };
  await transport.receive(challenge);
  const prove = JSON.parse(transport.sent.at(-1)!) as Record<string, unknown>;
  const sessionId = crypto.randomUUID();
  await transport.receive({
    ...base(), kind: 'hello_ack', phase: 'accepted',
    reply_to_message_id: prove.message_id, session_id: sessionId,
    heartbeat_interval_ms: 5000, heartbeat_timeout_ms: 15000,
  });

  client.sendHeartbeat();
  const ping = JSON.parse(transport.sent.at(-1)!) as Record<string, unknown>;
  assert.equal(ping.kind, 'ping');
  assert.equal(ping.session_id, sessionId);
  await transport.receive({
    ...base(), session_id: sessionId, kind: 'pong',
    reply_to_message_id: ping.message_id, nonce: ping.nonce,
  });
  assert.equal(client.state, 'authenticated');
  client.stop();
});

test('HMAC proof matches the Python canonical vector', async () => {
  const proof = await computeProof(SECRET, {
    clientInstanceId: '33333333-3333-4333-8333-333333333333',
    challengeId: '55555555-5555-4555-8555-555555555555',
    clientNonce: 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
    serverNonce: 'BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB',
    expiresAt: '2026-08-23T08:00:11Z',
  });
  assert.equal(proof, '9pCfy9emzR9AqdQnR3cHEdUyYjqG80juEQUDO7-YoPw');
});

test('reconnect backoff is bounded', async () => {
  let registrations = 0;
  const transport: WebSocketTransport = {
    register: () => {
      registrations += 1;
      throw new Error('backend unavailable');
    },
    send: () => undefined,
    close: () => undefined,
  };
  const client = new JlcEdaProtocolClient({
    transport,
    validator: new ProtocolMessageValidator(),
    serviceUri: 'ws://127.0.0.1:49624',
    secret: SECRET,
    reconnectDelaysMs: [1, 1],
    connectTimeoutMs: 60_000,
  });
  client.start();
  await new Promise((resolve) => setTimeout(resolve, 30));
  assert.equal(registrations, 3);
  assert.equal(client.state, 'reconnect_exhausted');
  client.stop();
});

function base(): Record<string, unknown> {
  return {
    protocol: 'aia-jlceda', protocol_version: '1.0',
    message_id: crypto.randomUUID(), sent_at: new Date().toISOString(),
    trace_id: crypto.randomUUID(),
  };
}

function nonce(fill: number): string {
  const bytes = new Uint8Array(32).fill(fill);
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');
}
