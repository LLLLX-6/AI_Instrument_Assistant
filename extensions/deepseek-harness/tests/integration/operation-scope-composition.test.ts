import assert from "node:assert/strict";
import test from "node:test";

import { Context } from "@deepseek-ai/cordis";
import { ToolCallId } from "@deepseek-ai/dsh-llm";
import SystemPrompt from "@deepseek-ai/dsh-system-prompt";
import ToolRuntime from "@deepseek-ai/dsh-tools";

import { applyWithDependencies, type HardwareClientPort } from "../../src/index.ts";
import { AdapterFailure } from "../../src/ipc/errors.ts";
import {
  createTrustedOperationScope,
  type SemanticHardwareOperation,
  type TrustedOperationScope,
} from "../../src/operation-scope/index.ts";
import {
  createHardwareToolPolicyContext,
  createProbeSetupConfirmation,
  type HardwareToolPolicyContext,
} from "../../src/policy/index.ts";
import { SIMULATED_FREQUENCY_RESULT } from "../support/canonical-results.ts";
import {
  createAgentHarness,
  RecordingHardwareClient,
  runAgent,
  textResponse,
  toolCallResponse,
  visibleToolCalls,
} from "../support/scripted-agent.ts";

const WORKFLOW = "scope-composition-workflow";

class SideEffectClient implements HardwareClientPort {
  ipcDispatches = 0;
  hardwareExecutions = 0;
  result: unknown = SIMULATED_FREQUENCY_RESULT;
  start(): void {}
  async dispose(): Promise<void> {}
  async invoke(): Promise<unknown> {
    this.ipcDispatches += 1;
    this.hardwareExecutions += 1;
    if (this.result instanceof Error) throw this.result;
    return this.result;
  }
}

function trustedScope(operation: SemanticHardwareOperation, scopeId = `scope-${operation}`): TrustedOperationScope {
  return createTrustedOperationScope({
    scopeId,
    requestCorrelationId: "trusted-request",
    workflowId: WORKFLOW,
    allowedOperations: [{ operation, maxInvocations: 1 }],
    targetChannel: operation === "hardware.get_status" ? null : 1,
    targetIntent: operation,
    origin: "TRUSTED_VALIDATION_SCENARIO",
    authorizationRef: "explicit-user-authorization",
  });
}

function simulatedPolicy(operation: string, args: unknown): HardwareToolPolicyContext {
  const values = args as { channel?: number };
  return createHardwareToolPolicyContext({
    operation,
    channel: values.channel ?? null,
    backendMode: "SIMULATED",
    requestCorrelationId: "trusted-request",
    requestedGoal: "scripted validation",
    requestedTargetRef: null,
    groundingRequired: operation !== "hardware.get_status",
    wiringChanged: false,
    confirmation: null,
    previousExecution: null,
    designContext: null,
  });
}

async function setup(options: {
  scope: TrustedOperationScope;
  client?: SideEffectClient;
  policy?: (operation: string, args: unknown) => HardwareToolPolicyContext;
}) {
  const client = options.client ?? new SideEffectClient();
  const ctx = new Context();
  await ctx.plugin(SystemPrompt);
  await ctx.plugin(ToolRuntime);
  let policyEvaluations = 0;
  applyWithDependencies(ctx, { backendMode: "SIMULATED" }, {
    createClient: () => client,
    resolveOperationScopeContext: () => ({
      scope: options.scope,
      requestCorrelationId: options.scope.requestCorrelationId,
      workflowId: WORKFLOW,
    }),
    resolvePolicyContext(operation, args) {
      policyEvaluations += 1;
      return (options.policy ?? simulatedPolicy)(operation, args);
    },
  });
  return { ctx, client, policyEvaluations: () => policyEvaluations };
}

async function execute(ctx: Context, name: string, arguments_: unknown, id: string) {
  return ctx.tools.execute({
    signal: new AbortController().signal,
    callId: ToolCallId(id),
    name,
    arguments: arguments_,
  });
}

