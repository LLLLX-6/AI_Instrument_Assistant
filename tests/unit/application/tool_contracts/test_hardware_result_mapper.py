from __future__ import annotations

import copy
import unittest

from ai_instrument_assistant.application.tool_contracts.hardware_result_mapper import (
    CanonicalMeasurementMappingError,
    CanonicalMeasurementResultMapper,
)
from ai_instrument_assistant.domain.measurement import (
    MeasurementKind,
    MeasurementQuality,
    ObservationQuality,
    ObservationSource,
)


def canonical(operation: str, kind: str, channel: int, value: float, source: str = "instrument") -> dict:
    observation_name = "instrument_frequency" if kind == "frequency" else "instrument_vpp"
    observation = {
        "value": value,
        "method": "oscilloscope measurement query",
        "observed_at": "2026-09-13T10:00:00Z",
        "quality": "good",
        "warnings": [],
        "evidence_artifact_ids": [],
    }
    if source is not None:
        observation["source"] = source
    return {
        "contract_version": "1.0",
        "ok": True,
        "operation": operation,
        "result": {
            "request_id": f"00000000-0000-4000-8000-0000000000{channel}{1 if kind == 'frequency' else 2}",
            "kind": kind,
            "channel": channel,
            "context_id": f"RE-001-{channel}",
            "instrument": {
                "manufacturer": "RIGOL TECHNOLOGIES",
                "model": "DS1102Z-E",
                "serial_number": "***0001",
                "firmware_version": "test",
            },
            "waveform": None,
            "observations": {
                observation_name: observation
            },
            "quality": "good",
            "warnings": [],
            "coherence": {
                "software_observations": "unknown",
                "instrument_vs_software": "unknown",
            },
            "provenance": {
                "started_at": "2026-09-13T10:00:00Z",
                "completed_at": "2026-09-13T10:00:01Z",
                "analysis_algorithm": None,
            },
        },
    }


class CanonicalMeasurementResultMapperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mapper = CanonicalMeasurementResultMapper()

    def test_maps_frequency_and_vpp_for_both_channels_as_instrument_evidence(self) -> None:
        cases = (
            ("hardware.measure_frequency", MeasurementKind.FREQUENCY, 1, 100.0),
            ("hardware.measure_vpp", MeasurementKind.VPP, 1, 3.3),
            ("hardware.measure_frequency", MeasurementKind.FREQUENCY, 2, 100.1),
            ("hardware.measure_vpp", MeasurementKind.VPP, 2, 2.2),
        )
        for operation, kind, channel, value in cases:
            with self.subTest(operation=operation, channel=channel):
                result = self.mapper.map_success(
                    canonical(operation, kind.value, channel, value),
                    expected_operation=operation,
                    expected_channel=channel,
                )
                self.assertIs(result.request.kind, kind)
                self.assertEqual(channel, result.request.channel)
                observation = result.instrument_frequency if kind is MeasurementKind.FREQUENCY else result.instrument_vpp
                self.assertEqual(value, observation.value)
                self.assertIs(observation.source, ObservationSource.INSTRUMENT)

    def test_rejects_wrong_channel_kind_malformed_and_non_finite_values(self) -> None:
        base = canonical("hardware.measure_frequency", "frequency", 1, 100.0)
        mutations = []
        wrong_channel = copy.deepcopy(base); wrong_channel["result"]["channel"] = 2; mutations.append(wrong_channel)
        wrong_kind = copy.deepcopy(base); wrong_kind["operation"] = "hardware.measure_vpp"; wrong_kind["result"]["kind"] = "vpp"; mutations.append(wrong_kind)
        malformed = copy.deepcopy(base); del malformed["result"]["instrument"]; mutations.append(malformed)
        non_finite = copy.deepcopy(base); non_finite["result"]["observations"]["instrument_frequency"]["value"] = float("nan"); mutations.append(non_finite)
        for payload in mutations:
            with self.subTest(payload=payload):
                with self.assertRaises(CanonicalMeasurementMappingError):
                    self.mapper.map_success(
                        payload,
                        expected_operation="hardware.measure_frequency",
                        expected_channel=1,
                    )

    def test_maps_simulated_backend_observation_preserving_simulated_provenance(self) -> None:
        cases = (
            ("hardware.measure_frequency", MeasurementKind.FREQUENCY, 1, 10000.0),
            ("hardware.measure_vpp", MeasurementKind.VPP, 1, 3.3),
            ("hardware.measure_frequency", MeasurementKind.FREQUENCY, 2, 10000.0),
            ("hardware.measure_vpp", MeasurementKind.VPP, 2, 3.3),
        )
        for operation, kind, channel, value in cases:
            with self.subTest(operation=operation, channel=channel):
                result = self.mapper.map_success(
                    canonical(operation, kind.value, channel, value, source="simulated"),
                    expected_operation=operation,
                    expected_channel=channel,
                )
                observation = result.instrument_frequency if kind is MeasurementKind.FREQUENCY else result.instrument_vpp
                self.assertEqual(value, observation.value)
                self.assertIs(observation.source, ObservationSource.SIMULATED)

    def test_unknown_observation_sources_fail_closed(self) -> None:
        # Unknown sources are rejected by the canonical Hardware schema before
        # the mapper runs; the rejection is still a bounded mapping error.
        for source in ("model", "user", "analysis", "unknown", "", "instrument "):
            with self.subTest(source=source):
                with self.assertRaises(CanonicalMeasurementMappingError):
                    self.mapper.map_success(
                        canonical("hardware.measure_frequency", "frequency", 1, 100.0, source=source),
                        expected_operation="hardware.measure_frequency",
                        expected_channel=1,
                    )

    def test_schema_valid_non_measurement_source_fails_closed_in_mapper(self) -> None:
        # "software_analysis" passes the transport schema but is not a valid
        # provenance for a frequency/Vpp measurement observation; the mapper's
        # own allowlist must reject it explicitly.
        with self.assertRaisesRegex(CanonicalMeasurementMappingError, "observation_source_invalid"):
            self.mapper.map_success(
                canonical("hardware.measure_frequency", "frequency", 1, 100.0, source="software_analysis"),
                expected_operation="hardware.measure_frequency",
                expected_channel=1,
                )

    def test_missing_observation_source_fails_closed(self) -> None:
        with self.assertRaises(CanonicalMeasurementMappingError):
            self.mapper.map_success(
                canonical("hardware.measure_frequency", "frequency", 1, 100.0, source=None),
                expected_operation="hardware.measure_frequency",
                expected_channel=1,
            )

    def test_schema_valid_ok_false_is_a_typed_failure_not_transport_exception(self) -> None:
        failure = self.mapper.map_failure(
            {
                "contract_version": "1.0",
                "ok": False,
                "operation": "hardware.measure_vpp",
                "error": {
                    "code": "measurement_failed",
                    "message": "Measurement could not be completed.",
                    "details": {},
                },
            },
            expected_operation="hardware.measure_vpp",
            expected_channel=2,
        )
        self.assertIs(failure.quality, MeasurementQuality.FAILED)
        self.assertIs(failure.observation_quality, ObservationQuality.UNAVAILABLE)
        self.assertEqual("measurement_failed", failure.error_code)
        self.assertEqual(2, failure.channel)


if __name__ == "__main__":
    unittest.main()
