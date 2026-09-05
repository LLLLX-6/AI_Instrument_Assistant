from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from ai_instrument_assistant.domain.eda.errors import DomainInvariantError
from ai_instrument_assistant.domain.eda.models import (
    CircuitEndpoint,
    CircuitNet,
    DesignDocument,
    DesignFingerprint,
    DesignObjectKind,
    DesignObjectRef,
    DesignSelection,
    DutyCycle,
    SelectionContext,
    SignalExpectation,
)
from ai_instrument_assistant.protocol.schema_validator import ValidatedInstance

from .errors import UnvalidatedWireDataError, WireToDomainMappingError


DESIGN_DOCUMENT_SCHEMA_ID = "aia://protocol/jlceda/v1/models/design-document"
SELECTION_CONTEXT_SCHEMA_ID = "aia://protocol/jlceda/v1/models/selection-context"


class JLCEDADomainMapper:
    """Maps schema-validated JLCEDA wire values into provider-neutral Domain."""

    def map_design_document(self, payload: ValidatedInstance) -> DesignDocument:
        wire = self._validated_mapping(payload, DESIGN_DOCUMENT_SCHEMA_ID)
        try:
            fingerprint_wire = wire["fingerprint"]
            fingerprint = None
            if fingerprint_wire is not None:
                fingerprint_mapping = _mapping(fingerprint_wire, "fingerprint")
                fingerprint = DesignFingerprint(
                    value=_string(fingerprint_mapping["value"], "fingerprint.value"),
                    scope_kind=_string(
                        fingerprint_mapping["scope_kind"], "fingerprint.scope_kind"
                    ),
                    scope_version=_string(
                        fingerprint_mapping["scope_version"],
                        "fingerprint.scope_version",
                    ),
                    included_paths=tuple(
                        _string(path, "fingerprint.included_paths item")
                        for path in _sequence(
                            fingerprint_mapping["included_paths"],
                            "fingerprint.included_paths",
                        )
                    ),
                )
            return DesignDocument(
                document_ref=self._map_object_ref(wire["document_ref"]),
                project_id=_optional_string(wire["project_id"], "project_id"),
                project_name=_optional_string(wire["project_name"], "project_name"),
                document_name=_optional_string(wire["document_name"], "document_name"),
                document_type=_string(wire["document_type"], "document_type"),
                native_revision=_optional_string(
                    wire["native_revision"],
                    "native_revision",
                ),
                fingerprint=fingerprint,
                is_dirty=_optional_boolean(wire["is_dirty"], "is_dirty"),
                captured_at=_timestamp(wire["captured_at"], "captured_at"),
            )
        except (KeyError, TypeError, ValueError, DomainInvariantError) as error:
            raise WireToDomainMappingError(
                f"Cannot map JLCEDA DesignDocument: {error}"
            ) from error

    def map_selection_context(self, payload: ValidatedInstance) -> SelectionContext:
        wire = self._validated_mapping(payload, SELECTION_CONTEXT_SCHEMA_ID)
        try:
            selection = self._map_selection(wire["selection"])
            nets = tuple(
                self._map_circuit_net(net)
                for net in _sequence(wire["nets"], "nets")
            )
            return SelectionContext(selection=selection, nets=nets)
        except (KeyError, TypeError, ValueError, DomainInvariantError) as error:
            raise WireToDomainMappingError(
                f"Cannot map JLCEDA SelectionContext: {error}"
            ) from error

    @staticmethod
    def _validated_mapping(
        payload: ValidatedInstance,
        expected_schema_id: str,
    ) -> Mapping[str, Any]:
        if not isinstance(payload, ValidatedInstance):
            raise UnvalidatedWireDataError(
                "JLCEDA mapper accepts only SchemaValidator validated instances"
            )
        if payload.schema_ref != expected_schema_id:
            raise WireToDomainMappingError(
                f"Expected {expected_schema_id}, received {payload.schema_ref}"
            )
        return _mapping(payload.instance, "validated instance")

    def _map_object_ref(self, value: Any) -> DesignObjectRef:
        wire = _mapping(value, "DesignObjectRef")
        return DesignObjectRef(
            provider=_string(wire["provider"], "provider"),
            object_type=DesignObjectKind(_string(wire["object_type"], "object_type")),
            document_id=_string(wire["document_id"], "document_id"),
            snapshot_id=UUID(_string(wire["snapshot_id"], "snapshot_id")),
            native_id=_optional_string(wire["native_id"], "native_id"),
            canonical_id=_string(wire["canonical_id"], "canonical_id"),
            display_name=_optional_string(wire["display_name"], "display_name"),
            provider_kind=_optional_string(wire.get("provider_kind"), "provider_kind"),
        )

    def _map_endpoint(self, value: Any) -> CircuitEndpoint:
        wire = _mapping(value, "CircuitEndpoint")
        return CircuitEndpoint(
            component_reference=_string(
                wire["component_reference"],
                "component_reference",
            ),
            pin_name=_string(wire["pin_name"], "pin_name"),
            pin_number=_optional_string(wire["pin_number"], "pin_number"),
        )

    def _map_signal_expectation(self, value: Any) -> SignalExpectation:
        wire = _mapping(value, "SignalExpectation")
        frequency = wire.get("frequency_hz")
        duty_ratio = wire.get("duty_cycle_ratio")
        return SignalExpectation(
            frequency_hz=None if frequency is None else _number(frequency, "frequency_hz"),
            duty_cycle=None
            if duty_ratio is None
            else DutyCycle.from_ratio(_number(duty_ratio, "duty_cycle_ratio")),
        )

    def _map_circuit_net(self, value: Any) -> CircuitNet:
        wire = _mapping(value, "CircuitNet")
        source = wire["source"]
        expectation = wire["signal_expectation"]
        return CircuitNet(
            ref=self._map_object_ref(wire["ref"]),
            endpoints=tuple(
                self._map_endpoint(endpoint)
                for endpoint in _sequence(wire["endpoints"], "endpoints")
            ),
            source=None if source is None else self._map_endpoint(source),
            signal_expectation=None
            if expectation is None
            else self._map_signal_expectation(expectation),
        )

    def _map_selection(self, value: Any) -> DesignSelection:
        wire = _mapping(value, "DesignSelection")
        primary = wire["primary_object"]
        return DesignSelection(
            document_ref=self._map_object_ref(wire["document_ref"]),
            selected_objects=tuple(
                self._map_object_ref(selected)
                for selected in _sequence(
                    wire["selected_objects"],
                    "selected_objects",
                )
            ),
            primary_object=None if primary is None else self._map_object_ref(primary),
        )


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be an object")
    return value


def _sequence(value: Any, field_name: str) -> Sequence[Any]:
    if not isinstance(value, (tuple, list)):
        raise TypeError(f"{field_name} must be an array")
    return value


def _string(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _optional_string(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _string(value, field_name)


def _number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric")
    return float(value)


def _boolean(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a boolean")
    return value


def _optional_boolean(value: Any, field_name: str) -> bool | None:
    if value is None:
        return None
    return _boolean(value, field_name)


def _timestamp(value: Any, field_name: str) -> datetime:
    timestamp = _string(value, field_name)
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
