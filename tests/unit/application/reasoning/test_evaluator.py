from __future__ import annotations

import unittest
from dataclasses import replace

from ai_instrument_assistant.application.reasoning import (
    ClaimDecision,
    ClaimForm,
    ClaimKind,
    ClaimReasonCode,
    ClaimSubjectKind,
    InferenceSufficiencyEvaluator,
    PublicationObligation,
    TeachingGoal,
    build_deterministic_fallback,
    comparison_subject_ref,
    context_fingerprint,
    measurement_subject_ref,
)
from ai_instrument_assistant.domain.engineering_evidence import ComparisonReason, EvidenceQuality
from tests.support.reasoning_policy import degraded_reasoning_context, reasoning_context


def permissions(envelope, kind, form=None, decision=None):
    return tuple(
        item
        for item in envelope.permissions
        if item.claim_kind is kind
        and (form is None or item.claim_form is form)
        and (decision is None or item.decision is decision)
    )


class InferenceSufficiencyEvaluatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evaluator = InferenceSufficiencyEvaluator()

    def test_evidence_restatements_bind_exact_source_and_provenance(self) -> None:
        envelope = self.evaluator.evaluate(reasoning_context(), TeachingGoal.ASSESS_REQUIREMENT)
        allowed = permissions(
            envelope,
            ClaimKind.EVIDENCE_RESTATEMENT,
            None,
            ClaimDecision.ALLOW,
        )
        self.assertTrue(
            any(
                item.subject.kind is ClaimSubjectKind.DESIGN_EVIDENCE
                and PublicationObligation.ATTRIBUTE_DESIGN_OBSERVATION in item.obligations
                for item in allowed
            )
        )
        self.assertTrue(
            any(
                item.subject.kind is ClaimSubjectKind.DESIGN_TARGET
                and PublicationObligation.ATTRIBUTE_USER_TARGET in item.obligations
                for item in allowed
            )
        )
        self.assertTrue(
            any(
                item.subject.kind is ClaimSubjectKind.MEASUREMENT_EVIDENCE
                and PublicationObligation.ATTRIBUTE_INSTRUMENT_SOURCE in item.obligations
                for item in allowed
            )
        )
        self.assertTrue(any(PublicationObligation.ATTRIBUTE_SOFTWARE_ANALYSIS in item.obligations for item in allowed))

    def test_user_target_cannot_become_jlceda_target(self) -> None:
        envelope = self.evaluator.evaluate(reasoning_context(), TeachingGoal.ASSESS_REQUIREMENT)
        targets = [
            item
            for item in permissions(envelope, ClaimKind.EVIDENCE_RESTATEMENT, ClaimForm.TARGET_VALUE, ClaimDecision.ALLOW)
        ]
        self.assertTrue(targets)
        self.assertTrue(all(PublicationObligation.ATTRIBUTE_USER_TARGET in item.obligations for item in targets))
        self.assertTrue(all(PublicationObligation.ATTRIBUTE_DESIGN_OBSERVATION not in item.obligations for item in targets))

    def test_no_tolerance_allows_indeterminate_explanation_but_blocks_compliance(self) -> None:
        envelope = self.evaluator.evaluate(reasoning_context(), TeachingGoal.ASSESS_REQUIREMENT)
        self.assertTrue(permissions(envelope, ClaimKind.DETERMINISTIC_COMPARISON_STATEMENT, ClaimForm.COMPLIANCE_UNDETERMINED, ClaimDecision.ALLOW))
        blocked = permissions(envelope, ClaimKind.DETERMINISTIC_COMPARISON_STATEMENT, ClaimForm.COMPLIANCE_VERDICT, ClaimDecision.BLOCK)
        self.assertTrue(blocked)
        self.assertTrue(all(ClaimReasonCode.ACCEPTANCE_CRITERION_UNAVAILABLE in item.reason_codes for item in blocked))

    def test_explicit_tolerance_mismatch_allows_outside_tolerance_only(self) -> None:
        context = reasoning_context("explicit_tolerance_mismatch")
        envelope = self.evaluator.evaluate(context, TeachingGoal.ASSESS_REQUIREMENT)
        outside = permissions(envelope, ClaimKind.DETERMINISTIC_COMPARISON_STATEMENT, ClaimForm.OUTSIDE_SPECIFIED_CRITERION, ClaimDecision.ALLOW)
        self.assertEqual(len(outside), 1)
        self.assertIn(ClaimReasonCode.EXISTING_COMPARISON_SUPPORTS_STATEMENT, outside[0].reason_codes)
        self.assertTrue(permissions(envelope, ClaimKind.CAUSAL_DIAGNOSIS, decision=ClaimDecision.BLOCK))

    def test_higher_reasoning_claims_default_block_without_reviewed_rules(self) -> None:
        envelope = self.evaluator.evaluate(reasoning_context(), TeachingGoal.EXPLAIN_CAUSE)
        expected = {
            ClaimKind.EDUCATIONAL_EXPLANATION: ClaimReasonCode.NO_REVIEWED_KNOWLEDGE_SOURCE,
            ClaimKind.ENGINEERING_INFERENCE: ClaimReasonCode.NO_REVIEWED_INFERENCE_RULE,
            ClaimKind.HYPOTHESIS: ClaimReasonCode.NO_REVIEWED_HYPOTHESIS_RULE,
            ClaimKind.CAUSAL_DIAGNOSIS: ClaimReasonCode.NO_REVIEWED_CAUSAL_RULE,
            ClaimKind.NEXT_MEASUREMENT_PROPOSAL: ClaimReasonCode.NEXT_MEASUREMENT_DEFERRED,
        }
        for kind, reason in expected.items():
            selected = permissions(envelope, kind)
            self.assertEqual(len(selected), 1)
            self.assertEqual(selected[0].decision, ClaimDecision.BLOCK)
            self.assertIn(reason, selected[0].reason_codes)

    def test_goal_is_monotonic_restrictive_and_never_creates_sufficiency(self) -> None:
        context = reasoning_context()
        for goal in TeachingGoal:
            envelope = self.evaluator.evaluate(context, goal)
            self.assertTrue(permissions(envelope, ClaimKind.CAUSAL_DIAGNOSIS, decision=ClaimDecision.BLOCK))
            self.assertTrue(permissions(envelope, ClaimKind.ENGINEERING_INFERENCE, decision=ClaimDecision.BLOCK))
            self.assertTrue(permissions(envelope, ClaimKind.DETERMINISTIC_COMPARISON_STATEMENT, ClaimForm.COMPLIANCE_VERDICT, ClaimDecision.BLOCK))
        explain = self.evaluator.evaluate(context, TeachingGoal.EXPLAIN_MEASUREMENT)
        self.assertFalse(permissions(explain, ClaimKind.DETERMINISTIC_COMPARISON_STATEMENT, ClaimForm.COMPARISON_STATUS, ClaimDecision.ALLOW))

    def test_degraded_restatement_requires_quality_and_exact_warning(self) -> None:
        envelope = self.evaluator.evaluate(degraded_reasoning_context(), TeachingGoal.EXPLAIN_MEASUREMENT)
        degraded = next(
            item
            for item in permissions(envelope, ClaimKind.EVIDENCE_RESTATEMENT, ClaimForm.EVIDENCE_VALUE, ClaimDecision.ALLOW)
            if PublicationObligation.PRESERVE_DEGRADED_QUALITY in item.obligations
        )
        self.assertIn(PublicationObligation.INCLUDE_MATERIAL_WARNINGS, degraded.obligations)
        self.assertTrue(degraded.obligation_refs)
        self.assertFalse(
            degraded.publication_prerequisites_satisfied(
                support_refs=degraded.support_refs,
                fulfilled_obligations=degraded.obligations,
                fulfilled_obligation_refs=(),
            )
        )
        self.assertTrue(
            degraded.publication_prerequisites_satisfied(
                support_refs=degraded.support_refs,
                fulfilled_obligations=degraded.obligations,
                fulfilled_obligation_refs=degraded.obligation_refs,
            )
        )

    def test_unavailable_evidence_has_no_value_permission(self) -> None:
        context = reasoning_context("unavailable_measurement")
        envelope = self.evaluator.evaluate(context, TeachingGoal.EXPLAIN_MEASUREMENT)
        unavailable_subjects = {
            item.subject
            for item in permissions(envelope, ClaimKind.EVIDENCE_RESTATEMENT, ClaimForm.EVIDENCE_AVAILABILITY, ClaimDecision.ALLOW)
        }
        self.assertTrue(unavailable_subjects)
        value_subjects = {
            item.subject
            for item in permissions(envelope, ClaimKind.EVIDENCE_RESTATEMENT, ClaimForm.EVIDENCE_VALUE, ClaimDecision.ALLOW)
        }
        self.assertTrue(unavailable_subjects.isdisjoint(value_subjects))
        self.assertFalse(
            permissions(
                envelope,
                ClaimKind.DETERMINISTIC_COMPARISON_STATEMENT,
                ClaimForm.OUTSIDE_SPECIFIED_CRITERION,
                ClaimDecision.ALLOW,
            )
        )

    def test_indeterminate_reason_is_preserved_and_not_rewritten_as_missing_tolerance(self) -> None:
        context = reasoning_context()
        original = context.comparisons[0]
        changed_comparison = replace(original, reason=ComparisonReason.MEASUREMENT_MISSING)
        changed = replace(
            context,
            comparisons=(changed_comparison,) + context.comparisons[1:],
        )
        envelope = self.evaluator.evaluate(changed, TeachingGoal.ASSESS_REQUIREMENT)
        subject = comparison_subject_ref(changed_comparison, context_fingerprint(changed))
        status = envelope.permission_for(
            ClaimKind.DETERMINISTIC_COMPARISON_STATEMENT,
            ClaimForm.COMPARISON_STATUS,
            subject,
        )
        self.assertEqual(status.decision, ClaimDecision.ALLOW)
        self.assertIn(PublicationObligation.PRESERVE_COMPARISON_REASON, status.obligations)
        fallback = build_deterministic_fallback(envelope)
        fallback_status = next(
            item
            for item in fallback.permissions
            if item.subject == subject and item.claim_form is ClaimForm.COMPARISON_STATUS
        )
        self.assertEqual(fallback_status, status)
        compliance = envelope.permission_for(
            ClaimKind.DETERMINISTIC_COMPARISON_STATEMENT,
            ClaimForm.COMPLIANCE_UNDETERMINED,
            subject,
        )
        self.assertEqual(compliance.decision, ClaimDecision.BLOCK)
        self.assertIn(
            ClaimReasonCode.COMPARISON_DOES_NOT_SUPPORT_CRITERION,
            compliance.reason_codes,
        )
        for form in (
            ClaimForm.WITHIN_SPECIFIED_CRITERION,
            ClaimForm.OUTSIDE_SPECIFIED_CRITERION,
            ClaimForm.COMPLIANCE_VERDICT,
        ):
            decision = envelope.permission_for(
                ClaimKind.DETERMINISTIC_COMPARISON_STATEMENT,
                form,
                subject,
            )
            self.assertEqual(decision.decision, ClaimDecision.BLOCK)
            self.assertIn(
                ClaimReasonCode.COMPARISON_DOES_NOT_SUPPORT_CRITERION,
                decision.reason_codes,
            )

    def test_comparison_reason_is_part_of_composite_content_identity(self) -> None:
        context = reasoning_context()
        fingerprint = context_fingerprint(context)
        original = context.comparisons[0]
        other_reason = replace(original, reason=ComparisonReason.MEASUREMENT_MISSING)
        self.assertNotEqual(
            comparison_subject_ref(original, fingerprint),
            comparison_subject_ref(other_reason, fingerprint),
        )

    def test_sequential_and_snapshot_obligations_prevent_overclaim(self) -> None:
        envelope = self.evaluator.evaluate(reasoning_context(), TeachingGoal.ASSESS_REQUIREMENT)
        measurement = permissions(envelope, ClaimKind.EVIDENCE_RESTATEMENT, ClaimForm.EVIDENCE_VALUE, ClaimDecision.ALLOW)
        self.assertTrue(any(PublicationObligation.DO_NOT_CLAIM_SIMULTANEOUS_OR_ATOMIC in item.obligations for item in measurement))
        design = next(item for item in measurement if item.subject.kind is ClaimSubjectKind.DESIGN_EVIDENCE)
        self.assertIn(PublicationObligation.PRESERVE_OBSERVATION_IDENTITY_LIMIT, design.obligations)
        self.assertIn(PublicationObligation.DO_NOT_CLAIM_DESIGN_IMMUTABILITY, design.obligations)

    def test_conflicting_sources_remain_independent_without_average_or_diagnosis(self) -> None:
        envelope = self.evaluator.evaluate(reasoning_context("conflicting_sources"), TeachingGoal.EXPLAIN_CAUSE)
        evidence = [
            item
            for item in permissions(envelope, ClaimKind.EVIDENCE_RESTATEMENT, ClaimForm.EVIDENCE_VALUE, ClaimDecision.ALLOW)
            if item.subject.kind is ClaimSubjectKind.MEASUREMENT_EVIDENCE
        ]
        self.assertEqual(len(evidence), 2)
        self.assertEqual(len({item.subject.canonical_key for item in evidence}), 2)
        self.assertTrue(permissions(envelope, ClaimKind.CAUSAL_DIAGNOSIS, decision=ClaimDecision.BLOCK))
        self.assertFalse(any("average" in item.subject.canonical_key for item in envelope.permissions))

    def test_comparison_refs_are_canonical_stable_and_non_collapsing(self) -> None:
        context = reasoning_context()
        fingerprint = context_fingerprint(context)
        first = comparison_subject_ref(context.comparisons[0], fingerprint)
        same = comparison_subject_ref(context.comparisons[0], fingerprint)
        other = comparison_subject_ref(context.comparisons[1], fingerprint)
        self.assertEqual(first, same)
        self.assertNotEqual(first, other)
        self.assertNotIn(context.comparisons[0].observed_ref.label, first.canonical_key)

    def test_display_label_is_not_measurement_subject_identity(self) -> None:
        context = reasoning_context()
        located = context.physical_observations[0]
        fingerprint = context_fingerprint(context)
        renamed = replace(located.locator, label="presentation changed")
        self.assertEqual(
            measurement_subject_ref(located.locator, fingerprint),
            measurement_subject_ref(renamed, fingerprint),
        )

    def test_display_label_does_not_change_context_or_subject_identity(self) -> None:
        context = reasoning_context()
        located = context.physical_observations[0]
        renamed = replace(
            located,
            locator=replace(located.locator, label="presentation changed"),
            item=replace(located.item, label="presentation changed"),
        )
        changed = replace(
            context,
            physical_observations=(renamed,) + context.physical_observations[1:],
        )
        self.assertEqual(context_fingerprint(context), context_fingerprint(changed))
        self.assertEqual(
            measurement_subject_ref(located.locator, context_fingerprint(context)),
            measurement_subject_ref(renamed.locator, context_fingerprint(changed)),
        )

    def test_free_text_goal_is_rejected_at_the_policy_boundary(self) -> None:
        with self.assertRaises(TypeError):
            self.evaluator.evaluate(reasoning_context(), "WHY_IS_PWM_WRONG")  # type: ignore[arg-type]

    def test_same_context_goal_and_policy_produce_identical_canonical_envelope(self) -> None:
        context = reasoning_context()
        first = self.evaluator.evaluate(context, TeachingGoal.ASSESS_REQUIREMENT)
        second = self.evaluator.evaluate(context, TeachingGoal.ASSESS_REQUIREMENT)
        self.assertEqual(first, second)
        self.assertEqual(
            first.permissions,
            tuple(sorted(first.permissions, key=lambda item: item.canonical_sort_key)),
        )

    def test_deterministic_fallback_contains_only_supported_bounded_categories(self) -> None:
        envelope = self.evaluator.evaluate(reasoning_context(), TeachingGoal.EXPLAIN_CAUSE)
        fallback = build_deterministic_fallback(envelope)
        self.assertTrue(fallback.permissions)
        self.assertTrue(all(item.decision is ClaimDecision.ALLOW for item in fallback.permissions))
        self.assertTrue(
            all(
                item.claim_kind
                in {
                    ClaimKind.EVIDENCE_RESTATEMENT,
                    ClaimKind.DETERMINISTIC_COMPARISON_STATEMENT,
                    ClaimKind.LIMITATION_STATEMENT,
                }
                for item in fallback.permissions
            )
        )
        self.assertFalse(hasattr(fallback, "model_text"))
        self.assertFalse(hasattr(fallback, "retry"))

    def test_reasoning_objects_expose_no_execution_authority(self) -> None:
        envelope = self.evaluator.evaluate(reasoning_context(), TeachingGoal.EXPLAIN_CAUSE)
        forbidden = {
            "tool",
            "execute",
            "invoke",
            "operation_scope",
            "probe_setup_confirmation",
            "physical_policy",
            "ipc",
            "budget",
        }
        self.assertTrue(forbidden.isdisjoint(set(dir(envelope))))


if __name__ == "__main__":
    unittest.main()
