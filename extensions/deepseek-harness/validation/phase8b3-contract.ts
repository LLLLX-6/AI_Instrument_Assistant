import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { Ajv2020 } from "ajv/dist/2020.js";
import addFormatsModule from "ajv-formats";

export const PHASE8B3_REQUEST_SCHEMA_ID = "https://aia.local/validation/support/phase8b3/v1/request.schema.json";
export const PHASE8B3_RECEIPT_SCHEMA_ID = "https://aia.local/validation/support/phase8b3/v1/receipt.schema.json";

export class Phase8B3ValidationContractBinding {
  readonly #ajv: Ajv2020;

  private constructor(ajv: Ajv2020) {
    this.#ajv = ajv;
  }

  static fromRepository(repositoryRoot: string): Phase8B3ValidationContractBinding {
    const ajv = new Ajv2020({ allErrors: true, strict: true, strictTypes: false });
    const addFormats = addFormatsModule as unknown as (instance: Ajv2020) => Ajv2020;
    addFormats(ajv);
    const paths = [
      "protocols/hardware/v1/hardware-tool.schema.json",
      "protocols/evidence/v1/common/evidence-item.schema.json",
      "protocols/evidence/v1/engineering-evidence-context.schema.json",
      "protocols/evidence/v1/teaching-evidence-context.schema.json",
      "validation/support/phase8b3/v1/request.schema.json",
      "validation/support/phase8b3/v1/receipt.schema.json",
    ];
    for (const path of paths) {
      ajv.addSchema(JSON.parse(readFileSync(resolve(repositoryRoot, path), "utf8")) as object);
    }
    if (!ajv.getSchema(PHASE8B3_REQUEST_SCHEMA_ID) || !ajv.getSchema(PHASE8B3_RECEIPT_SCHEMA_ID)) {
      throw new Error("Phase 8B.3 validation schemas did not compile");
    }
    return new Phase8B3ValidationContractBinding(ajv);
  }

  validate(schemaId: string, value: unknown): boolean {
    const validate = this.#ajv.getSchema(schemaId);
    if (!validate) throw new Error("Unknown Phase 8B.3 validation schema");
    return Boolean(validate(value));
  }

  requireValid(schemaId: string, value: unknown): Readonly<Record<string, unknown>> {
    if (!this.validate(schemaId, value) || typeof value !== "object" || value === null || Array.isArray(value)) {
      throw new TypeError("Phase 8B.3 private validation contract rejected the value");
    }
    return Object.freeze(value as Record<string, unknown>);
  }
}
