import { createUserMessage, type UserMessage } from "@deepseek-ai/dsh-llm";

import type { TeachingEvidenceContext } from "../evidence/index.ts";

const CONTEXT_MARKER = "AIA_TEACHING_EVIDENCE_CONTEXT";
const MAX_CONTEXT_CHARACTERS = 16_384;

export function serializeTeachingEvidenceContext(context: TeachingEvidenceContext): string {
  const serialized = `${CONTEXT_MARKER}\n${JSON.stringify(context)}`;
  if (serialized.length > MAX_CONTEXT_CHARACTERS) {
    throw new RangeError("TeachingEvidenceContext exceeds the bounded Agent context limit");
  }
  return serialized;
}

export function createTeachingEvidenceMessage(context: TeachingEvidenceContext): UserMessage {
  return createUserMessage({
    content: [{ type: "text", text: serializeTeachingEvidenceContext(context) }],
    source: { kind: "plugin", plugin: "aia-hardware-evidence" },
  });
}
