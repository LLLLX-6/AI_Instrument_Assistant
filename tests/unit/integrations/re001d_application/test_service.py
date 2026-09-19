from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
import unittest

from ai_instrument_assistant.integrations.re001d_application import (
    RE001DApplicationError,
    RE001DApplicationService,
)


ROOT = Path(__file__).resolve().parents[4]
REQUEST_TEXT = (
    "Measure the current STM32 output. Treat CH1 as Vin and CH2 as Vout. "
    "Measure frequency and Vpp and explain the result."
)


class Publisher:
    """Hermes-free publisher double that projects evidence provenance."""

    def __init__(self) -> None:
        self.contexts = []

    async def publish(self, **kwargs):
        context = kwargs["context"]
        self.contexts.append(context)
        projected = " | ".join(
            f"{located.item.source.value} {located.item.label} = {located.item.value}"
            for located in context.physical_observations
        )
        return SimpleNamespace(
            publication=SimpleNamespace(
                status="FALLBACK_PUBLISHED",
                text=f"Bounded grounded result. {projected}",
            ),
            audit=SimpleNamespace(
                grounding_result="FALLBACK", final_egress="SAFE",
                model_request_count=0, model_retry_count=0,
            ),
        )


def service() -> RE001DApplicationService:
    return RE001DApplicationService(
        ROOT / "protocols/re001d-application/v1",
        lambda: Publisher(),  # type: ignore[arg-type]
    )


def prepare_request(workflow="workflow-1", correlation="request-1", text=REQUEST_TEXT):
    return {
        "protocol": "aia-re001d-application/v1", "operation": "prepare",
        "workflow_id": workflow, "request_correlation_id": correlation, "user_text": text,
    }


def canonical(operation: str, channel: int, value: float, source: str = "instrument"):
    kind = "frequency" if operation.endswith("frequency") else "vpp"
    observation = "instrument_frequency" if kind == "frequency" else "instrument_vpp"
    return {
        "contract_version": "1.0", "ok": True, "operation": operation,
        "result": {
            "request_id": f"00000000-0000-4000-8000-0000000000{channel}{1 if kind == 'frequency' else 2}",
            "kind": kind, "channel": channel, "context_id": f"RE-001:{channel}",
            "instrument": {"manufacturer": "SIMULATED", "model": "FAKE", "serial_number": "SYNTHETIC", "firmware_version": "test"},
            "waveform": None,
            "observations": {observation: {"value": value, "source": source, "method": "simulated query", "observed_at": "2026-09-16T00:00:00Z", "quality": "good", "warnings": ["SIMULATED_BACKEND"], "evidence_artifact_ids": []}},
            "quality": "good", "warnings": ["SIMULATED_BACKEND"],
            "coherence": {"software_observations": "unknown", "instrument_vs_software": "unknown"},
            "provenance": {"started_at": "2026-09-16T00:00:00Z", "completed_at": "2026-09-16T00:00:01Z", "analysis_algorithm": None},
        },
    }


def simulated_backend_canonical(operation: str, channel: int, value: float):
    """Exactly the shape the real FAKE backend emits over Harness-Hardware v1."""
    kind = "frequency" if operation.endswith("frequency") else "vpp"
    observation = "instrument_frequency" if kind == "frequency" else "instrument_vpp"
    return {
        "contract_version": "1.0", "ok": True, "operation": operation,
        "result": {
            "request_id": f"00000000-0000-4000-8000-0000000000{channel}{1 if kind == 'frequency' else 2}",
            "kind": kind, "channel": channel, "context_id": None,
            "instrument": {"manufacturer": "AI Instrument Assistant", "model": "Simulated Oscilloscope", "serial_number": "***ATED", "firmware_version": "1.0"},
            "waveform": None,
            "observations": {observation: {"value": value, "source": "simulated", "method": f"oscilloscope.{ 'measure_frequency' if kind == 'frequency' else 'measure_vpp' }", "observed_at": "2026-09-19T09:00:00+00:00", "quality": "good", "warnings": [], "evidence_artifact_ids": []}},
            "quality": "good", "warnings": [],
            "coherence": {"software_observations": "unknown", "instrument_vs_software": "unknown"},
            "provenance": {"started_at": "2026-09-19T09:00:00+00:00", "completed_at": "2026-09-19T09:00:01+00:00", "analysis_algorithm": None},
        },
    }


