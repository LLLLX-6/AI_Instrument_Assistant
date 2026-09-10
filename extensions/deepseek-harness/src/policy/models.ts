export type BackendMode = "REAL" | "SIMULATED";
export type ToolRisk = "SAFE_OBSERVATION" | "PHYSICAL_MEASUREMENT";
export type PolicyDecisionKind = "ALLOW" | "REQUIRE_CONFIRMATION" | "DENY";
export type ConfirmationField =
  | "channel"
  | "safe_low_voltage"
  | "common_ground"
  | "physical_target"
  | "explicit_remeasure_decision";

export type PolicyReasonCode =
  | "allowed_safe_observation"
  | "allowed_simulated_measurement"
  | "allowed_confirmed_physical_setup"
  | "physical_setup_confirmation_required"
  | "channel_confirmation_mismatch"
  | "unsafe_voltage_not_confirmed"
  | "grounding_not_confirmed"
  | "physical_target_confirmation_mismatch"
  | "confirmation_scope_mismatch"
  | "physical_confirmation_workflow_mismatch"
  | "wiring_change_requires_reconfirmation"
  | "indeterminate_previous_execution"
  | "untrusted_confirmation_source"
  | "operation_not_policy_allowed";

export interface ConfirmationScope {
  readonly requestCorrelationId: string;
  readonly workflowId: string;
}

export interface ProbeSetupConfirmation {
  readonly confirmationId: string;
  readonly source: "TRUSTED_USER_EVENT";
  readonly confirmedBy: string;
  readonly channel: 1 | 2;
  readonly targetRef: string | null;
  readonly safeLowVoltageConfirmed: boolean;
  readonly commonGroundConfirmed: boolean;
  readonly confirmedAt: string;
  readonly scope: ConfirmationScope;
}

export interface DesignContextReference {
  readonly documentCanonicalId: string;
  readonly snapshotId: string;
  readonly probeTargetId: string | null;
}

export interface PreviousExecution {
  readonly status: "INDETERMINATE_EXECUTION";
  readonly operation: string;
  readonly channel: 1 | 2;
  readonly targetRef: string | null;
  readonly explicitRemeasureApproved: boolean;
}

export interface HardwareToolPolicyContext {
  readonly operation: string;
  readonly channel: 1 | 2 | null;
  readonly backendMode: BackendMode;
  readonly workflowId: string;
  readonly requestCorrelationId: string;
  readonly requestedGoal: string;
  readonly requestedTargetRef: string | null;
  readonly groundingRequired: boolean;
  readonly wiringChanged: boolean;
  readonly confirmation: ProbeSetupConfirmation | null;
  readonly previousExecution: PreviousExecution | null;
  readonly designContext: DesignContextReference | null;
}

export interface PolicyDecision {
  readonly decision: PolicyDecisionKind;
  readonly reasonCode: PolicyReasonCode;
  readonly explanation: string;
  readonly requiredConfirmationFields: readonly ConfirmationField[];
}

export interface ProbeSetupConfirmationInput {
  readonly confirmationId: string;
  readonly source: "TRUSTED_USER_EVENT";
  readonly confirmedBy: string;
  readonly channel: number;
  readonly targetRef: string | null;
  readonly safeLowVoltageConfirmed: boolean;
  readonly commonGroundConfirmed: boolean;
  readonly confirmedAt: string;
  readonly scope: ConfirmationScope;
}

export interface HardwareToolPolicyContextInput {
  readonly operation: string;
  readonly channel: number | null;
  readonly backendMode: BackendMode;
  readonly workflowId: string;
  readonly requestCorrelationId: string;
  readonly requestedGoal: string;
  readonly requestedTargetRef: string | null;
  readonly groundingRequired: boolean;
  readonly wiringChanged: boolean;
  readonly confirmation: ProbeSetupConfirmation | null;
  readonly previousExecution: PreviousExecution | null;
  readonly designContext: DesignContextReference | null;
}

export function createProbeSetupConfirmation(input: ProbeSetupConfirmationInput): ProbeSetupConfirmation {
  const value = record(input, "confirmation");
  if (value.source !== "TRUSTED_USER_EVENT") throw new TypeError("confirmation source must be trusted user event");
  const scopeValue = record(value.scope, "confirmation scope");
  const scope = Object.freeze({
    requestCorrelationId: boundedText(scopeValue.requestCorrelationId, "requestCorrelationId"),
    workflowId: boundedText(scopeValue.workflowId, "workflowId"),
  });
  return Object.freeze({
    confirmationId: boundedText(value.confirmationId, "confirmationId"),
    source: "TRUSTED_USER_EVENT",
    confirmedBy: boundedText(value.confirmedBy, "confirmedBy"),
    channel: channel(value.channel),
    targetRef: optionalText(value.targetRef, "targetRef"),
    safeLowVoltageConfirmed: boolean(value.safeLowVoltageConfirmed, "safeLowVoltageConfirmed"),
    commonGroundConfirmed: boolean(value.commonGroundConfirmed, "commonGroundConfirmed"),
    confirmedAt: timestamp(value.confirmedAt, "confirmedAt"),
    scope,
  });
}

