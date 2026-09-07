import { Ajv2020 } from "ajv/dist/2020.js";
import addFormatsModule from "ajv-formats";

import hardwareSchema from "../../../../protocols/hardware/v1/hardware-tool.schema.json" with { type: "json" };
import envelopeSchema from "../../../../protocols/harness-hardware/v1/common/envelope.schema.json" with { type: "json" };
import identifiersSchema from "../../../../protocols/harness-hardware/v1/common/identifiers.schema.json" with { type: "json" };
import messageSchema from "../../../../protocols/harness-hardware/v1/message.schema.json" with { type: "json" };
import authSchema from "../../../../protocols/harness-hardware/v1/messages/auth.schema.json" with { type: "json" };
import sessionSchema from "../../../../protocols/harness-hardware/v1/messages/session.schema.json" with { type: "json" };

const ROOT_SCHEMA_ID = "https://aia.local/protocols/harness-hardware/v1/message.schema.json";

export class ProtocolMessageError extends Error {
  constructor(message = "Harness Hardware protocol message is invalid") {
    super(message);
    this.name = "ProtocolMessageError";
  }
}

export class HarnessHardwareProtocolValidator {
  readonly #validate;

  constructor() {
    const ajv = new Ajv2020({ allErrors: true, strict: true, strictTypes: false });
    const addFormats = addFormatsModule as unknown as (instance: Ajv2020) => Ajv2020;
    addFormats(ajv);
    for (const schema of [hardwareSchema, identifiersSchema, envelopeSchema, authSchema, sessionSchema, messageSchema]) {
      ajv.addSchema(schema);
    }
    const validate = ajv.getSchema(ROOT_SCHEMA_ID);
    if (!validate) throw new Error("Harness Hardware root schema did not compile");
    this.#validate = validate;
  }

  parse(raw: unknown, maximumBytes = 65_536): Record<string, unknown> {
    if (typeof raw !== "string") throw new ProtocolMessageError("Binary protocol messages are not supported");
    if (Buffer.byteLength(raw, "utf8") > maximumBytes) throw new ProtocolMessageError("Protocol message is too large");
    let value: unknown;
    try {
      value = JSON.parse(raw);
    } catch {
      throw new ProtocolMessageError();
    }
    if (!this.#validate(value)) throw new ProtocolMessageError();
    return value as Record<string, unknown>;
  }

  serialize(message: Record<string, unknown>, maximumBytes = 65_536): string {
    if (!this.#validate(message)) throw new ProtocolMessageError();
    const raw = JSON.stringify(message);
    if (Buffer.byteLength(raw, "utf8") > maximumBytes) throw new ProtocolMessageError("Protocol message is too large");
    return raw;
  }
}
