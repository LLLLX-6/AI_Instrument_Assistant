from __future__ import annotations

import unittest
from datetime import UTC, datetime
from uuid import UUID

from ai_instrument_assistant.adapters.artifacts import InMemoryArtifactStore
from ai_instrument_assistant.analysis import DeterministicWaveformAnalysisEngine
from ai_instrument_assistant.application.services import MeasurementService
from ai_instrument_assistant.domain.measurement import (
    MeasurementKind,
    MeasurementQuality,
    MeasurementRequest,
)
from tests.support.fake_oscilloscope import FakeOscilloscope
from tests.support.fault_injecting_oscilloscope import FaultInjectingOscilloscope
from tests.support.synthetic_waveform import square_wave


NOW = datetime(2026, 9, 6, 15, 0, tzinfo=UTC)


def run_with_fault(**fault):
    delegate = FakeOscilloscope(square_wave(
        frequency_hz=10_000.0,
        duty_ratio=0.3,
        sample_interval=2e-7,
        duration=0.0004,
    ))
    service = MeasurementService(
        oscilloscope=FaultInjectingOscilloscope(delegate, **fault),
        analyzer=DeterministicWaveformAnalysisEngine(),
        artifact_store=InMemoryArtifactStore(),
        clock=lambda: NOW,
    )
    return service.measure(MeasurementRequest(
        UUID("00000000-0000-4000-8000-0000000006f4"),
        MeasurementKind.PWM,
        1,
    ))


class RecordedBoundaryPartialResultTests(unittest.TestCase):
    def test_frequency_fault_keeps_waveform_and_software_evidence(self) -> None:
        result = run_with_fault(fail_frequency=True)
        self.assertIsNotNone(result.waveform)
        self.assertIsNotNone(result.software_frequency.value)
        self.assertIsNotNone(result.software_vpp.value)
        self.assertIsNotNone(result.software_duty_cycle.value)
        self.assertIsNone(result.instrument_frequency.value)
        self.assertIs(MeasurementQuality.DEGRADED, result.quality)

    def test_vpp_fault_keeps_other_evidence(self) -> None:
        result = run_with_fault(fail_vpp=True)
        self.assertIsNone(result.instrument_vpp.value)
        self.assertIsNotNone(result.instrument_frequency.value)
        self.assertIsNotNone(result.software_vpp.value)
        self.assertIs(MeasurementQuality.DEGRADED, result.quality)

    def test_waveform_fault_never_fabricates_software_metrics(self) -> None:
        result = run_with_fault(fail_waveform=True)
        self.assertIsNone(result.waveform)
        self.assertIsNone(result.software_frequency.value)
        self.assertIsNone(result.software_duty_cycle.value)
        self.assertIsNone(result.software_vpp.value)
        self.assertIs(MeasurementQuality.FAILED, result.quality)


if __name__ == "__main__":
    unittest.main()
