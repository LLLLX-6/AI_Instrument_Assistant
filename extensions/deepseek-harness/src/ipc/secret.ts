import { readFile } from "node:fs/promises";

export async function loadHarnessHardwareSecret(path: string): Promise<Uint8Array> {
  let encoded: string;
  try {
    encoded = (await readFile(path, "ascii")).trim();
  } catch {
    throw new Error("Harness Hardware secret is unavailable");
  }
  if (!/^[A-Za-z0-9_-]{43}$/.test(encoded)) {
    throw new Error("Harness Hardware secret is invalid");
  }
  const decoded = Buffer.from(encoded, "base64url");
  if (decoded.byteLength !== 32 || decoded.toString("base64url") !== encoded) {
    throw new Error("Harness Hardware secret is invalid");
  }
  return decoded;
}
