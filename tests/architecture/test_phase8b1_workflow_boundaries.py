from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / "src" / "ai_instrument_assistant" / "application" / "services" / "engineering_evidence_workflow.py"


class Phase8B1WorkflowArchitectureTests(unittest.TestCase):
    def test_workflow_depends_only_on_provider_neutral_evidence_services_and_models(self) -> None:
        tree = ast.parse(WORKFLOW.read_text(encoding="utf-8"), filename=str(WORKFLOW))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        text = " ".join(sorted(imports)).lower()
        for forbidden in (
            "deepseek", "harness", "agentloop", "rigol", "pyvisa", "scpi",
            "jlceda", "hardwaretoolruntime", "measurementservice",
        ):
            self.assertNotIn(forbidden, text)

    def test_workflow_has_no_execution_or_safety_authority_creation_surface(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        for forbidden in (
            "TrustedOperationScope", "ProbeSetupConfirmation", "ToolRuntime",
            "execute_tool", "measure_frequency", "measure_pwm",
        ):
            self.assertNotIn(forbidden, text)

    def test_orchestration_order_is_explicit_and_cross_reference_precedes_comparison(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        execute_body = text[text.index("    def execute(") :]
        order = (
            "validate_design_and_targets",
            "establish_evidence_cross_reference",
            "locate_measurement_evidence",
            ".compare(",
            ".assemble(",
            "project_teaching_diagnosis",
        )
        positions = tuple(execute_body.index(marker) for marker in order)
        self.assertEqual(positions, tuple(sorted(positions)))


if __name__ == "__main__":
    unittest.main()
