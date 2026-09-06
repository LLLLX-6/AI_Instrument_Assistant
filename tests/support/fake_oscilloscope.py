from __future__ import annotations

from dataclasses import replace

from ai_instrument_assistant.application.ports.oscilloscope import (
    ChannelCoupling,
    OscilloscopeInterface,
)
from ai_instrument_assistant.domain.instrument import (
    InstrumentCommandError,
    InstrumentIdentity,
    Waveform,
    WaveformAcquisitionError,
)


class FakeOscilloscope(OscilloscopeInterface):
    def __init__(self, waveform: Waveform) -> None:
        self.waveform = waveform
        self.identity = waveform.instrument_identity
        self.frequency_hz = 10_020.04
        self.vpp_v = 0.424
        self.fail_frequency = False
        self.fail_vpp = False
        self.fail_waveform = False
        self.calls: list[str] = []

    def connect(self) -> InstrumentIdentity:
        self.calls.append("connect")
        return self.identity

    def disconnect(self) -> None:
        self.calls.append("disconnect")

    def get_identity(self) -> InstrumentIdentity:
        self.calls.append("get_identity")
        return self.identity

    def get_channel_enabled(self, channel: int) -> bool:
        return True

    def set_channel_enabled(self, channel: int, enabled: bool) -> None:
        return None

    def get_channel_coupling(self, channel: int) -> ChannelCoupling:
        return ChannelCoupling.DC

    def set_channel_coupling(self, channel: int, coupling: ChannelCoupling) -> None:
        return None

    def get_channel_scale(self, channel: int) -> float:
        return 1.0

    def set_channel_scale(self, channel: int, volts_per_div: float) -> None:
        return None

    def get_probe_ratio(self, channel: int) -> float:
        return 1.0

    def set_probe_ratio(self, channel: int, ratio: float) -> None:
        return None

    def get_timebase_scale(self) -> float:
        return 1e-4

    def set_timebase_scale(self, seconds_per_div: float) -> None:
        return None

    def measure_frequency(self, channel: int) -> float:
        self.calls.append("measure_frequency")
        if self.fail_frequency:
            raise InstrumentCommandError("frequency unavailable")
        return self.frequency_hz

    def measure_vpp(self, channel: int) -> float:
        self.calls.append("measure_vpp")
        if self.fail_vpp:
            raise InstrumentCommandError("Vpp unavailable")
        return self.vpp_v

    def capture_waveform(self, channel: int) -> Waveform:
        self.calls.append("capture_waveform")
        if self.fail_waveform:
            raise WaveformAcquisitionError("waveform unavailable")
        return replace(self.waveform, channel=channel)
