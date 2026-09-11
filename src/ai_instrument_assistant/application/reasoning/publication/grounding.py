from __future__ import annotations

from ai_instrument_assistant.domain.engineering_evidence import TeachingDiagnosisContext

from ..fallback import build_deterministic_fallback
from ..inference_sufficiency import InferenceSufficiencyEvaluator, claim_subject_catalog
from ..models import AllowedClaimEnvelope, ClaimDecision, ClaimKind, TeachingGoal
from .errors import PublicationBoundaryError, PublicationFailureCode
from .identity import content_identity, permission_content_id
from .models import (
    MAX_CANDIDATE_CLAIMS,
    GroundedPublicationPlan,
    PublicationProjection,
    PublicationSlot,
    StructuredClaimCandidateSet,
)
from .projection import PUBLISHABLE_KINDS, PublicationProjectionBuilder


class EngineeringClaimGroundingGuard:
    """Resolve minimal candidate aliases exclusively against trusted Host state."""

    def ground(
        self,
        context: TeachingDiagnosisContext,
        envelope: AllowedClaimEnvelope,
        goal: TeachingGoal,
        projection: PublicationProjection,
        candidate: StructuredClaimCandidateSet,
    ) -> GroundedPublicationPlan:
        expected_envelope = InferenceSufficiencyEvaluator().evaluate(context, goal)
        if expected_envelope != envelope:
            raise PublicationBoundaryError(PublicationFailureCode.PROJECTION_BINDING_INVALID)
        expected_projection = PublicationProjectionBuilder().build(context, envelope, goal)
        if expected_projection != projection:
            raise PublicationBoundaryError(PublicationFailureCode.PROJECTION_BINDING_INVALID)
        if (
            candidate.projection_id != projection.projection_id
            or candidate.context_fingerprint != projection.context_fingerprint
            or candidate.envelope_id != projection.envelope_id
            or candidate.goal is not goal
        ):
            raise PublicationBoundaryError(PublicationFailureCode.CANDIDATE_BINDING_MISMATCH)
        if len(candidate.ordered_permission_refs) > MAX_CANDIDATE_CLAIMS:
            raise PublicationBoundaryError(PublicationFailureCode.CANDIDATE_SCHEMA_INVALID)
        if len(candidate.ordered_permission_refs) != len(set(candidate.ordered_permission_refs)):
            raise PublicationBoundaryError(PublicationFailureCode.DUPLICATE_PERMISSION_REFERENCE)

        catalog = claim_subject_catalog(context)
        selected: list[PublicationSlot] = []
        for alias in candidate.ordered_permission_refs:
            slot = projection.slot_for_alias(alias)
            if slot is None:
                raise PublicationBoundaryError(PublicationFailureCode.UNKNOWN_PERMISSION_REFERENCE)
            permission = slot.permission
            if permission.decision is not ClaimDecision.ALLOW:
                raise PublicationBoundaryError(PublicationFailureCode.PERMISSION_NOT_ALLOWED)
            if permission.claim_kind not in PUBLISHABLE_KINDS:
                raise PublicationBoundaryError(PublicationFailureCode.CLAIM_KIND_NOT_PUBLISHABLE)
            if permission_content_id(envelope, permission) != slot.permission_content_id:
                raise PublicationBoundaryError(PublicationFailureCode.PERMISSION_SEMANTICS_CHANGED)
            if permission not in envelope.permissions:
                raise PublicationBoundaryError(PublicationFailureCode.PERMISSION_SEMANTICS_CHANGED)
            if permission.subject not in catalog:
                raise PublicationBoundaryError(PublicationFailureCode.SUBJECT_UNRESOLVED)
            if any(ref not in catalog for ref in permission.support_refs):
                raise PublicationBoundaryError(PublicationFailureCode.SUPPORT_REFERENCE_UNRESOLVED)
            if any(ref not in catalog for ref in permission.obligation_refs):
                raise PublicationBoundaryError(PublicationFailureCode.OBLIGATION_REFERENCE_UNRESOLVED)
            if not set(permission.obligations).issubset(set(slot.renderable_obligations)):
                raise PublicationBoundaryError(PublicationFailureCode.PUBLICATION_OBLIGATION_UNSATISFIED)
            selected.append(slot)
        return _plan(projection, tuple(selected), fallback=False)


def deterministic_fallback_plan(
    context: TeachingDiagnosisContext,
    envelope: AllowedClaimEnvelope,
    goal: TeachingGoal,
    projection: PublicationProjection,
) -> GroundedPublicationPlan:
    expected = PublicationProjectionBuilder().build(context, envelope, goal)
    if expected != projection:
        raise PublicationBoundaryError(PublicationFailureCode.PROJECTION_BINDING_INVALID)
    fallback = build_deterministic_fallback(envelope)
    identities = {permission_content_id(envelope, item) for item in fallback.permissions}
    eligible = [slot for slot in projection.slots if slot.permission_content_id in identities]
    priority = {
        ClaimKind.EVIDENCE_RESTATEMENT: 0,
        ClaimKind.DETERMINISTIC_COMPARISON_STATEMENT: 1,
        ClaimKind.LIMITATION_STATEMENT: 2,
    }
    ordered = sorted(
        eligible,
        key=lambda slot: (priority[slot.permission.claim_kind], slot.permission.canonical_sort_key),
    )[:MAX_CANDIDATE_CLAIMS]
    if not ordered:
        raise PublicationBoundaryError(PublicationFailureCode.FALLBACK_UNAVAILABLE)
    for slot in ordered:
        if not set(slot.permission.obligations).issubset(set(slot.renderable_obligations)):
            raise PublicationBoundaryError(PublicationFailureCode.PUBLICATION_OBLIGATION_UNSATISFIED)
    return _plan(projection, tuple(ordered), fallback=True)


def _plan(
    projection: PublicationProjection,
    slots: tuple[PublicationSlot, ...],
    *,
    fallback: bool,
) -> GroundedPublicationPlan:
    basis = {
        "projection": projection.projection_id,
        "renderer": projection.renderer_version,
        "permissions": [slot.permission_content_id for slot in slots],
        "fallback": fallback,
    }
    return GroundedPublicationPlan(
        plan_id=content_identity(basis),
        projection_id=projection.projection_id,
        context_fingerprint=projection.context_fingerprint,
        envelope_id=projection.envelope_id,
        goal=projection.goal,
        renderer_version=projection.renderer_version,
        slots=slots,
        fallback=fallback,
    )
