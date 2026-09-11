from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ai_instrument_assistant.protocol.schema_registry import SchemaRegistry
from ai_instrument_assistant.protocol.schema_validator import SchemaValidator


REQUEST_SCHEMA_ID = "https://aia.local/validation/support/phase8b3/v1/request.schema.json"
RECEIPT_SCHEMA_ID = "https://aia.local/validation/support/phase8b3/v1/receipt.schema.json"


class Phase8B3ValidationContract:
    """Schema-only binding for the private, validation-only stdio contract."""

    def __init__(self, validator: SchemaValidator) -> None:
        self._validator = validator

    @classmethod
    def from_repository(cls, repository_root: Path) -> Phase8B3ValidationContract:
        paths = [
            repository_root / "protocols" / "hardware" / "v1" / "hardware-tool.schema.json",
            *sorted((repository_root / "protocols" / "evidence" / "v1").rglob("*.schema.json")),
            *sorted((repository_root / "validation" / "support" / "phase8b3" / "v1").glob("*.schema.json")),
        ]
        return cls(SchemaValidator(SchemaRegistry.from_files(paths), enforce_formats=True))

    def validate_request(self, value: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._validator.validate_and_freeze(REQUEST_SCHEMA_ID, value).instance

    def validate_receipt(self, value: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._validator.validate_and_freeze(RECEIPT_SCHEMA_ID, value).instance
