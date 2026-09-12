import { createHash } from "node:crypto";

import { inspectEgressCandidate } from "../egress/index.ts";
import type { ModelInvocationRequest } from "./contract.ts";
import { collectStructuredCandidate } from "./stream-collector.ts";

export const EXECUTOR_VERSION = "aia-phase8c2b-executor/1" as const;
export const RUNTIME_VERSION = "0.1.3-alpha.1" as const;
export const PROVIDER_ID = "deepseek-official" as const;
export const MODEL_ID = "deepseek-v4-flash" as const;

type DurationBucket = "LT_1S" | "LT_5S" | "LT_20S" | "LT_45S" | "TIMEOUT";

function durationBucket(milliseconds: number): DurationBucket {
  if (milliseconds < 1_000) return "LT_1S";
  if (milliseconds < 5_000) return "LT_5S";
  if (milliseconds < 20_000) return "LT_20S";
  if (milliseconds < 45_000) return "LT_45S";
  return "TIMEOUT";
}

function base(request: ModelInvocationRequest, started: number) {
  return {
    schema_id: "aia-harness-publication-model-receipt/v1",
    request_id: request.request_id,
    request_digest: request.request_digest,
    executor_version: EXECUTOR_VERSION,
    runtime_version: RUNTIME_VERSION,
    provider_id: PROVIDER_ID,
    model_id: MODEL_ID,
    duration_bucket: durationBucket(Date.now() - started),
  } as const;
}

export async function executeOneShotCandidate(
  request: ModelInvocationRequest,
  createStream: (signal: AbortSignal) => AsyncIterable<unknown>,
  deadlineMs = 45_000,
): Promise<Record<string, unknown>> {
  const started = Date.now();
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  let stream: AsyncIterable<unknown>;
  try {
    stream = createStream(controller.signal);
  } catch {
    return failedReceipt(request, started, "MODEL_PROVIDER_UNAVAILABLE", "NOT_STARTED", 0);
  }
  const timeout = new Promise<"TIMEOUT">((resolve) => {
    timer = setTimeout(() => { controller.abort(); resolve("TIMEOUT"); }, deadlineMs);
  });
  const collected = await Promise.race([collectStructuredCandidate(stream), timeout]);
  if (timer !== undefined) clearTimeout(timer);
  if (collected === "TIMEOUT") {
    return failedReceipt(request, started, "MODEL_REQUEST_TIMEOUT", "INCOMPLETE", 1);
  }
  if (collected.status === "FAILED") {
    return failedReceipt(request, started, collected.failureCode, collected.finishCategory, 1);
  }
  const inspection = inspectEgressCandidate({
    candidate: collected.text,
    source: "MODEL_CANDIDATE_RAW",
    correlationId: request.request_id,
    maximumCharacters: 16_384,
  });
  if (inspection.status === "UNSAFE") {
    return failedReceipt(request, started, "RAW_MODEL_EGRESS_REJECTED", "STOP", 1, "REJECTED");
  }
  const bytes = Buffer.byteLength(collected.text, "utf8");
  return Object.freeze({
    ...base(request, started),
    status: "CANDIDATE",
    model_request_count: 1,
    raw_byte_count: bytes,
    raw_digest: `sha256:${createHash("sha256").update(collected.text, "utf8").digest("hex")}`,
    raw_precheck: "SAFE",
    finish_category: "STOP",
    failure_code: null,
    raw_candidate: collected.text,
  });
}

export async function executeOneShotCandidateWithDisposal(
  request: ModelInvocationRequest,
  createStream: (signal: AbortSignal) => AsyncIterable<unknown>,
  dispose: () => Promise<void>,
): Promise<Record<string, unknown>> {
  const started = Date.now();
  const result = await executeOneShotCandidate(request, createStream);
  try {
    await dispose();
  } catch {
    return failedReceipt(
      request,
      started,
      "MODEL_PROCESS_FAILED",
      "ERROR",
      Number(result.model_request_count) === 1 ? 1 : 0,
    );
  }
  return result;
}

export function failedReceipt(
  request: ModelInvocationRequest,
  started: number,
  failureCode: string,
  finishCategory: string,
  modelRequestCount: 0 | 1,
  rawPrecheck: "NOT_RUN" | "REJECTED" = "NOT_RUN",
): Record<string, unknown> {
  return Object.freeze({
    ...base(request, started),
    status: failureCode === "MODEL_REQUEST_CANCELLED" ? "CANCELLED" : "FAILED",
    model_request_count: modelRequestCount,
    raw_byte_count: 0,
    raw_digest: null,
    raw_precheck: rawPrecheck,
    finish_category: finishCategory,
    failure_code: failureCode,
  });
}
