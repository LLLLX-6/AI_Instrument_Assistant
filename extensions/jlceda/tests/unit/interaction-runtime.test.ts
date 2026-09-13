import assert from 'node:assert/strict';
import test from 'node:test';

import { JlcEdaApiAdapter, type JlcEdaRuntimeBoundary } from '../../src/runtime/jlc-eda-api-adapter.ts';

test('official confirmation and select surfaces preserve hidden exact values', async () => {
  let confirmation = false; let selected = '';
  const runtime: JlcEdaRuntimeBoundary = { sys_Dialog: {
    showConfirmationMessage: (_content, _title, _accept, _cancel, callback) => { callback?.(true); },
    showSelectDialog: (options, _before, _after, _title, _default, _multiple, callback) => {
      const values = options as Array<{ value: string; displayContent: string }>;
      selected = values[1]!.value; void (callback as ((value: string) => void) | undefined)?.(selected);
    },
  } };
  const api = new JlcEdaApiAdapter(runtime);
  confirmation = await api.showConfirmation('Bounded statement');
  const result = await api.showSelection([
    { value: 'candidate:one', displayContent: 'Same name' },
    { value: 'candidate:two', displayContent: 'Same name' },
  ]);
  assert.equal(confirmation, true); assert.equal(result, 'candidate:two'); assert.equal(selected, 'candidate:two');
});

test('selection listener replaces a stale same-id registration and removes idempotently', () => {
  const listeners = new Map<string, () => void>();
  let removals = 0;
  const runtime: JlcEdaRuntimeBoundary = { sch_Event: {
    addMouseEventListener: (id, _event, callback) => { listeners.set(id, () => { void callback('all' as any); }); },
    removeEventListener: (id) => { removals += 1; return listeners.delete(id); },
    isEventListenerAlreadyExist: (id) => listeners.has(id),
  } };
  const api = new JlcEdaApiAdapter(runtime);
  assert.equal(api.registerSelectionListener('aia-listener', () => undefined), true);
  assert.equal(api.registerSelectionListener('aia-listener', () => undefined), true);
  assert.equal(removals, 1);
  assert.equal(api.removeSelectionListener('aia-listener'), true);
  assert.equal(api.removeSelectionListener('aia-listener'), true);
});

test('only non-secret interactive port configuration is persisted', async () => {
  const storage = new Map<string, unknown>();
  const api = new JlcEdaApiAdapter({ sys_Storage: {
    getExtensionUserConfig: (key) => storage.get(key),
    setExtensionUserConfig: async (key, value) => { storage.set(key, value); return true; },
  } });
  assert.equal(api.readInteractivePort(49_626), 49_626);
  assert.equal(await api.writeInteractivePort(50_001), true);
  assert.deepEqual([...storage.entries()], [['aia_interactive_port', 50_001]]);
  await assert.rejects(() => api.writeInteractivePort(49_625));
});
