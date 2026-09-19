import type { Context } from "@deepseek-ai/cordis";
import type { GenerateOptions, StreamChunk } from "@deepseek-ai/dsh-llm";

import {
  type AgentEgressStateStore,
  inspectEgressCandidate,
  renderSafeAgentFallback,
  toEgressDiagnostic,
  type EgressDiagnostic,
  type EgressViolation,
  type TrustedAgentEgressState,
} from "../egress/index.ts";
import {
  inspectGroundingCandidate,
  renderGroundedFallback,
  toGroundingDiagnostic,
  type GroundingDiagnostic,
} from "../grounding/index.ts";

const LAST_RESORT = "The model response was discarded because it could not be safely grounded. No additional operation or measurement was executed.";

export function installHarnessAgentEgressBoundary(
  ctx: Context,
  state: AgentEgressStateStore,
  diagnostic: (value: EgressDiagnostic) => void = () => undefined,
  groundingDiagnostic: (value: GroundingDiagnostic) => void = () => undefined,
  options: { relaxReasoningInspection?: boolean } = {},
): () => void {
  return ctx.on("llm/stream", (generateOptions, next) => guardedStream(
    generateOptions,
    next,
    state,
    diagnostic,
    groundingDiagnostic,
    options.relaxReasoningInspection ?? false,
  ));
}

async function* guardedStream(
  options: GenerateOptions,
  next: () => AsyncIterable<StreamChunk>,
  state: AgentEgressStateStore,
  diagnostic: (value: EgressDiagnostic) => void,
  groundingDiagnostic: (value: GroundingDiagnostic) => void,
  relaxReasoningInspection: boolean = false,
): AsyncIterable<StreamChunk> {
  const chunks: StreamChunk[] = [];
  for await (const chunk of next()) chunks.push(chunk);
  const correlationId = String(options.sessionId ?? "unscoped");
  const egressViolations = inspectChunks(chunks, correlationId, relaxReasoningInspection);
  const hasToolCall = chunks.some((chunk) => chunk.type === "block-end" && chunk.block.type === "tool-call");
  const trusted = state.snapshot(correlationId);

  if (egressViolations.length > 0) {
    for (const violation of egressViolations) diagnostic(toEgressDiagnostic(violation));
    const egressFallback = renderSafeAgentFallback({
      correlationId,
      violations: egressViolations.map((violation) => violation.category),
      policyDecision: trusted.policyDecision,
      evidence: trusted.evidence,
    });
    const fallback = verifiedFallback(egressFallback, correlationId, trusted);
    state.clear(correlationId);
    yield* replacementChunks(chunks, fallback);
    return;
  }

  if (hasToolCall) {
    yield* chunks;
    return;
  }

  const grounding = inspectGroundingCandidate({
    candidate: finalText(chunks),
    evidence: trusted.evidence,
    policyDecision: trusted.policyDecision,
    correlationId,
  });
  if (grounding.status === "SUPPORTED") {
    state.clear(correlationId);
    yield* chunks;
    return;
  }

  for (const violation of grounding.violations) {
    groundingDiagnostic(toGroundingDiagnostic(violation, correlationId));
  }
  const fallback = verifiedFallback(renderGroundedFallback(trusted), correlationId, trusted);
  state.clear(correlationId);
  yield* replacementChunks(chunks, fallback);
}

function verifiedFallback(
  candidate: string,
  correlationId: string,
  trusted: TrustedAgentEgressState,
): string {
  if (fallbackPassesBoth(candidate, correlationId, trusted)) return candidate;
  const grounded = renderGroundedFallback(trusted);
  return fallbackPassesBoth(grounded, correlationId, trusted) ? grounded : LAST_RESORT;
}

function fallbackPassesBoth(
  candidate: string,
  correlationId: string,
  trusted: TrustedAgentEgressState,
): boolean {
  const egress = inspectEgressCandidate({
    candidate,
    source: "FINAL_RESPONSE",
    correlationId,
    knownSensitiveValues: [],
  });
  if (egress.status !== "SAFE") return false;
  return inspectGroundingCandidate({
    candidate,
    evidence: trusted.evidence,
    policyDecision: trusted.policyDecision,
    correlationId,
  }).status === "SUPPORTED";
}

function* replacementChunks(chunks: readonly StreamChunk[], fallback: string): Iterable<StreamChunk> {
  yield { type: "block-start", index: 0, blockType: "text" };
  yield { type: "text-delta", index: 0, text: fallback };
  yield { type: "block-end", index: 0, block: { type: "text", text: fallback } };
  const usage = chunks.findLast((chunk) => chunk.type === "usage");
  if (usage?.type === "usage") yield usage;
  yield { type: "finish", reason: { kind: "stop" } };
}

function finalText(chunks: readonly StreamChunk[]): string {
  return chunks
    .filter((chunk) => chunk.type === "block-end" && chunk.block.type === "text")
    .map((chunk) => chunk.type === "block-end" && chunk.block.type === "text" ? chunk.block.text : "")
    .join("\n");
}

function inspectChunks(
  chunks: readonly StreamChunk[],
  correlationId: string,
  relaxReasoningInspection: boolean = false,
): EgressViolation[] {
  // Trust boundary: a reasoning block is model-internal intermediate state.
  // It is consumed by neither the tool dispatch path (which reads tool-call
  // arguments only) nor the final-response grounding path (which reads text
  // blocks only), so skipping its egress inspection cannot mint hardware
  // authority or alter a published response. Final text and tool arguments
  // are always inspected; `relaxReasoningInspection` is a NON-PRODUCTION,
  // developer-local opt-in (AIA_RELAX_EGRESS_REASONING) that affects only
  // reasoning-block hygiene inspection.
  const violations: EgressViolation[] = [];
  for (const chunk of chunks) {
    if (chunk.type !== "block-end") continue;
    const block = chunk.block;
    if (relaxReasoningInspection && block.type === "reasoning") continue;
    const candidate = block.type === "tool-call" ? block.arguments : block.type === "text" || block.type === "reasoning" ? block.text : null;
    if (candidate === null) continue;
    const result = inspectEgressCandidate({
      candidate,
      source: block.type === "tool-call" ? "TOOL_ARGUMENTS" : block.type === "text" ? "FINAL_RESPONSE" : "INTERMEDIATE_TEXT",
      correlationId,
      knownSensitiveValues: [],
      maximumCharacters: block.type === "tool-call" ? 4_096 : 16_384,
    });
    if (result.status === "UNSAFE") violations.push(...result.violations);
  }
  return violations;
}
