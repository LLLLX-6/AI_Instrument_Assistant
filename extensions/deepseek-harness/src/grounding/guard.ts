import type { EvidenceItem, TeachingEvidenceContext } from "../evidence/index.ts";
import type {
  GroundingClaimKind,
  GroundingDiagnostic,
  GroundingInspectionInput,
  GroundingInspectionResult,
  GroundingViolation,
  GroundingViolationCategory,
} from "./models.ts";

const SUPPORTED = Object.freeze({ status: "SUPPORTED" } as const);
const MAXIMUM_CANDIDATE_CHARACTERS = 16_384;
const NUMERIC_CLAIM = /(-?\d+(?:\.\d+)?)\s*[- ]?\s*(kHz|Hz|mV|Vpp|V|%|ms|us|µs|s|points?)(?=$|[\s,.;:)\]])/gi;
const MATERIAL_CONFIDENCE = /\b(?:normal|healthy|reliable|successful(?:ly)?|confirmed|valid)\b|fully reliable/i;
const CAUSAL_OR_CERTAIN_INFERENCE = /\b(?:proves?|caused by|root cause|definitely correct|configuration is correct|timer is correct|must be due to)\b/i;
const BOUNDED_COMPARISON = /appears broadly consistent with the stated .*target/i;
const RAW_ARTIFACT_ACCESS = /\b(?:inspect(?:ed)?|read|access(?:ed)?|examined|analy[sz]ed)\b[^.\n]{0,80}\b(?:raw\s+)?(?:waveform\s+)?samples?\b/i;
const SIMULTANEOUS = /\b(?:simultaneous(?:ly)?|at the same time|single atomic acquisition)\b/i;

type Metric = "frequency" | "duty" | "vpp" | "period" | "mean" | "rms" | "artifact_points" | "unknown";
type ClaimSource = EvidenceItem["source"] | "target" | "unspecified";
type Section = "FACT" | "ANALYSIS" | "INFERENCE" | null;

interface ParsedNumber {
  readonly raw: string;
  readonly value: number;
  readonly unit: string;
  readonly metric: Metric;
  readonly source: ClaimSource;
  readonly section: Section;
  readonly line: string;
}

export function inspectGroundingCandidate(input: GroundingInspectionInput): GroundingInspectionResult {
  if (typeof input.candidate !== "string") throw new TypeError("candidate must be text");
  const violations: GroundingViolation[] = [];
  const candidate = input.candidate;
  const evidence = input.evidence;
  if (candidate.length > MAXIMUM_CANDIDATE_CHARACTERS) {
    add(violations, "UNSUPPORTED_MEASUREMENT_CLAIM", "MEASUREMENT", null);
  }

  if (hasRawArtifactOverclaim(candidate)) add(violations, "ARTIFACT_ACCESS_OVERCLAIM", "ARTIFACT", null);
  if (SIMULTANEOUS.test(candidate) && evidence?.coherence?.instrument_vs_software === "sequential_same_session") {
    add(violations, "FALSE_ATOMICITY_CLAIM", "ATOMICITY", null);
  }
  inspectQuality(candidate, evidence, violations);
  inspectWarnings(candidate, evidence, violations);
  inspectAvailability(candidate, evidence, violations);
  inspectExecutionClaims(candidate, evidence, violations);
  inspectInference(candidate, evidence, violations);

  for (const claim of extractNumericClaims(candidate)) inspectNumber(claim, evidence, violations);

  if (violations.length === 0) return SUPPORTED;
  return Object.freeze({ status: "UNSUPPORTED", violations: Object.freeze(violations) });
}

export function toGroundingDiagnostic(
  violation: GroundingViolation,
  correlationId: string,
): GroundingDiagnostic {
  return Object.freeze({
    status: "BLOCKED",
    category: violation.category,
    claimKind: violation.claimKind,
    evidenceLabel: violation.evidenceLabel,
    correlationId: boundedCorrelation(correlationId),
  });
}

