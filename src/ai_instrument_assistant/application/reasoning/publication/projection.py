from __future__ import annotations

from dataclasses import asdict

from ai_instrument_assistant.domain.eda import DutyCycle
from ai_instrument_assistant.domain.engineering_evidence import (
    AbsoluteTolerance,
    ComparisonResult,
    DesignEvidenceItem,
    DesignEvidenceOrigin,
    DiscreteExpectation,
    EngineeringTarget,
    EvidenceCoherence,
    ExactNumericExpectation,
    LocatedEvidence,
    NumericRangeExpectation,
    Quantity,
    RelativeTolerance,
    TargetProvenance,
    TeachingDiagnosisContext,
    TeachingEvidenceSource,
    UnresolvedQuestion,
)

from ..inference_sufficiency import (
    InferenceSufficiencyEvaluator,
    claim_subject_catalog,
    context_fingerprint,
)
from ..models import (
    AllowedClaimEnvelope,
    ClaimDecision,
    ClaimKind,
    ClaimPermission,
    ClaimSubjectKind,
    TeachingGoal,
)
from .errors import PublicationBoundaryError, PublicationFailureCode
from .identity import content_identity, permission_content_id
from .models import (
    MAX_PROJECTION_SLOTS,
    RENDERER_VERSION,
    PublicationProjection,
    PublicationRenderAtom,
    PublicationSlot,
)


PUBLISHABLE_KINDS = frozenset(
    {
        ClaimKind.EVIDENCE_RESTATEMENT,
        ClaimKind.DETERMINISTIC_COMPARISON_STATEMENT,
        ClaimKind.LIMITATION_STATEMENT,
    }
)


class PublicationProjectionBuilder:
    def __init__(self, *, max_slots: int = MAX_PROJECTION_SLOTS) -> None:
        if not isinstance(max_slots, int) or isinstance(max_slots, bool) or max_slots <= 0:
            raise ValueError("max_slots must be a positive integer")
        self._max_slots = max_slots

    def build(
        self,
        context: TeachingDiagnosisContext,
        envelope: AllowedClaimEnvelope,
        goal: TeachingGoal,
    ) -> PublicationProjection:
        if not isinstance(goal, TeachingGoal):
            raise PublicationBoundaryError(PublicationFailureCode.PROJECTION_BINDING_INVALID)
        expected = InferenceSufficiencyEvaluator().evaluate(context, goal)
        if expected != envelope or context_fingerprint(context) != envelope.context_fingerprint:
            raise PublicationBoundaryError(PublicationFailureCode.PROJECTION_BINDING_INVALID)

        catalog = claim_subject_catalog(context)
        permissions = tuple(
            permission
            for permission in envelope.permissions
            if permission.decision is ClaimDecision.ALLOW
            and permission.claim_kind in PUBLISHABLE_KINDS
        )
        if len(permissions) > self._max_slots:
            raise PublicationBoundaryError(PublicationFailureCode.PROJECTION_TOO_LARGE)

        slots: list[PublicationSlot] = []
        for ordinal, permission in enumerate(permissions, start=1):
            resolved = catalog.get(permission.subject)
            if resolved is None:
                raise PublicationBoundaryError(PublicationFailureCode.SUBJECT_UNRESOLVED)
            if any(ref not in catalog for ref in permission.support_refs):
                raise PublicationBoundaryError(PublicationFailureCode.SUPPORT_REFERENCE_UNRESOLVED)
            if any(ref not in catalog for ref in permission.obligation_refs):
                raise PublicationBoundaryError(PublicationFailureCode.OBLIGATION_REFERENCE_UNRESOLVED)
            atom = _render_atom(permission, resolved, context)
            renderable = _renderable_obligations(permission, atom)
            if not set(permission.obligations).issubset(set(renderable)):
                raise PublicationBoundaryError(PublicationFailureCode.PUBLICATION_OBLIGATION_UNSATISFIED)
            slots.append(
                PublicationSlot(
                    alias=f"p{ordinal:03d}",
                    permission_content_id=permission_content_id(envelope, permission),
                    permission=permission,
                    atom=atom,
                    renderable_obligations=renderable,
                )
            )

        projection_basis = {
            "schema": "aia-publication-projection/v1",
            "context": envelope.context_fingerprint,
            "envelope": envelope.envelope_id,
            "goal": goal.value,
            "renderer": RENDERER_VERSION,
            "slots": [
                {
                    "alias": slot.alias,
                    "permission": slot.permission_content_id,
                    "atom": asdict(slot.atom),
                    "renderable_obligations": [item.value for item in slot.renderable_obligations],
                }
                for slot in slots
            ],
        }
        return PublicationProjection(
            projection_id=content_identity(projection_basis),
            context_fingerprint=envelope.context_fingerprint,
            envelope_id=envelope.envelope_id,
            goal=goal,
            renderer_version=RENDERER_VERSION,
            slots=tuple(slots),
        )


