from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
import hashlib
import json
from uuid import UUID

from ...domain.engineering_evidence import (
    ComparisonReason,
    ComparisonResult,
    ComparisonStatus,
    DesignEvidenceOrigin,
    EvidenceQuality,
    LocatedEvidence,
    MeasurementEvidenceLocator,
    TargetProvenance,
    TeachingDiagnosisContext,
    TeachingEvidenceSource,
)
from .models import (
    AllowedClaimEnvelope,
    ClaimDecision,
    ClaimForm,
    ClaimKind,
    ClaimPermission,
    ClaimReasonCode,
    ClaimSubjectKind,
    ClaimSubjectRef,
    ClaimSupportBasis,
    PublicationObligation,
    TeachingGoal,
)


POLICY_NAME = "aia.inference-sufficiency"
POLICY_VERSION = "1"


def context_fingerprint(context: TeachingDiagnosisContext) -> str:
    """Return a bounded content identity, not trust, freshness, signature, or proof."""

    if not isinstance(context, TeachingDiagnosisContext):
        raise TypeError("context must be TeachingDiagnosisContext")
    return _digest(_canonical_value(context))


def measurement_subject_ref(
    locator: MeasurementEvidenceLocator,
    fingerprint: str,
) -> ClaimSubjectRef:
    identity = {
        "measurement_context_id": locator.measurement_context_id,
        "collection": locator.collection,
        "ordinal": locator.ordinal,
        "metric": locator.metric,
        "category": locator.category,
    }
    return ClaimSubjectRef(
        context_fingerprint=fingerprint,
        kind=ClaimSubjectKind.MEASUREMENT_EVIDENCE,
        canonical_key="measurement:" + _digest_value(identity),
    )


def comparison_subject_ref(
    comparison: ComparisonResult,
    fingerprint: str,
) -> ClaimSubjectRef:
    """Build a comparison content identity, not provenance or authorization proof."""

    observed = None
    if comparison.observed_ref is not None:
        observed = {
            "measurement_context_id": comparison.observed_ref.measurement_context_id,
            "collection": comparison.observed_ref.collection,
            "ordinal": comparison.observed_ref.ordinal,
            "metric": comparison.observed_ref.metric,
            "category": comparison.observed_ref.category,
        }
    identity = {
        "metric": comparison.metric,
        "target_id": comparison.target_id,
        "observed_ref": observed,
        "expected": comparison.expected,
        "observed": comparison.observed,
        "difference": comparison.difference,
        "relative_difference": comparison.relative_difference,
        "status": comparison.status,
        "reason": comparison.reason,
        "comparator_name": comparison.comparator_name,
        "comparator_version": comparison.comparator_version,
    }
    return ClaimSubjectRef(
        context_fingerprint=fingerprint,
        kind=ClaimSubjectKind.COMPARISON,
        canonical_key="comparison:" + _digest_value(identity),
    )


