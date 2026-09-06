"""Domain-facing exports of the shared provider-neutral hardware errors."""

from ai_instrument_assistant.hardware.errors import (
    HardwareError,
    InstrumentCommandError,
    InstrumentConnectionError,
    InstrumentDisconnectedError,
    InstrumentIdentityMismatchError,
    InstrumentResponseError,
    InstrumentStateVerificationError,
    InstrumentTimeoutError,
    WaveformDecodeError,
)

__all__ = [
    "HardwareError",
    "InstrumentCommandError",
    "InstrumentConnectionError",
    "InstrumentDisconnectedError",
    "InstrumentIdentityMismatchError",
    "InstrumentResponseError",
    "InstrumentStateVerificationError",
    "InstrumentTimeoutError",
    "WaveformDecodeError",
]
