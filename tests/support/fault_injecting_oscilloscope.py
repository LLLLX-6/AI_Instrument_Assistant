from __future__ import annotations

from ai_instrument_assistant.domain.instrument import InstrumentCommandError


class FaultInjectingOscilloscope:
    """Controlled test wrapper; never requires disconnecting physical USB."""

    def __init__(
        self,
        delegate,
        *,
        fail_frequency: bool = False,
        fail_vpp: bool = False,
        fail_waveform: bool = False,
    ) -> None:
        self._delegate = delegate
        self._fail_frequency = fail_frequency
        self._fail_vpp = fail_vpp
        self._fail_waveform = fail_waveform

    def connect(self):
        return self._delegate.connect()

    def disconnect(self):
        return self._delegate.disconnect()

    def get_identity(self):
        return self._delegate.get_identity()

    def capture_waveform(self, channel: int):
        if self._fail_waveform:
            raise InstrumentCommandError("controlled waveform failure")
        return self._delegate.capture_waveform(channel)

    def measure_frequency(self, channel: int):
        if self._fail_frequency:
            raise InstrumentCommandError("controlled frequency failure")
        return self._delegate.measure_frequency(channel)

    def measure_vpp(self, channel: int):
        if self._fail_vpp:
            raise InstrumentCommandError("controlled Vpp failure")
        return self._delegate.measure_vpp(channel)
