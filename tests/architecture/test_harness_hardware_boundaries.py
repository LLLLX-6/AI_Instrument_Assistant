from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INTEGRATION_ROOT = ROOT / "src/ai_instrument_assistant/integrations"
HARDWARE_RUNTIME = ROOT / "src/ai_instrument_assistant/application/tool_runtime/hardware.py"


def imports(path: Path) -> frozenset[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return frozenset(found)


class HarnessHardwareArchitectureTests(unittest.TestCase):
    def test_harness_contract_and_projection_do_not_depend_on_hardware_implementation(self) -> None:
        paths = tuple((INTEGRATION_ROOT / "harness_hardware").rglob("*.py")) + tuple(
            (INTEGRATION_ROOT / "deepseek_harness").rglob("*.py")
        )
        self.assertGreaterEqual(len(paths), 4)
        forbidden = (
            "pyvisa", "ai_instrument_assistant.drivers", "ai_instrument_assistant.communication",
            "ai_instrument_assistant.analysis", "ai_instrument_assistant.application.services",
        )
        for path in paths:
            with self.subTest(path=path.name):
                found = imports(path)
                self.assertFalse(any(name.startswith(forbidden) for name in found), found)

    def test_no_dynamic_or_dangerous_operation_surface(self) -> None:
        paths = tuple((INTEGRATION_ROOT / "harness_hardware").rglob("*.py")) + tuple(
            (INTEGRATION_ROOT / "deepseek_harness").rglob("*.py")
        )
        source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
        for marker in ("raw_scpi", "send_command", "visa_resource", "eval(", "exec(", "getattr("):
            self.assertNotIn(marker, source)

    def test_hardware_tool_runtime_is_unchanged_by_phase_7b(self) -> None:
        self.assertEqual(
            "762c53a925dee82810d787437400f9354d2f25381a96106f2c2fd1da544184cb",
            __import__("hashlib").sha256(HARDWARE_RUNTIME.read_bytes()).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
