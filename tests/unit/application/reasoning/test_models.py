from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError, replace
from inspect import getdoc

from ai_instrument_assistant.application.reasoning import (
    AllowedClaimEnvelope,
    ClaimDecision,
    ClaimForm,
    ClaimKind,
    ClaimReasonCode,
    ClaimSubjectKind,
    ClaimSubjectRef,
    ClaimSupportBasis,
    PublicationObligation,
    TeachingGoal,
)


class ReasoningPolicyModelTests(unittest.TestCase):
    def test_claim_kinds_are_independent_from_evidence_categories(self) -> None:
        self.assertEqual(
            {kind.value for kind in ClaimKind},
            {
                "EVIDENCE_RESTATEMENT",
                "DETERMINISTIC_COMPARISON_STATEMENT",
                "LIMITATION_STATEMENT",
                "EDUCATIONAL_EXPLANATION",
                "ENGINEERING_INFERENCE",
                "HYPOTHESIS",
                "CAUSAL_DIAGNOSIS",
                "NEXT_MEASUREMENT_PROPOSAL",
            },
        )
        self.assertNotIn("PHYSICAL_FACT", {kind.value for kind in ClaimKind})
        self.assertNotIn("SOFTWARE_ANALYSIS", {kind.value for kind in ClaimKind})

    def test_subject_identity_is_context_bound_and_not_display_text(self) -> None:
        subject = ClaimSubjectRef(
            context_fingerprint="sha256:" + "a" * 64,
            kind=ClaimSubjectKind.MEASUREMENT_EVIDENCE,
            canonical_key="measurement:context/facts/0/FREQUENCY/PHYSICAL_FACT",
        )
        self.assertFalse(hasattr(subject, "display_text"))
        with self.assertRaises(FrozenInstanceError):
            subject.canonical_key = "changed"  # type: ignore[misc]

    def test_envelope_and_permissions_are_deeply_immutable(self) -> None:
        subject = ClaimSubjectRef(
            context_fingerprint="sha256:" + "a" * 64,
            kind=ClaimSubjectKind.CONTEXT,
            canonical_key="context",
        )
        from ai_instrument_assistant.application.reasoning import ClaimPermission

        permission = ClaimPermission(
            claim_kind=ClaimKind.CAUSAL_DIAGNOSIS,
            claim_form=ClaimForm.CAUSAL_EXPLANATION,
            subject=subject,
            decision=ClaimDecision.BLOCK,
            support_basis=ClaimSupportBasis.INSUFFICIENT,
            reason_codes=(ClaimReasonCode.NO_REVIEWED_CAUSAL_RULE,),
            support_refs=(),
            obligations=(),
            obligation_refs=(),
            policy_name="aia.inference-sufficiency",
            policy_version="1",
        )
        envelope = AllowedClaimEnvelope.create(
            context_fingerprint=subject.context_fingerprint,
            goal=TeachingGoal.EXPLAIN_CAUSE,
            policy_name="aia.inference-sufficiency",
            policy_version="1",
            permissions=(permission,),
            unresolved_question_refs=(),
        )
        self.assertIsInstance(envelope.permissions, tuple)
        with self.assertRaises(FrozenInstanceError):
            envelope.goal = TeachingGoal.EXPLAIN_MEASUREMENT  # type: ignore[misc]

    def test_allow_requires_concrete_support_and_obligations(self) -> None:
        from ai_instrument_assistant.application.reasoning import ClaimPermission

        subject = ClaimSubjectRef(
            context_fingerprint="sha256:" + "a" * 64,
            kind=ClaimSubjectKind.MEASUREMENT_EVIDENCE,
            canonical_key="measurement:one",
        )
        permission = ClaimPermission(
            claim_kind=ClaimKind.EVIDENCE_RESTATEMENT,
            claim_form=ClaimForm.EVIDENCE_VALUE,
            subject=subject,
            decision=ClaimDecision.ALLOW,
            support_basis=ClaimSupportBasis.EXACT_RESTATEMENT,
            reason_codes=(ClaimReasonCode.EXACT_EVIDENCE_AVAILABLE,),
            support_refs=(subject,),
            obligations=(PublicationObligation.ATTRIBUTE_INSTRUMENT_SOURCE,),
            obligation_refs=(),
            policy_name="aia.inference-sufficiency",
            policy_version="1",
        )
        self.assertFalse(
            permission.publication_prerequisites_satisfied(
                support_refs=(subject,), fulfilled_obligations=()
            )
        )
        self.assertTrue(
            permission.publication_prerequisites_satisfied(
                support_refs=(subject,),
                fulfilled_obligations=(PublicationObligation.ATTRIBUTE_INSTRUMENT_SOURCE,),
            )
        )
        self.assertFalse(hasattr(permission, "can_publish"))
        self.assertFalse(hasattr(permission, "is_publishable"))

    def test_wrong_source_attribution_and_wrong_support_do_not_publish(self) -> None:
        from ai_instrument_assistant.application.reasoning import ClaimPermission

        subject = ClaimSubjectRef(
            context_fingerprint="sha256:" + "a" * 64,
            kind=ClaimSubjectKind.MEASUREMENT_EVIDENCE,
            canonical_key="measurement:software-analysis",
        )
        other = replace(subject, canonical_key="measurement:other")
        permission = ClaimPermission(
            claim_kind=ClaimKind.EVIDENCE_RESTATEMENT,
            claim_form=ClaimForm.EVIDENCE_VALUE,
            subject=subject,
            decision=ClaimDecision.ALLOW,
            support_basis=ClaimSupportBasis.EXACT_RESTATEMENT,
            reason_codes=(ClaimReasonCode.EXACT_EVIDENCE_AVAILABLE,),
            support_refs=(subject,),
            obligations=(PublicationObligation.ATTRIBUTE_SOFTWARE_ANALYSIS,),
            obligation_refs=(),
            policy_name="aia.inference-sufficiency",
            policy_version="1",
        )
        self.assertFalse(
            permission.publication_prerequisites_satisfied(
                support_refs=(subject,),
                fulfilled_obligations=(PublicationObligation.ATTRIBUTE_INSTRUMENT_SOURCE,),
            )
        )
        self.assertFalse(
            permission.publication_prerequisites_satisfied(
                support_refs=(other,),
                fulfilled_obligations=(PublicationObligation.ATTRIBUTE_SOFTWARE_ANALYSIS,),
            )
        )

    def test_sha256_values_are_documented_as_content_identity_only(self) -> None:
        from ai_instrument_assistant.application.reasoning import (
            ClaimPermission,
            comparison_subject_ref,
            context_fingerprint,
        )

        for value in (
            ClaimSubjectRef,
            AllowedClaimEnvelope,
            ClaimPermission,
            context_fingerprint,
            comparison_subject_ref,
        ):
            documentation = (getdoc(value) or "").lower()
            self.assertIn("content identity", documentation)
            self.assertIn("not", documentation)

        subject = ClaimSubjectRef(
            context_fingerprint="sha256:" + "a" * 64,
            kind=ClaimSubjectKind.CONTEXT,
            canonical_key="context",
        )
        envelope = AllowedClaimEnvelope.create(
            context_fingerprint=subject.context_fingerprint,
            goal=TeachingGoal.EXPLAIN_MEASUREMENT,
            policy_name="aia.inference-sufficiency",
            policy_version="1",
            permissions=(),
            unresolved_question_refs=(),
        )
        authority_markers = {
            "authenticate",
            "authorize",
            "is_trusted",
            "is_fresh",
            "verify_signature",
        }
        self.assertTrue(authority_markers.isdisjoint(dir(subject)))
        self.assertTrue(authority_markers.isdisjoint(dir(envelope)))

    def test_unknown_or_stale_subject_is_blocked(self) -> None:
        subject = ClaimSubjectRef(
            context_fingerprint="sha256:" + "a" * 64,
            kind=ClaimSubjectKind.CONTEXT,
            canonical_key="context",
        )
        envelope = AllowedClaimEnvelope.create(
            context_fingerprint=subject.context_fingerprint,
            goal=TeachingGoal.EXPLAIN_MEASUREMENT,
            policy_name="aia.inference-sufficiency",
            policy_version="1",
            permissions=(),
            unresolved_question_refs=(),
        )
        unknown = replace(subject, canonical_key="unknown")
        stale = replace(subject, context_fingerprint="sha256:" + "b" * 64)
        for candidate in (unknown, stale):
            decision = envelope.permission_for(
                ClaimKind.EVIDENCE_RESTATEMENT,
                ClaimForm.EVIDENCE_VALUE,
                candidate,
            )
            self.assertEqual(decision.decision, ClaimDecision.BLOCK)
            self.assertIn(ClaimReasonCode.UNKNOWN_OR_STALE_SUBJECT, decision.reason_codes)


if __name__ == "__main__":
    unittest.main()
