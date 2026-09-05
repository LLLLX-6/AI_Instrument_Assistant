from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import Any, Protocol

from ai_instrument_assistant.application.ports.eda_interface import (
    CapabilityUnsupportedError,
    EDAConnectionLostError,
    EDACapability,
    EDACapabilitySet,
    EDAInterface,
    EDAInterfaceError,
    EDANotConnectedError,
    EDAProtocolError,
    EDARequestTimeoutError,
    HighlightCommand,
    HighlightRejectedError, GuardMode, ScopeExpansion, SubmissionStatus, VerificationStatus,
    HighlightResult,
    InconsistentDesignObservationError,
    NoActiveDocumentError,
    OperationNotAllowedError,
)
from ai_instrument_assistant.domain.eda.models import DesignDocument, SelectionContext
from ai_instrument_assistant.protocol.schema_validator import (
    SchemaInstanceValidationError,
    SchemaValidator,
)

from .highlight_mapping import encode_highlight
from .errors import (
    JLCEDAConnectionLostError,
    JLCEDAProtocolError,
    JLCEDARequestTimeoutError,
    JLCEDATransportUnavailableError,
    WireToDomainMappingError,
)
from .mapper import (
    DESIGN_DOCUMENT_SCHEMA_ID,
    SELECTION_CONTEXT_SCHEMA_ID,
    JLCEDADomainMapper,
)


MESSAGE_SCHEMA_ID = "aia://protocol/jlceda/v1/message"
GET_ACTIVE_DOCUMENT = "eda.document.get_active"
GET_SELECTION = "eda.selection.get"


class JLCEDARequestClient(Protocol):
    async def request(
        self,
        operation: str,
        payload: object,
        *,
        timeout: float,
    ) -> object: ...


