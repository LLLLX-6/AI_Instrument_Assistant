from __future__ import annotations

import base64
import hashlib
import hmac
import secrets


def canonical_proof_payload(
    *,
    client_instance_id: str,
    client_nonce: str,
    server_nonce: str,
    challenge_id: str,
    expires_at: str,
) -> bytes:
    return "\n".join(
        (
            "aia-harness-hardware",
            "1",
            client_instance_id,
            client_nonce,
            server_nonce,
            challenge_id,
            expires_at,
        )
    ).encode("utf-8")


def compute_proof(
    secret: bytes,
    *,
    client_instance_id: str,
    client_nonce: str,
    server_nonce: str,
    challenge_id: str,
    expires_at: str,
) -> str:
    if len(secret) != 32:
        raise ValueError("Harness Hardware PSK must contain exactly 256 bits")
    digest = hmac.new(
        secret,
        canonical_proof_payload(
            client_instance_id=client_instance_id,
            client_nonce=client_nonce,
            server_nonce=server_nonce,
            challenge_id=challenge_id,
            expires_at=expires_at,
        ),
        hashlib.sha256,
    ).digest()
    return _base64url(digest)


def verify_proof(received: str, expected: str) -> bool:
    try:
        received_bytes = received.encode("ascii")
        expected_bytes = expected.encode("ascii")
    except UnicodeEncodeError:
        return False
    return hmac.compare_digest(received_bytes, expected_bytes)


def new_nonce() -> str:
    return _base64url(secrets.token_bytes(32))


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")
