from __future__ import annotations

import unittest
from pathlib import Path

from ai_instrument_assistant.protocol.fixture_loader import FixtureLoader
from ai_instrument_assistant.protocol.schema_registry import SchemaRegistry
from ai_instrument_assistant.protocol.schema_validator import SchemaValidator
from ai_instrument_assistant.integrations.interactive import (
    InteractiveProtocolBinding,
    InteractiveProtocolError,
)


ROOT = Path(__file__).resolve().parents[3]
PROTOCOL = ROOT / "protocols" / "interactive" / "v1"
FIXTURES = PROTOCOL / "fixtures"


class InteractiveProtocolContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = SchemaRegistry.from_directory(PROTOCOL)
        self.validator = SchemaValidator(self.registry, enforce_formats=True)

    def test_shared_valid_fixtures_pass(self) -> None:
        fixtures = FixtureLoader(FIXTURES).load("valid")
        self.assertGreaterEqual(len(fixtures), 5)
        for fixture in fixtures:
            with self.subTest(fixture=fixture.path.name):
                self.assertTrue(
                    self.validator.validate(fixture.schema_ref, fixture.instance).is_valid
                )

    def test_shared_invalid_fixtures_fail(self) -> None:
        fixtures = FixtureLoader(FIXTURES).load("invalid")
        self.assertGreaterEqual(len(fixtures), 5)
        for fixture in fixtures:
            with self.subTest(fixture=fixture.path.name):
                self.assertFalse(
                    self.validator.validate(fixture.schema_ref, fixture.instance).is_valid
                )

    def test_schema_ids_are_unique_and_refs_resolve(self) -> None:
        ids = tuple(item.schema_id for item in self.registry.schemas)
        self.assertEqual(len(ids), len(set(ids)))
        for schema in self.registry.schemas:
            self.assertIsNotNone(self.registry.resolve(schema.schema_id))

    def test_gateway_binding_rejects_message_above_wire_limit(self) -> None:
        binding = InteractiveProtocolBinding.from_repository(ROOT)
        with self.assertRaises(InteractiveProtocolError):
            binding.validate_message({"oversized": "x" * 70_000})


if __name__ == "__main__":
    unittest.main()
