import { Context } from "@deepseek-ai/cordis";
import { ToolCallId } from "@deepseek-ai/dsh-llm";
import SystemPrompt from "@deepseek-ai/dsh-system-prompt";
import ToolRuntime from "@deepseek-ai/dsh-tools";

import { applyWithDependencies, type HardwareClientPort, type PluginDependencies } from "../src/index.ts";
import type { HardwareOperation } from "../src/generated/hardware-tools.generated.ts";
import { createTrustedOperationScope } from "../src/operation-scope/index.ts";
import { createHardwareToolPolicyContext, createProbeSetupConfirmation } from "../src/policy/index.ts";

type JsonObject = Readonly<Record<string, unknown>>;
type PhysicalOperation = "hardware.measure_frequency" | "hardware.measure_vpp";
type Channel = 1 | 2;

export interface Re001CLiteDependencies {
  readonly createClient: PluginDependencies["createClient"];
}

export interface Re001CLiteReceipt extends JsonObject {
  readonly status: "COMPLETED" | "FAILED" | "UNKNOWN";
  readonly operations: readonly JsonObject[];
  readonly failure_code: string | null;
}

interface Accounting {
  readonly operation: PhysicalOperation;
  readonly channel: Channel;
  scopeRemaining: number | null;
  policyReason: string | null;
  ipcDispatchCount: number;
  hardwareExecutionCount: number;
  canonicalResult: JsonObject | null;
  failureCode: string | null;
}

const ORDER = Object.freeze([
  ["hardware.measure_frequency", 1],
  ["hardware.measure_vpp", 1],
  ["hardware.measure_frequency", 2],
  ["hardware.measure_vpp", 2],
] as const);

/** Validation-only composition; it adds no public Tool or protocol. */
export async function executeRe001CLiteValidation(
  input: unknown,
  dependencies: Re001CLiteDependencies,
): Promise<Re001CLiteReceipt> {
  let request: JsonObject;
  try {
    request = validateRequest(input);
  } catch {
    return receipt("FAILED", [], "validation_request_invalid");
  }
  let workflowId: string;
  let correlationId: string;
  let scopes: ReturnType<typeof scopesByBinding>;
  let confirmations: ReturnType<typeof confirmationsByChannel>;
  try {
    workflowId = text(request.workflow_id);
    correlationId = text(request.request_correlation_id);
    scopes = scopesByBinding(request, workflowId, correlationId);
    confirmations = confirmationsByChannel(request, workflowId, correlationId);
  } catch {
    return receipt("FAILED", [], "validation_request_invalid");
  }
  if (scopes === null || confirmations === null) return receipt("FAILED", [], "validation_request_invalid");

  const accounting: Accounting[] = [];
  let active: Accounting | null = null;
  const client = dependencies.createClient(clientConfig(request));
  const countedClient: HardwareClientPort = {
    start: () => client.start(),
    dispose: () => client.dispose(),
    async invoke(operation, args, signal) {
      if (active === null || active.operation !== operation || active.channel !== invocationChannel(args)) {
        throw new TypeError("governed invocation binding mismatch");
      }
      active.ipcDispatchCount += 1;
      try {
        const value = await client.invoke(operation, args, signal);
        active.hardwareExecutionCount = 1;
        return value;
      } catch {
        active.failureCode = "hardware_invocation_failed";
        throw new Error("bounded hardware invocation failure");
      }
    },
  };

  const ctx = new Context();
  try {
    await ctx.plugin(SystemPrompt);
    await ctx.plugin(ToolRuntime);
    applyWithDependencies(ctx, clientConfig(request), {
      createClient: () => countedClient,
      resolveOperationScopeContext(_config, operation, args) {
        const channel = invocationChannel(args);
        const scope = scopes.get(key(operation, channel));
        if (scope === undefined) throw new TypeError("scope binding unavailable");
        return Object.freeze({ scope, workflowId, requestCorrelationId: correlationId });
      },
      resolvePolicyContext(operation, args, config, trustedWorkflowId) {
        const channel = invocationChannel(args);
        const confirmation = confirmations.get(channel);
        if (confirmation === undefined) throw new TypeError("confirmation binding unavailable");
        return createHardwareToolPolicyContext({
          operation,
          channel,
          backendMode: config.backendMode,
          workflowId: trustedWorkflowId,
          requestCorrelationId: correlationId,
          requestedGoal: channel === 1 ? "Measure the user-confirmed Vin channel." : "Measure the user-confirmed Vout channel.",
          requestedTargetRef: confirmation.targetRef,
          groundingRequired: true,
          wiringChanged: false,
          confirmation,
          previousExecution: null,
          designContext: null,
        });
      },
      onOperationScopeDecision(event) {
        if (active !== null && event.phase === "FINAL_AUTHORIZATION") active.scopeRemaining = event.decision.remainingInvocations;
      },
      onPolicyDecision(event) {
        if (active !== null) active.policyReason = event.decision.reasonCode;
      },
    });

    for (const [operation, channel] of ORDER) {
      active = { operation, channel, scopeRemaining: null, policyReason: null, ipcDispatchCount: 0, hardwareExecutionCount: 0, canonicalResult: null, failureCode: null };
      accounting.push(active);
      const toolName = operation === "hardware.measure_frequency" ? "hardware_measure_frequency" : "hardware_measure_vpp";
      const result = await ctx.tools.execute({
        signal: AbortSignal.timeout(number(object(request.backend).request_timeout_ms)),
        callId: ToolCallId(`re001c-lite-${operation}-${channel}`),
        name: toolName,
        arguments: { channel, context_id: channel === 1 ? "RE-001:Vin" : "RE-001:Vout" },
      });
      if (result.isError) {
        active.failureCode ??= "governed_operation_failed";
        return receipt("FAILED", accounting, active.failureCode);
      }
      active.canonicalResult = optionalObject(result.value) ?? null;
      if (active.canonicalResult?.ok !== true) {
        active.failureCode = text(optionalObject(active.canonicalResult?.error)?.code ?? "canonical_operation_failed");
        return receipt("FAILED", accounting, active.failureCode);
      }
      if (!canonicalBindingMatches(active.canonicalResult, operation, channel)) {
        active.failureCode = "canonical_binding_mismatch";
        return receipt("FAILED", accounting, active.failureCode);
      }
    }
    return receipt("COMPLETED", accounting, null);
  } catch {
    return receipt("FAILED", accounting, "validation_executor_failure");
  } finally {
    await ctx.fiber.dispose().catch(() => undefined);
  }
}

