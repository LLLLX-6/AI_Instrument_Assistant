from __future__ import annotations

import math
from typing import Any

from ai_instrument_assistant.communication.errors import (
    TransportDisconnectedError,
    TransportError,
    TransportTimeoutError,
)
from ai_instrument_assistant.communication.visa import VisaConnection, VisaTransport


class PyVisaTransport(VisaTransport):
    """Small PyVISA adapter. PyVISA is an optional hardware runtime dependency."""

    def __init__(self, *, resource_manager: Any | None = None, backend: str | None = None) -> None:
        if resource_manager is None:
            try:
                import pyvisa
            except ImportError as error:
                raise TransportError(
                    "PyVISA hardware runtime is unavailable"
                ) from error
            try:
                resource_manager = (
                    pyvisa.ResourceManager()
                    if backend is None
                    else pyvisa.ResourceManager(backend)
                )
            except Exception as error:
                raise _translate_visa_error(error, "VISA backend initialization failed") from error
        self._resource_manager = resource_manager

    def discover_resources(self) -> tuple[str, ...]:
        try:
            values = self._resource_manager.list_resources("?*::INSTR")
            return tuple(str(value) for value in values)
        except Exception as error:
            raise _translate_visa_error(error, "VISA resource discovery failed") from error

    def open(self, resource_name: str, *, timeout_seconds: float) -> VisaConnection:
        if (
            not isinstance(resource_name, str)
            or not resource_name
            or resource_name != resource_name.strip()
            or len(resource_name) > 1024
            or not resource_name.isprintable()
        ):
            raise ValueError("resource_name must be bounded printable text without surrounding whitespace")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
            raise ValueError("timeout_seconds must be a positive finite number")
        timeout = float(timeout_seconds)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout_seconds must be a positive finite number")
        resource: Any | None = None
        try:
            resource = self._resource_manager.open_resource(resource_name)
            resource.timeout = round(timeout * 1000)
            resource.write_termination = "\n"
            return _PyVisaConnection(resource)
        except Exception as error:
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    pass
            raise _translate_visa_error(error, "VISA resource open failed") from error


class _PyVisaConnection:
    __slots__ = ("_resource", "_closed")

    def __init__(self, resource: Any) -> None:
        self._resource = resource
        self._closed = False

    def write(self, command: str) -> None:
        self._require_open()
        try:
            self._resource.write(command)
        except Exception as error:
            raise _translate_visa_error(error, "VISA I/O failed") from error

    def query(self, command: str) -> str:
        self._require_open()
        try:
            value = self._resource.query(command)
        except Exception as error:
            raise _translate_visa_error(error, "VISA I/O failed") from error
        if not isinstance(value, str):
            raise TransportError("VISA query returned non-text data")
        return value

    def read_raw(self) -> bytes:
        self._require_open()
        try:
            value = self._resource.read_raw()
        except Exception as error:
            raise _translate_visa_error(error, "VISA I/O failed") from error
        if not isinstance(value, bytes):
            raise TransportError("VISA read returned non-bytes data")
        return value

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._resource.close()
        except Exception as error:
            raise _translate_visa_error(error, "VISA resource close failed") from error

    def _require_open(self) -> None:
        if self._closed:
            raise TransportDisconnectedError("VISA resource is closed")


def _translate_visa_error(error: Exception, message: str) -> TransportError:
    if isinstance(error, TransportError):
        return error
    if isinstance(error, TimeoutError) or _is_visa_timeout(error):
        return TransportTimeoutError(message)
    if isinstance(error, (ConnectionError, BrokenPipeError)):
        return TransportDisconnectedError(message)
    return TransportError(message)


def _is_visa_timeout(error: Exception) -> bool:
    error_code = getattr(error, "error_code", None)
    numeric = getattr(error_code, "value", error_code)
    return numeric == -1073807339  # VI_ERROR_TMO, mapped only inside PyVISA boundary.
