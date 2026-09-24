from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .errors import YuanlituProtocolError


MAX_COMPONENTS = 4096
MAX_PINS_PER_COMPONENT = 256
MAX_WIRES = 8192
MAX_WIRE_COORDINATES = 16384
MAX_NET_LABELS = 4096
MAX_TEXT = 512
_MODEL_KEYS = frozenset({"Sim Model Title", "NGSpice Model Title"})
_VALUE_KEY = "Value"


@dataclass(frozen=True, slots=True)
class HealthDto:
    project_ref: str
    project_name: str | None
    page_ref: str
    page_name: str | None
    coordinate_tolerance: float


@dataclass(frozen=True, slots=True)
class PageDto:
    provider_ref: str
    name: str | None
    schematic_ref: str
    schematic_name: str | None


@dataclass(frozen=True, slots=True)
class PinDto:
    component_ref: str
    name: str
    number: str
    x: float
    y: float
    no_connected: bool


@dataclass(frozen=True, slots=True)
class ComponentDto:
    provider_ref: str
    designator: str
    name: str | None
    model_titles: tuple[str, ...]
    value_text: str | None
    pins: tuple[PinDto, ...]


@dataclass(frozen=True, slots=True)
class WireDto:
    provider_ref: str
    native_net: str | None
    line: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class NetLabelDto:
    provider_ref: str
    net: str
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class PageInspectionDto:
    page_ref: str
    page_name: str | None
    components: tuple[ComponentDto, ...]
    wires: tuple[WireDto, ...]
    net_labels: tuple[NetLabelDto, ...]


def parse_health(raw: object) -> HealthDto:
    root = _mapping(raw, "health")
    context = _mapping(root.get("context"), "health.context")
    project = _mapping(context.get("project"), "health.context.project")
    page = _mapping(context.get("page"), "health.context.page")
    cache = _mapping(root.get("cache"), "health.cache")
    tolerance = _finite_number(cache.get("coordinateTolerance"), "coordinateTolerance")
    if tolerance <= 0 or tolerance > 10:
        raise YuanlituProtocolError("coordinate tolerance is outside the supported range")
    return HealthDto(
        project_ref=_text(project.get("uuid"), "project.uuid"),
        project_name=_optional_text(project.get("friendlyName") or project.get("name"), "project.name"),
        page_ref=_text(page.get("uuid"), "page.uuid"),
        page_name=_optional_text(page.get("name"), "page.name"),
        coordinate_tolerance=tolerance,
    )


def parse_pages(raw: object) -> tuple[PageDto, ...]:
    pages = _sequence(_mapping(raw, "pages result").get("pages"), "pages")
    if len(pages) > 4096:
        raise YuanlituProtocolError("page result exceeds the bounded limit")
    result = []
    for index, item in enumerate(pages):
        page = _mapping(item, f"pages[{index}]")
        result.append(PageDto(
            provider_ref=_text(page.get("uuid"), "page.uuid"),
            name=_optional_text(page.get("name"), "page.name"),
            schematic_ref=_text(page.get("schematicUuid"), "page.schematicUuid"),
            schematic_name=_optional_text(page.get("schematicName"), "page.schematicName"),
        ))
    return tuple(result)


def parse_inspection(raw: object) -> PageInspectionDto:
    root = _mapping(raw, "inspection")
    page = _mapping(root.get("page"), "inspection.page")
    raw_components = _sequence(root.get("components"), "inspection.components")
    raw_wires = _sequence(root.get("wires"), "inspection.wires")
    raw_labels = _sequence(root.get("netLabels", ()), "inspection.netLabels")
    if len(raw_components) > MAX_COMPONENTS or len(raw_wires) > MAX_WIRES or len(raw_labels) > MAX_NET_LABELS:
        raise YuanlituProtocolError("inspection exceeds a bounded collection limit")

    components: list[ComponentDto] = []
    for index, item in enumerate(raw_components):
        component = _mapping(item, f"components[{index}]")
        component_type = _text(component.get("type"), "component.type")
        if component_type != "part":
            continue
        provider_ref = _text(component.get("id"), "component.id")
        designator = _text(component.get("designator"), "component.designator")
        attributes = _sequence(component.get("attributes", ()), "component.attributes")
        model_titles: list[str] = []
        value_text: str | None = None
        for raw_attribute in attributes:
            attribute = _mapping(raw_attribute, "component.attribute")
            key = attribute.get("key")
            if key == _VALUE_KEY:
                value_text = _optional_text(attribute.get("value"), "component.Value")
            elif key in _MODEL_KEYS:
                title = _optional_text(attribute.get("value"), "component.modelTitle")
                if title is not None and title not in model_titles:
                    model_titles.append(title)
        raw_pins = _sequence(component.get("pins"), "component.pins")
        if len(raw_pins) > MAX_PINS_PER_COMPONENT:
            raise YuanlituProtocolError("component pin count exceeds the bounded limit")
        pins = tuple(
            PinDto(
                component_ref=provider_ref,
                name=_text(_mapping(pin, "pin").get("name"), "pin.name"),
                number=_text(_mapping(pin, "pin").get("number"), "pin.number"),
                x=_finite_number(_mapping(pin, "pin").get("x"), "pin.x"),
                y=_finite_number(_mapping(pin, "pin").get("y"), "pin.y"),
                no_connected=_optional_bool(_mapping(pin, "pin").get("noConnected"), False),
            )
            for pin in raw_pins
        )
        components.append(ComponentDto(
            provider_ref=provider_ref,
            designator=designator,
            name=_optional_text(component.get("name"), "component.name"),
            model_titles=tuple(model_titles),
            value_text=value_text,
            pins=pins,
        ))

    wires: list[WireDto] = []
    for index, item in enumerate(raw_wires):
        wire = _mapping(item, f"wires[{index}]")
        line = _sequence(wire.get("line"), "wire.line")
        if len(line) < 4 or len(line) % 2 or len(line) > MAX_WIRE_COORDINATES:
            raise YuanlituProtocolError("wire line must be a bounded coordinate sequence")
        wires.append(WireDto(
            provider_ref=_text(wire.get("id"), "wire.id"),
            native_net=_optional_text(wire.get("net"), "wire.net", empty_is_none=True),
            line=tuple(_finite_number(value, "wire coordinate") for value in line),
        ))

    labels: list[NetLabelDto] = []
    for index, item in enumerate(raw_labels):
        label = _mapping(item, f"netLabels[{index}]")
        labels.append(NetLabelDto(
            provider_ref=_text(label.get("id"), "netLabel.id"),
            net=_text(label.get("net"), "netLabel.net"),
            x=_finite_number(label.get("x"), "netLabel.x"),
            y=_finite_number(label.get("y"), "netLabel.y"),
        ))
    return PageInspectionDto(
        page_ref=_text(page.get("uuid"), "inspection.page.uuid"),
        page_name=_optional_text(page.get("name"), "inspection.page.name"),
        components=tuple(components), wires=tuple(wires), net_labels=tuple(labels),
    )


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise YuanlituProtocolError(f"{name} must be an object")
    return value


def _sequence(value: object, name: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise YuanlituProtocolError(f"{name} must be an array")
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT:
        raise YuanlituProtocolError(f"{name} must be bounded non-empty text")
    return value.strip()


def _optional_text(value: object, name: str, *, empty_is_none: bool = False) -> str | None:
    if value is None or (empty_is_none and value == ""):
        return None
    return _text(value, name)


def _finite_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise YuanlituProtocolError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise YuanlituProtocolError(f"{name} must be finite")
    return result


def _optional_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise YuanlituProtocolError("boolean provider field is malformed")
    return value
