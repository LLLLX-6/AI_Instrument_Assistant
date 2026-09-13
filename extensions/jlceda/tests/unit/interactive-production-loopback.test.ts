import assert from 'node:assert/strict';
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {
  InteractiveClient,
  type InteractiveTransport,
} from '../../src/interaction/interactive-client.ts';
import { InteractionSurface } from '../../src/interaction/interaction-surface.ts';
import { JlcEdaInteractionRuntime } from '../../src/interaction/product-runtime.ts';
import {
  ActivationRuntimeCommandService,
  dispatchRuntimeCommand,
  invokeRuntimeCommand,
} from '../../src/interaction/runtime-command-bridge.ts';
import {
  JlcEdaApiAdapter,
  type JlcEdaRuntimeBoundary,
} from '../../src/runtime/jlc-eda-api-adapter.ts';

const ROOT = path.resolve(import.meta.dirname, '../../../..');
const SECRET = new Uint8Array(32).fill(41);

class NodeWebSocketTransport implements InteractiveTransport {
  readonly #sockets = new Map<string, WebSocket>();
  register(
    id: string,
    uri: string,
    onMessage: (data: string) => void | Promise<void>,
    onConnected: () => void | Promise<void>,
    onBoundaryFailure: (detail: string) => void = () => undefined,
  ): void {
    const socket = new WebSocket(uri);
    this.#sockets.set(id, socket);
    socket.addEventListener('open', () => { void onConnected(); });
    socket.addEventListener('message', (event) => { void onMessage(String(event.data)); });
    socket.addEventListener('error', () => onBoundaryFailure('node_loopback_error'));
    socket.addEventListener('close', () => this.#sockets.delete(id));
  }
  send(id: string, data: string): void {
    const socket = this.#sockets.get(id);
    if (socket?.readyState !== WebSocket.OPEN) throw new Error('socket_unavailable');
    socket.send(data);
  }
  close(id: string, code?: number, reason?: string): void {
    const socket = this.#sockets.get(id);
    if (socket === undefined) return;
    socket.close(code, reason);
    this.#sockets.delete(id);
  }
}

test('production TypeScript client completes explicit Status snapshot from production Python server', async () => {
  const temporary = await mkdtemp(path.join(os.tmpdir(), 'aia-interactive-loopback-'));
  const credential = path.join(temporary, 'credential.txt');
  await writeFile(credential, Buffer.from(SECRET).toString('base64url'), 'ascii');
  const port = await freePort();
  const server = spawn(
    path.join(ROOT, '.venv', 'Scripts', 'python.exe'),
    [path.join(ROOT, 'tests', 'support', 'interactive_production_snapshot_server.py'), '--port', String(port), '--credential', credential],
    { cwd: ROOT, stdio: ['pipe', 'pipe', 'pipe'] },
  );
  try {
    await waitForReady(server);
    let resolveConnected!: () => void;
    const connected = new Promise<void>((resolve) => { resolveConnected = resolve; });
    const client = new InteractiveClient({
      transport: new NodeWebSocketTransport(),
      endpoint: { host: '127.0.0.1', port },
      secret: SECRET,
      clientInstanceId: '11111111-1111-4111-8111-111111111111',
      onState: (state) => { if (state === 'CONNECTED') resolveConnected(); },
    });
    client.start();
    await bounded(connected, 'client_connect_timeout');
    const refreshed = await client.refreshSnapshot();
    assert.equal(refreshed.status.host_state, 'READY');
    assert.equal(client.diagnostics.workflowSnapshotFrameCount, 2);
    assert.equal(client.diagnostics.snapshotWaiterAbsentCount, 1);
    assert.equal(client.diagnostics.snapshotWaiterPresentCount, 1);
    assert.equal(client.diagnostics.snapshotWaiterResolvedCount, 1);
    assert.equal(client.diagnostics.snapshotWaiterTimeoutCount, 0);

    const rendered: string[] = [];
    new InteractionSurface({
      showInformation: (content: string) => rendered.push(content),
      confirm: async () => false,
      select: async () => null,
    }, client).showStatus();
    assert.equal(rendered.length, 1);
    assert.match(rendered[0]!, /Application Host: READY/);
    client.dispose();
  } finally {
    server.kill('SIGINT');
    await waitForExit(server);
    await rm(temporary, { recursive: true, force: true });
  }
});

test('menu VM reaches activation runtime Status and design.observe through production Python loopback', async () => {
  const temporary = await mkdtemp(path.join(os.tmpdir(), 'aia-menu-bridge-loopback-'));
  const credential = path.join(temporary, 'credential.txt');
  await writeFile(credential, Buffer.from(SECRET).toString('base64url'), 'ascii');
  const port = await freePort();
  const server = spawn(
    path.join(ROOT, '.venv', 'Scripts', 'python.exe'),
    [path.join(ROOT, 'tests', 'support', 'interactive_production_snapshot_server.py'), '--port', String(port), '--credential', credential],
    { cwd: ROOT, stdio: ['pipe', 'pipe', 'pipe'] },
  );
  const bus = new PrivateMessageBus();
  const rendered: Array<{ content: string; title: string }> = [];
  let listenerPresent = false;
  const activationApi = new JlcEdaApiAdapter({
    sys_MessageBus: bus.runtime,
    sys_Storage: { setExtensionUserConfig: async () => true },
    sys_Message: { showToastMessage: () => undefined },
    sys_Dialog: {
      showInformationMessage: (content: string, title: string) => {
        rendered.push({ content, title });
      },
    },
    sch_Event: {
      isEventListenerAlreadyExist: () => listenerPresent,
      addMouseEventListener: () => { listenerPresent = true; },
      removeEventListener: () => { listenerPresent = false; },
    },
  } as unknown as JlcEdaRuntimeBoundary);
  const menuApi = new JlcEdaApiAdapter({
    sys_MessageBus: bus.runtime,
  } as unknown as JlcEdaRuntimeBoundary);
  let runtime!: JlcEdaInteractionRuntime;
  const service = new ActivationRuntimeCommandService(
    activationApi,
    (ownerRuntimeNo) => runtime.debugRuntimeNo === ownerRuntimeNo && runtime.clientPresent,
    (action) => dispatchRuntimeCommand(runtime, action),
  );
  runtime = new JlcEdaInteractionRuntime(
    activationApi,
    new NodeWebSocketTransport(),
    undefined,
    (runtimeNo) => service.register(runtimeNo),
  );
  try {
    await waitForReady(server);
    await runtime.configure(port, SECRET);
    await waitUntil(() => runtime.state === 'CONNECTED', 'runtime_connect_timeout');
    assert.equal(bus.registrations, 1);

    await invokeRuntimeCommand(menuApi, 'STATUS');
    assert.equal(rendered.length, 1);
    assert.equal(rendered[0]?.title, 'AI Instrument Assistant — Status');
    assert.match(rendered[0]?.content ?? '', /Application Host: READY/);
    assert.equal(runtime.diagnostics.snapshotWaiterResolvedCount, 1);

    const beforeObserve = runtime.diagnostics.workflowSnapshotFrameCount;
    await invokeRuntimeCommand(menuApi, 'REFRESH_DESIGN_CONTEXT');
    await waitUntil(
      () => runtime.diagnostics.workflowSnapshotFrameCount > beforeObserve + 1,
      'design_observe_result_timeout',
    );
    assert.equal(bus.calls.filter((value) => value === 'REFRESH_DESIGN_CONTEXT').length, 1);
  } finally {
    runtime.dispose();
    server.kill('SIGINT');
    await waitForExit(server);
    await rm(temporary, { recursive: true, force: true });
  }
});

class PrivateMessageBus {
  service: ((request: unknown) => unknown) | null = null;
  registrations = 0;
  readonly calls: string[] = [];
  readonly runtime = {
    rpcService: (topic: string, service: (request: unknown) => unknown) => {
      assert.equal(topic, 'aia.runtime.command');
      this.registrations += 1; this.service = service;
    },
    rpcCall: async (topic: string, request: unknown) => {
      assert.equal(topic, 'aia.runtime.command');
      assert.ok(request !== null && typeof request === 'object');
      this.calls.push(String((request as { action?: unknown }).action));
      if (this.service === null) throw new Error('service unavailable');
      return await this.service(request);
    },
  };
}

async function freePort(): Promise<number> {
  return await new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      assert.ok(address !== null && typeof address !== 'string');
      const port = address.port;
      server.close((error) => error === undefined ? resolve(port) : reject(error));
    });
  });
}