export function createHardwareToolPolicyContext(input: HardwareToolPolicyContextInput): HardwareToolPolicyContext {
  const value = record(input, "policy context");
  const requestedChannel = value.channel === null ? null : channel(value.channel);
  if (value.backendMode !== "REAL" && value.backendMode !== "SIMULATED") {
    throw new TypeError("backendMode must be REAL or SIMULATED");
  }
  const confirmation = value.confirmation === null
    ? null
    : createProbeSetupConfirmation(value.confirmation as ProbeSetupConfirmationInput);
  const previous = value.previousExecution === null ? null : freezePrevious(value.previousExecution);
  const design = value.designContext === null ? null : freezeDesignContext(value.designContext);
  return Object.freeze({
    operation: boundedText(value.operation, "operation", 128),
    channel: requestedChannel,
    backendMode: value.backendMode,
    workflowId: boundedText(value.workflowId, "workflowId"),
    requestCorrelationId: boundedText(value.requestCorrelationId, "requestCorrelationId"),
    requestedGoal: boundedText(value.requestedGoal, "requestedGoal"),
    requestedTargetRef: optionalText(value.requestedTargetRef, "requestedTargetRef"),
    groundingRequired: boolean(value.groundingRequired, "groundingRequired"),
    wiringChanged: boolean(value.wiringChanged, "wiringChanged"),
    confirmation,
    previousExecution: previous,
    designContext: design,
  });
}

export function policyDecision(
  decision: PolicyDecisionKind,
  reasonCode: PolicyReasonCode,
  explanation: string,
  required: readonly ConfirmationField[] = [],
): PolicyDecision {
  return Object.freeze({
    decision,
    reasonCode,
    explanation: boundedText(explanation, "explanation", 256),
    requiredConfirmationFields: Object.freeze([...required]),
  });
}

function freezePrevious(value: unknown): PreviousExecution {
  const previous = record(value, "previousExecution");
  if (previous.status !== "INDETERMINATE_EXECUTION") throw new TypeError("unsupported previous execution status");
  return Object.freeze({
    status: "INDETERMINATE_EXECUTION",
    operation: boundedText(previous.operation, "previous operation", 128),
    channel: channel(previous.channel),
    targetRef: optionalText(previous.targetRef, "previous targetRef"),
    explicitRemeasureApproved: boolean(previous.explicitRemeasureApproved, "explicitRemeasureApproved"),
  });
}

function freezeDesignContext(value: unknown): DesignContextReference {
  const design = record(value, "designContext");
  return Object.freeze({
    documentCanonicalId: boundedText(design.documentCanonicalId, "documentCanonicalId"),
    snapshotId: boundedText(design.snapshotId, "snapshotId"),
    probeTargetId: optionalText(design.probeTargetId, "probeTargetId"),
  });
}

function record(value: unknown, name: string): Readonly<Record<string, unknown>> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new TypeError(`${name} must be an object`);
  return value as Readonly<Record<string, unknown>>;
}

function channel(value: unknown): 1 | 2 {
  if (value !== 1 && value !== 2) throw new TypeError("channel must be 1 or 2");
  return value;
}

function boolean(value: unknown, name: string): boolean {
  if (typeof value !== "boolean") throw new TypeError(`${name} must be boolean`);
  return value;
}

function boundedText(value: unknown, name: string, maximum = 512): string {
  if (typeof value !== "string" || !value.trim() || value.length > maximum) throw new TypeError(`${name} must be bounded text`);
  return value.trim();
}

function optionalText(value: unknown, name: string): string | null {
  return value === null ? null : boundedText(value, name);
}

function timestamp(value: unknown, name: string): string {
  const text = boundedText(value, name, 64);
  if (!Number.isFinite(Date.parse(text)) || !/(?:Z|[+-]\d{2}:\d{2})$/i.test(text)) {
    throw new TypeError(`${name} must be a timezone-bearing ISO timestamp`);
  }
  return text;
}
