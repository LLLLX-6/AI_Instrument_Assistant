from __future__ import annotations

import ast
import hashlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "src/ai_instrument_assistant/integrations/harness_hardware"
RUNTIME = ROOT / "src/ai_instrument_assistant/application/tool_runtime/hardware.py"
SMOKE = ROOT / "scripts/check_harness_hardware_ipc.py"


def imports(path: Path) -> frozenset[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return frozenset(found)


class HarnessHardwareBackendArchitectureTests(unittest.TestCase):
    def test_server_protocol_core_avoids_concrete_hardware_and_jlceda(self) -> None:
        core_files = (CORE / "server.py", CORE / "auth.py", CORE / "runtime_port.py")
        forbidden = (
            "pyvisa", "ai_instrument_assistant.drivers", "ai_instrument_assistant.communication",
            "ai_instrument_assistant.analysis", "ai_instrument_assistant.application.services",
            "ai_instrument_assistant.integrations.jlceda", "ai_instrument_assistant.agent",
        )
        for path in core_files:
            self.assertTrue(path.is_file(), path)
            found = imports(path)
            self.assertFalse(any(name.startswith(forbidden) for name in found), found)

    def test_server_has_no_dynamic_dispatch_or_forbidden_command_surface(self) -> None:
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in CORE.glob("*.py")
        )
        for marker in ("getattr(", "eval(", "exec(", "__import__", "hardware.raw_", "visa_resource"):
            self.assertNotIn(marker, source)

    def test_hardware_tool_runtime_remains_unchanged(self) -> None:
        self.assertEqual(
            "762c53a925dee82810d787437400f9354d2f25381a96106f2c2fd1da544184cb",
            hashlib.sha256(RUNTIME.read_bytes()).hexdigest(),
        )

    def test_smoke_client_is_explicitly_fake_and_has_no_sample_array_output(self) -> None:
        source = SMOKE.read_text(encoding="utf-8")
        self.assertIn("HardwareBackend.FAKE", source)
        self.assertNotIn("build_real_hardware_tool_composition", source)
        self.assertNotIn('response["result"]["waveform"]["voltage_values"]', source)
        self.assertNotIn('response["result"]["waveform"]["time_values"]', source)


if __name__ == "__main__":
    unittest.main()
