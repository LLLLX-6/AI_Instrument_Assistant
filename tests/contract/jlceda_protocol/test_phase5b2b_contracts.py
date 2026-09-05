from __future__ import annotations

import unittest
from pathlib import Path

from ai_instrument_assistant.protocol.schema_registry import SchemaRegistry
from ai_instrument_assistant.protocol.schema_validator import SchemaValidator


ROOT = Path(__file__).resolve().parents[3]
PROTOCOL_ROOT = ROOT / "protocols" / "jlceda" / "v1"


class PhaseFiveBTwoBContractTests(unittest.TestCase):
    def test_document_operation_schema_exists_and_compiles(self) -> None:
        path = PROTOCOL_ROOT / "messages" / "eda-document.schema.json"
        self.assertTrue(path.is_file(), f"Missing operation schema: {path}")
        validator = SchemaValidator(SchemaRegistry.from_directory(PROTOCOL_ROOT))
        self.assertFalse(
            validator.validate("aia://protocol/jlceda/v1/message", {}).is_valid
        )


if __name__ == "__main__":
    unittest.main()
