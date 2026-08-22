from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator

from .schema_registry import SchemaReferenceError, SchemaRegistry


class SchemaNotFoundError(LookupError):
    """The requested schema identifier or fragment is absent from the registry."""


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    instance_path: tuple[Any, ...]
    schema_path: tuple[Any, ...]
    keyword: str | None
    message: str


@dataclass(frozen=True, slots=True)
class ValidationResult:
    is_valid: bool
    errors: tuple[ValidationIssue, ...]


class SchemaValidator:
    """Validates arbitrary JSON values exclusively through registered JSON Schemas."""

    def __init__(self, registry: SchemaRegistry) -> None:
        self._registry = registry
        self._validators: dict[str, Draft202012Validator] = {}

    def validate(self, schema_ref: str, instance: Any) -> ValidationResult:
        validator = self._validator_for(schema_ref)
        errors = tuple(
            ValidationIssue(
                instance_path=tuple(error.absolute_path),
                schema_path=tuple(error.absolute_schema_path),
                keyword=error.validator,
                message=error.message,
            )
            for error in sorted(
                validator.iter_errors(instance),
                key=lambda item: tuple(str(part) for part in item.absolute_path),
            )
        )
        return ValidationResult(is_valid=not errors, errors=errors)

    def _validator_for(self, schema_ref: str) -> Draft202012Validator:
        cached = self._validators.get(schema_ref)
        if cached is not None:
            return cached

        try:
            self._registry.resolve(schema_ref)
        except SchemaReferenceError as error:
            raise SchemaNotFoundError(f"Unknown schema reference: {schema_ref}") from error

        validator = Draft202012Validator(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$ref": schema_ref,
            },
            registry=self._registry.referencing_registry,
        )
        self._validators[schema_ref] = validator
        return validator
