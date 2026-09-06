from __future__ import annotations

import json
import threading
import time
import unittest
from unittest.mock import Mock
from uuid import UUID

from ai_instrument_assistant.adapters.instruments.simulated import SimulatedOscilloscope
from ai_instrument_assistant.adapters.artifacts import InMemoryArtifactStore
from ai_instrument_assistant.analysis import DeterministicWaveformAnalysisEngine
from ai_instrument_assistant.application.services import MeasurementService
from ai_instrument_assistant.application.services import (
    AnalysisFailedError,
    ArtifactUnavailableError,
)
from ai_instrument_assistant.application.tool_runtime.hardware import HardwareToolRuntime
from ai_instrument_assistant.domain.instrument import (
    InstrumentCommandError,
    InstrumentConnectionError,
    InstrumentDisconnectedError,
    InstrumentIdentityMismatchError,
    WaveformAcquisitionError,
)
from ai_instrument_assistant.domain.measurement import ObservationSource
from ai_instrument_assistant.protocol.hardware import HardwareToolContractValidator
from tests.support.fault_injecting_oscilloscope import FaultInjectingOscilloscope


IDS = iter(UUID(f"00000000-0000-4000-8000-{value:012d}") for value in range(700, 800))


def request(operation: str, channel: int | None = 1) -> dict:
    arguments = {} if channel is None else {"channel": channel}
    return {"contract_version": "1.0", "operation": operation, "arguments": arguments}


def runtime_with_scope(scope=None) -> HardwareToolRuntime:
    if scope is None:
        scope = SimulatedOscilloscope()
    scope.connect()
    service = MeasurementService(
        oscilloscope=scope,
        analyzer=DeterministicWaveformAnalysisEngine(),
        artifact_store=InMemoryArtifactStore(id_factory=lambda: next(IDS)),
        instrument_observation_source=ObservationSource.SIMULATED,
    )
    return HardwareToolRuntime(
        service,
        HardwareToolContractValidator(),
        id_factory=lambda: next(IDS),
    )


