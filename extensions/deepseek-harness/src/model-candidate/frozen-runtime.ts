import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { Context } from "@deepseek-ai/cordis";
import LlmRuntime, { createUserMessage, ReasoningEffortId } from "@deepseek-ai/dsh-llm";

import type { ModelInvocationRequest } from "./contract.ts";
import { executeOneShotCandidateWithDisposal, failedReceipt } from "./one-shot-executor.ts";
import { buildStructuredCandidatePrompt, STRUCTURED_CANDIDATE_SYSTEM_PROMPT } from "./prompt.ts";

const MODEL_DEADLINE_MS = 45_000;
const STREAM_IDLE_TIMEOUT_MS = 20_000;

/** Mount only LlmRuntime plus the exact frozen DeepSeek adapter. */
export async function runFrozenOneShot(request: ModelInvocationRequest): Promise<Record<string, unknown>> {
  const started = Date.now();
  const harnessRoot = process.env.DEEPSEEK_HARNESS_DEV_ROOT;
  if (harnessRoot === undefined) return failedReceipt(request, started, "MODEL_PROVIDER_UNAVAILABLE", "NOT_STARTED", 0);
  const ctx = new Context();
  const deadline = AbortSignal.timeout(MODEL_DEADLINE_MS);
  let result: Record<string, unknown>;
  try {
    const module = await import(pathToFileURL(join(
      resolve(harnessRoot), "packages", "llm", "llm-deepseek", "lib", "index.js",
    )).href);
    await ctx.plugin(LlmRuntime);
    await ctx.plugin(module, {
      apiKeyEnv: "DEEPSEEK_API_KEY",
      thinking: "disabled",
      reasoningEffort: "off",
      maxTokens: 512,
      streamIdleTimeoutMs: STREAM_IDLE_TIMEOUT_MS,
      retryPolicy: { mode: "normal", maxRetries: 0 },
      models: [{ id: "deepseek-v4-flash" }],
    });
    result = await executeOneShotCandidateWithDisposal(request, (collectorSignal) => ctx.llm.stream({
      provider: "deepseek-official",
      model: "deepseek-v4-flash",
      reasoningEffort: ReasoningEffortId("off"),
      messages: [createUserMessage({
        content: [{ type: "text", text: buildStructuredCandidatePrompt(request.projection) }],
        source: { kind: "user" },
      })],
      system: STRUCTURED_CANDIDATE_SYSTEM_PROMPT,
      tools: [],
      temperature: 0,
      maxTokens: 512,
      signal: AbortSignal.any([deadline, collectorSignal]),
    }), () => ctx.fiber.dispose());
  } catch {
    result = failedReceipt(
      request,
      started,
      deadline.aborted ? "MODEL_REQUEST_TIMEOUT" : "MODEL_PROCESS_FAILED",
      deadline.aborted ? "INCOMPLETE" : "ERROR",
      0,
    );
    try { await ctx.fiber.dispose(); } catch { /* bounded setup failure already selected */ }
  }
  return result;
}
