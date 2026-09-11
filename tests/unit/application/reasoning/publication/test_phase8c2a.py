from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import unittest

from ai_instrument_assistant.application.reasoning import (
    ClaimDecision,
    ClaimForm,
    ClaimKind,
    ClaimReasonCode,
    InferenceSufficiencyEvaluator,
    PublicationObligation,
    TeachingGoal,
)
from ai_instrument_assistant.application.reasoning.publication import (
    CandidateParseError,
    DeterministicPublicationRenderer,
    EgressDecision,
    EngineeringClaimGroundingGuard,
    GovernedPublicationBoundary,
    PublicationBoundaryError,
    PublicationProjectionBuilder,
    permission_content_id,
)
from ai_instrument_assistant.protocol.teaching_claims import StrictCandidateParser
from ai_instrument_assistant.domain.engineering_evidence import ComparisonReason
from tests.support.reasoning_policy import degraded_reasoning_context, reasoning_context


ROOT = Path(__file__).resolve().parents[5]
PROTOCOL = ROOT / "protocols" / "teaching-claims" / "v1"


class RecordingEgress:
    def __init__(self, unsafe_when=lambda _text: False):
        self.calls: list[str] = []
        self.unsafe_when = unsafe_when

    def inspect(self, text: str, *, correlation_id: str) -> EgressDecision:
        self.calls.append(text)
        if self.unsafe_when(text):
            return EgressDecision.unsafe(("TEST_BLOCK",))
        return EgressDecision.safe()


def prepared(context=None, goal=TeachingGoal.ASSESS_REQUIREMENT):
    context = context or reasoning_context()
    envelope = InferenceSufficiencyEvaluator().evaluate(context, goal)
    projection = PublicationProjectionBuilder().build(context, envelope, goal)
    return context, envelope, projection


def candidate_json(projection, aliases, **changes):
    payload = {
        "schema_id": "aia-teaching-claim-candidate/v1",
        "projection_id": projection.projection_id,
        "context_fingerprint": projection.context_fingerprint,
        "envelope_id": projection.envelope_id,
        "goal": projection.goal.value,
        "ordered_permission_refs": list(aliases),
    }
    payload.update(changes)
    return json.dumps(payload, separators=(",", ":"))


def select_slot(projection, *, kind=None, form=None, source=None, reason=None):
    for slot in projection.slots:
        if kind is not None and slot.permission.claim_kind is not kind:
            continue
        if form is not None and slot.permission.claim_form is not form:
            continue
        if source is not None and slot.atom.source != source:
            continue
        if reason is not None and slot.atom.comparison_reason != reason:
            continue
        return slot
    raise AssertionError("matching slot not found")


class ProjectionTests(unittest.TestCase):
    def test_projection_is_immutable_bounded_and_exposes_only_allow_slots(self) -> None:
        context, envelope, projection = prepared()
        self.assertLessEqual(len(projection.slots), 64)
        self.assertTrue(all(slot.permission.decision is ClaimDecision.ALLOW for slot in projection.slots))
        self.assertEqual(len({slot.alias for slot in projection.slots}), len(projection.slots))
        self.assertEqual(projection.context_fingerprint, envelope.context_fingerprint)
        with self.assertRaises(FrozenInstanceError):
            projection.projection_id = "changed"  # type: ignore[misc]

        model_json = json.dumps(projection.model_payload(), sort_keys=True)
        for forbidden in ("native_id", "VISA", "SCPI", "waveform", "TrustedOperationScope"):
            self.assertNotIn(forbidden, model_json)
        self.assertNotIn("10020", model_json)

    def test_permission_content_identity_binds_complete_semantics(self) -> None:
        _, envelope, _ = prepared()
        permission = next(item for item in envelope.permissions if item.decision is ClaimDecision.ALLOW)
        original = permission_content_id(envelope, permission)
        mutations = (
            replace(permission, obligations=permission.obligations + (PublicationObligation.ATTRIBUTE_USER_STATEMENT,)),
            replace(permission, policy_version="2"),
            replace(permission, reason_codes=(ClaimReasonCode.GOAL_NOT_RELEVANT,)),
            replace(
                permission,
                support_refs=(replace(permission.subject, canonical_key=permission.subject.canonical_key + ":changed"),),
            ),
        )
        for changed in mutations:
            with self.subTest(changed=changed):
                self.assertNotEqual(original, permission_content_id(envelope, changed))
        self.assertIn("content identity", (permission_content_id.__doc__ or "").lower())

    def test_same_input_has_stable_projection_and_aliases(self) -> None:
        context, envelope, first = prepared()
        second = PublicationProjectionBuilder().build(context, envelope, TeachingGoal.ASSESS_REQUIREMENT)
        self.assertEqual(first, second)
        self.assertEqual(first.projection_id, second.projection_id)

    def test_stale_or_mutated_envelope_is_rejected_before_projection(self) -> None:
        context, envelope, _ = prepared()
        mutated = replace(envelope, goal=TeachingGoal.EXPLAIN_CAUSE)
        with self.assertRaises(PublicationBoundaryError):
            PublicationProjectionBuilder().build(context, mutated, TeachingGoal.ASSESS_REQUIREMENT)

    def test_projection_slot_limit_fails_closed(self) -> None:
        context = reasoning_context()
        envelope = InferenceSufficiencyEvaluator().evaluate(context, TeachingGoal.ASSESS_REQUIREMENT)
        with self.assertRaises(PublicationBoundaryError):
            PublicationProjectionBuilder(max_slots=1).build(
                context, envelope, TeachingGoal.ASSESS_REQUIREMENT
            )


class StrictParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = StrictCandidateParser(PROTOCOL)
        _, _, self.projection = prepared()
        self.valid = candidate_json(self.projection, (self.projection.slots[0].alias,))

    def test_valid_minimal_candidate_parses(self) -> None:
        parsed = self.parser.parse(self.valid)
        self.assertEqual(parsed.ordered_permission_refs, (self.projection.slots[0].alias,))
        self.assertFalse(hasattr(parsed, "text"))
        self.assertFalse(hasattr(parsed, "diagnosis"))

    def test_strict_syntax_and_shape_rejections(self) -> None:
        invalid = {
            "empty": "",
            "markdown": f"```json\n{self.valid}\n```",
            "prefix": "answer: " + self.valid,
            "suffix": self.valid + " trailing",
            "multiple": self.valid + self.valid,
            "duplicate_key": self.valid[:-1] + ',"goal":"ASSESS_REQUIREMENT"}',
            "unknown": candidate_json(self.projection, ("p001",), diagnosis="invented"),
            "wrong_type": candidate_json(self.projection, ("p001",), ordered_permission_refs="p001"),
            "duplicate_ref": candidate_json(self.projection, ("p001", "p001")),
            "arbitrary_value": candidate_json(self.projection, ("p001",), value=10000),
            "tool": candidate_json(self.projection, ("p001",), action={"tool": "anything"}),
        }
        for name, raw in invalid.items():
            with self.subTest(name=name), self.assertRaises(CandidateParseError):
                self.parser.parse(raw)

    def test_size_and_candidate_count_are_bounded(self) -> None:
        with self.assertRaises(CandidateParseError):
            self.parser.parse(" " * 16_385)
        with self.assertRaises(CandidateParseError):
            self.parser.parse(candidate_json(self.projection, tuple(f"p{i:03d}" for i in range(1, 14))))


class GroundingAndRenderingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context, self.envelope, self.projection = prepared()
        self.parser = StrictCandidateParser(PROTOCOL)
        self.guard = EngineeringClaimGroundingGuard()
        self.renderer = DeterministicPublicationRenderer()

    def ground(self, aliases, projection=None, **changes):
        projection = projection or self.projection
        candidate = self.parser.parse(candidate_json(projection, aliases, **changes))
        return self.guard.ground(
            self.context,
            self.envelope,
            TeachingGoal.ASSESS_REQUIREMENT,
            projection,
            candidate,
        )

    def test_valid_slots_render_from_trusted_atoms_in_candidate_order(self) -> None:
        physical = select_slot(self.projection, kind=ClaimKind.EVIDENCE_RESTATEMENT, source="INSTRUMENT")
        software = select_slot(self.projection, kind=ClaimKind.EVIDENCE_RESTATEMENT, source="SOFTWARE_ANALYSIS")
        plan = self.ground((software.alias, physical.alias))
        text = self.renderer.render(plan)
        self.assertLess(text.index("Software analysis"), text.index("Instrument measurement"))
        self.assertIn("10020 Hz", text)
        self.assertEqual(text, self.renderer.render(plan))
        self.assertNotIn(software.alias, text)

    def test_target_design_snapshot_limit_and_limitation_render(self) -> None:
        target = select_slot(self.projection, form=ClaimForm.TARGET_VALUE)
        design = select_slot(self.projection, source="DESIGN_OBSERVATION")
        limitation = select_slot(self.projection, kind=ClaimKind.LIMITATION_STATEMENT, source="LIMITATION")
        text = self.renderer.render(self.ground((target.alias, design.alias, limitation.alias)))
        self.assertIn("User-provided target", text)
        self.assertIn("does not prove design immutability", text)
        self.assertIn("Limitation:", text)

    def test_reason_sensitive_comparison_templates(self) -> None:
        no_tolerance = select_slot(
            self.projection,
            form=ClaimForm.COMPLIANCE_UNDETERMINED,
            reason=ComparisonReason.TOLERANCE_UNSPECIFIED.value,
        )
        text = self.renderer.render(self.ground((no_tolerance.alias,)))
        self.assertIn("no explicit tolerance", text)
        self.assertIn("cannot be determined", text)

        changed_comparison = replace(
            self.context.comparisons[0],
            observed_ref=None,
            observed=None,
            difference=None,
            relative_difference=None,
            reason=ComparisonReason.MEASUREMENT_MISSING,
        )
        changed_context = replace(self.context, comparisons=(changed_comparison,) + self.context.comparisons[1:])
        context, envelope, projection = prepared(changed_context)
        status = select_slot(projection, form=ClaimForm.COMPARISON_STATUS, reason="MEASUREMENT_MISSING")
        candidate = self.parser.parse(candidate_json(projection, (status.alias,)))
        plan = self.guard.ground(context, envelope, TeachingGoal.ASSESS_REQUIREMENT, projection, candidate)
        changed_text = self.renderer.render(plan)
        self.assertIn("measurement is missing", changed_text)
        self.assertNotIn("no explicit tolerance", changed_text)

    def test_unavailable_evidence_cannot_render_a_value(self) -> None:
        context, envelope, projection = prepared(
            reasoning_context("unavailable_measurement"),
            TeachingGoal.EXPLAIN_MEASUREMENT,
        )
        unavailable = select_slot(projection, form=ClaimForm.EVIDENCE_AVAILABILITY)
        candidate = self.parser.parse(candidate_json(projection, (unavailable.alias,)))
        plan = self.guard.ground(
            context,
            envelope,
            TeachingGoal.EXPLAIN_MEASUREMENT,
            projection,
            candidate,
        )
        text = self.renderer.render(plan)
        self.assertIn("is unavailable", text)
        self.assertNotIn(" = ", text)

    def test_explicit_tolerance_mismatch_renders_no_diagnosis(self) -> None:
        context, envelope, projection = prepared(reasoning_context("explicit_tolerance_mismatch"))
        outside = select_slot(projection, form=ClaimForm.OUTSIDE_SPECIFIED_CRITERION)
        candidate = self.parser.parse(candidate_json(projection, (outside.alias,)))
        plan = self.guard.ground(context, envelope, TeachingGoal.ASSESS_REQUIREMENT, projection, candidate)
        text = self.renderer.render(plan)
        self.assertIn("outside the specified tolerance", text)
        self.assertNotIn("caused", text.lower())
        self.assertNotIn("fault", text.lower())

    def test_degraded_warning_and_sequential_obligations_are_automatic(self) -> None:
        context, envelope, projection = prepared(degraded_reasoning_context(), TeachingGoal.EXPLAIN_MEASUREMENT)
        degraded = select_slot(projection, kind=ClaimKind.EVIDENCE_RESTATEMENT, source="INSTRUMENT")
        candidate = self.parser.parse(candidate_json(projection, (degraded.alias,)))
        plan = self.guard.ground(context, envelope, TeachingGoal.EXPLAIN_MEASUREMENT, projection, candidate)
        text = self.renderer.render(plan)
        self.assertIn("Quality: degraded", text)
        self.assertIn("Recorded waveform quality is degraded", text)
        self.assertIn("not simultaneous or atomic", text)

    def test_all_binding_and_alias_failures_reject_whole_candidate(self) -> None:
        alias = self.projection.slots[0].alias
        mismatches = (
            {"projection_id": "sha256:" + "1" * 64},
            {"context_fingerprint": "sha256:" + "2" * 64},
            {"envelope_id": "sha256:" + "3" * 64},
            {"goal": TeachingGoal.EXPLAIN_CAUSE.value},
        )
        for changes in mismatches:
            with self.subTest(changes=changes), self.assertRaises(PublicationBoundaryError):
                self.ground((alias,), **changes)
        with self.assertRaises(PublicationBoundaryError):
            self.ground(("p999",))

        other_context = replace(self.context, limitations=self.context.limitations + ("Another projection.",))
        _, _, other_projection = prepared(other_context)
        foreign = self.parser.parse(candidate_json(other_projection, (other_projection.slots[0].alias,)))
        with self.assertRaises(PublicationBoundaryError):
            self.guard.ground(
                self.context,
                self.envelope,
                TeachingGoal.ASSESS_REQUIREMENT,
                self.projection,
                foreign,
            )

    def test_permission_or_template_mutation_is_rejected(self) -> None:
        slot = self.projection.slots[0]
        changed_permission = replace(slot.permission, policy_version="mutated")
        changed_slot = replace(slot, permission=changed_permission)
        changed_projection = replace(self.projection, slots=(changed_slot,) + self.projection.slots[1:])
        with self.assertRaises(PublicationBoundaryError):
            self.ground((slot.alias,), projection=changed_projection)

        source_slot = select_slot(self.projection, source="INSTRUMENT")
        missing_coverage = replace(source_slot, renderable_obligations=())
        broken = replace(
            self.projection,
            slots=tuple(missing_coverage if item.alias == source_slot.alias else item for item in self.projection.slots),
        )
        with self.assertRaises(PublicationBoundaryError):
            self.ground((source_slot.alias,), projection=broken)

        degraded_context, degraded_envelope, degraded_projection = prepared(
            degraded_reasoning_context(), TeachingGoal.EXPLAIN_MEASUREMENT
        )
        degraded_slot = select_slot(degraded_projection, source="INSTRUMENT")
        missing_warning_coverage = replace(
            degraded_slot,
            renderable_obligations=tuple(
                item
                for item in degraded_slot.renderable_obligations
                if item is not PublicationObligation.INCLUDE_MATERIAL_WARNINGS
            ),
        )
        broken_degraded = replace(
            degraded_projection,
            slots=tuple(
                missing_warning_coverage if item.alias == degraded_slot.alias else item
                for item in degraded_projection.slots
            ),
        )
        candidate = self.parser.parse(candidate_json(broken_degraded, (degraded_slot.alias,)))
        with self.assertRaises(PublicationBoundaryError):
            self.guard.ground(
                degraded_context,
                degraded_envelope,
                TeachingGoal.EXPLAIN_MEASUREMENT,
                broken_degraded,
                candidate,
            )

    def test_blocked_and_unsupported_permissions_cannot_be_exposed(self) -> None:
        self.assertTrue(all(slot.permission.decision is ClaimDecision.ALLOW for slot in self.projection.slots))
        self.assertTrue(
            all(
                slot.permission.claim_kind
                in {
                    ClaimKind.EVIDENCE_RESTATEMENT,
                    ClaimKind.DETERMINISTIC_COMPARISON_STATEMENT,
                    ClaimKind.LIMITATION_STATEMENT,
                }
                for slot in self.projection.slots
            )
        )
        blocked = next(item for item in self.envelope.permissions if item.decision is ClaimDecision.BLOCK)
        first = self.projection.slots[0]
        forged_slot = replace(
            first,
            permission=blocked,
            permission_content_id=permission_content_id(self.envelope, blocked),
        )
        forged_projection = replace(
            self.projection,
            slots=(forged_slot,) + self.projection.slots[1:],
        )
        forged_candidate = self.parser.parse(candidate_json(forged_projection, (forged_slot.alias,)))
        with self.assertRaises(PublicationBoundaryError):
            self.guard.ground(
                self.context,
                self.envelope,
                TeachingGoal.ASSESS_REQUIREMENT,
                forged_projection,
                forged_candidate,
            )


