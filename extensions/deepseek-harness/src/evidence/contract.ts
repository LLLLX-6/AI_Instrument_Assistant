import { Ajv2020 } from "ajv/dist/2020.js";
import addFormatsModule from "ajv-formats";

import hardwareSchema from "../../../../protocols/hardware/v1/hardware-tool.schema.json" with { type: "json" };
import evidenceItemSchema from "../../../../protocols/evidence/v1/common/evidence-item.schema.json" with { type: "json" };
import teachingContextSchema from "../../../../protocols/evidence/v1/teaching-evidence-context.schema.json" with { type: "json" };
import engineeringContextSchema from "../../../../protocols/evidence/v1/engineering-evidence-context.schema.json" with { type: "json" };

import type { TeachingEvidenceContext } from "./models.ts";

export const EVIDENCE_CONTEXT_SCHEMA_ID =
  "https://aia.local/protocols/evidence/v1/teaching-evidence-context.schema.json";

export class EvidenceContractError extends Error {
  constructor(message = "Evidence v1 contract value is invalid") {
    super(message);
    this.name = "EvidenceContractError";
  }
}

export interface EvidenceValidationResult {
  readonly valid: boolean;
}

export class EvidenceContractBinding {
  readonly schemaId = EVIDENCE_CONTEXT_SCHEMA_ID;
  readonly #validators: ReadonlyMap<string, ReturnType<Ajv2020["compile"]>>;

  private constructor() {
    const ajv = new Ajv2020({ allErrors: true, strict: true, strictTypes: false });
    const addFormats = addFormatsModule as unknown as (instance: Ajv2020) => Ajv2020;
    addFormats(ajv);
    for (const schema of [hardwareSchema, evidenceItemSchema, teachingContextSchema, engineeringContextSchema]) {
      ajv.addSchema(schema);
    }
    const validators = new Map<string, ReturnType<Ajv2020["compile"]>>();
    for (const schema of [evidenceItemSchema, teachingContextSchema, engineeringContextSchema]) {
      const validate = ajv.getSchema(schema.$id);
      if (!validate) throw new EvidenceContractError("Evidence schema did not compile");
      validators.set(schema.$id, validate);
    }
    this.#validators = validators;
  }

  static fromRepository(_repositoryRoot: string): EvidenceContractBinding {
    return new EvidenceContractBinding();
  }

  validate(schemaRef: string, value: unknown): EvidenceValidationResult {
    const validator = this.#validators.get(schemaRef);
    if (!validator) throw new EvidenceContractError("Unknown Evidence v1 schema identifier");
    return Object.freeze({ valid: Boolean(validator(value)) });
  }

  parseTeachingContext(value: unknown): TeachingEvidenceContext {
    if (!this.validate(this.schemaId, value).valid) throw new EvidenceContractError();
    assertDutyCycleRepresentations(value);
    const wire = value as Record<string, unknown>;
    const artifact = wire.artifact as Record<string, unknown> | null;
    let boundArtifact: TeachingEvidenceContext["artifact"] = null;
    if (artifact) {
      const reference = artifact.reference as Record<string, unknown>;
      boundArtifact = {
        artifactId: reference.artifact_id as string,
        uri: reference.uri as string,
        mediaType: reference.media_type as string,
        sizeBytes: (reference.size_bytes as number | undefined) ?? null,
        sha256: (reference.sha256 as string | undefined) ?? null,
        channel: artifact.channel as number,
        pointCount: artifact.pointCount as number,
        sampleIntervalSeconds: artifact.sampleIntervalSeconds as number,
        timeRangeSeconds: artifact.timeRangeSeconds as readonly [number, number],
        voltageRangeV: artifact.voltageRangeV as readonly [number, number],
        acquisitionMode: artifact.acquisitionMode as string,
        capturedAt: artifact.capturedAt as string,
        opaque: true,
      };
    }
    const result = {
      ...wire,
      artifact: boundArtifact,
    } as unknown as TeachingEvidenceContext;
    return deepFreeze(result);
  }

  toWire(context: TeachingEvidenceContext): Record<string, unknown> {
    let artifact: Record<string, unknown> | null = null;
    if (context.artifact) {
      const reference: Record<string, unknown> = {
        artifact_id: context.artifact.artifactId,
        uri: context.artifact.uri,
        media_type: context.artifact.mediaType,
      };
      if (context.artifact.sizeBytes !== null) reference.size_bytes = context.artifact.sizeBytes;
      if (context.artifact.sha256 !== null) reference.sha256 = context.artifact.sha256;
      artifact = {
        reference,
        channel: context.artifact.channel,
        pointCount: context.artifact.pointCount,
        sampleIntervalSeconds: context.artifact.sampleIntervalSeconds,
        timeRangeSeconds: [...context.artifact.timeRangeSeconds],
        voltageRangeV: [...context.artifact.voltageRangeV],
        acquisitionMode: context.artifact.acquisitionMode,
        capturedAt: context.artifact.capturedAt,
        opaque: true,
      };
    }
    const result = { ...context, artifact } as Record<string, unknown>;
    if (!this.validate(this.schemaId, result).valid) throw new EvidenceContractError();
    assertDutyCycleRepresentations(result);
    return result;
  }
}

function assertDutyCycleRepresentations(value: unknown): void {
  const wire = value as Record<string, unknown>;
  for (const collectionName of ["facts", "analyses", "inferences"] as const) {
    const collection = wire[collectionName] as readonly Record<string, unknown>[];
    for (const item of collection) {
      const itemValue = item.value;
      if (itemValue && typeof itemValue === "object" && "ratio" in itemValue && "percent" in itemValue) {
        const duty = itemValue as { readonly ratio: number; readonly percent: number };
        if (Math.abs(duty.ratio * 100 - duty.percent) > 1e-12) {
          throw new EvidenceContractError("Duty-cycle ratio and percent representations disagree");
        }
      }
    }
  }
}

function deepFreeze<T>(value: T): T {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const nested of Object.values(value as Record<string, unknown>)) deepFreeze(nested);
  }
  return value;
}
