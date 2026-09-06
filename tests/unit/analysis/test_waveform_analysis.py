from __future__ import annotations

import math
import random
import unittest
from dataclasses import replace

from ai_instrument_assistant.analysis.models import AnalysisQuality, AnalysisWarning
from ai_instrument_assistant.analysis.waveform import analyze_waveform
from tests.support.synthetic_waveform import (
    clipped_sine_wave,
    jittered_square_wave,
    square_wave,
    waveform_from_values,
)


class BasicStatisticsTests(unittest.TestCase):
    def test_vpp_mean_and_rms_use_defined_population_formulas(self) -> None:
        waveform = waveform_from_values((-1.0, 1.0, -1.0, 1.0), sample_interval=1e-6)
        result = analyze_waveform(waveform)
        self.assertEqual(2.0, result.vpp_v)
        self.assertEqual(0.0, result.mean_v)
        self.assertEqual(1.0, result.rms_v)

    def test_finite_inputs_that_overflow_voltage_span_are_rejected(self) -> None:
        waveform = waveform_from_values(
            (-1e308, 1e308, -1e308),
            sample_interval=1e-6,
            voltage_increment=1.0,
        )
        with self.assertRaises(ValueError):
            analyze_waveform(waveform)

    def test_constant_zero_and_dc_return_statistics_but_no_periodic_metrics(self) -> None:
        for value in (0.0, 2.5):
            waveform = waveform_from_values((value,) * 100, sample_interval=1e-6)
            result = analyze_waveform(waveform)
            with self.subTest(value=value):
                self.assertEqual(0.0, result.vpp_v)
                self.assertEqual(value, result.mean_v)
                self.assertEqual(abs(value), result.rms_v)
                self.assertIsNone(result.frequency_hz)
                self.assertIsNone(result.duty_cycle)
                self.assertIn(AnalysisWarning.SIGNAL_TOO_SMALL, result.warnings)
                self.assertIn(AnalysisWarning.NO_EDGES_DETECTED, result.warnings)

    def test_small_amplitude_noise_is_quality_gated(self) -> None:
        source = random.Random(1234)
        values = tuple(source.uniform(-0.0004, 0.0004) for _ in range(1000))
        result = analyze_waveform(
            waveform_from_values(values, sample_interval=1e-6, voltage_increment=1e-3)
        )
        self.assertIsNone(result.frequency_hz)
        self.assertIsNone(result.duty_cycle)
        self.assertIn(AnalysisWarning.SIGNAL_TOO_SMALL, result.warnings)
        self.assertIs(AnalysisQuality.DEGRADED, result.quality)


