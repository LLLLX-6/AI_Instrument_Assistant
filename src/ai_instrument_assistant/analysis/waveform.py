from __future__ import annotations

import math
from statistics import median

from ai_instrument_assistant.domain.instrument.waveform import Waveform
from ai_instrument_assistant.domain.values import DutyCycle

from .models import (
    AnalysisAlgorithmMetadata,
    AnalysisQuality,
    AnalysisWarning,
    WaveformAnalysisResult,
    WaveformProvenance,
)


_ALGORITHM_NAME = "aia.threshold_edges"
_ALGORITHM_VERSION = "1.0.0"
_HYSTERESIS_FRACTION = 0.10
_TIME_STEP_RELATIVE_TOLERANCE = 1e-6
_PERIOD_INLIER_RELATIVE_TOLERANCE = 0.10
_MINIMUM_PERIODS = 2


def analyze_waveform(waveform: Waveform) -> WaveformAnalysisResult:
    """Deterministically analyze one provider-neutral waveform without I/O."""

    if not isinstance(waveform, Waveform):
        raise TypeError("waveform must be a provider-neutral Waveform")
    values = waveform.voltage_values
    if not values:
        raise ValueError("waveform must contain at least one sample")
    if not all(math.isfinite(value) for value in values):
        raise ValueError("waveform voltage samples must be finite")

    minimum = min(values)
    maximum = max(values)
    vpp = maximum - minimum
    if not math.isfinite(vpp):
        raise ValueError("waveform voltage span is not finite")
    mean, rms = _stable_mean_and_rms(values)
    threshold = minimum + vpp / 2.0
    hysteresis_band = vpp * _HYSTERESIS_FRACTION
    warnings: list[AnalysisWarning] = []
    rising: tuple[float, ...] = ()
    falling: tuple[float, ...] = ()
    periods_used = 0
    duty_cycles_used = 0
    frequency: float | None = None
    period: float | None = None
    duty: DutyCycle | None = None

    time_status = _validate_time_axis(waveform)
    if time_status is not None:
        _warn(warnings, time_status)
        quality = AnalysisQuality.INVALID
    elif waveform.point_count < 3:
        _warn(warnings, AnalysisWarning.INSUFFICIENT_SAMPLES)
        _warn(warnings, AnalysisWarning.SIGNAL_TOO_SMALL)
        _warn(warnings, AnalysisWarning.NO_EDGES_DETECTED)
        quality = AnalysisQuality.DEGRADED
    elif vpp < max(4.0 * abs(waveform.voltage_increment), 1e-12):
        _warn(warnings, AnalysisWarning.SIGNAL_TOO_SMALL)
        _warn(warnings, AnalysisWarning.NO_EDGES_DETECTED)
        quality = AnalysisQuality.DEGRADED
    else:
        rising, falling = _schmitt_edges(
            waveform.time_values,
            values,
            threshold - hysteresis_band / 2.0,
            threshold + hysteresis_band / 2.0,
        )
        if not rising and not falling:
            _warn(warnings, AnalysisWarning.NO_EDGES_DETECTED)
        if _looks_clipped(values, minimum, maximum):
            _warn(warnings, AnalysisWarning.CLIPPED_SIGNAL_SUSPECTED)

        period_values = tuple(
            later - earlier for earlier, later in zip(rising, rising[1:])
        )
        period_inliers = _robust_inliers(
            period_values,
            relative_tolerance=_PERIOD_INLIER_RELATIVE_TOLERANCE,
        )
        if len(period_values) < _MINIMUM_PERIODS:
            _warn(warnings, AnalysisWarning.INSUFFICIENT_CYCLES)
        elif len(period_inliers) < _MINIMUM_PERIODS or len(period_inliers) / len(period_values) < 0.75:
            _warn(warnings, AnalysisWarning.UNSTABLE_PERIOD)
        else:
            period = median(period_inliers)
            frequency = 1.0 / period
            periods_used = len(period_inliers)
            duty_values = _complete_cycle_duties(rising, falling, period_inliers)
            duty_inliers = _robust_inliers(duty_values, relative_tolerance=0.15)
            if len(duty_inliers) < _MINIMUM_PERIODS:
                _warn(warnings, AnalysisWarning.AMBIGUOUS_THRESHOLD)
            else:
                duty = DutyCycle.from_ratio(median(duty_inliers))
                duty_cycles_used = len(duty_inliers)

        quality = (
            AnalysisQuality.GOOD
            if frequency is not None and duty is not None and not warnings
            else AnalysisQuality.DEGRADED
        )

    metadata = AnalysisAlgorithmMetadata(
        name=_ALGORITHM_NAME,
        version=_ALGORITHM_VERSION,
        threshold_strategy="midpoint(min,max)",
        threshold_v=threshold,
        hysteresis_strategy="symmetric_10_percent_amplitude",
        hysteresis_band_v=hysteresis_band,
        rising_edge_count=len(rising),
        falling_edge_count=len(falling),
        periods_used=periods_used,
        duty_cycles_used=duty_cycles_used,
    )
    provenance = WaveformProvenance(
        instrument_identity=waveform.instrument_identity,
        channel=waveform.channel,
        captured_at=waveform.captured_at,
        point_count=waveform.point_count,
        sample_interval_seconds=waveform.sample_interval_seconds,
        acquisition_mode=waveform.acquisition_mode.value,
    )
    return WaveformAnalysisResult(
        vpp_v=vpp,
        mean_v=mean,
        rms_v=rms,
        frequency_hz=frequency,
        period_s=period,
        duty_cycle=duty,
        quality=quality,
        warnings=tuple(warnings),
        algorithm=metadata,
        waveform=provenance,
    )


