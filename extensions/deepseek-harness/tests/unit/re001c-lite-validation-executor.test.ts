import assert from "node:assert/strict";
import test from "node:test";

import type { HardwareClientPort } from "../../src/index.ts";
import type { HardwareOperation } from "../../src/generated/hardware-tools.generated.ts";
import { executeRe001CLiteValidation } from "../../validation/re001c-lite-executor.ts";

const REQUEST = {
  workflow_id: "re001c-lite",
  request_correlation_id: "re001c-lite-request",
  backend: { endpoint: "ws://127.0.0.1:49625", connect_timeout_ms: 1000, request_timeout_ms: 1000 },
  scopes: [
    { scope_id: "scope-a", workflow_id: "re001c-lite", request_correlation_id: "re001c-lite-request", operation: "hardware.measure_frequency", channel: 1, budget: 1 },
    { scope_id: "scope-b", workflow_id: "re001c-lite", request_correlation_id: "re001c-lite-request", operation: "hardware.measure_vpp", channel: 1, budget: 1 },
    { scope_id: "scope-c", workflow_id: "re001c-lite", request_correlation_id: "re001c-lite-request", operation: "hardware.measure_frequency", channel: 2, budget: 1 },
    { scope_id: "scope-d", workflow_id: "re001c-lite", request_correlation_id: "re001c-lite-request", operation: "hardware.measure_vpp", channel: 2, budget: 1 },
  ],
  confirmations: [
    { confirmation_id: "confirm-ch1", workflow_id: "re001c-lite", request_correlation_id: "re001c-lite-request", role: "Vin", channel: 1, target_ref: "RE-001:Vin", maximum_expected_voltage_v: 3.3, safe_low_voltage_confirmed: true, common_ground_confirmed: true, wiring_checked: true, wiring_unchanged: true, confirmed_at: "2026-09-13T10:00:00Z" },
    { confirmation_id: "confirm-ch2", workflow_id: "re001c-lite", request_correlation_id: "re001c-lite-request", role: "Vout", channel: 2, target_ref: "RE-001:Vout", maximum_expected_voltage_v: 3.3, safe_low_voltage_confirmed: true, common_ground_confirmed: true, wiring_checked: true, wiring_unchanged: true, confirmed_at: "2026-09-13T10:00:00Z" },
  ],
} as const;

function result(operation: "hardware.measure_frequency" | "hardware.measure_vpp", channel: 1 | 2) {
  const kind = operation.endsWith("frequency") ? "frequency" : "vpp";
  const key = kind === "frequency" ? "instrument_frequency" : "instrument_vpp";
  return {
    contract_version: "1.0", ok: true, operation,
    result: {
      request_id: `00000000-0000-4000-8000-0000000000${channel}${kind === "frequency" ? 1 : 2}`,
      kind, channel, context_id: `RE-001-${channel}`,
      instrument: { manufacturer: "RIGOL", model: "DS1102Z-E", serial_number: "***0001", firmware_version: "test" },
      waveform: null,
      observations: { [key]: { value: kind === "frequency" ? 100 : channel === 1 ? 3.3 : 2.2, source: "instrument", method: "query", observed_at: "2026-09-13T10:00:00Z", quality: "good", warnings: [], evidence_artifact_ids: [] } },
      quality: "good", warnings: [], coherence: { software_observations: "unknown", instrument_vs_software: "unknown" },
      provenance: { started_at: "2026-09-13T10:00:00Z", completed_at: "2026-09-13T10:00:01Z", analysis_algorithm: null },
    },
  };
}

class Client implements HardwareClientPort {
  readonly calls: Array<{ operation: HardwareOperation; args: unknown }> = [];
  failAt = 0;
  wrongChannelAt = 0;
  start(): void {}
  async dispose(): Promise<void> {}
  async invoke(operation: HardwareOperation, args: any): Promise<unknown> {
    this.calls.push({ operation, args });
    if (this.failAt === this.calls.length) return { contract_version: "1.0", ok: false, operation, error: { code: "measurement_failed", message: "failed", details: {} } };
    const value = result(operation as "hardware.measure_frequency" | "hardware.measure_vpp", args.channel);
    if (this.wrongChannelAt === this.calls.length) value.result.channel = args.channel === 1 ? 2 : 1;
    return value;
  }
}

test("uses four independent scopes and two channel confirmations in fixed order", async () => {
  const client = new Client();
  const receipt = await executeRe001CLiteValidation(REQUEST, { createClient: () => client });
  assert.equal(receipt.status, "COMPLETED");
  assert.deepEqual(client.calls.map(({ operation, args }: any) => [operation, args.channel]), [
    ["hardware.measure_frequency", 1], ["hardware.measure_vpp", 1],
    ["hardware.measure_frequency", 2], ["hardware.measure_vpp", 2],
  ]);
  assert.deepEqual(receipt.operations.map((item: any) => item.scope_remaining_invocations), [0, 0, 0, 0]);
  assert.deepEqual(receipt.operations.map((item: any) => item.policy_reason), Array(4).fill("allowed_confirmed_physical_setup"));
});

test("canonical channel mismatch stops before later physical operations", async () => {
  const client = new Client(); client.wrongChannelAt = 1;
  const receipt = await executeRe001CLiteValidation(REQUEST, { createClient: () => client });
  assert.equal(receipt.status, "FAILED");
  assert.equal(receipt.failure_code, "canonical_binding_mismatch");
  assert.equal(client.calls.length, 1);
});

test("operation two failure prevents operations three and four with no retry", async () => {
  const client = new Client(); client.failAt = 2;
  const receipt = await executeRe001CLiteValidation(REQUEST, { createClient: () => client });
  assert.equal(receipt.status, "FAILED");
  assert.equal(client.calls.length, 2);
  assert.deepEqual(client.calls.map((item) => item.operation), ["hardware.measure_frequency", "hardware.measure_vpp"]);
});

test("CH1 confirmation cannot authorize CH2 and invalid scope budget fails closed", async () => {
  for (const mutate of [
    (request: any) => { request.confirmations[1] = { ...request.confirmations[0], role: "Vout" }; },
    (request: any) => { request.scopes[3].budget = 2; },
    (request: any) => { request.scopes[2].workflow_id = "wrong-workflow"; },
    (request: any) => { request.confirmations[1].request_correlation_id = "wrong-request"; },
    (request: any) => { request.unexpected = true; },
  ]) {
    const request: any = structuredClone(REQUEST); mutate(request);
    const client = new Client();
    const receipt = await executeRe001CLiteValidation(request, { createClient: () => client });
    assert.equal(receipt.status, "FAILED");
    assert.equal(client.calls.length, 0);
  }
});

test("validation creates one client and never exposes a broad or reusable scope", async () => {
  let clients = 0;
  const client = new Client();
  const receipt = await executeRe001CLiteValidation(REQUEST, {
    createClient: () => { clients += 1; return client; },
  });
  assert.equal(receipt.status, "COMPLETED");
  assert.equal(clients, 1);
  assert.equal(client.calls.length, 4);
  assert.equal(new Set(REQUEST.scopes.map((scope) => scope.scope_id)).size, 4);
  assert.ok(REQUEST.scopes.every((scope) => scope.budget === 1));
});
