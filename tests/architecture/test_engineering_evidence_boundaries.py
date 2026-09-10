from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "src" / "ai_instrument_assistant" / "domain" / "engineering_evidence"
SERVICE = ROOT / "src" / "ai_instrument_assistant" / "application" / "services" / "engineering_evidence.py"
SCHEMAS = ROOT / "protocols" / "evidence" / "v1"


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


class EngineeringEvidenceArchitectureTests(unittest.TestCase):
    def test_core_is_provider_and_runtime_neutral(self) -> None:
        forbidden = (
            "deepseek", "harness", "rigol", "pyvisa", "scpi", "jlceda",
            "hardwaretoolruntime", "measurementservice",
        )
        for path in CORE.rglob("*.py"):
            imported = " ".join(sorted(imports(path))).lower()
            with self.subTest(path=path.name):
                self.assertFalse(any(token in imported for token in forbidden), imported)

    def test_comparator_has_no_llm_or_hardware_dependency(self) -> None:
        imported = " ".join(sorted(imports(SERVICE))).lower()
        for forbidden in ("llm", "deepseek", "rigol", "pyvisa", "scpi"):
            self.assertNotIn(forbidden, imported)

    def test_shared_schema_has_no_typescript_runtime_authority(self) -> None:
        for path in SCHEMAS.rglob("*.schema.json"):
            schema = json.loads(path.read_text(encoding="utf-8"))
            text = json.dumps(schema).lower()
            with self.subTest(path=path.name):
                self.assertNotIn("typescript", text)
                self.assertNotIn("deepseek", text)
                self.assertNotIn("jlceda", text)

    def test_phase7_safety_authorities_are_not_reimplemented(self) -> None:
        text = SERVICE.read_text(encoding="utf-8")
        self.assertNotIn("TrustedOperationScope", text)
        self.assertNotIn("ProbeSetupConfirmation", text)
        self.assertNotIn("PhysicalPolicy", text)


if __name__ == "__main__":
    unittest.main()
