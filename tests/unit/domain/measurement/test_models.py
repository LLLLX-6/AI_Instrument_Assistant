from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from uuid import UUID

from ai_instrument_assistant.domain.artifacts import ArtifactReference, WaveformArtifact
from ai_instrument_assistant.domain.instrument import InstrumentIdentity
from ai_instrument_assistant.domain.measurement import (
    CoherenceKind,
    MeasurementCoherence,
    MeasurementKind,
    MeasurementObservation,
    MeasurementProvenance,
    MeasurementQuality,
    MeasurementRequest,
    MeasurementResult,
    ObservationQuality,
    ObservationSource,
)
from ai_instrument_assistant.domain.values import DutyCycle


NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
REQUEST_ID = UUID("00000000-0000-4000-8000-000000000601")
ARTIFACT_ID = UUID("00000000-0000-4000-8000-000000000602")
IDENTITY = InstrumentIdentity("RIGOL", "DS1102Z-E", "SERIAL", "1.0")


def artifact() -> WaveformArtifact:
    return WaveformArtifact(
        reference=ArtifactReference(
            artifact_id=ARTIFACT_ID,
            uri=f"memory://waveforms/{ARTIFACT_ID}",
            media_type="application/vnd.aia.waveform",
        ),
        channel=1,
        point_count=1200,
        sample_interval_seconds=2e-7,
        time_start_seconds=-0.00012,
        time_end_seconds=0.0001198,
        minimum_voltage=-0.34,
        maximum_voltage=0.01,
        acquisition_mode="normal",
        captured_at=NOW,
    )


def provenance() -> MeasurementProvenance:
    return MeasurementProvenance(
        instrument_identity=IDENTITY,
        channel=1,
        started_at=NOW,
        completed_at=NOW,
        analysis_algorithm_name="aia.threshold_edges",
        analysis_algorithm_version="1.0.0",
    )


class MeasurementDomainTests(unittest.TestCase):
    def test_request_is_immutable_and_validates_scope(self) -> None:
        request = MeasurementRequest(REQUEST_ID, MeasurementKind.PWM, 1, "eda-42")
        self.assertEqual(1, request.channel)
        with self.assertRaises(FrozenInstanceError):
            request.channel = 2  # type: ignore[misc]
        for invalid in (0, 3, True):
            with self.subTest(invalid=invalid), self.assertRaises((TypeError, ValueError)):
                MeasurementRequest(REQUEST_ID, MeasurementKind.PWM, invalid)  # type: ignore[arg-type]

    def test_observation_requires_explicit_source_method_quality_and_time(self) -> None:
        observation = MeasurementObservation(
            value=DutyCycle.from_ratio(0.3),
            source=ObservationSource.SOFTWARE_ANALYSIS,
            method="aia.threshold_edges/1.0.0",
            observed_at=NOW,
            quality=ObservationQuality.GOOD,
            warnings=(),
            evidence_artifact_ids=(ARTIFACT_ID,),
        )
        self.assertAlmostEqual(30.0, observation.value.percent)
        with self.assertRaises(ValueError):
            MeasurementObservation(
                value=None,
                source=ObservationSource.INSTRUMENT,
                method="oscilloscope.measure_frequency",
                observed_at=NOW,
                quality=ObservationQuality.GOOD,
                warnings=(),
            )

    def test_waveform_artifact_is_summary_not_sample_arrays(self) -> None:
        summary = artifact()
        names = {field.name for field in fields(WaveformArtifact)}
        self.assertNotIn("time_values", names)
        self.assertNotIn("voltage_values", names)
        self.assertEqual(1200, summary.point_count)

    def test_result_is_independent_of_eda_context_and_preserves_sources(self) -> None:
        request = MeasurementRequest(REQUEST_ID, MeasurementKind.PWM, 1)
        instrument = MeasurementObservation(
            10_020.04, ObservationSource.INSTRUMENT,
            "oscilloscope.measure_frequency", NOW, ObservationQuality.GOOD,
        )
        software = MeasurementObservation(
            10_006.77, ObservationSource.SOFTWARE_ANALYSIS,
            "aia.threshold_edges/1.0.0", NOW, ObservationQuality.GOOD,
            evidence_artifact_ids=(ARTIFACT_ID,),
        )
        result = MeasurementResult(
            request=request,
            waveform=artifact(),
            instrument_frequency=instrument,
            software_frequency=software,
            quality=MeasurementQuality.GOOD,
            warnings=(),
            coherence=MeasurementCoherence(
                software_observations=CoherenceKind.SAME_ARTIFACT,
                instrument_vs_software=CoherenceKind.SEQUENTIAL_SAME_SESSION,
            ),
            provenance=provenance(),
        )
        self.assertNotIn("document", {field.name for field in fields(MeasurementResult)})
        self.assertIs(ObservationSource.INSTRUMENT, result.instrument_frequency.source)
        self.assertIs(ObservationSource.SOFTWARE_ANALYSIS, result.software_frequency.source)

    def test_result_rejects_observation_in_wrong_source_slot(self) -> None:
        wrong = MeasurementObservation(
            10_000.0, ObservationSource.SOFTWARE_ANALYSIS, "fixture", NOW,
            ObservationQuality.GOOD,
        )
        with self.assertRaises(ValueError):
            MeasurementResult(
                request=MeasurementRequest(REQUEST_ID, MeasurementKind.FREQUENCY, 1),
                waveform=None,
                instrument_frequency=wrong,
                quality=MeasurementQuality.GOOD,
                warnings=(),
                coherence=MeasurementCoherence.unknown(),
                provenance=provenance(),
            )

    def test_instrument_slot_accepts_explicitly_simulated_adapter_fact(self) -> None:
        simulated = MeasurementObservation(
            10_000.0, ObservationSource.SIMULATED, "simulated.measure_frequency", NOW,
            ObservationQuality.GOOD,
        )
        result = MeasurementResult(
            request=MeasurementRequest(REQUEST_ID, MeasurementKind.FREQUENCY, 1),
            waveform=None,
            instrument_frequency=simulated,
            quality=MeasurementQuality.GOOD,
            warnings=(),
            coherence=MeasurementCoherence.unknown(),
            provenance=provenance(),
        )
        self.assertIs(ObservationSource.SIMULATED, result.instrument_frequency.source)

    def test_coherence_does_not_claim_same_capture_for_sequential_queries(self) -> None:
        coherence = MeasurementCoherence(
            software_observations=CoherenceKind.SAME_ARTIFACT,
            instrument_vs_software=CoherenceKind.SEQUENTIAL_SAME_SESSION,
        )
        self.assertIs(CoherenceKind.SAME_ARTIFACT, coherence.software_observations)
        self.assertIs(
            CoherenceKind.SEQUENTIAL_SAME_SESSION,
            coherence.instrument_vs_software,
        )


if __name__ == "__main__":
    unittest.main()
