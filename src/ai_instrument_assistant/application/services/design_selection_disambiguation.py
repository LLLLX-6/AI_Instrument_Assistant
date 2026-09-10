from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import NAMESPACE_URL, UUID, uuid5

from ...domain.eda.models import (
    DesignObjectKind,
    DesignObjectRef,
    ProbeTarget,
    ProbeTargetKind,
    SelectionContext,
)
from ...domain.errors import DomainInvariantError


CANDIDATE_FINGERPRINT_SCOPE = "design-selection-candidate-identities/v1"
_TRUSTED_ISSUER_TOKEN = object()


class TrustedDesignSelectionOrigin(StrEnum):
    TRUSTED_HOST_USER_EVENT = "TRUSTED_HOST_USER_EVENT"


class TrustedDesignSelectionResolutionStatus(StrEnum):
    RESOLVED = "RESOLVED"
    DECISION_REQUIRED = "DECISION_REQUIRED"
    INVALID_DECISION = "INVALID_DECISION"
    UNSUPPORTED_CHOICE = "UNSUPPORTED_CHOICE"
    DERIVED_TARGET_AMBIGUOUS = "DERIVED_TARGET_AMBIGUOUS"


class TrustedDesignSelectionReason(StrEnum):
    RESOLVED = "RESOLVED"
    TRUSTED_DECISION_REQUIRED = "TRUSTED_DECISION_REQUIRED"
    SELECTION_NOT_AMBIGUOUS = "SELECTION_NOT_AMBIGUOUS"
    WORKFLOW_MISMATCH = "WORKFLOW_MISMATCH"
    REQUEST_MISMATCH = "REQUEST_MISMATCH"
    PROVIDER_MISMATCH = "PROVIDER_MISMATCH"
    DOCUMENT_MISMATCH = "DOCUMENT_MISMATCH"
    SNAPSHOT_MISMATCH = "SNAPSHOT_MISMATCH"
    OBSERVATION_TIME_MISMATCH = "OBSERVATION_TIME_MISMATCH"
    CANDIDATE_SET_MISMATCH = "CANDIDATE_SET_MISMATCH"
    FINGERPRINT_MISMATCH = "FINGERPRINT_MISMATCH"
    CHOSEN_CANDIDATE_ABSENT = "CHOSEN_CANDIDATE_ABSENT"
    STALE_DECISION = "STALE_DECISION"
    CHOSEN_OBJECT_UNSUPPORTED = "CHOSEN_OBJECT_UNSUPPORTED"
    DERIVED_NET_UNAVAILABLE = "DERIVED_NET_UNAVAILABLE"
    MULTIPLE_DERIVED_NETS = "MULTIPLE_DERIVED_NETS"
    WIRE_NET_RELATION_UNRESOLVED = "WIRE_NET_RELATION_UNRESOLVED"


@dataclass(frozen=True, slots=True, order=True)
class DesignSelectionCandidateIdentity:
    """Stable bounded identity; presentation and provider raw data are excluded."""

    provider: str
    document_id: str
    snapshot_id: UUID
    object_type: DesignObjectKind
    canonical_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", _text(self.provider, "provider"))
        object.__setattr__(self, "document_id", _text(self.document_id, "document_id"))
        object.__setattr__(self, "canonical_id", _text(self.canonical_id, "canonical_id"))
        if not isinstance(self.snapshot_id, UUID):
            raise DomainInvariantError("snapshot_id must be UUID")
        if not isinstance(self.object_type, DesignObjectKind):
            raise DomainInvariantError("object_type must be DesignObjectKind")

    @classmethod
    def from_ref(cls, value: DesignObjectRef) -> DesignSelectionCandidateIdentity:
        if not isinstance(value, DesignObjectRef):
            raise DomainInvariantError("candidate identity requires DesignObjectRef")
        return cls(
            provider=value.provider,
            document_id=value.document_id,
            snapshot_id=value.snapshot_id,
            object_type=value.object_type,
            canonical_id=value.canonical_id,
        )


