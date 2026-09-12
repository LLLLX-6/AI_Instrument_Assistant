from __future__ import annotations

import json
from pathlib import Path
import unittest

from ai_instrument_assistant.protocol import SchemaRegistry, SchemaValidator


ROOT = Path(__file__).resolve().parents[3]
PROTOCOL = ROOT / "protocols" / "harness-publication-bridge" / "v1"


class HarnessPublicationBridgeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = SchemaRegistry.from_directory(PROTOCOL)
        cls.validator = SchemaValidator(cls.registry)

    def test_shared_valid_and_invalid_fixtures(self) -> None:
        for kind, expected in (("valid", True), ("invalid", False)):
            paths = sorted((PROTOCOL / "fixtures" / kind).glob("*.case.json"))
            self.assertTrue(paths)
            for path in paths:
                case = json.loads(path.read_text(encoding="utf-8"))
                result = self.validator.validate(case["schema_ref"], case["instance"])
                self.assertEqual(result.is_valid, expected, path.name)

    def test_bridge_has_exactly_four_closed_schemas(self) -> None:
        schemas = sorted(PROTOCOL.glob("*.schema.json"))
        self.assertEqual(len(schemas), 4)
        for path in schemas:
            schema = json.loads(path.read_text(encoding="utf-8"))
            self.assertFalse(schema["additionalProperties"], path.name)


if __name__ == "__main__":
    unittest.main()
