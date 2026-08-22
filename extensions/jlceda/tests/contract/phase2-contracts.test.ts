import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { Ajv2020 } from "ajv/dist/2020.js";


interface FixtureCase {
  description: string;
  schema_ref: string;
  instance: unknown;
}

const repositoryRoot = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
  "..",
  "..",
);
const protocolRoot = join(repositoryRoot, "protocols", "jlceda", "v1");
const fixturesRoot = join(protocolRoot, "fixtures");
const schemaPaths = [
  join(protocolRoot, "common", "identifiers.schema.json"),
  join(protocolRoot, "common", "envelope.schema.json"),
  join(protocolRoot, "models", "design-object-ref.schema.json"),
  join(protocolRoot, "models", "design-document.schema.json"),
];

function readJson(path: string): Record<string, unknown> {
  return JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>;
}

function casePaths(root: string): string[] {
  return readdirSync(root, { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith(".case.json"))
    .map((entry) => resolve(entry.parentPath, entry.name))
    .sort();
}

function buildValidator(): Ajv2020 {
  const ajv = new Ajv2020({ allErrors: true, strict: true });
  for (const schemaPath of schemaPaths) {
    ajv.addSchema(readJson(schemaPath));
  }
  return ajv;
}

test("the four required Phase 2 schema files exist", () => {
  for (const schemaPath of schemaPaths) {
    assert.ok(existsSync(schemaPath), `Phase 2 schema is missing: ${schemaPath}`);
  }
});

test("valid shared fixtures are accepted", () => {
  const ajv = buildValidator();
  const paths = casePaths(join(fixturesRoot, "valid"));
  assert.ok(paths.length > 0, "No valid Phase 2 fixtures were found");

  for (const path of paths) {
    const fixture = readJson(path) as unknown as FixtureCase;
    const validate = ajv.getSchema(fixture.schema_ref);
    assert.ok(validate, `Unresolved fixture schema_ref: ${fixture.schema_ref}`);
    assert.equal(
      validate(fixture.instance),
      true,
      `${relative(fixturesRoot, path)}: ${fixture.description}\n${ajv.errorsText(validate.errors)}`,
    );
  }
});

test("invalid shared fixtures are rejected", () => {
  const ajv = buildValidator();
  const paths = casePaths(join(fixturesRoot, "invalid"));
  assert.ok(paths.length > 0, "No invalid Phase 2 fixtures were found");

  for (const path of paths) {
    const fixture = readJson(path) as unknown as FixtureCase;
    const validate = ajv.getSchema(fixture.schema_ref);
    assert.ok(validate, `Unresolved fixture schema_ref: ${fixture.schema_ref}`);
    assert.equal(
      validate(fixture.instance),
      false,
      `${relative(fixturesRoot, path)} should be rejected: ${fixture.description}`,
    );
  }
});

test("schema identifiers are unique and every schema compiles", () => {
  const schemas = schemaPaths.map(readJson);
  const identifiers = schemas.map((schema) => schema.$id);
  assert.equal(new Set(identifiers).size, identifiers.length);

  const ajv = buildValidator();
  for (const identifier of identifiers) {
    assert.equal(typeof identifier, "string");
    assert.ok(ajv.getSchema(identifier as string), `Schema did not compile: ${identifier}`);
  }
});
