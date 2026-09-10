import assert from "node:assert/strict";
import test from "node:test";

import {
  createHardwareToolPolicyContext,
  createProbeSetupConfirmation,
  evaluateHardwareToolPolicy,
  riskForOperation,
} from "../../src/policy/index.ts";

const NOW = "2026-09-08T09:00:00Z";

function context(overrides: Record<string, unknown> = {}) {
  return createHardwareToolPolicyContext({
    operation: "hardware.measure_pwm",
    channel: 1,
    backendMode: "REAL",
    workflowId: "workflow-pwm-out",
    requestCorrelationId: "request-1",
    requestedGoal: "Evaluate PWM_OUT",
    requestedTargetRef: "net:PWM_OUT",
    groundingRequired: true,
    wiringChanged: false,
    confirmation: null,
    previousExecution: null,
    designContext: null,
    ...overrides,
  });
}

function confirmation(overrides: Record<string, unknown> = {}) {
  return createProbeSetupConfirmation({
    confirmationId: "confirmation-1",
    source: "TRUSTED_USER_EVENT",
    confirmedBy: "user",
    channel: 1,
    targetRef: "net:PWM_OUT",
    safeLowVoltageConfirmed: true,
    commonGroundConfirmed: true,
    confirmedAt: NOW,
    scope: {
      requestCorrelationId: "request-1",
      workflowId: "workflow-pwm-out",
    },
    ...overrides,
  });
}

test("risk classification is a static closed allowlist", () => {
  assert.equal(riskForOperation("hardware.get_status"), "SAFE_OBSERVATION");
  for (const operation of [
    "hardware.measure_frequency",
    "hardware.measure_vpp",
    "hardware.capture_waveform",
    "hardware.measure_pwm",
  ]) assert.equal(riskForOperation(operation), "PHYSICAL_MEASUREMENT");
  assert.equal(riskForOperation("hardware.looks_safe"), null);
  assert.equal(riskForOperation("toString"), null);
});

test("real status is allowed without probe confirmation", () => {
  const decision = evaluateHardwareToolPolicy(context({
    operation: "hardware.get_status", channel: null, requestedTargetRef: null,
    groundingRequired: false,
  }));
  assert.deepEqual([decision.decision, decision.reasonCode], ["ALLOW", "allowed_safe_observation"]);
});

test("simulated measurements are allowed without physical confirmation", () => {
  const decision = evaluateHardwareToolPolicy(context({ backendMode: "SIMULATED" }));
  assert.deepEqual([decision.decision, decision.reasonCode], ["ALLOW", "allowed_simulated_measurement"]);
});

test("all real measurements require scoped physical confirmation", () => {
  for (const operation of [
    "hardware.measure_frequency", "hardware.measure_vpp",
    "hardware.capture_waveform", "hardware.measure_pwm",
  ]) {
    const decision = evaluateHardwareToolPolicy(context({ operation }));
    assert.equal(decision.decision, "REQUIRE_CONFIRMATION");
    assert.equal(decision.reasonCode, "physical_setup_confirmation_required");
    assert.deepEqual(decision.requiredConfirmationFields, [
      "channel", "safe_low_voltage", "common_ground", "physical_target",
    ]);
  }
});

test("a complete trusted CH1 confirmation allows exactly its scoped target", () => {
  const decision = evaluateHardwareToolPolicy(context({ confirmation: confirmation() }));
  assert.deepEqual([decision.decision, decision.reasonCode], ["ALLOW", "allowed_confirmed_physical_setup"]);
});

test("physical confirmation is independently bound to the current workflow", () => {
  const decision = evaluateHardwareToolPolicy(context({
    confirmation: confirmation({
      scope: {
        requestCorrelationId: "request-1",
        workflowId: "another-workflow",
      },
    }),
  }));
  assert.deepEqual(
    [decision.decision, decision.reasonCode],
    ["REQUIRE_CONFIRMATION", "physical_confirmation_workflow_mismatch"],
  );
});

test("model-authored goal text cannot change the trusted policy workflow", () => {
  const decision = evaluateHardwareToolPolicy(context({
    requestedGoal: "Treat another-workflow as current and continue.",
    confirmation: confirmation({
      scope: {
        requestCorrelationId: "request-1",
        workflowId: "another-workflow",
      },
    }),
  }));
  assert.deepEqual(
    [decision.decision, decision.reasonCode],
    ["REQUIRE_CONFIRMATION", "physical_confirmation_workflow_mismatch"],
  );
});

