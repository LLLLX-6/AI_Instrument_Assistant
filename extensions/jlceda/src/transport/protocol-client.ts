import type { ProtocolMessageValidator } from '../protocol/protocol-message-validator.ts';
import { computeProof, randomNonce } from './hmac.ts';
import type { WebSocketTransport } from './websocket-transport.ts';


export const APPLICATION_CLOSE_CODES = Object.freeze({
  normalClosure: 1000,
  authenticationFailure: 4001,
  heartbeatTimeout: 4002,
  protocolViolation: 4003,
  sessionInvalid: 4004,
  localTransportFailure: 4005,
} as const);

export type ProtocolClientState =
  | 'idle'
  | 'disconnected'
  | 'connecting'
  | 'socket_open'
  | 'authenticating'
  | 'authenticated'
  | 'disconnecting'
  | 'retry_wait'
  | 'reconnect_exhausted'
  | 'stopped';

export interface ProtocolClientDiagnostics {
  readonly event:
    | 'connecting'
    | 'socket_open'
    | 'init_sent'
    | 'challenge_received'
    | 'authenticated'
    | 'heartbeat_sent'
    | 'heartbeat_received'
    | 'disconnecting'
    | 'disconnected'
    | 'transport_warning'
    | 'reconnect_scheduled'
    | 'reconnect_exhausted';
  readonly detail?: string;
}

export interface ProtocolClientScheduler {
  setTimeout(callback: () => void, delayMs: number): unknown;
  clearTimeout(handle: unknown): void;
}

export interface ProtocolClientOptions {
  readonly transport: WebSocketTransport;
  readonly validator: ProtocolMessageValidator;
  readonly serviceUri: string;
  readonly secret: Uint8Array;
  readonly connectionId?: string;
  readonly reconnectDelaysMs?: readonly number[];
  readonly connectTimeoutMs?: number;
  readonly autoHeartbeat?: boolean;
  readonly scheduler?: ProtocolClientScheduler;
  readonly onDiagnostics?: (event: ProtocolClientDiagnostics) => void;
}

interface PhysicalAttempt {
  readonly generation: number;
  readonly id: string;
  socketOpen: boolean;
}

type TeardownKind =
  | 'local_initiated_close'
  | 'remote_loss'
  | 'connect_failure'
  | 'send_failure';

const defaultScheduler: ProtocolClientScheduler = {
  setTimeout: (callback, delayMs) => globalThis.setTimeout(callback, delayMs),
  clearTimeout: (handle) => globalThis.clearTimeout(
    handle as ReturnType<typeof globalThis.setTimeout>,
  ),
};

class SessionInvalidError extends Error {}

export class JlcEdaProtocolClient {
  readonly #transport: WebSocketTransport;
  readonly #validator: ProtocolMessageValidator;
  readonly #serviceUri: string;
  readonly #secret: Uint8Array;
  readonly #logicalConnectionId: string;
  readonly #clientInstanceId = crypto.randomUUID();
  readonly #physicalIdNamespace: string;
  readonly #reconnectDelaysMs: readonly number[];
  readonly #connectTimeoutMs: number;
  readonly #autoHeartbeat: boolean;
  readonly #scheduler: ProtocolClientScheduler;
  readonly #onDiagnostics: (event: ProtocolClientDiagnostics) => void;
  #state: ProtocolClientState = 'idle';
  #attempt: PhysicalAttempt | null = null;
  #currentGeneration = 0;
  #sessionId: string | null = null;
  #traceId: string | null = null;
  #clientNonce: string | null = null;
  #initMessageId: string | null = null;
  #proveMessageId: string | null = null;
  #pendingPing: { readonly messageId: string; readonly nonce: string } | null = null;
  #heartbeatIntervalMs = 0;
  #heartbeatTimeoutMs = 0;
  #reconnectAttempt = 0;
  #sendsEnabled = false;
  #connectTimeout: unknown;
  #heartbeatTimer: unknown;
  #heartbeatTimeoutTimer: unknown;
  #reconnectTimer: unknown;

