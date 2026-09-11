from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json


class ClaimKind(StrEnum):
    EVIDENCE_RESTATEMENT = "EVIDENCE_RESTATEMENT"
    DETERMINISTIC_COMPARISON_STATEMENT = "DETERMINISTIC_COMPARISON_STATEMENT"
    LIMITATION_STATEMENT = "LIMITATION_STATEMENT"
    EDUCATIONAL_EXPLANATION = "EDUCATIONAL_EXPLANATION"
    ENGINEERING_INFERENCE = "ENGINEERING_INFERENCE"
    HYPOTHESIS = "HYPOTHESIS"
    CAUSAL_DIAGNOSIS = "CAUSAL_DIAGNOSIS"
    NEXT_MEASUREMENT_PROPOSAL = "NEXT_MEASUREMENT_PROPOSAL"


class ClaimDecision(StrEnum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"


class ClaimForm(StrEnum):
    EVIDENCE_VALUE = "EVIDENCE_VALUE"
    EVIDENCE_AVAILABILITY = "EVIDENCE_AVAILABILITY"
    TARGET_VALUE = "TARGET_VALUE"
    COMPARISON_STATUS = "COMPARISON_STATUS"
    COMPARISON_DIFFERENCE = "COMPARISON_DIFFERENCE"
    COMPLIANCE_UNDETERMINED = "COMPLIANCE_UNDETERMINED"
    WITHIN_SPECIFIED_CRITERION = "WITHIN_SPECIFIED_CRITERION"
    OUTSIDE_SPECIFIED_CRITERION = "OUTSIDE_SPECIFIED_CRITERION"
    COMPLIANCE_VERDICT = "COMPLIANCE_VERDICT"
    LIMITATION_RESTATEMENT = "LIMITATION_RESTATEMENT"
    EDUCATIONAL_CONTENT = "EDUCATIONAL_CONTENT"
    CASE_SPECIFIC_CONCLUSION = "CASE_SPECIFIC_CONCLUSION"
    POSSIBLE_CAUSE = "POSSIBLE_CAUSE"
    CAUSAL_EXPLANATION = "CAUSAL_EXPLANATION"
    MEASUREMENT_PROPOSAL = "MEASUREMENT_PROPOSAL"


class ClaimSubjectKind(StrEnum):
    CONTEXT = "CONTEXT"
    DESIGN_EVIDENCE = "DESIGN_EVIDENCE"
    DESIGN_TARGET = "DESIGN_TARGET"
    MEASUREMENT_EVIDENCE = "MEASUREMENT_EVIDENCE"
    COMPARISON = "COMPARISON"
    LIMITATION = "LIMITATION"
    WARNING = "WARNING"
    QUALITY = "QUALITY"
    COHERENCE = "COHERENCE"
    UNRESOLVED_QUESTION = "UNRESOLVED_QUESTION"


class ClaimSupportBasis(StrEnum):
    EXACT_RESTATEMENT = "EXACT_RESTATEMENT"
    DETERMINISTIC_DERIVATION = "DETERMINISTIC_DERIVATION"
    REVIEWED_MULTI_EVIDENCE_RULE = "REVIEWED_MULTI_EVIDENCE_RULE"
    INSUFFICIENT = "INSUFFICIENT"


class ClaimReasonCode(StrEnum):
    EXACT_EVIDENCE_AVAILABLE = "EXACT_EVIDENCE_AVAILABLE"
    EXACT_TARGET_AVAILABLE = "EXACT_TARGET_AVAILABLE"
    EXACT_LIMITATION_AVAILABLE = "EXACT_LIMITATION_AVAILABLE"
    EXISTING_COMPARISON_SUPPORTS_STATEMENT = "EXISTING_COMPARISON_SUPPORTS_STATEMENT"
    ACCEPTANCE_CRITERION_UNAVAILABLE = "ACCEPTANCE_CRITERION_UNAVAILABLE"
    EVIDENCE_UNAVAILABLE = "EVIDENCE_UNAVAILABLE"
    COMPARISON_DOES_NOT_SUPPORT_CRITERION = "COMPARISON_DOES_NOT_SUPPORT_CRITERION"
    GOAL_NOT_RELEVANT = "GOAL_NOT_RELEVANT"
    UNKNOWN_OR_STALE_SUBJECT = "UNKNOWN_OR_STALE_SUBJECT"
    NO_REVIEWED_KNOWLEDGE_SOURCE = "NO_REVIEWED_KNOWLEDGE_SOURCE"
    NO_REVIEWED_INFERENCE_RULE = "NO_REVIEWED_INFERENCE_RULE"
    NO_REVIEWED_HYPOTHESIS_RULE = "NO_REVIEWED_HYPOTHESIS_RULE"
    NO_REVIEWED_CAUSAL_RULE = "NO_REVIEWED_CAUSAL_RULE"
    NEXT_MEASUREMENT_DEFERRED = "NEXT_MEASUREMENT_DEFERRED"


class PublicationObligation(StrEnum):
    ATTRIBUTE_DESIGN_OBSERVATION = "ATTRIBUTE_DESIGN_OBSERVATION"
    ATTRIBUTE_USER_STATEMENT = "ATTRIBUTE_USER_STATEMENT"
    ATTRIBUTE_USER_TARGET = "ATTRIBUTE_USER_TARGET"
    ATTRIBUTE_DESIGN_TARGET = "ATTRIBUTE_DESIGN_TARGET"
    ATTRIBUTE_INSTRUMENT_SOURCE = "ATTRIBUTE_INSTRUMENT_SOURCE"
    ATTRIBUTE_SOFTWARE_ANALYSIS = "ATTRIBUTE_SOFTWARE_ANALYSIS"
    ATTRIBUTE_SIMULATED_SOURCE = "ATTRIBUTE_SIMULATED_SOURCE"
    PRESERVE_UNAVAILABLE = "PRESERVE_UNAVAILABLE"
    PRESERVE_DEGRADED_QUALITY = "PRESERVE_DEGRADED_QUALITY"
    INCLUDE_MATERIAL_WARNINGS = "INCLUDE_MATERIAL_WARNINGS"
    PRESERVE_SEQUENTIAL_COHERENCE = "PRESERVE_SEQUENTIAL_COHERENCE"
    DO_NOT_CLAIM_SIMULTANEOUS_OR_ATOMIC = "DO_NOT_CLAIM_SIMULTANEOUS_OR_ATOMIC"
    PRESERVE_OBSERVATION_IDENTITY_LIMIT = "PRESERVE_OBSERVATION_IDENTITY_LIMIT"
    DO_NOT_CLAIM_DESIGN_IMMUTABILITY = "DO_NOT_CLAIM_DESIGN_IMMUTABILITY"
    STATE_TOLERANCE_UNSPECIFIED = "STATE_TOLERANCE_UNSPECIFIED"
    STATE_COMPLIANCE_UNDETERMINED = "STATE_COMPLIANCE_UNDETERMINED"
    PRESERVE_COMPARISON_REASON = "PRESERVE_COMPARISON_REASON"


class TeachingGoal(StrEnum):
    EXPLAIN_MEASUREMENT = "EXPLAIN_MEASUREMENT"
    ASSESS_REQUIREMENT = "ASSESS_REQUIREMENT"
    EXPLAIN_CAUSE = "EXPLAIN_CAUSE"


@dataclass(frozen=True, slots=True)
class ClaimSubjectRef:
    """Context-bound content identity; not trust, freshness, proof, or authority."""

    context_fingerprint: str
    kind: ClaimSubjectKind
    canonical_key: str

    def __post_init__(self) -> None:
        _validate_fingerprint(self.context_fingerprint)
        if not isinstance(self.kind, ClaimSubjectKind):
            raise ValueError("kind must be ClaimSubjectKind")
        if not isinstance(self.canonical_key, str) or not self.canonical_key.strip():
            raise ValueError("canonical_key must be non-empty")
        if len(self.canonical_key) > 512:
            raise ValueError("canonical_key is too large")

    @property
    def canonical_sort_key(self) -> tuple[str, str, str]:
        return (self.kind.value, self.canonical_key, self.context_fingerprint)


@dataclass(frozen=True, slots=True)
class ClaimPermission:
    """A content identity bound policy result, not a publication authorization."""

    claim_kind: ClaimKind
    claim_form: ClaimForm
    subject: ClaimSubjectRef
    decision: ClaimDecision
    support_basis: ClaimSupportBasis
    reason_codes: tuple[ClaimReasonCode, ...]
    support_refs: tuple[ClaimSubjectRef, ...]
    obligations: tuple[PublicationObligation, ...]
    obligation_refs: tuple[ClaimSubjectRef, ...]
    policy_name: str
    policy_version: str

    def __post_init__(self) -> None:
        for value, expected, name in (
            (self.claim_kind, ClaimKind, "claim_kind"),
            (self.claim_form, ClaimForm, "claim_form"),
            (self.decision, ClaimDecision, "decision"),
            (self.support_basis, ClaimSupportBasis, "support_basis"),
        ):
            if not isinstance(value, expected):
                raise ValueError(f"{name} has an invalid type")
        if not isinstance(self.subject, ClaimSubjectRef):
            raise ValueError("subject must be ClaimSubjectRef")
        _validate_text(self.policy_name, "policy_name")
        _validate_text(self.policy_version, "policy_version")
        _enum_tuple(self.reason_codes, ClaimReasonCode, "reason_codes", required=True)
        _ref_tuple(self.support_refs, "support_refs")
        _enum_tuple(self.obligations, PublicationObligation, "obligations")
        _ref_tuple(self.obligation_refs, "obligation_refs")
        for ref in self.support_refs + self.obligation_refs:
            if ref.context_fingerprint != self.subject.context_fingerprint:
                raise ValueError("permission references must share the subject context")
        if self.decision is ClaimDecision.ALLOW:
            if self.support_basis is ClaimSupportBasis.INSUFFICIENT or not self.support_refs:
                raise ValueError("ALLOW requires concrete support")
        elif self.support_basis is not ClaimSupportBasis.INSUFFICIENT:
            raise ValueError("BLOCK must use INSUFFICIENT support basis")

    @property
    def canonical_sort_key(self) -> tuple[str, str, str, str]:
        return (
            self.claim_kind.value,
            self.claim_form.value,
            self.subject.kind.value,
            self.subject.canonical_key,
        )

    def publication_prerequisites_satisfied(
        self,
        *,
        support_refs: tuple[ClaimSubjectRef, ...],
        fulfilled_obligations: tuple[PublicationObligation, ...],
        fulfilled_obligation_refs: tuple[ClaimSubjectRef, ...] = (),
    ) -> bool:
        """Check local obligations only; Grounding and Egress are still required."""

        return (
            self.decision is ClaimDecision.ALLOW
            and set(self.support_refs).issubset(set(support_refs))
            and set(self.obligations).issubset(set(fulfilled_obligations))
            and set(self.obligation_refs).issubset(set(fulfilled_obligation_refs))
        )


@dataclass(frozen=True, slots=True)
class AllowedClaimEnvelope:
    """Deterministic content identity and scoped policy; not authorization or proof."""

    envelope_id: str
    context_fingerprint: str
    goal: TeachingGoal
    policy_name: str
    policy_version: str
    permissions: tuple[ClaimPermission, ...]
    unresolved_question_refs: tuple[ClaimSubjectRef, ...]

    def __post_init__(self) -> None:
        _validate_fingerprint(self.envelope_id)
        _validate_fingerprint(self.context_fingerprint)
        if not isinstance(self.goal, TeachingGoal):
            raise ValueError("goal must be TeachingGoal")
        _validate_text(self.policy_name, "policy_name")
        _validate_text(self.policy_version, "policy_version")
        if not isinstance(self.permissions, tuple) or not all(
            isinstance(value, ClaimPermission) for value in self.permissions
        ):
            raise ValueError("permissions must be a tuple of ClaimPermission")
        _ref_tuple(self.unresolved_question_refs, "unresolved_question_refs")
        if self.permissions != tuple(sorted(self.permissions, key=lambda item: item.canonical_sort_key)):
            raise ValueError("permissions must use canonical ordering")
        slots = [value.canonical_sort_key for value in self.permissions]
        if len(slots) != len(set(slots)):
            raise ValueError("claim slots must be unique")
        for permission in self.permissions:
            if permission.subject.context_fingerprint != self.context_fingerprint:
                raise ValueError("permission belongs to another context")
            if permission.policy_name != self.policy_name or permission.policy_version != self.policy_version:
                raise ValueError("permission policy identity must match the envelope")
        for question in self.unresolved_question_refs:
            if question.context_fingerprint != self.context_fingerprint:
                raise ValueError("unresolved question belongs to another context")

    @classmethod
    def create(
        cls,
        *,
        context_fingerprint: str,
        goal: TeachingGoal,
        policy_name: str,
        policy_version: str,
        permissions: tuple[ClaimPermission, ...],
        unresolved_question_refs: tuple[ClaimSubjectRef, ...],
    ) -> AllowedClaimEnvelope:
        _validate_fingerprint(context_fingerprint)
        if not isinstance(goal, TeachingGoal):
            raise ValueError("goal must be TeachingGoal")
        permission_values = tuple(sorted(tuple(permissions), key=lambda item: item.canonical_sort_key))
        question_values = tuple(sorted(tuple(unresolved_question_refs), key=lambda item: item.canonical_sort_key))
        keys = [item.canonical_sort_key for item in permission_values]
        if len(keys) != len(set(keys)):
            raise ValueError("claim slots must be unique")
        for permission in permission_values:
            if permission.subject.context_fingerprint != context_fingerprint:
                raise ValueError("permission belongs to another context")
        for question in question_values:
            if question.context_fingerprint != context_fingerprint:
                raise ValueError("unresolved question belongs to another context")
        canonical = {
            "context": context_fingerprint,
            "goal": goal.value,
            "policy": [policy_name, policy_version],
            "permissions": [_permission_identity(value) for value in permission_values],
            "unresolved": [value.canonical_sort_key for value in question_values],
        }
        envelope_id = "sha256:" + hashlib.sha256(
            json.dumps(canonical, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()
        return cls(
            envelope_id=envelope_id,
            context_fingerprint=context_fingerprint,
            goal=goal,
            policy_name=policy_name,
            policy_version=policy_version,
            permissions=permission_values,
            unresolved_question_refs=question_values,
        )

    def permission_for(
        self,
        claim_kind: ClaimKind,
        claim_form: ClaimForm,
        subject: ClaimSubjectRef,
    ) -> ClaimPermission:
        for permission in self.permissions:
            if (
                permission.claim_kind is claim_kind
                and permission.claim_form is claim_form
                and permission.subject == subject
            ):
                return permission
        return ClaimPermission(
            claim_kind=claim_kind,
            claim_form=claim_form,
            subject=subject,
            decision=ClaimDecision.BLOCK,
            support_basis=ClaimSupportBasis.INSUFFICIENT,
            reason_codes=(ClaimReasonCode.UNKNOWN_OR_STALE_SUBJECT,),
            support_refs=(),
            obligations=(),
            obligation_refs=(),
            policy_name=self.policy_name,
            policy_version=self.policy_version,
        )


@dataclass(frozen=True, slots=True)
class DeterministicFallback:
    envelope_id: str
    context_fingerprint: str
    permissions: tuple[ClaimPermission, ...]

    def __post_init__(self) -> None:
        _validate_fingerprint(self.envelope_id)
        _validate_fingerprint(self.context_fingerprint)
        if not isinstance(self.permissions, tuple) or not all(
            isinstance(value, ClaimPermission) for value in self.permissions
        ):
            raise ValueError("permissions must be a tuple of ClaimPermission")
        if any(value.decision is not ClaimDecision.ALLOW for value in self.permissions):
            raise ValueError("fallback can contain only allowed permissions")
        allowed = {
            ClaimKind.EVIDENCE_RESTATEMENT,
            ClaimKind.DETERMINISTIC_COMPARISON_STATEMENT,
            ClaimKind.LIMITATION_STATEMENT,
        }
        if any(value.claim_kind not in allowed for value in self.permissions):
            raise ValueError("fallback contains an unsupported claim kind")


def _permission_identity(permission: ClaimPermission) -> dict[str, object]:
    return {
        "slot": permission.canonical_sort_key,
        "decision": permission.decision.value,
        "basis": permission.support_basis.value,
        "reasons": tuple(value.value for value in permission.reason_codes),
        "support": tuple(value.canonical_sort_key for value in permission.support_refs),
        "obligations": tuple(value.value for value in permission.obligations),
        "obligation_refs": tuple(value.canonical_sort_key for value in permission.obligation_refs),
    }


def _validate_fingerprint(value: str) -> None:
    if not isinstance(value, str) or len(value) != 71 or not value.startswith("sha256:"):
        raise ValueError("context_fingerprint must be sha256:<64 lowercase hex>")
    try:
        int(value[7:], 16)
    except ValueError as exc:
        raise ValueError("context_fingerprint must be sha256:<64 lowercase hex>") from exc
    if value[7:] != value[7:].lower():
        raise ValueError("context_fingerprint must use lowercase hex")


def _validate_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty")


def _enum_tuple(values: tuple, expected: type, name: str, *, required: bool = False) -> None:
    if not isinstance(values, tuple) or not all(isinstance(value, expected) for value in values):
        raise ValueError(f"{name} must be a tuple of {expected.__name__}")
    if required and not values:
        raise ValueError(f"{name} must not be empty")
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must not contain duplicates")


def _ref_tuple(values: tuple[ClaimSubjectRef, ...], name: str) -> None:
    if not isinstance(values, tuple) or not all(isinstance(value, ClaimSubjectRef) for value in values):
        raise ValueError(f"{name} must be a tuple of ClaimSubjectRef")
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must not contain duplicates")
