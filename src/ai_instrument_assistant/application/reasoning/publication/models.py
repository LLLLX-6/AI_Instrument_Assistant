from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
import re
from typing import Protocol

from ..models import ClaimPermission, PublicationObligation, TeachingGoal


MAX_PROJECTION_SLOTS = 64
MAX_CANDIDATE_CLAIMS = 12
MAX_RAW_CANDIDATE_BYTES = 16_384
MAX_MODEL_PROJECTION_BYTES = 65_536
RENDERER_VERSION = "AIA_CANONICAL_EN_V1"
_CONTENT_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
_ALIAS = re.compile(r"^p[0-9]{3}$")


@dataclass(frozen=True, slots=True)
class PublicationRenderAtom:
    source: str
    label: str
    value: str | None = None
    unit: str | None = None
    metric: str | None = None
    quality: str | None = None
    warnings: tuple[str, ...] = ()
    detail: str | None = None
    comparison_status: str | None = None
    comparison_reason: str | None = None
    expected: str | None = None
    observed: str | None = None
    difference: str | None = None

    def __post_init__(self) -> None:
        _bounded_text(self.source, "source", 64)
        _bounded_text(self.label, "label", 512)
        for name, maximum in (
            ("value", 128), ("unit", 32), ("metric", 64), ("quality", 32),
            ("detail", 512), ("comparison_status", 32),
            ("comparison_reason", 64), ("expected", 128),
            ("observed", 128), ("difference", 128),
        ):
            value = getattr(self, name)
            if value is not None:
                _bounded_text(value, name, maximum)
        if not isinstance(self.warnings, tuple) or len(self.warnings) > 16:
            raise ValueError("warnings must be a bounded tuple")
        for warning in self.warnings:
            _bounded_text(warning, "warning", 512)


@dataclass(frozen=True, slots=True)
class PublicationSlot:
    alias: str
    permission_content_id: str
    permission: ClaimPermission
    atom: PublicationRenderAtom
    renderable_obligations: tuple[PublicationObligation, ...]

    def __post_init__(self) -> None:
        if _ALIAS.fullmatch(self.alias) is None:
            raise ValueError("alias must be a bounded projection-local reference")
        _content_id(self.permission_content_id, "permission_content_id")
        if not isinstance(self.permission, ClaimPermission):
            raise ValueError("permission must be ClaimPermission")
        if not isinstance(self.atom, PublicationRenderAtom):
            raise ValueError("atom must be PublicationRenderAtom")
        if not isinstance(self.renderable_obligations, tuple) or not all(
            isinstance(item, PublicationObligation) for item in self.renderable_obligations
        ):
            raise ValueError("renderable_obligations must be PublicationObligation values")


