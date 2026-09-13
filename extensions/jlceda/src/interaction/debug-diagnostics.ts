export type AiaDiagnosticValue = string | number | boolean;
export type AiaDiagnosticFields = Readonly<Record<string, AiaDiagnosticValue>>;
export type AiaDiagnosticSink = (
  scope: string,
  event: string,
  fields?: AiaDiagnosticFields,
) => void;

const SAFE_TOKEN = /^[A-Za-z0-9_.-]{1,80}$/;
const SAFE_ERROR_CODES = new Set([
  'SNAPSHOT_FRAME_INVALID',
  'SNAPSHOT_SESSION_MISMATCH',
  'SNAPSHOT_TRANSPORT_TIMEOUT',
  'SNAPSHOT_TRANSPORT_UNAVAILABLE',
  'SNAPSHOT_WAITER_ALREADY_PENDING',
  'STATUS_PRESENTATION_FAILED',
  'host_unavailable',
  'interaction_runtime_unavailable',
]);

export const noAiaDiagnostics: AiaDiagnosticSink = () => undefined;

export const consoleAiaDiagnostics: AiaDiagnosticSink = (scope, event, fields = {}) => {
  const tokens = [`[AIA][${safeToken(scope)}]`];
  if (event.length > 0) tokens.push(`event=${safeToken(event)}`);
  for (const [name, value] of Object.entries(fields)) {
    tokens.push(`${safeToken(name)}=${safeValue(value)}`);
  }
  try { console.warn(tokens.join(' ')); }
  catch { /* diagnostics must never change product behavior */ }
};

export function boundedDiagnosticError(error: unknown): string {
  if (error instanceof Error && SAFE_ERROR_CODES.has(error.message)) return error.message;
  return error instanceof Error ? 'bounded_error' : 'bounded_non_error';
}

function safeToken(value: string): string {
  return SAFE_TOKEN.test(value) ? value : 'invalid_token';
}

function safeValue(value: AiaDiagnosticValue): string {
  if (typeof value === 'number') return Number.isSafeInteger(value) && value >= 0 ? String(value) : 'invalid_number';
  if (typeof value === 'boolean') return String(value);
  return safeToken(value);
}
