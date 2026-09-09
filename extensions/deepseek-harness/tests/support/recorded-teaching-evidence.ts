import type {
  EvidenceItem,
  EvidenceProvenanceSummary,
  TeachingEvidenceContext,
} from "../../src/evidence/index.ts";

const OBSERVED_AT = "2026-09-09T00:00:00Z";
const ARTIFACT_ID = "phase7c4d-bounded-waveform";

function provenance(source: EvidenceItem["source"]): EvidenceProvenanceSummary {
  return Object.freeze({
    method: source === "software_analysis" ? "recorded bounded software analysis" : "recorded bounded observation",
    observedAt: OBSERVED_AT,
    analysisAlgorithm: source === "software_analysis" ? "recorded-phase7c4d-analysis" : null,
    evidenceArtifactIds: source === "software_analysis" ? Object.freeze([ARTIFACT_ID]) : Object.freeze([]),
  });
}

function item(
  kind: EvidenceItem["kind"],
  label: string,
  value: EvidenceItem["value"],
  unit: string | null,
  source: EvidenceItem["source"],
  quality: EvidenceItem["quality"] = "good",
  warnings: readonly string[] = [],
): EvidenceItem {
  return Object.freeze({
    kind,
    label,
    value: value !== null && typeof value === "object" ? Object.freeze({ ...value }) : value,
    unit,
    source,
    quality,
    warnings: Object.freeze([...warnings]),
    provenance: provenance(source),
  });
}

function context(
  values: Partial<TeachingEvidenceContext> & Pick<TeachingEvidenceContext, "facts" | "analyses">,
): TeachingEvidenceContext {
  return Object.freeze({
    requestedGoal: "Compare PWM_OUT with the stated 10 kHz / 30% duty target.",
    measurementDecisionReason: "Recorded bounded Phase 7C.4D validation evidence.",
    operation: "hardware.measure_pwm",
    executionStatus: "COMPLETED",
    confirmationState: "CONFIRMED",
    requiredUserAction: "NONE",
    instrument: null,
    inferences: Object.freeze([]),
    quality: "good",
    warnings: Object.freeze([]),
    coherence: Object.freeze({
      software_observations: "same_artifact",
      instrument_vs_software: "sequential_same_session",
    }),
    artifact: Object.freeze({
      artifactId: ARTIFACT_ID,
      uri: "fixture://phase7c4d/bounded-waveform",
      mediaType: "application/vnd.aia.waveform+json",
      sizeBytes: null,
      sha256: null,
      channel: 1,
      pointCount: 1200,
      sampleIntervalSeconds: 1,
      timeRangeSeconds: Object.freeze([0, 1] as const),
      voltageRangeV: Object.freeze([0, 0.4] as const),
      acquisitionMode: "recorded-bounded-fixture",
      capturedAt: OBSERVED_AT,
      opaque: true,
    }),
    limitations: Object.freeze([
      "The waveform artifact is opaque; sample arrays are not accessible to the Agent.",
      "Instrument and software observations are sequential in one session, not atomic.",
    ]),
    failure: null,
    allowedInferenceBoundary: "Only explicitly marked, non-causal comparison with the stated target is allowed.",
    ...values,
    facts: Object.freeze([...values.facts]),
    analyses: Object.freeze([...values.analyses]),
  });
}

export const PHASE7C4D_FREQUENCY_EVIDENCE = context({
  requestedGoal: "Measure CH1 frequency.",
  operation: "hardware.measure_frequency",
  facts: [item("FACT", "instrument frequency", 10_000, "Hz", "instrument")],
  analyses: [],
  coherence: null,
  artifact: null,
  limitations: Object.freeze(["This is a bounded instrument observation."]),
});

export const PHASE7C4D_PWM_EVIDENCE = context({
  facts: [
    item("FACT", "instrument frequency", 10_020.04, "Hz", "instrument"),
    item("FACT", "instrument Vpp", 0.4, "V", "instrument"),
  ],
  analyses: [
    item("ANALYSIS", "software frequency", 10_006.059835993472, "Hz", "software_analysis"),
    item("ANALYSIS", "software duty cycle", { ratio: 0.299541153263868, percent: 29.9541153263868 }, "%", "software_analysis"),
    item("ANALYSIS", "software Vpp", 0.4, "V", "software_analysis"),
  ],
});

export const PHASE7C4D_DEGRADED_EVIDENCE = context({
  facts: [
    item("FACT", "instrument frequency", null, "Hz", "instrument", "unavailable", ["instrument_frequency_unavailable"]),
    item("FACT", "instrument Vpp", 0.016, "V", "instrument", "degraded"),
  ],
  analyses: [
    item("ANALYSIS", "software frequency", null, "Hz", "software_analysis", "unavailable", ["no_edges_detected"]),
    item("ANALYSIS", "software duty cycle", null, "%", "software_analysis", "unavailable", ["no_edges_detected"]),
    item("ANALYSIS", "software Vpp", 0.008, "V", "software_analysis", "degraded"),
    item("ANALYSIS", "software mean", 0.0036633333333333335, "V", "software_analysis", "degraded"),
    item("ANALYSIS", "software RMS", 0.005134199061197374, "V", "software_analysis", "degraded"),
  ],
  quality: "degraded",
  warnings: Object.freeze(["signal_too_small", "no_edges_detected", "instrument_frequency_unavailable"]),
  limitations: Object.freeze([
    "The result is degraded; available evidence and warnings must be interpreted separately.",
    "The waveform artifact is opaque; sample arrays are not accessible to the Agent.",
    "Instrument and software observations are sequential in one session, not atomic.",
  ]),
});

export const FAILED_MEASUREMENT_EVIDENCE = context({
  facts: [],
  analyses: [],
  executionStatus: "FAILED",
  quality: "failed",
  warnings: Object.freeze([]),
  coherence: null,
  artifact: null,
  limitations: Object.freeze(["The canonical operation failed; no measurement evidence is available."]),
  failure: Object.freeze({ code: "measurement_failed", message: "Measurement could not be completed.", deliveryState: null }),
});

export const SIMULATED_FREQUENCY_EVIDENCE = context({
  facts: [item("FACT", "instrument frequency", 10_000, "Hz", "simulated")],
  analyses: [],
  confirmationState: "SIMULATED",
  coherence: null,
  artifact: null,
  limitations: Object.freeze(["Simulated evidence is not a physical instrument observation."]),
});
