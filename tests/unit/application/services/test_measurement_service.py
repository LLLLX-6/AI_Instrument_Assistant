from __future__ import annotations

import unittest
from datetime import UTC, datetime
from uuid import UUID

from ai_instrument_assistant.adapters.artifacts.in_memory import InMemoryArtifactStore
from ai_instrument_assistant.analysis import DeterministicWaveformAnalysisEngine
from ai_instrument_assistant.application.services.measurement import MeasurementService
from ai_instrument_assistant.domain.measurement import (
    CoherenceKind,
    MeasurementKind,
    MeasurementQuality,
    MeasurementRequest,
    ObservationQuality,
    ObservationSource,
)
from tests.support.fake_oscilloscope import FakeOscilloscope
from tests.support.synthetic_waveform import square_wave


NOW = datetime(2026, 9, 6, 13, 0, tzinfo=UTC)
REQUEST_ID = UUID("00000000-0000-4000-8000-000000000611")


def request(kind: MeasurementKind, channel: int = 1) -> MeasurementRequest:
    return MeasurementRequest(REQUEST_ID, kind, channel, "test-correlation")


def service_for(*, duration: float = 0.0004):
    waveform = square_wave(
        frequency_hz=10_000.0,
        duty_ratio=0.3,
        sample_interval=2e-7,
        duration=duration,
        low=-0.34,
        high=0.01,
    )
    scope = FakeOscilloscope(waveform)
    store = InMemoryArtifactStore(id_factory=lambda: UUID(
        "00000000-0000-4000-8000-000000000612"
    ))
    service = MeasurementService(
        oscilloscope=scope,
        analyzer=DeterministicWaveformAnalysisEngine(),
        artifact_store=store,
        clock=lambda: NOW,
    )
    return service, scope, store


class MeasurementServiceTests(unittest.TestCase):
    def test_frequency_request_returns_instrument_observation(self) -> None:
        service, scope, _ = service_for()
        result = service.measure(request(MeasurementKind.FREQUENCY))
        self.assertEqual(10_020.04, result.instrument_frequency.value)
        self.assertIs(ObservationSource.INSTRUMENT, result.instrument_frequency.source)
        self.assertEqual(["get_identity", "measure_frequency"], scope.calls)

    def test_vpp_request_returns_instrument_observation(self) -> None:
        service, scope, _ = service_for()
        result = service.measure(request(MeasurementKind.VPP))
        self.assertEqual(0.424, result.instrument_vpp.value)
        self.assertEqual(["get_identity", "measure_vpp"], scope.calls)

    def test_waveform_request_stores_artifact_not_arrays(self) -> None:
        service, _, store = service_for()
        result = service.measure(request(MeasurementKind.WAVEFORM))
        self.assertEqual(2001, result.waveform.point_count)
        self.assertIsNotNone(store.get(result.waveform.reference))
        self.assertIs(MeasurementQuality.GOOD, result.quality)

    def test_pwm_combines_software_and_instrument_evidence_without_merging(self) -> None:
        service, scope, _ = service_for()
        result = service.measure(request(MeasurementKind.PWM))
        self.assertAlmostEqual(10_000.0, result.software_frequency.value, delta=21.0)
        self.assertAlmostEqual(30.0, result.software_duty_cycle.value.percent, delta=0.3)
        self.assertAlmostEqual(0.35, result.software_vpp.value, places=9)
        self.assertEqual(10_020.04, result.instrument_frequency.value)
        self.assertEqual(0.424, result.instrument_vpp.value)
        self.assertEqual(
            ["get_identity", "capture_waveform", "measure_frequency", "measure_vpp"],
            scope.calls,
        )

    def test_pwm_marks_software_same_artifact_and_cross_source_sequential(self) -> None:
        service, _, _ = service_for()
        result = service.measure(request(MeasurementKind.PWM))
        self.assertIs(CoherenceKind.SAME_ARTIFACT, result.coherence.software_observations)
        self.assertIs(
            CoherenceKind.SEQUENTIAL_SAME_SESSION,
            result.coherence.instrument_vs_software,
        )
        artifact_id = result.waveform.reference.artifact_id
        self.assertEqual((artifact_id,), result.software_frequency.evidence_artifact_ids)
        self.assertEqual((artifact_id,), result.software_duty_cycle.evidence_artifact_ids)

    def test_frequency_failure_preserves_software_pwm_result_as_partial(self) -> None:
        service, scope, _ = service_for()
        scope.fail_frequency = True
        result = service.measure(request(MeasurementKind.PWM))
        self.assertIsNone(result.instrument_frequency.value)
        self.assertIs(ObservationQuality.UNAVAILABLE, result.instrument_frequency.quality)
        self.assertIsNotNone(result.software_frequency.value)
        self.assertIs(MeasurementQuality.DEGRADED, result.quality)
        self.assertIn("instrument_frequency_unavailable", result.warnings)

    def test_vpp_failure_preserves_software_pwm_result_as_partial(self) -> None:
        service, scope, _ = service_for()
        scope.fail_vpp = True
        result = service.measure(request(MeasurementKind.PWM))
        self.assertIsNone(result.instrument_vpp.value)
        self.assertIsNotNone(result.software_vpp.value)
        self.assertIs(MeasurementQuality.DEGRADED, result.quality)

    def test_waveform_failure_returns_structured_failure_without_queries(self) -> None:
        service, scope, _ = service_for()
        scope.fail_waveform = True
        result = service.measure(request(MeasurementKind.PWM))
        self.assertIsNone(result.waveform)
        self.assertIsNone(result.software_frequency.value)
        self.assertIs(ObservationQuality.UNAVAILABLE, result.software_frequency.quality)
        self.assertIs(MeasurementQuality.FAILED, result.quality)
        self.assertNotIn("measure_frequency", scope.calls)
        self.assertNotIn("measure_vpp", scope.calls)

    def test_insufficient_cycles_preserves_statistics_and_propagates_warnings(self) -> None:
        service, _, _ = service_for(duration=0.00015)
        result = service.measure(request(MeasurementKind.PWM))
        self.assertIsNone(result.software_frequency.value)
        self.assertIsNotNone(result.software_vpp.value)
        self.assertIn("insufficient_cycles", result.warnings)
        self.assertIs(MeasurementQuality.DEGRADED, result.quality)

    def test_provenance_tracks_instrument_channel_algorithm_and_artifact_metadata(self) -> None:
        service, scope, _ = service_for()
        result = service.measure(request(MeasurementKind.PWM, channel=2))
        self.assertIs(scope.identity, result.provenance.instrument_identity)
        self.assertEqual(2, result.provenance.channel)
        self.assertEqual("aia.threshold_edges", result.provenance.analysis_algorithm_name)
        self.assertEqual("1.0.0", result.provenance.analysis_algorithm_version)
        self.assertEqual("normal", result.waveform.acquisition_mode)
        self.assertGreater(result.waveform.point_count, 0)

    def test_status_is_a_timestamped_identity_fact(self) -> None:
        service, scope, _ = service_for()
        status = service.get_status()
        self.assertIs(scope.identity, status.identity)
        self.assertEqual(NOW, status.observed_at)


if __name__ == "__main__":
    unittest.main()
