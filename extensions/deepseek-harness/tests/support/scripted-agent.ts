import type { Agent } from "@deepseek-ai/dsh-agent";
import AgentRegistry from "@deepseek-ai/dsh-agent";
import AgentLoop from "@deepseek-ai/dsh-agent-loop";
import { Context } from "@deepseek-ai/cordis";
import LlmRuntime, {
  createUserMessage,
  LlmAdapter,
  ToolCallId,
  type GenerateOptions,
  type StreamChunk,
} from "@deepseek-ai/dsh-llm";
import SessionStore, { SessionId } from "@deepseek-ai/dsh-session";
import SessionProjectionRegistry from "@deepseek-ai/dsh-session-projection";
import SystemPrompt from "@deepseek-ai/dsh-system-prompt";
import ToolRuntime from "@deepseek-ai/dsh-tools";

import {
  applyWithDependencies,
  type Config,
  type HardwareClientPort,
  type PluginDependencies,
} from "../../src/index.ts";
import {
  HARDWARE_TOOL_CONTRACTS,
  type HardwareOperation,
} from "../../src/generated/hardware-tools.generated.ts";
import {
  createHardwareToolPolicyContext,
  type HardwareToolPolicyContext,
} from "../../src/policy/index.ts";
import type { EgressDiagnostic } from "../../src/egress/index.ts";
import {
  SEMANTIC_HARDWARE_OPERATIONS,
  createTrustedOperationScope,
  type TrustedOperationScopeContext,
} from "../../src/operation-scope/index.ts";

export type ScriptStep =
  | readonly StreamChunk[]
  | ((request: GenerateOptions) => readonly StreamChunk[]);

export class ScriptedAgentAdapter extends LlmAdapter {
  readonly requests: GenerateOptions[] = [];
  private readonly steps: ScriptStep[];

  constructor(steps: ScriptStep[]) {
    super();
    this.steps = steps;
  }

  override resolveModel(provider: string, model: string) {
    return Promise.resolve({ provider, id: model, name: model });
  }

  async *stream(request: GenerateOptions): AsyncIterable<StreamChunk> {
    this.requests.push(request);
    const step = this.steps.shift();
    if (step === undefined) throw new Error("ScriptedAgentAdapter: script exhausted");
    const chunks = typeof step === "function" ? step(request) : step;
    for (const chunk of chunks) yield chunk;
  }
}

export class RecordingHardwareClient implements HardwareClientPort {
  started = 0;
  disposed = 0;
  readonly calls: Array<{ operation: string; args: unknown }> = [];

  result: unknown;

  constructor(result: unknown) {
    this.result = result;
  }

  start(): void { this.started += 1; }
  async dispose(): Promise<void> { this.disposed += 1; }
  async invoke(operation: HardwareOperation, args: unknown): Promise<unknown> {
    this.calls.push({ operation, args });
    if (this.result instanceof Error) throw this.result;
    return this.result;
  }
}

export function simulatedPolicy(operation: string, args: unknown): HardwareToolPolicyContext {
  const values = record(args);
  return createHardwareToolPolicyContext({
    operation,
    channel: values.channel === 1 || values.channel === 2 ? values.channel : null,
    backendMode: "SIMULATED",
    requestCorrelationId: "agent-evaluation",
    requestedGoal: `User requested ${operation}.`,
    requestedTargetRef: typeof values.context_id === "string" ? values.context_id : null,
    groundingRequired: operation !== "hardware.get_status",
    wiringChanged: false,
    confirmation: null,
    previousExecution: null,
    designContext: null,
  });
}

export interface AgentHarnessOptions {
  readonly script: ScriptStep[];
  readonly client?: RecordingHardwareClient;
  readonly config?: Config;
  readonly resolvePolicyContext?: PluginDependencies["resolvePolicyContext"];
  readonly onEgressDiagnostic?: (diagnostic: EgressDiagnostic) => void;
  readonly operationScopeContext?: TrustedOperationScopeContext;
}

let sessionSequence = 0;
let scopeSequence = 0;

