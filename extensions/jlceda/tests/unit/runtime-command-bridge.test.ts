import assert from 'node:assert/strict';
import test from 'node:test';

import {
  ActivationRuntimeCommandService,
  dispatchRuntimeCommand,
  RUNTIME_COMMAND_ACTIONS,
  invokeRuntimeCommand,
} from '../../src/interaction/runtime-command-bridge.ts';
import {
  JlcEdaApiAdapter,
  RuntimeCommandRpcError,
  type JlcEdaRuntimeBoundary,
} from '../../src/runtime/jlc-eda-api-adapter.ts';

class PrivateBus {
  service: ((request: unknown) => unknown) | null = null;
  registrations = 0;
  readonly runtime = {
    rpcService: (topic: string, service: (request: unknown) => unknown) => {
      assert.equal(topic, 'aia.runtime.command');
      this.registrations += 1; this.service = service;
    },
    rpcCall: async (topic: string, request: unknown) => {
      assert.equal(topic, 'aia.runtime.command');
      if (this.service === null) throw new Error('missing private service');
      return await this.service(request);
    },
  };
}

test('menu VM without local runtime invokes every closed action exactly once on connected owner', async () => {
  const bus = new PrivateBus();
  const activationApi = new JlcEdaApiAdapter({ sys_MessageBus: bus.runtime } as unknown as JlcEdaRuntimeBoundary);
  const menuApi = new JlcEdaApiAdapter({ sys_MessageBus: bus.runtime } as unknown as JlcEdaRuntimeBoundary);
  const invoked: string[] = [];
  const service = new ActivationRuntimeCommandService(
    activationApi,
    (ownerRuntimeNo) => ownerRuntimeNo === 7,
    async (action) => { invoked.push(action); },
  );
  service.register(7); service.register(7);

  for (const action of RUNTIME_COMMAND_ACTIONS) {
    await invokeRuntimeCommand(menuApi, action);
  }

  assert.equal(bus.registrations, 1);
  assert.deepEqual(invoked, RUNTIME_COMMAND_ACTIONS);
});

test('stale owner and action failures return bounded rejection without raw error', async () => {
  const bus = new PrivateBus();
  const api = new JlcEdaApiAdapter({ sys_MessageBus: bus.runtime } as unknown as JlcEdaRuntimeBoundary);
  const stale = new ActivationRuntimeCommandService(api, () => false, async () => undefined);
  stale.register(4);
  await assert.rejects(
    invokeRuntimeCommand(api, 'STATUS'),
    (error: unknown) => error instanceof RuntimeCommandRpcError
      && error.code === 'runtime_owner_stale',
  );

  const failingBus = new PrivateBus();
  const failingApi = new JlcEdaApiAdapter({ sys_MessageBus: failingBus.runtime } as unknown as JlcEdaRuntimeBoundary);
  const failing = new ActivationRuntimeCommandService(
    failingApi, () => true,
    async () => { throw new Error('credential session_id raw-provider-payload'); },
  );
  failing.register(5);
  await assert.rejects(
    invokeRuntimeCommand(failingApi, 'STATUS'),
    (error: unknown) => error instanceof RuntimeCommandRpcError
      && error.code === 'runtime_action_failed',
  );
});

test('adapter rejects arbitrary private commands and exposes no dynamic method surface', async () => {
  const bus = new PrivateBus();
  const api = new JlcEdaApiAdapter({ sys_MessageBus: bus.runtime } as unknown as JlcEdaRuntimeBoundary);
  const service = new ActivationRuntimeCommandService(api, () => true, async () => undefined);
  service.register(1);
  await assert.rejects(
    bus.runtime.rpcCall('aia.runtime.command', { action: 'ARBITRARY_METHOD', code: 'execute()' }),
  );
});

test('closed dispatcher calls each existing runtime operation exactly once', async () => {
  const calls: string[] = [];
  const owner = {
    clientPresent: true, state: 'CONNECTED',
    showStatus: async () => { calls.push('STATUS'); },
    refreshDesignContext: async () => { calls.push('REFRESH_DESIGN_CONTEXT'); },
    resolvePendingAction: async () => { calls.push('RESOLVE'); },
    showCurrentTarget: async () => { calls.push('CURRENT_TARGET'); },
    showEvidenceSummary: async () => { calls.push('EVIDENCE_SUMMARY'); },
    highlightTarget: async () => { calls.push('HIGHLIGHT_TARGET'); },
    cancelWorkflow: async () => { calls.push('CANCEL_WORKFLOW'); },
    disconnect: () => { calls.push('DISCONNECT'); },
    reconnect: () => { calls.push('RECONNECT'); },
  };
  for (const action of RUNTIME_COMMAND_ACTIONS) await dispatchRuntimeCommand(owner, action);
  assert.deepEqual(calls, [
    'STATUS', 'REFRESH_DESIGN_CONTEXT', 'RESOLVE', 'CURRENT_TARGET',
    'RESOLVE', 'EVIDENCE_SUMMARY', 'HIGHLIGHT_TARGET', 'CANCEL_WORKFLOW',
    'DISCONNECT', 'RECONNECT',
  ]);
});

test('only reconnect and disconnect remain available after an owned client disconnects', async () => {
  let reconnects = 0; let disconnects = 0;
  const owner = {
    clientPresent: true, state: 'DISCONNECTED',
    showStatus: async () => undefined,
    refreshDesignContext: async () => undefined,
    resolvePendingAction: async () => undefined,
    showCurrentTarget: async () => undefined,
    showEvidenceSummary: async () => undefined,
    highlightTarget: async () => undefined,
    cancelWorkflow: async () => undefined,
    disconnect: () => { disconnects += 1; },
    reconnect: () => { reconnects += 1; },
  };
  await assert.rejects(dispatchRuntimeCommand(owner, 'STATUS'), /runtime_not_connected/);
  await dispatchRuntimeCommand(owner, 'DISCONNECT');
  await dispatchRuntimeCommand(owner, 'RECONNECT');
  assert.deepEqual({ disconnects, reconnects }, { disconnects: 1, reconnects: 1 });
});
