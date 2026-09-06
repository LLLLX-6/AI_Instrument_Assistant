from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

from ai_instrument_assistant.analysis.models import (
    AnalysisAlgorithmMetadata,
    AnalysisQuality,
    AnalysisWarning,
    WaveformAnalysisResult,
    WaveformProvenance,
)
from ai_instrument_assistant.domain.eda.models import DutyCycle as EdaDutyCycle
from ai_instrument_assistant.domain.values import DutyCycle
from tests.support.synthetic_waveform import SYNTHETIC_IDENTITY


class AnalysisResultModelTests(unittest.TestCase):
    def test_duty_cycle_is_one_shared_domain_value_object(self) -> None:
        self.assertIs(DutyCycle, EdaDutyCycle)
        self.assertAlmostEqual(0.3, DutyCycle.from_percent(30).ratio)

    def test_result_is_immutable_structured_and_carries_provenance(self) -> None:
        provenance = WaveformProvenance(
            instrument_identity=SYNTHETIC_IDENTITY,
            channel=1,
            captured_at=datetime(2026, 9, 6, tzinfo=UTC),
            point_count=1001,
            sample_interval_seconds=1e-6,
            acquisition_mode="normal",
        )
        metadata = AnalysisAlgorithmMetadata(
            name="aia.threshold_edges",
            version="1.0.0",
            threshold_strategy="midpoint(min,max)",
            threshold_v=1.65,
            hysteresis_strategy="symmetric_10_percent_amplitude",
            hysteresis_band_v=0.33,
            rising_edge_count=10,
            falling_edge_count=10,
            periods_used=9,
            duty_cycles_used=9,
        )
        result = WaveformAnalysisResult(
            vpp_v=3.3,
            mean_v=0.99,
            rms_v=1.807,
            frequency_hz=10_000.0,
            period_s=100e-6,
            duty_cycle=DutyCycle.from_ratio(0.3),
            quality=AnalysisQuality.GOOD,
            warnings=(),
            algorithm=metadata,
            waveform=provenance,
        )
        self.assertEqual(30.0, result.duty_cycle.percent)
        with self.assertRaises(FrozenInstanceError):
            result.vpp_v = 0.0  # type: ignore[misc]

    def test_result_rejects_partial_frequency_and_duplicate_warnings(self) -> None:
        provenance = WaveformProvenance(
            SYNTHETIC_IDENTITY, 1, datetime(2026, 9, 6, tzinfo=UTC),
            3, 1e-6, "normal",
        )
        metadata = AnalysisAlgorithmMetadata(
            "aia.threshold_edges", "1.0.0", "midpoint(min,max)", 0.0,
            "symmetric_10_percent_amplitude", 0.0, 0, 0, 0, 0,
        )
        with self.assertRaises(ValueError):
            WaveformAnalysisResult(
                1.0, 0.0, 0.5, 100.0, None, None,
                AnalysisQuality.DEGRADED, (), metadata, provenance,
            )
        with self.assertRaises(ValueError):
            WaveformAnalysisResult(
                1.0, 0.0, 0.5, None, None, None,
                AnalysisQuality.DEGRADED,
                (AnalysisWarning.INSUFFICIENT_CYCLES, AnalysisWarning.INSUFFICIENT_CYCLES),
                metadata, provenance,
            )


if __name__ == "__main__":
    unittest.main()
