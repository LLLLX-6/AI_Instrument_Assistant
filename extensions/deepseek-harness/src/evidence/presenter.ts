import type {
  ConfirmationState,
  EvidenceFailure,
  EvidenceItem,
  EvidencePresentationOptions,
  InstrumentEvidenceSummary,
  OpaqueWaveformEvidence,
  TeachingEvidenceContext,
} from "./models.ts";

type JsonObject = Readonly<Record<string, unknown>>;

const OBSERVATIONS = Object.freeze([
  ["instrument_frequency", "instrument frequency", "Hz"],
  ["instrument_vpp", "instrument Vpp", "V"],
  ["software_frequency", "software frequency", "Hz"],
  ["software_period", "software period", "s"],
  ["software_duty_cycle", "software duty cycle", "%"],
  ["software_vpp", "software Vpp", "V"],
  ["software_mean", "software mean", "V"],
  ["software_rms", "software RMS", "V"],
] as const);

const INFERENCE_BOUNDARY = "Interpretation may compare labelled evidence with an explicit design criterion, but must not invent measurements, tolerances, sample access, or atomicity.";

export function presentHardwareResult(
  value: unknown,
  options: EvidencePresentationOptions,
): TeachingEvidenceContext {
  const root = object(value, "hardware result");
  const normalizedOptions = presentationOptions(options);
  const operation = optionalText(root.operation, "operation");
  if (root.ok === false) return failedContext(root, operation, normalizedOptions);
  if (root.ok !== true) throw new TypeError("hardware result ok must be boolean");
  const result = object(root.result, "result");
  if (operation === "hardware.get_status") return statusContext(result, operation, normalizedOptions);

  const instrument = instrumentSummary(object(result.instrument, "instrument"));
  const observations = object(result.observations, "observations");
  const facts: EvidenceItem[] = [];
  const analyses: EvidenceItem[] = [];
  const warnings = textArray(result.warnings, "warnings");
  const algorithm = analysisAlgorithm(result.provenance);
  let simulated = false;
  for (const [key, label, unit] of OBSERVATIONS) {
    if (!(key in observations)) continue;
    const item = evidenceItem(object(observations[key], key), label, unit, algorithm);
    if (item.source === "software_analysis") analyses.push(item);
    else {
      facts.push(item);
      simulated ||= item.source === "simulated";
    }
    for (const warning of item.warnings) if (!warnings.includes(warning)) warnings.push(warning);
  }
  const coherence = coherenceSummary(result.coherence);
  const artifact = result.waveform === null ? null : waveformEvidence(result.waveform);
  const quality = measurementQuality(result.quality);
  const limitations = ["No industrial-grade accuracy claim is made."];
  if (artifact !== null) limitations.push("The waveform artifact is opaque; sample arrays are not accessible to the Agent.");
  if (coherence?.instrument_vs_software === "sequential_same_session") {
    limitations.push("Instrument and software observations are sequential in one session, not atomic.");
  }
  if (quality === "degraded") limitations.push("The result is degraded; available evidence and warnings must be interpreted separately.");
  if (simulated) limitations.push("Simulated evidence is not a physical instrument observation.");
  return freezeContext({
    ...normalizedOptions,
    operation,
    executionStatus: "COMPLETED",
    requiredUserAction: "NONE",
    instrument,
    facts,
    analyses,
    inferences: [],
    quality,
    warnings,
    coherence,
    artifact,
    limitations,
    failure: null,
    allowedInferenceBoundary: INFERENCE_BOUNDARY,
  });
}

export function presentAdapterFailure(
  value: unknown,
  options: EvidencePresentationOptions,
): TeachingEvidenceContext {
  const failure = object(value, "adapter failure");
  const code = boundedText(failure.code, "failure code", 128);
  const deliveryState = optionalText(failure.deliveryState, "deliveryState");
  const operation = optionalText(failure.operation, "operation");
  const unknown = code === "indeterminate_execution";
  return freezeContext({
    ...presentationOptions(options),
    operation,
    executionStatus: unknown ? "UNKNOWN" : "FAILED",
    requiredUserAction: unknown ? "EXPLICIT_REMEASURE_DECISION" : "NONE",
    instrument: null,
    facts: [],
    analyses: [],
    inferences: [],
    quality: null,
    warnings: [],
    coherence: null,
    artifact: null,
    limitations: unknown
      ? ["Execution may have occurred, but no correlated result was confirmed; automatic replay is forbidden."]
      : ["No canonical measurement evidence was returned."],
    failure: Object.freeze({
      code,
      message: boundedText(failure.message, "failure message", 256),
      deliveryState,
    }),
    allowedInferenceBoundary: INFERENCE_BOUNDARY,
  });
}

