from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from uuid import NAMESPACE_URL, UUID, uuid5

from ..ports.eda_interface import (
    EDACapability,
    EDAInterface,
    InconsistentDesignObservationError,
    ScopeExpansion,
)
from ...domain.eda.models import (
    DesignDocument,
    DesignObjectKind,
    DesignObjectRef,
    ProbeTarget,
    ProbeTargetKind,
    SelectionContext,
)
from ...domain.engineering_evidence import (
    AbsoluteTolerance,
    DesignEvidenceContext,
    DesignEvidenceItem,
    DesignEvidenceKind,
    DesignEvidenceOrigin,
    EngineeringMetric,
    EngineeringTarget,
    ExactNumericExpectation,
    Quantity,
    RelativeTolerance,
    TargetProvenance,
    VerificationState,
)
from ...domain.errors import DomainInvariantError
from .design_selection_disambiguation import (
    TrustedDesignSelectionResolution,
    TrustedDesignSelectionResolutionStatus,
)


class DesignEvidenceProjectionStatus(StrEnum):
    PROJECTED = "PROJECTED"
    EMPTY_SELECTION = "EMPTY_SELECTION"
    UNSUPPORTED_SELECTION = "UNSUPPORTED_SELECTION"
    AMBIGUOUS_SELECTION = "AMBIGUOUS_SELECTION"


class ProjectionResolutionStage(StrEnum):
    SELECTION_CARDINALITY = "selection_cardinality"
    SELECTED_OBJECT_KIND = "selected_object_kind"
    WIRE_NET_RESOLUTION = "wire_net_resolution"
    RESOLVED = "resolved"


class ProjectionDiagnosticReason(StrEnum):
    EMPTY_SELECTION = "empty_selection"
    MULTIPLE_SELECTED_OBJECTS = "multiple_selected_objects"
    SELECTED_NET = "selected_net"
    WIRE_TO_SINGLE_DERIVED_NET = "wire_to_single_derived_net"
    WIRE_NET_UNRESOLVED = "wire_net_unresolved"
    WIRE_MULTIPLE_DERIVED_NETS = "wire_multiple_derived_nets"
    UNSUPPORTED_SELECTED_OBJECT = "unsupported_selected_object"


@dataclass(frozen=True, slots=True)
class SelectionProjectionDiagnostic:
    """Finite provider-neutral metadata explaining one projection decision."""

    selection_count: int
    provider_kinds: tuple[str, ...]
    selected_references: tuple[DesignObjectRef, ...]
    derived_net_count: int
    projected_candidates: tuple[DesignObjectRef, ...]
    reason: ProjectionDiagnosticReason
    resolution_stage: ProjectionResolutionStage
    scope_expansion: ScopeExpansion

    def __post_init__(self) -> None:
        if self.selection_count != len(self.selected_references):
            raise DomainInvariantError("selection diagnostic count must match references")
        if len(self.provider_kinds) != self.selection_count:
            raise DomainInvariantError("provider kind count must match selection count")
        if self.derived_net_count < 0:
            raise DomainInvariantError("derived net count cannot be negative")
        if len(self.projected_candidates) != len(set(self.projected_candidates)):
            raise DomainInvariantError("projected diagnostic candidates must be unique")

    @property
    def projected_candidate_count(self) -> int:
        return len(self.projected_candidates)

    @property
    def projected_candidate_kinds(self) -> tuple[DesignObjectKind, ...]:
        return tuple(candidate.object_type for candidate in self.projected_candidates)

    @property
    def is_ambiguous(self) -> bool:
        return self.reason in {
            ProjectionDiagnosticReason.MULTIPLE_SELECTED_OBJECTS,
            ProjectionDiagnosticReason.WIRE_MULTIPLE_DERIVED_NETS,
        }


