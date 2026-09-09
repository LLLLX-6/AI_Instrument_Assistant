import type { Context } from "@deepseek-ai/cordis";
import type { GenerateOptions, StreamChunk } from "@deepseek-ai/dsh-llm";

import {
  type AgentEgressStateStore,
  inspectEgressCandidate,
  renderSafeAgentFallback,
  toEgressDiagnostic,
  type EgressDiagnostic,
  type EgressViolation,
} from "../egress/index.ts";

export function installHarnessAgentEgressBoundary(
  ctx: Context,
  state: AgentEgressStateStore,
  diagnostic: (value: EgressDiagnostic) => void = () => undefined,
): () => void {
  return ctx.on("llm/stream", (options, next) => guardedStream(options, next, state, diagnostic));
}

async function* guardedStream(
  options: GenerateOptions,
  next: () => AsyncIterable<StreamChunk>,
  state: AgentEgressStateStore,
  diagnostic: (value: EgressDiagnostic) => void,
): AsyncIterable<StreamChunk> {
  const chunks: StreamChunk[] = [];
  for await (const chunk of next()) chunks.push(chunk);
  const correlationId = String(options.sessionId ?? "unscoped");
  const violations = inspectChunks(chunks, correlationId);
  const hasToolCall = chunks.some((chunk) => chunk.type === "block-end" && chunk.block.type === "tool-call");
  if (violations.length === 0) {
    if (!hasToolCall) state.clear(correlationId);
    yield* chunks;
    return;
  }

  for (const violation of violations) diagnostic(toEgressDiagnostic(violation));
  const trusted = state.snapshot(correlationId);
  const fallback = renderSafeAgentFallback({
    correlationId,
    violations: violations.map((violation) => violation.category),
    policyDecision: trusted.policyDecision,
    evidence: trusted.evidence,
  });
  state.clear(correlationId);
  yield { type: "block-start", index: 0, blockType: "text" };
  yield { type: "text-delta", index: 0, text: fallback };
  yield { type: "block-end", index: 0, block: { type: "text", text: fallback } };
  const usage = chunks.findLast((chunk) => chunk.type === "usage");
  if (usage?.type === "usage") yield usage;
  yield { type: "finish", reason: { kind: "stop" } };
}

function inspectChunks(chunks: readonly StreamChunk[], correlationId: string): EgressViolation[] {
  const violations: EgressViolation[] = [];
  for (const chunk of chunks) {
    if (chunk.type !== "block-end") continue;
    const block = chunk.block;
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

