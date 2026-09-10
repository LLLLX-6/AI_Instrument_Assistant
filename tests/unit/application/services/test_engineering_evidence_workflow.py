from __future__ import annotations

import unittest
from dataclasses import replace

from ai_instrument_assistant.application.services.engineering_evidence import (
    DeterministicEngineeringComparator,
    EngineeringEvidenceAssembler,
)
from ai_instrument_assistant.application.services.engineering_evidence_workflow import (
    EngineeringEvidenceWorkflow,
)
from ai_instrument_assistant.domain.engineering_evidence import (
    ComparisonReason,
    ComparisonStatus,
    CrossReferenceState,
    EngineeringMetric,
    EvidenceCategory,
)
from ai_instrument_assistant.domain.errors import DomainInvariantError
from tests.support.engineering_evidence_workflow import workflow_request


def workflow() -> EngineeringEvidenceWorkflow:
    return EngineeringEvidenceWorkflow(
        assembler=EngineeringEvidenceAssembler(),
        comparator=DeterministicEngineeringComparator(),
    )


class EngineeringEvidenceWorkflowTests(unittest.TestCase):
    def test_request_rejects_partial_measurement_metadata(self) -> None:
        request = workflow_request("pwm_no_tolerance")
        with self.assertRaises(DomainInvariantError):
            replace(
                request,
                measurement_context=None,
                measurement_context_id=None,
            )

    def test_frequency_target_selects_both_instrument_and_software_frequency(self) -> None:
        result = workflow().execute(workflow_request("pwm_no_tolerance"))
        labels = [
            item.observed_ref.label
            for item in result.engineering_context.comparison_results
            if item.metric is EngineeringMetric.FREQUENCY
        ]
        self.assertEqual(labels, ["instrument frequency", "software frequency"])

    def test_duty_target_selects_only_duty_evidence(self) -> None:
        result = workflow().execute(workflow_request("pwm_no_tolerance"))
        labels = [
            item.observed_ref.label
            for item in result.engineering_context.comparison_results
            if item.metric is EngineeringMetric.DUTY_CYCLE
        ]
        self.assertEqual(labels, ["software duty cycle"])

    def test_incompatible_voltage_metrics_are_not_compared_to_frequency_or_duty(self) -> None:
        result = workflow().execute(workflow_request("pwm_no_tolerance"))
        labels = {item.observed_ref.label for item in result.engineering_context.comparison_results}
        self.assertTrue(labels.isdisjoint({"instrument vpp", "software vpp"}))

    def test_hz_to_khz_conversion_is_reused_from_comparator(self) -> None:
        result = workflow().execute(workflow_request("pwm_no_tolerance"))
        instrument = next(
            item
            for item in result.engineering_context.comparison_results
            if item.observed_ref.label == "instrument frequency"
        )
        self.assertEqual(instrument.observed.unit, "kHz")
        self.assertAlmostEqual(instrument.observed.value, 10.02)

    def test_name_equality_without_trusted_confirmation_never_verifies_link(self) -> None:
        request = workflow_request("missing_confirmation")
        self.assertEqual(request.probe_target.design_object.display_name, "PWM_OUT")
        self.assertEqual(request.measurement_context.confirmation_state.value, "CONFIRMED")
        result = workflow().execute(request)
        self.assertEqual(
            result.engineering_context.cross_references[0].state,
            CrossReferenceState.INSUFFICIENT_EVIDENCE,
        )

    def test_workflow_emits_no_generated_diagnosis_conclusion(self) -> None:
        result = workflow().execute(workflow_request("explicit_tolerance_mismatch"))
        self.assertFalse(hasattr(result.teaching_context, "diagnosis"))
        self.assertFalse(hasattr(result.teaching_context, "causal_explanation"))
        self.assertEqual(result.teaching_context.inferences, ())

    def test_workflow_result_is_structured_not_an_authorization(self) -> None:
        result = workflow().execute(workflow_request("pwm_no_tolerance"))
        self.assertFalse(hasattr(result, "operation_scope"))
        self.assertFalse(hasattr(result, "physical_confirmation"))
        self.assertFalse(hasattr(result, "execute"))

    def test_complete_pwm_fixture_assembles_with_multi_source_metric_matching(self) -> None:
        result = workflow().execute(workflow_request("pwm_no_tolerance"))
        comparisons = result.engineering_context.comparison_results
        frequency = [item for item in comparisons if item.metric is EngineeringMetric.FREQUENCY]
        duty = [item for item in comparisons if item.metric is EngineeringMetric.DUTY_CYCLE]

        self.assertEqual(len(frequency), 2)
        self.assertEqual(
            {item.observed_ref.label for item in frequency},
            {"instrument frequency", "software frequency"},
        )
        self.assertEqual(len(duty), 1)
        self.assertEqual(duty[0].observed_ref.label, "software duty cycle")
        self.assertNotIn("instrument vpp", {item.observed_ref.label for item in comparisons})
        self.assertNotIn("software vpp", {item.observed_ref.label for item in comparisons})
        self.assertIn(
            "instrument vpp",
            {item.locator.label for item in result.teaching_context.physical_observations},
        )
        self.assertIn(
            "software vpp",
            {item.locator.label for item in result.teaching_context.software_analyses},
        )

    def test_no_tolerance_remains_indeterminate_with_normalized_differences(self) -> None:
        result = workflow().execute(workflow_request("pwm_no_tolerance"))
        comparisons = result.engineering_context.comparison_results
        instrument = next(item for item in comparisons if item.observed_ref.label == "instrument frequency")
        software = next(item for item in comparisons if item.observed_ref.label == "software frequency")
        duty = next(item for item in comparisons if item.metric is EngineeringMetric.DUTY_CYCLE)

        self.assertEqual(instrument.status, ComparisonStatus.INDETERMINATE)
        self.assertEqual(instrument.reason, ComparisonReason.TOLERANCE_UNSPECIFIED)
        self.assertAlmostEqual(instrument.observed.value, 10.02)
        self.assertAlmostEqual(instrument.difference.value, 0.02)
        self.assertAlmostEqual(software.difference.value, 0.01)
        self.assertAlmostEqual(duty.difference.value, -0.05)

    def test_explicit_tolerance_match_and_mismatch_have_no_causal_diagnosis(self) -> None:
        match = workflow().execute(workflow_request("explicit_tolerance_match"))
        mismatch = workflow().execute(workflow_request("explicit_tolerance_mismatch"))
        self.assertEqual(match.engineering_context.comparison_results[0].status, ComparisonStatus.MATCH)
        self.assertEqual(mismatch.engineering_context.comparison_results[0].status, ComparisonStatus.MISMATCH)
        self.assertFalse(hasattr(mismatch.engineering_context.comparison_results[0], "diagnosis"))
        self.assertEqual(mismatch.teaching_context.inferences, ())

    def test_missing_confirmation_gates_all_authoritative_comparisons(self) -> None:
        result = workflow().execute(workflow_request("missing_confirmation"))
        self.assertEqual(result.engineering_context.cross_references[0].state, CrossReferenceState.INSUFFICIENT_EVIDENCE)
        self.assertTrue(all(item.status is ComparisonStatus.INDETERMINATE for item in result.engineering_context.comparison_results))
        self.assertTrue(all(item.reason is ComparisonReason.CROSS_REFERENCE_UNVERIFIED for item in result.engineering_context.comparison_results))

    def test_channel_and_snapshot_mismatches_fail_closed_despite_name_match(self) -> None:
        channel = workflow().execute(workflow_request("channel_mismatch"))
        snapshot = workflow().execute(workflow_request("snapshot_mismatch"))
        for result, reason in ((channel, "CHANNEL_MISMATCH"), (snapshot, "SNAPSHOT_MISMATCH")):
            link = result.engineering_context.cross_references[0]
            self.assertEqual(link.state, CrossReferenceState.MISMATCH)
            self.assertIn(reason, link.reasons)
            self.assertEqual(result.engineering_context.comparison_results[0].reason, ComparisonReason.CROSS_REFERENCE_UNVERIFIED)

    def test_conflicting_sources_remain_two_distinct_results_without_averaging(self) -> None:
        result = workflow().execute(workflow_request("conflicting_sources"))
        comparisons = result.engineering_context.comparison_results
        self.assertEqual(len(comparisons), 2)
        self.assertEqual([item.observed.value for item in comparisons], [8.0, 8.02])
        self.assertNotIn(8.01, [item.observed.value for item in comparisons])
        self.assertTrue(all(item.status is ComparisonStatus.MISMATCH for item in comparisons))

    def test_missing_target_and_measurement_are_preserved(self) -> None:
        no_target = workflow().execute(workflow_request("pwm_no_tolerance", omit_targets=True))
        self.assertEqual(no_target.engineering_context.targets, ())
        self.assertEqual(no_target.engineering_context.comparison_results, ())
        self.assertIn("TARGET_MISSING", {item.code for item in no_target.engineering_context.unresolved_questions})

        no_measurement = workflow().execute(workflow_request("pwm_no_tolerance", omit_measurement=True))
        self.assertIsNone(no_measurement.engineering_context.measurement_context)
        self.assertTrue(all(item.reason is ComparisonReason.MEASUREMENT_MISSING for item in no_measurement.engineering_context.comparison_results))
        self.assertIn("MEASUREMENT_MISSING", {item.code for item in no_measurement.engineering_context.unresolved_questions})

    def test_empty_and_unavailable_measurements_are_bounded(self) -> None:
        empty = workflow().execute(workflow_request("empty_measurement"))
        unavailable = workflow().execute(workflow_request("unavailable_measurement"))
        self.assertEqual(empty.engineering_context.comparison_results[0].reason, ComparisonReason.MEASUREMENT_MISSING)
        self.assertEqual(unavailable.engineering_context.comparison_results[0].reason, ComparisonReason.OBSERVATION_UNAVAILABLE)
        self.assertIsNone(unavailable.engineering_context.comparison_results[0].observed)

    def test_projection_is_faithful_and_generates_zero_inference_or_authority(self) -> None:
        result = workflow().execute(workflow_request("pwm_no_tolerance"))
        engineering = result.engineering_context
        teaching = result.teaching_context
        self.assertEqual(teaching.goal, engineering.user_goal)
        self.assertEqual(teaching.design_targets, engineering.targets)
        self.assertEqual(teaching.comparisons, engineering.comparison_results)
        self.assertEqual(teaching.quality, engineering.measurement_context.quality)
        self.assertEqual(teaching.warnings, engineering.measurement_context.warnings)
        self.assertEqual(teaching.coherence, engineering.measurement_context.coherence)
        self.assertEqual(teaching.limitations, engineering.limitations)
        self.assertEqual(teaching.unresolved_questions, engineering.unresolved_questions)
        self.assertEqual(engineering.inferences, ())
        self.assertEqual(teaching.inferences, ())
        self.assertEqual(teaching.candidate_next_measurements, ())
        self.assertFalse(hasattr(result, "trusted_operation_scope"))
        self.assertFalse(hasattr(result, "tool_invocation"))

    def test_workflow_retains_link_comparison_and_assembly_provenance(self) -> None:
        result = workflow().execute(workflow_request("pwm_no_tolerance"))
        link = result.engineering_context.cross_references[0]
        comparison = result.engineering_context.comparison_results[0]
        context = result.engineering_context
        self.assertEqual(link.workflow_id, "phase8b1-fixture")
        self.assertEqual(link.request_correlation_id, "request-1")
        self.assertEqual(link.measurement_channel, 1)
        self.assertEqual(link.confirmation_source, "TRUSTED_USER_EVENT")
        self.assertEqual(comparison.comparator_version, "1")
        self.assertEqual(context.assembler_version, "1")
        self.assertEqual(context.targets[0].source_evidence_ids[0], context.design_context.evidence[0].evidence_id)
        self.assertEqual(link.probe_target_id, context.design_context.probe_targets[0].target_id)
        self.assertEqual(comparison.observed_ref.measurement_context_id, context.measurement_context_id)
        self.assertLess(link.confirmed_at, link.measured_at)
        self.assertLess(link.measured_at, context.assembled_at)

    def test_categories_remain_distinct_end_to_end(self) -> None:
        result = workflow().execute(workflow_request("pwm_no_tolerance"))
        teaching = result.teaching_context
        self.assertTrue(all(item.locator.category is EvidenceCategory.PHYSICAL_FACT for item in teaching.physical_observations))
        self.assertTrue(all(item.locator.category is EvidenceCategory.SOFTWARE_ANALYSIS for item in teaching.software_analyses))
        self.assertEqual(teaching.simulated_evidence, ())


if __name__ == "__main__":
    unittest.main()
