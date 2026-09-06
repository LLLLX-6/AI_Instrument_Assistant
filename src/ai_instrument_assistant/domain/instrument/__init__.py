"""Provider-neutral instrument domain."""

from .errors import (
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
from .models import InstrumentIdentity
from .waveform import Waveform, WaveformAcquisitionMode

__all__ = [
    "HardwareError",
    "InstrumentCommandError",
    "InstrumentConnectionError",
    "InstrumentDisconnectedError",
    "InstrumentIdentity",
    "InstrumentIdentityMismatchError",
    "InstrumentResponseError",
    "InstrumentStateVerificationError",
    "InstrumentTimeoutError",
    "Waveform",
    "WaveformAcquisitionError",
    "WaveformAcquisitionMode",
    "WaveformDecodeError",
    "WaveformLengthMismatchError",
    "WaveformMetadataError",
    "WaveformProtocolError",
]
