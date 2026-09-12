from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from uuid import UUID, uuid4

from ...application.interactive import (
    ApplicationHost,
    FrontendConnectionError,
    FrontendConnection,
    FrontendKind,
    SubscriptionBatch,
)
from .protocol import INTERACTIVE_PROTOCOL, InteractiveProtocolBinding, InteractiveProtocolError


class AuthenticationError(PermissionError):
    pass


class ProtocolNegotiationError(ValueError):
    pass


class FrontendAuthenticator(Protocol):
    def authenticate(self, frontend_kind: FrontendKind, credential: str) -> str | None: ...


@dataclass(frozen=True, slots=True)
class LoopbackGatewayConfig:
    host: str = "127.0.0.1"
    port: int = 49624
    path: str = "/interactive/v1"

    def __post_init__(self) -> None:
        if self.host != "127.0.0.1":
            raise ValueError("interactive gateway must bind explicit 127.0.0.1")
        if not isinstance(self.port, int) or not 1 <= self.port <= 65535:
            raise ValueError("interactive gateway port must be valid")
        if self.path != "/interactive/v1":
            raise ValueError("interactive gateway path is version-bound")


@dataclass(frozen=True, slots=True)
class HandshakeResult:
    acknowledgement: Mapping[str, Any]
    connection: FrontendConnection
    initial_subscription: SubscriptionBatch


class InteractiveGateway:
    """Schema-bounded handler seam; no socket implementation is used in Phase 8.5A."""

    def __init__(
        self,
        *,
        host: ApplicationHost,
        protocol: InteractiveProtocolBinding,
        authenticator: FrontendAuthenticator,
    ) -> None:
        self._host = host
        self._protocol = protocol
        self._authenticator = authenticator

    def handle_hello(self, message: Mapping[str, Any], credential: str) -> HandshakeResult:
        validated = self._protocol.validate_message(message).instance
        if validated["message_type"] != "hello":
            raise ProtocolNegotiationError("first message must be hello")
        versions = tuple(validated["supported_versions"])
        if INTERACTIVE_PROTOCOL not in versions:
            raise ProtocolNegotiationError("interactive protocol version is incompatible")
        frontend_kind = FrontendKind(validated["frontend_kind"])
        principal = self._authenticator.authenticate(frontend_kind, credential)
        if principal is None:
            raise AuthenticationError("frontend authentication failed")
        connection = self._host.connect_frontend(frontend_kind, principal)
        cursor = validated["resume_cursor"]
        initial = self._host.subscribe(connection.connection_id, 0 if cursor is None else cursor)
        acknowledgement = {
            "protocol": INTERACTIVE_PROTOCOL,
            "message_id": str(uuid4()),
            "sent_at": self._host.application_session.started_at.isoformat().replace("+00:00", "Z"),
            "message_type": "hello_ack",
            "accepted": True,
            "selected_version": INTERACTIVE_PROTOCOL,
            "application_generation": str(self._host.application_session.generation),
            "connection_id": str(connection.connection_id),
            "connection_generation": connection.connection_generation,
            "session_id": str(connection.session_id),
            "current_event_cursor": initial.next_cursor,
            "reason_code": None,
        }
        self._protocol.validate_message(acknowledgement)
        return HandshakeResult(acknowledgement, connection, initial)

    def handle_challenge_answer(
        self,
        connection_id: UUID,
        message: Mapping[str, Any],
    ):
        value = self._session_message(connection_id, message, "challenge_answer")
        answer = value["answer"]
        common = (
            connection_id,
            UUID(value["workflow_id"]),
            value["expected_workflow_revision"],
            UUID(value["challenge_id"]),
            value["nonce"],
        )
        if value["challenge_kind"] == "DESIGN_SELECTION":
            return self._host.answer_design_selection(
                *common, answer["candidate_set_identity"], answer["candidate_identity"]
            )
        if value["challenge_kind"] == "OPERATION_AUTHORIZATION":
            return self._host.answer_operation_authorization(
                *common, answer["operation_plan_identity"], answer["authorized"]
            )
        return self._host.answer_physical_setup(
            *common,
            answer["probe_target_identity"], answer["operation_plan_identity"],
            answer["channel"], answer["maximum_expected_voltage_v"],
            answer["probe_connected"], answer["common_ground_confirmed"],
            answer["voltage_range_confirmed"], answer["wiring_unchanged"],
        )

    def handle_command(self, connection_id: UUID, message: Mapping[str, Any]):
        value = self._session_message(connection_id, message, "command")
        command = value["command"]
        payload = value["payload"]
        if command == "workflow.start":
            connection = self._host.get_connection(connection_id)
            if connection.frontend_kind is not FrontendKind.HARNESS:
                raise AuthenticationError("only Harness may start a conversational workflow")
            return self._host.start_workflow(
                payload["safe_label"], value["correlation_id"],
                payload["harness_conversation_id"],
            )
        if command == "workflow.cancel":
            return self._host.cancel_workflow(
                UUID(payload["workflow_id"]),
                payload["expected_workflow_revision"],
                payload["reason"],
            )
        raise InteractiveProtocolError("command is valid but not orchestrated in Phase 8.5A")

    def subscribe(self, connection_id: UUID, cursor: int) -> SubscriptionBatch:
        return self._host.subscribe(connection_id, cursor)

    def disconnect(self, connection_id: UUID) -> None:
        self._host.disconnect_frontend(connection_id)

    def _session_message(
        self,
        connection_id: UUID,
        message: Mapping[str, Any],
        expected_type: str,
    ) -> Mapping[str, Any]:
        try:
            connection = self._host.get_connection(connection_id)
        except FrontendConnectionError as error:
            raise AuthenticationError("interactive connection is not active") from error
        value = self._protocol.validate_message(message).instance
        if value["message_type"] != expected_type:
            raise InteractiveProtocolError("unexpected interactive message type")
        if str(connection.session_id) != value["session_id"]:
            raise AuthenticationError("interactive session mismatch")
        if str(connection.application_generation) != value["application_generation"]:
            raise AuthenticationError("application generation mismatch")
        return value
