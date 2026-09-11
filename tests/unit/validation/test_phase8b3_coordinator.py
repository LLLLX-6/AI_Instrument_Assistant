from __future__ import annotations

import json
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ai_instrument_assistant.application.services.design_selection_disambiguation import (
    DesignSelectionCandidateIdentity,
)
from ai_instrument_assistant.application.services.eda_design_evidence import (
    DesignEvidenceProjectionStatus,
    EDADesignEvidenceCaptureService,
)
from ai_instrument_assistant.domain.eda import DesignObjectKind
from ai_instrument_assistant.domain.engineering_evidence import (
    ComparisonReason,
    CrossReferenceState,
    DesignEvidenceOrigin,
    TargetProvenance,
)
from tests.unit.application.services.test_phase8b2_real_eda_recorded_workflow import (
    real_style_projection,
)
from validation.support.phase8b3.coordinator import (
    ConfirmationAction,
    OperationAuthorizationAction,
    Phase8B3Coordinator,
    SNAPSHOT_LIMITATION,
)


ROOT = Path(__file__).resolve().parents[3]
OBSERVED_AT = datetime(2026, 9, 10, 6, 0, tzinfo=timezone.utc)


class StaticCapture:
    def __init__(self, projection=None, error: Exception | None = None) -> None:
        self.projection = projection
        self.error = error
        self.calls = 0

    async def capture(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.projection


class TrustedHost:
    def __init__(
        self,
        *,
        confirm=ConfirmationAction.CONFIRM,
        authorize=OperationAuthorizationAction.AUTHORIZE,
        choose=True,
    ) -> None:
        self.confirm = confirm
        self.authorize = authorize
        self.choose = choose
        self.prompts = []
        self.operation_prompts = []

    async def choose_design_candidate(self, binding):
        if not self.choose:
            return None
        wire = next(item for item in binding.candidate_identities if item.object_type is DesignObjectKind.WIRE)
        return wire

    async def confirm_probe_connection(self, prompt):
        self.prompts.append(prompt)
        return self.confirm

    async def authorize_operation_plan(self, prompt):
        self.operation_prompts.append(prompt)
        return self.authorize


class FakeGovernedHardware:
    def __init__(self) -> None:
        self.start_count = 0
        self.requests = []

    async def execute(self, request):
        self.start_count += 1
        self.requests.append(request)
        evidence = json.loads((
            ROOT / "protocols/evidence/v1/fixtures/valid/pwm-teaching-context.case.json"
        ).read_text(encoding="utf-8"))["instance"]
        _replace_evidence_times(evidence, "2026-09-10T06:00:03Z")
        status_canonical = {
            "contract_version": "1.0", "ok": True, "operation": "hardware.get_status",
            "result": {
                "instrument": {
                    "manufacturer": "RIGOL TECHNOLOGIES", "model": "DS1102Z-E",
                    "serial_number": "***9517", "firmware_version": "00.06.03.SP2",
                },
                "observed_at": "2026-09-10T06:00:03Z",
            },
        }
        pwm_canonical = _canonical_pwm(evidence, request["target"]["target_ref"])
        operation = lambda name, channel, canonical: {
            "operation": name,
            "channel": channel,
            "delivery_state": "RESPONSE_RECEIVED",
            "scope_decision": {
                "decision": "ALLOW",
                "reason_code": "allowed_operation_in_scope",
                "remaining_invocations": 0,
            },
            "policy_decision": {
                "decision": "ALLOW",
                "reason_code": "allowed_safe_observation" if channel is None else "allowed_confirmed_physical_setup",
            },
            "ipc_dispatch_count": 1,
            "hardware_execution_count": 1,
            "execution_started_at": "2026-09-10T06:00:02.500000Z",
            "execution_completed_at": "2026-09-10T06:00:03Z",
            "canonical_result": canonical,
            "failure_code": None,
        }
        return {
            "contract": "aia-phase8b3-validation",
            "contract_version": "1.0",
            "kind": "governed_hardware_receipt",
            "run_id": request["run_id"],
            "workflow_id": request["workflow_id"],
            "request_correlation_id": request["request_correlation_id"],
            "status": "COMPLETED",
            "operations": [
                operation("hardware.get_status", None, status_canonical),
                operation("hardware.measure_pwm", 1, pwm_canonical),
            ],
            "pwm_teaching_evidence": evidence,
            "failure_code": None,
            "limitations": ["Synthetic governed Hardware boundary."],
        }


class ChannelMutatingHardware(FakeGovernedHardware):
    def __init__(self, *, status_channel=None, pwm_channel=1) -> None:
        super().__init__()
        self.status_channel = status_channel
        self.pwm_channel = pwm_channel

    async def execute(self, request):
        receipt = await super().execute(request)
        receipt["operations"][0]["channel"] = self.status_channel
        receipt["operations"][1]["channel"] = self.pwm_channel
        return receipt


class FixedClock:
    def __init__(self, start=OBSERVED_AT + timedelta(seconds=1)) -> None:
        self.current = start

    def __call__(self):
        value = self.current
        self.current += timedelta(seconds=1)
        return value


async def ambiguous_projection():
    base, _ = await real_style_projection()
    selection = base.design_context.selection
    wire = selection.selection.selected_objects[0]
    component = replace(
        wire,
        object_type=DesignObjectKind.COMPONENT,
        native_id="bounded-component",
        canonical_id="jlceda-pro:component:bounded-component",
        display_name=None,
        provider_kind="Component",
    )
    ambiguous = replace(
        selection,
        selection=replace(
            selection.selection,
            selected_objects=(wire, component),
            primary_object=None,
        ),
    )
    return EDADesignEvidenceCaptureService.project(
        active_document=base.active_document,
        selection_context=ambiguous,
        observed_at=OBSERVED_AT,
    )


class Phase8B3CoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_positive_ambiguous_wire_path_produces_verified_evidence_only_context(self):
        projection = await ambiguous_projection()
        hardware = FakeGovernedHardware()
        host = TrustedHost()
        result = await Phase8B3Coordinator(
            capture=StaticCapture(projection),
            host=host,
            hardware=hardware,
            repository_root=ROOT,
            clock=FixedClock(),
        ).run()

        self.assertEqual(
            result.status,
            "PASS",
            (result.failure_stage, result.failure_code),
        )
        self.assertEqual(hardware.start_count, 1)
        request = hardware.requests[0]
        self.assertEqual(request["status_scope"]["operation"], "hardware.get_status")
        self.assertEqual(request["status_scope"]["max_invocations"], 1)
        self.assertIsNone(request["status_scope"]["target_channel"])
        self.assertEqual(request["pwm_scope"]["operation"], "hardware.measure_pwm")
        self.assertEqual(request["pwm_scope"]["max_invocations"], 1)
        self.assertEqual(request["pwm_scope"]["target_channel"], 1)
        self.assertEqual(request["confirmation"]["maximum_expected_voltage_v"], 3.3)
        receipt = result.hardware_receipt
        self.assertEqual(receipt["operations"][0]["channel"], None)
        self.assertEqual(receipt["operations"][1]["channel"], 1)
        self.assertEqual(
            sum(item["hardware_execution_count"] for item in receipt["operations"]),
            2,
        )
        self.assertEqual(
            sum(
                item["hardware_execution_count"]
                for item in receipt["operations"]
                if item["operation"] == "hardware.measure_pwm"
            ),
            1,
        )
        workflow = result.workflow_result
        self.assertEqual(workflow.engineering_context.cross_references[0].state, CrossReferenceState.VERIFIED_LINK)
        self.assertTrue(all(item.reason is ComparisonReason.TOLERANCE_UNSPECIFIED for item in workflow.engineering_context.comparison_results))
        self.assertTrue(all(item.provenance is TargetProvenance.USER_PROVIDED for item in workflow.engineering_context.targets))
        target_evidence = workflow.engineering_context.design_context.evidence[-2:]
        self.assertTrue(all(item.origin is DesignEvidenceOrigin.USER_STATEMENT for item in target_evidence))
        self.assertEqual(workflow.engineering_context.inferences, ())
        self.assertEqual(workflow.teaching_context.inferences, ())
        self.assertEqual(workflow.teaching_context.candidate_next_measurements, ())
        self.assertIn(SNAPSHOT_LIMITATION, result.limitations)
        self.assertNotIn("unchanged", " ".join(result.limitations).replace("does not prove the design remained unchanged", ""))
        bounded = json.dumps(result.to_bounded_output())
        for forbidden in (
            "memory://", "USB0::", "primitiveId", "native_id", "PSK", "HMAC",
            "DEEPSEEK_API_KEY", "voltage_values", "time_values", '"samples"', "C:\\\\",
        ):
            self.assertNotIn(forbidden, bounded)

    async def test_pre_hardware_failures_never_start_governed_executor(self):
        projection = await ambiguous_projection()
        second_net = replace(
            projection.design_context.selection.nets[0],
            ref=replace(
                projection.design_context.selection.nets[0].ref,
                canonical_id="jlceda-pro:net:second",
                display_name="SECOND_NET",
            ),
        )
        multiple_net_selection = replace(
            projection.design_context.selection,
            nets=projection.design_context.selection.nets + (second_net,),
        )
        multiple_net_projection = EDADesignEvidenceCaptureService.project(
            active_document=projection.active_document,
            selection_context=multiple_net_selection,
            observed_at=OBSERVED_AT,
        )
        no_target_projection = replace(
            projection,
            status=DesignEvidenceProjectionStatus.UNSUPPORTED_SELECTION,
            probe_target=None,
        )
        cases = [
            (StaticCapture(error=RuntimeError("authentication failed")), TrustedHost()),
            (StaticCapture(projection), TrustedHost(choose=False)),
            (StaticCapture(projection), TrustedHost(confirm=ConfirmationAction.CANCEL)),
            (StaticCapture(projection), TrustedHost(authorize=OperationAuthorizationAction.CANCEL)),
            (StaticCapture(projection), TrustedHost(), FixedClock(OBSERVED_AT - timedelta(seconds=1))),
            (StaticCapture(multiple_net_projection), TrustedHost()),
            (StaticCapture(no_target_projection), TrustedHost()),
        ]
        for case in cases:
            with self.subTest(case=case):
                capture, host, *clock = case
                hardware = FakeGovernedHardware()
                result = await Phase8B3Coordinator(
                    capture=capture,
                    host=host,
                    hardware=hardware,
                    repository_root=ROOT,
                    clock=clock[0] if clock else FixedClock(),
                ).run()
                self.assertEqual(result.status, "NOT_PASS")
                self.assertEqual(hardware.start_count, 0)
                self.assertEqual(hardware.requests, [])

    async def test_prompt_binds_exact_target_workflow_channel_and_safety_provenance(self):
        projection = await ambiguous_projection()
        host = TrustedHost(confirm=ConfirmationAction.CANCEL)
        await Phase8B3Coordinator(
            capture=StaticCapture(projection), host=host, hardware=FakeGovernedHardware(),
            repository_root=ROOT, clock=FixedClock(),
        ).run()
        prompt = host.prompts[0]
        self.assertEqual(prompt.channel, 1)
        self.assertEqual(prompt.maximum_expected_voltage_v, 3.3)
        self.assertEqual(prompt.display_label, "PWM_OUT")
        self.assertIn("unchanged", prompt.wiring_statement)
        self.assertTrue(prompt.workflow_id.startswith("phase8b3-"))

    async def test_recorded_null_pwm_channel_is_rejected_before_evidence_assembly(self):
        case = json.loads((
            ROOT / "tests/fixtures/phase8b3/real-attempt-1-pwm-channel-loss.case.json"
        ).read_text(encoding="utf-8"))
        hardware = ChannelMutatingHardware(
            status_channel=case["recorded_receipt"]["status_channel"],
            pwm_channel=case["recorded_receipt"]["pwm_channel"],
        )
        result = await Phase8B3Coordinator(
            capture=StaticCapture(await ambiguous_projection()),
            host=TrustedHost(),
            hardware=hardware,
            repository_root=ROOT,
            clock=FixedClock(),
        ).run()

        self.assertEqual((result.failure_stage, result.failure_code), (
            "hardware", "receipt_semantics_invalid"
        ))
        self.assertIsNone(result.workflow_result)
        self.assertIsNone(result.to_bounded_output()["evidence"])

    async def test_receipt_channel_tampering_fails_closed(self):
        for status_channel, pwm_channel in ((None, 2), (None, None), (1, 1)):
            with self.subTest(status_channel=status_channel, pwm_channel=pwm_channel):
                result = await Phase8B3Coordinator(
                    capture=StaticCapture(await ambiguous_projection()),
                    host=TrustedHost(),
                    hardware=ChannelMutatingHardware(
                        status_channel=status_channel,
                        pwm_channel=pwm_channel,
                    ),
                    repository_root=ROOT,
                    clock=FixedClock(),
                ).run()
                self.assertEqual((result.failure_stage, result.failure_code), (
                    "hardware", "receipt_semantics_invalid"
                ))
                self.assertIsNone(result.workflow_result)


def _replace_evidence_times(value, timestamp):
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in {"observedAt", "capturedAt"}:
                value[key] = timestamp
            else:
                _replace_evidence_times(nested, timestamp)
    elif isinstance(value, list):
        for nested in value:
            _replace_evidence_times(nested, timestamp)


def _canonical_pwm(evidence, target_ref):
    artifact = evidence["artifact"]
    observations = {}
    for item in (*evidence["facts"], *evidence["analyses"]):
        key = {
            "instrument frequency": "instrument_frequency",
            "software frequency": "software_frequency",
            "software duty cycle": "software_duty_cycle",
        }.get(item["label"])
        if key is None:
            continue
        observations[key] = {
            "value": item["value"],
            "source": item["source"],
            "method": item["provenance"]["method"],
            "observed_at": item["provenance"]["observedAt"],
            "quality": item["quality"],
            "warnings": item["warnings"],
            "evidence_artifact_ids": item["provenance"]["evidenceArtifactIds"],
        }
    return {
        "contract_version": "1.0", "ok": True, "operation": "hardware.measure_pwm",
        "result": {
            "request_id": "88888888-8888-4888-8888-888888888888",
            "kind": "pwm", "channel": 1, "context_id": target_ref,
            "instrument": {
                "manufacturer": "RIGOL TECHNOLOGIES", "model": "DS1102Z-E",
                "serial_number": "***9517", "firmware_version": "00.06.03.SP2",
            },
            "waveform": {
                "artifact": dict(artifact["reference"]), "channel": 1,
                "point_count": artifact["pointCount"],
                "sample_interval_seconds": artifact["sampleIntervalSeconds"],
                "time_range_seconds": artifact["timeRangeSeconds"],
                "voltage_range_v": artifact["voltageRangeV"],
                "acquisition_mode": artifact["acquisitionMode"],
                "captured_at": artifact["capturedAt"],
            },
            "observations": observations, "quality": evidence["quality"],
            "warnings": evidence["warnings"], "coherence": evidence["coherence"],
            "provenance": {
                "started_at": "2026-09-10T06:00:02.500000Z",
                "completed_at": "2026-09-10T06:00:03Z",
                "analysis_algorithm": {"name": "edge", "version": "1"},
            },
        },
    }


if __name__ == "__main__":
    unittest.main()
