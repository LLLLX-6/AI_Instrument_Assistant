from __future__ import annotations

import hashlib

from ai_instrument_assistant.domain.engineering_evidence import TeachingDiagnosisContext

from ..models import AllowedClaimEnvelope, TeachingGoal
from .errors import PublicationBoundaryError, PublicationFailureCode
from .grounding import EngineeringClaimGroundingGuard, deterministic_fallback_plan
from .models import (
    EgressStatus,
    CandidateParser,
    FinalEgressInspector,
    PublicationAuditRecord,
    PublicationProjection,
    PublicationResult,
    RENDERER_VERSION,
)
from .renderer import DeterministicPublicationRenderer


TERMINAL_SAFE_TEXT = "A grounded engineering explanation could not be published safely."


class GovernedPublicationBoundary:
    """Model-free Phase 8C.2A composition ending at a required final Egress port."""

    def __init__(self, egress: FinalEgressInspector, parser: CandidateParser) -> None:
        self._egress = egress
        self._parser = parser
        self._guard = EngineeringClaimGroundingGuard()
        self._renderer = DeterministicPublicationRenderer()

    def publish(
        self,
        *,
        context: TeachingDiagnosisContext,
        envelope: AllowedClaimEnvelope,
        goal: TeachingGoal,
        projection: PublicationProjection,
        raw_candidate: str,
        correlation_id: str,
    ) -> PublicationResult:
        candidate_digest = _digest_raw(raw_candidate)
        selected_aliases: tuple[str, ...] = ()
        failure: PublicationFailureCode | None = None
        plan = None
        try:
            candidate = self._parser.parse(raw_candidate)
            selected_aliases = candidate.ordered_permission_refs
            plan = self._guard.ground(context, envelope, goal, projection, candidate)
        except PublicationBoundaryError as error:
            failure = error.code
            try:
                plan = deterministic_fallback_plan(context, envelope, goal, projection)
            except PublicationBoundaryError as fallback_error:
                return self._terminal_result(
                    context=context,
                    envelope=envelope,
                    projection=projection,
                    goal=goal,
                    correlation_id=correlation_id,
                    candidate_digest=candidate_digest,
                    selected_aliases=selected_aliases,
                    failure=fallback_error.code,
                )
        except Exception:
            failure = PublicationFailureCode.BOUNDED_INTERNAL_FAILURE
            try:
                plan = deterministic_fallback_plan(context, envelope, goal, projection)
            except Exception:
                return self._terminal_result(
                    context=context,
                    envelope=envelope,
                    projection=projection,
                    goal=goal,
                    correlation_id=correlation_id,
                    candidate_digest=candidate_digest,
                    selected_aliases=selected_aliases,
                    failure=PublicationFailureCode.BOUNDED_INTERNAL_FAILURE,
                )

        try:
            text = self._renderer.render(plan)
        except PublicationBoundaryError as error:
            return self._terminal_result(
                context=context,
                envelope=envelope,
                projection=projection,
                goal=goal,
                correlation_id=correlation_id,
                candidate_digest=candidate_digest,
                selected_aliases=selected_aliases,
                failure=error.code,
            )
        try:
            egress = self._egress.inspect(text, correlation_id=correlation_id)
        except Exception:
            return self._terminal_result(
                context=context,
                envelope=envelope,
                projection=projection,
                goal=goal,
                correlation_id=correlation_id,
                candidate_digest=candidate_digest,
                selected_aliases=selected_aliases,
                failure=PublicationFailureCode.BOUNDED_INTERNAL_FAILURE,
            )
        if egress.status is EgressStatus.UNSAFE:
            return self._terminal_result(
                context=context,
                envelope=envelope,
                projection=projection,
                goal=goal,
                correlation_id=correlation_id,
                candidate_digest=candidate_digest,
                selected_aliases=selected_aliases,
                failure=PublicationFailureCode.FINAL_EGRESS_BLOCKED,
            )
        status = "FALLBACK_PUBLISHED" if plan.fallback else "PUBLISHED"
        return PublicationResult(
            status=status,
            text=text,
            audit=_audit(
                correlation_id=correlation_id,
                goal=goal,
                envelope=envelope,
                projection=projection,
                candidate_digest=candidate_digest,
                aliases=selected_aliases,
                plan_id=plan.plan_id,
                grounding="FALLBACK" if plan.fallback else "PASS",
                egress="SAFE",
                fallback=plan.fallback,
                status=status,
                failure=failure,
            ),
        )

    def _terminal_result(
        self,
        *,
        context: TeachingDiagnosisContext,
        envelope: AllowedClaimEnvelope,
        projection: PublicationProjection,
        goal: TeachingGoal,
        correlation_id: str,
        candidate_digest: str,
        selected_aliases: tuple[str, ...],
        failure: PublicationFailureCode,
    ) -> PublicationResult:
        try:
            terminal = self._egress.inspect(TERMINAL_SAFE_TEXT, correlation_id=correlation_id)
            safe = terminal.status is EgressStatus.SAFE
        except Exception:
            safe = False
        status = "TERMINAL_FALLBACK_PUBLISHED" if safe else "BLOCKED"
        return PublicationResult(
            status=status,
            text=TERMINAL_SAFE_TEXT if safe else "",
            audit=_audit(
                correlation_id=correlation_id,
                goal=goal,
                envelope=envelope,
                projection=projection,
                candidate_digest=candidate_digest,
                aliases=selected_aliases,
                plan_id=None,
                grounding="REJECTED",
                egress="SAFE" if safe else "UNSAFE",
                fallback=True,
                status=status,
                failure=failure,
            ),
        )


def _digest_raw(raw: object) -> str:
    value = raw if isinstance(raw, str) else "<non-text>"
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _audit(
    *,
    correlation_id: str,
    goal: TeachingGoal,
    envelope: AllowedClaimEnvelope,
    projection: PublicationProjection,
    candidate_digest: str,
    aliases: tuple[str, ...],
    plan_id: str | None,
    grounding: str,
    egress: str,
    fallback: bool,
    status: str,
    failure: PublicationFailureCode | None,
) -> PublicationAuditRecord:
    bounded_correlation = correlation_id.strip()[:96] if isinstance(correlation_id, str) else "unscoped"
    return PublicationAuditRecord(
        correlation_id=bounded_correlation or "unscoped",
        trusted_goal=goal,
        context_fingerprint=envelope.context_fingerprint,
        envelope_id=envelope.envelope_id,
        projection_id=projection.projection_id,
        candidate_digest=candidate_digest,
        selected_aliases=aliases,
        grounding_decision=grounding,
        grounded_plan_id=plan_id,
        renderer_version=RENDERER_VERSION,
        final_egress_decision=egress,
        fallback_used=fallback,
        publication_status=status,
        failure_code=None if failure is None else failure.value,
    )
