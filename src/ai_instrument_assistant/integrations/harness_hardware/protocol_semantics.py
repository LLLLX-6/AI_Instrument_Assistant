from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


PROTOCOL_NAME = "aia-harness-hardware"
PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 65_536

ALLOWED_OPERATIONS = frozenset(
    {
        "hardware.get_status",
        "hardware.measure_frequency",
        "hardware.measure_vpp",
        "hardware.capture_waveform",
        "hardware.measure_pwm",
    }
)

ADAPTER_FAILURE_CODES = frozenset(
    {
        "ipc_authentication_failed",
        "backend_protocol_mismatch",
        "backend_unreachable",
        "backend_response_invalid",
        "indeterminate_execution",
    }
)


class DeliveryState(str, Enum):
    NOT_SENT = "NOT_SENT"
    SENT_UNCONFIRMED = "SENT_UNCONFIRMED"
    RESPONSE_RECEIVED = "RESPONSE_RECEIVED"


class CancellationState(str, Enum):
    ACTIVE = "ACTIVE"
    CLIENT_CANCELLED_WAIT = "CLIENT_CANCELLED_WAIT"


class ProtocolSemanticError(ValueError):
    """A structurally valid message violates cross-message protocol semantics."""


class MessageSizeError(ProtocolSemanticError):
    """A serialized message exceeds the protocol's bounded size."""


class IndeterminateExecutionError(ProtocolSemanticError):
    """Delivery may have occurred, so an observation must not be replayed."""


@dataclass(slots=True)
class PendingRequest:
    message_id: str
    operation: str
    session_id: str
    connection_generation: int
    delivery_state: DeliveryState = DeliveryState.NOT_SENT
    cancellation_state: CancellationState = CancellationState.ACTIVE

    @property
    def may_auto_replay(self) -> bool:
        return False

    @property
    def measurement_cancelled(self) -> bool:
        return False


@dataclass(slots=True)
class _Challenge:
    challenge_id: str
    server_nonce: str
    expires_at: datetime
    consumed: bool = False


class ProtocolContractState:
    """Pure state rules for authentication, correlation, delivery, and cancellation.

    This class performs no networking and no authentication cryptography. JSON Schema
    owns single-message shape; this object owns rules spanning multiple messages.
    """

    def __init__(self, *, connection_generation: int) -> None:
        if connection_generation < 1:
            raise ValueError("connection_generation must be at least 1")
        self.connection_generation = connection_generation
        self.active_session_id: str | None = None
        self._seen_message_ids: set[str] = set()
        self._challenges: dict[str, _Challenge] = {}
        self._proof_ids: set[str] = set()
        self._requests: dict[str, PendingRequest] = {}

    def establish_session(
        self,
        session_id: str,
        *,
        connection_generation: int | None = None,
    ) -> None:
        if connection_generation is not None:
            if connection_generation <= self.connection_generation:
                raise ProtocolSemanticError("connection generation must increase")
            self.connection_generation = connection_generation
        self.active_session_id = session_id
        self._seen_message_ids.clear()

    def register_challenge(
        self,
        challenge_id: str,
        server_nonce: str,
        expires_at: datetime,
    ) -> None:
        if challenge_id in self._challenges:
            raise ProtocolSemanticError("challenge replay detected")
        if expires_at.tzinfo is None:
            raise ProtocolSemanticError("challenge expiry must be timezone-aware")
        self._challenges[challenge_id] = _Challenge(
            challenge_id=challenge_id,
            server_nonce=server_nonce,
            expires_at=expires_at,
        )

    def consume_proof(
        self,
        challenge_id: str,
        proof_id: str,
        *,
        now: datetime | None = None,
    ) -> None:
        challenge = self._challenges.get(challenge_id)
        if challenge is None or challenge.consumed or proof_id in self._proof_ids:
            raise ProtocolSemanticError("challenge or proof replay detected")
        observed_at = now or datetime.now(timezone.utc)
        if observed_at > challenge.expires_at:
            raise ProtocolSemanticError("challenge expired")
        challenge.consumed = True
        self._proof_ids.add(proof_id)

    def observe_session_message(self, message_id: str, session_id: str) -> None:
        self._require_active_session(session_id)
        if message_id in self._seen_message_ids:
            raise ProtocolSemanticError("duplicate message_id")
        self._seen_message_ids.add(message_id)

    def mark_request_sent(
        self,
        message_id: str,
        operation: str,
        session_id: str,
    ) -> None:
        if operation not in ALLOWED_OPERATIONS:
            raise ProtocolSemanticError("operation is not statically allowlisted")
        self.observe_session_message(message_id, session_id)
        pending = PendingRequest(
            message_id=message_id,
            operation=operation,
            session_id=session_id,
            connection_generation=self.connection_generation,
            delivery_state=DeliveryState.SENT_UNCONFIRMED,
        )
        self._requests[message_id] = pending

    def receive_response(
        self,
        message_id: str,
        reply_to: str,
        session_id: str,
        *,
        operation: str | None = None,
    ) -> str:
        self.observe_session_message(message_id, session_id)
        pending = self._requests.get(reply_to)
        if pending is None:
            raise ProtocolSemanticError("unknown reply_to")
        if pending.session_id != session_id:
            raise ProtocolSemanticError("response belongs to an old session")
        if pending.connection_generation != self.connection_generation:
            raise ProtocolSemanticError("response belongs to an old connection generation")
        if operation is not None and operation != pending.operation:
            raise ProtocolSemanticError("response operation does not match its request")
        if pending.delivery_state is DeliveryState.RESPONSE_RECEIVED:
            raise ProtocolSemanticError("duplicate response")
        pending.delivery_state = DeliveryState.RESPONSE_RECEIVED
        if pending.cancellation_state is CancellationState.CLIENT_CANCELLED_WAIT:
            return "late_discarded"
        return "accepted"

    def cancel_client_wait(self, request_id: str) -> None:
        pending = self.request(request_id)
        pending.cancellation_state = CancellationState.CLIENT_CANCELLED_WAIT

    def disconnect(self) -> None:
        self.active_session_id = None
        uncertain = tuple(
            request
            for request in self._requests.values()
            if request.delivery_state is DeliveryState.SENT_UNCONFIRMED
        )
        if uncertain:
            raise IndeterminateExecutionError(
                "one or more requests were sent without a confirmed response"
            )

    def request(self, request_id: str) -> PendingRequest:
        try:
            return self._requests[request_id]
        except KeyError as error:
            raise ProtocolSemanticError("unknown request") from error

    @staticmethod
    def ensure_message_size(serialized_message: bytes) -> None:
        if len(serialized_message) > MAX_MESSAGE_BYTES:
            raise MessageSizeError(
                f"message is larger than {MAX_MESSAGE_BYTES} bytes"
            )

    def _require_active_session(self, session_id: str) -> None:
        if self.active_session_id is None or session_id != self.active_session_id:
            raise ProtocolSemanticError("message does not belong to the active session")
