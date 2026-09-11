import { Context } from "@deepseek-ai/cordis";
import { ToolCallId } from "@deepseek-ai/dsh-llm";
import SystemPrompt from "@deepseek-ai/dsh-system-prompt";
import ToolRuntime from "@deepseek-ai/dsh-tools";

import {
  applyWithDependencies,
  type HardwareClientPort,
  type PluginDependencies,
} from "../src/index.ts";
import type { HardwareOperation } from "../src/generated/hardware-tools.generated.ts";
import { AdapterFailure, type DeliveryState } from "../src/ipc/errors.ts";
import {
  EvidenceContractBinding,
  type TeachingEvidenceContext,
} from "../src/evidence/index.ts";
import {
  createHardwareToolPolicyContext,
  createProbeSetupConfirmation,
} from "../src/policy/index.ts";
import { createTrustedOperationScope } from "../src/operation-scope/index.ts";
import {
  PHASE8B3_RECEIPT_SCHEMA_ID,
  PHASE8B3_REQUEST_SCHEMA_ID,
  Phase8B3ValidationContractBinding,
} from "./phase8b3-contract.ts";

type JsonObject = Readonly<Record<string, unknown>>;

export interface Phase8B3ExecutorDependencies {
  readonly repositoryRoot: string;
  readonly createClient: PluginDependencies["createClient"];
  readonly now?: () => Date;
}

export interface Phase8B3ValidationReceipt extends JsonObject {
  readonly status: "COMPLETED" | "FAILED" | "UNKNOWN";
  readonly operations: readonly JsonObject[];
  readonly pwm_teaching_evidence: JsonObject | null;
  readonly failure_code: string | null;
}

interface OperationAccounting {
  operation: HardwareOperation;
  channel: 1 | null;
  deliveryState: DeliveryState;
  scopeDecision: JsonObject | null;
  policyDecision: JsonObject | null;
  ipcDispatchCount: number;
  hardwareExecutionCount: number;
  startedAt: string | null;
  completedAt: string | null;
  canonicalResult: JsonObject | null;
  teachingEvidence: JsonObject | null;
  failureCode: string | null;
}

