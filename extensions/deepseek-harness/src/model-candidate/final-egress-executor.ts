import { inspectDeterministicPublication } from "../publication/index.ts";

export function executeFinalEgress(request: Readonly<Record<string, unknown>>): Record<string, unknown> {
  const decision = inspectDeterministicPublication(String(request.text), String(request.correlation_id));
  return Object.freeze({
    schema_id: "aia-harness-publication-egress-receipt/v1",
    request_id: request.request_id,
    status: decision.status,
    violations: decision.status === "SAFE" ? [] : decision.violations.map((item) => item.category),
  });
}
