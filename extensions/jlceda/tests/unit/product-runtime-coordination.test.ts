import assert from 'node:assert/strict';
import test from 'node:test';

import { JlcEdaInteractionRuntime, PendingDesignRefresh } from '../../src/interaction/product-runtime.ts';
import { ActivationRuntimeCommandService } from '../../src/interaction/runtime-command-bridge.ts';
import type { AiaDiagnosticFields } from '../../src/interaction/debug-diagnostics.ts';
import type { JlcEdaApiAdapter } from '../../src/runtime/jlc-eda-api-adapter.ts';
import type { InteractiveTransport } from '../../src/interaction/interactive-client.ts';

test('selection during synchronization produces exactly one post-sync observation', () => {
  const coordination = new PendingDesignRefresh();
  let observations = 0;
  coordination.selectionChanged('SYNCHRONIZING', 'workflow:0', () => { observations += 1; return true; });
  coordination.selectionChanged('SYNCHRONIZING', 'workflow:0', () => { observations += 1; return true; });
  assert.equal(observations, 0);
  coordination.synchronized('CONNECTED', 'workflow:0', () => { observations += 1; return true; });
  coordination.synchronized('CONNECTED', 'workflow:0', () => { observations += 1; return true; });
  assert.equal(observations, 1);
});

test('selection after synchronization dispatches immediately without replay state', () => {
  const coordination = new PendingDesignRefresh();
  let observations = 0;
  coordination.selectionChanged('CONNECTED', 'workflow:0', () => { observations += 1; return true; });
  coordination.synchronized('CONNECTED', 'workflow:1', () => { observations += 1; return true; });
  assert.equal(observations, 1);
});

test('selection change during an observation is coalesced until workflow revision advances', () => {
  const coordination = new PendingDesignRefresh();
  let observations = 0;
  const dispatch = (): boolean => { observations += 1; return true; };

  coordination.selectionChanged('CONNECTED', 'workflow:0', dispatch);
  coordination.selectionChanged('CONNECTED', 'workflow:0', dispatch);
  coordination.synchronized('CONNECTED', 'workflow:0', dispatch);
  assert.equal(observations, 1);

  coordination.synchronized('CONNECTED', 'workflow:1', dispatch);
  assert.equal(observations, 2);
  coordination.synchronized('CONNECTED', 'workflow:1', dispatch);
  assert.equal(observations, 2);
});

test('pending refresh is generation-local and disposal clears it', () => {
  const coordination = new PendingDesignRefresh();
  let observations = 0;
  coordination.selectionChanged('AUTH_REQUIRED', 'workflow:0', () => { observations += 1; return true; });
  coordination.dispose();
  coordination.synchronized('CONNECTED', 'workflow:1', () => { observations += 1; return true; });
  assert.equal(observations, 0);
});

test('only a runtime with a CONNECTED client registers the private command service once', async () => {
  let registrations = 0;
  let callback: ((action: 'STATUS') => Promise<unknown>) | undefined;
  let invocations = 0;
  const api = {
    writeInteractivePort: async () => true,
    registerSelectionListener: () => true,
    removeSelectionListener: () => true,
    showToast: () => undefined,
    registerRuntimeCommandService: (dispatch: (action: 'STATUS') => Promise<unknown>) => {
      registrations += 1; callback = dispatch;
    },
  } as unknown as JlcEdaApiAdapter;
  const transport = new RuntimeTransport();
  let runtime!: JlcEdaInteractionRuntime;
  const service = new ActivationRuntimeCommandService(
    api,
    (ownerRuntimeNo) => runtime.debugRuntimeNo === ownerRuntimeNo && runtime.clientPresent,
    async () => { invocations += 1; },
  );
  runtime = new JlcEdaInteractionRuntime(
    api, transport, () => undefined, (runtimeNo) => service.register(runtimeNo),
  );

  assert.equal(registrations, 0, 'created runtime must not register');
  await runtime.configure(49_626, new Uint8Array(32).fill(9));
  assert.equal(runtime.state, 'CONNECTING');
  assert.equal(registrations, 0, 'CONNECTING runtime must not register');

  const registration = transport.registrations[0]!;
  await registration.connected();
  await registration.message(JSON.stringify({ protocol: 'aia-interactive-auth/v1', phase: 'accepted' }));
  await registration.message(JSON.stringify({
    protocol: 'aia-interactive/v1', message_id: '33333333-3333-4333-8333-333333333333',
    sent_at: '2026-09-12T08:00:00Z', message_type: 'hello_ack', accepted: true,
    selected_version: 'aia-interactive/v1', application_generation: '44444444-4444-4444-8444-444444444444',
    connection_id: '55555555-5555-4555-8555-555555555555', connection_generation: 1,
    session_id: '66666666-6666-4666-8666-666666666666', current_event_cursor: 1, reason_code: null,
  }));
  assert.equal(runtime.state, 'SYNCHRONIZING');
  assert.equal(registrations, 0, 'SYNCHRONIZING runtime must not register');

  await registration.message(JSON.stringify(snapshotEvent(1)));
  assert.equal(runtime.state, 'CONNECTED');
  assert.equal(registrations, 1);
  await registration.message(JSON.stringify(snapshotEvent(2)));
  assert.equal(registrations, 1, 'repeated CONNECTED observations must be idempotent');
  assert.deepEqual(await callback?.('STATUS'), { status: 'COMPLETED', reasonCode: null });
  assert.equal(invocations, 1);
  runtime.dispose();
});

