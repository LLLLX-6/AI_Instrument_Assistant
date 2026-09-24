from __future__ import annotations

import unittest

from ai_instrument_assistant.integrations.yuanlitu.dto import PinDto, WireDto
from ai_instrument_assistant.integrations.yuanlitu.geometry import derive_connectivity


def wire(identity: str, *coordinates: float) -> WireDto:
    return WireDto(identity, None, tuple(coordinates))


class YuanlituGeometryTests(unittest.TestCase):
    def assert_connected(self, first: WireDto, second: WireDto, *, tolerance: float = 0.01) -> None:
        result = derive_connectivity((first, second), (), tolerance)
        self.assertEqual(result.wire_networks[first.provider_ref], result.wire_networks[second.provider_ref])

    def test_endpoint_t_junction_and_collinear_connections(self) -> None:
        self.assert_connected(wire("a", 0, 0, 10, 0), wire("b", 10, 0, 10, 10))
        self.assert_connected(wire("a", 0, 0, 20, 0), wire("b", 10, 0, 10, 10))
        self.assert_connected(wire("a", 0, 0, 10, 0), wire("b", 10, 0, 20, 0))
        self.assert_connected(wire("a", 0, 0, 20, 0), wire("b", 5, 0, 15, 0))

    def test_interior_crossing_is_not_automatically_connected(self) -> None:
        first, second = wire("a", 0, 5, 10, 5), wire("b", 5, 0, 5, 10)
        result = derive_connectivity((first, second), (), 0.01)
        self.assertNotEqual(result.wire_networks[first.provider_ref], result.wire_networks[second.provider_ref])

    def test_pin_on_endpoint_segment_and_disconnected_pin(self) -> None:
        line = wire("w", 0, 0, 10, 0)
        pins = (
            PinDto("c", "end", "1", 0, 0, False),
            PinDto("c", "middle", "2", 5, 0, False),
            PinDto("c", "free", "3", 5, 5, False),
        )
        result = derive_connectivity((line,), pins, 0.01)
        self.assertEqual(result.pin_networks[("c", "1")], result.pin_networks[("c", "2")])
        self.assertIsNone(result.pin_networks[("c", "3")])

    def test_coordinate_tolerance_is_explicit(self) -> None:
        first, second = wire("a", 0, 0, 10, 0), wire("b", 10.005, 0, 20, 0)
        self.assert_connected(first, second, tolerance=0.01)
        result = derive_connectivity((first, second), (), 0.001)
        self.assertNotEqual(result.wire_networks["a"], result.wire_networks["b"])


if __name__ == "__main__":
    unittest.main()
