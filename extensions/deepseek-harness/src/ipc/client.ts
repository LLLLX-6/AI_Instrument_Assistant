import { randomBytes, randomUUID } from "node:crypto";

import type { HardwareOperation } from "../generated/hardware-tools.generated.ts";
import { computeProof } from "./auth.ts";
import {
  AdapterFailure,
  safeAdapterFailure,
  type AdapterFailureCode,
  type DeliveryState,
} from "./errors.ts";
import { HarnessHardwareProtocolValidator, ProtocolMessageError } from "./protocol-validator.ts";
import {
  createPlatformWebSocket,
  type TextWebSocket,
  type WebSocketCloseEvent,
  type WebSocketFactory,
  type WebSocketMessageEvent,
} from "./websocket.ts";

export type ClientConnectionState =
  | "DISCONNECTED"
  | "CONNECTING"
  | "AUTHENTICATING"
  | "AUTHENTICATED"
  | "DISCONNECTING"
  | "RETRY_WAIT"
  | "RECONNECT_EXHAUSTED";

export interface ClientDiagnostic {
  readonly kind:
    | "state_changed"
    | "unknown_reply_to"
    | "duplicate_response"
    | "late_response"
    | "protocol_rejected"
    | "reconnect_exhausted";
  readonly generation: number;
}

export interface HarnessHardwareClientConfiguration {
  readonly endpoint: string;
  readonly secretFile?: string;
  readonly loadSecret: () => Promise<Uint8Array>;
  readonly socketFactory: WebSocketFactory;
  readonly connectTimeoutMs: number;
  readonly authTimeoutMs: number;
  readonly requestTimeoutMs: number;
  readonly heartbeatIntervalMs: number;
  readonly heartbeatTimeoutMs: number;
  readonly reconnectDelaysMs: readonly number[];
  readonly maximumMessageBytes: number;
  readonly diagnostics?: (event: ClientDiagnostic) => void;
}

export interface HarnessHardwareClientOptions {
  readonly endpoint: string;
  readonly secretFile?: string;
  readonly loadSecret: () => Promise<Uint8Array>;
  readonly socketFactory?: WebSocketFactory;
  readonly connectTimeoutMs?: number;
  readonly authTimeoutMs?: number;
  readonly requestTimeoutMs?: number;
  readonly heartbeatIntervalMs?: number;
  readonly heartbeatTimeoutMs?: number;
  readonly reconnectDelaysMs?: readonly number[];
  readonly maximumMessageBytes?: number;
  readonly diagnostics?: (event: ClientDiagnostic) => void;
}

interface AuthWaiter {
  readonly resolve: () => void;
  readonly reject: (error: AdapterFailure) => void;
  readonly timer: ReturnType<typeof setTimeout>;
}

interface PendingRequest {
  readonly operation: HardwareOperation;
  readonly generation: number;
  readonly resolve: (value: unknown) => void;
  readonly reject: (error: AdapterFailure) => void;
  readonly timeout: ReturnType<typeof setTimeout>;
  readonly signal: AbortSignal;
  readonly abort: () => void;
}

const PROTOCOL = "aia-harness-hardware";
const VERSION = 1;
const DEFAULT_RECONNECT_DELAYS = [500, 1_000, 2_000, 5_000] as const;
const MAX_RECORDS = 1_024;

export class HarnessHardwareIpcClient {
  readonly configuration: HarnessHardwareClientConfiguration;
  readonly #validator = new HarnessHardwareProtocolValidator();
  readonly #clientInstanceId = randomUUID();
  readonly #authWaiters = new Set<AuthWaiter>();
  readonly #pending = new Map<string, PendingRequest>();
  readonly #delivery = new Map<string, DeliveryState>();
  readonly #completed = new Set<string>();
  readonly #abandoned = new Set<string>();
  readonly #closedGenerations = new Set<number>();

  #state: ClientConnectionState = "DISCONNECTED";
  #socket: TextWebSocket | undefined;
  #generation = 0;
  #serverConnectionGeneration: number | undefined;
  #sessionId: string | undefined;
  #started = false;
  #disposed = false;
  #reconnectIndex = 0;
  #reconnectTimer: ReturnType<typeof setTimeout> | undefined;
  #connectTimer: ReturnType<typeof setTimeout> | undefined;
  #authTimer: ReturnType<typeof setTimeout> | undefined;
  #heartbeatTimer: ReturnType<typeof setInterval> | undefined;
  #heartbeatTimeoutTimer: ReturnType<typeof setTimeout> | undefined;
  #heartbeatMessageId: string | undefined;
  #helloMessageId: string | undefined;
  #proveMessageId: string | undefined;
  #clientNonce: string | undefined;
  #secretPromise: Promise<Uint8Array> | undefined;
  #lastAuthenticationFailure: AdapterFailure | undefined;