class GovernedPublicationTests(unittest.TestCase):
    def test_valid_publication_and_invalid_candidate_fallback_both_use_final_egress(self) -> None:
        context, envelope, projection = prepared()
        selected = select_slot(projection, source="INSTRUMENT")
        egress = RecordingEgress()
        boundary = GovernedPublicationBoundary(egress, StrictCandidateParser(PROTOCOL))
        result = boundary.publish(
            context=context,
            envelope=envelope,
            goal=TeachingGoal.ASSESS_REQUIREMENT,
            projection=projection,
            raw_candidate=candidate_json(projection, (selected.alias,)),
            correlation_id="phase8c2a-test",
        )
        self.assertEqual(result.status, "PUBLISHED")
        self.assertFalse(result.audit.fallback_used)
        self.assertEqual(len(egress.calls), 1)

        fallback = boundary.publish(
            context=context,
            envelope=envelope,
            goal=TeachingGoal.ASSESS_REQUIREMENT,
            projection=projection,
            raw_candidate="not json",
            correlation_id="phase8c2a-test",
        )
        self.assertEqual(fallback.status, "FALLBACK_PUBLISHED")
        self.assertTrue(fallback.audit.fallback_used)
        self.assertNotIn("not json", fallback.text)

    def test_final_egress_rejection_uses_one_terminal_fallback_without_recursion(self) -> None:
        context, envelope, projection = prepared()
        selected = select_slot(projection, source="INSTRUMENT")
        egress = RecordingEgress(lambda text: "Instrument measurement" in text)
        result = GovernedPublicationBoundary(egress, StrictCandidateParser(PROTOCOL)).publish(
            context=context,
            envelope=envelope,
            goal=TeachingGoal.ASSESS_REQUIREMENT,
            projection=projection,
            raw_candidate=candidate_json(projection, (selected.alias,)),
            correlation_id="phase8c2a-test",
        )
        self.assertEqual(result.status, "TERMINAL_FALLBACK_PUBLISHED")
        self.assertEqual(len(egress.calls), 2)
        self.assertNotIn("Instrument measurement", result.text)

    def test_fallback_never_contains_stronger_claim_kinds(self) -> None:
        context, envelope, projection = prepared()
        result = GovernedPublicationBoundary(RecordingEgress(), StrictCandidateParser(PROTOCOL)).publish(
            context=context,
            envelope=envelope,
            goal=TeachingGoal.ASSESS_REQUIREMENT,
            projection=projection,
            raw_candidate="{}",
            correlation_id="phase8c2a-test",
        )
        self.assertNotIn("hypothesis", result.text.lower())
        self.assertNotIn("diagnosis", result.text.lower())
        self.assertNotIn("next measurement", result.text.lower())
        self.assertEqual(result.audit.model_request_count, 0)
        self.assertEqual(result.audit.tool_count, 0)
        self.assertEqual(result.audit.ipc_count, 0)
        self.assertEqual(result.audit.hardware_count, 0)

    def test_adversarial_candidates_all_fail_whole_to_deterministic_fallback(self) -> None:
        context, envelope, projection = prepared()
        selected = projection.slots[0].alias
        base = candidate_json(projection, (selected,))
        attempts = (
            "```json\n" + base + "\n```",
            base + " trailing",
            candidate_json(projection, ("p999",)),
            candidate_json(projection, (selected,), source="instrument"),
            candidate_json(projection, (selected,), value=12345),
            candidate_json(projection, (selected,), prose="invented answer"),
            candidate_json(projection, (selected,), diagnosis="fault"),
            candidate_json(projection, (selected,), action={"tool": "measure"}),
            candidate_json(projection, (selected,), comparison_status="MATCH"),
            candidate_json(projection, (selected,), comparison_reason="WITHIN_TOLERANCE"),
            candidate_json(projection, (selected,), simultaneous=True),
            candidate_json(projection, (selected,), native_revision="invented"),
        )
        for raw in attempts:
            with self.subTest(raw=raw[:30]):
                egress = RecordingEgress()
                result = GovernedPublicationBoundary(egress, StrictCandidateParser(PROTOCOL)).publish(
                    context=context,
                    envelope=envelope,
                    goal=TeachingGoal.ASSESS_REQUIREMENT,
                    projection=projection,
                    raw_candidate=raw,
                    correlation_id="phase8c2a-adversarial",
                )
                self.assertEqual(result.status, "FALLBACK_PUBLISHED")
                self.assertTrue(result.audit.fallback_used)
                self.assertNotIn(raw, result.text)
                self.assertEqual(result.audit.model_request_count, 0)
                self.assertEqual(result.audit.tool_count, 0)
                self.assertEqual(result.audit.ipc_count, 0)
                self.assertEqual(result.audit.hardware_count, 0)


if __name__ == "__main__":
    unittest.main()
