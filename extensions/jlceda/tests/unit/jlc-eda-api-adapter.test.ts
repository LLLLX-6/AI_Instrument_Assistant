import assert from 'node:assert/strict';
import test from 'node:test';

import {
  JlcEdaApiAdapter,
  JlcEdaApiCallError,
  JlcEdaCapabilityUnavailableError,
  type JlcEdaRuntimeBoundary,
} from '../../src/runtime/jlc-eda-api-adapter.ts';

type FakePrimitive = {
  getState_PrimitiveId(): string;
  getState_PrimitiveType(): string;
  getState_Net?(): string;
  getState_Designator?(): string | undefined;
  internalSecret?: string;
  hugePayload?: string;
};

function fakeWire(id = 'wire-1', net = 'PWM_OUT'): FakePrimitive {
  return {
    getState_PrimitiveId: () => id,
    getState_PrimitiveType: () => 'Wire',
    getState_Net: () => net,
    internalSecret: 'must-not-cross-adapter',
    hugePayload: 'x'.repeat(100_000),
  };
}

function runtime(overrides: Record<string, unknown> = {}): JlcEdaRuntimeBoundary {
  return {
    dmt_SelectControl: {
      getCurrentDocumentInfo: async () => undefined,
    },
    sch_SelectControl: {
      getAllSelectedPrimitives: async () => [],
      getAllSelectedPrimitives_PrimitiveId: async () => [],
      clearSelected: () => true,
      doSelectPrimitives: async () => true,
      doCrossProbeSelect: () => true,
    },
    sys_Environment: {
      getEditorCurrentVersion: () => '3.2.42',
      getEditorCompliedDate: () => '2026-08-01',
      isClient: () => false,
      isWeb: () => true,
      isJLCEDAProEdition: () => true,
      isEasyEDAProEdition: () => false,
    },
    sys_Dialog: {
      showInformationMessage: () => undefined,
    },
    sys_Message: {
      showToastMessage: () => undefined,
    },
    ...overrides,
  } as unknown as JlcEdaRuntimeBoundary;
}

test('no active document returns an explicit null document DTO', async () => {
  const adapter = new JlcEdaApiAdapter(runtime());

  const result = await adapter.readCurrentDocument();

  assert.equal(result.document, null);
  assert.equal(result.rawShape.kind, 'undefined');
});

test('schematic document is normalized to a finite transport DTO', async () => {
  const adapter = new JlcEdaApiAdapter(runtime({
    dmt_SelectControl: {
      getCurrentDocumentInfo: async () => ({
        documentType: 1,
        uuid: 'doc-main-schematic',
        tabId: 'tab-private-runtime-value',
        parentProjectUuid: 'project-stm32-test',
        privateRuntimeState: { huge: 'x'.repeat(100_000) },
      }),
    },
  }));

  const result = await adapter.readCurrentDocument();

  assert.deepEqual(result.document, {
    provider: 'jlceda-pro',
    documentId: 'doc-main-schematic',
    documentType: 'schematic',
    projectId: 'project-stm32-test',
    libraryId: null,
  });
  assert.equal(result.rawShape.kind, 'object');
  assert.equal(result.rawShape.ownKeyCount, 5);
  assert.ok(result.rawShape.ownKeys.includes('documentType'));
  assert.ok(!JSON.stringify(result).includes('tab-private-runtime-value'));
  assert.ok(!JSON.stringify(result).includes('privateRuntimeState'));
});

test('empty selection is a valid finite selection DTO', async () => {
  const adapter = new JlcEdaApiAdapter(runtime());

  const result = await adapter.readCurrentSelection();

  assert.deepEqual(result.objects, []);
  assert.equal(result.totalSelected, 0);
  assert.equal(result.truncated, false);
  assert.deepEqual(result.primitiveTypeSummary, {});
});

test('one selected wire is normalized and the raw object is cropped', async () => {
  const adapter = new JlcEdaApiAdapter(runtime({
    sch_SelectControl: {
      getAllSelectedPrimitives: async () => [fakeWire()],
      getAllSelectedPrimitives_PrimitiveId: async () => ['wire-1'],
      doCrossProbeSelect: () => true,
    },
  }));

  const result = await adapter.readCurrentSelection();

  assert.deepEqual(result.objects, [{
    primitiveId: 'wire-1',
    primitiveType: 'Wire',
    netName: 'PWM_OUT',
  }]);
  assert.deepEqual(result.primitiveTypeSummary, { Wire: 1 });
  const serialized = JSON.stringify(result);
  assert.ok(!serialized.includes('internalSecret'));
  assert.ok(!serialized.includes('hugePayload'));
  assert.ok(serialized.length < 2_000);
});

