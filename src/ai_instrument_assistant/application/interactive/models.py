from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class FrontendKind(StrEnum):
    HARNESS = "HARNESS"
    JLCEDA = "JLCEDA"


class WorkflowState(StrEnum):
    IDLE = "IDLE"
    OBSERVING_DESIGN = "OBSERVING_DESIGN"
    DESIGN_CONTEXT_READY = "DESIGN_CONTEXT_READY"
    WAITING_FOR_DESIGN_SELECTION = "WAITING_FOR_DESIGN_SELECTION"
    TARGET_RESOLVED = "TARGET_RESOLVED"
    OPERATION_PREPARED = "OPERATION_PREPARED"
    WAITING_FOR_OPERATION_AUTHORIZATION = "WAITING_FOR_OPERATION_AUTHORIZATION"
    WAITING_FOR_PHYSICAL_CONFIRMATION = "WAITING_FOR_PHYSICAL_CONFIRMATION"
    READY_TO_EXECUTE = "READY_TO_EXECUTE"
    CONNECTING_INSTRUMENT = "CONNECTING_INSTRUMENT"
    MEASURING = "MEASURING"
    ANALYZING = "ANALYZING"
    BUILDING_EVIDENCE = "BUILDING_EVIDENCE"
    GENERATING_TEACHING_RESPONSE = "GENERATING_TEACHING_RESPONSE"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    @property
    def terminal(self) -> bool:
        return self in {self.COMPLETE, self.FAILED, self.CANCELLED}


class ChallengeKind(StrEnum):
    DESIGN_SELECTION = "DESIGN_SELECTION"
    OPERATION_AUTHORIZATION = "OPERATION_AUTHORIZATION"
    PHYSICAL_SETUP = "PHYSICAL_SETUP"


class SemanticOperation(StrEnum):
    GET_STATUS = "hardware.get_status"
    MEASURE_FREQUENCY = "hardware.measure_frequency"
    MEASURE_VPP = "hardware.measure_vpp"
    CAPTURE_WAVEFORM = "hardware.capture_waveform"
    MEASURE_PWM = "hardware.measure_pwm"


class DeliveryState(StrEnum):
    NOT_SENT = "NOT_SENT"
    SENT_UNCONFIRMED = "SENT_UNCONFIRMED"
    RESPONSE_RECEIVED = "RESPONSE_RECEIVED"


class HostState(StrEnum):
    STARTING = "STARTING"
    READY = "READY"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAULTED = "FAULTED"