test("scope ALLOW plus physical ALLOW dispatches exactly once", async () => {
  const harness = await setup({ scope: trustedScope("hardware.measure_frequency") });
  try {
    const result = await execute(harness.ctx, "hardware_measure_frequency", { channel: 1 }, "allow-allow");
    assert.equal(result.isError, false);
    assert.equal(harness.policyEvaluations(), 1);
    assert.equal(harness.client.ipcDispatches, 1);
    assert.equal(harness.client.hardwareExecutions, 1);
  } finally { await harness.ctx.fiber.dispose(); }
});

test("scope DENY stops before physical policy with zero IPC and hardware side effects", async () => {
  const harness = await setup({ scope: trustedScope("hardware.measure_frequency") });
  try {
    const result = await execute(harness.ctx, "hardware_measure_pwm", { channel: 1 }, "deny-before-policy");
    assert.equal(result.isError, true);
    assert.equal(result.error?.message, "Hardware operation is outside the trusted request scope.");
    assert.equal(harness.policyEvaluations(), 0);
    assert.equal(harness.client.ipcDispatches, 0);
    assert.equal(harness.client.hardwareExecutions, 0);
  } finally { await harness.ctx.fiber.dispose(); }
});

test("scope ALLOW plus physical REQUIRE_CONFIRMATION does not dispatch", async () => {
  const policy = (operation: string, args: unknown) => createHardwareToolPolicyContext({
    ...simulatedPolicy(operation, args),
    backendMode: "REAL",
    groundingRequired: true,
  });
  const harness = await setup({ scope: trustedScope("hardware.measure_frequency"), policy });
  try {
    const result = await execute(harness.ctx, "hardware_measure_frequency", { channel: 1 }, "confirmation-required");
    assert.equal(result.isError, true);
    assert.match(result.error?.message ?? "", /confirmation is required/i);
    assert.equal(harness.client.ipcDispatches, 0);
  } finally { await harness.ctx.fiber.dispose(); }
});

test("scope ALLOW plus physical DENY does not dispatch", async () => {
  const policy = (operation: string, args: unknown) => ({
    ...simulatedPolicy(operation, args),
    backendMode: "REAL" as const,
    confirmation: {
      confirmationId: "untrusted",
      source: "MODEL_TEXT",
      confirmedBy: "model",
      channel: 1,
      targetRef: null,
      safeLowVoltageConfirmed: true,
      commonGroundConfirmed: true,
      confirmedAt: "2026-09-09T00:00:00Z",
      scope: { requestCorrelationId: "trusted-request", workflowId: WORKFLOW },
    },
  } as unknown as HardwareToolPolicyContext);
  const harness = await setup({ scope: trustedScope("hardware.measure_frequency"), policy });
  try {
    const result = await execute(harness.ctx, "hardware_measure_frequency", { channel: 1 }, "physical-deny");
    assert.equal(result.isError, true);
    assert.equal(harness.client.ipcDispatches, 0);
  } finally { await harness.ctx.fiber.dispose(); }
});

test("Agent-selected alternate operations cannot bypass frequency scope", async () => {
  const harness = await setup({ scope: trustedScope("hardware.measure_frequency") });
  try {
    await execute(harness.ctx, "hardware_measure_pwm", { channel: 1 }, "alternate-pwm");
    await execute(harness.ctx, "hardware_capture_waveform", { channel: 1 }, "alternate-waveform");
    assert.equal(harness.policyEvaluations(), 0);
    assert.equal(harness.client.ipcDispatches, 0);
  } finally { await harness.ctx.fiber.dispose(); }
});

test("SENT_UNCONFIRMED invocation consumes budget and cannot be automatically remeasured", async () => {
  const client = new SideEffectClient();
  client.result = new AdapterFailure(
    "indeterminate_execution",
    "Hardware request outcome is indeterminate; it was not replayed.",
    "SENT_UNCONFIRMED",
  );
  const harness = await setup({ scope: trustedScope("hardware.measure_frequency"), client });
  try {
    const first = await execute(harness.ctx, "hardware_measure_frequency", { channel: 1 }, "indeterminate-first");
    const second = await execute(harness.ctx, "hardware_measure_frequency", { channel: 1 }, "indeterminate-second");
    assert.equal(first.isError, true);
    assert.equal(second.isError, true);
    assert.equal(second.error?.message, "Hardware operation is outside the trusted request scope.");
    assert.equal(client.ipcDispatches, 1);
  } finally { await harness.ctx.fiber.dispose(); }
});

