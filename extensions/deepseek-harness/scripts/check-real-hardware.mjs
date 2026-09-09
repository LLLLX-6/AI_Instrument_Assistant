import { createInterface } from "node:readline/promises";
import { resolve } from "node:path";

import { Context } from "@deepseek-ai/cordis";
import { ToolCallId } from "@deepseek-ai/dsh-llm";
import SystemPrompt from "@deepseek-ai/dsh-system-prompt";
import ToolRuntime from "@deepseek-ai/dsh-tools";

import { applyWithDependencies } from "../src/index.ts";
import { HarnessHardwareIpcClient } from "../src/ipc/client.ts";
import { loadHarnessHardwareSecret } from "../src/ipc/secret.ts";
import { createTrustedOperationScope } from "../src/operation-scope/index.ts";

const endpoint = process.env.AIA_HARNESS_HARDWARE_ENDPOINT ?? "ws://127.0.0.1:49625";
const secretFile = resolve(process.env.AIA_HARNESS_HARDWARE_SECRET_FILE ?? ".aia-secrets/harness-hardware-psk.txt");
const allOperations = [
  ["hardware_get_status", {}],
  ["hardware_measure_frequency", { channel: 1 }],
  ["hardware_measure_vpp", { channel: 1 }],
  ["hardware_capture_waveform", { channel: 1 }],
  ["hardware_measure_pwm", { channel: 1 }],
];
const diagnosticFrequencyOnly = process.argv.includes("--diagnostic-frequency");
const lifecycleOnly = process.argv.includes("--lifecycle-only");
const operations = diagnosticFrequencyOnly
  ? allOperations.slice(0, 2)
  : lifecycleOnly
    ? allOperations.slice(0, 1)
    : allOperations;

console.log("Safety: real DS1102Z-E validation requires a safe low-voltage source and confirmed common ground.");
console.log("Do not probe mains or high voltage.");

const client = new HarnessHardwareIpcClient({
  endpoint,
  secretFile,
  loadSecret: () => loadHarnessHardwareSecret(secretFile),
  connectTimeoutMs: 2_000,
  authTimeoutMs: 2_000,
  requestTimeoutMs: 30_000,
  diagnostics(event) {
    console.log(JSON.stringify({
      transport_diagnostic: {
        ...event,
        state: client.state,
        observed_at: new Date().toISOString(),
      },
    }));
  },
});
const ctx = new Context();
const input = createInterface({ input: process.stdin, output: process.stdout });
const workflowId = "manual-real-hardware-validation";
const scope = createTrustedOperationScope({
  scopeId: "manual-real-hardware-validation-scope",
  requestCorrelationId: workflowId,
  workflowId,
  allowedOperations: [
    { operation: "hardware.get_status", maxInvocations: 3 },
    { operation: "hardware.measure_frequency", maxInvocations: 1 },
    { operation: "hardware.measure_vpp", maxInvocations: 1 },
    { operation: "hardware.capture_waveform", maxInvocations: 1 },
    { operation: "hardware.measure_pwm", maxInvocations: 1 },
  ],
  targetChannel: null,
  targetIntent: "explicit manual hardware validation",
  origin: "TRUSTED_VALIDATION_SCENARIO",
  authorizationRef: "manual-runner-confirmation",
});