async function bounded<T>(value: Promise<T>, code: string): Promise<T> {
  let timeout: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      value,
      new Promise<never>((_resolve, reject) => {
        timeout = setTimeout(() => reject(new Error(code)), 3_000);
      }),
    ]);
  } finally {
    if (timeout !== undefined) clearTimeout(timeout);
  }
}

async function waitUntil(condition: () => boolean, code: string): Promise<void> {
  await bounded(new Promise<void>((resolve) => {
    const poll = (): void => {
      if (condition()) { resolve(); return; }
      setTimeout(poll, 10);
    };
    poll();
  }), code);
}

async function waitForReady(server: ChildProcessWithoutNullStreams): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('server_ready_timeout')), 3_000);
    server.stdout.on('data', (chunk: Buffer) => {
      if (!chunk.toString('utf8').includes('READY')) return;
      clearTimeout(timeout); resolve();
    });
    server.once('exit', () => reject(new Error('server_exited_before_ready')));
  });
}

async function waitForExit(server: ChildProcessWithoutNullStreams): Promise<void> {
  if (server.exitCode !== null) return;
  await new Promise<void>((resolve) => {
    const timeout = setTimeout(() => { server.kill(); resolve(); }, 1_000);
    server.once('exit', () => { clearTimeout(timeout); resolve(); });
  });
}
