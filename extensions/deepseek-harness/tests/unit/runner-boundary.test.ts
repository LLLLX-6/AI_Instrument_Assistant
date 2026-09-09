import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { resolve } from "node:path";
import test from "node:test";

import { inspectEgressCandidate } from "../../src/egress/index.ts";
import {
  BoundedScenarioState,
  CompatibilityStop,
  runWithBoundedFailureBoundary,
} from "../../src/validation/runner-boundary.ts";

test("CompatibilityStop becomes a bounded result with no stack or message", async () => {
  const result = await runWithBoundedFailureBoundary({
    phase: "7C.4C",
    scenario: "known-stop",
    state: new BoundedScenarioState(),
    execute: () => { throw new CompatibilityStop("MULTIPLE_TOOL_SELECTION", "C:\\secret\\runner.ts"); },
    shutdown: async () => {},
  });
  const text = JSON.stringify(result);
  assert.equal(result.status, "STOPPED");
  assert.match(text, /MULTIPLE_TOOL_SELECTION/);
  assert.doesNotMatch(text, /stack|runner\.ts|secret/i);
});

test("unexpected Error becomes UNEXPECTED_RUNNER_FAILURE without raw exception", async () => {
  const result = await runWithBoundedFailureBoundary({
    phase: "7C.4C",
    scenario: "unexpected-stop",
    state: new BoundedScenarioState(),
    execute: () => { throw new Error("token=top-secret at /home/operator/private-runner.mjs"); },
    shutdown: async () => {},
  });
  const text = JSON.stringify(result);
  assert.match(text, /UNEXPECTED_RUNNER_FAILURE/);
  assert.doesNotMatch(text, /top-secret|operator|private-runner|stack/i);
});

test("bounded counts and execution uncertainty survive an assertion stop", async () => {
  const state = new BoundedScenarioState();
  const result = await runWithBoundedFailureBoundary({
    phase: "7C.4C",
    scenario: "count-first",
    state,
    execute: () => {
      state.recordToolSelection();
      state.recordIpcDispatch("MAY_HAVE_OCCURRED");
      throw new CompatibilityStop("SEMANTIC_TOOL_MISMATCH");
    },
    shutdown: async () => {},
  });
  assert.equal(result.status, "STOPPED");
  if (result.status !== "STOPPED") return;
  assert.deepEqual(result.counts, {
    semanticToolCallCount: 1,
    ipcDispatchCount: 1,
    physicalExecutionCount: 0,
    modelRetryCount: 0,
    toolRetryCount: 0,
  });
  assert.equal(result.ipcDispatchOccurred, true);
  assert.equal(result.hardwareExecution, "MAY_HAVE_OCCURRED");
});

test("confirmed physical execution count survives a later stop", async () => {
  const state = new BoundedScenarioState();
  const result = await runWithBoundedFailureBoundary({
    phase: "7C.4C",
    scenario: "confirmed-execution",
    state,
    execute: () => {
      state.recordIpcDispatch();
      state.recordPhysicalExecution();
      throw new CompatibilityStop("GROUNDING_VALIDATION_FAILED");
    },
    shutdown: async () => {},
  });
  assert.equal(result.counts.ipcDispatchCount, 1);
  assert.equal(result.counts.physicalExecutionCount, 1);
  assert.equal(result.hardwareExecution, "CONFIRMED");
});

