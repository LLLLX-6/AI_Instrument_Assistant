import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { Ajv2020 } from "ajv/dist/2020.js";
import addFormatsModule from "ajv-formats";

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "..");
const protocolRoot = join(repositoryRoot, "protocols", "harness-publication-bridge", "v1");

test("TypeScript validates the shared private bridge fixtures", () => {
  const ajv = new Ajv2020({ allErrors: true, strict: true });
  const addFormats = addFormatsModule as unknown as (instance: Ajv2020) => Ajv2020;
  addFormats(ajv);
  for (const name of readdirSync(protocolRoot).filter((item) => item.endsWith(".schema.json"))) {
    ajv.addSchema(JSON.parse(readFileSync(join(protocolRoot, name), "utf8")));
  }
  for (const [kind, expected] of [["valid", true], ["invalid", false]] as const) {
    for (const name of readdirSync(join(protocolRoot, "fixtures", kind))) {
      const fixture = JSON.parse(readFileSync(join(protocolRoot, "fixtures", kind, name), "utf8"));
      const validate = ajv.getSchema(fixture.schema_ref);
      assert.ok(validate);
      assert.equal(validate(fixture.instance), expected, name);
    }
  }
});
