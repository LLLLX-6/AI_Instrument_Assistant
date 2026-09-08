import assert from "node:assert/strict";
import test from "node:test";

import {
  presentAdapterFailure,
  presentHardwareResult,
} from "../../src/evidence/index.ts";
import { DEGRADED_PWM_RESULT, HARDWARE_ERROR_RESULT } from "../support/canonical-results.ts";

const COMPLETE_PWM_RESULT = {
  ...DEGRADED_PWM_RESULT,
  result: {
    ...DEGRADED_PWM_RESULT.result,
    quality: "good",
    warnings: [],
    observations: {
      instrument_frequency: observation(10040.16, "instrument", "oscilloscope query"),
      instrument_vpp: observation(0.396, "instrument", "oscilloscope query"),
      software_frequency: observation(10004.33, "software_analysis", "threshold edges"),
      software_duty_cycle: observation(
        { ratio: 0.2996, percent: 29.96 }, "software_analysis", "threshold edges",
      ),
      software_vpp: observation(0.4, "software_analysis", "sample extrema"),
    },
  },
} as const;

function observation(value: unknown, source: string, method: string) {
  return {
    value, source, method, observed_at: "2026-09-08T09:00:00Z", quality: "good",
    warnings: [], evidence_artifact_ids: ["550e8400-e29b-41d4-a716-446655440001"],
  };
}

const OPTIONS = {
  requestedGoal: "Evaluate PWM signal",
  measurementDecisionReason: "PWM metrics directly answer the request.",
  confirmationState: "CONFIRMED" as const,
};

test("presenter classifies instrument FACT and software ANALYSIS without inference", () => {
  const context = presentHardwareResult(COMPLETE_PWM_RESULT, OPTIONS);
  assert.equal(context.executionStatus, "COMPLETED");
  assert.deepEqual(context.facts.map((item) => item.label), ["instrument frequency", "instrument Vpp"]);
  assert.deepEqual(context.analyses.map((item) => item.label), [
    "software frequency", "software duty cycle", "software Vpp",
  ]);
  assert.ok(context.facts.every((item) => item.kind === "FACT" && item.source === "instrument"));
  assert.ok(context.analyses.every((item) => item.kind === "ANALYSIS" && item.source === "software_analysis"));
  assert.deepEqual(context.inferences, []);
  assert.equal(context.instrument?.serialNumber, "***9517");
});

test("presenter preserves coherence, provenance, and opaque artifact metadata without samples", () => {
  const context = presentHardwareResult(COMPLETE_PWM_RESULT, OPTIONS);
  assert.deepEqual(context.coherence, COMPLETE_PWM_RESULT.result.coherence);
  assert.equal(context.artifact?.artifactId, "550e8400-e29b-41d4-a716-446655440001");
  assert.equal(context.artifact?.uri, "memory://waveforms/550e8400-e29b-41d4-a716-446655440001");
  assert.equal(context.artifact?.pointCount, 1200);
  assert.match(context.limitations.join(" "), /opaque/i);
  assert.match(context.limitations.join(" "), /sequential|not atomic/i);
  assert.doesNotMatch(JSON.stringify(context), /"samples"/);
  assert.equal(context.facts[0]?.provenance.method, "oscilloscope query");
  assert.equal(context.analyses[0]?.provenance.method, "threshold edges");
});

test("degraded result preserves available evidence and warnings", () => {
  const degraded = {
    ...COMPLETE_PWM_RESULT,
    result: {
      ...COMPLETE_PWM_RESULT.result,
      quality: "degraded",
      warnings: ["Instrument frequency unavailable."],
      observations: {
        ...COMPLETE_PWM_RESULT.result.observations,
        instrument_frequency: {
          ...COMPLETE_PWM_RESULT.result.observations.instrument_frequency,
          value: null, quality: "unavailable", warnings: ["No stable trigger."],
        },
      },
    },
  };
  const context = presentHardwareResult(degraded, OPTIONS);
  assert.equal(context.quality, "degraded");
  assert.equal(context.facts[0]?.value, null);
  assert.equal(context.facts[0]?.quality, "unavailable");
  assert.ok(context.analyses.length > 0);
  assert.deepEqual(context.warnings, ["Instrument frequency unavailable.", "No stable trigger."]);
  assert.equal(context.failure, null);
});

test("canonical ok=false produces bounded failure and no fabricated evidence", () => {
  const context = presentHardwareResult(HARDWARE_ERROR_RESULT, OPTIONS);
  assert.equal(context.executionStatus, "FAILED");
  assert.equal(context.failure?.code, "measurement_failed");
  assert.deepEqual(context.facts, []);
  assert.deepEqual(context.analyses, []);
  assert.deepEqual(context.inferences, []);
});

test("indeterminate adapter failure is UNKNOWN and requires explicit retry decision", () => {
  const context = presentAdapterFailure({
    code: "indeterminate_execution",
    message: "Hardware execution status is unknown.",
    deliveryState: "SENT_UNCONFIRMED",
  }, OPTIONS);
  assert.equal(context.executionStatus, "UNKNOWN");
  assert.equal(context.requiredUserAction, "EXPLICIT_REMEASURE_DECISION");
  assert.deepEqual(context.facts, []);
  assert.deepEqual(context.analyses, []);
});

test("simulated evidence remains visibly labeled simulated", () => {
  const simulated = {
    ...COMPLETE_PWM_RESULT,
    result: {
      ...COMPLETE_PWM_RESULT.result,
      observations: {
        instrument_frequency: observation(10000, "simulated", "synthetic waveform"),
      },
    },
  };
  const context = presentHardwareResult(simulated, OPTIONS);
  assert.equal(context.facts[0]?.source, "simulated");
  assert.match(context.limitations.join(" "), /simulated/i);
});

test("presenter re-masks a noncanonical serial defensively", () => {
  const unsafe = {
    ...COMPLETE_PWM_RESULT,
    result: {
      ...COMPLETE_PWM_RESULT.result,
      instrument: { ...COMPLETE_PWM_RESULT.result.instrument, serial_number: "SERIAL-ABC123" },
    },
  };
  const context = presentHardwareResult(unsafe, OPTIONS);
  assert.equal(context.instrument?.serialNumber, "***C123");
  assert.doesNotMatch(JSON.stringify(context), /SERIAL-ABC123/);
});