@dataclass(frozen=True, slots=True)
class DesignSelectionCandidateSetBinding:
    """Exact bounded candidate presentation bound to one selection observation."""

    document_ref: DesignObjectRef
    selection_observed_at: datetime
    presented_candidates: tuple[DesignObjectRef, ...]
    candidate_identities: tuple[DesignSelectionCandidateIdentity, ...]
    fingerprint_scope: str
    candidate_set_fingerprint: str

    def __post_init__(self) -> None:
        if not isinstance(self.document_ref, DesignObjectRef):
            raise DomainInvariantError("document_ref must be DesignObjectRef")
        if self.document_ref.object_type is not DesignObjectKind.DOCUMENT:
            raise DomainInvariantError("candidate binding requires document reference")
        _aware(self.selection_observed_at, "selection_observed_at")
        candidates = tuple(self.presented_candidates)
        identities = tuple(self.candidate_identities)
        if len(candidates) < 2:
            raise DomainInvariantError("candidate binding requires an ambiguous selection")
        if not all(isinstance(item, DesignObjectRef) for item in candidates):
            raise DomainInvariantError("presented candidates must be DesignObjectRef values")
        derived_identities = tuple(
            DesignSelectionCandidateIdentity.from_ref(item) for item in candidates
        )
        if identities != derived_identities:
            raise DomainInvariantError("candidate identities must match presented candidates")
        if len(set(identities)) != len(identities):
            raise DomainInvariantError("candidate identities must be unique")
        document_identity = DesignSelectionCandidateIdentity.from_ref(self.document_ref)
        for identity in identities:
            if (
                identity.provider != document_identity.provider
                or identity.document_id != document_identity.document_id
                or identity.snapshot_id != document_identity.snapshot_id
            ):
                raise DomainInvariantError(
                    "candidate identities must belong to the bound document observation"
                )
        if self.fingerprint_scope != CANDIDATE_FINGERPRINT_SCOPE:
            raise DomainInvariantError("unsupported candidate fingerprint scope")
        fingerprint = _text(
            self.candidate_set_fingerprint,
            "candidate_set_fingerprint",
        )
        if not _is_sha256(fingerprint):
            raise DomainInvariantError("candidate_set_fingerprint must be sha256:<hex>")
        object.__setattr__(self, "presented_candidates", candidates)
        object.__setattr__(self, "candidate_identities", identities)
        object.__setattr__(self, "candidate_set_fingerprint", fingerprint)


@dataclass(frozen=True, slots=True, init=False)
class TrustedDesignSelectionDecision:
    """Trusted Host-issued choice. Direct construction from external data is disabled."""

    decision_id: UUID
    workflow_id: str
    request_correlation_id: str
    candidate_binding: DesignSelectionCandidateSetBinding
    selected_object: DesignObjectRef
    selected_identity: DesignSelectionCandidateIdentity
    trusted_origin: TrustedDesignSelectionOrigin
    decided_at: datetime

    @classmethod
    def _issue(
        cls,
        *,
        issuer_token: object,
        decision_id: UUID,
        workflow_id: str,
        request_correlation_id: str,
        candidate_binding: DesignSelectionCandidateSetBinding,
        selected_object: DesignObjectRef,
        selected_identity: DesignSelectionCandidateIdentity,
        decided_at: datetime,
    ) -> TrustedDesignSelectionDecision:
        if issuer_token is not _TRUSTED_ISSUER_TOKEN:
            raise DomainInvariantError("trusted decision requires Host issuer boundary")
        value = object.__new__(cls)
        object.__setattr__(value, "decision_id", decision_id)
        object.__setattr__(value, "workflow_id", workflow_id)
        object.__setattr__(value, "request_correlation_id", request_correlation_id)
        object.__setattr__(value, "candidate_binding", candidate_binding)
        object.__setattr__(value, "selected_object", selected_object)
        object.__setattr__(value, "selected_identity", selected_identity)
        object.__setattr__(
            value,
            "trusted_origin",
            TrustedDesignSelectionOrigin.TRUSTED_HOST_USER_EVENT,
        )
        object.__setattr__(value, "decided_at", decided_at)
        value.__post_init__()
        return value

    def __post_init__(self) -> None:
        if not isinstance(self.decision_id, UUID):
            raise DomainInvariantError("decision_id must be UUID")
        object.__setattr__(self, "workflow_id", _text(self.workflow_id, "workflow_id"))
        object.__setattr__(
            self,
            "request_correlation_id",
            _text(self.request_correlation_id, "request_correlation_id"),
        )
        if not isinstance(self.candidate_binding, DesignSelectionCandidateSetBinding):
            raise DomainInvariantError("candidate_binding must be a bounded binding")
        if self.trusted_origin is not TrustedDesignSelectionOrigin.TRUSTED_HOST_USER_EVENT:
            raise DomainInvariantError("trusted decision requires trusted Host user event")
        if not isinstance(self.selected_object, DesignObjectRef):
            raise DomainInvariantError("selected_object must be DesignObjectRef")
        if not isinstance(self.selected_identity, DesignSelectionCandidateIdentity):
            raise DomainInvariantError("selected_identity must be bounded candidate identity")
        if DesignSelectionCandidateIdentity.from_ref(self.selected_object) != self.selected_identity:
            raise DomainInvariantError("selected object and identity differ")
        if self.selected_object not in self.candidate_binding.presented_candidates:
            raise DomainInvariantError("selected object must be an exact presented candidate")
        if self.selected_identity not in self.candidate_binding.candidate_identities:
            raise DomainInvariantError("selected identity must belong to candidate set")
        _aware(self.decided_at, "decided_at")
        if self.decided_at < self.candidate_binding.selection_observed_at:
            raise DomainInvariantError("decision cannot predate its selection observation")


