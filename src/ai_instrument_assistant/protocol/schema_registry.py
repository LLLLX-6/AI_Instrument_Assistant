from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource
from referencing.exceptions import Unresolvable


class SchemaRegistryError(RuntimeError):
    """Base error raised while constructing or resolving a schema registry."""


class SchemaFileNotFoundError(SchemaRegistryError):
    """A requested schema file or schema directory does not exist."""


class SchemaDefinitionError(SchemaRegistryError):
    """A schema document is malformed, unsupported, or has a duplicate identifier."""


class SchemaReferenceError(SchemaRegistryError):
    """A schema contains a reference that cannot be resolved locally."""


@dataclass(frozen=True, slots=True)
class RegisteredSchema:
    path: Path
    schema_id: str
    document: Mapping[str, Any]


class SchemaRegistry:
    """Discovers JSON Schemas and builds a closed, locally resolvable registry."""

    def __init__(
        self,
        schemas: tuple[RegisteredSchema, ...],
        registry: Registry,
    ) -> None:
        self._schemas = schemas
        self._registry = registry

    @property
    def schemas(self) -> tuple[RegisteredSchema, ...]:
        return self._schemas

    @property
    def referencing_registry(self) -> Registry:
        return self._registry

    @classmethod
    def from_directory(cls, protocol_root: Path) -> SchemaRegistry:
        root = protocol_root.resolve()
        if not root.is_dir():
            raise SchemaFileNotFoundError(f"Schema directory does not exist: {root}")

        schema_paths = sorted(root.rglob("*.schema.json"))
        if not schema_paths:
            raise SchemaFileNotFoundError(f"No JSON Schema files found under: {root}")
        return cls.from_files(schema_paths)

    @classmethod
    def from_files(cls, schema_paths: Iterable[Path]) -> SchemaRegistry:
        schemas: list[RegisteredSchema] = []
        resources: list[tuple[str, Resource]] = []
        seen_ids: dict[str, Path] = {}

        for supplied_path in schema_paths:
            path = supplied_path.resolve()
            if not path.is_file():
                raise SchemaFileNotFoundError(f"Schema file does not exist: {path}")

            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise SchemaDefinitionError(
                    f"Cannot read JSON Schema document {path}: {error}"
                ) from error

            if not isinstance(document, dict):
                raise SchemaDefinitionError(f"Schema root must be an object: {path}")

            schema_id = document.get("$id")
            if not isinstance(schema_id, str) or not schema_id:
                raise SchemaDefinitionError(f"Schema has no non-empty $id: {path}")
            if schema_id in seen_ids:
                raise SchemaDefinitionError(
                    f"Duplicate schema $id {schema_id!r}: {seen_ids[schema_id]} and {path}"
                )

            try:
                Draft202012Validator.check_schema(document)
            except SchemaError as error:
                raise SchemaDefinitionError(
                    f"Invalid Draft 2020-12 schema {path}: {error.message}"
                ) from error
            try:
                resource = Resource.from_contents(document)
            except Exception as error:
                raise SchemaDefinitionError(
                    f"Cannot register JSON Schema document {path}: {error}"
                ) from error

            seen_ids[schema_id] = path
            schemas.append(RegisteredSchema(path, schema_id, document))
            resources.append((schema_id, resource))

        if not schemas:
            raise SchemaFileNotFoundError("No JSON Schema files were supplied")

        registry = Registry().with_resources(resources)
        instance = cls(tuple(schemas), registry)
        instance._verify_all_references()
        return instance

    def resolve(self, schema_ref: str) -> Any:
        try:
            return self._registry.resolver().lookup(schema_ref).contents
        except Unresolvable as error:
            raise SchemaReferenceError(
                f"Schema reference cannot be resolved: {schema_ref}"
            ) from error

    def _verify_all_references(self) -> None:
        for schema in self._schemas:
            resolver = self._registry.resolver(base_uri=schema.schema_id)
            for reference in _nested_references(schema.document):
                try:
                    resolver.lookup(reference)
                except Unresolvable as error:
                    raise SchemaReferenceError(
                        f"Broken $ref {reference!r} in {schema.path}"
                    ) from error


def _nested_references(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "$ref" and isinstance(item, str):
                yield item
            else:
                yield from _nested_references(item)
    elif isinstance(value, list):
        for item in value:
            yield from _nested_references(item)
