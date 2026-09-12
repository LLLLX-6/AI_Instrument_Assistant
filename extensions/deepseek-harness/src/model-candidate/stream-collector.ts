const MAX_OUTPUT_BYTES = 16_384;

export type CollectorFailureCode =
  | "MODEL_STREAM_INCOMPLETE"
  | "MODEL_STREAM_PROTOCOL_INVALID"
  | "MODEL_OUTPUT_TOO_LARGE"
  | "MODEL_TOOL_EVENT_FORBIDDEN"
  | "MODEL_REASONING_EVENT_FORBIDDEN";

export type CollectorResult =
  | Readonly<{ status: "COMPLETE"; text: string; finishCategory: "STOP" }>
  | Readonly<{ status: "FAILED"; failureCode: CollectorFailureCode; finishCategory: string }>;

function failed(failureCode: CollectorFailureCode, finishCategory = "PROTOCOL_INVALID"): CollectorResult {
  return Object.freeze({ status: "FAILED", failureCode, finishCategory });
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

/** Dedicated fail-closed collector. It intentionally does not use BlockAssembler. */
export async function collectStructuredCandidate(source: AsyncIterable<unknown>): Promise<CollectorResult> {
  let index: number | null = null;
  let text = "";
  let ended = false;
  let finished = false;
  let usageSeen = false;
  try {
    for await (const value of source) {
      const chunk = record(value);
      if (chunk === null || typeof chunk.type !== "string") return failed("MODEL_STREAM_PROTOCOL_INVALID");
      if (finished) return failed("MODEL_STREAM_PROTOCOL_INVALID");
      if (chunk.type === "reasoning-delta" || (chunk.type === "block-start" && chunk.blockType === "reasoning")) {
        return failed("MODEL_REASONING_EVENT_FORBIDDEN");
      }
      if (chunk.type === "tool-call-delta" || (chunk.type === "block-start" && chunk.blockType === "tool-call")) {
        return failed("MODEL_TOOL_EVENT_FORBIDDEN", "TOOL_CALLS");
      }
      if (chunk.type === "block-start") {
        if (index !== null || chunk.blockType !== "text" || chunk.index !== 0) {
          return failed("MODEL_STREAM_PROTOCOL_INVALID");
        }
        index = 0;
      } else if (chunk.type === "text-delta") {
        if (index !== 0 || ended || chunk.index !== 0 || typeof chunk.text !== "string") {
          return failed("MODEL_STREAM_PROTOCOL_INVALID");
        }
        text += chunk.text;
        if (Buffer.byteLength(text, "utf8") > MAX_OUTPUT_BYTES) return failed("MODEL_OUTPUT_TOO_LARGE");
      } else if (chunk.type === "block-end") {
        const block = record(chunk.block);
        if (block?.type === "reasoning") return failed("MODEL_REASONING_EVENT_FORBIDDEN");
        if (block?.type === "tool-call" || block?.type === "tool-result") return failed("MODEL_TOOL_EVENT_FORBIDDEN", "TOOL_CALLS");
        if (index !== 0 || ended || chunk.index !== 0 || block?.type !== "text" || block.text !== text) {
          return failed("MODEL_STREAM_PROTOCOL_INVALID");
        }
        ended = true;
      } else if (chunk.type === "usage") {
        const usage = record(chunk.usage);
        if (usageSeen || usage === null) return failed("MODEL_STREAM_PROTOCOL_INVALID");
        try {
          if (Buffer.byteLength(JSON.stringify(usage), "utf8") > 2_048) return failed("MODEL_STREAM_PROTOCOL_INVALID");
        } catch {
          return failed("MODEL_STREAM_PROTOCOL_INVALID");
        }
        usageSeen = true;
      } else if (chunk.type === "finish") {
        const reason = record(chunk.reason);
        if (!ended || finished || typeof reason?.kind !== "string") return failed("MODEL_STREAM_PROTOCOL_INVALID");
        finished = true;
        if (reason.kind === "tool-calls") return failed("MODEL_TOOL_EVENT_FORBIDDEN", "TOOL_CALLS");
        if (reason.kind !== "stop") return failed("MODEL_STREAM_INCOMPLETE", reason.kind.toUpperCase().replaceAll("-", "_"));
      } else {
        return failed("MODEL_STREAM_PROTOCOL_INVALID");
      }
    }
  } catch {
    return failed("MODEL_STREAM_INCOMPLETE", "ERROR");
  }
  if (!finished || !ended || text.length === 0) return failed("MODEL_STREAM_INCOMPLETE", "INCOMPLETE");
  return Object.freeze({ status: "COMPLETE", text, finishCategory: "STOP" });
}