@dataclass(frozen=True, slots=True)
class DesignEvidenceProjection:
    """Bounded EDA observation projected without provider runtime objects."""

    status: DesignEvidenceProjectionStatus
    active_document: DesignDocument
    design_context: DesignEvidenceContext
    source_object: DesignObjectRef | None
    probe_target: ProbeTarget | None
    limitations: tuple[str, ...]
    trusted_selection_resolution: TrustedDesignSelectionResolution | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, DesignEvidenceProjectionStatus):
            raise DomainInvariantError("status must be DesignEvidenceProjectionStatus")
        limitations = tuple(self.limitations)
        if not all(isinstance(value, str) and value.strip() for value in limitations):
            raise DomainInvariantError("limitations must contain non-empty text")
        if len(limitations) != len(set(limitations)):
            raise DomainInvariantError("limitations must be unique")
        if self.status is DesignEvidenceProjectionStatus.PROJECTED:
            if self.source_object is None or self.probe_target is None:
                raise DomainInvariantError("projected selection requires source object and probe target")
        elif self.probe_target is not None:
            raise DomainInvariantError("non-projected selection cannot claim a probe target")
        if self.trusted_selection_resolution is not None:
            resolution = self.trusted_selection_resolution
            if not isinstance(resolution, TrustedDesignSelectionResolution):
                raise DomainInvariantError("trusted selection resolution has invalid type")
            if resolution.status is not TrustedDesignSelectionResolutionStatus.RESOLVED:
                raise DomainInvariantError("projection can retain only a resolved trusted decision")
            if resolution.provider_selection != self.design_context.selection:
                raise DomainInvariantError("trusted resolution must preserve provider selection")
            if (
                resolution.chosen_candidate != self.source_object
                or resolution.probe_target != self.probe_target
            ):
                raise DomainInvariantError("trusted resolution and projection derivation differ")
        object.__setattr__(self, "limitations", limitations)


@dataclass(frozen=True, slots=True)
class UserProvidedNumericTarget:
    evidence: DesignEvidenceItem
    target: EngineeringTarget

    def __post_init__(self) -> None:
        if self.evidence.origin is not DesignEvidenceOrigin.USER_STATEMENT:
            raise DomainInvariantError("user target evidence must remain USER_STATEMENT")
        if self.target.provenance is not TargetProvenance.USER_PROVIDED:
            raise DomainInvariantError("user target must remain USER_PROVIDED")
        if self.target.source_evidence_ids != (self.evidence.evidence_id,):
            raise DomainInvariantError("user target must reference its declaration evidence")