test('schematic wire identity comes from selection control without reading PCB-backed object identity', async () => {
  let objectPrimitiveIdWasRead = false;
  const wire = fakeWire();
  wire.getState_PrimitiveId = () => {
    objectPrimitiveIdWasRead = true;
    throw new Error('对象未在 PCB 画布初始化，不存在 PrimitiveId。');
  };
  const adapter = new JlcEdaApiAdapter(runtime({
    sch_SelectControl: {
      getAllSelectedPrimitives: async () => [wire],
      getAllSelectedPrimitives_PrimitiveId: async () => ['wire-1'],
      doCrossProbeSelect: () => true,
    },
  }));

  const result = await adapter.readCurrentSelection();

  assert.equal(objectPrimitiveIdWasRead, false);
  assert.equal(result.objects[0]?.primitiveId, 'wire-1');
  assert.equal(result.objects[0]?.netName, 'PWM_OUT');
});

test('missing BETA selection API is reported as unsupported', async () => {
  const adapter = new JlcEdaApiAdapter(runtime({ sch_SelectControl: {} }));

  await assert.rejects(
    adapter.readCurrentSelection(),
    (error: unknown) => error instanceof JlcEdaCapabilityUnavailableError
      && error.operation === 'sch_SelectControl.getAllSelectedPrimitives',
  );
});

test('official API exceptions are wrapped without exposing the raw error object', async () => {
  const rawError = Object.assign(new Error('official runtime failed'), {
    internalState: 'do-not-leak',
  });
  const adapter = new JlcEdaApiAdapter(runtime({
    dmt_SelectControl: {
      getCurrentDocumentInfo: async () => { throw rawError; },
    },
  }));

  await assert.rejects(
    adapter.readCurrentDocument(),
    (error: unknown) => error instanceof JlcEdaApiCallError
      && error.operation === 'dmt_SelectControl.getCurrentDocumentInfo'
      && !error.message.includes('internalState'),
  );
});

test('highlight uses the static semantic cross-probe operation', async () => {
  const calls: unknown[][] = [];
  const adapter = new JlcEdaApiAdapter(runtime({
    sch_SelectControl: {
      getAllSelectedPrimitives: async () => [fakeWire()],
      getAllSelectedPrimitives_PrimitiveId: async () => ['wire-1'],
      clearSelected: () => true,
      doSelectPrimitives: async () => true,
      doCrossProbeSelect: (...args: unknown[]) => {
        calls.push(args);
        return true;
      },
    },
  }));

  const result = await adapter.highlightSelection();

  assert.deepEqual(calls, [[[], [], ['PWM_OUT'], true, false]]);
  assert.deepEqual(result, {
    status: 'applied',
    componentCount: 0,
    pinCount: 0,
    netCount: 1,
    warnings: [
      'Official API accepted the request after clearing the selected overlay; visual rendering cannot be verified through the API.',
    ],
  });
});

test('highlight awaits an asynchronous official result instead of treating the Promise as applied', async () => {
  const restoredIds: unknown[] = [];
  const adapter = new JlcEdaApiAdapter(runtime({
    sch_SelectControl: {
      getAllSelectedPrimitives: async () => [fakeWire()],
      getAllSelectedPrimitives_PrimitiveId: async () => ['wire-1'],
      clearSelected: () => true,
      doSelectPrimitives: async (ids: unknown) => {
        restoredIds.push(ids);
        return true;
      },
      doCrossProbeSelect: async () => false,
    },
  }));

  const result = await adapter.highlightSelection();

  assert.equal(result.status, 'noop');
  assert.deepEqual(result.warnings, [
    'Official cross-probe API returned false.',
    'Original selection was restored.',
  ]);
  assert.deepEqual(restoredIds, [['wire-1']]);
});

test('highlight removes the selected overlay before cross-probe rendering', async () => {
  const events: string[] = [];
  const adapter = new JlcEdaApiAdapter(runtime({
    sch_SelectControl: {
      getAllSelectedPrimitives: async () => [fakeWire()],
      getAllSelectedPrimitives_PrimitiveId: async () => ['wire-1'],
      clearSelected: () => {
        events.push('clear-selection');
        return true;
      },
      doSelectPrimitives: async () => {
        events.push('restore-selection');
        return true;
      },
      doCrossProbeSelect: async () => {
        events.push('apply-highlight');
        return true;
      },
    },
  }));

  const result = await adapter.highlightSelection();

  assert.equal(result.status, 'applied');
  assert.deepEqual(events, ['clear-selection', 'apply-highlight']);
});

