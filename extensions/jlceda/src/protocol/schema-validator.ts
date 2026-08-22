import { Ajv2020 } from "ajv/dist/2020.js";
import type { ErrorObject, ValidateFunction } from "ajv";

import {
  SchemaDefinitionError,
  SchemaReferenceError,
  type LoadedSchema,
} from "./schema-loader.ts";


export class SchemaNotFoundError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SchemaNotFoundError";
  }
}

export interface ValidationResult {
  readonly isValid: boolean;
  readonly errors: readonly ErrorObject[];
}

export class SchemaValidator {
  readonly #ajv: Ajv2020;

  constructor(schemas: readonly LoadedSchema[]) {
    this.#ajv = new Ajv2020({ allErrors: true, strict: true });
    for (const schema of schemas) {
      try {
        this.#ajv.addSchema(schema.document, schema.id);
      } catch (error) {
        throw new SchemaDefinitionError(
          `Cannot register JSON Schema document ${schema.path}: ${error}`,
        );
      }
    }

    for (const schema of schemas) {
      try {
        const compiled = this.#ajv.getSchema(schema.id);
        if (compiled === undefined) {
          throw new Error(`Schema was not registered: ${schema.id}`);
        }
      } catch (error) {
        throw new SchemaReferenceError(
          `Cannot compile schema ${schema.id} from ${schema.path}: ${error}`,
          { cause: error },
        );
      }
    }
  }

  validate(schemaRef: string, instance: unknown): ValidationResult {
    const validator = this.#validatorFor(schemaRef);
    const isValid = validator(instance);
    return {
      isValid,
      errors: validator.errors === null || validator.errors === undefined
        ? []
        : [...validator.errors],
    };
  }

  #validatorFor(schemaRef: string): ValidateFunction {
    let validator: ValidateFunction | undefined;
    try {
      validator = this.#ajv.getSchema(schemaRef);
    } catch (error) {
      throw new SchemaNotFoundError(`Unknown schema reference: ${schemaRef}`);
    }
    if (validator === undefined) {
      throw new SchemaNotFoundError(`Unknown schema reference: ${schemaRef}`);
    }
    return validator;
  }
}
