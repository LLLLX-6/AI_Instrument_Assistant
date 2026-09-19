import type { Agent } from "@deepseek-ai/dsh-agent";
import type { Context } from "@deepseek-ai/cordis";
import { createUserMessage, type UserMessage } from "@deepseek-ai/dsh-llm";

import type { HardwareOperation } from "./generated/hardware-tools.generated.ts";
import { createTrustedOperationScope, type TrustedOperationScopeContext } from "./operation-scope/index.ts";
import { createHardwareToolPolicyContext, createProbeSetupConfirmation, type HardwareToolPolicyContext } from "./policy/index.ts";
import type { Re001dApplicationPort, Re001dPrepareResponse } from "./re001d-application-client.ts";

type PhysicalOperation = "hardware.measure_frequency" | "hardware.measure_vpp";
type Channel = 1 | 2;

const ORDER = Object.freeze([
  ["hardware.measure_frequency", 1], ["hardware.measure_vpp", 1],
  ["hardware.measure_frequency", 2], ["hardware.measure_vpp", 2],
] as const);

export const RE001D_WEB_REQUEST = "Measure the current STM32 output. Treat CH1 as Vin and CH2 as Vout. Measure frequency and Vpp and explain the result.";
export const RE001D_WEB_CONFIRMATION = "I confirm CH1 is connected to the intended Vin signal and CH2 to the intended Vout signal; both are safe low-voltage STM32 signals with a maximum expected voltage of 3.3 V; both probe grounds are connected to STM32 GND; the wiring has been checked and will remain unchanged during this measurement.";

export const RE001D_WEB_POLICY = `For the exact RE-001D request, explain that Vin is CH1, Vout is CH2, and both references must be STM32 GND. Ask the user to reply with this exact confirmation before selecting any measurement tool: "${RE001D_WEB_CONFIRMATION}". After confirmation, select exactly hardware_measure_frequency CH1, hardware_measure_vpp CH1, hardware_measure_frequency CH2, and hardware_measure_vpp CH2 in that order. Do not retry.`;

interface Entry {
  readonly workflowId: string;
  readonly requestCorrelationId: string;
  readonly prepared: Re001dPrepareResponse;
  readonly sequence: number;
  scopes: ReadonlyMap<string, TrustedOperationScopeContext>;
  confirmations: ReadonlyMap<Channel, ReturnType<typeof createProbeSetupConfirmation>>;
  readonly operations: Record<string, unknown>[];
  next: number;
  confirmed: boolean;
  failed: boolean;
  completing: boolean;
}

/** Trusted Web composition. Python contributes application data, never authority. */
export class InteractiveRe001dAuthority {
  readonly #entries = new Map<string, Entry>();
  readonly #application: Re001dApplicationPort;
  #sequence = 0;

  constructor(application: Re001dApplicationPort) {
    this.#application = application;
  }

