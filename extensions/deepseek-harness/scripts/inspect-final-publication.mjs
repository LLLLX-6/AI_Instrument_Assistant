const MAX_STDIN_BYTES = 20 * 1024;

function write(value) { process.stdout.write(JSON.stringify(value) + "\n"); }

try {
  let total = 0;
  const chunks = [];
  for await (const chunk of process.stdin) {
    total += chunk.length;
    if (total > MAX_STDIN_BYTES) throw new Error("REQUEST_TOO_LARGE");
    chunks.push(chunk);
  }
  const raw = Buffer.concat(chunks).toString("utf8");
  if (raw.split(/\r?\n/).filter(Boolean).length !== 1) throw new Error("ONE_LINE_REQUIRED");
  const contract = await import("../src/model-candidate/contract.ts");
  const request = contract.validateBridgeValue(contract.FINAL_EGRESS_REQUEST_SCHEMA_ID, JSON.parse(raw));
  const { executeFinalEgress } = await import("../src/model-candidate/final-egress-executor.ts");
  write(executeFinalEgress(request));
} catch {
  write({
    schema_id: "aia-harness-publication-egress-receipt/v1",
    request_id: "00000000-0000-4000-8000-000000000000",
    status: "UNSAFE",
    violations: ["OVERSIZED_OUTPUT"],
  });
}
