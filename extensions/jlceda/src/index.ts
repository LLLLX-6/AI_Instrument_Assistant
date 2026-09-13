import extensionConfig from '../extension.json' with { type: 'json' };

import { JlcEdaInteractionRuntime } from './interaction/product-runtime.ts';
import { DEFAULT_INTERACTIVE_PORT } from './interaction/interactive-client.ts';
import {
  boundedDiagnosticError,
  consoleAiaDiagnostics,
} from './interaction/debug-diagnostics.ts';
import {
  ActivationRuntimeCommandService,
  dispatchRuntimeCommand,
  invokeRuntimeCommand,
  type RuntimeCommandAction,
} from './interaction/runtime-command-bridge.ts';
import { ProtocolMessageValidator } from './protocol/protocol-message-validator.ts';
import { EdaProtocolDispatcher } from './runtime/eda-protocol-dispatcher.ts';
import { JlcEdaApiAdapter } from './runtime/jlc-eda-api-adapter.ts';
import { JlcEdaProtocolClient } from './transport/protocol-client.ts';
import { JlcEdaWebSocketTransport } from './transport/jlceda-websocket-transport.ts';

const api = new JlcEdaApiAdapter(eda);
const dispatcher = new EdaProtocolDispatcher(api);
let transport: JlcEdaWebSocketTransport | null = null;
let interaction: JlcEdaInteractionRuntime | null = null;
let providerClient: JlcEdaProtocolClient | null = null;
let activationGeneration = 0;
let diagnosticListenersInstalled = false;
const runtimeCommandService = new ActivationRuntimeCommandService(
  api,
  (ownerRuntimeNo) => interaction !== null
    && interaction.debugRuntimeNo === ownerRuntimeNo
    && interaction.clientPresent,
  (action) => executeRuntimeCommand(action),
);

export function activate(status?: 'onStartupFinished', arg?: string): void {
  void status; void arg;
  activationGeneration += 1;
  installUnhandledDiagnostics();
  consoleAiaDiagnostics('BOOT', '', {
    version: extensionConfig.version,
    activationGeneration,
    runtimePresent: interaction !== null,
  });
  if (interaction === null) {
    transport = new JlcEdaWebSocketTransport(api);
    interaction = new JlcEdaInteractionRuntime(
      api,
      transport,
      consoleAiaDiagnostics,
      (runtimeNo) => runtimeCommandService.register(runtimeNo),
    );
  }
  consoleAiaDiagnostics('BOOT', 'activation_ready', {
    activationGeneration,
    runtimePresent: true,
    runtimeNo: interaction.debugRuntimeNo,
  });
}

export function deactivate(): void {
  consoleAiaDiagnostics('BOOT', 'deactivation_entered', {
    activationGeneration,
    runtimePresent: interaction !== null,
    runtimeNo: interaction?.debugRuntimeNo ?? 0,
  });
  interaction?.dispose(); interaction = null;
  providerClient?.stop(); providerClient = null;
  transport = null;
  removeUnhandledDiagnostics();
  consoleAiaDiagnostics('BOOT', 'deactivation_completed', { activationGeneration });
}

export function configureConnection(): void {
  void boundedAction('Configure Connection', () => {
    activateForMenuIfNeeded();
    const port = api.readInteractivePort(DEFAULT_INTERACTIVE_PORT);
    api.requestBackendSecret((encodedSecret) => {
      if (encodedSecret === null) return;
      afterOfficialDialog(() => boundedAction(
        'Configure Connection',
        () => interactionOrUnavailable().configure(port, decodeSecret(encodedSecret)),
      ));
    });
  });
}

export function configureProviderConnection(): void {
  api.requestBackendSecret((encodedSecret) => {
    if (encodedSecret === null) return;
    afterOfficialDialog(() => configureProvider(encodedSecret));
  });
}

