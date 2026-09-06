from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ai_instrument_assistant.domain.instrument.models import InstrumentIdentity
from ai_instrument_assistant.domain.values import DutyCycle


class AnalysisQuality(StrEnum):
    GOOD = "good"
    DEGRADED = "degraded"
    INVALID = "invalid"


class AnalysisWarning(StrEnum):
    INSUFFICIENT_SAMPLES = "insufficient_samples"
    INSUFFICIENT_CYCLES = "insufficient_cycles"
    SIGNAL_TOO_SMALL = "signal_too_small"
    UNSTABLE_PERIOD = "unstable_period"
    CLIPPED_SIGNAL_SUSPECTED = "clipped_signal_suspected"
    AMBIGUOUS_THRESHOLD = "ambiguous_threshold"
    NO_EDGES_DETECTED = "no_edges_detected"
    INVALID_TIME_AXIS = "invalid_time_axis"
    NONUNIFORM_SAMPLING = "nonuniform_sampling"


@dataclass(frozen=True, slots=True)
class WaveformProvenance:
    instrument_identity: InstrumentIdentity
    channel: int
    captured_at: datetime
    point_count: int
    sample_interval_seconds: float
    acquisition_mode: str

    def __post_init__(self) -> None:
        if not isinstance(self.instrument_identity, InstrumentIdentity):
            raise TypeError("instrument_identity must be InstrumentIdentity")
        if isinstance(self.channel, bool) or not isinstance(self.channel, int) or self.channel < 1:
            raise ValueError("channel must be a positive integer")
        if not isinstance(self.captured_at, datetime) or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at must be timezone-aware")
        if isinstance(self.point_count, bool) or not isinstance(self.point_count, int) or self.point_count < 1:
            raise ValueError("point_count must be a positive integer")
        if not _positive_finite(self.sample_interval_seconds):
            raise ValueError("sample_interval_seconds must be finite and positive")
        if not isinstance(self.acquisition_mode, str) or not self.acquisition_mode.strip():
            raise ValueError("acquisition_mode must be non-empty text")


@dataclass(frozen=True, slots=True)
class AnalysisAlgorithmMetadata:
    name: str
    version: str
    threshold_strategy: str
    threshold_v: float
    hysteresis_strategy: str
    hysteresis_band_v: float
    rising_edge_count: int
    falling_edge_count: int
    periods_used: int
    duty_cycles_used: int

    def __post_init__(self) -> None:
        for field_name in ("name", "version", "threshold_strategy", "hysteresis_strategy"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be non-empty text")
        if not _finite(self.threshold_v):
            raise ValueError("threshold_v must be finite")
        if not _finite(self.hysteresis_band_v) or self.hysteresis_band_v < 0:
            raise ValueError("hysteresis_band_v must be finite and non-negative")
        for field_name in (
            "rising_edge_count", "falling_edge_count", "periods_used", "duty_cycles_used"
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class WaveformAnalysisResult:
    vpp_v: float
    mean_v: float
    rms_v: float
    frequency_hz: float | None
    period_s: float | None
    duty_cycle: DutyCycle | None
    quality: AnalysisQuality
    warnings: tuple[AnalysisWarning, ...]
    algorithm: AnalysisAlgorithmMetadata
    waveform: WaveformProvenance

    def __post_init__(self) -> None:
        for field_name in ("vpp_v", "mean_v", "rms_v"):
            if not _finite(getattr(self, field_name)):
                raise ValueError(f"{field_name} must be finite")
        if self.vpp_v < 0 or self.rms_v < 0:
            raise ValueError("vpp_v and rms_v must be non-negative")
        if (self.frequency_hz is None) is not (self.period_s is None):
            raise ValueError("frequency_hz and period_s must be present together")
        for field_name in ("frequency_hz", "period_s"):
            value = getattr(self, field_name)
            if value is not None and not _positive_finite(value):
                raise ValueError(f"{field_name} must be finite and positive")
        if self.duty_cycle is not None and not isinstance(self.duty_cycle, DutyCycle):
            raise TypeError("duty_cycle must be DutyCycle or None")
        if not isinstance(self.quality, AnalysisQuality):
            raise TypeError("quality must be AnalysisQuality")
        if not isinstance(self.warnings, tuple) or any(
            not isinstance(warning, AnalysisWarning) for warning in self.warnings
        ):
            raise TypeError("warnings must be a tuple of AnalysisWarning values")
        if len(self.warnings) != len(set(self.warnings)):
            raise ValueError("warnings must be unique")
        if not isinstance(self.algorithm, AnalysisAlgorithmMetadata):
            raise TypeError("algorithm must be AnalysisAlgorithmMetadata")
        if not isinstance(self.waveform, WaveformProvenance):
            raise TypeError("waveform must be WaveformProvenance")


def _finite(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(float(value))


def _positive_finite(value: object) -> bool:
    return _finite(value) and float(value) > 0
