import assert from "node:assert/strict";
import { randomBytes, randomUUID } from "node:crypto";
import test from "node:test";

import { computeProof } from "../../src/ipc/auth.ts";
import {
  HarnessHardwareIpcClient,
  type HarnessHardwareClientOptions,
} from "../../src/ipc/client.ts";
import { AdapterFailure } from "../../src/ipc/errors.ts";
import { FakeWebSocketFactory } from "../support/fake-websocket.ts";
import { HARDWARE_ERROR_RESULT, STATUS_RESULT } from "../support/canonical-results.ts";

const SECRET = randomBytes(32);
const tick = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

function createClient(
  factory = new FakeWebSocketFactory(),
  overrides: Partial<HarnessHardwareClientOptions> = {},
) {
  const client = new HarnessHardwareIpcClient({
    endpoint: "ws://127.0.0.1:49625",
    loadSecret: async () => Uint8Array.from(SECRET),
    socketFactory: factory.create,
    connectTimeoutMs: 100,
    authTimeoutMs: 100,
    requestTimeoutMs: 100,
    heartbeatIntervalMs: 1_000,
    heartbeatTimeoutMs: 2_000,
    reconnectDelaysMs: [1, 2],
    ...overrides,
  });
  return { client, factory };
}

async function authenticate(client: HarnessHardwareIpcClient, factory: FakeWebSocketFactory) {
  client.start();
  const socket = factory.sockets[0]!;
  socket.open();
  await tick();
  const hello = JSON.parse(socket.sent.at(-1)!);
  const expiresAt = new Date(Date.now() + 10_000).toISOString();
  const challenge = {
    protocol: "aia-harness-hardware",
    version: 1,
    message_id: randomUUID(),
    type: "challenge",
    reply_to: hello.message_id,
    challenge_id: randomUUID(),
    client_nonce: hello.client_nonce,
    server_nonce: randomBytes(32).toString("base64url"),
    algorithm: "hmac-sha256",
    expires_at: expiresAt,
  };
  socket.receive(challenge);
  await tick();
  const prove = JSON.parse(socket.sent.at(-1)!);
  assert.equal(prove.proof, computeProof(SECRET, {
    clientInstanceId: hello.client_instance_id,
    clientNonce: hello.client_nonce,
    serverNonce: challenge.server_nonce,
    challengeId: challenge.challenge_id,
    expiresAt,
  }));
  const sessionId = randomUUID();
  socket.receive({
    protocol: "aia-harness-hardware",
    version: 1,
    message_id: randomUUID(),
    type: "accepted",
    reply_to: prove.message_id,
    session_id: sessionId,
    connection_generation: 1,
    expires_at: new Date(Date.now() + 60_000).toISOString(),
  });
  await client.waitUntilAuthenticated(100);
  return { socket, sessionId, hello, challenge, prove };
}

test("auth success uses fresh challenge proof and reaches AUTHENTICATED", async () => {
  const { client, factory } = createClient();
  const { sessionId } = await authenticate(client, factory);
  assert.equal(client.state, "AUTHENTICATED");
  assert.equal(client.sessionId, sessionId);
  await client.dispose();
});

test("auth rejection is bounded and never leaks the secret", async () => {
  const { client, factory } = createClient();
  client.start();
  const socket = factory.sockets[0]!;
  socket.open();
  await tick();
  const hello = JSON.parse(socket.sent[0]!);
  socket.receive({
    protocol: "aia-harness-hardware", version: 1, message_id: randomUUID(), type: "rejected",
    reply_to: hello.message_id, code: "authentication_failed", message: "Authentication failed.",
  });
  await assert.rejects(client.waitUntilAuthenticated(50), (error: unknown) => {
    assert.ok(error instanceof AdapterFailure);
    assert.equal(error.code, "ipc_authentication_failed");
    assert.doesNotMatch(error.message, new RegExp(SECRET.toString("base64url")));
    return true;
  });
  await client.dispose();
});

