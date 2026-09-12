import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { Ajv2020 } from "ajv/dist/2020.js";
import addFormatsModule from "ajv-formats";

export const MODEL_REQUEST_SCHEMA_ID = "https://ai-instrument-assistant.local/schemas/harness-publication-bridge/v1/model-invocation-request.schema.json";
export const MODEL_RECEIPT_SCHEMA_ID = "https://ai-instrument-assistant.local/schemas/harness-publication-bridge/v1/model-invocation-receipt.schema.json";
export const FINAL_EGRESS_REQUEST_SCHEMA_ID = "https://ai-instrument-assistant.local/schemas/harness-publication-bridge/v1/final-egress-request.schema.json";
export const FINAL_EGRESS_RECEIPT_SCHEMA_ID = "https://ai-instrument-assistant.local/schemas/harness-publication-bridge/v1/final-egress-receipt.schema.json";

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "..");
const protocolRoot = join(repositoryRoot, "protocols", "harness-publication-bridge", "v1");
const ajv = new Ajv2020({ allErrors: true, strict: true });
const addFormats = addFormatsModule as unknown as (instance: Ajv2020) => Ajv2020;
addFormats(ajv);
for (const name of [
  "model-invocation-request.schema.json",
  "model-invocation-receipt.schema.json",
  "final-egress-request.schema.json",
  "final-egress-receipt.schema.json",
]) {
  ajv.addSchema(JSON.parse(readFileSync(join(protocolRoot, name), "utf8")));
}

export interface ModelInvocationRequest {
  readonly schema_id: "aia-harness-publication-model-request/v1";
  readonly request_id: string;
  readonly request_digest: string;
  readonly prompt_profile: "AIA_STRUCTURED_CANDIDATE_V1";
  readonly projection: Readonly<Record<string, unknown>>;
}

export function validateBridgeValue<T>(schemaId: string, value: unknown): T {
  const validate = ajv.getSchema(schemaId);
  if (validate === undefined || !validate(value)) throw new TypeError("PRIVATE_BRIDGE_SCHEMA_INVALID");
  return value as T;
}
