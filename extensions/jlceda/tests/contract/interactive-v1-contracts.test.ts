import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { Ajv2020 } from "ajv/dist/2020.js";

interface FixtureCase { readonly schema_ref: string; readonly instance: unknown }

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../../..");
const protocol = join(root, "protocols", "interactive", "v1");
const fixtures = join(protocol, "fixtures");
const paths = (base: string, suffix: string): string[] =>
  readdirSync(base, { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith(suffix))
    .map((entry) => resolve(entry.parentPath, entry.name)).sort();
const json = (path: string): Record<string, unknown> =>
  JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>;

function validator(): Ajv2020 {
  const ajv = new Ajv2020({ allErrors: true, strict: true, formats: { "date-time": true, uuid: true } });
  for (const path of paths(protocol, ".schema.json")) ajv.addSchema(json(path));
  return ajv;
}

for (const kind of ["valid", "invalid"] as const) {
  test(`shared interactive ${kind} fixtures have the same TypeScript verdict`, () => {
    const ajv = validator();
    const cases = paths(join(fixtures, kind), ".case.json");
    assert.ok(cases.length >= 5);
    for (const path of cases) {
      const fixture = json(path) as unknown as FixtureCase;
      const validate = ajv.getSchema(fixture.schema_ref);
      assert.ok(validate, fixture.schema_ref);
      assert.equal(validate(fixture.instance), kind === "valid", path);
    }
  });
}
