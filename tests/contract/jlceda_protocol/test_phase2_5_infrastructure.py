from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ai_instrument_assistant.protocol.fixture_loader import FixtureLoader
from ai_instrument_assistant.protocol.schema_registry import (
    SchemaFileNotFoundError,
    SchemaReferenceError,
    SchemaRegistry,
)
from ai_instrument_assistant.protocol.schema_validator import (
    SchemaNotFoundError,
    SchemaValidator,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PROTOCOL_ROOT = REPOSITORY_ROOT / "protocols" / "jlceda" / "v1"
FIXTURES_ROOT = PROTOCOL_ROOT / "fixtures"


class PhaseTwoPointFiveInfrastructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = SchemaRegistry.from_directory(PROTOCOL_ROOT)
        cls.validator = SchemaValidator(cls.registry)
        cls.fixture_loader = FixtureLoader.from_protocol_root(PROTOCOL_ROOT)

    def test_missing_schema_file_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            missing_path = Path(temporary_directory) / "missing.schema.json"

            with self.assertRaises(SchemaFileNotFoundError):
                SchemaRegistry.from_files([missing_path])

    def test_unknown_schema_reference_is_reported(self) -> None:
        with self.assertRaises(SchemaNotFoundError):
            self.validator.validate("aia://protocol/jlceda/v1/missing", {})

    def test_broken_schema_reference_is_reported_during_registry_build(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            schema_path = Path(temporary_directory) / "broken.schema.json"
            schema_path.write_text(
                json.dumps(
                    {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "$id": "aia://test/broken",
                        "$ref": "aia://test/missing",
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(SchemaReferenceError):
                SchemaRegistry.from_directory(Path(temporary_directory))

    def test_all_valid_shared_fixtures_pass(self) -> None:
        fixtures = self.fixture_loader.load("valid")
        self.assertGreater(len(fixtures), 0)

        for fixture in fixtures:
            with self.subTest(fixture=fixture.path.relative_to(FIXTURES_ROOT)):
                result = self.validator.validate(
                    fixture.schema_ref,
                    fixture.instance,
                )
                self.assertTrue(result.is_valid, result.errors)

    def test_all_invalid_shared_fixtures_are_rejected(self) -> None:
        fixtures = self.fixture_loader.load("invalid")
        self.assertGreater(len(fixtures), 0)

        for fixture in fixtures:
            with self.subTest(fixture=fixture.path.relative_to(FIXTURES_ROOT)):
                result = self.validator.validate(
                    fixture.schema_ref,
                    fixture.instance,
                )
                self.assertFalse(result.is_valid)

    def test_unknown_instance_field_is_rejected(self) -> None:
        fixture = next(
            fixture
            for fixture in self.fixture_loader.load("valid")
            if fixture.path.name == "document.case.json"
            and fixture.path.parent.name == "design-object-ref"
        )
        instance = dict(fixture.instance)
        instance["phase_2_5_unknown_field"] = True

        result = self.validator.validate(fixture.schema_ref, instance)

        self.assertFalse(result.is_valid)

    def test_fixture_loader_uses_only_the_shared_fixture_tree(self) -> None:
        fixtures = self.fixture_loader.load_all()
        self.assertGreater(len(fixtures), 0)
        self.assertTrue(
            all(fixture.path.is_relative_to(FIXTURES_ROOT) for fixture in fixtures)
        )


if __name__ == "__main__":
    unittest.main()