class HardwareToolRuntimeTests(unittest.TestCase):
    def test_static_allowlist_executes_exactly_five_operations(self) -> None:
        runtime = runtime_with_scope()
        operations = (
            ("hardware.get_status", None),
            ("hardware.measure_frequency", 1),
            ("hardware.measure_vpp", 1),
            ("hardware.capture_waveform", 1),
            ("hardware.measure_pwm", 1),
        )
        for operation, channel in operations:
            with self.subTest(operation=operation):
                response = runtime.execute(request(operation, channel))
                self.assertTrue(response["ok"], response)
                self.assertEqual(operation, response["operation"])
                HardwareToolContractValidator().validate_runtime_response(response)

    def test_ch1_and_ch2_use_the_same_contract(self) -> None:
        runtime = runtime_with_scope()
        for channel in (1, 2):
            response = runtime.execute(request("hardware.measure_pwm", channel))
            self.assertTrue(response["ok"])
            self.assertEqual(channel, response["result"]["channel"])

    def test_fake_instrument_observations_are_simulated_never_instrument(self) -> None:
        response = runtime_with_scope().execute(request("hardware.measure_pwm"))
        observations = response["result"]["observations"]
        self.assertEqual("simulated", observations["instrument_frequency"]["source"])
        self.assertEqual("simulated", observations["instrument_vpp"]["source"])
        self.assertEqual("software_analysis", observations["software_frequency"]["source"])

    def test_invalid_requests_are_rejected_before_service_side_effects(self) -> None:
        service = Mock()
        runtime = HardwareToolRuntime(service, HardwareToolContractValidator())
        invalid = (
            {},
            request("hardware.measure_pwm", 3),
            {**request("hardware.measure_pwm"), "extra": True},
            {**request("hardware.measure_pwm"), "kind": "frequency"},
        )
        for payload in invalid:
            with self.subTest(payload=payload):
                response = runtime.execute(payload)
                self.assertFalse(response["ok"])
                self.assertEqual("invalid_request", response["error"]["code"])
        service.assert_not_called()
        self.assertFalse(service.method_calls)

    def test_unknown_operation_is_structured_and_never_dispatched(self) -> None:
        service = Mock()
        runtime = HardwareToolRuntime(service, HardwareToolContractValidator())
        response = runtime.execute(request("hardware.send_scpi"))
        self.assertFalse(response["ok"])
        self.assertEqual("unsupported_operation", response["error"]["code"])
        self.assertFalse(service.method_calls)

    def test_partial_pwm_is_successful_degraded_result(self) -> None:
        scope = FaultInjectingOscilloscope(
            SimulatedOscilloscope(), fail_frequency=True
        )
        response = runtime_with_scope(scope).execute(request("hardware.measure_pwm"))
        self.assertTrue(response["ok"])
        self.assertEqual("degraded", response["result"]["quality"])
        self.assertIsNone(
            response["result"]["observations"]["instrument_frequency"]["value"]
        )
        self.assertIsNotNone(
            response["result"]["observations"]["software_frequency"]["value"]
        )

    def test_waveform_failure_maps_to_stable_error_without_backend_details(self) -> None:
        scope = FaultInjectingOscilloscope(
            SimulatedOscilloscope(), fail_waveform=True
        )
        response = runtime_with_scope(scope).execute(request("hardware.measure_pwm"))
        self.assertFalse(response["ok"])
        self.assertEqual("waveform_acquisition_failed", response["error"]["code"])
        encoded = json.dumps(response)
        self.assertNotIn("SCPI", encoded.upper())
        self.assertNotIn("VisaIOError", encoded)

    def test_internal_exception_is_bounded_and_does_not_leak(self) -> None:
        service = Mock()
        service.get_status.side_effect = RuntimeError("secret backend stack detail")
        runtime = HardwareToolRuntime(service, HardwareToolContractValidator())
        response = runtime.execute(request("hardware.get_status", None))
        self.assertEqual("internal_error", response["error"]["code"])
        self.assertNotIn("secret backend", json.dumps(response))

    def test_typed_failures_map_to_the_stable_error_taxonomy(self) -> None:
        cases = (
            (InstrumentDisconnectedError("raw"), "hardware_unavailable"),
            (InstrumentConnectionError("raw"), "instrument_connection_failed"),
            (InstrumentIdentityMismatchError("raw"), "instrument_identity_mismatch"),
            (InstrumentCommandError("raw SCPI :BAD"), "measurement_failed"),
            (WaveformAcquisitionError("raw SCPI :WAV?"), "waveform_acquisition_failed"),
            (AnalysisFailedError("raw algorithm"), "analysis_failed"),
            (ArtifactUnavailableError("C:\\secret\\waveform"), "artifact_unavailable"),
        )
        for failure, expected in cases:
            with self.subTest(expected=expected):
                service = Mock()
                service.get_status.side_effect = failure
                response = HardwareToolRuntime(
                    service, HardwareToolContractValidator()
                ).execute(request("hardware.get_status", None))
                self.assertEqual(expected, response["error"]["code"])
                encoded = json.dumps(response)
                self.assertNotIn("SCPI", encoded)
                self.assertNotIn("secret", encoded)

    def test_success_is_json_safe_and_contains_no_resource_or_sample_arrays(self) -> None:
        response = runtime_with_scope().execute(request("hardware.measure_pwm"))
        encoded = json.dumps(response, sort_keys=True)
        self.assertEqual(encoded, json.dumps(json.loads(encoded), sort_keys=True))
        self.assertNotIn("USB0::", encoded)
        self.assertNotIn("time_values", encoded)
        self.assertNotIn("voltage_values", encoded)

    def test_repeated_measurements_are_not_cached_or_idempotently_replayed(self) -> None:
        runtime = runtime_with_scope()
        first = runtime.execute(request("hardware.capture_waveform"))
        second = runtime.execute(request("hardware.capture_waveform"))
        self.assertNotEqual(first["result"]["request_id"], second["result"]["request_id"])
        self.assertNotEqual(
            first["result"]["waveform"]["artifact"]["artifact_id"],
            second["result"]["waveform"]["artifact"]["artifact_id"],
        )

    def test_runtime_serializes_concurrent_workflows(self) -> None:
        class SerialProbeService:
            def __init__(self) -> None:
                self.active = 0
                self.maximum_active = 0
                self.lock = threading.Lock()

            def measure(self, value):
                with self.lock:
                    self.active += 1
                    self.maximum_active = max(self.maximum_active, self.active)
                time.sleep(0.02)
                with self.lock:
                    self.active -= 1
                raise InstrumentCommandError("controlled completion")

        service = SerialProbeService()
        runtime = HardwareToolRuntime(service, HardwareToolContractValidator())
        threads = [threading.Thread(
            target=runtime.execute,
            args=(request("hardware.measure_frequency"),),
        ) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(1, service.maximum_active)


if __name__ == "__main__":
    unittest.main()
