import assert from "node:assert/strict";
import test from "node:test";

import { executeOneShotCandidate, executeOneShotCandidateWithDisposal } from "../../src/model-candidate/one-shot-executor.ts";

const request = Object.freeze({
  schema_id: "aia-harness-publication-model-request/v1" as const,
  request_id: "11111111-1111-4111-8111-111111111111",
  request_digest: `sha256:${"a".repeat(64)}`,
  prompt_profile: "AIA_STRUCTURED_CANDIDATE_V1" as const,
  projection: Object.freeze({ schema_id: "aia-teaching-selection-projection/v1" }),
});

async function* text(value: string): AsyncGenerator<unknown> {
  yield { type: "block-start", index: 0, blockType: "text" };
  yield { type: "text-delta", index: 0, text: value };
  yield { type: "block-end", index: 0, block: { type: "text", text: value } };
  yield { type: "finish", reason: { kind: "stop" } };
}

test("one-shot executor emits raw only after complete stream and raw Egress SAFE", async () => {
  let calls = 0;
  const receipt = await executeOneShotCandidate(request, () => { calls += 1; return text("{}"); });
  assert.equal(calls, 1);
  assert.equal(receipt.status, "CANDIDATE");
  assert.equal(receipt.raw_candidate, "{}");
  assert.equal(receipt.raw_precheck, "SAFE");
});

test("raw Egress rejection and Tool events omit raw text", async () => {
  const unsafe = await executeOneShotCandidate(request, () => text("DEEPSEEK_API_KEY=sk-SYNTHETIC_TEST_VALUE_0000"));
  assert.equal(unsafe.failure_code, "RAW_MODEL_EGRESS_REJECTED");
  assert.equal("raw_candidate" in unsafe, false);
  async function* tool(): AsyncGenerator<unknown> {
    yield { type: "tool-call-delta", index: 0, id: "x", argumentsDelta: "{}" };
  }
  const toolReceipt = await executeOneShotCandidate(request, tool);
  assert.equal(toolReceipt.failure_code, "MODEL_TOOL_EVENT_FORBIDDEN");
  assert.equal("raw_candidate" in toolReceipt, false);
});

test("one-shot deadline aborts and returns no late candidate", async () => {
  async function* delayed(signal: AbortSignal): AsyncGenerator<unknown> {
    await new Promise<void>((resolve) => {
      const timer = setTimeout(resolve, 100);
      signal.addEventListener("abort", () => { clearTimeout(timer); resolve(); }, { once: true });
    });
    if (signal.aborted) return;
    yield* text("{}");
  }
  const receipt = await executeOneShotCandidate(request, delayed, 5);
  assert.equal(receipt.failure_code, "MODEL_REQUEST_TIMEOUT");
  assert.equal("raw_candidate" in receipt, false);
});

test("disposal failure discards an otherwise safe raw candidate", async () => {
  const receipt = await executeOneShotCandidateWithDisposal(
    request,
    () => text("{}"),
    () => Promise.reject(new Error("private cleanup detail")),
  );
  assert.equal(receipt.failure_code, "MODEL_PROCESS_FAILED");
  assert.equal("raw_candidate" in receipt, false);
});
