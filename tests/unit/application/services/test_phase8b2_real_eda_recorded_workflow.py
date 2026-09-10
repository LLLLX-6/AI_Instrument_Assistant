from __future__ import annotations

import json
import unittest
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from ai_instrument_assistant.application.services.eda_design_evidence import (
    DesignEvidenceProjectionStatus,
    EDADesignEvidenceCaptureService,
    create_user_provided_numeric_target,
    diagnose_selection_projection,
)
from ai_instrument_assistant.application.services.design_selection_disambiguation import (
    TrustedDesignSelectionResolutionStatus,
    build_candidate_set_binding,
    resolve_trusted_design_selection,
)
from ai_instrument_assistant.application.services.engineering_evidence import (
    DeterministicEngineeringComparator,
    EngineeringEvidenceAssembler,
)
from ai_instrument_assistant.application.services.engineering_evidence_workflow import (
    EngineeringEvidenceWorkflow,
    EngineeringEvidenceWorkflowRequest,
)
from ai_instrument_assistant.domain.engineering_evidence import (
    ComparisonReason,
    ComparisonStatus,
    CrossReferenceState,
    DesignEvidenceContext,
    DesignEvidenceOrigin,
    EngineeringMetric,
    EvidenceCategory,
    RelativeTolerance,
    TargetProvenance,
    TrustedPhysicalConfirmationEvidence,
)
from ai_instrument_assistant.protocol.evidence_binding import (
    EvidenceContractBinding,
)
from ai_instrument_assistant.integrations.jlceda.mapper import JLCEDADomainMapper
from ai_instrument_assistant.integrations.jlceda.remote_adapter import JLCEDARemoteAdapter
from ai_instrument_assistant.protocol.schema_registry import SchemaRegistry
from ai_instrument_assistant.protocol.schema_validator import SchemaValidator
from scripts.validate_phase8b2_real_jlceda import (
    BoundedValidationFailure,
    create_cli_trusted_selection_decision,
    execute_recorded_workflow,
)


ROOT = Path(__file__).resolve().parents[4]
PROTOCOL = ROOT / "protocols/jlceda/v1"
RECORDED = ROOT / "protocols/evidence/v1/fixtures/valid/pwm-teaching-context.case.json"
NOW = datetime(2026, 9, 10, 6, 0, tzinfo=timezone.utc)
MEASURED_AT = datetime(2026, 9, 10, 2, 0, 3, tzinfo=timezone.utc)
CONFIRMED_AT = datetime(2026, 9, 10, 2, 0, 1, tzinfo=timezone.utc)
WORKFLOW_ID = "phase8b2-real-jlceda-recorded"
REQUEST_ID = "phase8b2-request-1"
MEASUREMENT_CONTEXT_ID = UUID("51515151-5151-4151-8151-515151515151")


class Responses:
    def __init__(self, values: list[object]) -> None:
        self.values = values
        self.calls: list[str] = []

    async def request(self, operation: str, payload: object, *, timeout: float) -> object:
        self.calls.append(operation)
        return self.values.pop(0)


def response(name: str) -> dict:
    path = PROTOCOL / "fixtures/valid" / name
    return json.loads(path.read_text(encoding="utf-8"))["instance"]


def aligned_responses() -> tuple[dict, dict]:
    document = deepcopy(response("eda-document/get-active-success.case.json"))
    selection = deepcopy(response("eda-selection/wire-net-response.case.json"))
    active_ref = document["payload"]["document"]["document_ref"]
    selection_context = selection["payload"]["context"]
    selection_ref = selection_context["selection"]["document_ref"]
    selection_snapshot = "61616161-6161-4161-8161-616161616161"
    for name in ("document_id", "native_id", "canonical_id"):
        selection_ref[name] = active_ref[name]
    selection_ref["snapshot_id"] = selection_snapshot
    for selected in selection_context["selection"]["selected_objects"]:
        selected["document_id"] = active_ref["document_id"]
        selected["snapshot_id"] = selection_snapshot
    for net in selection_context["nets"]:
        net["ref"]["document_id"] = active_ref["document_id"]
        net["ref"]["snapshot_id"] = selection_snapshot
    return document, selection