class JLCEDARemoteAdapter(EDAInterface):
    """JLCEDA integration adapter; transport JSON stops at this boundary."""

    def __init__(
        self,
        *,
        request_client: JLCEDARequestClient,
        validator: SchemaValidator,
        mapper: JLCEDADomainMapper,
        request_timeout: float = 5.0,
    ) -> None:
        if request_timeout <= 0:
            raise ValueError("request_timeout must be positive")
        self._highlight_ledger: dict[str, tuple[str, asyncio.Task[HighlightResult]]] = {}
        self._request_client = request_client
        self._validator = validator
        self._mapper = mapper
        self._request_timeout = request_timeout
        self._capabilities = EDACapabilitySet(
            frozenset(
                {EDACapability.DOCUMENT_READ, EDACapability.SELECTION_READ, EDACapability.VIEW_HIGHLIGHT}
            )
        )

    @property
    def capabilities(self) -> EDACapabilitySet:
        return self._capabilities

    async def get_active_document(self) -> DesignDocument:
        try:
            raw_response = await self._request_client.request(
                GET_ACTIVE_DOCUMENT,
                {},
                timeout=self._request_timeout,
            )
            self._validator.validate_and_freeze(
                MESSAGE_SCHEMA_ID,
                raw_response,
            )
            response = _mapping(raw_response)
            if response.get("operation") != GET_ACTIVE_DOCUMENT:
                raise JLCEDAProtocolError("Remote response operation mismatch")
            if response.get("status") == "error":
                self._raise_remote_error(_mapping(response.get("error")))
            payload = _mapping(response.get("payload"))
            validated_document = self._validator.validate_and_freeze(
                DESIGN_DOCUMENT_SCHEMA_ID,
                payload.get("document"),
            )
            return self._mapper.map_design_document(validated_document)
        except SchemaInstanceValidationError as error:
            raise EDAProtocolError(f"JLCEDA protocol response rejected: {error}") from error
        except WireToDomainMappingError as error:
            raise EDAProtocolError(f"JLCEDA mapping failed: {error}") from error
        except JLCEDATransportUnavailableError as error:
            raise EDANotConnectedError(str(error)) from error
        except JLCEDARequestTimeoutError as error:
            raise EDARequestTimeoutError(str(error)) from error
        except JLCEDAConnectionLostError as error:
            raise EDAConnectionLostError(str(error)) from error
        except JLCEDAProtocolError as error:
            raise EDAProtocolError(str(error)) from error

    async def get_selection(self) -> SelectionContext:
        try:
            raw_response = await self._request_client.request(
                GET_SELECTION,
                {},
                timeout=self._request_timeout,
            )
            self._validator.validate_and_freeze(MESSAGE_SCHEMA_ID, raw_response)
            response = _mapping(raw_response)
            if response.get("operation") != GET_SELECTION:
                raise JLCEDAProtocolError("Remote response operation mismatch")
            if response.get("status") == "error":
                self._raise_remote_error(_mapping(response.get("error")))
            payload = _mapping(response.get("payload"))
            validated_context = self._validator.validate_and_freeze(
                SELECTION_CONTEXT_SCHEMA_ID,
                payload.get("context"),
            )
            return self._mapper.map_selection_context(validated_context)
        except SchemaInstanceValidationError as error:
            raise EDAProtocolError(f"JLCEDA protocol response rejected: {error}") from error
        except WireToDomainMappingError as error:
            raise EDAProtocolError(f"JLCEDA mapping failed: {error}") from error
        except JLCEDATransportUnavailableError as error:
            raise EDANotConnectedError(str(error)) from error
        except JLCEDARequestTimeoutError as error:
            raise EDARequestTimeoutError(str(error)) from error
        except JLCEDAConnectionLostError as error:
            raise EDAConnectionLostError(str(error)) from error
        except JLCEDAProtocolError as error:
            raise EDAProtocolError(str(error)) from error

    async def highlight(self, command: HighlightCommand) -> HighlightResult:
        wire = encode_highlight(command)
        self._validator.validate_and_freeze("aia://protocol/jlceda/v1/models/highlight-command", wire)
        canonical = json.dumps(wire, sort_keys=True, separators=(",", ":"))
        existing = self._highlight_ledger.get(command.idempotency_key)
        if existing is not None:
            if existing[0] != canonical:
                raise HighlightRejectedError("idempotency_conflict")
            return await asyncio.shield(existing[1])
        if len(self._highlight_ledger) >= 1024:
            raise HighlightRejectedError("idempotency_capacity_exceeded")
        task = asyncio.create_task(self._submit_highlight(command, wire))
        task.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        self._highlight_ledger[command.idempotency_key] = (canonical, task)
        return await asyncio.shield(task)

    async def _submit_highlight(self, command: HighlightCommand, wire: object) -> HighlightResult:
        if command.guard_mode is GuardMode.STRONG_REQUIRED:
            raise HighlightRejectedError("strong_guard_unavailable")
        try:
            raw = await self._request_client.request("eda.view.highlight", {"command": wire}, timeout=self._request_timeout)
            self._validator.validate_and_freeze(MESSAGE_SCHEMA_ID, raw)
            response = _mapping(raw)
            if response.get("kind") != "response" or response.get("operation") != "eda.view.highlight":
                raise JLCEDAProtocolError("Highlight response mismatch")
            if response.get("status") == "error":
                raise HighlightRejectedError(str(_mapping(response["error"])["code"]))
            result = self._mapper.map_highlight_result(self._validator.validate_and_freeze(
                "aia://protocol/jlceda/v1/models/highlight-result", _mapping(response["payload"])["result"]))
            if (result.submitted_targets != command.targets
                or result.guard_mode_used != command.guard_mode
                or result.verification_status is not VerificationStatus.UNVERIFIED
                or result.verified_applied_targets or result.expires_at is not None
                or (result.scope_expansion is ScopeExpansion.WIRE_TO_NET and not command.allow_scope_expansion)):
                raise JLCEDAProtocolError("Unsupported highlight evidence")
            return result
        except JLCEDATransportUnavailableError as error:
            raise EDANotConnectedError("No authenticated transport; highlight was not submitted") from error
        except (JLCEDAConnectionLostError, JLCEDARequestTimeoutError, JLCEDAProtocolError,
                SchemaInstanceValidationError, WireToDomainMappingError):
            return HighlightResult(
                submission_status=SubmissionStatus.INDETERMINATE,
                verification_status=VerificationStatus.UNVERIFIED,
                submitted_targets=command.targets, verified_applied_targets=(),
                guard_mode_used=command.guard_mode, scope_expansion=ScopeExpansion.NONE,
                warnings=("Delivery/outcome unknown; not replayed. Scope expansion is unconfirmed, not proven absent.",),
                expires_at=None,
            )

    @staticmethod
    def _raise_remote_error(error: Mapping[str, Any]) -> None:
        code = error.get("code")
        message = str(error.get("message", "Remote JLCEDA operation failed"))
        if code == "no_active_document":
            raise NoActiveDocumentError(message)
        if code == "capability_unsupported":
            raise CapabilityUnsupportedError(message)
        if code == "operation_not_allowed":
            raise OperationNotAllowedError(message)
        if code == "inconsistent_observation":
            raise InconsistentDesignObservationError(message)
        raise EDAInterfaceError(message)


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise JLCEDAProtocolError("Expected a protocol object")
    return value
