import {
  isSemanticHardwareOperation,
  operationScopeDecision,
  type OperationScopeDecision,
  type OperationScopeRequest,
  type TrustedOperationScope,
} from "./models.ts";

export class OperationScopeGate {
  private readonly dispatchCounts = new Map<string, number>();

  evaluate(scope: TrustedOperationScope, request: OperationScopeRequest): OperationScopeDecision {
    if (!isSemanticHardwareOperation(request.operation)) {
      return operationScopeDecision("DENY", "unknown_operation", 0);
    }
    if (request.workflowId !== scope.workflowId
      || request.requestCorrelationId !== scope.requestCorrelationId) {
      return operationScopeDecision("DENY", "workflow_scope_mismatch", 0);
    }
    const budget = scope.allowedOperations.find((entry) => entry.operation === request.operation);
    if (budget === undefined) {
      return operationScopeDecision("DENY", "operation_not_authorized", 0);
    }
    if (scope.targetChannel !== null && request.channel !== scope.targetChannel) {
      return operationScopeDecision("DENY", "channel_out_of_scope", remaining(scope, budget.operation, budget.maxInvocations, this.dispatchCounts));
    }
    const available = remaining(scope, budget.operation, budget.maxInvocations, this.dispatchCounts);
    if (available <= 0) {
      return operationScopeDecision("DENY", "invocation_budget_exhausted", 0);
    }
    return operationScopeDecision("ALLOW", "allowed_operation_in_scope", available);
  }

  authorizeDispatch(scope: TrustedOperationScope, request: OperationScopeRequest): OperationScopeDecision {
    const decision = this.evaluate(scope, request);
    if (decision.decision === "DENY") return decision;
    const key = ledgerKey(scope.scopeId, request.operation);
    this.dispatchCounts.set(key, (this.dispatchCounts.get(key) ?? 0) + 1);
    return operationScopeDecision("ALLOW", "allowed_operation_in_scope", decision.remainingInvocations - 1);
  }
}

function remaining(
  scope: TrustedOperationScope,
  operation: string,
  maximum: number,
  counts: ReadonlyMap<string, number>,
): number {
  return Math.max(0, maximum - (counts.get(ledgerKey(scope.scopeId, operation)) ?? 0));
}

function ledgerKey(scopeId: string, operation: string): string {
  return `${scopeId}\u0000${operation}`;
}
