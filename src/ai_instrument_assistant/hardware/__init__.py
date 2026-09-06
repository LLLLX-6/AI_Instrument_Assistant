"""Shared provider-neutral hardware contracts."""

from .errors import (
    HardwareError,
    InstrumentCommandError,
    InstrumentConnectionError,
    InstrumentDisconnectedError,
    InstrumentIdentityMismatchError,
    InstrumentResponseError,
    InstrumentStateVerificationError,
    InstrumentTimeoutError,
    TransportDisconnectedError,
    TransportError,
    TransportTimeoutError,
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
    "TransportDisconnectedError",
    "TransportError",
    "TransportTimeoutError",
    "WaveformAcquisitionError",
    "WaveformDecodeError",
    "WaveformLengthMismatchError",
    "WaveformMetadataError",
    "WaveformProtocolError",
]
