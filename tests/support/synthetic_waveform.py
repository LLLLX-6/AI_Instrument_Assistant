from __future__ import annotations

import math
import random
from datetime import UTC, datetime

from ai_instrument_assistant.domain.instrument.models import InstrumentIdentity
from ai_instrument_assistant.domain.instrument.waveform import (
    Waveform,
    WaveformAcquisitionMode,
)


SYNTHETIC_IDENTITY = InstrumentIdentity(
    "AIA",
    "SyntheticWaveform",
    "DETERMINISTIC",
    "1",
)


def waveform_from_values(
    values: tuple[float, ...],
    *,
    sample_interval: float,
    times: tuple[float, ...] | None = None,
    voltage_increment: float = 1e-3,
) -> Waveform:
    time_values = times or tuple(index * sample_interval for index in range(len(values)))
    return Waveform(
        channel=1,
        point_count=len(values),
        sample_interval_seconds=sample_interval,
        time_origin_seconds=time_values[0],
        time_reference=0.0,
        voltage_increment=voltage_increment,
        voltage_origin=0.0,
        voltage_reference=0.0,
        time_values=time_values,
        voltage_values=values,
        acquisition_mode=WaveformAcquisitionMode.NORMAL,
        instrument_identity=SYNTHETIC_IDENTITY,
        captured_at=datetime(2026, 9, 6, tzinfo=UTC),
        average_count=1,
        requested_start=1,
        requested_stop=len(values),
    )


def square_wave(
    *,
    frequency_hz: float,
    duty_ratio: float,
    sample_interval: float,
    duration: float,
    phase_seconds: float = 0.0,
    low: float = 0.0,
    high: float = 3.3,
    noise_peak: float = 0.0,
) -> Waveform:
    count = int(duration / sample_interval) + 1
    random_source = random.Random(0xA1A6D)
    period = 1.0 / frequency_hz
    values = []
    for index in range(count):
        time_value = index * sample_interval
        phase = ((time_value + phase_seconds) % period) / period
        ideal = high if phase < duty_ratio else low
        noise = random_source.uniform(-noise_peak, noise_peak)
        values.append(ideal + noise)
    return waveform_from_values(
        tuple(values),
        sample_interval=sample_interval,
        voltage_increment=1e-3,
    )


def clipped_sine_wave(
    *,
    frequency_hz: float,
    sample_interval: float,
    duration: float,
) -> Waveform:
    count = int(duration / sample_interval) + 1
    values = tuple(
        max(-0.6, min(0.6, math.sin(2.0 * math.pi * frequency_hz * index * sample_interval)))
        for index in range(count)
    )
    return waveform_from_values(values, sample_interval=sample_interval)


def jittered_square_wave(
    *,
    periods: tuple[float, ...],
    duty_ratio: float,
    sample_interval: float,
) -> Waveform:
    boundaries = [0.0]
    for period in periods:
        boundaries.append(boundaries[-1] + period)
    duration = boundaries[-1] + periods[-1] * 0.1
    count = int(duration / sample_interval) + 1
    values: list[float] = []
    cycle = 0
    for index in range(count):
        time_value = index * sample_interval
        while cycle + 1 < len(boundaries) and time_value >= boundaries[cycle + 1]:
            cycle += 1
        if cycle >= len(periods):
            values.append(0.0)
            continue
        in_cycle = time_value - boundaries[cycle]
        values.append(3.3 if in_cycle < periods[cycle] * duty_ratio else 0.0)
    return waveform_from_values(tuple(values), sample_interval=sample_interval)
