import assert from 'node:assert/strict';
import test from 'node:test';

import { EdaProtocolDispatcher } from '../../src/runtime/eda-protocol-dispatcher.ts';
import {
  JlcEdaApiAdapter,
  type CurrentDocumentReadDto,
  type JlcEdaRuntimeBoundary,
} from '../../src/runtime/jlc-eda-api-adapter.ts';


function pin(x: number, y: number, number: string): ISCH_PrimitiveComponentPin {
  return {
    getState_X: () => x,
    getState_Y: () => y,
    getState_PinName: () => number,
    getState_PinNumber: () => number,
  } as unknown as ISCH_PrimitiveComponentPin;
}

function component(
  id: string, designator: string | undefined, name: string,
  value: string | undefined, pins: ISCH_PrimitiveComponentPin[],
  providerKind = 'part', net?: string,
): ISCH_PrimitiveComponent {
  return {
    getState_PrimitiveId: () => id,
    getState_ComponentType: () => providerKind,
    getState_Designator: () => designator,
    getState_Name: () => name,
    getState_Net: () => net,
    getState_OtherProperty: () => value === undefined ? undefined : { Value: value, Secret: 'not-projected' },
    getAllPins: async () => pins,
  } as unknown as ISCH_PrimitiveComponent;
}

function wire(net: string, line: number[]): ISCH_PrimitiveWire {
  return {
    getState_Net: () => net,
    getState_Line: () => line,
  } as unknown as ISCH_PrimitiveWire;
}

function runtime(): JlcEdaRuntimeBoundary {
  const components = [
    component('r1', 'R1', 'Resistor', '159.155 kOhm', [pin(0, 0, '1'), pin(10, 0, '2')]),
    component('c1', 'C1', 'Capacitor', '1 nF', [pin(10, 0, '1'), pin(10, 10, '2')]),
    component('g1', undefined, 'Ground', undefined, [pin(10, 10, '1')], 'Ground', 'GND'),
  ];
  const wires = [
    wire('VIN', [-10, 0, 0, 0]),
    wire('VOUT', [10, 0, 20, 0]),
    wire('GND', [10, 10, 20, 10]),
  ];
  return {
    sch_PrimitiveComponent: { getAll: async () => components },
    sch_PrimitiveWire: { getAll: async () => wires },
  };
}

test('adapter reads bounded full design and derives connectivity from geometry', async () => {
  const result = await new JlcEdaApiAdapter(runtime()).readCurrentDesign();

  assert.equal(result.components.length, 3);
  assert.equal(result.nets.length, 3);
  assert.equal(result.components[0]!.componentKind, 'resistor');
  assert.equal(result.components[0]!.pins[1]!.netName, 'VOUT');
  assert.equal(result.components[1]!.pins[1]!.netName, 'GND');
  assert.equal(result.nets.find((net) => net.netName === 'GND')?.isReference, true);
  const serialized = JSON.stringify(result);
  assert.equal(serialized.includes('Secret'), false);
  assert.equal(serialized.includes('getState'), false);
  assert.equal(serialized.includes('"x"'), false);
});

test('dispatcher creates one coherent full-design wire snapshot', async () => {
  const adapter = new JlcEdaApiAdapter(runtime());
  const document: CurrentDocumentReadDto = {
    document: { provider: 'jlceda-pro', documentId: 'doc-rc', documentType: 'schematic', projectId: null, libraryId: null },
    rawShape: { kind: 'object', ownKeyCount: 1, ownKeys: ['uuid'], unknownKeyCount: 0 },
  };
  const dispatcher = new EdaProtocolDispatcher({
    readCurrentDocument: async () => document,
    readCurrentDesign: () => adapter.readCurrentDesign(),
  }, {
    now: () => new Date('2026-09-13T00:00:00Z'),
    randomUuid: () => '11111111-1111-4111-8111-111111111111',
  });

  const outcome = await dispatcher.dispatch({ operation: 'eda.design.get' });

  assert.equal(outcome.status, 'success');
  if (outcome.status !== 'success') return;
  const observation = outcome.payload.observation as Record<string, unknown>;
  assert.equal((observation.components as unknown[]).length, 3);
  assert.equal((observation.nets as unknown[]).length, 3);
  assert.equal(JSON.stringify(outcome).includes('rawShape'), false);
  assert.equal(JSON.stringify(outcome).includes('Secret'), false);
});

test('full-design observation fails closed for unavailable API and document change', async () => {
  const document = (id: string): CurrentDocumentReadDto => ({
    document: { provider: 'jlceda-pro', documentId: id, documentType: 'schematic', projectId: null, libraryId: null },
    rawShape: { kind: 'object', ownKeyCount: 1, ownKeys: ['uuid'], unknownKeyCount: 0 },
  });
  const unsupported = new EdaProtocolDispatcher({ readCurrentDocument: async () => document('a') });
  assert.equal((await unsupported.dispatch({ operation: 'eda.design.get' })).error?.code, 'capability_unsupported');

  let reads = 0;
  const changed = new EdaProtocolDispatcher({
    readCurrentDocument: async () => document(++reads === 1 ? 'a' : 'b'),
    readCurrentDesign: async () => ({ components: [], nets: [], truncated: false }),
  });
  assert.equal((await changed.dispatch({ operation: 'eda.design.get' })).error?.code, 'inconsistent_observation');
});
