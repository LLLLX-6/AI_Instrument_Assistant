import type { Agent } from "@deepseek-ai/dsh-agent";
import type { Context } from "@deepseek-ai/cordis";
import type { UserMessage } from "@deepseek-ai/dsh-session";

import {
  createTrustedOperationScope,
  type TrustedOperationScopeContext,
} from "./operation-scope/index.ts";

const STATUS_REQUEST = "check the current hardware status";

/**
 * Process-local composition between a trusted Harness inbox claim and the
 * existing operation-scope gate. It recognizes one deliberately narrow Host
 * intent and never consumes tool arguments or model output as authority.
 */
export class InteractiveStatusScopeAuthority {
  readonly #contexts = new Map<string, TrustedOperationScopeContext>();
  #scopeSequence = 0;

  claim(agent: Agent, message: UserMessage): boolean {
    const workflowId = String(agent.id);

    // A newly claimed request always supersedes authority from the previous
    // request, including when the new request has no authorized intent.
    this.#contexts.delete(workflowId);
    if (!isTrustedStatusRequest(message)) return false;

    const requestCorrelationId = String(message.id);
    const scope = createTrustedOperationScope({
      scopeId: `interactive-status-${++this.#scopeSequence}`,
      workflowId,
      requestCorrelationId,
      allowedOperations: [{ operation: "hardware.get_status", maxInvocations: 1 }],
      targetChannel: null,
      targetIntent: "Read current hardware status.",
      origin: "TRUSTED_HOST_WORKFLOW",
      authorizationRef: "interactive-status-intent-policy/v1",
    });
    this.#contexts.set(workflowId, Object.freeze({
      scope,
      workflowId,
      requestCorrelationId,
    }));
    return true;
  }

  resolve(agent: Agent | undefined): TrustedOperationScopeContext | undefined {
    return agent === undefined ? undefined : this.#contexts.get(String(agent.id));
  }

  dispose(agent: Agent): void {
    this.#contexts.delete(String(agent.id));
  }
}

export function installInteractiveStatusScopeAuthority(
  ctx: Context,
): InteractiveStatusScopeAuthority {
  const authority = new InteractiveStatusScopeAuthority();
  ctx.on("agent/inbox/claimed", ({ agent, message }) => {
    authority.claim(agent, message);
  });
  ctx.on("agent/disposed", ({ agent }) => {
    authority.dispose(agent);
  });
  return authority;
}

function isTrustedStatusRequest(message: UserMessage): boolean {
  if (message.source.kind !== "user" || message.content.length !== 1) return false;
  const block = message.content[0];
  if (block?.type !== "text") return false;
  const normalized = block.text.trim().toLowerCase().replace(/\s+/g, " ").replace(/[.?!]$/, "");
  return normalized === STATUS_REQUEST;
}