async def real_style_projection():
    client = Responses(list(aligned_responses()))
    validator = SchemaValidator(SchemaRegistry.from_directory(PROTOCOL))
    adapter = JLCEDARemoteAdapter(
        request_client=client,
        validator=validator,
        mapper=JLCEDADomainMapper(),
    )
    projection = await EDADesignEvidenceCaptureService(
        eda=adapter,
        clock=lambda: NOW,
    ).capture()
    return projection, client


def recorded_context():
    fixture = json.loads(RECORDED.read_text(encoding="utf-8"))["instance"]
    return EvidenceContractBinding.from_repository(ROOT).parse_teaching_context(fixture)


def target_declarations(projection, *, tolerance=None):
    frequency = create_user_provided_numeric_target(
        evidence_id=UUID("62626262-6262-4262-8262-626262626262"),
        target_id=UUID("63636363-6363-4363-8363-636363636363"),
        document=projection.design_context.document,
        design_object=projection.probe_target.design_object,
        observed_at=CONFIRMED_AT,
        label="PWM_OUT expected frequency from trusted user context",
        metric=EngineeringMetric.FREQUENCY,
        value=10.0,
        unit="kHz",
        tolerance=tolerance,
    )
    duty = create_user_provided_numeric_target(
        evidence_id=UUID("64646464-6464-4464-8464-646464646464"),
        target_id=UUID("65656565-6565-4565-8565-656565656565"),
        document=projection.design_context.document,
        design_object=projection.probe_target.design_object,
        observed_at=CONFIRMED_AT,
        label="PWM_OUT expected duty cycle from trusted user context",
        metric=EngineeringMetric.DUTY_CYCLE,
        value=30.0,
        unit="percent",
        tolerance=None,
    )
    return frequency, duty


def confirmation(projection, **changes):
    values = {
        "confirmation_id": "phase8b2-trusted-confirmation-fixture",
        "source": "TRUSTED_USER_EVENT",
        "confirmed_by": "phase8b2-trusted-fixture",
        "workflow_id": WORKFLOW_ID,
        "request_correlation_id": REQUEST_ID,
        "channel": 1,
        "target_ref": projection.probe_target.design_object.canonical_id,
        "design_snapshot_id": projection.probe_target.snapshot_id,
        "probe_target_id": projection.probe_target.target_id,
        "safe_low_voltage_confirmed": True,
        "common_ground_confirmed": True,
        "wiring_unchanged": True,
        "confirmed_at": CONFIRMED_AT,
    }
    values.update(changes)
    return TrustedPhysicalConfirmationEvidence(**values)


def request_for(
    projection,
    *,
    targets=None,
    confirmation_value=None,
    omit_measurement: bool = False,
):
    frequency, duty = target_declarations(projection)
    declarations = (frequency, duty) if targets is None else targets
    design = DesignEvidenceContext(
        document=projection.design_context.document,
        evidence=projection.design_context.evidence + tuple(item.evidence for item in declarations),
        probe_targets=projection.design_context.probe_targets,
        selection=projection.design_context.selection,
    )
    measurement = None if omit_measurement else recorded_context()
    return EngineeringEvidenceWorkflowRequest(
        context_id=UUID("66666666-6666-4666-8666-666666666666"),
        workflow_id=WORKFLOW_ID,
        request_correlation_id=REQUEST_ID,
        user_goal="Compare real JLCEDA PWM_OUT structure with recorded PWM evidence",
        assembled_at=NOW,
        design_context=design,
        targets=tuple(item.target for item in declarations),
        probe_target=projection.probe_target,
        confirmation=(
            confirmation(projection)
            if confirmation_value is None
            else confirmation_value
        ),
        measurement_context_id=None if omit_measurement else MEASUREMENT_CONTEXT_ID,
        measurement_context=measurement,
        measurement_channel=None if omit_measurement else 1,
        measured_at=None if omit_measurement else MEASURED_AT,
    )


def workflow():
    return EngineeringEvidenceWorkflow(
        assembler=EngineeringEvidenceAssembler(),
        comparator=DeterministicEngineeringComparator(),
    )


