export type TransportMessageHandler = (data: string) => void | Promise<void>;
export type TransportConnectedHandler = () => void | Promise<void>;
export type TransportBoundaryFailureHandler = (detail: string) => void;

export interface WebSocketTransport {
  register(
    connectionId: string,
    serviceUri: string,
    onMessage: TransportMessageHandler,
    onConnected: TransportConnectedHandler,
    onBoundaryFailure?: TransportBoundaryFailureHandler,
  ): void;
  send(connectionId: string, data: string): void;
  close(connectionId: string, code?: number, reason?: string): void;
}
