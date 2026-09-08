import type { Context } from "@deepseek-ai/cordis";

import { applyWithDependencies, type Config } from "./plugin.ts";

export const name = "aia-hardware-tools";
export const inject = ["tools"];

export function apply(ctx: Context, config: Config = {}): void {
  applyWithDependencies(ctx, config);
}

export { applyWithDependencies } from "./plugin.ts";
export type { Config, HardwareClientPort, PluginDependencies } from "./plugin.ts";
export {
  createHardwareToolPolicyContext,
  createProbeSetupConfirmation,
  evaluateHardwareToolPolicy,
  riskForOperation,
} from "./policy/index.ts";
export { presentAdapterFailure, presentHardwareResult } from "./evidence/index.ts";
export type { HardwareToolPolicyContext, PolicyDecision } from "./policy/index.ts";
export type { TeachingEvidenceContext } from "./evidence/index.ts";
