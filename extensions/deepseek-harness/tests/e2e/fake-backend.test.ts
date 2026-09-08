import assert from "node:assert/strict";
import test from "node:test";

import { Context } from "@deepseek-ai/cordis";
import { ToolCallId } from "@deepseek-ai/dsh-llm";
import SystemPrompt from "@deepseek-ai/dsh-system-prompt";
import ToolRuntime from "@deepseek-ai/dsh-tools";

import { applyWithDependencies } from "../../src/index.ts";
import { startFakeBackend } from "../support/fake-backend-process.ts";

const OPERATIONS = [
  ["hardware_get_status", "hardware.get_status", {}],
  ["hardware_measure_frequency", "hardware.measure_frequency", { channel: 1 }],
  ["hardware_measure_vpp", "hardware.measure_vpp", { channel: 1 }],
  ["hardware_capture_waveform", "hardware.capture_waveform", { channel: 1 }],
  ["hardware_measure_pwm", "hardware.measure_pwm", { channel: 1, context_id: "PWM_OUT" }],
] as const;

test("real frozen ToolRuntime executes all five tools through the Python fake backend", { timeout: 30_000 }, async () => {
  const backend = await startFakeBackend();
  const ctx = new Context();
  try {
    await ctx.plugin(SystemPrompt);
    await ctx.plugin(ToolRuntime);
    applyWithDependencies(ctx, {
      endpoint: backend.endpoint,
      secretFile: backend.secretFile,
      backendMode: "SIMULATED",
      connectTimeoutMs: 2_000,
      authTimeoutMs: 2_000,
      requestTimeoutMs: 5_000,
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
