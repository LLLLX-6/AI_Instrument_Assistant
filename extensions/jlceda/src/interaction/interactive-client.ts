import { computeInteractiveProof, randomInteractiveNonce } from './interactive-hmac.ts';
import { InteractiveProtocolValidator } from './interactive-protocol-validator.ts';
import {
  boundedDiagnosticError,
  noAiaDiagnostics,
  type AiaDiagnosticSink,
} from './debug-diagnostics.ts';

const AUTH_PROTOCOL = 'aia-interactive-auth/v1';
const PROTOCOL = 'aia-interactive/v1';
const RETRY_DELAYS = [500, 1_000, 2_000, 5_000] as const;
const MAX_FRAME = 65_536;
export const DEFAULT_INTERACTIVE_PORT = 49_626;

export type InteractiveConnectionState =
  | 'DISCONNECTED' | 'CONNECTING' | 'SYNCHRONIZING' | 'CONNECTED' | 'RECONNECTING'
  | 'INCOMPATIBLE' | 'AUTH_REQUIRED' | 'FAILED';

export interface InteractiveEndpoint { readonly host: '127.0.0.1'; readonly port: number }
export interface InteractiveTransport {
  register(id: string, uri: string, onMessage: (data: string) => void | Promise<void>, onConnected: () => void | Promise<void>, onBoundaryFailure?: (detail: string) => void): void;
  send(id: string, data: string): void;
  close(id: string, code?: number, reason?: string): void;
}
export interface InteractiveClientClock {
  now(): Date;
  setTimeout(callback: () => void, delayMs: number): unknown;
  clearTimeout(handle: unknown): void;
}
export interface InteractiveSession {
  readonly applicationGeneration: string;
  readonly sessionId: string;
  readonly connectionGeneration: number;
}
export interface InteractiveSnapshot {
  readonly application_generation: string;
  readonly event_cursor: number;
  readonly status: Readonly<Record<string, unknown>>;
  readonly workflows: ReadonlyArray<Readonly<Record<string, unknown>>>;
  readonly pending_challenges: ReadonlyArray<Readonly<Record<string, unknown>>>;
}

export interface InteractiveClientDiagnostics {
  readonly websocketMessageReceivedCount: number;
  readonly jsonParseSuccessCount: number;
  readonly schemaValidationSuccessCount: number;
  readonly workflowSnapshotFrameCount: number;
  readonly snapshotRejectedAttemptMismatchCount: number;
  readonly snapshotRejectedSessionMismatchCount: number;
  readonly snapshotWaiterRegisteredCount: number;
  readonly snapshotRequestSentCount: number;
  readonly snapshotWaiterPresentCount: number;
  readonly snapshotWaiterAbsentCount: number;
  readonly snapshotWaiterResolvedCount: number;
  readonly snapshotWaiterTimeoutCount: number;
  readonly snapshotObserverFailureCount: number;
}

type SnapshotWaiter = {
  resolve(snapshot: InteractiveSnapshot): void;
  reject(error: Error): void;
  timer: unknown;
  attempt: number;
  sessionId: string;
};

export class InteractiveClient {
  readonly #transport: InteractiveTransport;
  readonly #endpoint: InteractiveEndpoint;
  readonly #secret: Uint8Array;
  readonly #clientInstanceId: string;
  readonly #validator: InteractiveProtocolValidator;
  readonly #clock: InteractiveClientClock;
  readonly #onState: (state: InteractiveConnectionState) => void;
  readonly #onSnapshot: (snapshot: InteractiveSnapshot) => void;
  readonly #onError: (code: string) => void;
  readonly #diagnostic: AiaDiagnosticSink;
  readonly #debugRuntimeNo: number;
  #state: InteractiveConnectionState = 'DISCONNECTED';
  #session: InteractiveSession | null = null;
  #snapshot: InteractiveSnapshot | null = null;
  #socketId: string | null = null;
  #socketOpened = false;
  #attempt = 0;
  #retryIndex = 0;
  #reconnectTimer: unknown = null;
  #watchdog: unknown = null;
  #synchronizationWatchdog: unknown = null;
  #stopped = true;
  #disposed = false;
  #snapshotWaiter: SnapshotWaiter | null = null;
  readonly #diagnostics = mutableDiagnostics();

