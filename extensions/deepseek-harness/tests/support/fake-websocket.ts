import type {
  TextWebSocket,
  WebSocketCloseEvent,
  WebSocketEventMap,
} from "../../src/ipc/websocket.ts";

export class FakeWebSocket implements TextWebSocket {
  readyState = 0;
  readonly sent: string[] = [];
  readonly closeCalls: Array<{ readonly code?: number; readonly reason?: string }> = [];
  readonly #listeners = new Map<keyof WebSocketEventMap, Set<(event: never) => void>>();

  addEventListener<K extends keyof WebSocketEventMap>(
    type: K,
    listener: (event: WebSocketEventMap[K]) => void,
  ): void {
    const listeners = this.#listeners.get(type) ?? new Set();
    listeners.add(listener as (event: never) => void);
    this.#listeners.set(type, listeners);
  }

  send(data: string): void {
    if (this.readyState !== 1) throw new Error("socket is not open");
    this.sent.push(data);
  }

  close(code?: number, reason?: string): void {
    this.closeCalls.push({ code, reason });
    if (this.readyState >= 2) return;
    this.readyState = 3;
    this.#emit("close", { code: code ?? 1000, reason: reason ?? "", wasClean: true });
  }

  open(): void {
    this.readyState = 1;
    this.#emit("open", {});
  }

  receive(message: unknown): void {
    this.#emit("message", { data: JSON.stringify(message) });
  }

  fail(): void {
    this.#emit("error", {});
  }

  disconnect(code = 1006): void {
    this.readyState = 3;
    this.#emit("close", { code, reason: "", wasClean: false });
  }

  #emit<K extends keyof WebSocketEventMap>(type: K, event: WebSocketEventMap[K]): void {
    for (const listener of this.#listeners.get(type) ?? []) {
      listener(event as never);
    }
  }
}

export class FakeWebSocketFactory {
  readonly sockets: FakeWebSocket[] = [];

  create = (_url: string): TextWebSocket => {
    const socket = new FakeWebSocket();
    this.sockets.push(socket);
    return socket;
  };
}

export function closeEvent(code = 1006): WebSocketCloseEvent {
  return { code, reason: "", wasClean: false };
}
