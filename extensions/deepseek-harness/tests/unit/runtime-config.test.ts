import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

import {
  resolveHardwareRuntimeConfig,
  resolveHardwareSecretFilePath,
} from "../../src/runtime-config.ts";

const extensionRoot = resolve(new URL("../..", import.meta.url).pathname.replace(/^\/(.:)/, "$1"));

test("development Web overlay replaces the stable bundle row instead of creating a second plugin", () => {
  const buildScript = readFileSync(resolve(extensionRoot, "scripts/build.mjs"), "utf8");
  assert.match(buildScript, /id: aia-hardware["']/);
  assert.doesNotMatch(buildScript, /aia-hardware-dev/);
});

test("Web runtime environment overrides Cordis endpoint and secret-file configuration", () => {
  const config = resolveHardwareRuntimeConfig(
    {
      endpoint: "ws://127.0.0.1:41000",
      secretFile: "C:\\configured\\hardware-psk.txt",
      backendMode: "SIMULATED",
    },
    {
      AIA_HARNESS_HARDWARE_ENDPOINT: "ws://127.0.0.1:49625",
      AIA_HARNESS_HARDWARE_SECRET_FILE: "C:\\runtime\\hardware-psk.txt",
    },
  );

  assert.equal(config.endpoint, "ws://127.0.0.1:49625");
  assert.equal(config.secretFile, "C:\\runtime\\hardware-psk.txt");
  assert.equal(config.backendMode, "SIMULATED");
});

test("Cordis configuration remains the fallback when runtime overrides are absent", () => {
  const config = resolveHardwareRuntimeConfig(
    {
      endpoint: "ws://127.0.0.1:49625",
      secretFile: "C:\\configured\\hardware-psk.txt",
    },
    {},
  );

  assert.equal(config.endpoint, "ws://127.0.0.1:49625");
  assert.equal(config.secretFile, "C:\\configured\\hardware-psk.txt");
});

test("production secret-file resolution accepts only an explicit absolute path", () => {
  assert.equal(
    resolveHardwareSecretFilePath("C:\\runtime\\hardware-psk.txt"),
    "C:\\runtime\\hardware-psk.txt",
  );
  assert.throws(
    () => resolveHardwareSecretFilePath(".aia-secrets/harness-hardware-psk.txt"),
    (error: unknown) => {
      assert.ok(error instanceof Error);
      assert.equal(error.message, "Harness Hardware secret-file path must be absolute.");
      assert.doesNotMatch(error.message, /aia-secrets|Administrator|hardware-psk\.txt/i);
      return true;
    },
  );
});

test("empty runtime overrides fail closed instead of falling back", () => {
  assert.throws(
    () => resolveHardwareRuntimeConfig({}, { AIA_HARNESS_HARDWARE_SECRET_FILE: "" }),
    /runtime configuration is empty/i,
  );
  assert.throws(
    () => resolveHardwareRuntimeConfig({}, { AIA_HARNESS_HARDWARE_ENDPOINT: "   " }),
    /runtime configuration is empty/i,
  );
});

test("resolved configuration contains path references but no secret material", () => {
  const secretMaterial = "never-embed-this-secret-material";
  const config = resolveHardwareRuntimeConfig(
    {},
    { AIA_HARNESS_HARDWARE_SECRET_FILE: "C:\\runtime\\hardware-psk.txt" },
  );

  assert.doesNotMatch(JSON.stringify(config), new RegExp(secretMaterial));
  assert.equal(Object.hasOwn(config, "secret"), false);
  assert.equal(Object.hasOwn(config, "psk"), false);
});

test("resolution fails closed without an externally supplied absolute secret path", () => {
  assert.throws(
    () => resolveHardwareRuntimeConfig({}, {}),
    /secret-file path must be absolute/i,
  );
  const source = readFileSync(resolve(extensionRoot, "src/runtime-config.ts"), "utf8");
  assert.doesNotMatch(source, /[A-Za-z]:[\\/]Users[\\/]/, "no machine-specific secret path may be committed");
  assert.doesNotMatch(source, /49635/, "Hardware backend stays on the established port 49625");
});