export function showStatus(): void {
  delegateRuntimeAction('STATUS', 'Status');
}
export function refreshDesignContext(): void { delegateRuntimeAction('REFRESH_DESIGN_CONTEXT', 'Refresh Design Context'); }
export function resolveCurrentSelection(): void { delegateRuntimeAction('RESOLVE_CURRENT_SELECTION', 'Resolve Current Selection'); }
export function showCurrentTarget(): void { delegateRuntimeAction('CURRENT_TARGET', 'Current Target'); }
export function showPendingAction(): void { delegateRuntimeAction('PENDING_ACTION', 'Pending Action'); }
export function showEvidenceSummary(): void { delegateRuntimeAction('EVIDENCE_SUMMARY', 'Evidence Summary'); }
export function highlightTarget(): void { delegateRuntimeAction('HIGHLIGHT_TARGET', 'Highlight Target'); }
export function cancelWorkflow(): void { delegateRuntimeAction('CANCEL_WORKFLOW', 'Cancel Workflow'); }
export function disconnect(): void {
  delegateRuntimeAction('DISCONNECT', 'Disconnect', () => {
    api.showToast('AI Instrument Assistant: Disconnected.');
  });
}
export function reconnect(): void { delegateRuntimeAction('RECONNECT', 'Reconnect'); }

export function about(): void {
  api.showInformation([
    `AI Instrument Assistant Extension v${extensionConfig.version}`,
    'JLCEDA is a read-only design companion. Harness is the primary teaching surface.',
    'Connection does not authorize hardware, instruments, or design changes.',
  ].join('\n'), 'About AI Instrument Assistant');
}

async function boundedAction(action: string, operation: () => void | Promise<void>): Promise<void> {
  try { await operation(); }
  catch (error) {
    consoleAiaDiagnostics('ERROR', 'bounded_action_failed', {
      action: action.replaceAll(' ', '_'),
      category: boundedDiagnosticError(error),
    });
    api.showToast(userMessage(action, error));
  }
}

function userMessage(action: string, error?: unknown): string {
  if (action === 'Status') return statusFailureMessage(error);
  const values: Readonly<Record<string, string>> = {
    'Refresh Design Context': 'Design context could not be refreshed. Check the Host connection.',
    'Resolve Current Selection': 'No current Host selection challenge is available.',
    'Pending Action': 'No current Host action is available.',
    'Current Target': 'No current Host-resolved target is available.',
    'Evidence Summary': 'No bounded evidence summary is available.',
    'Highlight Target': 'The guarded highlight request was not accepted.',
    'Cancel Workflow': 'No cancellable Host workflow is available.',
    'Configure Connection': 'Connection configuration was not accepted.',
    'Configure EDA Provider Connection': 'EDA provider connection configuration failed.',
  };
  return values[action] ?? 'AI Instrument Assistant could not complete this action.';
}

function statusFailureMessage(error: unknown): string {
  const code = error instanceof Error ? error.message : '';
  const values: Readonly<Record<string, string>> = {
    SNAPSHOT_TRANSPORT_TIMEOUT: 'Status snapshot timed out before a valid current-session reply was accepted.',
    SNAPSHOT_TRANSPORT_UNAVAILABLE: 'Status snapshot transport is unavailable. Configure the connection.',
    SNAPSHOT_FRAME_INVALID: 'Status snapshot reply failed bounded frame validation.',
    SNAPSHOT_SESSION_MISMATCH: 'Status snapshot reply did not match the active session.',
    SNAPSHOT_WAITER_ALREADY_PENDING: 'A Status snapshot request is already pending.',
    STATUS_PRESENTATION_FAILED: 'Status snapshot resolved, but the official Dialog could not be presented.',
    message_bus_unavailable: 'The connected AI Instrument Assistant runtime bridge is unavailable. Configure the connection.',
    message_bus_call_failed: 'The connected AI Instrument Assistant runtime could not be reached. Configure the connection.',
    message_bus_response_invalid: 'The connected AI Instrument Assistant runtime returned an invalid bounded response.',
    runtime_owner_stale: 'The connected AI Instrument Assistant runtime is stale. Reconfigure the connection.',
    runtime_owner_unavailable: 'No connected AI Instrument Assistant runtime owner is available. Configure the connection.',
    runtime_not_connected: 'The AI Instrument Assistant runtime is not connected. Reconnect or configure the connection.',
    runtime_action_failed: 'The connected AI Instrument Assistant runtime could not complete Status.',
  };
  return values[code] ?? 'AI Instrument Assistant Host is unavailable. Configure the connection.';
}

function delegateRuntimeAction(
  action: RuntimeCommandAction,
  label: string,
  completed: () => void = () => undefined,
): void {
  void boundedAction(label, async () => {
    await invokeRuntimeCommand(api, action);
    completed();
  });
}

