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


class Phase6GArchitectureTests(unittest.TestCase):
    def test_core_runtime_has_no_concrete_hardware_or_agent_dependency(self) -> None:
        path = ROOT / "src/ai_instrument_assistant/application/tool_runtime/hardware.py"
        self.assertTrue(path.exists())
        found = imports(path)
        forbidden = (
            "pyvisa", "ai_instrument_assistant.drivers",
            "ai_instrument_assistant.integrations", "ai_instrument_assistant.communication",
            "ai_instrument_assistant.analysis", "ai_instrument_assistant.domain.eda",
            "ai_instrument_assistant.agent", "ai_instrument_assistant.mcp",
        )
        self.assertFalse(any(name.startswith(forbidden) for name in found), found)
        source = path.read_text(encoding="utf-8")
        for marker in ("getattr(", "eval(", "exec(", "__import__", "send_scpi", "query_scpi"):
            self.assertNotIn(marker, source)

    def test_fake_adapter_does_not_serialize_tool_dtos(self) -> None:
        path = ROOT / "src/ai_instrument_assistant/adapters/instruments/simulated.py"
        self.assertTrue(path.exists())
        source = path.read_text(encoding="utf-8")
        self.assertNotIn("serialize_measurement_result", source)
        self.assertNotIn("hardware.measure_", source)

    def test_real_hil_script_invokes_only_tool_runtime(self) -> None:
        path = ROOT / "scripts/check_hardware_tool_runtime.py"
        self.assertTrue(path.exists())
        source = path.read_text(encoding="utf-8")
        found = imports(path)
        self.assertFalse(any(name.startswith((
            "ai_instrument_assistant.application.services",
            "ai_instrument_assistant.drivers",
            "ai_instrument_assistant.integrations.visa",
            "pyvisa",
        )) for name in found), found)
        self.assertIn(".runtime.execute(", source)
        for marker in ("time_values", "voltage_values", "send_scpi", "query_scpi"):
            self.assertNotIn(marker, source)


if __name__ == "__main__":
    unittest.main()
