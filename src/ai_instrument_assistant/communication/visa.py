from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol


class VisaConnection(Protocol):
    """Finite connection surface hidden from instrument and application callers."""

    def write(self, command: str) -> None: ...
    def query(self, command: str) -> str: ...
    def read_raw(self) -> bytes: ...
    def close(self) -> None: ...


class VisaTransport(ABC):
    @abstractmethod
    def discover_resources(self) -> tuple[str, ...]:
        """Return finite VISA resource names; no instrument semantics are inferred."""

    @abstractmethod
    def open(self, resource_name: str, *, timeout_seconds: float) -> VisaConnection:
        """Open one resource using a positive I/O timeout."""
