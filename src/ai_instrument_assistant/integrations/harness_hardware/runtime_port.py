from __future__ import annotations

from typing import Any, Protocol


class HardwareRuntimePort(Protocol):
    """The only execution dependency visible to the IPC server core."""

    def execute(self, payload: Any) -> dict[str, Any]: ...


class HardwareResponseValidatorPort(Protocol):
    """Validates a returned value against the canonical Hardware Tool contract."""

    def validate_runtime_response(self, payload: Any) -> None: ...
