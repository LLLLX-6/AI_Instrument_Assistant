from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from .models import OperationBudget, SemanticOperation


@dataclass(frozen=True, slots=True)
class StartInteractiveWorkflow:
    safe_label: str
    request_correlation_id: str
    harness_conversation_id: str | None = None


@dataclass(frozen=True, slots=True)
class ObserveCurrentDesign:
    workflow_id: UUID
    expected_revision: int


@dataclass(frozen=True, slots=True)
class SubmitDesignSelectionAnswer:
    workflow_id: UUID
    expected_revision: int
    challenge_id: UUID
    nonce: str
    candidate_set_identity: str
    candidate_identity: str


@dataclass(frozen=True, slots=True)
class PrepareMeasurementPlan:
    workflow_id: UUID
    expected_revision: int
    probe_target_identity: str
    operations: tuple[SemanticOperation, ...]
    channel: int | None
    budgets: tuple[OperationBudget, ...]


@dataclass(frozen=True, slots=True)
class SubmitOperationAuthorizationAnswer:
    workflow_id: UUID
    expected_revision: int
    challenge_id: UUID
    nonce: str
    operation_plan_identity: str
    authorized: bool


@dataclass(frozen=True, slots=True)
class SubmitPhysicalSetupAnswer:
    workflow_id: UUID
    expected_revision: int
    challenge_id: UUID
    nonce: str
    probe_target_identity: str
    operation_plan_identity: str
    channel: int
    maximum_expected_voltage_v: float
    probe_connected: bool
    common_ground_confirmed: bool
    voltage_range_confirmed: bool
    wiring_unchanged: bool


@dataclass(frozen=True, slots=True)
class HighlightResolvedTarget:
    workflow_id: UUID
    expected_revision: int


@dataclass(frozen=True, slots=True)
class CancelWorkflow:
    workflow_id: UUID
    expected_revision: int
    reason: str


@dataclass(frozen=True, slots=True)
class RequestTeachingPublication:
    workflow_id: UUID
    expected_revision: int
