import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { Ajv2020 } from "ajv/dist/2020.js";

interface FixtureCase {
  readonly description: string;
  readonly schema_ref: string;
  readonly instance: unknown;
}

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "..");
const protocolRoot = join(repositoryRoot, "protocols", "teaching-claims", "v1");

function json(path: string): Record<string, unknown> {
  return JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>;
}

function fixturePaths(kind: "valid" | "invalid"): string[] {
  const root = join(protocolRoot, "fixtures", kind);
  return readdirSync(root, { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith(".case.json"))
    .map((entry) => join(root, entry.name))
    .sort();
}

test("Python and TypeScript share the teaching candidate fixtures", () => {
  const schema = json(join(protocolRoot, "structured-claim-candidate-set.schema.json"));
  const ajv = new Ajv2020({ allErrors: true, strict: true });
  ajv.addSchema(schema);
  for (const [kind, expected] of [["valid", true], ["invalid", false]] as const) {
    for (const path of fixturePaths(kind)) {
      const fixture = json(path) as unknown as FixtureCase;
      const validate = ajv.getSchema(fixture.schema_ref);
      assert.ok(validate, fixture.schema_ref);
      assert.equal(validate(fixture.instance), expected, fixture.description);
    }
  }
});