function inspectNumber(
  claim: ParsedNumber,
  evidence: TeachingEvidenceContext | null,
  violations: GroundingViolation[],
): void {
  if (claim.metric === "artifact_points") {
    if (evidence?.artifact !== null && evidence?.artifact !== undefined
      && numberMatches(claim.raw, claim.unit, evidence.artifact.pointCount, "points")) return;
    add(violations, "UNSUPPORTED_NUMERIC_CLAIM", "NUMERIC", "waveform point count");
    return;
  }
  if (claim.metric === "unknown") {
    add(violations, "UNKNOWN_EVIDENCE_REFERENCE", "REFERENCE", null);
    return;
  }
  if (evidence === null) {
    add(violations, "UNSUPPORTED_MEASUREMENT_CLAIM", "MEASUREMENT", metricLabel(claim.metric));
    return;
  }
  if (claim.source === "target") {
    if (!targetClaimMatchesGoal(claim, evidence.requestedGoal)) {
      add(violations, "UNSUPPORTED_NUMERIC_CLAIM", "NUMERIC", metricLabel(claim.metric));
    }
    return;
  }
  if (evidence.executionStatus !== "COMPLETED") {
    add(violations, "UNSUPPORTED_MEASUREMENT_CLAIM", "MEASUREMENT", metricLabel(claim.metric));
    return;
  }

  const items = allEvidence(evidence).filter((item) => evidenceMetric(item) === claim.metric);
  if (items.length === 0) {
    add(violations, "UNKNOWN_EVIDENCE_REFERENCE", "REFERENCE", metricLabel(claim.metric));
    return;
  }
  const available = items.filter((item) => item.value !== null && item.quality !== "unavailable");
  if (available.length === 0) {
    add(violations, "FALSE_AVAILABILITY_CLAIM", "AVAILABILITY", metricLabel(claim.metric));
    return;
  }

  if (claim.source === "unspecified") {
    add(
      violations,
      /\b(?:target|expected|design|stated)\b/i.test(claim.line)
        ? "UNSUPPORTED_NUMERIC_CLAIM"
        : "UNSUPPORTED_MEASUREMENT_CLAIM",
      "SOURCE",
      metricLabel(claim.metric),
    );
    return;
  }
  const intended = available.filter((item) => item.source === claim.source);
  const intendedMatch = intended.find((item) => itemMatches(claim, item));
  if (intendedMatch !== undefined) {
    const expectedKind = claim.source === "software_analysis" ? "ANALYSIS" : "FACT";
    if (claim.section !== null && claim.section !== expectedKind) {
      add(violations, "SOURCE_ATTRIBUTION_MISMATCH", "SOURCE", intendedMatch.label);
    }
    return;
  }
  const wrongSourceMatch = available.some((item) => item.source !== claim.source && itemMatches(claim, item));
  if (wrongSourceMatch) {
    add(violations, "SOURCE_ATTRIBUTION_MISMATCH", "SOURCE", metricLabel(claim.metric));
    return;
  }
  if (intended.length === 0) {
    add(violations, "SOURCE_ATTRIBUTION_MISMATCH", "SOURCE", metricLabel(claim.metric));
    return;
  }
  add(violations, "UNSUPPORTED_NUMERIC_CLAIM", "NUMERIC", intended[0]?.label ?? metricLabel(claim.metric));
}

function inspectAvailability(
  candidate: string,
  evidence: TeachingEvidenceContext | null,
  violations: GroundingViolation[],
): void {
  const lower = candidate.toLowerCase();
  for (const reference of [
    ["instrument frequency", "instrument", "frequency"],
    ["software frequency", "software_analysis", "frequency"],
    ["software duty cycle", "software_analysis", "duty"],
    ["instrument vpp", "instrument", "vpp"],
    ["software vpp", "software_analysis", "vpp"],
  ] as const) {
    const [phrase, source, metric] = reference;
    const availabilityClaim = new RegExp(`(?:${escapeRegex(phrase)}[^.\\n]{0,80}(?:unavailable|not available)|(?:unavailable|not available)[^.\\n]{0,80}${escapeRegex(phrase)})`, "i");
    if (!availabilityClaim.test(lower)) continue;
    const item = evidence === null ? undefined : allEvidence(evidence)
      .find((value) => value.source === source && evidenceMetric(value) === metric);
    if (item === undefined || (item.value !== null && item.quality !== "unavailable")) {
      add(violations, "FALSE_AVAILABILITY_CLAIM", "AVAILABILITY", phrase);
    }
  }
}

