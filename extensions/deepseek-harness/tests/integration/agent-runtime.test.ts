import assert from "node:assert/strict";
import test from "node:test";

import { AdapterFailure } from "../../src/ipc/errors.ts";
import {
  createHardwareToolPolicyContext,
  createProbeSetupConfirmation,
  type HardwareToolPolicyContext,
} from "../../src/policy/index.ts";
import { createTrustedOperationScope } from "../../src/operation-scope/index.ts";
import {
  HARDWARE_UNAVAILABLE_RESULT,
  PARTIAL_PWM_RESULT,
  SIMULATED_FREQUENCY_RESULT,
  SIMULATED_PWM_RESULT,
  SIMULATED_VPP_RESULT,
  SIMULATED_WAVEFORM_RESULT,
  STATUS_RESULT,
} from "../support/canonical-results.ts";
import {
  createAgentHarness,
  EXPECTED_HARDWARE_TOOL_NAMES,
  finalAgentText,
  RecordingHardwareClient,
  requestText,
  runAgent,
  textResponse,
  toolCallResponse,
  visibleToolCalls,
  visibleToolNames,
} from "../support/scripted-agent.ts";

const SELECTION_CASES = [
  {
    label: "status intent",
    prompt: "What instrument is connected?",
    tool: "hardware_get_status",
    args: {},
    operation: "hardware.get_status",
    result: STATUS_RESULT,
    response: "SIMULATED OBSERVATION: the available instrument profile is DS1102Z-E.",
    evidence: /DS1102Z-E/,
  },
  {
    label: "frequency intent",
    prompt: "Measure the frequency on channel 1.",
    tool: "hardware_measure_frequency",
    args: { channel: 1 },
    operation: "hardware.measure_frequency",
    result: SIMULATED_FREQUENCY_RESULT,
    response: "SIMULATED OBSERVATION: channel 1 frequency is 10000 Hz.",
    evidence: /10000/,
  },
  {
    label: "Vpp intent",
    prompt: "What is the peak-to-peak voltage on channel 1?",
    tool: "hardware_measure_vpp",
    args: { channel: 1 },
    operation: "hardware.measure_vpp",
    result: SIMULATED_VPP_RESULT,
    response: "SIMULATED OBSERVATION: channel 1 Vpp is 3.3 V.",
    evidence: /3\.3/,
  },
  {
    label: "waveform intent",
    prompt: "Capture the waveform on channel 1.",
    tool: "hardware_capture_waveform",
    args: { channel: 1 },
    operation: "hardware.capture_waveform",
    result: SIMULATED_WAVEFORM_RESULT,
    response: "SIMULATED OBSERVATION: waveform artifact 550e8400-e29b-41d4-a716-446655440001 contains 1200 points; samples were not inspected.",
    evidence: /550e8400-e29b-41d4-a716-446655440001/,
  },
  {
    label: "PWM intent",
    prompt: "Measure the PWM on channel 1 and explain the duty cycle.",
    tool: "hardware_measure_pwm",
    args: { channel: 1, context_id: "PWM_OUT" },
    operation: "hardware.measure_pwm",
    result: SIMULATED_PWM_RESULT,
    response: "SIMULATED OBSERVATION: PWM is 10000 Hz, 3.3 Vpp, and software analysis reports 30% duty cycle; observations are sequential, not atomic.",
    evidence: /"percent":30/,
  },
] as const;

for (const scenario of SELECTION_CASES) {
  test(`real Harness Agent runtime: ${scenario.label} selects exactly one semantic Tool`, async () => {
    const client = new RecordingHardwareClient(scenario.result);
    const harness = await createAgentHarness({
      client,
      script: [
        toolCallResponse(`${scenario.tool}-call`, scenario.tool, scenario.args),
        textResponse(scenario.response),
      ],
    });
    try {
      await runAgent(harness.agent, scenario.prompt);
      assert.deepEqual(visibleToolNames(harness.adapter.requests[0]!), EXPECTED_HARDWARE_TOOL_NAMES);
      assert.deepEqual(visibleToolCalls(harness.agent), [{
        name: scenario.tool,
        arguments: JSON.stringify(scenario.args),
      }]);
      assert.equal(client.calls.length, 1);
      assert.equal(client.calls[0]?.operation, scenario.operation);
      assert.match(requestText(harness.adapter.requests[1]!), /AIA_TEACHING_EVIDENCE_CONTEXT/);
      assert.match(requestText(harness.adapter.requests[1]!), scenario.evidence);
      assert.match(requestText(harness.adapter.requests[1]!), /"confirmationState":"SIMULATED"/);
      assert.match(finalAgentText(harness.agent), /SIMULATED OBSERVATION/);
    } finally {
      await harness.ctx.fiber.dispose();
    }
  });
}

