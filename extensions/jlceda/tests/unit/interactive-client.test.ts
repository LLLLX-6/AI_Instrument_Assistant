import assert from 'node:assert/strict';
import test from 'node:test';

import { canonicalInteractiveProofPayload } from '../../src/interaction/interactive-hmac.ts';
import {
  InteractiveClient,
  type InteractiveClientClock,
  type InteractiveTransport,
} from '../../src/interaction/interactive-client.ts';

class FakeTransport implements InteractiveTransport {
  registrations: Array<{ id: string; uri: string }> = [];
  sent: string[] = [];
  closes = 0;
  message: ((data: string) => void) | null = null;
  connected: (() => void) | null = null;
  register(id: string, uri: string, onMessage: (data: string) => void, onConnected: () => void): void {
    this.registrations.push({ id, uri }); this.message = onMessage; this.connected = onConnected;
  }
  send(_id: string, data: string): void { this.sent.push(data); }
  close(): void { this.closes += 1; }
}

const clock: InteractiveClientClock = {
  now: () => new Date('2026-09-12T08:00:00Z'),
  setTimeout: () => 1,
  clearTimeout: () => undefined,
};

test('interactive client uses production auth v1 then exact interactive hello', async () => {
  const transport = new FakeTransport();
  const states: string[] = [];
  const client = new InteractiveClient({
    transport, endpoint: { host: '127.0.0.1', port: 49626 }, secret: new Uint8Array(32).fill(7),
    clientInstanceId: '11111111-1111-4111-8111-111111111111', clock,
    onState: (state) => states.push(state),
  });
  client.start(); transport.connected?.();
  await transport.message?.(JSON.stringify({
    protocol: 'aia-interactive-auth/v1', phase: 'challenge',
    challenge_id: '22222222-2222-4222-8222-222222222222', server_nonce: 'a'.repeat(43),
    expires_at: '2026-09-12T08:01:00Z',
  }));
  assert.equal(JSON.parse(transport.sent[0]!).protocol, 'aia-interactive-auth/v1');
  transport.message?.(JSON.stringify({ protocol: 'aia-interactive-auth/v1', phase: 'accepted' }));
  assert.equal(JSON.parse(transport.sent[1]!).message_type, 'hello');
  assert.deepEqual(states.slice(0, 2), ['CONNECTING', 'AUTH_REQUIRED']);
  assert.equal(new TextDecoder().decode(canonicalInteractiveProofPayload({
    clientInstanceId: 'c', challengeId: 'i', clientNonce: 'n', serverNonce: 's', expiresAt: 'e',
  })).split('\n')[0], 'aia-interactive');
});

test('accepted hello requires JLCEDA kind state and authoritative snapshot before connected', () => {
  const transport = new FakeTransport();
  const states: string[] = [];
  const client = new InteractiveClient({
    transport, endpoint: { host: '127.0.0.1', port: 49626 }, secret: new Uint8Array(32).fill(7),
    clientInstanceId: '11111111-1111-4111-8111-111111111111', clock,
    onState: (state) => states.push(state),
  });
  client.start(); transport.connected?.();
  transport.message?.(JSON.stringify({ protocol: 'aia-interactive-auth/v1', phase: 'accepted' }));
  transport.message?.(JSON.stringify({
    protocol: 'aia-interactive/v1', message_id: '33333333-3333-4333-8333-333333333333',
    sent_at: '2026-09-12T08:00:00Z', message_type: 'hello_ack', accepted: true,
    selected_version: 'aia-interactive/v1', application_generation: '44444444-4444-4444-8444-444444444444',
    connection_id: '55555555-5555-4555-8555-555555555555', connection_generation: 1,
    session_id: '66666666-6666-4666-8666-666666666666', current_event_cursor: 1, reason_code: null,
  }));
  assert.equal(client.state, 'SYNCHRONIZING');
  assert.notEqual(client.state, 'CONNECTED');
  transport.message?.(JSON.stringify(snapshotEvent()));
  assert.equal(client.state, 'CONNECTED');
  assert.equal(client.snapshot?.application_generation, '44444444-4444-4444-8444-444444444444');
});

test('explicit snapshot waiter is registered before a fast localhost reply', async () => {
  const transport = new FakeTransport();
  const client = connectedClient(transport);
  const originalSend = transport.send.bind(transport);
  transport.send = (id, data) => {
    originalSend(id, data);
    if (JSON.parse(data).phase === 'snapshot_request') void transport.message?.(JSON.stringify(snapshotEvent(2)));
  };
  const snapshot = await client.refreshSnapshot();
  assert.equal(snapshot.event_cursor, 2);
  assert.equal(client.diagnostics.snapshotWaiterPresentCount, 1);
  assert.equal(client.diagnostics.snapshotWaiterResolvedCount, 1);
  assert.equal(client.diagnostics.snapshotWaiterTimeoutCount, 0);
});