test("correlated response returns canonical value including ok=false", async () => {
  const { client, factory } = createClient();
  const { socket, sessionId } = await authenticate(client, factory);
  const pending = client.invoke("hardware.measure_vpp", { channel: 1 }, new AbortController().signal);
  await tick();
  const request = JSON.parse(socket.sent.at(-1)!);
  socket.receive({
    protocol: "aia-harness-hardware", version: 1, message_id: randomUUID(), session_id: sessionId,
    type: "response", reply_to: request.message_id, operation: request.operation,
    hardware_result: HARDWARE_ERROR_RESULT,
  });
  assert.deepEqual(await pending, HARDWARE_ERROR_RESULT);
  assert.equal(client.deliveryState(request.message_id), "RESPONSE_RECEIVED");
  await client.dispose();
});

test("unknown reply_to is ignored with a bounded diagnostic", async () => {
  const diagnostics: string[] = [];
  const factory = new FakeWebSocketFactory();
  const client = new HarnessHardwareIpcClient({
    ...createClient(factory).client.configuration,
    diagnostics: (event) => diagnostics.push(event.kind),
  });
  const { socket, sessionId } = await authenticate(client, factory);
  const response = {
    protocol: "aia-harness-hardware", version: 1, message_id: randomUUID(), session_id: sessionId,
    type: "response", reply_to: randomUUID(), operation: "hardware.get_status", hardware_result: STATUS_RESULT,
  };
  socket.receive(response);
  await tick();
  assert.ok(diagnostics.includes("unknown_reply_to"));
  assert.notEqual(client.state, "AUTHENTICATED");
  await client.dispose();
});

test("duplicate response is ignored with a bounded diagnostic", async () => {
  const diagnostics: string[] = [];
  const factory = new FakeWebSocketFactory();
  const client = new HarnessHardwareIpcClient({
    ...createClient(factory).client.configuration,
    diagnostics: (event) => diagnostics.push(event.kind),
  });
  const { socket, sessionId } = await authenticate(client, factory);
  const pending = client.invoke("hardware.get_status", {}, new AbortController().signal);
  await tick();
  const request = JSON.parse(socket.sent.at(-1)!);
  const response = {
    protocol: "aia-harness-hardware", version: 1, message_id: randomUUID(), session_id: sessionId,
    type: "response", reply_to: request.message_id, operation: request.operation, hardware_result: STATUS_RESULT,
  };
  socket.receive(response);
  assert.deepEqual(await pending, STATUS_RESULT);
  socket.receive({ ...response, message_id: randomUUID() });
  await tick();
  assert.ok(diagnostics.includes("duplicate_response"));
  await client.dispose();
});

test("disconnect before send is backend_unreachable and never creates a request", async () => {
  const { client, factory } = createClient(new FakeWebSocketFactory(), { reconnectDelaysMs: [] });
  client.start();
  const socket = factory.sockets[0]!;
  const pending = client.invoke("hardware.get_status", {}, new AbortController().signal);
  socket.disconnect();
  await assert.rejects(
    pending,
    (error: unknown) => error instanceof AdapterFailure
      && error.code === "backend_unreachable"
      && error.deliveryState === "NOT_SENT",
  );
  assert.equal(socket.sent.length, 0);
  await client.dispose();
});

test("disconnect after send is indeterminate and request is never replayed", async () => {
  const { client, factory } = createClient();
  const { socket } = await authenticate(client, factory);
  const pending = client.invoke("hardware.get_status", {}, new AbortController().signal);
  await tick();
  const sendCount = socket.sent.length;
  socket.disconnect();
  await assert.rejects(pending, (error: unknown) => {
    assert.ok(error instanceof AdapterFailure);
    assert.equal(error.code, "indeterminate_execution");
    assert.equal(error.deliveryState, "SENT_UNCONFIRMED");
    return true;
  });
  await new Promise((resolve) => setTimeout(resolve, 5));
  assert.equal(socket.sent.length, sendCount);
  assert.ok(factory.sockets.length >= 2);
  await client.dispose();
});

test("request timeout after send is indeterminate", async () => {
  const { client, factory } = createClient();
  await authenticate(client, factory);
  await assert.rejects(
    client.invoke("hardware.get_status", {}, new AbortController().signal),
    (error: unknown) => error instanceof AdapterFailure && error.code === "indeterminate_execution",
  );
  await client.dispose();
});