@dataclass(frozen=True, slots=True)
class TrustedDesignSelectionResolution:
    status: TrustedDesignSelectionResolutionStatus
    reason: TrustedDesignSelectionReason
    provider_selection: SelectionContext
    candidate_binding: DesignSelectionCandidateSetBinding
    decision: TrustedDesignSelectionDecision | None
    chosen_candidate: DesignObjectRef | None
    derived_target: DesignObjectRef | None
    probe_target: ProbeTarget | None

    def __post_init__(self) -> None:
        if not isinstance(self.status, TrustedDesignSelectionResolutionStatus):
            raise DomainInvariantError("resolution status is invalid")
        if not isinstance(self.reason, TrustedDesignSelectionReason):
            raise DomainInvariantError("resolution reason is invalid")
        if not isinstance(self.provider_selection, SelectionContext):
            raise DomainInvariantError("provider_selection must be SelectionContext")
        if not isinstance(self.candidate_binding, DesignSelectionCandidateSetBinding):
            raise DomainInvariantError("candidate_binding is invalid")
        if self.status is TrustedDesignSelectionResolutionStatus.RESOLVED:
            if (
                self.reason is not TrustedDesignSelectionReason.RESOLVED
                or self.decision is None
                or self.chosen_candidate is None
                or self.derived_target is None
                or self.probe_target is None
            ):
                raise DomainInvariantError("resolved result requires complete derivation provenance")
        elif self.probe_target is not None:
            raise DomainInvariantError("non-resolved decision cannot create ProbeTarget")


def build_candidate_set_binding(
    *,
    selection_context: SelectionContext,
    selection_observed_at: datetime,
) -> DesignSelectionCandidateSetBinding:
    if not isinstance(selection_context, SelectionContext):
        raise DomainInvariantError("selection_context must be SelectionContext")
    _aware(selection_observed_at, "selection_observed_at")
    selection = selection_context.selection
    candidates = tuple(selection.selected_objects)
    identities = tuple(
        DesignSelectionCandidateIdentity.from_ref(item) for item in candidates
    )
    return DesignSelectionCandidateSetBinding(
        document_ref=selection.document_ref,
        selection_observed_at=selection_observed_at,
        presented_candidates=candidates,
        candidate_identities=identities,
        fingerprint_scope=CANDIDATE_FINGERPRINT_SCOPE,
        candidate_set_fingerprint=_candidate_set_fingerprint(
            selection.document_ref,
            identities,
        ),
    )


