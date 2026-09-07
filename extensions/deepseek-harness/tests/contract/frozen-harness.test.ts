import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import test from "node:test";

const EXPECTED_COMMIT = "d347e703908d0406b7a7ef80e3a0e594d86b2215";
const EXPECTED_TOOLS_VERSION = "0.1.3-alpha.1";

test("frozen Harness checkout and package version are exact", () => {
  const root = process.env.DEEPSEEK_HARNESS_DEV_ROOT;
  assert.ok(root, "DEEPSEEK_HARNESS_DEV_ROOT is required");
  const head = execFileSync(
    "git",
    ["-c", `safe.directory=${resolve(root).replaceAll("\\", "/")}`, "-C", root, "rev-parse", "HEAD"],
    { encoding: "utf8" },
  ).trim();
  assert.equal(head, EXPECTED_COMMIT);
  const manifest = JSON.parse(readFileSync(join(root, "packages", "core", "tools", "package.json"), "utf8"));
  assert.equal(manifest.version, EXPECTED_TOOLS_VERSION);
});

test("plugin pins only the reviewed source versions", () => {
  const manifest = JSON.parse(readFileSync(new URL("../../package.json", import.meta.url), "utf8"));
  assert.equal(manifest.peerDependencies["@deepseek-ai/dsh-tools"], EXPECTED_TOOLS_VERSION);
  assert.equal(manifest.peerDependencies["@deepseek-ai/cordis"], "4.0.2");
  assert.doesNotMatch(JSON.stringify(manifest), /0\.1\.3-alpha\.2|0\.1\.2-rc\.1/);
});

test("official API exposes defineTool and Context plugin lifecycle", async () => {
  const tools = await import("@deepseek-ai/dsh-tools");
  const cordis = await import("@deepseek-ai/cordis");
  assert.equal(typeof tools.defineTool, "function");
  assert.equal(typeof tools.validateJsonSchemaValue, "function");
  assert.equal(typeof cordis.Context, "function");
  const context = new cordis.Context();
  assert.equal(typeof context.plugin, "function");
  assert.equal(typeof context.effect, "function");
  await context.fiber.dispose();
});
