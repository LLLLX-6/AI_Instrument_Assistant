const MAX_STDIN_BYTES = 96 * 1024;

function write(value) {
  process.stdout.write(JSON.stringify(value) + "\n");
}

let total = 0;
const chunks = [];
try {
  for await (const chunk of process.stdin) {
    total += chunk.length;
    if (total > MAX_STDIN_BYTES) throw new Error("REQUEST_TOO_LARGE");
    chunks.push(chunk);
  }
  const raw = Buffer.concat(chunks).toString("utf8");
  if (raw.split(/\r?\n/).filter(Boolean).length !== 1) throw new Error("ONE_LINE_REQUIRED");
  const contract = await import("../src/model-candidate/contract.ts");
  const request = contract.validateBridgeValue(contract.MODEL_REQUEST_SCHEMA_ID, JSON.parse(raw));
  const { runFrozenOneShot } = await import("../src/model-candidate/frozen-runtime.ts");
  write(await runFrozenOneShot(request));
} catch {
  write({
    schema_id: "aia-harness-publication-model-receipt/v1",
    request_id: "00000000-0000-4000-8000-000000000000",
    request_digest: `sha256:${"0".repeat(64)}`,
    status: "FAILED",
    executor_version: "aia-phase8c2b-executor/1",
    runtime_version: "0.1.3-alpha.1",
    provider_id: "deepseek-official",
    model_id: "deepseek-v4-flash",
    model_request_count: 0,
    raw_byte_count: 0,
    raw_digest: null,
    raw_precheck: "NOT_RUN",
    finish_category: "PROTOCOL_INVALID",
    duration_bucket: "LT_1S",
    failure_code: "MODEL_PROCESS_FAILED",
  });
}
