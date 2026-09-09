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

test("egress-safe but ungrounded final prose is replaced before persistence", async () => {
  const client = new RecordingHardwareClient(SIMULATED_FREQUENCY_RESULT);
  const diagnostics: Array<Record<string, unknown>> = [];
  const harness = await createAgentHarness({
    client,
    onGroundingDiagnostic: (diagnostic) => { diagnostics.push({ ...diagnostic }); },
    script: [
      toolCallResponse("grounding-call", "hardware_measure_frequency", { channel: 1 }),
      textResponse("The simulated measurement proved a frequency of 12 kHz."),
    ],
  });
  try {
    await runAgent(harness.agent, "Measure frequency on CH1.");
    const text = finalAgentText(harness.agent);
    assert.equal(client.calls.length, 1, "grounding fallback must not remeasure");
    assert.equal(harness.adapter.requests.length, 2, "grounding fallback must not retry the model");
    assert.equal(visibleToolCalls(harness.agent).length, 1, "grounding fallback must not add a Tool call");
    assert.doesNotMatch(text, /12 kHz|\bproved\b/i);
    assert.match(text, /OBSERVED FACTS:/);
    assert.match(text, /10000 Hz/);
    const events = JSON.stringify(harness.agent.session.snapshotEvents());
    assert.doesNotMatch(events, /12 kHz|\bproved\b/i, "rejected raw prose must not be durably persisted");
    assert.ok(diagnostics.some((diagnostic) => diagnostic.category === "UNSUPPORTED_INFERENCE"
      || diagnostic.category === "UNSUPPORTED_NUMERIC_CLAIM"));
    assert.doesNotMatch(JSON.stringify(diagnostics), /12 kHz|\bproved\b/i);
  } finally {
    await harness.ctx.fiber.dispose();
  }
});

test("grounded scripted response crosses both output boundaries unchanged", async () => {
  const client = new RecordingHardwareClient(SIMULATED_FREQUENCY_RESULT);
  const grounded = "FACT: simulated frequency: 10 kHz [simulated; good]";
  const diagnostics: unknown[] = [];
  const harness = await createAgentHarness({
    client,
    onGroundingDiagnostic: (diagnostic) => { diagnostics.push(diagnostic); },
    script: [
      toolCallResponse("supported-call", "hardware_measure_frequency", { channel: 1 }),
      textResponse(grounded),
    ],
  });
  try {
    await runAgent(harness.agent, "Measure simulated frequency on CH1.");
    assert.equal(finalAgentText(harness.agent), grounded);
    assert.equal(client.calls.length, 1);
    assert.equal(harness.adapter.requests.length, 2);
    assert.deepEqual(diagnostics, []);
  } finally {
    await harness.ctx.fiber.dispose();
  }
});

test("egress and grounding diagnostics remain separate", async () => {
  const client = new RecordingHardwareClient(SIMULATED_FREQUENCY_RESULT);
  const egress: unknown[] = [];
  const grounding: unknown[] = [];
  const harness = await createAgentHarness({
    client,
    onEgressDiagnostic: (diagnostic) => { egress.push(diagnostic); },
    onGroundingDiagnostic: (diagnostic) => { grounding.push(diagnostic); },
    script: [textResponse("Read C:\\FAKE_TEST_ONLY\\operator\\private.txt; the frequency was 12 kHz.")],
  });
  try {
    await runAgent(harness.agent, "Explain without a Tool call.");
    assert.ok(egress.length > 0);
    assert.deepEqual(grounding, [], "an Egress rejection does not masquerade as a Grounding decision");
    assert.match(finalAgentText(harness.agent), /unsafe model output was discarded/i);
  } finally {
    await harness.ctx.fiber.dispose();
  }
});