try {
  await ctx.plugin(SystemPrompt);
  await ctx.plugin(ToolRuntime);
  applyWithDependencies(ctx, { endpoint, secretFile, requestTimeoutMs: 30_000 }, {
    createClient: () => client,
    resolveOperationScopeContext: () => ({ scope, requestCorrelationId: workflowId, workflowId }),
  });
  await client.waitUntilAuthenticated(10_000);
  const initialSession = client.sessionId;
  const initialGeneration = client.connectionGeneration;

  const invalid = await execute("hardware_measure_frequency", { channel: 9 }, "invalid-channel");
  if (!invalid.isError) throw new Error("Invalid channel reached the adapter instead of failing Tool validation");
  if (invalid.error?.message !== "Hardware tool arguments are invalid.") {
    throw new Error("Invalid arguments did not retain the approved local adapter classification");
  }
  console.log(JSON.stringify({ invalid_request: boundedFailure(invalid), instrument_side_effect_expected: "none (rejected by Tool schema)" }, null, 2));

  const evidence = {};
  for (const [name, args] of operations) {
    const response = await execute(name, args, name);
    if (response.isError) throw new Error(`${name} failed at the Harness boundary: ${response.error?.message ?? "unknown"}`);
    assertSafeVisibleOutput(response);
    evidence[name] = { canonical: response.value, render: response.content };
    console.log(JSON.stringify({ observed_tool: name, canonical: response.value, render: response.content }, null, 2));
  }
  if (diagnosticFrequencyOnly) {
    process.exitCode = 3;
  } else {
    if (lifecycleOnly) validateStatusEvidence(evidence);
    else validateEvidence(evidence);
    console.log(JSON.stringify({ real_hardware_evidence: evidence }, null, 2));

    console.log("PHASE7B5_STOP_BACKEND: stop the Python backend cleanly, then press Enter.");
    await input.question("");
    await waitFor(
      () => client.state !== "AUTHENTICATED" || client.connectionGeneration > initialGeneration,
      10_000,
    );
    const offlineProbe = await execute("hardware_get_status", {}, "offline");
    let recovered;
    if (offlineProbe.isError) {
      assertSafeVisibleOutput(offlineProbe);
      console.log(JSON.stringify({
        backend_offline: boundedFailure(offlineProbe),
        registered_tool_count: ctx.tools.schemas().filter((item) => item.name.startsWith("hardware_")).length,
        plugin_state: "active",
      }, null, 2));
      console.log("PHASE7B5_RESTART_BACKEND: restart the same real backend now, then press Enter.");
      await input.question("");
      await client.waitUntilAuthenticated(15_000);
      recovered = await execute("hardware_get_status", {}, "recovered");
    } else {
      recovered = offlineProbe;
      console.log(JSON.stringify({
        backend_recovered_before_offline_probe: true,
        registered_tool_count: ctx.tools.schemas().filter((item) => item.name.startsWith("hardware_")).length,
        plugin_state: "active",
      }, null, 2));
    }
    if (recovered.isError) throw new Error(`Recovered get_status failed: ${recovered.error?.message ?? "unknown"}`);
    assertSafeVisibleOutput(recovered);
    const sessionChanged = Boolean(initialSession && client.sessionId && initialSession !== client.sessionId);
    const generationAdvanced = client.connectionGeneration > initialGeneration;
    if (!sessionChanged || !generationAdvanced) throw new Error("Reconnect did not establish a fresh session and generation");
    console.log(JSON.stringify({
      reconnect: {
        authenticated: client.state === "AUTHENTICATED",
        session_changed: sessionChanged,
        generation_advanced: generationAdvanced,
        old_request_replay: false,
      },
      recovered_status: { canonical: recovered.value, render: recovered.content },
    }, null, 2));
  }
} finally {
  input.close();
  await ctx.fiber.dispose();
}

async function execute(name, args, suffix) {
  return ctx.tools.execute({
    signal: AbortSignal.timeout(40_000),
    callId: ToolCallId(`phase7b5-${suffix}`),
    name,
    arguments: args,
  });
}

function validateStatusEvidence(evidence) {
  const status = canonicalResult(evidence.hardware_get_status);
  if (status.operation !== "hardware.get_status" || status.ok !== true) {
    throw new Error("get_status canonical result mismatch");
  }
  assertCanonicalMaskedSerial(status);
}

