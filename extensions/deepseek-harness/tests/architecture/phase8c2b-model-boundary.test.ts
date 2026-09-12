import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const sourceRoot = join(root, "src", "model-candidate");

test("one-shot model composition is statically zero-Tool and has one stream call site", () => {
  const source = readdirSync(sourceRoot).filter((name) => name.endsWith(".ts"))
    .map((name) => readFileSync(join(sourceRoot, name), "utf8")).join("\n");
  assert.equal(source.match(/ctx\.llm\.stream\(/g)?.length, 1);
  assert.match(source, /tools:\s*\[\]/);
  for (const forbidden of ["AgentLoop", "AgentRegistry", "ToolRuntime", "SessionStore", "applyWithDependencies"]){
    assert.doesNotMatch(source, new RegExp(forbidden));
  }
});

test("final Egress executor imports no model runtime and cannot alter text", () => {
  const source = readFileSync(join(sourceRoot, "final-egress-executor.ts"), "utf8");
  assert.doesNotMatch(source, /dsh-llm|DEEPSEEK_API_KEY|candidate\s*[+.]=/);
  assert.match(source, /inspectDeterministicPublication\(String\(request\.text\)/);
});
