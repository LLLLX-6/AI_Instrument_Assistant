from __future__ import annotations

from threading import RLock

from ai_instrument_assistant.communication.errors import (
    TransportDisconnectedError,
    TransportError,
    TransportTimeoutError,
)
from ai_instrument_assistant.communication.visa import VisaConnection


class ScpiSession:
    """Serial SCPI request boundary; command vocabulary belongs to drivers."""

    def __init__(self, connection: VisaConnection) -> None:
        self._connection: VisaConnection | None = connection
        self._lock = RLock()

    @property
    def is_open(self) -> bool:
        with self._lock:
            return self._connection is not None

    def write(self, command: str) -> None:
        with self._lock:
            connection = self._require_connection()
            try:
                connection.write(command)
            except Exception as error:
                raise _communication_error(error, "SCPI write failed") from error

    def query(self, command: str) -> str:
        with self._lock:
            connection = self._require_connection()
            try:
                response = connection.query(command)
            except Exception as error:
                raise _communication_error(error, "SCPI query failed") from error
            if not isinstance(response, str):
                raise TransportError("SCPI query returned a non-text response")
            return response.rstrip("\r\n")

    def read_raw(self) -> bytes:
        with self._lock:
            connection = self._require_connection()
            try:
                response = connection.read_raw()
            except Exception as error:
                raise _communication_error(error, "SCPI binary read failed") from error
            if not isinstance(response, bytes):
                raise TransportError("SCPI binary read returned a non-bytes response")
            return response

    def query_raw(self, command: str) -> bytes:
        """Keep the command and binary response as one serialized exchange."""

        with self._lock:
            connection = self._require_connection()
            try:
                connection.write(command)
                response = connection.read_raw()
            except Exception as error:
                raise _communication_error(error, "SCPI binary query failed") from error
            if not isinstance(response, bytes):
                raise TransportError("SCPI binary query returned a non-bytes response")
            return response

    def close(self) -> None:
        with self._lock:
            connection = self._connection
            if connection is None:
                return
            self._connection = None
            try:
                connection.close()
            except Exception as error:
                raise _communication_error(error, "SCPI close failed") from error

    def _require_connection(self) -> VisaConnection:
        if self._connection is None:
            raise TransportDisconnectedError("SCPI session is closed")
        return self._connection


def _communication_error(error: Exception, message: str) -> TransportError:
    if isinstance(error, TransportError):
        return error
    if isinstance(error, TimeoutError):
        return TransportTimeoutError(message)
    if isinstance(error, (ConnectionError, BrokenPipeError)):
        return TransportDisconnectedError(message)
    return TransportError(message)
