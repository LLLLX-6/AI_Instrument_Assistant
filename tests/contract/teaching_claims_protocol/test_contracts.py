from __future__ import annotations

import json
from pathlib import Path
import unittest

from ai_instrument_assistant.protocol import SchemaRegistry, SchemaValidator


ROOT = Path(__file__).resolve().parents[3]
PROTOCOL = ROOT / "protocols" / "teaching-claims" / "v1"
SCHEMA_ID = (
    "https://ai-instrument-assistant.local/schemas/teaching-claims/v1/"
    "structured-claim-candidate-set.schema.json"
)


class TeachingClaimsContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = SchemaRegistry.from_directory(PROTOCOL)
        cls.validator = SchemaValidator(cls.registry)

    def test_shared_valid_and_invalid_fixtures(self) -> None:
        for expected, directory in ((True, "valid"), (False, "invalid")):
            paths = sorted((PROTOCOL / "fixtures" / directory).glob("*.case.json"))
            self.assertTrue(paths)
            for path in paths:
                case = json.loads(path.read_text(encoding="utf-8"))
                result = self.validator.validate(case["schema_ref"], case["instance"])
                self.assertEqual(result.is_valid, expected, path.name)

    def test_candidate_schema_is_minimal_closed_and_bounded(self) -> None:
        schema = self.registry.resolve(SCHEMA_ID)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["ordered_permission_refs"]["maxItems"], 12)
        self.assertTrue(schema["properties"]["ordered_permission_refs"]["uniqueItems"])
        self.assertEqual(
            set(schema["properties"]),
            {
                "schema_id",
                "projection_id",
                "context_fingerprint",
                "envelope_id",
                "goal",
                "ordered_permission_refs",
            },
        )


if __name__ == "__main__":
    unittest.main()