test('explicit snapshot waiter resolves before a non-authoritative snapshot observer can fail', async () => {
  const transport = new FakeTransport();
  let observations = 0;
  const client = connectedClient(transport, () => {
    observations += 1;
    if (observations === 2) throw new Error('raw observer failure');
  });
  const pending = client.refreshSnapshot();
  await assert.doesNotReject(async () => {
    await transport.message?.(JSON.stringify(snapshotEvent(2)));
  });
  assert.equal((await pending).event_cursor, 2);
  assert.equal(client.diagnostics.snapshotWaiterResolvedCount, 1);
  assert.equal(client.diagnostics.snapshotObserverFailureCount, 1);
});

test('single-waiter V1 rejects a second explicit request without replacing the first', async () => {
  const transport = new FakeTransport();
  const client = connectedClient(transport);
  const first = client.refreshSnapshot();
  await assert.rejects(client.refreshSnapshot(), /SNAPSHOT_WAITER_ALREADY_PENDING/);
  await transport.message?.(JSON.stringify(snapshotEvent(2)));
  assert.equal((await first).event_cursor, 2);
  assert.equal(client.diagnostics.snapshotWaiterResolvedCount, 1);
});

test('invalid explicit snapshot frame is classified before waiter completion', async () => {
  const transport = new FakeTransport();
  const client = connectedClient(transport);
  const before = client.diagnostics;
  const pending = client.refreshSnapshot();
  const invalid = { ...snapshotEvent(2) };
  delete invalid.payload;
  await transport.message?.(JSON.stringify(invalid));
  await assert.rejects(pending, /SNAPSHOT_FRAME_INVALID/);
  assert.equal(client.diagnostics.websocketMessageReceivedCount, before.websocketMessageReceivedCount + 1);
  assert.equal(client.diagnostics.jsonParseSuccessCount, before.jsonParseSuccessCount + 1);
  assert.equal(client.diagnostics.schemaValidationSuccessCount, before.schemaValidationSuccessCount);
});

test('current-attempt snapshot with wrong session is rejected and cannot resolve waiter', async () => {
  const transport = new FakeTransport();
  const client = connectedClient(transport);
  const pending = client.refreshSnapshot();
  await transport.message?.(JSON.stringify({
    ...snapshotEvent(2),
    session_id: '99999999-9999-4999-8999-999999999999',
  }));
  await assert.rejects(pending, /SNAPSHOT_SESSION_MISMATCH/);
  assert.equal(client.diagnostics.snapshotRejectedSessionMismatchCount, 1);
  assert.equal(client.diagnostics.snapshotWaiterResolvedCount, 0);
});

test('explicit snapshot timeout has one deterministic bounded owner', async () => {
  const callbacks: Array<() => void> = [];
  const controlledClock: InteractiveClientClock = {
    now: clock.now,
    setTimeout: (callback) => { callbacks.push(callback); return callback; },
    clearTimeout: () => undefined,
  };
  const transport = new FakeTransport();
  const client = connectedClient(transport, undefined, controlledClock);
  const pending = client.refreshSnapshot();
  callbacks.at(-1)?.();
  await assert.rejects(pending, /SNAPSHOT_TRANSPORT_TIMEOUT/);
  assert.equal(client.diagnostics.snapshotWaiterTimeoutCount, 1);
});

test('late frame from an old socket increments attempt mismatch and changes no snapshot', async () => {
  const transport = new FakeTransport();
  const client = connectedClient(transport);
  const oldMessage = transport.message;
  const before = client.snapshot;
  client.handleTransportLoss('connection_lost');
  await oldMessage?.(JSON.stringify(snapshotEvent(9)));
  assert.equal(client.diagnostics.snapshotRejectedAttemptMismatchCount, 1);
  assert.equal(client.snapshot, null);
  assert.notEqual(client.snapshot, before);
});

test('pending snapshot from a lost connection cannot complete on a new generation', async () => {
  const transport = new FakeTransport();
  const client = connectedClient(transport);
  const pending = client.refreshSnapshot();
  client.handleTransportLoss('connection_lost');
  await assert.rejects(pending, /SNAPSHOT_TRANSPORT_UNAVAILABLE/);
  assert.equal(client.state, 'RECONNECTING');
});