test('activation runtime sends one observe for a selection debounced during synchronization', async () => {
  const selectionCallbacks: Array<() => void> = [];
  let presentationReads = 0;
  const api = {
    writeInteractivePort: async () => true,
    registerSelectionListener: (_id: string, callback: () => void) => { selectionCallbacks.push(callback); return true; },
    removeSelectionListener: () => true,
    readCurrentSelection: async () => {
      presentationReads += 1;
      throw new Error('presentation-only read failed');
    },
    showToast: () => undefined,
  } as unknown as JlcEdaApiAdapter;
  const transport = new RuntimeTransport();
  const runtime = new JlcEdaInteractionRuntime(api, transport);
  await runtime.configure(49_626, new Uint8Array(32).fill(9));
  selectionCallbacks[0]?.();
  await synchronize(transport.registrations[0]!, 1);
  await transport.observeSent;
  assert.equal(transport.sent.filter((value) => JSON.parse(value).command === 'design.observe').length, 1);
  assert.equal(presentationReads, 0, 'presentation read cannot gate or race Host refresh');
  runtime.dispose();
});

test('reconfigured activation runtime routes the current listener to the current connection', async () => {
  const listeners: Array<() => void> = [];
  const api = {
    writeInteractivePort: async () => true,
    registerSelectionListener: (_id: string, callback: () => void) => { listeners.push(callback); return true; },
    removeSelectionListener: () => true,
    showToast: () => undefined,
  } as unknown as JlcEdaApiAdapter;
  const transport = new RuntimeTransport();
  const runtime = new JlcEdaInteractionRuntime(api, transport);
  await runtime.configure(49_626, new Uint8Array(32).fill(9));
  await runtime.configure(49_626, new Uint8Array(32).fill(9));
  await synchronize(transport.registrations[1]!, 2);
  listeners[1]?.();
  await transport.observeSent;
  assert.equal(transport.registrations.length, 2);
  assert.equal(transport.sent.filter((value) => JSON.parse(value).command === 'design.observe').length, 1);
  runtime.dispose();
});

test('Status distinguishes a presentation failure after the explicit snapshot resolves', async () => {
  const diagnostics: Array<{ scope: string; event: string; fields: AiaDiagnosticFields }> = [];
  const api = {
    writeInteractivePort: async () => true,
    registerSelectionListener: () => true,
    removeSelectionListener: () => true,
    showToast: () => undefined,
    showInformation: () => { throw new Error('raw official dialog failure'); },
  } as unknown as JlcEdaApiAdapter;
  const transport = new RuntimeTransport();
  const runtime = new JlcEdaInteractionRuntime(
    api,
    transport,
    (scope, event, fields = {}) => { diagnostics.push({ scope, event, fields }); },
  );
  await runtime.configure(49_626, new Uint8Array(32).fill(9));
  const registration = transport.registrations[0]!;
  await synchronize(registration, 1);
  transport.onSnapshotRequest = () => { void registration.message(JSON.stringify(snapshotEvent(2))); };

  await assert.rejects(runtime.showStatus(), /STATUS_PRESENTATION_FAILED/);
  assert.equal(runtime.diagnostics.statusActionSnapshotResolvedCount, 1);
  assert.equal(runtime.diagnostics.statusDialogRenderAttemptCount, 1);
  assert.equal(runtime.diagnostics.statusDialogRenderSuccessCount, 0);
  assert.deepEqual(
    diagnostics.filter((value) => value.scope === 'STATUS').map((value) => value.event),
    ['runtime_entered', 'projection_succeeded', 'dialog_invocation_attempted', 'dialog_invocation_failed'],
  );
  runtime.dispose();
});

