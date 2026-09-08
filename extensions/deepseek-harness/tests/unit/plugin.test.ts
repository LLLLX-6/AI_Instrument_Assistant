import assert from "node:assert/strict";
import test from "node:test";

import { Context } from "@deepseek-ai/cordis";
import { ToolCallId } from "@deepseek-ai/dsh-llm";
import SystemPrompt from "@deepseek-ai/dsh-system-prompt";
import ToolRuntime from "@deepseek-ai/dsh-tools";

import { applyWithDependencies, inject, name } from "../../src/index.ts";
import { AdapterFailure, safeAdapterFailure } from "../../src/ipc/errors.ts";
import { HARDWARE_TOOL_CONTRACTS } from "../../src/generated/hardware-tools.generated.ts";
import { DEGRADED_PWM_RESULT, HARDWARE_ERROR_RESULT, STATUS_RESULT } from "../support/canonical-results.ts";

class FakeClient {
  started = 0;
  disposed = 0;
  readonly calls: Array<{ operation: string; arguments: unknown; signal: AbortSignal }> = [];
  result: unknown = STATUS_RESULT;

  start(): void { this.started += 1; }
  async dispose(): Promise<void> { this.disposed += 1; }
  async invoke(operation: string, args: unknown, signal: AbortSignal): Promise<unknown> {
    this.calls.push({ operation, arguments: args, signal });
    if (this.result instanceof Error) throw this.result;
    return this.result;
  }
}

async function setup(client: FakeClient) {
  const ctx = new Context();
  await ctx.plugin(SystemPrompt);
  await ctx.plugin(ToolRuntime);
  applyWithDependencies(ctx, {}, { createClient: () => client });
  return ctx;
}

test("plugin identity and injection follow the reviewed Harness shape", () => {
  assert.equal(name, "aia-hardware-tools");
  assert.deepEqual(inject, ["tools"]);
});

test("apply registers exactly five projected static tools", async () => {
  const client = new FakeClient();
  const ctx = await setup(client);
  const schemas = ctx.tools.schemas();
  assert.deepEqual(schemas.map((item) => item.name).sort(), HARDWARE_TOOL_CONTRACTS.map((item) => item.harnessName).sort());
  for (const contract of HARDWARE_TOOL_CONTRACTS) {
    assert.deepEqual(ctx.tools.get(contract.harnessName)?.parameters, contract.parametersSchema);
    assert.deepEqual(ctx.tools.get(contract.harnessName)?.output.schema, contract.outputSchema);
    assert.equal(ctx.tools.get(contract.harnessName)?.isConcurrencySafe, undefined);
    assert.equal(ctx.tools.get(contract.harnessName)?.timeoutMs, undefined);
  }
  assert.equal(client.started, 1);
  await ctx.fiber.dispose();
  assert.equal(client.disposed, 1);
});

test("canonical ok=false remains a successful structured Tool value", async () => {
  const client = new FakeClient();
  client.result = HARDWARE_ERROR_RESULT;
  const ctx = await setup(client);
  const result = await ctx.tools.execute({
    signal: new AbortController().signal,
    callId: ToolCallId("phase7b4-error"),
    name: "hardware_measure_vpp",
    arguments: { channel: 1 },
  });
  assert.equal(result.isError, false);
  assert.deepEqual(result.value, HARDWARE_ERROR_RESULT);
  assert.equal(client.calls[0]?.operation, "hardware.measure_vpp");
  await ctx.fiber.dispose();
});

test("degraded result and opaque artifact metadata are preserved without samples", async () => {
  const client = new FakeClient();
  client.result = DEGRADED_PWM_RESULT;
  const ctx = await setup(client);
  const result = await ctx.tools.execute({
    signal: new AbortController().signal,
    callId: ToolCallId("phase7b4-pwm"),
    name: "hardware_measure_pwm",
    arguments: { channel: 1, context_id: "PWM_OUT" },
  });
  assert.equal(result.isError, false);
  assert.deepEqual(result.value, DEGRADED_PWM_RESULT);
  assert.doesNotMatch(JSON.stringify(result.value), /"samples"/);
  assert.match(result.content[0]?.type === "text" ? result.content[0].text : "", /degraded/i);
  assert.match(result.content[0]?.type === "text" ? result.content[0].text : "", /550e8400/);
  await ctx.fiber.dispose();
});

test("adapter failures become bounded Harness failures and tools remain registered", async () => {
  const client = new FakeClient();
  client.result = new AdapterFailure("backend_unreachable", "Hardware backend is unavailable.", "NOT_SENT");
  const ctx = await setup(client);
  const result = await ctx.tools.execute({
    signal: new AbortController().signal,
    callId: ToolCallId("phase7b4-offline"),
    name: "hardware_get_status",
    arguments: {},
  });
  assert.equal(result.isError, true);
  assert.match(result.error?.message ?? "", /backend is unavailable/i);
  assert.ok(ctx.tools.get("hardware_get_status"));
  await ctx.fiber.dispose();
});

test("projected argument validation reports invalid_tool_arguments before IPC", async () => {
  const invalidArguments = [
    { channel: 0 },
    { channel: 3 },
    { channel: "1" },
    { channel: 1, unexpected: true },
  ];
  for (const [index, args] of invalidArguments.entries()) {
    const client = new FakeClient();
    const ctx = await setup(client);
    const result = await ctx.tools.execute({
      signal: new AbortController().signal,
      callId: ToolCallId(`phase7b5-invalid-${index}`),
      name: "hardware_measure_frequency",
      arguments: args,
    });
    assert.equal(result.isError, true);
    assert.equal(result.error?.message, "Hardware tool arguments are invalid.");
    assert.doesNotMatch(result.error?.message ?? "", /ajv|schema|instancePath|keyword|SCPI|VISA|secret/i);
    assert.equal(client.calls.length, 0);
    await ctx.fiber.dispose();
  }
});

test("invalid_tool_arguments is a bounded NOT_SENT adapter failure", () => {
  const failure = safeAdapterFailure("invalid_tool_arguments", "NOT_SENT");
  assert.equal(failure.code, "invalid_tool_arguments");
  assert.equal(failure.deliveryState, "NOT_SENT");
  assert.equal(failure.message, "Hardware tool arguments are invalid.");
});

test("adapter failures expose no secret, local path, SCPI, or VISA detail", async () => {
  const client = new FakeClient();
  client.result = new AdapterFailure(
    "backend_response_invalid",
    "Hardware backend returned an invalid response.",
    "SENT_UNCONFIRMED",
  );
  const ctx = await setup(client);
  const result = await ctx.tools.execute({
    signal: new AbortController().signal,
    callId: ToolCallId("phase7b4-bounded-error"),
    name: "hardware_get_status",
    arguments: {},
  });
  assert.equal(result.isError, true);
  assert.doesNotMatch(result.error?.message ?? "", /secret|\.aia-secrets|[A-Za-z]:\\|SCPI|VISA/i);
  await ctx.fiber.dispose();
});