test("response arriving after request timeout is ignored as late", async () => {
  const diagnostics: string[] = [];
  const factory = new FakeWebSocketFactory();
  const { client } = createClient(factory, {
    requestTimeoutMs: 5,
    diagnostics: (event) => diagnostics.push(event.kind),
  });
  const { socket, sessionId } = await authenticate(client, factory);
  const pending = client.invoke("hardware.get_status", {}, new AbortController().signal);
  await tick();
  const request = JSON.parse(socket.sent.at(-1)!);
  await assert.rejects(pending, (error: unknown) => error instanceof AdapterFailure && error.code === "indeterminate_execution");
  socket.receive({
    protocol: "aia-harness-hardware", version: 1, message_id: randomUUID(), session_id: sessionId,
    type: "response", reply_to: request.message_id, operation: request.operation, hardware_result: STATUS_RESULT,
  });
  await tick();
  assert.ok(diagnostics.includes("late_response"));
  assert.equal(client.state, "AUTHENTICATED");
  await client.dispose();
});

test("cancellation before send and after send only stop client waiting", async () => {
  const first = createClient();
  const preAborted = new AbortController();
  preAborted.abort();
  await assert.rejects(
    first.client.invoke("hardware.get_status", {}, preAborted.signal),
    (error: unknown) => error instanceof AdapterFailure
      && error.code === "client_cancelled_wait"
      && error.deliveryState === "NOT_SENT",
  );
  await first.client.dispose();

  const second = createClient();
  await authenticate(second.client, second.factory);
  const controller = new AbortController();
  const pending = second.client.invoke("hardware.get_status", {}, controller.signal);
  await tick();
  controller.abort();
  await assert.rejects(
    pending,
    (error: unknown) => error instanceof AdapterFailure
      && error.code === "client_cancelled_wait"
      && error.deliveryState === "SENT_UNCONFIRMED",
  );
  await second.client.dispose();
});

test("reconnect creates a new generation and ignores old callbacks", async () => {
  const { client, factory } = createClient();
  const first = await authenticate(client, factory);
  first.socket.disconnect();
  await new Promise((resolve) => setTimeout(resolve, 3));
  const secondSocket = factory.sockets.at(-1)!;
  assert.notEqual(secondSocket, first.socket);
  first.socket.receive({
    protocol: "aia-harness-hardware", version: 1, message_id: randomUUID(), type: "accepted",
    reply_to: randomUUID(), session_id: randomUUID(), connection_generation: 99,
    expires_at: new Date(Date.now() + 60_000).toISOString(),
  });
  assert.notEqual(client.state, "AUTHENTICATED");
  await client.dispose();
});

test("reconnect authenticates with a new nonce and new session", async () => {
  const { client, factory } = createClient();
  const first = await authenticate(client, factory);
  first.socket.disconnect();
  await new Promise((resolve) => setTimeout(resolve, 3));
  const secondSocket = factory.sockets.at(-1)!;
  secondSocket.open();
  await tick();
  const secondHello = JSON.parse(secondSocket.sent.at(-1)!);
  assert.notEqual(secondHello.client_nonce, first.hello.client_nonce);
  const expiresAt = new Date(Date.now() + 10_000).toISOString();
  const challenge = {
    protocol: "aia-harness-hardware", version: 1, message_id: randomUUID(), type: "challenge",
    reply_to: secondHello.message_id, challenge_id: randomUUID(), client_nonce: secondHello.client_nonce,
    server_nonce: randomBytes(32).toString("base64url"), algorithm: "hmac-sha256", expires_at: expiresAt,
  };
  secondSocket.receive(challenge);
  await tick();
  const secondProve = JSON.parse(secondSocket.sent.at(-1)!);
  const secondSession = randomUUID();
  secondSocket.receive({
    protocol: "aia-harness-hardware", version: 1, message_id: randomUUID(), type: "accepted",
    reply_to: secondProve.message_id, session_id: secondSession, connection_generation: 2,
    expires_at: new Date(Date.now() + 60_000).toISOString(),
  });
  await client.waitUntilAuthenticated(100);
  assert.notEqual(secondSession, first.sessionId);
  assert.equal(client.sessionId, secondSession);
  assert.equal(client.connectionGeneration, 2);
  await client.dispose();
});

