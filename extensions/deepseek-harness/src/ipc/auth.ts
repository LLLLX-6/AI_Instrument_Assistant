import { createHmac, timingSafeEqual } from "node:crypto";

export interface ProofFields {
  readonly clientInstanceId: string;
  readonly clientNonce: string;
  readonly serverNonce: string;
  readonly challengeId: string;
  readonly expiresAt: string;
}

export function computeProof(secret: Uint8Array, fields: ProofFields): string {
  if (secret.byteLength !== 32) throw new Error("Harness Hardware PSK must contain exactly 256 bits");
  const payload = [
    "aia-harness-hardware",
    "1",
    fields.clientInstanceId,
    fields.clientNonce,
    fields.serverNonce,
    fields.challengeId,
    fields.expiresAt,
  ].join("\n");
  return createHmac("sha256", secret).update(payload, "utf8").digest("base64url");
}

export function constantTimeEqual(left: string, right: string): boolean {
  const leftBytes = Buffer.from(left, "utf8");
  const rightBytes = Buffer.from(right, "utf8");
  return leftBytes.length === rightBytes.length && timingSafeEqual(leftBytes, rightBytes);
}