class Phase8B2RealEDARecordedWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.projection, self.client = await real_style_projection()

    async def test_existing_contracts_project_real_style_wire_without_native_leak(self) -> None:
        self.assertEqual(self.client.calls, ["eda.document.get_active", "eda.selection.get"])
        self.assertEqual(self.projection.status, DesignEvidenceProjectionStatus.PROJECTED)
        self.assertEqual(self.projection.active_document.document_ref.provider, "jlceda-pro")
        self.assertEqual(self.projection.source_object.object_type.value, "wire")
        self.assertEqual(self.projection.probe_target.design_object.object_type.value, "net")
        self.assertEqual(self.projection.probe_target.design_object.display_name, "PWM_OUT")
        self.assertFalse(hasattr(self.projection.source_object, "primitiveId"))
        net = self.projection.design_context.selection.nets[0]
        self.assertIsNone(net.signal_expectation)
        self.assertEqual(net.endpoints, ())

    async def test_validation_runner_publishes_bounded_zero_side_effect_summary(self) -> None:
        output = execute_recorded_workflow(
            projection=self.projection,
            assembled_at=NOW,
        )
        self.assertEqual(output["status"], "PASS")
        self.assertEqual(output["target_provenance"]["source"], "USER_PROVIDED")
        self.assertFalse(output["target_provenance"]["schematic_derived"])
        self.assertEqual(output["cross_reference"]["state"], "VERIFIED_LINK")
        self.assertEqual(output["contexts"]["engineering_inference_count"], 0)
        self.assertEqual(output["contexts"]["teaching_inference_count"], 0)
        self.assertEqual(output["contexts"]["candidate_next_measurement_count"], 0)
        self.assertEqual(
            output["external_actions"],
            {
                "jlceda_document_reads": 1,
                "jlceda_selection_reads": 1,
                "jlceda_writes": 0,
                "hardware_backend_starts": 0,
                "hardware_ipc_dispatches": 0,
                "physical_measurements": 0,
                "model_requests": 0,
            },
        )
        self.assertTrue(
            any(
                "not claimed as schematic-derived" in limitation
                for limitation in output["limitations"]
            )
        )

    async def test_bounded_failure_contains_no_provider_exception_or_fake_success(self) -> None:
        output = BoundedValidationFailure("selection", "read_failed").output()
        self.assertEqual(output["status"], "NOT_PASS")
        self.assertEqual(output["failure"], {"stage": "selection", "code": "read_failed"})
        self.assertFalse(output["fixture_fallback_used"])
        self.assertEqual(output["automatic_retry_count"], 0)
        self.assertNotIn("exception", output)
        self.assertNotIn("message", output["failure"])

    async def test_ambiguous_failure_exposes_only_bounded_selection_diagnostic(self) -> None:
        context = self.projection.design_context.selection
        first = context.selection.selected_objects[0]
        second = replace(
            first,
            native_id="bounded-second-wire",
            canonical_id="jlceda-pro:wire:bounded-second-wire",
        )
        ambiguous = replace(
            context,
            selection=replace(
                context.selection,
                selected_objects=(first, second),
            ),
        )
        diagnostic = diagnose_selection_projection(ambiguous)

        output = BoundedValidationFailure(
            "projection",
            "ambiguous_selection",
            diagnostic,
        ).output()

        self.assertEqual(
            output["diagnostic"],
            {
                "selection_count": 2,
                "provider_kinds": ["Wire", "Wire"],
                "selected_objects": [
                    {
                        "object_type": "wire",
                        "provider_kind": "Wire",
                        "native_id": first.native_id,
                        "canonical_id": first.canonical_id,
                        "display_name": first.display_name,
                    },
                    {
                        "object_type": "wire",
                        "provider_kind": "Wire",
                        "native_id": second.native_id,
                        "canonical_id": second.canonical_id,
                        "display_name": second.display_name,
                    },
                ],
                "derived_net_count": 1,
                "projected_candidate_count": 1,
                "projected_candidate_kinds": ["net"],
                "projected_candidate_refs": [context.nets[0].ref.canonical_id],
                "ambiguity_reason": "multiple_selected_objects",
                "resolution_stage": "selection_cardinality",
                "scope_expansion": "wire_to_net",
            },
        )
        serialized = json.dumps(output)
        self.assertNotIn("secret", serialized.lower())
        self.assertNotIn("traceback", serialized.lower())
        self.assertNotIn("C:\\", serialized)

    async def test_cli_choice_maps_exact_menu_key_not_display_name(self) -> None:
        base = self.projection.design_context.selection
        wire = base.selection.selected_objects[0]
        component = replace(
            wire,
            object_type=wire.object_type.COMPONENT,
            native_id="bounded-component",
            canonical_id="jlceda-pro:component:bounded-component",
            display_name=None,
            provider_kind="Component",
        )
        ambiguous = replace(
            base,
            selection=replace(
                base.selection,
                selected_objects=(wire, component),
                primary_object=None,
            ),
        )
        candidate_binding = build_candidate_set_binding(
            selection_context=ambiguous,
            selection_observed_at=NOW,
        )

        trusted = create_cli_trusted_selection_decision(
            candidate_binding=candidate_binding,
            menu_choice="A",
            decided_at=NOW,
            decision_id=UUID("90909090-9090-4090-8090-909090909090"),
        )
        self.assertEqual(trusted.selected_object, wire)
        self.assertNotEqual(trusted.selected_object, component)

        with self.assertRaises(BoundedValidationFailure) as caught:
            create_cli_trusted_selection_decision(
                candidate_binding=candidate_binding,
                menu_choice="PWM_OUT",
                decided_at=NOW,
                decision_id=UUID("92929292-9292-4292-8292-929292929292"),
            )
        self.assertEqual(caught.exception.stage, "disambiguation")
        self.assertEqual(caught.exception.code, "invalid_menu_choice")

    async def test_ambiguous_selection_trusted_wire_path_runs_existing_workflow(self) -> None:
        base = self.projection.design_context.selection
        wire = base.selection.selected_objects[0]
        component = replace(
            wire,
            object_type=wire.object_type.COMPONENT,
            native_id="bounded-component",
            canonical_id="jlceda-pro:component:bounded-component",
            display_name=None,
            provider_kind="Component",
        )
        ambiguous = replace(
            base,
            selection=replace(
                base.selection,
                selected_objects=(wire, component),
                primary_object=None,
            ),
        )
        candidate_binding = build_candidate_set_binding(
            selection_context=ambiguous,
            selection_observed_at=NOW,
        )
        trusted = create_cli_trusted_selection_decision(
            candidate_binding=candidate_binding,
            menu_choice="A",
            decided_at=NOW,
            decision_id=UUID("93939393-9393-4393-8393-939393939393"),
        )
        resolution = resolve_trusted_design_selection(
            current_selection=ambiguous,
            current_binding=candidate_binding,
            decision=trusted,
            trusted_workflow_id=WORKFLOW_ID,
            trusted_request_correlation_id=REQUEST_ID,
        )
        resolved_projection = EDADesignEvidenceCaptureService.project(
            active_document=self.projection.active_document,
            selection_context=ambiguous,
            observed_at=NOW,
            trusted_resolution=resolution,
        )

        output = execute_recorded_workflow(
            projection=resolved_projection,
            assembled_at=NOW,
        )

        self.assertEqual(resolution.status, TrustedDesignSelectionResolutionStatus.RESOLVED)
        self.assertEqual(output["status"], "PASS")
        self.assertIsNone(output["real_jlceda"]["provider_primary_object"])
        audit = output["trusted_design_disambiguation"]
        self.assertEqual(audit["trusted_origin"], "TRUSTED_HOST_USER_EVENT")
        self.assertEqual(audit["chosen_candidate"]["object_type"], "wire")
        self.assertEqual(audit["derived_target"]["object_type"], "net")
        self.assertEqual(output["cross_reference"]["state"], "VERIFIED_LINK")
        self.assertEqual(output["contexts"]["engineering_inference_count"], 0)
        self.assertEqual(output["contexts"]["teaching_inference_count"], 0)
        self.assertEqual(output["external_actions"]["physical_measurements"], 0)
        self.assertEqual(output["external_actions"]["model_requests"], 0)

    async def test_real_structure_plus_user_targets_and_recorded_evidence_runs_existing_workflow(self) -> None:
        result = workflow().execute(request_for(self.projection))
        link = result.engineering_context.cross_references[0]
        self.assertEqual(link.state, CrossReferenceState.VERIFIED_LINK)
        self.assertEqual(link.design_snapshot_id, self.projection.probe_target.snapshot_id)
        self.assertTrue(
            all(target.provenance is TargetProvenance.USER_PROVIDED for target in result.engineering_context.targets)
        )
        target_evidence = tuple(
            item
            for item in result.engineering_context.design_context.evidence
            if item.category is EvidenceCategory.DESIGN_TARGET
        )
        self.assertTrue(target_evidence)
        self.assertTrue(all(item.origin is DesignEvidenceOrigin.USER_STATEMENT for item in target_evidence))
        self.assertEqual(len(result.engineering_context.comparison_results), 3)
        self.assertTrue(
            all(item.status is ComparisonStatus.INDETERMINATE for item in result.engineering_context.comparison_results)
        )
        self.assertTrue(
            all(item.reason is ComparisonReason.TOLERANCE_UNSPECIFIED for item in result.engineering_context.comparison_results)
        )
        self.assertEqual(result.engineering_context.inferences, ())
        self.assertEqual(result.teaching_context.inferences, ())
        self.assertEqual(result.teaching_context.candidate_next_measurements, ())

    async def test_explicit_user_tolerance_preserves_comparator_semantics(self) -> None:
        frequency, _ = target_declarations(
            self.projection,
            tolerance=RelativeTolerance.from_percent(1.0),
        )
        result = workflow().execute(request_for(self.projection, targets=(frequency,)))
        self.assertEqual(len(result.engineering_context.comparison_results), 2)
        self.assertTrue(
            all(item.status is ComparisonStatus.MATCH for item in result.engineering_context.comparison_results)
        )

    async def test_cross_reference_mismatches_remain_independently_gated(self) -> None:
        cases = {
            "SNAPSHOT_MISMATCH": {"design_snapshot_id": UUID("71717171-7171-4171-8171-717171717171")},
            "TARGET_REFERENCE_MISMATCH": {"target_ref": "PWM_OUT"},
            "CHANNEL_MISMATCH": {"channel": 2},
            "WORKFLOW_MISMATCH": {"workflow_id": "another-workflow"},
            "REQUEST_SCOPE_MISMATCH": {"request_correlation_id": "another-request"},
        }
        for reason, changes in cases.items():
            with self.subTest(reason=reason):
                result = workflow().execute(
                    request_for(
                        self.projection,
                        confirmation_value=confirmation(self.projection, **changes),
                    )
                )
                link = result.engineering_context.cross_references[0]
                self.assertEqual(link.state, CrossReferenceState.MISMATCH)
                self.assertIn(reason, link.reasons)
                self.assertTrue(
                    all(
                        item.reason is ComparisonReason.CROSS_REFERENCE_UNVERIFIED
                        for item in result.engineering_context.comparison_results
                    )
                )

    async def test_missing_target_or_recorded_measurement_is_not_fabricated(self) -> None:
        no_target = workflow().execute(request_for(self.projection, targets=()))
        self.assertEqual(no_target.engineering_context.comparison_results, ())
        self.assertIn(
            "TARGET_MISSING",
            {item.code for item in no_target.engineering_context.unresolved_questions},
        )
        self.assertIsNotNone(no_target.engineering_context.measurement_context)

        no_measurement = workflow().execute(request_for(self.projection, omit_measurement=True))
        self.assertIsNotNone(no_measurement.engineering_context.design_context)
        self.assertTrue(
            all(
                item.reason is ComparisonReason.MEASUREMENT_MISSING
                for item in no_measurement.engineering_context.comparison_results
            )
        )


if __name__ == "__main__":
    unittest.main()