  async claim(agent: Agent, message: UserMessage): Promise<"PREPARED" | "CONFIRMED" | "IGNORED" | "REJECTED"> {
    const workflowId = String(agent.id);
    const text = trustedUserText(message);
    if (text === undefined) return "IGNORED";
    const current = this.#entries.get(workflowId);
    if (current !== undefined && isConfirmationText(text)) {
      if (current.confirmed) return "REJECTED";
      // A failed workflow stays failed: only a fresh request may prepare again.
      if (current.failed) return "REJECTED";
      const issuedScopes = scopes(current.workflowId, current.requestCorrelationId, current.sequence);
      const physicalConfirmations = confirmations(current.workflowId, current.requestCorrelationId, current.sequence);
      current.scopes = issuedScopes;
      current.confirmations = physicalConfirmations;
      current.confirmed = true;
      return "CONFIRMED";
    }

    // Every other newly claimed user request revokes stale experiment authority.
    this.#entries.delete(workflowId);
    if (text !== RE001D_WEB_REQUEST) return "IGNORED";
    const requestCorrelationId = String(message.id);
    let prepared: Re001dPrepareResponse;
    try {
      prepared = await this.#application.prepare({ workflowId, requestCorrelationId, userText: text });
    } catch {
      return "REJECTED";
    }
    if (prepared.workflow_id !== workflowId || prepared.request_correlation_id !== requestCorrelationId
      || prepared.status !== "CONFIRMATION_REQUIRED" || !validOrder(prepared.plan.operation_sequence)) return "REJECTED";
    this.#entries.set(workflowId, {
      workflowId, requestCorrelationId, prepared,
      sequence: ++this.#sequence, scopes: new Map(), confirmations: new Map(),
      operations: [], next: 0, confirmed: false, failed: false, completing: false,
    });
    agent.followup(createUserMessage({
      content: [{
        type: "text",
        text: `RE001D_CONFIRMATION_REQUIRED\nVin=CH1\nVout=CH2\nReference=STM32 GND\n${prepared.wiring_instructions}\nReply exactly: ${RE001D_WEB_CONFIRMATION}`,
      }],
      source: { kind: "plugin", plugin: "aia-re001d-application" },
    }));
    return "PREPARED";
  }

  resolve(agent: Agent | undefined, operation: HardwareOperation | undefined, args: unknown): TrustedOperationScopeContext | undefined {
    const entry = this.#entry(agent);
    if (entry === undefined || !entry.confirmed || entry.failed || entry.completing) return undefined;
    const expected = ORDER[entry.next];
    const channel = requestedChannel(args);
    if (expected === undefined || operation !== expected[0] || channel !== expected[1]) return undefined;
    return entry.scopes.get(key(operation, channel));
  }

  policy(agent: Agent | undefined, operation: string, args: unknown, backendMode: "REAL" | "SIMULATED"): HardwareToolPolicyContext | undefined {
    const entry = this.#entry(agent);
    const channel = requestedChannel(args);
    if (entry === undefined || channel === null || this.resolve(agent, operation as HardwareOperation, args) === undefined) return undefined;
    return createHardwareToolPolicyContext({
      operation, channel, backendMode, workflowId: entry.workflowId,
      requestCorrelationId: entry.requestCorrelationId,
      requestedGoal: "Execute the bounded RE-001D single-point STM32 measurement.",
      requestedTargetRef: channel === 1 ? "RE-001:Vin" : "RE-001:Vout",
      groundingRequired: true, wiringChanged: false,
      confirmation: entry.confirmations.get(channel) ?? null,
      previousExecution: null, designContext: null,
    });
  }

  async recordSuccess(agent: Agent | undefined, operation: HardwareOperation, args: unknown, canonicalResult: unknown): Promise<UserMessage | undefined> {
    const entry = this.#entry(agent);
    const channel = requestedChannel(args);
    const expected = entry === undefined ? undefined : ORDER[entry.next];
    if (entry === undefined || channel === null || expected === undefined || expected[0] !== operation || expected[1] !== channel) return undefined;
    entry.operations.push({
      operation, channel, scope_remaining_invocations: 0,
      policy_reason: "allowed_confirmed_physical_setup", ipc_dispatch_count: 1,
      hardware_execution_count: 1, canonical_result: canonicalResult, failure_code: null,
    });
    entry.next += 1;
    if (entry.next !== ORDER.length) return undefined;
    entry.completing = true;
    try {
      const response = await this.#application.complete({
        workflowId: entry.workflowId, requestCorrelationId: entry.requestCorrelationId,
        governedReceipt: {
          contract: "aia-re001c-lite-validation", contract_version: "1.0",
          kind: "governed_measurement_receipt", status: "COMPLETED",
          operations: entry.operations, failure_code: null,
        },
      });
      if (response.workflow_id !== entry.workflowId || response.request_correlation_id !== entry.requestCorrelationId
        || response.publication.final_egress !== "SAFE") throw new Error("publication correlation invalid");
      this.#entries.delete(entry.workflowId);
      return createUserMessage({
        content: [{ type: "text", text: `Trusted RE-001D publication:\n${response.publication.text}` }],
        source: { kind: "plugin", plugin: "aia-re001d-application" },
      });
    } catch {
      entry.failed = true;
      return undefined;
    }
  }

  recordFailure(agent: Agent | undefined): void {
    const entry = this.#entry(agent);
    if (entry !== undefined) entry.failed = true;
  }

  dispose(agent: Agent): void { this.#entries.delete(String(agent.id)); }
  snapshot(agent: Agent): Readonly<{
    confirmed: boolean; next: number; failed: boolean;
    issuedScopeCount: number; physicalConfirmationCount: number;
  }> | undefined {
    const value = this.#entries.get(String(agent.id));
    return value === undefined ? undefined : Object.freeze({
      confirmed: value.confirmed, next: value.next, failed: value.failed,
      issuedScopeCount: value.scopes.size, physicalConfirmationCount: value.confirmations.size,
    });
  }
  #entry(agent: Agent | undefined): Entry | undefined { return agent === undefined ? undefined : this.#entries.get(String(agent.id)); }
}

