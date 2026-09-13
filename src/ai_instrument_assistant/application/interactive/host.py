from __future__ import annotations

import secrets
import threading
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol
from uuid import UUID, uuid4

from .errors import (
    ChallengeRejectedError,
    FrontendConnectionError,
    InvalidEventCursorError,
    InteractiveCapabilityUnavailableError,
    StaleWorkflowRevisionError,
    WorkflowNotFoundError,
)
from .events import (
    ApplicationSnapshot,
    AuditRecord,
    EventType,
    InteractiveEvent,
    SafeEventPayload,
    SubscriptionBatch,
)
from .models import (
    ApplicationSession,
    Challenge,
    ChallengeKind,
    DesignSelectionBinding,
    FrontendConnection,
    FrontendKind,
    HardwareState,
    HostState,
    OperationAuthorizationBinding,
    OperationBudget,
    OperationPlan,
    PhysicalSetupBinding,
    SemanticOperation,
    DesignSelectionDecisionIssuer,
    OperationAuthorizationIssuer,
    PhysicalConfirmationIssuer,
    ValidatedDesignSelectionRequest,
    ValidatedOperationAuthorizationRequest,
    ValidatedPhysicalSetupRequest,
    WorkflowSession,
    WorkflowActionGuard,
    WorkflowState,
)
from ..services.design_selection_disambiguation import (
    DesignSelectionCandidateSetBinding,
    TrustedDesignSelectionResolution,
    TrustedDesignSelectionResolutionStatus,
    candidate_choice_tokens,
)
from ...domain.eda.models import ProbeTarget, SelectionContext
from .state_machine import transition_allowed
from .status import ProductErrorCode, ProductStatus, project_product_status


class RuntimeLifecyclePort(Protocol):
    """Inward lifecycle seam owned by the Host composition root."""

    async def shutdown(self) -> None: ...


