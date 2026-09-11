import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";


const root = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");

test("Phase 8C.2A publication adapter is final-Egress-only", () => {
  const text = readFileSync(resolve(root, "src", "publication", "final-egress.ts"), "utf8");
  const imports = [...text.matchAll(/from\s+["']([^"']+)["']/g)].map((match) => match[1]);
  assert.deepEqual(imports, ["../egress/index.ts", "../egress/index.ts"]);
  assert.doesNotMatch(text, /@deepseek-ai|agentLoop|ToolRuntime|Hardware|JLCEDA|VISA|SCPI|WebSocket/);
});