export async function createAgentHarness(options: AgentHarnessOptions): Promise<{
  readonly ctx: Context;
  readonly agent: Agent;
  readonly adapter: ScriptedAgentAdapter;
}> {
  const ctx = new Context();
  const adapter = new ScriptedAgentAdapter(options.script);
  const operationScopeContext = options.operationScopeContext ?? trustedTestScopeContext();
  await ctx.plugin(LlmRuntime);
  await ctx.plugin(SessionStore);
  await ctx.plugin(SessionProjectionRegistry);
  await ctx.plugin(SystemPrompt, { persona: "" });
  await ctx.plugin(ToolRuntime);
  await ctx.plugin(AgentRegistry);
  await ctx.plugin(AgentLoop, { agents: [] });
  ctx.llm.registerAdapter(["aia-scripted"], adapter);
  applyWithDependencies(
    ctx,
    { backendMode: "SIMULATED", ...options.config },
    {
      ...(options.client === undefined ? {} : { createClient: () => options.client! }),
      resolveOperationScopeContext: () => operationScopeContext,
      resolvePolicyContext: options.resolvePolicyContext ?? simulatedPolicy,
      onEgressDiagnostic: options.onEgressDiagnostic,
    },
  );
  const agent = await ctx.agentLoop.create(
    SessionId(`aia-agent-evaluation-${++sessionSequence}`),
    { provider: "aia-scripted", model: "scripted" },
  );
  return { ctx, agent, adapter };
}

export function trustedTestScopeContext(): TrustedOperationScopeContext {
  const ordinal = ++scopeSequence;
  const workflowId = `scripted-agent-workflow-${ordinal}`;
  const scope = createTrustedOperationScope({
    scopeId: `scripted-agent-scope-${ordinal}`,
    requestCorrelationId: workflowId,
    workflowId,
    allowedOperations: SEMANTIC_HARDWARE_OPERATIONS.map((operation) => ({
      operation,
      maxInvocations: 8,
    })),
    targetChannel: null,
    targetIntent: "scripted Agent regression",
    origin: "TRUSTED_VALIDATION_SCENARIO",
    authorizationRef: null,
  });
  return Object.freeze({ scope, requestCorrelationId: workflowId, workflowId });
}

export async function runAgent(agent: Agent, prompt: string): Promise<void> {
  agent.followup(createUserMessage({
    content: [{ type: "text", text: prompt }],
    source: { kind: "user" },
  }));
  await agent.whenIdle();
}

export function toolCallResponse(id: string, name: string, args: unknown): StreamChunk[] {
  const callId = ToolCallId(id);
  const argumentsJson = JSON.stringify(args);
  return [
    { type: "block-start", index: 0, blockType: "tool-call" },
    { type: "tool-call-delta", index: 0, id: callId, name, argumentsDelta: argumentsJson },
    { type: "block-end", index: 0, block: { type: "tool-call", id: callId, name, arguments: argumentsJson } },
    { type: "usage", usage: { inputTokens: 10, outputTokens: 5 } },
    { type: "finish", reason: { kind: "tool-calls" } },
  ];
}

export function textResponse(text: string): StreamChunk[] {
  return [
    { type: "block-start", index: 0, blockType: "text" },
    { type: "text-delta", index: 0, text },
    { type: "block-end", index: 0, block: { type: "text", text } },
    { type: "usage", usage: { inputTokens: 10, outputTokens: text.length } },
    { type: "finish", reason: { kind: "stop" } },
  ];
}

export function finalAgentText(agent: Agent): string {
  const message = agent.session.deriveMessages().at(-1);
  return message?.content
    .filter((block) => block.type === "text")
    .map((block) => block.text)
    .join("") ?? "";
}

export function visibleToolCalls(agent: Agent): Array<{ name: string; arguments: string }> {
  return agent.session.snapshotEvents()
    .filter((event) => event.type === "tool/call")
    .map((event) => ({ name: event.data.name, arguments: event.data.arguments }));
}

export function requestText(request: GenerateOptions): string {
  return request.messages.flatMap((message) => message.content)
    .filter((block) => block.type === "text")
    .map((block) => block.text)
    .join("\n");
}

export function visibleToolNames(request: GenerateOptions): string[] {
  return request.tools?.map((tool) => tool.name).sort() ?? [];
}

export const EXPECTED_HARDWARE_TOOL_NAMES = Object.freeze(
  HARDWARE_TOOL_CONTRACTS.map((contract) => contract.harnessName).sort(),
);

function record(value: unknown): Readonly<Record<string, unknown>> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Readonly<Record<string, unknown>>
    : {};
}
