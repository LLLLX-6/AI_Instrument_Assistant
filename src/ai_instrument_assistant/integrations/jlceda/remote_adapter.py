from __future__ import annotations

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
    HighlightResult,
    NoActiveDocumentError,
    OperationNotAllowedError,
)
from ai_instrument_assistant.domain.eda.models import DesignDocument, SelectionContext
from ai_instrument_assistant.protocol.schema_validator import (
    SchemaInstanceValidationError,
    SchemaValidator,
)

from .errors import (
    JLCEDAConnectionLostError,
    JLCEDAProtocolError,
    JLCEDARequestTimeoutError,
    JLCEDATransportUnavailableError,
    WireToDomainMappingError,
)
from .mapper import DESIGN_DOCUMENT_SCHEMA_ID, JLCEDADomainMapper


MESSAGE_SCHEMA_ID = "aia://protocol/jlceda/v1/message"
GET_ACTIVE_DOCUMENT = "eda.document.get_active"


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
        self._request_client = request_client
        self._validator = validator
        self._mapper = mapper
        self._request_timeout = request_timeout
        self._capabilities = EDACapabilitySet(frozenset({EDACapability.DOCUMENT_READ}))

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
        raise CapabilityUnsupportedError("selection.read is not enabled in Phase 5B.2b")

    async def highlight(self, command: HighlightCommand) -> HighlightResult:
        del command
        raise CapabilityUnsupportedError("view.highlight is not enabled in Phase 5B.2b")

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
        raise EDAInterfaceError(message)


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise JLCEDAProtocolError("Expected a protocol object")
    return value
