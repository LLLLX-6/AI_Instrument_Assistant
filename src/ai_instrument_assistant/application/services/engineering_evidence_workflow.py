from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from ..ports.engineering_comparator import EngineeringComparator
from ...domain.eda.models import ProbeTarget
from ...domain.engineering_evidence import (
    ComparisonResult,
    DesignEvidenceContext,
    EngineeringEvidenceContext,
    EngineeringTarget,
    EvidenceCategory,
    TeachingDiagnosisContext,
    TeachingEvidenceContext,
    TrustedPhysicalConfirmationEvidence,
)
from ...domain.errors import DomainInvariantError
from .engineering_evidence import (
    EngineeringEvidenceAssembler,
    establish_evidence_cross_reference,
    locate_measurement_evidence,
    project_teaching_diagnosis,
)


@dataclass(frozen=True, slots=True)
class EngineeringEvidenceWorkflowRequest:
    context_id: UUID
    workflow_id: str
    request_correlation_id: str
    user_goal: str
    assembled_at: datetime
    design_context: DesignEvidenceContext | None
    targets: tuple[EngineeringTarget, ...]
    probe_target: ProbeTarget | None
    confirmation: TrustedPhysicalConfirmationEvidence | None
    measurement_context_id: UUID | None
    measurement_context: TeachingEvidenceContext | None
    measurement_channel: int | None
    measured_at: datetime | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "targets", tuple(self.targets))
        if not isinstance(self.context_id, UUID):
            raise DomainInvariantError("context_id must be UUID")
        for name in ("workflow_id", "request_correlation_id", "user_goal"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise DomainInvariantError(f"{name} must be non-empty text")
        if not isinstance(self.assembled_at, datetime) or self.assembled_at.utcoffset() is None:
            raise DomainInvariantError("assembled_at must be timezone-aware")
        has_measurement = self.measurement_context is not None
        required_measurement_metadata = (
            self.measurement_context_id,
            self.measurement_channel,
            self.measured_at,
        )
        if (
            has_measurement
            and not all(value is not None for value in required_measurement_metadata)
        ) or (
            not has_measurement
            and any(value is not None for value in required_measurement_metadata)
        ):
            raise DomainInvariantError(
                "measurement context, identifier, channel, and observation time must be present together"
            )
        if self.measurement_context_id is not None and not isinstance(
            self.measurement_context_id, UUID
        ):
            raise DomainInvariantError("measurement_context_id must be UUID")
        if self.measurement_channel is not None and (
            isinstance(self.measurement_channel, bool) or self.measurement_channel not in (1, 2)
        ):
            raise DomainInvariantError("measurement_channel must be 1 or 2")
        if self.measured_at is not None:
            if not isinstance(self.measured_at, datetime) or self.measured_at.utcoffset() is None:
                raise DomainInvariantError("measured_at must be timezone-aware")
            if self.measured_at > self.assembled_at:
                raise DomainInvariantError("assembly cannot precede the recorded measurement")
        if self.design_context is not None and self.probe_target is not None:
            if self.probe_target not in self.design_context.probe_targets:
                raise DomainInvariantError("probe target must belong to the design evidence context")


@dataclass(frozen=True, slots=True)
class EngineeringEvidenceWorkflowResult:
    engineering_context: EngineeringEvidenceContext
    teaching_context: TeachingDiagnosisContext


class EngineeringEvidenceWorkflow:
    """Deterministic orchestration only; it has no diagnosis or execution authority."""

    def __init__(
        self,
        *,
        assembler: EngineeringEvidenceAssembler,
        comparator: EngineeringComparator,
    ) -> None:
        self._assembler = assembler
        self._comparator = comparator

    def execute(
        self,
        request: EngineeringEvidenceWorkflowRequest,
    ) -> EngineeringEvidenceWorkflowResult:
        self._assembler.validate_design_and_targets(
            design_context=request.design_context,
            targets=request.targets,
        )

        cross_reference = None
        if request.measurement_context is not None:
            cross_reference = establish_evidence_cross_reference(
                cross_reference_id=_cross_reference_id(request.context_id),
                workflow_id=request.workflow_id,
                request_correlation_id=request.request_correlation_id,
                probe_target=request.probe_target,
                confirmation=request.confirmation,
                measurement_context_id=request.measurement_context_id,
                measurement_channel=request.measurement_channel,
                measured_at=request.measured_at,
            )

        located = (
            ()
            if request.measurement_context is None
            else locate_measurement_evidence(
                request.measurement_context_id,
                request.measurement_context,
            )
        )
        comparisons: list[ComparisonResult] = []
        for target in request.targets:
            compatible = tuple(
                evidence
                for evidence in located
                if evidence.locator.metric is target.metric
                and evidence.locator.category is not EvidenceCategory.INFERENCE
            )
            if not compatible:
                comparisons.append(
                    self._comparator.compare(
                        target=target,
                        observed=None,
                        observed_ref=None,
                        cross_reference=cross_reference,
                    )
                )
                continue
            for evidence in compatible:
                comparisons.append(
                    self._comparator.compare(
                        target=target,
                        observed=evidence.item,
                        observed_ref=evidence.locator,
                        cross_reference=cross_reference,
                    )
                )

        engineering_context = self._assembler.assemble(
            context_id=request.context_id,
            workflow_id=request.workflow_id,
            user_goal=request.user_goal,
            assembled_at=request.assembled_at,
            design_context=request.design_context,
            targets=request.targets,
            measurement_context_id=request.measurement_context_id,
            measurement_context=request.measurement_context,
            cross_references=() if cross_reference is None else (cross_reference,),
            comparison_results=tuple(comparisons),
        )
        teaching_context = project_teaching_diagnosis(engineering_context)
        return EngineeringEvidenceWorkflowResult(engineering_context, teaching_context)


def _cross_reference_id(context_id: UUID) -> UUID:
    """Derive a stable idempotent record identity without claiming evidence content."""

    return UUID(int=context_id.int ^ 0x8B1)