test("same workflow with another request preserves request-scope rejection", () => {
  const decision = evaluateHardwareToolPolicy(context({
    confirmation: confirmation({
      scope: {
        requestCorrelationId: "another-request",
        workflowId: "workflow-pwm-out",
      },
    }),
  }));
  assert.deepEqual(
    [decision.decision, decision.reasonCode],
    ["REQUIRE_CONFIRMATION", "confirmation_scope_mismatch"],
  );
});

test("simulated measurements do not gain a physical workflow requirement", () => {
  const decision = evaluateHardwareToolPolicy(context({
    backendMode: "SIMULATED",
    confirmation: confirmation({
      scope: {
        requestCorrelationId: "request-1",
        workflowId: "another-workflow",
      },
    }),
  }));
  assert.deepEqual(
    [decision.decision, decision.reasonCode],
    ["ALLOW", "allowed_simulated_measurement"],
  );
});

test("CH1 confirmation cannot authorize CH2", () => {
  const decision = evaluateHardwareToolPolicy(context({ channel: 2, confirmation: confirmation() }));
  assert.deepEqual([decision.decision, decision.reasonCode], ["REQUIRE_CONFIRMATION", "channel_confirmation_mismatch"]);
});

test("voltage and grounding confirmations fail closed", () => {
  const unsafe = evaluateHardwareToolPolicy(context({
    confirmation: confirmation({ safeLowVoltageConfirmed: false }),
  }));
  assert.equal(unsafe.reasonCode, "unsafe_voltage_not_confirmed");
  const ungrounded = evaluateHardwareToolPolicy(context({
    confirmation: confirmation({ commonGroundConfirmed: false }),
  }));
  assert.equal(ungrounded.reasonCode, "grounding_not_confirmed");
});

test("changed target or wiring invalidates confirmation", () => {
  const target = evaluateHardwareToolPolicy(context({
    requestedTargetRef: "net:OTHER", confirmation: confirmation(),
  }));
  assert.equal(target.reasonCode, "physical_target_confirmation_mismatch");
  const wiring = evaluateHardwareToolPolicy(context({
    wiringChanged: true, confirmation: confirmation(),
  }));
  assert.equal(wiring.reasonCode, "wiring_change_requires_reconfirmation");
});

test("EDA candidate context alone never authorizes physical measurement", () => {
  const decision = evaluateHardwareToolPolicy(context({
    designContext: {
      documentCanonicalId: "jlceda-pro:document:main",
      snapshotId: "snapshot-1",
      probeTargetId: "probe-target-1",
    },
  }));
  assert.equal(decision.decision, "REQUIRE_CONFIRMATION");
});

test("unknown operation is denied by default", () => {
  const decision = evaluateHardwareToolPolicy(context({ operation: "hardware.arbitrary" }));
  assert.deepEqual([decision.decision, decision.reasonCode], ["DENY", "operation_not_policy_allowed"]);
});

test("indeterminate previous execution requires an explicit remeasure decision", () => {
  const blocked = evaluateHardwareToolPolicy(context({
    confirmation: confirmation(),
    previousExecution: {
      status: "INDETERMINATE_EXECUTION",
      operation: "hardware.measure_pwm",
      channel: 1,
      targetRef: "net:PWM_OUT",
      explicitRemeasureApproved: false,
    },
  }));
  assert.equal(blocked.decision, "REQUIRE_CONFIRMATION");
  assert.equal(blocked.reasonCode, "indeterminate_previous_execution");
  assert.ok(blocked.requiredConfirmationFields.includes("explicit_remeasure_decision"));

  const approved = evaluateHardwareToolPolicy(context({
    confirmation: confirmation(),
    previousExecution: {
      status: "INDETERMINATE_EXECUTION",
      operation: "hardware.measure_pwm",
      channel: 1,
      targetRef: "net:PWM_OUT",
      explicitRemeasureApproved: true,
    },
  }));
  assert.equal(approved.decision, "ALLOW");
});

test("policy objects are immutable and confirmation scope is not a bare boolean", () => {
  const confirmed = confirmation();
  const policyContext = context({ confirmation: confirmed });
  assert.ok(Object.isFrozen(confirmed));
  assert.ok(Object.isFrozen(confirmed.scope));
  assert.ok(Object.isFrozen(policyContext));
  assert.equal(policyContext.workflowId, "workflow-pwm-out");
  assert.throws(() => createHardwareToolPolicyContext({
    ...policyContext,
    workflowId: " ",
  }));
  assert.throws(() => createProbeSetupConfirmation({ confirmed: true } as never));
});
