import assert from 'node:assert/strict';
import test from 'node:test';

import { InteractionSurface } from '../../src/interaction/interaction-surface.ts';
import type { InteractiveConnectionState } from '../../src/interaction/interactive-client.ts';

class FakeUi {
  information: string[] = []; confirmations: Array<{ content: string; answer: boolean }> = [];
  selections: Array<{ options: ReadonlyArray<{ value: string; displayContent: string }>; answer: string | null }> = [];
  selectionCalls: ReadonlyArray<{ value: string; displayContent: string }>[] = [];
  showInformation(content: string): void { this.information.push(content); }
  async confirm(content: string): Promise<boolean> { const next = this.confirmations.shift(); assert.ok(next); next.content = content; return next.answer; }
  async select(options: ReadonlyArray<{ value: string; displayContent: string }>): Promise<string | null> { this.selectionCalls.push(options); const next = this.selections.shift(); assert.ok(next); return next.answer; }
}

class FakeClient {
  state: InteractiveConnectionState = 'CONNECTED'; answers: unknown[] = []; commands: unknown[] = [];
  snapshot: any = { application_generation: 'app', event_cursor: 1,
    status: { host_state: 'READY', harness_state: 'DISCONNECTED', hardware_state: 'UNAVAILABLE', workflow_state: 'WAITING_FOR_DESIGN_SELECTION', safe_workflow_label: 'PWM_OUT', message: 'Ready.' },
    workflows: [{ workflow_id: 'wf', revision: 2, state: 'WAITING_FOR_DESIGN_SELECTION', safe_label: 'PWM_OUT', terminal: false, pending_challenge_ids: ['challenge'] }],
    pending_challenges: [] };
  requestSnapshot(): void {}
  sendCommand(command: string, payload: unknown): void { this.commands.push({ command, payload }); }
  answerChallenge(challenge: unknown, answer: unknown): void { this.answers.push({ challenge, answer }); }
  stop(): void { this.state = 'DISCONNECTED'; }
  start(): void { this.state = 'CONNECTED'; }
}

test('design selection returns exact option identity, independent of display order', async () => {
  const ui = new FakeUi(); const client = new FakeClient();
  const first = 'candidate:wire-exact'; const second = 'candidate:component-exact';
  client.snapshot.pending_challenges = [challenge('DESIGN_SELECTION', {
    observation_identity: 'sha256:' + 'a'.repeat(64), candidate_set_identity: 'sha256:' + 'b'.repeat(64),
    allowed_candidate_identities: [first, second],
  })];
  ui.selections.push({ options: [], answer: first });
  await new InteractionSurface(ui, client as any).resolvePendingAction();
  assert.equal((client.answers[0] as any).answer.candidate_identity, first);
  assert.equal(ui.selectionCalls[0]![0]!.value, first);
  assert.notEqual(ui.selectionCalls[0]![0]!.displayContent, first);
});

test('physical setup is deferred to Harness and sends no answer', async () => {
  const ui = new FakeUi(); const client = new FakeClient();
  client.snapshot.pending_challenges = [challenge('PHYSICAL_SETUP', {
    probe_target_identity: 'target:pwm', operation_plan_identity: 'sha256:' + 'c'.repeat(64),
    channel: 1, maximum_expected_voltage_v: 3.3,
    probe_statement: 'Probe statement', ground_statement: 'Ground statement',
    voltage_statement: 'Voltage statement', wiring_statement: 'Wiring statement',
  })];
  await new InteractionSurface(ui, client as any).resolvePendingAction();
  assert.equal(client.answers.length, 0);
  assert.equal(ui.confirmations.length, 0);
  assert.match(ui.information[0]!, /Continue authorization in DeepSeek Harness/);
});

test('operation authorization is deferred to Harness and sends no answer', async () => {
  const ui = new FakeUi(); const client = new FakeClient();
  client.snapshot.pending_challenges = [challenge('OPERATION_AUTHORIZATION', {
    operation_plan_identity: 'sha256:' + 'd'.repeat(64), semantic_operations: ['hardware.measure_pwm'],
    channel: 1, budgets: [{ operation: 'hardware.measure_pwm', maximum_invocations: 1 }],
  })];
  await new InteractionSurface(ui, client as any).resolvePendingAction();
  assert.equal(client.answers.length, 0);
  assert.equal(ui.confirmations.length, 0);
  assert.match(ui.information[0]!, /Continue authorization in DeepSeek Harness/);
});

test('cancel command keeps exact Host workflow and revision binding', () => {
  const ui = new FakeUi(); const client = new FakeClient();
  new InteractionSurface(ui, client as any).cancelWorkflow();
  assert.deepEqual(client.commands[0], {
    command: 'workflow.cancel', payload: { workflow_id: 'wf', expected_workflow_revision: 2, reason: 'user_cancelled' },
  });
});

test('status presentation excludes transport and secret details', () => {
  const ui = new FakeUi(); const client = new FakeClient();
  new InteractionSurface(ui, client as any).showStatus();
  const rendered = ui.information[0]!;
  assert.match(rendered, /Connected/); assert.match(rendered, /PWM_OUT/);
  assert.match(rendered, /Design selection authority: Available/);
  assert.match(rendered, /Operation authorization: Continue authorization in DeepSeek Harness/);
  assert.match(rendered, /Physical confirmation: Continue authorization in DeepSeek Harness/);
  assert.doesNotMatch(rendered, /49626|session|secret|VISA|SCPI/i);
});

function challenge(kind: string, binding: unknown): any {
  return { challenge_id: 'challenge', challenge_kind: kind, application_generation: 'app',
    workflow_id: 'wf', workflow_revision: 2, request_correlation_id: 'r', allowed_frontend_kind: 'JLCEDA',
    issued_at: '2026-09-12T08:00:00Z', expires_at: '2099-09-12T08:00:00Z', nonce: 'n'.repeat(24), binding };
}
