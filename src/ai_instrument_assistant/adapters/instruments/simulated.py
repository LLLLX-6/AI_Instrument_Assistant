from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from ai_instrument_assistant.application.ports.oscilloscope import (
    ChannelCoupling,
    OscilloscopeInterface,
)
from ai_instrument_assistant.domain.instrument import (
    InstrumentDisconnectedError,
    InstrumentIdentity,
    Waveform,
    WaveformAcquisitionMode,
)


class SimulatedOscilloscope(OscilloscopeInterface):
    """Deterministic in-memory oscilloscope for development without hardware."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._clock = clock
        self._connected = False
        self._identity = InstrumentIdentity(
            manufacturer="AI Instrument Assistant",
            model="Simulated Oscilloscope",
            serial_number="SIMULATED",
            firmware_version="1.0",
        )
        self._enabled = {1: True, 2: True}
        self._coupling = {1: ChannelCoupling.DC, 2: ChannelCoupling.DC}
        self._scale = {1: 1.0, 2: 1.0}
        self._probe_ratio = {1: 1.0, 2: 1.0}
        self._timebase = 20e-6

    def connect(self) -> InstrumentIdentity:
        self._connected = True
        return self._identity

    def disconnect(self) -> None:
        self._connected = False

    def get_identity(self) -> InstrumentIdentity:
        self._require_connected()
        return self._identity

    def get_channel_enabled(self, channel: int) -> bool:
        self._require_connected()
        return self._enabled[self._channel(channel)]

    def set_channel_enabled(self, channel: int, enabled: bool) -> None:
        self._require_connected()
        if not isinstance(enabled, bool):
            raise TypeError("enabled must be bool")
        self._enabled[self._channel(channel)] = enabled

    def get_channel_coupling(self, channel: int) -> ChannelCoupling:
        self._require_connected()
        return self._coupling[self._channel(channel)]

    def set_channel_coupling(self, channel: int, coupling: ChannelCoupling) -> None:
        self._require_connected()
        if not isinstance(coupling, ChannelCoupling):
            raise TypeError("coupling must be ChannelCoupling")
        self._coupling[self._channel(channel)] = coupling

    def get_channel_scale(self, channel: int) -> float:
        self._require_connected()
        return self._scale[self._channel(channel)]

    def set_channel_scale(self, channel: int, volts_per_div: float) -> None:
        self._require_connected()
        self._scale[self._channel(channel)] = self._positive(volts_per_div)

    def get_probe_ratio(self, channel: int) -> float:
        self._require_connected()
        return self._probe_ratio[self._channel(channel)]

    def set_probe_ratio(self, channel: int, ratio: float) -> None:
        self._require_connected()
        self._probe_ratio[self._channel(channel)] = self._positive(ratio)

    def get_timebase_scale(self) -> float:
        self._require_connected()
        return self._timebase

    def set_timebase_scale(self, seconds_per_div: float) -> None:
        self._require_connected()
        self._timebase = self._positive(seconds_per_div)

    def measure_frequency(self, channel: int) -> float:
        self._require_connected()
        self._channel(channel)
        return 10_000.0

    def measure_vpp(self, channel: int) -> float:
        self._require_connected()
        self._channel(channel)
        return 3.3

    def capture_waveform(self, channel: int) -> Waveform:
        self._require_connected()
        channel = self._channel(channel)
        point_count = 1200
        interval = 200e-9
        time_origin = -120e-6
        times = tuple(time_origin + index * interval for index in range(point_count))
        values = tuple(
            3.3 if index >= 50 and (index - 50) % 500 < 150 else 0.0
            for index in range(point_count)
        )
        captured_at = self._clock()
        if not isinstance(captured_at, datetime) or captured_at.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return Waveform(
            channel=channel,
            point_count=point_count,
            sample_interval_seconds=interval,
            time_origin_seconds=time_origin,
            time_reference=0.0,
            voltage_increment=0.01,
            voltage_origin=0.0,
            voltage_reference=0.0,
            time_values=times,
            voltage_values=values,
            acquisition_mode=WaveformAcquisitionMode.NORMAL,
            instrument_identity=self._identity,
            captured_at=captured_at,
            average_count=1,
            requested_start=1,
            requested_stop=point_count,
        )

    def _require_connected(self) -> None:
        if not self._connected:
            raise InstrumentDisconnectedError("simulated oscilloscope is disconnected")

    @staticmethod
    def _channel(channel: int) -> int:
        if isinstance(channel, bool) or channel not in (1, 2):
            raise ValueError("channel must be 1 or 2")
        return channel

    @staticmethod
    def _positive(value: float) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise ValueError("value must be positive")
        return float(value)
