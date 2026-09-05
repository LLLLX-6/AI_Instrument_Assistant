from __future__ import annotations

import base64
import secrets
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import Callable, Mapping
from uuid import uuid4

from ai_instrument_assistant.protocol.schema_validator import ValidatedInstance

from .auth import compute_proof, verify_proof
from .registries import ConnectionRegistry, SessionRecord, SessionRegistry


UTC = timezone.utc
MESSAGE_SCHEMA_REF = "aia://protocol/jlceda/v1/message"


@dataclass(slots=True)
class ChallengeRecord:
    challenge_id: str
    connection_id: str
    challenge_message_id: str
    client_instance_id: str
    client_nonce: str
    server_nonce: str
    expires_at: datetime


class ProtocolStateMachine:
    """Cross-message authentication and session rules for validated v1 messages."""

    def __init__(
        self,
        *,
        secret: bytes,
        clock: Callable[[], datetime] | None = None,
        challenge_ttl: timedelta = timedelta(seconds=10),
        heartbeat_interval: timedelta = timedelta(seconds=5),
        heartbeat_timeout: timedelta = timedelta(seconds=15),
    ) -> None:
        if len(secret) < 32:
            raise ValueError("The production pre-shared secret must contain at least 32 bytes")
        if heartbeat_timeout <= heartbeat_interval:
            raise ValueError("Heartbeat timeout must exceed heartbeat interval")
        self._secret = bytes(secret)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._challenge_ttl = challenge_ttl
        self._heartbeat_interval = heartbeat_interval
        self._heartbeat_timeout = heartbeat_timeout
        self._challenges: dict[str, ChallengeRecord] = {}
        self._consumed_challenges: set[str] = set()
        self._consumed_challenge_order: deque[str] = deque()
        self.connections = ConnectionRegistry()
        self.sessions = SessionRegistry()

    def connect(self, connection_id: str, remote_host: str) -> None:
        self.connections.add(connection_id, remote_host)

    def disconnect(self, connection_id: str) -> None:
        self.sessions.remove_for_connection(connection_id)
        for challenge_id in tuple(self._challenges):
            if self._challenges[challenge_id].connection_id == connection_id:
                self._consume_challenge(challenge_id)
                del self._challenges[challenge_id]
        self.connections.remove(connection_id)

    def handle(
        self,
        connection_id: str,
        validated: ValidatedInstance,
    ) -> dict[str, object]:
        if validated.schema_ref != MESSAGE_SCHEMA_REF:
            raise TypeError("State machine accepts only root-message validated instances")
        self.connections.require(connection_id)
        message = _mutable_message(validated.instance)
        kind = message["kind"]
        if kind == "hello" and message["phase"] == "init":
            return self._handle_init(connection_id, message)
        if kind == "hello" and message["phase"] == "prove":
            return self._handle_prove(connection_id, message)
        if kind == "ping":
            return self._handle_ping(connection_id, message)
        if kind == "pong":
            record = self.sessions.require(str(message["session_id"]), connection_id)
            record.last_seen_at = self._now()
            return {}
        raise PermissionError("Message direction or state is not allowed on the server")

    def heartbeat_timeouts(self) -> list[str]:
        expired = self.sessions.expired_connections(
            self._now(), self._heartbeat_timeout.total_seconds(),
        )
        for connection_id in expired:
            self.sessions.remove_for_connection(connection_id)
        return expired

    def _handle_init(
        self,
        connection_id: str,
        message: Mapping[str, object],
    ) -> dict[str, object]:
        for existing_id in tuple(self._challenges):
            if self._challenges[existing_id].connection_id == connection_id:
                del self._challenges[existing_id]
                self._consume_challenge(existing_id)
        challenge_id = str(uuid4())
        expires_at = self._now() + self._challenge_ttl
        response = self._response_base(message) | {
            "kind": "hello_ack",
            "phase": "challenge",
            "reply_to_message_id": message["message_id"],
            "challenge_id": challenge_id,
            "client_nonce": message["client_nonce"],
            "server_nonce": _random_value(),
            "expires_at": _timestamp(expires_at),
        }
        self._challenges[challenge_id] = ChallengeRecord(
            challenge_id=challenge_id,
            connection_id=connection_id,
            challenge_message_id=str(response["message_id"]),
            client_instance_id=str(message["client_instance_id"]),
            client_nonce=str(message["client_nonce"]),
            server_nonce=str(response["server_nonce"]),
            expires_at=expires_at,
        )
        return response

    def _handle_prove(
        self,
        connection_id: str,
        message: Mapping[str, object],
    ) -> dict[str, object]:
        challenge_id = str(message["challenge_id"])
        challenge = self._challenges.pop(challenge_id, None)
        if challenge is None:
            reason = "replay_detected" if challenge_id in self._consumed_challenges else "protocol_error"
            return self._rejected(message, reason)
        self._consume_challenge(challenge_id)
        if challenge.connection_id != connection_id or str(message["reply_to_message_id"]) != challenge.challenge_message_id:
            return self._rejected(message, "protocol_error")
        if self._now() > challenge.expires_at:
            return self._rejected(message, "challenge_expired")
        expected = compute_proof(
            self._secret,
            client_instance_id=challenge.client_instance_id,
            challenge_id=challenge.challenge_id,
            client_nonce=challenge.client_nonce,
            server_nonce=challenge.server_nonce,
            expires_at=_timestamp(challenge.expires_at),
        )
        if not verify_proof(str(message["proof"]), expected):
            return self._rejected(message, "authentication_failed")

        session_id = str(uuid4())
        self.sessions.add(SessionRecord(session_id, connection_id, self._now()))
        return self._response_base(message) | {
            "kind": "hello_ack",
            "phase": "accepted",
            "reply_to_message_id": message["message_id"],
            "session_id": session_id,
            "heartbeat_interval_ms": int(self._heartbeat_interval.total_seconds() * 1000),
            "heartbeat_timeout_ms": int(self._heartbeat_timeout.total_seconds() * 1000),
        }

    def _handle_ping(
        self,
        connection_id: str,
        message: Mapping[str, object],
    ) -> dict[str, object]:
        record = self.sessions.require(str(message["session_id"]), connection_id)
        record.last_seen_at = self._now()
        return self._response_base(message) | {
            "session_id": record.session_id,
            "kind": "pong",
            "reply_to_message_id": message["message_id"],
            "nonce": message["nonce"],
        }

    def _rejected(self, request: Mapping[str, object], reason: str) -> dict[str, object]:
        return self._response_base(request) | {
            "kind": "hello_ack",
            "phase": "rejected",
            "reply_to_message_id": request["message_id"],
            "reason_code": reason,
        }

    def _response_base(self, request: Mapping[str, object]) -> dict[str, object]:
        return {
            "protocol": "aia-jlceda",
            "protocol_version": "1.0",
            "message_id": str(uuid4()),
            "sent_at": _timestamp(self._now()),
            "trace_id": request["trace_id"],
        }

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("Protocol clock must return an aware UTC datetime")
        return value.astimezone(UTC)

    def _consume_challenge(self, challenge_id: str) -> None:
        if challenge_id in self._consumed_challenges:
            return
        if len(self._consumed_challenge_order) >= 4096:
            oldest = self._consumed_challenge_order.popleft()
            self._consumed_challenges.discard(oldest)
        self._consumed_challenge_order.append(challenge_id)
        self._consumed_challenges.add(challenge_id)


def _random_value() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _mutable_message(value: object) -> dict[str, object]:
    if not isinstance(value, (dict, MappingProxyType)):
        raise TypeError("Validated root message must be a JSON object")
    return dict(value)
