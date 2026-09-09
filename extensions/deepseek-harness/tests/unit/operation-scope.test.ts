import assert from "node:assert/strict";
import test from "node:test";

import {
  OperationScopeGate,
  createTrustedOperationScope,
  type SemanticHardwareOperation,
} from "../../src/operation-scope/index.ts";

const WORKFLOW = "phase7c4c-workflow";

function scope(
  operation: SemanticHardwareOperation,
  overrides: Partial<Parameters<typeof createTrustedOperationScope>[0]> = {},
) {
  return createTrustedOperationScope({
    scopeId: `authorization-${operation}`,
    requestCorrelationId: "request-1",
    workflowId: WORKFLOW,
    allowedOperations: [{ operation, maxInvocations: 1 }],
    targetChannel: operation === "hardware.get_status" ? null : 1,
    targetIntent: operation,
    origin: "TRUSTED_VALIDATION_SCENARIO",
    authorizationRef: "user-authorization-1",
    ...overrides,
  });
}

function request(operation: string, channel: 1 | 2 | null = 1) {
  return { requestCorrelationId: "request-1", workflowId: WORKFLOW, operation, channel };
}

test("frequency scope allows frequency", () => {
  const decision = new OperationScopeGate().evaluate(scope("hardware.measure_frequency"), request("hardware.measure_frequency"));
  assert.deepEqual([decision.decision, decision.reasonCode], ["ALLOW", "allowed_operation_in_scope"]);
});

for (const operation of ["hardware.measure_pwm", "hardware.capture_waveform", "hardware.measure_vpp"] as const) {
  test(`frequency scope denies ${operation}`, () => {
    const decision = new OperationScopeGate().evaluate(scope("hardware.measure_frequency"), request(operation));
    assert.deepEqual([decision.decision, decision.reasonCode], ["DENY", "operation_not_authorized"]);
  });
}

test("frequency budget one blocks the second dispatch", () => {
  const gate = new OperationScopeGate();
  const trusted = scope("hardware.measure_frequency");
  assert.equal(gate.authorizeDispatch(trusted, request("hardware.measure_frequency")).decision, "ALLOW");
  const second = gate.authorizeDispatch(trusted, request("hardware.measure_frequency"));
  assert.deepEqual([second.decision, second.reasonCode], ["DENY", "invocation_budget_exhausted"]);
});

test("PWM scope allows PWM and denies separate frequency", () => {
  const gate = new OperationScopeGate();
  const trusted = scope("hardware.measure_pwm");
  assert.equal(gate.evaluate(trusted, request("hardware.measure_pwm")).decision, "ALLOW");
  assert.equal(gate.evaluate(trusted, request("hardware.measure_frequency")).reasonCode, "operation_not_authorized");
});

test("status scope explicitly allows status", () => {
  const decision = new OperationScopeGate().evaluate(
    scope("hardware.get_status"),
    request("hardware.get_status", null),
  );
  assert.equal(decision.decision, "ALLOW");
});

test("unknown operation is denied", () => {
  const decision = new OperationScopeGate().evaluate(scope("hardware.measure_frequency"), request("hardware.raw_execute"));
  assert.equal(decision.reasonCode, "unknown_operation");
});

test("channel one scope denies channel two", () => {
  const decision = new OperationScopeGate().evaluate(scope("hardware.measure_frequency"), request("hardware.measure_frequency", 2));
  assert.equal(decision.reasonCode, "channel_out_of_scope");
});

test("workflow mismatch is denied", () => {
  const decision = new OperationScopeGate().evaluate(scope("hardware.measure_frequency"), {
    ...request("hardware.measure_frequency"),
    workflowId: "another-workflow",
  });
  assert.equal(decision.reasonCode, "workflow_scope_mismatch");
});

test("request correlation mismatch is denied as a workflow scope mismatch", () => {
  const decision = new OperationScopeGate().evaluate(scope("hardware.measure_frequency"), {
    ...request("hardware.measure_frequency"),
    requestCorrelationId: "another-request",
  });
  assert.equal(decision.reasonCode, "workflow_scope_mismatch");
});

test("scope is deeply immutable and cannot be expanded by model-owned values", () => {
  const trusted = scope("hardware.measure_frequency");
  assert.ok(Object.isFrozen(trusted));
  assert.ok(Object.isFrozen(trusted.allowedOperations));
  assert.ok(Object.isFrozen(trusted.allowedOperations[0]));
  assert.throws(() => {
    (trusted.allowedOperations as unknown as unknown[]).push({ operation: "hardware.measure_pwm", maxInvocations: 99 });
  }, TypeError);
  assert.equal(new OperationScopeGate().evaluate(trusted, request("hardware.measure_pwm")).decision, "DENY");
});

