from __future__ import annotations

import json
import unittest
from pathlib import Path

from ai_instrument_assistant.application.experiments.rc_low_pass import (
    RCExperimentReadiness,
    RCFilterExperimentSpec,
    RCLowPassExperimentService,
)
from ai_instrument_assistant.application.ports.eda_interface import CapabilityUnsupportedError
from ai_instrument_assistant.domain.eda import CircuitComponentKind
from ai_instrument_assistant.integrations.yuanlitu.adapter import YuanlituMcpEDAAdapter
from ai_instrument_assistant.integrations.yuanlitu.errors import YuanlituProtocolError


FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "yuanlitu"


class FakeToolClient:
    def __init__(self, fixture: dict[str, object]) -> None:
        self.fixture = fixture
        self.calls: list[tuple[str, object]] = []

    async def call_tool(self, name: str, arguments: object) -> object:
        self.calls.append((name, arguments))
        return {
            "easyeda_health": self.fixture["health"],
            "schematic_list_pages": self.fixture["pages"],
            "schematic_inspect_page": self.fixture["inspection"],
        }[name]


def load(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class YuanlituAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_positive_fixture_maps_and_feeds_unchanged_core(self) -> None:
        client = FakeToolClient(load("re001-positive-page.json"))
        adapter = YuanlituMcpEDAAdapter(client)
        observation = await adapter.observe_design()
        self.assertEqual(3, len(observation.components))
        self.assertEqual(3, len(observation.nets))
        self.assertIsNone(observation.document.native_revision)
        self.assertEqual(
            ["easyeda_health", "schematic_list_pages", "schematic_inspect_page"],
            [name for name, _ in client.calls],
        )
        self.assertEqual({CircuitComponentKind.RESISTOR, CircuitComponentKind.CAPACITOR, CircuitComponentKind.REFERENCE}, {item.kind for item in observation.components})
        reference = next(item for item in observation.nets if item.is_reference)
        ground = next(item for item in observation.components if item.kind is CircuitComponentKind.REFERENCE)
        self.assertEqual(reference.ref, ground.pins[0].net_ref)

        result = await RCLowPassExperimentService(YuanlituMcpEDAAdapter(FakeToolClient(load("re001-positive-page.json")))).evaluate(RCFilterExperimentSpec(1000.0))
        self.assertIs(result.readiness, RCExperimentReadiness.DESIGN_READY_FOR_MEASUREMENT)
        self.assertEqual(1600.0, result.resistance_ohm)
        self.assertAlmostEqual(100e-9, result.capacitance_f)
        self.assertAlmostEqual(994.718394, result.calculated_cutoff_hz, places=5)

    async def test_recorded_real_fixture_remains_intentional_negative(self) -> None:
        result = await RCLowPassExperimentService(YuanlituMcpEDAAdapter(FakeToolClient(load("recorded-real-negative-page.json")))).evaluate(RCFilterExperimentSpec(1000.0))
        self.assertIs(result.readiness, RCExperimentReadiness.DESIGN_NOT_RECOGNIZED)

    async def test_malformed_structured_content_fails_closed(self) -> None:
        fixture = load("re001-positive-page.json")
        fixture["inspection"] = {"page": {}, "components": "raw", "wires": []}
        with self.assertRaises(YuanlituProtocolError):
            await YuanlituMcpEDAAdapter(FakeToolClient(fixture)).observe_design()

    async def test_missing_required_component_data_fails_closed(self) -> None:
        fixture = load("re001-positive-page.json")
        del fixture["inspection"]["components"][0]["id"]
        with self.assertRaises(YuanlituProtocolError):
            await YuanlituMcpEDAAdapter(FakeToolClient(fixture)).observe_design()

    async def test_selection_and_write_capabilities_are_not_exposed(self) -> None:
        adapter = YuanlituMcpEDAAdapter(FakeToolClient(load("re001-positive-page.json")))
        with self.assertRaises(CapabilityUnsupportedError):
            await adapter.get_selection()
        with self.assertRaises(CapabilityUnsupportedError):
            await adapter.highlight(None)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
