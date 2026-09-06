from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def imported_modules(path: Path) -> frozenset[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return frozenset(modules)


class Phase6FHILBoundaryTests(unittest.TestCase):
    def test_composition_root_is_the_only_new_concrete_wiring_boundary(self) -> None:
        composition = ROOT / "src/ai_instrument_assistant/bootstrap/hardware.py"
        self.assertTrue(composition.exists())
        found = imported_modules(composition)
        self.assertIn("ai_instrument_assistant.drivers.rigol", found)
        self.assertIn("ai_instrument_assistant.integrations.visa", found)

    def test_hil_script_uses_measurement_service_not_driver_or_visa(self) -> None:
        script = ROOT / "scripts/check_measurement_service.py"
        self.assertTrue(script.exists())
        source = script.read_text(encoding="utf-8")
        found = imported_modules(script)
        self.assertIn("ai_instrument_assistant.domain.measurement", found)
        self.assertFalse(any(name.startswith((
            "ai_instrument_assistant.drivers",
            "ai_instrument_assistant.integrations.visa",
            "pyvisa",
        )) for name in found), found)
        for marker in (
            "send_scpi", "query_scpi", "*IDN?", ":MEASure", ":WAVeform",
            ".measure_frequency(", ".measure_vpp(", ".capture_waveform(",
        ):
            self.assertNotIn(marker, source)
        self.assertIn(".service.measure(", source)

    def test_hil_script_never_prints_full_waveform_arrays(self) -> None:
        source = (
            ROOT / "scripts/check_measurement_service.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("time_values", source)
        self.assertNotIn("voltage_values", source)


if __name__ == "__main__":
    unittest.main()
