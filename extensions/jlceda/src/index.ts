import extensionConfig from '../extension.json' with { type: 'json' };

import { JlcEdaApiAdapter } from './runtime/jlc-eda-api-adapter.ts';
import { ProtocolMessageValidator } from './protocol/protocol-message-validator.ts';
import { EdaProtocolDispatcher } from './runtime/eda-protocol-dispatcher.ts';
import { JlcEdaProtocolClient } from './transport/protocol-client.ts';
import { JlcEdaWebSocketTransport } from './transport/jlceda-websocket-transport.ts';

const api = new JlcEdaApiAdapter(eda);
// Ledger survives transport re-authentication, but not an extension reload.
const dispatcher = new EdaProtocolDispatcher(api);
let protocolClient: JlcEdaProtocolClient | null = null;

export function activate(status?: 'onStartupFinished', arg?: string): void {
  void status;
  void arg;
  console.info(
    '[AI Instrument Assistant] runtime diagnostics',
    JSON.stringify(api.readRuntimeDiagnostics()),
  );
}

export async function inspectCurrentDocument(): Promise<void> {
  await runMenuAction('Inspect Current Document', async () => {
    const result = await api.readCurrentDocument();
    console.info(
      '[AI Instrument Assistant] current document',
      JSON.stringify(result),
    );
    api.showInformation(
      JSON.stringify(result, null, 2),
      'AI Instrument Assistant — Current Document',
    );
  });
}

export async function inspectSelection(): Promise<void> {
  await runMenuAction('Inspect Selection', async () => {
    const result = await api.readCurrentSelection();
    console.info(
      '[AI Instrument Assistant] current selection',
      JSON.stringify(result),
    );
    api.showInformation(
      JSON.stringify(result, null, 2),
      `AI Instrument Assistant — Selection (${result.totalSelected})`,
    );
  });
}

export async function highlightSelection(): Promise<void> {
  await runMenuAction('Highlight Selection', async () => {
    api.showInformation(
      'Use scripts/highlight_jlceda_selection.py for guarded remote highlight. Local legacy highlight is disabled to avoid implicit wire-to-net expansion.',
      'AI Instrument Assistant — Guarded Highlight',
    );
  });
}

export function about(): void {
  const diagnostics = api.readRuntimeDiagnostics();
  api.showInformation(
    [
      `AI Instrument Assistant Extension v${extensionConfig.version}`,
      'Phase 5B.4b: authenticated reads and guarded highlight submission',
      `Editor: ${diagnostics.editorVersion ?? 'unknown'}`,
      `Environment: ${diagnostics.environment}`,
      `Edition: ${diagnostics.edition}`,
      `Backend: ${protocolClient?.state ?? 'not configured'}`,
      'Highlight acceptance is not visual verification. Agent, instruments and design mutation are disabled.',
    ].join('\n'),
    'About AI Instrument Assistant',
  );
}

export function configureBackendConnection(): void {
  runSynchronousMenuAction('Configure Backend Connection', () => {
    api.requestBackendSecret((encodedSecret) => {
      try {
        if (encodedSecret === null || encodedSecret.length === 0) return;
        const secret = decodeSecret(encodedSecret);
        protocolClient?.stop();
        protocolClient = new JlcEdaProtocolClient({
          transport: new JlcEdaWebSocketTransport(api),
          validator: new ProtocolMessageValidator(),
          serviceUri: 'ws://127.0.0.1:49624',
          secret,
          onDiagnostics: (event) => {
            const serialized = JSON.stringify(event);
            if (event.event === 'transport_warning') {
              console.warn('[AI Instrument Assistant] backend transport', serialized);
            }
            else {
              console.info('[AI Instrument Assistant] backend transport', serialized);
            }
            if (event.event === 'authenticated') {
              api.showToast('AI Instrument Assistant: backend authenticated.');
            }
            if (event.event === 'disconnected') {
              api.showToast('AI Instrument Assistant: backend disconnected.');
            }
            if (event.event === 'reconnect_exhausted') {
              api.showToast(
                'AI Instrument Assistant: reconnect exhausted; configure backend connection again.',
              );
            }
          },
          requestDispatcher: dispatcher,
        });
        protocolClient.start();
      }
      catch (error) {
        const detail = error instanceof Error ? error.message : 'unknown error';
        api.showToast(`Backend configuration failed: ${detail.slice(0, 256)}`);
      }
    });
  });
}

async function runMenuAction(
  action: string,
  operation: () => Promise<void>,
): Promise<void> {
  try {
    await operation();
  }
  catch (error) {
    const detail = error instanceof Error ? error.message : 'unknown error';
    const message = `${action} failed: ${detail.slice(0, 512)}`;
    console.error(`[AI Instrument Assistant] ${message}`);
    try {
      api.showToast(message);
    }
    catch {
      console.error('[AI Instrument Assistant] toast capability unavailable');
    }
  }
}

function runSynchronousMenuAction(action: string, operation: () => void): void {
  try {
    operation();
  }
  catch (error) {
    const detail = error instanceof Error ? error.message : 'unknown error';
    api.showToast(`${action} failed: ${detail.slice(0, 256)}`);
  }
}

function decodeSecret(value: string): Uint8Array {
  if (!/^[A-Za-z0-9_-]{43}$/.test(value)) {
    throw new Error('Backend secret must be a 43-character base64url value');
  }
  const base64 = value.replaceAll('-', '+').replaceAll('_', '/') + '=';
  const binary = atob(base64);
  const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
  if (bytes.byteLength !== 32) throw new Error('Backend secret must decode to 32 bytes');
  return bytes;
}