/** Validation-only one-shot composition of the production Tool governance path. */
export async function executeGovernedHardwareValidation(
  input: unknown,
  dependencies: Phase8B3ExecutorDependencies,
): Promise<Phase8B3ValidationReceipt> {
  const contract = Phase8B3ValidationContractBinding.fromRepository(dependencies.repositoryRoot);
  let request: JsonObject;
  try {
    request = contract.requireValid(PHASE8B3_REQUEST_SCHEMA_ID, input);
  } catch {
    return boundedReceipt(null, "FAILED", [], null, "contract_schema_invalid", contract);
  }
  if (!identitiesAreCoherent(request)) {
    return boundedReceipt(request, "FAILED", [], null, "contract_semantics_invalid", contract);
  }

  const now = dependencies.now ?? (() => new Date());
  const accounting = new Map<HardwareOperation, OperationAccounting>();
  const client = dependencies.createClient(normalizedClientConfig(request));
  const countedClient: HardwareClientPort = {
    start: () => client.start(),
    dispose: () => client.dispose(),
    async invoke(operation, args, signal) {
      const entry = operationAccounting(accounting, operation, args, now);
      entry.ipcDispatchCount += 1;
      entry.startedAt = now().toISOString();
      try {
        const value = await client.invoke(operation, args, signal);
        entry.deliveryState = "RESPONSE_RECEIVED";
        entry.hardwareExecutionCount = 1;
        entry.completedAt = now().toISOString();
        return value;
      } catch (error: unknown) {
        entry.completedAt = now().toISOString();
        if (error instanceof AdapterFailure) {
          entry.deliveryState = error.deliveryState;
          entry.failureCode = error.code;
        } else {
          entry.deliveryState = "SENT_UNCONFIRMED";
          entry.failureCode = "indeterminate_execution";
        }
        throw error;
      }
    },
  };

  const ctx = new Context();
  try {
    await ctx.plugin(SystemPrompt);
    await ctx.plugin(ToolRuntime);
    const statusScope = createScope(object(request.status_scope, "status_scope"));
    const pwmScopeInput = object(request.pwm_scope, "pwm_scope");
    const pwmScope = createScope(pwmScopeInput);
    const pwmChannel = channel(pwmScopeInput.target_channel);
    if (pwmChannel !== 1) throw new TypeError("Phase 8B.3 PWM scope must bind CH1");
    const confirmationInput = object(request.confirmation, "confirmation");
    const target = object(request.target, "target");
    const confirmation = createProbeSetupConfirmation({
      confirmationId: text(confirmationInput.confirmation_id),
      source: "TRUSTED_USER_EVENT",
      confirmedBy: text(confirmationInput.confirmed_by),
      channel: number(confirmationInput.channel),
      targetRef: text(confirmationInput.target_ref),
      safeLowVoltageConfirmed: confirmationInput.safe_low_voltage_confirmed === true,
      commonGroundConfirmed: confirmationInput.common_ground_confirmed === true,
      confirmedAt: text(confirmationInput.confirmed_at),
      scope: {
        workflowId: text(confirmationInput.workflow_id),
        requestCorrelationId: text(confirmationInput.request_correlation_id),
      },
    });
    applyWithDependencies(ctx, normalizedClientConfig(request), {
      createClient: () => countedClient,
      resolveOperationScopeContext: (_config, operation) => {
        const scope = operation === "hardware.get_status" ? statusScope : pwmScope;
        return Object.freeze({
          scope,
          workflowId: scope.workflowId,
          requestCorrelationId: scope.requestCorrelationId,
        });
      },
      resolvePolicyContext(operation, args, config, trustedWorkflowId) {
        const values = optionalObject(args);
        const isStatus = operation === "hardware.get_status";
        return createHardwareToolPolicyContext({
          operation,
          channel: isStatus ? null : number(values?.channel),
          backendMode: config.backendMode,
          workflowId: trustedWorkflowId,
          requestCorrelationId: text(request.request_correlation_id),
          requestedGoal: isStatus
            ? "Read bounded oscilloscope status for the governed validation workflow."
            : `Measure PWM at the confirmed design target ${text(target.display_label)}.`,
          requestedTargetRef: isStatus ? null : text(target.target_ref),
          groundingRequired: !isStatus,
          wiringChanged: !isStatus && confirmationInput.wiring_unchanged !== true,
          confirmation: isStatus ? null : confirmation,
          previousExecution: null,
          designContext: isStatus ? null : {
            documentCanonicalId: text(target.document_canonical_id),
            snapshotId: text(target.snapshot_id),
            probeTargetId: text(target.probe_target_id),
          },
        });
      },
      onOperationScopeDecision(event) {
        const entry = operationAccounting(accounting, event.operation, undefined, now);
        if (event.phase === "FINAL_AUTHORIZATION" || entry.scopeDecision === null) {
          entry.scopeDecision = Object.freeze({
            decision: event.decision.decision,
            reason_code: event.decision.reasonCode,
            remaining_invocations: event.decision.remainingInvocations,
          });
        }
      },
      onPolicyDecision(event) {
        const entry = operationAccounting(accounting, event.operation, undefined, now);
        entry.policyDecision = Object.freeze({
          decision: event.decision.decision,
          reason_code: event.decision.reasonCode,
        });
      },
    });

    const statusResult = await executeTool(ctx, "hardware_get_status", {}, request, accounting, now);
    if (!statusResult.ok) return receiptFromAccounting(request, accounting, contract);
    const pwmResult = await executeTool(ctx, "hardware_measure_pwm", {
      channel: pwmChannel,
      context_id: text(target.target_ref),
    }, request, accounting, now);
    if (!pwmResult.ok) return receiptFromAccounting(request, accounting, contract);
    return receiptFromAccounting(request, accounting, contract);
  } catch {
    return receiptFromAccounting(request, accounting, contract, "validation_executor_failure");
  } finally {
    await ctx.fiber.dispose().catch(() => undefined);
  }
}

