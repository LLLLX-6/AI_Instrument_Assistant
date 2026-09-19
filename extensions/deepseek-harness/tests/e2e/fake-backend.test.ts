import assert from "node:assert/strict";
import { randomBytes } from "node:crypto";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { Context } from "@deepseek-ai/cordis";
import { ToolCallId } from "@deepseek-ai/dsh-llm";
import SystemPrompt from "@deepseek-ai/dsh-system-prompt";
import ToolRuntime from "@deepseek-ai/dsh-tools";

import { applyWithDependencies } from "../../src/index.ts";
import { HarnessHardwareIpcClient } from "../../src/ipc/client.ts";
import { AdapterFailure } from "../../src/ipc/errors.ts";
import { loadHarnessHardwareSecret } from "../../src/ipc/secret.ts";
import {
  createAgentHarness,
  finalAgentText,
  requestText,
  runAgent,
  textResponse,
  toolCallResponse,
  visibleToolCalls,
  simulatedPolicy,
  trustedTestScopeContext,
} from "../support/scripted-agent.ts";
import { startFakeBackend } from "../support/fake-backend-process.ts";

const OPERATIONS = [
  ["hardware_get_status", "hardware.get_status", {}],
  ["hardware_measure_frequency", "hardware.measure_frequency", { channel: 1 }],
  ["hardware_measure_vpp", "hardware.measure_vpp", { channel: 1 }],
  ["hardware_capture_waveform", "hardware.capture_waveform", { channel: 1 }],
  ["hardware_measure_pwm", "hardware.measure_pwm", { channel: 1, context_id: "PWM_OUT" }],
] as const;

test("wrong PSK fails closed before any Hardware request and leaks no secret", { timeout: 30_000 }, async () => {
  const backend = await startFakeBackend();
  const temporaryRoot = await mkdtemp(join(tmpdir(), "aia-wrong-psk-"));
  const wrongSecretFile = join(temporaryRoot, "wrong-hardware-psk.txt");
  const wrongSecret = randomBytes(32).toString("base64url");
  await writeFile(wrongSecretFile, wrongSecret, { encoding: "ascii", mode: 0o600 });
  const client = new HarnessHardwareIpcClient({
    endpoint: backend.endpoint,
    secretFile: wrongSecretFile,
    loadSecret: () => loadHarnessHardwareSecret(wrongSecretFile),
    connectTimeoutMs: 2_000,
    authTimeoutMs: 2_000,
    requestTimeoutMs: 5_000,
    reconnectDelaysMs: [],
  });
  try {
    client.start();
    await assert.rejects(client.waitUntilAuthenticated(5_000), (error: unknown) => {
      assert.ok(error instanceof AdapterFailure);
      assert.equal(error.code, "ipc_authentication_failed");
      assert.equal(error.deliveryState, "NOT_SENT");
      assert.doesNotMatch(error.message, new RegExp(wrongSecret));
      assert.doesNotMatch(error.message, /wrong-hardware-psk|aia-wrong-psk/i);
      return true;
    });
  } finally {
    await client.dispose();
    await backend.dispose();
    await rm(temporaryRoot, { recursive: true, force: true });
  }
});

test("real frozen ToolRuntime executes all five tools through the Python fake backend", { timeout: 30_000 }, async () => {
  const backend = await startFakeBackend();
  const ctx = new Context();
  try {
    await ctx.plugin(SystemPrompt);
    await ctx.plugin(ToolRuntime);
    const client = new HarnessHardwareIpcClient({
      endpoint: backend.endpoint,
      secretFile: backend.secretFile,
      loadSecret: () => loadHarnessHardwareSecret(backend.secretFile),
      connectTimeoutMs: 2_000,
      authTimeoutMs: 2_000,
      requestTimeoutMs: 5_000,
    });
    const operationScopeContext = trustedTestScopeContext();
    applyWithDependencies(ctx, {
      endpoint: backend.endpoint,
      secretFile: backend.secretFile,
      backendMode: "SIMULATED",
      connectTimeoutMs: 2_000,
      authTimeoutMs: 2_000,
      requestTimeoutMs: 5_000,
    }, {
      createClient: () => client,
      resolveOperationScopeContext: () => operationScopeContext,
      resolvePolicyContext: simulatedPolicy,
    });

    for (const [name, operation, arguments_] of OPERATIONS) {
      const response = await ctx.tools.execute({
        signal: new AbortController().signal,
        callId: ToolCallId(`phase7b4-${name}`),
        name,
        arguments: arguments_,
      });
      assert.equal(response.isError, false, `${name} should return a Tool value`);
      const value = response.value as Record<string, unknown>;
      assert.equal(value.operation, operation);
      assert.equal(typeof value.ok, "boolean");
    }

    const capture = await ctx.tools.execute({
      signal: new AbortController().signal,
      callId: ToolCallId("phase7b4-artifact"),
      name: "hardware_capture_waveform",
      arguments: { channel: 1 },
    });
    const encoded = JSON.stringify(capture.value);
    assert.match(encoded, /artifact_id/);
    assert.doesNotMatch(encoded, /"samples"|voltage_values|time_values/);

    await backend.stop();
    const offline = await ctx.tools.execute({
      signal: AbortSignal.timeout(5_000),
      callId: ToolCallId("phase7b4-offline"),
      name: "hardware_get_status",
      arguments: {},
    });
    assert.equal(offline.isError, true);
    assert.match(offline.error?.message ?? "", /unavailable|indeterminate/i);
    assert.ok(ctx.tools.get("hardware_get_status"), "tool registration survives backend loss");
  } finally {
    await ctx.fiber.dispose();
    await backend.dispose();
  }
});

test("real frozen Harness Agent consumes PWM evidence through authenticated simulated backend", { timeout: 30_000 }, async () => {
  const backend = await startFakeBackend();
  const harness = await createAgentHarness({
    config: {
      endpoint: backend.endpoint,
      secretFile: backend.secretFile,
      backendMode: "SIMULATED",
      connectTimeoutMs: 2_000,
      authTimeoutMs: 2_000,
      requestTimeoutMs: 5_000,
    },
    script: [
      toolCallResponse("agent-fake-pwm", "hardware_measure_pwm", { channel: 1, context_id: "PWM_OUT" }),
      (request) => {
        const evidence = requestText(request);
        assert.match(evidence, /AIA_TEACHING_EVIDENCE_CONTEXT/);
        assert.match(evidence, /"confirmationState":"SIMULATED"/);
        assert.match(evidence, /"source":"simulated"/);
        assert.match(evidence, /"percent":(?:29\.|30)/);
        assert.doesNotMatch(evidence, /"samples"|voltage_values|time_values/);
        return textResponse("SIMULATED OBSERVATION: PWM is approximately 10 kHz, 3.3 Vpp, and 30% duty cycle; this is not a real oscilloscope measurement.");
      },
    ],
  });
  try {
    await runAgent(harness.agent, "Measure the PWM on channel 1 and explain the duty cycle.");
    assert.deepEqual(visibleToolCalls(harness.agent), [{
      name: "hardware_measure_pwm",
      arguments: JSON.stringify({ channel: 1, context_id: "PWM_OUT" }),
    }]);
    const answer = finalAgentText(harness.agent);
    assert.match(answer, /SIMULATED OBSERVATION/);
    assert.match(answer, /10 kHz|10000/i);
    assert.match(answer, /30%/);
    assert.match(answer, /not a real oscilloscope measurement/i);
  } finally {
    await harness.ctx.fiber.dispose();
    await backend.dispose();
  }
});
