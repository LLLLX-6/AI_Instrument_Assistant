from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class RE001ArchitectureTests(unittest.TestCase):
    def test_experiment_core_has_no_provider_simulation_hardware_or_model_dependency(self) -> None:
        target = ROOT / "src/ai_instrument_assistant/application/experiments/rc_low_pass.py"
        tree = ast.parse(target.read_text(encoding="utf-8"))
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        forbidden = ("integrations.jlceda", "simulide", "visa", "scpi", "deepseek")
        self.assertFalse(any(token in name.lower() for name in imports for token in forbidden))

    def test_measurement_core_has_no_provider_hardware_or_authority_dependency(self) -> None:
        target = ROOT / "src/ai_instrument_assistant/application/experiments/rc_low_pass_measurement.py"
        tree = ast.parse(target.read_text(encoding="utf-8"))
        imports = {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        forbidden = (
            "integrations", "drivers", "visa", "scpi", "simulide", "deepseek",
            "operation_scope", "physical_policy",
        )
        self.assertFalse(any(token in name.lower() for name in imports for token in forbidden))

    def test_existing_hardware_tool_set_is_not_expanded_for_re001b(self) -> None:
        target = ROOT / "src/ai_instrument_assistant/application/tool_contracts/hardware.py"
        text = target.read_text(encoding="utf-8")
        self.assertNotIn("hardware.measure_rc_filter", text)
        self.assertNotIn("hardware.measure_gain", text)
        self.assertNotIn("hardware.find_cutoff", text)

    def test_re001c_python_validation_cannot_execute_hardware_or_mint_authority(self) -> None:
        target = ROOT / "validation/support/re001c_lite/coordinator.py"
        tree = ast.parse(target.read_text(encoding="utf-8"))
        imports = {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        forbidden = (
            "integrations.harness_hardware", "drivers", "visa", "scpi",
            "operation_scope", "physical_policy",
        )
        self.assertFalse(any(token in name.lower() for name in imports for token in forbidden))


if __name__ == "__main__":
    unittest.main()
