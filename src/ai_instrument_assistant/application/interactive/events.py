from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from .models import ApplicationSession, Challenge, WorkflowSession


class EventType(StrEnum):
    APPLICATION_STATUS_CHANGED = "application_status_changed"
    FRONTEND_CONNECTION_CHANGED = "frontend_connection_changed"
    WORKFLOW_SNAPSHOT = "workflow_snapshot"
    WORKFLOW_STATE_CHANGED = "workflow_state_changed"
    DESIGN_OBSERVATION_CHANGED = "design_observation_changed"
    DESIGN_SELECTION_REQUIRED = "design_selection_required"
    PROBE_TARGET_READY = "probe_target_ready"
    OPERATION_AUTHORIZATION_REQUIRED = "operation_authorization_required"
    PHYSICAL_CONFIRMATION_REQUIRED = "physical_confirmation_required"
    MEASUREMENT_PROGRESS_CHANGED = "measurement_progress_changed"
    EVIDENCE_SUMMARY_READY = "evidence_summary_ready"
    TEACHING_PUBLICATION_READY = "teaching_publication_ready"
    WORKFLOW_CANCELLED = "workflow_cancelled"
    WORKFLOW_FAILED = "workflow_failed"


@dataclass(frozen=True, slots=True)
class SafeEventPayload:
    code: str
    message: str
    challenge: Challenge | None = None


@dataclass(frozen=True, slots=True)
class InteractiveEvent:
    event_id: UUID
    cursor: int
    application_generation: UUID
    workflow_id: UUID | None
    workflow_revision: int | None
    correlation_id: str
    event_type: EventType
    occurred_at: datetime
    payload: SafeEventPayload


@dataclass(frozen=True, slots=True)
class ApplicationSnapshot:
    application_session: ApplicationSession
    event_cursor: int
    workflows: tuple[WorkflowSession, ...]
    pending_challenges: tuple[Challenge, ...]


@dataclass(frozen=True, slots=True)
class SubscriptionBatch:
    snapshot: ApplicationSnapshot
    events: tuple[InteractiveEvent, ...]
    next_cursor: int


@dataclass(frozen=True, slots=True)
class AuditRecord:
    audit_id: UUID
    application_generation: UUID
    workflow_id: UUID | None
    workflow_revision: int | None
    correlation_id: str
    action: str
    occurred_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.action, str) or not self.action or len(self.action) > 128:
            raise ValueError("audit action must be bounded non-empty text")
        if not isinstance(self.correlation_id, str) or not self.correlation_id or len(self.correlation_id) > 256:
            raise ValueError("audit correlation must be bounded non-empty text")