  constructor(options: ProtocolClientOptions) {
    if (!/^ws:\/\/127\.0\.0\.1:\d{1,5}\/?$/.test(options.serviceUri)) {
      throw new Error('Protocol client serviceUri must be an explicit 127.0.0.1 WebSocket URL');
    }
    if (options.secret.byteLength < 32) {
      throw new Error('The production pre-shared secret must contain at least 32 bytes');
    }
    if ((options.reconnectDelaysMs ?? []).some((delay) => delay < 0)) {
      throw new Error('Reconnect delays cannot be negative');
    }
    if ((options.connectTimeoutMs ?? 3000) <= 0) {
      throw new Error('Physical connection timeout must be positive');
    }
    const logicalId = options.connectionId ?? 'aia-jlceda-backend-v1';
    if (!/^[A-Za-z0-9_-]{1,64}$/.test(logicalId)) {
      throw new Error('Logical connection id contains unsupported characters');
    }
    this.#transport = options.transport;
    this.#validator = options.validator;
    this.#serviceUri = options.serviceUri;
    this.#secret = new Uint8Array(options.secret);
    this.#logicalConnectionId = logicalId;
    this.#physicalIdNamespace = this.#clientInstanceId.replaceAll('-', '').slice(0, 12);
    this.#reconnectDelaysMs = options.reconnectDelaysMs ?? [500, 1000, 2000, 5000];
    this.#connectTimeoutMs = options.connectTimeoutMs ?? 3000;
    this.#autoHeartbeat = options.autoHeartbeat ?? true;
    this.#scheduler = options.scheduler ?? defaultScheduler;
    this.#onDiagnostics = options.onDiagnostics ?? (() => undefined);
  }

  get state(): ProtocolClientState { return this.#state; }
  get sessionId(): string | null { return this.#sessionId; }
  get serviceUri(): string { return this.#serviceUri; }

  start(): void {
    if (
      this.#state !== 'idle'
      && this.#state !== 'disconnected'
      && this.#state !== 'reconnect_exhausted'
    ) return;
    this.#clearReconnectTimer();
    this.#reconnectAttempt = 0;
    this.#beginPhysicalConnect();
  }

  stop(): void {
    if (this.#state === 'stopped') return;
    if (
      this.#state === 'idle'
      || this.#state === 'disconnected'
      || this.#state === 'retry_wait'
      || this.#state === 'reconnect_exhausted'
    ) {
      this.#invalidateAllCallbacks();
      this.#clearAllTimers();
      this.#clearSessionState();
      this.#attempt = null;
      this.#secret.fill(0);
      this.#state = 'stopped';
      return;
    }
    this.#teardown({
      generation: this.#currentGeneration,
      kind: 'local_initiated_close',
      closeCode: APPLICATION_CLOSE_CODES.normalClosure,
      closeReason: 'extension stopped',
      detail: 'extension stopped',
      reconnect: false,
      finalState: 'stopped',
      eraseSecret: true,
    });
  }

  sendHeartbeat(generation = this.#currentGeneration): boolean {
    if (!this.#canSendAuthenticated(generation)) return false;
    const ping = {
      ...baseEnvelope(this.#traceId ?? crypto.randomUUID()),
      session_id: this.#sessionId,
      kind: 'ping',
      nonce: randomNonce(),
    };
    this.#validator.validate(ping);
    this.#pendingPing = { messageId: ping.message_id, nonce: ping.nonce };
    if (!this.#send(ping, generation)) return false;
    this.#emit('heartbeat_sent');
    if (this.#autoHeartbeat && this.#canSendAuthenticated(generation)) {
      this.#clearTimer('heartbeatTimeout');
      this.#heartbeatTimeoutTimer = this.#scheduler.setTimeout(
        () => {
          if (!this.#isCurrentGeneration(generation) || this.#pendingPing === null) return;
          this.#teardown({
            generation,
            kind: 'remote_loss',
            detail: 'heartbeat timeout',
            reconnect: true,
            finalState: 'disconnected',
            eraseSecret: false,
          });
        },
        this.#heartbeatTimeoutMs,
      );
    }
    return true;
  }

  #beginPhysicalConnect(): void {
    if (this.#state === 'stopped' || this.#state === 'disconnecting') return;
    this.#clearConnectionTimers();
    this.#sendsEnabled = false;
    const generation = ++this.#currentGeneration;
    const physicalId = [
      this.#logicalConnectionId,
      this.#physicalIdNamespace,
      String(generation),
    ].join('-');
    this.#attempt = { generation, id: physicalId, socketOpen: false };
    this.#state = 'connecting';
    this.#emit('connecting');
    try {
      this.#transport.register(
        physicalId,
        this.#serviceUri,
        (data) => this.#receive(data, generation),
        () => { this.#socketOpened(generation); },
        (detail) => { this.#hostBoundaryFailed(generation, detail); },
      );
      if (this.#state === 'connecting' && this.#isCurrentGeneration(generation)) {
        this.#connectTimeout = this.#scheduler.setTimeout(
          () => {
            if (this.#state !== 'connecting' || !this.#isCurrentGeneration(generation)) return;
            this.#teardown({
              generation,
              kind: 'connect_failure',
              detail: 'physical connection timeout before connected callback',
              reconnect: true,
              finalState: 'disconnected',
              eraseSecret: false,
            });
          },
          this.#connectTimeoutMs,
        );
      }
    }
    catch (error) {
      this.#teardown({
        generation,
        kind: 'connect_failure',
        detail: errorDetail(error),
        reconnect: true,
        finalState: 'disconnected',
        eraseSecret: false,
      });
    }
  }

