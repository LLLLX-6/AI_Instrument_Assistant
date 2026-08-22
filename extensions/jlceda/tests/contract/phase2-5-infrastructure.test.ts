import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  SchemaFileNotFoundError,
  SchemaLoader,
  SchemaReferenceError,
} from "../../src/protocol/schema-loader.ts";
import {
  SchemaNotFoundError,
  SchemaValidator,
} from "../../src/protocol/schema-validator.ts";
import {
  loadFixtureCases,
  runSharedContractFixtures,
} from "../support/shared-contract-runner.ts";


const repositoryRoot = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
  "..",
  "..",
);
const protocolRoot = join(repositoryRoot, "protocols", "jlceda", "v1");
const fixturesRoot = join(protocolRoot, "fixtures");

function buildValidator(): SchemaValidator {
  return new SchemaValidator(SchemaLoader.loadDirectory(protocolRoot));
}

test("a missing schema file is reported", () => {
  assert.throws(
    () => SchemaLoader.loadFiles([join(protocolRoot, "missing.schema.json")]),
    SchemaFileNotFoundError,
  );
});

test("an unknown schema reference is reported", () => {
  const validator = buildValidator();

  assert.throws(
    () => validator.validate("aia://protocol/jlceda/v1/missing", {}),
    SchemaNotFoundError,
  );
});

test("a broken schema reference is reported while building the validator", (context) => {
  const temporaryDirectory = mkdtempSync(join(tmpdir(), "aia-schema-"));
  context.after(() => rmSync(temporaryDirectory, { recursive: true, force: true }));
  writeFileSync(
    join(temporaryDirectory, "broken.schema.json"),
    JSON.stringify({
      $schema: "https://json-schema.org/draft/2020-12/schema",
      $id: "aia://test/broken",
      $ref: "aia://test/missing",
    }),
    "utf8",
  );

  assert.throws(
    () => new SchemaValidator(SchemaLoader.loadDirectory(temporaryDirectory)),
    SchemaReferenceError,
  );
});

test("the shared runner accepts every valid fixture and rejects every invalid fixture", () => {
  const summary = runSharedContractFixtures(buildValidator(), fixturesRoot);

  assert.ok(summary.validFixtureCount > 0);
  assert.ok(summary.invalidFixtureCount > 0);
  assert.deepEqual(summary.failures, []);
});

test("an unknown instance field is rejected", () => {
  const fixture = loadFixtureCases(fixturesRoot, "valid").find(
    (candidate) => candidate.path.endsWith(join("design-object-ref", "document.case.json")),
  );
  assert.ok(fixture, "The shared DesignObjectRef document fixture was not found");
  assert.equal(typeof fixture.instance, "object");
  assert.notEqual(fixture.instance, null);
  const instance = {
    ...(fixture.instance as Record<string, unknown>),
    phase_2_5_unknown_field: true,
  };

  assert.equal(buildValidator().validate(fixture.schemaRef, instance).isValid, false);
});

test("the TypeScript runner reads only the protocol shared fixture tree", () => {
  const fixtures = loadFixtureCases(fixturesRoot);
  const normalizedRoot = resolve(fixturesRoot);

  assert.ok(fixtures.length > 0);
  assert.ok(fixtures.every((fixture) => resolve(fixture.path).startsWith(normalizedRoot)));
});
