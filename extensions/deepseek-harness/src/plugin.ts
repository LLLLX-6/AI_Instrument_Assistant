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
import {
  createTeachingEvidenceMessage,
  HARDWARE_AGENT_POLICY,
  installHarnessAgentEgressBoundary,
} from "./agent/index.ts";
import { presentAdapterFailure, presentHardwareResult } from "./evidence/index.ts";
import { AgentEgressStateStore, type EgressDiagnostic } from "./egress/index.ts";
import type { GroundingDiagnostic } from "./grounding/index.ts";
import { AdapterFailure } from "./ipc/errors.ts";
import {
  createHardwareToolPolicyContext,
  evaluateHardwareToolPolicy,
  type BackendMode,
  type HardwareToolPolicyContext,
} from "./policy/index.ts";
import {
  OperationScopeGate,
  createTrustedOperationScope,
  type TrustedOperationScopeContext,
} from "./operation-scope/index.ts";

export interface Config {
  readonly endpoint?: string;
  readonly secretFile?: string;
  readonly connectTimeoutMs?: number;
  readonly authTimeoutMs?: number;
  readonly requestTimeoutMs?: number;
  readonly backendMode?: BackendMode;
}

export interface HardwareClientPort {
  start(): void;
  dispose(): Promise<void>;
  invoke(operation: HardwareOperation, args: unknown, signal: AbortSignal): Promise<unknown>;
}

export interface PluginDependencies {
  readonly createClient: (config: Required<Config>) => HardwareClientPort;
  readonly resolveOperationScopeContext: (
    config: Required<Config>,
  ) => TrustedOperationScopeContext;
  readonly resolvePolicyContext: (
    operation: string,
    args: unknown,
    config: Required<Config>,
  ) => HardwareToolPolicyContext;
  readonly onEgressDiagnostic?: (diagnostic: EgressDiagnostic) => void;
  readonly onGroundingDiagnostic?: (diagnostic: GroundingDiagnostic) => void;
}

const DEFAULT_CONFIG: Required<Config> = {
  endpoint: "ws://127.0.0.1:49625",
  secretFile: ".aia-secrets/harness-hardware-psk.txt",
  connectTimeoutMs: 2_000,
  authTimeoutMs: 2_000,
  requestTimeoutMs: 30_000,
  backendMode: "REAL",
};

const FAIL_CLOSED_OPERATION_SCOPE = createTrustedOperationScope({
  scopeId: "no-trusted-operation-authorization",
  requestCorrelationId: "unconfigured-host-workflow",
  workflowId: "unconfigured-host-workflow",
  allowedOperations: [],
  targetChannel: null,
  targetIntent: null,
  origin: "TRUSTED_HOST_WORKFLOW",
  authorizationRef: null,
});

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
  resolveOperationScopeContext() {
    return Object.freeze({
      scope: FAIL_CLOSED_OPERATION_SCOPE,
      requestCorrelationId: FAIL_CLOSED_OPERATION_SCOPE.requestCorrelationId,
      workflowId: FAIL_CLOSED_OPERATION_SCOPE.workflowId,
    });
  },
  resolvePolicyContext(operation, args, config) {
    const values = object(args);
    return createHardwareToolPolicyContext({
      operation,
      channel: typeof values?.channel === "number" ? values.channel : null,
      backendMode: config.backendMode,
      requestCorrelationId: typeof values?.context_id === "string"
        ? values.context_id
        : "harness-tool-request",
      requestedGoal: `Execute explicitly selected semantic operation ${operation}.`,
      requestedTargetRef: typeof values?.context_id === "string" ? values.context_id : null,
      groundingRequired: operation !== "hardware.get_status",
      wiringChanged: false,
      confirmation: null,
      previousExecution: null,
      designContext: null,
    });
  },
};

