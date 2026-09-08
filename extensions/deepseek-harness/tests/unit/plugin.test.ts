import assert from "node:assert/strict";
import test from "node:test";

import { Context } from "@deepseek-ai/cordis";
import { ToolCallId } from "@deepseek-ai/dsh-llm";
import SystemPrompt from "@deepseek-ai/dsh-system-prompt";
import ToolRuntime from "@deepseek-ai/dsh-tools";

import { applyWithDependencies, inject, name } from "../../src/index.ts";
import { AdapterFailure, safeAdapterFailure } from "../../src/ipc/errors.ts";
import { HARDWARE_TOOL_CONTRACTS } from "../../src/generated/hardware-tools.generated.ts";
import {
  createHardwareToolPolicyContext,
  createProbeSetupConfirmation,
  type HardwareToolPolicyContext,
} from "../../src/policy/index.ts";
import { DEGRADED_PWM_RESULT, HARDWARE_ERROR_RESULT, STATUS_RESULT } from "../support/canonical-results.ts";

class FakeClient {
  started = 0;
  disposed = 0;
  readonly calls: Array<{ operation: string; arguments: unknown; signal: AbortSignal }> = [];
  result: unknown = STATUS_RESULT;

  start(): void { this.started += 1; }
  async dispose(): Promise<void> { this.disposed += 1; }
  async invoke(operation: string, args: unknown, signal: AbortSignal): Promise<unknown> {
    this.calls.push({ operation, arguments: args, signal });
    if (this.result instanceof Error) throw this.result;
    return this.result;
  }
}

function simulatedPolicy(operation: string, args: unknown): HardwareToolPolicyContext {
  const values = typeof args === "object" && args !== null ? args as Record<string, unknown> : {};
  return createHardwareToolPolicyContext({
    operation,
    channel: typeof values.channel === "number" ? values.channel : null,
    backendMode: "SIMULATED",
    requestCorrelationId: "trusted-test-request",
    requestedGoal: "Test an explicitly invoked tool",
    requestedTargetRef: typeof values.context_id === "string" ? values.context_id : null,
    groundingRequired: false,
    wiringChanged: false,
    confirmation: null,
    previousExecution: null,
    designContext: null,
  });
}

async function setup(
  client: FakeClient,
  resolvePolicyContext: (operation: string, args: unknown) => HardwareToolPolicyContext = simulatedPolicy,
) {
  const ctx = new Context();
  await ctx.plugin(SystemPrompt);
  await ctx.plugin(ToolRuntime);
  applyWithDependencies(ctx, {}, { createClient: () => client, resolvePolicyContext });
  return ctx;
}

test("plugin identity and injection follow the reviewed Harness shape", () => {
  assert.equal(name, "aia-hardware-tools");
  assert.deepEqual(inject, ["tools", "systemPrompt"]);
});

test("apply registers exactly five projected static tools", async () => {
  const client = new FakeClient();
  const ctx = await setup(client);
  const schemas = ctx.tools.schemas();
  assert.deepEqual(schemas.map((item) => item.name).sort(), HARDWARE_TOOL_CONTRACTS.map((item) => item.harnessName).sort());
  for (const contract of HARDWARE_TOOL_CONTRACTS) {
    assert.deepEqual(ctx.tools.get(contract.harnessName)?.parameters, contract.parametersSchema);
    assert.deepEqual(ctx.tools.get(contract.harnessName)?.output.schema, contract.outputSchema);
    assert.equal(ctx.tools.get(contract.harnessName)?.isConcurrencySafe, undefined);
    assert.equal(ctx.tools.get(contract.harnessName)?.timeoutMs, undefined);
  }
  assert.equal(client.started, 1);
  await ctx.fiber.dispose();
  assert.equal(client.disposed, 1);
});

test("canonical ok=false remains a successful structured Tool value", async () => {
  const client = new FakeClient();
  client.result = HARDWARE_ERROR_RESULT;
  const ctx = await setup(client);
  const result = await ctx.tools.execute({
    signal: new AbortController().signal,
    callId: ToolCallId("phase7b4-error"),
    name: "hardware_measure_vpp",
    arguments: { channel: 1 },
  });
  assert.equal(result.isError, false);
  assert.deepEqual(result.value, HARDWARE_ERROR_RESULT);
  assert.equal(result.additionalContexts?.[0]?.source.kind, "plugin");
  assert.match(contextText(result.additionalContexts), /"executionStatus":"FAILED"/);
  assert.equal(client.calls[0]?.operation, "hardware.measure_vpp");
  await ctx.fiber.dispose();
});

