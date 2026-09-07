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
  assert.doesNotMatch(sourceText(), /pyvisa|SCPI|DS1102|Rigol|MeasurementService|jlceda/i);
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
