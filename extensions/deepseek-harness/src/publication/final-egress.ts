import { inspectEgressCandidate } from "../egress/index.ts";
import type { EgressInspectionResult } from "../egress/index.ts";

/** Phase 8C.2A final-output adapter; model/raw-output inspection remains deferred. */
export function inspectDeterministicPublication(
  text: string,
  correlationId: string,
): EgressInspectionResult {
  return inspectEgressCandidate({
    candidate: text,
    source: "FINAL_RESPONSE",
    correlationId,
    maximumCharacters: 16_384,
  });
}