export function installInteractiveRe001dAuthority(
  ctx: Context,
  application: Re001dApplicationPort,
): InteractiveRe001dAuthority {
  const authority = new InteractiveRe001dAuthority(application);
  ctx.on("agent/inbox/claimed", ({ agent, message }) => { void authority.claim(agent, message); });
  ctx.on("agent/disposed", ({ agent }) => authority.dispose(agent));
  return authority;
}

function scopes(workflowId: string, correlation: string, sequence: number) {
  return new Map(ORDER.map(([operation, channel], index) => {
    const scope = createTrustedOperationScope({
      scopeId: `interactive-re001d-${sequence}-${index + 1}`, workflowId,
      requestCorrelationId: correlation, allowedOperations: [{ operation, maxInvocations: 1 }],
      targetChannel: channel, targetIntent: channel === 1 ? "RE-001 Vin" : "RE-001 Vout",
      origin: "TRUSTED_HOST_WORKFLOW", authorizationRef: "interactive-re001d-intent-policy/v1",
    });
    return [key(operation, channel), Object.freeze({ scope, workflowId, requestCorrelationId: correlation })] as const;
  }));
}

function confirmations(workflowId: string, correlation: string, sequence: number) {
  return new Map<Channel, ReturnType<typeof createProbeSetupConfirmation>>(([1, 2] as const).map((channel) => [channel, createProbeSetupConfirmation({
    confirmationId: `interactive-re001d-${sequence}-ch${channel}`,
    source: "TRUSTED_USER_EVENT", confirmedBy: "web-user", channel,
    targetRef: channel === 1 ? "RE-001:Vin" : "RE-001:Vout",
    safeLowVoltageConfirmed: true, commonGroundConfirmed: true,
    confirmedAt: new Date().toISOString(), scope: { workflowId, requestCorrelationId: correlation },
  })]));
}

/**
 * Only the exact high-confidence workflow phrase authorizes. Generic
 * affirmatives ("yes", "confirm", "确认") never authorize by themselves, and
 * any other text revokes the prepared workflow as stale.
 */
function isConfirmationText(text: string): boolean {
  return text === RE001D_WEB_CONFIRMATION;
}

function trustedUserText(message: UserMessage): string | undefined {
  if (message.source.kind !== "user" || message.content.length !== 1 || message.content[0]?.type !== "text") return undefined;
  return message.content[0].text.trim();
}
function requestedChannel(args: unknown): Channel | null { const value = object(args)?.channel; return value === 1 || value === 2 ? value : null; }
function object(value: unknown): Readonly<Record<string, unknown>> | undefined { return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Readonly<Record<string, unknown>> : undefined; }
function key(operation: string | undefined, channel: Channel | null): string { return `${operation ?? "unknown"}:${channel ?? "none"}`; }
function validOrder(value: readonly (readonly [string, number])[]): boolean { return value.length === ORDER.length && value.every((item, index) => item[0] === ORDER[index]?.[0] && item[1] === ORDER[index]?.[1]); }
