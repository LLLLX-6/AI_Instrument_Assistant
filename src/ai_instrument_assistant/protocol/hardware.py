from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from ai_instrument_assistant.application.tool_contracts.errors import (
    ContractIssue,
    ToolContractValidationError,
)


_DEFAULT_SCHEMA = (
    Path(__file__).resolve().parents[3]
    / "protocols"
    / "hardware"
    / "v1"
    / "hardware-tool.schema.json"
)


class HardwareToolContractValidator:
    """Validate hardware wire values without reproducing schema fields in Python."""

    def __init__(self, schema_path: Path = _DEFAULT_SCHEMA) -> None:
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError("hardware tool schema is unavailable") from error
        Draft202012Validator.check_schema(schema)
        definitions = schema.get("$defs", {})
        request_schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$defs": definitions,
            "oneOf": [
                {"$ref": "#/$defs/statusRequest"},
                {"$ref": "#/$defs/measurementRequest"},
            ],
        }
        response_schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$defs": definitions,
            "oneOf": [
                {"$ref": "#/$defs/runtimeStatusSuccess"},
                {"$ref": "#/$defs/runtimeMeasurementSuccess"},
                {"$ref": "#/$defs/runtimeError"},
            ],
        }
        checker = FormatChecker()
        self._request_validator = Draft202012Validator(
            request_schema, format_checker=checker
        )
        self._response_validator = Draft202012Validator(
            response_schema, format_checker=checker
        )

    def validate_request(self, payload: Any) -> None:
        self._validate(self._request_validator, payload)

    def validate_runtime_response(self, payload: Any) -> None:
        self._validate(self._response_validator, payload)

    @staticmethod
    def _validate(validator: Draft202012Validator, payload: Any) -> None:
        errors = sorted(
            validator.iter_errors(payload),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
        if not errors:
            return
        issues = tuple(
            ContractIssue(
                path="/" + "/".join(str(part) for part in error.absolute_path),
                rule=str(error.validator or "schema"),
            )
            for error in errors[:8]
        )
        raise ToolContractValidationError(issues)
