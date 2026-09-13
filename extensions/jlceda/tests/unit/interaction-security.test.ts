import assert from 'node:assert/strict';
import test from 'node:test';

import { InteractionSurface } from '../../src/interaction/interaction-surface.ts';

test('changed candidate set while dialog is open fails closed with zero answer', async () => {
  const challenge = selectionChallenge(['candidate:a', 'candidate:b']);
  const client: any = {
    state: 'CONNECTED', answers: [], commands: [],
    snapshot: { workflows: [], pending_challenges: [challenge] },
    start() {}, stop() {}, requestSnapshot() {}, sendCommand() {},
    answerChallenge(value: unknown, answer: unknown) { this.answers.push({ value, answer }); },
  };
  const ui = {
    showInformation() {}, async confirm() { return false; },
    async select() {
      client.snapshot = { workflows: [], pending_challenges: [selectionChallenge(['candidate:a', 'candidate:c'])] };
      return 'candidate:a';
    },
  };
  await assert.rejects(() => new InteractionSurface(ui, client).resolvePendingAction(), /challenge_stale/);
  assert.equal(client.answers.length, 0);
});

test('forged candidate identity and cancellation create no answer', async () => {
  const challenge = selectionChallenge(['candidate:a', 'candidate:b']);
  const client: any = { state: 'CONNECTED', answers: [], snapshot: { workflows: [], pending_challenges: [challenge] },
    start() {}, stop() {}, requestSnapshot() {}, sendCommand() {}, answerChallenge() { this.answers.push(1); } };
  for (const selected of ['candidate:forged', null]) {
    const ui = { showInformation() {}, async confirm() { return false; }, async select() { return selected; } };
    await new InteractionSurface(ui, client).resolvePendingAction();
  }
  assert.equal(client.answers.length, 0);
});

function selectionChallenge(candidates: string[]): any {
  return { challenge_id: 'challenge', challenge_kind: 'DESIGN_SELECTION', application_generation: 'app',
    workflow_id: 'wf', workflow_revision: 2, request_correlation_id: 'r', allowed_frontend_kind: 'JLCEDA',
    issued_at: '2026-09-12T08:00:00Z', expires_at: '2099-09-12T08:00:00Z', nonce: 'n'.repeat(24),
    binding: { observation_identity: 'sha256:' + 'a'.repeat(64), candidate_set_identity: 'sha256:' + (candidates[1] === 'candidate:b' ? 'b' : 'c').repeat(64), allowed_candidate_identities: candidates } };
}