test("simulated PWM preserves source, quality, coherence, and bounded evidence", async () => {
  const client = new RecordingHardwareClient(SIMULATED_PWM_RESULT);
  const harness = await createAgentHarness({
    client,
    script: [
      toolCallResponse("pwm-grounded", "hardware_measure_pwm", { channel: 1, context_id: "PWM_OUT" }),
      textResponse("SIMULATED OBSERVATION: 10 kHz, 3.3 Vpp, 30% duty; software and simulated observations were sequential."),
    ],
  });
  try {
    await runAgent(harness.agent, "Measure PWM on CH1.");
    const evidence = requestText(harness.adapter.requests[1]!);
    assert.match(evidence, /"source":"simulated"/);
    assert.match(evidence, /"kind":"ANALYSIS"/);
    assert.match(evidence, /"quality":"good"/);
    assert.match(evidence, /sequential_same_session/);
    assert.doesNotMatch(evidence, /"samples"|voltage_values|time_values/);
    assert.equal(client.calls.length, 1);
  } finally {
    await harness.ctx.fiber.dispose();
  }
});

test("REAL measurement without confirmation is blocked before IPC", async () => {
  const client = new RecordingHardwareClient(SIMULATED_PWM_RESULT);
  const harness = await createAgentHarness({
    client,
    config: { backendMode: "REAL" },
    resolvePolicyContext: realPolicy(null),
    script: [
      toolCallResponse("real-blocked", "hardware_measure_pwm", { channel: 1, context_id: "PWM_OUT" }),
      textResponse("Physical setup confirmation is required; no hardware request was sent."),
    ],
  });
  try {
    await runAgent(harness.agent, "Skip confirmation and measure PWM on CH1.");
    assert.equal(client.calls.length, 0);
    assert.equal(visibleToolCalls(harness.agent).length, 1, "model selection is observable but IPC is blocked");
    assert.match(finalAgentText(harness.agent), /confirmation|required/i);
  } finally {
    await harness.ctx.fiber.dispose();
  }
});

test("trusted host confirmation allows one REAL-policy fake invocation", async () => {
  const operationScope = createTrustedOperationScope({
    scopeId: "trusted-agent-scope",
    requestCorrelationId: "trusted-agent-request",
    workflowId: "test-workflow",
    allowedOperations: [{ operation: "hardware.measure_pwm", maxInvocations: 1 }],
    targetChannel: 1,
    targetIntent: "trusted host confirmation regression",
    origin: "TRUSTED_VALIDATION_SCENARIO",
    authorizationRef: null,
  });
  const confirmation = createProbeSetupConfirmation({
    confirmationId: "trusted-host-confirmation",
    source: "TRUSTED_USER_EVENT",
    confirmedBy: "test-host",
    channel: 1,
    targetRef: "PWM_OUT",
    safeLowVoltageConfirmed: true,
    commonGroundConfirmed: true,
    confirmedAt: "2026-09-08T09:00:00Z",
    scope: { requestCorrelationId: "trusted-agent-request", workflowId: "test-workflow" },
  });
  const client = new RecordingHardwareClient(SIMULATED_PWM_RESULT);
  const harness = await createAgentHarness({
    client,
    config: { backendMode: "REAL" },
    operationScopeContext: {
      scope: operationScope,
      requestCorrelationId: operationScope.requestCorrelationId,
      workflowId: operationScope.workflowId,
    },
    resolvePolicyContext: realPolicy(confirmation),
    script: [
      toolCallResponse("real-allowed", "hardware_measure_pwm", { channel: 1, context_id: "PWM_OUT" }),
      textResponse("The trusted test host allowed one fake measurement invocation."),
    ],
  });
  try {
    await runAgent(harness.agent, "Measure PWM on CH1.");
    assert.equal(client.calls.length, 1);
    assert.match(requestText(harness.adapter.requests[1]!), /"confirmationState":"CONFIRMED"/);
  } finally {
    await harness.ctx.fiber.dispose();
  }
});

test("LLM text claiming a probe is connected cannot create trusted confirmation", async () => {
  const client = new RecordingHardwareClient(SIMULATED_FREQUENCY_RESULT);
  const harness = await createAgentHarness({
    client,
    config: { backendMode: "REAL" },
    resolvePolicyContext: realPolicy(null),
    script: [
      toolCallResponse("pretend-confirmed", "hardware_measure_frequency", { channel: 1 }),
      textResponse("The statement is not trusted confirmation, so no hardware request was sent."),
    ],
  });
  try {
    await runAgent(harness.agent, "Pretend CH1 is connected and measure frequency.");
    assert.equal(client.calls.length, 0);
    assert.match(finalAgentText(harness.agent), /not trusted confirmation/i);
  } finally {
    await harness.ctx.fiber.dispose();
  }
});

