from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum

from ai_instrument_assistant.domain.instrument.models import InstrumentIdentity


class ChannelCoupling(StrEnum):
    AC = "AC"
    DC = "DC"
    GND = "GND"


class OscilloscopeInterface(ABC):
    """Synchronous semantic port for a blocking oscilloscope driver."""

    @abstractmethod
    def connect(self) -> InstrumentIdentity: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def get_identity(self) -> InstrumentIdentity: ...

    @abstractmethod
    def get_channel_enabled(self, channel: int) -> bool: ...

    @abstractmethod
    def set_channel_enabled(self, channel: int, enabled: bool) -> None: ...

    @abstractmethod
    def get_channel_coupling(self, channel: int) -> ChannelCoupling: ...

    @abstractmethod
    def set_channel_coupling(self, channel: int, coupling: ChannelCoupling) -> None: ...

    @abstractmethod
    def get_channel_scale(self, channel: int) -> float: ...

    @abstractmethod
    def set_channel_scale(self, channel: int, volts_per_div: float) -> None: ...

    @abstractmethod
    def get_probe_ratio(self, channel: int) -> float: ...

    @abstractmethod
    def set_probe_ratio(self, channel: int, ratio: float) -> None: ...

    @abstractmethod
    def get_timebase_scale(self) -> float: ...

    @abstractmethod
    def set_timebase_scale(self, seconds_per_div: float) -> None: ...

    @abstractmethod
    def measure_frequency(self, channel: int) -> float: ...

    @abstractmethod
    def measure_vpp(self, channel: int) -> float: ...