test("model arguments cannot increase trusted invocation budget", () => {
  const gate = new OperationScopeGate();
  const trusted = scope("hardware.measure_frequency");
  const modelArguments = { channel: 1, allowed_operations: ["hardware.measure_pwm"], max_invocations: 999 };
  assert.equal(gate.authorizeDispatch(trusted, request("hardware.measure_frequency", modelArguments.channel as 1)).decision, "ALLOW");
  assert.equal(gate.authorizeDispatch(trusted, request("hardware.measure_frequency", modelArguments.channel as 1)).reasonCode, "invocation_budget_exhausted");
});

test("denied attempts do not consume the authorized operation budget", () => {
  const gate = new OperationScopeGate();
  const trusted = scope("hardware.measure_frequency");
  assert.equal(gate.authorizeDispatch(trusted, request("hardware.measure_pwm")).decision, "DENY");
  assert.equal(gate.authorizeDispatch(trusted, request("hardware.measure_frequency")).decision, "ALLOW");
});

test("preflight evaluation does not consume dispatch budget", () => {
  const gate = new OperationScopeGate();
  const trusted = scope("hardware.measure_frequency");
  assert.equal(gate.evaluate(trusted, request("hardware.measure_frequency")).decision, "ALLOW");
  assert.equal(gate.evaluate(trusted, request("hardware.measure_frequency")).decision, "ALLOW");
  assert.equal(gate.authorizeDispatch(trusted, request("hardware.measure_frequency")).decision, "ALLOW");
});

test("indeterminate execution does not restore consumed budget", () => {
  const gate = new OperationScopeGate();
  const trusted = scope("hardware.measure_frequency");
  assert.equal(gate.authorizeDispatch(trusted, request("hardware.measure_frequency")).decision, "ALLOW");
  // No refund API exists: SENT_UNCONFIRMED remains a consumed dispatch.
  assert.equal(gate.evaluate(trusted, request("hardware.measure_frequency")).reasonCode, "invocation_budget_exhausted");
});

test("explicit trusted new authorization creates a new independent budget", () => {
  const gate = new OperationScopeGate();
  const first = scope("hardware.measure_frequency", { scopeId: "authorization-1" });
  const second = scope("hardware.measure_frequency", {
    scopeId: "authorization-2",
    authorizationRef: "explicit-remeasurement-authorization",
  });
  assert.equal(gate.authorizeDispatch(first, request("hardware.measure_frequency")).decision, "ALLOW");
  assert.equal(gate.authorizeDispatch(first, request("hardware.measure_frequency")).decision, "DENY");
  assert.equal(gate.authorizeDispatch(second, request("hardware.measure_frequency")).decision, "ALLOW");
});

test("multi-operation trusted scope keeps separate bounded budgets", () => {
  const trusted = createTrustedOperationScope({
    scopeId: "multi-operation-authorization",
    requestCorrelationId: "request-2",
    workflowId: WORKFLOW,
    allowedOperations: [
      { operation: "hardware.capture_waveform", maxInvocations: 1 },
      { operation: "hardware.measure_frequency", maxInvocations: 2 },
    ],
    targetChannel: 1,
    targetIntent: "bounded waveform analysis",
    origin: "TRUSTED_APPLICATION_INTENT",
    authorizationRef: null,
  });
  const gate = new OperationScopeGate();
  const multiRequest = (operation: string) => ({
    requestCorrelationId: "request-2",
    workflowId: WORKFLOW,
    operation,
    channel: 1 as const,
  });
  assert.equal(gate.authorizeDispatch(trusted, multiRequest("hardware.capture_waveform")).decision, "ALLOW");
  assert.equal(gate.authorizeDispatch(trusted, multiRequest("hardware.capture_waveform")).decision, "DENY");
  assert.equal(gate.authorizeDispatch(trusted, multiRequest("hardware.measure_frequency")).decision, "ALLOW");
  assert.equal(gate.authorizeDispatch(trusted, multiRequest("hardware.measure_frequency")).decision, "ALLOW");
  assert.equal(gate.authorizeDispatch(trusted, multiRequest("hardware.measure_frequency")).decision, "DENY");
});

test("trusted scope factory rejects unknown allowed operations", () => {
  assert.throws(() => scope("hardware.raw_execute" as SemanticHardwareOperation), TypeError);
});