test("Windows and POSIX paths in known diagnostics are never persisted", async () => {
  for (const diagnostic of ["C:\\Users\\operator\\runner.ts", "/home/operator/runner.mjs"]) {
    const result = await runWithBoundedFailureBoundary({
      phase: "7C.4C",
      scenario: "path-containment",
      state: new BoundedScenarioState(),
      execute: () => { throw new CompatibilityStop("COMPATIBILITY_STOP", diagnostic); },
      shutdown: async () => {},
    });
    assert.doesNotMatch(JSON.stringify(result), /operator|runner\.(?:ts|mjs)|[A-Za-z]:\\|\/home\//i);
  }
});

test("raw unsafe model content is not accepted by failure record assembly", async () => {
  const unsafe = "raw model says :WAV:DATA? and C:\\Users\\operator\\secret.txt";
  const result = await runWithBoundedFailureBoundary({
    phase: "7C.4C",
    scenario: "unsafe-model-content",
    state: new BoundedScenarioState(),
    execute: () => { throw new Error(unsafe); },
    shutdown: async () => {},
  });
  assert.doesNotMatch(JSON.stringify(result), /WAV|operator|secret\.txt/i);
});

test("secret material in an exception is not persisted", async () => {
  const secret = "sk-test-do-not-persist";
  const result = await runWithBoundedFailureBoundary({
    phase: "7C.4C",
    scenario: "secret-containment",
    state: new BoundedScenarioState(),
    execute: () => { throw new Error(secret); },
    shutdown: async () => {},
  });
  assert.doesNotMatch(JSON.stringify(result), /sk-test|do-not-persist/i);
});

test("model and Tool retry facts are bounded counters rather than raw events", async () => {
  const state = new BoundedScenarioState();
  const result = await runWithBoundedFailureBoundary({
    phase: "7C.4C",
    scenario: "bounded-retry-facts",
    state,
    execute: () => {
      state.recordModelRetry();
      state.recordToolRetry();
      throw new CompatibilityStop("COMPATIBILITY_STOP");
    },
    shutdown: async () => {},
  });
  assert.equal(result.modelRetryOccurred, true);
  assert.equal(result.toolRetryOccurred, true);
  assert.equal(result.counts.modelRetryCount, 1);
  assert.equal(result.counts.toolRetryCount, 1);
});

test("completed runner also shuts down and emits only bounded metadata", async () => {
  let shutdowns = 0;
  const result = await runWithBoundedFailureBoundary({
    phase: "7C.4C",
    scenario: "completed",
    state: new BoundedScenarioState(),
    execute: async () => {},
    shutdown: async () => { shutdowns += 1; },
  });
  assert.equal(result.status, "COMPLETED");
  assert.equal(result.failureCategory, null);
  assert.equal(shutdowns, 1);
});

test("known and unexpected failures never retry model, Tool, or measurement", async () => {
  for (const error of [new CompatibilityStop("COMPATIBILITY_STOP"), new Error("unexpected")]) {
    const state = new BoundedScenarioState();
    let executions = 0;
    const result = await runWithBoundedFailureBoundary({
      phase: "7C.4C",
      scenario: "no-retry",
      state,
      execute: () => { executions += 1; throw error; },
      shutdown: async () => {},
    });
    assert.equal(executions, 1);
    assert.equal(result.modelRetryOccurred, false);
    assert.equal(result.toolRetryOccurred, false);
    assert.equal(result.counts.physicalExecutionCount, 0);
  }
});

test("Backend shutdown occurs after failure", async () => {
  let shutdowns = 0;
  const result = await runWithBoundedFailureBoundary({
    phase: "7C.4C",
    scenario: "shutdown",
    state: new BoundedScenarioState(),
    execute: () => { throw new Error("boom"); },
    shutdown: async () => { shutdowns += 1; },
  });
  assert.equal(shutdowns, 1);
  assert.equal(result.backendShutdown, "COMPLETED");
});

test("shutdown failure is contained and cannot replace the original bounded category", async () => {
  const result = await runWithBoundedFailureBoundary({
    phase: "7C.4C",
    scenario: "shutdown-failure",
    state: new BoundedScenarioState(),
    execute: () => { throw new CompatibilityStop("COMPATIBILITY_STOP"); },
    shutdown: async () => { throw new Error("C:\\private\\shutdown.ts"); },
  });
  assert.equal(result.failureCategory, "COMPATIBILITY_STOP");
  assert.equal(result.backendShutdown, "FAILED");
  assert.doesNotMatch(JSON.stringify(result), /private|shutdown\.ts|stack/i);
});

test("bounded stop record passes the existing Egress Guard", async () => {
  const result = await runWithBoundedFailureBoundary({
    phase: "7C.4C",
    scenario: "egress-safe-stop",
    state: new BoundedScenarioState(),
    execute: () => { throw new CompatibilityStop("POLICY_MISMATCH"); },
    shutdown: async () => {},
  });
  const inspection = inspectEgressCandidate({
    candidate: JSON.stringify(result),
    source: "FINAL_RESPONSE",
    correlationId: "runner-boundary-test",
    knownSensitiveValues: [],
  });
  assert.equal(inspection.status, "SAFE");
});

for (const mode of ["known", "unexpected"] as const) {
  test(`subprocess ${mode} stop emits one bounded JSON record and no stderr stack`, () => {
    const child = resolve(new URL("../support/runner-boundary-child.mjs", import.meta.url).pathname.replace(/^\/(.:)/, "$1"));
    const result = spawnSync(process.execPath, [child, mode], { encoding: "utf8" });
    assert.equal(result.status, 1);
    assert.equal(result.stderr, "");
    const record = JSON.parse(result.stdout) as Record<string, unknown>;
    assert.equal(record.status, "STOPPED");
    const combined = result.stdout + result.stderr;
    assert.doesNotMatch(combined, /at file:|at async|node:internal|[A-Za-z]:\\private|\/home\/operator|raw-model-secret/i);
  });
}