test("missing secret is converted to a bounded authentication failure", async () => {
  const { client } = createClient(new FakeWebSocketFactory(), {
    loadSecret: async () => { throw new Error("C:\\private\\secret.txt unavailable"); },
  });
  client.start();
  await assert.rejects(client.waitUntilAuthenticated(100), (error: unknown) => {
    assert.ok(error instanceof AdapterFailure);
    assert.equal(error.code, "ipc_authentication_failed");
    assert.doesNotMatch(error.message, /private|secret\.txt/i);
    return true;
  });
  await client.dispose();
});

test("endpoint policy accepts only explicit IPv4 loopback WebSocket URLs", () => {
  for (const endpoint of (
    ["wss://127.0.0.1:49625", "ws://localhost:49625", "ws://0.0.0.0:49625", "ws://127.0.0.1:49625/path"]
  )) {
    assert.throws(() => createClient(new FakeWebSocketFactory(), { endpoint }));
  }
});

test("connect timeout and auth timeout are distinct bounded pre-send failures", async () => {
  const connecting = createClient(new FakeWebSocketFactory(), {
    connectTimeoutMs: 5,
    reconnectDelaysMs: [],
  });
  connecting.client.start();
  await assert.rejects(
    connecting.client.waitUntilAuthenticated(100),
    (error: unknown) => error instanceof AdapterFailure
      && error.code === "backend_unreachable"
      && error.deliveryState === "NOT_SENT",
  );
  await connecting.client.dispose();

  const authenticating = createClient(new FakeWebSocketFactory(), {
    authTimeoutMs: 5,
    reconnectDelaysMs: [],
  });
  authenticating.client.start();
  authenticating.factory.sockets[0]!.open();
  await assert.rejects(
    authenticating.client.waitUntilAuthenticated(100),
    (error: unknown) => error instanceof AdapterFailure
      && error.code === "ipc_authentication_failed"
      && error.deliveryState === "NOT_SENT",
  );
  await authenticating.client.dispose();
});

test("heartbeat carries no hardware operation and pong preserves the session", async () => {
  const { client, factory } = createClient(new FakeWebSocketFactory(), {
    heartbeatIntervalMs: 10,
    heartbeatTimeoutMs: 100,
  });
  const { socket, sessionId } = await authenticate(client, factory);
  await new Promise((resolve) => setTimeout(resolve, 15));
  const ping = JSON.parse(socket.sent.at(-1)!);
  assert.equal(ping.type, "ping");
  assert.equal(ping.session_id, sessionId);
  assert.equal("operation" in ping, false);
  socket.receive({
    protocol: "aia-harness-hardware", version: 1, message_id: randomUUID(), session_id: sessionId,
    type: "pong", reply_to: ping.message_id, sent_at: new Date().toISOString(),
  });
  await tick();
  assert.equal(client.state, "AUTHENTICATED");
  await client.dispose();
});

test("response operation mismatch is rejected instead of crossing correlations", async () => {
  const { client, factory } = createClient();
  const { socket, sessionId } = await authenticate(client, factory);
  const pending = client.invoke("hardware.get_status", {}, new AbortController().signal);
  await tick();
  const request = JSON.parse(socket.sent.at(-1)!);
  socket.receive({
    protocol: "aia-harness-hardware", version: 1, message_id: randomUUID(), session_id: sessionId,
    type: "response", reply_to: request.message_id, operation: "hardware.get_status",
    hardware_result: HARDWARE_ERROR_RESULT,
  });
  await assert.rejects(
    pending,
    (error: unknown) => error instanceof AdapterFailure && error.code === "backend_response_invalid",
  );
  await client.dispose();
});

test("invalid server message is bounded and never reaches a pending invocation", async () => {
  const { client, factory } = createClient();
  const { socket } = await authenticate(client, factory);
  const pending = client.invoke("hardware.get_status", {}, new AbortController().signal);
  await tick();
  socket.receive({ unexpected: "unvalidated" });
  await assert.rejects(
    pending,
    (error: unknown) => error instanceof AdapterFailure && error.code === "backend_response_invalid",
  );
  await client.dispose();
});
