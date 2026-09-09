import type { TeachingEvidenceContext } from "../evidence/index.ts";
import type { PolicyDecision } from "../policy/index.ts";

export type GroundingViolationCategory =
  | "UNSUPPORTED_NUMERIC_CLAIM"
  | "SOURCE_ATTRIBUTION_MISMATCH"
  | "UNSUPPORTED_MEASUREMENT_CLAIM"
  | "UNSUPPORTED_INFERENCE"
  | "FALSE_AVAILABILITY_CLAIM"
  | "FALSE_ATOMICITY_CLAIM"
  | "ARTIFACT_ACCESS_OVERCLAIM"
  | "QUALITY_MISREPRESENTATION"
  | "WARNING_OMISSION_MATERIAL"
  | "UNKNOWN_EVIDENCE_REFERENCE";

export type GroundingClaimKind =
  | "NUMERIC"
  | "SOURCE"
  | "MEASUREMENT"
  | "INFERENCE"
  | "AVAILABILITY"
  | "ATOMICITY"
  | "ARTIFACT"
  | "QUALITY"
  | "WARNING"
  | "REFERENCE";

export interface GroundingViolation {
  readonly category: GroundingViolationCategory;
  readonly claimKind: GroundingClaimKind;
  readonly evidenceLabel: string | null;
}

export type GroundingInspectionResult =
  | Readonly<{ status: "SUPPORTED" }>
  | Readonly<{ status: "UNSUPPORTED"; violations: readonly GroundingViolation[] }>;

export interface GroundingInspectionInput {
  readonly candidate: string;
  readonly evidence: TeachingEvidenceContext | null;
  readonly policyDecision: PolicyDecision | null;
  readonly correlationId: string;
}

export interface GroundingDiagnostic {
  readonly status: "BLOCKED";
  readonly category: GroundingViolationCategory;
  readonly claimKind: GroundingClaimKind;
  readonly evidenceLabel: string | null;
  readonly correlationId: string;
}

export interface GroundedFallbackInput {
  readonly evidence: TeachingEvidenceContext | null;
  readonly policyDecision: PolicyDecision | null;
}
