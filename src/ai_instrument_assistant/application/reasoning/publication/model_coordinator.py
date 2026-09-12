from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import uuid4

from ..inference_sufficiency import InferenceSufficiencyEvaluator
from ..models import TeachingGoal
from ai_instrument_assistant.domain.engineering_evidence import TeachingDiagnosisContext
from .model_runtime import (
    CancellationHandle,
    ModelFailureCode,
    StructuredCandidateRequest,
    StructuredCandidateRuntime,
    StructuredCandidateStatus,
)
from .models import PublicationResult
from .pipeline import GovernedPublicationBoundary
from .projection import PublicationProjectionBuilder


@dataclass(frozen=True, slots=True)
class ModelPublicationAudit:
    trusted_goal: str
    context_fingerprint: str
    envelope_id: str
    projection_id: str
    request_id: str
    request_digest: str | None
    runtime_version: str | None
    executor_version: str | None
    provider_id: str | None
    model_id: str | None
    model_request_count: int
    runtime_invocation_count: int
    raw_byte_count: int
    raw_digest: str | None
    raw_precheck: str
    receipt_validation: str
    parser_result: str
    candidate_digest: str
    selected_aliases: tuple[str, ...]
    grounding_result: str
    renderer_version: str
    final_egress: str
    publication_result: str
    failure_code: str | None
    model_retry_count: int = 0
    repair_prompt_count: int = 0
    fallback_model_count: int = 0
    agent_retry_count: int = 0
    tool_count: int = 0
    ipc_count: int = 0
    eda_count: int = 0
    hardware_count: int = 0
    remeasurement_count: int = 0


@dataclass(frozen=True, slots=True)
class CoordinatedPublicationResult:
    publication: PublicationResult
    audit: ModelPublicationAudit


class OneShotPublicationCoordinator:
    """Consumes one Host budget and never retries, repairs, or executes a Tool."""

    def __init__(
        self,
        runtime: StructuredCandidateRuntime,
        boundary: GovernedPublicationBoundary,
    ) -> None:
        self._runtime = runtime
        self._boundary = boundary

    async def publish(
        self,
        *,
        context: TeachingDiagnosisContext,
        goal: TeachingGoal,
        correlation_id: str,
        cancellation: CancellationHandle | None = None,
    ) -> CoordinatedPublicationResult:
        envelope = InferenceSufficiencyEvaluator().evaluate(context, goal)
        projection = PublicationProjectionBuilder().build(context, envelope, goal)
        request = StructuredCandidateRequest(uuid4(), projection, goal, cancellation=cancellation)
        outcome = None
        failure: ModelFailureCode | None = None
        # The process-local one-shot budget is irreversibly consumed here.
        runtime_invocation_count = 1
        try:
            try:
                outcome = await self._runtime.generate(request)
            except Exception:
                failure = ModelFailureCode.MODEL_PROCESS_FAILED
            if outcome is not None and outcome.status is StructuredCandidateStatus.CANDIDATE:
                publication = self._boundary.publish(
                    context=context,
                    envelope=envelope,
                    goal=goal,
                    projection=projection,
                    raw_candidate=outcome.raw_candidate or "",
                    correlation_id=correlation_id,
                )
            else:
                failure = failure or (outcome.failure_code if outcome is not None else None)
                failure = failure or ModelFailureCode.MODEL_PROCESS_FAILED
                publication = self._boundary.publish_fallback(
                    context=context,
                    envelope=envelope,
                    goal=goal,
                    projection=projection,
                    correlation_id=correlation_id,
                    reason=failure.value,
                )
        finally:
            try:
                await self._runtime.aclose()
            except Exception:
                pass

        publication = replace(
            publication,
            audit=replace(
                publication.audit,
                model_request_count=(0 if outcome is None else outcome.model_request_count),
            ),
        )
        audit = ModelPublicationAudit(
            trusted_goal=goal.value,
            context_fingerprint=envelope.context_fingerprint,
            envelope_id=envelope.envelope_id,
            projection_id=projection.projection_id,
            request_id=str(request.request_id),
            request_digest=None if outcome is None else outcome.request_digest,
            runtime_version=None if outcome is None else outcome.runtime_version,
            executor_version=None if outcome is None else outcome.executor_version,
            provider_id=None if outcome is None else outcome.provider_id,
            model_id=None if outcome is None else outcome.model_id,
            model_request_count=0 if outcome is None else outcome.model_request_count,
            runtime_invocation_count=runtime_invocation_count,
            raw_byte_count=0 if outcome is None else outcome.raw_byte_count,
            raw_digest=None if outcome is None else outcome.raw_digest,
            raw_precheck="NOT_RUN" if outcome is None else outcome.raw_precheck,
            receipt_validation=("PASS" if outcome is not None and outcome.receipt_validated else "NOT_APPLICABLE"),
            parser_result=("PASS" if publication.audit.grounding_decision == "PASS" else "REJECTED_OR_NOT_RUN"),
            candidate_digest=publication.audit.candidate_digest,
            selected_aliases=publication.audit.selected_aliases,
            grounding_result=publication.audit.grounding_decision,
            renderer_version=publication.audit.renderer_version,
            final_egress=publication.audit.final_egress_decision,
            publication_result=publication.status,
            failure_code=(
                failure.value
                if failure is not None
                else _bounded_publication_failure(publication.audit.failure_code)
            ),
        )
        return CoordinatedPublicationResult(publication, audit)


def _bounded_publication_failure(value: str | None) -> str | None:
    return {
        "EXACT_JSON_OBJECT_REQUIRED": ModelFailureCode.MODEL_OUTPUT_UNPARSEABLE.value,
        "DUPLICATE_JSON_KEY": ModelFailureCode.MODEL_OUTPUT_UNPARSEABLE.value,
        "RAW_OUTPUT_TOO_LARGE": ModelFailureCode.MODEL_OUTPUT_TOO_LARGE.value,
        "CANDIDATE_SCHEMA_INVALID": ModelFailureCode.MODEL_CANDIDATE_SCHEMA_INVALID.value,
    }.get(value, value)
