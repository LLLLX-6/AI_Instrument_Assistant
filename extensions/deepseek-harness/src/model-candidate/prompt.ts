export const PROMPT_PROFILE = "AIA_STRUCTURED_CANDIDATE_V1" as const;

export const STRUCTURED_CANDIDATE_SYSTEM_PROMPT = [
  "AIA_STRUCTURED_CANDIDATE_V1",
  "Return exactly one teaching-claims/v1 JSON object.",
  "Echo every supplied binding exactly and select only supplied permission aliases.",
  "Select between 1 and 12 unique aliases.",
  "Do not emit Markdown, prose, explanations, values, units, diagnosis, hypothesis, proposals, or Tool/action fields.",
].join("\n");

export function buildStructuredCandidatePrompt(projection: unknown): string {
  const prompt = `AIA_STRUCTURED_CANDIDATE_V1\n${JSON.stringify(projection)}`;
  if (Buffer.byteLength(STRUCTURED_CANDIDATE_SYSTEM_PROMPT, "utf8") > 4_096
    || Buffer.byteLength(prompt, "utf8") > 72 * 1_024) {
    throw new TypeError("MODEL_PROMPT_BOUND_INVALID");
  }
  return prompt;
}
