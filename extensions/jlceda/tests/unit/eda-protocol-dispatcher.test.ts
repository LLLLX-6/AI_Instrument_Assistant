import assert from 'node:assert/strict';
import test from 'node:test';

import {
  EdaProtocolDispatcher,
} from '../../src/runtime/eda-protocol-dispatcher.ts';
import {
  JlcEdaApiCallError,
  JlcEdaCapabilityUnavailableError,
  type CurrentDocumentReadDto,
  type CurrentSelectionDto,
} from '../../src/runtime/jlc-eda-api-adapter.ts';


const request = Object.freeze({
  operation: 'eda.document.get_active',
});

test('static dispatcher normalizes finite DTO to wire document without tab/raw shape', async () => {
  const api = {
    async readCurrentDocument(): Promise<CurrentDocumentReadDto> {
      return {
        document: {
          provider: 'jlceda-pro',
          documentId: 'official-document-uuid',
          documentType: 'schematic',
          projectId: 'official-project-uuid',
          libraryId: null,
        },
        rawShape: {
          kind: 'object', ownKeyCount: 5,
          ownKeys: ['documentType', 'uuid', 'tabId'], unknownKeyCount: 0,
        },
      };
    },
  };
  const dispatcher = new EdaProtocolDispatcher(api, {
    now: () => new Date('2026-09-05T08:00:00Z'),
    randomUuid: () => '55555555-5555-4555-8555-555555555555',
  });

  const outcome = await dispatcher.dispatch(request);

  assert.equal(outcome.status, 'success');
  if (outcome.status !== 'success') return;
  assert.deepEqual(outcome.payload.document, {
    model_version: '1.0',
    document_ref: {
      model_version: '1.0', provider: 'jlceda-pro', object_type: 'document',
      document_id: 'official-document-uuid',
      snapshot_id: '55555555-5555-4555-8555-555555555555',
      native_id: 'official-document-uuid',
      canonical_id: 'jlceda-pro:document:official-document-uuid',
      display_name: null,
    },
    project_id: 'official-project-uuid', project_name: null,
    document_name: null, document_type: 'schematic', native_revision: null,
    fingerprint: null, is_dirty: null, captured_at: '2026-09-05T08:00:00.000Z',
  });
  assert.equal(JSON.stringify(outcome).includes('tabId'), false);
  assert.equal(JSON.stringify(outcome).includes('rawShape'), false);
});

test('static dispatcher maps no document and bounded runtime errors', async () => {
  const noDocument = new EdaProtocolDispatcher({
    async readCurrentDocument() {
      return {
        document: null,
        rawShape: { kind: 'undefined' as const, ownKeyCount: 0, ownKeys: [], unknownKeyCount: 0 },
      };
    },
  });
  assert.equal((await noDocument.dispatch(request)).error?.code, 'no_active_document');

  for (const [error, code] of [
    [new JlcEdaCapabilityUnavailableError('read'), 'capability_unsupported'],
    [new JlcEdaApiCallError('read', 'failed'), 'provider_error'],
  ] as const) {
    const dispatcher = new EdaProtocolDispatcher({
      async readCurrentDocument(): Promise<CurrentDocumentReadDto> { throw error; },
    });
    assert.equal((await dispatcher.dispatch(request)).error?.code, code);
  }
});

test('selection dispatcher creates one coherent snapshot and separates wire from derived net', async () => {
  let documentReads = 0;
  const api = {
    async readCurrentDocument(): Promise<CurrentDocumentReadDto> {
      documentReads += 1;
      return documentObservation('official-document-uuid');
    },
    async readCurrentSelection(): Promise<CurrentSelectionDto> {
      return {
        objects: [{
          primitiveId: 'wire-1', primitiveType: 'Wire', netName: 'PWM_OUT',
        }],
        totalSelected: 1, truncated: false,
        primitiveTypeSummary: { Wire: 1 },
      };
    },
  };
  const dispatcher = new EdaProtocolDispatcher(api, {
    now: () => new Date('2026-09-05T09:00:00Z'),
    randomUuid: () => '55555555-5555-4555-8555-555555555555',
  });

  const outcome = await dispatcher.dispatch({ operation: 'eda.selection.get' });

  assert.equal(outcome.status, 'success');
  if (outcome.status !== 'success') return;
  assert.equal(documentReads, 2);
  const context = outcome.payload.context as Record<string, unknown>;
  const selection = context.selection as Record<string, unknown>;
  const documentRef = selection.document_ref as Record<string, unknown>;
  const selected = (selection.selected_objects as Record<string, unknown>[])[0]!;
  const net = (context.nets as Record<string, unknown>[])[0]!;
  const netRef = net.ref as Record<string, unknown>;
  assert.equal(documentRef.snapshot_id, '55555555-5555-4555-8555-555555555555');
  assert.equal(selected.snapshot_id, documentRef.snapshot_id);
  assert.equal(netRef.snapshot_id, documentRef.snapshot_id);
  assert.equal(selected.object_type, 'wire');
  assert.equal(selected.native_id, 'wire-1');
  assert.equal(selected.provider_kind, 'Wire');
  assert.equal(netRef.object_type, 'net');
  assert.equal(netRef.native_id, null);
  assert.deepEqual(net.endpoints, []);
  assert.equal(net.source, null);
  assert.equal(net.signal_expectation, null);
  assert.equal(selection.primary_object, null);
  assert.equal(JSON.stringify(outcome).includes('primitiveTypeSummary'), false);
  assert.equal(JSON.stringify(outcome).includes('totalSelected'), false);
});

