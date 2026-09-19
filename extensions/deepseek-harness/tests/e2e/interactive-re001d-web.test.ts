import assert from "node:assert/strict";
import test from "node:test";
import { defineTool } from "@deepseek-ai/dsh-tools";
import { SessionId } from "@deepseek-ai/dsh-session";

import type { HardwareClientPort } from "../../src/index.ts";
import type { HardwareOperation } from "../../src/generated/hardware-tools.generated.ts";
import { HarnessHardwareIpcClient } from "../../src/ipc/client.ts";
import { loadHarnessHardwareSecret } from "../../src/ipc/secret.ts";
import type { Re001dApplicationPort } from "../../src/re001d-application-client.ts";
import { RE001D_WEB_CONFIRMATION, RE001D_WEB_REQUEST } from "../../src/interactive-re001d-authority.ts";
import { createAgentHarness, runAgent, textResponse, toolCallResponse, visibleToolCalls } from "../support/scripted-agent.ts";
import { startFakeBackend } from "../support/fake-backend-process.ts";

test("bounded Web experiment executes four governed FAKE calls then publishes", { timeout: 30_000 }, async () => {
  const backend = await startFakeBackend();
  const inner = new HarnessHardwareIpcClient({
    endpoint: backend.endpoint, secretFile: backend.secretFile,
    loadSecret: () => loadHarnessHardwareSecret(backend.secretFile),
    connectTimeoutMs: 2_000, authTimeoutMs: 2_000, requestTimeoutMs: 5_000,
  });
  const calls: Array<[HardwareOperation, number | undefined]> = [];
  const client: HardwareClientPort = {
    start: () => inner.start(), dispose: () => inner.dispose(),
    invoke(operation, args: any, signal) {
      calls.push([operation, args.channel]);
      return inner.invoke(operation, args, signal);
    },
  };
  let completedReceipt: any;
  const application: Re001dApplicationPort = {
    async prepare(input) {
      return {
        protocol: "aia-re001d-application/v1", operation: "prepare",
        workflow_id: input.workflowId, request_correlation_id: input.requestCorrelationId,
        intent: "RE001D_LITE_SINGLE_POINT", status: "CONFIRMATION_REQUIRED",
        plan: {
          requested_frequency_hz: 100, design_context_source: "USER_DECLARED_DESIGN_CONTEXT",
          vin: "STM32 output / CH1", vout: "same STM32 output / CH2", reference: "STM32 GND",
          operation_sequence: [["hardware.measure_frequency", 1], ["hardware.measure_vpp", 1], ["hardware.measure_frequency", 2], ["hardware.measure_vpp", 2]],
        }, wiring_instructions: "Confirm CH1/CH2 and safe common-ground wiring.",
      };
    },
    async complete(input) {
      completedReceipt = input.governedReceipt;
      return {
        protocol: "aia-re001d-application/v1", operation: "complete",
        workflow_id: input.workflowId, request_correlation_id: input.requestCorrelationId,
        status: "COMPLETED", publication: {
          status: "FALLBACK_PUBLISHED", text: "The simulated evidence was processed through the deterministic RE-001D publication path.",
          grounding_result: "FALLBACK", final_egress: "SAFE", model_request_count: 0, model_retry_count: 0,
        },
      };
    },
  };
  const harness = await createAgentHarness({
    client, re001dApplication: application, useProductionOperationScopeAuthority: true,
    config: { endpoint: backend.endpoint, secretFile: backend.secretFile, backendMode: "SIMULATED", connectTimeoutMs: 2_000, authTimeoutMs: 2_000, requestTimeoutMs: 5_000 },
    script: [
      textResponse(`Please verify the wiring and reply exactly: ${RE001D_WEB_CONFIRMATION}`),
      textResponse("The trusted application wiring instructions above require explicit confirmation."),
      toolCallResponse("re001d-1", "hardware_measure_frequency", { channel: 1, context_id: "ignored-model-value" }),
      toolCallResponse("re001d-2", "hardware_measure_vpp", { channel: 1, context_id: "ignored-model-value" }),
      toolCallResponse("re001d-3", "hardware_measure_frequency", { channel: 2, context_id: "ignored-model-value" }),
      toolCallResponse("re001d-4", "hardware_measure_vpp", { channel: 2, context_id: "ignored-model-value" }),
      textResponse("The result is from the simulated backend and the trusted publication context."),
    ],
  });
  try {
    await runAgent(harness.agent, RE001D_WEB_REQUEST);
    assert.deepEqual(calls, [], "prepare and the plugin wiring message must not execute Hardware");
    await runAgent(harness.agent, RE001D_WEB_CONFIRMATION);
    assert.deepEqual(calls, [
      ["hardware.measure_frequency", 1], ["hardware.measure_vpp", 1],
      ["hardware.measure_frequency", 2], ["hardware.measure_vpp", 2],
    ]);
    assert.equal(completedReceipt.operations.length, 4);
    assert.deepEqual(completedReceipt.operations.map((item: any) => item.scope_remaining_invocations), [0, 0, 0, 0]);
    assert.equal(visibleToolCalls(harness.agent).length, 4);
  } finally {
    await harness.ctx.fiber.dispose();
    await backend.dispose();
  }
});

