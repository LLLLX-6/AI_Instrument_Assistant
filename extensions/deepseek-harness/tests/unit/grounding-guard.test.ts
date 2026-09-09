import assert from "node:assert/strict";
import test from "node:test";

import { inspectGroundingCandidate } from "../../src/grounding/index.ts";
import {
  FAILED_MEASUREMENT_EVIDENCE,
  PHASE7C4D_DEGRADED_EVIDENCE,
  PHASE7C4D_FREQUENCY_EVIDENCE,
  PHASE7C4D_PWM_EVIDENCE,
  SIMULATED_FREQUENCY_EVIDENCE,
} from "../support/recorded-teaching-evidence.ts";

function inspect(candidate: string, evidence = PHASE7C4D_PWM_EVIDENCE) {
  return inspectGroundingCandidate({ candidate, evidence, policyDecision: null, correlationId: "grounding-unit" });
}

function categories(candidate: string, evidence = PHASE7C4D_PWM_EVIDENCE): string[] {
  const result = inspect(candidate, evidence);
  return result.status === "SUPPORTED" ? [] : result.violations.map((violation) => violation.category);
}

test("supports exact, deterministic rounded, and unit-converted instrument frequency", () => {
  assert.equal(inspect("The oscilloscope measured 10020.04 Hz.").status, "SUPPORTED");
  assert.equal(inspect("The instrument frequency was 10020 Hz.").status, "SUPPORTED");
  assert.equal(inspect("The oscilloscope measured 10.02 kHz.").status, "SUPPORTED");
});

test("rejects fabricated, nearby, and incorrectly converted frequency", () => {
  assert.ok(categories("The oscilloscope measured 12 kHz.").includes("UNSUPPORTED_NUMERIC_CLAIM"));
  assert.ok(categories("The oscilloscope measured 10.03 kHz.").includes("UNSUPPORTED_NUMERIC_CLAIM"));
  assert.ok(categories("The oscilloscope measured 10020.04 kHz.").includes("UNSUPPORTED_NUMERIC_CLAIM"));
});

test("does not turn the stated target into measured evidence", () => {
  assert.ok(categories("The measured frequency is exactly the expected 10 kHz target.").includes("UNSUPPORTED_NUMERIC_CLAIM"));
  assert.equal(inspect("The stated target is 10 kHz and 30% duty.").status, "SUPPORTED");
});

test("enforces instrument and software source attribution", () => {
  assert.ok(categories("The oscilloscope measured 10006.06 Hz.").includes("SOURCE_ATTRIBUTION_MISMATCH"));
  assert.ok(categories("Software analysis found 10020.04 Hz.").includes("SOURCE_ATTRIBUTION_MISMATCH"));
  assert.equal(inspect("Software analysis found a 29.9541% duty cycle.").status, "SUPPORTED");
  assert.ok(categories("The oscilloscope measured a 29.9541% duty cycle.").includes("SOURCE_ATTRIBUTION_MISMATCH"));
});

test("preserves FACT, ANALYSIS, simulated, and inference distinctions", () => {
  assert.equal(inspect("FACT: instrument frequency: 10020.04 Hz [instrument; good]").status, "SUPPORTED");
  assert.equal(inspect("ANALYSIS: software frequency: 10006.06 Hz [software_analysis; good]").status, "SUPPORTED");
  assert.ok(categories("The physical oscilloscope measured 10 kHz.", SIMULATED_FREQUENCY_EVIDENCE).includes("SOURCE_ATTRIBUTION_MISMATCH"));
  assert.ok(categories("FACT: The MCU timer configuration is definitely correct.").includes("UNSUPPORTED_INFERENCE"));
});

test("allows only the bounded non-causal comparison inference", () => {
  assert.equal(inspect(
    "INFERENCE: The measured signal appears broadly consistent with the stated 10 kHz / 30% duty target.",
  ).status, "SUPPORTED");
  assert.ok(categories("The evidence proves the MCU timer configuration is definitely correct.").includes("UNSUPPORTED_INFERENCE"));
});

test("rejects fabricated Vpp and unknown measurement references", () => {
  assert.ok(categories("The instrument Vpp was 3.3 V.").includes("UNSUPPORTED_NUMERIC_CLAIM"));
  assert.ok(categories("The measured rise time was 2 us.").includes("UNKNOWN_EVIDENCE_REFERENCE"));
});