class EDADesignEvidenceCaptureService:
    """Read-only provider-neutral projection from EDA selection to design evidence."""

    def __init__(
        self,
        *,
        eda: EDAInterface,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._eda = eda
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    async def capture(self) -> DesignEvidenceProjection:
        self._eda.capabilities.require(EDACapability.DOCUMENT_READ)
        self._eda.capabilities.require(EDACapability.SELECTION_READ)
        active_document = await self._eda.get_active_document()
        selection_context = await self._eda.get_selection()
        observed_at = self._clock()
        if not isinstance(observed_at, datetime) or observed_at.utcoffset() is None:
            raise DomainInvariantError("capture clock must return a timezone-aware datetime")
        return self.project(
            active_document=active_document,
            selection_context=selection_context,
            observed_at=observed_at,
        )

    @staticmethod
    def project(
        *,
        active_document: DesignDocument,
        selection_context: SelectionContext,
        observed_at: datetime,
        trusted_resolution: TrustedDesignSelectionResolution | None = None,
    ) -> DesignEvidenceProjection:
        active_ref = active_document.document_ref
        selection_ref = selection_context.selection.document_ref
        if (
            active_ref.provider,
            active_ref.document_id,
            active_ref.canonical_id,
        ) != (
            selection_ref.provider,
            selection_ref.document_id,
            selection_ref.canonical_id,
        ):
            raise InconsistentDesignObservationError(
                "active document and selection document identity differ"
            )

        limitations: list[str] = []
        selection_document = active_document
        if active_document.snapshot_id != selection_context.snapshot_id:
            selection_document = replace(
                active_document,
                document_ref=selection_ref,
                native_revision=None,
                fingerprint=None,
                is_dirty=None,
                captured_at=observed_at,
            )
            limitations.append(
                "Document and selection are separate bounded observations; "
                "the selection snapshot is not an atomic provider revision."
            )

        evidence = [
            DesignEvidenceItem(
                evidence_id=_stable_id(
                    "document-fact",
                    selection_ref.provider,
                    selection_ref.canonical_id,
                    str(selection_ref.snapshot_id),
                ),
                kind=DesignEvidenceKind.DOCUMENT_FACT,
                label="active design document type",
                value=selection_document.document_type,
                unit=None,
                document=selection_document,
                design_object=selection_ref,
                verification_state=VerificationState.SNAPSHOT_BOUNDED,
                observed_at=observed_at,
                origin=DesignEvidenceOrigin.DESIGN_DERIVED,
            )
        ]

        if trusted_resolution is None:
            status, source_object, probe_ref = _probe_candidate(selection_context)
            probe_target = None
        else:
            if not isinstance(trusted_resolution, TrustedDesignSelectionResolution):
                raise DomainInvariantError("trusted_resolution has invalid type")
            if trusted_resolution.status is not TrustedDesignSelectionResolutionStatus.RESOLVED:
                raise DomainInvariantError("trusted_resolution must be RESOLVED")
            if trusted_resolution.provider_selection != selection_context:
                raise DomainInvariantError(
                    "trusted resolution must belong to the current provider selection"
                )
            if trusted_resolution.candidate_binding.document_ref != selection_ref:
                raise DomainInvariantError(
                    "trusted resolution must belong to the current selection snapshot"
                )
            status = DesignEvidenceProjectionStatus.PROJECTED
            source_object = trusted_resolution.chosen_candidate
            probe_ref = trusted_resolution.derived_target
            probe_target = trusted_resolution.probe_target
        if probe_ref is not None and source_object is not None:
            if probe_target is None:
                probe_target = ProbeTarget(
                    target_id=_stable_id(
                        "probe-target",
                        probe_ref.provider,
                        probe_ref.canonical_id,
                        str(probe_ref.snapshot_id),
                    ),
                    design_object=probe_ref,
                    kind=ProbeTargetKind.DESIGN_ONLY,
                )
            evidence.append(
                DesignEvidenceItem(
                    evidence_id=_stable_id(
                        "connectivity-fact",
                        probe_ref.provider,
                        probe_ref.canonical_id,
                        str(probe_ref.snapshot_id),
                    ),
                    kind=DesignEvidenceKind.CONNECTIVITY_FACT,
                    label="selected design net",
                    value=probe_ref.display_name or probe_ref.canonical_id,
                    unit=None,
                    document=selection_document,
                    design_object=probe_ref,
                    verification_state=VerificationState.SNAPSHOT_BOUNDED,
                    observed_at=observed_at,
                    origin=DesignEvidenceOrigin.DESIGN_DERIVED,
                )
            )
            limitations.append(
                "The selected net is a design-side probe candidate, not physical confirmation."
            )
            if trusted_resolution is not None:
                limitations.append(
                    "The provider selection remained ambiguous; a trusted Host user "
                    "decision selected one observed source object for this workflow."
                )
        elif status is DesignEvidenceProjectionStatus.EMPTY_SELECTION:
            limitations.append("No selected design object was observed.")
        elif status is DesignEvidenceProjectionStatus.AMBIGUOUS_SELECTION:
            limitations.append("Selection is ambiguous; no probe target was chosen.")
        else:
            limitations.append("The selected object cannot produce a supported probe target.")

        design_context = DesignEvidenceContext(
            document=selection_document,
            evidence=tuple(evidence),
            probe_targets=() if probe_target is None else (probe_target,),
            selection=selection_context,
        )
        return DesignEvidenceProjection(
            status=status,
            active_document=active_document,
            design_context=design_context,
            source_object=source_object,
            probe_target=probe_target,
            limitations=tuple(limitations),
            trusted_selection_resolution=trusted_resolution,
        )


def create_user_provided_numeric_target(
    *,
    evidence_id: UUID,
    target_id: UUID,
    document: DesignDocument,
    design_object: DesignObjectRef,
    observed_at: datetime,
    label: str,
    metric: EngineeringMetric,
    value: float,
    unit: str,
    tolerance: AbsoluteTolerance | RelativeTolerance | None,
) -> UserProvidedNumericTarget:
    """Create explicit user context without relabeling it as EDA-derived."""

    quantity = Quantity(value=value, unit=unit)
    evidence = DesignEvidenceItem(
        evidence_id=evidence_id,
        kind=DesignEvidenceKind.TARGET_DECLARATION,
        label=label,
        value=quantity,
        unit=unit,
        document=document,
        design_object=design_object,
        verification_state=VerificationState.USER_ASSERTED,
        observed_at=observed_at,
        origin=DesignEvidenceOrigin.USER_STATEMENT,
    )
    target = EngineeringTarget(
        target_id=target_id,
        metric=metric,
        expectation=ExactNumericExpectation(quantity),
        tolerance=tolerance,
        provenance=TargetProvenance.USER_PROVIDED,
        source_evidence_ids=(evidence_id,),
    )
    return UserProvidedNumericTarget(evidence=evidence, target=target)


def diagnose_selection_projection(
    context: SelectionContext,
) -> SelectionProjectionDiagnostic:
    """Explain projection using only already-bounded Domain references."""

    selected = context.selection.selected_objects
    provider_kinds = tuple(
        selected_object.provider_kind or selected_object.object_type.value
        for selected_object in selected
    )

    candidates: list[DesignObjectRef] = [
        selected_object
        for selected_object in selected
        if selected_object.object_type is DesignObjectKind.NET
    ]
    for net in context.nets:
        if net.ref not in candidates:
            candidates.append(net.ref)

    scope_expansion = (
        ScopeExpansion.WIRE_TO_NET
        if context.nets
        and any(
            selected_object.object_type is DesignObjectKind.WIRE
            for selected_object in selected
        )
        else ScopeExpansion.NONE
    )

    if not selected:
        reason = ProjectionDiagnosticReason.EMPTY_SELECTION
        stage = ProjectionResolutionStage.SELECTION_CARDINALITY
    elif len(selected) != 1:
        reason = ProjectionDiagnosticReason.MULTIPLE_SELECTED_OBJECTS
        stage = ProjectionResolutionStage.SELECTION_CARDINALITY
    else:
        source = selected[0]
        if source.object_type is DesignObjectKind.NET:
            reason = ProjectionDiagnosticReason.SELECTED_NET
            stage = ProjectionResolutionStage.RESOLVED
        elif source.object_type is DesignObjectKind.WIRE and len(context.nets) == 1:
            reason = ProjectionDiagnosticReason.WIRE_TO_SINGLE_DERIVED_NET
            stage = ProjectionResolutionStage.RESOLVED
        elif source.object_type is DesignObjectKind.WIRE and len(context.nets) > 1:
            reason = ProjectionDiagnosticReason.WIRE_MULTIPLE_DERIVED_NETS
            stage = ProjectionResolutionStage.WIRE_NET_RESOLUTION
        elif source.object_type is DesignObjectKind.WIRE:
            reason = ProjectionDiagnosticReason.WIRE_NET_UNRESOLVED
            stage = ProjectionResolutionStage.WIRE_NET_RESOLUTION
        else:
            reason = ProjectionDiagnosticReason.UNSUPPORTED_SELECTED_OBJECT
            stage = ProjectionResolutionStage.SELECTED_OBJECT_KIND

    return SelectionProjectionDiagnostic(
        selection_count=len(selected),
        provider_kinds=provider_kinds,
        selected_references=selected,
        derived_net_count=len(context.nets),
        projected_candidates=tuple(candidates),
        reason=reason,
        resolution_stage=stage,
        scope_expansion=scope_expansion,
    )


def _probe_candidate(
    context: SelectionContext,
) -> tuple[DesignEvidenceProjectionStatus, DesignObjectRef | None, DesignObjectRef | None]:
    selected = context.selection.selected_objects
    if not selected:
        return DesignEvidenceProjectionStatus.EMPTY_SELECTION, None, None
    if len(selected) != 1:
        return DesignEvidenceProjectionStatus.AMBIGUOUS_SELECTION, None, None
    source = selected[0]
    if source.object_type is DesignObjectKind.NET:
        return DesignEvidenceProjectionStatus.PROJECTED, source, source
    if source.object_type is DesignObjectKind.WIRE:
        if len(context.nets) == 1:
            return DesignEvidenceProjectionStatus.PROJECTED, source, context.nets[0].ref
        if len(context.nets) > 1:
            return DesignEvidenceProjectionStatus.AMBIGUOUS_SELECTION, source, None
    return DesignEvidenceProjectionStatus.UNSUPPORTED_SELECTION, source, None


def _stable_id(*parts: str) -> UUID:
    return uuid5(NAMESPACE_URL, "/".join(("ai-instrument-assistant", *parts)))
