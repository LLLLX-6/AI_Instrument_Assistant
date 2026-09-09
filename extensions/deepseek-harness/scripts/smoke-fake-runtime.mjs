import { Context } from "@deepseek-ai/cordis";
import { ToolCallId } from "@deepseek-ai/dsh-llm";
import SystemPrompt from "@deepseek-ai/dsh-system-prompt";
import ToolRuntime from "@deepseek-ai/dsh-tools";

import { applyWithDependencies } from "../src/index.ts";
import { createTrustedOperationScope } from "../src/operation-scope/index.ts";

const endpoint = process.env.AIA_HARNESS_HARDWARE_ENDPOINT ?? "ws://127.0.0.1:49625";
const secretFile = process.env.AIA_HARNESS_HARDWARE_SECRET_FILE ?? ".aia-secrets/harness-hardware-psk.txt";
const operations = [
  ["hardware_get_status", {}],
  ["hardware_measure_frequency", { channel: 1 }],
  ["hardware_measure_vpp", { channel: 1 }],
  ["hardware_capture_waveform", { channel: 1 }],
  ["hardware_measure_pwm", { channel: 1, context_id: "PWM_OUT" }],
];

const ctx = new Context();
const workflowId = "manual-fake-runtime-smoke";
const scope = createTrustedOperationScope({
  scopeId: "manual-fake-runtime-smoke-scope",
  requestCorrelationId: workflowId,
  workflowId,
  allowedOperations: operations.map(([name]) => ({
    operation: name === "hardware_get_status"
      ? "hardware.get_status"
      : name.replace("hardware_", "hardware."),
    maxInvocations: 1,
  })),
  targetChannel: null,
  targetIntent: "explicit fake runtime smoke",
  origin: "TRUSTED_VALIDATION_SCENARIO",
  authorizationRef: null,
});
try {
  await ctx.plugin(SystemPrompt);
  await ctx.plugin(ToolRuntime);
  applyWithDependencies(ctx, { endpoint, secretFile, backendMode: "SIMULATED" }, {
    resolveOperationScopeContext: () => ({ scope, requestCorrelationId: workflowId, workflowId }),
  });
  const summaries = [];
  for (const [name, args] of operations) {
    const response = await ctx.tools.execute({
      signal: AbortSignal.timeout(35_000),
      callId: ToolCallId(`manual-${name}`),
      name,
      arguments: args,
    });
    const value = response.value ?? {};
    const artifact = value?.result?.waveform?.artifact;
    summaries.push({
      name,
      harness_error: response.isError,
      operation: value.operation,
      ok: value.ok,
      artifact_id: artifact?.artifact_id,
      artifact_media_type: artifact?.media_type,
    });
  }
  console.log(JSON.stringify({ authenticated_tool_results: summaries }, null, 2));
  if (summaries.some((item) => item.harness_error)) process.exitCode = 2;
} finally {
  await ctx.fiber.dispose();
}