async function executeTool(
  ctx: Context,
  name: "hardware_get_status" | "hardware_measure_pwm",
  args: JsonObject,
  request: JsonObject,
  accounting: Map<HardwareOperation, OperationAccounting>,
  now: () => Date,
): Promise<{ readonly ok: boolean }> {
  const operation: HardwareOperation = name === "hardware_get_status"
    ? "hardware.get_status"
    : "hardware.measure_pwm";
  const result = await ctx.tools.execute({
    signal: AbortSignal.timeout(number(object(request.backend, "backend").request_timeout_ms)),
    callId: ToolCallId(`phase8b3-${operation}`),
    name,
    arguments: args,
  });
  const entry = operationAccounting(accounting, operation, args, now);
  if (result.isError) {
    if (entry.failureCode === null) {
      entry.deliveryState = "NOT_SENT";
      entry.failureCode = failureFromDecisions(entry);
    }
    entry.completedAt ??= now().toISOString();
    entry.teachingEvidence = parseTeachingEvidence(result.additionalContexts);
    return { ok: false };
  }
  entry.deliveryState = "RESPONSE_RECEIVED";
  entry.canonicalResult = optionalObject(result.value) ?? null;
  entry.teachingEvidence = parseTeachingEvidence(result.additionalContexts);
  if (entry.canonicalResult?.ok === false) {
    entry.failureCode = text(optionalObject(entry.canonicalResult.error)?.code ?? "canonical_operation_failed");
    return { ok: false };
  }
  return { ok: true };
}

function createScope(value: JsonObject) {
  return createTrustedOperationScope({
    scopeId: text(value.scope_id),
    workflowId: text(value.workflow_id),
    requestCorrelationId: text(value.request_correlation_id),
    allowedOperations: [{
      operation: text(value.operation) as HardwareOperation,
      maxInvocations: number(value.max_invocations),
    }],
    targetChannel: value.target_channel === null ? null : channel(value.target_channel),
    targetIntent: "Phase 8B.3 bounded validation operation",
    origin: "TRUSTED_VALIDATION_SCENARIO",
    authorizationRef: text(value.authorization_ref),
  });
}

function normalizedClientConfig(request: JsonObject) {
  const backend = object(request.backend, "backend");
  return Object.freeze({
    endpoint: text(backend.endpoint),
    secretFile: ".aia-secrets/harness-hardware-psk.txt",
    connectTimeoutMs: number(backend.connect_timeout_ms),
    authTimeoutMs: number(backend.connect_timeout_ms),
    requestTimeoutMs: number(backend.request_timeout_ms),
    backendMode: "REAL" as const,
  });
}

function identitiesAreCoherent(request: JsonObject): boolean {
  const workflow = request.workflow_id;
  const correlation = request.request_correlation_id;
  const target = optionalObject(request.target);
  const confirmation = optionalObject(request.confirmation);
  const scopes = [optionalObject(request.status_scope), optionalObject(request.pwm_scope)];
  return typeof workflow === "string"
    && typeof correlation === "string"
    && confirmation?.workflow_id === workflow
    && confirmation.request_correlation_id === correlation
    && confirmation.target_ref === target?.target_ref
    && confirmation.channel === 1
    && confirmation.wiring_checked === true
    && confirmation.wiring_unchanged === true
    && scopes.every((scope) => scope?.workflow_id === workflow && scope.request_correlation_id === correlation);
}

function operationAccounting(
  values: Map<HardwareOperation, OperationAccounting>,
  operation: HardwareOperation,
  args: unknown,
  _now: () => Date,
): OperationAccounting {
  const existing = values.get(operation);
  const validatedChannel = invocationChannel(args);
  if (existing !== undefined) {
    if (validatedChannel !== undefined) existing.channel = validatedChannel;
    return existing;
  }
  const created: OperationAccounting = {
    operation,
    channel: validatedChannel ?? null,
    deliveryState: "NOT_SENT",
    scopeDecision: null,
    policyDecision: null,
    ipcDispatchCount: 0,
    hardwareExecutionCount: 0,
    startedAt: null,
    completedAt: null,
    canonicalResult: null,
    teachingEvidence: null,
    failureCode: null,
  };
  values.set(operation, created);
  return created;
}

function invocationChannel(args: unknown): 1 | null | undefined {
  const values = optionalObject(args);
  if (values === undefined || !("channel" in values)) return undefined;
  const value = channel(values.channel);
  if (value !== 1) throw new TypeError("Phase 8B.3 invocation channel must match CH1");
  return value;
}

