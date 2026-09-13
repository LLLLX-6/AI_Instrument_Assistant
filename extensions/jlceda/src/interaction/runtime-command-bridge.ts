import {
  RUNTIME_COMMAND_ACTIONS,
  RuntimeCommandRpcError,
  type JlcEdaApiAdapter,
  type RuntimeCommandAction,
  type RuntimeCommandFailureCode,
  type RuntimeCommandResult,
} from '../runtime/jlc-eda-api-adapter.ts';

export { RUNTIME_COMMAND_ACTIONS };
export type { RuntimeCommandAction };

export interface RuntimeCommandOwner {
  readonly clientPresent: boolean;
  readonly state: string;
  showStatus(): Promise<void>;
  refreshDesignContext(): Promise<void>;
  resolvePendingAction(): Promise<void>;
  showCurrentTarget(): Promise<void>;
  showEvidenceSummary(): Promise<void>;
  highlightTarget(): Promise<void>;
  cancelWorkflow(): Promise<void>;
  disconnect(): void;
  reconnect(): void;
}

const KNOWN_ACTION_FAILURES = new Set<RuntimeCommandFailureCode>([
  'runtime_owner_unavailable',
  'runtime_not_connected',
  'SNAPSHOT_FRAME_INVALID',
  'SNAPSHOT_SESSION_MISMATCH',
  'SNAPSHOT_TRANSPORT_TIMEOUT',
  'SNAPSHOT_TRANSPORT_UNAVAILABLE',
  'SNAPSHOT_WAITER_ALREADY_PENDING',
  'STATUS_PRESENTATION_FAILED',
]);

export class ActivationRuntimeCommandService {
  readonly #api: Pick<JlcEdaApiAdapter, 'registerRuntimeCommandService'>;
  readonly #isCurrentOwner: (ownerRuntimeNo: number) => boolean;
  readonly #execute: (action: RuntimeCommandAction) => void | Promise<void>;
  #registeredOwnerRuntimeNo: number | null = null;

  constructor(
    api: Pick<JlcEdaApiAdapter, 'registerRuntimeCommandService'>,
    isCurrentOwner: (ownerRuntimeNo: number) => boolean,
    execute: (action: RuntimeCommandAction) => void | Promise<void>,
  ) {
    this.#api = api;
    this.#isCurrentOwner = isCurrentOwner;
    this.#execute = execute;
  }

  register(ownerRuntimeNo: number): void {
    if (this.#registeredOwnerRuntimeNo !== null) return;
    if (!Number.isSafeInteger(ownerRuntimeNo) || ownerRuntimeNo < 1) return;
    this.#api.registerRuntimeCommandService(async (action) => {
      if (!this.#isCurrentOwner(ownerRuntimeNo)) return rejected('runtime_owner_stale');
      try {
        await this.#execute(action);
        return Object.freeze({ status: 'COMPLETED', reasonCode: null });
      }
      catch (error) {
        return rejected(actionFailure(error));
      }
    });
    this.#registeredOwnerRuntimeNo = ownerRuntimeNo;
  }
}

export async function invokeRuntimeCommand(
  api: Pick<JlcEdaApiAdapter, 'callRuntimeCommand'>,
  action: RuntimeCommandAction,
): Promise<void> {
  const result = await api.callRuntimeCommand(action);
  if (result.status === 'REJECTED') throw new RuntimeCommandRpcError(result.reasonCode);
}

export async function dispatchRuntimeCommand(
  runtime: RuntimeCommandOwner | null,
  action: RuntimeCommandAction,
): Promise<void> {
  if (runtime === null || !runtime.clientPresent) throw new Error('runtime_owner_unavailable');
  if (action === 'RECONNECT') { runtime.reconnect(); return; }
  if (action === 'DISCONNECT') { runtime.disconnect(); return; }
  if (runtime.state !== 'CONNECTED') throw new Error('runtime_not_connected');
  switch (action) {
    case 'STATUS': await runtime.showStatus(); return;
    case 'REFRESH_DESIGN_CONTEXT': await runtime.refreshDesignContext(); return;
    case 'RESOLVE_CURRENT_SELECTION': await runtime.resolvePendingAction(); return;
    case 'CURRENT_TARGET': await runtime.showCurrentTarget(); return;
    case 'PENDING_ACTION': await runtime.resolvePendingAction(); return;
    case 'EVIDENCE_SUMMARY': await runtime.showEvidenceSummary(); return;
    case 'HIGHLIGHT_TARGET': await runtime.highlightTarget(); return;
    case 'CANCEL_WORKFLOW': await runtime.cancelWorkflow(); return;
  }
}

function actionFailure(error: unknown): RuntimeCommandFailureCode {
  if (error instanceof Error
    && KNOWN_ACTION_FAILURES.has(error.message as RuntimeCommandFailureCode)) {
    return error.message as RuntimeCommandFailureCode;
  }
  return 'runtime_action_failed';
}

function rejected(reasonCode: RuntimeCommandFailureCode): RuntimeCommandResult {
  return Object.freeze({ status: 'REJECTED', reasonCode });
}