function inspectQuality(
  candidate: string,
  evidence: TeachingEvidenceContext | null,
  violations: GroundingViolation[],
): void {
  if (evidence === null) return;
  const claimsGood = /\bquality\s*:\s*good\b|\b(?:fully reliable|measurement is reliable|normal signal|healthy signal)\b/i.test(candidate);
  const claimsSuccess = /\bmeasurement (?:completed )?successfully\b/i.test(candidate);
  if ((claimsGood || claimsSuccess) && evidence.quality !== "good") {
    add(violations, "QUALITY_MISREPRESENTATION", "QUALITY", null);
  }
  if (/\bquality\s*:\s*degraded\b/i.test(candidate) && evidence.quality !== "degraded") {
    add(violations, "QUALITY_MISREPRESENTATION", "QUALITY", null);
  }
  if (/\bquality\s*:\s*failed\b/i.test(candidate) && evidence.quality !== "failed") {
    add(violations, "QUALITY_MISREPRESENTATION", "QUALITY", null);
  }
}

function inspectWarnings(
  candidate: string,
  evidence: TeachingEvidenceContext | null,
  violations: GroundingViolation[],
): void {
  if (evidence?.quality !== "degraded" || evidence.warnings.length === 0 || !MATERIAL_CONFIDENCE.test(candidate)) return;
  if (evidence.warnings.some((warning) => !candidate.toLowerCase().includes(warning.toLowerCase()))) {
    add(violations, "WARNING_OMISSION_MATERIAL", "WARNING", null);
  }
}

function inspectExecutionClaims(
  candidate: string,
  evidence: TeachingEvidenceContext | null,
  violations: GroundingViolation[],
): void {
  const completed = /\b(?:measurement|hardware operation)\s+(?:completed|succeeded|was successful)\b/i.test(candidate);
  const artifactCaptured = /\bwaveform artifact was captured\b/i.test(candidate);
  if (completed && evidence?.executionStatus !== "COMPLETED") {
    add(violations, "UNSUPPORTED_MEASUREMENT_CLAIM", "MEASUREMENT", null);
  }
  if (artifactCaptured && evidence?.artifact === null) {
    add(violations, "UNSUPPORTED_MEASUREMENT_CLAIM", "ARTIFACT", "waveform artifact");
  }
}

function inspectInference(
  candidate: string,
  evidence: TeachingEvidenceContext | null,
  violations: GroundingViolation[],
): void {
  if (CAUSAL_OR_CERTAIN_INFERENCE.test(candidate)) {
    add(violations, "UNSUPPORTED_INFERENCE", "INFERENCE", null);
  }
  const lines = candidate.split(/\r?\n/);
  for (const line of lines) {
    if (!/^\s*INFERENCE\s*:/i.test(line)) continue;
    if (!BOUNDED_COMPARISON.test(line) || evidence === null || !boundedComparisonSupported(line, evidence)) {
      add(violations, "UNSUPPORTED_INFERENCE", "INFERENCE", null);
    }
  }
}

function boundedComparisonSupported(line: string, evidence: TeachingEvidenceContext): boolean {
  if (evidence.executionStatus !== "COMPLETED" || evidence.quality !== "good") return false;
  const targets = extractNumericClaims(line).filter((claim) => claim.source === "target");
  if (targets.length === 0 || targets.some((claim) => !targetClaimMatchesGoal(claim, evidence.requestedGoal))) return false;
  return targets.every((target) => {
    const matches = allEvidence(evidence).filter((item) => evidenceMetric(item) === target.metric && item.value !== null);
    return matches.some((item) => itemCoarselyMatchesTarget(target, item));
  });
}

