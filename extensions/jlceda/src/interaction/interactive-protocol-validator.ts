import { Ajv2020 } from 'ajv/dist/2020.js';
import type { ValidateFunction } from 'ajv';

import identifiers from '../../../../protocols/interactive/v1/common/identifiers.schema.json' with { type: 'json' };
import envelope from '../../../../protocols/interactive/v1/common/envelope.schema.json' with { type: 'json' };
import status from '../../../../protocols/interactive/v1/models/status.schema.json' with { type: 'json' };
import challenge from '../../../../protocols/interactive/v1/models/challenge.schema.json' with { type: 'json' };
import snapshot from '../../../../protocols/interactive/v1/models/snapshot.schema.json' with { type: 'json' };
import hello from '../../../../protocols/interactive/v1/messages/hello.schema.json' with { type: 'json' };
import helloAck from '../../../../protocols/interactive/v1/messages/hello-ack.schema.json' with { type: 'json' };
import command from '../../../../protocols/interactive/v1/messages/command.schema.json' with { type: 'json' };
import answer from '../../../../protocols/interactive/v1/messages/challenge-answer.schema.json' with { type: 'json' };
import event from '../../../../protocols/interactive/v1/messages/event.schema.json' with { type: 'json' };
import message from '../../../../protocols/interactive/v1/message.schema.json' with { type: 'json' };

const MESSAGE_ID = 'https://aia.local/protocols/interactive/v1/message.schema.json';

export class InteractiveProtocolValidator {
  readonly #validate: ValidateFunction;
  constructor() {
    const ajv = new Ajv2020({ allErrors: true, strict: true, formats: { 'date-time': true, uuid: true } });
    for (const value of [identifiers, envelope, status, challenge, snapshot, hello, helloAck, command, answer, event, message]) {
      ajv.addSchema(value);
    }
    const validate = ajv.getSchema(MESSAGE_ID);
    if (validate === undefined) throw new Error('interactive_protocol_schema_unavailable');
    this.#validate = validate;
  }
  validate(value: unknown): Readonly<Record<string, unknown>> {
    if (!this.#validate(value)) throw new Error('interactive_protocol_message_invalid');
    return Object.freeze(value as Record<string, unknown>);
  }
}