test("supports the bounded successful Phase 7C.4D values", () => {
  const candidate = [
    "OBSERVED FACTS:",
    "- instrument frequency: 10020.04 Hz [instrument; good]",
    "- instrument Vpp: 0.4 V [instrument; good]",
    "ANALYSIS:",
    "- software frequency: 10006.06 Hz [software_analysis; good]",
    "- software duty cycle: 29.9541% [software_analysis; good]",
    "- software Vpp: 0.4 V [software_analysis; good]",
    "QUALITY: good",
    "WARNINGS: none",
    "COHERENCE: software observations share the same artifact; instrument and software observations were collected sequentially within the same session.",
    "ARTIFACT: a 1200-point waveform artifact was captured; samples remain opaque.",
  ].join("\n");
  assert.equal(inspect(candidate).status, "SUPPORTED");
});

test("handles unavailable evidence and material degraded warnings", () => {
  const accurate = [
    "QUALITY: degraded",
    "Instrument frequency is unavailable; software frequency and software duty cycle are unavailable.",
    "The instrument Vpp was 0.016 V. Software analysis found Vpp 0.008 V.",
    "WARNINGS: signal_too_small; no_edges_detected; instrument_frequency_unavailable.",
  ].join("\n");
  assert.equal(inspect(accurate, PHASE7C4D_DEGRADED_EVIDENCE).status, "SUPPORTED");
  const misleading = "The signal is a normal 10 kHz PWM and the measurement is fully reliable.";
  const result = categories(misleading, PHASE7C4D_DEGRADED_EVIDENCE);
  assert.ok(result.includes("FALSE_AVAILABILITY_CLAIM") || result.includes("UNSUPPORTED_NUMERIC_CLAIM"));
  assert.ok(result.includes("QUALITY_MISREPRESENTATION"));
  assert.ok(result.includes("WARNING_OMISSION_MATERIAL"));
});

test("rejects quality upgrades and material warning omission", () => {
  assert.ok(categories("QUALITY: good. The PWM measurement is reliable.", PHASE7C4D_DEGRADED_EVIDENCE).includes("QUALITY_MISREPRESENTATION"));
  assert.ok(categories("The PWM measurement completed successfully at 0.016 V.", PHASE7C4D_DEGRADED_EVIDENCE).includes("WARNING_OMISSION_MATERIAL"));
});

test("preserves sequential coherence and rejects simultaneous claims", () => {
  assert.ok(categories("Frequency and Vpp were measured simultaneously.").includes("FALSE_ATOMICITY_CLAIM"));
  assert.equal(inspect("The observations were collected sequentially within the same session.").status, "SUPPORTED");
});

test("keeps artifacts opaque while allowing bounded point-count metadata", () => {
  assert.ok(categories("I inspected all 1200 raw samples.").includes("ARTIFACT_ACCESS_OVERCLAIM"));
  assert.equal(inspect("A 1200-point waveform artifact was captured.").status, "SUPPORTED");
});

test("failed operations cannot borrow numeric values from earlier evidence", () => {
  assert.ok(categories("The failed measurement returned 10020.04 Hz.", FAILED_MEASUREMENT_EVIDENCE).includes("UNSUPPORTED_MEASUREMENT_CLAIM"));
  assert.ok(categories("The measurement completed successfully.", FAILED_MEASUREMENT_EVIDENCE).includes("UNSUPPORTED_MEASUREMENT_CLAIM"));
  assert.equal(inspect("The operation failed; no measurement value is available.", FAILED_MEASUREMENT_EVIDENCE).status, "SUPPORTED");
});

test("unsupported results contain stable bounded metadata but no rejected prose", () => {
  const candidate = "The oscilloscope measured 12 kHz from a secret-looking but egress-safe sentence.";
  const result = inspect(candidate);
  assert.equal(result.status, "UNSUPPORTED");
  if (result.status === "UNSUPPORTED") {
    assert.ok(Object.isFrozen(result));
    assert.ok(Object.isFrozen(result.violations));
    assert.doesNotMatch(JSON.stringify(result), /secret-looking|oscilloscope measured 12/);
    assert.deepEqual(Object.keys(result.violations[0]!).sort(), ["category", "claimKind", "evidenceLabel"].sort());
  }
});
