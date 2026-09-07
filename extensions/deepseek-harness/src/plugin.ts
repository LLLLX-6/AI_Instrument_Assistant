import { resolve } from "node:path";

import type { Context } from "@deepseek-ai/cordis";
import {
  validateJsonSchemaValue,
  type JsonSchemaNode,
  type ToolDefinition,
} from "@deepseek-ai/dsh-tools";

import {
  HARDWARE_TOOL_CONTRACTS,
  type HardwareOperation,
} from "./generated/hardware-tools.generated.ts";
import { HarnessHardwareIpcClient } from "./ipc/client.ts";
import { safeAdapterFailure } from "./ipc/errors.ts";
import { loadHarnessHardwareSecret } from "./ipc/secret.ts";
import { renderHardwareResult } from "./render.ts";

export interface Config {
  readonly endpoint?: string;
  readonly secretFile?: string;
  readonly connectTimeoutMs?: number;
  readonly authTimeoutMs?: number;
  readonly requestTimeoutMs?: number;
}

export interface HardwareClientPort {
  start(): void;
  dispose(): Promise<void>;
  invoke(operation: HardwareOperation, args: unknown, signal: AbortSignal): Promise<unknown>;
}

export interface PluginDependencies {
  readonly createClient: (config: Required<Config>) => HardwareClientPort;
}

const DEFAULT_CONFIG: Required<Config> = {
  endpoint: "ws://127.0.0.1:49625",
  secretFile: ".aia-secrets/harness-hardware-psk.txt",
  connectTimeoutMs: 2_000,
  authTimeoutMs: 2_000,
  requestTimeoutMs: 30_000,
};

const REAL_DEPENDENCIES: PluginDependencies = {
  createClient(config) {
    const secretPath = resolve(config.secretFile);
    return new HarnessHardwareIpcClient({
      endpoint: config.endpoint,
      secretFile: secretPath,
      loadSecret: () => loadHarnessHardwareSecret(secretPath),
      connectTimeoutMs: config.connectTimeoutMs,
      authTimeoutMs: config.authTimeoutMs,
      requestTimeoutMs: config.requestTimeoutMs,
    });
  },
};

export function applyWithDependencies(
  ctx: Context,
  suppliedConfig: Config = {},
  dependencies: PluginDependencies = REAL_DEPENDENCIES,
): void {
  const config = normalizeConfig(suppliedConfig);
  const client = dependencies.createClient(config);
  ctx.effect(() => {
    client.start();
    return () => client.dispose();
  }, "aia-hardware-ipc-client");

  for (const contract of HARDWARE_TOOL_CONTRACTS) {
    const parameters = contract.parametersSchema as unknown as JsonSchemaNode;
    const outputSchema = contract.outputSchema as unknown as JsonSchemaNode;
    const operation = contract.canonicalOperation;
    const definition: ToolDefinition = {
      name: contract.harnessName,
      description: descriptionFor(operation),
      parameters: parameters as unknown as Record<string, unknown>,
      output: {
        schema: outputSchema,
        render: renderHardwareResult,
      },
      async execute(args, exec) {
        const violations = validateJsonSchemaValue(parameters, args, "");
        if (violations.length) {
          throw safeAdapterFailure("backend_response_invalid", "NOT_SENT");
        }
        return client.invoke(operation, args, exec.signal);
      },
    };
    ctx.tools.register(definition);
  }
}

function normalizeConfig(config: Config): Required<Config> {
  const merged = { ...DEFAULT_CONFIG, ...config };
  for (const key of ["connectTimeoutMs", "authTimeoutMs", "requestTimeoutMs"] as const) {
    if (!Number.isSafeInteger(merged[key]) || merged[key] <= 0) throw new Error(`${key} must be a positive integer`);
  }
  return Object.freeze(merged);
}

function descriptionFor(operation: HardwareOperation): string {
  switch (operation) {
    case "hardware.get_status": return "Read bounded oscilloscope availability and identity status.";
    case "hardware.measure_frequency": return "Measure signal frequency on an approved oscilloscope channel.";
    case "hardware.measure_vpp": return "Measure peak-to-peak voltage on an approved oscilloscope channel.";
    case "hardware.capture_waveform": return "Capture a bounded waveform artifact reference without returning sample arrays.";
    case "hardware.measure_pwm": return "Measure PWM frequency, duty cycle, voltage, quality, and bounded evidence.";
  }
}
