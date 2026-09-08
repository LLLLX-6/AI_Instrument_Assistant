export type EvidenceKind = "FACT" | "ANALYSIS" | "INFERENCE";
export type ExecutionStatus = "COMPLETED" | "FAILED" | "UNKNOWN";
export type ConfirmationState = "NOT_REQUIRED" | "REQUIRED" | "CONFIRMED" | "SIMULATED";
export type RequiredUserAction = "NONE" | "EXPLICIT_REMEASURE_DECISION";

export interface EvidenceProvenanceSummary {
  readonly method: string;
  readonly observedAt: string;
  readonly analysisAlgorithm: string | null;
  readonly evidenceArtifactIds: readonly string[];
}

export interface EvidenceItem {
  readonly kind: EvidenceKind;
  readonly label: string;
  readonly value: number | Readonly<{ ratio: number; percent: number }> | string | null;
  readonly unit: string | null;
  readonly source: "instrument" | "software_analysis" | "simulated";
  readonly quality: "good" | "degraded" | "unavailable";
  readonly warnings: readonly string[];
  readonly provenance: EvidenceProvenanceSummary;
}

export interface OpaqueWaveformEvidence {
  readonly artifactId: string;
  readonly uri: string;
  readonly mediaType: string;
  readonly sizeBytes: number | null;
  readonly sha256: string | null;
  readonly channel: number;
  readonly pointCount: number;
  readonly sampleIntervalSeconds: number;
  readonly timeRangeSeconds: readonly [number, number];
  readonly voltageRangeV: readonly [number, number];
  readonly acquisitionMode: string;
  readonly capturedAt: string;
  readonly opaque: true;
}

export interface InstrumentEvidenceSummary {
  readonly manufacturer: string;
  readonly model: string;
  readonly serialNumber: string;
  readonly firmwareVersion: string;
}

export interface EvidenceFailure {
  readonly code: string;
  readonly message: string;
  readonly deliveryState: string | null;
}

export interface TeachingEvidenceContext {
  readonly requestedGoal: string;
  readonly measurementDecisionReason: string;
  readonly operation: string | null;
  readonly executionStatus: ExecutionStatus;
  readonly confirmationState: ConfirmationState;
  readonly requiredUserAction: RequiredUserAction;
  readonly instrument: InstrumentEvidenceSummary | null;
  readonly facts: readonly EvidenceItem[];
  readonly analyses: readonly EvidenceItem[];
  readonly inferences: readonly EvidenceItem[];
  readonly quality: "good" | "degraded" | "failed" | null;
  readonly warnings: readonly string[];
  readonly coherence: Readonly<{
    software_observations: string;
    instrument_vs_software: string;
  }> | null;
  readonly artifact: OpaqueWaveformEvidence | null;
  readonly limitations: readonly string[];
  readonly failure: EvidenceFailure | null;
  readonly allowedInferenceBoundary: string;
}

export interface EvidencePresentationOptions {
  readonly requestedGoal: string;
  readonly measurementDecisionReason: string;
  readonly confirmationState: ConfirmationState;
}