  constructor(options: HarnessHardwareClientOptions) {
    validateEndpoint(options.endpoint);
    const reconnectDelays = options.reconnectDelaysMs ?? DEFAULT_RECONNECT_DELAYS;
    const configuration: HarnessHardwareClientConfiguration = {
      endpoint: options.endpoint,
      ...(options.secretFile === undefined ? {} : { secretFile: options.secretFile }),
      loadSecret: options.loadSecret,
      socketFactory: options.socketFactory ?? createPlatformWebSocket,
      connectTimeoutMs: positive(options.connectTimeoutMs ?? 2_000, "connectTimeoutMs"),
      authTimeoutMs: positive(options.authTimeoutMs ?? 2_000, "authTimeoutMs"),
      requestTimeoutMs: positive(options.requestTimeoutMs ?? 30_000, "requestTimeoutMs"),
      heartbeatIntervalMs: positive(options.heartbeatIntervalMs ?? 10_000, "heartbeatIntervalMs"),
      heartbeatTimeoutMs: positive(options.heartbeatTimeoutMs ?? 30_000, "heartbeatTimeoutMs"),
      reconnectDelaysMs: reconnectDelays.map((value) => positive(value, "reconnectDelaysMs")),
      maximumMessageBytes: positive(options.maximumMessageBytes ?? 65_536, "maximumMessageBytes"),
      ...(options.diagnostics === undefined ? {} : { diagnostics: options.diagnostics }),
    };
    if (configuration.heartbeatTimeoutMs <= configuration.heartbeatIntervalMs) {
      throw new Error("heartbeatTimeoutMs must exceed heartbeatIntervalMs");
    }
    this.configuration = Object.freeze(configuration);
  }

