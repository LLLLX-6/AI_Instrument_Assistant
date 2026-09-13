from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import UUID, uuid4


INTERACTIVE_AUTH_PROTOCOL = "aia-interactive-auth/v1"


class InteractiveReplayError(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class InteractiveAuthChallenge:
    challenge_id: str
    server_nonce: str
    expires_at: str

    def to_wire(self) -> dict[str, str]:
        return {
            "protocol": INTERACTIVE_AUTH_PROTOCOL,
            "phase": "challenge",
            "challenge_id": self.challenge_id,
            "server_nonce": self.server_nonce,
            "expires_at": self.expires_at,
        }


class InteractiveHmacAuthenticator:
    """One-use transport authenticator, independent from AIA-JLCEDA v1."""

    def __init__(
        self,
        secret: bytes,
        *,
        clock: Callable[[], datetime] | None = None,
        ttl: timedelta = timedelta(seconds=30),
    ) -> None:
        if not isinstance(secret, bytes) or len(secret) < 32:
            raise ValueError("interactive secret must contain at least 32 bytes")
        self._secret = bytes(secret)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._ttl = ttl
        self._pending: dict[str, tuple[InteractiveAuthChallenge, datetime]] = {}
        self._consumed: set[str] = set()

    def issue_challenge(self) -> InteractiveAuthChallenge:
        now = self._clock()
        expires = now + self._ttl
        challenge = InteractiveAuthChallenge(
            str(uuid4()),
            _token(),
            expires.isoformat().replace("+00:00", "Z"),
        )
        self._pending[challenge.challenge_id] = (challenge, expires)
        return challenge

    def verify(
        self,
        challenge_id: str,
        client_instance_id: str,
        client_nonce: str,
        proof: str,
    ) -> str:
        try:
            UUID(client_instance_id)
        except (TypeError, ValueError) as error:
            raise PermissionError("interactive client identity is invalid") from error
        if challenge_id in self._consumed or challenge_id not in self._pending:
            raise InteractiveReplayError("interactive challenge is unavailable")
        challenge, expires = self._pending.pop(challenge_id)
        self._consumed.add(challenge_id)
        if self._clock() >= expires:
            raise PermissionError("interactive challenge expired")
        if not _bounded_token(client_nonce) or not _bounded_token(proof):
            raise PermissionError("interactive proof fields are invalid")
        canonical = "\n".join((
            "aia-interactive", "1.0", client_instance_id, challenge.challenge_id,
            client_nonce, challenge.server_nonce, challenge.expires_at,
        )).encode("utf-8")
        expected = _encoded(hmac.new(self._secret, canonical, hashlib.sha256).digest())
        if not hmac.compare_digest(expected, proof):
            raise PermissionError("interactive authentication failed")
        return client_instance_id


def _token() -> str:
    return _encoded(secrets.token_bytes(32))


def _encoded(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _bounded_token(value: object) -> bool:
    return isinstance(value, str) and 24 <= len(value) <= 128 and all(
        character.isalnum() or character in "_-" for character in value
    )
