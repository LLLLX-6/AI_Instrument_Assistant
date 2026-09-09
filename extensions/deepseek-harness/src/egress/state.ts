import type { TeachingEvidenceContext } from "../evidence/index.ts";
import type { PolicyDecision } from "../policy/index.ts";
import type { TrustedAgentEgressState } from "./models.ts";

const MAX_SESSIONS = 1_024;
const EMPTY = Object.freeze({ policyDecision: null, evidence: null });

export class AgentEgressStateStore {
  readonly #states = new Map<string, TrustedAgentEgressState>();

  recordPolicy(correlationId: string, decision: PolicyDecision): void {
    const previous = this.#states.get(correlationId) ?? EMPTY;
    this.#set(correlationId, Object.freeze({ policyDecision: decision, evidence: previous.evidence }));
  }

  recordEvidence(correlationId: string, evidence: TeachingEvidenceContext): void {
    const previous = this.#states.get(correlationId) ?? EMPTY;
    this.#set(correlationId, Object.freeze({ policyDecision: previous.policyDecision, evidence }));
  }

  snapshot(correlationId: string): TrustedAgentEgressState {
    return this.#states.get(correlationId) ?? EMPTY;
  }

  clear(correlationId: string): void {
    this.#states.delete(correlationId);
  }

  #set(correlationId: string, value: TrustedAgentEgressState): void {
    this.#states.delete(correlationId);
    this.#states.set(correlationId, value);
    while (this.#states.size > MAX_SESSIONS) this.#states.delete(this.#states.keys().next().value as string);
  }
}

