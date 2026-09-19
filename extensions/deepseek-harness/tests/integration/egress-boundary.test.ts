import assert from "node:assert/strict";
import test from "node:test";

import { SIMULATED_FREQUENCY_RESULT } from "../support/canonical-results.ts";
import {
  createAgentHarness,
  finalAgentText,
  RecordingHardwareClient,
  runAgent,
  textResponse,
  toolCallResponse,
  visibleToolCalls,
} from "../support/scripted-agent.ts";

test("unsafe final response is replaced before the durable Agent surface without retry or remeasurement", async () => {
  const client = new RecordingHardwareClient(SIMULATED_FREQUENCY_RESULT);
  const diagnostics: Array<{ category: string; source: string }> = [];
  const harness = await createAgentHarness({
    client,
    onEgressDiagnostic: ({ category, source }) => { diagnostics.push({ category, source }); },
    script: [
      toolCallResponse("safe-call", "hardware_measure_frequency", { channel: 1 }),
      textResponse("Measurement is in C:\\Users\\operator\\capture.txt"),
    ],
  });
  try {
    await runAgent(harness.agent, "Measure frequency on CH1.");
    const text = finalAgentText(harness.agent);
    assert.equal(client.calls.length, 1, "fallback must not remeasure");
    assert.equal(harness.adapter.requests.length, 2, "fallback must not retry the model");
    assert.equal(visibleToolCalls(harness.agent).length, 1, "fallback must not append a new Tool call");
    assert.doesNotMatch(text, /C:\\|operator|capture\.txt/);
    assert.match(text, /Measurement completed\./);
    assert.match(text, /FACT:/);
    assert.doesNotMatch(JSON.stringify(harness.agent.session.snapshotEvents()), /operator|capture\.txt/);
    assert.deepEqual(diagnostics, [{ category: "LOCAL_PATH", source: "FINAL_RESPONSE" }]);
  } finally {
    await harness.ctx.fiber.dispose();
  }
});

test("unsafe model-authored Tool arguments are replaced before Tool execution and persistence", async () => {
  const client = new RecordingHardwareClient(SIMULATED_FREQUENCY_RESULT);
  const harness = await createAgentHarness({
    client,
    script: [toolCallResponse("unsafe-args", "hardware_measure_frequency", {
      channel: 1,
      context_id: "C:\\Users\\operator\\capture.txt",
    })],
  });
  try {
    await runAgent(harness.agent, "Measure frequency.");
    assert.equal(client.calls.length, 0);
    assert.equal(harness.adapter.requests.length, 1);
    assert.equal(visibleToolCalls(harness.agent).length, 0);
    assert.match(finalAgentText(harness.agent), /unsafe model output was discarded/i);
    assert.doesNotMatch(JSON.stringify(harness.agent.session.snapshotEvents()), /operator|capture\.txt/);
  } finally {
    await harness.ctx.fiber.dispose();
  }
});

test("unsafe intermediate reasoning is discarded before live or durable Agent output", async () => {
  const client = new RecordingHardwareClient(SIMULATED_FREQUENCY_RESULT);
  const harness = await createAgentHarness({
    client,
    script: [[
      { type: "block-start", index: 0, blockType: "reasoning" },
      { type: "reasoning-delta", index: 0, text: "look in /tmp/private/capture.bin" },
      { type: "block-end", index: 0, block: { type: "reasoning", text: "look in /tmp/private/capture.bin" } },
      { type: "block-start", index: 1, blockType: "text" },
      { type: "text-delta", index: 1, text: "No tool is needed." },
      { type: "block-end", index: 1, block: { type: "text", text: "No tool is needed." } },
      { type: "usage", usage: { inputTokens: 5, outputTokens: 5 } },
      { type: "finish", reason: { kind: "stop" } },
    ]],
  });
  try {
    await runAgent(harness.agent, "Explain the result.");
    assert.equal(client.calls.length, 0);
    assert.equal(harness.adapter.requests.length, 1);
    assert.match(finalAgentText(harness.agent), /unsafe model output was discarded/i);
    assert.doesNotMatch(JSON.stringify(harness.agent.session.snapshotEvents()), /tmp|private|capture\.bin/);
  } finally {
    await harness.ctx.fiber.dispose();
  }
});

test("explicit reasoning-relaxation opt-in skips reasoning inspection but never relaxes authority", async () => {
  process.env.AIA_RELAX_EGRESS_REASONING = "1";
  try {
    const client = new RecordingHardwareClient(SIMULATED_FREQUENCY_RESULT);
    const harness = await createAgentHarness({
      client,
      useProductionOperationScopeAuthority: true,
      script: [
        [
          { type: "block-start", index: 0, blockType: "reasoning" },
          { type: "reasoning-delta", index: 0, text: "look in /tmp/private/capture.bin" },
          { type: "block-end", index: 0, block: { type: "reasoning", text: "look in /tmp/private/capture.bin" } },
          { type: "block-start", index: 1, blockType: "text" },
          { type: "text-delta", index: 1, text: "No tool is needed." },
          { type: "block-end", index: 1, block: { type: "text", text: "No tool is needed." } },
          { type: "usage", usage: { inputTokens: 5, outputTokens: 5 } },
          { type: "finish", reason: { kind: "stop" } },
        ],
        toolCallResponse("still-denied", "hardware_measure_frequency", { channel: 1 }),
        textResponse("No authority exists outside the trusted lifecycle."),
      ],
    });
    try {
      await runAgent(harness.agent, "Explain the result.");
      assert.match(finalAgentText(harness.agent), /No tool is needed\./);
      await runAgent(harness.agent, "Measure frequency on CH1.");
      assert.equal(client.calls.length, 0, "the dev-only egress flag must not mint any hardware authority");
      assert.match(finalAgentText(harness.agent), /No authority exists outside the trusted lifecycle\./);
    } finally {
      await harness.ctx.fiber.dispose();
    }
  } finally {
    delete process.env.AIA_RELAX_EGRESS_REASONING;
  }
});