def complete_request(workflow="workflow-1", correlation="request-1", builder=canonical, values=(10000.0, 3.3, 10000.0, 3.3)):
    bindings = (
        ("hardware.measure_frequency", 1, values[0]), ("hardware.measure_vpp", 1, values[1]),
        ("hardware.measure_frequency", 2, values[2]), ("hardware.measure_vpp", 2, values[3]),
    )
    return {
        "protocol": "aia-re001d-application/v1", "operation": "complete",
        "workflow_id": workflow, "request_correlation_id": correlation,
        "governed_receipt": {
            "contract": "aia-re001c-lite-validation", "contract_version": "1.0",
            "kind": "governed_measurement_receipt", "status": "COMPLETED", "failure_code": None,
            "operations": [{
                "operation": operation, "channel": channel, "scope_remaining_invocations": 0,
                "policy_reason": "allowed_confirmed_physical_setup", "ipc_dispatch_count": 1,
                "hardware_execution_count": 1, "canonical_result": builder(operation, channel, value),
                "failure_code": None,
            } for operation, channel, value in bindings],
        },
    }


class RE001DApplicationServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_prepare_is_bounded_and_contains_no_authority(self):
        result = service().prepare(prepare_request())
        self.assertEqual(result["status"], "CONFIRMATION_REQUIRED")
        self.assertEqual(tuple(result["plan"]["operation_sequence"][0]), ("hardware.measure_frequency", 1))
        self.assertFalse({"scope", "confirmation", "authorization", "token"} & set(str(result).lower().split()))

    def test_unsupported_intent_and_extra_fields_fail_closed(self):
        with self.assertRaisesRegex(RE001DApplicationError, "UNSUPPORTED_INTENT"):
            service().prepare(prepare_request(text="Measure frequency on CH1"))
        value = prepare_request(); value["scope"] = "forged"
        with self.assertRaisesRegex(RE001DApplicationError, "INVALID_REQUEST"):
            service().prepare(value)

    async def test_complete_reuses_strict_mapper_and_is_single_submission(self):
        target = service(); target.prepare(prepare_request())
        result = await target.complete(complete_request())
        self.assertEqual(result["publication"]["final_egress"], "SAFE")
        with self.assertRaisesRegex(RE001DApplicationError, "DUPLICATE_COMPLETE"):
            await target.complete(complete_request())

    async def test_complete_accepts_simulated_backend_receipt_and_preserves_provenance(self):
        target = service(); target.prepare(prepare_request())
        result = await target.complete(
            complete_request(builder=simulated_backend_canonical, values=(10000.0, 3.3, 10000.0, 3.3)),
        )
        self.assertEqual(result["publication"]["final_egress"], "SAFE")
        text = result["publication"]["text"]
        self.assertIn("simulated CH1 frequency = 10000.0", text)
        self.assertIn("simulated CH2 Vpp = 3.3", text)
        self.assertNotIn("instrument CH1 frequency", text)
        self.assertNotIn("instrument CH2 Vpp", text)

    async def test_wrong_correlation_and_wrong_binding_fail_closed(self):
        target = service(); target.prepare(prepare_request())
        with self.assertRaisesRegex(RE001DApplicationError, "CORRELATION_MISMATCH"):
            await target.complete(complete_request(correlation="wrong"))
        value = complete_request(); value["governed_receipt"]["operations"][0]["channel"] = 2
        with self.assertRaisesRegex(RE001DApplicationError, "APPLICATION_FAILURE"):
            await target.complete(value)


if __name__ == "__main__":
    unittest.main()
