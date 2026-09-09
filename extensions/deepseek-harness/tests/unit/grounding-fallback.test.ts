import assert from "node:assert/strict";
import test from "node:test";

import { inspectEgressCandidate } from "../../src/egress/index.ts";
import { inspectGroundingCandidate, renderGroundedFallback } from "../../src/grounding/index.ts";
import {
  FAILED_MEASUREMENT_EVIDENCE,
  PHASE7C4D_DEGRADED_EVIDENCE,
  PHASE7C4D_PWM_EVIDENCE,
} from "../support/recorded-teaching-evidence.ts";

test("successful deterministic fallback contains bounded evidence without causal diagnosis", () => {
  const text = renderGroundedFallback({ evidence: PHASE7C4D_PWM_EVIDENCE, policyDecision: null });
  assert.match(text, /OBSERVED FACTS:/);
  assert.match(text, /instrument frequency: 10020\.04 Hz/);
  assert.match(text, /ANALYSIS:/);
  assert.match(text, /software duty cycle: 29\.9541153264%/);
  assert.match(text, /QUALITY: good/);
  assert.match(text, /WARNINGS: none/);
  assert.match(text, /sequentially within the same session/i);
  assert.doesNotMatch(text, /timer|cause|definitely correct/i);
  assertFallbackSafeAndGrounded(text, PHASE7C4D_PWM_EVIDENCE);
});

test("degraded fallback preserves unavailable values and every material warning", () => {
  const text = renderGroundedFallback({ evidence: PHASE7C4D_DEGRADED_EVIDENCE, policyDecision: null });
  assert.match(text, /instrument frequency: unavailable/);
  assert.match(text, /software duty cycle: unavailable/);
  assert.match(text, /QUALITY: degraded/);
  for (const warning of PHASE7C4D_DEGRADED_EVIDENCE.warnings) assert.match(text, new RegExp(warning));
  assertFallbackSafeAndGrounded(text, PHASE7C4D_DEGRADED_EVIDENCE);
});

test("failure fallback includes no stale HIL numbers", () => {
  const text = renderGroundedFallback({ evidence: FAILED_MEASUREMENT_EVIDENCE, policyDecision: null });
  assert.match(text, /EXECUTION STATUS: failed/i);
  assert.doesNotMatch(text, /10000|10020|29\.95|0\.4/);
  assertFallbackSafeAndGrounded(text, FAILED_MEASUREMENT_EVIDENCE);
});

function assertFallbackSafeAndGrounded(text: string, evidence: typeof PHASE7C4D_PWM_EVIDENCE): void {
  assert.equal(inspectEgressCandidate({
    candidate: text,
    source: "FINAL_RESPONSE",
    correlationId: "fallback-test",
    knownSensitiveValues: [],
  }).status, "SAFE");
  assert.equal(inspectGroundingCandidate({
    candidate: text,
    evidence,
    policyDecision: null,
    correlationId: "fallback-test",
  }).status, "SUPPORTED");
}