test('Status diagnostics identify one runtime through projection and Dialog success', async () => {
  const diagnostics: Array<{ scope: string; event: string; fields: AiaDiagnosticFields }> = [];
  const api = {
    writeInteractivePort: async () => true,
    registerSelectionListener: () => true,
    removeSelectionListener: () => true,
    showToast: () => undefined,
    showInformation: () => undefined,
  } as unknown as JlcEdaApiAdapter;
  const transport = new RuntimeTransport();
  const runtime = new JlcEdaInteractionRuntime(
    api,
    transport,
    (scope, event, fields = {}) => { diagnostics.push({ scope, event, fields }); },
  );
  await runtime.configure(49_626, new Uint8Array(32).fill(9));
  const registration = transport.registrations[0]!;
  await synchronize(registration, 1);
  transport.onSnapshotRequest = () => { void registration.message(JSON.stringify(snapshotEvent(2))); };

  await runtime.showStatus();

  const status = diagnostics.filter((value) => value.scope === 'STATUS');
  assert.deepEqual(status.map((value) => value.event), [
    'runtime_entered', 'projection_succeeded', 'dialog_invocation_attempted', 'dialog_invocation_succeeded',
  ]);
  assert.ok(status.every((value) => value.fields.runtimeNo === runtime.debugRuntimeNo));
  runtime.dispose();
});

class RuntimeTransport implements InteractiveTransport {
  readonly registrations: Array<{
    id: string;
    message: (data: string) => void | Promise<void>;
    connected: () => void | Promise<void>;
  }> = [];
  readonly sent: string[] = [];
  readonly observeSent: Promise<void>;
  #resolveObserve!: () => void;
  onSnapshotRequest: (() => void) | null = null;

  constructor() {
    this.observeSent = new Promise((resolve) => { this.#resolveObserve = resolve; });
  }
  register(id: string, _uri: string, message: (data: string) => void | Promise<void>, connected: () => void | Promise<void>): void {
    this.registrations.push({ id, message, connected });
  }
  send(_id: string, data: string): void {
    this.sent.push(data);
    const value = JSON.parse(data);
    if (value.command === 'design.observe') this.#resolveObserve();
    if (value.phase === 'snapshot_request') this.onSnapshotRequest?.();
  }
  close(): void { /* bounded fake transport */ }
}

async function synchronize(
  registration: RuntimeTransport['registrations'][number],
  generation: number,
): Promise<void> {
  await registration.connected();
  await registration.message(JSON.stringify({ protocol: 'aia-interactive-auth/v1', phase: 'accepted' }));
  await registration.message(JSON.stringify({
    protocol: 'aia-interactive/v1', message_id: '33333333-3333-4333-8333-333333333333',
    sent_at: '2026-09-12T08:00:00Z', message_type: 'hello_ack', accepted: true,
    selected_version: 'aia-interactive/v1', application_generation: '44444444-4444-4444-8444-444444444444',
    connection_id: '55555555-5555-4555-8555-555555555555', connection_generation: generation,
    session_id: '66666666-6666-4666-8666-666666666666', current_event_cursor: 1, reason_code: null,
  }));
  await registration.message(JSON.stringify(snapshotEvent(1, generation)));
}

function snapshotEvent(cursor: number, generation = 1): Record<string, unknown> {
  return {
    protocol: 'aia-interactive/v1', message_id: '77777777-7777-4777-8777-777777777777',
    sent_at: '2026-09-12T08:00:00Z', message_type: 'event',
    application_generation: '44444444-4444-4444-8444-444444444444',
    session_id: '66666666-6666-4666-8666-666666666666',
    event_id: '88888888-8888-4888-8888-888888888888', cursor: 1,
    event_type: 'workflow_snapshot', workflow_id: null, workflow_revision: null,
    correlation_id: 'snapshot', payload: { snapshot: {
      application_generation: '44444444-4444-4444-8444-444444444444', event_cursor: 1,
      status: { host_state: 'READY', protocol_compatible: true, harness_state: 'DISCONNECTED',
        jlceda_state: 'CONNECTED', hardware_state: 'UNAVAILABLE', workflow_state: 'OBSERVING_DESIGN',
        workflow_revision: 0, safe_workflow_label: 'PWM_OUT', last_error_code: null, message: 'Ready.' },
      workflows: [{ workflow_id: '99999999-9999-4999-8999-999999999999', revision: 0,
        state: 'OBSERVING_DESIGN', safe_label: 'PWM_OUT', pending_challenge_ids: [], terminal: false }],
      pending_challenges: [],
    } },
  };
}
