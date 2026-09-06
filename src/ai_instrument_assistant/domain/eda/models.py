from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from .errors import DomainInvariantError
from ..values import DutyCycle


MeasurementScalar = str | int | float | bool | None


class DesignObjectKind(StrEnum):
    DOCUMENT = "document"
    NET = "net"
    WIRE = "wire"
    COMPONENT = "component"
    OTHER = "other"


class ProbeTargetKind(StrEnum):
    DESIGN_ONLY = "design_only"
    PHYSICAL = "physical"


@dataclass(frozen=True, slots=True)
class DesignObjectRef:
    provider: str
    object_type: DesignObjectKind
    document_id: str
    snapshot_id: UUID
    native_id: str | None
    canonical_id: str
    display_name: str | None
    provider_kind: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", _non_empty(self.provider, "provider"))
        object.__setattr__(
            self,
            "document_id",
            _non_empty(self.document_id, "document_id"),
        )
        object.__setattr__(
            self,
            "canonical_id",
            _non_empty(self.canonical_id, "canonical_id"),
        )
        if self.display_name is not None:
            object.__setattr__(
                self,
                "display_name",
                _non_empty(self.display_name, "display_name"),
            )
        if self.native_id is not None:
            object.__setattr__(
                self,
                "native_id",
                _non_empty(self.native_id, "native_id"),
            )
        if self.provider_kind is not None:
            object.__setattr__(
                self,
                "provider_kind",
                _non_empty(self.provider_kind, "provider_kind"),
            )
        _require_uuid(self.snapshot_id, "snapshot_id")
        if not isinstance(self.object_type, DesignObjectKind):
            raise DomainInvariantError("object_type must be a DesignObjectKind")


@dataclass(frozen=True, slots=True)
class DesignFingerprint:
    """A value plus the complete finite projection from which it was computed."""

    value: str
    scope_kind: str
    scope_version: str
    included_paths: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in ("value", "scope_kind", "scope_version"):
            object.__setattr__(
                self,
                field_name,
                _non_empty(getattr(self, field_name), field_name),
            )
        paths = tuple(
            _non_empty(path, "included_paths item") for path in self.included_paths
        )
        if not paths:
            raise DomainInvariantError("included_paths must not be empty")
        if len(paths) != len(set(paths)):
            raise DomainInvariantError("included_paths must be unique")
        object.__setattr__(self, "included_paths", paths)


@dataclass(frozen=True, slots=True)
class DesignDocument:
    """A provider observation whose snapshot_id is an AIA observation token.

    The token correlates one captured observation. It is not a provider revision,
    content version, or proof that the design has not changed.
    """

    document_ref: DesignObjectRef
    project_id: str | None
    project_name: str | None
    document_name: str | None
    document_type: str
    native_revision: str | None
    fingerprint: DesignFingerprint | None
    is_dirty: bool | None
    captured_at: datetime

    def __post_init__(self) -> None:
        if self.document_ref.object_type is not DesignObjectKind.DOCUMENT:
            raise DomainInvariantError("document_ref must reference a document")
        for field_name in ("project_id", "project_name", "document_name"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _non_empty(value, field_name))
        for field_name in ("document_type",):
            object.__setattr__(
                self,
                field_name,
                _non_empty(getattr(self, field_name), field_name),
            )
        if self.native_revision is not None:
            object.__setattr__(
                self,
                "native_revision",
                _non_empty(self.native_revision, "native_revision"),
            )

        if self.fingerprint is not None and not isinstance(
            self.fingerprint, DesignFingerprint
        ):
            raise DomainInvariantError(
                "fingerprint must be a complete DesignFingerprint or None"
            )
        if self.is_dirty is not None and not isinstance(self.is_dirty, bool):
            raise DomainInvariantError("is_dirty must be a boolean or None")
        _require_aware_datetime(self.captured_at, "captured_at")

    @property
    def snapshot_id(self) -> UUID:
        return self.document_ref.snapshot_id