class InferenceSufficiencyEvaluator:
    """Creates exact, deterministic claim slots; it never generates prose."""

    def evaluate(
        self,
        context: TeachingDiagnosisContext,
        goal: TeachingGoal,
    ) -> AllowedClaimEnvelope:
        if not isinstance(context, TeachingDiagnosisContext):
            raise TypeError("context must be TeachingDiagnosisContext")
        if not isinstance(goal, TeachingGoal):
            raise TypeError("goal must be TeachingGoal")

        fingerprint = context_fingerprint(context)
        context_ref = _subject(fingerprint, ClaimSubjectKind.CONTEXT, "context")
        permissions: list[ClaimPermission] = []
        warning_refs = {
            text: _text_subject(fingerprint, ClaimSubjectKind.WARNING, "warning", text, ordinal)
            for ordinal, text in enumerate(context.warnings)
        }
        limitation_refs = tuple(
            _text_subject(fingerprint, ClaimSubjectKind.LIMITATION, "limitation", text, ordinal)
            for ordinal, text in enumerate(context.limitations)
        )
        unresolved_refs = tuple(
            _subject(
                fingerprint,
                ClaimSubjectKind.UNRESOLVED_QUESTION,
                "unresolved:" + _digest_value(
                    {"code": value.code, "subject_ref": value.subject_ref, "ordinal": ordinal}
                ),
            )
            for ordinal, value in enumerate(context.unresolved_questions)
        )
        snapshot_ref = _subject(
            fingerprint,
            ClaimSubjectKind.LIMITATION,
            "constraint:design-observation-identity",
        )
        coherence_ref = (
            None
            if context.coherence is None
            else _subject(
                fingerprint,
                ClaimSubjectKind.COHERENCE,
                "coherence:" + _digest_value(context.coherence),
            )
        )

        for fact in context.design_facts:
            subject = _subject(
                fingerprint,
                ClaimSubjectKind.DESIGN_EVIDENCE,
                f"design-evidence:{fact.evidence_id}",
            )
            form = ClaimForm.EVIDENCE_AVAILABILITY if fact.value is None else ClaimForm.EVIDENCE_VALUE
            attribution = (
                PublicationObligation.ATTRIBUTE_DESIGN_OBSERVATION
                if fact.origin is DesignEvidenceOrigin.DESIGN_DERIVED
                else PublicationObligation.ATTRIBUTE_USER_STATEMENT
            )
            permissions.append(
                self._allow(
                    ClaimKind.EVIDENCE_RESTATEMENT,
                    form,
                    subject,
                    ClaimSupportBasis.EXACT_RESTATEMENT,
                    ClaimReasonCode.EXACT_EVIDENCE_AVAILABLE,
                    obligations=(
                        attribution,
                        PublicationObligation.PRESERVE_OBSERVATION_IDENTITY_LIMIT,
                        PublicationObligation.DO_NOT_CLAIM_DESIGN_IMMUTABILITY,
                    ),
                    obligation_refs=(snapshot_ref,),
                )
            )

        for target in context.design_targets:
            subject = _subject(
                fingerprint,
                ClaimSubjectKind.DESIGN_TARGET,
                f"design-target:{target.target_id}",
            )
            attribution = (
                PublicationObligation.ATTRIBUTE_USER_TARGET
                if target.provenance is TargetProvenance.USER_PROVIDED
                else PublicationObligation.ATTRIBUTE_DESIGN_TARGET
            )
            permissions.append(
                self._allow(
                    ClaimKind.EVIDENCE_RESTATEMENT,
                    ClaimForm.TARGET_VALUE,
                    subject,
                    ClaimSupportBasis.EXACT_RESTATEMENT,
                    ClaimReasonCode.EXACT_TARGET_AVAILABLE,
                    obligations=(attribution,),
                )
            )

        all_measurements = (
            context.physical_observations
            + context.software_analyses
            + context.simulated_evidence
        )
        for located in all_measurements:
            permissions.append(
                self._measurement_permission(
                    located,
                    fingerprint,
                    warning_refs,
                    coherence_ref,
                )
            )

        for subject in limitation_refs:
            permissions.append(self._allow_limitation(subject))
        for subject in warning_refs.values():
            permissions.append(self._allow_limitation(subject))
        for subject in unresolved_refs:
            permissions.append(self._allow_limitation(subject))
        if coherence_ref is not None:
            permissions.append(self._allow_limitation(coherence_ref))
        if context.quality is not None:
            quality_ref = _subject(
                fingerprint,
                ClaimSubjectKind.QUALITY,
                "quality:" + _digest_value(context.quality),
            )
            permissions.append(self._allow_limitation(quality_ref))
        for comparison in context.comparisons:
            permissions.extend(self._comparison_permissions(comparison, fingerprint, goal))

        blocked = {
            ClaimKind.EDUCATIONAL_EXPLANATION: (
                ClaimForm.EDUCATIONAL_CONTENT,
                ClaimReasonCode.NO_REVIEWED_KNOWLEDGE_SOURCE,
            ),
            ClaimKind.ENGINEERING_INFERENCE: (
                ClaimForm.CASE_SPECIFIC_CONCLUSION,
                ClaimReasonCode.NO_REVIEWED_INFERENCE_RULE,
            ),
            ClaimKind.HYPOTHESIS: (
                ClaimForm.POSSIBLE_CAUSE,
                ClaimReasonCode.NO_REVIEWED_HYPOTHESIS_RULE,
            ),
            ClaimKind.CAUSAL_DIAGNOSIS: (
                ClaimForm.CAUSAL_EXPLANATION,
                ClaimReasonCode.NO_REVIEWED_CAUSAL_RULE,
            ),
            ClaimKind.NEXT_MEASUREMENT_PROPOSAL: (
                ClaimForm.MEASUREMENT_PROPOSAL,
                ClaimReasonCode.NEXT_MEASUREMENT_DEFERRED,
            ),
        }
        for kind, (form, reason) in blocked.items():
            permissions.append(self._block(kind, form, context_ref, reason))

        return AllowedClaimEnvelope.create(
            context_fingerprint=fingerprint,
            goal=goal,
            policy_name=POLICY_NAME,
            policy_version=POLICY_VERSION,
            permissions=tuple(permissions),
            unresolved_question_refs=unresolved_refs,
        )

    def _measurement_permission(
        self,
        located: LocatedEvidence,
        fingerprint: str,
        warning_refs: dict[str, ClaimSubjectRef],
        coherence_ref: ClaimSubjectRef | None,
    ) -> ClaimPermission:
        subject = measurement_subject_ref(located.locator, fingerprint)
        item = located.item
        form = (
            ClaimForm.EVIDENCE_AVAILABILITY
            if item.quality is EvidenceQuality.UNAVAILABLE or item.value is None
            else ClaimForm.EVIDENCE_VALUE
        )
        obligations: list[PublicationObligation] = []
        if item.source is TeachingEvidenceSource.INSTRUMENT:
            obligations.append(PublicationObligation.ATTRIBUTE_INSTRUMENT_SOURCE)
        elif item.source is TeachingEvidenceSource.SOFTWARE_ANALYSIS:
            obligations.append(PublicationObligation.ATTRIBUTE_SOFTWARE_ANALYSIS)
        else:
            obligations.append(PublicationObligation.ATTRIBUTE_SIMULATED_SOURCE)

        obligation_refs: list[ClaimSubjectRef] = []
        if item.quality is EvidenceQuality.UNAVAILABLE:
            obligations.append(PublicationObligation.PRESERVE_UNAVAILABLE)
        if item.quality is EvidenceQuality.DEGRADED:
            obligations.append(PublicationObligation.PRESERVE_DEGRADED_QUALITY)
        if item.warnings:
            obligations.append(PublicationObligation.INCLUDE_MATERIAL_WARNINGS)
            for ordinal, warning in enumerate(item.warnings):
                obligation_refs.append(
                    warning_refs.get(warning)
                    or _text_subject(
                        fingerprint,
                        ClaimSubjectKind.WARNING,
                        "evidence-warning",
                        warning,
                        ordinal,
                    )
                )
        if coherence_ref is not None:
            obligations.extend(
                (
                    PublicationObligation.PRESERVE_SEQUENTIAL_COHERENCE,
                    PublicationObligation.DO_NOT_CLAIM_SIMULTANEOUS_OR_ATOMIC,
                )
            )
            obligation_refs.append(coherence_ref)

        reason = (
            ClaimReasonCode.EVIDENCE_UNAVAILABLE
            if item.quality is EvidenceQuality.UNAVAILABLE
            else ClaimReasonCode.EXACT_EVIDENCE_AVAILABLE
        )
        return self._allow(
            ClaimKind.EVIDENCE_RESTATEMENT,
            form,
            subject,
            ClaimSupportBasis.EXACT_RESTATEMENT,
            reason,
            obligations=tuple(dict.fromkeys(obligations)),
            obligation_refs=tuple(dict.fromkeys(obligation_refs)),
        )

    def _comparison_permissions(
        self,
        comparison: ComparisonResult,
        fingerprint: str,
        goal: TeachingGoal,
    ) -> tuple[ClaimPermission, ...]:
        subject = comparison_subject_ref(comparison, fingerprint)
        values: list[ClaimPermission] = []
        comparison_allowed = goal is not TeachingGoal.EXPLAIN_MEASUREMENT

        def supported(form: ClaimForm, obligations: tuple[PublicationObligation, ...] = ()) -> None:
            if comparison_allowed:
                values.append(
                    self._allow(
                        ClaimKind.DETERMINISTIC_COMPARISON_STATEMENT,
                        form,
                        subject,
                        ClaimSupportBasis.DETERMINISTIC_DERIVATION,
                        ClaimReasonCode.EXISTING_COMPARISON_SUPPORTS_STATEMENT,
                        obligations=(PublicationObligation.PRESERVE_COMPARISON_REASON,) + obligations,
                    )
                )
            else:
                values.append(
                    self._block(
                        ClaimKind.DETERMINISTIC_COMPARISON_STATEMENT,
                        form,
                        subject,
                        ClaimReasonCode.GOAL_NOT_RELEVANT,
                    )
                )

        supported(ClaimForm.COMPARISON_STATUS)
        if comparison.difference is not None:
            supported(ClaimForm.COMPARISON_DIFFERENCE)

        no_tolerance = comparison.reason is ComparisonReason.TOLERANCE_UNSPECIFIED
        if no_tolerance:
            supported(
                ClaimForm.COMPLIANCE_UNDETERMINED,
                (
                    PublicationObligation.STATE_TOLERANCE_UNSPECIFIED,
                    PublicationObligation.STATE_COMPLIANCE_UNDETERMINED,
                ),
            )
            for form in (
                ClaimForm.WITHIN_SPECIFIED_CRITERION,
                ClaimForm.OUTSIDE_SPECIFIED_CRITERION,
                ClaimForm.COMPLIANCE_VERDICT,
            ):
                values.append(
                    self._block(
                        ClaimKind.DETERMINISTIC_COMPARISON_STATEMENT,
                        form,
                        subject,
                        ClaimReasonCode.ACCEPTANCE_CRITERION_UNAVAILABLE,
                    )
                )
        elif comparison.status in (ComparisonStatus.MATCH, ComparisonStatus.MISMATCH):
            supported_form = (
                ClaimForm.WITHIN_SPECIFIED_CRITERION
                if comparison.status is ComparisonStatus.MATCH
                else ClaimForm.OUTSIDE_SPECIFIED_CRITERION
            )
            supported(supported_form)
            opposite = (
                ClaimForm.OUTSIDE_SPECIFIED_CRITERION
                if supported_form is ClaimForm.WITHIN_SPECIFIED_CRITERION
                else ClaimForm.WITHIN_SPECIFIED_CRITERION
            )
            values.append(
                self._block(
                    ClaimKind.DETERMINISTIC_COMPARISON_STATEMENT,
                    opposite,
                    subject,
                    ClaimReasonCode.ACCEPTANCE_CRITERION_UNAVAILABLE,
                )
            )
            values.append(
                self._block(
                    ClaimKind.DETERMINISTIC_COMPARISON_STATEMENT,
                    ClaimForm.COMPLIANCE_VERDICT,
                    subject,
                    ClaimReasonCode.ACCEPTANCE_CRITERION_UNAVAILABLE,
                )
            )
        else:
            for form in (
                ClaimForm.COMPLIANCE_UNDETERMINED,
                ClaimForm.WITHIN_SPECIFIED_CRITERION,
                ClaimForm.OUTSIDE_SPECIFIED_CRITERION,
                ClaimForm.COMPLIANCE_VERDICT,
            ):
                values.append(
                    self._block(
                        ClaimKind.DETERMINISTIC_COMPARISON_STATEMENT,
                        form,
                        subject,
                        ClaimReasonCode.COMPARISON_DOES_NOT_SUPPORT_CRITERION,
                    )
                )
        return tuple(values)

    @staticmethod
    def _allow(
        kind: ClaimKind,
        form: ClaimForm,
        subject: ClaimSubjectRef,
        basis: ClaimSupportBasis,
        reason: ClaimReasonCode,
        *,
        obligations: tuple[PublicationObligation, ...] = (),
        obligation_refs: tuple[ClaimSubjectRef, ...] = (),
    ) -> ClaimPermission:
        return ClaimPermission(
            claim_kind=kind,
            claim_form=form,
            subject=subject,
            decision=ClaimDecision.ALLOW,
            support_basis=basis,
            reason_codes=(reason,),
            support_refs=(subject,),
            obligations=obligations,
            obligation_refs=obligation_refs,
            policy_name=POLICY_NAME,
            policy_version=POLICY_VERSION,
        )

    @staticmethod
    def _block(
        kind: ClaimKind,
        form: ClaimForm,
        subject: ClaimSubjectRef,
        reason: ClaimReasonCode,
    ) -> ClaimPermission:
        return ClaimPermission(
            claim_kind=kind,
            claim_form=form,
            subject=subject,
            decision=ClaimDecision.BLOCK,
            support_basis=ClaimSupportBasis.INSUFFICIENT,
            reason_codes=(reason,),
            support_refs=(),
            obligations=(),
            obligation_refs=(),
            policy_name=POLICY_NAME,
            policy_version=POLICY_VERSION,
        )

    def _allow_limitation(self, subject: ClaimSubjectRef) -> ClaimPermission:
        return self._allow(
            ClaimKind.LIMITATION_STATEMENT,
            ClaimForm.LIMITATION_RESTATEMENT,
            subject,
            ClaimSupportBasis.EXACT_RESTATEMENT,
            ClaimReasonCode.EXACT_LIMITATION_AVAILABLE,
        )


def _subject(
    fingerprint: str,
    kind: ClaimSubjectKind,
    canonical_key: str,
) -> ClaimSubjectRef:
    return ClaimSubjectRef(fingerprint, kind, canonical_key)


def _text_subject(
    fingerprint: str,
    kind: ClaimSubjectKind,
    prefix: str,
    text: str,
    ordinal: int,
) -> ClaimSubjectRef:
    return _subject(
        fingerprint,
        kind,
        f"{prefix}:{ordinal}:" + _digest_value(text),
    )


def _digest_value(value: object) -> str:
    canonical = _canonical_value(value)
    return hashlib.sha256(
        json.dumps(canonical, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _digest(value: object) -> str:
    return "sha256:" + _digest_value(value)


def _canonical_value(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _canonical_value(getattr(value, field.name))
            for field in fields(value)
            if field.name != "label"
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_canonical_value(item) for item in value]
    if isinstance(value, list):
        return [_canonical_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _canonical_value(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported canonical value type: {type(value).__name__}")
