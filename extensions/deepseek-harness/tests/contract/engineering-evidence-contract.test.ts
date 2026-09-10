import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

import {
  EvidenceContractBinding,
  EVIDENCE_CONTEXT_SCHEMA_ID,
} from "../../src/evidence/contract.ts";

const repositoryRoot = resolve(import.meta.dirname, "../../../..");
const fixtureRoot = resolve(repositoryRoot, "protocols/evidence/v1/fixtures");

function fixture(relativePath: string): { schema_ref: string; instance: unknown } {
  return JSON.parse(readFileSync(resolve(fixtureRoot, relativePath), "utf8")) as {
    schema_ref: string;
    instance: unknown;
  };
}

test("TypeScript binding accepts the canonical PWM fixture and preserves semantics", () => {
  const binding = EvidenceContractBinding.fromRepository(repositoryRoot);
  const canonical = fixture("valid/pwm-teaching-context.case.json").instance;
  const context = binding.parseTeachingContext(canonical);

  assert.equal(context.facts[0]?.source, "instrument");
  assert.equal(context.analyses[0]?.source, "software_analysis");
  assert.deepEqual(context.warnings, [
    "Instrument and software observations were sequential, not atomic.",
  ]);
  assert.equal(context.coherence?.instrument_vs_software, "sequential_same_session");
  assert.equal(context.artifact?.opaque, true);
  assert.equal(context.artifact?.uri, "memory://waveforms/pwm-out-1");
  assert.deepEqual(binding.toWire(context), canonical);
  assert.equal(binding.schemaId, EVIDENCE_CONTEXT_SCHEMA_ID);
});

test("TypeScript and Python share the same valid and invalid fixtures", () => {
  const binding = EvidenceContractBinding.fromRepository(repositoryRoot);
  for (const name of [
    "valid/pwm-teaching-context.case.json",
    "valid/unavailable-teaching-context.case.json",
    "valid/engineering-context-design-only.case.json",
  ]) {
    const item = fixture(name);
    assert.equal(binding.validate(item.schema_ref, item.instance).valid, true, name);
  }
  for (const name of [
    "invalid/fact-source-mismatch.case.json",
    "invalid/unavailable-with-value.case.json",
    "invalid/raw-artifact-samples.case.json",
    "invalid/unknown-field.case.json",
    "invalid/bad-identifiers-and-time.case.json",
  ]) {
    const item = fixture(name);
    assert.equal(binding.validate(item.schema_ref, item.instance).valid, false, name);
  }
});

test("canonical teaching schema reuses rather than duplicates Hardware ArtifactReference", () => {
  const schema = JSON.parse(
    readFileSync(resolve(repositoryRoot, "protocols/evidence/v1/teaching-evidence-context.schema.json"), "utf8"),
  ) as Record<string, unknown>;
  const text = JSON.stringify(schema);
  assert.match(text, /hardware-tool\.schema\.json#\/\$defs\/artifact/);
  const opaqueArtifact = ((schema.$defs as Record<string, unknown>).opaqueArtifact as Record<string, unknown>);
  const properties = opaqueArtifact.properties as Record<string, unknown>;
  assert.equal(Object.hasOwn(properties, "artifact_id"), false);
  assert.equal(Object.hasOwn(properties, "uri"), false);
});

test("unavailable observations and opaque artifacts do not gain data", () => {
  const binding = EvidenceContractBinding.fromRepository(repositoryRoot);
  const unavailable = binding.parseTeachingContext(
    fixture("valid/unavailable-teaching-context.case.json").instance,
  );
  assert.equal(unavailable.facts[0]?.quality, "unavailable");
  assert.equal(unavailable.facts[0]?.value, null);
  assert.throws(() =>
    binding.parseTeachingContext(fixture("invalid/raw-artifact-samples.case.json").instance),
  );
});
