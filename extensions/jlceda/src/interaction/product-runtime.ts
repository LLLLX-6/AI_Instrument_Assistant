import type { JlcEdaApiAdapter } from '../runtime/jlc-eda-api-adapter.ts';
import type { WebSocketTransport } from '../transport/websocket-transport.ts';
import {
  boundedDiagnosticError,
  noAiaDiagnostics,
  type AiaDiagnosticSink,
} from './debug-diagnostics.ts';
import { InteractionSurface } from './interaction-surface.ts';
import {
  InteractiveClient,
  type InteractiveConnectionState,
  type InteractiveClientDiagnostics,
} from './interactive-client.ts';
import { OfficialJlcEdaDialogUi } from './official-dialog-ui.ts';
import { SelectionObserver } from './selection-observer.ts';

const LISTENER_ID = 'aia_interactive_selection_observer_v1';
let nextRuntimeDebugNo = 0;

export interface InteractionRuntimeDiagnostics extends InteractiveClientDiagnostics {
  readonly statusActionSnapshotResolvedCount: number;
  readonly statusDialogRenderAttemptCount: number;
  readonly statusDialogRenderSuccessCount: number;
}

export class PendingDesignRefresh {
  #needed = false;
  #active = true;
  #inFlightWorkflow: string | null = null;