test("degraded result and opaque artifact metadata are preserved without samples", async () => {
  const client = new FakeClient();
  client.result = DEGRADED_PWM_RESULT;
  const ctx = await setup(client);
  const result = await ctx.tools.execute({
    signal: new AbortController().signal,
    callId: ToolCallId("phase7b4-pwm"),
    name: "hardware_measure_pwm",
    arguments: { channel: 1, context_id: "PWM_OUT" },
  });
  assert.equal(result.isError, false);
  assert.deepEqual(result.value, DEGRADED_PWM_RESULT);
  assert.doesNotMatch(JSON.stringify(result.value), /"samples"/);
  assert.match(result.content[0]?.type === "text" ? result.content[0].text : "", /degraded/i);
  assert.match(result.content[0]?.type === "text" ? result.content[0].text : "", /550e8400/);
  assert.match(contextText(result.additionalContexts), /AIA_TEACHING_EVIDENCE_CONTEXT/);
  assert.match(contextText(result.additionalContexts), /"quality":"degraded"/);
  await ctx.fiber.dispose();
});

test("adapter failures become bounded Harness failures and tools remain registered", async () => {
  const client = new FakeClient();
  client.result = new AdapterFailure("backend_unreachable", "Hardware backend is unavailable.", "NOT_SENT");
  const ctx = await setup(client);
  const result = await ctx.tools.execute({
    signal: new AbortController().signal,
    callId: ToolCallId("phase7b4-offline"),
    name: "hardware_get_status",
    arguments: {},
  });
  assert.equal(result.isError, true);
  assert.match(result.error?.message ?? "", /backend is unavailable/i);
  assert.match(contextText(result.additionalContexts), /"executionStatus":"FAILED"/);
  assert.ok(ctx.tools.get("hardware_get_status"));
  await ctx.fiber.dispose();
});

test("projected argument validation reports invalid_tool_arguments before IPC", async () => {
  const invalidArguments = [
    { channel: 0 },
    { channel: 3 },
    { channel: "1" },
    { channel: 1, unexpected: true },
  ];
  for (const [index, args] of invalidArguments.entries()) {
    const client = new FakeClient();
    const ctx = await setup(client);
    const result = await ctx.tools.execute({
      signal: new AbortController().signal,
      callId: ToolCallId(`phase7b5-invalid-${index}`),
      name: "hardware_measure_frequency",
      arguments: args,
    });
    assert.equal(result.isError, true);
    assert.equal(result.error?.message, "Hardware tool arguments are invalid.");
    assert.doesNotMatch(result.error?.message ?? "", /ajv|schema|instancePath|keyword|SCPI|VISA|secret/i);
    assert.equal(client.calls.length, 0);
    await ctx.fiber.dispose();
  }
});

test("invalid_tool_arguments is a bounded NOT_SENT adapter failure", () => {
  const failure = safeAdapterFailure("invalid_tool_arguments", "NOT_SENT");
  assert.equal(failure.code, "invalid_tool_arguments");
  assert.equal(failure.deliveryState, "NOT_SENT");
  assert.equal(failure.message, "Hardware tool arguments are invalid.");
});

test("real measurement requiring confirmation causes zero IPC invocation", async () => {
  const client = new FakeClient();
  const ctx = await setup(client, (operation, args) => createHardwareToolPolicyContext({
    operation,
    channel: (args as { channel: number }).channel,
    backendMode: "REAL",
    requestCorrelationId: "real-request",
    requestedGoal: "Measure PWM",
    requestedTargetRef: "net:PWM_OUT",
    groundingRequired: true,
    wiringChanged: false,
    confirmation: null,
    previousExecution: null,
    designContext: null,
  }));
  const result = await ctx.tools.execute({
    signal: new AbortController().signal,
    callId: ToolCallId("phase7c2-confirmation-required"),
    name: "hardware_measure_pwm",
    arguments: { channel: 1, context_id: "PWM_OUT" },
  });
  assert.equal(result.isError, true);
  assert.equal(result.error?.message, "Physical setup confirmation is required before this hardware measurement.");
  assert.equal(client.calls.length, 0);
  await ctx.fiber.dispose();
});