def candidate_choice_tokens(
    binding: DesignSelectionCandidateSetBinding,
) -> tuple[tuple[str, DesignSelectionCandidateIdentity], ...]:
    if not isinstance(binding, DesignSelectionCandidateSetBinding):
        raise DomainInvariantError("choice tokens require candidate binding")
    pairs: list[tuple[str, DesignSelectionCandidateIdentity]] = []
    for identity in binding.candidate_identities:
        serialized = _canonical_json(
            {
                "binding": binding.candidate_set_fingerprint,
                "candidate": _identity_payload(identity),
                "scope": "design-selection-choice-token/v1",
            }
        )
        pairs.append((f"choice:{hashlib.sha256(serialized).hexdigest()}", identity))
    return tuple(pairs)


def issue_trusted_design_selection_decision(
    *,
    decision_id: UUID,
    candidate_binding: DesignSelectionCandidateSetBinding,
    selected_candidate: DesignSelectionCandidateIdentity,
    workflow_id: str,
    request_correlation_id: str,
    decided_at: datetime,
) -> TrustedDesignSelectionDecision:
    """Host-only issuer from an exact typed candidate selected by bounded UI."""

    if not isinstance(candidate_binding, DesignSelectionCandidateSetBinding):
        raise DomainInvariantError("candidate_binding must be bounded binding")
    if not isinstance(selected_candidate, DesignSelectionCandidateIdentity):
        raise DomainInvariantError("trusted UI must provide an exact candidate identity")
    if candidate_binding.candidate_set_fingerprint != _candidate_set_fingerprint(
        candidate_binding.document_ref,
        candidate_binding.candidate_identities,
    ):
        raise DomainInvariantError("candidate binding fingerprint is invalid")
    matches = tuple(
        candidate
        for candidate in candidate_binding.presented_candidates
        if DesignSelectionCandidateIdentity.from_ref(candidate) == selected_candidate
    )
    if len(matches) != 1:
        raise DomainInvariantError("selected candidate must occur exactly once in candidate set")
    return TrustedDesignSelectionDecision._issue(
        issuer_token=_TRUSTED_ISSUER_TOKEN,
        decision_id=decision_id,
        workflow_id=_text(workflow_id, "workflow_id"),
        request_correlation_id=_text(
            request_correlation_id,
            "request_correlation_id",
        ),
        candidate_binding=candidate_binding,
        selected_object=matches[0],
        selected_identity=selected_candidate,
        decided_at=decided_at,
    )


