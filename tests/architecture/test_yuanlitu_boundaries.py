from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INTEGRATION = ROOT / "src" / "ai_instrument_assistant" / "integrations" / "yuanlitu"
CORE = ROOT / "src" / "ai_instrument_assistant" / "application" / "experiments" / "rc_low_pass.py"


class YuanlituArchitectureTests(unittest.TestCase):
    def test_re001_core_has_no_yuanlitu_or_mcp_dependency(self) -> None:
        text = CORE.read_text(encoding="utf-8").lower()
        self.assertNotIn("yuanlitu", text)
        self.assertNotIn("mcp", text)

    def test_adapter_has_static_read_only_tool_allowlist(self) -> None:
        text = (INTEGRATION / "client.py").read_text(encoding="utf-8")
        tree = ast.parse(text)
        values = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        self.assertTrue({"easyeda_health", "schematic_list_pages", "schematic_inspect_page"} <= values)
        self.assertNotIn("schematic_apply_operations", values)

    def test_adapter_has_no_simulation_hardware_driver_or_agent_dependency(self) -> None:
        for path in INTEGRATION.glob("*.py"):
            text = path.read_text(encoding="utf-8").lower()
            for forbidden in ("simulide", "pyvisa", "scpi", "deepseek", "agentloop"):
                self.assertNotIn(forbidden, text, path.name)


if __name__ == "__main__":
    unittest.main()
