import assert from "node:assert/strict";
import test from "node:test";

import {
  HARDWARE_AGENT_POLICY,
  createTeachingEvidenceMessage,
  serializeTeachingEvidenceContext,
} from "../../src/agent/index.ts";
import type { TeachingEvidenceContext } from "../../src/evidence/index.ts";

const CONTEXT: TeachingEvidenceContext = Object.freeze({
  requestedGoal: "Measure PWM",
  measurementDecisionReason: "Simulated measurement is allowed.",
  operation: "hardware.measure_pwm",
  executionStatus: "COMPLETED",
  confirmationState: "SIMULATED",
  requiredUserAction: "NONE",
  instrument: null,
  facts: Object.freeze([]),
  analyses: Object.freeze([]),
  inferences: Object.freeze([]),
  quality: "good",
  warnings: Object.freeze([]),
  coherence: null,
  artifact: null,
  limitations: Object.freeze(["Simulated evidence is not a physical instrument observation."]),
  failure: null,
  allowedInferenceBoundary: "Do not invent measurements.",
});

test("hardware Agent policy states semantic and deterministic safety boundaries", () => {
  assert.match(HARDWARE_AGENT_POLICY, /five semantic hardware tools/i);
  assert.match(HARDWARE_AGENT_POLICY, /deterministic policy gate/i);
  assert.match(HARDWARE_AGENT_POLICY, /simulated/i);
  assert.match(HARDWARE_AGENT_POLICY, /indeterminate/i);
  assert.match(HARDWARE_AGENT_POLICY, /opaque/i);
  assert.doesNotMatch(HARDWARE_AGENT_POLICY, /api key|psk|visa resource/i);
});

test("TeachingEvidenceContext is serialized as bounded structured Agent context", () => {
  const serialized = serializeTeachingEvidenceContext(CONTEXT);
  assert.match(serialized, /^AIA_TEACHING_EVIDENCE_CONTEXT\n/);
  assert.match(serialized, /"confirmationState":"SIMULATED"/);
  assert.match(serialized, /not a physical instrument observation/i);
  assert.doesNotMatch(serialized, /samples|PSK|\.aia-secrets|[A-Za-z]:\\/i);
});

test("TeachingEvidenceContext enters Harness as project-owned plugin context", () => {
  const message = createTeachingEvidenceMessage(CONTEXT);
  assert.deepEqual(message.source, { kind: "plugin", plugin: "aia-hardware-evidence" });
  assert.equal(message.content.length, 1);
  assert.equal(message.content[0]?.type, "text");
});
