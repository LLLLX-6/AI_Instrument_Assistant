"""Communication-facing exports of the shared transport error taxonomy."""

from ai_instrument_assistant.hardware.errors import (
    TransportDisconnectedError,
    TransportError,
    TransportTimeoutError,
)

__all__ = ["TransportDisconnectedError", "TransportError", "TransportTimeoutError"]