@dataclass(frozen=True, slots=True)
class CircuitEndpoint:
    component_reference: str
    pin_name: str
    pin_number: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "component_reference",
            _non_empty(self.component_reference, "component_reference"),
        )
        object.__setattr__(self, "pin_name", _non_empty(self.pin_name, "pin_name"))
        if self.pin_number is not None:
            object.__setattr__(
                self,
                "pin_number",
                _non_empty(self.pin_number, "pin_number"),
            )


@dataclass(frozen=True, slots=True)
class SignalExpectation:
    frequency_hz: float | None = None
    duty_cycle: DutyCycle | None = None

    def __post_init__(self) -> None:
        if self.frequency_hz is None and self.duty_cycle is None:
            raise DomainInvariantError(
                "SignalExpectation must define at least one expected property"
            )
        if self.frequency_hz is not None:
            frequency = _finite_number(self.frequency_hz, "frequency_hz")
            if frequency <= 0:
                raise DomainInvariantError("frequency_hz must be greater than zero")
            object.__setattr__(self, "frequency_hz", frequency)
        if self.duty_cycle is not None and not isinstance(
            self.duty_cycle,
            DutyCycle,
        ):
            raise DomainInvariantError(
                "duty_cycle must be constructed explicitly as DutyCycle"
            )


@dataclass(frozen=True, slots=True)
class CircuitNet:
    """Observed network context.

    An empty endpoints tuple means unresolved connectivity. It never asserts a
    known network topology containing zero endpoints.
    """

    ref: DesignObjectRef
    endpoints: tuple[CircuitEndpoint, ...]
    source: CircuitEndpoint | None = None
    signal_expectation: SignalExpectation | None = None

    def __post_init__(self) -> None:
        if self.ref.object_type is not DesignObjectKind.NET:
            raise DomainInvariantError("CircuitNet ref must reference a net")
        endpoints = tuple(self.endpoints)
        if not all(isinstance(endpoint, CircuitEndpoint) for endpoint in endpoints):
            raise DomainInvariantError(
                "CircuitNet endpoints must contain only CircuitEndpoint values"
            )
        if len(endpoints) != len(set(endpoints)):
            raise DomainInvariantError("CircuitNet endpoints must be unique")
        if self.source is not None and self.source not in endpoints:
            raise DomainInvariantError("CircuitNet source must belong to endpoints")
        object.__setattr__(self, "endpoints", endpoints)

    @property
    def connectivity_unresolved(self) -> bool:
        """True only when no endpoint connectivity could be resolved."""
        return not self.endpoints


@dataclass(frozen=True, slots=True)
class DesignSelection:
    document_ref: DesignObjectRef
    selected_objects: tuple[DesignObjectRef, ...] = ()
    primary_object: DesignObjectRef | None = None

    def __post_init__(self) -> None:
        if self.document_ref.object_type is not DesignObjectKind.DOCUMENT:
            raise DomainInvariantError("selection document_ref must reference a document")

        selected_objects = tuple(self.selected_objects)
        if not all(
            isinstance(selected_object, DesignObjectRef)
            for selected_object in selected_objects
        ):
            raise DomainInvariantError(
                "selected_objects must contain only DesignObjectRef values"
            )
        if len(selected_objects) != len(set(selected_objects)):
            raise DomainInvariantError("selected_objects must be unique")
        for selected_object in selected_objects:
            if selected_object.snapshot_id != self.document_ref.snapshot_id:
                raise DomainInvariantError(
                    "all selected objects must belong to the selection snapshot"
                )
            if selected_object.provider != self.document_ref.provider:
                raise DomainInvariantError(
                    "all selected objects must belong to the selection provider"
                )
            if selected_object.document_id != self.document_ref.document_id:
                raise DomainInvariantError(
                    "all selected objects must belong to the selection document"
                )
        if self.primary_object is not None and self.primary_object not in selected_objects:
            raise DomainInvariantError(
                "primary_object must belong to selected_objects"
            )
        object.__setattr__(self, "selected_objects", selected_objects)

    @property
    def snapshot_id(self) -> UUID:
        return self.document_ref.snapshot_id


