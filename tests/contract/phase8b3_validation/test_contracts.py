from __future__ import annotations

import json
import unittest
from pathlib import Path

from ai_instrument_assistant.protocol.schema_registry import SchemaRegistry
from ai_instrument_assistant.protocol.schema_validator import (
    SchemaInstanceValidationError,
    SchemaValidator,
)


ROOT = Path(__file__).resolve().parents[3]
CONTRACT_ROOT = ROOT / "validation" / "support" / "phase8b3" / "v1"
FIXTURE_ROOT = CONTRACT_ROOT / "fixtures"


class Phase8B3ValidationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        validation_schemas = sorted(CONTRACT_ROOT.glob("*.schema.json"))
        evidence_schemas = sorted((ROOT / "protocols" / "evidence" / "v1").rglob("*.schema.json"))
        hardware_schema = ROOT / "protocols" / "hardware" / "v1" / "hardware-tool.schema.json"
        cls.validator = SchemaValidator(
            SchemaRegistry.from_files([*validation_schemas, *evidence_schemas, hardware_schema]),
            enforce_formats=True,
        )

    def test_required_private_schemas_exist(self) -> None:
        self.assertTrue((CONTRACT_ROOT / "request.schema.json").is_file())
        self.assertTrue((CONTRACT_ROOT / "receipt.schema.json").is_file())

    def test_shared_valid_fixtures_pass(self) -> None:
        for path in sorted((FIXTURE_ROOT / "valid").glob("*.json")):
            case = json.loads(path.read_text(encoding="utf-8"))
            self.validator.validate_and_freeze(case["schema_ref"], case["instance"])

    def test_shared_invalid_fixtures_fail(self) -> None:
        for path in sorted((FIXTURE_ROOT / "invalid").glob("*.json")):
            case = json.loads(path.read_text(encoding="utf-8"))
            with self.assertRaises(SchemaInstanceValidationError, msg=path.name):
                self.validator.validate_and_freeze(case["schema_ref"], case["instance"])

    def test_fixtures_are_nonempty(self) -> None:
        self.assertGreaterEqual(len(tuple((FIXTURE_ROOT / "valid").glob("*.json"))), 2)
        self.assertGreaterEqual(len(tuple((FIXTURE_ROOT / "invalid").glob("*.json"))), 2)


if __name__ == "__main__":
    unittest.main()
