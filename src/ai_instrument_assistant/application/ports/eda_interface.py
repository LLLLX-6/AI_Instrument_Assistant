from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from ai_instrument_assistant.domain.eda.models import (
    DesignDocument,
    DesignFingerprint,
    DesignObjectKind,
    DesignObjectRef,
    SelectionContext,
)


class EDACapability(StrEnum):
    DOCUMENT_READ = "document.read"
    SELECTION_READ = "selection.read"
    VIEW_HIGHLIGHT = "view.highlight"


class HighlightStyle(StrEnum):
    ANALYSIS = "analysis"
    INFORMATION = "information"
    WARNING = "warning"
    ERROR = "error"


class HighlightStatus(StrEnum):
    APPLIED = "applied"
    NOOP = "noop"


class EDAInterfaceError(RuntimeError):
    """Base error exposed by a provider-neutral EDA port."""


class CapabilityUnsupportedError(EDAInterfaceError):
    """The active adapter does not support a requested semantic capability."""


class NoActiveDocumentError(EDAInterfaceError):
    """The EDA environment has no active design document."""


class StaleDesignSnapshotError(EDAInterfaceError):
    """An operation references a design snapshot that is no longer current."""


class DesignObjectNotFoundError(EDAInterfaceError):
    """A referenced design object cannot be found in the requested snapshot."""


class OperationNotAllowedError(EDAInterfaceError):
    """Policy or current EDA state does not allow the requested operation."""


class EDANotConnectedError(EDAInterfaceError):
    """No authenticated EDA integration session is currently available."""


class EDARequestTimeoutError(EDAInterfaceError):
    """A remote EDA operation exceeded its bounded response deadline."""


class EDAConnectionLostError(EDAInterfaceError):
    """The active EDA integration disconnected while an operation was pending."""


class EDAProtocolError(EDAInterfaceError):
    """The remote peer violated the validated/correlated protocol contract."""


@dataclass(frozen=True, slots=True)
class HighlightCommand:
    document_ref: DesignObjectRef
    expected_snapshot_id: UUID
    expected_fingerprint: DesignFingerprint
    targets: tuple[DesignObjectRef, ...]
    style: HighlightStyle
    ttl: timedelta | None
    replace_existing: bool
    idempotency_key: str

    def __post_init__(self) -> None:
        if self.document_ref.object_type is not DesignObjectKind.DOCUMENT:
            raise ValueError("document_ref must reference a document")
        if self.expected_snapshot_id != self.document_ref.snapshot_id:
            raise ValueError("expected snapshot must match document_ref")
        if not isinstance(self.expected_fingerprint, DesignFingerprint):
            raise ValueError(
                "expected_fingerprint must provide a complete strong stale guard"
            )
        for field_name in ("idempotency_key",):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
            object.__setattr__(self, field_name, value.strip())

        targets = tuple(self.targets)
        if not targets:
            raise ValueError("highlight targets must not be empty")
        if not all(isinstance(target, DesignObjectRef) for target in targets):
            raise ValueError("targets must contain only DesignObjectRef values")
        for target in targets:
            if (
                target.provider != self.document_ref.provider
                or target.document_id != self.document_ref.document_id
                or target.snapshot_id != self.expected_snapshot_id
            ):
                raise ValueError(
                    "highlight targets must belong to the guarded document snapshot"
                )
        object.__setattr__(self, "targets", targets)

        if not isinstance(self.style, HighlightStyle):
            raise ValueError("style must be a HighlightStyle")
        if self.ttl is not None:
            if not isinstance(self.ttl, timedelta) or self.ttl.total_seconds() <= 0:
                raise ValueError("ttl must be a positive timedelta")
        if not isinstance(self.replace_existing, bool):
            raise ValueError("replace_existing must be a boolean")


@dataclass(frozen=True, slots=True)
class HighlightResult:
    status: HighlightStatus
    applied_targets: tuple[DesignObjectRef, ...] = ()
    warnings: tuple[str, ...] = ()
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, HighlightStatus):
            raise ValueError("status must be a HighlightStatus")
        targets = tuple(self.applied_targets)
        if not all(isinstance(target, DesignObjectRef) for target in targets):
            raise ValueError("applied_targets must contain DesignObjectRef values")
        if self.status is HighlightStatus.APPLIED and not targets:
            raise ValueError("an applied result must contain applied targets")
        if self.status is HighlightStatus.NOOP and targets:
            raise ValueError("a noop result cannot contain applied targets")
        object.__setattr__(self, "applied_targets", targets)

        warnings = tuple(self.warnings)
        if not all(isinstance(warning, str) and warning.strip() for warning in warnings):
            raise ValueError("warnings must contain non-empty strings")
        object.__setattr__(self, "warnings", warnings)
        if self.expires_at is not None and (
            not isinstance(self.expires_at, datetime)
            or self.expires_at.tzinfo is None
            or self.expires_at.utcoffset() is None
        ):
            raise ValueError("expires_at must be timezone-aware")

    @property
    def applied(self) -> bool:
        return self.status is HighlightStatus.APPLIED

    @property
    def noop(self) -> bool:
        return self.status is HighlightStatus.NOOP


@dataclass(frozen=True, slots=True)
class EDACapabilitySet:
    supported: frozenset[EDACapability]

    def __post_init__(self) -> None:
        normalized = frozenset(self.supported)
        if not all(isinstance(item, EDACapability) for item in normalized):
            raise TypeError("supported must contain only EDACapability values")
        object.__setattr__(self, "supported", normalized)

    def supports(self, capability: EDACapability) -> bool:
        return capability in self.supported

    def require(self, capability: EDACapability) -> None:
        if not self.supports(capability):
            raise CapabilityUnsupportedError(
                f"EDA capability is unsupported: {capability.value}"
            )


class EDAInterface(ABC):
    """Provider-neutral outbound port for the Phase 3 EDA use cases."""

    @property
    @abstractmethod
    def capabilities(self) -> EDACapabilitySet:
        """Return semantic capabilities exposed by the current adapter."""

    @abstractmethod
    async def get_active_document(self) -> DesignDocument:
        """Return the current active design document."""

    @abstractmethod
    async def get_selection(self) -> SelectionContext:
        """Return the selection associated with the active design snapshot."""

    @abstractmethod
    async def highlight(self, command: HighlightCommand) -> HighlightResult:
        """Apply a guarded semantic highlight command to the EDA view."""
