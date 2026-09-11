from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ai_instrument_assistant.application.reasoning.models import TeachingGoal
from ai_instrument_assistant.application.reasoning.publication.errors import (
    CandidateParseError,
    PublicationFailureCode,
)
from ai_instrument_assistant.application.reasoning.publication.models import (
    MAX_RAW_CANDIDATE_BYTES,
    StructuredClaimCandidateSet,
)

from .schema_registry import SchemaRegistry
from .schema_validator import SchemaInstanceValidationError, SchemaValidator


SCHEMA_ID = (
    "https://ai-instrument-assistant.local/schemas/teaching-claims/v1/"
    "structured-claim-candidate-set.schema.json"
)


class _DuplicateKey(ValueError):
    pass


class StrictCandidateParser:
    """Protocol adapter that never extracts, repairs, coerces, or logs input."""

    def __init__(self, protocol_root: Path, *, maximum_bytes: int = MAX_RAW_CANDIDATE_BYTES) -> None:
        self._maximum_bytes = maximum_bytes
        self._validator = SchemaValidator(SchemaRegistry.from_directory(protocol_root))

    def parse(self, raw: str) -> StructuredClaimCandidateSet:
        if not isinstance(raw, str) or not raw:
            raise CandidateParseError(PublicationFailureCode.EXACT_JSON_OBJECT_REQUIRED)
        encoded = raw.encode("utf-8")
        if len(encoded) > self._maximum_bytes:
            raise CandidateParseError(PublicationFailureCode.RAW_OUTPUT_TOO_LARGE)
        try:
            value = json.loads(raw, object_pairs_hook=_object_without_duplicates)
        except _DuplicateKey as error:
            raise CandidateParseError(PublicationFailureCode.DUPLICATE_JSON_KEY) from error
        except (json.JSONDecodeError, UnicodeError) as error:
            raise CandidateParseError(PublicationFailureCode.EXACT_JSON_OBJECT_REQUIRED) from error
        if not isinstance(value, dict):
            raise CandidateParseError(PublicationFailureCode.EXACT_JSON_OBJECT_REQUIRED)
        try:
            validated = self._validator.validate_and_freeze(SCHEMA_ID, value).instance
        except SchemaInstanceValidationError as error:
            raise CandidateParseError(PublicationFailureCode.CANDIDATE_SCHEMA_INVALID) from error
        return StructuredClaimCandidateSet(
            schema_id=validated["schema_id"],
            projection_id=validated["projection_id"],
            context_fingerprint=validated["context_fingerprint"],
            envelope_id=validated["envelope_id"],
            goal=TeachingGoal(validated["goal"]),
            ordered_permission_refs=tuple(validated["ordered_permission_refs"]),
            candidate_digest="sha256:" + hashlib.sha256(encoded).hexdigest(),
        )


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey()
        result[key] = value
    return result