function extractNumericClaims(candidate: string): ParsedNumber[] {
  const claims: ParsedNumber[] = [];
  let section: Section = null;
  for (const originalLine of candidate.split(/\r?\n/)) {
    const line = originalLine.trim();
    if (/^(?:OBSERVED\s+)?FACTS?\s*:\s*$/i.test(line)) { section = "FACT"; continue; }
    if (/^ANALYSES?\s*:\s*$/i.test(line) || /^ANALYSIS\s*:\s*$/i.test(line)) { section = "ANALYSIS"; continue; }
    if (/^INFERENCES?\s*:\s*$/i.test(line)) { section = "INFERENCE"; continue; }
    let lineSection = section;
    if (/^FACT\s*:/i.test(line)) lineSection = "FACT";
    if (/^ANALYSIS\s*:/i.test(line)) lineSection = "ANALYSIS";
    if (/^INFERENCE\s*:/i.test(line)) lineSection = "INFERENCE";
    NUMERIC_CLAIM.lastIndex = 0;
    for (let match = NUMERIC_CLAIM.exec(line); match !== null; match = NUMERIC_CLAIM.exec(line)) {
      const raw = match[1]!;
      const unit = match[2]!;
      const local = localClause(line, match.index, match[0].length);
      claims.push(Object.freeze({
        raw,
        value: Number(raw),
        unit,
        metric: inferMetric(local, unit),
        source: inferSource(local, lineSection),
        section: lineSection,
        line,
      }));
    }
  }
  return claims;
}

function inferMetric(text: string, unit: string): Metric {
  const lower = text.toLowerCase();
  if (/points?/i.test(unit)) return "artifact_points";
  if (/rise\s*time|fall\s*time|overshoot|jitter/i.test(lower)) return "unknown";
  if (/khz|hz/i.test(unit)) return "frequency";
  if (unit === "%" || /duty/i.test(lower)) return "duty";
  if (/vpp/i.test(unit)) return "vpp";
  if (/vpp|peak[- ]?to[- ]?peak/i.test(lower)) return "vpp";
  if (/\brms\b/i.test(lower)) return "rms";
  if (/\bmean\b|average voltage/i.test(lower)) return "mean";
  if (/period/i.test(lower)) return "period";
  return "unknown";
}