def resolve_trusted_design_selection(
    *,
    current_selection: SelectionContext,
    current_binding: DesignSelectionCandidateSetBinding,
    decision: TrustedDesignSelectionDecision | None,
    trusted_workflow_id: str,
    trusted_request_correlation_id: str,
) -> TrustedDesignSelectionResolution:
    if not isinstance(current_selection, SelectionContext):
        raise DomainInvariantError("current_selection must be SelectionContext")
    if not isinstance(current_binding, DesignSelectionCandidateSetBinding):
        raise DomainInvariantError("current_binding must be bounded binding")
    trusted_workflow_id = _text(trusted_workflow_id, "trusted_workflow_id")
    trusted_request_correlation_id = _text(
        trusted_request_correlation_id,
        "trusted_request_correlation_id",
    )

    if not _binding_matches_selection(current_binding, current_selection):
        return _invalid(
            TrustedDesignSelectionReason.CANDIDATE_SET_MISMATCH,
            current_selection,
            current_binding,
            decision,
        )
    expected_fingerprint = _candidate_set_fingerprint(
        current_binding.document_ref,
        current_binding.candidate_identities,
    )
    if current_binding.candidate_set_fingerprint != expected_fingerprint:
        return _invalid(
            TrustedDesignSelectionReason.FINGERPRINT_MISMATCH,
            current_selection,
            current_binding,
            decision,
        )
    selected = current_selection.selection.selected_objects
    if len(selected) < 2 or current_selection.selection.primary_object is not None:
        return _invalid(
            TrustedDesignSelectionReason.SELECTION_NOT_AMBIGUOUS,
            current_selection,
            current_binding,
            decision,
        )
    if decision is None:
        return _resolution(
            TrustedDesignSelectionResolutionStatus.DECISION_REQUIRED,
            TrustedDesignSelectionReason.TRUSTED_DECISION_REQUIRED,
            current_selection,
            current_binding,
            None,
        )
    if not isinstance(decision, TrustedDesignSelectionDecision):
        raise DomainInvariantError("decision must be trusted decision or None")
    if decision.workflow_id != trusted_workflow_id:
        return _invalid(TrustedDesignSelectionReason.WORKFLOW_MISMATCH, current_selection, current_binding, decision)
    if decision.request_correlation_id != trusted_request_correlation_id:
        return _invalid(TrustedDesignSelectionReason.REQUEST_MISMATCH, current_selection, current_binding, decision)

    old_doc = decision.candidate_binding.document_ref
    new_doc = current_binding.document_ref
    if old_doc.provider != new_doc.provider:
        return _invalid(TrustedDesignSelectionReason.PROVIDER_MISMATCH, current_selection, current_binding, decision)
    if (old_doc.document_id, old_doc.canonical_id) != (
        new_doc.document_id,
        new_doc.canonical_id,
    ):
        return _invalid(TrustedDesignSelectionReason.DOCUMENT_MISMATCH, current_selection, current_binding, decision)
    if old_doc.snapshot_id != new_doc.snapshot_id:
        return _invalid(TrustedDesignSelectionReason.SNAPSHOT_MISMATCH, current_selection, current_binding, decision)
    if decision.decided_at < current_binding.selection_observed_at:
        return _invalid(TrustedDesignSelectionReason.STALE_DECISION, current_selection, current_binding, decision)
    if (
        decision.candidate_binding.selection_observed_at
        != current_binding.selection_observed_at
    ):
        return _invalid(
            TrustedDesignSelectionReason.OBSERVATION_TIME_MISMATCH,
            current_selection,
            current_binding,
            decision,
        )
    if decision.candidate_binding.fingerprint_scope != current_binding.fingerprint_scope:
        return _invalid(TrustedDesignSelectionReason.FINGERPRINT_MISMATCH, current_selection, current_binding, decision)
    old_identities = frozenset(decision.candidate_binding.candidate_identities)
    new_identities = frozenset(current_binding.candidate_identities)
    if old_identities != new_identities:
        reason = (
            TrustedDesignSelectionReason.CHOSEN_CANDIDATE_ABSENT
            if decision.selected_identity not in new_identities
            else TrustedDesignSelectionReason.CANDIDATE_SET_MISMATCH
        )
        return _invalid(reason, current_selection, current_binding, decision)
    if (
        decision.candidate_binding.candidate_set_fingerprint
        != current_binding.candidate_set_fingerprint
    ):
        return _invalid(TrustedDesignSelectionReason.FINGERPRINT_MISMATCH, current_selection, current_binding, decision)
    current_matches = tuple(
        item
        for item in selected
        if DesignSelectionCandidateIdentity.from_ref(item) == decision.selected_identity
    )
    if len(current_matches) != 1:
        return _invalid(TrustedDesignSelectionReason.CHOSEN_CANDIDATE_ABSENT, current_selection, current_binding, decision)

    chosen = current_matches[0]
    if chosen.object_type is DesignObjectKind.NET:
        return _resolved(current_selection, current_binding, decision, chosen, chosen)
    if chosen.object_type is not DesignObjectKind.WIRE:
        return _resolution(
            TrustedDesignSelectionResolutionStatus.UNSUPPORTED_CHOICE,
            TrustedDesignSelectionReason.CHOSEN_OBJECT_UNSUPPORTED,
            current_selection,
            current_binding,
            decision,
            chosen=chosen,
        )
    if sum(item.object_type is DesignObjectKind.WIRE for item in selected) != 1:
        return _resolution(
            TrustedDesignSelectionResolutionStatus.DERIVED_TARGET_AMBIGUOUS,
            TrustedDesignSelectionReason.WIRE_NET_RELATION_UNRESOLVED,
            current_selection,
            current_binding,
            decision,
            chosen=chosen,
        )
    if not current_selection.nets:
        return _resolution(
            TrustedDesignSelectionResolutionStatus.UNSUPPORTED_CHOICE,
            TrustedDesignSelectionReason.DERIVED_NET_UNAVAILABLE,
            current_selection,
            current_binding,
            decision,
            chosen=chosen,
        )
    if len(current_selection.nets) != 1:
        return _resolution(
            TrustedDesignSelectionResolutionStatus.DERIVED_TARGET_AMBIGUOUS,
            TrustedDesignSelectionReason.MULTIPLE_DERIVED_NETS,
            current_selection,
            current_binding,
            decision,
            chosen=chosen,
        )
    return _resolved(
        current_selection,
        current_binding,
        decision,
        chosen,
        current_selection.nets[0].ref,
    )


