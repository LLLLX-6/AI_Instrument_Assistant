import extensionConfig from '../extension.json' with { type: 'json' };

import { JlcEdaApiAdapter } from './runtime/jlc-eda-api-adapter.ts';

const api = new JlcEdaApiAdapter(eda);

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
    const result = await api.highlightSelection();
    console.info(
      '[AI Instrument Assistant] highlight result',
      JSON.stringify(result),
    );
    api.showInformation(
      JSON.stringify(result, null, 2),
      'AI Instrument Assistant — Highlight Result',
    );
  });
}

export function about(): void {
  const diagnostics = api.readRuntimeDiagnostics();
  api.showInformation(
    [
      `AI Instrument Assistant Extension v${extensionConfig.version}`,
      'Phase 5A: read-only runtime validation',
      `Editor: ${diagnostics.editorVersion ?? 'unknown'}`,
      `Environment: ${diagnostics.environment}`,
      `Edition: ${diagnostics.edition}`,
      'No Backend, WebSocket, Agent, or design mutation.',
    ].join('\n'),
    'About AI Instrument Assistant',
  );
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
