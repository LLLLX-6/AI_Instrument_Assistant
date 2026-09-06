from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from jsonschema import Draft202012Validator, ValidationError

from ai_instrument_assistant.adapters.artifacts.in_memory import InMemoryArtifactStore
from ai_instrument_assistant.analysis import DeterministicWaveformAnalysisEngine
from ai_instrument_assistant.application.services.measurement import MeasurementService
from ai_instrument_assistant.application.tool_contracts.hardware import (
    serialize_instrument_status,
    serialize_measurement_result,
)
from ai_instrument_assistant.domain.measurement import (
    InstrumentStatus,
    MeasurementKind,
    MeasurementRequest,
)
from tests.support.fake_oscilloscope import FakeOscilloscope
from tests.support.synthetic_waveform import square_wave


ROOT = Path(__file__).resolve().parents[4]
SCHEMA = ROOT / "protocols/hardware/v1/hardware-tool.schema.json"
NOW = datetime(2026, 9, 6, 14, 0, tzinfo=UTC)


class HardwareToolContractTests(unittest.TestCase):
    def test_pwm_result_is_stable_json_and_contains_artifact_reference_not_samples(self) -> None:
        waveform = square_wave(
            frequency_hz=10_000.0,
            duty_ratio=0.3,
            sample_interval=2e-7,
            duration=0.0004,
        )
        service = MeasurementService(
            oscilloscope=FakeOscilloscope(waveform),
            analyzer=DeterministicWaveformAnalysisEngine(),
            artifact_store=InMemoryArtifactStore(),
            clock=lambda: NOW,
        )
        result = service.measure(MeasurementRequest(
            UUID("00000000-0000-4000-8000-000000000621"),
            MeasurementKind.PWM,
            1,
        ))
        payload = serialize_measurement_result(result)
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)
        encoded = json.dumps(payload)
        self.assertNotIn("time_values", encoded)
        self.assertNotIn("voltage_values", encoded)
        self.assertEqual("hardware.measure_pwm", payload["operation"])
        self.assertIn("artifact", payload["result"]["waveform"])

    def test_contract_has_only_semantic_allowlisted_operations(self) -> None:
        schema_text = SCHEMA.read_text(encoding="utf-8")
        for operation in (
            "hardware.get_status",
            "hardware.measure_frequency",
            "hardware.measure_vpp",
            "hardware.capture_waveform",
            "hardware.measure_pwm",
        ):
            self.assertIn(operation, schema_text)
        for forbidden in ("send_scpi", "query_scpi", "visa_resource", "command"):
            self.assertNotIn(forbidden, schema_text)

    def test_status_result_is_schema_valid_and_omits_raw_identity(self) -> None:
        waveform = square_wave(
            frequency_hz=10_000.0,
            duty_ratio=0.3,
            sample_interval=2e-7,
            duration=0.0004,
        )
        payload = serialize_instrument_status(InstrumentStatus(
            identity=waveform.instrument_identity,
            observed_at=NOW,
        ))
        validator = Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
        validator.validate(payload)
        self.assertNotIn("raw_identity", json.dumps(payload))

    def test_schema_rejects_operation_kind_mismatch(self) -> None:
        waveform = square_wave(
            frequency_hz=10_000.0,
            duty_ratio=0.3,
            sample_interval=2e-7,
            duration=0.0004,
        )
        service = MeasurementService(
            oscilloscope=FakeOscilloscope(waveform),
            analyzer=DeterministicWaveformAnalysisEngine(),
            artifact_store=InMemoryArtifactStore(),
            clock=lambda: NOW,
        )
        payload = serialize_measurement_result(service.measure(MeasurementRequest(
            UUID("00000000-0000-4000-8000-000000000622"),
            MeasurementKind.PWM,
            1,
        )))
        payload["operation"] = "hardware.measure_frequency"
        validator = Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
        with self.assertRaises(ValidationError):
            validator.validate(payload)


if __name__ == "__main__":
    unittest.main()
