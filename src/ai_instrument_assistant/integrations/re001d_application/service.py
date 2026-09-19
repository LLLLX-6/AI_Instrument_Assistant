from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from threading import Lock
from typing import Any

from ai_instrument_assistant.application.reasoning.publication import OneShotPublicationCoordinator
from ai_instrument_assistant.application.services.re001d_lite import (
    RE001DIntentError,
    RE001DLiteCoordinator,
    RE001DPreparedExperiment,
)
from ai_instrument_assistant.protocol.schema_registry import SchemaRegistry
from ai_instrument_assistant.protocol.schema_validator import (
    SchemaInstanceValidationError,
    SchemaValidator,
)


PROTOCOL = "aia-re001d-application/v1"
BASE = "https://ai-instrument-assistant.local/schemas/re001d-application/v1/"


class RE001DApplicationError(ValueError):
    """A bounded private application-service rejection."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class RE001DApplicationService:
    """Owns prepare/complete correlation, never Hardware authority or execution."""

    def __init__(
        self,
        protocol_root: Path,
        publisher_factory: Callable[[], OneShotPublicationCoordinator],
    ) -> None:
        self._validator = SchemaValidator(
            SchemaRegistry.from_directory(protocol_root), enforce_formats=True
        )
        self._publisher_factory = publisher_factory
        self._coordinator = RE001DLiteCoordinator()
        self._prepared: dict[tuple[str, str], RE001DPreparedExperiment] = {}
        self._completed: set[tuple[str, str]] = set()
        self._lock = Lock()

    def prepare(self, value: object) -> dict[str, Any]:
        request = self._validate("prepare-request.schema.json", value)
        key = _key(request)
        try:
            prepared = self._coordinator.prepare(str(request["user_text"]))
        except RE001DIntentError as error:
            raise RE001DApplicationError("UNSUPPORTED_INTENT") from error
        with self._lock:
            self._prepared[key] = prepared
            self._completed.discard(key)
        plan = prepared.plan
        response = {
            "protocol": PROTOCOL,
            "operation": "prepare",
            "workflow_id": key[0],
            "request_correlation_id": key[1],
            "intent": prepared.intent,
            "status": prepared.status,
            "plan": {
                "requested_frequency_hz": plan.requested_frequency_hz,
                "design_context_source": plan.design_context_source.value,
                "vin": plan.vin_role.declared_label,
                "vout": plan.vout_role.declared_label,
                "reference": plan.reference_role.declared_label,
                "operation_sequence": [list(item) for item in prepared.operation_sequence],
            },
            "wiring_instructions": prepared.confirmation_prompt,
        }
        return dict(self._validate("prepare-response.schema.json", response))

    async def complete(self, value: object) -> dict[str, Any]:
        request = self._validate("complete-request.schema.json", value)
        key = _key(request)
        with self._lock:
            prepared = self._prepared.get(key)
            if prepared is None:
                raise RE001DApplicationError("CORRELATION_MISMATCH")
            if key in self._completed:
                raise RE001DApplicationError("DUPLICATE_COMPLETE")
            # Reserve exactly once before model/publication I/O. Failure is not
            # implicitly retryable because the governed receipt was dispatched.
            self._completed.add(key)
        try:
            result = await self._coordinator.complete(
                prepared,
                _plain(request["governed_receipt"]),
                publisher=self._publisher_factory(),
                correlation_id=key[1],
            )
        except Exception as error:
            raise RE001DApplicationError("APPLICATION_FAILURE") from error
        publication = result.publication
        response = {
            "protocol": PROTOCOL,
            "operation": "complete",
            "workflow_id": key[0],
            "request_correlation_id": key[1],
            "status": "COMPLETED",
            "publication": {
                "status": publication.publication.status,
                "text": publication.publication.text,
                "grounding_result": publication.audit.grounding_result,
                "final_egress": publication.audit.final_egress,
                "model_request_count": publication.audit.model_request_count,
                "model_retry_count": publication.audit.model_retry_count,
            },
        }
        return dict(self._validate("complete-response.schema.json", response))

    def _validate(self, name: str, value: object) -> Mapping[str, Any]:
        try:
            result = self._validator.validate_and_freeze(BASE + name, value).instance
        except SchemaInstanceValidationError as error:
            raise RE001DApplicationError("INVALID_REQUEST") from error
        if not isinstance(result, Mapping):
            raise RE001DApplicationError("INVALID_REQUEST")
        return result


def _key(value: Mapping[str, Any]) -> tuple[str, str]:
    return str(value["workflow_id"]), str(value["request_correlation_id"])


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value
