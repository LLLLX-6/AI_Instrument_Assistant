from __future__ import annotations

import unittest
from pathlib import Path

from ai_instrument_assistant.protocol.schema_registry import SchemaRegistry
from ai_instrument_assistant.protocol.schema_validator import SchemaValidator


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PROTOCOL_ROOT = REPOSITORY_ROOT / "protocols" / "jlceda" / "v1"
REQUIRED_SCHEMAS = (
    PROTOCOL_ROOT / "common" / "security.schema.json",
    PROTOCOL_ROOT / "messages" / "handshake.schema.json",
    PROTOCOL_ROOT / "messages" / "heartbeat.schema.json",
    PROTOCOL_ROOT / "message.schema.json",
)


class PhaseFiveBOneContractTests(unittest.TestCase):
    def test_phase5b1_schema_files_exist(self) -> None:
        for path in REQUIRED_SCHEMAS:
            with self.subTest(schema=path.name):
                self.assertTrue(path.is_file(), f"Phase 5B.1 schema is missing: {path}")

    def test_root_message_schema_is_registered(self) -> None:
        registry = SchemaRegistry.from_directory(PROTOCOL_ROOT)
        result = SchemaValidator(registry).validate(
            "aia://protocol/jlceda/v1/message",
            {},
        )
        self.assertFalse(result.is_valid)


if __name__ == "__main__":
    unittest.main()