  get state(): ClientConnectionState { return this.#state; }
  get sessionId(): string | undefined { return this.#sessionId; }
  get connectionGeneration(): number { return this.#generation; }

  start(): void {
    if (this.#disposed || this.#started) return;
    this.#started = true;
    this.#beginConnection();
  }

  async dispose(): Promise<void> {
    if (this.#disposed) return;
    this.#disposed = true;
    this.#started = false;
    this.#setState("DISCONNECTING");
    this.#clearTransportTimers();
    this.#rejectAllPending("client_cancelled_wait");
    this.#rejectAuthWaiters(safeAdapterFailure("client_cancelled_wait"));
    const socket = this.#socket;
    this.#socket = undefined;
    this.#sessionId = undefined;
    this.#serverConnectionGeneration = undefined;
    this.#secretPromise = undefined;
    if (socket && socket.readyState < 2) {
      try { socket.close(1000, "plugin disposed"); } catch { /* best effort */ }
    }
    this.#setState("DISCONNECTED");
  }

  waitUntilAuthenticated(timeoutMs = this.configuration.connectTimeoutMs + this.configuration.authTimeoutMs): Promise<void> {
    if (this.#state === "AUTHENTICATED") return Promise.resolve();
    if (this.#disposed) return Promise.reject(safeAdapterFailure("backend_unreachable"));
    if (this.#lastAuthenticationFailure) return Promise.reject(this.#lastAuthenticationFailure);
    if (!this.#started) this.start();
    return new Promise<void>((resolve, reject) => {
      const waiter: AuthWaiter = {
        resolve: () => {
          clearTimeout(waiter.timer);
          this.#authWaiters.delete(waiter);
          resolve();
        },
        reject: (error) => {
          clearTimeout(waiter.timer);
          this.#authWaiters.delete(waiter);
          reject(error);
        },
        timer: setTimeout(() => {
          this.#authWaiters.delete(waiter);
          reject(safeAdapterFailure("backend_unreachable"));
        }, positive(timeoutMs, "authentication wait timeout")),
      };
      this.#authWaiters.add(waiter);
    });
  }

  async invoke(operation: HardwareOperation, args: unknown, signal: AbortSignal): Promise<unknown> {
    if (signal.aborted) throw safeAdapterFailure("client_cancelled_wait", "NOT_SENT");
    await this.waitUntilAuthenticated();
    if (signal.aborted) throw safeAdapterFailure("client_cancelled_wait", "NOT_SENT");
    const socket = this.#socket;
    const sessionId = this.#sessionId;
    const generation = this.#generation;
    if (!socket || socket.readyState !== 1 || !sessionId || this.#state !== "AUTHENTICATED") {
      throw safeAdapterFailure("backend_unreachable", "NOT_SENT");
    }
    const messageId = randomUUID();
    this.#rememberDelivery(messageId, "NOT_SENT");
    const result = new Promise<unknown>((resolve, reject) => {
      const abort = () => {
        const pending = this.#takePending(messageId);
        if (!pending) return;
        this.#rememberAbandoned(messageId);
        this.#rememberCompleted(messageId);
        pending.reject(safeAdapterFailure("client_cancelled_wait", "SENT_UNCONFIRMED"));
      };
      const timeout = setTimeout(() => {
        const pending = this.#takePending(messageId);
        if (!pending) return;
        this.#rememberAbandoned(messageId);
        this.#rememberCompleted(messageId);
        pending.reject(safeAdapterFailure("indeterminate_execution", "SENT_UNCONFIRMED"));
      }, this.configuration.requestTimeoutMs);
      this.#pending.set(messageId, { operation, generation, resolve, reject, timeout, signal, abort });
      signal.addEventListener("abort", abort, { once: true });
    });
    this.#rememberDelivery(messageId, "SENT_UNCONFIRMED");
    try {
      this.#send({
        protocol: PROTOCOL,
        version: VERSION,
        message_id: messageId,
        session_id: sessionId,
        type: "request",
        operation,
        arguments: args,
      });
    } catch {
      const pending = this.#takePending(messageId);
      if (pending) pending.reject(safeAdapterFailure("indeterminate_execution", "SENT_UNCONFIRMED"));
      this.#disconnect(generation, true);
    }
    return result;
  }

  deliveryState(messageId: string): DeliveryState | undefined {
    return this.#delivery.get(messageId);
  }

  #beginConnection(): void {
    if (!this.#started || this.#disposed || this.#state === "CONNECTING" || this.#state === "AUTHENTICATING" || this.#state === "AUTHENTICATED") return;
    this.#clearReconnectTimer();
    const generation = ++this.#generation;
    this.#setState("CONNECTING");
    this.#sessionId = undefined;
    this.#serverConnectionGeneration = undefined;
    this.#helloMessageId = undefined;
    this.#proveMessageId = undefined;
    this.#clientNonce = undefined;
    const secretPromise = this.configuration.loadSecret();
    this.#secretPromise = secretPromise;
    void secretPromise.catch(() => {
      if (generation === this.#generation && !this.#disposed) {
        this.#authenticationFailed(generation);
      }
    });
    let socket: TextWebSocket;
    try {
      socket = this.configuration.socketFactory(this.configuration.endpoint);
    } catch {
      this.#disconnect(generation, true);
      return;
    }
    this.#socket = socket;
    socket.addEventListener("open", () => { void this.#onOpen(generation); });
    socket.addEventListener("message", (event) => {
      void this.#onMessage(generation, event).catch(() => this.#disconnect(generation, true));
    });
    socket.addEventListener("error", () => { this.#disconnect(generation, true); });
    socket.addEventListener("close", (event) => { this.#onClose(generation, event); });
    this.#connectTimer = setTimeout(() => this.#disconnect(generation, true), this.configuration.connectTimeoutMs);
  }

  async #onOpen(generation: number): Promise<void> {
    if (!this.#isCurrent(generation, "CONNECTING")) return;
    this.#clearConnectTimer();
    try {
      const secret = await this.#secretPromise;
      if (!secret || secret.byteLength !== 32) throw new Error("invalid secret");
      if (!this.#isCurrent(generation, "CONNECTING")) {
        secret.fill(0);
        return;
      }
      this.#setState("AUTHENTICATING");
      this.#helloMessageId = randomUUID();
      this.#clientNonce = randomBytes(32).toString("base64url");
      this.#send({
        protocol: PROTOCOL,
        version: VERSION,
        message_id: this.#helloMessageId,
        type: "hello",
        client_instance_id: this.#clientInstanceId,
        client_nonce: this.#clientNonce,
      });
      this.#authTimer = setTimeout(
        () => this.#authenticationFailed(generation),
        this.configuration.authTimeoutMs,
      );
    } catch {
      this.#authenticationFailed(generation);
    }
  }

  async #onMessage(generation: number, event: WebSocketMessageEvent): Promise<void> {
    if (generation !== this.#generation || this.#disposed) return;
    let message: Record<string, unknown>;
    try {
      message = this.#validator.parse(event.data, this.configuration.maximumMessageBytes);
    } catch (error) {
      if (error instanceof ProtocolMessageError) {
        this.#rejectAllPending("backend_response_invalid");
        this.#disconnect(generation, true);
        return;
      }
      this.#disconnect(generation, true);
      return;
    }
    const type = message.type;
    if (this.#state === "AUTHENTICATING") {
      if (type === "challenge") await this.#onChallenge(generation, message);
      else if (type === "accepted") this.#onAccepted(generation, message);
      else if (type === "rejected") this.#authenticationFailed(generation);
      else this.#authenticationFailed(generation, "backend_protocol_mismatch");
      return;
    }
    if (this.#state !== "AUTHENTICATED") return;
    if (message.session_id !== this.#sessionId) {
      this.#rejectAllPending("backend_response_invalid");
      this.#disconnect(generation, true);
      return;
    }
    if (type === "response") this.#onResponse(generation, message);
    else if (type === "error") this.#onProtocolError(generation, message);
    else if (type === "ping") this.#onPing(message);
    else if (type === "pong") this.#onPong(message);
    else {
      this.#rejectAllPending("backend_response_invalid");
      this.#disconnect(generation, true);
    }
  }

  async #onChallenge(generation: number, message: Record<string, unknown>): Promise<void> {
    if (
      message.reply_to !== this.#helloMessageId
      || message.client_nonce !== this.#clientNonce
      || message.algorithm !== "hmac-sha256"
      || typeof message.expires_at !== "string"
      || Date.parse(message.expires_at) <= Date.now()
    ) {
      this.#authenticationFailed(generation, "backend_protocol_mismatch");
      return;
    }
    const secret = await this.#secretPromise;
    if (!secret || !this.#isCurrent(generation, "AUTHENTICATING")) return;
    try {
      this.#proveMessageId = randomUUID();
      const proof = computeProof(secret, {
        clientInstanceId: this.#clientInstanceId,
        clientNonce: String(this.#clientNonce),
        serverNonce: String(message.server_nonce),
        challengeId: String(message.challenge_id),
        expiresAt: message.expires_at,
      });
      this.#send({
        protocol: PROTOCOL,
        version: VERSION,
        message_id: this.#proveMessageId,
        type: "prove",
        reply_to: message.message_id,
        challenge_id: message.challenge_id,
        proof,
      });
    } finally {
      secret.fill(0);
      this.#secretPromise = undefined;
    }
  }

  #onAccepted(generation: number, message: Record<string, unknown>): void {
    if (
      message.reply_to !== this.#proveMessageId
      || typeof message.session_id !== "string"
      || typeof message.connection_generation !== "number"
      || typeof message.expires_at !== "string"
      || Date.parse(message.expires_at) <= Date.now()
    ) {
      this.#authenticationFailed(generation, "backend_protocol_mismatch");
      return;
    }
    this.#clearAuthTimer();
    this.#sessionId = message.session_id;
    this.#serverConnectionGeneration = message.connection_generation;
    this.#reconnectIndex = 0;
    this.#lastAuthenticationFailure = undefined;
    this.#setState("AUTHENTICATED");
    this.#startHeartbeat(generation);
    for (const waiter of [...this.#authWaiters]) waiter.resolve();
  }

  #onResponse(generation: number, message: Record<string, unknown>): void {
    const replyTo = String(message.reply_to);
    const pending = this.#pending.get(replyTo);
    if (!pending) {
      if (this.#completed.has(replyTo)) {
        this.#diagnose(this.#abandoned.has(replyTo) ? "late_response" : "duplicate_response", generation);
      } else {
        this.#diagnose("unknown_reply_to", generation);
        this.#rejectAllPending("backend_response_invalid");
        this.#disconnect(generation, true);
      }
      return;
    }
    const hardwareResult = message.hardware_result;
    if (
      pending.generation !== generation
      || message.operation !== pending.operation
      || typeof hardwareResult !== "object"
      || hardwareResult === null
      || Array.isArray(hardwareResult)
      || (hardwareResult as Record<string, unknown>).operation !== pending.operation
    ) {
      const removed = this.#takePending(replyTo);
      removed?.reject(safeAdapterFailure("backend_response_invalid", "SENT_UNCONFIRMED"));
      this.#disconnect(generation, true);
      return;
    }
    const removed = this.#takePending(replyTo);
    if (!removed) return;
    this.#rememberDelivery(replyTo, "RESPONSE_RECEIVED");
    this.#rememberCompleted(replyTo);
    removed.resolve(hardwareResult);
  }

  #onProtocolError(generation: number, message: Record<string, unknown>): void {
    const replyTo = String(message.reply_to);
    const pending = this.#takePending(replyTo);
    if (!pending) {
      if (this.#completed.has(replyTo)) {
        this.#diagnose(this.#abandoned.has(replyTo) ? "late_response" : "duplicate_response", generation);
      } else {
        this.#diagnose("unknown_reply_to", generation);
        this.#rejectAllPending("backend_response_invalid");
        this.#disconnect(generation, true);
      }
      return;
    }
    this.#rememberCompleted(replyTo);
    pending.reject(safeAdapterFailure("backend_response_invalid", "SENT_UNCONFIRMED"));
  }

  #onPing(message: Record<string, unknown>): void {
    if (!this.#sessionId) return;
    this.#send({
      protocol: PROTOCOL,
      version: VERSION,
      message_id: randomUUID(),
      session_id: this.#sessionId,
      type: "pong",
      reply_to: message.message_id,
      sent_at: new Date().toISOString(),
    });
  }

  #onPong(message: Record<string, unknown>): void {
    if (message.reply_to !== this.#heartbeatMessageId) return;
    this.#heartbeatMessageId = undefined;
    if (this.#heartbeatTimeoutTimer) clearTimeout(this.#heartbeatTimeoutTimer);
    this.#heartbeatTimeoutTimer = undefined;
  }

  #startHeartbeat(generation: number): void {
    this.#stopHeartbeat();
    this.#heartbeatTimer = setInterval(() => {
      if (!this.#isCurrent(generation, "AUTHENTICATED") || !this.#sessionId) return;
      if (this.#heartbeatMessageId) return;
      const messageId = randomUUID();
      this.#heartbeatMessageId = messageId;
      try {
        this.#send({
          protocol: PROTOCOL,
          version: VERSION,
          message_id: messageId,
          session_id: this.#sessionId,
          type: "ping",
          sent_at: new Date().toISOString(),
        });
      } catch {
        this.#disconnect(generation, true);
        return;
      }
      this.#heartbeatTimeoutTimer = setTimeout(
        () => this.#disconnect(generation, true),
        this.configuration.heartbeatTimeoutMs,
      );
    }, this.configuration.heartbeatIntervalMs);
  }

  #onClose(generation: number, _event: WebSocketCloseEvent): void {
    this.#disconnect(generation, true);
  }

  #authenticationFailed(
    generation: number,
    code: AdapterFailureCode = "ipc_authentication_failed",
  ): void {
    if (generation !== this.#generation) return;
    const failure = safeAdapterFailure(code);
    this.#lastAuthenticationFailure = failure;
    this.#rejectAuthWaiters(failure);
    this.#disconnect(generation, false);
    this.#setState("RECONNECT_EXHAUSTED");
  }

  #disconnect(generation: number, reconnect: boolean): void {
    if (generation !== this.#generation || this.#closedGenerations.has(generation)) return;
    this.#closedGenerations.add(generation);
    this.#setState("DISCONNECTING");
    this.#clearTransportTimers();
    this.#rejectAllPending("indeterminate_execution");
    const socket = this.#socket;
    this.#socket = undefined;
    this.#sessionId = undefined;
    this.#serverConnectionGeneration = undefined;
    const secret = this.#secretPromise;
    this.#secretPromise = undefined;
    void secret?.then((value) => value.fill(0), () => undefined);
    if (socket && socket.readyState < 2) {
      try { socket.close(4005, "transport unavailable"); } catch { /* best effort */ }
    }
    this.#setState("DISCONNECTED");
    if (reconnect && this.#started && !this.#disposed) this.#scheduleReconnect();
  }

  #scheduleReconnect(): void {
    if (this.#reconnectTimer || this.#state === "RETRY_WAIT") return;
    const delay = this.configuration.reconnectDelaysMs[this.#reconnectIndex];
    if (delay === undefined) {
      this.#setState("RECONNECT_EXHAUSTED");
      this.#diagnose("reconnect_exhausted", this.#generation);
      this.#rejectAuthWaiters(safeAdapterFailure("backend_unreachable"));
      return;
    }
    this.#reconnectIndex += 1;
    this.#setState("RETRY_WAIT");
    this.#reconnectTimer = setTimeout(() => {
      this.#reconnectTimer = undefined;
      this.#setState("DISCONNECTED");
      this.#beginConnection();
    }, delay);
  }

  #send(message: Record<string, unknown>): void {
    const socket = this.#socket;
    if (!socket || socket.readyState !== 1) throw new Error("socket unavailable");
    socket.send(this.#validator.serialize(message, this.configuration.maximumMessageBytes));
  }

  #takePending(messageId: string): PendingRequest | undefined {
    const pending = this.#pending.get(messageId);
    if (!pending) return undefined;
    this.#pending.delete(messageId);
    clearTimeout(pending.timeout);
    pending.signal.removeEventListener("abort", pending.abort);
    return pending;
  }

  #rejectAllPending(code: AdapterFailureCode): void {
    for (const messageId of [...this.#pending.keys()]) {
      const pending = this.#takePending(messageId);
      if (!pending) continue;
      this.#rememberAbandoned(messageId);
      this.#rememberCompleted(messageId);
      pending.reject(safeAdapterFailure(code, this.#delivery.get(messageId) ?? "NOT_SENT"));
    }
  }

  #rememberDelivery(messageId: string, state: DeliveryState): void {
    this.#delivery.set(messageId, state);
    while (this.#delivery.size > MAX_RECORDS) this.#delivery.delete(this.#delivery.keys().next().value!);
  }

  #rememberCompleted(messageId: string): void {
    this.#completed.add(messageId);
    while (this.#completed.size > MAX_RECORDS) this.#completed.delete(this.#completed.values().next().value!);
  }

  #rememberAbandoned(messageId: string): void {
    this.#abandoned.add(messageId);
    while (this.#abandoned.size > MAX_RECORDS) this.#abandoned.delete(this.#abandoned.values().next().value!);
  }

  #isCurrent(generation: number, state?: ClientConnectionState): boolean {
    return generation === this.#generation && !this.#disposed && (state === undefined || this.#state === state);
  }

  #setState(state: ClientConnectionState): void {
    this.#state = state;
    this.#diagnose("state_changed", this.#generation);
  }

  #diagnose(kind: ClientDiagnostic["kind"], generation: number): void {
    try { this.configuration.diagnostics?.({ kind, generation }); } catch { /* diagnostics cannot affect transport */ }
  }

  #rejectAuthWaiters(error: AdapterFailure): void {
    for (const waiter of [...this.#authWaiters]) waiter.reject(error);
  }

  #clearConnectTimer(): void {
    if (this.#connectTimer) clearTimeout(this.#connectTimer);
    this.#connectTimer = undefined;
  }

  #clearAuthTimer(): void {
    if (this.#authTimer) clearTimeout(this.#authTimer);
    this.#authTimer = undefined;
  }

  #clearReconnectTimer(): void {
    if (this.#reconnectTimer) clearTimeout(this.#reconnectTimer);
    this.#reconnectTimer = undefined;
  }

  #stopHeartbeat(): void {
    if (this.#heartbeatTimer) clearInterval(this.#heartbeatTimer);
    if (this.#heartbeatTimeoutTimer) clearTimeout(this.#heartbeatTimeoutTimer);
    this.#heartbeatTimer = undefined;
    this.#heartbeatTimeoutTimer = undefined;
    this.#heartbeatMessageId = undefined;
  }

  #clearTransportTimers(): void {
    this.#clearConnectTimer();
    this.#clearAuthTimer();
    this.#stopHeartbeat();
  }
}

function validateEndpoint(value: string): void {
  let url: URL;
  try { url = new URL(value); } catch { throw new Error("endpoint must be a valid URL"); }
  if (
    url.protocol !== "ws:"
    || url.hostname !== "127.0.0.1"
    || !url.port
    || (url.pathname !== "" && url.pathname !== "/")
    || url.username
    || url.password
    || url.search
    || url.hash
  ) {
    throw new Error("endpoint must be an explicit ws://127.0.0.1:<port> URL");
  }
}

function positive(value: number, name: string): number {
  if (!Number.isSafeInteger(value) || value <= 0) throw new Error(`${name} must be a positive integer`);
  return value;
}
