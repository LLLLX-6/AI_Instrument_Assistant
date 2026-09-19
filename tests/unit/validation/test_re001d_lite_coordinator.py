from __future__ import annotations

import json
import unittest
from pathlib import Path

from ai_instrument_assistant.application.reasoning.publication import (
    EgressDecision,
    GovernedPublicationBoundary,
    OneShotPublicationCoordinator,
    StructuredCandidateOutcome,
)
from ai_instrument_assistant.domain.engineering_evidence import TeachingEvidenceSource
from ai_instrument_assistant.protocol.teaching_claims import StrictCandidateParser
from validation.support.re001d_lite import (
    RE001DIntentError,
    RE001DLiteCoordinator,
)


ROOT = Path(__file__).resolve().parents[3]


def canonical(operation: str, channel: int, value: float) -> dict:
    kind = "frequency" if operation.endswith("frequency") else "vpp"
    observation_name = "instrument_frequency" if kind == "frequency" else "instrument_vpp"
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
                "serial_number": "SYNTHETIC",
                "firmware_version": "00.06.03.SP2",
            },
            "waveform": None,
            "observations": {
                observation_name: {
                    "value": value,
                    "source": "instrument",
                    "method": "oscilloscope measurement query",
                    "observed_at": "2026-09-14T08:00:00Z",
                    "quality": "good",
                    "warnings": [],
                    "evidence_artifact_ids": [],
                }
            },
            "quality": "good",
            "warnings": [],
            "coherence": {
                "software_observations": "unknown",
                "instrument_vs_software": "unknown",
            },
            "provenance": {
                "started_at": "2026-09-14T08:00:00Z",
                "completed_at": "2026-09-14T08:00:01Z",
                "analysis_algorithm": None,
            },
        },
    }


def receipt(values=(10020.04, 0.34, 10020.04, 3.24)) -> dict:
    bindings = (
        ("hardware.measure_frequency", 1),
        ("hardware.measure_vpp", 1),
        ("hardware.measure_frequency", 2),
        ("hardware.measure_vpp", 2),
    )
    return {
        "contract": "aia-re001c-lite-validation",
        "contract_version": "1.0",
        "kind": "governed_measurement_receipt",
        "status": "COMPLETED",
        "operations": [
            {
                "operation": operation,
                "channel": channel,
                "scope_remaining_invocations": 0,
                "policy_reason": "allowed_confirmed_physical_setup",
                "ipc_dispatch_count": 1,
                "hardware_execution_count": 1,
                "canonical_result": canonical(operation, channel, value),
                "failure_code": None,
            }
            for (operation, channel), value in zip(bindings, values, strict=True)
        ],
        "failure_code": None,
    }


def simulated_backend_canonical(operation: str, channel: int, value: float) -> dict:
    """A canonical result exactly as the real FAKE backend emits it."""
    kind = "frequency" if operation.endswith("frequency") else "vpp"
    observation_name = "instrument_frequency" if kind == "frequency" else "instrument_vpp"
    return {
        "contract_version": "1.0",
        "ok": True,
        "operation": operation,
        "result": {
            "request_id": f"00000000-0000-4000-8000-0000000000{channel}{1 if kind == 'frequency' else 2}",
            "kind": kind,
            "channel": channel,
            "context_id": None,
            "instrument": {
                "manufacturer": "AI Instrument Assistant",
                "model": "Simulated Oscilloscope",
                "serial_number": "***ATED",
                "firmware_version": "1.0",
            },
            "waveform": None,
            "observations": {
                observation_name: {
                    "value": value,
                    "source": "simulated",
                    "method": "oscilloscope.measure_frequency"
                    if kind == "frequency" else "oscilloscope.measure_vpp",
                    "observed_at": "2026-09-19T09:00:00+00:00",
                    "quality": "good",
                    "warnings": [],
                    "evidence_artifact_ids": [],
                }
            },
            "quality": "good",
            "warnings": [],
            "coherence": {
                "software_observations": "unknown",
                "instrument_vs_software": "unknown",
            },
            "provenance": {
                "started_at": "2026-09-19T09:00:00+00:00",
                "completed_at": "2026-09-19T09:00:01+00:00",
                "analysis_algorithm": None,
            },
        },
    }


