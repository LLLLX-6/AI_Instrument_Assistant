import assert from 'node:assert/strict';
import test from 'node:test';

import { ProtocolMessageValidator } from '../../src/protocol/protocol-message-validator.ts';
import {
  JlcEdaProtocolClient,
  type ProtocolRequestDispatcher,
} from '../../src/transport/protocol-client.ts';
import type {
  TransportConnectedHandler,
  TransportMessageHandler,
  WebSocketTransport,
} from '../../src/transport/websocket-transport.ts';


const SECRET = new Uint8Array(Array.from({ length: 32 }, (_, index) => index));

class FakeTransport implements WebSocketTransport {
  readonly sent: string[] = [];
  closeCount = 0;
  #onMessage?: TransportMessageHandler;
  #onConnected?: TransportConnectedHandler;

  register(
    _id: string, _uri: string, onMessage: TransportMessageHandler,
    onConnected: TransportConnectedHandler,
  ): void {
    this.#onMessage = onMessage;
    this.#onConnected = onConnected;
  }
  send(_id: string, data: string): void { this.sent.push(data); }
  close(): void { this.closeCount += 1; }
  async connect(): Promise<void> { await this.#onConnected?.(); }
  async receive(value: unknown): Promise<void> {
    await this.#onMessage?.(JSON.stringify(value));
  }
}

test('authenticated business request produces correlated current-session response', async () => {
  const transport = new FakeTransport();
  const dispatcher: ProtocolRequestDispatcher = {
    async dispatch() {
      return {
        status: 'error',
        error: { code: 'no_active_document', message: 'No active document.' },
      };
    },
  };
  const client = new JlcEdaProtocolClient({
    transport, validator: new ProtocolMessageValidator(),
    serviceUri: 'ws://127.0.0.1:49624', secret: SECRET,
    autoHeartbeat: false, connectTimeoutMs: 60_000, requestDispatcher: dispatcher,
  });
  const sessionId = await authenticate(client, transport);
  const request: Record<string, unknown> = {
    ...base(), session_id: sessionId, kind: 'request',
    operation: 'eda.document.get_active', payload: {},
  };

  await transport.receive(request);

  const response = JSON.parse(transport.sent.at(-1)!) as Record<string, unknown>;
  assert.equal(response.kind, 'response');
  assert.equal(response.operation, request.operation);
  assert.equal(response.reply_to_message_id, request.message_id);
  assert.equal(response.session_id, sessionId);
  assert.equal(response.status, 'error');
  client.stop();
});

test('response from an old connection generation is never sent', async () => {
  const transport = new FakeTransport();
  let resolveDispatch: (() => void) | undefined;
  const dispatcher: ProtocolRequestDispatcher = {
    async dispatch() {
      await new Promise<void>((resolve) => { resolveDispatch = resolve; });
      return {
        status: 'error',
        error: { code: 'no_active_document', message: 'No active document.' },
      };
    },
  };
  const client = new JlcEdaProtocolClient({
    transport, validator: new ProtocolMessageValidator(),
    serviceUri: 'ws://127.0.0.1:49624', secret: SECRET,
    autoHeartbeat: false, connectTimeoutMs: 60_000, requestDispatcher: dispatcher,
  });
  const sessionId = await authenticate(client, transport);
  const sentBefore = transport.sent.length;
  const receive = transport.receive({
    ...base(), session_id: sessionId, kind: 'request',
    operation: 'eda.document.get_active', payload: {},
  });
  await Promise.resolve();
  client.stop();
  resolveDispatch?.();
  await receive;

  assert.equal(transport.sent.length, sentBefore);
});

test('business request with the wrong session is rejected before dispatch', async () => {
  const transport = new FakeTransport();
  let dispatchCount = 0;
  const client = new JlcEdaProtocolClient({
    transport, validator: new ProtocolMessageValidator(),
    serviceUri: 'ws://127.0.0.1:49624', secret: SECRET,
    autoHeartbeat: false, connectTimeoutMs: 60_000,
    reconnectDelaysMs: [],
    requestDispatcher: {
      async dispatch() {
        dispatchCount += 1;
        return { status: 'error', error: { code: 'internal_error', message: 'no' } };
      },
    },
  });
  await authenticate(client, transport);

  await transport.receive({
    ...base(), session_id: crypto.randomUUID(), kind: 'request',
    operation: 'eda.document.get_active', payload: {},
  });

  assert.equal(dispatchCount, 0);
  assert.equal(client.state, 'reconnect_exhausted');
  assert.equal(transport.closeCount, 1);
  client.stop();
});

test('pre-auth business request is rejected before dispatch', async () => {
  const transport = new FakeTransport();
  let dispatchCount = 0;
  const client = new JlcEdaProtocolClient({
    transport, validator: new ProtocolMessageValidator(),
    serviceUri: 'ws://127.0.0.1:49624', secret: SECRET,
    autoHeartbeat: false, connectTimeoutMs: 60_000,
    reconnectDelaysMs: [],
    requestDispatcher: {
      async dispatch() {
        dispatchCount += 1;
        return { status: 'error', error: { code: 'internal_error', message: 'no' } };
      },
    },
  });
  client.start();
  await transport.connect();

  await transport.receive({
    ...base(), session_id: crypto.randomUUID(), kind: 'request',
    operation: 'eda.document.get_active', payload: {},
  });

  assert.equal(dispatchCount, 0);
  assert.equal(client.state, 'reconnect_exhausted');
  client.stop();
});

async function authenticate(
  client: JlcEdaProtocolClient,
  transport: FakeTransport,
): Promise<string> {
  client.start();
  await transport.connect();
  const init = JSON.parse(transport.sent.at(-1)!) as Record<string, unknown>;
  const challenge = {
    ...base(), kind: 'hello_ack', phase: 'challenge',
    reply_to_message_id: init.message_id, challenge_id: crypto.randomUUID(),
    client_nonce: init.client_nonce, server_nonce: nonce(7),
    expires_at: new Date(Date.now() + 10_000).toISOString(),
  };
  await transport.receive(challenge);
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

function nonce(fill: number): string {
  const bytes = new Uint8Array(32).fill(fill);
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');
}