class PeriodicAnalysisGoldenTests(unittest.TestCase):
    def test_ideal_10khz_30_percent_square_wave(self) -> None:
        sample_interval = 1e-6
        waveform = square_wave(
            frequency_hz=10_000.0, duty_ratio=0.30,
            sample_interval=sample_interval, duration=1.05e-3,
        )
        result = analyze_waveform(waveform)
        # Frequency tolerance is one microhertz because this deterministic fixture
        # has exactly 100 uniform samples per period and linear edge interpolation.
        self.assertAlmostEqual(10_000.0, result.frequency_hz, delta=1e-6)
        self.assertAlmostEqual(100e-6, result.period_s, delta=1e-15)
        # One sample is 1% of a period; 1.1% bounds edge quantization conservatively.
        self.assertAlmostEqual(0.30, result.duty_cycle.ratio, delta=0.011)
        self.assertIs(AnalysisQuality.GOOD, result.quality)
        self.assertGreaterEqual(result.algorithm.periods_used, 8)

    def test_phase6c_screen_window_contains_two_complete_periods(self) -> None:
        sample_interval = 200e-9
        waveform = square_wave(
            frequency_hz=10_000.0,
            duty_ratio=0.30,
            sample_interval=sample_interval,
            duration=1199 * sample_interval,
            # Equivalent to a -120 us screen start with a rising edge at -100 us.
            phase_seconds=80e-6,
        )
        self.assertEqual(1200, waveform.point_count)
        result = analyze_waveform(waveform)
        # A 200 ns edge quantization step over 100 us permits about 20 Hz at 10 kHz.
        self.assertAlmostEqual(10_000.0, result.frequency_hz, delta=21.0)
        # 200 ns is 0.2% of the period; 0.3 percentage points bounds one edge sample.
        self.assertAlmostEqual(0.30, result.duty_cycle.ratio, delta=0.003)
        self.assertGreaterEqual(result.algorithm.periods_used, 2)

    def test_ideal_1khz_50_percent_square_wave(self) -> None:
        waveform = square_wave(
            frequency_hz=1_000.0, duty_ratio=0.50,
            sample_interval=10e-6, duration=8.2e-3,
        )
        result = analyze_waveform(waveform)
        self.assertAlmostEqual(1_000.0, result.frequency_hz, delta=1e-7)
        # 10 us resolution is 1% of the period; allow 1.1 percentage points.
        self.assertAlmostEqual(0.50, result.duty_cycle.ratio, delta=0.011)

    def test_noisy_square_wave_uses_hysteresis_and_multiple_periods(self) -> None:
        waveform = square_wave(
            frequency_hz=10_000.0, duty_ratio=0.30,
            sample_interval=1e-6, duration=1.2e-3, noise_peak=0.08,
        )
        result = analyze_waveform(waveform)
        # With 1 us sampling, one-sample crossing uncertainty gives 100 Hz at 10 kHz.
        self.assertAlmostEqual(10_000.0, result.frequency_hz, delta=100.0)
        # Two independently interpolated edges permit about 2 samples / period.
        self.assertAlmostEqual(0.30, result.duty_cycle.ratio, delta=0.021)
        self.assertGreater(result.algorithm.hysteresis_band_v, 0.0)

    def test_non_integer_period_count_and_phase_shift_do_not_bias_result(self) -> None:
        for duration, phase in ((735e-6, 0.0), (735e-6, 37e-6)):
            result = analyze_waveform(square_wave(
                frequency_hz=10_000.0, duty_ratio=0.30,
                sample_interval=1e-6, duration=duration, phase_seconds=phase,
            ))
            with self.subTest(phase=phase):
                self.assertAlmostEqual(10_000.0, result.frequency_hz, delta=1e-6)
                self.assertAlmostEqual(0.30, result.duty_cycle.ratio, delta=0.011)

    def test_slightly_jittered_periods_use_robust_median(self) -> None:
        periods = (100e-6, 101e-6, 99e-6, 100e-6, 102e-6, 98e-6)
        result = analyze_waveform(jittered_square_wave(
            periods=periods, duty_ratio=0.30, sample_interval=1e-6,
        ))
        # Median source period is 100 us; 1 us quantization permits 100 Hz.
        self.assertAlmostEqual(10_000.0, result.frequency_hz, delta=100.0)
        self.assertAlmostEqual(0.30, result.duty_cycle.ratio, delta=0.021)

    def test_one_anomalous_crossing_does_not_determine_frequency(self) -> None:
        waveform = square_wave(
            frequency_hz=10_000.0, duty_ratio=0.30,
            sample_interval=1e-6, duration=1.2e-3,
        )
        values = list(waveform.voltage_values)
        # Insert one narrow high pulse into a low interval. It creates one extra
        # rising/falling pair and splits one nominal period into two outliers.
        values[560:563] = (3.3, 3.3, 3.3)
        result = analyze_waveform(replace(waveform, voltage_values=tuple(values)))
        self.assertAlmostEqual(10_000.0, result.frequency_hz, delta=1e-6)
        self.assertGreaterEqual(result.algorithm.periods_used, 8)

    def test_materially_unstable_periods_are_not_reported_as_frequency(self) -> None:
        periods = (80e-6, 120e-6, 80e-6, 120e-6, 80e-6, 120e-6)
        result = analyze_waveform(jittered_square_wave(
            periods=periods, duty_ratio=0.30, sample_interval=1e-6,
        ))
        self.assertIsNone(result.frequency_hz)
        self.assertIsNone(result.period_s)
        self.assertIsNone(result.duty_cycle)
        self.assertIn(AnalysisWarning.UNSTABLE_PERIOD, result.warnings)

    def test_less_than_two_complete_periods_is_not_forced_to_a_frequency(self) -> None:
        result = analyze_waveform(square_wave(
            frequency_hz=10_000.0, duty_ratio=0.30,
            sample_interval=1e-6, duration=190e-6, phase_seconds=5e-6,
        ))
        self.assertIsNone(result.frequency_hz)
        self.assertIsNone(result.period_s)
        self.assertIsNone(result.duty_cycle)
        self.assertIn(AnalysisWarning.INSUFFICIENT_CYCLES, result.warnings)

    def test_clipped_looking_waveform_is_marked_degraded_without_hiding_metrics(self) -> None:
        result = analyze_waveform(clipped_sine_wave(
            frequency_hz=1_000.0, sample_interval=10e-6, duration=8e-3,
        ))
        self.assertIn(AnalysisWarning.CLIPPED_SIGNAL_SUSPECTED, result.warnings)
        self.assertIs(AnalysisQuality.DEGRADED, result.quality)
        self.assertAlmostEqual(1_000.0, result.frequency_hz, delta=20.0)


class TimeAxisAndQualityTests(unittest.TestCase):
    def test_non_increasing_time_axis_invalidates_only_time_metrics(self) -> None:
        values = (0.0, 3.3, 0.0, 3.3, 0.0)
        times = (0.0, 1e-6, 1e-6, 3e-6, 4e-6)
        result = analyze_waveform(waveform_from_values(
            values, sample_interval=1e-6, times=times,
        ))
        self.assertEqual(3.3, result.vpp_v)
        self.assertIsNone(result.frequency_hz)
        self.assertIsNone(result.duty_cycle)
        self.assertIs(AnalysisQuality.INVALID, result.quality)
        self.assertIn(AnalysisWarning.INVALID_TIME_AXIS, result.warnings)

    def test_nonuniform_time_axis_is_rejected_when_uniform_sampling_is_assumed(self) -> None:
        values = tuple(3.3 if index % 4 < 2 else 0.0 for index in range(20))
        times = tuple(index * 1e-6 + (2e-7 if index == 10 else 0.0) for index in range(20))
        result = analyze_waveform(waveform_from_values(
            values, sample_interval=1e-6, times=times,
        ))
        self.assertIsNone(result.frequency_hz)
        self.assertIn(AnalysisWarning.NONUNIFORM_SAMPLING, result.warnings)

    def test_one_sample_reports_insufficient_samples(self) -> None:
        result = analyze_waveform(waveform_from_values((1.0,), sample_interval=1e-6))
        self.assertEqual(0.0, result.vpp_v)
        self.assertIsNone(result.frequency_hz)
        self.assertIn(AnalysisWarning.INSUFFICIENT_SAMPLES, result.warnings)


if __name__ == "__main__":
    unittest.main()
