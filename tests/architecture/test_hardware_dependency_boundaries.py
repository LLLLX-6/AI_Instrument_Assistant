from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def imports(path: Path) -> frozenset[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return frozenset(result)


class HardwareArchitectureTests(unittest.TestCase):
    def test_instrument_domain_is_provider_and_transport_neutral(self) -> None:
        for path in (ROOT / "src/ai_instrument_assistant/domain/instrument").glob("*.py"):
            found = imports(path)
            self.assertFalse(any(name.startswith((
                "pyvisa", "ai_instrument_assistant.communication",
                "ai_instrument_assistant.drivers", "ai_instrument_assistant.integrations",
            )) for name in found), found)

    def test_oscilloscope_port_has_no_rigol_visa_or_scpi_dependency(self) -> None:
        found = imports(ROOT / "src/ai_instrument_assistant/application/ports/oscilloscope.py")
        self.assertFalse(any(name.startswith(("pyvisa", "ai_instrument_assistant.communication",
            "ai_instrument_assistant.drivers", "ai_instrument_assistant.integrations")) for name in found), found)

    def test_visa_transport_has_no_rigol_analysis_or_tool_dependency(self) -> None:
        paths = tuple((ROOT / "src/ai_instrument_assistant/communication").glob("*.py"))
        self.assertGreater(len(paths), 0)
        for path in paths:
            found = imports(path)
            self.assertFalse(any(name.startswith(("ai_instrument_assistant.drivers",
                "ai_instrument_assistant.analysis", "ai_instrument_assistant.tools")) for name in found), found)

    def test_rigol_driver_depends_on_ports_and_communication_not_concrete_visa(self) -> None:
        found = imports(ROOT / "src/ai_instrument_assistant/drivers/rigol/ds1102ze.py")
        self.assertFalse(any(name.startswith((
            "pyvisa", "ai_instrument_assistant.integrations",
            "ai_instrument_assistant.analysis", "ai_instrument_assistant.tools",
            "ai_instrument_assistant.integrations.jlceda",
        )) for name in found), found)

    def test_pyvisa_import_is_confined_to_the_visa_integration(self) -> None:
        allowed = ROOT / "src/ai_instrument_assistant/integrations/visa/pyvisa_transport.py"
        for path in (ROOT / "src/ai_instrument_assistant").rglob("*.py"):
            if path == allowed:
                continue
            self.assertNotIn("pyvisa", imports(path), path)

    def test_hardware_tool_analysis_and_arbitrary_scpi_are_absent_in_phase6c(self) -> None:
        self.assertFalse((ROOT / "src/ai_instrument_assistant/tools/hardware.py").exists())
        port = (ROOT / "src/ai_instrument_assistant/application/ports/oscilloscope.py").read_text(encoding="utf-8")
        self.assertNotIn("send_scpi", port)
        self.assertIn("capture_waveform", port)
        self.assertNotIn("measure_pwm", port)
        self.assertNotIn("analyze", port)

    def test_generic_binary_parser_has_no_driver_dependency(self) -> None:
        found = imports(ROOT / "src/ai_instrument_assistant/communication/ieee4882.py")
        self.assertFalse(any(name.startswith(
            "ai_instrument_assistant.drivers"
        ) for name in found), found)

    def test_waveform_domain_has_no_driver_or_communication_dependency(self) -> None:
        found = imports(ROOT / "src/ai_instrument_assistant/domain/instrument/waveform.py")
        self.assertFalse(any(name.startswith((
            "ai_instrument_assistant.drivers",
            "ai_instrument_assistant.communication",
        )) for name in found), found)

    def test_analysis_is_provider_neutral_and_driver_does_not_depend_on_it(self) -> None:
        analysis_paths = tuple((ROOT / "src/ai_instrument_assistant/analysis").glob("*.py"))
        self.assertGreater(len(analysis_paths), 0)
        forbidden = (
            "pyvisa",
            "ai_instrument_assistant.communication",
            "ai_instrument_assistant.drivers",
            "ai_instrument_assistant.integrations",
            "ai_instrument_assistant.domain.eda",
            "ai_instrument_assistant.agent",
            "ai_instrument_assistant.tools",
        )
        for path in analysis_paths:
            found = imports(path)
            self.assertFalse(any(name.startswith(forbidden) for name in found), (path, found))
        for path in (ROOT / "src/ai_instrument_assistant/drivers").rglob("*.py"):
            self.assertFalse(any(name.startswith(
                "ai_instrument_assistant.analysis"
            ) for name in imports(path)), path)

    def test_analysis_hil_script_uses_semantic_driver_and_analysis_engine(self) -> None:
        script = ROOT / "scripts/check_ds1102ze_analysis.py"
        self.assertTrue(script.exists())
        source = script.read_text(encoding="utf-8")
        self.assertIn("analyze_waveform", source)
        self.assertIn("capture_waveform", source)
        self.assertIn("measure_frequency", source)
        self.assertIn("measure_vpp", source)
        for raw_command_marker in ("*IDN?", ":WAVeform", ":MEASure", "send_scpi"):
            self.assertNotIn(raw_command_marker, source)

    def test_manual_hil_script_uses_semantic_driver_not_raw_scpi(self) -> None:
        script = ROOT / "scripts/check_ds1102ze_basic.py"
        self.assertTrue(script.exists())
        source = script.read_text(encoding="utf-8")
        for raw_command_marker in (
            "*IDN?", ":CHANnel", ":TIMebase", ":MEASure", ":WAVeform"
        ):
            self.assertNotIn(raw_command_marker, source)
        found = imports(script)
        self.assertFalse(any(name.startswith(
            "ai_instrument_assistant.communication"
        ) for name in found), found)

    def test_waveform_hil_script_uses_semantic_driver_not_raw_scpi(self) -> None:
        script = ROOT / "scripts/check_ds1102ze_waveform.py"
        self.assertTrue(script.exists())
        source = script.read_text(encoding="utf-8")
        for raw_command_marker in ("*IDN?", ":WAVeform", "send_scpi"):
            self.assertNotIn(raw_command_marker, source)
        self.assertIn("capture_waveform", source)
        self.assertNotIn("frequency", source.lower())
        self.assertNotIn("duty", source.lower())
        found = imports(script)
        self.assertFalse(any(name.startswith(
            "ai_instrument_assistant.communication"
        ) for name in found), found)


if __name__ == "__main__":
    unittest.main()