function scopesByBinding(request: JsonObject, workflowId: string, correlationId: string) {
  const values = array(request.scopes);
  if (values.length !== 4) return null;
  const result = new Map<string, ReturnType<typeof createTrustedOperationScope>>();
  for (const raw of values) {
    const value = object(raw);
    exactKeys(value, ["scope_id", "workflow_id", "request_correlation_id", "operation", "channel", "budget"]);
    const operation = physicalOperation(value.operation);
    const channel = boundedChannel(value.channel);
    if (value.workflow_id !== workflowId || value.request_correlation_id !== correlationId
      || value.budget !== 1 || result.has(key(operation, channel))) return null;
    result.set(key(operation, channel), createTrustedOperationScope({
      scopeId: text(value.scope_id), workflowId, requestCorrelationId: correlationId,
      allowedOperations: [{ operation, maxInvocations: 1 }], targetChannel: channel,
      targetIntent: channel === 1 ? "RE-001 Vin" : "RE-001 Vout",
      origin: "TRUSTED_VALIDATION_SCENARIO", authorizationRef: "explicit-real-validation-authorization",
    }));
  }
  return result.size === 4 && ORDER.every(([operation, channel]) => result.has(key(operation, channel))) ? result : null;
}

function confirmationsByChannel(request: JsonObject, workflowId: string, correlationId: string) {
  const values = array(request.confirmations);
  if (values.length !== 2) return null;
  const result = new Map<Channel, ReturnType<typeof createProbeSetupConfirmation>>();
  for (const raw of values) {
    const value = object(raw);
    exactKeys(value, [
      "confirmation_id", "workflow_id", "request_correlation_id", "role", "channel",
      "target_ref", "maximum_expected_voltage_v", "safe_low_voltage_confirmed",
      "common_ground_confirmed", "wiring_checked", "wiring_unchanged", "confirmed_at",
    ]);
    const channel = boundedChannel(value.channel);
    const expectedRole = channel === 1 ? "Vin" : "Vout";
    const expectedTarget = channel === 1 ? "RE-001:Vin" : "RE-001:Vout";
    if (value.workflow_id !== workflowId || value.request_correlation_id !== correlationId
      || value.role !== expectedRole || value.target_ref !== expectedTarget || result.has(channel)
      || value.maximum_expected_voltage_v !== 3.3
      || value.safe_low_voltage_confirmed !== true || value.common_ground_confirmed !== true
      || value.wiring_checked !== true || value.wiring_unchanged !== true) return null;
    result.set(channel, createProbeSetupConfirmation({
      confirmationId: text(value.confirmation_id), source: "TRUSTED_USER_EVENT",
      confirmedBy: "user", channel, targetRef: expectedTarget,
      safeLowVoltageConfirmed: true, commonGroundConfirmed: true,
      confirmedAt: text(value.confirmed_at), scope: { workflowId, requestCorrelationId: correlationId },
    }));
  }
  return result.size === 2 ? result : null;
}

