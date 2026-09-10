import {
  policyDecision,
  type HardwareToolPolicyContext,
  type PolicyDecision,
  type ToolRisk,
} from "./models.ts";

const CONFIRMATION_FIELDS = Object.freeze([
  "channel", "safe_low_voltage", "common_ground", "physical_target",
] as const);

export function riskForOperation(operation: string): ToolRisk | null {
  switch (operation) {
    case "hardware.get_status": return "SAFE_OBSERVATION";
    case "hardware.measure_frequency":
    case "hardware.measure_vpp":
    case "hardware.capture_waveform":
    case "hardware.measure_pwm": return "PHYSICAL_MEASUREMENT";
    default: return null;
  }
}

export function evaluateHardwareToolPolicy(context: HardwareToolPolicyContext): PolicyDecision {
  const risk = riskForOperation(context.operation);
  if (risk === null) return policyDecision(
    "DENY", "operation_not_policy_allowed", "This hardware operation is not allowed by policy.",
  );
  if (risk === "SAFE_OBSERVATION") return policyDecision(
    "ALLOW", "allowed_safe_observation", "The requested operation is an allowed safe observation.",
  );
  if (context.backendMode === "SIMULATED") return policyDecision(
    "ALLOW", "allowed_simulated_measurement", "The measurement uses an explicitly simulated backend.",
  );

  const previous = context.previousExecution;
  if (previous !== null
    && previous.operation === context.operation
    && previous.channel === context.channel
    && previous.targetRef === context.requestedTargetRef
    && !previous.explicitRemeasureApproved) {
    return policyDecision(
      "REQUIRE_CONFIRMATION",
      "indeterminate_previous_execution",
      "The previous execution is indeterminate; the user must explicitly decide whether to measure again.",
      ["explicit_remeasure_decision"],
    );
  }

  const confirmation = context.confirmation;
  if (confirmation === null) return policyDecision(
    "REQUIRE_CONFIRMATION",
    "physical_setup_confirmation_required",
    "Physical setup confirmation is required before this hardware measurement.",
    context.groundingRequired
      ? CONFIRMATION_FIELDS
      : ["channel", "safe_low_voltage", "physical_target"],
  );
  if (confirmation.source !== "TRUSTED_USER_EVENT") return policyDecision(
    "DENY", "untrusted_confirmation_source", "Physical confirmation must come from a trusted user event.",
  );
  if (context.channel !== confirmation.channel) return policyDecision(
    "REQUIRE_CONFIRMATION", "channel_confirmation_mismatch", "Confirmation does not cover the requested channel.", ["channel"],
  );
  if (confirmation.scope.requestCorrelationId !== context.requestCorrelationId) return policyDecision(
    "REQUIRE_CONFIRMATION", "confirmation_scope_mismatch", "Confirmation does not cover this request.",
    context.groundingRequired ? CONFIRMATION_FIELDS : ["channel", "safe_low_voltage", "physical_target"],
  );
  if (confirmation.scope.workflowId !== context.workflowId) return policyDecision(
    "REQUIRE_CONFIRMATION",
    "physical_confirmation_workflow_mismatch",
    "Physical confirmation does not cover the current workflow.",
    context.groundingRequired ? CONFIRMATION_FIELDS : ["channel", "safe_low_voltage", "physical_target"],
  );
  if (context.wiringChanged) return policyDecision(
    "REQUIRE_CONFIRMATION", "wiring_change_requires_reconfirmation", "Wiring changed after confirmation and must be confirmed again.",
    context.groundingRequired ? CONFIRMATION_FIELDS : ["channel", "safe_low_voltage", "physical_target"],
  );
  if (context.requestedTargetRef !== confirmation.targetRef) return policyDecision(
    "REQUIRE_CONFIRMATION", "physical_target_confirmation_mismatch", "Confirmation does not cover the requested physical target.", ["physical_target"],
  );
  if (!confirmation.safeLowVoltageConfirmed) return policyDecision(
    "REQUIRE_CONFIRMATION", "unsafe_voltage_not_confirmed", "Safe low-voltage operation has not been confirmed.", ["safe_low_voltage"],
  );
  if (context.groundingRequired && !confirmation.commonGroundConfirmed) return policyDecision(
    "REQUIRE_CONFIRMATION", "grounding_not_confirmed", "An appropriate common ground has not been confirmed.", ["common_ground"],
  );
  return policyDecision(
    "ALLOW", "allowed_confirmed_physical_setup", "The trusted physical setup confirmation covers this measurement.",
  );
}