@dataclass(frozen=True, slots=True)
class PublicationProjection:
    """Host-owned bounded content view; its digest is identity, not authority."""

    projection_id: str
    context_fingerprint: str
    envelope_id: str
    goal: TeachingGoal
    renderer_version: str
    slots: tuple[PublicationSlot, ...]

    def __post_init__(self) -> None:
        for name in ("projection_id", "context_fingerprint", "envelope_id"):
            _content_id(getattr(self, name), name)
        if not isinstance(self.goal, TeachingGoal):
            raise ValueError("goal must be TeachingGoal")
        if self.renderer_version != RENDERER_VERSION:
            raise ValueError("unsupported renderer version")
        if not isinstance(self.slots, tuple) or not all(isinstance(item, PublicationSlot) for item in self.slots):
            raise ValueError("slots must be a tuple of PublicationSlot")
        if len(self.slots) > MAX_PROJECTION_SLOTS:
            raise ValueError("projection slot limit exceeded")
        aliases = tuple(item.alias for item in self.slots)
        if len(aliases) != len(set(aliases)):
            raise ValueError("projection aliases must be unique")

    def slot_for_alias(self, alias: str) -> PublicationSlot | None:
        return next((slot for slot in self.slots if slot.alias == alias), None)

    def model_payload(self) -> dict[str, object]:
        payload = {
            "schema_id": "aia-teaching-selection-projection/v1",
            "projection_id": self.projection_id,
            "context_fingerprint": self.context_fingerprint,
            "envelope_id": self.envelope_id,
            "goal": self.goal.value,
            "claim_limit": MAX_CANDIDATE_CLAIMS,
            "slots": [
                {
                    "permission_ref": slot.alias,
                    "claim_kind": slot.permission.claim_kind.value,
                    "claim_form": slot.permission.claim_form.value,
                    "subject_kind": slot.permission.subject.kind.value,
                    "source_category": slot.atom.source,
                    "metric": slot.atom.metric,
                    "quality": slot.atom.quality,
                    "comparison_status": slot.atom.comparison_status,
                    "comparison_reason": slot.atom.comparison_reason,
                    "obligations": [item.value for item in slot.permission.obligations],
                }
                for slot in self.slots
            ],
        }
        if len(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")) > MAX_MODEL_PROJECTION_BYTES:
            raise ValueError("model projection exceeds its serialized bound")
        return payload


@dataclass(frozen=True, slots=True)
class StructuredClaimCandidateSet:
    schema_id: str
    projection_id: str
    context_fingerprint: str
    envelope_id: str
    goal: TeachingGoal
    ordered_permission_refs: tuple[str, ...]
    candidate_digest: str

    def __post_init__(self) -> None:
        if self.schema_id != "aia-teaching-claim-candidate/v1":
            raise ValueError("unsupported candidate schema")
        for name in ("projection_id", "context_fingerprint", "envelope_id", "candidate_digest"):
            _content_id(getattr(self, name), name)
        if not isinstance(self.goal, TeachingGoal):
            raise ValueError("goal must be TeachingGoal")
        if not isinstance(self.ordered_permission_refs, tuple):
            raise ValueError("ordered_permission_refs must be a tuple")
        if not 1 <= len(self.ordered_permission_refs) <= MAX_CANDIDATE_CLAIMS:
            raise ValueError("candidate claim count is outside the bounded range")
        if any(_ALIAS.fullmatch(item) is None for item in self.ordered_permission_refs):
            raise ValueError("invalid permission alias")
        if len(self.ordered_permission_refs) != len(set(self.ordered_permission_refs)):
            raise ValueError("duplicate permission alias")


@dataclass(frozen=True, slots=True)
class GroundedPublicationPlan:
    """Trusted resolved semantics only; never candidate-authored factual prose."""

    plan_id: str
    projection_id: str
    context_fingerprint: str
    envelope_id: str
    goal: TeachingGoal
    renderer_version: str
    slots: tuple[PublicationSlot, ...]
    fallback: bool

    def __post_init__(self) -> None:
        for name in ("plan_id", "projection_id", "context_fingerprint", "envelope_id"):
            _content_id(getattr(self, name), name)
        if not isinstance(self.goal, TeachingGoal):
            raise ValueError("goal must be TeachingGoal")
        if self.renderer_version != RENDERER_VERSION:
            raise ValueError("unsupported renderer version")
        if not isinstance(self.slots, tuple) or not self.slots or not all(
            isinstance(item, PublicationSlot) for item in self.slots
        ):
            raise ValueError("grounded plan requires trusted slots")
        if len(self.slots) > MAX_CANDIDATE_CLAIMS:
            raise ValueError("grounded plan claim limit exceeded")


class EgressStatus(StrEnum):
    SAFE = "SAFE"
    UNSAFE = "UNSAFE"


@dataclass(frozen=True, slots=True)
class EgressDecision:
    status: EgressStatus
    categories: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, EgressStatus):
            raise ValueError("status must be EgressStatus")
        if not isinstance(self.categories, tuple) or not all(
            isinstance(item, str) and item for item in self.categories
        ):
            raise ValueError("categories must be bounded strings")
        if self.status is EgressStatus.SAFE and self.categories:
            raise ValueError("SAFE decision cannot contain violations")
        if self.status is EgressStatus.UNSAFE and not self.categories:
            raise ValueError("UNSAFE decision requires a violation category")

    @classmethod
    def safe(cls) -> EgressDecision:
        return cls(EgressStatus.SAFE)

    @classmethod
    def unsafe(cls, categories: tuple[str, ...]) -> EgressDecision:
        return cls(EgressStatus.UNSAFE, tuple(categories))


class FinalEgressInspector(Protocol):
    """Port implemented by the existing production Egress boundary in 8C.2B."""

    def inspect(self, text: str, *, correlation_id: str) -> EgressDecision: ...


class CandidateParser(Protocol):
    def parse(self, raw: str) -> StructuredClaimCandidateSet: ...


@dataclass(frozen=True, slots=True)
class PublicationAuditRecord:
    correlation_id: str
    trusted_goal: TeachingGoal
    context_fingerprint: str
    envelope_id: str
    projection_id: str
    candidate_digest: str
    selected_aliases: tuple[str, ...]
    grounding_decision: str
    grounded_plan_id: str | None
    renderer_version: str
    final_egress_decision: str
    fallback_used: bool
    publication_status: str
    failure_code: str | None
    model_request_count: int = 0
    tool_count: int = 0
    ipc_count: int = 0
    hardware_count: int = 0


@dataclass(frozen=True, slots=True)
class PublicationResult:
    status: str
    text: str
    audit: PublicationAuditRecord


def _content_id(value: str, name: str) -> None:
    if not isinstance(value, str) or _CONTENT_ID.fullmatch(value) is None:
        raise ValueError(f"{name} must be a sha256 content identity")


def _bounded_text(value: str, name: str, maximum: int) -> None:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ValueError(f"{name} must be non-empty bounded text")