function receiptFromAccounting(
  request: JsonObject,
  accounting: ReadonlyMap<HardwareOperation, OperationAccounting>,
  contract: Phase8B3ValidationContractBinding,
  fallbackFailure: string | null = null,
): Phase8B3ValidationReceipt {
  const operations = [...accounting.values()].map((entry) => Object.freeze({
    operation: entry.operation,
    channel: entry.channel,
    delivery_state: entry.deliveryState,
    scope_decision: entry.scopeDecision,
    policy_decision: entry.policyDecision,
    ipc_dispatch_count: entry.ipcDispatchCount,
    hardware_execution_count: entry.hardwareExecutionCount,
    execution_started_at: entry.startedAt,
    execution_completed_at: entry.completedAt,
    canonical_result: entry.canonicalResult,
    failure_code: entry.failureCode,
  }));
  const pwm = accounting.get("hardware.measure_pwm");
  const failure = fallbackFailure ?? [...accounting.values()].find((entry) => entry.failureCode !== null)?.failureCode ?? null;
  const status = pwm?.deliveryState === "SENT_UNCONFIRMED"
    ? "UNKNOWN" as const
    : failure !== null
      ? "FAILED" as const
      : pwm?.canonicalResult?.ok === true
        ? "COMPLETED" as const
        : "FAILED" as const;
  return boundedReceipt(request, status, operations, pwm?.teachingEvidence ?? null, failure, contract);
}

function boundedReceipt(
  request: JsonObject | null,
  status: "COMPLETED" | "FAILED" | "UNKNOWN",
  operations: readonly JsonObject[],
  evidence: JsonObject | null,
  failureCode: string | null,
  contract: Phase8B3ValidationContractBinding,
): Phase8B3ValidationReceipt {
  const value = Object.freeze({
    contract: "aia-phase8b3-validation",
    contract_version: "1.0",
    kind: "governed_hardware_receipt",
    run_id: typeof request?.run_id === "string" ? request.run_id : "00000000-0000-4000-8000-000000000000",
    workflow_id: typeof request?.workflow_id === "string" ? request.workflow_id : "invalid-request",
    request_correlation_id: typeof request?.request_correlation_id === "string" ? request.request_correlation_id : "invalid-request",
    status,
    operations: Object.freeze([...operations]),
    pwm_teaching_evidence: evidence,
    failure_code: failureCode,
    limitations: Object.freeze([
      "Validation-only inherited-stdio receipt; it is not an authorization source.",
      "JLCEDA snapshot identity binds an observation and does not prove later design immutability.",
    ]),
  });
  return contract.requireValid(PHASE8B3_RECEIPT_SCHEMA_ID, value) as Phase8B3ValidationReceipt;
}

function failureFromDecisions(entry: OperationAccounting): string {
  if (entry.scopeDecision?.decision === "DENY") return "operation_scope_denied";
  if (entry.policyDecision?.decision === "REQUIRE_CONFIRMATION") return "policy_confirmation_required";
  if (entry.policyDecision?.decision === "DENY") return "policy_denied";
  return "validation_executor_failure";
}

function parseTeachingEvidence(contexts: readonly { readonly content: readonly unknown[] }[] | undefined): JsonObject | null {
  for (const context of contexts ?? []) {
    for (const block of context.content) {
      const value = optionalObject(block);
      if (value?.type !== "text" || typeof value.text !== "string") continue;
      const marker = "AIA_TEACHING_EVIDENCE_CONTEXT\n";
      if (!value.text.startsWith(marker)) continue;
      const parsed: unknown = JSON.parse(value.text.slice(marker.length));
      const internal = object(parsed, "TeachingEvidenceContext");
      return EvidenceContractBinding.fromRepository("").toWire(
        internal as unknown as TeachingEvidenceContext,
      );
    }
  }
  return null;
}

function object(value: unknown, name: string): JsonObject {
  const result = optionalObject(value);
  if (result === undefined) throw new TypeError(`${name} must be an object`);
  return result;
}

function optionalObject(value: unknown): JsonObject | undefined {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as JsonObject
    : undefined;
}

function text(value: unknown): string {
  if (typeof value !== "string" || value.length === 0) throw new TypeError("expected bounded text");
  return value;
}

function number(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new TypeError("expected finite number");
  return value;
}

function channel(value: unknown): 1 | 2 {
  if (value !== 1 && value !== 2) throw new TypeError("expected channel 1 or 2");
  return value;
}
