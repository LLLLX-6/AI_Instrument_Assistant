from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
from typing import Protocol
from uuid import UUID

from ..models import TeachingGoal
from .models import PublicationProjection


PROMPT_PROFILE = "AIA_STRUCTURED_CANDIDATE_V1"


class ModelFailureCode(StrEnum):
    MODEL_PROVIDER_UNAVAILABLE = "MODEL_PROVIDER_UNAVAILABLE"
    MODEL_REQUEST_TIMEOUT = "MODEL_REQUEST_TIMEOUT"
    MODEL_REQUEST_CANCELLED = "MODEL_REQUEST_CANCELLED"
    MODEL_STREAM_INCOMPLETE = "MODEL_STREAM_INCOMPLETE"
    MODEL_STREAM_PROTOCOL_INVALID = "MODEL_STREAM_PROTOCOL_INVALID"
    MODEL_OUTPUT_TOO_LARGE = "MODEL_OUTPUT_TOO_LARGE"
    MODEL_TOOL_EVENT_FORBIDDEN = "MODEL_TOOL_EVENT_FORBIDDEN"
    MODEL_REASONING_EVENT_FORBIDDEN = "MODEL_REASONING_EVENT_FORBIDDEN"
    RAW_MODEL_EGRESS_REJECTED = "RAW_MODEL_EGRESS_REJECTED"
    MODEL_OUTPUT_UNPARSEABLE = "MODEL_OUTPUT_UNPARSEABLE"
    MODEL_CANDIDATE_SCHEMA_INVALID = "MODEL_CANDIDATE_SCHEMA_INVALID"
    MODEL_PROCESS_FAILED = "MODEL_PROCESS_FAILED"
    MODEL_RECEIPT_INVALID = "MODEL_RECEIPT_INVALID"
    FINAL_EGRESS_PROCESS_FAILED = "FINAL_EGRESS_PROCESS_FAILED"


class StructuredCandidateStatus(StrEnum):
    CANDIDATE = "CANDIDATE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class CancellationHandle(Protocol):
    def is_cancelled(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class StructuredCandidateRequest:
    """Provider-neutral, Host-minted request; it carries no execution authority."""

    request_id: UUID
    projection: PublicationProjection
    goal: TeachingGoal
    prompt_profile: str = PROMPT_PROFILE
    deadline_seconds: float = 50.0
    cancellation: CancellationHandle | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, UUID):
            raise ValueError("request_id must be UUID")
        if not isinstance(self.projection, PublicationProjection):
            raise ValueError("projection must be PublicationProjection")
        if self.goal is not self.projection.goal:
            raise ValueError("goal must match projection")
        if self.prompt_profile != PROMPT_PROFILE:
            raise ValueError("unsupported prompt profile")
        if not 0 < self.deadline_seconds <= 50.0:
            raise ValueError("deadline must be within the reviewed bound")
        if self.cancellation is not None and not callable(getattr(self.cancellation, "is_cancelled", None)):
            raise ValueError("cancellation must be a trusted cancellation handle")


@dataclass(frozen=True, slots=True)
class StructuredCandidateOutcome:
    status: StructuredCandidateStatus
    raw_candidate: str | None = None
    failure_code: ModelFailureCode | None = None
    request_digest: str | None = None
    executor_version: str | None = None
    runtime_version: str | None = None
    provider_id: str | None = None
    model_id: str | None = None
    model_request_count: int = 1
    raw_byte_count: int = 0
    raw_digest: str | None = None
    raw_precheck: str = "NOT_RUN"
    receipt_validated: bool = False

    def __post_init__(self) -> None:
        if self.model_request_count not in (0, 1):
            raise ValueError("model_request_count must be bounded")
        if self.status is StructuredCandidateStatus.CANDIDATE:
            if not isinstance(self.raw_candidate, str) or not self.raw_candidate:
                raise ValueError("CANDIDATE requires raw_candidate")
            if self.failure_code is not None:
                raise ValueError("CANDIDATE cannot carry a failure")
        else:
            if self.raw_candidate is not None:
                raise ValueError("failed outcomes cannot expose candidate text")
            if self.failure_code is None:
                raise ValueError("failed outcomes require a bounded failure")

    @classmethod
    def candidate(cls, raw: str, **metadata: object) -> "StructuredCandidateOutcome":
        encoded = raw.encode("utf-8")
        metadata.setdefault("raw_byte_count", len(encoded))
        metadata.setdefault("raw_digest", "sha256:" + hashlib.sha256(encoded).hexdigest())
        metadata.setdefault("raw_precheck", "SAFE")
        return cls(
            status=StructuredCandidateStatus.CANDIDATE,
            raw_candidate=raw,
            **metadata,
        )

    @classmethod
    def failed(cls, code: ModelFailureCode, **metadata: object) -> "StructuredCandidateOutcome":
        return cls(status=StructuredCandidateStatus.FAILED, failure_code=code, **metadata)

    @classmethod
    def cancelled(cls, **metadata: object) -> "StructuredCandidateOutcome":
        return cls(
            status=StructuredCandidateStatus.CANCELLED,
            failure_code=ModelFailureCode.MODEL_REQUEST_CANCELLED,
            **metadata,
        )


class StructuredCandidateRuntime(Protocol):
    """Async application port. Provider/process/credential choices stay outside."""

    async def generate(
        self,
        request: StructuredCandidateRequest,
    ) -> StructuredCandidateOutcome: ...

    async def aclose(self) -> None: ...