def _render_atom(
    permission: ClaimPermission,
    resolved: object,
    context: TeachingDiagnosisContext,
) -> PublicationRenderAtom:
    if isinstance(resolved, DesignEvidenceItem):
        value, unit = _value_and_unit(resolved.value, resolved.unit)
        return PublicationRenderAtom(
            source=(
                "DESIGN_OBSERVATION"
                if resolved.origin is DesignEvidenceOrigin.DESIGN_DERIVED
                else "USER_STATEMENT"
            ),
            label=resolved.label,
            value=value,
            unit=unit,
            detail=resolved.verification_state.value,
        )
    if isinstance(resolved, EngineeringTarget):
        value, unit = _expectation(resolved)
        return PublicationRenderAtom(
            source=("USER_TARGET" if resolved.provenance is TargetProvenance.USER_PROVIDED else "DESIGN_TARGET"),
            label=resolved.metric.value.lower().replace("_", " "),
            value=value,
            unit=unit,
            metric=resolved.metric.value,
            detail=_tolerance(resolved),
        )
    if isinstance(resolved, LocatedEvidence):
        value, unit = _value_and_unit(resolved.item.value, resolved.item.unit)
        source = {
            TeachingEvidenceSource.INSTRUMENT: "INSTRUMENT",
            TeachingEvidenceSource.SOFTWARE_ANALYSIS: "SOFTWARE_ANALYSIS",
            TeachingEvidenceSource.SIMULATED: "SIMULATED",
        }[resolved.item.source]
        return PublicationRenderAtom(
            source=source,
            label=resolved.item.label,
            value=value,
            unit=unit,
            metric=resolved.locator.metric.value,
            quality=resolved.item.quality.value,
            warnings=resolved.item.warnings,
            detail=(context.coherence.instrument_vs_software if context.coherence is not None else None),
        )
    if isinstance(resolved, ComparisonResult):
        expected_value, expected_unit = _expectation_value(resolved.expected)
        observed_value, observed_unit = _value_and_unit(resolved.observed, None)
        difference_value, difference_unit = _value_and_unit(resolved.difference, None)
        return PublicationRenderAtom(
            source="COMPARISON",
            label=resolved.metric.value.lower().replace("_", " "),
            metric=resolved.metric.value,
            comparison_status=resolved.status.value,
            comparison_reason=resolved.reason.value,
            expected=_joined_value(expected_value, expected_unit),
            observed=_joined_value(observed_value, observed_unit),
            difference=_joined_value(difference_value, difference_unit),
        )
    if isinstance(resolved, EvidenceCoherence):
        return PublicationRenderAtom(
            source="COHERENCE",
            label="evidence coherence",
            detail=resolved.instrument_vs_software,
        )
    if isinstance(resolved, UnresolvedQuestion):
        return PublicationRenderAtom(
            source="UNRESOLVED_QUESTION",
            label=resolved.code,
            detail=resolved.detail,
        )
    if isinstance(resolved, str):
        source = {
            ClaimSubjectKind.WARNING: "WARNING",
            ClaimSubjectKind.QUALITY: "QUALITY",
            ClaimSubjectKind.LIMITATION: "LIMITATION",
        }.get(permission.subject.kind, "LIMITATION")
        return PublicationRenderAtom(source=source, label=source.lower(), detail=resolved)
    raise PublicationBoundaryError(PublicationFailureCode.RENDER_PLAN_INVALID)


