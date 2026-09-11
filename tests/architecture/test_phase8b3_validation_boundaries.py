from __future__ import annotations

import hashlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class Phase8B3ValidationArchitectureTests(unittest.TestCase):
    def test_python_coordinator_cannot_bypass_hardware_governance(self):
        source = (ROOT / "validation/support/phase8b3/coordinator.py").read_text(encoding="utf-8")
        imports = "\n".join(line for line in source.splitlines() if line.startswith(("from ", "import ")))
        self.assertNotRegex(imports, r"HardwareToolRuntime|MeasurementService|bootstrap\.hardware_tool|harness_hardware\.composition|drivers?|pyvisa")
        self.assertNotRegex(source, r"evaluateHardwareToolPolicy|OperationScopeGate|authorizeDispatch|SENT_UNCONFIRMED.*retry")
        self.assertNotRegex(source, r"AgentLoop|DEEPSEEK_API_KEY|DeepSeek")

    def test_node_executor_reuses_production_plugin_governance(self):
        source = (ROOT / "extensions/deepseek-harness/validation/phase8b3-executor.ts").read_text(encoding="utf-8")
        self.assertIn("applyWithDependencies", source)
        self.assertNotIn("evaluateHardwareToolPolicy", source)
        self.assertNotIn("new OperationScopeGate", source)
        self.assertNotRegex(source, r"AgentLoop|dsh-agent|DEEPSEEK_API_KEY")

    def test_private_contract_is_clearly_validation_only(self):
        paths = tuple((ROOT / "validation/support/phase8b3").rglob("*"))
        self.assertTrue(paths)
        self.assertTrue(all("validation" in path.parts for path in paths))
        request = (ROOT / "validation/support/phase8b3/v1/request.schema.json").read_text(encoding="utf-8")
        for shortcut in ("scopeApproved", "physicalPolicyApproved", "skipPolicy", "budgetAlreadyAuthorized"):
            self.assertNotIn(shortcut, request)

    def test_frozen_product_contracts_have_not_changed_in_phase8b3_diff(self):
        # Hash the current reviewed baselines; Phase 8B.3 introduces only a private contract.
        expected = {
            "protocols/evidence/v1/teaching-evidence-context.schema.json": "a59885604d01942c0a2270dbfba62771fbfa602038343657637c69ef3f3642d1",
            "protocols/hardware/v1/hardware-tool.schema.json": "eba930ef4b9f85e73d19814fe7df53b846acbf4c31e404092b38145e4b71a5fa",
            "protocols/jlceda/v1/message.schema.json": "64bc6ceef5a606a48918feec8b4a4641e4ebfb60e696a85a3e59080a594f743f",
        }
        for relative, digest in expected.items():
            with self.subTest(path=relative):
                self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main()
