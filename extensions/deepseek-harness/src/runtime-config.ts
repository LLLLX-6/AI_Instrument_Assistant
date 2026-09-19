import { isAbsolute, normalize } from "node:path";

import type { BackendMode } from "./policy/index.ts";

export interface HardwareRuntimeConfig {
  readonly endpoint?: string;
  readonly secretFile?: string;
  readonly connectTimeoutMs?: number;
  readonly authTimeoutMs?: number;
  readonly requestTimeoutMs?: number;
  readonly backendMode?: BackendMode;
}

export type HardwareRuntimeEnvironment = Readonly<Record<string, string | undefined>>;

const DEFAULT_CONFIG: Required<HardwareRuntimeConfig> = Object.freeze({
  endpoint: "ws://127.0.0.1:49625",
  // No machine-specific default: production resolution requires an explicit
  // absolute path supplied through AIA_HARNESS_HARDWARE_SECRET_FILE or
  // explicit runtime configuration, and fails closed otherwise.
  secretFile: "",
  connectTimeoutMs: 2_000,
  authTimeoutMs: 2_000,
  requestTimeoutMs: 30_000,
  backendMode: "REAL",
});

/**
 * Resolve process-local runtime overrides before static Cordis configuration.
 * Values remain references/configuration only; secret material is never read
 * or retained here.
 */
export function resolveHardwareRuntimeConfig(
  supplied: HardwareRuntimeConfig = {},
  environment: HardwareRuntimeEnvironment = process.env,
): Required<HardwareRuntimeConfig> {
  const endpointOverride = runtimeOverride(environment, "AIA_HARNESS_HARDWARE_ENDPOINT");
  const secretFileOverride = runtimeOverride(environment, "AIA_HARNESS_HARDWARE_SECRET_FILE");
  const merged: Required<HardwareRuntimeConfig> = {
    ...DEFAULT_CONFIG,
    ...supplied,
    ...(endpointOverride === undefined ? {} : { endpoint: endpointOverride }),
    ...(secretFileOverride === undefined ? {} : { secretFile: secretFileOverride }),
  };

  for (const key of ["connectTimeoutMs", "authTimeoutMs", "requestTimeoutMs"] as const) {
    if (!Number.isSafeInteger(merged[key]) || merged[key] <= 0) {
      throw new Error(`${key} must be a positive integer`);
    }
  }
  if (merged.backendMode !== "REAL" && merged.backendMode !== "SIMULATED") {
    throw new Error("backendMode must be REAL or SIMULATED");
  }
  if (!isAbsolute(merged.secretFile)) {
    throw new Error("Harness Hardware secret-file path must be absolute.");
  }
  return Object.freeze(merged);
}

/**
 * Production authentication must not reinterpret a relative path against an
 * unrelated launcher working directory. Local machine paths enter through
 * runtime configuration and must already be explicit absolute references.
 */
export function resolveHardwareSecretFilePath(secretFile: string): string {
  if (!isAbsolute(secretFile)) {
    throw new Error("Harness Hardware secret-file path must be absolute.");
  }
  return normalize(secretFile);
}

function runtimeOverride(
  environment: HardwareRuntimeEnvironment,
  name: "AIA_HARNESS_HARDWARE_ENDPOINT" | "AIA_HARNESS_HARDWARE_SECRET_FILE",
): string | undefined {
  const value = environment[name];
  if (value === undefined) return undefined;
  if (value.trim().length === 0) throw new Error(`${name} runtime configuration is empty`);
  return value;
}
