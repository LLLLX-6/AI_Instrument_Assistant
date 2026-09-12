from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ...protocol.schema_registry import SchemaRegistry
from ...protocol.schema_validator import SchemaInstanceValidationError, SchemaValidator, ValidatedInstance


INTERACTIVE_PROTOCOL = "aia-interactive/v1"
INTERACTIVE_MESSAGE_SCHEMA_ID = "https://aia.local/protocols/interactive/v1/message.schema.json"
MAX_MESSAGE_BYTES = 65_536


class InteractiveProtocolError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class InteractiveProtocolBinding:
    validator: SchemaValidator

    @classmethod
    def from_repository(cls, repository_root: Path) -> InteractiveProtocolBinding:
        protocol = repository_root / "protocols" / "interactive" / "v1"
        return cls(SchemaValidator(SchemaRegistry.from_directory(protocol), enforce_formats=True))

    def validate_message(self, value: Mapping[str, Any]) -> ValidatedInstance:
        try:
            encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise InteractiveProtocolError("interactive message is not JSON serializable") from error
        if len(encoded) > MAX_MESSAGE_BYTES:
            raise InteractiveProtocolError("interactive message exceeds the bounded size")
        try:
            return self.validator.validate_and_freeze(INTERACTIVE_MESSAGE_SCHEMA_ID, value)
        except SchemaInstanceValidationError as error:
            raise InteractiveProtocolError("interactive message failed schema validation") from error