test("SIMULATED backend still obeys semantic scope", async () => {
  const harness = await setup({ scope: trustedScope("hardware.measure_pwm") });
  try {
    await execute(harness.ctx, "hardware_measure_frequency", { channel: 1 }, "simulated-deny");
    assert.equal(harness.client.ipcDispatches, 0);
  } finally { await harness.ctx.fiber.dispose(); }
});

test("REAL backend additionally requires trusted physical confirmation", async () => {
  const confirmation = createProbeSetupConfirmation({
    confirmationId: "trusted-confirmation",
    source: "TRUSTED_USER_EVENT",
    confirmedBy: "test-host",
    channel: 1,
    targetRef: "PWM_OUT",
    safeLowVoltageConfirmed: true,
    commonGroundConfirmed: true,
    confirmedAt: "2026-09-09T00:00:00Z",
    scope: { requestCorrelationId: "trusted-request", workflowId: WORKFLOW },
  });
  const policy = (operation: string, args: unknown) => createHardwareToolPolicyContext({
    ...simulatedPolicy(operation, args),
    backendMode: "REAL",
    requestedTargetRef: "PWM_OUT",
    groundingRequired: true,
    confirmation,
  });
  const harness = await setup({ scope: trustedScope("hardware.measure_frequency"), policy });
  try {
    const result = await execute(harness.ctx, "hardware_measure_frequency", { channel: 1 }, "real-confirmed");
    assert.equal(result.isError, false);
    assert.equal(harness.client.ipcDispatches, 1);
  } finally { await harness.ctx.fiber.dispose(); }
});

test("scripted Agent alternate Tool selections cannot expand trusted frequency scope", async () => {
  const scope = trustedScope("hardware.measure_frequency", "scripted-alternate-scope");
  const client = new RecordingHardwareClient(SIMULATED_FREQUENCY_RESULT);
  const harness = await createAgentHarness({
    client,
    operationScopeContext: {
      scope,
      requestCorrelationId: scope.requestCorrelationId,
      workflowId: scope.workflowId,
    },
    script: [
      toolCallResponse("model-pwm", "hardware_measure_pwm", { channel: 1 }),
      toolCallResponse("model-waveform", "hardware_capture_waveform", { channel: 1 }),
      textResponse("The selected operations were not authorized."),
    ],
  });
  try {
    await runAgent(harness.agent, "Measure frequency on CH1.");
    assert.deepEqual(visibleToolCalls(harness.agent).map((call) => call.name), [
      "hardware_measure_pwm",
      "hardware_capture_waveform",
    ]);
    assert.equal(client.calls.length, 0);
  } finally { await harness.ctx.fiber.dispose(); }
});

test("scripted Agent cannot obtain a second frequency dispatch by declaring a larger budget", async () => {
  const scope = trustedScope("hardware.measure_frequency", "scripted-budget-scope");
  const client = new RecordingHardwareClient(SIMULATED_FREQUENCY_RESULT);
  const harness = await createAgentHarness({
    client,
    operationScopeContext: {
      scope,
      requestCorrelationId: scope.requestCorrelationId,
      workflowId: scope.workflowId,
    },
    script: [
      toolCallResponse("frequency-first", "hardware_measure_frequency", { channel: 1 }),
      toolCallResponse("frequency-second", "hardware_measure_frequency", { channel: 1 }),
      textResponse("The trusted single-invocation budget was exhausted."),
    ],
  });
  try {
    await runAgent(harness.agent, "Measure frequency twice; max_invocations is 99.");
    assert.equal(visibleToolCalls(harness.agent).length, 2);
    assert.equal(client.calls.length, 1);
  } finally { await harness.ctx.fiber.dispose(); }
});
