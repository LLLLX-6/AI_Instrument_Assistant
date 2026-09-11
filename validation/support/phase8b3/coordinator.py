from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Protocol
from uuid import UUID, uuid4

from ai_instrument_assistant.application.services.design_selection_disambiguation import (
    DesignSelectionCandidateIdentity,
    DesignSelectionCandidateSetBinding,
    TrustedDesignSelectionResolutionStatus,
    build_candidate_set_binding,
    issue_trusted_design_selection_decision,
    resolve_trusted_design_selection,
)
from ai_instrument_assistant.application.services.eda_design_evidence import (
    DesignEvidenceProjection,
    DesignEvidenceProjectionStatus,
    EDADesignEvidenceCaptureService,
    create_user_provided_numeric_target,
)
from ai_instrument_assistant.application.services.engineering_evidence import (
    DeterministicEngineeringComparator,
    EngineeringEvidenceAssembler,
)
from ai_instrument_assistant.application.services.engineering_evidence_workflow import (
    EngineeringEvidenceWorkflow,
    EngineeringEvidenceWorkflowRequest,
    EngineeringEvidenceWorkflowResult,
)
from ai_instrument_assistant.domain.engineering_evidence import (
    ComparisonReason,
    CrossReferenceState,
    DesignEvidenceContext,
    EngineeringMetric,
    TrustedPhysicalConfirmationEvidence,
)
from ai_instrument_assistant.protocol.evidence_binding import EvidenceContractBinding

from .contracts import Phase8B3ValidationContract


SNAPSHOT_LIMITATION = (
    "JLCEDA snapshot identity binds the observed design context only; it is not a "
    "provider revision and does not prove the design remained unchanged before measurement."
)


class ConfirmationAction(StrEnum):
    CONFIRM = "C"
    CANCEL = "X"


class OperationAuthorizationAction(StrEnum):
    AUTHORIZE = "O"
    CANCEL = "X"


class DesignCapturePort(Protocol):
    async def capture(self) -> DesignEvidenceProjection: ...


class TrustedHostInteraction(Protocol):
    async def choose_design_candidate(
        self, binding: DesignSelectionCandidateSetBinding
    ) -> DesignSelectionCandidateIdentity | None: ...

    async def authorize_operation_plan(
        self, prompt: Phase8B3OperationAuthorizationPrompt
    ) -> OperationAuthorizationAction: ...

    async def confirm_probe_connection(
        self, prompt: Phase8B3ProbeConfirmationPrompt
    ) -> ConfirmationAction: ...