class ApplicationHost:
    """Authoritative in-process interactive aggregate and trust-conversion boundary."""

    def __init__(
        self,
        *,
        design_selection_issuer: DesignSelectionDecisionIssuer,
        operation_authorization_issuer: OperationAuthorizationIssuer | None = None,
        physical_confirmation_issuer: PhysicalConfirmationIssuer | None = None,
        clock: Callable[[], datetime] | None = None,
        event_retention: int = 1024,
        runtime_lifecycle: RuntimeLifecyclePort | None = None,
    ) -> None:
        if not isinstance(event_retention, int) or event_retention < 1:
            raise ValueError("event_retention must be a positive integer")
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        now = self._clock()
        self._application_session = ApplicationSession(uuid4(), now)
        self._design_selection_issuer = design_selection_issuer
        self._operation_authorization_issuer = operation_authorization_issuer
        self._physical_confirmation_issuer = physical_confirmation_issuer
        self._runtime_lifecycle = runtime_lifecycle
        self._workflows: dict[UUID, WorkflowSession] = {}
        self._connections: dict[UUID, FrontendConnection] = {}
        self._connection_generation = 0
        self._challenges: dict[UUID, Challenge] = {}
        self._consumed_challenges: set[UUID] = set()
        self._withdrawn_challenges: set[UUID] = set()
        self._events: list[InteractiveEvent] = []
        self._event_retention = event_retention
        self._event_base_cursor = 0
        self._next_event_cursor = 0
        self._audit: list[AuditRecord] = []
        self._lock = threading.RLock()
        self._execution_dispatch_count = 0
        self._hardware_state = HardwareState.UNAVAILABLE
        self._last_error_code: ProductErrorCode | None = None

    @property
    def application_session(self) -> ApplicationSession:
        return self._application_session

    @property
    def execution_dispatch_count(self) -> int:
        return self._execution_dispatch_count

    @property
    def audit_records(self) -> tuple[AuditRecord, ...]:
        return tuple(self._audit)

    @property
    def runtime_lifecycle(self) -> RuntimeLifecyclePort | None:
        return self._runtime_lifecycle

    async def shutdown(self) -> None:
        """Invalidate ephemeral interaction state before owned runtimes stop."""
        with self._lock:
            if self._application_session.host_state is HostState.STOPPED:
                return
            self._application_session = replace(
                self._application_session, host_state=HostState.STOPPING
            )
            self._withdraw(tuple(self._challenges))
            self._connections = {
                key: replace(value, connected=False)
                for key, value in self._connections.items()
            }
            self._emit(
                None, None, "application-lifecycle",
                EventType.APPLICATION_STATUS_CHANGED,
                "host_stopping", "Application Host is stopping.",
            )
        try:
            if self._runtime_lifecycle is not None:
                await self._runtime_lifecycle.shutdown()
        except Exception:
            with self._lock:
                self._application_session = replace(
                    self._application_session, host_state=HostState.FAULTED
                )
            raise
        with self._lock:
            self._application_session = replace(
                self._application_session, host_state=HostState.STOPPED
            )

    def connect_frontend(
        self,
        frontend_kind: FrontendKind,
        authenticated_principal: str,
    ) -> FrontendConnection:
        if not isinstance(frontend_kind, FrontendKind):
            raise FrontendConnectionError("unsupported frontend kind")
        if not isinstance(authenticated_principal, str) or not authenticated_principal.strip():
            raise FrontendConnectionError("authenticated principal is required")
        with self._lock:
            self._connection_generation += 1
            connection = FrontendConnection(
                connection_id=uuid4(),
                session_id=uuid4(),
                application_generation=self._application_session.generation,
                frontend_kind=frontend_kind,
                connection_generation=self._connection_generation,
                authenticated_principal=authenticated_principal.strip(),
                connected_at=self._clock(),
            )
            self._connections[connection.connection_id] = connection
            self._emit(None, None, "frontend-connection", EventType.FRONTEND_CONNECTION_CHANGED, "connected", "Frontend connected.")
            self._audit_event(None, None, "frontend-connection", f"frontend_connected:{frontend_kind.value.lower()}")
            return connection

    def disconnect_frontend(self, connection_id: UUID) -> None:
        with self._lock:
            connection = self._connections.get(connection_id)
            if connection is None or not connection.connected:
                return
            self._connections[connection_id] = replace(connection, connected=False)
            self._emit(None, None, "frontend-connection", EventType.FRONTEND_CONNECTION_CHANGED, "disconnected", "Frontend disconnected.")
            self._audit_event(None, None, "frontend-connection", f"frontend_disconnected:{connection.frontend_kind.value.lower()}")

    def start_workflow(
        self,
        safe_label: str,
        request_correlation_id: str,
        harness_conversation_id: str | None = None,
    ) -> WorkflowSession:
        with self._lock:
            workflow = WorkflowSession(
                workflow_id=uuid4(),
                revision=0,
                request_correlation_id=request_correlation_id,
                safe_label=" ".join(safe_label.split())[:80],
                state=WorkflowState.IDLE,
                harness_conversation_id=harness_conversation_id,
            )
            self._workflows[workflow.workflow_id] = workflow
            self._emit_workflow(workflow, EventType.WORKFLOW_STATE_CHANGED, "workflow_started", "Interactive workflow started.")
            self._audit_action(workflow, "workflow_started")
            return workflow

    def get_workflow(self, workflow_id: UUID) -> WorkflowSession:
        with self._lock:
            try:
                return self._workflows[workflow_id]
            except (KeyError, TypeError) as error:
                raise WorkflowNotFoundError("workflow was not found") from error

    def capture_workflow_guard(
        self,
        workflow_id: UUID,
        expected_revision: int,
    ) -> WorkflowActionGuard:
        """Capture async-action coherence under the Host lock, without doing I/O."""
        with self._lock:
            workflow = self._cas(workflow_id, expected_revision)
            return WorkflowActionGuard(
                application_generation=self._application_session.generation,
                workflow_id=workflow.workflow_id,
                workflow_revision=workflow.revision,
                request_correlation_id=workflow.request_correlation_id,
            )

    def get_connection(self, connection_id: UUID) -> FrontendConnection:
        return self._active_connection(connection_id)

    def product_status(self, workflow_id: UUID | None = None) -> ProductStatus:
        workflow = None if workflow_id is None else self.get_workflow(workflow_id)
        connected_kinds = {
            value.frontend_kind for value in self._connections.values() if value.connected
        }
        return project_product_status(
            host_state=self._application_session.host_state,
            protocol_compatible=True,
            harness_connected=FrontendKind.HARNESS in connected_kinds,
            jlceda_connected=FrontendKind.JLCEDA in connected_kinds,
            hardware_state=self._hardware_state,
            workflow=workflow,
            last_error_code=self._last_error_code,
        )

    def record_hardware_status(
        self,
        state: HardwareState,
        error_code: ProductErrorCode | None = None,
    ) -> ProductStatus:
        """Internal lifecycle projection; it grants no execution authority."""
        if not isinstance(state, HardwareState):
            raise TypeError("state must be HardwareState")
        with self._lock:
            self._hardware_state = state
            self._last_error_code = error_code
            self._emit(None, None, "application-status", EventType.APPLICATION_STATUS_CHANGED, "status_changed", "Application status changed.")
            self._audit_event(None, None, "application-status", f"hardware_status:{state.value.lower()}")
            return self.product_status()

    def transition(
        self,
        workflow_id: UUID,
        expected_revision: int,
        target: WorkflowState,
    ) -> WorkflowSession:
        with self._lock:
            workflow = self._cas(workflow_id, expected_revision)
            transition_allowed(workflow.state, target, raise_on_error=True)
            pending = workflow.pending_challenge_ids
            if target.terminal:
                self._withdraw(pending)
                pending = ()
            updated = replace(workflow, revision=workflow.revision + 1, state=target, pending_challenge_ids=pending)
            self._save(updated, EventType.WORKFLOW_STATE_CHANGED, "workflow_state_changed", f"Workflow entered {target.value}.")
            self._audit_action(updated, f"workflow_transition:{target.value.lower()}")
            return updated

    def record_design_observation(
        self,
        workflow_id: UUID,
        expected_revision: int,
        observation_identity: str,
        *,
        selection_context: SelectionContext,
        candidate_binding: DesignSelectionCandidateSetBinding | None,
        probe_target: ProbeTarget | None,
    ) -> WorkflowSession:
        """Record only bounded observation references and invalidate dependent trust."""
        with self._lock:
            workflow = self._cas(workflow_id, expected_revision)
            transition_allowed(workflow.state, WorkflowState.DESIGN_CONTEXT_READY, raise_on_error=True)
            self._withdraw(workflow.pending_challenge_ids)
            updated = replace(
                workflow,
                revision=workflow.revision + 1,
                state=WorkflowState.DESIGN_CONTEXT_READY,
                design_observation_ref=observation_identity,
                candidate_set_identity=(
                    None if candidate_binding is None
                    else candidate_binding.candidate_set_fingerprint
                ),
                design_selection_context=(
                    selection_context if candidate_binding is not None else None
                ),
                design_selection_binding=candidate_binding,
                trusted_design_selection=None,
                probe_target=probe_target,
                trusted_design_decision_ref=None,
                probe_target_ref=(
                    None if probe_target is None
                    else f"probe-target:{probe_target.target_id}"
                ),
                operation_plan=None,
                pending_challenge_ids=(),
                operation_scope_ref=None,
                remaining_budget=(),
                physical_confirmation_ref=None,
            )
            self._save(updated, EventType.DESIGN_OBSERVATION_CHANGED, "design_observation_changed", "Design observation was refreshed.")
            return updated

    def commit_guarded_design_observation(
        self,
        guard: WorkflowActionGuard,
        observation_identity: str,
        *,
        selection_context: SelectionContext,
        candidate_binding: DesignSelectionCandidateSetBinding | None,
        probe_target: ProbeTarget | None,
    ) -> WorkflowSession | None:
        """Commit only if generation, workflow, revision, and request are unchanged."""
        if not isinstance(guard, WorkflowActionGuard):
            raise TypeError("guard must be WorkflowActionGuard")
        with self._lock:
            if self._application_session.generation != guard.application_generation:
                return None
            workflow = self._workflows.get(guard.workflow_id)
            if (
                workflow is None
                or workflow.revision != guard.workflow_revision
                or workflow.request_correlation_id != guard.request_correlation_id
            ):
                return None
            transition_allowed(
                workflow.state,
                WorkflowState.DESIGN_CONTEXT_READY,
                raise_on_error=True,
            )
            self._withdraw(workflow.pending_challenge_ids)
            updated = replace(
                workflow,
                revision=workflow.revision + 1,
                state=WorkflowState.DESIGN_CONTEXT_READY,
                design_observation_ref=observation_identity,
                candidate_set_identity=(
                    None if candidate_binding is None
                    else candidate_binding.candidate_set_fingerprint
                ),
                design_selection_context=(
                    selection_context if candidate_binding is not None else None
                ),
                design_selection_binding=candidate_binding,
                trusted_design_selection=None,
                probe_target=probe_target,
                trusted_design_decision_ref=None,
                probe_target_ref=(
                    None if probe_target is None
                    else f"probe-target:{probe_target.target_id}"
                ),
                operation_plan=None,
                pending_challenge_ids=(),
                operation_scope_ref=None,
                remaining_budget=(),
                physical_confirmation_ref=None,
            )
            self._save(
                updated,
                EventType.DESIGN_OBSERVATION_CHANGED,
                "design_observation_changed",
                "Design observation was refreshed.",
            )
            return updated

    def fail_guarded_workflow(
        self,
        guard: WorkflowActionGuard,
        *,
        code: str,
        message: str,
    ) -> WorkflowSession | None:
        """Fail only the still-current workflow with bounded application text."""
        if not isinstance(guard, WorkflowActionGuard):
            raise TypeError("guard must be WorkflowActionGuard")
        with self._lock:
            if self._application_session.generation != guard.application_generation:
                return None
            workflow = self._workflows.get(guard.workflow_id)
            if (
                workflow is None
                or workflow.revision != guard.workflow_revision
                or workflow.request_correlation_id != guard.request_correlation_id
            ):
                return None
            transition_allowed(workflow.state, WorkflowState.FAILED, raise_on_error=True)
            self._withdraw(workflow.pending_challenge_ids)
            updated = replace(
                workflow,
                revision=workflow.revision + 1,
                state=WorkflowState.FAILED,
                pending_challenge_ids=(),
            )
            self._save(updated, EventType.WORKFLOW_FAILED, code, message)
            return updated

    def request_design_selection(
        self,
        workflow_id: UUID,
        expected_revision: int,
        allowed_frontend: FrontendKind,
        ttl: timedelta,
    ) -> Challenge:
        workflow = self._cas(workflow_id, expected_revision)
        typed_binding = workflow.design_selection_binding
        if typed_binding is None or workflow.design_selection_context is None:
            raise ChallengeRejectedError("typed design selection is unavailable")
        candidate_identities = tuple(
            token for token, _identity in candidate_choice_tokens(typed_binding)
        )
        binding = DesignSelectionBinding(
            workflow.design_observation_ref,
            typed_binding.candidate_set_fingerprint,
            candidate_identities,
        )
        if len(binding.allowed_candidate_identities) < 2 or len(set(binding.allowed_candidate_identities)) != len(binding.allowed_candidate_identities):
            raise ValueError("design-selection challenge requires unique ambiguous candidates")
        return self._issue_challenge(
            workflow_id, expected_revision, ChallengeKind.DESIGN_SELECTION,
            allowed_frontend, ttl, binding,
            WorkflowState.WAITING_FOR_DESIGN_SELECTION,
            EventType.DESIGN_SELECTION_REQUIRED,
        )

    def answer_design_selection(
        self,
        connection_id: UUID,
        workflow_id: UUID,
        expected_revision: int,
        challenge_id: UUID,
        nonce: str,
        candidate_set_identity: str,
        candidate_identity: str,
    ) -> WorkflowSession:
        with self._lock:
            challenge, workflow = self._validate_challenge(
                connection_id, workflow_id, expected_revision, challenge_id, nonce,
                ChallengeKind.DESIGN_SELECTION,
            )
            binding = challenge.binding
            if not isinstance(binding, DesignSelectionBinding):
                raise ChallengeRejectedError("challenge binding is invalid")
            if candidate_set_identity != binding.candidate_set_identity:
                raise ChallengeRejectedError("candidate set is stale")
            if candidate_identity not in binding.allowed_candidate_identities:
                raise ChallengeRejectedError("candidate was not offered")
            typed_binding = workflow.design_selection_binding
            selection_context = workflow.design_selection_context
            if typed_binding is None or selection_context is None:
                raise ChallengeRejectedError("typed design selection is unavailable")
            choice_map = dict(candidate_choice_tokens(typed_binding))
            selected_candidate = choice_map.get(candidate_identity)
            if selected_candidate is None:
                raise ChallengeRejectedError("candidate was not offered")
            self._consume(challenge)
            self._audit_action(workflow, "challenge_answer_validated:design_selection")
            resolution = self._design_selection_issuer.issue_design_selection(
                ValidatedDesignSelectionRequest(
                    workflow.workflow_id, workflow.request_correlation_id,
                    selection_context, typed_binding, selected_candidate, self._clock(),
                )
            )
            if (
                not isinstance(resolution, TrustedDesignSelectionResolution)
                or resolution.status is not TrustedDesignSelectionResolutionStatus.RESOLVED
                or resolution.decision is None
                or resolution.probe_target is None
            ):
                raise ChallengeRejectedError("trusted design selection was not resolved")
            updated = replace(
                workflow,
                revision=workflow.revision + 1,
                state=WorkflowState.TARGET_RESOLVED,
                design_observation_ref=binding.observation_identity,
                candidate_set_identity=binding.candidate_set_identity,
                trusted_design_selection=resolution,
                probe_target=resolution.probe_target,
                trusted_design_decision_ref=f"design-decision:{resolution.decision.decision_id}",
                probe_target_ref=f"probe-target:{resolution.probe_target.target_id}",
                pending_challenge_ids=(),
            )
            self._save(updated, EventType.PROBE_TARGET_READY, "probe_target_ready", "Design target was resolved.")
            self._audit_action(updated, "trusted_design_decision_issued")
            return updated

    def prepare_measurement_plan(
        self,
        workflow_id: UUID,
        expected_revision: int,
        probe_target_identity: str,
        operations: tuple[SemanticOperation, ...],
        channel: int | None,
        budgets: tuple[OperationBudget, ...],
    ) -> WorkflowSession:
        with self._lock:
            workflow = self._cas(workflow_id, expected_revision)
            transition_allowed(workflow.state, WorkflowState.OPERATION_PREPARED, raise_on_error=True)
            plan = OperationPlan.create(probe_target_identity, operations, channel, budgets)
            self._withdraw(workflow.pending_challenge_ids)
            updated = replace(
                workflow, revision=workflow.revision + 1,
                state=WorkflowState.OPERATION_PREPARED,
                probe_target_ref=probe_target_identity,
                operation_plan=plan,
                pending_challenge_ids=(),
                operation_scope_ref=None,
                remaining_budget=(),
                physical_confirmation_ref=None,
            )
            self._save(updated, EventType.WORKFLOW_STATE_CHANGED, "operation_prepared", "Measurement plan prepared.")
            return updated

    def replace_operation_plan(
        self,
        workflow_id: UUID,
        expected_revision: int,
        probe_target_identity: str,
        operations: tuple[SemanticOperation, ...],
        channel: int | None,
        budgets: tuple[OperationBudget, ...],
    ) -> WorkflowSession:
        with self._lock:
            workflow = self._cas(workflow_id, expected_revision)
            if workflow.state not in {
                WorkflowState.OPERATION_PREPARED,
                WorkflowState.WAITING_FOR_OPERATION_AUTHORIZATION,
                WorkflowState.WAITING_FOR_PHYSICAL_CONFIRMATION,
            }:
                transition_allowed(workflow.state, WorkflowState.OPERATION_PREPARED, raise_on_error=True)
            self._withdraw(workflow.pending_challenge_ids)
            plan = OperationPlan.create(
                probe_target_identity, tuple(operations), channel, tuple(budgets),
            )
            updated = replace(
                workflow, revision=workflow.revision + 1,
                state=WorkflowState.OPERATION_PREPARED,
                probe_target_ref=plan.probe_target_identity,
                operation_plan=plan,
                pending_challenge_ids=(), operation_scope_ref=None,
                remaining_budget=(), physical_confirmation_ref=None,
            )
            self._save(updated, EventType.WORKFLOW_STATE_CHANGED, "operation_replaced", "Measurement plan changed; prior approvals were invalidated.")
            return updated

    def request_operation_authorization(
        self,
        workflow_id: UUID,
        expected_revision: int,
        allowed_frontend: FrontendKind,
        ttl: timedelta,
    ) -> Challenge:
        if self._operation_authorization_issuer is None:
            raise InteractiveCapabilityUnavailableError(
                "operation authorization is deferred to Harness"
            )
        workflow = self._cas(workflow_id, expected_revision)
        if workflow.operation_plan is None:
            raise ValueError("operation plan is required")
        plan = workflow.operation_plan
        binding = OperationAuthorizationBinding(plan.identity, plan.operations, plan.channel, plan.budgets)
        return self._issue_challenge(
            workflow_id, expected_revision, ChallengeKind.OPERATION_AUTHORIZATION,
            allowed_frontend, ttl, binding,
            WorkflowState.WAITING_FOR_OPERATION_AUTHORIZATION,
            EventType.OPERATION_AUTHORIZATION_REQUIRED,
        )

    def answer_operation_authorization(
        self,
        connection_id: UUID,
        workflow_id: UUID,
        expected_revision: int,
        challenge_id: UUID,
        nonce: str,
        operation_plan_identity: str,
        authorized: bool,
    ) -> WorkflowSession:
        with self._lock:
            challenge, workflow = self._validate_challenge(
                connection_id, workflow_id, expected_revision, challenge_id, nonce,
                ChallengeKind.OPERATION_AUTHORIZATION,
            )
            binding = challenge.binding
            if not isinstance(binding, OperationAuthorizationBinding) or operation_plan_identity != binding.operation_plan_identity:
                raise ChallengeRejectedError("operation plan changed")
            self._consume(challenge)
            self._audit_action(workflow, "challenge_answer_validated:operation_authorization")
            if not authorized:
                updated = replace(workflow, revision=workflow.revision + 1, state=WorkflowState.CANCELLED, pending_challenge_ids=())
                self._save(updated, EventType.WORKFLOW_CANCELLED, "cancelled", "Operation authorization was declined.")
                return updated
            if self._operation_authorization_issuer is None:
                raise InteractiveCapabilityUnavailableError(
                    "operation authorization is deferred to Harness"
                )
            reference = self._operation_authorization_issuer.issue_operation_authorization(
                ValidatedOperationAuthorizationRequest(
                    workflow.workflow_id, workflow.request_correlation_id,
                    binding, self._clock(),
                )
            )
            updated = replace(
                workflow, revision=workflow.revision + 1,
                state=WorkflowState.WAITING_FOR_PHYSICAL_CONFIRMATION,
                pending_challenge_ids=(), operation_scope_ref=reference,
                remaining_budget=binding.budgets,
            )
            self._save(updated, EventType.WORKFLOW_STATE_CHANGED, "operation_authorized", "Operation plan was authorized once.")
            self._audit_action(updated, "operation_scope_issuance_requested")
            return updated

    def request_physical_setup(
        self,
        workflow_id: UUID,
        expected_revision: int,
        allowed_frontend: FrontendKind,
        maximum_expected_voltage_v: float,
        ttl: timedelta,
    ) -> Challenge:
        if self._physical_confirmation_issuer is None:
            raise InteractiveCapabilityUnavailableError(
                "physical confirmation is deferred to Harness"
            )
        workflow = self._cas(workflow_id, expected_revision)
        plan = workflow.operation_plan
        if workflow.state is not WorkflowState.WAITING_FOR_PHYSICAL_CONFIRMATION or plan is None or plan.channel is None:
            raise ChallengeRejectedError("physical setup is not expected")
        binding = PhysicalSetupBinding(
            probe_target_identity=plan.probe_target_identity,
            operation_plan_identity=plan.identity,
            channel=plan.channel,
            maximum_expected_voltage_v=float(maximum_expected_voltage_v),
            probe_statement="Probe is connected to the displayed target.",
            ground_statement="Oscilloscope and circuit share a safe common ground.",
            voltage_statement="Signal is within the displayed safe voltage range.",
            wiring_statement="Wiring has not changed since this challenge was opened.",
        )
        return self._issue_challenge(
            workflow_id, expected_revision, ChallengeKind.PHYSICAL_SETUP,
            allowed_frontend, ttl, binding,
            WorkflowState.WAITING_FOR_PHYSICAL_CONFIRMATION,
            EventType.PHYSICAL_CONFIRMATION_REQUIRED,
            allow_same_state=True,
        )

    def answer_physical_setup(
        self,
        connection_id: UUID,
        workflow_id: UUID,
        expected_revision: int,
        challenge_id: UUID,
        nonce: str,
        probe_target_identity: str,
        operation_plan_identity: str,
        channel: int,
        maximum_expected_voltage_v: float,
        probe_connected: bool,
        common_ground_confirmed: bool,
        voltage_range_confirmed: bool,
        wiring_unchanged: bool,
    ) -> WorkflowSession:
        with self._lock:
            challenge, workflow = self._validate_challenge(
                connection_id, workflow_id, expected_revision, challenge_id, nonce,
                ChallengeKind.PHYSICAL_SETUP,
            )
            binding = challenge.binding
            exact = isinstance(binding, PhysicalSetupBinding) and (
                probe_target_identity == binding.probe_target_identity
                and operation_plan_identity == binding.operation_plan_identity
                and channel == binding.channel
                and maximum_expected_voltage_v == binding.maximum_expected_voltage_v
            )
            if not exact or not all((probe_connected, common_ground_confirmed, voltage_range_confirmed, wiring_unchanged)):
                raise ChallengeRejectedError("physical confirmation does not match the current plan")
            self._consume(challenge)
            self._audit_action(workflow, "challenge_answer_validated:physical_setup")
            if self._physical_confirmation_issuer is None:
                raise InteractiveCapabilityUnavailableError(
                    "physical confirmation is deferred to Harness"
                )
            reference = self._physical_confirmation_issuer.issue_physical_confirmation(
                ValidatedPhysicalSetupRequest(
                    workflow.workflow_id, workflow.request_correlation_id,
                    binding, self._clock(),
                )
            )
            updated = replace(
                workflow, revision=workflow.revision + 1,
                state=WorkflowState.READY_TO_EXECUTE,
                pending_challenge_ids=(), physical_confirmation_ref=reference,
            )
            self._save(updated, EventType.WORKFLOW_STATE_CHANGED, "physical_setup_confirmed", "Physical setup was confirmed for this workflow.")
            self._audit_action(updated, "physical_confirmation_issuance_requested")
            return updated

    def cancel_workflow(self, workflow_id: UUID, expected_revision: int, reason: str) -> WorkflowSession:
        with self._lock:
            workflow = self._cas(workflow_id, expected_revision)
            transition_allowed(workflow.state, WorkflowState.CANCELLED, raise_on_error=True)
            self._withdraw(workflow.pending_challenge_ids)
            updated = replace(
                workflow, revision=workflow.revision + 1,
                state=WorkflowState.CANCELLED, pending_challenge_ids=(),
            )
            self._save(updated, EventType.WORKFLOW_CANCELLED, "cancelled", "Workflow was cancelled.")
            self._audit_action(updated, "workflow_cancelled")
            return updated

    def subscribe(self, connection_id: UUID, cursor: int) -> SubscriptionBatch:
        with self._lock:
            connection = self._active_connection(connection_id)
            current = self._next_event_cursor
            if (
                not isinstance(cursor, int)
                or cursor < self._event_base_cursor
                or cursor > current
            ):
                raise InvalidEventCursorError("event cursor is outside the retained range")
            snapshot = self._snapshot_for(connection, current)
            events = tuple(event for event in self._events if event.cursor > cursor)
            return SubscriptionBatch(snapshot, events, current)

    def current_snapshot(self, connection_id: UUID) -> ApplicationSnapshot:
        """Return current state without requiring a retained historical cursor."""
        with self._lock:
            connection = self._active_connection(connection_id)
            return self._snapshot_for(connection, self._next_event_cursor)

    def _snapshot_for(
        self,
        connection: FrontendConnection,
        current: int,
    ) -> ApplicationSnapshot:
        pending = tuple(
            challenge for challenge in self._challenges.values()
            if challenge.challenge_id not in self._consumed_challenges
            and challenge.challenge_id not in self._withdrawn_challenges
            and challenge.application_generation == self._application_session.generation
            and challenge.allowed_frontend_kind is connection.frontend_kind
            and challenge.expires_at > self._clock()
        )
        return ApplicationSnapshot(
            self._application_session, current,
            tuple(self._workflows.values()), pending,
        )

    def _issue_challenge(
        self,
        workflow_id: UUID,
        expected_revision: int,
        kind: ChallengeKind,
        allowed_frontend: FrontendKind,
        ttl: timedelta,
        binding,
        target_state: WorkflowState,
        event_type: EventType,
        *,
        allow_same_state: bool = False,
    ) -> Challenge:
        with self._lock:
            workflow = self._cas(workflow_id, expected_revision)
            if not isinstance(ttl, timedelta) or ttl <= timedelta(0) or ttl > timedelta(minutes=15):
                raise ValueError("challenge ttl must be between zero and fifteen minutes")
            if not (allow_same_state and workflow.state is target_state):
                transition_allowed(workflow.state, target_state, raise_on_error=True)
            self._withdraw(workflow.pending_challenge_ids)
            revision = workflow.revision + 1
            now = self._clock()
            challenge = Challenge(
                challenge_id=uuid4(), kind=kind,
                application_generation=self._application_session.generation,
                workflow_id=workflow.workflow_id, workflow_revision=revision,
                request_correlation_id=workflow.request_correlation_id,
                allowed_frontend_kind=allowed_frontend,
                issued_at=now, expires_at=now + ttl,
                nonce=secrets.token_urlsafe(24), binding=binding,
            )
            self._challenges[challenge.challenge_id] = challenge
            updated = replace(
                workflow, revision=revision, state=target_state,
                pending_challenge_ids=(challenge.challenge_id,),
            )
            self._workflows[workflow.workflow_id] = updated
            self._emit_workflow(updated, event_type, "challenge_required", "User decision is required.", challenge)
            self._audit_action(updated, f"challenge_issued:{kind.value}")
            return challenge

    def _validate_challenge(
        self,
        connection_id: UUID,
        workflow_id: UUID,
        expected_revision: int,
        challenge_id: UUID,
        nonce: str,
        expected_kind: ChallengeKind,
    ) -> tuple[Challenge, WorkflowSession]:
        try:
            connection = self._active_connection(connection_id)
        except FrontendConnectionError as error:
            raise ChallengeRejectedError("frontend connection is not active") from error
        challenge = self._challenges.get(challenge_id)
        if challenge is None or challenge_id in self._consumed_challenges or challenge_id in self._withdrawn_challenges:
            raise ChallengeRejectedError("challenge is unavailable")
        if challenge.kind is not expected_kind:
            raise ChallengeRejectedError("challenge kind mismatch")
        if challenge.application_generation != self._application_session.generation:
            raise ChallengeRejectedError("application generation mismatch")
        if connection.application_generation != challenge.application_generation:
            raise ChallengeRejectedError("frontend generation mismatch")
        if connection.frontend_kind is not challenge.allowed_frontend_kind:
            raise ChallengeRejectedError("frontend kind is not permitted")
        if workflow_id != challenge.workflow_id:
            raise ChallengeRejectedError("workflow mismatch")
        workflow = self._workflows.get(challenge.workflow_id)
        if workflow is None:
            raise ChallengeRejectedError("workflow is unavailable")
        if expected_revision != challenge.workflow_revision or workflow.revision != challenge.workflow_revision:
            raise ChallengeRejectedError("workflow revision is stale")
        if self._clock() >= challenge.expires_at:
            self._withdrawn_challenges.add(challenge.challenge_id)
            raise ChallengeRejectedError("challenge expired")
        if not secrets.compare_digest(nonce, challenge.nonce):
            raise ChallengeRejectedError("challenge nonce mismatch")
        return challenge, workflow

    def _consume(self, challenge: Challenge) -> None:
        if challenge.challenge_id in self._consumed_challenges:
            raise ChallengeRejectedError("challenge was already consumed")
        self._consumed_challenges.add(challenge.challenge_id)

    def _withdraw(self, challenge_ids: tuple[UUID, ...]) -> None:
        self._withdrawn_challenges.update(challenge_ids)

    def _cas(self, workflow_id: UUID, expected_revision: int) -> WorkflowSession:
        workflow = self.get_workflow(workflow_id)
        if workflow.revision != expected_revision:
            raise StaleWorkflowRevisionError("workflow revision does not match")
        return workflow

    def _active_connection(self, connection_id: UUID) -> FrontendConnection:
        connection = self._connections.get(connection_id)
        if connection is None or not connection.connected:
            raise FrontendConnectionError("frontend connection is not active")
        return connection

    def _save(self, workflow: WorkflowSession, event_type: EventType, code: str, message: str) -> None:
        self._workflows[workflow.workflow_id] = workflow
        self._emit_workflow(workflow, event_type, code, message)

    def _emit_workflow(
        self,
        workflow: WorkflowSession,
        event_type: EventType,
        code: str,
        message: str,
        challenge: Challenge | None = None,
    ) -> None:
        self._emit(workflow.workflow_id, workflow.revision, workflow.request_correlation_id, event_type, code, message, challenge)

    def _emit(
        self,
        workflow_id: UUID | None,
        revision: int | None,
        correlation: str,
        event_type: EventType,
        code: str,
        message: str,
        challenge: Challenge | None = None,
    ) -> None:
        self._next_event_cursor += 1
        self._events.append(InteractiveEvent(
            event_id=uuid4(), cursor=self._next_event_cursor,
            application_generation=self._application_session.generation,
            workflow_id=workflow_id, workflow_revision=revision,
            correlation_id=correlation, event_type=event_type,
            occurred_at=self._clock(),
            payload=SafeEventPayload(code, message, challenge),
        ))
        while len(self._events) > self._event_retention:
            removed = self._events.pop(0)
            self._event_base_cursor = removed.cursor

    def _audit_action(self, workflow: WorkflowSession, action: str) -> None:
        self._audit_event(
            workflow.workflow_id,
            workflow.revision,
            workflow.request_correlation_id,
            action,
        )

    def _audit_event(
        self,
        workflow_id: UUID | None,
        workflow_revision: int | None,
        correlation_id: str,
        action: str,
    ) -> None:
        self._audit.append(AuditRecord(
            audit_id=uuid4(), application_generation=self._application_session.generation,
            workflow_id=workflow_id, workflow_revision=workflow_revision,
            correlation_id=correlation_id,
            action=action, occurred_at=self._clock(),
        ))
