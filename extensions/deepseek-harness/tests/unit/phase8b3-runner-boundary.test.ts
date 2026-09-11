import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { resolve } from "node:path";
import test from "node:test";

const root = resolve(new URL("../..", import.meta.url).pathname.replace(/^\/(.:)/, "$1"));

test("private one-shot runner bounds malformed input without stack or host paths", async () => {
  const script = resolve(root, "scripts/execute-phase8b3-governed-hardware.mjs");
  const result = await run(script, "{}\n");
  const receipt = JSON.parse(result.stdout);
  assert.equal(receipt.status, "FAILED");
  assert.equal(receipt.failure_code, "contract_schema_invalid");
  assert.equal(receipt.operations.length, 0);
  assert.equal(result.stderr, "");
  assert.doesNotMatch(result.stdout, /[A-Za-z]:\\|stack|trace|secret|HMAC|PSK|VISA|USB\d+::/i);
});

function run(script: string, input: string): Promise<{ stdout: string; stderr: string }> {
  return new Promise((resolveResult, reject) => {
    const child = spawn(process.execPath, [script], { cwd: root, stdio: ["pipe", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8").on("data", (chunk) => { stdout += chunk; });
    child.stderr.setEncoding("utf8").on("data", (chunk) => { stderr += chunk; });
    child.once("error", reject);
    child.once("close", () => resolveResult({ stdout, stderr }));
    child.stdin.end(input);
  });
}
