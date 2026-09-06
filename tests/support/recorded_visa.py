from __future__ import annotations

from typing import Any


class RecordedVisaConnection:
    def __init__(
        self,
        *,
        responses: dict[str, str | list[str]] | None = None,
        query_error: Exception | None = None,
        close_error: Exception | None = None,
        raw_response: bytes = b"",
    ) -> None:
        self.responses = responses or {}
        self.query_error = query_error
        self.close_error = close_error
        self.raw_response = raw_response
        self.calls: list[tuple[str, str]] = []
        self.closed = False

    def write(self, command: str) -> None:
        self.calls.append(("write", command))

    def query(self, command: str) -> str:
        self.calls.append(("query", command))
        if self.query_error is not None:
            raise self.query_error
        response = self.responses[command]
        if isinstance(response, list):
            if not response:
                raise AssertionError(f"No recorded response remains for {command}")
            return response.pop(0)
        return response

    def read_raw(self) -> bytes:
        self.calls.append(("read_raw", ""))
        return self.raw_response

    def close(self) -> None:
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


class RecordedVisaTransport:
    def __init__(
        self,
        connection: RecordedVisaConnection,
        resources: tuple[str, ...] = ("USB::SCOPE",),
        *,
        open_error: Exception | None = None,
    ) -> None:
        self.connection = connection
        self.resources = resources
        self.open_error = open_error
        self.open_calls: list[tuple[str, float]] = []

    def discover_resources(self) -> tuple[str, ...]:
        return self.resources

    def open(self, resource_name: str, *, timeout_seconds: float):
        self.open_calls.append((resource_name, timeout_seconds))
        if self.open_error is not None:
            raise self.open_error
        return self.connection
