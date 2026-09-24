from __future__ import annotations

import ast
from dataclasses import fields
import hashlib
import unittest
from pathlib import Path

from ai_instrument_assistant.application.reasoning import (
    AllowedClaimEnvelope,
    ClaimPermission,
    ClaimSubjectRef,
    DeterministicFallback,
)


ROOT = Path(__file__).resolve().parents[2]
REASONING_ROOT = ROOT / "src/ai_instrument_assistant/application/reasoning"


class Phase8CReasoningArchitectureTests(unittest.TestCase):
    def test_reasoning_core_has_only_approved_provider_neutral_dependencies(self) -> None:
        forbidden = (
            "deepseek",
            "harness",
            "jlceda",
            "hardware",
            "visa",
            "scpi",
            "rigol",
            "instrument",
            "driver",
            "transport",
            "physical_policy",
            "tool_runtime",
        )
        for path in REASONING_ROOT.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.append(node.module or "")
            joined = "\n".join(imports).lower()
            with self.subTest(path=path.name):
                self.assertFalse(any(value in joined for value in forbidden), joined)

    def test_reasoning_core_cannot_create_tool_scope_confirmation_or_execution(self) -> None:
        forbidden_symbols = {
            "TrustedOperationScope",
            "ProbeSetupConfirmation",
            "HardwareToolRuntime",
            "evaluateHardwareToolPolicy",
            "AgentLoop",
        }
        for path in REASONING_ROOT.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
            attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
            with self.subTest(path=path.name):
                self.assertTrue(forbidden_symbols.isdisjoint(names | attrs))

    def test_frozen_protocols_remain_byte_stable(self) -> None:
        expected = {
            "protocols/evidence/v1/teaching-evidence-context.schema.json": "a59885604d01942c0a2270dbfba62771fbfa602038343657637c69ef3f3642d1",
            "protocols/hardware/v1/hardware-tool.schema.json": "eba930ef4b9f85e73d19814fe7df53b846acbf4c31e404092b38145e4b71a5fa",
            "protocols/jlceda/v1/message.schema.json": "5e1d025e97addf93ba3a16ab7faf91c9e423e348502e3f7f46b248b664111a5d",
        }
        for relative, digest in expected.items():
            with self.subTest(path=relative):
                self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), digest)

    def test_reasoning_values_carry_no_execution_authority_or_secret_payload_fields(self) -> None:
        forbidden = {
            "tool",
            "operation_scope",
            "trusted_operation_scope",
            "probe_setup_confirmation",
            "ipc_authorization",
            "hardware_action",
            "secret",
            "raw_provider_payload",
            "authentication",
            "authorization",
        }
        for model in (
            ClaimSubjectRef,
            ClaimPermission,
            AllowedClaimEnvelope,
            DeterministicFallback,
        ):
            names = {field.name.lower() for field in fields(model)}
            with self.subTest(model=model.__name__):
                self.assertTrue(forbidden.isdisjoint(names))


if __name__ == "__main__":
    unittest.main()
