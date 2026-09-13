const AUTH_SCOPE = 'aia-interactive';

export function canonicalInteractiveProofPayload(fields: {
  readonly clientInstanceId: string;
  readonly challengeId: string;
  readonly clientNonce: string;
  readonly serverNonce: string;
  readonly expiresAt: string;
}): Uint8Array {
  return new TextEncoder().encode([
    AUTH_SCOPE, '1.0', fields.clientInstanceId, fields.challengeId,
    fields.clientNonce, fields.serverNonce, fields.expiresAt,
  ].join('\n'));
}

export async function computeInteractiveProof(
  secret: Uint8Array,
  fields: Parameters<typeof canonicalInteractiveProofPayload>[0],
): Promise<string> {
  if (secret.byteLength !== 32) throw new Error('interactive_credential_invalid');
  const key = await crypto.subtle.importKey(
    'raw', secret.slice().buffer as ArrayBuffer,
    { name: 'HMAC', hash: 'SHA-256' }, false, ['sign'],
  );
  const signature = await crypto.subtle.sign(
    'HMAC', key, canonicalInteractiveProofPayload(fields) as BufferSource,
  );
  return base64Url(new Uint8Array(signature));
}

export function randomInteractiveNonce(): string {
  return base64Url(crypto.getRandomValues(new Uint8Array(32)));
}

function base64Url(value: Uint8Array): string {
  let binary = '';
  for (const byte of value) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');
}