function failedContext(
  root: JsonObject,
  operation: string | null,
  options: Readonly<{ requestedGoal: string; measurementDecisionReason: string; confirmationState: ConfirmationState }>,
): TeachingEvidenceContext {
  const error = object(root.error, "hardware error");
  return freezeContext({
    ...options,
    operation,
    executionStatus: "FAILED",
    requiredUserAction: "NONE",
    instrument: null,
    facts: [],
    analyses: [],
    inferences: [],
    quality: "failed",
    warnings: [],
    coherence: null,
    artifact: null,
    limitations: ["The canonical operation failed; no measurement evidence is available."],
    failure: Object.freeze({
      code: boundedText(error.code, "error code", 128),
      message: boundedText(error.message, "error message", 256),
      deliveryState: null,
    }),
    allowedInferenceBoundary: INFERENCE_BOUNDARY,
  });
}

function statusContext(
  result: JsonObject,
  operation: string,
  options: Readonly<{ requestedGoal: string; measurementDecisionReason: string; confirmationState: ConfirmationState }>,
): TeachingEvidenceContext {
  const instrument = instrumentSummary(object(result.instrument, "instrument"));
  const item: EvidenceItem = Object.freeze({
    kind: "FACT",
    label: "instrument status",
    value: instrument.model,
    unit: null,
    source: "instrument",
    quality: "good",
    warnings: Object.freeze([]),
    provenance: Object.freeze({
      method: "hardware.get_status",
      observedAt: boundedText(result.observed_at, "observed_at", 64),
      analysisAlgorithm: null,
      evidenceArtifactIds: Object.freeze([]),
    }),
  });
  return freezeContext({
    ...options,
    operation,
    executionStatus: "COMPLETED",
    requiredUserAction: "NONE",
    instrument,
    facts: [item],
    analyses: [],
    inferences: [],
    quality: "good",
    warnings: [],
    coherence: null,
    artifact: null,
    limitations: ["Status is a bounded observation, not proof of physical probe setup."],
    failure: null,
    allowedInferenceBoundary: INFERENCE_BOUNDARY,
  });
}

function evidenceItem(
  observation: JsonObject,
  label: string,
  unit: string,
  algorithm: string | null,
): EvidenceItem {
  const source = observationSource(observation.source);
  const warnings = textArray(observation.warnings, `${label} warnings`);
  return Object.freeze({
    kind: source === "software_analysis" ? "ANALYSIS" : "FACT",
    label,
    value: observationValue(observation.value),
    unit,
    source,
    quality: observationQuality(observation.quality),
    warnings: Object.freeze(warnings),
    provenance: Object.freeze({
      method: boundedText(observation.method, `${label} method`),
      observedAt: boundedText(observation.observed_at, `${label} observed_at`, 64),
      analysisAlgorithm: source === "software_analysis" ? algorithm : null,
      evidenceArtifactIds: Object.freeze(textArray(observation.evidence_artifact_ids, `${label} artifact ids`)),
    }),
  });
}

function waveformEvidence(value: unknown): OpaqueWaveformEvidence {
  const waveform = object(value, "waveform");
  const artifact = object(waveform.artifact, "artifact");
  return Object.freeze({
    artifactId: boundedText(artifact.artifact_id, "artifact_id"),
    uri: boundedText(artifact.uri, "artifact uri", 2048),
    mediaType: boundedText(artifact.media_type, "artifact media type", 255),
    sizeBytes: optionalNonnegativeInteger(artifact.size_bytes, "artifact size_bytes"),
    sha256: optionalText(artifact.sha256, "artifact sha256"),
    channel: positiveInteger(waveform.channel, "waveform channel"),
    pointCount: positiveInteger(waveform.point_count, "point_count"),
    sampleIntervalSeconds: positiveNumber(waveform.sample_interval_seconds, "sample_interval_seconds"),
    timeRangeSeconds: numberPair(waveform.time_range_seconds, "time_range_seconds"),
    voltageRangeV: numberPair(waveform.voltage_range_v, "voltage_range_v"),
    acquisitionMode: boundedText(waveform.acquisition_mode, "acquisition_mode", 64),
    capturedAt: boundedText(waveform.captured_at, "captured_at", 64),
    opaque: true,
  });
}

function instrumentSummary(value: JsonObject): InstrumentEvidenceSummary {
  return Object.freeze({
    manufacturer: boundedText(value.manufacturer, "manufacturer", 256),
    model: boundedText(value.model, "model", 256),
    serialNumber: maskSerial(boundedText(value.serial_number, "serial_number", 256)),
    firmwareVersion: boundedText(value.firmware_version, "firmware_version", 256),
  });
}