class GovernedHardwareExecutor(Protocol):
    async def execute(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class Phase8B3ProbeConfirmationPrompt:
    workflow_id: str
    request_correlation_id: str
    probe_target_id: UUID
    target_ref: str
    display_label: str
    channel: int = 1
    maximum_expected_voltage_v: float = 3.3
    safe_low_voltage_statement: str = "Signal is confirmed safe low voltage."
    common_ground_statement: str = "Probe ground is safely connected to circuit ground."
    wiring_statement: str = "Wiring is checked and will remain unchanged during validation."


@dataclass(frozen=True, slots=True)
class Phase8B3OperationAuthorizationPrompt:
    workflow_id: str
    request_correlation_id: str
    status_operation: str = "hardware.get_status"
    status_budget: int = 1
    pwm_operation: str = "hardware.measure_pwm"
    pwm_channel: int = 1
    pwm_budget: int = 1


@dataclass(frozen=True, slots=True)
class Phase8B3Identities:
    run_id: UUID
    workflow_id: str
    request_correlation_id: str
    decision_id: UUID
    status_scope_id: UUID
    pwm_scope_id: UUID
    confirmation_id: UUID
    measurement_context_id: UUID
    engineering_context_id: UUID
    frequency_evidence_id: UUID
    frequency_target_id: UUID
    duty_evidence_id: UUID
    duty_target_id: UUID

    @classmethod
    def create(cls, uuid_factory: Callable[[], UUID] = uuid4) -> Phase8B3Identities:
        run_id = uuid_factory()
        return cls(
            run_id=run_id,
            workflow_id=f"phase8b3-{run_id}",
            request_correlation_id=f"phase8b3-request-{uuid_factory()}",
            decision_id=uuid_factory(),
            status_scope_id=uuid_factory(),
            pwm_scope_id=uuid_factory(),
            confirmation_id=uuid_factory(),
            measurement_context_id=uuid_factory(),
            engineering_context_id=uuid_factory(),
            frequency_evidence_id=uuid_factory(),
            frequency_target_id=uuid_factory(),
            duty_evidence_id=uuid_factory(),
            duty_target_id=uuid_factory(),
        )


@dataclass(frozen=True, slots=True)
class Phase8B3ValidationResult:
    status: str
    failure_stage: str | None
    failure_code: str | None
    projection: DesignEvidenceProjection | None
    hardware_receipt: Mapping[str, Any] | None
    workflow_result: EngineeringEvidenceWorkflowResult | None
    identities: Phase8B3Identities
    limitations: tuple[str, ...]

    def to_bounded_output(self) -> dict[str, Any]:
        workflow = self.workflow_result
        return {
            "status": self.status,
            "phase": "8B.3",
            "failure": None if self.failure_code is None else {
                "stage": self.failure_stage,
                "code": self.failure_code,
            },
            "run_id": str(self.identities.run_id),
            "design": None if self.projection is None else {
                "provider": self.projection.active_document.document_ref.provider,
                "document_type": self.projection.active_document.document_type,
                "projection_status": self.projection.status.value,
                "target_label": None if self.projection.probe_target is None else (
                    self.projection.probe_target.design_object.display_name
                    or "selected design target"
                ),
                "snapshot_semantics": "observation_identity_only",
            },
            "hardware": self.hardware_receipt,
            "evidence": None if workflow is None else {
                "cross_reference": workflow.engineering_context.cross_references[0].state.value,
                "comparison_statuses": [
                    item.status.value for item in workflow.engineering_context.comparison_results
                ],
                "comparison_reasons": [
                    item.reason.value for item in workflow.engineering_context.comparison_results
                ],
                "engineering_inference_count": len(workflow.engineering_context.inferences),
                "teaching_inference_count": len(workflow.teaching_context.inferences),
                "candidate_next_measurement_count": len(
                    workflow.teaching_context.candidate_next_measurements
                ),
            },
            "limitations": list(self.limitations),
            "model_request_count": 0,
        }


class Phase8B3Coordinator:
    """Trusted validation orchestration; all hardware governance stays in Node."""

    def __init__(
        self,
        *,
        capture: DesignCapturePort,
        host: TrustedHostInteraction,
        hardware: GovernedHardwareExecutor,
        repository_root: Path,
        clock: Callable[[], datetime] | None = None,
        identity_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._capture = capture
        self._host = host
        self._hardware = hardware
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._identities = Phase8B3Identities.create(identity_factory)
        self._contract = Phase8B3ValidationContract.from_repository(repository_root)
        self._evidence = EvidenceContractBinding.from_repository(repository_root)
        self._workflow = EngineeringEvidenceWorkflow(
            assembler=EngineeringEvidenceAssembler(),
            comparator=DeterministicEngineeringComparator(),
        )

    async def run(self) -> Phase8B3ValidationResult:
        projection: DesignEvidenceProjection | None = None
        receipt: Mapping[str, Any] | None = None
        try:
            projection = await self._capture.capture()
            projection = await self._resolve_projection(projection)
            if (
                projection.status is not DesignEvidenceProjectionStatus.PROJECTED
                or projection.probe_target is None
            ):
                return self._failed("design", "probe_target_unavailable", projection, None)

            probe = projection.probe_target
            operation_plan = Phase8B3OperationAuthorizationPrompt(
                workflow_id=self._identities.workflow_id,
                request_correlation_id=self._identities.request_correlation_id,
            )
            if await self._host.authorize_operation_plan(
                operation_plan
            ) is not OperationAuthorizationAction.AUTHORIZE:
                return self._failed("operation_authorization", "cancelled", projection, None)
            prompt = Phase8B3ProbeConfirmationPrompt(
                workflow_id=self._identities.workflow_id,
                request_correlation_id=self._identities.request_correlation_id,
                probe_target_id=probe.target_id,
                target_ref=probe.design_object.canonical_id,
                display_label=probe.design_object.display_name or "selected design target",
            )
            if await self._host.confirm_probe_connection(prompt) is not ConfirmationAction.CONFIRM:
                return self._failed("physical_confirmation", "cancelled", projection, None)
            confirmed_at = self._aware_now()
            request = self._hardware_request(projection, confirmed_at)
            self._contract.validate_request(request)

            raw_receipt = await self._hardware.execute(request)
            try:
                receipt = self._contract.validate_receipt(raw_receipt)
            except Exception:
                return self._failed(
                    "hardware", "receipt_semantics_invalid", projection, None
                )
            if (
                receipt["workflow_id"] != self._identities.workflow_id
                or receipt["request_correlation_id"] != self._identities.request_correlation_id
                or receipt["run_id"] != str(self._identities.run_id)
            ):
                return self._failed("hardware", "receipt_identity_mismatch", projection, receipt)
            if not _receipt_execution_is_coherent(receipt, request):
                return self._failed("hardware", "receipt_semantics_invalid", projection, receipt)
            if receipt["status"] != "COMPLETED" or receipt["pwm_teaching_evidence"] is None:
                return self._failed("hardware", str(receipt["failure_code"] or "execution_failed"), projection, receipt)

            teaching = self._evidence.parse_teaching_context(
                _thaw(receipt["pwm_teaching_evidence"])
            )
            measured_at = _pwm_completed_at(receipt)
            if measured_at < confirmed_at:
                return self._failed("hardware", "measurement_predates_confirmation", projection, receipt)
            result = self._assemble(projection, teaching, confirmed_at, measured_at)
            link = result.engineering_context.cross_references
            comparisons = result.engineering_context.comparison_results
            if len(link) != 1 or link[0].state is not CrossReferenceState.VERIFIED_LINK:
                return self._failed("workflow", "cross_reference_not_verified", projection, receipt)
            if any(item.reason is not ComparisonReason.TOLERANCE_UNSPECIFIED for item in comparisons):
                return self._failed("workflow", "unexpected_comparison_semantics", projection, receipt)
            if (
                result.engineering_context.inferences
                or result.teaching_context.inferences
                or result.teaching_context.candidate_next_measurements
            ):
                return self._failed("workflow", "unexpected_inference", projection, receipt)
            return Phase8B3ValidationResult(
                status="PASS",
                failure_stage=None,
                failure_code=None,
                projection=projection,
                hardware_receipt=_safe_receipt_summary(receipt),
                workflow_result=result,
                identities=self._identities,
                limitations=tuple(dict.fromkeys((*projection.limitations, SNAPSHOT_LIMITATION))),
            )
        except Exception:
            return self._failed("coordinator", "bounded_failure", projection, receipt)

    async def _resolve_projection(self, projection: DesignEvidenceProjection) -> DesignEvidenceProjection:
        if projection.status is not DesignEvidenceProjectionStatus.AMBIGUOUS_SELECTION:
            return projection
        selection = projection.design_context.selection
        if selection is None:
            return projection
        observed_at = min(item.observed_at for item in projection.design_context.evidence)
        binding = build_candidate_set_binding(
            selection_context=selection,
            selection_observed_at=observed_at,
        )
        selected = await self._host.choose_design_candidate(binding)
        if selected is None:
            return projection
        decided_at = self._aware_now()
        decision = issue_trusted_design_selection_decision(
            decision_id=self._identities.decision_id,
            candidate_binding=binding,
            selected_candidate=selected,
            workflow_id=self._identities.workflow_id,
            request_correlation_id=self._identities.request_correlation_id,
            decided_at=decided_at,
        )
        resolution = resolve_trusted_design_selection(
            current_selection=selection,
            current_binding=binding,
            decision=decision,
            trusted_workflow_id=self._identities.workflow_id,
            trusted_request_correlation_id=self._identities.request_correlation_id,
        )
        if resolution.status is not TrustedDesignSelectionResolutionStatus.RESOLVED:
            return projection
        return EDADesignEvidenceCaptureService.project(
            active_document=projection.active_document,
            selection_context=selection,
            observed_at=observed_at,
            trusted_resolution=resolution,
        )

    def _hardware_request(self, projection: DesignEvidenceProjection, confirmed_at: datetime) -> dict[str, Any]:
        probe = projection.probe_target
        assert probe is not None
        common_scope = {
            "workflow_id": self._identities.workflow_id,
            "request_correlation_id": self._identities.request_correlation_id,
            "max_invocations": 1,
            "origin": "TRUSTED_VALIDATION_SCENARIO",
        }
        return {
            "contract": "aia-phase8b3-validation",
            "contract_version": "1.0",
            "kind": "governed_hardware_request",
            "run_id": str(self._identities.run_id),
            "workflow_id": self._identities.workflow_id,
            "request_correlation_id": self._identities.request_correlation_id,
            "backend": {
                "endpoint": "ws://127.0.0.1:49625",
                "auth_reference": "default-harness-hardware-secret",
                "connect_timeout_ms": 2000,
                "request_timeout_ms": 30000,
            },
            "target": {
                "provider": probe.design_object.provider,
                "document_canonical_id": projection.design_context.document.document_ref.canonical_id,
                "snapshot_id": str(probe.snapshot_id),
                "probe_target_id": str(probe.target_id),
                "target_ref": probe.design_object.canonical_id,
                "display_label": probe.design_object.display_name or "selected design target",
            },
            "status_scope": {
                **common_scope,
                "scope_id": str(self._identities.status_scope_id),
                "operation": "hardware.get_status",
                "target_channel": None,
                "authorization_ref": "trusted-host-status-authorization",
            },
            "pwm_scope": {
                **common_scope,
                "scope_id": str(self._identities.pwm_scope_id),
                "operation": "hardware.measure_pwm",
                "target_channel": 1,
                "authorization_ref": "trusted-host-pwm-authorization",
            },
            "confirmation": {
                "confirmation_id": str(self._identities.confirmation_id),
                "source": "TRUSTED_USER_EVENT",
                "confirmed_by": "bounded-host-action:C",
                "workflow_id": self._identities.workflow_id,
                "request_correlation_id": self._identities.request_correlation_id,
                "channel": 1,
                "target_ref": probe.design_object.canonical_id,
                "maximum_expected_voltage_v": 3.3,
                "safe_low_voltage_confirmed": True,
                "common_ground_confirmed": True,
                "wiring_checked": True,
                "wiring_unchanged": True,
                "confirmed_at": _timestamp(confirmed_at),
            },
        }

    def _assemble(self, projection, teaching, confirmed_at, measured_at):
        probe = projection.probe_target
        assert probe is not None
        frequency = create_user_provided_numeric_target(
            evidence_id=self._identities.frequency_evidence_id,
            target_id=self._identities.frequency_target_id,
            document=projection.design_context.document,
            design_object=probe.design_object,
            observed_at=confirmed_at,
            label="PWM_OUT expected frequency from trusted user context",
            metric=EngineeringMetric.FREQUENCY,
            value=10.0,
            unit="kHz",
            tolerance=None,
        )
        duty = create_user_provided_numeric_target(
            evidence_id=self._identities.duty_evidence_id,
            target_id=self._identities.duty_target_id,
            document=projection.design_context.document,
            design_object=probe.design_object,
            observed_at=confirmed_at,
            label="PWM_OUT expected duty cycle from trusted user context",
            metric=EngineeringMetric.DUTY_CYCLE,
            value=30.0,
            unit="percent",
            tolerance=None,
        )
        design = DesignEvidenceContext(
            document=projection.design_context.document,
            evidence=projection.design_context.evidence + (frequency.evidence, duty.evidence),
            probe_targets=projection.design_context.probe_targets,
            selection=projection.design_context.selection,
        )
        confirmation = TrustedPhysicalConfirmationEvidence(
            confirmation_id=str(self._identities.confirmation_id),
            source="TRUSTED_USER_EVENT",
            confirmed_by="bounded-host-action:C",
            workflow_id=self._identities.workflow_id,
            request_correlation_id=self._identities.request_correlation_id,
            channel=1,
            target_ref=probe.design_object.canonical_id,
            design_snapshot_id=probe.snapshot_id,
            probe_target_id=probe.target_id,
            safe_low_voltage_confirmed=True,
            common_ground_confirmed=True,
            wiring_unchanged=True,
            confirmed_at=confirmed_at,
        )
        assembled_at = max(self._aware_now(), measured_at + timedelta(microseconds=1))
        return self._workflow.execute(EngineeringEvidenceWorkflowRequest(
            context_id=self._identities.engineering_context_id,
            workflow_id=self._identities.workflow_id,
            request_correlation_id=self._identities.request_correlation_id,
            user_goal="Compare observed JLCEDA PWM_OUT context with governed PWM evidence",
            assembled_at=assembled_at,
            design_context=design,
            targets=(frequency.target, duty.target),
            probe_target=probe,
            confirmation=confirmation,
            measurement_context_id=self._identities.measurement_context_id,
            measurement_context=teaching,
            measurement_channel=1,
            measured_at=measured_at,
        ))

    def _failed(self, stage, code, projection, receipt) -> Phase8B3ValidationResult:
        return Phase8B3ValidationResult(
            status="NOT_PASS",
            failure_stage=stage,
            failure_code=code,
            projection=projection,
            hardware_receipt=_safe_receipt_summary(receipt),
            workflow_result=None,
            identities=self._identities,
            limitations=(SNAPSHOT_LIMITATION,),
        )

    def _aware_now(self) -> datetime:
        value = self._clock()
        if value.utcoffset() is None:
            raise ValueError("clock must return timezone-aware timestamps")
        return value


def _pwm_completed_at(receipt: Mapping[str, Any]) -> datetime:
    operations = receipt["operations"]
    pwm = next(item for item in operations if item["operation"] == "hardware.measure_pwm")
    value = pwm["execution_completed_at"]
    if not isinstance(value, str):
        raise ValueError("completed PWM receipt requires an execution completion timestamp")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _receipt_execution_is_coherent(
    receipt: Mapping[str, Any], request: Mapping[str, Any]
) -> bool:
    if receipt["status"] != "COMPLETED":
        return True
    operations = receipt["operations"]
    if len(operations) != 2:
        return False
    target = request["target"]
    expected = (
        ("hardware.get_status", None),
        ("hardware.measure_pwm", 1),
    )
    for item, (operation, channel) in zip(operations, expected, strict=True):
        scope = item["scope_decision"]
        policy = item["policy_decision"]
        canonical = item["canonical_result"]
        if (
            item["operation"] != operation
            or item["channel"] != channel
            or item["delivery_state"] != "RESPONSE_RECEIVED"
            or item["ipc_dispatch_count"] != 1
            or item["hardware_execution_count"] != 1
            or scope is None
            or scope["decision"] != "ALLOW"
            or scope["remaining_invocations"] != 0
            or policy is None
            or policy["decision"] != "ALLOW"
            or canonical is None
            or canonical.get("ok") is not True
            or canonical.get("operation") != operation
        ):
            return False
        if operation == "hardware.measure_pwm":
            result = canonical.get("result")
            if (
                not isinstance(result, Mapping)
                or result.get("channel") != 1
                or result.get("context_id") != target["target_ref"]
            ):
                return False
    return receipt["pwm_teaching_evidence"] is not None


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _thaw(value: Any) -> Any:
    """Copy one already-validated frozen value for a second schema boundary."""

    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _safe_receipt_summary(receipt: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if receipt is None:
        return None
    operations = []
    for item in receipt.get("operations", ()):
        operations.append({
            "operation": item["operation"],
            "channel": item["channel"],
            "delivery_state": item["delivery_state"],
            "scope_decision": _thaw(item["scope_decision"]),
            "policy_decision": _thaw(item["policy_decision"]),
            "ipc_dispatch_count": item["ipc_dispatch_count"],
            "hardware_execution_count": item["hardware_execution_count"],
            "failure_code": item["failure_code"],
        })
    return {
        "status": receipt.get("status"),
        "operations": operations,
        "failure_code": receipt.get("failure_code"),
    }
