import {
  BoundedScenarioState,
  CompatibilityStop,
  runWithBoundedFailureBoundary,
} from "../../src/validation/runner-boundary.ts";

const mode = process.argv[2];
const state = new BoundedScenarioState();
const result = await runWithBoundedFailureBoundary({
  phase: "7C.4C",
  scenario: `child-${mode}`,
  state,
  execute() {
    state.recordToolSelection();
    if (mode === "known") throw new CompatibilityStop("COMPATIBILITY_STOP", "C:\\private\\runner.ts");
    throw new Error("raw-model-secret /home/operator/runner.mjs");
  },
  shutdown: async () => {},
});

process.stdout.write(`${JSON.stringify(result)}\n`);
process.exitCode = result.status === "STOPPED" ? 1 : 0;
