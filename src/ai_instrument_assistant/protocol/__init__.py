"""JSON Schema-driven protocol infrastructure."""

from .fixture_loader import FixtureCase, FixtureFormatError, FixtureLoader
from .schema_registry import (
    SchemaDefinitionError,
    SchemaFileNotFoundError,
    SchemaReferenceError,
    SchemaRegistry,
)
from .schema_validator import (
    SchemaNotFoundError,
    SchemaInstanceValidationError,
    SchemaValidator,
    ValidatedInstance,
    ValidationIssue,
    ValidationResult,
)

__all__ = [
    "FixtureCase",
    "FixtureFormatError",
    "FixtureLoader",
    "SchemaDefinitionError",
    "SchemaFileNotFoundError",
    "SchemaNotFoundError",
    "SchemaInstanceValidationError",
    "SchemaReferenceError",
    "SchemaRegistry",
    "SchemaValidator",
    "ValidatedInstance",
    "ValidationIssue",
    "ValidationResult",
]
