import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

import { Phase8B3ValidationContractBinding } from "../../validation/phase8b3-contract.ts";

const repositoryRoot = resolve(import.meta.dirname, "../../../..");
const fixtureRoot = resolve(repositoryRoot, "validation/support/phase8b3/v1/fixtures");

function fixtures(kind: "valid" | "invalid") {
  return readdirSync(resolve(fixtureRoot, kind))
    .filter((name) => name.endsWith(".json"))
    .map((name) => JSON.parse(readFileSync(resolve(fixtureRoot, kind, name), "utf8")) as {
      schema_ref: string;
      instance: unknown;
    });
}

test("Phase 8B.3 TypeScript and Python use the same private validation fixtures", () => {
  const binding = Phase8B3ValidationContractBinding.fromRepository(repositoryRoot);
  const valid = fixtures("valid");
  const invalid = fixtures("invalid");
  assert.ok(valid.length >= 2);
  assert.ok(invalid.length >= 2);
  for (const item of valid) assert.equal(binding.validate(item.schema_ref, item.instance), true);
  for (const item of invalid) assert.equal(binding.validate(item.schema_ref, item.instance), false);
});

test("private request cannot carry pre-approved governance conclusions", () => {
  const binding = Phase8B3ValidationContractBinding.fromRepository(repositoryRoot);
  const request = fixtures("valid")[0]!.instance as Record<string, unknown>;
  assert.equal(binding.validate(
    "https://aia.local/validation/support/phase8b3/v1/request.schema.json",
    { ...request, scopeApproved: true },
  ), false);
});
