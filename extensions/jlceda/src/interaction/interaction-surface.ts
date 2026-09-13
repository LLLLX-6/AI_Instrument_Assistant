import type { InteractiveConnectionState, InteractiveSnapshot } from './interactive-client.ts';

export interface OfficialDialogUi {
  showInformation(content: string, title?: string): void;
  confirm(content: string, title?: string, accept?: string, cancel?: string): Promise<boolean>;
  select(options: ReadonlyArray<{ value: string; displayContent: string }>, before?: string, after?: string, title?: string): Promise<string | null>;
}
export interface InteractionClientPort {
  readonly state: InteractiveConnectionState;
  readonly snapshot: InteractiveSnapshot | null;
  start(): void; stop(): void; requestSnapshot(): void;
  sendCommand(command: string, payload: unknown): void;
  answerChallenge(challenge: Readonly<Record<string, unknown>>, answer: unknown): void;
}

export class InteractionSurface {
  readonly #ui: OfficialDialogUi;
  readonly #client: InteractionClientPort;
  readonly #selectionLabel: () => string;
  constructor(ui: OfficialDialogUi, client: InteractionClientPort, selectionLabel: () => string = () => 'Not observed') {
    this.#ui = ui; this.#client = client; this.#selectionLabel = selectionLabel;
  }

  showStatus(): void {
    const snapshot = this.#client.snapshot; const status = snapshot?.status;
    this.#ui.showInformation([
      `AI Instrument Assistant: ${this.#client.state === 'CONNECTED' ? 'Connected' : 'Disconnected'}`,
      `Application Host: ${text(status?.host_state, 'Unavailable')}`,
      `Workflow: ${text(status?.workflow_state, 'Idle')}`,
      `Workflow label: ${text(status?.safe_workflow_label, 'None')}`,
      `Harness: ${text(status?.harness_state, 'Disconnected')}`,
      `Hardware: ${text(status?.hardware_state, 'Unavailable')}`,
      `Current selection: ${text(this.#selectionLabel(), 'Not observed')}`,
      'Resolved target: Host workflow state only',
      'Design selection authority: Available',
      'Operation authorization: Continue authorization in DeepSeek Harness',
      'Physical confirmation: Continue authorization in DeepSeek Harness',
      `Pending action: ${snapshot?.pending_challenges.length ?? 0}`,
    ].join('\n'), 'AI Instrument Assistant — Status');
  }

  refreshDesignContext(): void {
    const workflow = this.#currentWorkflow();
    this.#client.sendCommand('design.observe', { workflow_id: workflow.workflow_id, expected_workflow_revision: workflow.revision });
  }
  highlightTarget(): void {
    const workflow = this.#currentWorkflow();
    this.#client.sendCommand('view.highlight', { workflow_id: workflow.workflow_id, expected_workflow_revision: workflow.revision });
  }
  cancelWorkflow(): void {
    const workflow = this.#currentWorkflow();
    this.#client.sendCommand('workflow.cancel', { workflow_id: workflow.workflow_id, expected_workflow_revision: workflow.revision, reason: 'user_cancelled' });
  }
  showCurrentTarget(): void {
    const workflow = this.#currentWorkflow();
    const resolvedStates = new Set([
      'TARGET_RESOLVED', 'OPERATION_PREPARED', 'WAITING_FOR_OPERATION_AUTHORIZATION',
      'WAITING_FOR_PHYSICAL_CONFIRMATION', 'READY_TO_EXECUTE', 'CONNECTING_INSTRUMENT',
      'MEASURING', 'ANALYZING', 'BUILDING_EVIDENCE', 'GENERATING_TEACHING_RESPONSE', 'COMPLETE',
    ]);
    if (!resolvedStates.has(String(workflow.state))) throw new Error('target_unavailable');
    this.#ui.showInformation([
      `Resolved design target: ${text(workflow.safe_label, 'Unavailable')}`,
      'Source: current Host workflow projection',
      'Snapshot: observation identity only',
      'Physical probe: not implied by design resolution',
    ].join('\n'), 'AI Instrument Assistant — Current Target');
  }
  showEvidenceSummary(): void {
    const ready = this.#client.snapshot?.workflows.some((value) => value.state === 'COMPLETE') === true;
    this.#ui.showInformation(ready
      ? 'A bounded evidence/teaching result is available in Harness. JLCEDA does not expose artifact bodies or raw model output.'
      : 'No bounded evidence summary is currently available.', 'AI Instrument Assistant — Evidence');
  }

  async resolvePendingAction(): Promise<void> {
    const challenge = this.#currentChallenge();
    if (challenge.challenge_kind === 'DESIGN_SELECTION') await this.#designSelection(challenge);
    else if (challenge.challenge_kind === 'OPERATION_AUTHORIZATION') this.#showHarnessDeferral('Operation authorization');
    else if (challenge.challenge_kind === 'PHYSICAL_SETUP') this.#showHarnessDeferral('Physical setup confirmation');
    else throw new Error('pending_action_unsupported');
  }

  async #designSelection(challenge: Readonly<Record<string, unknown>>): Promise<void> {
    const binding = challenge.binding as Readonly<Record<string, unknown>>;
    const candidates = binding.allowed_candidate_identities as readonly string[];
    const options = candidates.map((identity, index) => ({ value: identity, displayContent: `Design candidate ${String.fromCharCode(65 + index)} — exact Host identity retained` }));
    const selected = await this.#ui.select(options, '请选择要作为测量目标的设计对象。', 'Displayed labels are presentation only.', 'AI Instrument Assistant');
    if (selected === null || !candidates.includes(selected)) return;
    this.#ensureCurrent(challenge);
    this.#client.answerChallenge(challenge, { candidate_set_identity: binding.candidate_set_identity, candidate_identity: selected });
  }
  #showHarnessDeferral(capability: string): void {
    this.#ui.showInformation(
      `${capability} is intentionally owned by the DeepSeek Harness. Continue authorization in DeepSeek Harness.`,
      'AI Instrument Assistant — Continue in Harness',
    );
  }
  #currentChallenge(): Readonly<Record<string, unknown>> {
    const values = this.#client.snapshot?.pending_challenges ?? [];
    const value = values.find((item) => item.allowed_frontend_kind === 'JLCEDA');
    if (value === undefined) throw new Error('pending_action_unavailable');
    return value;
  }
  #ensureCurrent(challenge: Readonly<Record<string, unknown>>): void {
    const current = this.#client.snapshot?.pending_challenges.find((item) => item.challenge_id === challenge.challenge_id);
    if (current === undefined || current.workflow_revision !== challenge.workflow_revision
      || current.application_generation !== challenge.application_generation
      || JSON.stringify(current) !== JSON.stringify(challenge)) throw new Error('challenge_stale');
  }
  #currentWorkflow(): Readonly<Record<string, unknown>> {
    const values = this.#client.snapshot?.workflows ?? [];
    const value = [...values].reverse().find((item) => item.terminal !== true);
    if (value === undefined) throw new Error('workflow_unavailable');
    return value;
  }
}

function text(value: unknown, fallback: string): string {
  if (typeof value === 'string' && value.length > 0) return value.replace(/[\u0000-\u001f\u007f]/g, ' ').slice(0, 120);
  if (typeof value === 'number') return String(value);
  return fallback;
}
