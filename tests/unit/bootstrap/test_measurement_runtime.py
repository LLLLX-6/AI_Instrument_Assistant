from __future__ import annotations

import json
import unittest
from pathlib import Path
from uuid import UUID

from jsonschema import Draft202012Validator

from ai_instrument_assistant.bootstrap.hardware import (
    build_ds1102ze_measurement_runtime,
)
from ai_instrument_assistant.domain.measurement import (
    CoherenceKind,
    MeasurementKind,
    MeasurementQuality,
    MeasurementRequest,
    ObservationSource,
)
from ai_instrument_assistant.application.tool_contracts.hardware import (
    serialize_measurement_result,
)
from tests.support.recorded_visa import RecordedVisaConnection, RecordedVisaTransport


ROOT = Path(__file__).resolve().parents[3]
RESOURCE = "USB0::0x1AB1::0x0517::DS1ZE000000001::INSTR"
IDN = "RIGOL TECHNOLOGIES,DS1102Z-E,DS1ZE000000001,00.06.03.SP2"
PREAMBLE = "0,0,1200,1,2e-7,-0.00012,0,0.002,0,127"


def pwm_payload() -> bytes:
    values = []
    for index in range(1200):
        if index < 50:
            high = False
        else:
            high = (index - 50) % 500 < 150
        values.append(220 if high else 20)
    return bytes(values)


def block(payload: bytes) -> bytes:
    length = str(len(payload)).encode("ascii")
    return b"#" + str(len(length)).encode("ascii") + length + payload + b"\n"


def recorded_runtime():
    connection = RecordedVisaConnection(
        responses={
            "*IDN?": IDN,
            ":WAVeform:SOURce?": "CHAN1",
            ":WAVeform:MODE?": "NORM",
            ":WAVeform:FORMat?": "BYTE",
            ":WAVeform:STARt?": "1",
            ":WAVeform:STOP?": "1200",
            ":WAVeform:PREamble?": PREAMBLE,
            ":MEASure:ITEM? FREQuency,CHANnel1": "10020.04",
            ":MEASure:ITEM? VPP,CHANnel1": "0.424",
        },
        raw_response=block(pwm_payload()),
    )
    runtime = build_ds1102ze_measurement_runtime(
        RESOURCE,
        timeout_seconds=3.0,
        transport=RecordedVisaTransport(connection, (RESOURCE,)),
    )
    return runtime, connection


class MeasurementRuntimeTests(unittest.TestCase):
    def test_real_composition_uses_driver_service_analysis_and_artifact_store(self) -> None:
        runtime, connection = recorded_runtime()
        with runtime:
            status = runtime.service.get_status()
            result = runtime.service.measure(MeasurementRequest(
                UUID("00000000-0000-4000-8000-0000000006f1"),
                MeasurementKind.PWM,
                1,
            ))
            stored = runtime.artifact_store.get(result.waveform.reference)

        self.assertEqual("DS1102Z-E", status.identity.model)
        self.assertEqual(10_020.04, result.instrument_frequency.value)
        self.assertAlmostEqual(10_000.0, result.software_frequency.value, delta=21.0)
        self.assertAlmostEqual(30.0, result.software_duty_cycle.value.percent, delta=0.3)
        self.assertIs(ObservationSource.INSTRUMENT, result.instrument_frequency.source)
        self.assertIs(ObservationSource.SOFTWARE_ANALYSIS, result.software_frequency.source)
        self.assertIs(MeasurementQuality.GOOD, result.quality)
        self.assertIsNotNone(stored)
        self.assertTrue(connection.closed)

    def test_real_composition_preserves_execution_order_and_coherence(self) -> None:
        runtime, connection = recorded_runtime()
        with runtime:
            result = runtime.service.measure(MeasurementRequest(
                UUID("00000000-0000-4000-8000-0000000006f2"),
                MeasurementKind.PWM,
                1,
            ))
        calls = connection.calls
        waveform_read = calls.index(("read_raw", ""))
        frequency_query = calls.index(("query", ":MEASure:ITEM? FREQuency,CHANnel1"))
        vpp_query = calls.index(("query", ":MEASure:ITEM? VPP,CHANnel1"))
        self.assertLess(waveform_read, frequency_query)
        self.assertLess(frequency_query, vpp_query)
        self.assertIs(CoherenceKind.SAME_ARTIFACT, result.coherence.software_observations)
        self.assertIs(
            CoherenceKind.SEQUENTIAL_SAME_SESSION,
            result.coherence.instrument_vs_software,
        )

    def test_real_composition_artifact_round_trip_and_tool_schema(self) -> None:
        runtime, _ = recorded_runtime()
        with runtime:
            result = runtime.service.measure(MeasurementRequest(
                UUID("00000000-0000-4000-8000-0000000006f3"),
                MeasurementKind.PWM,
                1,
            ))
            stored = runtime.artifact_store.get(result.waveform.reference)
            self.assertEqual(result.waveform.point_count, stored.point_count)
            self.assertEqual(
                result.waveform.sample_interval_seconds,
                stored.sample_interval_seconds,
            )
            self.assertEqual(result.waveform.channel, stored.channel)

        payload = serialize_measurement_result(result)
        schema = json.loads((
            ROOT / "protocols/hardware/v1/hardware-tool.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(payload)
        encoded = json.dumps(payload)
        self.assertNotIn("time_values", encoded)
        self.assertNotIn("voltage_values", encoded)


if __name__ == "__main__":
    unittest.main()