  constructor(options: {
    transport: InteractiveTransport; endpoint: InteractiveEndpoint; secret: Uint8Array;
    clientInstanceId?: string; validator?: InteractiveProtocolValidator; clock?: InteractiveClientClock;
    onState?: (state: InteractiveConnectionState) => void;
    onSnapshot?: (snapshot: InteractiveSnapshot) => void;
    onError?: (code: string) => void;
    diagnostic?: AiaDiagnosticSink;
    debugRuntimeNo?: number;
  }) {
    if (options.endpoint.host !== '127.0.0.1' || !Number.isInteger(options.endpoint.port)
      || options.endpoint.port < 1 || options.endpoint.port > 65_535
      || options.endpoint.port === 49_624 || options.endpoint.port === 49_625) {
      throw new Error('interactive_endpoint_invalid');
    }
    if (options.secret.byteLength !== 32) throw new Error('interactive_credential_invalid');
    this.#transport = options.transport; this.#endpoint = options.endpoint;
    this.#secret = options.secret.slice();
    this.#clientInstanceId = options.clientInstanceId ?? crypto.randomUUID();
    this.#validator = options.validator ?? new InteractiveProtocolValidator();
    this.#clock = options.clock ?? {
      now: () => new Date(),
      setTimeout: (callback, delayMs) => globalThis.setTimeout(callback, delayMs),
      clearTimeout: (handle) => globalThis.clearTimeout(handle as ReturnType<typeof setTimeout>),
    };
    this.#onState = options.onState ?? (() => undefined);
    this.#onSnapshot = options.onSnapshot ?? (() => undefined);
    this.#onError = options.onError ?? (() => undefined);
    this.#diagnostic = options.diagnostic ?? noAiaDiagnostics;
    this.#debugRuntimeNo = options.debugRuntimeNo ?? 0;
    this.#log('created');
  }

  get state(): InteractiveConnectionState { return this.#state; }
  get session(): InteractiveSession | null { return this.#session; }
  get snapshot(): InteractiveSnapshot | null { return this.#snapshot; }
  get diagnostics(): InteractiveClientDiagnostics { return Object.freeze({ ...this.#diagnostics }); }

  start(): void {
    if (this.#disposed) return;
    if (!this.#stopped && this.#socketId !== null) return;
    this.#log('start');
    this.#stopped = false; this.#retryIndex = 0; this.#connect(false);
  }

  stop(): void {
    if (this.#stopped && this.#state === 'DISCONNECTED') return;
    this.#log('stop');
    this.#stopped = true; this.#clearTimers();
    const socket = this.#socketId; const opened = this.#socketOpened;
    this.#socketId = null; this.#socketOpened = false;
    this.#session = null; this.#snapshot = null; this.#rejectSnapshotWaiter('SNAPSHOT_TRANSPORT_UNAVAILABLE');
    if (socket !== null && opened) {
      try { this.#transport.close(socket, 1000, 'interactive client stopped'); } catch { /* best effort */ }
    }
    this.#setState('DISCONNECTED');
  }

  dispose(): void {
    if (this.#disposed) return;
    this.#log('dispose');
    this.stop();
    this.#secret.fill(0);
    this.#disposed = true;
  }

  handleTransportLoss(_code: string): void {
    if (this.#stopped || this.#state === 'RECONNECTING') return;
    this.#log('transport_loss', { category: boundedTransportCategory(_code) });
    this.#clearTimers(); const socket = this.#socketId; const opened = this.#socketOpened;
    this.#socketId = null; this.#socketOpened = false;
    this.#session = null; this.#snapshot = null;
    this.#rejectSnapshotWaiter(snapshotFailureCode(_code));
    if (socket !== null && opened) {
      try { this.#transport.close(socket, 4005, 'local interactive transport failure'); } catch { /* bounded */ }
    }
    this.#setState('RECONNECTING'); this.#scheduleReconnect();
  }

  requestSnapshot(): void {
    this.#log('snapshot_request_send_attempt');
    if (this.#session === null) {
      this.#log('snapshot_request_send_failed', { category: 'host_unavailable' });
      throw new Error('host_unavailable');
    }
    if (this.#sendControl({ protocol: AUTH_PROTOCOL, phase: 'snapshot_request' })) {
      this.#diagnostics.snapshotRequestSentCount += 1;
      this.#log('snapshot_request_send_succeeded');
    } else {
      this.#log('snapshot_request_send_failed', { category: 'bounded_transport_failure' });
    }
  }

  refreshSnapshot(): Promise<InteractiveSnapshot> {
    this.#log('request_snapshot_entered');
    this.#requireSession();
    if (this.#snapshotWaiter !== null) {
      this.#log('snapshot_waiter_rejected', { category: 'SNAPSHOT_WAITER_ALREADY_PENDING' });
      return Promise.reject(new Error('SNAPSHOT_WAITER_ALREADY_PENDING'));
    }
    return new Promise((resolve, reject) => {
      const waiter: SnapshotWaiter = {
        resolve, reject,
        attempt: this.#attempt,
        sessionId: this.#session!.sessionId,
        timer: this.#clock.setTimeout(() => {
          if (this.#snapshotWaiter !== waiter) return;
          this.#snapshotWaiter = null;
          this.#diagnostics.snapshotWaiterTimeoutCount += 1;
          this.#log('snapshot_waiter_timeout', { category: 'SNAPSHOT_TRANSPORT_TIMEOUT' });
          reject(new Error('SNAPSHOT_TRANSPORT_TIMEOUT'));
        }, 3_000),
      };
      this.#snapshotWaiter = waiter;
      this.#diagnostics.snapshotWaiterRegisteredCount += 1;
      this.#log('snapshot_waiter_registered');
      this.requestSnapshot();
    });
  }

  sendCommand(command: string, payload: unknown): void {
    const session = this.#requireSession();
    this.#sendValidated({
      protocol: PROTOCOL, message_id: crypto.randomUUID(), sent_at: this.#clock.now().toISOString(),
      message_type: 'command', application_generation: session.applicationGeneration,
      session_id: session.sessionId, correlation_id: crypto.randomUUID(), command, payload,
    });
  }

  answerChallenge(challenge: Readonly<Record<string, unknown>>, answer: unknown): void {
    const session = this.#requireSession();
    const current = this.#snapshot?.pending_challenges.find((item) => item.challenge_id === challenge.challenge_id);
    if (current !== challenge && JSON.stringify(current) !== JSON.stringify(challenge)) throw new Error('challenge_stale');
    if (challenge.application_generation !== session.applicationGeneration) throw new Error('challenge_stale');
    const expires = Date.parse(requiredString(challenge.expires_at));
    if (!Number.isFinite(expires) || expires <= this.#clock.now().getTime()) throw new Error('challenge_expired');
    this.#sendValidated({
      protocol: PROTOCOL, message_id: crypto.randomUUID(), sent_at: this.#clock.now().toISOString(),
      message_type: 'challenge_answer', application_generation: session.applicationGeneration,
      session_id: session.sessionId, workflow_id: challenge.workflow_id,
      expected_workflow_revision: challenge.workflow_revision, challenge_id: challenge.challenge_id,
      challenge_kind: challenge.challenge_kind, nonce: challenge.nonce, answer,
    });
  }

  #connect(reconnect: boolean): void {
    if (this.#stopped) return;
    this.#attempt += 1; const socket = `aia_interactive_${this.#attempt}`;
    this.#socketId = socket; this.#socketOpened = false;
    this.#setState(reconnect ? 'RECONNECTING' : 'CONNECTING');
    try {
      this.#transport.register(
        socket, `ws://${this.#endpoint.host}:${this.#endpoint.port}`,
        (data) => this.#message(socket, data), () => this.#connected(socket),
        () => this.handleTransportLoss('runtime_boundary_failure'),
      );
      this.#watchdog = this.#clock.setTimeout(() => this.handleTransportLoss('connect_timeout'), 5_000);
    } catch { this.#onError('external_interaction_permission_required'); this.handleTransportLoss('register_failed'); }
  }

  #connected(socket: string): void {
    if (this.#socketId !== socket || this.#stopped) return;
    this.#socketOpened = true;
    this.#setState('AUTH_REQUIRED');
  }

  async #message(socket: string, data: string): Promise<void> {
    this.#diagnostics.websocketMessageReceivedCount += 1;
    if (this.#socketId !== socket) {
      this.#diagnostics.snapshotRejectedAttemptMismatchCount += 1;
      return;
    }
    if (this.#stopped || data.length > MAX_FRAME) return;
    this.#clearWatchdog();
    let value: Readonly<Record<string, unknown>>;
    try {
      value = parseObject(data);
      this.#diagnostics.jsonParseSuccessCount += 1;
    } catch { this.handleTransportLoss('invalid_frame'); return; }
    if (value.protocol === AUTH_PROTOCOL) {
      await this.#authMessage(value); return;
    }
    try {
      value = this.#validator.validate(value);
      this.#diagnostics.schemaValidationSuccessCount += 1;
    } catch { this.handleTransportLoss('protocol_violation'); return; }
    if (value.message_type === 'hello_ack') { this.#helloAccepted(value); return; }
    if (value.message_type !== 'event') {
      this.handleTransportLoss('session_invalid'); return;
    }
    if (value.event_type === 'workflow_snapshot') {
      this.#diagnostics.workflowSnapshotFrameCount += 1;
      this.#log('workflow_snapshot_observed');
    }
    if (this.#session === null
      || value.application_generation !== this.#session.applicationGeneration
      || value.session_id !== this.#session.sessionId) {
      this.#diagnostics.snapshotRejectedSessionMismatchCount += 1;
      this.handleTransportLoss('session_invalid'); return;
    }
    if (value.event_type === 'workflow_snapshot') {
      const initialSnapshot = this.#snapshot === null;
      const payload = value.payload as Readonly<Record<string, unknown>>;
      this.#snapshot = Object.freeze(payload.snapshot as InteractiveSnapshot);
      if (initialSnapshot) this.#log('initial_snapshot_accepted');
      this.#clearSynchronizationWatchdog();
      this.#retryIndex = 0; this.#setState('CONNECTED');
      const currentAttempt = this.#attempt;
      const currentSession = this.#session.sessionId;
      const waiter = this.#snapshotWaiter;
      if (waiter !== null
        && waiter.attempt === currentAttempt && waiter.sessionId === currentSession) {
        this.#diagnostics.snapshotWaiterPresentCount += 1;
        this.#snapshotWaiter = null;
        this.#clock.clearTimeout(waiter.timer);
        waiter.resolve(this.#snapshot);
        this.#diagnostics.snapshotWaiterResolvedCount += 1;
        this.#log('snapshot_waiter_resolved');
      } else {
        this.#diagnostics.snapshotWaiterAbsentCount += 1;
      }
      try { this.#onSnapshot(this.#snapshot); }
      catch { this.#diagnostics.snapshotObserverFailureCount += 1; }
    } else {
      this.requestSnapshot();
    }
  }

  async #authMessage(value: Readonly<Record<string, unknown>>): Promise<void> {
    if (value.phase === 'challenge') {
      const fields = {
        clientInstanceId: this.#clientInstanceId,
        challengeId: requiredString(value.challenge_id), clientNonce: randomInteractiveNonce(),
        serverNonce: requiredString(value.server_nonce), expiresAt: requiredString(value.expires_at),
      };
      const proof = await computeInteractiveProof(this.#secret, fields);
      this.#sendControl({ protocol: AUTH_PROTOCOL, phase: 'proof', client_instance_id: fields.clientInstanceId,
        challenge_id: fields.challengeId, client_nonce: fields.clientNonce, proof });
      return;
    }
    if (value.phase === 'accepted') { this.#sendHello(); return; }
    if (value.phase === 'heartbeat') {
      this.#sendControl({ protocol: AUTH_PROTOCOL, phase: 'pong' });
      this.#watchdog = this.#clock.setTimeout(() => this.handleTransportLoss('heartbeat_timeout'), 12_000);
      return;
    }
    if (value.phase === 'rejected') {
      this.#stopped = true; this.#session = null; this.#onError('authentication_failed'); this.#setState('FAILED');
    }
  }

  #sendHello(): void {
    this.#sendValidated({
      protocol: PROTOCOL, message_id: crypto.randomUUID(), sent_at: this.#clock.now().toISOString(),
      message_type: 'hello', frontend_kind: 'JLCEDA', client_instance_id: this.#clientInstanceId,
      supported_versions: [PROTOCOL], resume_cursor: this.#snapshot?.event_cursor ?? null,
    });
  }

  #helloAccepted(value: Readonly<Record<string, unknown>>): void {
    if (value.accepted !== true || value.selected_version !== PROTOCOL) {
      this.#stopped = true; this.#onError('version_incompatible'); this.#setState('INCOMPATIBLE'); return;
    }
    this.#session = Object.freeze({
      applicationGeneration: requiredString(value.application_generation),
      sessionId: requiredString(value.session_id),
      connectionGeneration: requiredNumber(value.connection_generation),
    });
    this.#setState('SYNCHRONIZING');
    this.#clearSynchronizationWatchdog();
    this.#synchronizationWatchdog = this.#clock.setTimeout(
      () => this.handleTransportLoss('snapshot_timeout'), 3_000,
    );
  }

  #sendValidated(value: Record<string, unknown>): void {
    this.#validator.validate(value); this.#sendControl(value);
  }
  #sendControl(value: Record<string, unknown>): boolean {
    if (this.#socketId === null) throw new Error('host_unavailable');
    const encoded = JSON.stringify(value); if (encoded.length > MAX_FRAME) throw new Error('message_too_large');
    try { this.#transport.send(this.#socketId, encoded); return true; }
    catch { this.handleTransportLoss('send_failed'); return false; }
  }
  #requireSession(): InteractiveSession {
    if (this.#state !== 'CONNECTED' || this.#session === null) throw new Error('host_unavailable');
    return this.#session;
  }
  #scheduleReconnect(): void {
    if (this.#stopped || this.#reconnectTimer !== null) return;
    const delay = RETRY_DELAYS[this.#retryIndex];
    if (delay === undefined) { this.#stopped = true; this.#onError('host_unavailable'); this.#setState('FAILED'); return; }
    this.#retryIndex += 1;
    this.#reconnectTimer = this.#clock.setTimeout(() => { this.#reconnectTimer = null; this.#connect(true); }, delay);
  }
  #clearWatchdog(): void { if (this.#watchdog !== null) this.#clock.clearTimeout(this.#watchdog); this.#watchdog = null; }
  #clearSynchronizationWatchdog(): void {
    if (this.#synchronizationWatchdog !== null) this.#clock.clearTimeout(this.#synchronizationWatchdog);
    this.#synchronizationWatchdog = null;
  }
  #clearTimers(): void {
    this.#clearWatchdog(); this.#clearSynchronizationWatchdog();
    if (this.#reconnectTimer !== null) this.#clock.clearTimeout(this.#reconnectTimer);
    this.#reconnectTimer = null;
  }
  #rejectSnapshotWaiter(code: string): void {
    const waiter = this.#snapshotWaiter;
    if (waiter === null) return;
    this.#snapshotWaiter = null;
    this.#clock.clearTimeout(waiter.timer);
    waiter.reject(new Error(code));
    this.#log('snapshot_waiter_rejected', { category: boundedDiagnosticError(new Error(code)) });
  }
  #setState(value: InteractiveConnectionState): void {
    if (this.#state === value) return;
    this.#state = value;
    this.#log('state_transition', { state: value });
    this.#onState(value);
  }
  #log(event: string, fields: Readonly<Record<string, string | number | boolean>> = {}): void {
    this.#diagnostic('CLIENT', event, { runtimeNo: this.#debugRuntimeNo, ...fields });
  }
}

function parseObject(data: string): Readonly<Record<string, unknown>> {
  const value: unknown = JSON.parse(data);
  if (value === null || typeof value !== 'object' || Array.isArray(value)) throw new Error('object_required');
  return value as Readonly<Record<string, unknown>>;
}
function requiredString(value: unknown): string { if (typeof value !== 'string' || value.length < 1 || value.length > 256) throw new Error('bounded_string_required'); return value; }
function requiredNumber(value: unknown): number { if (!Number.isInteger(value) || Number(value) < 1) throw new Error('positive_integer_required'); return Number(value); }

function mutableDiagnostics(): { -readonly [Key in keyof InteractiveClientDiagnostics]: number } {
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

function snapshotFailureCode(code: string): string {
  if (code === 'invalid_frame' || code === 'protocol_violation') return 'SNAPSHOT_FRAME_INVALID';
  if (code === 'session_invalid') return 'SNAPSHOT_SESSION_MISMATCH';
  return 'SNAPSHOT_TRANSPORT_UNAVAILABLE';
}

function boundedTransportCategory(code: string): string {
  const values = new Set([
    'connect_timeout', 'connection_lost', 'heartbeat_timeout', 'invalid_frame',
    'protocol_violation', 'register_failed', 'runtime_boundary_failure',
    'send_failed', 'session_invalid', 'snapshot_timeout',
  ]);
  return values.has(code) ? code : 'bounded_transport_failure';
}