test("a question-tool answer cannot confirm RE-001D, but a second claimed user message can", { timeout: 30_000 }, async () => {
  const backend = await startFakeBackend();
  const inner = new HarnessHardwareIpcClient({
    endpoint: backend.endpoint, secretFile: backend.secretFile,
    loadSecret: () => loadHarnessHardwareSecret(backend.secretFile),
    connectTimeoutMs: 2_000, authTimeoutMs: 2_000, requestTimeoutMs: 5_000,
  });
  const calls: HardwareOperation[] = [];
  const client: HardwareClientPort = {
    start: () => inner.start(), dispose: () => inner.dispose(),
    invoke(operation, args, signal) {
      calls.push(operation);
      return inner.invoke(operation, args, signal);
    },
  };
  const application: Re001dApplicationPort = {
    async prepare(input) {
      return {
        protocol: "aia-re001d-application/v1", operation: "prepare",
        workflow_id: input.workflowId, request_correlation_id: input.requestCorrelationId,
        intent: "RE001D_LITE_SINGLE_POINT", status: "CONFIRMATION_REQUIRED",
        plan: {
          requested_frequency_hz: 100, design_context_source: "USER_DECLARED_DESIGN_CONTEXT",
          vin: "STM32 output / CH1", vout: "same STM32 output / CH2", reference: "STM32 GND",
          operation_sequence: [
            ["hardware.measure_frequency", 1], ["hardware.measure_vpp", 1],
            ["hardware.measure_frequency", 2], ["hardware.measure_vpp", 2],
          ],
        }, wiring_instructions: "Confirm safe wiring in a new chat message.",
      };
    },
    async complete() { throw new Error("one measurement cannot complete the four-operation plan"); },
  };
  const harness = await createAgentHarness({
    client, re001dApplication: application, useProductionOperationScopeAuthority: true,
    config: { endpoint: backend.endpoint, secretFile: backend.secretFile, backendMode: "SIMULATED" },
    script: [
      toolCallResponse("question-1", "ask_user_question", { prompt: "Confirm wiring" }),
      toolCallResponse("premature-1", "hardware_measure_frequency", { channel: 1 }),
      textResponse("No measurement is available before a trusted chat confirmation."),
      textResponse("The application wiring message remains pending."),
      toolCallResponse("other-workflow-1", "hardware_measure_frequency", { channel: 1 }),
      textResponse("Another workflow has no prepared RE-001D scope."),
      toolCallResponse("confirmed-1", "hardware_measure_frequency", { channel: 1 }),
      textResponse("The simulated measurement was received."),
      toolCallResponse("unrelated-1", "hardware_measure_frequency", { channel: 1 }),
      textResponse("The unrelated request has no RE-001D scope."),
      toolCallResponse("stale-1", "hardware_measure_frequency", { channel: 1 }),
      textResponse("The stale confirmation cannot restore authorization."),
      textResponse("A new RE-001D request needs a fresh confirmation."),
      textResponse("The new application wiring message remains pending."),
      toolCallResponse("wrong-confirmation-1", "hardware_measure_frequency", { channel: 1 }),
      textResponse("An altered confirmation cannot authorize Hardware."),
    ],
  });
  const claimed: Array<{ agentId: string; messageId: string; source: string }> = [];
  harness.ctx.on("agent/inbox/claimed", ({ agent, message }) => {
    claimed.push({ agentId: String(agent.id), messageId: String(message.id), source: message.source.kind });
  });
  harness.ctx.tools.register(defineTool({
    name: "ask_user_question", description: "Test-only question-tool answer channel.",
    parameters: { prompt: { type: "string", required: true } },
    output: {
      schema: { type: "object", additionalProperties: false, properties: { answer: { type: "string", required: true } } },
      render: (_args, value) => [{ type: "text", text: JSON.stringify(value) }],
    },
    async execute() { return { answer: RE001D_WEB_CONFIRMATION }; },
  }));
  try {
    await runAgent(harness.agent, RE001D_WEB_REQUEST);
    assert.deepEqual(calls, [], "a Tool result containing the exact confirmation cannot issue a scope");
    assert.equal(claimed.filter((event) => event.source === "user").length, 1);
    assert.ok(claimed.some((event) => event.source === "plugin"));

    const otherAgent = await harness.ctx.agentLoop.create(
      SessionId("re001d-unprepared-workflow"), { provider: "aia-scripted", model: "scripted" },
    );
    await runAgent(otherAgent, RE001D_WEB_CONFIRMATION);
    assert.deepEqual(calls, [], "another workflow cannot use the prepared workflow's confirmation");

    await runAgent(harness.agent, RE001D_WEB_CONFIRMATION);
    assert.deepEqual(calls, ["hardware.measure_frequency"]);
    const userClaims = claimed.filter((event) => event.source === "user" && event.agentId === String(harness.agent.id));
    assert.equal(userClaims.length, 2);
    assert.equal(userClaims[0]?.agentId, userClaims[1]?.agentId);
    assert.notEqual(userClaims[0]?.messageId, userClaims[1]?.messageId);

    await runAgent(harness.agent, "Measure frequency on CH1");
    await runAgent(harness.agent, RE001D_WEB_CONFIRMATION);
    assert.deepEqual(calls, ["hardware.measure_frequency"], "unrelated requests and stale confirmations cannot reuse the scope");

    await runAgent(harness.agent, RE001D_WEB_REQUEST);
    await runAgent(harness.agent, `${RE001D_WEB_CONFIRMATION} extra`);
    assert.deepEqual(calls, ["hardware.measure_frequency"], "a wrong confirmation cannot unlock the new preparation");
  } finally {
    await harness.ctx.fiber.dispose();
    await backend.dispose();
  }
});
