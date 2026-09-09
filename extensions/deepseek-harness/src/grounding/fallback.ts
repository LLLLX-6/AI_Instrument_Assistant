import type { EvidenceItem, TeachingEvidenceContext } from "../evidence/index.ts";
import type { GroundedFallbackInput } from "./models.ts";

export function renderGroundedFallback(input: GroundedFallbackInput): string {
  const evidence = input.evidence;
  if (evidence === null) {
    if (input.policyDecision?.decision === "DENY") return "The request was denied by policy. No measurement was executed.";
    if (input.policyDecision?.decision === "REQUIRE_CONFIRMATION") {
      return "The measurement was not executed. Physical confirmation is required.";
    }
    return "No trusted measurement evidence is available. No measurement value is reported.";
  }
  if (evidence.executionStatus !== "COMPLETED") return failureFallback(evidence);

  const lines: string[] = ["OBSERVED FACTS:"];
  if (evidence.facts.some((item) => item.source === "simulated")) {
    lines.unshift("EVIDENCE MODE: SIMULATED OBSERVATION", "SIMULATION LIMIT: this is not a real oscilloscope measurement.");
  }
  addItems(lines, evidence.facts);
  lines.push("ANALYSIS:");
  addItems(lines, evidence.analyses);
  lines.push(`QUALITY: ${evidence.quality ?? "unavailable"}`);
  if (evidence.warnings.length === 0) lines.push("WARNINGS: none");
  else lines.push("WARNINGS:", ...evidence.warnings.map((warning) => `- ${warning}`));
  if (evidence.coherence !== null) {
    const coherence: string[] = [];
    if (evidence.coherence.software_observations === "same_artifact") {
      coherence.push("software observations share the same artifact");
    }
    if (evidence.coherence.instrument_vs_software === "sequential_same_session") {
      coherence.push("instrument and software observations were collected sequentially within the same session");
    }
    if (coherence.length > 0) lines.push(`COHERENCE: ${coherence.join("; ")}.`);
  }
  if (evidence.artifact !== null) {
    lines.push(`ARTIFACT: a ${evidence.artifact.pointCount}-point waveform artifact was captured; samples remain opaque.`);
    lines.push("RAW SAMPLE ACCESS: the Agent did not inspect samples.");
  }
  if (evidence.limitations.length > 0) {
    lines.push("LIMITATIONS:", ...evidence.limitations.map((limitation) => `- ${limitation}`));
  }
  return lines.join("\n");
}

function failureFallback(evidence: TeachingEvidenceContext): string {
  const lines = [
    `EXECUTION STATUS: ${evidence.executionStatus.toLowerCase()}`,
    "No measurement value is available.",
  ];
  if (evidence.failure !== null) lines.push(`Failure code: ${evidence.failure.code}`);
  if (evidence.requiredUserAction === "EXPLICIT_REMEASURE_DECISION") {
    lines.push("An explicit remeasurement decision is required; no automatic retry occurred.");
  }
  if (evidence.limitations.length > 0) {
    lines.push("LIMITATIONS:", ...evidence.limitations.map((limitation) => `- ${limitation}`));
  }
  return lines.join("\n");
}

function addItems(lines: string[], items: readonly EvidenceItem[]): void {
  if (items.length === 0) {
    lines.push("- none");
    return;
  }
  for (const item of items) {
    const value = item.value === null
      ? "unavailable"
      : typeof item.value === "object"
        ? `${formatNumber(item.value.percent)}%`
        : typeof item.value === "number"
          ? `${formatNumber(item.value)}${item.unit === null ? "" : ` ${item.unit}`}`
          : item.value;
    lines.push(`- ${item.label}: ${value} [${item.source}; ${item.quality}]`);
  }
}

function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : String(Number(value.toPrecision(12)));
}
