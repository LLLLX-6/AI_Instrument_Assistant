import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { relative, resolve } from "node:path";
import test from "node:test";

const root = resolve(new URL("../..", import.meta.url).pathname.replace(/^\/(.:)/, "$1"));

function sourceText(): string {
  return readdirSync(resolve(root, "src"), { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith(".ts"))
    .map((entry) => readFileSync(resolve(entry.parentPath, entry.name), "utf8"))
    .join("\n");
}

test("plugin boundary contains no hardware implementation or JLCEDA dependency", () => {
  const imports = sourceText().split("\n").filter((line) => /^import .* from /.test(line)).join("\n");
  assert.doesNotMatch(imports, /pyvisa|drivers?\/|MeasurementService|jlceda/i);
  assert.doesNotMatch(sourceText(), /["']:\w+(?:ure)?:/i, "production code must not contain raw SCPI commands");
});

test("production source has no dynamic execution, subprocess, or arbitrary operation surface", () => {
  const text = sourceText();
  assert.doesNotMatch(text, /\beval\s*\(|new\s+Function|child_process|hardware_execute|raw_hardware|send_scpi|query_scpi/);
});

test("no committed source contains an absolute Harness checkout path", () => {
  const text = [sourceText(), readFileSync(resolve(root, "package.json"), "utf8")].join("\n");
  assert.doesNotMatch(text, /[A-Za-z]:[\\/]Dev[\\/]deepseek-harness/i);
});

test("frozen Harness source is not copied into the project", () => {
  const paths = readdirSync(resolve(root, "../.."), { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile())
    .map((entry) => relative(resolve(root, "../.."), resolve(entry.parentPath, entry.name)).replaceAll("\\", "/"));
  assert.ok(!paths.some((path) => path.startsWith("vendor/deepseek-harness/")));
});

test("provider-neutral policy has no Harness, driver, transport, EDA adapter, or LLM dependency", () => {
  const policy = readdirSync(resolve(root, "src/policy"), { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith(".ts"))
    .map((entry) => readFileSync(resolve(entry.parentPath, entry.name), "utf8"))
    .join("\n");
  assert.doesNotMatch(policy, /@deepseek-ai|Rigol|DS1102|pyvisa|SCPI|jlceda|ipc\/|generated\//i);
});

test("evidence presenter has no LLM, Harness runtime, driver, or VISA dependency", () => {
  const evidence = readdirSync(resolve(root, "src/evidence"), { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith(".ts"))
    .map((entry) => readFileSync(resolve(entry.parentPath, entry.name), "utf8"))
    .join("\n");
  assert.doesNotMatch(evidence, /@deepseek-ai|ToolRuntime|Rigol|DS1102|pyvisa|SCPI|VISA|ipc\//i);
});

test("prompt prose is not the physical execution authority", () => {
  const plugin = readFileSync(resolve(root, "src/plugin.ts"), "utf8");
  const review = readFileSync(resolve(root, "../../docs/agent/phase7c-agent-policy-review.md"), "utf8");
  assert.match(review, /Prompt-level guidance is advisory for model behavior\./);
  assert.match(review, /Deterministic policy\s+enforcement is authoritative for real tool execution\./);
  assert.match(plugin, /evaluateHardwareToolPolicy/);
  assert.match(plugin, /decision\s*!==\s*"ALLOW"/);
  assert.ok(plugin.indexOf("evaluateHardwareToolPolicy") < plugin.indexOf("client.invoke"));
});

test("Agent integration can present evidence but cannot invoke IPC or hardware runtime", () => {
  const agent = readdirSync(resolve(root, "src/agent"), { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith(".ts"))
    .map((entry) => readFileSync(resolve(entry.parentPath, entry.name), "utf8"))
    .join("\n");
  const imports = agent.split("\n").filter((line) => /^import .* from /.test(line)).join("\n");
  assert.doesNotMatch(imports, /ipc\/|HarnessHardwareIpcClient|HardwareToolRuntime|pyvisa|DS1102/i);
  assert.doesNotMatch(agent, /client\.invoke\s*\(/);
  assert.match(agent, /TeachingEvidenceContext/);
});

test("canonical result is validated after IPC and before evidence projection", () => {
  const plugin = readFileSync(resolve(root, "src/plugin.ts"), "utf8");
  const policyAt = plugin.indexOf("evaluateHardwareToolPolicy");
  const invokeAt = plugin.indexOf("client.invoke");
  const outputValidationAt = plugin.indexOf("validateJsonSchemaValue(outputSchema");
  const evidenceAt = plugin.lastIndexOf("presentHardwareResult(");
  assert.ok(policyAt >= 0 && invokeAt > policyAt);
  assert.ok(outputValidationAt > invokeAt);
  assert.ok(evidenceAt > outputValidationAt);
});

test("model-visible surface has no generic executor or deployment-state argument", async () => {
  const generated = await import("../../src/generated/hardware-tools.generated.ts");
  const contracts = generated.HARDWARE_TOOL_CONTRACTS;
  assert.equal(contracts.length, 5);
  assert.ok(contracts.every((contract) => !/execute|scpi|visa|backend/i.test(contract.harnessName)));
  const parameters = JSON.stringify(contracts.map((contract) => contract.parametersSchema));
  assert.doesNotMatch(parameters, /backend.?mode|confirmation|visa|scpi/i);
});
