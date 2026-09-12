import type { TeachingEvidenceContext } from "../evidence/index.ts";
import type { PolicyDecision } from "../policy/index.ts";

export type EgressViolationCategory =
  | "LOCAL_PATH"
  | "FULL_INSTRUMENT_SERIAL"
  | "VISA_RESOURCE_IDENTIFIER"
  | "CREDENTIAL_MATERIAL"
  | "RAW_INSTRUMENT_COMMAND"
  | "WAVEFORM_SAMPLE_ARRAY"
  | "OVERSIZED_OUTPUT";

export type EgressSource = "TOOL_ARGUMENTS" | "FINAL_RESPONSE" | "INTERMEDIATE_TEXT" | "MODEL_CANDIDATE_RAW";

export interface EgressInspectionInput {
  readonly candidate: string;
  readonly source: EgressSource;
  readonly correlationId: string;
  readonly knownSensitiveValues?: readonly string[];
  readonly maximumCharacters?: number;
}

export interface EgressViolation {
  readonly category: EgressViolationCategory;
  readonly source: EgressSource;
  readonly correlationId: string;
}

export type EgressInspectionResult =
  | Readonly<{ status: "SAFE" }>
  | Readonly<{ status: "UNSAFE"; violations: readonly EgressViolation[] }>;

export interface EgressDiagnostic {
  readonly status: "BLOCKED";
  readonly category: EgressViolationCategory;
  readonly source: EgressSource;
  readonly correlationId: string;
}

export interface SafeAgentFallbackInput {
  readonly correlationId: string;
  readonly violations: readonly EgressViolationCategory[];
  readonly policyDecision: PolicyDecision | null;
  readonly evidence: TeachingEvidenceContext | null;
}

export interface TrustedAgentEgressState {
  readonly policyDecision: PolicyDecision | null;
  readonly evidence: TeachingEvidenceContext | null;
}
