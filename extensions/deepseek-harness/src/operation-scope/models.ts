export const SEMANTIC_HARDWARE_OPERATIONS = Object.freeze([
  "hardware.get_status",
  "hardware.measure_frequency",
  "hardware.measure_vpp",
  "hardware.capture_waveform",
  "hardware.measure_pwm",
] as const);

export type SemanticHardwareOperation = typeof SEMANTIC_HARDWARE_OPERATIONS[number];
export type TrustedOperationScopeOrigin =
  | "TRUSTED_HOST_WORKFLOW"
  | "TRUSTED_APPLICATION_INTENT"
  | "TRUSTED_VALIDATION_SCENARIO";

export interface OperationInvocationBudget {
  readonly operation: SemanticHardwareOperation;
  readonly maxInvocations: number;
}

export interface TrustedOperationScope {
  readonly scopeId: string;
  readonly requestCorrelationId: string;
  readonly workflowId: string;
  readonly allowedOperations: readonly OperationInvocationBudget[];
  readonly targetChannel: 1 | 2 | null;
  readonly targetIntent: string | null;
  readonly origin: TrustedOperationScopeOrigin;
  readonly authorizationRef: string | null;
}

export interface TrustedOperationScopeInput {
  readonly scopeId: string;
  readonly requestCorrelationId: string;
  readonly workflowId: string;
  readonly allowedOperations: readonly {
    readonly operation: SemanticHardwareOperation;
    readonly maxInvocations: number;
  }[];
  readonly targetChannel: 1 | 2 | null;
  readonly targetIntent: string | null;
  readonly origin: TrustedOperationScopeOrigin;
  readonly authorizationRef: string | null;
}

export interface OperationScopeRequest {
  readonly requestCorrelationId: string;
  readonly workflowId: string;
  readonly operation: string;
  readonly channel: 1 | 2 | null;
}

export interface TrustedOperationScopeContext {
  readonly scope: TrustedOperationScope;
  readonly requestCorrelationId: string;
  readonly workflowId: string;
}

export type OperationScopeDecisionKind = "ALLOW" | "DENY";
export type OperationScopeReasonCode =
  | "allowed_operation_in_scope"
  | "operation_not_authorized"
  | "invocation_budget_exhausted"
  | "channel_out_of_scope"
  | "workflow_scope_mismatch"
  | "unknown_operation";

export interface OperationScopeDecision {
  readonly decision: OperationScopeDecisionKind;
  readonly reasonCode: OperationScopeReasonCode;
  readonly remainingInvocations: number;
}

export function createTrustedOperationScope(input: TrustedOperationScopeInput): TrustedOperationScope {
  const operations = new Set<string>();
  const budgets = input.allowedOperations.map((entry) => {
    if (!isSemanticHardwareOperation(entry.operation)) throw new TypeError("operation scope contains an unknown operation");
    if (operations.has(entry.operation)) throw new TypeError("operation scope contains a duplicate operation");
    if (!Number.isSafeInteger(entry.maxInvocations) || entry.maxInvocations <= 0) {
      throw new TypeError("operation invocation budget must be a positive integer");
    }
    operations.add(entry.operation);
    return Object.freeze({ operation: entry.operation, maxInvocations: entry.maxInvocations });
  });
  if (input.targetChannel !== null && input.targetChannel !== 1 && input.targetChannel !== 2) {
    throw new TypeError("targetChannel must be 1, 2, or null");
  }
  if (!isScopeOrigin(input.origin)) throw new TypeError("operation scope origin is not trusted");
  return Object.freeze({
    scopeId: boundedText(input.scopeId, "scopeId"),
    requestCorrelationId: boundedText(input.requestCorrelationId, "requestCorrelationId"),
    workflowId: boundedText(input.workflowId, "workflowId"),
    allowedOperations: Object.freeze(budgets),
    targetChannel: input.targetChannel,
    targetIntent: optionalBoundedText(input.targetIntent, "targetIntent"),
    origin: input.origin,
    authorizationRef: optionalBoundedText(input.authorizationRef, "authorizationRef"),
  });
}

export function isSemanticHardwareOperation(value: string): value is SemanticHardwareOperation {
  return (SEMANTIC_HARDWARE_OPERATIONS as readonly string[]).includes(value);
}

export function operationScopeDecision(
  decision: OperationScopeDecisionKind,
  reasonCode: OperationScopeReasonCode,
  remainingInvocations: number,
): OperationScopeDecision {
  return Object.freeze({ decision, reasonCode, remainingInvocations });
}

function isScopeOrigin(value: string): value is TrustedOperationScopeOrigin {
  return value === "TRUSTED_HOST_WORKFLOW"
    || value === "TRUSTED_APPLICATION_INTENT"
    || value === "TRUSTED_VALIDATION_SCENARIO";
}

function boundedText(value: string, field: string): string {
  if (typeof value !== "string" || value.length === 0 || value.length > 256) {
    throw new TypeError(`${field} must contain 1 to 256 characters`);
  }
  return value;
}

function optionalBoundedText(value: string | null, field: string): string | null {
  return value === null ? null : boundedText(value, field);
}
