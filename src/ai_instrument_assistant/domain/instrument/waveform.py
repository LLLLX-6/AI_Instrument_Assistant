from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .models import InstrumentIdentity


class WaveformAcquisitionMode(StrEnum):
    NORMAL = "normal"


@dataclass(frozen=True, slots=True)
class Waveform:
    """Provider-neutral, immutable waveform with explicit axis metadata."""

    channel: int
    point_count: int
    sample_interval_seconds: float
    time_origin_seconds: float
    time_reference: float
    voltage_increment: float
    voltage_origin: float
    voltage_reference: float
    time_values: tuple[float, ...]
    voltage_values: tuple[float, ...]
    acquisition_mode: WaveformAcquisitionMode
    instrument_identity: InstrumentIdentity
    captured_at: datetime
    average_count: int
    requested_start: int
    requested_stop: int

    def __post_init__(self) -> None:
        if isinstance(self.channel, bool) or not isinstance(self.channel, int) or self.channel < 1:
            raise ValueError("channel must be a positive integer")
        if isinstance(self.point_count, bool) or not isinstance(self.point_count, int) or self.point_count < 1:
            raise ValueError("point_count must be a positive integer")
        if not isinstance(self.time_values, tuple) or not isinstance(self.voltage_values, tuple):
            raise TypeError("waveform sample collections must be tuples")
        if len(self.time_values) != self.point_count or len(self.voltage_values) != self.point_count:
            raise ValueError("waveform sample lengths must equal point_count")
        if not isinstance(self.acquisition_mode, WaveformAcquisitionMode):
            raise TypeError("acquisition_mode must be WaveformAcquisitionMode")
        if not isinstance(self.instrument_identity, InstrumentIdentity):
            raise TypeError("instrument_identity must be InstrumentIdentity")
        if not isinstance(self.captured_at, datetime) or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at must be timezone-aware")
        if isinstance(self.average_count, bool) or not isinstance(self.average_count, int) or self.average_count < 1:
            raise ValueError("average_count must be a positive integer")
        if any(isinstance(value, bool) or not isinstance(value, int) for value in (self.requested_start, self.requested_stop)):
            raise TypeError("requested waveform positions must be integers")
        if self.requested_start < 1 or self.requested_stop < self.requested_start:
            raise ValueError("requested waveform range is invalid")
        if self.requested_stop - self.requested_start + 1 != self.point_count:
            raise ValueError("requested waveform range must equal point_count")

        positive = {
            "sample_interval_seconds": self.sample_interval_seconds,
            "voltage_increment": self.voltage_increment,
        }
        finite = {
            "time_origin_seconds": self.time_origin_seconds,
            "time_reference": self.time_reference,
            "voltage_origin": self.voltage_origin,
            "voltage_reference": self.voltage_reference,
        }
        for field, value in positive.items():
            if not _is_finite_number(value) or float(value) <= 0:
                raise ValueError(f"{field} must be finite and positive")
        for field, value in finite.items():
            if not _is_finite_number(value):
                raise ValueError(f"{field} must be finite")
        if not all(_is_finite_number(value) for value in self.time_values + self.voltage_values):
            raise ValueError("waveform samples must be finite numbers")


def _is_finite_number(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(float(value))
