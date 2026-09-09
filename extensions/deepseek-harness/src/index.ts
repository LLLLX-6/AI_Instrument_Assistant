import type { Context } from "@deepseek-ai/cordis";

import { applyWithDependencies, type Config } from "./plugin.ts";

export const name = "aia-hardware-tools";
export const inject = ["tools", "systemPrompt"];

export function apply(ctx: Context, config: Config = {}): void {
  applyWithDependencies(ctx, config);
}

export { applyWithDependencies } from "./plugin.ts";
export type { Config, HardwareClientPort, PluginDependencies } from "./plugin.ts";
export {
  OperationScopeGate,
  SEMANTIC_HARDWARE_OPERATIONS,
  createTrustedOperationScope,
  isSemanticHardwareOperation,
} from "./operation-scope/index.ts";
export type {
  OperationScopeDecision,
  OperationScopeReasonCode,
  SemanticHardwareOperation,
  TrustedOperationScope,
  TrustedOperationScopeContext,
  TrustedOperationScopeOrigin,
} from "./operation-scope/index.ts";
export {
  createHardwareToolPolicyContext,
  createProbeSetupConfirmation,
  evaluateHardwareToolPolicy,
  riskForOperation,
} from "./policy/index.ts";
export { presentAdapterFailure, presentHardwareResult } from "./evidence/index.ts";
export type { HardwareToolPolicyContext, PolicyDecision } from "./policy/index.ts";
export type { TeachingEvidenceContext } from "./evidence/index.ts";
export {
  createTeachingEvidenceMessage,
  HARDWARE_AGENT_POLICY,
  installHarnessAgentEgressBoundary,
  serializeTeachingEvidenceContext,
} from "./agent/index.ts";
export {
  AgentEgressStateStore,
  inspectEgressCandidate,
  renderSafeAgentFallback,
  toEgressDiagnostic,
} from "./egress/index.ts";
export type {
  EgressDiagnostic,
  EgressInspectionResult,
  EgressSource,
  EgressViolation,
  EgressViolationCategory,
} from "./egress/index.ts";