test('unsupported highlight API is rejected before any side effect', async () => {
  const adapter = new JlcEdaApiAdapter(runtime({
    sch_SelectControl: {
      getAllSelectedPrimitives: async () => [fakeWire()],
      getAllSelectedPrimitives_PrimitiveId: async () => ['wire-1'],
    },
  }));

  await assert.rejects(
    adapter.highlightSelection(),
    (error: unknown) => error instanceof JlcEdaCapabilityUnavailableError
      && error.operation === 'sch_SelectControl.doCrossProbeSelect',
  );
});

test('runtime diagnostics expose version and capability booleans only', () => {
  const adapter = new JlcEdaApiAdapter(runtime());

  assert.deepEqual(adapter.readRuntimeDiagnostics(), {
    editorVersion: '3.2.42',
    editorCompiledDate: '2026-08-01',
    environment: 'web',
    edition: 'jlceda-pro',
    capabilities: {
      documentRead: true,
      selectionRead: true,
      crossProbeHighlight: true,
    },
  });
});

test('official WebSocket boundary accepts only explicit loopback text transport', async () => {
  const registrations: unknown[][] = [];
  const sent: unknown[][] = [];
  const closed: unknown[][] = [];
  const adapter = new JlcEdaApiAdapter(runtime({
    sys_WebSocket: {
      register: (...args: unknown[]) => { registrations.push(args); },
      send: (...args: unknown[]) => { sent.push(args); },
      close: (...args: unknown[]) => { closed.push(args); },
    },
  }));
  let received = '';
  adapter.registerWebSocket(
    'aia-test', 'ws://127.0.0.1:49624',
    (data) => { received = data; },
    () => undefined,
  );
  const messageCallback = registrations[0]![2] as (event: { data: string }) => void;
  assert.equal(messageCallback({ data: '{"kind":"ping"}' }), undefined);
  adapter.sendWebSocket('aia-test', '{"kind":"hello"}');
  adapter.closeWebSocket('aia-test', 1000, 'done');

  assert.equal(received, '{"kind":"ping"}');
  assert.deepEqual(sent[0], ['aia-test', '{"kind":"hello"}']);
  assert.deepEqual(closed[0], ['aia-test', 1000, 'done']);
  assert.throws(
    () => adapter.registerWebSocket('bad', 'ws://0.0.0.0:49624', () => undefined, () => undefined),
    JlcEdaApiCallError,
  );
});

test('official host callbacks never return rejected Promises', async () => {
  const registrations: unknown[][] = [];
  const boundaryFailures: string[] = [];
  const adapter = new JlcEdaApiAdapter(runtime({
    sys_WebSocket: {
      register: (...args: unknown[]) => { registrations.push(args); },
      send: () => undefined,
      close: () => undefined,
    },
  }));
  adapter.registerWebSocket(
    'aia-test', 'ws://127.0.0.1:49624',
    () => Promise.reject(new Error('message callback rejected')),
    () => Promise.reject(new Error('connected callback rejected')),
    (detail) => { boundaryFailures.push(detail); },
  );
  const messageCallback = registrations[0]![2] as (event: { data: string }) => void;
  const connectedCallback = registrations[0]![3] as () => void;

  assert.equal(messageCallback({ data: '{"kind":"pong"}' }), undefined);
  assert.equal(connectedCallback(), undefined);
  await Promise.resolve();
  await Promise.resolve();

  assert.deepEqual(boundaryFailures.sort(), [
    'connected callback rejected',
    'message callback rejected',
  ]);
});

test('invalid client close code is rejected before reaching official runtime', () => {
  const closed: unknown[][] = [];
  const adapter = new JlcEdaApiAdapter(runtime({
    sys_WebSocket: {
      register: () => undefined,
      send: () => undefined,
      close: (...args: unknown[]) => { closed.push(args); },
    },
  }));

  assert.throws(
    () => adapter.closeWebSocket('aia-test', 1008, 'policy violation'),
    JlcEdaApiCallError,
  );
  assert.deepEqual(closed, []);
});