test("confirmed allowed invocation reaches IPC exactly once", async () => {
  const client = new FakeClient();
  const confirmed = createProbeSetupConfirmation({
    confirmationId: "confirmation-1",
    source: "TRUSTED_USER_EVENT",
    confirmedBy: "user",
    channel: 1,
    targetRef: "net:PWM_OUT",
    safeLowVoltageConfirmed: true,
    commonGroundConfirmed: true,
    confirmedAt: "2026-09-08T09:00:00Z",
    scope: { requestCorrelationId: "real-request", workflowId: "workflow-1" },
  });
  const ctx = await setup(client, (operation, args) => createHardwareToolPolicyContext({
    operation,
    channel: (args as { channel: number }).channel,
    backendMode: "REAL",
    requestCorrelationId: "real-request",
    requestedGoal: "Measure PWM",
    requestedTargetRef: "net:PWM_OUT",
    groundingRequired: true,
    wiringChanged: false,
    confirmation: confirmed,
    previousExecution: null,
    designContext: null,
  }));
  await ctx.tools.execute({
    signal: new AbortController().signal,
    callId: ToolCallId("phase7c2-confirmed"),
    name: "hardware_measure_pwm",
    arguments: { channel: 1, context_id: "PWM_OUT" },
  });
  assert.equal(client.calls.length, 1);
  await ctx.fiber.dispose();
});

test("policy denial causes zero IPC invocation", async () => {
  const client = new FakeClient();
  const ctx = await setup(client, (operation, args) => ({
    ...simulatedPolicy(operation, args),
    backendMode: "REAL",
    confirmation: {
      confirmationId: "untrusted",
      source: "MODEL_TEXT",
      confirmedBy: "model",
      channel: 1,
      targetRef: null,
      safeLowVoltageConfirmed: true,
      commonGroundConfirmed: true,
      confirmedAt: "2026-09-08T09:00:00Z",
      scope: { requestCorrelationId: "trusted-test-request", workflowId: "workflow" },
    },
  } as unknown as HardwareToolPolicyContext));
  const result = await ctx.tools.execute({
    signal: new AbortController().signal,
    callId: ToolCallId("phase7c2-policy-denied"),
    name: "hardware_measure_frequency",
    arguments: { channel: 1 },
  });
  assert.equal(result.isError, true);
  assert.equal(result.error?.message, "Hardware tool request was denied by policy.");
  assert.equal(client.calls.length, 0);
  await ctx.fiber.dispose();
});

test("indeterminate prior execution is never replayed through the gate", async () => {
  const client = new FakeClient();
  const confirmed = createProbeSetupConfirmation({
    confirmationId: "confirmation-retry",
    source: "TRUSTED_USER_EVENT",
    confirmedBy: "user",
    channel: 1,
    targetRef: "PWM_OUT",
    safeLowVoltageConfirmed: true,
    commonGroundConfirmed: true,
    confirmedAt: "2026-09-08T09:00:00Z",
    scope: { requestCorrelationId: "PWM_OUT", workflowId: "workflow-retry" },
  });
  const ctx = await setup(client, (operation, args) => createHardwareToolPolicyContext({
    operation,
    channel: (args as { channel: number }).channel,
    backendMode: "REAL",
    requestCorrelationId: "PWM_OUT",
    requestedGoal: "Measure PWM again",
    requestedTargetRef: "PWM_OUT",
    groundingRequired: true,
    wiringChanged: false,
    confirmation: confirmed,
    previousExecution: {
      status: "INDETERMINATE_EXECUTION",
      operation,
      channel: 1,
      targetRef: "PWM_OUT",
      explicitRemeasureApproved: false,
    },
    designContext: null,
  }));
  const result = await ctx.tools.execute({
    signal: new AbortController().signal,
    callId: ToolCallId("phase7c2-no-replay"),
    name: "hardware_measure_pwm",
    arguments: { channel: 1, context_id: "PWM_OUT" },
  });
  assert.equal(result.isError, true);
  assert.equal(client.calls.length, 0);
  await ctx.fiber.dispose();
});

test("adapter failures expose no secret, local path, SCPI, or VISA detail", async () => {
  const client = new FakeClient();
  client.result = new AdapterFailure(
    "backend_response_invalid",
    "Hardware backend returned an invalid response.",
    "SENT_UNCONFIRMED",
  );
  const ctx = await setup(client);
  const result = await ctx.tools.execute({
    signal: new AbortController().signal,
    callId: ToolCallId("phase7b4-bounded-error"),
    name: "hardware_get_status",
    arguments: {},
  });
  assert.equal(result.isError, true);
  assert.doesNotMatch(result.error?.message ?? "", /secret|\.aia-secrets|[A-Za-z]:\\|SCPI|VISA/i);
  await ctx.fiber.dispose();
});

function contextText(contexts: readonly { readonly content: readonly unknown[] }[] | undefined): string {
  const block = contexts?.[0]?.content[0];
  return typeof block === "object" && block !== null && "type" in block && block.type === "text"
    && "text" in block && typeof block.text === "string"
    ? block.text
    : "";
}
