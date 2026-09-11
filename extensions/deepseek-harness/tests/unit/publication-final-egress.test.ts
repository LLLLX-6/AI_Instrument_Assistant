import assert from "node:assert/strict";
import test from "node:test";

import { inspectDeterministicPublication } from "../../src/publication/index.ts";


test("deterministic publication uses the existing production final Egress guard", () => {
  const safe = inspectDeterministicPublication(
    "Instrument measurement: instrument frequency = 10020 Hz.",
    "phase8c2a-test",
  );
  assert.equal(safe.status, "SAFE");

  const unsafe = inspectDeterministicPublication(
    "Hidden host path: C:\\Users\\example\\secret.txt",
    "phase8c2a-test",
  );
  assert.equal(unsafe.status, "UNSAFE");
  if (unsafe.status === "UNSAFE") {
    assert.deepEqual(unsafe.violations.map((item) => item.category), ["LOCAL_PATH"]);
    assert.ok(unsafe.violations.every((item) => item.source === "FINAL_RESPONSE"));
  }
});
