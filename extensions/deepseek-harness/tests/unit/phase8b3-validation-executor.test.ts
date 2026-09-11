import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

import type { HardwareClientPort } from "../../src/index.ts";
import { AdapterFailure } from "../../src/ipc/errors.ts";
import type { HardwareOperation } from "../../src/generated/hardware-tools.generated.ts";
import { executeGovernedHardwareValidation } from "../../validation/phase8b3-executor.ts";
import { SIMULATED_PWM_RESULT, STATUS_RESULT } from "../support/canonical-results.ts";

const repositoryRoot = resolve(new URL("../../../..", import.meta.url).pathname.replace(/^\/(.:)/, "$1"));
const REQUEST = JSON.parse(readFileSync(resolve(
  repositoryRoot,
  "validation/support/phase8b3/v1/fixtures/valid/governed-hardware-request.case.json",
), "utf8")).instance;

const PHYSICAL_PWM_RESULT = {
  ...SIMULATED_PWM_RESULT,
  result: {
    ...SIMULATED_PWM_RESULT.result,
    instrument: {
      manufacturer: "RIGOL TECHNOLOGIES",
      model: "DS1102Z-E",
      serial_number: "***9517",
      firmware_version: "00.06.03.SP2",
    },
    observations: {
      ...SIMULATED_PWM_RESULT.result.observations,
      instrument_frequency: {
        ...(SIMULATED_PWM_RESULT.result.observations.instrument_frequency as object),
        source: "instrument",
        method: "oscilloscope measurement query",
      },
      instrument_vpp: {
        ...(SIMULATED_PWM_RESULT.result.observations.instrument_vpp as object),
        source: "instrument",
        method: "oscilloscope measurement query",
      },
    },
  },
} as const;

class ScriptedClient implements HardwareClientPort {
  started = 0;
  disposed = 0;
  readonly calls: Array<{ operation: HardwareOperation; args: unknown }> = [];
  private readonly pwmResult: unknown;

  constructor(pwmResult: unknown = PHYSICAL_PWM_RESULT) { this.pwmResult = pwmResult; }

  start(): void { this.started += 1; }
  async dispose(): Promise<void> { this.disposed += 1; }
  async invoke(operation: HardwareOperation, args: unknown): Promise<unknown> {
    this.calls.push({ operation, args });
    if (operation === "hardware.get_status") return STATUS_RESULT;
    if (this.pwmResult instanceof Error) throw this.pwmResult;
    return this.pwmResult;
  }
}

test("one-shot executor reuses governed Tool path for exact status and PWM scopes", async () => {
  const client = new ScriptedClient();
  const receipt = await executeGovernedHardwareValidation(REQUEST, {
    repositoryRoot,
    createClient: () => client,
  });

  assert.equal(receipt.status, "COMPLETED");
  assert.deepEqual(client.calls.map((item) => item.operation), [
    "hardware.get_status",
    "hardware.measure_pwm",
  ]);
  assert.equal(client.started, 1);
  assert.equal(client.disposed, 1);
  const bounded = receipt as any;
  assert.equal(bounded.operations[0]?.scope_decision?.decision, "ALLOW");
  assert.equal(bounded.operations[0]?.channel, null);
  assert.equal(bounded.operations[0]?.policy_decision?.reason_code, "allowed_safe_observation");
  assert.equal(bounded.operations[1]?.scope_decision?.remaining_invocations, 0);
  assert.equal(bounded.operations[1]?.channel, 1);
  assert.equal(bounded.operations[1]?.policy_decision?.reason_code, "allowed_confirmed_physical_setup");
  assert.equal(bounded.operations[1]?.ipc_dispatch_count, 1);
  assert.equal(bounded.operations[1]?.hardware_execution_count, 1);
  assert.equal(bounded.pwm_teaching_evidence?.inferences.length, 0);
  assert.equal(bounded.pwm_teaching_evidence?.coherence?.software_observations, "same_artifact");
  assert.equal(bounded.pwm_teaching_evidence?.coherence?.instrument_vs_software, "sequential_same_session");
});

test("cross-field identity mismatch fails before client lifecycle", async () => {
  const client = new ScriptedClient();
  const mismatched = structuredClone(REQUEST);
  mismatched.confirmation.workflow_id = "different-workflow";
  const receipt = await executeGovernedHardwareValidation(mismatched, {
    repositoryRoot,
    createClient: () => client,
  });

  assert.equal(receipt.status, "FAILED");
  assert.equal(receipt.failure_code, "contract_semantics_invalid");
  assert.equal(client.started, 0);
  assert.equal(client.calls.length, 0);
  assert.equal(client.disposed, 0);
});

test("all physical-confirmation identity and wiring mismatches fail before client lifecycle", async () => {
  const mutations: Array<(value: any) => void> = [
    (value) => { value.confirmation.workflow_id = "different-workflow"; },
    (value) => { value.confirmation.request_correlation_id = "different-request"; },
    (value) => { value.confirmation.target_ref = "different-target"; },
    (value) => { value.confirmation.channel = 2; },
    (value) => { value.confirmation.wiring_checked = false; },
    (value) => { value.confirmation.wiring_unchanged = false; },
    (value) => { value.pwm_scope.workflow_id = "different-workflow"; },
    (value) => { value.pwm_scope.request_correlation_id = "different-request"; },
  ];
  for (const mutate of mutations) {
    const client = new ScriptedClient();
    const request = structuredClone(REQUEST);
    mutate(request);
    const receipt = await executeGovernedHardwareValidation(request, {
      repositoryRoot,
      createClient: () => client,
    });
    assert.equal(receipt.status, "FAILED");
    assert.equal(client.started, 0);
    assert.equal(client.calls.length, 0);
    assert.equal(receipt.operations.length, 0);
  }
});

