import { resolve } from "node:path";
import { createInterface } from "node:readline";

import { HarnessHardwareIpcClient } from "../src/ipc/client.ts";
import { loadHarnessHardwareSecret } from "../src/ipc/secret.ts";
import { executeGovernedHardwareValidation } from "../validation/phase8b3-executor.ts";

const repositoryRoot = resolve(new URL("../../..", import.meta.url).pathname.replace(/^\/(.:)/, "$1"));

const lines = createInterface({ input: process.stdin, crlfDelay: Infinity });
const input = lines[Symbol.asyncIterator]();

try {
  const raw = await readBoundedLine(input);
  const request = JSON.parse(raw);
  const receipt = await executeGovernedHardwareValidation(request, {
    repositoryRoot,
    createClient(config) {
      let client;
      return {
        start() {},
        async dispose() {
          await client?.dispose();
        },
        async invoke(operation, args, signal) {
          if (client === undefined) {
            process.stdout.write(`${JSON.stringify({
              contract: "aia-phase8b3-validation",
              contract_version: "1.0",
              kind: "backend_start_required",
            })}\n`);
            const acknowledgement = JSON.parse(await readBoundedLine(input));
            if (!isBackendReady(acknowledgement)) {
              throw new Error("bounded backend readiness acknowledgement was invalid");
            }
            const secretFile = resolve(repositoryRoot, config.secretFile);
            client = new HarnessHardwareIpcClient({
              endpoint: config.endpoint,
              secretFile,
              loadSecret: () => loadHarnessHardwareSecret(secretFile),
              connectTimeoutMs: config.connectTimeoutMs,
              authTimeoutMs: config.authTimeoutMs,
              requestTimeoutMs: config.requestTimeoutMs,
            });
            client.start();
          }
          return client.invoke(operation, args, signal);
        },
      };
    },
  });
  process.stdout.write(`${JSON.stringify(receipt)}\n`);
} catch {
  process.stdout.write(`${JSON.stringify({
    contract: "aia-phase8b3-validation",
    contract_version: "1.0",
    kind: "governed_hardware_receipt",
    run_id: "00000000-0000-4000-8000-000000000000",
    workflow_id: "invalid-request",
    request_correlation_id: "invalid-request",
    status: "FAILED",
    operations: [],
    pwm_teaching_evidence: null,
    failure_code: "bounded_runner_failure",
    limitations: ["The validation runner failed within its bounded outer boundary."],
  })}\n`);
  process.exitCode = 1;
} finally {
  lines.close();
}

async function readBoundedLine(iterator) {
  const item = await iterator.next();
  if (item.done || Buffer.byteLength(item.value, "utf8") > 65_536) {
    throw new RangeError("bounded input line missing or too large");
  }
  return item.value;
}

function isBackendReady(value) {
  return value !== null
    && typeof value === "object"
    && Object.keys(value).length === 3
    && value.contract === "aia-phase8b3-validation"
    && value.contract_version === "1.0"
    && value.kind === "backend_ready";
}
