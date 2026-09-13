from __future__ import annotations

import ast
import hashlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INTERACTIVE = ROOT / "src" / "ai_instrument_assistant" / "application" / "interactive"
INTERACTIVE_ADAPTER = ROOT / "src" / "ai_instrument_assistant" / "integrations" / "interactive"
INTERACTIVE_BOOTSTRAP = ROOT / "src" / "ai_instrument_assistant" / "bootstrap" / "interactive.py"
DESIGN_SELECTION_ISSUER = (
    INTERACTIVE_ADAPTER / "design_selection_issuer.py"
)


class Phase85AArchitectureTests(unittest.TestCase):
    def test_interactive_application_has_no_external_or_hardware_dependencies(self) -> None:
        forbidden = (
            "jlceda", "harness", "visa", "scpi", "rigol", "drivers",
            "deepseek", "websocket", "subprocess",
        )
        for path in INTERACTIVE.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.append(node.module or "")
            joined = "\n".join(imports).lower()
            with self.subTest(path=path.name):
                self.assertFalse(any(item in joined for item in forbidden), joined)

    def test_interactive_frontend_protocol_is_additive_to_frozen_contracts(self) -> None:
        expected = {
            "protocols/evidence/v1/teaching-evidence-context.schema.json": "a59885604d01942c0a2270dbfba62771fbfa602038343657637c69ef3f3642d1",
            "protocols/hardware/v1/hardware-tool.schema.json": "eba930ef4b9f85e73d19814fe7df53b846acbf4c31e404092b38145e4b71a5fa",
            "protocols/jlceda/v1/message.schema.json": "64bc6ceef5a606a48918feec8b4a4641e4ebfb60e696a85a3e59080a594f743f",
        }
        for relative, digest in expected.items():
            self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), digest)

    def test_phase85b_adds_only_jlceda_frontend_implementation(self) -> None:
        self.assertTrue((ROOT / "extensions/jlceda/src/interaction").exists())
        self.assertFalse((ROOT / "extensions/deepseek-harness/src/interactive/client").exists())

    def test_interactive_gateway_has_no_driver_model_or_vendor_sdk_dependency(self) -> None:
        forbidden = ("drivers", "visa", "scpi", "rigol", "deepseek", "jlceda", "harness")
        for path in INTERACTIVE_ADAPTER.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.append(node.module or "")
            joined = "\n".join(imports).lower()
            with self.subTest(path=path.name):
                self.assertFalse(any(item in joined for item in forbidden), joined)

    def test_frontend_commands_carry_no_execution_or_trust_object_fields(self) -> None:
        command_file = INTERACTIVE / "commands.py"
        tree = ast.parse(command_file.read_text(encoding="utf-8"), filename=str(command_file))
        names = {node.id.lower() for node in ast.walk(tree) if isinstance(node, ast.Name)}
        attrs = {node.attr.lower() for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        forbidden = {
            "trustedoperationscope", "probesetupconfirmation", "hardwaretoolruntime",
            "scpi", "visa", "driver", "executepreparedmeasurement",
        }
        self.assertTrue(forbidden.isdisjoint(names | attrs))

    def test_phase85b1_production_glue_contains_no_fake_or_execution_dependency(self) -> None:
        source = INTERACTIVE_BOOTSTRAP.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(INTERACTIVE_BOOTSTRAP))
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
        joined = "\n".join(imports).lower()
        forbidden = (
            "tests", "fake", "driver", "visa", "scpi", "rigol", "deepseek",
            "hardware_tool", "agent",
        )
        self.assertFalse(any(value in joined for value in forbidden), joined)
        self.assertIn("LocalWebSocketGateway", source)
        self.assertIn("JLCEDARemoteAdapter", source)
        self.assertIn("ProductionInteractiveApplicationActions", source)
        self.assertIn("ProductionDesignSelectionDecisionIssuer()", source)
        self.assertNotIn("FakeTrustedDecisionIssuer", source)
        self.assertNotIn("ProductionTrustedDecisionIssuer", source)

    def test_production_design_selection_issuer_delegates_to_reviewed_factory(self) -> None:
        source = DESIGN_SELECTION_ISSUER.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(DESIGN_SELECTION_ISSUER))
        calls = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        self.assertIn("issue_trusted_design_selection_decision", calls)
        self.assertIn("resolve_trusted_design_selection", calls)
        forbidden = (
            "harness", "hardware", "driver", "visa", "scpi", "deepseek", "tests"
        )
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
        joined = "\n".join(imports).lower()
        self.assertFalse(any(value in joined for value in forbidden), joined)

    def test_remote_interactive_action_boundary_is_explicitly_async(self) -> None:
        gateway = INTERACTIVE_ADAPTER / "gateway.py"
        tree = ast.parse(gateway.read_text(encoding="utf-8"), filename=str(gateway))
        async_names = {
            node.name for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)
        }
        self.assertTrue({
            "handle_command",
            "request_design_observation",
            "prepare_measurement",
            "highlight_target",
            "request_teaching_publication",
        }.issubset(async_names))

        source = gateway.read_text(encoding="utf-8")
        self.assertNotIn("asyncio.run", source)
        self.assertNotIn("run_until_complete", source)


if __name__ == "__main__":
    unittest.main()
