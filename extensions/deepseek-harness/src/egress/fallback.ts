import { inspectEgressCandidate } from "./guard.ts";
import type { EvidenceItem, TeachingEvidenceContext } from "../evidence/index.ts";
import type { SafeAgentFallbackInput } from "./models.ts";

const LAST_RESORT = "Unsafe model output was discarded. No additional operation or measurement was executed.";

export function renderSafeAgentFallback(input: SafeAgentFallbackInput): string {
  const candidate = renderCandidate(input);
  const check = inspectEgressCandidate({
    candidate,
    source: "FINAL_RESPONSE",
    correlationId: input.correlationId,
    knownSensitiveValues: [],
  });
  return check.status === "SAFE" ? candidate : LAST_RESORT;
}

function renderCandidate(input: SafeAgentFallbackInput): string {
  const evidence = input.evidence;
  if (evidence?.executionStatus === "UNKNOWN") {
    return [
      "Execution may have occurred, but the result was not confirmed.",
      "No automatic retry occurred.",
      "An explicit remeasurement decision is required.",
    ].join("\n");
  }
  if (evidence?.executionStatus === "FAILED") {
    return [
      "The hardware operation failed. No measurement value is available.",
      evidence.failure === null ? "Failure code: unavailable" : `Failure code: ${evidence.failure.code}`,
    ].join("\n");
  }
  if (evidence?.executionStatus === "COMPLETED") return completed(evidence, input.violations.length > 0);

  const policy = input.policyDecision;
  if (policy?.decision === "REQUIRE_CONFIRMATION") {
    return [
      "The measurement was not executed.",
      "Physical confirmation is required.",
      `Missing confirmation fields: ${policy.requiredConfirmationFields.join(", ") || "unspecified"}.`,
    ].join("\n");
  }
  if (policy?.decision === "DENY") {
    return "The request was denied by policy. The measurement was not executed.";
  }
  if (input.violations.length > 0) {
    return "Unsafe model output was discarded. No measurement was executed and no retry occurred.";
  }
  return "No trusted measurement evidence is available. No measurement value is reported.";
}

function completed(evidence: TeachingEvidenceContext, discarded: boolean): string {
  const lines = ["Measurement completed."];
  if (discarded) lines.push("Unsafe model-authored prose was discarded; this response is deterministic.");
  addEvidenceSection(lines, "FACT", evidence.facts);
  addEvidenceSection(lines, "ANALYSIS", evidence.analyses);
  if (evidence.quality === "degraded") lines.push("QUALITY: degraded");
  if (evidence.warnings.length > 0) {
    lines.push("WARNINGS:", ...evidence.warnings.map((warning) => `- ${warning}`));
  }
  if (evidence.limitations.length > 0) {
    lines.push("LIMITATIONS:", ...evidence.limitations.map((limitation) => `- ${limitation}`));
  }
  return lines.join("\n");
}

function addEvidenceSection(lines: string[], title: string, items: readonly EvidenceItem[]): void {
  if (items.length === 0) return;
  lines.push(`${title}:`);
  for (const item of items) {
    const value = item.value === null
      ? "unavailable"
      : typeof item.value === "object"
        ? `${formatNumber(item.value.percent)}% (ratio ${formatNumber(item.value.ratio)})`
        : typeof item.value === "number" ? formatNumber(item.value) : item.value;
    const unit = item.unit === null || typeof item.value === "object" ? "" : ` ${item.unit}`;
    lines.push(`- ${item.label}: ${value}${unit} [${item.source}; ${item.quality}]`);
  }
}

function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : String(Number(value.toPrecision(12)));
}