function coherenceSummary(value: unknown): TeachingEvidenceContext["coherence"] {
  const coherence = object(value, "coherence");
  return Object.freeze({
    software_observations: boundedText(coherence.software_observations, "software coherence", 64),
    instrument_vs_software: boundedText(coherence.instrument_vs_software, "instrument coherence", 64),
  });
}

function analysisAlgorithm(value: unknown): string | null {
  const provenance = object(value, "provenance");
  if (provenance.analysis_algorithm === null) return null;
  const algorithm = object(provenance.analysis_algorithm, "analysis_algorithm");
  return `${boundedText(algorithm.name, "algorithm name", 128)}@${boundedText(algorithm.version, "algorithm version", 64)}`;
}

function freezeContext(value: TeachingEvidenceContext): TeachingEvidenceContext {
  const failure: EvidenceFailure | null = value.failure === null ? null : Object.freeze({ ...value.failure });
  return Object.freeze({
    ...value,
    facts: Object.freeze([...value.facts]),
    analyses: Object.freeze([...value.analyses]),
    inferences: Object.freeze([...value.inferences]),
    warnings: Object.freeze([...value.warnings]),
    limitations: Object.freeze([...value.limitations]),
    failure,
  });
}

function presentationOptions(options: EvidencePresentationOptions) {
  return Object.freeze({
    requestedGoal: boundedText(options.requestedGoal, "requestedGoal"),
    measurementDecisionReason: boundedText(options.measurementDecisionReason, "measurementDecisionReason"),
    confirmationState: confirmationState(options.confirmationState),
  });
}

function observationValue(value: unknown): EvidenceItem["value"] {
  if (value === null) return null;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  const duty = object(value, "duty cycle");
  const ratio = finiteNumber(duty.ratio, "duty ratio");
  const percent = finiteNumber(duty.percent, "duty percent");
  return Object.freeze({ ratio, percent });
}

function object(value: unknown, name: string): JsonObject {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new TypeError(`${name} must be an object`);
  return value as JsonObject;
}

function boundedText(value: unknown, name: string, maximum = 512): string {
  if (typeof value !== "string" || !value.trim() || value.length > maximum) throw new TypeError(`${name} must be bounded text`);
  return value.trim();
}

function optionalText(value: unknown, name: string): string | null {
  return value === null || value === undefined ? null : boundedText(value, name);
}

function textArray(value: unknown, name: string): string[] {
  if (!Array.isArray(value)) throw new TypeError(`${name} must be an array`);
  return value.map((item, index) => boundedText(item, `${name}[${index}]`));
}

function observationSource(value: unknown): EvidenceItem["source"] {
  if (value !== "instrument" && value !== "software_analysis" && value !== "simulated") throw new TypeError("unknown observation source");
  return value;
}

function observationQuality(value: unknown): EvidenceItem["quality"] {
  if (value !== "good" && value !== "degraded" && value !== "unavailable") throw new TypeError("unknown observation quality");
  return value;
}

function measurementQuality(value: unknown): TeachingEvidenceContext["quality"] {
  if (value !== "good" && value !== "degraded" && value !== "failed") throw new TypeError("unknown measurement quality");
  return value;
}

function confirmationState(value: unknown): ConfirmationState {
  if (value !== "NOT_REQUIRED" && value !== "REQUIRED" && value !== "CONFIRMED" && value !== "SIMULATED") {
    throw new TypeError("unknown confirmation state");
  }
  return value;
}

function maskSerial(value: string): string {
  if (value === "***" || (value.startsWith("***") && value.length === 7)) return value;
  return value.length <= 4 ? "***" : `***${value.slice(-4)}`;
}

function finiteNumber(value: unknown, name: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new TypeError(`${name} must be finite`);
  return value;
}

function positiveNumber(value: unknown, name: string): number {
  const result = finiteNumber(value, name);
  if (result <= 0) throw new TypeError(`${name} must be positive`);
  return result;
}

function positiveInteger(value: unknown, name: string): number {
  if (!Number.isSafeInteger(value) || (value as number) <= 0) throw new TypeError(`${name} must be a positive integer`);
  return value as number;
}

function optionalNonnegativeInteger(value: unknown, name: string): number | null {
  if (value === undefined) return null;
  if (!Number.isSafeInteger(value) || (value as number) < 0) throw new TypeError(`${name} must be a nonnegative integer`);
  return value as number;
}

function numberPair(value: unknown, name: string): readonly [number, number] {
  if (!Array.isArray(value) || value.length !== 2) throw new TypeError(`${name} must contain two numbers`);
  return Object.freeze([finiteNumber(value[0], name), finiteNumber(value[1], name)] as const);
}