function validateEvidence(evidence) {
  const status = canonicalResult(evidence.hardware_get_status);
  if (status.operation !== "hardware.get_status" || status.ok !== true) throw new Error("get_status canonical result mismatch");
  if (status.result?.instrument?.manufacturer !== "RIGOL TECHNOLOGIES" || status.result?.instrument?.model !== "DS1102Z-E") {
    throw new Error("Unexpected real instrument identity");
  }
  assertCanonicalMaskedSerial(status);

  const frequency = measurement(evidence.hardware_measure_frequency, "hardware.measure_frequency", "frequency");
  assertCanonicalMaskedSerial(frequency);
  const instrumentFrequency = frequency.result.observations?.instrument_frequency;
  if (instrumentFrequency?.source !== "instrument" || !positiveFinite(instrumentFrequency.value)) throw new Error("Frequency observation is not finite instrument evidence");

  const vpp = measurement(evidence.hardware_measure_vpp, "hardware.measure_vpp", "vpp");
  assertCanonicalMaskedSerial(vpp);
  const instrumentVpp = vpp.result.observations?.instrument_vpp;
  if (instrumentVpp?.source !== "instrument" || !nonNegativeFinite(instrumentVpp.value)) throw new Error("Vpp observation is not finite instrument evidence");

  const waveform = measurement(evidence.hardware_capture_waveform, "hardware.capture_waveform", "waveform");
  const pwm = measurement(evidence.hardware_measure_pwm, "hardware.measure_pwm", "pwm");
  assertCanonicalMaskedSerial(waveform);
  assertCanonicalMaskedSerial(pwm);
  for (const result of [waveform.result, pwm.result]) {
    if (!result.waveform?.artifact?.artifact_id || !positiveFinite(result.waveform.sample_interval_seconds) || !positiveFinite(result.waveform.point_count)) {
      throw new Error("Waveform artifact metadata is incomplete");
    }
  }
  if (waveform.result.waveform.artifact.artifact_id === pwm.result.waveform.artifact.artifact_id) {
    throw new Error("Independent waveform observations unexpectedly reused one artifact identity");
  }
  if (pwm.result.coherence?.software_observations !== "same_artifact" || pwm.result.coherence?.instrument_vs_software !== "sequential_same_session") {
    throw new Error("PWM coherence semantics were not preserved");
  }
  for (const key of ["instrument_frequency", "instrument_vpp", "software_frequency", "software_period", "software_duty_cycle", "software_vpp", "software_mean", "software_rms"]) {
    if (!(key in (pwm.result.observations ?? {}))) throw new Error(`PWM observation missing: ${key}`);
  }
}

function assertCanonicalMaskedSerial(value) {
  const serial = value.result?.instrument?.serial_number;
  if (typeof serial !== "string" || !/^\*\*\*(?:.{4})?$/.test(serial)) {
    throw new Error("Instrument serial is not in canonical masked form");
  }
}

function measurement(entry, operation, kind) {
  const value = canonicalResult(entry);
  if (value.operation !== operation || value.ok !== true || value.result?.kind !== kind || value.result?.channel !== 1) {
    throw new Error(`${operation} canonical result mismatch`);
  }
  if (!value.result.provenance?.started_at || !value.result.provenance?.completed_at) throw new Error(`${operation} provenance missing`);
  return value;
}

function canonicalResult(entry) {
  if (!entry || typeof entry !== "object" || !entry.canonical || typeof entry.canonical !== "object") throw new Error("Canonical structured value missing");
  return entry.canonical;
}

function assertSafeVisibleOutput(response) {
  const encoded = JSON.stringify({ value: response.value, content: response.content });
  const forbidden = [
    /USB\d+::/i,
    /(?:^|[^A-Za-z])(?:SCPI|VISA)(?:[^A-Za-z]|$)/i,
    /[A-Za-z]:\\/,
    /(?:hmac|proof|secret|traceback|stack trace)/i,
    /(?:time_values|voltage_values|"samples")/i,
  ];
  for (const pattern of forbidden) {
    if (pattern.test(encoded)) throw new Error(`Visible Harness output failed security inspection: ${pattern}`);
  }
}

function boundedFailure(response) {
  return { is_error: response.isError, message: String(response.error?.message ?? "").slice(0, 256) };
}

function positiveFinite(value) {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}

function nonNegativeFinite(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

async function waitFor(predicate, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (!predicate()) {
    if (Date.now() >= deadline) throw new Error("Timed out waiting for transport state change");
    await new Promise((resolveWait) => setTimeout(resolveWait, 50));
  }
}