def simulated_backend_receipt(values=(10000.0, 3.3, 10000.0, 3.3)) -> dict:
    bindings = (
        ("hardware.measure_frequency", 1),
        ("hardware.measure_vpp", 1),
        ("hardware.measure_frequency", 2),
        ("hardware.measure_vpp", 2),
    )
    return {
        "contract": "aia-re001c-lite-validation",
        "contract_version": "1.0",
        "kind": "governed_measurement_receipt",
        "status": "COMPLETED",
        "operations": [
            {
                "operation": operation,
                "channel": channel,
                "scope_remaining_invocations": 0,
                "policy_reason": "allowed_confirmed_physical_setup",
                "ipc_dispatch_count": 1,
                "hardware_execution_count": 1,
                "canonical_result": simulated_backend_canonical(operation, channel, value),
                "failure_code": None,
            }
            for (operation, channel), value in zip(bindings, values, strict=True)
        ],
        "failure_code": None,
    }


class SafeEgress:
    def __init__(self) -> None:
        self.values: list[str] = []

    def inspect(self, text: str, *, correlation_id: str) -> EgressDecision:
        self.values.append(text)
        return EgressDecision.safe()


class SelectingRuntime:
    def __init__(self, *, contradict: bool = False) -> None:
        self.requests = []
        self.closed = 0
        self.contradict = contradict

    async def generate(self, request):
        self.requests.append(request)
        payload = {
            "schema_id": "aia-teaching-claim-candidate/v1",
            "projection_id": request.projection.projection_id,
            "context_fingerprint": request.projection.context_fingerprint,
            "envelope_id": request.projection.envelope_id,
            "goal": request.goal.value,
            "ordered_permission_refs": [slot.alias for slot in request.projection.slots[:12]],
        }
        if self.contradict:
            payload["claimed_frequency_hz"] = 100.0
        return StructuredCandidateOutcome.candidate(json.dumps(payload, separators=(",", ":")))

    async def aclose(self) -> None:
        self.closed += 1


def publisher(runtime: SelectingRuntime, egress: SafeEgress) -> OneShotPublicationCoordinator:
    boundary = GovernedPublicationBoundary(
        egress,
        StrictCandidateParser(ROOT / "protocols" / "teaching-claims" / "v1"),
    )
    return OneShotPublicationCoordinator(runtime, boundary)