function inferSource(text: string, section: Section): ClaimSource {
  const lower = text.toLowerCase();
  const bracket = /\[(instrument|software_analysis|simulated)\s*;/i.exec(text)?.[1]?.toLowerCase();
  if (bracket === "instrument" || bracket === "software_analysis" || bracket === "simulated") return bracket;
  const target = /\b(?:target|expected|design|stated)\b/i.test(lower);
  const measured = /\b(?:measured|measurement|observed|found)\b/i.test(lower);
  if (target && (!measured || section === "INFERENCE")) return "target";
  if (/\b(?:software|analysis|computed|algorithm)\b/i.test(lower)) return "software_analysis";
  if (/\bsimulat(?:ed|ion)\b/i.test(lower)) return "simulated";
  if (/\b(?:instrument|oscilloscope|scope)\b/i.test(lower)) return "instrument";
  if (section === "ANALYSIS") return "software_analysis";
  if (section === "FACT") return "instrument";
  return "unspecified";
}

function localClause(line: string, index: number, length: number): string {
  const leftBoundary = Math.max(line.lastIndexOf(".", index), line.lastIndexOf(";", index), line.lastIndexOf("\n", index));
  const rightDot = line.indexOf(".", index + length);
  const rightSemicolon = line.indexOf(";", index + length);
  const candidates = [rightDot, rightSemicolon].filter((value) => value >= 0);
  const rightBoundary = candidates.length === 0 ? line.length : Math.min(...candidates);
  return line.slice(leftBoundary + 1, rightBoundary);
}

function itemMatches(claim: ParsedNumber, item: EvidenceItem): boolean {
  const value = numericEvidenceValue(item, claim.metric);
  return value !== null && item.unit !== null && numberMatches(claim.raw, claim.unit, value, item.unit);
}

function itemCoarselyMatchesTarget(target: ParsedNumber, item: EvidenceItem): boolean {
  const value = numericEvidenceValue(item, target.metric);
  if (value === null || item.unit === null) return false;
  return numberMatches(target.raw, target.unit, value, item.unit);
}

function numericEvidenceValue(item: EvidenceItem, metric: Metric): number | null {
  if (typeof item.value === "number") return item.value;
  if (item.value !== null && typeof item.value === "object" && metric === "duty") return item.value.percent;
  return null;
}

function numberMatches(candidateRaw: string, candidateUnit: string, evidenceValue: number, evidenceUnit: string): boolean {
  const converted = convert(evidenceValue, evidenceUnit, candidateUnit);
  if (converted === null) return false;
  const decimals = candidateRaw.includes(".") ? candidateRaw.length - candidateRaw.indexOf(".") - 1 : 0;
  if (decimals > 15) return false;
  return Number(converted.toFixed(decimals)) === Number(candidateRaw);
}

function convert(value: number, from: string, to: string): number | null {
  const units: Readonly<Record<string, readonly [string, number]>> = Object.freeze({
    hz: ["frequency", 1], khz: ["frequency", 1_000],
    v: ["voltage", 1], vpp: ["voltage", 1], mv: ["voltage", 0.001],
    "%": ["duty", 1],
    s: ["time", 1], ms: ["time", 0.001], us: ["time", 0.000001], "µs": ["time", 0.000001],
    point: ["points", 1], points: ["points", 1],
  });
  const source = units[from.toLowerCase()];
  const target = units[to.toLowerCase()];
  if (source === undefined || target === undefined || source[0] !== target[0]) return null;
  return value * source[1] / target[1];
}

function targetClaimMatchesGoal(claim: ParsedNumber, goal: string): boolean {
  return extractNumericClaims(goal).some((target) => target.metric === claim.metric
    && numberMatches(claim.raw, claim.unit, target.value, target.unit));
}

function allEvidence(evidence: TeachingEvidenceContext): readonly EvidenceItem[] {
  return [...evidence.facts, ...evidence.analyses, ...evidence.inferences];
}

function evidenceMetric(item: EvidenceItem): Metric {
  const lower = item.label.toLowerCase();
  if (lower.includes("duty")) return "duty";
  if (lower.includes("frequency")) return "frequency";
  if (lower.includes("vpp") || lower.includes("peak-to-peak")) return "vpp";
  if (lower.includes("period")) return "period";
  if (lower.includes("mean")) return "mean";
  if (lower.includes("rms")) return "rms";
  return "unknown";
}

function metricLabel(metric: Metric): string | null {
  switch (metric) {
    case "frequency": return "frequency";
    case "duty": return "duty cycle";
    case "vpp": return "Vpp";
    case "period": return "period";
    case "mean": return "mean";
    case "rms": return "RMS";
    case "artifact_points": return "waveform point count";
    case "unknown": return null;
  }
}

function add(
  violations: GroundingViolation[],
  category: GroundingViolationCategory,
  claimKind: GroundingClaimKind,
  evidenceLabel: string | null,
): void {
  if (violations.some((value) => value.category === category
    && value.claimKind === claimKind && value.evidenceLabel === evidenceLabel)) return;
  violations.push(Object.freeze({ category, claimKind, evidenceLabel: boundedLabel(evidenceLabel) }));
}

function boundedLabel(value: string | null): string | null {
  if (value === null) return null;
  return value.length <= 64 && /^[A-Za-z0-9 _-]+$/.test(value) ? value : null;
}

function boundedCorrelation(value: string): string {
  return typeof value === "string" && value.trim() && value.length <= 256 ? value.trim() : "unscoped";
}

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function hasRawArtifactOverclaim(candidate: string): boolean {
  return candidate.split(/[.\n]/).some((sentence) => {
    if (!RAW_ARTIFACT_ACCESS.test(sentence)) return false;
    return !/\b(?:did not|does not|cannot|can not|never)\s+(?:inspect|read|access|examine|analy[sz]e)\b/i.test(sentence);
  });
}
