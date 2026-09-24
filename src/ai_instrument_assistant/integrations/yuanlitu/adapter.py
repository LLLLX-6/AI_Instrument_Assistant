from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from hashlib import sha256
from typing import Protocol
from uuid import UUID, uuid4

from ai_instrument_assistant.application.ports.eda_interface import (
    EDACapability,
    EDACapabilitySet,
    EDAInterface,
    HighlightCommand,
    HighlightResult,
)
from ai_instrument_assistant.domain.eda import (
    CircuitComponent,
    CircuitComponentKind,
    CircuitPin,
    DesignDocument,
    DesignNet,
    DesignObjectKind,
    DesignObjectRef,
    DesignObservation,
)

from .dto import ComponentDto, HealthDto, PageInspectionDto, WireDto, parse_health, parse_inspection, parse_pages
from .errors import YuanlituMappingError, YuanlituProtocolError
from .geometry import derive_connectivity


PROVIDER = "yuanlitu-mcp"


class YuanlituToolClient(Protocol):
    async def call_tool(self, name: str, arguments: object) -> object: ...


class YuanlituMcpEDAAdapter(EDAInterface):
    """Read-only Yuanlitu boundary that emits existing provider-neutral models."""

    def __init__(
        self,
        client: YuanlituToolClient,
        *,
        clock: Callable[[], datetime] | None = None,
        snapshot_factory: Callable[[], UUID] | None = None,
    ) -> None:
        self._client = client
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._snapshot_factory = snapshot_factory or uuid4
        self._capabilities = EDACapabilitySet(frozenset({EDACapability.DESIGN_READ}))

    @property
    def capabilities(self) -> EDACapabilitySet:
        return self._capabilities

    async def observe_design(self) -> DesignObservation:
        health = parse_health(await self._client.call_tool("easyeda_health", {}))
        pages = parse_pages(await self._client.call_tool("schematic_list_pages", {}))
        matching = tuple(page for page in pages if page.provider_ref == health.page_ref)
        if len(matching) != 1:
            raise YuanlituProtocolError("active page is not uniquely present in the page list")
        inspection = parse_inspection(await self._client.call_tool(
            "schematic_inspect_page", {"pageUuid": health.page_ref, "includeWires": True}
        ))
        if inspection.page_ref != health.page_ref:
            raise YuanlituProtocolError("inspected page does not match the active page")
        return self._map_observation(health, matching[0].schematic_name, inspection)

    async def get_active_document(self) -> DesignDocument:
        self.capabilities.require(EDACapability.DOCUMENT_READ)
        raise AssertionError("unreachable")

    async def get_selection(self):
        self.capabilities.require(EDACapability.SELECTION_READ)
        raise AssertionError("unreachable")

    async def highlight(self, command: HighlightCommand) -> HighlightResult:
        del command
        self.capabilities.require(EDACapability.VIEW_HIGHLIGHT)
        raise AssertionError("unreachable")

    def _map_observation(
        self,
        health: HealthDto,
        schematic_name: str | None,
        inspection: PageInspectionDto,
    ) -> DesignObservation:
        snapshot_id = self._snapshot_factory()
        captured_at = self._clock()
        if captured_at.tzinfo is None or captured_at.utcoffset() is None:
            raise YuanlituMappingError("observation clock must be timezone-aware")
        document_ref = DesignObjectRef(
            provider=PROVIDER,
            object_type=DesignObjectKind.DOCUMENT,
            document_id=health.page_ref,
            snapshot_id=snapshot_id,
            native_id=health.page_ref,
            canonical_id=f"{PROVIDER}:page:{health.page_ref}",
            display_name=inspection.page_name,
            provider_kind="schematic_page",
        )
        document = DesignDocument(
            document_ref=document_ref,
            project_id=health.project_ref,
            project_name=health.project_name,
            document_name=schematic_name or inspection.page_name,
            document_type="schematic",
            native_revision=None,
            fingerprint=None,
            is_dirty=None,
            captured_at=captured_at,
        )
        all_pins = tuple(pin for component in inspection.components for pin in component.pins)
        connectivity = derive_connectivity(inspection.wires, all_pins, health.coordinate_tolerance)
        net_refs: dict[str, DesignObjectRef] = {}
        for network_id, wire_refs in sorted(connectivity.network_wires.items()):
            signature = sha256("\0".join(wire_refs).encode("utf-8")).hexdigest()[:24]
            names = {
                wire.native_net for wire in inspection.wires
                if wire.provider_ref in wire_refs and wire.native_net is not None
            }
            display_name = next(iter(names)) if len(names) == 1 else None
            net_refs[network_id] = DesignObjectRef(
                provider=PROVIDER,
                object_type=DesignObjectKind.NET,
                document_id=health.page_ref,
                snapshot_id=snapshot_id,
                native_id=None,
                canonical_id=f"{PROVIDER}:page:{health.page_ref}:observation:{snapshot_id}:net:{signature}",
                display_name=display_name,
                provider_kind="geometry_connectivity",
            )
        classified = tuple((component, _classify(component)) for component in inspection.components)
        reference_networks = {
            connectivity.pin_networks[(component.provider_ref, pin.number)]
            for component, kind in classified if kind is CircuitComponentKind.REFERENCE
            for pin in component.pins
            if connectivity.pin_networks[(component.provider_ref, pin.number)] is not None
        }
        nets = tuple(
            DesignNet(ref=net_refs[network_id], is_reference=network_id in reference_networks)
            for network_id in sorted(net_refs)
        )
        components = tuple(
            CircuitComponent(
                ref=DesignObjectRef(
                    provider=PROVIDER,
                    object_type=DesignObjectKind.COMPONENT,
                    document_id=health.page_ref,
                    snapshot_id=snapshot_id,
                    native_id=component.provider_ref,
                    canonical_id=f"{PROVIDER}:page:{health.page_ref}:component:{component.provider_ref}",
                    display_name=component.designator,
                    provider_kind=kind.value,
                ),
                kind=kind,
                designator=component.designator,
                value_text=component.value_text,
                pins=tuple(
                    CircuitPin(
                        pin_name=pin.name,
                        pin_number=pin.number,
                        net_ref=None if connectivity.pin_networks[(component.provider_ref, pin.number)] is None
                        else net_refs[connectivity.pin_networks[(component.provider_ref, pin.number)]],
                    )
                    for pin in component.pins
                ),
            )
            for component, kind in classified
        )
        return DesignObservation(document=document, components=components, nets=nets)


def _classify(component: ComponentDto) -> CircuitComponentKind:
    facts = {value.strip().casefold() for value in component.model_titles}
    if "resistor" in facts:
        return CircuitComponentKind.RESISTOR
    if "capacitor" in facts:
        return CircuitComponentKind.CAPACITOR
    if facts & {"ground", "analog ground", "protect ground", "protection ground"}:
        return CircuitComponentKind.REFERENCE
    return CircuitComponentKind.OTHER
