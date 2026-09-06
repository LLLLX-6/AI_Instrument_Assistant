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
    WaveformAcquisitionError,
    WaveformDecodeError,
    WaveformLengthMismatchError,
    WaveformMetadataError,
    WaveformProtocolError,
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
    "WaveformAcquisitionError",
    "WaveformDecodeError",
    "WaveformLengthMismatchError",
    "WaveformMetadataError",
    "WaveformProtocolError",
]
