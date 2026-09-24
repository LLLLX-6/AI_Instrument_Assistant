import highlight0Schema from '../../../../protocols/jlceda/v1/models/highlight-command.schema.json' with { type: 'json' };
import highlight1Schema from '../../../../protocols/jlceda/v1/models/highlight-result.schema.json' with { type: 'json' };
import edaHighlightSchema from '../../../../protocols/jlceda/v1/messages/eda-highlight.schema.json' with { type: 'json' };
import { Ajv2020 } from 'ajv/dist/2020.js';
import type { ErrorObject, ValidateFunction } from 'ajv';

import envelopeSchema from '../../../../protocols/jlceda/v1/common/envelope.schema.json' with { type: 'json' };
import identifiersSchema from '../../../../protocols/jlceda/v1/common/identifiers.schema.json' with { type: 'json' };
import securitySchema from '../../../../protocols/jlceda/v1/common/security.schema.json' with { type: 'json' };
import errorsSchema from '../../../../protocols/jlceda/v1/common/errors.schema.json' with { type: 'json' };
import designObjectRefSchema from '../../../../protocols/jlceda/v1/models/design-object-ref.schema.json' with { type: 'json' };
import designDocumentSchema from '../../../../protocols/jlceda/v1/models/design-document.schema.json' with { type: 'json' };
import circuitEndpointSchema from '../../../../protocols/jlceda/v1/models/circuit-endpoint.schema.json' with { type: 'json' };
import signalExpectationSchema from '../../../../protocols/jlceda/v1/models/signal-expectation.schema.json' with { type: 'json' };
import circuitNetSchema from '../../../../protocols/jlceda/v1/models/circuit-net.schema.json' with { type: 'json' };
import designSelectionSchema from '../../../../protocols/jlceda/v1/models/design-selection.schema.json' with { type: 'json' };
import selectionContextSchema from '../../../../protocols/jlceda/v1/models/selection-context.schema.json' with { type: 'json' };
import designNetSchema from '../../../../protocols/jlceda/v1/models/design-net.schema.json' with { type: 'json' };
import circuitPinSchema from '../../../../protocols/jlceda/v1/models/circuit-pin.schema.json' with { type: 'json' };
import circuitComponentSchema from '../../../../protocols/jlceda/v1/models/circuit-component.schema.json' with { type: 'json' };
import designObservationSchema from '../../../../protocols/jlceda/v1/models/design-observation.schema.json' with { type: 'json' };
import messageSchema from '../../../../protocols/jlceda/v1/message.schema.json' with { type: 'json' };
import edaDocumentSchema from '../../../../protocols/jlceda/v1/messages/eda-document.schema.json' with { type: 'json' };
import edaSelectionSchema from '../../../../protocols/jlceda/v1/messages/eda-selection.schema.json' with { type: 'json' };
import edaDesignSchema from '../../../../protocols/jlceda/v1/messages/eda-design.schema.json' with { type: 'json' };
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
      designObjectRefSchema, designDocumentSchema, circuitEndpointSchema,
      signalExpectationSchema, circuitNetSchema, designSelectionSchema,
      selectionContextSchema,
      designNetSchema, circuitPinSchema, circuitComponentSchema, designObservationSchema,
      handshakeSchema, heartbeatSchema, edaDocumentSchema, edaSelectionSchema, edaDesignSchema,
      highlight0Schema, highlight1Schema, edaHighlightSchema, messageSchema,
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