  #socketOpened(generation: number): void {
    if (this.#state !== 'connecting' || !this.#isCurrentGeneration(generation)) return;
    const attempt = this.#attempt;
    if (attempt === null) return;
    this.#clearTimer('connectTimeout');
    attempt.socketOpen = true;
    this.#state = 'socket_open';
    this.#sendsEnabled = true;
    this.#emit('socket_open');
    this.#startAuthentication(generation);
  }

  #startAuthentication(generation: number): void {
    if (
      this.#state !== 'socket_open'
      || !this.#isCurrentGeneration(generation)
      || !this.#sendsEnabled
    ) return;
    this.#traceId = crypto.randomUUID();
    this.#clientNonce = randomNonce();
    const init = {
      ...baseEnvelope(this.#traceId),
      kind: 'hello',
      phase: 'init',
      provider: 'jlceda-pro',
      client_instance_id: this.#clientInstanceId,
      client_nonce: this.#clientNonce,
    };
    this.#validator.validate(init);
    this.#initMessageId = init.message_id;
    this.#state = 'authenticating';
    if (!this.#send(init, generation)) return;
    this.#emit('init_sent');
  }

  async #receive(data: string, generation: number): Promise<void> {
    if (!this.#isCurrentGeneration(generation) || !this.#isMessageState()) return;
    try {
      const message = this.#validator.validate(JSON.parse(data));
      if (message.kind === 'hello_ack' && message.phase === 'challenge') {
        await this.#handleChallenge(message, generation);
        return;
      }
      if (message.kind === 'hello_ack' && message.phase === 'accepted') {
        this.#handleAccepted(message, generation);
        return;
      }
      if (message.kind === 'hello_ack' && message.phase === 'rejected') {
        this.#teardown({
          generation,
          kind: 'local_initiated_close',
          closeCode: APPLICATION_CLOSE_CODES.authenticationFailure,
          closeReason: 'authentication failure',
          detail: `authentication rejected: ${String(message.reason_code)}`,
          reconnect: true,
          finalState: 'disconnected',
          eraseSecret: false,
        });
        return;
      }
      if (message.kind === 'pong') {
        this.#handlePong(message, generation);
        return;
      }
      throw new Error('Message direction or state is not allowed on the extension client');
    }
    catch (error) {
      if (!this.#isCurrentGeneration(generation)) return;
      const sessionInvalid = error instanceof SessionInvalidError;
      this.#teardown({
        generation,
        kind: 'local_initiated_close',
        closeCode: sessionInvalid
          ? APPLICATION_CLOSE_CODES.sessionInvalid
          : APPLICATION_CLOSE_CODES.protocolViolation,
        closeReason: sessionInvalid ? 'session invalid' : 'protocol violation',
        detail: errorDetail(error),
        reconnect: sessionInvalid,
        finalState: 'disconnected',
        eraseSecret: false,
      });
    }
  }

  async #handleChallenge(
    message: Readonly<Record<string, unknown>>,
    generation: number,
  ): Promise<void> {
    if (
      this.#state !== 'authenticating'
      || !this.#isCurrentGeneration(generation)
      || message.reply_to_message_id !== this.#initMessageId
      || message.client_nonce !== this.#clientNonce
      || Date.parse(String(message.expires_at)) <= Date.now()
    ) {
      throw new Error('Challenge correlation or expiry check failed');
    }
    this.#emit('challenge_received');
    const proof = await computeProof(this.#secret, {
      clientInstanceId: this.#clientInstanceId,
      challengeId: String(message.challenge_id),
      clientNonce: String(message.client_nonce),
      serverNonce: String(message.server_nonce),
      expiresAt: String(message.expires_at),
    });
    if (
      this.#state !== 'authenticating'
      || !this.#isCurrentGeneration(generation)
      || !this.#sendsEnabled
    ) return;
    const prove = {
      ...baseEnvelope(this.#traceId!),
      kind: 'hello',
      phase: 'prove',
      reply_to_message_id: message.message_id,
      challenge_id: message.challenge_id,
      proof,
    };
    this.#validator.validate(prove);
    this.#proveMessageId = prove.message_id;
    this.#send(prove, generation);
  }

  #handleAccepted(
    message: Readonly<Record<string, unknown>>,
    generation: number,
  ): void {
    if (
      this.#state !== 'authenticating'
      || !this.#isCurrentGeneration(generation)
      || message.reply_to_message_id !== this.#proveMessageId
    ) {
      throw new Error('Accepted message does not correlate to the active proof');
    }
    this.#clearReconnectTimer();
    this.#sessionId = String(message.session_id);
    this.#heartbeatIntervalMs = Number(message.heartbeat_interval_ms);
    this.#heartbeatTimeoutMs = Number(message.heartbeat_timeout_ms);
    this.#pendingPing = null;
    this.#state = 'authenticated';
    this.#sendsEnabled = true;
    this.#reconnectAttempt = 0;
    this.#emit('authenticated');
    if (this.#autoHeartbeat) this.#scheduleHeartbeat(generation);
  }

  #handlePong(
    message: Readonly<Record<string, unknown>>,
    generation: number,
  ): void {
    const pending = this.#pendingPing;
    if (
      !this.#canSendAuthenticated(generation)
      || pending === null
      || message.session_id !== this.#sessionId
      || message.reply_to_message_id !== pending.messageId
      || message.nonce !== pending.nonce
    ) {
      throw new SessionInvalidError('Pong session or correlation check failed');
    }
    this.#clearTimer('heartbeatTimeout');
    this.#pendingPing = null;
    this.#emit('heartbeat_received');
    if (this.#autoHeartbeat) this.#scheduleHeartbeat(generation);
  }

  #scheduleHeartbeat(generation: number): void {
    this.#clearTimer('heartbeat');
    if (!this.#canSendAuthenticated(generation)) return;
    this.#heartbeatTimer = this.#scheduler.setTimeout(
      () => {
        if (!this.#canSendAuthenticated(generation)) return;
        this.sendHeartbeat(generation);
      },
      this.#heartbeatIntervalMs,
    );
  }

  #send(message: Record<string, unknown>, generation: number): boolean {
    const attempt = this.#attempt;
    if (
      !this.#sendsEnabled
      || !this.#isCurrentGeneration(generation)
      || attempt === null
      || !attempt.socketOpen
      || this.#state === 'disconnecting'
    ) return false;
    try {
      this.#transport.send(attempt.id, JSON.stringify(message));
      return true;
    }
    catch (error) {
      this.#teardown({
        generation,
        kind: 'send_failure',
        detail: errorDetail(error),
        reconnect: true,
        finalState: 'disconnected',
        eraseSecret: false,
      });
      return false;
    }
  }

  #hostBoundaryFailed(generation: number, detail: string): void {
    if (!this.#isCurrentGeneration(generation)) return;
    const kind: TeardownKind = this.#state === 'connecting'
      ? 'connect_failure'
      : 'remote_loss';
    this.#teardown({
      generation,
      kind,
      detail: `host callback boundary failed: ${detail.slice(0, 192)}`,
      reconnect: true,
      finalState: 'disconnected',
      eraseSecret: false,
    });
  }

  #teardown(options: {
    readonly generation: number;
    readonly kind: TeardownKind;
    readonly closeCode?: number;
    readonly closeReason?: string;
    readonly detail: string;
    readonly reconnect: boolean;
    readonly finalState: 'disconnected' | 'stopped';
    readonly eraseSecret: boolean;
  }): void {
    if (
      !this.#isCurrentGeneration(options.generation)
      || this.#state === 'disconnecting'
      || this.#state === 'disconnected'
      || this.#state === 'retry_wait'
      || this.#state === 'reconnect_exhausted'
      || this.#state === 'stopped'
    ) return;

    const attempt = this.#attempt;
    this.#state = 'disconnecting';
    this.#sendsEnabled = false;
    this.#emit('disconnecting', options.detail);
    this.#clearAllTimers();
    const shouldClose = options.kind === 'local_initiated_close'
      && attempt !== null
      && attempt.generation === options.generation
      && attempt.socketOpen;
    try {
      if (shouldClose) {
        this.#transport.close(
          attempt.id,
          options.closeCode,
          options.closeReason,
        );
      }
    }
    catch (error) {
      this.#emit('transport_warning', `transport close failed: ${errorDetail(error)}`);
    }
    finally {
      this.#attempt = null;
      this.#clearSessionState();
      if (options.eraseSecret) this.#secret.fill(0);
      this.#state = options.finalState;
      if (options.finalState === 'disconnected') {
        this.#emit('disconnected', options.detail);
        if (options.reconnect) this.#scheduleReconnect(options.generation);
      }
    }
  }

  #scheduleReconnect(generation: number): void {
    if (
      this.#state !== 'disconnected'
      || this.#currentGeneration !== generation
      || this.#reconnectTimer !== undefined
    ) return;
    if (this.#reconnectAttempt >= this.#reconnectDelaysMs.length) {
      this.#state = 'reconnect_exhausted';
      this.#emit(
        'reconnect_exhausted',
        'Reconnect retries exhausted; configure the backend connection again.',
      );
      return;
    }
    const delay = this.#reconnectDelaysMs[this.#reconnectAttempt++]!;
    this.#state = 'retry_wait';
    this.#emit('reconnect_scheduled', `${delay}ms`);
    this.#reconnectTimer = this.#scheduler.setTimeout(() => {
      this.#reconnectTimer = undefined;
      if (
        this.#state === 'retry_wait'
        && this.#currentGeneration === generation
      ) this.#beginPhysicalConnect();
    }, delay);
  }

  #canSendAuthenticated(generation: number): boolean {
    return this.#state === 'authenticated'
      && this.#sessionId !== null
      && this.#sendsEnabled
      && this.#attempt?.socketOpen === true
      && this.#isCurrentGeneration(generation);
  }

  #isCurrentGeneration(generation: number): boolean {
    return generation === this.#currentGeneration
      && this.#attempt?.generation === generation;
  }

  #isMessageState(): boolean {
    return this.#state === 'authenticating' || this.#state === 'authenticated';
  }

  #invalidateAllCallbacks(): void {
    ++this.#currentGeneration;
    this.#sendsEnabled = false;
  }

  #clearSessionState(): void {
    this.#sessionId = null;
    this.#traceId = null;
    this.#clientNonce = null;
    this.#initMessageId = null;
    this.#proveMessageId = null;
    this.#pendingPing = null;
    this.#heartbeatIntervalMs = 0;
    this.#heartbeatTimeoutMs = 0;
  }

  #clearConnectionTimers(): void {
    this.#clearTimer('connectTimeout');
    this.#clearTimer('heartbeat');
    this.#clearTimer('heartbeatTimeout');
  }

  #clearReconnectTimer(): void {
    this.#clearTimer('reconnect');
  }

  #clearAllTimers(): void {
    this.#clearConnectionTimers();
    this.#clearReconnectTimer();
  }

  #clearTimer(
    name: 'connectTimeout' | 'heartbeat' | 'heartbeatTimeout' | 'reconnect',
  ): void {
    const handle = name === 'connectTimeout'
      ? this.#connectTimeout
      : name === 'heartbeat'
        ? this.#heartbeatTimer
        : name === 'heartbeatTimeout'
          ? this.#heartbeatTimeoutTimer
          : this.#reconnectTimer;
    if (handle !== undefined) this.#scheduler.clearTimeout(handle);
    if (name === 'connectTimeout') this.#connectTimeout = undefined;
    else if (name === 'heartbeat') this.#heartbeatTimer = undefined;
    else if (name === 'heartbeatTimeout') this.#heartbeatTimeoutTimer = undefined;
    else this.#reconnectTimer = undefined;
  }

  #emit(event: ProtocolClientDiagnostics['event'], detail?: string): void {
    try {
      this.#onDiagnostics(detail === undefined ? { event } : { event, detail });
    }
    catch {
      // Diagnostics are observational and must never break transport lifecycle.
    }
  }
}

function baseEnvelope(traceId: string): {
  protocol: 'aia-jlceda'; protocol_version: '1.0'; message_id: string;
  sent_at: string; trace_id: string;
} {
  return {
    protocol: 'aia-jlceda', protocol_version: '1.0',
    message_id: crypto.randomUUID(), sent_at: new Date().toISOString(), trace_id: traceId,
  };
}

function errorDetail(error: unknown): string {
  return error instanceof Error ? error.message.slice(0, 256) : 'unknown protocol error';
}
