import { Ajv2020 } from 'ajv/dist/2020.js';
import type { ErrorObject, ValidateFunction } from 'ajv';

import envelopeSchema from '../../../../protocols/jlceda/v1/common/envelope.schema.json' with { type: 'json' };
import identifiersSchema from '../../../../protocols/jlceda/v1/common/identifiers.schema.json' with { type: 'json' };
import securitySchema from '../../../../protocols/jlceda/v1/common/security.schema.json' with { type: 'json' };
import errorsSchema from '../../../../protocols/jlceda/v1/common/errors.schema.json' with { type: 'json' };
import designObjectRefSchema from '../../../../protocols/jlceda/v1/models/design-object-ref.schema.json' with { type: 'json' };
import designDocumentSchema from '../../../../protocols/jlceda/v1/models/design-document.schema.json' with { type: 'json' };
import messageSchema from '../../../../protocols/jlceda/v1/message.schema.json' with { type: 'json' };
import edaDocumentSchema from '../../../../protocols/jlceda/v1/messages/eda-document.schema.json' with { type: 'json' };
import handshakeSchema from '../../../../protocols/jlceda/v1/messages/handshake.schema.json' with { type: 'json' };
import heartbeatSchema from '../../../../protocols/jlceda/v1/messages/heartbeat.schema.json' with { type: 'json' };


const MESSAGE_SCHEMA_ID = 'aia://protocol/jlceda/v1/message';

export class ProtocolMessageValidationError extends Error {
  readonly errors: readonly ErrorObject[];

  constructor(errors: readonly ErrorObject[]) {
    super('Message does not satisfy the AIA-JLCEDA v1 root schema');
    this.name = 'ProtocolMessageValidationError';
    this.errors = errors;
  }
}

export class ProtocolMessageValidator {
  readonly #validate: ValidateFunction;

  constructor() {
    const ajv = new Ajv2020({ allErrors: true, strict: true });
    for (const schema of [
      identifiersSchema, envelopeSchema, securitySchema, errorsSchema,
      designObjectRefSchema, designDocumentSchema,
      handshakeSchema, heartbeatSchema, edaDocumentSchema, messageSchema,
    ]) {
      ajv.addSchema(schema);
    }
    const validate = ajv.getSchema(MESSAGE_SCHEMA_ID);
    if (validate === undefined) {
      throw new Error('AIA-JLCEDA root message schema did not compile');
    }
    this.#validate = validate;
  }

  validate(message: unknown): Readonly<Record<string, unknown>> {
    if (!this.#validate(message)) {
      throw new ProtocolMessageValidationError(
        this.#validate.errors === null || this.#validate.errors === undefined
          ? [] : [...this.#validate.errors],
      );
    }
    return Object.freeze(message as Record<string, unknown>);
  }
}
