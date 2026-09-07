export interface WebSocketOpenEvent {}
export interface WebSocketMessageEvent { readonly data: unknown }
export interface WebSocketErrorEvent {}
export interface WebSocketCloseEvent {
  readonly code: number;
  readonly reason: string;
  readonly wasClean: boolean;
}

export interface WebSocketEventMap {
  readonly open: WebSocketOpenEvent;
  readonly message: WebSocketMessageEvent;
  readonly error: WebSocketErrorEvent;
  readonly close: WebSocketCloseEvent;
}

export interface TextWebSocket {
  readonly readyState: number;
  addEventListener<K extends keyof WebSocketEventMap>(
    type: K,
    listener: (event: WebSocketEventMap[K]) => void,
  ): void;
  send(data: string): void;
  close(code?: number, reason?: string): void;
}

export type WebSocketFactory = (url: string) => TextWebSocket;

export function createPlatformWebSocket(url: string): TextWebSocket {
  return new WebSocket(url) as unknown as TextWebSocket;
}