def _resolved(
    selection: SelectionContext,
    binding: DesignSelectionCandidateSetBinding,
    decision: TrustedDesignSelectionDecision,
    chosen: DesignObjectRef,
    target: DesignObjectRef,
) -> TrustedDesignSelectionResolution:
    probe = ProbeTarget(
        target_id=uuid5(
            NAMESPACE_URL,
            "/".join(
                (
                    "ai-instrument-assistant",
                    "probe-target",
                    target.provider,
                    target.canonical_id,
                    str(target.snapshot_id),
                )
            ),
        ),
        design_object=target,
        kind=ProbeTargetKind.DESIGN_ONLY,
    )
    return TrustedDesignSelectionResolution(
        status=TrustedDesignSelectionResolutionStatus.RESOLVED,
        reason=TrustedDesignSelectionReason.RESOLVED,
        provider_selection=selection,
        candidate_binding=binding,
        decision=decision,
        chosen_candidate=chosen,
        derived_target=target,
        probe_target=probe,
    )


def _invalid(
    reason: TrustedDesignSelectionReason,
    selection: SelectionContext,
    binding: DesignSelectionCandidateSetBinding,
    decision: TrustedDesignSelectionDecision | None,
) -> TrustedDesignSelectionResolution:
    return _resolution(
        TrustedDesignSelectionResolutionStatus.INVALID_DECISION,
        reason,
        selection,
        binding,
        decision,
    )


def _resolution(
    status: TrustedDesignSelectionResolutionStatus,
    reason: TrustedDesignSelectionReason,
    selection: SelectionContext,
    binding: DesignSelectionCandidateSetBinding,
    decision: TrustedDesignSelectionDecision | None,
    *,
    chosen: DesignObjectRef | None = None,
) -> TrustedDesignSelectionResolution:
    return TrustedDesignSelectionResolution(
        status=status,
        reason=reason,
        provider_selection=selection,
        candidate_binding=binding,
        decision=decision,
        chosen_candidate=chosen,
        derived_target=None,
        probe_target=None,
    )


def _binding_matches_selection(
    binding: DesignSelectionCandidateSetBinding,
    selection: SelectionContext,
) -> bool:
    observed = selection.selection
    return (
        DesignSelectionCandidateIdentity.from_ref(binding.document_ref)
        == DesignSelectionCandidateIdentity.from_ref(observed.document_ref)
        and binding.presented_candidates == observed.selected_objects
        and binding.candidate_identities
        == tuple(
            DesignSelectionCandidateIdentity.from_ref(item)
            for item in observed.selected_objects
        )
    )


def _candidate_set_fingerprint(
    document_ref: DesignObjectRef,
    identities: tuple[DesignSelectionCandidateIdentity, ...],
) -> str:
    document_identity = DesignSelectionCandidateIdentity.from_ref(document_ref)
    candidates = sorted(
        (_identity_payload(identity) for identity in identities),
        key=lambda value: _canonical_json(value),
    )
    payload = {
        "scope": CANDIDATE_FINGERPRINT_SCOPE,
        "document": _identity_payload(document_identity),
        "candidates": candidates,
    }
    return f"sha256:{hashlib.sha256(_canonical_json(payload)).hexdigest()}"


def _identity_payload(identity: DesignSelectionCandidateIdentity) -> dict[str, str]:
    return {
        "provider": identity.provider,
        "document_id": identity.document_id,
        "snapshot_id": str(identity.snapshot_id),
        "object_type": identity.object_type.value,
        "canonical_id": identity.canonical_id,
    }


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _is_sha256(value: str) -> bool:
    if not value.startswith("sha256:") or len(value) != 71:
        return False
    try:
        int(value[7:], 16)
    except ValueError:
        return False
    return True


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainInvariantError(f"{field_name} must be non-empty text")
    return value.strip()


def _aware(value: object, field_name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise DomainInvariantError(f"{field_name} must be timezone-aware datetime")