class RE001DLiteCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.coordinator = RE001DLiteCoordinator()
        self.request = (
            "Measure the current STM32 output. Treat CH1 as Vin and CH2 as Vout. "
            "Measure frequency and Vpp and explain the result."
        )

    def test_natural_language_maps_only_to_bounded_re001d_intent(self) -> None:
        prepared = self.coordinator.prepare(self.request)
        self.assertEqual(prepared.intent, "RE001D_LITE_SINGLE_POINT")
        self.assertEqual(prepared.operation_sequence, (
            ("hardware.measure_frequency", 1),
            ("hardware.measure_vpp", 1),
            ("hardware.measure_frequency", 2),
            ("hardware.measure_vpp", 2),
        ))
        self.assertEqual(prepared.status, "CONFIRMATION_REQUIRED")
        self.assertIn("0–3.3 V", prepared.confirmation_prompt)

    def test_unrecognized_or_broadened_intent_fails_closed(self) -> None:
        for value in ("Explain Ohm's law", "Capture waveforms and sweep the filter"):
            with self.subTest(value=value), self.assertRaises(RE001DIntentError):
                self.coordinator.prepare(value)

    def test_prepared_flow_contains_no_authority_object(self) -> None:
        prepared = self.coordinator.prepare(self.request)
        names = set(prepared.__dataclass_fields__)
        self.assertFalse(names & {"scope", "confirmation", "authorization", "tool_arguments"})

    async def test_fake_e2e_maps_analyzes_and_publishes_exact_evidence(self) -> None:
        prepared = self.coordinator.prepare(self.request)
        runtime, egress = SelectingRuntime(), SafeEgress()
        result = await self.coordinator.complete(
            prepared,
            receipt(),
            publisher=publisher(runtime, egress),
            correlation_id="re001d-fake-e2e",
        )
        self.assertEqual(result.measurement.gain_ratio, 3.24 / 0.34)
        self.assertAlmostEqual(result.measurement.gain_db, 19.58132186328714)
        self.assertEqual(len(result.teaching_context.physical_observations), 4)
        self.assertEqual(len(result.teaching_context.software_analyses), 4)
        self.assertEqual(result.teaching_context.inferences, ())
        self.assertEqual(result.publication.audit.hardware_count, 0)
        self.assertIn("10020.04 Hz", result.publication.publication.text)
        self.assertIn("0.34 V", result.publication.publication.text)
        self.assertIn("3.24 V", result.publication.publication.text)
        self.assertNotIn("100 Hz", result.publication.publication.text)
        self.assertEqual(runtime.closed, 1)
        self.assertEqual(len(egress.values), 1)

    async def test_contradictory_candidate_cannot_override_evidence(self) -> None:
        runtime, egress = SelectingRuntime(contradict=True), SafeEgress()
        result = await self.coordinator.complete(
            self.coordinator.prepare(self.request),
            receipt(),
            publisher=publisher(runtime, egress),
            correlation_id="re001d-contradiction",
        )
        self.assertEqual(result.publication.publication.status, "FALLBACK_PUBLISHED")
        self.assertIn("10020.04 Hz", result.publication.publication.text)
        self.assertNotIn("100 Hz", result.publication.publication.text)

    async def test_fake_backend_simulated_receipt_maps_analyzes_and_preserves_provenance(self) -> None:
        prepared = self.coordinator.prepare(self.request)
        runtime, egress = SelectingRuntime(), SafeEgress()
        result = await self.coordinator.complete(
            prepared,
            simulated_backend_receipt(),
            publisher=publisher(runtime, egress),
            correlation_id="re001d-fake-web-e2e",
        )
        # Deterministic analysis on the FAKE values (Vin and Vout agree).
        self.assertEqual(result.measurement.gain_ratio, 1.0)
        self.assertAlmostEqual(result.measurement.gain_db, 0.0)
        # Simulated provenance is preserved through mapping into teaching evidence.
        self.assertEqual(len(result.teaching_context.physical_observations), 4)
        for located in result.teaching_context.physical_observations:
            self.assertIs(located.item.source, TeachingEvidenceSource.SIMULATED)
        # The publication must attribute the numbers to simulated evidence, never
        # to a real instrument measurement.
        text = result.publication.publication.text
        self.assertIn("Simulated evidence:", text)
        self.assertIn("Simulated evidence: CH1 frequency = 10000 Hz.", text)
        self.assertIn("Simulated evidence: CH1 Vpp = 3.3 V.", text)
        self.assertNotIn("Instrument measurement:", text)
        self.assertNotIn("observation_source_invalid", text)
        self.assertEqual(result.publication.audit.final_egress, "SAFE")
        self.assertEqual(result.publication.audit.model_retry_count, 0)
        self.assertEqual(result.publication.audit.tool_count, 0)

    async def test_invalid_governed_receipt_stops_before_model(self) -> None:
        invalid = receipt()
        invalid["operations"][0]["scope_remaining_invocations"] = 1
        runtime, egress = SelectingRuntime(), SafeEgress()
        with self.assertRaises(ValueError):
            await self.coordinator.complete(
                self.coordinator.prepare(self.request),
                invalid,
                publisher=publisher(runtime, egress),
                correlation_id="re001d-invalid-receipt",
            )
        self.assertEqual(runtime.requests, [])
        self.assertEqual(egress.values, [])

    async def test_troubleshooting_is_unresolved_not_physical_fact(self) -> None:
        result = await self.coordinator.complete(
            self.coordinator.prepare(self.request),
            receipt(),
            publisher=publisher(SelectingRuntime(), SafeEgress()),
            correlation_id="re001d-troubleshooting",
        )
        self.assertEqual(len(result.teaching_context.unresolved_questions), 1)
        question = result.teaching_context.unresolved_questions[0]
        self.assertIn("probe attenuation", question.detail)
        self.assertNotIn(question.detail, tuple(item.item.label for item in result.teaching_context.physical_observations))
        self.assertEqual(result.teaching_context.inferences, ())


if __name__ == "__main__":
    unittest.main()