test("trusted PWM channel cannot be replaced by a Tool-side channel", async () => {
  const client = new ScriptedClient();
  const request = structuredClone(REQUEST);
  request.pwm_scope.target_channel = 2;
  const receipt = await executeGovernedHardwareValidation(request, {
    repositoryRoot,
    createClient: () => client,
  });

  assert.equal(receipt.status, "FAILED");
  assert.equal(receipt.failure_code, "contract_schema_invalid");
  assert.equal(client.started, 0);
  assert.equal(client.calls.length, 0);
});

test("SENT_UNCONFIRMED is not replayed and consumed PWM budget is retained", async () => {
  const client = new ScriptedClient(new AdapterFailure(
    "indeterminate_execution",
    "Hardware request outcome is indeterminate; it was not replayed.",
    "SENT_UNCONFIRMED",
  ));
  const receipt = await executeGovernedHardwareValidation(REQUEST, {
    repositoryRoot,
    createClient: () => client,
  });

  assert.equal(receipt.status, "UNKNOWN");
  assert.equal(client.calls.filter((item) => item.operation === "hardware.measure_pwm").length, 1);
  const pwm = receipt.operations[1] as any;
  assert.equal(pwm?.delivery_state, "SENT_UNCONFIRMED");
  assert.equal(pwm?.scope_decision?.remaining_invocations, 0);
  assert.equal(pwm?.ipc_dispatch_count, 1);
  assert.equal(pwm?.hardware_execution_count, 0);
  assert.equal(receipt.failure_code, "indeterminate_execution");
});

test("instrument unavailable and other canonical ok=false results are bounded and never retried", async () => {
  for (const code of ["hardware_unavailable", "measurement_failed"] as const) {
    const failed = {
      contract_version: "1.0",
      ok: false,
      operation: "hardware.measure_pwm",
      error: { code, message: "Measurement could not be completed.", details: {} },
    } as const;
    const client = new ScriptedClient(failed);
    const receipt = await executeGovernedHardwareValidation(REQUEST, {
      repositoryRoot,
      createClient: () => client,
    });

    assert.equal(client.calls.filter((item) => item.operation === "hardware.measure_pwm").length, 1);
    assert.equal(receipt.status, "FAILED");
    assert.equal(receipt.operations[1]?.delivery_state, "RESPONSE_RECEIVED");
    assert.deepEqual(receipt.operations[1]?.canonical_result, failed);
  }
});

test("backend unavailable is bounded before PWM and has no retry", async () => {
  const client = new ScriptedClient();
  client.invoke = async (operation, args) => {
    client.calls.push({ operation, args });
    throw new AdapterFailure("backend_unreachable", "Hardware backend is unavailable.", "NOT_SENT");
  };
  const receipt = await executeGovernedHardwareValidation(REQUEST, {
    repositoryRoot,
    createClient: () => client,
  });
  assert.equal(receipt.status, "FAILED");
  assert.equal(receipt.failure_code, "backend_unreachable");
  assert.equal(client.calls.length, 1);
  assert.equal(receipt.operations[0]?.delivery_state, "NOT_SENT");
  assert.equal(receipt.operations[0]?.ipc_dispatch_count, 1);
});

test("degraded and unavailable observations preserve separate sources and coherence", async () => {
  const degraded = structuredClone(PHYSICAL_PWM_RESULT) as any;
  degraded.result.quality = "degraded";
  degraded.result.warnings = ["Instrument frequency unavailable."];
  degraded.result.observations.instrument_frequency = {
    ...degraded.result.observations.instrument_frequency,
    value: null,
    quality: "unavailable",
    warnings: ["No stable trigger."],
  };
  degraded.result.observations.software_frequency = {
    ...degraded.result.observations.software_frequency,
    value: null,
    quality: "unavailable",
    warnings: ["Insufficient edges."],
  };
  const client = new ScriptedClient(degraded);
  const receipt = await executeGovernedHardwareValidation(REQUEST, {
    repositoryRoot,
    createClient: () => client,
  });
  assert.equal(receipt.status, "COMPLETED");
  assert.equal(receipt.pwm_teaching_evidence?.quality, "degraded");
  const evidence = receipt.pwm_teaching_evidence as any;
  assert.equal(evidence.facts[0].source, "instrument");
  assert.equal(evidence.analyses[0].source, "software_analysis");
  assert.equal(evidence.facts[0].value, null);
  assert.equal(evidence.analyses[0].value, null);
  assert.equal(evidence.coherence.software_observations, "same_artifact");
  assert.equal(evidence.coherence.instrument_vs_software, "sequential_same_session");
  assert.doesNotMatch(JSON.stringify(evidence), /"simultaneous"\s*:\s*true|"atomic"\s*:\s*true|averaged_value/i);
});