def _stable_mean_and_rms(values: tuple[float, ...]) -> tuple[float, float]:
    scale = max(abs(value) for value in values)
    if scale == 0.0:
        return 0.0, 0.0
    normalized = tuple(value / scale for value in values)
    mean = scale * (math.fsum(normalized) / len(normalized))
    rms = scale * math.sqrt(
        math.fsum(value * value for value in normalized) / len(normalized)
    )
    if not math.isfinite(mean) or not math.isfinite(rms):
        raise ValueError("waveform statistics are not finite")
    return mean, rms


def _validate_time_axis(waveform: Waveform) -> AnalysisWarning | None:
    times = waveform.time_values
    if len(times) != len(waveform.voltage_values) or not all(
        math.isfinite(value) for value in times
    ):
        return AnalysisWarning.INVALID_TIME_AXIS
    if len(times) < 2:
        return None
    deltas = tuple(later - earlier for earlier, later in zip(times, times[1:]))
    if any(delta <= 0.0 or not math.isfinite(delta) for delta in deltas):
        return AnalysisWarning.INVALID_TIME_AXIS
    typical = median(deltas)
    tolerance = max(abs(typical) * _TIME_STEP_RELATIVE_TOLERANCE, 1e-15)
    if (
        any(abs(delta - typical) > tolerance for delta in deltas)
        or abs(waveform.sample_interval_seconds - typical) > tolerance
    ):
        return AnalysisWarning.NONUNIFORM_SAMPLING
    return None


def _schmitt_edges(
    times: tuple[float, ...],
    values: tuple[float, ...],
    low_threshold: float,
    high_threshold: float,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    state: str | None
    if values[0] <= low_threshold:
        state = "low"
    elif values[0] >= high_threshold:
        state = "high"
    else:
        state = None
    rising: list[float] = []
    falling: list[float] = []
    for index in range(1, len(values)):
        current = values[index]
        if state == "low" and current >= high_threshold:
            rising.append(_interpolate_crossing(
                times[index - 1], values[index - 1], times[index], current, high_threshold
            ))
            state = "high"
        elif state == "high" and current <= low_threshold:
            falling.append(_interpolate_crossing(
                times[index - 1], values[index - 1], times[index], current, low_threshold
            ))
            state = "low"
        elif state is None:
            if current <= low_threshold:
                state = "low"
            elif current >= high_threshold:
                state = "high"
    return tuple(rising), tuple(falling)


def _interpolate_crossing(
    t0: float,
    v0: float,
    t1: float,
    v1: float,
    threshold: float,
) -> float:
    voltage_delta = v1 - v0
    if voltage_delta == 0.0:
        return t1
    fraction = (threshold - v0) / voltage_delta
    return t0 + min(1.0, max(0.0, fraction)) * (t1 - t0)


def _robust_inliers(
    values: tuple[float, ...],
    *,
    relative_tolerance: float,
) -> tuple[float, ...]:
    positive = tuple(value for value in values if math.isfinite(value) and value > 0.0)
    if not positive:
        return ()
    center = median(positive)
    limit = center * relative_tolerance
    return tuple(value for value in positive if abs(value - center) <= limit)


def _complete_cycle_duties(
    rising: tuple[float, ...],
    falling: tuple[float, ...],
    accepted_periods: tuple[float, ...],
) -> tuple[float, ...]:
    accepted = list(accepted_periods)
    ratios: list[float] = []
    for start, stop in zip(rising, rising[1:]):
        cycle_period = stop - start
        match_index = next(
            (index for index, value in enumerate(accepted) if math.isclose(
                value, cycle_period, rel_tol=1e-9, abs_tol=1e-15
            )),
            None,
        )
        if match_index is None:
            continue
        del accepted[match_index]
        fall = next((edge for edge in falling if start < edge < stop), None)
        if fall is None:
            continue
        ratio = (fall - start) / cycle_period
        if 0.0 <= ratio <= 1.0:
            ratios.append(ratio)
    return tuple(ratios)


def _looks_clipped(values: tuple[float, ...], minimum: float, maximum: float) -> bool:
    if len(values) < 20 or minimum == maximum:
        return False
    minimum_count = sum(value == minimum for value in values)
    maximum_count = sum(value == maximum for value in values)
    distinct = len(set(values))
    return distinct >= 8 and minimum_count / len(values) >= 0.05 and maximum_count / len(values) >= 0.05


def _warn(warnings: list[AnalysisWarning], warning: AnalysisWarning) -> None:
    if warning not in warnings:
        warnings.append(warning)