async function executeRuntimeCommand(action: RuntimeCommandAction): Promise<void> {
  const runtime = interaction;
  try { await dispatchRuntimeCommand(runtime, action); }
  finally {
    if (action === 'STATUS' && runtime !== null) {
      consoleAiaDiagnostics('STATUS', 'bounded_counts', {
        runtimeNo: runtime.debugRuntimeNo,
        ...runtime.diagnostics,
      });
    }
  }
}

function decodeSecret(value: string): Uint8Array {
  if (!/^[A-Za-z0-9_-]{43}$/.test(value)) throw new Error('credential_invalid');
  const binary = atob(value.replaceAll('-', '+').replaceAll('_', '/') + '=');
  const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
  if (bytes.byteLength !== 32) throw new Error('credential_invalid');
  return bytes;
}

function afterOfficialDialog(operation: () => void | Promise<void>): void {
  // The tested JLCEDA desktop runtime does not reliably permit another
  // official Dialog (or WebSocket registration) while the current Dialog's
  // callback is still unwinding. Defer one task without changing authority or
  // carrying provider data across the boundary.
  globalThis.setTimeout(() => {
    void Promise.resolve().then(operation).catch((error) => {
      consoleAiaDiagnostics('ERROR', 'deferred_action_rejected', {
        category: boundedDiagnosticError(error),
      });
    });
  }, 0);
}

type DiagnosticEventTarget = {
  addEventListener?: (type: string, listener: (event: unknown) => void) => void;
  removeEventListener?: (type: string, listener: (event: unknown) => void) => void;
};

const unhandledErrorDiagnostic = (): void => {
  consoleAiaDiagnostics('ERROR', 'unhandled', { category: 'unhandled_error' });
};
const unhandledRejectionDiagnostic = (): void => {
  consoleAiaDiagnostics('ERROR', 'unhandled', { category: 'unhandled_rejection' });
};

function installUnhandledDiagnostics(): void {
  if (diagnosticListenersInstalled) return;
  const target = globalThis as unknown as DiagnosticEventTarget;
  try {
    target.addEventListener?.('error', unhandledErrorDiagnostic);
    target.addEventListener?.('unhandledrejection', unhandledRejectionDiagnostic);
  } catch { /* diagnostics must never change activation behavior */ }
  diagnosticListenersInstalled = true;
}

function removeUnhandledDiagnostics(): void {
  if (!diagnosticListenersInstalled) return;
  const target = globalThis as unknown as DiagnosticEventTarget;
  try {
    target.removeEventListener?.('error', unhandledErrorDiagnostic);
    target.removeEventListener?.('unhandledrejection', unhandledRejectionDiagnostic);
  } catch { /* diagnostics must never change deactivation behavior */ }
  diagnosticListenersInstalled = false;
}

function configureProvider(encodedSecret: string): void {
  let stage = 'runtime_initialization';
  try {
    activateForMenuIfNeeded();
    const currentTransport = transportOrUnavailable();
    stage = 'credential_validation';
    const secret = decodeSecret(encodedSecret);
    stage = 'schema_validator_initialization';
    const validator = new ProtocolMessageValidator();
    stage = 'provider_client_initialization';
    providerClient?.stop();
    providerClient = new JlcEdaProtocolClient({
      transport: currentTransport, validator,
      serviceUri: 'ws://127.0.0.1:49624', secret,
      requestDispatcher: dispatcher,
      onDiagnostics: (event) => {
        if (event.event === 'authenticated') {
          api.showToast('EDA provider connection authenticated.');
        }
        if (event.event === 'reconnect_exhausted') api.showToast('EDA provider connection unavailable. Configure it again.');
      },
    });
    stage = 'provider_client_start';
    providerClient.start();
  }
  catch {
    api.showToast(`EDA provider connection configuration failed (${stage}).`);
  }
}

function activateForMenuIfNeeded(): void {
  if (interaction === null || transport === null) activate();
}

function interactionOrUnavailable(): JlcEdaInteractionRuntime {
  if (interaction === null) throw new Error('interaction_runtime_unavailable');
  return interaction;
}

function transportOrUnavailable(): JlcEdaWebSocketTransport {
  if (transport === null) throw new Error('interaction_runtime_unavailable');
  return transport;
}