def _value_and_unit(value: object, unit: str | None) -> tuple[str | None, str | None]:
    if value is None:
        return None, unit
    if isinstance(value, Quantity):
        return _number(value.value), value.unit
    if isinstance(value, DutyCycle):
        return _number(value.percent), "percent"
    if isinstance(value, bool):
        return ("true" if value else "false"), unit
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _number(float(value)), unit
    if isinstance(value, str):
        return value, unit
    raise PublicationBoundaryError(PublicationFailureCode.RENDER_PLAN_INVALID)


def _expectation(target: EngineeringTarget) -> tuple[str, str | None]:
    return _expectation_value(target.expectation)


def _expectation_value(expectation: object) -> tuple[str, str | None]:
    if isinstance(expectation, ExactNumericExpectation):
        return _number(expectation.quantity.value), expectation.quantity.unit
    if isinstance(expectation, NumericRangeExpectation):
        return f"{_number(expectation.minimum)} to {_number(expectation.maximum)}", expectation.unit
    if isinstance(expectation, DiscreteExpectation):
        return str(expectation.value).lower() if isinstance(expectation.value, bool) else expectation.value, None
    raise PublicationBoundaryError(PublicationFailureCode.RENDER_PLAN_INVALID)


def _tolerance(target: EngineeringTarget) -> str | None:
    if isinstance(target.tolerance, RelativeTolerance):
        return f"±{_number(target.tolerance.ratio * 100)} percent"
    if isinstance(target.tolerance, AbsoluteTolerance):
        return f"±{_number(target.tolerance.quantity.value)} {target.tolerance.quantity.unit}"
    return None


def _number(value: float) -> str:
    return format(value, ".12g")


def _joined_value(value: str | None, unit: str | None) -> str | None:
    if value is None:
        return None
    return value if unit is None else f"{value} {unit}"


def _renderable_obligations(
    permission: ClaimPermission,
    atom: PublicationRenderAtom,
) -> tuple:
    from ..models import PublicationObligation

    supported: list[PublicationObligation] = []
    attribution = {
        "DESIGN_OBSERVATION": PublicationObligation.ATTRIBUTE_DESIGN_OBSERVATION,
        "USER_STATEMENT": PublicationObligation.ATTRIBUTE_USER_STATEMENT,
        "USER_TARGET": PublicationObligation.ATTRIBUTE_USER_TARGET,
        "DESIGN_TARGET": PublicationObligation.ATTRIBUTE_DESIGN_TARGET,
        "INSTRUMENT": PublicationObligation.ATTRIBUTE_INSTRUMENT_SOURCE,
        "SOFTWARE_ANALYSIS": PublicationObligation.ATTRIBUTE_SOFTWARE_ANALYSIS,
        "SIMULATED": PublicationObligation.ATTRIBUTE_SIMULATED_SOURCE,
    }.get(atom.source)
    if attribution is not None:
        supported.append(attribution)
    if atom.value is None:
        supported.append(PublicationObligation.PRESERVE_UNAVAILABLE)
    if atom.quality == "degraded":
        supported.append(PublicationObligation.PRESERVE_DEGRADED_QUALITY)
    if atom.warnings:
        supported.append(PublicationObligation.INCLUDE_MATERIAL_WARNINGS)
    if atom.detail == "sequential_same_session":
        supported.extend(
            (
                PublicationObligation.PRESERVE_SEQUENTIAL_COHERENCE,
                PublicationObligation.DO_NOT_CLAIM_SIMULTANEOUS_OR_ATOMIC,
            )
        )
    if atom.source in {"DESIGN_OBSERVATION", "USER_STATEMENT"}:
        supported.extend(
            (
                PublicationObligation.PRESERVE_OBSERVATION_IDENTITY_LIMIT,
                PublicationObligation.DO_NOT_CLAIM_DESIGN_IMMUTABILITY,
            )
        )
    if atom.source == "COMPARISON":
        supported.append(PublicationObligation.PRESERVE_COMPARISON_REASON)
        if atom.comparison_status == "INDETERMINATE" and atom.comparison_reason == "TOLERANCE_UNSPECIFIED":
            supported.extend(
                (
                    PublicationObligation.STATE_TOLERANCE_UNSPECIFIED,
                    PublicationObligation.STATE_COMPLIANCE_UNDETERMINED,
                )
            )
    return tuple(dict.fromkeys(supported))
