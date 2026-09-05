import assert from 'node:assert/strict';
import test from 'node:test';

import {
  EdaProtocolDispatcher,
} from '../../src/runtime/eda-protocol-dispatcher.ts';
import {
  JlcEdaApiCallError,
  JlcEdaCapabilityUnavailableError,
  type CurrentDocumentReadDto,
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

test('static dispatcher rejects every operation outside the allowlist', async () => {
  let calls = 0;
  const dispatcher = new EdaProtocolDispatcher({
    async readCurrentDocument() {
      calls += 1;
      throw new Error('must not execute');
    },
  });

  const outcome = await dispatcher.dispatch({ operation: 'eda.selection.get' });

  assert.equal(outcome.status, 'error');
  assert.equal(outcome.error?.code, 'operation_not_allowed');
  assert.equal(calls, 0);
});
