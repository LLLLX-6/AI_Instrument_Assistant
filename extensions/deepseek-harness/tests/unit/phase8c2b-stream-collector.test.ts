import assert from "node:assert/strict";
import test from "node:test";

import { collectStructuredCandidate } from "../../src/model-candidate/stream-collector.ts";


async function* chunks(values: readonly unknown[]): AsyncGenerator<unknown> {
  for (const value of values) yield value;
}

test("strict collector accepts one exact completed text block", async () => {
  const text = '{"schema_id":"aia-teaching-claim-candidate/v1"}';
  const result = await collectStructuredCandidate(chunks([
    { type: "block-start", index: 0, blockType: "text" },
    { type: "text-delta", index: 0, text: text.slice(0, 12) },
    { type: "text-delta", index: 0, text: text.slice(12) },
    { type: "block-end", index: 0, block: { type: "text", text } },
    { type: "finish", reason: { kind: "stop" } },
  ]));
  assert.equal(result.status, "COMPLETE");
  assert.equal(result.text, text);
});

test("collector preserves split UTF-8 content by exact string accumulation", async () => {
  const text = "PWM 输出：30% ⚙";
  const result = await collectStructuredCandidate(chunks([
    { type: "block-start", index: 0, blockType: "text" },
    { type: "text-delta", index: 0, text: text.slice(0, 4) },
    { type: "text-delta", index: 0, text: text.slice(4) },
    { type: "block-end", index: 0, block: { type: "text", text } },
    { type: "finish", reason: { kind: "stop" } },
  ]));
  assert.equal(result.status, "COMPLETE");
  assert.equal(result.status === "COMPLETE" && result.text, text);
});

test("reasoning, Tool events, mismatch and late chunks fail closed without text", async () => {
  const cases: readonly [string, readonly unknown[]][] = [
    ["MODEL_REASONING_EVENT_FORBIDDEN", [{ type: "reasoning-delta", index: 0, delta: "hidden" }]],
    ["MODEL_TOOL_EVENT_FORBIDDEN", [{ type: "tool-call-delta", index: 0, delta: "{}" }]],
    ["MODEL_STREAM_PROTOCOL_INVALID", [
      { type: "block-start", index: 0, blockType: "text" },
      { type: "text-delta", index: 0, text: "a" },
      { type: "block-end", index: 0, block: { type: "text", text: "b" } },
    ]],
    ["MODEL_STREAM_PROTOCOL_INVALID", [
      { type: "finish", reason: { kind: "stop" } },
      { type: "usage", usage: {} },
    ]],
  ];
  for (const [code, values] of cases) {
    const result = await collectStructuredCandidate(chunks(values));
    assert.equal(result.status, "FAILED");
    assert.equal(result.failureCode, code);
    assert.equal("text" in result, false);
  }
});

test("all incomplete or ambiguous terminal sequences fail without raw text", async () => {
  const complete = (reason: string): readonly unknown[] => [
    { type: "block-start", index: 0, blockType: "text" },
    { type: "text-delta", index: 0, text: "ok" },
    { type: "block-end", index: 0, block: { type: "text", text: "ok" } },
    { type: "finish", reason: { kind: reason } },
  ];
  const cases: readonly unknown[][] = [
    [...complete("max-tokens")], [...complete("aborted")], [...complete("error")],
    [...complete("stop"), { type: "finish", reason: { kind: "stop" } }],
    [...complete("stop"), { type: "text-delta", index: 0, text: "late" }],
    [{ type: "block-start", index: 0, blockType: "text" }],
    [{ type: "block-start", index: 0, blockType: "text" }, { type: "block-start", index: 1, blockType: "text" }],
    [{ type: "block-start", index: 0, blockType: "image" }],
  ];
  for (const values of cases) {
    const result = await collectStructuredCandidate(chunks(values));
    assert.equal(result.status, "FAILED");
    assert.equal("text" in result, false);
  }
});

test("iterator exceptions and UTF-8 byte overflow fail closed", async () => {
  async function* throwing(): AsyncGenerator<unknown> {
    yield { type: "block-start", index: 0, blockType: "text" };
    throw new Error("provider detail must not escape");
  }
  const thrown = await collectStructuredCandidate(throwing());
  assert.deepEqual(thrown, { status: "FAILED", failureCode: "MODEL_STREAM_INCOMPLETE", finishCategory: "ERROR" });
  const overflow = await collectStructuredCandidate(chunks([
    { type: "block-start", index: 0, blockType: "text" },
    { type: "text-delta", index: 0, text: "测".repeat(6000) },
  ]));
  assert.equal(overflow.status, "FAILED");
  assert.equal(overflow.status === "FAILED" && overflow.failureCode, "MODEL_OUTPUT_TOO_LARGE");
});