@dataclass(frozen=True, slots=True)
class SelectionContext:
    selection: DesignSelection
    nets: tuple[CircuitNet, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.selection, DesignSelection):
            raise DomainInvariantError("selection must be a DesignSelection")
        nets = tuple(self.nets)
        if not all(isinstance(net, CircuitNet) for net in nets):
            raise DomainInvariantError("nets must contain only CircuitNet values")
        net_refs = tuple(net.ref for net in nets)
        if len(net_refs) != len(set(net_refs)):
            raise DomainInvariantError("SelectionContext nets must be unique")
        for net_ref in net_refs:
            document_ref = self.selection.document_ref
            if (
                net_ref.provider != document_ref.provider
                or net_ref.document_id != document_ref.document_id
                or net_ref.snapshot_id != document_ref.snapshot_id
            ):
                raise DomainInvariantError(
                    "SelectionContext nets must belong to the selection observation"
                )
        object.__setattr__(self, "nets", nets)

    @property
    def snapshot_id(self) -> UUID:
        return self.selection.snapshot_id


@dataclass(frozen=True, slots=True)
class ProbeTarget:
    target_id: UUID
    design_object: DesignObjectRef
    kind: ProbeTargetKind
    endpoint: CircuitEndpoint | None = None
    physical_location: str | None = None

    def __post_init__(self) -> None:
        _require_uuid(self.target_id, "target_id")
        if self.design_object.object_type is not DesignObjectKind.NET:
            raise DomainInvariantError("ProbeTarget must reference a net")
        if not isinstance(self.kind, ProbeTargetKind):
            raise DomainInvariantError("kind must be a ProbeTargetKind")
        if self.physical_location is not None:
            object.__setattr__(
                self,
                "physical_location",
                _non_empty(self.physical_location, "physical_location"),
            )
        if self.kind is ProbeTargetKind.PHYSICAL and self.physical_location is None:
            raise DomainInvariantError(
                "a physical ProbeTarget requires physical_location"
            )

    @property
    def snapshot_id(self) -> UUID:
        return self.design_object.snapshot_id


@dataclass(frozen=True, slots=True)
class ProbeConnectionConfirmation:
    confirmation_id: UUID
    probe_target_id: UUID
    snapshot_id: UUID
    confirmed_at: datetime
    confirmed_by: str

    def __post_init__(self) -> None:
        _require_uuid(self.confirmation_id, "confirmation_id")
        _require_uuid(self.probe_target_id, "probe_target_id")
        _require_uuid(self.snapshot_id, "snapshot_id")
        _require_aware_datetime(self.confirmed_at, "confirmed_at")
        object.__setattr__(
            self,
            "confirmed_by",
            _non_empty(self.confirmed_by, "confirmed_by"),
        )


@dataclass(frozen=True, slots=True)
class ArtifactReference:
    artifact_id: UUID
    uri: str
    media_type: str
    size_bytes: int | None = None
    sha256: str | None = None

    def __post_init__(self) -> None:
        _require_uuid(self.artifact_id, "artifact_id")
        object.__setattr__(self, "uri", _non_empty(self.uri, "uri"))
        object.__setattr__(
            self,
            "media_type",
            _non_empty(self.media_type, "media_type"),
        )
        if ":" not in self.uri:
            raise DomainInvariantError("uri must include a scheme")
        if "/" not in self.media_type:
            raise DomainInvariantError("media_type must be a MIME type")
        if self.size_bytes is not None:
            if (
                isinstance(self.size_bytes, bool)
                or not isinstance(self.size_bytes, int)
                or self.size_bytes < 0
            ):
                raise DomainInvariantError("size_bytes must be a non-negative integer")
        if self.sha256 is not None:
            if not isinstance(self.sha256, str):
                raise DomainInvariantError("sha256 must be a hexadecimal string")
            normalized_digest = self.sha256.lower()
            if re.fullmatch(r"[0-9a-f]{64}", normalized_digest) is None:
                raise DomainInvariantError("sha256 must contain 64 hexadecimal characters")
            object.__setattr__(self, "sha256", normalized_digest)


