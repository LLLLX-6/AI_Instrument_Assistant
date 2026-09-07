import { spawn, type ChildProcessByStdio } from "node:child_process";
import { once } from "node:events";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import type { Readable } from "node:stream";

export interface RunningFakeBackend {
  readonly endpoint: string;
  readonly secretFile: string;
  stop(): Promise<void>;
  dispose(): Promise<void>;
}

export async function startFakeBackend(): Promise<RunningFakeBackend> {
  const projectRoot = resolve(new URL("../../../..", import.meta.url).pathname.replace(/^\/(.:)/, "$1"));
  const temporaryRoot = await mkdtemp(join(tmpdir(), "aia-harness-e2e-"));
  const secretFile = join(temporaryRoot, "harness-hardware-psk.txt");
  const secret = crypto.getRandomValues(new Uint8Array(32));
  await writeFile(secretFile, Buffer.from(secret).toString("base64url"), { encoding: "ascii", mode: 0o600 });
  secret.fill(0);
  const port = await reservePort();
  const python = process.env.AIA_PYTHON ?? resolve(projectRoot, ".venv", "Scripts", "python.exe");
  const child = spawn(
    python,
    [
      "-u", "-m", "ai_instrument_assistant.integrations.harness_hardware.cli",
      "--backend", "fake", "--port", String(port), "--secret-file", secretFile,
    ],
    {
      cwd: projectRoot,
      env: { ...process.env, PYTHONPATH: resolve(projectRoot, "src") },
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    },
  );
  try {
    await waitUntilReady(child);
  } catch (error) {
    child.kill();
    await rm(temporaryRoot, { recursive: true, force: true });
    throw error;
  }
  let stopped = false;
  return {
    endpoint: `ws://127.0.0.1:${port}`,
    secretFile,
    async stop() {
      if (stopped) return;
      stopped = true;
      if (child.exitCode === null) {
        child.kill();
        await Promise.race([once(child, "exit"), delay(3_000)]);
      }
    },
    async dispose() {
      if (!stopped && child.exitCode === null) {
        child.kill();
        await Promise.race([once(child, "exit"), delay(3_000)]);
      }
      stopped = true;
      await rm(temporaryRoot, { recursive: true, force: true });
    },
  };
}

async function reservePort(): Promise<number> {
  const server = createServer();
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("Could not reserve a loopback port");
  const port = address.port;
  server.close();
  await once(server, "close");
  return port;
}

function waitUntilReady(child: ChildProcessByStdio<null, Readable, Readable>): Promise<void> {
  return new Promise((resolveReady, reject) => {
    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => fail("Timed out starting Python fake backend"), 10_000);
    const cleanup = () => {
      clearTimeout(timer);
      child.stdout.off("data", onStdout);
      child.stderr.off("data", onStderr);
      child.off("exit", onExit);
    };
    const fail = (message: string) => {
      cleanup();
      reject(new Error(`${message}: ${stderr.slice(0, 500)}`));
    };
    const onStdout = (chunk: Buffer) => {
      stdout += chunk.toString("utf8");
      if (stdout.includes("Harness Hardware backend ready at")) {
        cleanup();
        resolveReady();
      }
    };
    const onStderr = (chunk: Buffer) => { stderr += chunk.toString("utf8"); };
    const onExit = (code: number | null) => fail(`Python fake backend exited with ${code}`);
    child.stdout.on("data", onStdout);
    child.stderr.on("data", onStderr);
    child.on("exit", onExit);
  });
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolveDelay) => setTimeout(resolveDelay, milliseconds));
}
