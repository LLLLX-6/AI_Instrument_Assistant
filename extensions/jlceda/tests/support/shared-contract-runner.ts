import { readFileSync, readdirSync } from "node:fs";
import { join, relative, resolve } from "node:path";

import type { ErrorObject } from "ajv";

import type { SchemaValidator } from "../../src/protocol/schema-validator.ts";


export interface FixtureCase {
  readonly path: string;
  readonly expectation: "valid" | "invalid";
  readonly description: string;
  readonly schemaRef: string;
  readonly instance: unknown;
}

export interface ContractFixtureFailure {
  readonly path: string;
  readonly expectedValid: boolean;
  readonly actualValid: boolean;
  readonly errors: readonly ErrorObject[];
}

export interface ContractRunSummary {
  readonly validFixtureCount: number;
  readonly invalidFixtureCount: number;
  readonly failures: readonly ContractFixtureFailure[];
}

export function loadFixtureCases(
  fixturesRoot: string,
  expectation?: "valid" | "invalid",
): readonly FixtureCase[] {
  const root = resolve(fixturesRoot);
  const expectations: readonly ("valid" | "invalid")[] = expectation === undefined
    ? ["valid", "invalid"]
    : [expectation];

  return expectations.flatMap((expectedResult) => {
    const expectationRoot = join(root, expectedResult);
    return readdirSync(expectationRoot, { recursive: true, withFileTypes: true })
      .filter((entry) => entry.isFile() && entry.name.endsWith(".case.json"))
      .map((entry) => resolve(entry.parentPath, entry.name))
      .sort()
      .map((path) => loadFixture(path, root, expectedResult));
  });
}

export function runSharedContractFixtures(
  validator: SchemaValidator,
  fixturesRoot: string,
): ContractRunSummary {
  const fixtures = loadFixtureCases(fixturesRoot);
  const failures: ContractFixtureFailure[] = [];

  for (const fixture of fixtures) {
    const result = validator.validate(fixture.schemaRef, fixture.instance);
    const expectedValid = fixture.expectation === "valid";
    if (result.isValid !== expectedValid) {
      failures.push({
        path: fixture.path,
        expectedValid,
        actualValid: result.isValid,
        errors: result.errors,
      });
    }
  }

  return {
    validFixtureCount: fixtures.filter((fixture) => fixture.expectation === "valid").length,
    invalidFixtureCount: fixtures.filter((fixture) => fixture.expectation === "invalid").length,
    failures,
  };
}

function loadFixture(
  path: string,
  fixturesRoot: string,
  expectation: "valid" | "invalid",
): FixtureCase {
  const pathWithinRoot = relative(fixturesRoot, path);
  if (pathWithinRoot.startsWith("..") || resolve(fixturesRoot, pathWithinRoot) !== path) {
    throw new Error(`Fixture is outside the shared fixture tree: ${path}`);
  }

  const document = JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>;
  if (typeof document.description !== "string" || document.description.length === 0) {
    throw new Error(`Fixture has no description: ${path}`);
  }
  if (typeof document.schema_ref !== "string" || document.schema_ref.length === 0) {
    throw new Error(`Fixture has no schema_ref: ${path}`);
  }
  if (!("instance" in document)) {
    throw new Error(`Fixture has no instance: ${path}`);
  }

  return {
    path,
    expectation,
    description: document.description,
    schemaRef: document.schema_ref,
    instance: document.instance,
  };
}