export function applyWithDependencies(
  ctx: Context,
  suppliedConfig: Config = {},
  suppliedDependencies: Partial<PluginDependencies> = {},
): void {
  const dependencies: PluginDependencies = { ...REAL_DEPENDENCIES, ...suppliedDependencies };
  const config = normalizeConfig(suppliedConfig);
  const client = dependencies.createClient(config);
  const egressState = new AgentEgressStateStore();
  const operationScopeGate = new OperationScopeGate();
  ctx.systemPrompt.section({
    name: "aia:hardware-agent-policy",
    order: 700,
    text: HARDWARE_AGENT_POLICY,
  });
  ctx.effect(() => {
    client.start();
    return () => client.dispose();
  }, "aia-hardware-ipc-client");
  ctx.effect(() => installHarnessAgentEgressBoundary(
    ctx,
    egressState,
    (diagnostic) => {
      dependencies.onEgressDiagnostic?.(diagnostic);
      ctx.logger.warn(`Agent egress blocked category=${diagnostic.category} source=${diagnostic.source} correlation=${diagnostic.correlationId}`);
    },
    (diagnostic) => {
      dependencies.onGroundingDiagnostic?.(diagnostic);
      ctx.logger.warn(`Agent grounding blocked category=${diagnostic.category} claim=${diagnostic.claimKind} correlation=${diagnostic.correlationId}`);
    },
  ), "aia-agent-output-boundary");

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
          throw safeAdapterFailure("invalid_tool_arguments", "NOT_SENT");
        }
        const trustedScopeContext = dependencies.resolveOperationScopeContext(config);
        const scopeRequest = {
          requestCorrelationId: trustedScopeContext.requestCorrelationId,
          workflowId: trustedScopeContext.workflowId,
          operation,
          channel: requestedChannel(args),
        };
        const scopeDecision = operationScopeGate.evaluate(trustedScopeContext.scope, scopeRequest);
        if (scopeDecision.decision !== "ALLOW") {
          throw safeAdapterFailure("operation_scope_denied", "NOT_SENT");
        }
        const policyContext = dependencies.resolvePolicyContext(operation, args, config);
        if (policyContext.operation !== operation || policyContext.channel !== requestedChannel(args)) {
          throw safeAdapterFailure("policy_denied", "NOT_SENT");
        }
        const policy = evaluateHardwareToolPolicy(policyContext);
        const correlationId = exec.agent === undefined ? null : String(exec.agent.session.id);
        if (correlationId !== null) egressState.recordPolicy(correlationId, policy);
        if (policy.decision === "REQUIRE_CONFIRMATION") {
          throw safeAdapterFailure("policy_confirmation_required", "NOT_SENT");
        }
        if (policy.decision !== "ALLOW") {
          throw safeAdapterFailure("policy_denied", "NOT_SENT");
        }
        const dispatchAuthorization = operationScopeGate.authorizeDispatch(
          trustedScopeContext.scope,
          scopeRequest,
        );
        if (dispatchAuthorization.decision !== "ALLOW") {
          throw safeAdapterFailure("operation_scope_denied", "NOT_SENT");
        }
        const evidenceOptions = {
          requestedGoal: policyContext.requestedGoal,
          measurementDecisionReason: policy.explanation,
          confirmationState: policyContext.backendMode === "SIMULATED"
            ? "SIMULATED" as const
            : operation === "hardware.get_status"
              ? "NOT_REQUIRED" as const
              : "CONFIRMED" as const,
        };
        try {
          const value = await client.invoke(operation, args, exec.signal);
          const outputViolations = validateJsonSchemaValue(outputSchema, value, "");
          if (outputViolations.length) {
            throw safeAdapterFailure("backend_response_invalid", "RESPONSE_RECEIVED");
          }
          const evidence = presentHardwareResult(value, evidenceOptions);
          if (correlationId !== null) egressState.recordEvidence(correlationId, evidence);
          exec.deferContext(createTeachingEvidenceMessage(evidence));
          return value;
        } catch (error: unknown) {
          if (error instanceof AdapterFailure) {
            const evidence = presentAdapterFailure({
              code: error.code,
              message: error.message,
              deliveryState: error.deliveryState,
              operation,
            }, evidenceOptions);
            if (correlationId !== null) egressState.recordEvidence(correlationId, evidence);
            exec.deferContext(createTeachingEvidenceMessage(evidence));
          }
          throw error;
        }
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
  if (merged.backendMode !== "REAL" && merged.backendMode !== "SIMULATED") {
    throw new Error("backendMode must be REAL or SIMULATED");
  }
  return Object.freeze(merged);
}

function object(value: unknown): Readonly<Record<string, unknown>> | undefined {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Readonly<Record<string, unknown>>
    : undefined;
}

function requestedChannel(args: unknown): 1 | 2 | null {
  const value = object(args)?.channel;
  return value === 1 || value === 2 ? value : null;
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