class ConnectionState(StrEnum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTED = "CONNECTED"


class HardwareState(StrEnum):
    UNAVAILABLE = "UNAVAILABLE"
    AVAILABLE = "AVAILABLE"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    FAULTED = "FAULTED"


@dataclass(frozen=True, slots=True)
class ApplicationSession:
    generation: UUID
    started_at: datetime
    host_state: HostState = HostState.READY

    def __post_init__(self) -> None:
        _uuid(self.generation, "generation")
        _aware(self.started_at, "started_at")


@dataclass(frozen=True, slots=True)
class FrontendConnection:
    connection_id: UUID
    session_id: UUID
    application_generation: UUID
    frontend_kind: FrontendKind
    connection_generation: int
    authenticated_principal: str
    connected_at: datetime
    connected: bool = True

    def __post_init__(self) -> None:
        _uuid(self.connection_id, "connection_id")
        _uuid(self.session_id, "session_id")
        _uuid(self.application_generation, "application_generation")
        if self.connection_generation < 1:
            raise ValueError("connection_generation must be positive")
        _text(self.authenticated_principal, "authenticated_principal", 192)
        _aware(self.connected_at, "connected_at")


@dataclass(frozen=True, slots=True)
class OperationBudget:
    operation: SemanticOperation
    maximum_invocations: int

    def __post_init__(self) -> None:
        if not isinstance(self.operation, SemanticOperation):
            raise TypeError("operation must be SemanticOperation")
        if not isinstance(self.maximum_invocations, int) or not 1 <= self.maximum_invocations <= 4:
            raise ValueError("maximum_invocations must be between 1 and 4")


@dataclass(frozen=True, slots=True)
class OperationPlan:
    identity: str
    probe_target_identity: str
    operations: tuple[SemanticOperation, ...]
    channel: int | None
    budgets: tuple[OperationBudget, ...]

    @classmethod
    def create(
        cls,
        probe_target_identity: str,
        operations: tuple[SemanticOperation, ...],
        channel: int | None,
        budgets: tuple[OperationBudget, ...],
    ) -> OperationPlan:
        target = _text(probe_target_identity, "probe_target_identity", 192)
        operations = tuple(operations)
        budgets = tuple(budgets)
        if not operations or len(operations) > 5 or len(set(operations)) != len(operations):
            raise ValueError("operations must contain one to five unique values")
        if not all(isinstance(item, SemanticOperation) for item in operations):
            raise TypeError("operations must be SemanticOperation values")
        if channel not in {None, 1, 2}:
            raise ValueError("channel must be null, 1, or 2")
        measurement_ops = set(operations) - {SemanticOperation.GET_STATUS}
        if measurement_ops and channel is None:
            raise ValueError("measurement operations require a channel")
        if len(budgets) != len(operations):
            raise ValueError("every operation requires one budget")
        budget_operations = tuple(item.operation for item in budgets)
        if len(set(budget_operations)) != len(budget_operations) or set(budget_operations) != set(operations):
            raise ValueError("budgets must exactly match operations")
        payload = {
            "scope": "interactive-operation-plan/v1",
            "probe_target_identity": target,
            "operations": [item.value for item in operations],
            "channel": channel,
            "budgets": [
                {"operation": item.operation.value, "maximum_invocations": item.maximum_invocations}
                for item in budgets
            ],
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return cls(f"sha256:{digest}", target, operations, channel, budgets)


@dataclass(frozen=True, slots=True)
class WorkflowSession:
    workflow_id: UUID
    revision: int
    request_correlation_id: str
    safe_label: str
    state: WorkflowState
    harness_conversation_id: str | None = None
    design_observation_ref: str | None = None
    candidate_set_identity: str | None = None
    trusted_design_decision_ref: str | None = None
    probe_target_ref: str | None = None
    operation_plan: OperationPlan | None = None
    pending_challenge_ids: tuple[UUID, ...] = ()
    operation_scope_ref: str | None = None
    remaining_budget: tuple[OperationBudget, ...] = ()
    physical_confirmation_ref: str | None = None
    delivery_state: DeliveryState = DeliveryState.NOT_SENT
    evidence_refs: tuple[str, ...] = ()
    publication_ref: str | None = None

    def __post_init__(self) -> None:
        _uuid(self.workflow_id, "workflow_id")
        if self.revision < 0:
            raise ValueError("revision must be non-negative")
        _text(self.request_correlation_id, "request_correlation_id", 256)
        _text(self.safe_label, "safe_label", 80)
        if not isinstance(self.state, WorkflowState):
            raise TypeError("state must be WorkflowState")
        if len(self.pending_challenge_ids) > 3:
            raise ValueError("at most three pending challenges are permitted")
        if not all(isinstance(item, UUID) for item in self.pending_challenge_ids):
            raise TypeError("pending challenge ids must be UUID values")

    @property
    def terminal(self) -> bool:
        return self.state.terminal


@dataclass(frozen=True, slots=True)
class DesignSelectionBinding:
    observation_identity: str
    candidate_set_identity: str
    allowed_candidate_identities: tuple[str, ...]

    def __post_init__(self) -> None:
        _content_identity(self.observation_identity, "observation_identity")
        _content_identity(self.candidate_set_identity, "candidate_set_identity")
        candidates = tuple(self.allowed_candidate_identities)
        if not 2 <= len(candidates) <= 16 or len(set(candidates)) != len(candidates):
            raise ValueError("candidate identities must contain two to sixteen unique values")
        for candidate in candidates:
            _text(candidate, "candidate_identity", 192)
        object.__setattr__(self, "allowed_candidate_identities", candidates)


@dataclass(frozen=True, slots=True)
class OperationAuthorizationBinding:
    operation_plan_identity: str
    semantic_operations: tuple[SemanticOperation, ...]
    channel: int | None
    budgets: tuple[OperationBudget, ...]

    def __post_init__(self) -> None:
        _content_identity(self.operation_plan_identity, "operation_plan_identity")
        plan = OperationPlan.create("binding:probe-target", self.semantic_operations, self.channel, self.budgets)
        if plan.operations != tuple(self.semantic_operations):
            raise ValueError("operation binding is invalid")


@dataclass(frozen=True, slots=True)
class PhysicalSetupBinding:
    probe_target_identity: str
    operation_plan_identity: str
    channel: int
    maximum_expected_voltage_v: float
    probe_statement: str
    ground_statement: str
    voltage_statement: str
    wiring_statement: str

    def __post_init__(self) -> None:
        _text(self.probe_target_identity, "probe_target_identity", 192)
        _content_identity(self.operation_plan_identity, "operation_plan_identity")
        if self.channel not in {1, 2}:
            raise ValueError("physical setup channel must be 1 or 2")
        if not 0 < self.maximum_expected_voltage_v <= 50:
            raise ValueError("maximum expected voltage must be within the bounded range")
        for name in ("probe_statement", "ground_statement", "voltage_statement", "wiring_statement"):
            _text(getattr(self, name), name, 256)


ChallengeBinding = DesignSelectionBinding | OperationAuthorizationBinding | PhysicalSetupBinding


@dataclass(frozen=True, slots=True)
class Challenge:
    challenge_id: UUID
    kind: ChallengeKind
    application_generation: UUID
    workflow_id: UUID
    workflow_revision: int
    request_correlation_id: str
    allowed_frontend_kind: FrontendKind
    issued_at: datetime
    expires_at: datetime
    nonce: str
    binding: ChallengeBinding

    def __post_init__(self) -> None:
        _uuid(self.challenge_id, "challenge_id")
        _uuid(self.application_generation, "application_generation")
        _uuid(self.workflow_id, "workflow_id")
        _aware(self.issued_at, "issued_at")
        _aware(self.expires_at, "expires_at")
        if self.expires_at <= self.issued_at:
            raise ValueError("challenge expiry must be after issuance")
        if self.workflow_revision < 0:
            raise ValueError("workflow_revision must be non-negative")
        _text(self.request_correlation_id, "request_correlation_id", 256)
        nonce = _text(self.nonce, "nonce", 128)
        if len(nonce) < 24:
            raise ValueError("challenge nonce must be at least 24 characters")
        expected_binding = {
            ChallengeKind.DESIGN_SELECTION: DesignSelectionBinding,
            ChallengeKind.OPERATION_AUTHORIZATION: OperationAuthorizationBinding,
            ChallengeKind.PHYSICAL_SETUP: PhysicalSetupBinding,
        }[self.kind]
        if not isinstance(self.binding, expected_binding):
            raise TypeError("challenge kind and binding do not match")


@dataclass(frozen=True, slots=True)
class TrustedDesignSelectionReceipt:
    """Reference-only outcome from the existing trusted design service."""

    decision_ref: str
    probe_target_ref: str

    def __post_init__(self) -> None:
        _text(self.decision_ref, "decision_ref", 192)
        _text(self.probe_target_ref, "probe_target_ref", 192)


@dataclass(frozen=True, slots=True)
class ValidatedDesignSelectionRequest:
    workflow_id: UUID
    request_correlation_id: str
    binding: DesignSelectionBinding
    selected_candidate_identity: str
    decided_at: datetime


@dataclass(frozen=True, slots=True)
class ValidatedOperationAuthorizationRequest:
    workflow_id: UUID
    request_correlation_id: str
    binding: OperationAuthorizationBinding
    authorized_at: datetime


@dataclass(frozen=True, slots=True)
class ValidatedPhysicalSetupRequest:
    workflow_id: UUID
    request_correlation_id: str
    binding: PhysicalSetupBinding
    confirmed_at: datetime


class TrustedDecisionIssuer(Protocol):
    """Inward port to existing trusted factories; frontend DTOs never implement it."""

    def issue_design_selection(self, request: ValidatedDesignSelectionRequest) -> TrustedDesignSelectionReceipt: ...
    def issue_operation_authorization(self, request: ValidatedOperationAuthorizationRequest) -> str: ...
    def issue_physical_confirmation(self, request: ValidatedPhysicalSetupRequest) -> str: ...


def _uuid(value: object, name: str) -> None:
    if not isinstance(value, UUID):
        raise TypeError(f"{name} must be UUID")


def _aware(value: object, name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise TypeError(f"{name} must be timezone-aware datetime")


def _text(value: object, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be bounded non-empty text")
    return value.strip()


def _content_identity(value: object, name: str) -> None:
    if not isinstance(value, str) or len(value) != 71 or not value.startswith("sha256:"):
        raise ValueError(f"{name} must be a sha256 content identity")
    try:
        int(value[7:], 16)
    except ValueError as error:
        raise ValueError(f"{name} must be a sha256 content identity") from error
