from __future__ import annotations

import base64
import hashlib
import hmac


def canonical_proof_payload(
    *,
    client_instance_id: str,
    challenge_id: str,
    client_nonce: str,
    server_nonce: str,
    expires_at: str,
) -> bytes:
    """Return the exact UTF-8 byte sequence authenticated by both peers."""

    return "\n".join(
        (
            "aia-jlceda",
            "1.0",
            client_instance_id,
            challenge_id,
            client_nonce,
            server_nonce,
            expires_at,
        )
    ).encode("utf-8")


def compute_proof(
    secret: bytes,
    *,
    client_instance_id: str,
    challenge_id: str,
    client_nonce: str,
    server_nonce: str,
    expires_at: str,
) -> str:
    if len(secret) < 32:
        raise ValueError("The production pre-shared secret must contain at least 32 bytes")
    digest = hmac.new(
        secret,
        canonical_proof_payload(
            client_instance_id=client_instance_id,
            challenge_id=challenge_id,
            client_nonce=client_nonce,
            server_nonce=server_nonce,
            expires_at=expires_at,
        ),
        hashlib.sha256,
    ).digest()
    return _base64url(digest)


def verify_proof(received: str, expected: str) -> bool:
    """Compare encoded proofs without data-dependent early exit."""

    return hmac.compare_digest(received.encode("ascii"), expected.encode("ascii"))


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")