  selectionChanged(
    state: string,
    workflow: string | null,
    dispatch: () => boolean,
  ): void {
    if (!this.#active) return;
    this.#needed = true;
    this.#dispatchIfReady(state, workflow, dispatch);
  }

  synchronized(
    state: string,
    workflow: string | null,
    dispatch: () => boolean,
  ): void {
    if (!this.#active) return;
    if (this.#inFlightWorkflow !== null && this.#inFlightWorkflow !== workflow) {
      this.#inFlightWorkflow = null;
    }
    this.#dispatchIfReady(state, workflow, dispatch);
  }

  dispose(): void {
    this.#active = false; this.#needed = false; this.#inFlightWorkflow = null;
  }

  #dispatchIfReady(
    state: string,
    workflow: string | null,
    dispatch: () => boolean,
  ): void {
    if (!this.#needed || state !== 'CONNECTED' || workflow === null
      || this.#inFlightWorkflow !== null) return;
    if (!dispatch()) return;
    this.#needed = false;
    this.#inFlightWorkflow = workflow;
  }
}

export class JlcEdaInteractionRuntime {
  readonly #api: JlcEdaApiAdapter;
  readonly #transport: WebSocketTransport;
  readonly #ui: OfficialJlcEdaDialogUi;
  readonly #diagnostic: AiaDiagnosticSink;
  readonly #onConnected: (runtimeNo: number) => void;
  readonly #debugRuntimeNo: number;
  #client: InteractiveClient | null = null;
  #surface: InteractionSurface | null = null;
  #observer: SelectionObserver | null = null;
  #pendingDesignRefresh: PendingDesignRefresh | null = null;
  #generation = 0;
  #statusActionSnapshotResolvedCount = 0;
  #statusDialogRenderAttemptCount = 0;
  #statusDialogRenderSuccessCount = 0;

  constructor(
    api: JlcEdaApiAdapter,
    transport: WebSocketTransport,
    diagnostic: AiaDiagnosticSink = noAiaDiagnostics,
    onConnected: (runtimeNo: number) => void = () => undefined,
  ) {
    this.#api = api; this.#transport = transport; this.#ui = new OfficialJlcEdaDialogUi(api);
    this.#diagnostic = diagnostic;
    this.#onConnected = onConnected;
    this.#debugRuntimeNo = ++nextRuntimeDebugNo;
    this.#log('created', { generation: this.#generation });
  }

  get state(): InteractiveConnectionState { return this.#client?.state ?? 'DISCONNECTED'; }
  get debugRuntimeNo(): number { return this.#debugRuntimeNo; }
  get clientPresent(): boolean { return this.#client !== null; }
  get diagnostics(): InteractionRuntimeDiagnostics {
    return Object.freeze({
      ...(this.#client?.diagnostics ?? emptyClientDiagnostics()),
      statusActionSnapshotResolvedCount: this.#statusActionSnapshotResolvedCount,
      statusDialogRenderAttemptCount: this.#statusDialogRenderAttemptCount,
      statusDialogRenderSuccessCount: this.#statusDialogRenderSuccessCount,
    });
  }

  async configure(port: number, secret: Uint8Array): Promise<void> {
    this.#log('configure_entered', { generation: this.#generation });
    this.dispose();
    this.#statusActionSnapshotResolvedCount = 0;
    this.#statusDialogRenderAttemptCount = 0;
    this.#statusDialogRenderSuccessCount = 0;
    const generation = ++this.#generation;
    await this.#api.writeInteractivePort(port);
    if (this.#generation !== generation) return;
    const pendingDesignRefresh = new PendingDesignRefresh();
    this.#pendingDesignRefresh = pendingDesignRefresh;
    const dispatchObservation = (): boolean => {
      if (this.#generation !== generation || this.#client !== client) return false;
      try {
        this.#surface?.refreshDesignContext();
        return this.#surface !== null;
      }
      catch { return false; /* Host state remains authoritative */ }
    };
    const client = new InteractiveClient({
      transport: this.#transport, endpoint: { host: '127.0.0.1', port }, secret,
      onState: (state) => {
        if (this.#generation !== generation || this.#client !== client) return;
        if (state === 'CONNECTED') {
          this.#api.showToast('AI Instrument Assistant: Connected.');
          try { this.#onConnected(this.#debugRuntimeNo); }
          catch { /* diagnostic registration cannot change connection behavior */ }
        }
        if (state === 'RECONNECTING') this.#api.showToast('AI Instrument Assistant: Reconnecting.');
        if (state === 'FAILED') this.#api.showToast('AI Instrument Assistant: connection failed.');
      },
      onSnapshot: (snapshot) => {
        if (this.#generation !== generation || this.#client !== client) return;
        pendingDesignRefresh.synchronized(
          client.state,
          activeWorkflowKey(snapshot.workflows),
          dispatchObservation,
        );
      },
      onError: (code) => {
        if (this.#generation === generation && this.#client === client) this.#showError(code);
      },
      diagnostic: this.#diagnostic,
      debugRuntimeNo: this.#debugRuntimeNo,
    });
    this.#client = client;
    this.#surface = new InteractionSurface(this.#ui, client);
    this.#observer = new SelectionObserver({
      register: (callback) => this.#api.registerSelectionListener(LISTENER_ID, callback),
      remove: () => this.#api.removeSelectionListener(LISTENER_ID),
      onDebouncedChange: () => {
        if (this.#generation !== generation || this.#client !== client) return;
        pendingDesignRefresh.selectionChanged(
          client.state,
          activeWorkflowKey(client.snapshot?.workflows ?? []),
          dispatchObservation,
        );
      },
    });
    this.#observer.start();
    this.#log('configured', { generation, clientPresent: true });
    client.start();
  }

  disconnect(): void { this.#client?.stop(); }
  reconnect(): void { this.#client?.stop(); this.#client?.start(); }
  dispose(): void {
    this.#log('dispose_entered', { generation: this.#generation, clientPresent: this.#client !== null });
    this.#generation += 1;
    this.#observer?.dispose(); this.#observer = null;
    this.#pendingDesignRefresh?.dispose(); this.#pendingDesignRefresh = null;
    this.#client?.dispose(); this.#client = null; this.#surface = null;
    this.#log('disposed', { generation: this.#generation, clientPresent: false });
  }

  async showStatus(): Promise<void> {
    this.#diagnostic('STATUS', 'runtime_entered', {
      runtimeNo: this.#debugRuntimeNo,
      clientPresent: this.#client !== null,
      state: this.state,
    });
    try {
      await this.#refreshIfConnected();
      this.#diagnostic('STATUS', 'projection_succeeded', { runtimeNo: this.#debugRuntimeNo });
    }
    catch (error) {
      this.#diagnostic('STATUS', 'projection_failed', {
        runtimeNo: this.#debugRuntimeNo,
        category: boundedDiagnosticError(error),
      });
      throw error;
    }
    this.#statusActionSnapshotResolvedCount += 1;
    this.#statusDialogRenderAttemptCount += 1;
    this.#diagnostic('STATUS', 'dialog_invocation_attempted', { runtimeNo: this.#debugRuntimeNo });
    try {
      this.#surfaceOrUnavailable().showStatus();
      this.#statusDialogRenderSuccessCount += 1;
      this.#diagnostic('STATUS', 'dialog_invocation_succeeded', { runtimeNo: this.#debugRuntimeNo });
    }
    catch {
      this.#diagnostic('STATUS', 'dialog_invocation_failed', {
        runtimeNo: this.#debugRuntimeNo,
        category: 'STATUS_PRESENTATION_FAILED',
      });
      throw new Error('STATUS_PRESENTATION_FAILED');
    }
  }
  async refreshDesignContext(): Promise<void> {
    await this.#refreshIfConnected();
    const client = this.#client;
    const pending = this.#pendingDesignRefresh;
    if (client === null || pending === null) throw new Error('host_unavailable');
    pending.selectionChanged(
      client.state,
      activeWorkflowKey(client.snapshot?.workflows ?? []),
      () => {
        try { this.#surfaceOrUnavailable().refreshDesignContext(); return true; }
        catch { return false; }
      },
    );
  }
  async resolvePendingAction(): Promise<void> {
    await this.#refreshIfConnected(); await this.#surfaceOrUnavailable().resolvePendingAction();
  }
  async showCurrentTarget(): Promise<void> {
    await this.#refreshIfConnected(); this.#surfaceOrUnavailable().showCurrentTarget();
  }
  async showEvidenceSummary(): Promise<void> {
    await this.#refreshIfConnected(); this.#surfaceOrUnavailable().showEvidenceSummary();
  }
  async highlightTarget(): Promise<void> {
    await this.#refreshIfConnected(); this.#surfaceOrUnavailable().highlightTarget();
  }
  async cancelWorkflow(): Promise<void> {
    await this.#refreshIfConnected(); this.#surfaceOrUnavailable().cancelWorkflow();
  }

  showPermissionGuidance(): void {
    void this.#ui.confirm(
      'Enable JLCEDA External Interaction permission for this extension. Then choose Retry. The extension connects only to the local AI Instrument Assistant Host on 127.0.0.1.',
      'AI Instrument Assistant — Permission required', 'Retry', 'Cancel',
    ).then((retry) => { if (retry) this.reconnect(); }).catch(() => undefined);
  }

  #surfaceOrUnavailable(): InteractionSurface {
    if (this.#surface === null) throw new Error('host_unavailable');
    return this.#surface;
  }
  async #refreshIfConnected(): Promise<void> {
    if (this.#client?.state !== 'CONNECTED') throw new Error('SNAPSHOT_TRANSPORT_UNAVAILABLE');
    await this.#client.refreshSnapshot();
  }
  #showError(code: string): void {
    if (code === 'external_interaction_permission_required') this.showPermissionGuidance();
    else this.#api.showToast(errorMessage(code));
  }
  #log(event: string, fields: Readonly<Record<string, string | number | boolean>> = {}): void {
    this.#diagnostic('RUNTIME', event, { runtimeNo: this.#debugRuntimeNo, ...fields });
  }
}

function emptyClientDiagnostics(): InteractiveClientDiagnostics {
  return {
    websocketMessageReceivedCount: 0,
    jsonParseSuccessCount: 0,
    schemaValidationSuccessCount: 0,
    workflowSnapshotFrameCount: 0,
    snapshotRejectedAttemptMismatchCount: 0,
    snapshotRejectedSessionMismatchCount: 0,
    snapshotWaiterRegisteredCount: 0,
    snapshotRequestSentCount: 0,
    snapshotWaiterPresentCount: 0,
    snapshotWaiterAbsentCount: 0,
    snapshotWaiterResolvedCount: 0,
    snapshotWaiterTimeoutCount: 0,
    snapshotObserverFailureCount: 0,
  };
}

function activeWorkflowKey(
  workflows: ReadonlyArray<Readonly<Record<string, unknown>>>,
): string | null {
  const workflow = [...workflows].reverse().find((value) => value.terminal !== true);
  if (workflow === undefined || typeof workflow.workflow_id !== 'string'
    || !Number.isInteger(workflow.revision)) return null;
  return `${workflow.workflow_id}:${workflow.revision}`;
}

function errorMessage(code: string): string {
  const messages: Readonly<Record<string, string>> = {
    host_unavailable: 'AI Instrument Assistant Host is unavailable.',
    version_incompatible: 'AI Instrument Assistant protocol version is incompatible.',
    authentication_failed: 'AI Instrument Assistant authentication failed. Configure the connection again.',
    ambiguous_selection: 'Choose the intended design object to continue.',
    design_observation_stale: 'The design observation changed. Refresh the current selection.',
    operation_authorization_required: 'Review and authorize the exact one-time operation plan.',
    physical_confirmation_required: 'Confirm the displayed physical probe setup before measurement.',
    physical_confirmation_stale: 'The physical setup changed. Confirm it again.',
    instrument_not_connected: 'The instrument is not connected.',
    instrument_disconnected: 'The instrument connection was lost.',
    workflow_cancelled: 'The workflow was cancelled.',
  };
  return messages[code] ?? 'AI Instrument Assistant could not complete this bounded action.';
}