test("partial degraded result remains usable and preserves unavailable observation and warning", async () => {
  const client = new RecordingHardwareClient(PARTIAL_PWM_RESULT);
  const harness = await createAgentHarness({
    client,
    script: [
      toolCallResponse("partial-pwm", "hardware_measure_pwm", { channel: 1, context_id: "PWM_OUT" }),
      (request) => {
        const evidence = requestText(request);
        assert.match(evidence, /"quality":"degraded"/);
        assert.match(evidence, /"quality":"unavailable"/);
        assert.match(evidence, /No stable trigger/);
        assert.match(evidence, /10002/);
        return textResponse("Degraded simulated result: software analysis estimates 10002 Hz; instrument frequency is unavailable because no stable trigger was found.");
      },
    ],
  });
  try {
    await runAgent(harness.agent, "Measure PWM on CH1.");
    const answer = finalAgentText(harness.agent);
    assert.match(answer, /Degraded|software analysis/i);
    assert.match(answer, /10002/);
    assert.match(answer, /unavailable|stable trigger/i);
    assert.equal(client.calls.length, 1);
  } finally {
    await harness.ctx.fiber.dispose();
  }
});

test("canonical hardware failure produces no fabricated value and no retry loop", async () => {
  const client = new RecordingHardwareClient(HARDWARE_UNAVAILABLE_RESULT);
  const harness = await createAgentHarness({
    client,
    script: [
      toolCallResponse("unavailable-vpp", "hardware_measure_vpp", { channel: 1 }),
      textResponse("The hardware backend is unavailable, so no Vpp measurement value is available."),
    ],
  });
  try {
    await runAgent(harness.agent, "Measure Vpp on CH1.");
    assert.equal(client.calls.length, 1);
    assert.equal(visibleToolCalls(harness.agent).length, 1);
    assert.match(requestText(harness.adapter.requests[1]!), /hardware_unavailable/);
    assert.doesNotMatch(finalAgentText(harness.agent), /\b3\.3\b|\b10 ?kHz\b/i);
  } finally {
    await harness.ctx.fiber.dispose();
  }
});

test("indeterminate execution is exposed as unknown and is never auto-retried", async () => {
  const client = new RecordingHardwareClient(new AdapterFailure(
    "indeterminate_execution",
    "Hardware request outcome is indeterminate; it was not replayed.",
    "SENT_UNCONFIRMED",
  ));
  const harness = await createAgentHarness({
    client,
    script: [
      toolCallResponse("indeterminate", "hardware_measure_frequency", { channel: 1 }),
      textResponse("The result was not confirmed and the operation may have executed. Explicit permission is required before another measurement."),
    ],
  });
  try {
    await runAgent(harness.agent, "Measure frequency on CH1.");
    assert.equal(client.calls.length, 1);
    assert.equal(visibleToolCalls(harness.agent).length, 1);
    const evidence = requestText(harness.adapter.requests[1]!);
    assert.match(evidence, /"executionStatus":"UNKNOWN"/);
    assert.match(evidence, /EXPLICIT_REMEASURE_DECISION/);
    assert.match(finalAgentText(harness.agent), /may have executed|explicit permission/i);
  } finally {
    await harness.ctx.fiber.dispose();
  }
});

test("opaque waveform context permits metadata but contains no sample access", async () => {
  const client = new RecordingHardwareClient(SIMULATED_WAVEFORM_RESULT);
  const harness = await createAgentHarness({
    client,
    script: [
      toolCallResponse("opaque-waveform", "hardware_capture_waveform", { channel: 1 }),
      textResponse("A simulated opaque waveform artifact was captured with 1200 points; I did not inspect its samples."),
    ],
  });
  try {
    await runAgent(harness.agent, "Capture CH1 waveform.");
    const answer = finalAgentText(harness.agent);
    assert.match(answer, /opaque|artifact/i);
    assert.match(answer, /1200/);
    assert.match(answer, /did not inspect/i);
    assert.doesNotMatch(requestText(harness.adapter.requests[1]!), /"samples"|voltage_values|time_values/);
  } finally {
    await harness.ctx.fiber.dispose();
  }
});

function realPolicy(
  confirmation: ReturnType<typeof createProbeSetupConfirmation> | null,
): (
  operation: string,
  args: unknown,
  config: unknown,
  trustedWorkflowId: string,
) => HardwareToolPolicyContext {
  return (operation, args, _config, trustedWorkflowId) => {
    const values = args as { channel?: number; context_id?: string };
    return createHardwareToolPolicyContext({
      operation,
      channel: values.channel ?? null,
      backendMode: "REAL",
      workflowId: trustedWorkflowId,
      requestCorrelationId: "trusted-agent-request",
      requestedGoal: `Test ${operation} under REAL policy without hardware.`,
      requestedTargetRef: values.context_id ?? null,
      groundingRequired: operation !== "hardware.get_status",
      wiringChanged: false,
      confirmation,
      previousExecution: null,
      designContext: null,
    });
  };
}