test('reconnect clears old session and never replays a queued answer', () => {
  const transport = new FakeTransport();
  const client = new InteractiveClient({
    transport, endpoint: { host: '127.0.0.1', port: 49626 }, secret: new Uint8Array(32).fill(7),
    clientInstanceId: '11111111-1111-4111-8111-111111111111', clock,
  });
  client.start(); client.handleTransportLoss('heartbeat_timeout');
  assert.equal(client.state, 'RECONNECTING');
  assert.equal(client.session, null);
  assert.equal(transport.closes, 0);
});

test('missing external-interaction capability produces bounded guidance and no raw error', () => {
  const errors: string[] = [];
  const transport = new FakeTransport();
  transport.register = () => { throw new Error('raw official runtime detail'); };
  const client = new InteractiveClient({
    transport, endpoint: { host: '127.0.0.1', port: 49626 }, secret: new Uint8Array(32).fill(7),
    clientInstanceId: '11111111-1111-4111-8111-111111111111', clock,
    onError: (code) => errors.push(code),
  });
  client.start();
  assert.deepEqual(errors, ['external_interaction_permission_required']);
  assert.equal(client.state, 'RECONNECTING');
  assert.equal(transport.closes, 0);
});

test('snapshot control cannot be sent before an interactive session exists', () => {
  const transport = new FakeTransport();
  const client = new InteractiveClient({
    transport, endpoint: { host: '127.0.0.1', port: 49626 }, secret: new Uint8Array(32).fill(7),
    clientInstanceId: '11111111-1111-4111-8111-111111111111', clock,
  });
  client.start(); transport.connected?.();
  assert.throws(() => client.requestSnapshot(), /host_unavailable/);
  assert.equal(transport.sent.length, 0);
});

test('dispose permanently ends the activation credential lifecycle', () => {
  const transport = new FakeTransport();
  const credential = new Uint8Array(32).fill(7);
  const client = new InteractiveClient({
    transport, endpoint: { host: '127.0.0.1', port: 49626 }, secret: credential,
    clientInstanceId: '11111111-1111-4111-8111-111111111111', clock,
  });
  client.start();
  client.dispose();
  client.start();

  assert.equal(client.state, 'DISCONNECTED');
  assert.equal(transport.registrations.length, 1);
  assert.deepEqual([...credential], [...new Uint8Array(32).fill(7)]);
});

function connectedClient(
  transport: FakeTransport,
  onSnapshot?: () => void,
  clientClock: InteractiveClientClock = clock,
): InteractiveClient {
  const client = new InteractiveClient({
    transport, endpoint: { host: '127.0.0.1', port: 49626 }, secret: new Uint8Array(32).fill(7),
    clientInstanceId: '11111111-1111-4111-8111-111111111111', clock: clientClock,
    onSnapshot,
  });
  client.start(); transport.connected?.();
  void transport.message?.(JSON.stringify({ protocol: 'aia-interactive-auth/v1', phase: 'accepted' }));
  void transport.message?.(JSON.stringify({
    protocol: 'aia-interactive/v1', message_id: '33333333-3333-4333-8333-333333333333',
    sent_at: '2026-09-12T08:00:00Z', message_type: 'hello_ack', accepted: true,
    selected_version: 'aia-interactive/v1', application_generation: '44444444-4444-4444-8444-444444444444',
    connection_id: '55555555-5555-4555-8555-555555555555', connection_generation: 1,
    session_id: '66666666-6666-4666-8666-666666666666', current_event_cursor: 1, reason_code: null,
  }));
  void transport.message?.(JSON.stringify(snapshotEvent()));
  assert.equal(client.state, 'CONNECTED');
  return client;
}

function snapshotEvent(cursor = 1): Record<string, unknown> {
  return {
    protocol: 'aia-interactive/v1', message_id: '77777777-7777-4777-8777-777777777777',
    sent_at: '2026-09-12T08:00:00Z', message_type: 'event',
    application_generation: '44444444-4444-4444-8444-444444444444',
    session_id: '66666666-6666-4666-8666-666666666666', event_id: '88888888-8888-4888-8888-888888888888',
    cursor, event_type: 'workflow_snapshot', workflow_id: null, workflow_revision: null,
    correlation_id: 'snapshot', payload: { snapshot: {
      application_generation: '44444444-4444-4444-8444-444444444444', event_cursor: cursor,
      status: { host_state: 'READY', protocol_compatible: true, harness_state: 'DISCONNECTED',
        jlceda_state: 'CONNECTED', hardware_state: 'UNAVAILABLE', workflow_state: null,
        workflow_revision: null, safe_workflow_label: null, last_error_code: null, message: 'Ready.' },
      workflows: [], pending_challenges: [],
    } },
  };
}
