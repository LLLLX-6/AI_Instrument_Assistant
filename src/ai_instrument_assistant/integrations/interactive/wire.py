from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from ...application.interactive import (
    ApplicationHost,
    ApplicationSnapshot,
    Challenge,
    DesignSelectionBinding,
    EventType,
    FrontendConnection,
    InteractiveEvent,
    OperationAuthorizationBinding,
    PhysicalSetupBinding,
)
from .protocol import INTERACTIVE_PROTOCOL, InteractiveProtocolBinding


class InteractiveWireProjector:
    """Allowlisted Application Host values to the frozen interactive wire contract."""

    def __init__(self, host: ApplicationHost, protocol: InteractiveProtocolBinding | None = None) -> None:
        self._host = host
        self._protocol = protocol or InteractiveProtocolBinding.from_repository(
            Path(__file__).resolve().parents[4]
        )

    def validate(self, message: dict[str, Any]) -> None:
        self._protocol.validate_message(message)

    def snapshot_event(
        self,
        connection: FrontendConnection,
        snapshot: ApplicationSnapshot,
    ) -> dict[str, Any]:
        workflow = next((value for value in reversed(snapshot.workflows) if not value.terminal), None)
        status = self._host.product_status(None if workflow is None else workflow.workflow_id)
        message = self._envelope(connection) | {
            "message_type": "event",
            "event_id": str(uuid4()),
            "cursor": max(1, snapshot.event_cursor),
            "event_type": "workflow_snapshot",
            "workflow_id": None,
            "workflow_revision": None,
            "correlation_id": "snapshot",
            "payload": {"snapshot": {
                "application_generation": str(snapshot.application_session.generation),
                "event_cursor": snapshot.event_cursor,
                "status": _status(status),
                "workflows": [_workflow(value) for value in snapshot.workflows[:32]],
                "pending_challenges": [_challenge(value) for value in snapshot.pending_challenges[:8]],
            }},
        }
        self.validate(message)
        return message

    def event(self, connection: FrontendConnection, event: InteractiveEvent) -> dict[str, Any]:
        base = self._envelope(connection) | {
            "message_type": "event",
            "event_id": str(event.event_id),
            "cursor": event.cursor,
            "event_type": event.event_type.value,
            "workflow_id": None if event.workflow_id is None else str(event.workflow_id),
            "workflow_revision": event.workflow_revision,
            "correlation_id": event.correlation_id,
        }
        if event.event_type is EventType.APPLICATION_STATUS_CHANGED:
            base["payload"] = {"status": _status(self._host.product_status(event.workflow_id))}
        elif event.payload.challenge is not None:
            base["payload"] = {"challenge": _challenge(event.payload.challenge)}
        else:
            base["payload"] = {"code": event.payload.code, "message": event.payload.message}
        self.validate(base)
        return base

    @staticmethod
    def _envelope(connection: FrontendConnection) -> dict[str, Any]:
        return {
            "protocol": INTERACTIVE_PROTOCOL,
            "message_id": str(uuid4()),
            "sent_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "application_generation": str(connection.application_generation),
            "session_id": str(connection.session_id),
        }


def _workflow(value: Any) -> dict[str, Any]:
    return {
        "workflow_id": str(value.workflow_id), "revision": value.revision,
        "state": value.state.value, "safe_label": value.safe_label,
        "pending_challenge_ids": [str(item) for item in value.pending_challenge_ids],
        "terminal": value.terminal,
    }


def _status(value: Any) -> dict[str, Any]:
    return {
        "host_state": value.host_state.value,
        "protocol_compatible": value.protocol_compatible,
        "harness_state": value.harness_state.value,
        "jlceda_state": value.jlceda_state.value,
        "hardware_state": value.hardware_state.value,
        "workflow_state": value.workflow_state,
        "workflow_revision": value.workflow_revision,
        "safe_workflow_label": value.safe_workflow_label,
        "last_error_code": None if value.last_error_code is None else value.last_error_code.value,
        "message": value.message,
    }


def _challenge(value: Challenge) -> dict[str, Any]:
    binding = value.binding
    if isinstance(binding, DesignSelectionBinding):
        wire_binding = {
            "observation_identity": binding.observation_identity,
            "candidate_set_identity": binding.candidate_set_identity,
            "allowed_candidate_identities": list(binding.allowed_candidate_identities),
        }
    elif isinstance(binding, OperationAuthorizationBinding):
        wire_binding = {
            "operation_plan_identity": binding.operation_plan_identity,
            "semantic_operations": [item.value for item in binding.semantic_operations],
            "channel": binding.channel,
            "budgets": [
                {"operation": item.operation.value, "maximum_invocations": item.maximum_invocations}
                for item in binding.budgets
            ],
        }
    elif isinstance(binding, PhysicalSetupBinding):
        wire_binding = {
            "probe_target_identity": binding.probe_target_identity,
            "operation_plan_identity": binding.operation_plan_identity,
            "channel": binding.channel,
            "maximum_expected_voltage_v": binding.maximum_expected_voltage_v,
            "probe_statement": binding.probe_statement,
            "ground_statement": binding.ground_statement,
            "voltage_statement": binding.voltage_statement,
            "wiring_statement": binding.wiring_statement,
        }
    else:
        raise TypeError("unsupported interactive challenge binding")
    return {
        "challenge_id": str(value.challenge_id), "challenge_kind": value.kind.value,
        "application_generation": str(value.application_generation),
        "workflow_id": str(value.workflow_id), "workflow_revision": value.workflow_revision,
        "request_correlation_id": value.request_correlation_id,
        "allowed_frontend_kind": value.allowed_frontend_kind.value,
        "issued_at": value.issued_at.isoformat().replace("+00:00", "Z"),
        "expires_at": value.expires_at.isoformat().replace("+00:00", "Z"),
        "nonce": value.nonce, "binding": wire_binding,
    }
