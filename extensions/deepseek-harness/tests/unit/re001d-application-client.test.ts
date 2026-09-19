import assert from "node:assert/strict";
import test from "node:test";

import { Re001dApplicationClient } from "../../src/re001d-application-client.ts";

test("client sends only bounded application data to loopback", async (t) => {
  const calls: Array<{ url: string; body: any }> = [];
  t.mock.method(globalThis, "fetch", async (input: string | URL | Request, init?: RequestInit) => {
    calls.push({ url: String(input), body: JSON.parse(String(init?.body)) });
    return new Response(JSON.stringify({
      protocol: "aia-re001d-application/v1", operation: "prepare",
      workflow_id: "w", request_correlation_id: "r", intent: "RE001D_LITE_SINGLE_POINT",
      status: "CONFIRMATION_REQUIRED", plan: {}, wiring_instructions: "bounded",
    }), { status: 200 });
  });
  const client = new Re001dApplicationClient("http://127.0.0.1:49627", 1000);
  await client.prepare({ workflowId: "w", requestCorrelationId: "r", userText: "request" });
  assert.equal(calls.length, 1);
  assert.equal(calls[0]?.url, "http://127.0.0.1:49627/aia-re001d-application/v1/prepare");
  assert.deepEqual(Object.keys(calls[0]?.body).sort(), ["operation", "protocol", "request_correlation_id", "user_text", "workflow_id"]);
  assert.doesNotMatch(JSON.stringify(calls[0]?.body), /scope|confirmation|authorization|secret|psk/i);
});

test("client rejects non-loopback endpoint and bounds unavailable service", async (t) => {
  assert.throws(() => new Re001dApplicationClient("http://localhost:49627"), /loopback/);
  t.mock.method(globalThis, "fetch", async () => { throw new Error("raw transport failure"); });
  const client = new Re001dApplicationClient(undefined, 50);
  await assert.rejects(client.prepare({ workflowId: "w", requestCorrelationId: "r", userText: "x" }), /re001d_application_unavailable/);
});
