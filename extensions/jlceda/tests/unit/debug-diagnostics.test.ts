import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import test from 'node:test';

import {
  boundedDiagnosticError,
  consoleAiaDiagnostics,
  type AiaDiagnosticFields,
} from '../../src/interaction/debug-diagnostics.ts';
import {
  InteractiveClient,
  type InteractiveTransport,
} from '../../src/interaction/interactive-client.ts';

const extensionRoot = resolve(import.meta.dirname, '../..');

test('debug build identity has the exact bounded AIA prefix and version', () => {
  const lines: string[] = [];
  const original = console.warn;
  console.warn = (value?: unknown) => { lines.push(String(value)); };
  try {
    consoleAiaDiagnostics('BOOT', '', {
      version: '0.2.26', activationGeneration: 1, runtimePresent: false,
    });
  } finally {
    console.warn = original;
  }
  assert.deepEqual(lines, [
    '[AIA][BOOT] version=0.2.26 activationGeneration=1 runtimePresent=false',
  ]);
  const manifest = JSON.parse(readFileSync(join(extensionRoot, 'extension.json'), 'utf8')) as { version: string };
  assert.equal(manifest.version, '0.2.26');
});

test('diagnostic formatter never emits an unbounded string value or raw error text', () => {
  const lines: string[] = [];
  const original = console.warn;
  console.warn = (value?: unknown) => { lines.push(String(value)); };
  try {
    consoleAiaDiagnostics('ERROR', 'unhandled', {
      category: 'value with spaces and sensitive material',
    });
  } finally {
    console.warn = original;
  }
  assert.equal(lines[0], '[AIA][ERROR] event=unhandled category=invalid_token');
  assert.equal(boundedDiagnosticError(new Error('raw provider exception')), 'bounded_error');
  assert.equal(boundedDiagnosticError(undefined), 'bounded_non_error');
});

test('console diagnostic failure cannot change product behavior', () => {
  const original = console.warn;
  console.warn = () => { throw new Error('raw console failure'); };
  try {
    assert.doesNotThrow(() => consoleAiaDiagnostics('CLIENT', 'start', { runtimeNo: 1 }));
  } finally {
    console.warn = original;
  }
});

test('client diagnostics expose the bounded Status request completion sequence', async () => {
  const events: Array<{ scope: string; event: string; fields: AiaDiagnosticFields }> = [];
  const transport = new DiagnosticTransport();
  const client = new InteractiveClient({
    transport,
    endpoint: { host: '127.0.0.1', port: 49_626 },
    secret: new Uint8Array(32).fill(7),
    clientInstanceId: '11111111-1111-4111-8111-111111111111',
    debugRuntimeNo: 4,
    diagnostic: (scope, event, fields = {}) => { events.push({ scope, event, fields }); },
  });
  client.start();
  await transport.connected?.();
  await transport.message?.(JSON.stringify({ protocol: 'aia-interactive-auth/v1', phase: 'accepted' }));
  await transport.message?.(JSON.stringify(helloAccepted()));
  await transport.message?.(JSON.stringify(snapshotEvent(1)));
  const pending = client.refreshSnapshot();
  await transport.message?.(JSON.stringify(snapshotEvent(2)));
  await pending;

  const names = events.map((value) => value.event);
  assertSubsequence(names, [
    'created', 'start', 'state_transition', 'state_transition', 'state_transition',
    'workflow_snapshot_observed', 'initial_snapshot_accepted', 'state_transition',
    'request_snapshot_entered', 'snapshot_waiter_registered',
    'snapshot_request_send_attempt', 'snapshot_request_send_succeeded',
    'workflow_snapshot_observed', 'snapshot_waiter_resolved',
  ]);
  assert.ok(events.every((value) => value.scope === 'CLIENT'));
  assert.ok(events.every((value) => value.fields.runtimeNo === 4));
});

test('production diagnostic call sites contain no forbidden diagnostic values', () => {
  const paths = [
    join(extensionRoot, 'src', 'index.ts'),
    join(extensionRoot, 'src', 'interaction', 'interactive-client.ts'),
    join(extensionRoot, 'src', 'interaction', 'product-runtime.ts'),
  ];
  const diagnosticLines = paths.flatMap((path) => readFileSync(path, 'utf8').split(/\r?\n/))
    .filter((line) => /consoleAiaDiagnostics|#diagnostic\(|#log\(/.test(line));
  assert.ok(diagnosticLines.length >= 20);
  assert.deepEqual(
    diagnosticLines.filter((line) => /(credential|hmac|sessionId|raw frame|provider payload|absolute path|visa|serial|waveform)/i.test(line)),
    [],
  );
});

class DiagnosticTransport implements InteractiveTransport {
  message?: (data: string) => void | Promise<void>;
  connected?: () => void | Promise<void>;
  register(
    _id: string,
    _uri: string,
    onMessage: (data: string) => void | Promise<void>,
    onConnected: () => void | Promise<void>,
  ): void {
    this.message = onMessage; this.connected = onConnected;
  }
  send(): void { /* bounded fake */ }
  close(): void { /* bounded fake */ }
}

function helloAccepted(): Record<string, unknown> {
  return {
    protocol: 'aia-interactive/v1', message_id: '33333333-3333-4333-8333-333333333333',
    sent_at: '2026-09-12T08:00:00Z', message_type: 'hello_ack', accepted: true,
    selected_version: 'aia-interactive/v1', application_generation: '44444444-4444-4444-8444-444444444444',
    connection_id: '55555555-5555-4555-8555-555555555555', connection_generation: 1,
    session_id: '66666666-6666-4666-8666-666666666666', current_event_cursor: 1, reason_code: null,
  };
}

function snapshotEvent(cursor: number): Record<string, unknown> {
  return {
    protocol: 'aia-interactive/v1', message_id: '77777777-7777-4777-8777-777777777777',
    sent_at: '2026-09-12T08:00:00Z', message_type: 'event',
    application_generation: '44444444-4444-4444-8444-444444444444',
    session_id: '66666666-6666-4666-8666-666666666666',
    event_id: '88888888-8888-4888-8888-888888888888', cursor,
    event_type: 'workflow_snapshot', workflow_id: null, workflow_revision: null,
    correlation_id: 'snapshot', payload: { snapshot: {
      application_generation: '44444444-4444-4444-8444-444444444444', event_cursor: cursor,
      status: { host_state: 'READY', protocol_compatible: true, harness_state: 'DISCONNECTED',
        jlceda_state: 'CONNECTED', hardware_state: 'UNAVAILABLE', workflow_state: null,
        workflow_revision: null, safe_workflow_label: null, last_error_code: null, message: 'Ready.' },
      workflows: [], pending_challenges: [],
    } },
  };
}

function assertSubsequence(actual: readonly string[], expected: readonly string[]): void {
  let cursor = 0;
  for (const value of actual) if (value === expected[cursor]) cursor += 1;
  assert.equal(cursor, expected.length, `missing diagnostic sequence after ${expected[cursor - 1] ?? 'start'}`);
}
