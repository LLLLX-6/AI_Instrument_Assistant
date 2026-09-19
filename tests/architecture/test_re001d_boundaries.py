from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class RE001DBoundaryTests(unittest.TestCase):
    def test_orchestration_cannot_mint_hardware_authority_or_import_drivers(self) -> None:
        target = ROOT / "validation" / "support" / "re001d_lite" / "coordinator.py"
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
        forbidden = ("drivers", "visa", "scpi", "integrations.harness_hardware", "integrations.deepseek")
        self.assertFalse(any(any(part in name for part in forbidden) for name in imports))
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        self.assertNotIn("TrustedOperationScope", names)
        self.assertNotIn("ProbeSetupConfirmation", names)


if __name__ == "__main__":
    unittest.main()
