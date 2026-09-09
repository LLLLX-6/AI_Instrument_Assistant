import {
  BoundedScenarioState,
  runWithBoundedFailureBoundary,
} from "../src/validation/runner-boundary.ts";

const boundaryResult = await runWithBoundedFailureBoundary({
  phase: "7C.4C",
  scenario: "real-agent-module-load",
  state: new BoundedScenarioState(),
  execute: () => import("./check-real-agent-runtime.mjs").then(() => undefined),
  shutdown: async () => {},
});

if (boundaryResult.status === "STOPPED") {
  process.stdout.write(`${JSON.stringify(boundaryResult)}\n`);
  process.exitCode = 1;
}
