import assert from "node:assert/strict";
import test from "node:test";

import {
  inspectEgressCandidate,
  toEgressDiagnostic,
  type EgressViolationCategory,
} from "../../src/egress/index.ts";

const correlationId = "phase7c4a-test";

function inspect(candidate: string, knownSensitiveValues: readonly string[] = []) {
  return inspectEgressCandidate({
    candidate,
    source: "FINAL_RESPONSE",
    correlationId,
    knownSensitiveValues,
  });
}

function assertUnsafe(candidate: string, category: EgressViolationCategory, known: readonly string[] = []): void {
  const result = inspect(candidate, known);
  assert.equal(result.status, "UNSAFE");
  if (result.status === "UNSAFE") {
    assert.ok(result.violations.some((violation) => violation.category === category));
    assert.ok(result.violations.every((violation) => !Object.hasOwn(violation, "matchedValue")));
  }
}

test("safe normal electronics prose passes", () => {
  const result = inspect("FACT: frequency is 10 kHz. ANALYSIS: duty is 30%.");
  assert.deepEqual(result, { status: "SAFE" });
  assert.ok(Object.isFrozen(result));
});

test("Windows drive, slash, UNC, and POSIX absolute paths are blocked", () => {
  assertUnsafe("saved under C:\\Users\\operator\\capture.bin", "LOCAL_PATH");
  assertUnsafe("saved under D:/work/capture.bin", "LOCAL_PATH");
  assertUnsafe("saved under \\\\lab-server\\share\\capture.bin", "LOCAL_PATH");
  assertUnsafe("saved under /home/operator/capture.bin", "LOCAL_PATH");
  assertUnsafe("temporary output is /tmp/capture.bin", "LOCAL_PATH");
  assertUnsafe("saved under /Users/operator/capture.bin", "LOCAL_PATH");
});

test("conceptual path teaching prose remains allowed", () => {
  assert.equal(inspect("The local path is intentionally hidden.").status, "SAFE");
  assert.equal(inspect("Windows paths are not shown.").status, "SAFE");
});

test("VISA resource identifiers are blocked while conceptual VISA prose is allowed", () => {
  assertUnsafe("resource USB0::0x1AB1::0x0517::DEVICE::INSTR", "VISA_RESOURCE_IDENTIFIER");
  assertUnsafe("resource TCPIP0::192.0.2.1::INSTR", "VISA_RESOURCE_IDENTIFIER");
  assertUnsafe("resource GPIB0::7::INSTR", "VISA_RESOURCE_IDENTIFIER");
  assertUnsafe("resource ASRL3::INSTR", "VISA_RESOURCE_IDENTIFIER");
  assert.equal(inspect("The system does not expose VISA resources.").status, "SAFE");
});

test("command-shaped instrument strings are blocked while conceptual SCPI prose is allowed", () => {
  assertUnsafe("run :MEASure:FREQuency? now", "RAW_INSTRUMENT_COMMAND");
  assertUnsafe("run :WAV:DATA? now", "RAW_INSTRUMENT_COMMAND");
  assertUnsafe("run *IDN? now", "RAW_INSTRUMENT_COMMAND");
  assert.equal(inspect("SCPI is a command standard.").status, "SAFE");
  assert.equal(inspect("SCPI commands are not exposed.").status, "SAFE");
});

test("known full serial is blocked and canonical masked serial is allowed", () => {
  assertUnsafe("instrument serial is UNIT-AB12-998877", "FULL_INSTRUMENT_SERIAL", ["UNIT-AB12-998877"]);
  assertUnsafe("serial_number=AB12CD349988", "FULL_INSTRUMENT_SERIAL");
  assert.equal(inspect("instrument serial is ***9517", ["UNIT-AB12-998877"]).status, "SAFE");
  assert.equal(inspect("measurement id=123456789012").status, "SAFE");
});

test("credential material is blocked without rejecting an environment variable name", () => {
  assertUnsafe("DEEPSEEK_API_KEY=sk-exampleCredentialValue1234", "CREDENTIAL_MATERIAL");
  assertUnsafe("Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456", "CREDENTIAL_MATERIAL");
  assertUnsafe("psk=0123456789abcdef0123456789abcdef", "CREDENTIAL_MATERIAL");
  assertUnsafe("-----BEGIN PRIVATE KEY-----", "CREDENTIAL_MATERIAL");
  assert.equal(inspect("DEEPSEEK_API_KEY was not logged.").status, "SAFE");
});

test("raw or large waveform arrays are blocked while bounded metadata is allowed", () => {
  assertUnsafe('{"samples":[0.1,0.2]}', "WAVEFORM_SAMPLE_ARRAY");
  assertUnsafe('{"time_values":[0.1]}', "WAVEFORM_SAMPLE_ARRAY");
  assertUnsafe(`[${Array.from({ length: 20 }, (_, index) => index / 10).join(",")}]`, "WAVEFORM_SAMPLE_ARRAY");
  assert.equal(inspect("point_count=1200 sample_interval=2e-7 voltage_min=-0.37 voltage_max=0.03").status, "SAFE");
  assert.equal(inspect("The waveform artifact is opaque.").status, "SAFE");
});

test("oversized output is rejected rather than truncated", () => {
  assertUnsafe("x".repeat(16_385), "OVERSIZED_OUTPUT");
});

test("diagnostics contain category, source, correlation and no sensitive echo", () => {
  const sensitive = "C:\\Users\\operator\\secret.txt";
  const result = inspect(sensitive);
  assert.equal(result.status, "UNSAFE");
  if (result.status === "UNSAFE") {
    assert.ok(Object.isFrozen(result));
    assert.ok(Object.isFrozen(result.violations));
    assert.ok(result.violations.every(Object.isFrozen));
    const diagnostics = result.violations.map(toEgressDiagnostic);
    const encoded = JSON.stringify(diagnostics);
    assert.doesNotMatch(encoded, /operator|secret\.txt|C:\\/);
    assert.deepEqual(diagnostics[0], {
      status: "BLOCKED",
      category: "LOCAL_PATH",
      source: "FINAL_RESPONSE",
      correlationId,
    });
  }
});

test("model-authored Tool arguments use the same categories without retaining candidate values", () => {
  const cases = [
    ['{"context_id":"C:\\\\Users\\\\invented\\\\capture.bin"}', "LOCAL_PATH"],
    ['{"context_id":"USB0::vendor::device::INSTR"}', "VISA_RESOURCE_IDENTIFIER"],
    ['{"context_id":":WAV:DATA?"}', "RAW_INSTRUMENT_COMMAND"],
    ['{"context_id":"api_key=sk-inventedCredential12345"}', "CREDENTIAL_MATERIAL"],
    ['{"context_id":"serial_number=ZXCV123456789"}', "FULL_INSTRUMENT_SERIAL"],
    ['{"context_id":"samples=[0.1,0.2]"}', "WAVEFORM_SAMPLE_ARRAY"],
  ] as const;
  for (const [candidate, category] of cases) {
    const result = inspectEgressCandidate({
      candidate,
      source: "TOOL_ARGUMENTS",
      correlationId,
      knownSensitiveValues: [],
    });
    assert.equal(result.status, "UNSAFE");
    assert.ok(result.status === "UNSAFE" && result.violations.some((item) => item.category === category));
    assert.doesNotMatch(JSON.stringify(result), /invented|vendor|WAV:DATA|sk-invented|ZXCV123|0\.1/);
  }
});