function validateRequest(value: unknown): JsonObject {
  const request = object(value);
  exactKeys(request, ["workflow_id", "request_correlation_id", "backend", "scopes", "confirmations"]);
  text(request.workflow_id); text(request.request_correlation_id); object(request.backend);
  exactKeys(object(request.backend), ["endpoint", "connect_timeout_ms", "request_timeout_ms"]);
  array(request.scopes); array(request.confirmations);
  return request;
}

function clientConfig(request: JsonObject) {
  const backend = object(request.backend);
  return Object.freeze({ endpoint: text(backend.endpoint), secretFile: ".aia-secrets/harness-hardware-psk.txt", connectTimeoutMs: number(backend.connect_timeout_ms), authTimeoutMs: number(backend.connect_timeout_ms), requestTimeoutMs: number(backend.request_timeout_ms), backendMode: "REAL" as const });
}

function receipt(status: "COMPLETED" | "FAILED" | "UNKNOWN", entries: readonly Accounting[], failureCode: string | null): Re001CLiteReceipt {
  return Object.freeze({
    contract: "aia-re001c-lite-validation", contract_version: "1.0", kind: "governed_measurement_receipt", status,
    operations: Object.freeze(entries.map((entry) => Object.freeze({
      operation: entry.operation, channel: entry.channel,
      scope_remaining_invocations: entry.scopeRemaining, policy_reason: entry.policyReason,
      ipc_dispatch_count: entry.ipcDispatchCount, hardware_execution_count: entry.hardwareExecutionCount,
      canonical_result: entry.canonicalResult, failure_code: entry.failureCode,
    }))),
    failure_code: failureCode,
  });
}

function canonicalBindingMatches(value: JsonObject, operation: PhysicalOperation, channel: Channel): boolean {
  const result = optionalObject(value.result);
  const expectedKind = operation === "hardware.measure_frequency" ? "frequency" : "vpp";
  return value.operation === operation && result?.kind === expectedKind && result.channel === channel;
}

function key(operation: HardwareOperation | undefined, channel: Channel): string { return `${operation ?? "unknown"}:${channel}`; }
function physicalOperation(value: unknown): PhysicalOperation { if (value !== "hardware.measure_frequency" && value !== "hardware.measure_vpp") throw new TypeError("unsupported operation"); return value; }
function invocationChannel(value: unknown): Channel { return boundedChannel(optionalObject(value)?.channel); }
function boundedChannel(value: unknown): Channel { if (value !== 1 && value !== 2) throw new TypeError("unsupported channel"); return value; }
function object(value: unknown): JsonObject { const result = optionalObject(value); if (result === undefined) throw new TypeError("object expected"); return result; }
function optionalObject(value: unknown): JsonObject | undefined { return typeof value === "object" && value !== null && !Array.isArray(value) ? value as JsonObject : undefined; }
function array(value: unknown): readonly unknown[] { if (!Array.isArray(value)) throw new TypeError("array expected"); return value; }
function text(value: unknown): string { if (typeof value !== "string" || value.length === 0 || value.length > 512) throw new TypeError("bounded text expected"); return value; }
function number(value: unknown): number { if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) throw new TypeError("positive number expected"); return value; }
function exactKeys(value: JsonObject, expected: readonly string[]): void {
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length || actual.some((item, index) => item !== wanted[index])) {
    throw new TypeError("unexpected validation field");
  }
}
