from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .schema_registry import SchemaRegistry
from .schema_validator import SchemaInstanceValidationError, SchemaValidator


BASE = "https://ai-instrument-assistant.local/schemas/harness-publication-bridge/v1/"
MODEL_REQUEST_SCHEMA = BASE + "model-invocation-request.schema.json"
MODEL_RECEIPT_SCHEMA = BASE + "model-invocation-receipt.schema.json"
EGRESS_REQUEST_SCHEMA = BASE + "final-egress-request.schema.json"
EGRESS_RECEIPT_SCHEMA = BASE + "final-egress-receipt.schema.json"


class PrivateBridgeError(ValueError):
    """Bounded private-transport error; never includes untrusted data."""


@dataclass(frozen=True, slots=True)
class ValidatedModelReceipt:
    request_id: str
    request_digest: str
    status: str
    executor_version: str
    runtime_version: str
    provider_id: str
    model_id: str
    model_request_count: int
    raw_byte_count: int
    raw_digest: str | None
    raw_precheck: str
    finish_category: str
    duration_bucket: str
    failure_code: str | None
    raw_candidate: str | None


class HarnessPublicationBridge:
    def __init__(self, protocol_root: Path) -> None:
        self._validator = SchemaValidator(
            SchemaRegistry.from_directory(protocol_root), enforce_formats=True
        )

    def build_model_request(self, request_id: str, projection: Mapping[str, Any]) -> dict[str, Any]:
        basis = {
            "schema_id": "aia-harness-publication-model-request/v1",
            "request_id": request_id,
            "prompt_profile": "AIA_STRUCTURED_CANDIDATE_V1",
            "projection": _plain(projection),
        }
        request = {**basis, "request_digest": _digest(basis)}
        return dict(self._validate(MODEL_REQUEST_SCHEMA, request))

    def parse_model_receipt(
        self,
        value: object,
        *,
        expected_request_id: str,
        expected_request_digest: str,
    ) -> ValidatedModelReceipt:
        item = self._validate(MODEL_RECEIPT_SCHEMA, value)
        if item["request_id"] != expected_request_id or item["request_digest"] != expected_request_digest:
            raise PrivateBridgeError("MODEL_RECEIPT_CORRELATION_INVALID")
        if item["executor_version"] != "aia-phase8c2b-executor/1" or item["runtime_version"] != "0.1.3-alpha.1":
            raise PrivateBridgeError("MODEL_RECEIPT_VERSION_INVALID")
        if item["provider_id"] != "deepseek-official" or item["model_id"] != "deepseek-v4-flash":
            raise PrivateBridgeError("MODEL_RECEIPT_ROUTE_INVALID")
        raw = item.get("raw_candidate")
        if raw is not None:
            encoded = raw.encode("utf-8")
            if len(encoded) != item["raw_byte_count"] or _digest_bytes(encoded) != item["raw_digest"]:
                raise PrivateBridgeError("MODEL_RECEIPT_CONTENT_INVALID")
        return ValidatedModelReceipt(**{name: item.get(name) for name in ValidatedModelReceipt.__dataclass_fields__})

    def build_egress_request(self, request_id: str, correlation_id: str, text: str) -> dict[str, Any]:
        value = {
            "schema_id": "aia-harness-publication-egress-request/v1",
            "request_id": request_id,
            "correlation_id": correlation_id,
            "text": text,
        }
        return dict(self._validate(EGRESS_REQUEST_SCHEMA, value))

    def parse_egress_receipt(self, value: object, *, expected_request_id: str) -> Mapping[str, Any]:
        item = self._validate(EGRESS_RECEIPT_SCHEMA, value)
        if item["request_id"] != expected_request_id:
            raise PrivateBridgeError("FINAL_EGRESS_RECEIPT_CORRELATION_INVALID")
        return item

    def _validate(self, schema: str, value: object) -> Mapping[str, Any]:
        try:
            result = self._validator.validate_and_freeze(schema, value).instance
        except SchemaInstanceValidationError as error:
            raise PrivateBridgeError("PRIVATE_BRIDGE_SCHEMA_INVALID") from error
        if not isinstance(result, Mapping):
            raise PrivateBridgeError("PRIVATE_BRIDGE_OBJECT_REQUIRED")
        return result


def parse_one_json_line(data: bytes, maximum_bytes: int) -> object:
    if len(data) > maximum_bytes or not data or b"\x00" in data:
        raise PrivateBridgeError("PRIVATE_BRIDGE_OUTPUT_BOUND_INVALID")
    try:
        text = data.decode("utf-8")
    except UnicodeError as error:
        raise PrivateBridgeError("PRIVATE_BRIDGE_UTF8_INVALID") from error
    lines = [line for line in text.splitlines() if line]
    if len(lines) != 1:
        raise PrivateBridgeError("PRIVATE_BRIDGE_ONE_LINE_REQUIRED")
    try:
        return json.loads(lines[0], object_pairs_hook=_no_duplicates)
    except (json.JSONDecodeError, _DuplicateKey) as error:
        raise PrivateBridgeError("PRIVATE_BRIDGE_JSON_INVALID") from error


def encode_one_json_line(value: object, maximum_bytes: int) -> bytes:
    data = (json.dumps(_plain(value), separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
    if len(data) > maximum_bytes:
        raise PrivateBridgeError("PRIVATE_BRIDGE_INPUT_TOO_LARGE")
    return data


def _digest(value: object) -> str:
    data = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _digest_bytes(data)


def _digest_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


class _DuplicateKey(ValueError):
    pass


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey()
        result[key] = value
    return result
