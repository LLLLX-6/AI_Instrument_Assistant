import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { EdaProtocolDispatcher } from '../../src/runtime/eda-protocol-dispatcher.ts';
import { JlcEdaApiAdapter, type JlcEdaRuntimeBoundary } from '../../src/runtime/jlc-eda-api-adapter.ts';

const fixture = JSON.parse(readFileSync(new URL('../../../../protocols/jlceda/v1/fixtures/valid/highlight/request.case.json', import.meta.url), 'utf8')).instance;
const live = { isActive: () => true };
function setup(accept: boolean | Error = true) {
  const calls: unknown[][] = [];
  let doc = 'doc-1';
  const wire = { getState_PrimitiveType: () => 'Wire', getState_Net: () => 'PWM_OUT' };
  const component = { getState_PrimitiveType: () => 'Component', getState_Designator: () => 'U1' };
  const runtime = {
    dmt_SelectControl: { getCurrentDocumentInfo: async () => ({ uuid: doc, documentType: 1 }) },
    sch_PrimitiveWire: { get: async (id: string) => id === 'wire-1' ? wire : undefined,
      getAll: async () => [wire] },
    sch_PrimitiveComponent: { get: async (id: string) => id === 'component-1' ? component : undefined,
      getAll: async () => [component] },
    sch_SelectControl: { doCrossProbeSelect: (...args: unknown[]) => {
      calls.push(args); if (accept instanceof Error) throw accept; return accept;
    }},
  } as unknown as JlcEdaRuntimeBoundary;
  return { calls, runtime, setDoc: (id: string) => { doc = id; },
    dispatcher: new EdaProtocolDispatcher(new JlcEdaApiAdapter(runtime)) };
}
function request(changes: Record<string, unknown> = {}) {
  const value = structuredClone(fixture);
  Object.assign(value.payload.command, changes);
  return value;
}
test('highlight true is accepted/unverified; explicit expansion preserves requested wire identity', async () => {
  const { dispatcher, calls } = setup();
  const result = await dispatcher.dispatch(request(), live);
  assert.equal(result.status, 'success');
  const value = result.payload!.result as Record<string, unknown>;
  assert.equal(value.submission_status, 'accepted');
  assert.equal(value.verification_status, 'unverified');
  assert.equal(value.scope_expansion, 'wire_to_net');
  assert.deepEqual(value.verified_applied_targets, []);
  assert.equal(value.expires_at, null);
  assert.deepEqual(calls, [[[], [], ['PWM_OUT'], true, false]]);
});
test('highlight guards and unsupported requests have zero effects', async () => {
  for (const [change, code] of [
    [{ guard_mode: 'strong_required' }, 'strong_guard_unavailable'],
    [{ allow_scope_expansion: false }, 'scope_expansion_required'],
    [{ ttl_ms: 500 }, 'presentation_unsupported'],
    [{ style: 'analysis' }, 'presentation_unsupported'],
    [{ replace_existing: true }, 'presentation_unsupported'],
    [{ replace_existing: false }, 'presentation_unsupported'],
  ] as const) {
    const { dispatcher, calls } = setup();
    const outcome = await dispatcher.dispatch(request(change), live);
    assert.equal(outcome.error?.code, code);
    assert.equal(calls.length, 0);
  }
});
test('malformed and inactive highlight requests have zero effects', async () => {
  const { dispatcher, calls } = setup();
  assert.equal((await dispatcher.dispatch(request({ raw: {} }), live)).status, 'error');
  assert.equal((await dispatcher.dispatch(request(), { isActive: () => false })).status, 'error');
  assert.equal((await dispatcher.dispatch(request())).status, 'error');
  assert.equal(calls.length, 0);
});
test('document mismatch and unknown target reject before effect', async () => {
  const { dispatcher, calls, setDoc } = setup();
  setDoc('another-doc');
  assert.equal((await dispatcher.dispatch(request(), live)).error?.code, 'stale_design_snapshot');
  setDoc('doc-1');
  const r = request({ idempotency_key: 'missing' });
  r.payload.command.targets[0].native_id = 'missing';
  assert.equal((await dispatcher.dispatch(r, live)).error?.code, 'object_not_found');
  assert.equal(calls.length, 0);
});
test('provider false rejects and exceptions preserve uncertainty without raw error', async () => {
  for (const flag of [false, new Error('private-provider-secret')]) {
    const { dispatcher, calls } = setup(flag);
    const outcome = await dispatcher.dispatch(request(), live);
    const value = outcome.payload!.result as Record<string, unknown>;
    assert.equal(value.submission_status, flag === false ? 'rejected' : 'indeterminate');
    assert.equal(value.verification_status, 'unverified');
    assert.equal(calls.length, 1);
    assert.equal(JSON.stringify(outcome).includes('private-provider-secret'), false);
  }
});
test('concurrent duplicate keys run once; changed canonical command conflicts', async () => {
  const { dispatcher, calls } = setup();
  const [a, b] = await Promise.all([dispatcher.dispatch(request(), live), dispatcher.dispatch(request(), live)]);
  assert.deepEqual(a, b);
  assert.equal(calls.length, 1);
  assert.equal((await dispatcher.dispatch(request({ allow_scope_expansion: false }), live)).error?.code, 'idempotency_conflict');
});
test('component resolves a designator, never uses a primitive id as designator', async () => {
  const { dispatcher, calls } = setup();
  const r = request();
  Object.assign(r.payload.command.targets[0], { object_type: 'component', native_id: 'component-1', provider_kind: 'Component' });
  const outcome = await dispatcher.dispatch(r, live);
  assert.equal(outcome.status, 'success');
  assert.deepEqual(calls, [[['U1'], [], [], true, false]]);
});
test('ambiguous component, unsupported object, and unavailable API reject without effects', async () => {
  const { dispatcher, calls, runtime } = setup();
  const r = request();
  Object.assign(r.payload.command.targets[0], { object_type: 'component', native_id: 'component-1' });
  const component = { getState_Designator: () => 'U1' };
  Object.assign(runtime.sch_PrimitiveComponent!, { getAll: async () => [component, component] });
  assert.equal((await dispatcher.dispatch(r, live)).error?.code, 'ambiguous_target');
  const unsupported = request({ idempotency_key: 'other' });
  unsupported.payload.command.targets[0].object_type = 'other';
  assert.equal((await dispatcher.dispatch(unsupported, live)).error?.code, 'unsupported_target');
  Object.assign(runtime.sch_SelectControl!, { doCrossProbeSelect: undefined });
  assert.equal((await dispatcher.dispatch(request({ idempotency_key: 'unavailable' }), live)).error?.code, 'capability_unsupported');
  assert.equal(calls.length, 0);
});
test('session lost during read-only resolution prevents invocation; lost after invocation is indeterminate', async () => {
  for (const after of [false, true]) {
    const { dispatcher, calls, runtime } = setup();
    let active = true;
    if (after) {
      Object.assign(runtime.sch_SelectControl!, { doCrossProbeSelect: (...args: unknown[]) => {
        calls.push(args); active = false; return true;
      }});
    } else {
      const get = runtime.sch_PrimitiveWire!.get!;
      Object.assign(runtime.sch_PrimitiveWire!, { get: async (id: string) => {
        const result = await get(id); active = false; return result;
      }});
    }
    const outcome = await dispatcher.dispatch(request(), { isActive: () => active });
    assert.equal(calls.length, after ? 1 : 0);
    if (after) {
      assert.equal((outcome.payload!.result as Record<string, unknown>).submission_status, 'indeterminate');
      active = true;
      assert.deepEqual(await dispatcher.dispatch(request(), live), outcome);
      assert.equal(calls.length, 1);
    } else assert.equal(outcome.error?.code, 'session_invalid');
  }
});
test('net references are resolved by official net membership, not canonical/native ids', async () => {
  const { dispatcher, calls } = setup();
  const r = request({ allow_scope_expansion: false });
  Object.assign(r.payload.command.targets[0], { object_type: 'net', native_id: null, display_name: 'PWM_OUT' });
  const outcome = await dispatcher.dispatch(r, live);
  assert.equal((outcome.payload!.result as Record<string, unknown>).scope_expansion, 'none');
  assert.deepEqual(calls, [[[], [], ['PWM_OUT'], true, false]]);
});
test('idempotency survives new session/message envelopes and canonical property order', async () => {
  const { dispatcher, calls } = setup();
  const first = await dispatcher.dispatch(request(), live);
  const again = request();
  again.message_id = crypto.randomUUID();
  again.session_id = crypto.randomUUID();
  again.payload.command = Object.fromEntries(Object.entries(again.payload.command).reverse());
  assert.deepEqual(await dispatcher.dispatch(again, live), first);
  assert.equal(calls.length, 1);
});
