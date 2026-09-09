import assert from "node:assert/strict";
import test from "node:test";

import {
  inspectEgressCandidate,
  renderSafeAgentFallback,
} from "../../src/egress/index.ts";
import { presentAdapterFailure, presentHardwareResult } from "../../src/evidence/index.ts";
import { evaluateHardwareToolPolicy, createHardwareToolPolicyContext } from "../../src/policy/index.ts";
import {
  HARDWARE_UNAVAILABLE_RESULT,
  PARTIAL_PWM_RESULT,
  SIMULATED_PWM_RESULT,
} from "../support/canonical-results.ts";

const presentation = {
  requestedGoal: "Measure PWM_OUT",
  measurementDecisionReason: "Validation fixture.",
  confirmationState: "SIMULATED" as const,
};

test("successful fallback preserves FACT and ANALYSIS without inventing inference", () => {
  const evidence = presentHardwareResult(SIMULATED_PWM_RESULT, presentation);
  const text = renderSafeAgentFallback({
    correlationId: "success",
    violations: ["LOCAL_PATH"],
    policyDecision: null,
    evidence,
  });
  assert.match(text, /Measurement completed\./);
  assert.match(text, /FACT:/);
  assert.match(text, /ANALYSIS:/);
  assert.match(text, /instrument frequency/i);
  assert.match(text, /software duty cycle/i);
  assert.doesNotMatch(text, /INFERENCE:/);
  assertSafe(text);
});

test("degraded fallback preserves warnings and unavailable observations", () => {
  const evidence = presentHardwareResult(PARTIAL_PWM_RESULT, presentation);
  const text = renderSafeAgentFallback({ correlationId: "degraded", violations: [], policyDecision: null, evidence });
  assert.match(text, /degraded/i);
  assert.match(text, /No stable trigger/);
  assert.match(text, /unavailable/i);
  assertSafe(text);
});

test("ok=false fallback fabricates no measurement values", () => {
  const evidence = presentHardwareResult(HARDWARE_UNAVAILABLE_RESULT, presentation);
  const text = renderSafeAgentFallback({ correlationId: "failed", violations: [], policyDecision: null, evidence });
  assert.match(text, /failed/i);
  assert.match(text, /hardware_unavailable/);
  assert.doesNotMatch(text, /10000|3\.3|30%/);
  assertSafe(text);
});

test("confirmation fallback states zero execution and missing fields", () => {
  const decision = evaluateHardwareToolPolicy(createHardwareToolPolicyContext({
    operation: "hardware.measure_frequency",
    channel: 1,
    backendMode: "REAL",
    requestCorrelationId: "confirmation",
    requestedGoal: "Measure frequency",
    requestedTargetRef: "PWM_OUT",
    groundingRequired: true,
    wiringChanged: false,
    confirmation: null,
    previousExecution: null,
    designContext: null,
  }));
  const text = renderSafeAgentFallback({ correlationId: "confirmation", violations: [], policyDecision: decision, evidence: null });
  assert.match(text, /was not executed/i);
  assert.match(text, /physical confirmation is required/i);
  assert.match(text, /channel.*safe_low_voltage.*common_ground.*physical_target/i);
  assertSafe(text);
});

test("deny fallback states zero execution", () => {
  const decision = evaluateHardwareToolPolicy(createHardwareToolPolicyContext({
    operation: "hardware.raw_execute",
    channel: null,
    backendMode: "REAL",
    requestCorrelationId: "deny",
    requestedGoal: "Run raw command",
    requestedTargetRef: null,
    groundingRequired: false,
    wiringChanged: false,
    confirmation: null,
    previousExecution: null,
    designContext: null,
  }));
  const text = renderSafeAgentFallback({ correlationId: "deny", violations: [], policyDecision: decision, evidence: null });
  assert.match(text, /denied by policy/i);
  assert.match(text, /was not executed/i);
  assertSafe(text);
});

test("indeterminate fallback requires an explicit remeasurement decision", () => {
  const evidence = presentAdapterFailure({
    code: "indeterminate_execution",
    message: "Hardware request outcome is indeterminate; it was not replayed.",
    deliveryState: "SENT_UNCONFIRMED",
    operation: "hardware.measure_frequency",
  }, { ...presentation, confirmationState: "CONFIRMED" });
  const text = renderSafeAgentFallback({ correlationId: "indeterminate", violations: [], policyDecision: null, evidence });
  assert.match(text, /may have occurred/i);
  assert.match(text, /no automatic retry occurred/i);
  assert.match(text, /explicit remeasurement decision is required/i);
  assertSafe(text);
});

test("egress-only violation without evidence returns a deterministic zero-execution fallback", () => {
  const text = renderSafeAgentFallback({
    correlationId: "blocked",
    violations: ["LOCAL_PATH", "CREDENTIAL_MATERIAL"],
    policyDecision: null,
    evidence: null,
  });
  assert.match(text, /unsafe model output was discarded/i);
  assert.match(text, /No measurement was executed/i);
  assert.doesNotMatch(text, /LOCAL_PATH|CREDENTIAL_MATERIAL/);
  assertSafe(text);
});

test("fallback self-inspection discards an unsafe trusted warning instead of echoing it", () => {
  const base = presentHardwareResult(PARTIAL_PWM_RESULT, presentation);
  const evidence = Object.freeze({
    ...base,
    warnings: Object.freeze(["diagnostic saved under C:\\Users\\operator\\trace.txt"]),
  });
  const text = renderSafeAgentFallback({ correlationId: "fallback-defense", violations: [], policyDecision: null, evidence });
  assert.equal(text, "Unsafe model output was discarded. No additional operation or measurement was executed.");
  assert.doesNotMatch(text, /operator|trace\.txt/);
  assertSafe(text);
});

function assertSafe(candidate: string): void {
  assert.equal(inspectEgressCandidate({
    candidate,
    source: "FINAL_RESPONSE",
    correlationId: "fallback-self-check",
    knownSensitiveValues: [],
  }).status, "SAFE");
}
