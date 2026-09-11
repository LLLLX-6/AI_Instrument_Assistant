import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const root = resolve(new URL("../..", import.meta.url).pathname.replace(/^\/(.:)/, "$1"));
const executor = readFileSync(resolve(root, "validation/phase8b3-executor.ts"), "utf8");
const plugin = readFileSync(resolve(root, "src/plugin.ts"), "utf8");
const runner = readFileSync(resolve(root, "scripts/execute-phase8b3-governed-hardware.mjs"), "utf8");

test("Phase 8B.3 executor composes the production governance path without Agent or model", () => {
  assert.match(executor, /applyWithDependencies/);
  assert.doesNotMatch(executor, /evaluateHardwareToolPolicy|new OperationScopeGate|AgentLoop|dsh-agent|DEEPSEEK_API_KEY/);
});

test("governance decision accounting hooks observe but do not reorder execution", () => {
  const schemaAt = plugin.lastIndexOf("validateJsonSchemaValue(parameters");
  const scopeAt = plugin.lastIndexOf("operationScopeGate.evaluate");
  const policyAt = plugin.lastIndexOf("evaluateHardwareToolPolicy");
  const authorizeAt = plugin.lastIndexOf("operationScopeGate.authorizeDispatch");
  const ipcAt = plugin.lastIndexOf("client.invoke");
  assert.ok(schemaAt >= 0 && scopeAt > schemaAt && policyAt > scopeAt && authorizeAt > policyAt && ipcAt > authorizeAt);
  assert.match(plugin, /onOperationScopeDecision/);
  assert.match(plugin, /onPolicyDecision/);
});

test("private runner has static semantic operations and no dynamic execution surface", () => {
  assert.doesNotMatch(`${executor}\n${runner}`, /\beval\s*\(|new\s+Function|executeScript|raw method|arbitrary/);
  assert.doesNotMatch(runner, /console\.(?:log|error)\(error|error\.stack/);
});

test("backend readiness is requested lazily from the governed client invocation", () => {
  const invokeAt = runner.indexOf("async invoke(operation, args, signal)");
  const requestAt = runner.indexOf('kind: "backend_start_required"');
  const readyAt = runner.indexOf("isBackendReady(acknowledgement)");
  const clientStartAt = runner.indexOf("client.start()", readyAt);
  const ipcAt = runner.indexOf("return client.invoke(operation, args, signal)");
  assert.ok(invokeAt >= 0 && requestAt > invokeAt && readyAt > requestAt);
  assert.ok(clientStartAt > readyAt && ipcAt > clientStartAt);
});

test("PWM Tool arguments take channel from the validated trusted scope input", () => {
  assert.match(executor, /const pwmChannel = channel\(pwmScopeInput\.target_channel\)/);
  assert.match(executor, /channel: pwmChannel/);
  assert.doesNotMatch(executor, /executeTool\([\s\S]*?hardware_measure_pwm[\s\S]*?channel:\s*1,/);
});
