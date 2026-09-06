"""Finite hardware errors that never expose backend exception details."""


class HardwareError(RuntimeError):
    """Base error for hardware communication and instrument operations."""


class TransportError(HardwareError):
    """A communication backend operation failed."""


class TransportTimeoutError(TransportError):
    """A communication backend operation exceeded its timeout."""


class TransportDisconnectedError(TransportError):
    """The transport resource is closed or no longer reachable."""


class InstrumentConnectionError(HardwareError):
    """An instrument connection or disconnection operation failed."""


class InstrumentDisconnectedError(InstrumentConnectionError):
    """An instrument operation requires a live connection."""


class InstrumentTimeoutError(InstrumentConnectionError):
    """An instrument operation exceeded the configured transport timeout."""


class InstrumentIdentityMismatchError(InstrumentConnectionError):
    """The connected device identity is incompatible with the selected driver."""


class InstrumentCommandError(HardwareError):
    """An instrument command could not be completed."""


class InstrumentResponseError(InstrumentCommandError):
    """A response is malformed, non-finite, or outside defined semantics."""


class InstrumentStateVerificationError(InstrumentCommandError):
    """Read-back does not establish the requested instrument post-condition."""


class WaveformAcquisitionError(InstrumentCommandError):
    """A semantic waveform acquisition could not be completed safely."""


class WaveformProtocolError(WaveformAcquisitionError):
    """A binary waveform response violates the supported framing protocol."""


class WaveformDecodeError(WaveformProtocolError):
    """A framed waveform payload could not be decoded."""


class WaveformMetadataError(WaveformAcquisitionError):
    """Waveform metadata is malformed or unsupported by the current slice."""


class WaveformLengthMismatchError(WaveformProtocolError):
    """Declared, requested, and received waveform lengths are inconsistent."""
