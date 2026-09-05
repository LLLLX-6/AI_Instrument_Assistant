import type { JlcEdaApiAdapter } from '../runtime/jlc-eda-api-adapter.ts';
import type {
  TransportConnectedHandler,
  TransportBoundaryFailureHandler,
  TransportMessageHandler,
  WebSocketTransport,
} from './websocket-transport.ts';


export class JlcEdaWebSocketTransport implements WebSocketTransport {
  readonly #api: JlcEdaApiAdapter;

  constructor(api: JlcEdaApiAdapter) {
    this.#api = api;
  }

  register(
    connectionId: string,
    serviceUri: string,
    onMessage: TransportMessageHandler,
    onConnected: TransportConnectedHandler,
    onBoundaryFailure?: TransportBoundaryFailureHandler,
  ): void {
    this.#api.registerWebSocket(
      connectionId, serviceUri, onMessage, onConnected, onBoundaryFailure,
    );
  }

  send(connectionId: string, data: string): void {
    this.#api.sendWebSocket(connectionId, data);
  }

  close(connectionId: string, code?: number, reason?: string): void {
    this.#api.closeWebSocket(connectionId, code, reason);
  }
}