test('selection dispatcher supports empty, component, other, and unnamed-wire selections without invented nets', async () => {
  const selections: CurrentSelectionDto[] = [
    { objects: [], totalSelected: 0, truncated: false, primitiveTypeSummary: {} },
    {
      objects: [{
        primitiveId: 'component-1', primitiveType: 'Component',
        componentDesignator: 'U1',
      }],
      totalSelected: 1, truncated: false,
      primitiveTypeSummary: { Component: 1 },
    },
    {
      objects: [{ primitiveId: 'text-1', primitiveType: 'Text' }],
      totalSelected: 1, truncated: false,
      primitiveTypeSummary: { Text: 1 },
    },
    {
      objects: [{ primitiveId: 'wire-2', primitiveType: 'Wire' }],
      totalSelected: 1, truncated: false,
      primitiveTypeSummary: { Wire: 1 },
    },
  ];
  for (const current of selections) {
    const dispatcher = new EdaProtocolDispatcher({
      async readCurrentDocument() { return documentObservation('doc-1'); },
      async readCurrentSelection() { return current; },
    });
    const outcome = await dispatcher.dispatch({ operation: 'eda.selection.get' });
    assert.equal(outcome.status, 'success');
    if (outcome.status !== 'success') continue;
    const context = outcome.payload.context as Record<string, unknown>;
    assert.deepEqual(context.nets, []);
  }
});

test('selection dispatcher maps unavailable and failed provider APIs to bounded errors', async () => {
  const noSelectionApi = new EdaProtocolDispatcher({
    async readCurrentDocument() { return documentObservation('doc-1'); },
  });
  assert.equal(
    (await noSelectionApi.dispatch({ operation: 'eda.selection.get' })).error?.code,
    'capability_unsupported',
  );

  const failedSelection = new EdaProtocolDispatcher({
    async readCurrentDocument() { return documentObservation('doc-1'); },
    async readCurrentSelection(): Promise<CurrentSelectionDto> {
      throw new JlcEdaApiCallError('selection', 'failed');
    },
  });
  assert.equal(
    (await failedSelection.dispatch({ operation: 'eda.selection.get' })).error?.code,
    'provider_error',
  );
});

test('selection dispatcher rejects a document change during the observation window', async () => {
  let documentReads = 0;
  const dispatcher = new EdaProtocolDispatcher({
    async readCurrentDocument() {
      documentReads += 1;
      return documentObservation(documentReads === 1 ? 'doc-before' : 'doc-after');
    },
    async readCurrentSelection() {
      return {
        objects: [], totalSelected: 0, truncated: false,
        primitiveTypeSummary: {},
      };
    },
  });

  const outcome = await dispatcher.dispatch({ operation: 'eda.selection.get' });

  assert.equal(outcome.status, 'error');
  assert.equal(outcome.error?.code, 'inconsistent_observation');
});

test('selection dispatcher rejects truncated provider observations', async () => {
  const dispatcher = new EdaProtocolDispatcher({
    async readCurrentDocument() { return documentObservation('doc-1'); },
    async readCurrentSelection() {
      return {
        objects: [], totalSelected: 129, truncated: true,
        primitiveTypeSummary: { Text: 128 },
      };
    },
  });

  const outcome = await dispatcher.dispatch({ operation: 'eda.selection.get' });

  assert.equal(outcome.status, 'error');
  assert.equal(outcome.error?.code, 'provider_error');
});

test('static dispatcher rejects every operation outside the allowlist', async () => {
  let calls = 0;
  const dispatcher = new EdaProtocolDispatcher({
    async readCurrentDocument() {
      calls += 1;
      throw new Error('must not execute');
    },
  });

  const outcome = await dispatcher.dispatch({ operation: 'eda.design.modify' });

  assert.equal(outcome.status, 'error');
  assert.equal(outcome.error?.code, 'operation_not_allowed');
  assert.equal(calls, 0);
});

function documentObservation(documentId: string): CurrentDocumentReadDto {
  return {
    document: {
      provider: 'jlceda-pro', documentId, documentType: 'schematic',
      projectId: null, libraryId: null,
    },
    rawShape: {
      kind: 'object', ownKeyCount: 2,
      ownKeys: ['documentType', 'uuid'], unknownKeyCount: 0,
    },
  };
}
