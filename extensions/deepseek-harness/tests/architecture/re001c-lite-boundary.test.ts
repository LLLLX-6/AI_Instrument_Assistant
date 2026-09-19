import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const root = resolve(new URL("../../../..", import.meta.url).pathname.replace(/^\/(.:)/, "$1"));
const source = readFileSync(resolve(root, "extensions/deepseek-harness/validation/re001c-lite-executor.ts"), "utf8");

test("RE-001C-Lite Harness boundary owns governance but not RC analysis or direct hardware", () => {
  assert.match(source, /createTrustedOperationScope/);
  assert.match(source, /createProbeSetupConfirmation/);
  assert.doesNotMatch(source, /RCSinglePointMeasurementAnalyzer|gain_ratio|gain_db|frequency_relative_deviation/);
  assert.doesNotMatch(source, /pyvisa|VISA|SCPI|DS1102Z|DeepSeek|JLCEDA|Yuanlitu/);
});

test("RE-001C-Lite exposes only the four existing semantic measurements", () => {
  const order = source.match(/const ORDER[\s\S]*?as const\);/)?.[0] ?? "";
  assert.equal((order.match(/hardware\.measure_frequency/g) ?? []).length, 2);
  assert.equal((order.match(/hardware\.measure_vpp/g) ?? []).length, 2);
  assert.doesNotMatch(order, /measure_pwm|capture_waveform|get_status/);
});
