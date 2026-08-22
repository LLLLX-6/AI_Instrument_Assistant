from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any, Iterator

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PROTOCOL_ROOT = REPOSITORY_ROOT / "protocols" / "jlceda" / "v1"
FIXTURES_ROOT = PROTOCOL_ROOT / "fixtures"
REQUIRED_PHASE_TWO_SCHEMA_PATHS = (
    PROTOCOL_ROOT / "common" / "identifiers.schema.json",
    PROTOCOL_ROOT / "common" / "envelope.schema.json",
    PROTOCOL_ROOT / "models" / "design-object-ref.schema.json",
    PROTOCOL_ROOT / "models" / "design-document.schema.json",
)


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def fixture_cases(expectation: str) -> Iterator[tuple[Path, dict[str, Any]]]:
    for path in sorted((FIXTURES_ROOT / expectation).rglob("*.case.json")):
        yield path, load_json(path)


def load_registry() -> tuple[Registry, list[dict[str, Any]]]:
    schemas = [load_json(path) for path in schema_paths()]
    resources = [
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas
    ]
    return Registry().with_resources(resources), schemas


def schema_paths() -> tuple[Path, ...]:
    return tuple(sorted(PROTOCOL_ROOT.rglob("*.schema.json")))


def validator_for(schema_ref: str, registry: Registry) -> Draft202012Validator:
    return Draft202012Validator(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$ref": schema_ref,
        },
        registry=registry,
    )


def nested_refs(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "$ref" and isinstance(item, str):
                yield item
            else:
                yield from nested_refs(item)
    elif isinstance(value, list):
        for item in value:
            yield from nested_refs(item)


class PhaseTwoContractTests(unittest.TestCase):
    def test_required_schema_files_exist(self) -> None:
        for path in REQUIRED_PHASE_TWO_SCHEMA_PATHS:
            with self.subTest(schema=path.name):
                self.assertTrue(path.is_file(), f"Phase 2 schema is missing: {path}")

    def test_valid_fixtures_are_accepted(self) -> None:
        registry, _ = load_registry()
        cases = list(fixture_cases("valid"))
        self.assertGreater(len(cases), 0, "No valid Phase 2 fixtures were found")

        for path, case in cases:
            with self.subTest(fixture=path.relative_to(FIXTURES_ROOT)):
                errors = list(
                    validator_for(case["schema_ref"], registry).iter_errors(
                        case["instance"]
                    )
                )
                self.assertEqual([], errors, case["description"])

    def test_invalid_fixtures_are_rejected(self) -> None:
        registry, _ = load_registry()
        cases = list(fixture_cases("invalid"))
        self.assertGreater(len(cases), 0, "No invalid Phase 2 fixtures were found")

        for path, case in cases:
            with self.subTest(fixture=path.relative_to(FIXTURES_ROOT)):
                errors = list(
                    validator_for(case["schema_ref"], registry).iter_errors(
                        case["instance"]
                    )
                )
                self.assertGreater(len(errors), 0, case["description"])

    def test_schema_ids_are_unique_and_schemas_are_valid(self) -> None:
        _, schemas = load_registry()
        schema_ids = [schema["$id"] for schema in schemas]
        self.assertEqual(len(schema_ids), len(set(schema_ids)))

        for schema in schemas:
            with self.subTest(schema=schema["$id"]):
                Draft202012Validator.check_schema(schema)

    def test_all_schema_references_resolve(self) -> None:
        registry, schemas = load_registry()

        for schema in schemas:
            resolver = registry.resolver(base_uri=schema["$id"])
            for reference in nested_refs(schema):
                with self.subTest(schema=schema["$id"], reference=reference):
                    resolver.lookup(reference)


if __name__ == "__main__":
    unittest.main()