@dataclass(frozen=True, slots=True)
class MeasurementContext:
    context_id: UUID
    document: DesignDocument
    selection: DesignSelection
    probe_target: ProbeTarget
    connection_confirmation: ProbeConnectionConfirmation | None = None
    evidence: tuple[ArtifactReference, ...] = ()
    results: tuple[tuple[str, MeasurementScalar], ...] = ()

    def __post_init__(self) -> None:
        _require_uuid(self.context_id, "context_id")
        snapshot_id = self.document.snapshot_id
        if self.selection.snapshot_id != snapshot_id:
            raise DomainInvariantError(
                "selection and document must belong to the same snapshot"
            )
        if self.probe_target.snapshot_id != snapshot_id:
            raise DomainInvariantError(
                "probe_target and document must belong to the same snapshot"
            )

        document_ref = self.document.document_ref
        selection_ref = self.selection.document_ref
        target_ref = self.probe_target.design_object
        if (
            selection_ref.provider != document_ref.provider
            or target_ref.provider != document_ref.provider
            or selection_ref.document_id != document_ref.document_id
            or target_ref.document_id != document_ref.document_id
        ):
            raise DomainInvariantError(
                "measurement objects must belong to the same provider and document"
            )

        if self.connection_confirmation is not None:
            if self.connection_confirmation.snapshot_id != snapshot_id:
                raise DomainInvariantError(
                    "connection confirmation must belong to the measurement snapshot"
                )
            if (
                self.connection_confirmation.probe_target_id
                != self.probe_target.target_id
            ):
                raise DomainInvariantError(
                    "connection confirmation must reference the measurement probe target"
                )

        evidence = tuple(self.evidence)
        if not all(isinstance(artifact, ArtifactReference) for artifact in evidence):
            raise DomainInvariantError(
                "evidence must contain only ArtifactReference values"
            )
        artifact_ids = tuple(artifact.artifact_id for artifact in evidence)
        if len(artifact_ids) != len(set(artifact_ids)):
            raise DomainInvariantError("evidence artifact identifiers must be unique")
        object.__setattr__(self, "evidence", evidence)

        normalized_results: list[tuple[str, MeasurementScalar]] = []
        for result in self.results:
            if not isinstance(result, (tuple, list)) or len(result) != 2:
                raise DomainInvariantError(
                    "each measurement result must be a name and scalar value pair"
                )
            name = _non_empty(result[0], "measurement result name")
            value = result[1]
            if not isinstance(value, (str, int, float, bool, type(None))):
                raise DomainInvariantError(
                    "measurement result values must be scalar; use ArtifactReference "
                    "for large data"
                )
            if isinstance(value, float) and not math.isfinite(value):
                raise DomainInvariantError("measurement result numbers must be finite")
            if isinstance(value, str) and len(value) > 4096:
                raise DomainInvariantError(
                    "large measurement result text must use ArtifactReference"
                )
            normalized_results.append((name, value))

        result_names = tuple(name for name, _ in normalized_results)
        if len(result_names) != len(set(result_names)):
            raise DomainInvariantError("measurement result names must be unique")
        object.__setattr__(self, "results", tuple(normalized_results))

    @property
    def snapshot_id(self) -> UUID:
        return self.document.snapshot_id


def _non_empty(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainInvariantError(f"{field_name} must be a non-empty string")
    return value.strip()


def _require_uuid(value: Any, field_name: str) -> None:
    if not isinstance(value, UUID):
        raise DomainInvariantError(f"{field_name} must be a UUID")


def _require_aware_datetime(value: datetime, field_name: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise DomainInvariantError(f"{field_name} must be timezone-aware")


def _finite_number(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DomainInvariantError(f"{field_name} must be numeric")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise DomainInvariantError(f"{field_name} must be finite")
    return normalized
