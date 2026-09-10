from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CAPTURE = ROOT / "src/ai_instrument_assistant/application/services/eda_design_evidence.py"
DISAMBIGUATION = ROOT / "src/ai_instrument_assistant/application/services/design_selection_disambiguation.py"
WORKFLOW = ROOT / "src/ai_instrument_assistant/application/services/engineering_evidence_workflow.py"
DOMAIN = ROOT / "src/ai_instrument_assistant/domain"
RUNNER = ROOT / "scripts/validate_phase8b2_real_jlceda.py"
JLCEDA_INTEGRATION = ROOT / "src/ai_instrument_assistant/integrations/jlceda"
HARNESS_INTEGRATION = ROOT / "src/ai_instrument_assistant/integrations/deepseek_harness"
TOOL_RUNTIME = ROOT / "src/ai_instrument_assistant/application/tool_runtime"


def imported_text(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return " ".join(names).lower()


class Phase8B2ArchitectureTests(unittest.TestCase):
    def test_trusted_disambiguation_has_no_provider_model_hardware_or_policy_dependency(self) -> None:
        imports = imported_text(DISAMBIGUATION)
        for forbidden in (
            "jlceda",
            "protocol",
            "deepseek",
            "harness",
            "agent",
            "hardware",
            "instrument",
            "visa",
            "scpi",
            "physical_policy",
            "operation_scope",
        ):
            self.assertNotIn(forbidden, imports)

    def test_no_provider_selection_role_abstraction_was_added(self) -> None:
        class_names: set[str] = set()
        for path in DOMAIN.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            class_names.update(
                node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
            )
        self.assertNotIn("SelectionRole", class_names)

    def test_provider_agent_and_tool_boundaries_cannot_issue_trusted_design_decisions(self) -> None:
        imports = " ".join(
            imported_text(path)
            for root in (JLCEDA_INTEGRATION, HARNESS_INTEGRATION, TOOL_RUNTIME)
            for path in root.rglob("*.py")
        )
        self.assertNotIn("design_selection_disambiguation", imports)

    def test_provider_neutral_projection_has_no_jlceda_sdk_or_protocol_dependency(self) -> None:
        imports = imported_text(CAPTURE)
        for forbidden in ("jlceda", "pro-api", "protocol", "typescript", "websocket"):
            self.assertNotIn(forbidden, imports)

    def test_existing_evidence_workflow_remains_provider_neutral(self) -> None:
        imports = imported_text(WORKFLOW)
        for forbidden in ("jlceda", "pro-api", "websocket", "deepseek", "agentloop"):
            self.assertNotIn(forbidden, imports)

    def test_domain_has_no_jlceda_sdk_or_provider_import(self) -> None:
        imports = " ".join(
            imported_text(path) for path in DOMAIN.rglob("*.py")
        )
        for forbidden in ("jlceda", "pro-api", "typescript", "websocket"):
            self.assertNotIn(forbidden, imports)

    def test_projection_cannot_create_confirmation_scope_tool_or_measurement(self) -> None:
        text = CAPTURE.read_text(encoding="utf-8")
        for forbidden in (
            "ProbeSetupConfirmation",
            "TrustedOperationScope",
            "HardwareToolRuntime",
            "MeasurementService",
            "AgentLoop",
            "measure_pwm",
            "measure_frequency",
        ):
            self.assertNotIn(forbidden, text)

    def test_validation_runner_has_no_hardware_or_model_execution_dependency(self) -> None:
        imports = imported_text(RUNNER)
        for forbidden in (
            "hardware_tool_runtime",
            "measurementservice",
            "drivers",
            "pyvisa",
            "deepseek",
            "agentloop",
            "dsh-agent",
        ):
            self.assertNotIn(forbidden, imports)
        text = RUNNER.read_text(encoding="utf-8")
        for forbidden in ("DEEPSEEK_API_KEY", "start_hardware", "client.invoke"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
